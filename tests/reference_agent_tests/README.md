# tests/reference_agent_tests/

Tests for the [`reference_agent/`](../../reference_agent/README.md) package.

| File | What it checks |
|---|---|
| `test_mcp.py` | The MCP client against a stub server, the approval gate (nothing leaves without a yes, unknown tools wait, the file allowlist, turning approval off), and that nothing key-shaped is anywhere in this repository |
| `test_agentbase_mcp.py` | The gate's read-only list for the workspace server, against a table typed by hand from its Go handlers. Two live tests start the real server from `mcp-workspace/` and are skipped until it is built |
| `test_suitecheck.py` | Reading a test run honestly, against verbatim output from real runners |
| `test_governance.py` | The epistemic governance gate, against the framework's own stated rules |
| `fixtures/` | The stub MCP server. See its README. |

Two tests read a `config.json` at the repository root and are skipped when there is none, as in a fresh clone.
