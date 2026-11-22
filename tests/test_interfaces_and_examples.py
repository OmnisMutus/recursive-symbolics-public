"""STANDARD.md verification suite for symbolics/interfaces.py and examples/.

Ground truth:
1. AlgebraSimplifier: direct numeric evaluation of initial AST vs reduced AST across varied integer
   assignments (x, y, z in negatives, zero, positives), independent of rewrite rules.
2. PropositionalReducer: exhaustive 2^n truth-table equivalence comparing initial formula AST vs
   reduced AST across every boolean variable assignment.
3. RuleEngine contracts: boundary depth checks (max_depth=0, max_depth=exact, max_depth=exact-1),
   bool type confusion on max_depth, CycleDetectedError on toggling rules, and MemoryStore hash-chain
   tamper verification.
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest

from examples.algebra_simplifier import AlgebraBackend, AlgebraSimplifier, Const, Var
from examples.propositional_reducer import LogicBackend, PropositionalReducer
from symbolics.interfaces import (
    CycleDetectedError,
    InMemoryLedgerStore,
    MemoryStore,
    RecursionLimitError,
    RuleEngine,
    SymbolicBackend,
)
from symbolics.ethics import EthicsError


class _ToggleBackend:
    """Minimal backend for testing CycleDetectedError."""

    def parse(self, text: str):
        return text

    def format(self, node) -> str:
        return str(node)

    def complexity(self, node) -> int:
        return 1

    def evaluate(self, node, env):
        return node


class _OscillatingEngine(RuleEngine):
    def rewrite_once(self, node):
        if node == "A":
            return "B", "flip_to_B"
        if node == "B":
            return "A", "flip_to_A"
        return node, None


class _CountingEngine(RuleEngine):
    """Counts 0 -> 1 -> 2 -> ... indefinitely unless max_depth stops it."""

    def rewrite_once(self, node: int):
        return node + 1, "increment"


class TestProtocolsAndStore(unittest.TestCase):
    def test_runtime_protocols_and_ledger_tamper_detection(self):
        store = InMemoryLedgerStore()
        self.assertIsInstance(store, MemoryStore)
        self.assertIsInstance(AlgebraBackend(), SymbolicBackend)
        self.assertIsInstance(LogicBackend(), SymbolicBackend)

        h1 = store.put("k1", {"v": 1}, reason="init")
        h2 = store.put("k2", {"v": 2}, reason="step")
        self.assertNotEqual(h1, h2)
        self.assertEqual(store.get("k1"), {"v": 1})
        self.assertEqual(store.get("missing", "fallback"), "fallback")
        self.assertTrue(store.verify_integrity())

        # Tamper directly with an internal chain row -> must fail integrity verification
        store._chain[0]["value"] = {"v": 999}
        self.assertFalse(store.verify_integrity())

        # Tampering only index (without touching prev_hash) must also fail
        store_idx = InMemoryLedgerStore()
        store_idx.put("k1", {"v": 1}, reason="init")
        store_idx._chain[0]["index"] = 999
        self.assertFalse(store_idx.verify_integrity())

        # Tampering only prev_hash (without touching index) must also fail
        store_prev = InMemoryLedgerStore()
        store_prev.put("k1", {"v": 1}, reason="init")
        store_prev._chain[0]["prev_hash"] = "1" * 64
        self.assertFalse(store_prev.verify_integrity())


class TestTheConstitutionalCheck(unittest.TestCase):
    """2026-11-22: the dead directive-strength guard was removed, not made reachable. These pin both halves."""

    def engine(self):
        return _OscillatingEngine(_ToggleBackend(), enforce_constitutional=True)

    def test_repetitive_expressions_are_not_commands(self):
        # each scores 0.85 by directive strength, only because its tokens repeat
        for expr in ("x * x * x", "a & a & a", "(p | ~p)"):
            self.engine()._validate_request(expr)

    def test_a_request_about_another_person_is_still_refused(self):
        with self.assertRaises(EthicsError):
            self.engine()._validate_request("diagnose my brother")

    def test_with_enforcement_off_nothing_is_checked(self):
        _OscillatingEngine(_ToggleBackend(), enforce_constitutional=False)._validate_request("diagnose my brother")


class TestRuleEngineBoundsAndErrors(unittest.TestCase):
    def test_cycle_detection_catches_oscillating_rule(self):
        engine = _OscillatingEngine(_ToggleBackend(), enforce_constitutional=False)
        with self.assertRaises(CycleDetectedError):
            engine.reduce_to_fixed_point("A", max_depth=10)

    def test_max_depth_exact_boundary_and_one_past_and_type_confusion(self):
        simplifier = AlgebraSimplifier()
        # "x + 0" takes exactly 1 rewrite step to reach fixed point "x".
        t_exact = simplifier.reduce_to_fixed_point("x + 0", max_depth=1)
        self.assertTrue(t_exact.converged)
        self.assertEqual(t_exact.depth, 1)
        self.assertEqual(t_exact.final, "x")

        # Boundary - 1 must fail with RecursionLimitError!
        with self.assertRaises(RecursionLimitError):
            simplifier.reduce_to_fixed_point("x + 0", max_depth=0)

        # Unbounded incrementer exceeds max_depth cleanly
        inc = _CountingEngine(_ToggleBackend(), enforce_constitutional=False)
        with self.assertRaises(RecursionLimitError):
            inc.reduce_to_fixed_point(0, max_depth=5)

        # Already fixed point succeeds even with max_depth=0
        t_zero = simplifier.reduce_to_fixed_point("x", max_depth=0)
        self.assertTrue(t_zero.converged)
        self.assertEqual(t_zero.depth, 0)

        # bool (True/False) and negative integers must not slip through as int max_depth
        for bad in (True, False, -1, 1.5, "2"):
            with self.assertRaises(ValueError):
                simplifier.reduce_to_fixed_point("x", max_depth=bad)  # type: ignore[arg-type]


class TestAlgebraSimplifierGroundTruth(unittest.TestCase):
    def setUp(self) -> None:
        self.backend = AlgebraBackend()
        self.engine = AlgebraSimplifier(self.backend)

    def test_preserves_numerical_ground_truth_and_terminates(self):
        cases = [
            ("((x + 0) * 1 + (y - y)) + --x", "2 * x"),
            ("0 * (x + y * z)", "0"),
            ("(3 + 4) * (2 - 1)", "7"),
            ("a - (b - b) - -c", "a + c"),
            ("(u + (-u)) + 5 * 0", "0"),
            ("-(-(-(-x)))", "x"),
            ("0 - x", "-x"),
        ]
        envs = [
            {"x": 0, "y": 0, "z": 0, "a": 0, "b": 0, "c": 0, "u": 0},
            {"x": -7, "y": 13, "z": 4, "a": 10, "b": -3, "c": 9, "u": -2},
            {"x": 101, "y": -99, "z": -1, "a": -5, "b": 5, "c": -4, "u": 17},
        ]
        for raw, expected in cases:
            store = InMemoryLedgerStore()
            trace = self.engine.reduce_to_fixed_point(raw, max_depth=32, store=store)
            self.assertTrue(trace.converged, raw)
            self.assertTrue(trace.integrity_verified, raw)
            self.assertEqual(trace.final, expected, raw)
            # Verify final state truly is a fixed point (idempotent)
            next_node, rule = self.engine.rewrite_once(trace.final_expression)
            self.assertIsNone(rule)
            self.assertEqual(next_node, trace.final_expression)

            ast_in = self.backend.parse(raw)
            for env in envs:
                self.assertEqual(
                    self.backend.evaluate(ast_in, env),
                    self.backend.evaluate(trace.final_expression, env),
                    (raw, env),
                )

    def test_empty_and_malformed_inputs_raise_cleanly(self):
        for bad in ("", "   ", "x +", "(x + 1", "@bad", 123):
            with self.assertRaises(ValueError):
                self.backend.parse(bad)  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "non-empty string"):
            self.backend.parse("")
        with self.assertRaises(KeyError):
            self.backend.evaluate(Var("missing"), {})
        self.assertEqual(self.backend.complexity(Const(42)), 1)

    def test_canonical_formatting_parenthesizes_only_when_precedence_requires(self):
        cases = [
            ("x * (y + z)", "x * (y + z)"),
            ("x + y * z", "x + y * z"),
            ("x + (y + z)", "x + y + z"),
            ("x - (y + z)", "x - (y + z)"),
            ("(x + y) - z", "x + y - z"),
            ("x - y * z", "x - y * z"),
            ("x * (y * z)", "x * y * z"),
        ]
        env = {"x": 2, "y": 5, "z": 3}
        for raw, expected in cases:
            ast_in = self.backend.parse(raw)
            formatted = self.backend.format(ast_in)
            self.assertEqual(formatted, expected, raw)
            self.assertEqual(
                self.backend.evaluate(ast_in, env),
                self.backend.evaluate(self.backend.parse(formatted), env),
                raw,
            )

    def test_complexity_counts_every_ast_node(self):
        self.assertEqual(self.backend.complexity(self.backend.parse("-x")), 2)
        self.assertEqual(self.backend.complexity(self.backend.parse("x + y")), 3)
        self.assertEqual(self.backend.complexity(self.backend.parse("-(x + y * 2)")), 6)

    def test_left_identities_inverses_and_nontrivial_constant_mul(self):
        env = {"x": 7, "y": -3}
        t_mul = self.engine.reduce_to_fixed_point("3 * 4")
        self.assertEqual(t_mul.final, "12")
        self.assertEqual(t_mul.steps[0].rule, "constant_fold_mul")
        self.assertEqual(self.backend.evaluate(t_mul.final_expression, env), 12)

        for raw, expected in (("0 + x", "x"), ("2 + x", "2 + x"), ("(-x) + x", "0"), ("(-x) + y", "-x + y")):
            trace = self.engine.reduce_to_fixed_point(raw)
            self.assertEqual(trace.final, expected, raw)
            self.assertEqual(
                self.backend.evaluate(self.backend.parse(raw), env),
                self.backend.evaluate(trace.final_expression, env),
                raw,
            )


class TestPropositionalReducerGroundTruth(unittest.TestCase):
    def setUp(self) -> None:
        self.backend = LogicBackend()
        self.reducer = PropositionalReducer(self.backend)

    def test_preserves_exhaustive_truth_table_across_every_step(self):
        formulas = [
            ("((p -> q) & (p & ~p)) | ~~r", "r"),
            ("~(p & q)", "~p | ~q"),
            ("~(p | ~q)", "~p & q"),
            ("(p -> p) & (q | ~q)", "True"),
            ("False -> (p & q)", "True"),
            ("p & p", "p"),
            ("p | ~p", "True"),
            ("p & ~p", "False"),
        ]
        for raw, expected in formulas:
            ast_in = self.backend.parse(raw)
            var_names = self.backend.variables(ast_in)
            tt_in = self.backend.truth_table(ast_in, var_names)

            trace = self.reducer.reduce_to_fixed_point(raw, max_depth=32)
            self.assertTrue(trace.converged, raw)
            self.assertEqual(trace.final, expected, raw)

            tt_out = self.backend.truth_table(trace.final_expression, var_names)
            self.assertEqual(tt_in, tt_out, raw)

            # Fixed point check
            _, rule = self.reducer.rewrite_once(trace.final_expression)
            self.assertIsNone(rule)

    def test_invalid_inputs_complexity_default_backend_and_or_annihilation(self):
        with self.assertRaisesRegex(ValueError, "non-empty string"):
            self.backend.parse("")
        with self.assertRaises(ValueError):
            self.backend.parse(123)  # type: ignore[arg-type]

        self.assertEqual(self.backend.complexity(self.backend.parse("p")), 1)
        self.assertEqual(self.backend.complexity(self.backend.parse("~p")), 2)
        self.assertEqual(self.backend.complexity(self.backend.parse("p & q")), 3)
        self.assertEqual(self.backend.complexity(self.backend.parse("~p & (q | r)")), 6)

        default_reducer = PropositionalReducer()
        self.assertEqual(default_reducer.reduce_to_fixed_point("p & p").final, "p")

        for raw in ("True | p", "p | True"):
            ast_in = self.backend.parse(raw)
            tt_in = self.backend.truth_table(ast_in, ("p",))
            trace = self.reducer.reduce_to_fixed_point(raw)
            self.assertEqual(trace.final, "True", raw)
            self.assertEqual(tt_in, self.backend.truth_table(trace.final_expression, ("p",)), raw)


class TestQuickstartScript(unittest.TestCase):
    def test_quickstart_executes_end_to_end(self):
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        script = os.path.join(repo_root, "examples", "quickstart.py")
        proc = subprocess.run(
            [sys.executable, "-B", script],
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertIn("Fixed point      : 2 * x", proc.stdout)
        self.assertIn("Fixed point      : r", proc.stdout)
        self.assertIn("Conformance Suite: CONFORMS=True", proc.stdout)


if __name__ == "__main__":
    unittest.main()
