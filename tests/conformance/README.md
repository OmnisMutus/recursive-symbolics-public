# tests/conformance/

Tests for `symbolics/conformance.py`, the Conformance Suite the licence names (Article 0.7). The suite is the
answer about whether the engine complies, so it is tested like any other module: that it passes today, that a
duty with no check behind it stops conformance, that one failure is enough to stop it, and that its checks fail
when their rule is broken on purpose (a network import, also inside a subpackage; an engine that lets a ranking
through; a caveat missing half its text; a gamma cap above the licence's 0.85).

The empty `__init__.py` is required. Without it `unittest discover` does not collect this folder, and these tests
silently never run. That happened once; `LIBER_0.md` records it, and the entry names this file as its guard.

Run only these:

```bash
python -m unittest tests.conformance.test_conformance -v
```
