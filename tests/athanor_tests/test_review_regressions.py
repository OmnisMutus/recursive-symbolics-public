"""Stdlib-only regression tests for reviewed vessel, GGUF and journal safeguards."""
import json
import os
import shutil
import struct
import tempfile
import unittest
from unittest import mock

from athanor import gguf, workshop


def _string(value):
    raw = value.encode("utf-8")
    return struct.pack("<Q", len(raw)) + raw


def _gguf(tensors, payload=b"\x00" * 128):
    """Build a minimal v3 GGUF with one-dimensional tensor declarations."""
    header = bytearray(b"GGUF" + struct.pack("<IQQ", 3, len(tensors), 0))
    for name, kind, offset in tensors:
        header += _string(name)
        header += struct.pack("<I", 1) + struct.pack("<Q", 4)
        header += struct.pack("<IQ", kind, offset)
    data_start = (len(header) + 31) // 32 * 32
    return bytes(header) + b"\x00" * (data_start - len(header)) + payload


def _bytes(path):
    with open(path, "rb") as fh:
        return fh.read()


class ReviewRegressions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.source = os.path.join(self.tmp, "source.gguf")
        self.vessel = os.path.join(self.tmp, "vessel.gguf")
        self._write_source(_gguf([("weight", 0, 0)], b"abcdefghijklmnop"))

    def tearDown(self):
        gguf._CACHE.clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_source(self, raw):
        with open(self.source, "wb") as fh:
            fh.write(raw)
        gguf._CACHE.clear()

    def _create(self):
        gguf._CACHE.clear()
        workshop.create(self.source, self.vessel, verify=False)
        gguf._CACHE.clear()
        return gguf.read(self.vessel)

    def test_create_does_not_follow_a_part_symlink(self):
        victim = os.path.join(self.tmp, "victim")
        with open(victim, "wb") as fh:
            fh.write(b"keep this file intact")
        try:
            os.symlink(victim, self.vessel + ".part")
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are unavailable")
        workshop.create(self.source, self.vessel, verify=False)
        with open(victim, "rb") as fh:
            self.assertEqual(fh.read(), b"keep this file intact")   # nothing was written through the link
        self.assertTrue(os.path.isfile(self.vessel))
        # The staging path is a unique mkstemp name, so <vessel>.part is never touched: the pre-existing link is
        # left exactly where it was. Asserting it had been removed contradicted
        # test_create_uses_a_unique_staging_path below, which requires that an existing staging name is left alone.
        self.assertTrue(os.path.islink(self.vessel + ".part"))

    def test_create_uses_a_unique_staging_path(self):
        stale = self.vessel + ".part"
        with open(stale, "wb") as fh:
            fh.write(b"leave the existing staging name alone")
        workshop.create(self.source, self.vessel, verify=False)
        with open(stale, "rb") as fh:
            self.assertEqual(fh.read(), b"leave the existing staging name alone")
        self.assertTrue(os.path.isfile(self.vessel))

    def test_edits_refuse_a_multiply_linked_vessel(self):
        info = self._create()
        alias = os.path.join(self.tmp, "hardlink.gguf")
        try:
            os.link(self.vessel, alias)
        except (OSError, NotImplementedError):
            self.skipTest("hard links are unavailable")
        start = info["data_start"] + info["tensors"][0]["offset"]
        with self.assertRaises(PermissionError):
            workshop.write(self.vessel, start, b"WXYZ", "test", info)

    def test_gguf_string_length_cannot_extend_past_file(self):
        raw = b"GGUF" + struct.pack("<IQQ", 3, 0, 1) + struct.pack("<Q", 64) + b"x"
        path = os.path.join(self.tmp, "bad-string.gguf")
        with open(path, "wb") as fh:
            fh.write(raw)
        with self.assertRaisesRegex(ValueError, "string.*past (the )?end"):
            gguf.read(path)

    def test_gguf_string_has_a_small_allocation_limit(self):
        too_long = 16 * 1024 * 1024 + 1
        raw = (b"GGUF" + struct.pack("<IQQ", 3, 0, 1) + _string("key") +
               struct.pack("<I", 8) + struct.pack("<Q", too_long))
        path = os.path.join(self.tmp, "oversized-string.gguf")
        with open(path, "wb") as fh:
            fh.write(raw)
        with self.assertRaisesRegex(ValueError, "maximum"):
            gguf.read(path)

    def test_edits_reject_invalid_tensor_layouts(self):
        cases = (
            ([("weight", 0, 1)], b"\x00" * 64, "misaligned"),
            ([("weight", 0, 32)], b"\x00" * 16, "outside"),
            ([("one", 0, 0), ("two", 0, 0)], b"\x00" * 32, "overlap"),
        )
        for declarations, payload, reason in cases:
            with self.subTest(reason=reason):
                self._write_source(_gguf(declarations, payload))
                self.vessel = os.path.join(self.tmp, reason + ".gguf")
                info = self._create()
                target = info["tensors"][0]
                start = info["data_start"] + target["offset"]
                before = _bytes(self.vessel)
                with self.assertRaises(ValueError):
                    workshop.write(self.vessel, start, b"WXYZ", "test", info)
                self.assertEqual(_bytes(self.vessel), before)

    def test_edits_fail_closed_on_unknown_size_tensor_types(self):
        self._write_source(_gguf([("weight", 0, 0), ("future", 999, 32)], b"\x00" * 64))
        self.vessel = os.path.join(self.tmp, "unknown.gguf")
        info = self._create()
        with self.assertRaisesRegex(ValueError, "unknown-size"):
            gguf.tensor(info, "future")
        start = info["data_start"]
        before = _bytes(self.vessel)
        with self.assertRaises(ValueError):
            workshop.write(self.vessel, start, b"WXYZ", "test", info)
        self.assertEqual(_bytes(self.vessel), before)

    def test_interrupted_write_restores_saved_bytes_when_current_range_is_partial(self):
        info = self._create()
        start = info["data_start"]
        original, replacement = b"abcd", b"WXYZ"
        d = workshop._dir(self.vessel)
        os.makedirs(os.path.join(d, "undo"), exist_ok=True)
        with open(os.path.join(d, "undo", "1.bin"), "wb") as fh:
            fh.write(original)
        rec = {"id": 1, "start": start, "bytes": len(replacement), "what": "interrupted",
               "tensor": "weight", "sha_before": workshop._sha(original),
               "sha_after": workshop._sha(replacement), "undone": False}
        with open(self.vessel, "r+b") as fh:
            fh.seek(start)
            fh.write(b"W!cd")
        with open(os.path.join(d, "pending.json"), "w", encoding="utf-8") as fh:
            json.dump(rec, fh)

        self.assertEqual(workshop.journal(self.vessel), [])
        self.assertEqual(_bytes(self.vessel)[start:start + 4], original)
        self.assertFalse(os.path.exists(os.path.join(d, "pending.json")))

    def test_undo_and_write_sync_backup_directory_before_pending_marker(self):
        info = self._create()
        events = []
        original_sync = workshop._fsync_dir
        original_pending = workshop._write_pending

        def record_sync(path):
            events.append(("sync", os.path.abspath(path)))
            return original_sync(path)

        def record_pending(path, rec):
            events.append(("pending", os.path.abspath(path)))
            return original_pending(path, rec)

        undo_dir = os.path.abspath(os.path.join(workshop._dir(self.vessel), "undo"))
        with mock.patch.object(workshop, "_fsync_dir", side_effect=record_sync), \
                mock.patch.object(workshop, "_write_pending", side_effect=record_pending):
            workshop.write(self.vessel, info["data_start"], b"WXYZ", "test", info)
            marker = next(i for i, event in enumerate(events) if event[0] == "pending")
            self.assertIn(("sync", undo_dir), events[:marker])
            events.clear()
            workshop.undo(self.vessel)
            marker = next(i for i, event in enumerate(events) if event[0] == "pending")
            self.assertIn(("sync", undo_dir), events[:marker])

    def test_recovery_rejects_redo_paths_outside_undo_directory(self):
        info = self._create()
        start = info["data_start"]
        row = workshop.write(self.vessel, start, b"WXYZ", "test", info)
        d = workshop._dir(self.vessel)
        victim = os.path.join(self.tmp, "victim")
        with open(victim, "wb") as fh:
            fh.write(b"must remain")
        # Simulate a completed undo whose pending record was altered to point outside undo/.
        with open(self.vessel, "r+b") as fh:
            fh.seek(start)
            fh.write(b"abcd")
        pending = dict(row, operation="undo", redo="../../victim",
                       sha_before=row["sha_after"], sha_after=row["sha_before"])
        with open(os.path.join(d, "pending.json"), "w", encoding="utf-8") as fh:
            json.dump(pending, fh)

        with self.assertRaisesRegex(ValueError, "redo|recovery path"):
            workshop.journal(self.vessel)
        with open(victim, "rb") as fh:
            self.assertEqual(fh.read(), b"must remain")

    def test_interrupted_undo_is_recovered_on_next_use(self):
        info = self._create()
        start = info["data_start"]
        row = workshop.write(self.vessel, start, b"WXYZ", "test", info)
        original_rewrite = workshop._rewrite
        with mock.patch.object(workshop, "_rewrite", side_effect=OSError("simulated interruption")):
            with self.assertRaisesRegex(OSError, "simulated interruption"):
                workshop.undo(self.vessel)
        self.assertEqual(_bytes(self.vessel)[start:start + 4], b"abcd")
        self.assertTrue(os.path.exists(os.path.join(workshop._dir(self.vessel), "pending.json")))
        with mock.patch.object(workshop, "_rewrite", original_rewrite):
            rows = workshop.journal(self.vessel)
        self.assertEqual([r["id"] for r in rows], [row["id"]])
        self.assertTrue(rows[0]["undone"])
        self.assertFalse(os.path.exists(os.path.join(workshop._dir(self.vessel), "pending.json")))

    def test_journal_rewrite_failure_preserves_original_file(self):
        self._create()
        jp = os.path.join(workshop._dir(self.vessel), "journal.jsonl")
        original = b'{"id":1}\n'
        with open(jp, "wb") as fh:
            fh.write(original)
        with mock.patch.object(workshop, "_replace_durable", side_effect=OSError("rename failed")):
            with self.assertRaisesRegex(OSError, "rename failed"):
                workshop._rewrite(self.vessel, [{"id": 2}])
        with open(jp, "rb") as fh:
            self.assertEqual(fh.read(), original)

    def test_recovery_separates_valid_unterminated_final_row(self):
        info = self._create()
        start = info["data_start"]
        rec = workshop.write(self.vessel, start, b"WXYZ", "test", info)
        d = workshop._dir(self.vessel)
        jp = os.path.join(d, "journal.jsonl")
        with open(jp, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"id": 99, "what": "prior row"}))
        with open(os.path.join(d, "pending.json"), "w", encoding="utf-8") as fh:
            json.dump(rec, fh)
        rows = workshop.journal(self.vessel)
        self.assertEqual([r["id"] for r in rows], [99, rec["id"]])
        with open(jp, "rb") as fh:
            data = fh.read()
        self.assertIn(b"}\n{", data)
        for line in data.splitlines():
            json.loads(line)


if __name__ == "__main__":
    unittest.main()


class Held(OSError):
    """An OSError as Windows raises it while another program holds the file (ERROR_SHARING_VIOLATION, 32)."""

    @property
    def winerror(self):
        return 32


class Denied(OSError):
    """Access denied (5): a real refusal, not a passing lock."""

    @property
    def winerror(self):
        return 5


class WindowsFileLocks(unittest.TestCase):
    """Added 2026-11-20: renames and removes of a file athanor has just written are retried while Windows reports
    the file as held by another program (a scanner or indexer), and never otherwise. Ground truth: the calls and
    waits are counted here, against TRIES and WAIT as documented in workshop.py."""

    def setUp(self):
        self.sleeps = []
        patcher = mock.patch.object(workshop.time, "sleep", self.sleeps.append)
        patcher.start()
        self.addCleanup(patcher.stop)

    def flaky(self, failures, error=Held):
        calls = []

        def fn(*args):
            calls.append(args)
            if len(calls) <= failures:
                raise error(13, "held by another process")
            return "done"
        return fn, calls

    def test_a_held_file_is_retried_until_it_is_free(self):
        fn, calls = self.flaky(2)
        self.assertEqual(workshop._retrying(fn, "a", "b"), "done")
        self.assertEqual(calls, [("a", "b")] * 3)
        self.assertEqual(self.sleeps, [workshop.WAIT * 1, workshop.WAIT * 2])

    def test_it_gives_up_after_the_last_try_and_raises_the_lock(self):
        fn, calls = self.flaky(10 ** 6)
        with self.assertRaises(Held):
            workshop._retrying(fn)
        self.assertEqual(len(calls), workshop.TRIES)
        # Each wait exactly, not their sum: summing floats differs in the last bit between Python versions (3.12
        # made sum() compensated), which the 3.11 CI runner showed on 2026-11-20.
        self.assertEqual(self.sleeps, [workshop.WAIT * k for k in range(1, workshop.TRIES)])

    def test_no_other_error_is_retried(self):
        for error in (Denied, PermissionError, FileNotFoundError, OSError):
            fn, calls = self.flaky(1, error)
            with self.subTest(error=error.__name__), self.assertRaises(error):
                workshop._retrying(fn)
            self.assertEqual(len(calls), 1, error.__name__)
        self.assertEqual(self.sleeps, [])
        self.assertFalse(workshop._locked(ValueError("not an OSError")))

    def test_a_pending_marker_is_written_through_a_passing_lock(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        real = workshop._move_once
        fails = [2]

        def move(src, dst):
            if fails[0]:
                fails[0] -= 1
                raise Held(13, "held")
            return real(src, dst)
        with mock.patch.object(workshop, "_move_once", move):
            workshop._write_pending(os.path.join(d, "pending.json"), {"id": 1})
        with open(os.path.join(d, "pending.json"), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), {"id": 1})
        self.assertEqual(os.listdir(d), ["pending.json"])          # no temporary file left behind

    def test_a_held_clean_up_does_not_hide_the_first_error(self):
        """The failure seen on 2026-11-20: the move failed, then removing the temporary file failed too, and the
        second error replaced the first. Now the clean-up waits out the lock and the move's error is the one raised."""
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        real_remove = os.remove
        held = [1]

        def remove(path):
            if held[0]:
                held[0] -= 1
                raise Held(13, "held")
            return real_remove(path)
        with mock.patch.object(workshop, "_move_once", side_effect=Denied(13, "denied")), \
                mock.patch.object(workshop.os, "remove", remove):
            with self.assertRaises(Denied):
                workshop._write_pending(os.path.join(d, "pending.json"), {"id": 1})
        self.assertEqual(os.listdir(d), [])