# Recursive Symbolics

**A Python framework for checkable, non-sycophantic symbolic reasoning.**

[![CI](https://github.com/OmnisMutus/recursive-symbolics-public/actions/workflows/ci.yml/badge.svg)](https://github.com/OmnisMutus/recursive-symbolics-public/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-RCA_Sovereignty_1.1-lightgrey.svg)](LICENSE.md)

> **Status:** Alpha research framework. It is usable for experiments and reference implementations, but it is not a complete AI-safety solution or a source of clinical or philosophical truth.

Minds, human and artificial alike, slip in four quiet ways:

- uncertainty becomes a confident answer;
- a preference becomes a command;
- an interpretation becomes apparent reality;
- "it ran" becomes "it is correct".

An AI does it to please. Someone tells a chatbot about a run of coincidences and asks whether it means
something. The chatbot says yes: it is a sign, they see what others miss, and it understands them as no one else
does. Each reply is warmer than the last, and none of it was checked. A person does it too, often to themselves:
an assumption that resonates, that simply feels right, is taken as a fact that was verified.

The usual cure, a stern filter, takes the decision away from both of them.

Recursive Symbolics puts checks against those slips in code, where they can be tested. It turns text into a
structured symbolic address, applies optional lenses, and passes every result through explicit ethical and agency
checks. Around that core it provides tools for:

- Verification and mutation testing
- Evidence-linked agent memory
- Human approval gates for outbound actions
- Append-only audit records
- Controlled, reversible editing of local GGUF model copies

New here? The [plain-language overview](docs/ELI5.md) explains the whole repository simply, and the
[developer overview](docs/OVERVIEW.md) covers the stack, every folder and the commands.

## Quick start

Python 3.10 or newer is required. The core package uses only the Python standard library.

```bash
git clone https://github.com/OmnisMutus/recursive-symbolics-public.git
cd recursive-symbolics-public
python -m pip install -e .
python examples/quickstart.py
```

```python
import symbolics

reading = symbolics.read(
    "I kept rewriting the same paragraph and felt stuck."
)

print(reading)
# Reads as Geburah under the Kabbalistic (Hermetic Tree of Life) lens.
# This sits between Geburah and Binah and Tiphareth; which feels more true for you?
# This is a symbolic map; the territory is your lived experience.
```

A reading says what it found, offers the alternatives, asks a question back, and always carries its caveat.
`read()` is on `main`; the v0.3.0 release does not have it yet.

## Example API

```python
import symbolics

reading = symbolics.read(
    "I kept rewriting the same paragraph and felt stuck.",
    lens="dynamical",
)

print(reading.reads)        # 'limit cycle'
print(reading.candidates)   # ['limit cycle', 'contraction', 'fixed point']
print(reading.address)      # (324, 334, 1000)
print(reading.as_dict())    # the whole record, as a plain dict
```

Available lenses:

```python
symbolics.lenses()
# ['dynamical', 'kabbalistic']
```

Requests about a third person are refused, while statements about the person’s own experience may be read:

```python
symbolics.read("Diagnose my coworker's mood.").type
# 'refusal'

symbolics.read("I was angry at my brother and ended the session early").type
# 'reading'
```

Empty or punctuation-only input returns an unknown result instead of a reading:

```python
symbolics.read("").type
# 'unknown'
```

Words about to be said, your own draft or a program's reply, can be checked for the slips before they go out:

```python
symbolics.check("You must meditate every morning. It is the only way.").slips
# ['command', 'only way']

symbolics.check("Anger is Geburah.").slips
# ['identity']
```

See [the API guide](docs/API.md) for records, refusals, sources, line anchors, exceptions, and checks.

## How a reading is made

```text
text
  -> address and measurements
  -> lens-specific interpretation
  -> ethics and agency checks
  -> typed reading, refusal, or unknown
```

1. `symbolics/metrics.py` derives a three-axis address.
2. `symbolics/address.py` reads that address through an isolated lens.
3. `symbolics/ethics.py` requires evidence, caveats, traditions, and non-coercive language.
4. `symbolics/reading.py` exposes the result as a read-only `Record`.

A lens is an interpretation, not a statement that the symbolic address is objective reality. The framework also acknowledges that its present measurements are partly derived from Kabbalistic vocabulary.

## What it promises

It takes a symbolic state from any caller and returns typed records, never a coerced conclusion.

- A lens can never write back into an address, so no single interpretation can claim to be what the state
  really is.
- Every reading carries its caveat, names the tradition and the source it read from, and points at the words it came from.
- No output may rank a person, and none may command: it offers. The gate, `ethics.emit()`, checks this one
  sentence at a time, and caps how directive a reply may be (`directive_strength <= 0.85`).
- `unknown` and `paradox` are honest answers. Nothing is forced to a verdict.
- This engine reads the person asking, and no one else.
- Corrections to the record are new entries, never edits that erase what was believed before. The one exception is removing what must not be kept, such as a key or a private path, and the removal is itself recorded as an entry. The record is [LIBER_0.md](LIBER_0.md), and `python -m symbolics.record` checks its git history.

## Repository map

| Directory | Purpose |
|---|---|
| [`symbolics/`](symbolics/README.md) | Core reading, ethics, agency, interfaces, ledgers, and verification. Standard library only, and nothing in it reaches the network |
| [`examples/`](examples/README.md) | Algebra and propositional-logic reference implementations, starting with `quickstart.py` |
| [`engines/`](engines/README.md) | Standalone symbolic, attractor, and safety engines (some need NumPy) |
| [`athanor/`](athanor/README.md) | Copy-on-write GGUF model editing with undo and crash recovery |
| [`reference_agent/`](reference_agent/README.md) | Approval gates and MCP agent infrastructure |
| [`mcp-workspace/`](mcp-workspace/README.md) | Go MCP server for ledger and evidence-linked workspace tools |
| [`corpus/`](corpus/README.md) | 24 practice engines and correspondence ledgers, where the testing discipline was learned |
| [`architecture/`](architecture/README.md) | Machine-readable architecture, intent, guards, and vocabulary |
| [`tests/`](tests/README.md) | Core and integration test suites |
| [`docs/`](docs/README.md) | The two overviews, and the API, assembly, and ethics guides |

## Three key tools

They are separate parts, each with its own tests; nothing here wires them into one running agent yet.

### MCP workspace memory

[`mcp-workspace/`](mcp-workspace/README.md) is a local Go MCP server whose workspace notes retain exact file evidence.

On recall, evidence is classified as:

- **FRESH** — its file and blob are unchanged
- **INTACT** — the file changed elsewhere; the evidence remains at the same lines
- **MOVED** — the evidence occurs elsewhere in the file
- **BROKEN** — the evidence is missing
- **GONE** — the file is missing

FRESH means the evidence is unchanged, not that the note was right.

```bash
cd mcp-workspace
go test -count=1 ./...
go build -o agentbase .
./agentbase --mcp --dir=./pb_data
```

### Outbound agent approvals

[`reference_agent/outbound.py`](reference_agent/outbound.py) previews tool calls and requires human approval before unknown or changing operations. Read-only operations are classified by server-specific allowlists rather than guessed from names.

The default rule is fail closed: if a server has no read-only list or nobody is available to approve an outbound call, the call is refused.

### GGUF model workbench

[`athanor/`](athanor/README.md) works only on a copy of a local GGUF model. It journals tensor changes, stores the previous bytes, supports undo and pristine checks, and attempts crash recovery before retrying normal commands.

```bash
python -m athanor vessel gpt-oss:20b gptoss
python -m athanor off gptoss "12:5"
python -m athanor journal gptoss
python -m athanor undo gptoss
```

## Verification

"It ran" is not "it works". The repository distinguishes execution from evidence:

- **VERIFIED** — independent ground truth, edge cases, and a mutation or break-it check
- **RAN_ONLY** — code ran but has no correctness evidence; it is never called passing
- **FAILED** — a test contradicted the implementation
- **MISSING** — no implementation or test file exists

[STANDARD.md](STANDARD.md) has the rules. The checks:

```bash
python -m unittest discover -s tests -v
python -m symbolics.conformance
python -m symbolics.layers
python -m symbolics.outgoing
python -m symbolics.record
python -m symbolics.breaches
python -B -m symbolics.mutate      # the mutation gate; slow
```

Three test modules need NumPy and are reported as skipped without it. The corpus also needs scikit-learn for one
comparison:

```bash
python -m pip install "numpy>=1.24" "scikit-learn>=1.3"

cd corpus
python test_all_engines.py
python run_all_correspondence_ledgers.py
python run_corpus.py
```

CI runs the Python suites, mutation gate, Athanor break-it tests, Go server tests, and corpus runners on every push and pull request.

## Install

The package is not on PyPI. Install it straight from GitHub, from `main`:

```bash
pip install git+https://github.com/OmnisMutus/recursive-symbolics-public
```

or from the v0.3.0 release, which does not have `read()` yet:

```bash
pip install git+https://github.com/OmnisMutus/recursive-symbolics-public@v0.3.0
```

A tag can still be moved by whoever owns the repository; for a pin that cannot, put the release's full commit
SHA, `91fd04ff90453336c5d60c7d8a950628a71134fc`, in place of the tag. The engines and athanor's editing also need
NumPy.

## Known limitations

Stated here so that nobody has to discover them:

- **The gate matches words and patterns, not meaning.** It catches the sentences pinned in
  `tests/test_address_and_ethics.py`, not every paraphrase, and it also refuses some harmless text: a banned word
  is refused wherever it appears, so "The text ranked nothing." is refused.
- **Reading a person's state is the core's purpose and its least checkable use.** It is not a diagnosis. The gate
  makes a reading arrive with its caveat, its source and its uncertainty; it cannot make the reading right.
- **The self-only boundary is a refusal, not a guarantee.** Nothing stops a person from describing someone else
  as if it were their own state.
- **Directive strength is a proxy** for persuasion, not a direct measurement of it.
- **The measurement is not tradition-neutral.** Lenses can be swapped, but the address is built partly from
  Kabbalistic keyword scores. Symbolic correspondences are not claims that the metaphors are objectively true.
- **Mutation testing covers logic, not vocabulary.** It changes comparisons, booleans and arithmetic, not word
  lists or regexes; the probe tests cover those.
- **Some things exist twice and can drift.** The ledger framework is in `symbolics/` and in `corpus/ledgers/`, and
  `symbolic_api.json` in `architecture/` and `corpus/data/` (the two differ).
- **Some optional tests need NumPy, scikit-learn, Ollama, or platform permissions.**

The project prefers a named gap to a claim of completeness.

## Read next

- [Plain-language overview](docs/ELI5.md)
- [Developer overview](docs/OVERVIEW.md)
- [API reference](docs/API.md)
- [Assembly and integration guide](docs/ASSEMBLY_GUIDE.md)
- [Testing standard](STANDARD.md)
- [Ethics and refusals](docs/ETHICS.md)
- [Append-only project record](LIBER_0.md)
- [Dated observations](OBSERVATIONS.md), including where the project's own gates failed

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) and [AGENTS.md](AGENTS.md) before changing core behaviour. In short:

- Run `python -m symbolics.conformance` after any edit in `symbolics/`, and the full test suite before pushing.
- A module is VERIFIED only with an independent ground truth, edge cases, and the mutation gate
  (`python -B -m symbolics.mutate --module <file>`) showing no unexplained survivors.
- The sentences under "What it promises" are quoted word for word in `architecture/intent.json`. To change one,
  change both in the same commit; `python -m symbolics.layers` fails otherwise.
- A file you add, move or rename that a layer depends on goes into `architecture/layers.json` in the same change.
- A mistake is recorded as a new entry in `LIBER_0.md`, naming the test that now guards against it.

## License

RCA Sephirotic Sovereignty License 1.1 (see [LICENSE.md](LICENSE.md)). Source-available and free for
non-commercial use; not an OSI-approved open-source licence. Under Article 0.7 of the License,
`symbolics/conformance.py` (run via `python -m symbolics.conformance`) is the official Conformance Suite, checking
Articles 5.1(D), 6, 8 and 9.

## Citation

```text
Recursive Symbolics Contributors. Recursive Symbolics, version 0.3.0.
https://github.com/OmnisMutus/recursive-symbolics-public
```
