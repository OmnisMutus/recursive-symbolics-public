# tests/

The test suite for the core, the engines and the examples. Run it from the repository root:

```bash
python -m unittest discover -s tests -v
```

The core needs only the standard library. Three modules, `test_recursive_attractor_engine.py`,
`test_engine_composition_loop.py` and `athanor_tests/test_athanor.py`, test code that needs NumPy; without it they
are reported as skipped, never as passed. Install it to run them: `pip install "numpy>=1.24"`. CI does.

## What a test here has to do

`STANDARD.md` sets the bar. A test file does not only check that code runs. It compares the output against an
**independent ground truth** (a real library, a published vector, values worked by hand, or a separate
algorithm), covers boundary and edge cases, and the module must survive the mutation gate
(`python -B -m symbolics.mutate`), which breaks the code on purpose and checks that some test notices. Each file's
docstring says what its ground truth is.

## The files

| File | Tests |
|---|---|
| `test_address_and_ethics.py` | The address space, lenses and the ethics gate, as a decision table. `TestRecordedBypasses` pins every bypass recorded in `OBSERVATIONS.md`, plus known false positives. |
| `test_agency.py` | The agency budget and its 0.85 cap. |
| `test_metrics.py` | The measurement layer. |
| `test_interfaces_and_examples.py` | The abstract interfaces, and both example reducers. |
| `test_family_f.py` | The D_22 permutation solver and its verification gate. |
| `test_ledger.py` | The correspondence ledger. |
| `test_record_and_staleness.py` | `record.py`, `ledger_history.py` and `ledger_staleness.py`, against real git repositories built in a temporary folder. |
| `test_breaches.py` | `breaches.py`, on toy records where the right answer is known by construction, plus one test on the real `LIBER_0.md`. |
| `test_layers.py` | The architecture index and intent checker. |
| `test_outgoing.py` | The home-folder path scanner, including a path added and then removed in history. |
| `test_mutate.py` | The mutation gate itself. |
| `test_sanitization_audit.py` | That the repository holds no home-folder paths, no private identifiers (see below), and no broken imports. |
| `athanor_tests/` | The `athanor/` package, plus its planted-bug check `breakit.py`. See its README. |
| `reference_agent_tests/` | The `reference_agent/` package. See its README. |
| `test_sovereign_wrapper.py`, `test_safe_memory_boundary_engine.py`, `test_recursive_attractor_engine.py`, `test_standalone_rca_sandbox.py`, `test_engine_composition_loop.py` | The engines in `engines/`. |
| `conformance/` | The Conformance Suite, tested itself. See its README. |
| `fixtures/` | Reference data the tests compare against. See its README. |

## The private-identifier check

`test_sanitization_audit.py` can check the repository against a list of names that must never be published. That
list is kept in a local, git-ignored file (`.sanitize-denylist`), because publishing it would publish the names.
On a clone without that file the check is reported as **skipped**, never as passed.
