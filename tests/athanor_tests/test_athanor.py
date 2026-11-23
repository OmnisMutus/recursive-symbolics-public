"""athanor tests. Ground truth: mini_oss.gguf, a small gpt-oss-shaped model written by the official `gguf`
package (llama.cpp's Python library): F32 router (ffn_gate_inp), BF16 attention, F16 norms, MXFP4 experts quantized
from real numbers. mini_oss_expected.npz holds that package's own decoding of every tensor, and its own BF16
rounding of attn_q x 0.9. Everything else is checked against those, or by byte-for-byte comparison of the file."""
import hashlib
import json
import os
import re
import shutil
import struct
import tempfile
import unittest
from unittest import mock

try:
    import numpy as np
except ImportError:  # athanor's codec and edits need NumPy; reading and the journal do not. Skipped, never passed.
    raise unittest.SkipTest("NumPy is not installed: athanor/codec.py and athanor/edits.py need it")

from athanor import cli, codec, edits, gguf, ollama, workshop

FX = os.path.join(os.path.dirname(__file__), "fixtures")
MINI = os.path.join(FX, "mini_oss.gguf")
EXP = np.load(os.path.join(FX, "mini_oss_expected.npz"))


def sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def tensor_values(path, name, expert=None):
    info = gguf.read(path)
    t = gguf.tensor(info, name)
    with open(path, "rb") as fh:
        raw = fh.read()[t["start"]:t["end"]]
    return codec.decode(raw, t["type"])


class Base(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        gguf._CACHE.clear()
        self.v = os.path.join(self.d, "vessels", "mini.gguf")
        workshop.create(MINI, self.v, verify=False)

    def tearDown(self):
        gguf._CACHE.clear()
        shutil.rmtree(self.d, ignore_errors=True)


class TestDecode(unittest.TestCase):
    def test_matches_the_official_decoder(self):
        info = gguf.read(MINI)
        for t in info["tensors"]:
            with self.subTest(t=t["name"], type=t["type"]):
                np.testing.assert_array_equal(tensor_values(MINI, t["name"]), EXP[t["name"]])

    def test_bf16_rounding_matches(self):
        v = EXP["blk.0.attn_q.weight"] * np.float32(0.9)
        self.assertEqual(codec.bf16_from_f32(v).astype("<u2").tobytes(), EXP["blk.0.attn_q.weight@x0.9"].tobytes())


class TestScale(Base):
    def test_bf16_scaled_like_the_package(self):
        edits.scale(self.v, "blk.0.attn_q.weight", 0.9)
        info = gguf.read(self.v)
        t = gguf.tensor(info, "blk.0.attn_q.weight")
        self.assertEqual(open(self.v, "rb").read()[t["start"]:t["end"]], EXP["blk.0.attn_q.weight@x0.9"].tobytes())

    def test_mxfp4_powers_of_two_exact(self):
        name = "blk.1.ffn_up_exps.weight"
        edits.scale(self.v, name, 0.5)
        np.testing.assert_array_equal(tensor_values(self.v, name), EXP[name] * np.float32(0.5))
        r = edits.scale(self.v, name, 4)
        np.testing.assert_array_equal(tensor_values(self.v, name), EXP[name] * np.float32(2))
        self.assertGreater(r["blocks_moved"], 0)
        for bad in (3, 0.9, -2):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                edits.scale(self.v, name, bad)

    def test_one_expert_only(self):
        name = "blk.0.ffn_up_exps.weight"
        before = EXP[name].reshape(4, -1)
        edits.scale(self.v, name, 0, expert=2)
        after = tensor_values(self.v, name).reshape(4, -1)
        np.testing.assert_array_equal(after[[0, 1, 3]], before[[0, 1, 3]])
        self.assertTrue(np.all(after[2] == 0))
        self.assertEqual(edits.values(self.v, name, expert=2)["zeros"], 4096)

    def test_f16_and_f32(self):
        edits.scale(self.v, "blk.0.attn_norm.weight", 2)
        np.testing.assert_array_equal(tensor_values(self.v, "blk.0.attn_norm.weight"), EXP["blk.0.attn_norm.weight"] * 2)
        with self.assertRaises(ValueError):                              # 1000 x 100 overflows half precision (65504)
            codec.scaled(np.array([1000.0], dtype="<f2").tobytes(), "F16", 100)
        edits.scale(self.v, "blk.1.ffn_gate_inp.weight", 1.5)
        np.testing.assert_allclose(tensor_values(self.v, "blk.1.ffn_gate_inp.weight"),
                                   EXP["blk.1.ffn_gate_inp.weight"] * np.float32(1.5), rtol=0, atol=0)
        for bad in (float("nan"), float("inf"), 1e-9, 1e9):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                edits.scale(self.v, "blk.1.ffn_gate_inp.weight", bad)


class TestRouter(Base):
    def test_bias_off_add_set(self):
        b0 = EXP["blk.1.ffn_gate_inp.bias"]
        r = edits.router_bias(self.v, 1, 3, off=True)
        self.assertEqual((r["before"], r["after"]), (float(b0[3]), edits.OFF))
        edits.router_bias(self.v, 1, 0, add=0.25)
        got = tensor_values(self.v, "blk.1.ffn_gate_inp.bias")
        np.testing.assert_array_equal(got, np.array([b0[0] + np.float32(0.25), b0[1], b0[2], edits.OFF], dtype=np.float32))
        np.testing.assert_array_equal(tensor_values(self.v, "blk.0.ffn_gate_inp.bias"), EXP["blk.0.ffn_gate_inp.bias"])
        with self.assertRaises(ValueError):
            edits.router_bias(self.v, 1, 4, off=True)                    # only experts 0-3
        with self.assertRaises(KeyError):
            edits.router_bias(self.v, 7, 0, off=True)                    # no layer 7


class TestJournal(Base):
    def test_undo_restores_every_byte(self):
        orig = sha(MINI)
        edits.router_bias(self.v, 0, 1, off=True)
        edits.scale(self.v, "blk.0.attn_q.weight", 0.9)
        edits.scale(self.v, "blk.1.ffn_up_exps.weight", 2, expert=0)
        self.assertNotEqual(sha(self.v), orig)
        self.assertEqual([r["id"] for r in workshop.journal(self.v)], [1, 2, 3])
        self.assertEqual(workshop.undo(self.v, "last"), [3])
        self.assertEqual(workshop.undo(self.v, "all"), [2, 1])
        self.assertEqual(sha(self.v), orig)
        self.assertTrue(workshop.pristine(self.v))
        self.assertEqual(workshop.undo(self.v), [])

    def test_undo_order_and_tampering(self):
        edits.scale(self.v, "blk.0.attn_q.weight", 0.5)
        edits.scale(self.v, "blk.0.attn_q.weight", 0.5)
        with self.assertRaises(ValueError):
            workshop.undo(self.v, "1")                                   # #2 changed the same tensor after it
        t = gguf.tensor(gguf.read(self.v), "blk.0.attn_q.weight")
        with open(self.v, "r+b") as fh:                                  # someone edits the vessel behind our back
            fh.seek(t["start"])
            fh.write(b"\x00\x00")
        with self.assertRaises(ValueError):
            workshop.undo(self.v, "last")
        self.assertFalse(workshop.journal(self.v)[-1]["undone"])

    def test_refusals(self):
        info = gguf.read(self.v)
        with self.assertRaises(PermissionError):
            workshop.write(self.v, 8, b"\x00\x00\x00\x00", "header", info)          # inside the header
        t = gguf.tensor(info, "blk.0.ffn_gate_inp.bias")
        with self.assertRaises(PermissionError):
            workshop.write(self.v, t["end"] - 2, b"\x00" * 8, "spill", info)        # runs past the tensor
        other = os.path.join(self.d, "plain.gguf")
        shutil.copy(MINI, other)
        with self.assertRaises(PermissionError):
            edits.scale(other, "blk.0.attn_q.weight", 0.5)                          # not a vessel
        store = os.path.join(self.d, ".ollama", "models", "blobs")
        os.makedirs(store)
        blob = os.path.join(store, "sha256-" + "ab" * 32)
        shutil.copy(self.v, blob)
        os.makedirs(os.path.splitext(blob)[0] + ".athanor")
        open(os.path.join(os.path.splitext(blob)[0] + ".athanor", "vessel.json"), "w").write("{}")
        with self.assertRaises(PermissionError):
            edits.scale(blob, "blk.0.attn_q.weight", 0.5)                           # Ollama's own file, even disguised
        self.assertEqual(sha(MINI), hashlib.sha256(open(MINI, "rb").read()).hexdigest())


class TestVessel(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.empty_ollama = os.path.join(self.d, "empty_ollama")
        os.makedirs(self.empty_ollama)
        self._old_ollama_models = os.environ.get("OLLAMA_MODELS")
        os.environ["OLLAMA_MODELS"] = self.empty_ollama

    def tearDown(self):
        if self._old_ollama_models is None:
            os.environ.pop("OLLAMA_MODELS", None)
        else:
            os.environ["OLLAMA_MODELS"] = self._old_ollama_models
        shutil.rmtree(self.d, ignore_errors=True)

    def store(self, digest):
        m = os.path.join(self.d, "models")
        man = os.path.join(m, "manifests", "registry.ollama.ai", "library", "gpt-oss")
        os.makedirs(man)
        os.makedirs(os.path.join(m, "blobs"))
        with open(os.path.join(man, "20b"), "w") as fh:
            json.dump({"layers": [{"mediaType": "application/vnd.ollama.image.model", "digest": "sha256:" + digest}]}, fh)
        shutil.copy(MINI, os.path.join(m, "blobs", "sha256-" + digest))
        return m

    def test_copy_checked_against_ollamas_checksum(self):
        m = self.store(sha(MINI))
        dest = os.path.join(self.d, "v", "a.gguf")
        meta = workshop.create("gpt-oss:20b", dest, models_dir=m)
        self.assertEqual((meta["sha256"], sha(dest)), (sha(MINI), sha(MINI)))
        with self.assertRaises(FileExistsError):
            workshop.create("gpt-oss:20b", dest, models_dir=m)

    def test_damaged_copy_not_kept(self):
        m = self.store("cd" * 32)                                   # the file doesn't match its name
        dest = os.path.join(self.d, "v", "b.gguf")
        with self.assertRaises(ValueError):
            workshop.create("gpt-oss:20b", dest, models_dir=m)
        self.assertFalse(os.path.exists(dest) or os.path.exists(dest + ".part"))

    def test_find_ollama_prefers_models_dir_and_falls_back_to_env(self):
        m = self.store(sha(MINI))
        want = os.path.join(m, "blobs", "sha256-" + sha(MINI))
        self.assertEqual(gguf.find_ollama("gpt-oss:20b", models_dir=m), want)
        with mock.patch.dict(os.environ, {"OLLAMA_MODELS": m}):
            self.assertEqual(gguf.find_ollama("gpt-oss:20b"), want)


class TestOllama(unittest.TestCase):
    ORIGINAL = ('# Modelfile generated by "ollama show"\nFROM D:\\ollama\\models\\blobs\\sha256-8ecb\n'
                'TEMPLATE """{{ .Prompt }}"""\nRENDERER gpt-oss\nPARSER gpt-oss\nPARAMETER temperature 1\nLICENSE """Apache"""\n')

    def test_only_from_changes(self):
        mf = ollama.modelfile_for(self.ORIGINAL, "/v/gptoss.gguf")
        self.assertIn(f"FROM {os.path.abspath('/v/gptoss.gguf')}\n", mf)
        self.assertNotIn("sha256-8ecb", mf)
        for keep in ('TEMPLATE """{{ .Prompt }}"""', "RENDERER gpt-oss", "PARSER gpt-oss", "PARAMETER temperature 1"):
            self.assertIn(keep, mf)
        mf2 = ollama.modelfile_for(self.ORIGINAL, "/v/x.gguf", {"temperature": 0.6, "num_ctx": 32768})
        self.assertNotIn("PARAMETER temperature 1\n", mf2)
        self.assertIn("PARAMETER temperature 0.6", mf2)
        with self.assertRaises(ValueError):
            ollama.modelfile_for("TEMPLATE x", "/v/x.gguf")

    def test_create_calls_ollama(self):
        calls = []

        class R:
            def __init__(self, out=""):
                self.returncode, self.stdout, self.stderr = 0, out, ""

        def fake(cmd, **kw):
            calls.append(cmd[1:])
            return R(self.ORIGINAL if cmd[1] == "show" else "success")
        d = tempfile.mkdtemp()
        try:
            v = os.path.join(d, "g.gguf")
            old = ollama._ollama
            ollama._ollama = lambda: "ollama"
            try:
                r = ollama.create(v, "athanor-g", "gpt-oss:20b", run=fake)
            finally:
                ollama._ollama = old
            self.assertEqual(calls, [["show", "--modelfile", "gpt-oss:20b"], ["create", "athanor-g", "-f", r["modelfile"]]])
            self.assertIn(f"FROM {os.path.abspath(v)}", open(r["modelfile"], encoding="utf-8").read())
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestCli(Base):
    def test_round_trip(self):
        v = self.v
        self.assertEqual(cli.main(["bias", v, "0", "2", "--off"]), 0)
        self.assertEqual(cli.main(["off", v, "1:0,1"]), 0)
        self.assertEqual(len(workshop.journal(v)), 3)
        self.assertEqual(cli.main(["undo", v, "all"]), 0)
        self.assertTrue(workshop.pristine(v))
        self.assertEqual(cli.main(["scale", v, "blk.0.ffn_up_exps.weight", "3"]), 1)    # refused, not crashed
        self.assertEqual(cli._experts("12:5,7 13:0"), {12: [5, 7], 13: [0]})

    def test_vessels_dir_never_points_into_site_packages(self):
        checkout = os.path.join(self.d, "checkout")
        os.makedirs(checkout)
        with open(os.path.join(checkout, "pyproject.toml"), "w", encoding="utf-8") as fh:
            fh.write("[project]\nname='recursive-symbolics'\n")
        site_pkgs = os.path.join(self.d, "venv", "Lib", "site-packages")
        dist_pkgs = os.path.join(self.d, "usr", "lib", "dist-packages")
        os.makedirs(site_pkgs)
        os.makedirs(dist_pkgs)
        with open(os.path.join(dist_pkgs, "pyproject.toml"), "w", encoding="utf-8") as fh:
            fh.write("")                                             # even with a stray pyproject, dist-packages stays fallback
        empty_dir = os.path.join(self.d, "empty")
        os.makedirs(empty_dir)
        user_default = os.path.join(os.path.expanduser("~"), ".athanor", "vessels")
        with mock.patch.dict(os.environ, {"ATHANOR_VESSELS": ""}):
            self.assertEqual(cli.vessels_dir(checkout), os.path.join(checkout, "vessels"))
            self.assertEqual(cli.vessels_dir(site_pkgs), user_default)
            self.assertEqual(cli.vessels_dir(dist_pkgs), user_default)
            self.assertEqual(cli.vessels_dir(empty_dir), user_default)
        with mock.patch.dict(os.environ, {"ATHANOR_VESSELS": "   "}):
            self.assertEqual(cli.vessels_dir(site_pkgs), user_default)
        custom = os.path.join(self.d, "custom_vessels")
        with mock.patch.dict(os.environ, {"ATHANOR_VESSELS": custom}):
            self.assertEqual(cli.vessels_dir(site_pkgs), custom)
            self.assertEqual(cli._vessel("demo"), os.path.join(custom, "demo.gguf"))
        explicit = os.path.join(self.d, "explicit.gguf")
        self.assertEqual(cli._vessel(explicit), explicit)

    def test_experts_spec_rejects_malformed_and_merges_repeated_layers(self):
        self.assertEqual(cli._experts("12:5 12:7,0"), {12: [5, 7, 0]})
        for bad in ("12", "12:"):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "Expected LAYER:EXPERT"):
                cli._experts(bad)
        for bad in ("", "   ", "12:5,", "12:5,,7", ":5", "x:1"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                cli._experts(bad)

    def test_cli_values_and_off_refuse_bad_inputs_cleanly(self):
        v = self.v
        self.assertEqual(cli.main(["values", v, "blk.0.ffn_up_exps.weight", "--expert", "0"]), 0)
        for args in (
            ["values", v, "blk.0.ffn_up_exps.weight", "--expert", "-1"],
            ["values", v, "blk.0.ffn_up_exps.weight", "--expert", "4"],
            ["values", v, "blk.0.attn_norm.weight", "--expert", "0"],
            ["off", v, "12"],
            ["off", v, ""],
        ):
            with self.subTest(args=args):
                self.assertEqual(cli.main(args), 1)


class TestLinksAndInterruptions(Base):
    """Review of 2026-11-06: a link pointing into Ollama's store was judged by the path given, not the file reached;
    and a crash between writing the vessel and journaling it left a change with no record."""
    def test_link_into_ollamas_store_refused(self):
        store = os.path.join(self.d, "store")
        os.makedirs(os.path.join(store, "blobs"))
        blob = os.path.join(store, "blobs", "model.gguf")              # no tell-tale name: only the store says so
        shutil.copy(self.v, blob)
        link = os.path.join(self.d, "innocent.gguf")
        try:
            os.symlink(blob, link)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not allowed here")
        os.makedirs(os.path.splitext(link)[0] + ".athanor")
        open(os.path.join(os.path.splitext(link)[0] + ".athanor", "vessel.json"), "w").write("{}")
        old = os.environ.get("OLLAMA_MODELS")
        os.environ["OLLAMA_MODELS"] = store
        try:
            before = sha(blob)
            with self.assertRaises(PermissionError):
                edits.scale(link, "blk.0.attn_q.weight", 0.5)
            self.assertEqual(sha(blob), before)
        finally:
            if old is None:
                os.environ.pop("OLLAMA_MODELS")
            else:
                os.environ["OLLAMA_MODELS"] = old

    def _interrupt(self):
        """A change whose model bytes were written but whose journal line never was."""
        real = workshop.json.dumps
        rec = edits.scale(self.v, "blk.0.attn_q.weight", 0.5)
        rows = workshop.journal(self.v)
        workshop._rewrite(self.v, rows[:-1])
        with open(os.path.join(workshop._dir(self.v), "pending.json"), "w", encoding="utf-8") as fh:
            fh.write(real(rows[-1]))
        return rows[-1]

    def test_interrupted_change_is_journaled_on_next_use(self):
        r = self._interrupt()
        rows = workshop.journal(self.v)
        self.assertEqual([x["id"] for x in rows], [r["id"]])
        self.assertIn("recovered", rows[0]["what"])
        self.assertFalse(os.path.exists(os.path.join(workshop._dir(self.v), "pending.json")))
        self.assertEqual(workshop.undo(self.v), [r["id"]])
        self.assertTrue(workshop.pristine(self.v))

    def test_interrupted_before_the_model_changed_is_dropped(self):
        r = self._interrupt()
        workshop._rewrite(self.v, [])
        with open(os.path.join(workshop._dir(self.v), "undo", f"{r['id']}.bin"), "rb") as u:
            old = u.read()
        with open(self.v, "r+b") as fh:                                    # the model write never happened
            fh.seek(r["start"])
            fh.write(old)
        self.assertEqual(workshop.journal(self.v), [])
        self.assertTrue(workshop.pristine(self.v))

    def test_interrupted_and_partly_written_is_rolled_back_from_the_backup(self):
        """POLICY, decided 2026-11-08 by the Maintainer: bytes matching neither sha_before nor sha_after are what a torn
        write actually looks like, so recovery rolls them back from the undo backup rather than stopping. It is
        safe to do because the backup's own sha is checked against sha_before first.

        This replaces test_interrupted_and_damaged_stops, which asserted the older rule (stop, write nothing,
        undo nothing). The guard it protected has not gone: see the test below, where the backup itself is
        damaged and recovery does stop."""
        r = self._interrupt()
        with open(self.v, "rb") as fh:
            fh.seek(r["start"])
            after = fh.read(r["bytes"])
        with open(os.path.join(workshop._dir(self.v), "undo", f"{r['id']}.bin"), "rb") as fh:
            before = fh.read()
        with open(self.v, "r+b") as fh:                    # a write that stopped halfway through its bytes
            fh.seek(r["start"])
            fh.write(b"\x11\x22\x33")
        self.assertEqual(workshop.journal(self.v), [])     # nothing is claimed to have happened
        with open(self.v, "rb") as fh:
            fh.seek(r["start"])
            self.assertEqual(fh.read(len(before)), before)  # the model is back as it was
        self.assertNotEqual(before[:3], after[:3])
        self.assertTrue(workshop.pristine(self.v))
        self.assertFalse(os.path.exists(os.path.join(workshop._dir(self.v), "pending.json")))

    def test_a_damaged_backup_still_stops(self):
        """The rollback is only safe because the backup is verified first. Damage the backup and recovery must
        refuse rather than write unknown bytes into the model."""
        r = self._interrupt()
        with open(self.v, "r+b") as fh:
            fh.seek(r["start"])
            fh.write(b"\x11\x22\x33")
        undo = os.path.join(workshop._dir(self.v), "undo", f"{r['id']}.bin")
        with open(undo, "r+b") as fh:
            fh.seek(0)
            fh.write(b"\x99\x99\x99")
        with self.assertRaises(ValueError) as e:
            workshop.journal(self.v)
        # It names the write that failed, so it cannot be mistaken for an undo.
        self.assertIn(f"Change {r['id']} recovery bytes are damaged", str(e.exception))

    def test_torn_last_journal_line_is_repaired(self):
        """Third review, 2026-11-06: stopped while appending the journal line, so the file ends mid-record."""
        r = self._interrupt()
        jp = os.path.join(workshop._dir(self.v), "journal.jsonl")
        with open(jp, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(r)[:25])                                   # half a record, no newline
        rows = workshop.journal(self.v)
        self.assertEqual([x["id"] for x in rows], [r["id"]])
        with open(jp, encoding="utf-8") as fh:
            self.assertTrue(all(json.loads(l) for l in fh if l.strip()))  # every line whole again
        self.assertEqual(workshop.undo(self.v), [r["id"]])
        self.assertTrue(workshop.pristine(self.v))

    def test_damage_inside_the_journal_is_not_guessed(self):
        edits.scale(self.v, "blk.0.attn_q.weight", 0.5)
        r = self._interrupt()
        jp = os.path.join(workshop._dir(self.v), "journal.jsonl")
        with open(jp, encoding="utf-8") as fh:
            first = fh.read()
        with open(jp, "w", encoding="utf-8") as fh:
            fh.write(first[:10] + "\n" + first)                           # a broken line before good ones
        with self.assertRaises(ValueError):
            workshop.journal(self.v)
        with open(jp, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), first[:10] + "\n" + first)        # left exactly as found

    def test_damaged_journal_without_pending_stops_clearly(self):
        edits.scale(self.v, "blk.0.attn_q.weight", 0.5)
        with open(os.path.join(workshop._dir(self.v), "journal.jsonl"), "a", encoding="utf-8") as fh:
            fh.write('{"id": 2, "wh')
        with self.assertRaisesRegex(ValueError, "damaged"):
            workshop.journal(self.v)



class TestCodecBoundaries(unittest.TestCase):
    """Added 2026-11-20 for the public repository: each test kills a boundary mutant of codec.py that survived the
    original suite. Ground truth is the format itself: an MXFP4 block is 1 exponent byte then 16 code bytes, and a
    power-of-two scale moves only the exponent (codec.py's docstring, after ggml); half precision tops out at
    65504."""

    @staticmethod
    def block(e):
        return bytes([e]) + bytes([0x21] * 16)

    def test_half_precision_may_reach_exactly_its_largest_value(self):
        """codec.py:53, > 65504. 32752 is exact in F16 (steps of 16 between 2**14 and 2**15); doubled it is
        65504, the largest finite half, which is allowed. Anything that would round above it is refused."""
        raw = np.array([32752.0], dtype="<f2").tobytes()
        out, _ = codec.scaled(raw, "F16", 2)
        self.assertEqual(np.frombuffer(out, dtype="<f2")[0], 65504.0)
        with self.assertRaises(ValueError):
            codec.scaled(raw, "F16", 2.01)

    def test_a_block_with_exponent_two_is_live_and_moves(self):
        """codec.py:68, e >= 2: exponent 2 is the smallest live exponent, so doubling makes it 3."""
        out, notes = codec.scaled(self.block(2), "MXFP4", 2)
        self.assertEqual(out[0], 3)
        self.assertEqual(out[1:], self.block(2)[1:])           # the codes never move
        self.assertEqual(notes, {"blocks_moved": 1})

    def test_the_new_exponent_may_land_exactly_on_either_end_of_the_range(self):
        """codec.py:70, ne < 2 and ne > 254: 2 and 254 are inside the range; 1 and 255 are not."""
        self.assertEqual(codec.scaled(self.block(3), "MXFP4", 0.5)[0][0], 2)
        self.assertEqual(codec.scaled(self.block(253), "MXFP4", 2)[0][0], 254)
        for e, factor in ((2, 0.5), (254, 2)):
            with self.assertRaises(ValueError, msg=(e, factor)):
                codec.scaled(self.block(e), "MXFP4", factor)

class TestEditsGaps(Base):
    """Added 2026-11-20 for the public repository: each test kills a mutant of edits.py that survived the original
    suite. Ground truth: the fixture's shapes (4 experts per layer; ffn_gate_inp.weight is [64, 4], so one
    expert's 64 weights are contiguous), its expected values, and the journal on disk."""

    def test_an_out_of_range_expert_is_named_with_the_real_range(self):
        """edits.py:25 and :60, n - 1: the fixture has 4 experts, so the range is 0 to 3."""
        with self.assertRaisesRegex(ValueError, r"has experts 0 to 3\."):
            edits.router_bias(self.v, 1, 4, off=True)
        with self.assertRaisesRegex(ValueError, r"has experts 0 to 3\."):
            edits.scale(self.v, "blk.0.ffn_up_exps.weight", 2, expert=4)

    def test_a_finite_but_huge_bias_is_refused_and_the_limit_itself_is_allowed(self):
        """edits.py:33, not finite OR abs > 1e6: either is enough to refuse, and exactly 1e6 is in range."""
        with self.assertRaises(ValueError):
            edits.router_bias(self.v, 1, 0, set_to=2e6)
        with self.assertRaises(ValueError):
            edits.router_bias(self.v, 1, 0, set_to=float("nan"))
        self.assertEqual(edits.router_bias(self.v, 1, 0, set_to=1e6)["after"], 1e6)

    def test_the_journal_id_returned_is_the_one_written(self):
        """edits.py:37 and :70, rec and rec["id"]: the id, not the whole record."""
        r1 = edits.router_bias(self.v, 1, 0, add=0.25)
        r2 = edits.scale(self.v, "blk.0.attn_norm.weight", 2)
        ids = [row["id"] for row in workshop.journal(self.v)]
        self.assertEqual((r1["journal_id"], r2["journal_id"]), (ids[-2], ids[-1]))
        self.assertIsInstance(r2["journal_id"], int)

    def test_one_expert_of_a_two_dimensional_tensor_can_be_scaled(self):
        """edits.py:56, len(shape) < 2: a 2-D tensor whose last dimension is the expert has experts too."""
        name = "blk.0.ffn_gate_inp.weight"
        before = EXP[name].reshape(4, -1)
        edits.scale(self.v, name, 2, expert=1)
        after = tensor_values(self.v, name).reshape(4, -1)
        np.testing.assert_array_equal(after[[0, 2, 3]], before[[0, 2, 3]])
        np.testing.assert_array_equal(after[1], before[1] * np.float32(2))
        with self.assertRaisesRegex(ValueError, "has no experts"):
            edits.scale(self.v, "blk.0.attn_norm.weight", 2, expert=0)     # 1-D: no experts

    def test_scale_factor_bounds_are_inclusive_and_outside_is_refused(self):
        """edits.py:52, 1e-4 <= abs(factor) <= 1e4: both ends (+/-) pass; outside raises ValueError."""
        name = "blk.0.ffn_gate_inp.weight"
        before = EXP[name].astype(np.float32)
        for factor in (1e-4, -1e-4, 1e4, -1e4):
            edits.scale(self.v, name, factor)
            np.testing.assert_allclose(tensor_values(self.v, name), before * np.float32(factor), rtol=1e-6)
            workshop.undo(self.v)
        for bad in (9.9e-5, -9.9e-5, 10001.0, -10001.0):
            with self.assertRaises(ValueError, msg=repr(bad)):
                edits.scale(self.v, name, bad)

    def test_values_checks_expert_bounds_and_decodes_slice(self):
        """edits.values() uses the same _expert_slice bounds as scale(): 0..3 ok, 1-D/-1/4/bool refused."""
        name = "blk.0.ffn_gate_inp.weight"
        rows = EXP[name].reshape(4, -1)
        for exp in (0, 1, 3):
            got = edits.values(self.v, name, expert=exp, count=4)
            expected = rows[exp]
            self.assertEqual(got["count"], int(expected.size))
            self.assertEqual(got["first"], [round(float(x), 6) for x in expected[:4]])
            self.assertAlmostEqual(got["mean"], float(expected.mean()), places=6)
        self.assertEqual(edits.values(self.v, "blk.0.ffn_up_exps.weight", expert=3)["count"], 4096)
        with self.assertRaisesRegex(ValueError, "has no experts"):
            edits.values(self.v, "blk.0.attn_norm.weight", expert=0)
        for bad in (-1, 4, True, False):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, r"has experts 0 to 3\."):
                edits.values(self.v, name, expert=bad)

    def test_scale_and_router_bias_reject_negative_and_bool_experts_or_layers(self):
        with self.assertRaisesRegex(ValueError, "Layer must be an integer"):
            edits.router_bias(self.v, True, 0, off=True)
        for bad in (-1, 4, True, False):
            with self.subTest(fn="router_bias", bad=bad), self.assertRaisesRegex(ValueError, r"has experts 0 to 3\."):
                edits.router_bias(self.v, 0, bad, off=True)
            with self.subTest(fn="scale", bad=bad), self.assertRaisesRegex(ValueError, r"has experts 0 to 3\."):
                edits.scale(self.v, "blk.0.ffn_gate_inp.weight", 2, expert=bad)

    def test_uneven_expert_byte_size_is_refused(self):
        """An MXFP4 tensor of shape [16, 4] is 2 blocks = 34 bytes, not divisible across 4 experts."""
        nm = b"uneven"
        hdr = (b"GGUF" + struct.pack("<IQQ", 3, 1, 0)
               + struct.pack("<Q", len(nm)) + nm
               + struct.pack("<IQQIQ", 2, 16, 4, 39, 0))
        data_start = (len(hdr) + 31) // 32 * 32
        src = os.path.join(self.d, "uneven_src.gguf")
        ves = os.path.join(self.d, "uneven_ves.gguf")
        with open(src, "wb") as fh:
            fh.write(hdr + b"\x00" * (data_start - len(hdr)) + b"\x00" * 34)
        workshop.create(src, ves, verify=False)
        with self.assertRaisesRegex(ValueError, "cannot be split evenly"):
            edits.values(ves, "uneven", expert=0)
        with self.assertRaisesRegex(ValueError, "cannot be split evenly"):
            edits.scale(ves, "uneven", 2, expert=0)

class TestGgufGaps(unittest.TestCase):
    """Added 2026-11-20 for the public repository: each test kills a mutant of gguf.py that survived the original
    suite. Ground truth: GGUF files built byte by byte here from the format (llama.cpp's gguf.md: magic, version,
    tensor count, key-value count, then length-prefixed strings), hand-made info dictionaries, and byte sizes
    computed from the fixture's shapes with the GGML block sizes (MXFP4: 17 bytes per 32 weights)."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        gguf._CACHE.clear()

    def tearDown(self):
        gguf._CACHE.clear()
        shutil.rmtree(self.d, ignore_errors=True)

    # ---------- building tiny files ----------
    @staticmethod
    def s(text):
        b = text.encode() if isinstance(text, str) else text
        return struct.pack("<Q", len(b)) + b

    def write(self, name, data):
        path = os.path.join(self.d, name)
        with open(path, "wb") as fh:
            fh.write(data)
        return path

    def gguf_file(self, name, kvs):
        """kvs: [(key, type_id, payload bytes)]; no tensors."""
        out = b"GGUF" + struct.pack("<I", 3) + struct.pack("<QQ", 0, len(kvs))
        for key, t, payload in kvs:
            out += self.s(key) + struct.pack("<I", t) + payload
        return self.write(name, out)

    # ---------- strings ----------
    def test_the_string_limit_is_sixteen_mebibytes_inclusive(self):
        """gguf.py:23 (both Mult->Add) and :42 (> MAX): a string of exactly 16 MiB is read; one byte more is not."""
        self.assertEqual(gguf.MAX_STRING_BYTES, 16 * 1024 * 1024)
        n = gguf.MAX_STRING_BYTES
        p = self.write("big.bin", struct.pack("<Q", n) + b"a" * n)
        with open(p, "rb") as fh:
            self.assertEqual(len(gguf._Reader(fh).string()), n)
        p = self.write("bigger.bin", struct.pack("<Q", n + 1))
        with open(p, "rb") as fh, self.assertRaisesRegex(ValueError, "exceeds the maximum"):
            gguf._Reader(fh).string()

    def test_a_string_may_end_exactly_at_the_end_of_the_file(self):
        """gguf.py:44, n > remaining: a string that fills the rest of the file is complete, not past the end."""
        p = self.write("exact.bin", self.s("hello"))
        with open(p, "rb") as fh:
            self.assertEqual(gguf._Reader(fh).string(), "hello")
        p = self.write("short.bin", struct.pack("<Q", 6) + b"hello")
        with open(p, "rb") as fh, self.assertRaisesRegex(ValueError, "past the end"):
            gguf._Reader(fh).string()

    # ---------- metadata ----------
    def test_a_numeric_array_longer_than_the_preview_is_skipped_correctly(self):
        """gguf.py:58, seek((n - len(head)) * size): after a 5-item int32 array previewed at 3, the reader must
        land exactly on the next key, so the value after it reads back as written."""
        arr = struct.pack("<IQ", 5, 5) + struct.pack("<5i", 10, 11, 12, 13, 14)
        p = self.gguf_file("arr.gguf", [("a.list", 9, arr), ("b.after", 4, struct.pack("<I", 7))])
        kv = gguf.read(p, preview=3)["metadata"]
        self.assertEqual(kv["a.list"], {"array_of": "int32", "length": 5, "first": [10, 11, 12]})
        self.assertEqual(kv["b.after"], 7)

    def test_an_alignment_that_is_not_a_positive_integer_is_refused(self):
        """gguf.py:105: zero, a bool, and a string are each refused as ValueError, never another error."""
        for t, payload in ((4, struct.pack("<I", 0)), (7, struct.pack("<?", True)), (8, self.s("32"))):
            p = self.gguf_file(f"align{t}.gguf", [("general.alignment", t, payload)])
            with self.subTest(type=t), self.assertRaisesRegex(ValueError, "Invalid GGUF tensor alignment"):
                gguf.read(p)

    # ---------- the edit-layout validator ----------
    def info(self, size=1024, **over):
        path = self.write(f"layout{size}.bin", b"\0" * size)
        base = {"path": path, "file_bytes": size, "alignment": 32, "data_start": 64,
                "tensors": [{"name": "t", "type": "F32", "elements": 10, "bytes": 40, "offset": 0}]}
        base.update(over)
        return base

    def test_a_sound_layout_passes_including_its_boundaries(self):
        """gguf.py:121: data may start at byte 0, and may start exactly at the end of a file with no tensors."""
        gguf.validate_edit_layout(self.info())
        gguf.validate_edit_layout(self.info(data_start=0))
        gguf.validate_edit_layout(self.info(data_start=1024, tensors=[]))

    def test_each_bad_layout_is_refused_as_a_value_error(self):
        """gguf.py:119, :121, :127 and :131: every condition refuses on its own, and with ValueError."""
        bad = {
            "misaligned start": dict(data_start=65),                               # :119 Or->And
            "zero alignment": dict(alignment=0),                                   # :119 LtE->Lt
            "file changed size": dict(file_bytes=999),                             # :121 Or->And
            "unknown type": dict(tensors=[{"name": "t", "type": "Q9_9", "elements": 10, "bytes": 40,
                                           "offset": 0}]),                         # :127 Or->And
            "no elements": dict(tensors=[{"name": "t", "type": "F32", "elements": 0, "bytes": 0,
                                          "offset": 0}]),                          # :131 LtE->Lt
            "partial block": dict(tensors=[{"name": "t", "type": "MXFP4", "elements": 33, "bytes": 17,
                                            "offset": 0}]),                        # :131 Or->And
        }
        for why, over in bad.items():
            with self.subTest(why), self.assertRaises(ValueError):
                gguf.validate_edit_layout(self.info(**over))

    # ---------- the summary ----------
    def test_sizes_are_shown_in_the_unit_they_reach(self):
        """gguf.py:148 and :152, n >= 1e9 and n >= 1e6: exactly a billion is 1.00 GB, exactly a million 1.00 MB."""
        self.assertEqual((gguf._gb(10**9), gguf._gb(10**6), gguf._gb(999)), ("1.00 GB", "1.00 MB", "1.0 KB"))
        self.assertEqual((gguf._count(10**9), gguf._count(10**6), gguf._count(999)),
                         ("1.00 billion", "1.00 million", "999"))

    def test_the_summary_adds_up_the_fixture_by_type(self):
        """gguf.py:164, :166, :171, :177, :185. Expected sizes come from shapes and GGML block sizes, not from the
        reader's own byte counts."""
        info = gguf.read(MINI)
        spec = {"F32": (1, 4), "F16": (1, 2), "BF16": (1, 2), "MXFP4": (32, 17)}
        params, nbytes, by_type, up = 0, 0, {}, 0
        for t in info["tensors"]:
            n = int(np.prod(t["shape"]))
            blk, bsz = spec[t["type"]]
            params += n
            nbytes += n // blk * bsz
            e = by_type.setdefault(t["type"], [0, 0])
            e[0] += n
            e[1] += n // blk * bsz
            if re.fullmatch(r"blk\.\d+\.ffn_up_exps\.weight", t["name"]):
                up += n
        s = gguf.summary(info)
        self.assertEqual(s["bits_per_weight"], round(8 * nbytes / params, 2))
        for kind, (p, b) in by_type.items():
            self.assertEqual(s["quantization"][kind]["size"], gguf._gb(b), kind)
            self.assertEqual(s["quantization"][kind]["share_of_parameters"], f"{100 * p / params:.1f}%", kind)
        self.assertEqual(s["largest_parts"]["ffn_up_exps"], f"{gguf._count(up)} parameters")

    def summary_info(self, data_start, file_bytes, kv=None):
        return {"metadata": kv or {}, "version": 3, "file_bytes": file_bytes, "data_start": data_start,
                "tensors": [{"name": "t", "shape": [10], "type": "F32", "elements": 10, "bytes": 40}]}

    def test_the_size_check_allows_an_exact_fit_and_catches_an_overrun(self):
        """gguf.py:188, data_start + data <= file_bytes."""
        self.assertEqual(gguf.summary(self.summary_info(60, 100))["check"], "tensor sizes add up to the file")
        self.assertEqual(gguf.summary(self.summary_info(61, 100))["check"],
                         "tensor sizes run past the end of the file")

    def test_the_mixture_of_experts_note_needs_both_counts(self):
        """gguf.py:191: experts and experts-used are both needed for the note."""
        kv = {"general.architecture": "oss", "oss.expert_count": 4}
        self.assertNotIn("note", gguf.summary(self.summary_info(60, 100, kv)))
        kv["oss.expert_used_count"] = 2
        self.assertIn("each token uses 2 of 4 expert", gguf.summary(self.summary_info(60, 100, kv))["note"])

    # ---------- listing and looking up ----------
    def test_a_pattern_filters_tensors_and_metadata(self):
        """gguf.py:226, :235, :237, :238."""
        names = {t["name"] for t in gguf.read(MINI)["tensors"] if "attn_q" in t["name"]}
        got = gguf.inspect(MINI, "tensors", "attn_q")
        self.assertEqual({t["name"] for t in got["tensors"]}, names)
        self.assertEqual(got["matching"], len(names))
        meta = gguf.inspect(MINI, "metadata", r"^general\.")["metadata"]
        self.assertTrue(meta and all(k.startswith("general.") for k in meta), meta)
        self.assertIn("read_only", gguf.inspect(MINI))

    def test_a_missing_tensor_suggests_the_same_part_in_other_layers(self):
        """gguf.py:251: suggestions share the last two name parts."""
        with self.assertRaises(KeyError) as caught:
            gguf.tensor(gguf.read(MINI), "blk.9.attn_q.weight")
        self.assertIn("Similar: blk.0.attn_q.weight, blk.1.attn_q.weight", str(caught.exception))

class TestWorkshopGaps(Base):
    """Added 2026-11-20 for the public repository: each test kills a mutant of workshop.py that survived the
    original suite. Pending records are built the way write() and undo() build them (workshop.py:357 and :428);
    the fixture's last tensor ends exactly at the end of the file."""

    def setUp(self):
        super().setUp()
        self.dd = workshop._dir(self.v)
        self.info = gguf.read(self.v)
        self.first = gguf.tensor(self.info, self.info["tensors"][0]["name"])
        self.last = max((gguf.tensor(self.info, t["name"]) for t in self.info["tensors"]), key=lambda t: t["end"])

    def put(self, name, data):
        with open(os.path.join(self.dd, name), "wb") as fh:
            fh.write(data)

    def pending(self, rec):
        with open(os.path.join(self.dd, "pending.json"), "w", encoding="utf-8") as fh:
            json.dump(rec, fh)

    def rec(self, **over):
        base = {"id": 1, "what": "test", "tensor": self.first["name"], "start": self.first["start"], "bytes": 4,
                "sha_before": "0" * 64, "sha_after": "1" * 64, "undone": False}
        base.update(over)
        return base

    def bytes_at(self, start, n):
        with open(self.v, "rb") as fh:
            fh.seek(start)
            return fh.read(n)

    # ---------- the journal's torn tail ----------
    def test_a_torn_last_line_is_cut_exactly_where_it_starts(self):
        """workshop.py:224 and :237, keep += len(line) + 1: a blank line before the torn one counts too."""
        self.put("journal.jsonl", b'{"id": 1}\n\n{"id": 2}\n{"id": 3, "wh')
        self.assertEqual(workshop._repair_tail(self.dd), [{"id": 1}, {"id": 2}])
        with open(os.path.join(self.dd, "journal.jsonl"), "rb") as fh:
            self.assertEqual(fh.read(), b'{"id": 1}\n\n{"id": 2}\n')

    def test_damage_before_the_end_names_its_line(self):
        """workshop.py:230, line k + 1."""
        self.put("journal.jsonl", b'{"id": 1}\n{bad\n{"id": 3}\n')
        with self.assertRaisesRegex(ValueError, r"damaged at line 2, not at its end"):
            workshop._repair_tail(self.dd)

    def test_only_a_missing_final_newline_is_added(self):
        """workshop.py:238: a journal that already ends in a newline is left byte for byte as it was."""
        for before, after in ((b'{"id": 1}\n', b'{"id": 1}\n'), (b'{"id": 1}', b'{"id": 1}\n')):
            self.put("journal.jsonl", before)
            workshop._repair_tail(self.dd)
            with open(os.path.join(self.dd, "journal.jsonl"), "rb") as fh:
                self.assertEqual(fh.read(), after, before)

    # ---------- the pending record's checks ----------
    def test_a_pending_record_with_a_bad_id_stops(self):
        """workshop.py:254: not a dict, an id that is not a positive int (a string, 0, a bool)."""
        for rec in ([1], self.rec(id="1"), self.rec(id=0), self.rec(id=True)):
            self.pending(rec)
            with self.subTest(rec=rec), self.assertRaisesRegex(ValueError, "invalid id"):
                workshop.journal(self.v)

    def test_a_pending_record_with_a_bad_range_stops(self):
        """workshop.py:257: start not an int, nothing to write, before the file, or past its end."""
        size = os.path.getsize(self.v)
        for over in (dict(start="5"), dict(bytes=0), dict(start=-1), dict(start=size - 4, bytes=8)):
            self.pending(self.rec(**over))
            with self.subTest(over=over), self.assertRaisesRegex(ValueError, "invalid byte range"):
                workshop.journal(self.v)

    def test_the_range_checks_allow_their_own_boundaries(self):
        """workshop.py:257, start < 0 and start + count > size: byte 0 is a valid range (refused later, as not
        inside a tensor), and a range ending exactly at the end of the file is in range."""
        self.pending(self.rec(start=0))
        with self.assertRaisesRegex(ValueError, "not inside one known tensor"):
            workshop.journal(self.v)
        t = self.last
        self.assertEqual(t["end"], os.path.getsize(self.v))
        current = workshop._sha(self.bytes_at(t["start"], t["bytes"]))
        self.pending(self.rec(tensor=t["name"], start=t["start"], bytes=t["bytes"], sha_before=current))
        workshop.journal(self.v)                        # bytes are still the "before" bytes: nothing to redo
        self.assertFalse(os.path.exists(os.path.join(self.dd, "pending.json")))

    def test_a_range_across_two_tensors_is_refused(self):
        """workshop.py:272 and :273: a pending change must lie inside ONE tensor."""
        self.pending(self.rec(start=self.first["end"] - 4, bytes=8))
        with self.assertRaisesRegex(ValueError, "not inside one known tensor"):
            workshop.journal(self.v)

    # ---------- recovering an interrupted undo ----------
    def interrupted_undo(self, redo_bytes):
        start = self.first["start"]
        old = self.bytes_at(start, 4)
        r = workshop.write(self.v, start, b"WXYZ", "test", self.info)
        pend = dict(r, operation="undo", redo=f"{r['id']}.redo.bin",
                    sha_before=r["sha_after"], sha_after=r["sha_before"])
        self.put(os.path.join("undo", f"{r['id']}.redo.bin"), redo_bytes)
        self.pending(pend)
        with open(self.v, "r+b") as fh:                 # torn: neither the written bytes nor the old ones
            fh.seek(start)
            fh.write(b"W" + old[1:3] + b"Z" if old[1:3] != b"XY" else b"WQQZ")
        return start

    def test_an_interrupted_undo_is_rolled_back_from_good_redo_bytes(self):
        """workshop.py:298: redo bytes of the right length and hash are trusted, and put back."""
        start = self.interrupted_undo(b"WXYZ")
        workshop.journal(self.v)
        self.assertEqual(self.bytes_at(start, 4), b"WXYZ")
        self.assertFalse(os.path.exists(os.path.join(self.dd, "pending.json")))

    def test_redo_bytes_of_the_right_length_but_wrong_content_stop(self):
        """workshop.py:298, len != count OR sha != before: either alone is enough to stop."""
        self.interrupted_undo(b"WXYQ")
        # It names the undo that failed, so it cannot be mistaken for a write.
        with self.assertRaisesRegex(ValueError, "Undo 1 recovery bytes are damaged"):
            workshop.journal(self.v)

    # ---------- names, writes, undo by id ----------
    def test_an_unsafe_undo_name_is_refused_as_a_value_error(self):
        """workshop.py:61: anything but a plain file name, including a name that is not a string."""
        for bad in (5, None, "", ".", "..", "a/b", "a\\b"):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "Unsafe undo recovery path"):
                workshop._undo_path(self.dd, bad)

    def test_a_write_reads_the_layout_itself_when_not_given_it(self):
        """workshop.py:343, info or gguf.read(path)."""
        r = workshop.write(self.v, self.first["start"], b"WXYZ", "no info passed")
        self.assertEqual((r["id"], self.bytes_at(self.first["start"], 4)), (1, b"WXYZ"))

    def test_undo_by_id_touches_only_that_change(self):
        """workshop.py:408 and :409: undoing #1 leaves #2, on another tensor, alone; a later change to the SAME
        tensor blocks it."""
        a, b = self.first, self.last
        workshop.write(self.v, a["start"], b"WXYZ", "on a", self.info)
        workshop.write(self.v, b["start"], b"WXYZ", "on b", self.info)
        self.assertEqual(workshop.undo(self.v, "1"), [1])
        self.assertEqual([(r["id"], r["undone"]) for r in workshop.journal(self.v)], [(1, True), (2, False)])
        workshop.write(self.v, b["start"] + 4, b"QQQQ", "on b again", self.info)
        with self.assertRaisesRegex(ValueError, r"later changes to the same tensor \(3\)"):
            workshop.undo(self.v, "2")