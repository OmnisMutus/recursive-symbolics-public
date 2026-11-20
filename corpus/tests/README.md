# corpus/tests/

The correctness suites for the engines in [`../engines/`](../engines/README.md), the protocols in
[`../protocols/`](../protocols/README.md) and the ledgers in [`../ledgers/`](../ledgers/README.md). One file per
module, named `test_<module>.py`; each file's docstring states its independent ground truth.

Run them through the corpus runners, from `corpus/`. The runners put the corpus subfolders on the import path, so
the tests can import their modules by bare name:

```bash
python test_all_engines.py      # the 24 engines, each with its test file
python run_corpus.py            # every test file in the corpus, scored
```

`run_corpus.py` refuses to call a file a pass unless it actually reported a score.

`test_production_engine_unit_tests.py` is a cross-engine suite rather than one engine's tests.
`test_run_all_correspondence_ledgers.py` pins the ledger runner's known baseline, so a change in the number of
VERIFIED, FAILED or UNTESTABLE claims shows up as a failure.
