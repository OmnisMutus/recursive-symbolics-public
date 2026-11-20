# tests/reference_agent_tests/fixtures/

`stub_mcp_server.py` is a small MCP server written independently of `reference_agent/mcp.py`, so the client is
tested against a second implementation of the protocol, including the paged `tools/list`. It writes every call it
really receives to the file named in `STUB_CALLS`, which is how the tests prove a refused call never reached a
server, instead of trusting the gate's own return value. `STUB_DIE=1` makes it exit before answering anything, to test a server that dies at start.
