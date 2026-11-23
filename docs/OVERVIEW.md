# Overview for developers

## What this is

Recursive Symbolics is an alpha, source-available Python framework for symbolic reasoning that resists several
common AI failure modes: fabricated certainty, coercive phrasing, person-ranking, third-party diagnosis, and false
claims that passing code means a result is correct.

It separates observation from interpretation. `symbolics/metrics.py` creates a three-axis `Address`, a `Lens` in
`symbolics/address.py` provides a tradition-specific interpretation, and `symbolics/ethics.py` performs the final
gate. The repository then applies the same "check it independently and explicitly record uncertainty" discipline
to agents, tests, model editing, and workspace memory.

The intended users are developers and researchers building symbolic tools or AI-agent infrastructure who want
verifiable boundaries, append-only records, human approval gates, and auditable evidence. It is explicitly not a
complete AI-safety solution or proof that symbolic correspondences describe reality. What it does not do yet is
listed under "Known limitations" in the [README](../README.md#known-limitations).

### Stack

- **Language(s):** Python 3.10+ for the core, examples, tests, agent machinery, and model tooling; Go 1.27.4 for
  the MCP server.
- **Framework / runtime:** A standard-library-first Python package; Go with PocketBase and `mcp-go`.
- **Notable libraries:** NumPy for selected engines and GGUF decoding, scikit-learn for corpus comparisons,
  PocketBase for embedded storage, `mcp-go` for protocol handling, and `dbx` for database queries.

The Python package has no required runtime dependencies: `pyproject.toml` declares an empty `dependencies` list.
Optional groups cover NumPy engines and the NumPy/scikit-learn corpus. The project is licensed under the RCA
Sephirotic Sovereignty License 1.1, permitting non-commercial source use rather than conventional OSI open-source
licensing.

## How it's organized

```text
symbolics/
  reading.py          Public read/readings API
  metrics.py          Text measurement and Address construction
  address.py          Three-axis state space and immutable lenses
  ethics.py           Request and output safety gate
  agency.py           Directive-strength measurement and 0.85 cap
  interfaces.py       Backends, rule engines, memory, and sandbox contracts
  ledger.py           VERIFIED / FAILED / UNTESTABLE claim tracking
  conformance.py      License-duty and no-network conformance suite
  mutate.py           Break-it mutation testing
  record.py           Append-only history checker
  breaches.py         Failed-entry guard checker
  layers.py           Architecture and intent consistency checks

examples/
  quickstart.py       Complete demonstrations
  algebra_simplifier.py
  propositional_reducer.py

athanor/
  GGUF inspection and copy-on-write model modification
  Undoable tensor edits, recovery journals, and Ollama vessel loading

reference_agent/
  outbound.py         Human approval and outbound-call classification
  mcp.py              Minimal MCP stdio client
  governance.py       Epistemic wording checks
  suitecheck.py       Conservative test-run status interpretation
  vector_bridge.py    Polling and approval-controlled Vector messaging

mcp-workspace/
  main.go             Stdio MCP, remote SSE, and usage-report entrypoints
  apis/               Ledger, policy, identity, webhook, and workspace tools
  STANDARD.md         Guard-by-guard break-it verification record

engines/
  sovereign_wrapper.py
  safe_memory_boundary_engine.py
  recursive_attractor_engine.py
  standalone_rca_sandbox.py
  engine_composition_loop.py

corpus/
  engines/            24 practice implementations, with their studies and benchmarks
  ledgers/            Symbolic-correspondence claim ledgers
  studies/            Exercises and onboarding material
  tests/              Independent correctness suites
  test_all_engines.py
  run_corpus.py

architecture/
  layers.json         Repository implementation map
  intent.json         Quoted intent that must remain aligned with the docs
  guards.json         Breach guards
  mutation_guards.json
  symbolic_api.json   Symbolic vocabulary and correspondences
```

**How it fits together:** The main Python API begins in `symbolics.reading.read()`, which first checks the
request, then measures text, builds an evidence-carrying `Address`, applies the requested lens, and returns only a
record accepted by `ethics.emit()`. Downstream packages use more general contracts from `symbolics/interfaces.py`:
backends parse and evaluate expressions, rule engines reduce bounded rewrite chains to fixed points, memory
implementations maintain integrity, and execution sandboxes isolate mutations.

The agent infrastructure is separate. `reference_agent/outbound.py` decides whether an MCP call is read-only or
outbound, previews payloads, restricts sent files, waits for human approval when required, and logs decisions.
`mcp-workspace/` exposes both ledger tools and local-only workspace evidence tools. `athanor/` is similarly
independent: it works on a copied GGUF vessel and journals every tensor change for exact undo and crash recovery.

The repository also has two different ideas of truth. The core tracks whether code satisfies executable claims;
the `corpus/ledgers/` machinery additionally distinguishes VERIFIED technical mappings from UNTESTABLE
philosophical or metaphysical claims.

## How to run it

Use Python 3.10 or newer for the core. NumPy enables the optional engine and Athanor coverage; scikit-learn is
needed for one corpus comparison. To get the code, follow "Quick start" in the [README](../README.md#quick-start).

Try the public API. `read()` is on `main`; the v0.3.0 release does not have it yet.

```python
import symbolics

reading = symbolics.read(
    "I kept rewriting the same paragraph and felt stuck.",
)
print(reading)
print(reading.reads)
print(reading.candidates)
print(reading.address)
```

Run the end-to-end reference demos:

```bash
python examples/quickstart.py
```

Run the Python suite and repository checks:

```bash
python -m unittest discover -s tests -v
python -m symbolics.conformance
python -m symbolics.layers
python -m symbolics.outgoing
python -m symbolics.record
python -m symbolics.breaches
python -B -m symbolics.mutate
```

Install optional engine dependencies:

```bash
python -m pip install "numpy>=1.24"
python -m pip install "numpy>=1.24" "scikit-learn>=1.3"
```

Build the Go MCP server:

```bash
cd mcp-workspace
go vet ./...
go test -count=1 ./...
go build -o agentbase .
```

Run it as a local stdio MCP server:

```bash
./agentbase --mcp --dir=./pb_data
```

For an inspector-only workspace session:

```bash
./agentbase --mcp --workspace-only --dir=./pb_data
```

Remote SSE requires `AGENTBASE_API_KEY`. Webhook access additionally requires explicit host and protocol
configuration through `AGENTBASE_HOOK_HOSTS` and the repository's related environment settings.

Athanor's main workflow is:

```bash
python -m athanor inspect gpt-oss:20b
python -m athanor vessel gpt-oss:20b gptoss
python -m athanor off gptoss "12:5"
python -m athanor ollama gptoss athanor-gptoss
python -m athanor pristine gptoss
python -m athanor undo gptoss
```

It also has `values` (look at a tensor's numbers), `bias` (change one expert's router bias), `scale` (multiply a
tensor or one expert of it) and `journal` (list the changes made to a vessel). `python -m athanor --help` lists
them all.

## Try asking

- How does `metrics.address_of()` derive the severity-mercy, descent, and entropy axes in `symbolics/metrics.py`?
- How does `mcp-workspace/` recheck workspace evidence and report FRESH, MOVED, or BROKEN findings?
- How does Athanor preserve and recover undo data in `athanor/workshop.py` when an interrupted GGUF edit occurs?
