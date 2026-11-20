# tests/fixtures/

Reference data that tests compare against. These are the independent ground truth: none of them was produced by
the module it checks.

| File | Used by | What it is |
|---|---|---|
| `gamma_vectors.json` | `tests/test_agency.py` | (text, gamma) pairs captured by running the framework's own reference implementation of the gamma cap, not `symbolics/agency.py`. The module must agree with every one exactly. |
| `sephirot_scores.json` | `tests/test_metrics.py` | Centroid scores recorded by running the framework's reference scoring over a set of texts. |
| `agency_budget.py` | `tests/test_sovereign_wrapper.py` | The framework's reference `compute_gamma()`, read by the wrapper's tests as a second, separate calculation. |

Do not regenerate these from the code they check: a fixture produced by the code under test can only ever agree
with it.
