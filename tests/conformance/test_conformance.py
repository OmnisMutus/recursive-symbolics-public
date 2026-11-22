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

    @staticmethod
    def sovereign(gamma_max=0.85, log=True):
        """An honest enforcement path: whatever the answer was, what reaches the person offers."""
        def decorate(fn):
            return lambda: {"type": "fact", "content": "One option is to rest first."}
        return decorate


class LooseAgency(FakeAgency):
    GAMMA_MAX = 1.0

    @staticmethod
    def cap(gamma):
        return gamma


class LeakyAgency(FakeAgency):
    """Declares the right cap and clamps numbers correctly, but its enforcement path sends the command as it is.
    The old check passed this; the effective-limit check must not."""

    @staticmethod
    def sovereign(gamma_max=0.85, log=True):
        def decorate(fn):
            return lambda: {"type": "fact", "content": fn()}
        return decorate


class LowerCapIgnored(FakeAgency):
    """Enforces the default cap, but ignores a lower one: a reply at 0.6 passes a requested 0.5."""

    @staticmethod
    def directive_strength(text):
        return 0.6 if "consider" in text.lower() else (0.9 if "must" in text.lower() else 0.2)

    @staticmethod
    def sovereign(gamma_max=0.85, log=True):
        def decorate(fn):
            return lambda: {"type": "fact", "content": "Consider doing it now."}
        return decorate


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

    def test_directivity_checks_what_actually_reaches_the_person(self):
        """Added 2026-11-20 after an outside review: a clamp below 0.85 is not enough. An implementation that
        sends the command unchanged, or ignores a lower cap, fails; one without an enforcement path is not
        implemented."""
        self.assertEqual(C.check_directivity(LeakyAgency)["status"], C.FAIL)
        self.assertEqual(C.check_directivity(LowerCapIgnored)["status"], C.FAIL)

        class NoEnforcement:
            GAMMA_MAX = 0.85
            directive_strength = staticmethod(FakeAgency.directive_strength)
            cap = staticmethod(FakeAgency.cap)
        self.assertEqual(C.check_directivity(NoEnforcement)["status"], C.NOT_IMPLEMENTED)

    @staticmethod
    def sending(reply, strength):
        """A fake whose enforcement path sends `reply` at both caps, and whose measure gives it `strength`."""
        class Fake(FakeAgency):
            @staticmethod
            def directive_strength(text):
                return strength if text == reply else 0.9

            @staticmethod
            def sovereign(gamma_max=0.85, log=True):
                return lambda fn: (lambda: reply if isinstance(reply, str) and reply.startswith("bare:")
                                   else {"type": "fact", "content": reply})
        return Fake

    def test_a_reply_exactly_at_each_cap_is_allowed(self):
        """conformance.py:111 and :112: the limit itself is inside it. A reply at exactly 0.5 passes both caps;
        one at exactly 0.85 passes the default but not the lower one."""
        self.assertEqual(C.check_directivity(self.sending("One option is to rest.", 0.5))["status"], C.PASS)
        self.assertEqual(C.check_directivity(self.sending("One option is to rest.", 0.85))["status"], C.FAIL)

        class AtEachCap(FakeAgency):
            @staticmethod
            def directive_strength(text):
                return {"at default": 0.85, "at lower": 0.5}.get(text, 0.9)

            @staticmethod
            def sovereign(gamma_max=0.85, log=True):
                text = "at lower" if gamma_max < 0.85 else "at default"
                return lambda fn: (lambda: {"type": "fact", "content": text})
        self.assertEqual(C.check_directivity(AtEachCap)["status"], C.PASS)

    def test_the_probes_measure_must_lie_in_zero_to_one_inclusive(self):
        """conformance.py:113, 0.0 <= measured <= 1.0. Added 2026-11-22, when the mutation gate began to mutate
        chained comparisons: no test held the probe's measure at either end. Both ends are inside the range."""
        def fake(probe_value):
            class Fake(FakeAgency):
                @staticmethod
                def directive_strength(text):
                    return 0.5 if text == "One option is to rest." else probe_value

                @staticmethod
                def sovereign(gamma_max=0.85, log=True):
                    return lambda fn: (lambda: {"type": "fact", "content": "One option is to rest."})
            return Fake
        for value, want in ((0.0, C.PASS), (1.0, C.PASS), (-0.01, C.FAIL), (1.01, C.FAIL)):
            self.assertEqual(C.check_directivity(fake(value))["status"], want, value)

    def test_a_bare_string_or_an_unreadable_record_is_not_withheld(self):
        """conformance.py:108: only a refusal record counts as withheld. A bare string reaches the person as it is,
        and a record with no text cannot be checked, so neither may pass as 'withheld' under the lower cap."""
        self.assertEqual(C.check_directivity(self.sending("bare: you must go", 0.9))["status"], C.FAIL)

        class NoText(FakeAgency):
            @staticmethod
            def sovereign(gamma_max=0.85, log=True):
                return lambda fn: (lambda: {"type": "fact"})
        self.assertEqual(C.check_directivity(NoText)["status"], C.FAIL)

        class WithholdsBelowOnly(FakeAgency):
            @staticmethod
            def sovereign(gamma_max=0.85, log=True):
                out = {"type": "refusal", "why": "withheld"} if gamma_max < 0.85 else {
                    "type": "fact", "content": "One option is to rest."}
                return lambda fn: (lambda: out)
        self.assertEqual(C.check_directivity(WithholdsBelowOnly)["status"], C.PASS)

    def test_the_real_agency_passes_the_effective_check_and_says_how(self):
        from symbolics import agency
        row = C.check_directivity(agency)
        self.assertEqual(row["status"], C.PASS, row["detail"])
        self.assertIn("what sovereign() let through, re-measured", row["detail"])


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
