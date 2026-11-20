# mcp-workspace/apis/

The server's Go package: every MCP tool and the guard behind it, with the tests beside them.

| File | What it holds |
|---|---|
| `mcp.go` | The MCP server, tool registration, the HTTP/SSE mount and bearer-token auth for remote use |
| `workspace.go`, `workspace_mcp.go` | The workspace: findings anchored to quoted lines, unknowns, notes, results. Its `ws_` tools are registered for local stdio use only |
| `workspace_usage.go` | Appends each workspace call's size (never its content) to a usage log |
| `business.go` | `setup_business`, `transact`, `query_ledger`: double-entry accounting in whole numbers |
| `policy.go` | Guardrail policies, evaluated inside the same database transaction as the transfer; fails closed |
| `hooks.go` | Webhooks, with host allowlist, no redirects, and the resolved IP pinned at connect time (SSRF hardening) |
| `identity.go` | ed25519 agent keys, signatures, and one-use nonces against replay |
| `link_windows.go`, `link_other.go` | Whether a path component is a symlink or junction, so a project path cannot escape its root |
| `*_test.go` | The tests. Which guard each protects, and the mutation shown to make it fail, is in [`../STANDARD.md`](../STANDARD.md) |

Run the tests from `mcp-workspace/`:

```bash
go test -count=1 ./...
```
