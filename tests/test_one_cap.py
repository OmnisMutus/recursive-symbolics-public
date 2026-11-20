"""One directive-strength cap in the repository, defined in one place.

Licence Article 6 caps directive strength at 0.85. `symbolics/agency.py` defines it as GAMMA_MAX. Until 2026-11-20,
`reference_agent/governance.py` kept its own copy (GAMMA_CAP = 0.85), so changing one would have left the other
behind with no test noticing: an outside review found the drift path, and this closes it.

Ground truth, in the order STANDARD.md asks for it:

1. INDEPENDENT REFERENCE. The licence's number, 0.85, written here from Article 6 and not read from the code.
2. A SECOND CHECK OF THE SCANNER. Before it is trusted to report no copies, the scanner is shown to find one
   planted in a sample, in each form a copy could take.
3. BY READING. Every module that uses a cap is checked to hold the very object agency.py defines.

What it does not cover: `corpus/`, the practice corpus, keeps its own historical constants on purpose and is not
part of the running system. `symbolics/conformance.py` writes 0.85 in a comparison, which is the licence's value
used as the check's own reference, not a definition.
"""
import ast
import os
import unittest

from symbolics import agency

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGES = ("symbolics", "engines", "reference_agent", "athanor", "examples")
HOME = "symbolics/agency.py"
ARTICLE_6 = 0.85


def copies(source, filename="<sample>"):
    """Lines that bind a name to the literal 0.85: `X = 0.85`, `X: float = 0.85`, or a default `def f(cap=0.85)`."""
    found = []
    for node in ast.walk(ast.parse(source, filename=filename)):
        values = []
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
            values = [node.value]
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            values = list(node.args.defaults) + [d for d in node.args.kw_defaults if d is not None]
        for v in values:
            if isinstance(v, ast.Constant) and type(v.value) is float and v.value == ARTICLE_6:
                found.append(getattr(v, "lineno", 0))
    return found


def modules():
    for pkg in PACKAGES:
        for here, dirs, files in os.walk(os.path.join(ROOT, pkg)):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for name in files:
                if name.endswith(".py"):
                    path = os.path.join(here, name)
                    yield os.path.relpath(path, ROOT).replace("\\", "/"), path


class TestOneCap(unittest.TestCase):
    def test_the_cap_is_the_licences_number(self):
        self.assertEqual(agency.GAMMA_MAX, ARTICLE_6)

    def test_the_scanner_finds_each_form_of_copy(self):
        for sample in ("CAP = 0.85\n", "CAP: float = 0.85\n", "def f(cap=0.85):\n    pass\n",
                       "def f(*, cap=0.85):\n    pass\n", "f = lambda cap=0.85: cap\n"):
            self.assertEqual(copies(sample), [1], sample)
        for sample in ("CAP = agency.GAMMA_MAX\n", "if x <= 0.85:\n    pass\n", "CAP = 0.850001\n", "N = 85\n"):
            self.assertEqual(copies(sample), [], sample)

    def test_only_agency_defines_it(self):
        found = {}
        for rel, path in modules():
            with open(path, encoding="utf-8") as fh:
                lines = copies(fh.read(), rel)
            if lines:
                found[rel] = lines
        self.assertEqual(found, {HOME: found.get(HOME, [])}, f"0.85 is defined outside {HOME}: {found}")
        self.assertTrue(found.get(HOME), f"{HOME} no longer defines the cap")

    def test_the_modules_that_use_a_cap_hold_agencys_own(self):
        from engines import sovereign_wrapper
        from reference_agent import governance
        self.assertIs(governance.GAMMA_CAP, agency.GAMMA_MAX)
        self.assertIs(governance.gamma.__defaults__[0], agency.GAMMA_MAX)
        self.assertIs(sovereign_wrapper.MAX_GAMMA, agency.GAMMA_MAX)


if __name__ == "__main__":
    unittest.main()
