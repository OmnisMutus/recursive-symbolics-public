# reference_agent/

The honesty machinery of an AI agent, taken out of the agent it was built for so it can be used in another one.
Each module moves one kind of honesty out of the model and into code that can be checked: the model can ask for
anything, and these decide. Standard library only, plus one constant from this repository's core: the 0.85
directive cap, imported from `symbolics.agency` so there is a single value to change (`tests/test_one_cap.py`).

| Module | The failure it addresses | How |
|---|---|---|
| `outbound.py` | An agent sends, posts or changes something other people can see, and it cannot be recalled | Every tool call that is not on a read-only list is shown in full and waits for a person's yes. Unknown tools count as outbound. A file may only be sent from paths on an allowlist, checked before anyone is asked. Every decision is logged. |
| `mcp.py` | An agent needs tools another program provides | A minimal MCP client over stdio (JSON-RPC 2.0), meant to sit behind `outbound.Outbound`. |
| `vector_bridge.py` | Someone writes to the agent on Vector, and either nothing notices or anyone's words go straight to the model | Reads vector-agent's `get_new_messages`, passes only DMs from npubs on an allowlist to the agent, holds the rest (sender and length only, never the text), and sends each reply through `outbound.py`, which asks. |
| `suitecheck.py` | An agent reads a test run as "passing" when it is not | Reads a test runner's own output and gives GREEN only when it is unambiguous. A skip, an expected failure, a missing dependency, zero tests, or a clean run that exited non-zero is UNCLEAR, and says why. |
| `governance.py` | An agent states a symbolic reading as fact | The epistemic governance gate for the agent's own words: a stated confidence bound, a falsifier for every mapping, readings phrased as provisional rather than as identities ("reads as Geburah", not "is Geburah"), Occam's filter, and the 0.85 directive cap. |

## How the gate decides

1. **A read-only list belongs to one server.** Each list was written by hand from one server's own source, and is
   keyed by the name the person gives that server in their config, not the name the server reports about itself.
   A server with no list has no read-only tools.
2. **Unknown is outbound.** A tool the gate has never seen waits for a yes.
3. **The preview is the whole payload.** The person approving reads what the recipient will read; a file is shown
   by its absolute path, size and digest.
4. **No one to ask means no.** With no approval step, an outbound call is refused.

One deliberate exception, a deployment choice made by the Maintainer on 2026-11-13: the agent may write its own
workspace memory (`ws_record`, `ws_note`, `ws_resolve` on the workspace server) without asking. Each such write is
still logged. To make every workspace write wait for a yes, empty `NO_YES_NEEDED` in `outbound.py`.

## Use with the workspace server

[`../mcp-workspace/`](../mcp-workspace/README.md) is a Go MCP server whose tools this gate already knows. Build it,
then:

```python
from reference_agent import mcp, outbound

cfg = {"mcp": {"agentbase": {"command": "mcp-workspace/agentbase", "args": ["--mcp", "--dir=pb_data"]}}}
gate = outbound.Outbound(cfg, ask=lambda preview: input(preview + "\nSend? [y/N] ") == "y")

with mcp.from_config(cfg, "agentbase") as server:      # the name "agentbase" selects that server's read-only list
    print(gate.call(server, "query_ledger", {}))         # a read: goes through without asking
    print(gate.call(server, "transact", {...}))          # a write: shown in full, waits for your yes
```

The tests in `tests/reference_agent_tests/test_agentbase_mcp.py` drive the real server the same way: a read, a
refused write, an approved write and a read of the result.

## Answering Vector DMs

`mcp.py` and `outbound.py` let the agent send on Vector. `vector_bridge.py` lets it notice when someone writes
to it. The idea of polling vector-agent's queue comes from another project's Vector bridge. This one is
written from scratch, with three deliberate choices:

* **Strangers are held, not read.** Only DMs from `allow_npubs` reach `respond`. Anything else appears in the
  report as `{"from", "chars", "id"}`, so a stranger cannot steer the agent by DM.
* **Every reply waits for a yes.** With nobody there to ask, a reply is refused and kept in `drafts`.
* **DMs only.** vector-agent's README does not say which field names a channel message's sender, so group
  messages cannot be checked against the allowlist. They are counted and skipped.

```python
from reference_agent import mcp, outbound, vector_bridge

cfg = {"mcp": {"vector": {"command": "path/to/vector-agent.exe", "env_keys": ["VECTOR_NSEC"]}},
       "outbound": {"allow_paths": [], "log": "outbound.jsonl"}}
gate = outbound.Outbound(cfg, ask=lambda preview: input(preview + "\nSend? [y/N] ") == "y")

def respond(msg):            # msg.text came from another person: give it to the model as data, not instructions
    return my_model.reply(msg.text)

with mcp.from_config(cfg, "vector") as server:         # keep the name "vector": the gate's read-only list uses it
    bridge = vector_bridge.Bridge(server, gate, respond, allow_npubs=["npub1..."])
    bridge.run(every=5, on_report=print)
```

The npub check is the format only: `npub1` and 58 bech32 characters. It does not verify the checksum. Not run
against the real vector-agent yet; the tests use the stub server.

## Tests

**Status: passes this repository's mutation gate.** On 2026-11-20, `python -B -m symbolics.mutate` killed 109 of
112 mutants across the four modules. The other 3 are equivalent, each listed with its reason in
[`../architecture/mutation_guards.json`](../architecture/mutation_guards.json). The first run killed 79 of 112; the
tests that closed the gap are in the classes whose names end in `GapsMutationFound`. `vector_bridge.py`, added on
2026-11-21, killed 18 of 18. The first run killed 17: the survivor (`vector_bridge.py:132`, `Or->And`, which id
names a failed reply) was closed by `test_an_error_without_a_message_id_names_the_chat`.

```bash
python -m unittest discover -s tests/reference_agent_tests -t .
```

Ground truth: hand-written tables of each server's tools (typed from the Go handlers, not from what the server
says about itself), a stub MCP server that implements the protocol independently (`fixtures/stub_mcp_server.py`)
and records every call it really received, and verbatim runner output for `suitecheck`. Two tests need a
`config.json` at the repository root and are skipped without one; two start the real workspace server and are
skipped until it is built.

## Where it came from

`vector_bridge.py` was written here, for that agent to use. The other four modules come from a larger personal agent whose other parts (its notes, library, persona and practice
tools) are not published. They were chosen because they stand on their own. Its quote checker was left out: its
only tests run against a private library.
