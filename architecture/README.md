# architecture/

This folder describes the project in machine-readable form, so that what the project says about itself can be
checked against what is on disk. Four of the five files are read by code, and a check fails when one of them
stops matching the repository. The fifth is reference data.

| File | What it is | Read by | Checked how |
|---|---|---|---|
| [`layers.json`](layers.json) | Each architecture layer mapped to the files that implement it and the tests behind them | `symbolics/layers.py` | Every named file and test must exist |
| [`intent.json`](intent.json) | The project's purpose and principles, each quoted word for word from a source document | `symbolics/layers.py` | Every quotation must still appear in its source |
| [`guards.json`](guards.json) | Guards for LIBER_0.md breaches, and in-place edits the Maintainer accepted | `symbolics/breaches.py`, `symbolics/record.py` | Every guard must exist; every edit to the record must be named |
| [`mutation_guards.json`](mutation_guards.json) | Mutants exempted from the mutation gate as equivalent, each with its reason | `symbolics/mutate.py` | Used during mutation runs |
| [`symbolic_api.json`](symbolic_api.json) | The symbolic vocabulary: Sephirot, the 22 paths, and their correspondences | Nothing in the core | Not checked: reference data |

Check the first two at any time:

```bash
python -m symbolics.layers
```

It ends with `INDEX OK: True    INTENT OK: True` when everything matches, and exits with an error otherwise. CI
runs it on every push and pull request to `main`.

---

## layers.json: where each layer lives

The architecture is described as layers of the Tree of Life, each with a plain role. The names are a map for
people, not a claim about how the code works:

| Layer | Role | Main files |
|---|---|---|
| Kether | Intent | `intent.json`, `AGENTS.md`, `docs/ETHICS.md` |
| Chokmah / Binah | Design | `symbolic_api.json`, `symbolics/interfaces.py`, `STANDARD.md`, `docs/ASSEMBLY_GUIDE.md` |
| Chesed | Expansion | `examples/algebra_simplifier.py`, `examples/propositional_reducer.py`, `symbolics/family_f.py` |
| Geburah | Boundary | `symbolics/ethics.py`, `symbolics/conformance.py`, `reference_agent/outbound.py`, `symbolics/outgoing.py`, `engines/safe_memory_boundary_engine.py` |
| Tiphareth | Integration | `symbolics/ledger.py`, `examples/quickstart.py` |
| Da'ath | Cavity (unknowns) | `symbolics/ledger.py`, `engines/recursive_attractor_engine.py` |
| Yesod | Foundation | `symbolics/address.py`, `symbolics/metrics.py`, `symbolics/agency.py`, `athanor/workshop.py`, `mcp-workspace/apis/workspace.go` |
| Malkuth | Mirror | `symbolics/layers.py`, `tests/test_sanitization_audit.py`, `LIBER_0.md`, `symbolics/record.py`, `symbolics/breaches.py`, `guards.json` |

Each component names a `path`, and may name an `evidence` file (the test that stands behind it). The checker
gives each component one status:

- **PRESENT**: the file is there, and so is its evidence file if it names one.
- **MISSING**: the index names a file that is not there. This is the failure.
- **NOT_HERE**: the component belongs to another repository that is not on this machine, so nothing was checked.

And each layer one status:

- **COVERED**: at least one component found, none missing.
- **BROKEN**: at least one component missing. The check fails.
- **GAP**: the layer lists no components. A declared gap is honest and is not a failure.
- **UNCHECKED**: every component is NOT_HERE.

A run in which nothing could be checked does not pass. Known shortfalls go in a layer's `gaps` list, so they are
printed with the report instead of being left out.

**Note:** a component without an `evidence` field is only checked for existence. It is listed, not verified.

**When you add, move or rename a file** that a layer depends on, update its entry here in the same change, or
`python -m symbolics.layers` fails.

---

## intent.json: what the project is for, pinned to its own words

Every statement in `intent.json` has a `text` and a `source`. The checker opens the source and looks for the text,
word for word (only differences in line wrapping are ignored). If the sentence has been reworded or removed in
the source, the check reports it as **DRIFTED** and fails.

This stops the stated intent and the documents from silently drifting apart. It also means some sentences in
`README.md` and `AGENTS.md` must not be reworded on their own, for example:

- "No output may rank a person, and none may command: it offers."
- "This engine reads the person asking, and no one else."

To change one, change the document and `intent.json` together, in the same commit.

**Status.** The intent is a **DRAFT** until the Maintainer ratifies it by setting all three of `ratified: true`,
`ratified_by` and `ratified_on`. With any of them missing, the checker reports DRAFT, never RATIFIED. Only the
Maintainer ratifies; a contributor or an agent does not.

---

## mutation_guards.json: equivalent mutants

`python -m symbolics.mutate` changes comparisons, booleans and arithmetic in a module and checks that some test
fails for each change. A change that no test catches is reported as a survivor.

Some changes cannot be caught by any test because they do not change behaviour (an *equivalent mutant*). Those,
and only those, may be listed here, using the label the mutation run prints:

```json
{
  "equivalent_mutants": [
    "symbolics/example.py:42 (Lt->LtE)"
  ]
}
```

An exempted mutant is reported as exempted, not as killed. Each entry has its reason beside it under `why`, because
each entry is a place where the tests are allowed to be blind, and a reader should be able to disagree with the
reason. A label includes a line number, so when the code moves the label stops matching and the mutant shows up as
a survivor again: the safe direction. Eight are listed today, all added 2026-11-20.

A target in `symbolics/mutate.py` may name several test modules (a tuple). A file tested from more than one place
is mutated against all of them, so a mutant counts as surviving only if no test anywhere catches it.

---

## symbolic_api.json: the vocabulary

The keyword, function and correspondence tables for the ten Sephirot, Da'ath, and paths 11 to 32 (letter, astrology,
tarot, alchemy, a programming pattern, and a cognitive reading). Its own `meta` block says what it is: a
convention-based mapping, offered as one lens among others, and meant to be rewritten to fit your tradition.

Nothing in the core imports it. Its correspondences are not verified claims; the ones that are tested live in the
practice corpus (`corpus/ledgers/`), sorted into VERIFIED, FAILED or UNTESTABLE.

---

## guards.json: what stands beside the record

[`LIBER_0.md`](../LIBER_0.md) is the project's append-only working record. Its entries are never edited, so
anything that has to be said about an old entry is said here, beside it. Two modules read this file:

- **`python -m symbolics.breaches`** checks that every entry whose Result says FAILED or CORRECTED names a guard:
  a test (`path/to/test_file.py::test_name`) or a whole file that exists, or a reason no test can guard it. New
  entries carry their own `**Guard:**` line. An entry written without one gets it here under `guards`, keyed by
  its heading exactly as written. A guard recorded for a heading that is not in LIBER_0.md is reported as BROKEN.
- **`python -m symbolics.record`** reads LIBER_0.md's git history and fails on any commit that changed or deleted
  a line, unless that commit is named under `record_edits.accepted`. That list is for the Maintainer only, and
  only for removing what must not be kept (a key, a private path).

Both lists start empty. "Guarded" means the named test exists, not that it passes; the test suite answers that.
