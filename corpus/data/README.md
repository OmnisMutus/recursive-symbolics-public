# corpus/data/

The symbolic tables the corpus reads. Plain JSON, no code.

| File | What it holds |
|---|---|
| `symbolic_api.json` | The operator vocabulary: the Sephirot, Da'ath and paths 11 to 32, with their keywords and correspondences. `../../architecture/symbolic_api.json` is a different version of it; the two files are not identical. |
| `hermetic_qabalah.json` | The Hebrew letters with their names, path numbers and cipher values. |
| `tradition_mappings.json` | The same recursive structure read through other traditions (Kabbalah, Kashmir Shaivism, semiotics, cybernetics, dynamical systems, and others), each with its operators and core concept. |

These are correspondences by convention, offered as lenses, not verified facts. A correspondence that is tested
is sorted into VERIFIED, FAILED or UNTESTABLE by a ledger in [`../ledgers/`](../ledgers/README.md).

`../tools/` keeps its own copies. `tradition_mappings.json` differs between the two folders.
