"""Calling another program's tools (mcp.py) and the gate in front of them (outbound.py).

Ground truth, in the order STANDARD.md asks for it:

1. INDEPENDENT REFERENCE. VECTOR_TOOLS below is the tool list from crates/vector-agent/README.md in
   VectorPrivacy/Vector, typed out with the judgement each one deserves: READ for a tool that only reads,
   SEND for one that leaves this machine. It was written from their documentation, not from outbound.py, and
   it is the table the classification is checked against.
2. A SECOND IMPLEMENTATION. The transport is exercised against a stub server (tests/fixtures/stub_mcp_server.py)
   that implements the protocol independently, including the tools/list cursor. The stub writes every call it
   is asked to perform to a file, so "nothing was sent" is checked by the absence of a line rather than by
   this module's own return value.
3. BY HAND. The two rules that matter are asserted directly: an unknown tool needs approval, and a file
   outside the allowlist is refused before anyone is asked.
"""
import gc
import json
import os
import shutil
import sys
import tempfile
import unittest
import warnings

from reference_agent import mcp, outbound

STUB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "stub_mcp_server.py")

# From crates/vector-agent/README.md. READ = only reads; SEND = leaves this machine or changes what others see.
VECTOR_TOOLS = [
    ("my_npub", "READ"), ("current_account", "READ"), ("list_accounts", "READ"),
    ("add_account", "SEND"), ("swap_account", "SEND"),
    ("get_new_messages", "READ"), ("list_chats", "READ"), ("get_messages", "READ"), ("sync_dms", "READ"),
    ("send_dm", "SEND"), ("send_file", "SEND"),
    ("get_profile", "READ"), ("load_profile", "READ"), ("get_blocked_users", "READ"),
    ("update_profile", "SEND"), ("set_nickname", "SEND"), ("block_user", "SEND"), ("unblock_user", "SEND"),
    ("list_communities", "READ"), ("list_pending_invites", "READ"), ("sync_community_channel", "READ"),
    ("join_community", "SEND"), ("accept_pending_invite", "SEND"), ("send_community_message", "SEND"),
    ("leave_community", "SEND"), ("create_community", "SEND"), ("edit_community_metadata", "SEND"),
    ("delete_community", "SEND"),
]


class Base(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.calls = os.path.join(self.root, "calls.jsonl")
        self.log = os.path.join(self.root, "outbound.jsonl")
        self.sendable = os.path.join(self.root, "sendable")
        os.makedirs(self.sendable, exist_ok=True)
        self.ok_file = os.path.join(self.sendable, "report.txt")
        with open(self.ok_file, "w", encoding="utf-8") as fh:
            fh.write("a report\n")
        self.secret = os.path.join(self.root, "secret.txt")
        with open(self.secret, "w", encoding="utf-8") as fh:
            fh.write("the diary\n")
        os.environ["STUB_CALLS"] = self.calls
        self.cfg = {"outbound": {"allow_paths": [self.sendable], "log": self.log}}

    def tearDown(self):
        os.environ.pop("STUB_CALLS", None)
        os.environ.pop("STUB_DIE", None)
        shutil.rmtree(self.root, ignore_errors=True)

    def server(self, **kw):
        # the stub stands in for vector-agent, so it carries the name config.json gives that server
        return mcp.MCPServer(sys.executable, [STUB], name=kw.pop("name", "vector"), timeout=20, **kw)

    def made(self):
        if not os.path.isfile(self.calls):
            return []
        with open(self.calls, encoding="utf-8") as fh:
            return [json.loads(l) for l in fh if l.strip()]

    def logged(self):
        if not os.path.isfile(self.log):
            return []
        with open(self.log, encoding="utf-8") as fh:
            return [json.loads(l) for l in fh if l.strip()]


class TestTheClassification(unittest.TestCase):
    def test_every_tool_in_their_readme(self):
        for name, expected in VECTOR_TOOLS:
            got = "READ" if outbound.is_read_only(name, "vector") else "SEND"
            self.assertEqual(got, expected, f"{name} classified {got}, expected {expected}")

    def test_a_tool_this_gate_has_never_seen_needs_approval(self):
        """A server adds tools in its next release. Naming the senders would let a new one through on the
        day it appears, so the list names the readers and everything else waits for a yes."""
        self.assertFalse(outbound.is_read_only("send_zap", "vector"))
        self.assertFalse(outbound.is_read_only("", "vector"))
        self.assertIn("not a tool this gate knows", outbound.reason("send_zap", "vector"))

    def test_a_reader_on_one_server_is_not_a_reader_on_another(self):
        """The list was written from vector-agent's README. A second server's get_messages could do anything."""
        for name, kind in VECTOR_TOOLS:
            if kind == "READ":
                self.assertFalse(outbound.is_read_only(name, "other"), name)
                self.assertFalse(outbound.is_read_only(name, ""), name)
                self.assertIn("no read-only list", outbound.reason(name, "other"))

    def test_every_outbound_tool_says_why(self):
        for name, kind in VECTOR_TOOLS:
            if kind == "SEND":
                self.assertTrue(outbound.reason(name, "vector"), name)
                self.assertNotIn("not a tool this gate knows", outbound.reason(name, "vector"), name)


class TestTheTransport(Base):
    def test_the_handshake_and_both_pages_of_the_tool_list(self):
        with self.server() as s:
            self.assertEqual(s.server_info.get("name"), "stub")
            names = [t["name"] for t in s.tools()]
        self.assertEqual(names, ["my_npub", "get_messages", "send_dm", "send_file", "brand_new_tool"])

    def test_a_call_returns_its_text(self):
        with self.server() as s:
            out = s.call("my_npub", {})
        self.assertTrue(out["text"].startswith("ok:my_npub"))
        self.assertFalse(out["is_error"])

    def test_a_server_error_is_raised_not_returned_as_success(self):
        with self.server() as s:
            with self.assertRaises(mcp.MCPError) as caught:
                s.call("boom", {})
        self.assertIn("no such tool", str(caught.exception))

    def test_a_missing_environment_variable_says_which(self):
        s = self.server(env_keys=["VECTOR_NSEC_DEFINITELY_UNSET"])
        with self.assertRaises(mcp.MCPError) as caught:
            s.start()
        self.assertIn("VECTOR_NSEC_DEFINITELY_UNSET", str(caught.exception))
        self.assertIn("never stores", str(caught.exception))

    def test_a_server_that_will_not_start_is_an_error_with_its_output(self):
        os.environ["STUB_DIE"] = "1"
        with self.assertRaises(mcp.MCPError):
            self.server().start()

    def test_a_command_that_does_not_exist(self):
        s = mcp.MCPServer("/nonexistent/vector-agent", name="vector")
        with self.assertRaises(mcp.MCPError) as caught:
            s.start()
        self.assertIn("cannot start", str(caught.exception))


class TestNothingLeavesWithoutAYes(Base):
    def test_a_read_only_call_is_not_gated(self):
        gate = outbound.Outbound(cfg=self.cfg, ask=None)
        with self.server() as s:
            out = gate.call(s, "get_messages", {"chat_id": "npub1x"})
        self.assertTrue(out["sent"])
        self.assertEqual([c["name"] for c in self.made()], ["get_messages"])
        self.assertEqual(self.logged(), [])            # a read is not a decision worth recording

    def test_a_same_named_reader_on_another_server_waits_for_a_yes(self):
        """The hole this closes: matched on the tool name alone, a second server's get_messages passed ungated."""
        gate = outbound.Outbound(cfg=self.cfg, ask=lambda _t: False)
        with self.server(name="other") as s:
            out = gate.call(s, "get_messages", {"chat_id": "npub1x"})
        self.assertFalse(out["sent"])
        self.assertEqual(self.made(), [])              # the other server was never asked
        self.assertEqual(self.logged()[0]["server"], "other")
        self.assertEqual(self.logged()[0]["decision"], "declined")

    def test_with_nobody_to_ask_an_outbound_call_is_refused(self):
        gate = outbound.Outbound(cfg=self.cfg, ask=None)
        with self.server() as s:
            out = gate.call(s, "send_dm", {"to_npub": "npub1x", "content": "hello"})
        self.assertFalse(out["sent"])
        self.assertIn("unanswered question is a no", out["why"])
        self.assertEqual(self.made(), [])              # the stub was never asked
        self.assertEqual(self.logged()[0]["decision"], "refused")

    def test_a_declined_call_never_reaches_the_server(self):
        gate = outbound.Outbound(cfg=self.cfg, ask=lambda _t: False)
        with self.server() as s:
            out = gate.call(s, "send_dm", {"to_npub": "npub1x", "content": "hello"})
        self.assertFalse(out["sent"])
        self.assertEqual(self.made(), [])
        self.assertEqual(self.logged()[0]["decision"], "declined")

    def test_an_approved_call_goes_through_and_is_recorded(self):
        seen = []
        gate = outbound.Outbound(cfg=self.cfg, ask=lambda text: seen.append(text) or True)
        with self.server() as s:
            out = gate.call(s, "send_dm", {"to_npub": "npub1x", "content": "hello"})
        self.assertTrue(out["sent"])
        self.assertEqual([c["name"] for c in self.made()], ["send_dm"])
        self.assertEqual(self.logged()[0]["decision"], "sent")
        self.assertIn("hello", seen[0])                # what was approved contained the message

    def test_an_unknown_tool_is_gated_like_a_sender(self):
        gate = outbound.Outbound(cfg=self.cfg, ask=lambda _t: False)
        with self.server() as s:
            out = gate.call(s, "brand_new_tool", {})
        self.assertFalse(out["sent"])
        self.assertEqual(self.made(), [])

    def test_an_approval_step_that_raises_sends_nothing(self):
        def explode(_text):
            raise RuntimeError("the prompt broke")
        gate = outbound.Outbound(cfg=self.cfg, ask=explode)
        with self.server() as s:
            out = gate.call(s, "send_dm", {"to_npub": "npub1x", "content": "hello"})
        self.assertFalse(out["sent"])
        self.assertIn("the prompt broke", out["why"])
        self.assertEqual(self.made(), [])


class TestTheFileAllowlist(Base):
    def test_a_file_outside_the_allowlist_is_refused_without_asking(self):
        """Their README says send_file can send any file the process can read, and this process can read the
        vault. An approval prompt is not the safeguard for a path nobody meant to be sendable."""
        asked = []
        gate = outbound.Outbound(cfg=self.cfg, ask=lambda t: asked.append(t) or True)
        with self.server() as s:
            out = gate.call(s, "send_file", {"to_npub": "npub1x", "file_path": self.secret})
        self.assertFalse(out["sent"])
        self.assertIn("outside every declared allow_paths root", out["why"])
        self.assertEqual(asked, [])                    # nobody was asked
        self.assertEqual(self.made(), [])

    def test_a_file_inside_the_allowlist_still_needs_a_yes(self):
        gate = outbound.Outbound(cfg=self.cfg, ask=lambda _t: False)
        with self.server() as s:
            out = gate.call(s, "send_file", {"to_npub": "npub1x", "file_path": self.ok_file})
        self.assertFalse(out["sent"])
        self.assertEqual(self.logged()[0]["decision"], "declined")

    def test_an_allowed_file_sends_once_approved(self):
        gate = outbound.Outbound(cfg=self.cfg, ask=lambda _t: True)
        with self.server() as s:
            out = gate.call(s, "send_file", {"to_npub": "npub1x", "file_path": self.ok_file})
        self.assertTrue(out["sent"])
        self.assertEqual([c["name"] for c in self.made()], ["send_file"])

    def test_without_an_allowlist_no_file_may_be_sent(self):
        gate = outbound.Outbound(cfg={}, ask=lambda _t: True)
        ok, _real, why = outbound.check_path(self.ok_file, {})
        self.assertFalse(ok)
        self.assertIn("nothing on this disk is sendable", why)
        with self.server() as s:
            self.assertFalse(gate.call(s, "send_file", {"file_path": self.ok_file})["sent"])

    def test_a_symlink_out_of_the_allowlist_does_not_get_in(self):
        link = os.path.join(self.sendable, "innocent.txt")
        target = self.secret
        jdir = None
        try:
            try:
                os.symlink(target, link)
            except (OSError, NotImplementedError):
                if os.name == "nt":
                    import subprocess
                    outside = os.path.join(self.root, "outside")
                    os.makedirs(outside, exist_ok=True)
                    target = os.path.join(outside, "secret.txt")
                    with open(target, "w", encoding="utf-8") as fh:
                        fh.write("the diary\n")
                    jdir = os.path.join(self.sendable, "linked_outside")
                    r = subprocess.run(["cmd", "/c", "mklink", "/J", jdir, outside], capture_output=True)
                    if r.returncode != 0:
                        self.skipTest("neither symlinks nor junctions are available here")
                    link = os.path.join(jdir, "secret.txt")
                else:
                    self.skipTest("symlinks are not available here")
            ok, real, why = outbound.check_path(link, self.cfg)
            self.assertFalse(ok)
            self.assertEqual(real, os.path.realpath(target))
            self.assertIn("outside every declared allow_paths root", why)
        finally:
            if jdir and os.path.lexists(jdir):
                try:
                    os.rmdir(jdir)
                except OSError:
                    pass

    def test_a_path_that_is_not_there_is_refused(self):
        ok, _r, why = outbound.check_path(os.path.join(self.sendable, "nope.txt"), self.cfg)
        self.assertFalse(ok)
        self.assertIn("no file at this path", why)


class TestThePreview(Base):
    def test_it_carries_the_whole_message_not_a_summary(self):
        body = "line one\nline two\nline three"
        text = outbound.preview("send_dm", {"to_npub": "npub1abc", "content": body}, self.cfg, "vector")
        for line in body.splitlines():
            self.assertIn(line, text)
        self.assertIn("npub1abc", text)
        self.assertIn("cannot be recalled", text)
        self.assertIn(outbound.digest(body), text)

    def test_a_file_is_identified_by_size_and_digest(self):
        text = outbound.preview("send_file", {"to_npub": "n", "file_path": self.ok_file}, self.cfg)
        self.assertIn(self.ok_file, text)
        self.assertIn("bytes", text)
        self.assertIn("sha256", text)

    def test_a_refused_path_says_so_in_the_preview(self):
        text = outbound.preview("send_file", {"file_path": self.secret}, self.cfg)
        self.assertIn("REFUSED", text)

    def test_arguments_are_never_silently_dropped(self):
        text = outbound.preview("send_community_message",
                                {"channel_id": "c1", "content": "hi", "replied_to": "m9"}, self.cfg)
        self.assertIn("replied_to", text)
        self.assertIn("m9", text)


class TestTurningApprovalOff(Base):
    def test_it_takes_an_explicit_setting_and_is_recorded(self):
        cfg = {"outbound": {"allow_paths": [self.sendable], "log": self.log, "require_approval": False}}
        gate = outbound.Outbound(cfg=cfg, ask=None)
        with self.server() as s:
            out = gate.call(s, "send_dm", {"to_npub": "n", "content": "hi"})
        self.assertTrue(out["sent"])
        self.assertIn("approval turned off", self.logged()[0]["why"])

    def test_it_does_not_defeat_the_allowlist(self):
        """Turning off the prompt is a statement about convenience, not about which files are sendable."""
        cfg = {"outbound": {"allow_paths": [self.sendable], "log": self.log, "require_approval": False}}
        gate = outbound.Outbound(cfg=cfg, ask=None)
        with self.server() as s:
            out = gate.call(s, "send_file", {"to_npub": "n", "file_path": self.secret})
        self.assertFalse(out["sent"])
        self.assertEqual(self.made(), [])


class TestCloseReleasesEverything(Base):
    """close() used to close stdin and stop the process but leave stdout and stderr open, and a start() whose
    handshake failed left the process and all three pipes behind, since __exit__ never runs after __enter__
    raises.

    Ground truth: the interpreter's own ResourceWarning, which CPython raises from a file object's finalizer
    when it is collected while still open, and from Popen's when the process was never waited on. Neither is
    computed by mcp.py. The pipes' own `closed` attributes and the process' return code are checked as well.
    """

    def unclosed_after(self, run):
        # Collect first, and keep only the two shapes this module can leak (an unclosed pipe is a FileIO, an
        # unwaited process is reported by Popen), so garbage left by other test modules is not blamed on it.
        gc.collect()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            run()
            gc.collect()
        return [str(w.message) for w in caught if issubclass(w.category, ResourceWarning)
                and ("FileIO" in str(w.message) or "subprocess" in str(w.message))]

    def test_all_three_pipes_are_closed_and_the_process_has_ended(self):
        s = self.server().start()
        proc = s.proc
        s.close()
        self.assertTrue(proc.stdin.closed, "stdin")
        self.assertTrue(proc.stdout.closed, "stdout")
        self.assertTrue(proc.stderr.closed, "stderr")
        self.assertIsNotNone(proc.returncode)
        self.assertIsNone(s.proc)

    def test_a_used_server_leaves_nothing_for_the_collector(self):
        def run():
            with self.server() as s:
                s.call("my_npub", {})
        self.assertEqual(self.unclosed_after(run), [])

    def test_a_failed_start_leaves_nothing_behind(self):
        os.environ["STUB_DIE"] = "1"

        def run():
            s = self.server()
            with self.assertRaises(mcp.MCPError):
                s.start()
            self.assertIsNone(s.proc)
        self.assertEqual(self.unclosed_after(run), [])

    def test_close_twice_and_close_unstarted_are_harmless(self):
        self.server().close()
        s = self.server().start()
        s.close()
        s.close()
        self.assertIsNone(s.proc)


if __name__ == "__main__":
    unittest.main()


class TestNoKeyIsEverInTheTree(unittest.TestCase):
    """The design claim is that the server's key lives in the environment and this repository never holds it.
    config.json names the VARIABLE, never the value. A claim about a repository should be checkable, so this
    runs the scanner over the whole working tree.

    Ground truth: the shapes themselves, with a real-form sample of each planted in this file's own fixtures
    below. A scanner that finds nothing proves nothing unless it is shown to find something.
    """

    # Not keys. Correctly-shaped strings, invented here, so the scanner is proved to work before it is
    # trusted to report zero. The nsec data part uses the bech32 charset and is 58 characters.
    BECH32 = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
    SAMPLES = (
        ("nsec1" + (BECH32 * 2)[:58], "Nostr private key"),
        ("sk-" + "A" * 24, "API key of the sk- form"),
        ("-----BEGIN OPENSSH PRIVATE KEY-----", "PEM private key"),
        ("ghp_" + "b" * 36, "GitHub personal access token"),
        ("xoxb-" + "1234567890-abcdefgh", "Slack token"),
    )

    def test_the_scanner_finds_each_shape(self):
        for sample, what in self.SAMPLES:
            found = outbound.looks_like_a_key(f"token = {sample}  # in a config")
            self.assertTrue(found, f"{what} was not detected")
            self.assertIn(what.split()[0].casefold(), found[0][0].casefold())

    def test_it_shows_only_a_prefix_never_the_whole_thing(self):
        sample = self.SAMPLES[0][0]
        found = outbound.looks_like_a_key(sample)
        self.assertNotIn(sample, found[0][1])
        self.assertTrue(found[0][1].endswith("..."))

    def test_ordinary_text_is_not_a_key(self):
        for benign in ("npub1abcdef", "nsec", "sk-", "the nsec goes in an environment variable",
                       'env_keys": ["VECTOR_NSEC"]', "-----BEGIN CERTIFICATE-----"):
            self.assertEqual(outbound.looks_like_a_key(benign), [], benign)

    def test_it_finds_a_planted_file(self):
        root = tempfile.mkdtemp()
        try:
            with open(os.path.join(root, "leaked.json"), "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"VECTOR_NSEC": self.SAMPLES[0][0]}))
            found = outbound.scan(root)
            self.assertEqual([f["file"] for f in found], ["leaked.json"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_the_repository_holds_none(self):
        """The one that matters. Runs over this working tree, including config.json."""
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        found = [f for f in outbound.scan(root)
                 if os.path.basename(f["file"]) != os.path.basename(__file__)]
        self.assertEqual(found, [], f"something key-shaped is in the tree: {found}")

    def test_config_names_the_variable_and_not_a_value(self):
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        path = os.path.join(root, "config.json")
        if not os.path.isfile(path):
            self.skipTest("no config.json on this machine")
        with open(path, encoding="utf-8") as fh:
            cfg = json.load(fh)
        for name, block in ((cfg.get("mcp") or {})).items():
            self.assertNotIn("nsec", json.dumps(block).casefold(),
                             f"the {name} server block mentions a key; it may name env_keys only")


class TestTheGapsMutationFound(unittest.TestCase):
    """Added 2026-11-20 for the public repository: each test kills a mutant of outbound.py that survived the
    original suite. Ground truth is stated in each test, never read back from the module."""

    SAMPLE = "sk-" + "A" * 24                 # an invented key shape, as in TestNoKeyIsEverInTheTree

    def test_a_file_of_exactly_two_million_bytes_is_still_scanned(self):
        """outbound.py:145, getsize > 2_000_000: the limit skips files LARGER than 2,000,000 bytes, so a file of
        exactly that size is read, and one byte more is not."""
        root = tempfile.mkdtemp()
        try:
            for name, size in (("at_limit.txt", 2_000_000), ("over_limit.txt", 2_000_001)):
                with open(os.path.join(root, name), "w", encoding="ascii", newline="") as fh:
                    fh.write(self.SAMPLE + " " * (size - len(self.SAMPLE)))
                self.assertEqual(os.path.getsize(os.path.join(root, name)), size)
            self.assertEqual([f["file"] for f in outbound.scan(root)], ["at_limit.txt"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_the_reason_names_the_server_or_says_it_has_none(self):
        """outbound.py:170, server or 'a server with no name'."""
        self.assertIn("comes from elsewhere,", outbound.reason("send_dm", "elsewhere"))
        self.assertIn("comes from a server with no name,", outbound.reason("send_dm", ""))

    def test_the_preview_lists_other_arguments_only_when_there_are_some(self):
        """outbound.py:238 and :241. A recipient and a message are shown in their own lines, never again under
        'other arguments'; an empty or None argument is not an argument; 'no arguments' means exactly that."""
        both = outbound.preview("send_dm", {"to_npub": "npub1x", "content": "hi"}, server="vector")
        self.assertIn("  to: to_npub=npub1x", both)
        self.assertNotIn("other arguments", both)
        self.assertNotIn("no arguments", both)
        blank = outbound.preview("ping", {"flag": "", "n": None}, server="vector")
        self.assertIn("  no arguments", blank)
        self.assertNotIn("other arguments", blank)
        extra = outbound.preview("ping", {"limit": 5}, server="vector")
        self.assertIn('  other arguments: {"limit": 5}', extra)
        self.assertNotIn("no arguments", extra)

    def test_the_log_is_written_into_a_folder_that_did_not_exist(self):
        """outbound.py:267, dirname(log) or ".": the gate creates the log's folder. The log swallows its own
        errors on purpose, so only the file on disk shows whether it was written."""
        root = tempfile.mkdtemp()
        try:
            log = os.path.join(root, "not", "yet", "there", "outbound.jsonl")
            gate = outbound.Outbound(cfg={}, ask=None, log_path=log)
            gate.decide("send_dm", {"to_npub": "npub1x", "content": "hi"}, "vector")
            with open(log, encoding="utf-8") as fh:
                rows = [json.loads(line) for line in fh]
            self.assertEqual(len(rows), 1)
        finally:
            shutil.rmtree(root, ignore_errors=True)

class TestTheClientGapsMutationFound(unittest.TestCase):
    """Added 2026-11-20 for the public repository: each test kills a mutant of mcp.py that survived the original
    suite. Ground truth: the stub's fixed answers, JSON-RPC 2.0's message shapes, and values written here."""

    FIXTURES = os.path.dirname(STUB)

    def test_the_server_starts_in_its_working_folder(self):
        """mcp.py:38, cwd or None: a server named by a path relative to its own folder starts only there."""
        with mcp.MCPServer(sys.executable, [os.path.basename(STUB)], cwd=self.FIXTURES, name="vector",
                           timeout=20) as s:
            self.assertEqual(s.server_info.get("name"), "stub")

    def test_a_notification_carries_an_object_for_params(self):
        """mcp.py:137, params or {}: JSON-RPC 2.0 allows params to be omitted or structured, never null."""
        s, sent = mcp.MCPServer("unused"), []
        s._send = sent.append
        s._notify("notifications/initialized")
        self.assertEqual(sent, [{"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}])

    def test_a_silent_server_times_out_with_the_seconds_it_waited(self):
        """mcp.py:150. A server that only prints noise never answers; after the deadline the client says so in
        an MCPError naming the wait, rather than failing some other way."""
        noisy = "import time\nwhile True:\n    print('noise', flush=True)\n    time.sleep(0.05)\n"
        s = mcp.MCPServer(sys.executable, ["-c", noisy], name="noisy", timeout=1)
        with self.assertRaises(mcp.MCPError) as caught:
            s.start()
        self.assertIn("noisy: no answer to initialize in 1s.", str(caught.exception))
        self.assertIsNone(s.proc)                       # a failed start closes what it opened

    def test_a_server_error_names_its_message_and_code_exactly(self):
        """mcp.py:163, err.get('message') or err: the message text, not the whole error object."""
        with mcp.MCPServer(sys.executable, [STUB], name="vector", timeout=20) as s:
            with self.assertRaises(mcp.MCPError) as caught:
                s.call("boom", {})
        self.assertIn("vector: tools/call refused: no such tool (code -32000)", str(caught.exception))

    def test_the_stderr_tail_is_joined_into_one_line(self):
        """mcp.py:168."""
        s = mcp.MCPServer("unused")
        self.assertEqual(s.stderr_tail(), "The server said nothing.")
        s._stderr = ["one", "two", "three", "four"]
        self.assertEqual(s.stderr_tail(), "Last from the server: two | three | four")

    def test_only_named_tools_are_listed(self):
        """mcp.py:177: a tool without a name, or an entry that is not an object, is not a tool."""
        s = mcp.MCPServer("unused")
        s._rpc = lambda method, params=None, timeout=None: {
            "tools": [{"name": "a"}, {"description": "no name"}, "junk", {"name": ""}]}
        self.assertEqual(s.tools(), [{"name": "a"}])

    def test_only_text_content_is_read_as_text(self):
        """mcp.py:187: other content types are named in brackets; an entry that is not an object is skipped."""
        s = mcp.MCPServer("unused")
        s._rpc = lambda method, params=None, timeout=None: {
            "content": [{"type": "text", "text": "hi"}, {"type": "image", "data": "x"}, "junk"]}
        self.assertEqual(s.call("anything")["text"], "hi\n[image]")

    def test_the_configured_timeout_is_used_and_30_seconds_otherwise(self):
        """mcp.py:203, block.get("timeout") or 30."""
        cfg = {"mcp": {"a": {"command": "x", "timeout": 5}, "b": {"command": "x"}}}
        self.assertEqual(mcp.from_config(cfg, "a").timeout, 5.0)
        self.assertEqual(mcp.from_config(cfg, "b").timeout, 30.0)