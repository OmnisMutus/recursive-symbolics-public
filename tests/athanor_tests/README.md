# tests/athanor_tests/

Tests for the [`athanor/`](../../athanor/README.md) package.

| File | What it checks |
|---|---|
| `test_athanor.py` | Reading, the codec, every kind of edit, undo, the journal, crash recovery and the Ollama Modelfile, against a model and decodings produced by the official `gguf` package. Needs NumPy; skipped without it. |
| `test_review_regressions.py` | Fixes found in a later review: malformed GGUF strings that would read past the file or allocate too much, invalid tensor layouts and unknown types refused, symlinked and multiply-linked vessels refused, unique staging paths, and recovery of interrupted writes, undos and journal rewrites. Standard library only |
| `breakit.py` | Not a test file: plants 13 bugs one at a time in a scratch copy of the package and exits 0 only if every one is caught. Run it on its own: `python tests/athanor_tests/breakit.py` |
| `fixtures/` | The reference model and its expected values. See its README. |

The folder is not called `athanor`, because `unittest` puts `tests/` on the import path and a folder of that name
would hide the package being tested.
