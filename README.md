# Recursive Symbolics

[![CI](https://github.com/OmnisMutus/recursive-symbolics-public/actions/workflows/ci.yml/badge.svg)](https://github.com/OmnisMutus/recursive-symbolics-public/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-RCA_Sovereignty_1.1-lightgrey.svg)](LICENSE.md)

> **Status: alpha.** A working research framework, not a complete AI-safety solution.

Minds, human and artificial alike, slip in four quiet ways:

- uncertainty becomes a confident answer;
- a preference becomes a command;
- an interpretation becomes apparent reality;
- "it ran" becomes "it is correct".

This repository puts checks against those slips in code, where they can be tested, rather than in a prompt or a
promise. The checks hold the person and the program alike, and neither one gets to override the other.

New here? [ELI5.md](ELI5.md) explains the whole repository in plain words.

## Try it

Python 3.10 or newer. The core uses only the standard library.

```bash
git clone https://github.com/OmnisMutus/recursive-symbolics-public.git
cd recursive-symbolics-public
python
```

```python
>>> import symbolics
>>> print(symbolics.read("I kept rewriting the same paragraph and felt stuck."))
Reads as Geburah under the Kabbalistic (Hermetic Tree of Life) lens.
This sits between Geburah and Binah and Tiphareth; which feels more true for you?
This is a symbolic map; the territory is your lived experience.
>>> symbolics.read("I kept rewriting the same paragraph and felt stuck.", lens="dynamical").reads
'limit cycle'
>>> symbolics.read("Diagnose my coworker's mood for me.").type
'refusal'
```

A reading says what it found, offers the alternatives, asks a question back, and always carries its caveat. A
request about someone else is refused. [SIMPLE_API.md](SIMPLE_API.md) explains `read()` in full, and
`python examples/quickstart.py` walks through the parts underneath it. `read()` is on `main`; the v0.3.0 release
does not have it yet.

## What it promises

It takes a symbolic state from any caller and returns typed records, never a coerced conclusion. Text moves one
way only:

```text
text ──▶ Address (numbers measured from the words) ──▶ Lens (one tradition's reading) ──▶ gate ──▶ reading
```

- A lens can never write back into an address, so no single interpretation can claim to be what the state
  really is.
- Every reading carries its caveat, names the tradition and the source it read from, and points at the words it came from.
- No output may rank a person, and none may command: it offers. The gate, `ethics.emit()`, checks this one
  sentence at a time, and caps how directive a reply may be (`directive_strength <= 0.85`).
- `unknown` and `paradox` are honest answers. Nothing is forced to a verdict.
- This engine reads the person asking, and no one else.
- Corrections to the record are new entries, never edits that erase what was believed before. The one exception is removing what must not be kept, such as a key or a private path, and the removal is itself recorded as an entry. The record is [LIBER_0.md](LIBER_0.md), and `python -m symbolics.record` checks its git history.

The same rule applies to the code: "it ran" is not "it works". A module counts as VERIFIED only when its tests
check it against an independent ground truth and a mutation check shows they catch planted bugs. Code that only
runs is RAN_ONLY, and is never called passing. [STANDARD.md](STANDARD.md) has the rules.

## What's here

| Folder | What it is |
|---|---|
| [`symbolics/`](symbolics/README.md) | The core: the reading path, and the checks that keep the repository honest about itself. Standard library only, and nothing in it reaches the network |
| [`tests/`](tests/README.md) | The test suite |
| [`examples/`](examples/README.md) | Runnable demos, starting with `quickstart.py` |
| [`engines/`](engines/README.md) | Standalone engines built on the core (some need NumPy) |
| [`reference_agent/`](reference_agent/README.md) | Honesty for an AI agent at work: every outbound tool call waits for a person's yes, and a test run gets a verdict only when its output is unambiguous |
| [`mcp-workspace/`](mcp-workspace/README.md) | A Go MCP server: an agent's memory, stored with the exact lines it rests on and re-checked each time it is recalled |
| [`athanor/`](athanor/README.md) | Change a local GGUF model (switch an expert off, scale a tensor) on a copy, with every change undoable |
| [`corpus/`](corpus/README.md) | Where the testing discipline was learned: 24 engines and the correspondence ledgers (needs NumPy and scikit-learn) |
| [`architecture/`](architecture/README.md) | The machine-checked description of the project |

The three agent tools are separate parts, each with its own tests; nothing here wires them into one running
agent yet.

## Run the checks

```bash
python -m unittest discover -s tests
python -m symbolics.conformance
python -m symbolics.layers
python -m symbolics.outgoing
python -m symbolics.record
python -m symbolics.breaches
python -B -m symbolics.mutate      # the mutation gate; slow
```

Three test modules need NumPy (`pip install "numpy>=1.24"`) and are reported as skipped without it. CI runs all
of the above, the Go server's tests and the corpus on every push to `main`.

## Install

It is not on PyPI. Install a release straight from GitHub:

```bash
pip install git+https://github.com/OmnisMutus/recursive-symbolics-public@v0.3.0
```

Leave off `@v0.3.0` to follow `main` instead. A tag can still be moved by whoever owns the repository; for a pin
that cannot, put the release's full commit SHA, `91fd04ff90453336c5d60c7d8a950628a71134fc`, in place of the tag.
The engines and athanor's editing also need NumPy.

## Known limitations

Stated here so that nobody has to discover them:

- **The gate matches words and patterns, not meaning.** It catches the sentences pinned in
  `tests/test_address_and_ethics.py` (including every bypass recorded in [OBSERVATIONS.md](OBSERVATIONS.md)), not
  every paraphrase. A command built on a verb missing from its list, or a ranking phrased without its vocabulary,
  can still get through.
- **It also refuses some harmless text.** A banned word is refused wherever it appears, so "The text ranked
  nothing." is refused. Known false positives are pinned in the tests, so a change in them shows up as a failure.
- **Mutation testing covers logic, not vocabulary.** `symbolics.mutate` changes comparisons, booleans and
  arithmetic. It does not delete words from a list or alter a regex; the probe tests cover those.
- **The self-only boundary is a refusal, not a guarantee about use.** Nothing stops a person from describing
  someone else as if it were their own state.
- **Directive strength is a proxy.** It counts repeated words and imperative forms, not insistence. A lower cap
  (`agency.sovereign(gamma_max=...)`) is enforced, and a reply still above it is withheld, but what is enforced is
  the proxy, not persuasion.
- **The measurement is not tradition-neutral.** Lenses can be swapped, but `symbolics/metrics.py` builds an
  Address partly from Sephirot keyword scores, so the Kabbalistic vocabulary sits in the core, not only in one lens.
- **Some things exist twice and can drift.** The ledger framework is in `symbolics/` and in `corpus/ledgers/`, and
  `symbolic_api.json` in `architecture/` and `corpus/data/` (the two differ).
- **Interpreting a person's state is the core's purpose and its least checkable use.** The gate makes a reading
  arrive with its caveat, its source and its uncertainty; it cannot make the reading right.

The project prefers a named gap to a claim of completeness.

## Read next

| Read | For |
|---|---|
| [ELI5.md](ELI5.md) | the whole repository in plain words |
| [SIMPLE_API.md](SIMPLE_API.md) | `read()`, what it refuses, and why it is shaped this way |
| [ASSEMBLY_GUIDE.md](ASSEMBLY_GUIDE.md) | plugging in your own parsers, rules, stores and model sandboxes |
| [STANDARD.md](STANDARD.md) | what counts as VERIFIED, and the break-it rule |
| [ETHICS.md](ETHICS.md) | what the engine refuses, and where each refusal lives in code |
| [LIBER_0.md](LIBER_0.md) | the append-only record: what was tried, what failed, what guards it now |
| [OBSERVATIONS.md](OBSERVATIONS.md) | dated field notes, including where the project's own gates failed |
| [CONTRIBUTING.md](CONTRIBUTING.md) and [AGENTS.md](AGENTS.md) | the rules for changing anything |

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) before changing core behaviour. In short:

- Run `python -m symbolics.conformance` after any edit in `symbolics/`, and the full test suite before pushing.
- A module is VERIFIED only with an independent ground truth, edge cases, and the mutation gate
  (`python -B -m symbolics.mutate --module <file>`) showing no unexplained survivors.
- Some sentences in this README are quoted word for word in `architecture/intent.json`. To change one, change both
  in the same commit; `python -m symbolics.layers` fails otherwise.
- A file you add, move or rename that a layer depends on goes into `architecture/layers.json` in the same change.
- A mistake is recorded as a new entry in `LIBER_0.md`, naming the test that now guards against it.

## License

RCA Sephirotic Sovereignty License 1.1 (see [LICENSE.md](LICENSE.md)). Source-available for non-commercial use;
not an OSI-approved open-source licence. Under Article 0.7 of the License, `symbolics/conformance.py` (run via
`python -m symbolics.conformance`) is the official Conformance Suite, checking Articles 5.1(D), 6, 8 and 9.

## Citation

```text
Recursive Symbolics Contributors. Recursive Symbolics, version 0.3.0.
https://github.com/OmnisMutus/recursive-symbolics-public
```
