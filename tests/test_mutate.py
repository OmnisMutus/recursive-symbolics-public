"""Dedicated tests for symbolics/mutate.py (isolated-copy AST mutation gate + SHA-256 receipts).

Ground truth:
1. Synthetic toy module with exact boundary test (must kill boundary mutant and return exit 0).
2. Synthetic toy module with missing boundary test (must report surviving mutant and return exit 1).
3. Baseline failure rejection (BaselineFailure when unmutated tests fail).
4. Read-only original file never modified during mutation execution, plus comment/string immunity.
"""

import ast
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

    def test_a_mutant_only_a_second_test_module_catches_is_killed_when_both_are_named(self):
        # Added 2026-11-20, when a target could first name several test modules. Ground truth by construction:
        # test_a never exercises the boundary, test_b does, so the one mutant survives test_a alone and dies
        # when test_b runs too.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "two_mod.py").write_bytes(b"def is_adult(age: int) -> bool:\n    return age >= 18\n")
            (root / "test_a.py").write_text(
                "import unittest\nimport two_mod\nclass T(unittest.TestCase):\n"
                "    def test_far(self):\n        self.assertTrue(two_mod.is_adult(40))\n",
                encoding="utf-8", newline="\n")
            (root / "test_b.py").write_text(
                "import unittest\nimport two_mod\nclass T(unittest.TestCase):\n"
                "    def test_edge(self):\n        self.assertTrue(two_mod.is_adult(18))\n",
                encoding="utf-8", newline="\n")
            alone = mutate.mutate_module("two_mod.py", "test_a", root=root)
            both = mutate.mutate_module("two_mod.py", ("test_a", "test_b"), root=root)
            self.assertEqual(alone["survivors"], ["two_mod.py:2 (GtE->Gt)"])
            self.assertEqual((both["killed"], both["total"], both["survivors"]), (1, 1, []))
            self.assertEqual(both["test_module"], "test_a test_b")
            self.assertNotEqual(alone["test_sha256"], both["test_sha256"])

    def _toy(self, root, src, test_body):
        (root / "toy2.py").write_bytes(src.encode())
        (root / "test_toy2.py").write_text(
            "import unittest\nimport toy2\nclass T(unittest.TestCase):\n    def test_it(self):\n" + test_body,
            encoding="utf-8", newline="\n")

    def test_arithmetic_and_boolean_mutants_are_really_applied(self):
        # Added 2026-11-20 (mutate.py:193, :195 survived): a mutant whose kind is never applied leaves the
        # source unchanged, so it would be reported as a survivor. Each toy here has exactly one site, and the
        # test kills it only if the swap really happened. Ground truth: 2 + 3 is 5; True and False is False.
        for src, body, label in (
                ("def f(a, b):\n    return a + b\n", "        self.assertEqual(toy2.f(2, 3), 5)\n", "Add->Sub"),
                ("def f(a, b):\n    return a and b\n", "        self.assertFalse(toy2.f(True, False))\n", "And->Or")):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self._toy(root, src, body)
                res = mutate.mutate_module("toy2.py", "test_toy2", root=root)
                self.assertEqual((res["killed"], res["total"], res["survivors"]), (1, 1, []), label)

    def test_every_operator_in_a_chained_comparison_is_mutated(self):
        # Added 2026-11-22: chains such as 0 < x <= 1 were skipped, so bounds written that way went untested.
        tree = ast.parse("def ok(x):\n    return 0 < x <= 1\n")
        self.assertEqual([d for _, d, _, _ in mutate.collect_mutants(tree)], ["Lt->LtE", "LtE->Lt"])
        # Ground truth by hand: ok(0) is False and ok(1) is True. Testing both ends kills both mutants;
        # testing only the middle (0.5) kills neither.
        for body, killed in (("        self.assertFalse(toy2.ok(0))\n        self.assertTrue(toy2.ok(1))\n", 2),
                             ("        self.assertTrue(toy2.ok(0.5))\n", 0)):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self._toy(root, "def ok(x):\n    return 0 < x <= 1\n", body)
                res = mutate.mutate_module("toy2.py", "test_toy2", root=root)
                self.assertEqual((res["killed"], res["total"]), (killed, 2), body)

    def test_the_same_swap_twice_on_one_line_gets_two_labels(self):
        # Added 2026-11-22 (outside review): two `+` on one line shared one label, so an exemption was ambiguous.
        tree = ast.parse("def f(a, b, c):\n    return a + b + c\n")
        self.assertEqual([d for _, d, _, _ in mutate.collect_mutants(tree)], ["Add->Sub", "Add->Sub #2"])
        tree = ast.parse("def ok(x):\n    return 0 <= x <= 1\n")
        self.assertEqual([d for _, d, _, _ in mutate.collect_mutants(tree)], ["LtE->Lt", "LtE->Lt #2"])

    def test_no_bytecode_is_written_even_by_a_child_process(self):
        # Added 2026-11-22 (outside review): a child `python` without -B wrote .pyc files into the sandbox, and a
        # later mutant of the same size could load the earlier one's code. The tests run with
        # PYTHONDONTWRITEBYTECODE=1, which a child inherits; this toy's baseline fails if it is missing.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._toy(root, "def f(a):\n    return a == 1\n",
                      "        import os\n        self.assertEqual(os.environ.get('PYTHONDONTWRITEBYTECODE'), '1')\n"
                      "        self.assertTrue(toy2.f(1))\n")
            res = mutate.mutate_module("toy2.py", "test_toy2", root=root)
            self.assertEqual((res["killed"], res["total"]), (1, 1))

    def test_limit_caps_the_mutants_at_exactly_that_number(self):
        # The cap at the end of collect_mutants. Three comparison sites; limit=2 must give 2, not 3.
        tree = ast.parse("def f(a):\n    return a < 1 or a > 9 or a == 5\n")
        self.assertEqual(len(mutate.collect_mutants(tree)), 4)           # one BoolOp and three comparisons
        self.assertEqual(len(mutate.collect_mutants(tree, limit=2)), 2)
        self.assertEqual(len(mutate.collect_mutants(tree, limit=1)), 1)

    def test_main_exits_1_when_a_mutant_survives_and_0_when_all_die(self):
        # mutate.py:304: CI relies on the exit code. A survivor alone (no errors) must still fail the run.
        import contextlib
        import io
        from unittest import mock
        for body, want in (("        self.assertTrue(toy2.f(25))\n", 1),
                           ("        self.assertTrue(toy2.f(18))\n        self.assertFalse(toy2.f(17))\n", 0)):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self._toy(root, "def f(age):\n    return age >= 18\n", body)
                with mock.patch.object(mutate, "REPO_ROOT", root), \
                        mock.patch.object(mutate, "TARGETS", {"toy2.py": "test_toy2"}), \
                        contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(mutate.main(["--module", "toy2.py"]), want, body)

    def test_test_modules_must_be_named(self):
        for bad in ((), [], ("",), ("ok", ""), None, 3):
            with self.assertRaises((ValueError, TypeError)):
                mutate._test_modules(bad)

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
