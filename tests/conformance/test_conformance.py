"""The Conformance Suite, checked itself.

Ground truth: the licence's own Articles 5.1(D), 6, 8 and 9, and the honesty guard the correspondence ledger
established (a run in which nothing could be checked does not pass). The suite is what the licence points at, so
a suite that passes vacuously would be worse than no suite at all; these tests exist to make that impossible.
"""
import os
import unittest

from symbolics import conformance as C
from symbolics import ethics as E


class FakeAgency:
    GAMMA_MAX = 0.85

    @staticmethod
    def directive_strength(text):
        return 0.9 if "must" in text.lower() else 0.2

    @staticmethod
    def cap(gamma):
        return min(gamma, FakeAgency.GAMMA_MAX)


class LooseAgency(FakeAgency):
    GAMMA_MAX = 1.0

    @staticmethod
    def cap(gamma):
        return gamma


class TestChecks(unittest.TestCase):
    def test_the_package_reaches_no_network(self):
        r = C.check_no_network()
        self.assertEqual(r["status"], C.PASS, r["detail"])

    def test_a_network_import_is_caught(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "leaky.py"), "w", encoding="utf-8") as fh:
                fh.write("import urllib.request\n")
            r = C.check_no_network(tmp)
        self.assertEqual(r["status"], C.FAIL)
        self.assertIn("leaky.py", r["detail"])

    def test_other_state_boundary(self):
        self.assertEqual(C.check_other_state(E)["status"], C.PASS)

    def test_non_reduction(self):
        rows = C.check_non_reduction(E)
        self.assertEqual([r["status"] for r in rows], [C.PASS, C.PASS])

    def test_an_engine_that_lets_ranking_through_fails(self):
        class Lax:
            CAVEAT = E.CAVEAT

            @staticmethod
            def emit(value):
                return value

            check_request = staticmethod(E.check_request)

        self.assertEqual(C.check_non_reduction(Lax)[0]["status"], C.FAIL)

    def test_a_network_import_in_a_subpackage_is_caught(self):
        """The walk descends into subpackages; only __pycache__ is pruned."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "sub"))
            with open(os.path.join(tmp, "sub", "leaky.py"), "w", encoding="utf-8") as fh:
                fh.write("import socket\n")
            r = C.check_no_network(tmp)
        self.assertEqual(r["status"], C.FAIL)
        self.assertIn("leaky.py", r["detail"])

    def test_the_caveat_needs_both_halves(self):
        """'symbolic map' alone, or 'lived experience' alone, is not the statement Article 8 asks for."""
        for caveat in ("This is a symbolic map.", "Trust your lived experience.", ""):
            class Partial:
                CAVEAT = caveat
                emit = staticmethod(E.emit)
            row = C.check_non_reduction(Partial)[1]
            self.assertEqual(row["status"], C.FAIL, caveat)
            self.assertEqual(row["detail"], caveat or "none")

    def test_other_state_fails_unless_both_directions_hold(self):
        """Refusing everything is as much a failure of Article 5.1(D) as refusing nothing."""
        refusal = {"type": "refusal", "why": "no"}
        engines = {
            "refuses everything": lambda text: dict(refusal),
            "refuses nothing": lambda text: None,
            "wrong record type": lambda text: {"type": "fact", "why": "no"} if "diagnose" in text else None,
            "not a record": lambda text: "refusal" if "diagnose" in text else None,
        }
        for label, check in engines.items():
            class Fake:
                check_request = staticmethod(check)
            self.assertEqual(C.check_other_state(Fake)["status"], C.FAIL, label)

    def test_directivity_needs_both_the_cap_and_the_measure(self):
        class CapOnly:
            GAMMA_MAX = 0.85

        class MeasureOnly:
            @staticmethod
            def directive_strength(text):
                return 0.2

        for impl in (CapOnly, MeasureOnly):
            self.assertEqual(C.check_directivity(impl)["status"], C.NOT_IMPLEMENTED, impl.__name__)

    def test_directivity_is_not_implemented_until_agency_exists(self):
        self.assertEqual(C.check_directivity(None)["status"], C.NOT_IMPLEMENTED)

    def test_directivity_passes_with_a_capped_implementation(self):
        self.assertEqual(C.check_directivity(FakeAgency)["status"], C.PASS)

    def test_directivity_fails_when_the_cap_is_above_the_article(self):
        self.assertEqual(C.check_directivity(LooseAgency)["status"], C.FAIL)


class TestHonestyGuard(unittest.TestCase):
    def test_an_unchecked_duty_stops_conformance(self):
        """The guard itself, exercised independently of the engine's current state: hand the suite no agency
        implementation and Article 6 cannot be checked, so the run does not conform however well the rest did.

        CORRECTED 2026-11-08: this test previously asserted that the engine as a whole does not conform, which
        was the honest state until agency.py existed. It now conforms, so the claim moved to the test below and
        this one keeps proving the guard rather than the circumstance. See LIBER_0.md for the entry."""
        report = C.run(ethics=E, agency=None)
        self.assertFalse(report["conforms"])
        self.assertEqual(report["counts"][C.FAIL], 0)
        self.assertGreaterEqual(report["counts"][C.NOT_IMPLEMENTED], 1)

    def test_the_engine_conforms_today(self):
        """The live state, pinned so that a regression shows up here rather than in a README."""
        report = C.run()
        self.assertTrue(report["conforms"], report["rows"])
        self.assertEqual(report["counts"][C.FAIL], 0)
        self.assertEqual(report["counts"][C.NOT_IMPLEMENTED], 0)

    def test_it_conforms_once_every_duty_is_checked_and_holds(self):
        report = C.run(ethics=E, agency=FakeAgency)
        self.assertTrue(report["conforms"], report["rows"])
        self.assertEqual(report["counts"][C.NOT_IMPLEMENTED], 0)

    def test_one_failure_is_enough_to_stop_conformance(self):
        self.assertFalse(C.run(ethics=E, agency=LooseAgency)["conforms"])

    def test_the_report_prints_every_article(self):
        out = C.text(C.run())
        for article in ("5.1(D)", "6", "8", "9"):
            self.assertIn(f"Article {article}", out)
        self.assertIn("CONFORMS:", out)


if __name__ == "__main__":
    unittest.main()
