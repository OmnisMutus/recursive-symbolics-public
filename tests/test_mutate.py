"""Dedicated tests for symbolics/mutate.py (isolated-copy AST mutation gate + SHA-256 receipts).

Ground truth:
1. Synthetic toy module with exact boundary test (must kill boundary mutant and return exit 0).
2. Synthetic toy module with missing boundary test (must report surviving mutant and return exit 1).
3. Baseline failure rejection (BaselineFailure when unmutated tests fail).
4. Read-only original file never modified during mutation execution, plus comment/string immunity.
"""

import hashlib
import stat
import tempfile
import unittest
from pathlib import Path

from symbolics import mutate


class TestMutationGate(unittest.TestCase):
    def test_kills_mutant_on_read_only_original_without_modifying_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mod_path = root / "toy_mod.py"
            test_path = root / "test_toy_mod.py"
            orig_bytes = (
                b"# comment >= 18 should not be mutated\n"
                b"def is_adult(age: int) -> bool:\n"
                b'    """docstring age >= 18"""\n'
                b"    return age >= 18\n"
            )
            mod_path.write_bytes(orig_bytes)
            mod_path.chmod(stat.S_IREAD)
            try:
                test_path.write_text(
                    "import unittest\n"
                    "import toy_mod\n"
                    "class T(unittest.TestCase):\n"
                    "    def test_boundary(self):\n"
                    "        self.assertTrue(toy_mod.is_adult(18))\n"
                    "        self.assertFalse(toy_mod.is_adult(17))\n",
                    encoding="utf-8",
                    newline="\n",
                )
                res = mutate.mutate_module("toy_mod.py", "test_toy_mod", root=root)
                self.assertEqual(res["total"], 1)
                self.assertEqual(res["killed"], 1)
                self.assertEqual(res["survivors"], [])
                self.assertEqual(res["errors"], [])
                self.assertEqual(res["module_sha256"], hashlib.sha256(orig_bytes).hexdigest())
                self.assertEqual(mod_path.read_bytes(), orig_bytes)
            finally:
                mod_path.chmod(stat.S_IWRITE | stat.S_IREAD)

    def test_reports_surviving_mutant_when_boundary_test_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mod_path = root / "weak_mod.py"
            test_path = root / "test_weak_mod.py"
            mod_path.write_bytes(b"def is_adult(age: int) -> bool:\n    return age >= 18\n")
            test_path.write_text(
                "import unittest\n"
                "import weak_mod\n"
                "class T(unittest.TestCase):\n"
                "    def test_middle_only(self):\n"
                "        self.assertTrue(weak_mod.is_adult(25))\n",
                encoding="utf-8",
                newline="\n",
            )
            res = mutate.mutate_module("weak_mod.py", "test_weak_mod", root=root)
            self.assertEqual(res["total"], 1)
            self.assertEqual(res["killed"], 0)
            self.assertEqual(res["survivors"], ["weak_mod.py:2 (GtE->Gt)"])

    def test_baseline_failure_raises_before_mutation_and_preserves_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mod_path = root / "broken_mod.py"
            orig_bytes = b"def is_adult(age: int) -> bool:\n    return age >= 18\n"
            mod_path.write_bytes(orig_bytes)
            (root / "test_broken_mod.py").write_text(
                "import unittest\n"
                "class T(unittest.TestCase):\n"
                "    def test_fail(self):\n"
                "        self.assertEqual(1, 2)\n",
                encoding="utf-8",
                newline="\n",
            )
            with self.assertRaises(mutate.BaselineFailure):
                mutate.mutate_module("broken_mod.py", "test_broken_mod", root=root)
            self.assertEqual(mod_path.read_bytes(), orig_bytes)

    def test_multiple_operators_and_string_comment_immunity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mod_path = root / "multi_mod.py"
            mod_path.write_bytes(
                b"def check(a: int, b: int) -> bool:\n"
                b'    text = "a >= b"\n'
                b"    # a >= b\n"
                b"    if a >= b:\n"
                b"        return a <= b\n"
                b"    return False\n"
            )
            (root / "test_multi_mod.py").write_text(
                "import unittest\n"
                "import multi_mod\n"
                "class T(unittest.TestCase):\n"
                "    def test_check(self):\n"
                "        self.assertTrue(multi_mod.check(5, 5))\n"
                "        self.assertFalse(multi_mod.check(6, 5))\n"
                "        self.assertFalse(multi_mod.check(4, 5))\n",
                encoding="utf-8",
                newline="\n",
            )
            res = mutate.mutate_module("multi_mod.py", "test_multi_mod", root=root)
            self.assertEqual(res["total"], 2)
            self.assertEqual(res["killed"], 2)
            self.assertEqual(res["survivors"], [])

    def test_timeout_is_recorded_and_kills_mutant(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "loop_mod.py").write_bytes(
                b"def step() -> int:\n"
                b"    i = 0\n"
                b"    while i > 0:\n"
                b"        i += 1\n"
                b"    return i\n"
            )
            (root / "test_loop_mod.py").write_text(
                "import unittest\n"
                "import loop_mod\n"
                "class T(unittest.TestCase):\n"
                "    def test_step(self):\n"
                "        self.assertEqual(loop_mod.step(), 0)\n",
                encoding="utf-8",
                newline="\n",
            )
            res = mutate.mutate_module("loop_mod.py", "test_loop_mod", root=root, timeout=1)
            self.assertEqual(res["total"], 1)
            self.assertEqual(res["killed"], 1)
            self.assertEqual(len(res["timeouts"]), 1)

    def test_no_eligible_operators_returns_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "const_mod.py").write_bytes(b"def f():\n    return 42\n")
            (root / "test_const_mod.py").write_text(
                "import unittest\n"
                "import const_mod\n"
                "class T(unittest.TestCase):\n"
                "    def test_f(self):\n"
                "        self.assertEqual(const_mod.f(), 42)\n",
                encoding="utf-8",
                newline="\n",
            )
            res = mutate.mutate_module("const_mod.py", "test_const_mod", root=root)
            self.assertEqual(res["total"], 0)
            self.assertEqual(res["killed"], 0)
            self.assertEqual(res["survivors"], [])


if __name__ == "__main__":
    unittest.main()
