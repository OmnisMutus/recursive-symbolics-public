# The corpus

A software engineering practice suite (24 independently verified engines
spanning OOP, ML, distributed networking, graphics, and reinforcement
learning) with a second, later layer built on top of it: a set of
Kabbalistic/dynamical-systems correspondences, held to the same
adversarial testing discipline as the code itself, and a working journal
recording how both layers were actually built.

**Start here if you're new**: 
→ [`studies/master_study_and_onboarding_manual.md`](studies/master_study_and_onboarding_manual.md)
→ [`studies/EXERCISES.md`](studies/EXERCISES.md).

**In plain language**: [`docs/eli5_architecture_guide.md`](docs/eli5_architecture_guide.md),
a short, jargon-free explanation of both layers and of the meta-tooling that checks them, with a diagram.

---

## What's Actually Verified Right Now

Don't trust a number in this file. Run it yourself, from this folder:

```powershell
python test_all_engines.py                  # the 24 engines
python run_all_correspondence_ledgers.py    # the meta layer: every correspondence claim
python run_corpus.py                        # every test file in the corpus, scored honestly
```

"VERIFIED" has a specific meaning here, not a vibe. See
[`TESTING_STANDARD.md`](../STANDARD.md): a dedicated test file, real
assertions checked against independent ground truth (a real library, a
published test vector, or a hand-derived reference), boundary cases, and a
confirmed adversarial "break it on purpose" proof that was actually run
and reverted, not merely asserted.

The engines need NumPy. One of them is checked against a real scikit-learn, and reports FAILED on a machine
where scikit-learn is not installed: that is the environment, and the failure message names the missing library.

## Three Layers, Two Different Kinds of Claim

**The engineering layer** is 24 tested engines in [`engines/`](engines/): OOP dispatch, KNN/Ridge/
LDA/K-means, a Kademlia DHT node, a DDPG quadcopter controller, an OpenGL
renderer, and more. Every claim here is falsifiable by running code.
[`PHILOSOPHICAL_AND_ENGINEERING_BOUNDARIES.md`](docs/PHILOSOPHICAL_AND_ENGINEERING_BOUNDARIES.md)
states the rules for keeping engineering claims and framing claims from bleeding
into each other.

**The philosophical layer** (`engines/recursive_attractor_engine.py`, the Kabbalistic hand-verification
series in `docs/`) takes the project's own Recursive Symbolics framework (Sephirotic correspondences,
fixed-point/attractor formalism) and holds it to the same standard where
that's possible, while stating explicitly where it isn't. The governing
rule, from `docs/fixed_point_closure_and_the_y_combinator.md` §1: never
collapse (A) traditional/textual claims about Kabbalah, (B) formal claims
checkable within this codebase's own math, and (C) metaphysical claims
about consciousness itself. Everything testable in this repo lives in (B).

**The meta layer** sits over both and is what keeps them honest:
[`ledgers/correspondence_ledger.py`](ledgers/correspondence_ledger.py) and its five worked examples
(Sephirotic reward engine, attractor engine, RCA sandbox gamma cap, DDPG quadcopter, 100-emotion codex).
It takes a claim from either layer and sorts it into VERIFIED (a real test backs it), FAILED (a real test
contradicts it), or UNTESTABLE (nobody can check this, and that is stated instead of hidden). Claims in
register (C) are marked `UNTESTABLE` rather than quietly assumed, and a ledger in which every entry is
UNTESTABLE refuses to report success. See
[`docs/correspondence_ledger_meta_tool_spec.md`](docs/correspondence_ledger_meta_tool_spec.md). The engine in
this repository's `symbolics/` inherits that rule in `symbolics/ledger.py`.

Study Module 6 (`studies/EXERCISES.md`) is built specifically to teach
this distinction hands-on, including a sandbox practicum against
`standalone_rca_sandbox.py`'s real slash commands.

## Map

| Where | What |
|---|---|
| `engines/` | The 24 engines, their studies and recorded results |
| `tests/` | Their `test_*.py` correctness suites |
| `test_all_engines.py` | The master test runner: the only source of truth for the live VERIFIED count |
| `ledgers/` | The meta layer: `correspondence_ledger.py`, 5 worked examples, run history and staleness checks |
| `run_all_correspondence_ledgers.py` | Master runner aggregating all 5 ledgers in one command: the meta-layer equivalent of `test_all_engines.py` |
| `run_corpus.py` | Runs every test file here and refuses to call an unscored file a pass |
| `protocols/`, `tools/`, `arch/` | The framework's protocols, its symbolic tooling, and the architecture tools |
| `data/` | `symbolic_api.json` and the tradition tables the tools read |
| `docs/` | Technical specs, architecture docs, and the Kabbalistic hand-verification series: see `docs/README_DOCS.md` for the full index |
| `studies/` | The learning path: onboarding manual, exercise workbook, this corpus's own curriculum |
| `FUTURE_WORK.md` | Ideas written down on purpose and not built yet. An entry leaves here once real work starts on it |
| [`../STANDARD.md`](../STANDARD.md) | What VERIFIED / RAN_ONLY / FAILED / MISSING actually mean |
| [`docs/PHILOSOPHICAL_AND_ENGINEERING_BOUNDARIES.md`](docs/PHILOSOPHICAL_AND_ENGINEERING_BOUNDARIES.md) | The three registers (A, B, C) and why they are never collapsed |
| [`../OBSERVATIONS.md`](../OBSERVATIONS.md) | This repository's dated field notes, corrections added and never erased |
| [`../LICENSE.md`](../LICENSE.md) | RCA Sephirotic Sovereignty License 1.1. It covers the whole repository, this corpus included |

## A Note on This Corpus's Own History

This project has, more than once, caught and corrected its own fabricated
or stale claims: a misattributed CVE, benchmark scripts with fake
timing, a technical spec with five verification claims that didn't survive
a `grep`, engine counts that drifted stale across a dozen docs. None of
that is hidden. That's deliberate: the discipline this repo is built
around only means something if it's applied to itself, not just to the
code.

## What the original mentions that is not carried here

Stated so that a dangling reference reads as a known gap and not as a broken promise:

- **`solo/`.** Many docs and docstrings name a `solo/` folder. That was this folder's name in the original
  working tree; read it as `corpus/`. The text is left as written, because it records how the work was done.
- **The original working journal.** Many docstrings and docs here say "dated, see LIBER_0.md". They mean the
  journal of the original working tree, which recorded those corrections as they happened. It is not in this
  repository. [`../OBSERVATIONS.md`](../OBSERVATIONS.md) is this repository's own record, kept under the same
  rule.
- `SEPHIROTIC_MAPPING_ANALYSIS.md`, named in these docs. It was not found in the original folders either
  (searched 2026-11-11).
- `ANTI_ECHO_ISOLATION_POLICY.md`, `GEMINI.md`, `GEMINI_EXPERIMENT_LOG.md`, `EPISTEMOLOGICAL_BOUNDARIES.md`,
  `core-axiom.md` and the C source `alx_c_functions_nested_loops.c`, each named
  somewhere in these docs. They are kept in the maintainer's working repository and are not published here.
- **Generated files.** `engines/rca_memory.json` and `tools/community_dataset.jsonl` are written when the
  sandbox and the feedback ingester run, so they are not committed; a link to one may point at nothing until
  you run the tool that writes it.
- **Network access.** The rule that nothing reaches the network (licence Article 9, checked by
  `python -m symbolics.conformance`) covers the core `symbolics/` package only. Here:
  - `tools/scan_anomaly.py` fetches a web page from the URL you give it. It is the only file that contacts
    another machine.
  - `tools/rca_llm_sandbox.py` calls a local Ollama server at `localhost:11434`.
  - The DHT, gRPC-web, NestJS and P2P engines, and `tools/telemetry_service.py`, open sockets on `127.0.0.1`
    to talk to themselves in their demos and tests.
  - `engines/standalone_rca_sandbox.py` imports `urllib` but does not use it.
