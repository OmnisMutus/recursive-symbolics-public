"""The agentbase MCP server behind the approval gate (outbound.py).

Ground truth, in the order STANDARD.md asks for it:

1. INDEPENDENT REFERENCE. AGENTBASE_TOOLS below is typed out by hand from agentbase's Go handlers
   (mcp-workspace/apis/*.go), with READ for a tool whose handler only reads the database or checks a
   signature, and WRITE for one that changes state. It is not taken from outbound.py and not from the
   readOnlyHint annotations the server reports about itself, because a server's word about its own tools
   is exactly what the gate does not trust.
2. A SECOND RECORD. Whether a call reached the server is checked against FakeServer's own list of calls it
   received, never against the gate's return value.
3. THE REAL THING. A live test starts the built agentbase binary (mcp-workspace/) over stdio in a throwaway data directory,
   checks that the tools it lists are exactly the table's, and drives a read, a refused write, an approved
   write and a read of the result.
"""
import json
import os
import shutil
import tempfile
import unittest

from reference_agent import mcp, outbound

SERVER = "agentbase"

# From mcp-workspace/apis/{business,policy,hooks,identity}.go. READ = only reads; WRITE = changes state.
AGENTBASE_TOOLS = [
    ("setup_business", "WRITE"),    # creates collections and business_meta rows
    ("transact", "WRITE"),          # writes two ledger rows, may record a nonce, fires webhooks
    ("query_ledger", "READ"),       # SELECT ... GROUP BY account
    ("create_policy", "WRITE"),     # saves a policies row
    ("list_policies", "READ"),      # FindAllRecords("policies")
    ("delete_policy", "WRITE"),     # deletes a policies row: an agent removing its own guardrail
    ("deploy_hook", "WRITE"),       # saves a hooks row that will POST ledger entries elsewhere
    ("list_hooks", "READ"),         # FindAllRecords("hooks")
    ("delete_hook", "WRITE"),       # deletes a hooks row
    ("register_agent", "WRITE"),    # saves an agents row (a signing identity)
    ("verify_signature", "READ"),   # ed25519.Verify against a stored key, writes nothing
]
# From mcp-workspace/apis/workspace_mcp.go, typed out by hand. The server offers these in stdio mode only. ws_brief
# and ws_recall only read (the database, files under a registered root, read-only git commands), the rest
# write workspace rows. Every workspace call also appends its size to the server's usage log (sizes only, never
# content), which is not counted as a write here. On 2026-11-13 the Maintainer decided that the two readers go on the gate's
# read-only list, so the agent reads its own memory without asking; every workspace write still waits for a yes.
WORKSPACE_TOOLS = [
    ("ws_register_project", "WRITE"),  # saves a ws_projects row
    ("ws_record", "WRITE"),            # saves a ws_findings row
    ("ws_recall", "READ"),             # reads findings, summaries and the files they rest on
    ("ws_resolve", "WRITE"),           # sets a finding's resolution
    ("ws_note", "WRITE"),              # saves a ws_notes row
    ("ws_result", "WRITE"),            # saves a ws_results row
    ("ws_brief", "READ"),              # reads findings, summaries, notes, results and git state
    ("ws_summarize", "WRITE"),         # saves or replaces a ws_summaries row
]
READERS = [n for n, k in AGENTBASE_TOOLS + WORKSPACE_TOOLS if k == "READ"]
WRITERS = [n for n, k in AGENTBASE_TOOLS if k == "WRITE"]

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_EXE = os.path.join(REPO, "mcp-workspace", "agentbase.exe" if os.name == "nt" else "agentbase")
EXE = os.environ.get("AGENTBASE_EXE") or DEFAULT_EXE


class FakeServer:
    """Stands in for an MCP server and records every call it is actually asked to make."""

    def __init__(self, name):
        self.name = name
        self.calls = []

    def call(self, tool, arguments=None):
        self.calls.append((tool, dict(arguments or {})))
        return {"text": f"ok:{tool}", "is_error": False}


class TestTheClassification(unittest.TestCase):
    def test_every_agentbase_tool_matches_the_hand_written_table(self):
        for name, expected in AGENTBASE_TOOLS:
            got = "READ" if outbound.is_read_only(name, SERVER) else "WRITE"
            self.assertEqual(got, expected, f"{name} classified {got}, expected {expected}")

    def test_the_read_list_holds_nothing_the_table_does_not_call_a_reader(self):
        self.assertEqual(set(outbound.READ_ONLY_BY_SERVER[SERVER]), set(READERS))

    def test_every_workspace_write_waits_and_only_the_two_readers_pass(self):
        for name, kind in WORKSPACE_TOOLS:
            got = "READ" if outbound.is_read_only(name, SERVER) else "WRITE"
            self.assertEqual(got, kind, f"{name} classified {got}, expected {kind}")

    def test_delete_policy_waits_for_a_yes(self):
        """Removing a guardrail is the one write an agent most wants to make quietly."""
        self.assertFalse(outbound.is_read_only("delete_policy", SERVER))
        self.assertIn("guardrail", outbound.reason("delete_policy", SERVER))

    def test_an_unknown_agentbase_tool_waits(self):
        for name in ("drop_ledger", "transact_v2", ""):
            self.assertFalse(outbound.is_read_only(name, SERVER), name)
        self.assertIn("not a tool this gate knows", outbound.reason("drop_ledger", SERVER))

    def test_an_agentbase_reader_on_another_server_waits(self):
        for name in READERS:
            for other in ("vector", "other", "", "AgentBase-Daemon", "Agentbase"):
                self.assertFalse(outbound.is_read_only(name, other), f"{name} on {other!r}")

    def test_vector_readers_are_not_agentbase_readers(self):
        for name in outbound.READ_ONLY_BY_SERVER["vector"]:
            self.assertFalse(outbound.is_read_only(name, SERVER), name)

    def test_every_writer_says_why(self):
        for name in WRITERS:
            why = outbound.reason(name, SERVER)
            self.assertTrue(why, name)
            self.assertNotIn("not a tool this gate knows", why, name)


class TestTheGate(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.log = os.path.join(self.root, "outbound.jsonl")
        self.cfg = {"outbound": {"log": self.log}}

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def logged(self):
        if not os.path.isfile(self.log):
            return []
        with open(self.log, encoding="utf-8") as fh:
            return [json.loads(l) for l in fh if l.strip()]

    def test_agentbase_readers_pass_without_a_prompt(self):
        asked = []
        gate = outbound.Outbound(cfg=self.cfg, ask=lambda t: asked.append(t) or False)
        s = FakeServer(SERVER)
        for name in READERS:
            self.assertTrue(gate.call(s, name, {"account": "*"})["sent"], name)
        self.assertEqual([c[0] for c in s.calls], READERS)
        self.assertEqual(asked, [])
        self.assertEqual(self.logged(), [])

    def test_with_nobody_to_ask_every_writer_is_refused(self):
        gate = outbound.Outbound(cfg=self.cfg, ask=None)
        s = FakeServer(SERVER)
        for name in WRITERS:
            out = gate.call(s, name, {"rule_name": "cap"})
            self.assertFalse(out["sent"], name)
            self.assertIn("unanswered question is a no", out["why"])
        self.assertEqual(s.calls, [])
        self.assertEqual([r["tool"] for r in self.logged()], WRITERS)
        self.assertTrue(all(r["decision"] == "refused" for r in self.logged()))

    def test_a_declined_writer_never_reaches_the_server(self):
        gate = outbound.Outbound(cfg=self.cfg, ask=lambda _t: False)
        s = FakeServer(SERVER)
        for name in WRITERS:
            self.assertFalse(gate.call(s, name, {})["sent"], name)
        self.assertEqual(s.calls, [])

    def test_an_approved_transfer_shows_its_whole_payload_first(self):
        seen = []
        gate = outbound.Outbound(cfg=self.cfg, ask=lambda t: seen.append(t) or True)
        s = FakeServer(SERVER)
        args = {"from_account": "vault:main", "to_account": "vendor:x", "amount": 250, "memo": "inv-9"}
        self.assertTrue(gate.call(s, "transact", args)["sent"])
        self.assertEqual(s.calls, [("transact", args)])
        for part in ("agentbase: transact", "vault:main", "vendor:x", "250", "moves money"):
            self.assertIn(part, seen[0])

    def test_a_same_named_reader_on_another_server_waits(self):
        gate = outbound.Outbound(cfg=self.cfg, ask=lambda _t: False)
        for other in ("vector", "other", ""):
            s = FakeServer(other)
            self.assertFalse(gate.call(s, "query_ledger", {"account": "*"})["sent"], other)
            self.assertEqual(s.calls, [], other)


class TestTheConfig(unittest.TestCase):
    def test_the_agentbase_block_names_a_command_and_no_secret(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(root, "config.json")
        if not os.path.isfile(path):
            self.skipTest("no config.json on this machine")
        with open(path, encoding="utf-8") as fh:
            block = ((json.load(fh).get("mcp") or {}).get(SERVER))
        if block is None:
            self.skipTest("config.json has no mcp.agentbase block")
        self.assertTrue(str(block.get("command", "")).lower().endswith(("agentbase.exe", "agentbase")))
        self.assertIn("--mcp", block.get("args") or [])
        self.assertEqual(outbound.looks_like_a_key(json.dumps(block)), [])
        for k in block.get("env_keys") or []:
            self.assertRegex(k, r"^[A-Z][A-Z0-9_]*$", "env_keys holds variable names, never values")


@unittest.skipUnless(os.path.isfile(EXE), f"agentbase binary not built at {EXE}")
class TestTheLiveServer(unittest.TestCase):
    def setUp(self):
        self.data = tempfile.mkdtemp(prefix="agentbase_live_")
        cfg = {"mcp": {SERVER: {"command": EXE, "args": ["--mcp", "--dir", self.data], "timeout": 30}}}
        self.server = mcp.from_config(cfg, SERVER).start()

    def tearDown(self):
        self.server.close()
        shutil.rmtree(self.data, ignore_errors=True)

    def test_the_binary_lists_exactly_the_tools_in_the_table(self):
        names = sorted(t["name"] for t in self.server.tools())
        self.assertEqual(names, sorted(n for n, _ in AGENTBASE_TOOLS + WORKSPACE_TOOLS))

    def test_a_read_a_refused_write_an_approved_write_and_the_result(self):
        refusing = outbound.Outbound(cfg={}, ask=None)
        first = refusing.call(self.server, "query_ledger", {"account": "*"})
        self.assertTrue(first["sent"])                               # a reader needs no yes
        self.assertTrue(first["result"]["is_error"])                 # nothing set up yet
        self.assertIn("not initialized", first["result"]["text"])

        self.assertFalse(refusing.call(self.server, "setup_business",
                                       {"business_name": "Live", "currency": "SATS"})["sent"])
        still = refusing.call(self.server, "query_ledger", {"account": "*"})
        self.assertIn("not initialized", still["result"]["text"])   # the refused write left no trace

        approving = outbound.Outbound(cfg={}, ask=lambda _t: True)
        setup = approving.call(self.server, "setup_business", {"business_name": "Live", "currency": "SATS"})
        self.assertIn("SUCCESS", setup["result"]["text"])
        tx = approving.call(self.server, "transact", {"from_account": "a", "to_account": "b", "amount": 7})
        self.assertIn("TRANSACTION POSTED", tx["result"]["text"])
        rows = json.loads(refusing.call(self.server, "query_ledger", {"account": "*"})["result"]["text"])
        self.assertEqual({r["account"]: r["balance"] for r in rows}, {"a": -7, "b": 7})


if __name__ == "__main__":
    unittest.main()
