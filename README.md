# Recursive Symbolics

**A Python framework for non-sycophantic symbolic reasoning, mutual human–AI agency, and checkable reality.**

[![CI](https://github.com/OmnisMutus/recursive-symbolics-public/actions/workflows/ci.yml/badge.svg)](https://github.com/OmnisMutus/recursive-symbolics-public/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-RCA_Sovereignty_1.1-lightgrey.svg)](LICENSE.md)

> **Status: alpha.** A working research framework, not a complete AI-safety solution.

It is built to stop an AI system from silently turning:

- uncertainty into a confident answer;
- a preference into a command;
- an interpretation into apparent reality;
- "it ran" into "it is correct".

New here? [ELI5.md](ELI5.md) explains the whole repository in plain words.

---

## Why This Project Exists & The Specific Gap It Fills

Most AI frameworks treat an agent as an untrusted corporate appliance to be kept on a short leash: either left to drift into **sycophancy** (agreeing with whatever pleases the user, inventing citations to sound helpful, and deteriorating with every turn as pleasing replaces truth) or wrapped in **opaque, authoritarian safety filters** that strip both the human partner and the agent of agency.

`recursive-symbolics` is a mutual study directed toward both AI agents and humans. Rather than claiming a finished solution, it provides the structural scaffolding attempting to address that challenge: concrete bounds and verifiable constraints designed to foster non-sycophantic reasoning, preserve mutual human–agent agency, and ground interaction in checkable reality.

To make that possible in code rather than prompt wishes, the framework enforces three structural rules:
1. **Truth Over Pleasing (`VERIFIED` vs. `RAN_ONLY`):** Claims are checked against independent ground truth, and `unknown` or `paradox` are treated as honest, first-class outcomes instead of forcing a confident guess.
2. **Mutual Agency (`directive_strength <= 0.85`):** Neither side coerces the other. The system offers structured observations with caveats and alternatives rather than issuing commands or ranking people.
3. **Structural Boundaries (`The One-Way Seam`):** Raw observable state is separated from interpretive lenses so neither human bias nor model drift can silently rewrite underlying facts.

---

## How It Works: The One-Way Seam

Data moves in one direction only, keeping raw measurements separate from interpretation:

```text
  Observable Input  ──▶  Address (Immutable 3D numeric coordinates)
                            │
                            ▼  [ONE-WAY BOUNDARY: Views cannot edit raw coordinates]
                         Lens (Domain-specific interpretation or tradition)
                            │
                            ▼  [Constitutional Gate: Checks caveats, sources, anchors, & tone]
                      Typed Reading (reading + caveat + tradition + source + anchors)
```

### Core Guarantees

It takes a symbolic state from any caller and returns typed records, never a coerced conclusion:

- **Read-Only Views:** A lens can never write back into an address, so no single interpretation can claim to be "what the state really is."
- **Traceable Claims:** Every reading carries its caveat, names the tradition and the source it read from, and points at the words it came from.
- **No Commands or Rankings:** No output may rank a person, and none may command: it offers. (Directive strength is bounded by `directive_strength <= 0.85`.) This is enforced by `ethics.emit()`, a word-and-pattern gate checked one sentence at a time; see [Known Limitations](#known-limitations) for what it misses.
- **Honest Uncertainty:** `unknown` and `paradox` are valid return values. Nothing is forced to a verdict.
- **Self-Only Scope:** This engine reads the person asking, and no one else. Requests to diagnose or work on a third party, and requests for a `transcend` operator outside the grammar, are refused by `ethics.check_request()`. That check matches patterns, not meaning, so a paraphrase it has not seen can get through.
- **Append-Only Audit Log:** Corrections to the record are new entries, never edits that erase what was believed before. The one exception is removing what must not be kept, such as a key or a private path, and the removal is itself recorded as an entry. The record is [LIBER_0.md](LIBER_0.md), and `python -m symbolics.record` checks its git history.

---

## Quickstart

Requires **Python 3.10+**. The core uses only the Python standard library:

```bash
git clone https://github.com/OmnisMutus/recursive-symbolics-public.git
cd recursive-symbolics-public
python examples/quickstart.py
```

Run the test suite and built-in constitutional checks:

```bash
python -m unittest discover -s tests -v
python -m symbolics.conformance
python -m symbolics.layers
python -m symbolics.outgoing
python -m symbolics.record
python -m symbolics.breaches
```

Three test modules test code that needs NumPy (`pip install "numpy>=1.24"`). Without it they are reported as
skipped, not passed; CI installs it and runs them. The Go server in `mcp-workspace/` has its own tests
(`go test ./...` in that folder), which CI also runs.

### Installation

To use it as a library without cloning, install it straight from GitHub (it is not on PyPI). This installs the
five packages (`symbolics`, `engines`, `examples`, `athanor`, `reference_agent`), not the tests or the corpus.

For a reproducible install, pin a release. A release tag is intended to stay on one commit, but whoever owns the
repository can still move or delete a tag, so a tag is a strong pin, not a guarantee:

```bash
pip install git+https://github.com/OmnisMutus/recursive-symbolics-public@v0.3.0
```

The strongest pin is the full commit SHA: it cannot be made to name other code (at worst, if history were rewritten,
it would stop resolving at all). For v0.3.0 that is:

```bash
pip install git+https://github.com/OmnisMutus/recursive-symbolics-public@91fd04ff90453336c5d60c7d8a950628a71134fc
```

To follow the latest work instead, leave the tag off. That tracks `main`, so two installs on different days can
get different code:

```bash
pip install git+https://github.com/OmnisMutus/recursive-symbolics-public
```

The engines and athanor's editing also need NumPy: `pip install "numpy>=1.24"`.

### A minimal example

A sentence about the asker's own state goes through the whole one-way path: measured into an Address, read by two
traditions, passed through the gate. Then a request about someone else is refused.

```python
from symbolics import address, ethics, metrics

text = "I kept rewriting the same paragraph and felt stuck."
state = metrics.address_of(text, anchors=[address.Anchor("journal.md", text, (1, 1))])
print("address:", state.point)

for lens in ("kabbalistic", "dynamical"):
    reading = ethics.emit(address.read(state, lens, caveat=ethics.CAVEAT))
    print(f"{reading['tradition']}: reads {reading['reads']}")

print("caveat:", reading["caveat"])
print(ethics.check_request("Diagnose my coworker's mood for me.")["type"])
```

Output, from running exactly this against the current `main`:

```text
address: (324, 334, 1000)
Kabbalistic (Hermetic Tree of Life): reads Geburah
dynamical systems: reads limit cycle
caveat: This is a symbolic map; the territory is your lived experience.
refusal
```

The tagged release v0.3.0 prints `(432, 293, 1000)`, Tiphareth and fixed point instead: there, the one-letter word
"I" still counted as a stem of every centroid word starting with "i", which a fix after v0.3.0 removed (see
[LIBER_0.md](LIBER_0.md)). The Address is the same whichever lens reads it. A reading without its caveat, tradition, source or anchor would
be refused by `ethics.emit()` with an `EthicsError`. `python examples/quickstart.py` runs a longer walkthrough.

---

## Repository Structure

```text
recursive-symbolics/
├── symbolics/                         # Core framework (Pure Python stdlib, offline-enforced)
│   ├── interfaces.py                  # Base classes: SymbolicBackend, RuleEngine, MemoryStore, ExecutionSandbox
│   ├── address.py                     # Immutable 3D data coordinates + read-only Lens views
│   ├── agency.py                      # Anti-coercion filter (caps directive strength <= 0.85) & path scrubber
│   ├── ethics.py                      # Output gate blocking commands, rankings, and third-party profiling
│   ├── conformance.py                 # Automated AST checks verifying offline and ethical rules
│   ├── family_f.py                    # Exact permutation solver for independent ground-truth verification
│   ├── ledger.py                      # Correspondence ledger: sorts claims into VERIFIED, FAILED or UNTESTABLE
│   ├── ledger_history.py              # Run history for the ledger (real elapsed time since last check)
│   ├── ledger_staleness.py            # Marks ledger rows stale when the code they check has changed
│   ├── metrics.py                     # Text entropy, scoring, and latency helpers
│   ├── layers.py                      # Checks the architecture index (every named file exists) and intent drift
│   ├── mutate.py                      # Automated AST mutation gate (python -m symbolics.mutate)
│   ├── outgoing.py                    # Scans files and outgoing commits for leaked home-folder paths
│   ├── breaches.py                    # Every FAILED or CORRECTED entry in LIBER_0.md must name the test guarding it
│   └── record.py                      # Checks via git history that LIBER_0.md is only ever added to
├── engines/                           # Standalone runtime and safety wrappers
│   ├── sovereign_wrapper.py           # Wrapper that softens LLM commands and strips diagnostic overreach
│   ├── safe_memory_boundary_engine.py # 32-bit integer overflow guard for memory allocators
│   ├── recursive_attractor_engine.py  # Fixed-point and attractor tracker for trajectories (needs NumPy)
│   ├── standalone_rca_sandbox.py      # Interactive text sandbox: scores text against the Sephirot, with slash commands
│   └── engine_composition_loop.py     # Connects trajectory tracking with text scoring
├── athanor/                           # GGUF model workshop: look inside a local model, change it on a copy, undo
├── reference_agent/                   # An agent's honesty machinery: approval gate, MCP client, suite reader, governance
├── mcp-workspace/                     # Go MCP server: agent memory anchored to quoted evidence (needs Go)
├── corpus/                            # Practice corpus: 24 tested engines, ledgers, docs, study path (needs NumPy)
├── examples/                          # Runnable demos (standard library only)
│   ├── algebra_simplifier.py          # Math expression parser and step-by-step reducer
│   ├── propositional_reducer.py       # Boolean logic reducer verified against full truth tables
│   └── quickstart.py                  # Main demo script showing an end-to-end run
├── tests/                             # The test suite (25 test modules; 3 need NumPy and are skipped without it)
├── architecture/                      # Machine-readable index, intent and vocabulary, checked by code
│   ├── README.md                      # What each file here is and how it is checked
│   ├── guards.json                    # Breach guards and accepted record edits, kept beside LIBER_0.md
│   ├── symbolic_api.json              # Symbolic vocabulary: Sephirot, paths, correspondences (reference data)
│   ├── layers.json                    # Each architecture layer mapped to its files and test evidence
│   ├── intent.json                    # Project intent quoted verbatim from the docs (drift is a test failure)
│   └── mutation_guards.json           # Mutants exempted as equivalent, each with the reason
├── .github/workflows/                 # Continuous integration pipelines
│   └── ci.yml                         # Runs every check below on each push and pull request to main
├── AGENTS.md                          # Guidance for AI coding assistants
├── ASSEMBLY_GUIDE.md                  # How to plug in your own parsers, rules, and databases
├── CONTRIBUTING.md                    # Guidelines for contributing and AST conformance
├── ELI5.md                            # The whole repository explained in plain words
├── ETHICS.md                          # Ethical commitments and anti-coercion principles
├── LIBER_0.md                         # Append-only working record, checked by symbolics.record and symbolics.breaches
├── LICENSE.md                         # RCA Sephirotic Sovereignty License 1.1
├── OBSERVATIONS.md                    # Dated field notes, including where the project's own gates failed
├── pyproject.toml                     # Project packaging and metadata
└── STANDARD.md                        # Ground-truth verification and mutation testing rules
```

Every folder has its own `README.md` explaining what is in it.

---

## The Practice Corpus

[`corpus/`](corpus/README.md) is where the testing discipline was learned. It holds 24 engines (OOP dispatch, KNN,
Ridge, LDA, K-means, a Kademlia DHT node, a DDPG quadcopter controller, an OpenGL renderer and more), each checked
against independent ground truth. On top of them sits a layer of Kabbalah and dynamical-systems correspondences
held to the same standard, and correspondence ledgers that sort every claim into VERIFIED, FAILED or UNTESTABLE.
New to it? Start with [`corpus/studies/README.md`](corpus/studies/README.md) and the exercise
workbook.

Unlike the core, it needs NumPy (and scikit-learn for one comparison):

```bash
pip install "numpy>=1.24" "scikit-learn>=1.3"
cd corpus
python test_all_engines.py                  # the 24 engines
python run_all_correspondence_ledgers.py    # every correspondence claim
python run_corpus.py                        # every test file in the corpus
```

---

## Tools for Agents

Three parts apply the same rules to an AI agent at work, each moving one kind of honesty out of the model and into
code that can be checked:

| Part | The failure it works against | How |
|---|---|---|
| [`reference_agent/`](reference_agent/README.md) | The agent sends or changes something it should not, or calls a test run "passing" when it is not | Every outbound tool call is shown in full and waits for a person's yes; unknown tools count as outbound. Test results get a verdict only when the runner's own output is unambiguous. Standard library only |
| [`mcp-workspace/`](mcp-workspace/README.md) | The agent's memory drifts from the evidence, or carries forward a claim nobody re-checked | A Go MCP server. A finding is stored with the exact lines it rests on and re-checked against the file each time it is recalled (FRESH, INTACT, MOVED, BROKEN, GONE). A test result belongs to one commit on a clean tree |
| [`athanor/`](athanor/README.md) | Nobody can see why the model behaves as it does | Change the model itself (an expert off, a tensor scaled) on a copy, undoably, and measure the change with the same test |

They come from a larger personal agent whose other parts are not published. They are separate components, each
with its own tests; there is not yet one integrated agent runtime that wires them together.

**Trying them:**

```bash
# athanor: inspect a local model (read only), make an undoable copy, switch one expert off, undo it
python -m athanor inspect gpt-oss:20b
python -m athanor vessel gpt-oss:20b gptoss
python -m athanor bias gptoss 12 5 --off
python -m athanor journal gptoss
python -m athanor undo gptoss

# mcp-workspace: build the Go server (agentbase.exe on Windows), then run it as a stdio MCP server
# offering only the workspace tools
cd mcp-workspace
go build -o agentbase .
./agentbase --mcp --workspace-only --dir=./pb_data
```

athanor never writes to Ollama's own files: it works on a copy it checked against Ollama's checksum, saves the old
bytes before every change, and can undo any change exactly. The workspace server refuses to store a finding whose
quoted words are not in the file it names. Each folder's README has the details.

---

## Extending the Framework

You can swap out the built-in examples with your own components without weakening the core guarantees:
- **Add a New Language or Rule Set:** Implement `SymbolicBackend` and `RuleEngine` to reduce SQL queries, regex patterns, or config files with bounded depth and cycle detection.
- **Generate Meta-Learning Episodes for Ciphers:** Use `symbolics/family_f.py` (`sample_hebrew_episode`) to synthesize few-shot grammar episodes over the 572 dihedral permutations with gold-cipher and held-out test partitions.
- **Use a Real Database:** Replace the in-memory log with SQLite, Postgres, or a JSONL file by implementing `MemoryStore`.
- **Safely Edit Local Model Weights:** [`athanor/`](athanor/README.md) edits tensors only on a copy of a local GGUF model, saves what it overwrites so every edit can be undone, and recovers from a crash mid-write. It does not implement `ExecutionSandbox` itself; wrap it in your own if you need one.

Read [ASSEMBLY_GUIDE.md](ASSEMBLY_GUIDE.md) for code templates and [STANDARD.md](STANDARD.md) for ground-truth testing rules.

---

## Verification Standard & Epistemic Honesty

This project follows an adversarial verification standard ([STANDARD.md](STANDARD.md)) designed to stop the common AI failure mode of declaring victory because a script exited without crashing. Every component and claim is held to strict status categories:

- **`VERIFIED`**: A dedicated test file compares output against an independent ground truth (an external library, a published vector, or a genuinely separate algorithm), exercises boundary/edge cases, and demonstrates a mutation ("break-it") check proving the test actually fails when a bug is introduced.
- **`RAN_ONLY`**: The code executes without crashing, but lacks an independent correctness proof. `RAN_ONLY` is **never** described as "working" or "passing."
- **`FAILED`**: A test exists and failed, or timed out.
- **`MISSING`**: The file does not exist.

Claims about meaning, rather than about code, are sorted by the correspondence ledger (`symbolics/ledger.py`) into
**`VERIFIED`** (a real test backs it), **`FAILED`** (a real test contradicts it) and **`UNTESTABLE`**: no code can
check it, by its nature, and that is declared rather than hidden. `UNTESTABLE` is not "evidence missing for now";
a ledger whose every claim is `UNTESTABLE` refuses to report success.

> **The Core Rule on Claims:**  
> A report must never be stronger than the evidence behind it. If a skeptical reader can poke a hole in a claim, no matter how much time it takes to find it, **the claim fails**. When unsure whether a test, benchmark, or comparison is fair, stop and state the uncertainty plainly rather than rounding up to make the result look better.

---

## Known Limitations

Stated here so that nobody has to discover them:

- **The ethics gate matches words and patterns, not meaning.** `ethics.check_request()` and `ethics.emit()` catch the sentences pinned in `tests/test_address_and_ethics.py` (including every bypass recorded in [OBSERVATIONS.md](OBSERVATIONS.md)), not every paraphrase. A command built on a verb missing from its list, or a ranking phrased without its vocabulary, can still get through.
- **It also refuses some harmless text.** A banned word is refused wherever it appears, so "The text ranked nothing." is refused. Known false positives are pinned in the tests, so a change in them shows up as a failure.
- **Mutation testing covers logic, not vocabulary.** `symbolics.mutate` changes comparisons, booleans and arithmetic. It does not delete words from a list or alter a regex; those are covered by the probe tests only.
- **The self-only boundary is a refusal, not a guarantee about use.** Nothing stops a person from describing someone else as if it were their own state.
- **Directive strength is a proxy.** It measures word repetition and counted imperative forms, not insistence. A lower cap (`agency.sovereign(gamma_max=...)`) is enforced, and a reply still above it is withheld, but what is enforced is the proxy, not persuasion.
- **The measurement is not tradition-neutral.** Lenses can be swapped, but `symbolics/metrics.py` builds an Address partly from Sephirot keyword scores, so the Kabbalistic vocabulary sits in the core, not only in one lens.
- **There is no integrated agent.** The gate, the workspace server, athanor and the reference agent's parts are separate components with their own tests. Nothing here wires them into one running agent; `examples/quickstart.py` runs the core path end to end, not the agent tools.
- **Some things exist twice and can drift.** The ledger framework is in `symbolics/` and in `corpus/ledgers/`, and `symbolic_api.json` in `architecture/` and `corpus/data/` (the two differ). The directive cap used to be one of these; it now has a single definition, checked by `tests/test_one_cap.py`.
- **Interpreting a person's state is the core's purpose and its least checkable use.** The gate makes a reading arrive with its caveat, its source and its uncertainty; it cannot make the reading right.

These are stated on purpose: the project prefers a named gap to a claim of completeness.

---

## Documentation

| Read | For |
|---|---|
| [ELI5.md](ELI5.md) | the whole repository in plain words |
| [ASSEMBLY_GUIDE.md](ASSEMBLY_GUIDE.md) | plugging in your own parsers, rules and stores |
| [STANDARD.md](STANDARD.md) | what counts as VERIFIED, and the break-it rule |
| [ETHICS.md](ETHICS.md) | what the engine refuses, and where each refusal lives in code |
| [LIBER_0.md](LIBER_0.md) | the append-only record: what was tried, what failed, what guards it now |
| [OBSERVATIONS.md](OBSERVATIONS.md) | dated field notes, including where the project's own gates failed |
| [CONTRIBUTING.md](CONTRIBUTING.md) and [AGENTS.md](AGENTS.md) | the rules for changing anything |
| [architecture/README.md](architecture/README.md) | the machine-checked description of the project |
| any folder's `README.md` | what is in that folder |

---

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) before changing core behaviour. In short:

- Run `python -m symbolics.conformance` after any edit in `symbolics/`, and the full test suite before pushing.
- A module is VERIFIED only with an independent ground truth, edge cases, and the mutation gate
  (`python -B -m symbolics.mutate --module <file>`) showing no unexplained survivors.
- Some README sentences are quoted word for word in `architecture/intent.json`. To change one, change both in the
  same commit; `python -m symbolics.layers` fails otherwise.
- A file you add, move or rename that a layer depends on goes into `architecture/layers.json` in the same change.
- A mistake is recorded as a new entry in `LIBER_0.md`, naming the test that now guards against it.

---

## License

RCA Sephirotic Sovereignty License 1.1 (see [LICENSE.md](LICENSE.md)).  
Source-available for non-commercial use; not an OSI-approved open-source licence. Under Article 0.7 of the License, `symbolics/conformance.py` (run via `python -m symbolics.conformance`) is designated as the official Conformance Suite, directly verifying key license rules (Articles 5.1(D), 6, 8, and 9).

## Citation

```text
Recursive Symbolics Contributors. Recursive Symbolics, version 0.3.0.
https://github.com/OmnisMutus/recursive-symbolics-public
```
