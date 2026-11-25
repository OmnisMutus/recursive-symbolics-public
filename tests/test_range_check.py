"""Tests for symbolics/range_check.py: can every gate both pass and fail?

Ground truth:
1. The verdict rule, on hand-made cases whose answer is known: (True, False) is OK; equal verdicts are STUCK;
   (False, True) is STUCK and says backwards; anything but two booleans, or a raise, is ERROR.
2. Break-it on real gates: replace a real gate with one hardcoded to pass, and its registered case must
   report STUCK. This is the failure the module exists to catch.
3. Discovery: a public `check` or `check_...` function nobody registered is UNREGISTERED; private helpers,
   methods and look-alike names (checkpoint) are not gates.
4. The real package: every registered gate is OK and none is unregistered.
"""
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from symbolics import breaches, conformance, outgoing, range_check as rc


class TestVerdict(unittest.TestCase):
    def test_good_passes_and_bad_fails_is_ok(self):
        self.assertEqual(rc.verdict(lambda: (True, False))["status"], rc.OK)

    def test_always_passing_is_stuck(self):
        v = rc.verdict(lambda: (True, True))
        self.assertEqual(v["status"], rc.STUCK)
        self.assertIn("both inputs passed", v["detail"])

    def test_always_failing_is_stuck(self):
        v = rc.verdict(lambda: (False, False))
        self.assertEqual(v["status"], rc.STUCK)
        self.assertIn("both inputs failed", v["detail"])

    def test_backwards_is_stuck_and_says_so(self):
        v = rc.verdict(lambda: (False, True))
        self.assertEqual(v["status"], rc.STUCK)
        self.assertIn("backwards", v["detail"])

    def test_non_boolean_verdicts_are_errors(self):
        for pair in [(1, 0), (True, None), ({"ok": True}, False), (True, 0)]:
            with self.subTest(pair=pair):
                self.assertEqual(rc.verdict(lambda: pair)["status"], rc.ERROR)

    def test_a_case_that_raises_is_an_error(self):
        def broken():
            raise RuntimeError("no git here")
        v = rc.verdict(broken)
        self.assertEqual(v["status"], rc.ERROR)
        self.assertIn("RuntimeError: no git here", v["detail"])


class TestBreakIt(unittest.TestCase):
    """A real gate hardcoded to pass must be reported STUCK by its own registered case."""

    def test_breaches_hardcoded_to_pass(self):
        with mock.patch.object(breaches, "check", lambda *a, **k: {"ok": True}):
            self.assertEqual(rc.verdict(rc.breaches_check)["status"], rc.STUCK)

    def test_outgoing_hardcoded_to_pass(self):
        with mock.patch.object(outgoing, "check", lambda *a, **k: {"ok": True}):
            self.assertEqual(rc.verdict(rc.outgoing_check)["status"], rc.STUCK)

    def test_no_network_hardcoded_to_pass(self):
        row = {"status": conformance.PASS}
        with mock.patch.object(conformance, "check_no_network", lambda *a, **k: row):
            self.assertEqual(rc.verdict(rc.conformance_no_network)["status"], rc.STUCK)

    def test_conformance_run_hardcoded_to_conform(self):
        with mock.patch.object(conformance, "run", lambda *a, **k: {"conforms": True}):
            self.assertEqual(rc.verdict(rc.conformance_run)["status"], rc.STUCK)


class TestDiscovery(unittest.TestCase):
    def _package(self, source):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        (Path(tmp.name) / "mod.py").write_text(source, encoding="utf-8")
        return tmp.name

    def test_finds_check_and_check_prefixed_functions_only(self):
        pkg = self._package(
            "def check(): pass\n"
            "def check_thing(): pass\n"
            "def _check_private(): pass\n"
            "def checkpoint(): pass\n"
            "def checker(): pass\n"
            "class C:\n    def check(self): pass\n"
        )
        self.assertEqual(rc.gate_names(pkg), {"mod.check", "mod.check_thing"})

    def test_an_unregistered_gate_fails_the_run(self):
        pkg = self._package("def check_new_rule(): pass\n")
        result = rc.run(gates={"x.ok": lambda: (True, False)}, package_dir=pkg, not_gates={})
        self.assertFalse(result["ok"])
        self.assertEqual([r["gate"] for r in result["rows"] if r["status"] == rc.UNREGISTERED],
                         ["mod.check_new_rule"])

    def test_a_gate_listed_as_not_a_gate_is_not_reported(self):
        pkg = self._package("def check_row(): pass\n")
        result = rc.run(gates={"x.ok": lambda: (True, False)}, package_dir=pkg,
                        not_gates={"mod.check_row": "a row of another gate"})
        self.assertTrue(result["ok"])

    def test_one_stuck_gate_fails_the_run(self):
        pkg = self._package("")
        result = rc.run(gates={"a": lambda: (True, False), "b": lambda: (True, True)}, package_dir=pkg,
                        not_gates={})
        self.assertFalse(result["ok"])

    def test_nothing_checked_is_not_a_pass(self):
        pkg = self._package("")
        self.assertFalse(rc.run(gates={}, package_dir=pkg, not_gates={})["ok"])

    def test_report_shows_each_row_and_the_verdict(self):
        pkg = self._package("")
        text = rc.report(rc.run(gates={"a.gate": lambda: (True, True)}, package_dir=pkg, not_gates={}))
        self.assertIn("STUCK", text)
        self.assertIn("a.gate", text)
        self.assertIn("RANGE OK: False", text)


class TestRealPackage(unittest.TestCase):
    def test_every_gate_in_the_package_can_pass_and_fail(self):
        result = rc.run()
        bad = [r for r in result["rows"] if r["status"] != rc.OK]
        self.assertEqual(bad, [])
        self.assertTrue(result["ok"])
        with contextlib.redirect_stdout(io.StringIO()) as shown:
            self.assertEqual(rc.main(), 0)
        self.assertIn("RANGE OK: True", shown.getvalue())

    def test_every_not_gate_entry_still_exists(self):
        # A stale entry here would quietly excuse a function that no longer exists, or hide a renamed one.
        self.assertTrue(set(rc.NOT_GATES) <= rc.gate_names())


if __name__ == "__main__":
    unittest.main()
