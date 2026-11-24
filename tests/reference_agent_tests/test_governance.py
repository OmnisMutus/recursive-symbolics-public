"""The V2.0 Epistemic Governance Framework, enforced on this agent's own output (governance.py).

Ground truth, in the order STANDARD.md asks for it:

1. INDEPENDENT REFERENCE. The framework document itself, which predates this module: the Core
   Axiom, the confidence formula, the falsifiability requirement, the Provisional Mapping Proviso, Occam's
   Razor Filter, and the 0.85 agency cap. CASES below is a hand-built table of statements with the verdict the
   framework gives each, written from that document. Its forbidden example, "Anger is Geburah", is also the
   engine's Core Axiom example, so the two agree independently.
2. A SECOND IMPLEMENTATION. The confidence figures are computed by hand in the table rather than by calling
   this module, so the arithmetic is checked and not merely re-run.
3. BY HAND. 0.6 x 0.7 / 3 = 0.14 = 14.0%, written out below.

The rule under test, in one line: a symbolic claim leaves this agent with a confidence bound, a falsifier and
a provisional label, or it does not leave.
"""
import unittest

from reference_agent import governance as G

# (statement, should it be refused, why)
CASES = [
    ("Frustration reads as Geburah under the Kabbalistic lens", False, "a reading under a named lens"),
    ("This state reads like Geburah on this map", False, "hedged, and the map is named"),
    ("Anger is Geburah.", True, "the Core Axiom's own forbidden example"),
    ("Your frustration corresponds to Geburah.", True, "identity by another verb"),
    ("That pattern means Tiphareth.", True, "identity by 'means'"),
    ("The third path equals Binah in this scheme.", True, "identity by 'equals'"),
    ("Shin represents Fire.", True, "identity about a letter, not a sephirah"),
    ("The vault has 969 notes.", False, "not a symbolic claim at all"),
]

FALSIFIER = "If the same state reads as expansive under every other lens tried, this reading is wrong."


class TestTheForbiddenShape(unittest.TestCase):
    def test_every_case(self):
        for text, refused, why in CASES:
            try:
                G.claim(text, 0.6, 0.7, 3, FALSIFIER, lens="kabbalistic")
                self.assertFalse(refused, f"{text!r} should have been refused ({why})")
            except G.GovernanceError:
                self.assertTrue(refused, f"{text!r} should have passed ({why})")

    def test_the_core_axiom_example_is_refused_and_the_fix_is_named(self):
        with self.assertRaises(G.GovernanceError) as caught:
            G.claim("Anger is Geburah", 1.0, 1.0, 1, FALSIFIER)
        said = str(caught.exception)
        self.assertIn("Core Axiom", said)
        self.assertIn("reads as", said)                      # it says what to write instead


class TestTheFourDuties(unittest.TestCase):
    def test_confidence_is_the_frameworks_formula_checked_by_hand(self):
        self.assertEqual(G.confidence(0.6, 0.7, 3), 14.0)    # 0.42 / 3 = 0.14
        self.assertEqual(G.confidence(1.0, 1.0, 1), 100.0)
        self.assertEqual(G.confidence(0.5, 0.5, 5), 5.0)     # 0.25 / 5 = 0.05

    def test_there_is_always_at_least_one_alternative(self):
        """Zero alternatives would divide by nothing and read as certainty. Coincidence is always a rival."""
        with self.assertRaises(G.GovernanceError) as caught:
            G.confidence(0.9, 0.9, 0)
        self.assertIn("coincidence", str(caught.exception))

    def test_an_input_outside_zero_to_one_is_refused(self):
        for bad in ((2.0, 0.5), (0.5, -1), ("high", 0.5)):
            with self.assertRaises(G.GovernanceError):
                G.confidence(bad[0], bad[1], 2)

    def test_a_claim_with_no_falsifier_is_not_a_claim(self):
        with self.assertRaises(G.GovernanceError) as caught:
            G.claim("X reads as Geburah under the lens", 0.6, 0.7, 3, "")
        self.assertIn("not a claim", str(caught.exception))

    def test_a_falsifier_naming_no_observation_is_refused(self):
        for vague in ("it feels wrong", "further study needed", "TBD"):
            with self.assertRaises(G.GovernanceError):
                G.claim("X reads as Geburah under the lens", 0.6, 0.7, 3, vague)

    def test_every_claim_is_labelled_provisional(self):
        out = G.claim("X reads as Geburah under the lens", 0.6, 0.7, 3, FALSIFIER)
        self.assertEqual(out["status"], G.PROVISIONAL)
        self.assertIn("maps, not territory", out["axiom"])

    def test_occams_filter_rejects_a_reading_that_explains_nothing_new(self):
        same = G.occam("sorting", ["why merge is stable"], ["why merge is stable"])
        self.assertFalse(same["keep"])
        self.assertIn("explains nothing", same["why"])
        more = G.occam("sorting", ["why merge is stable", "why quicksort splits"], ["why merge is stable"])
        self.assertTrue(more["keep"])
        self.assertEqual(more["gained"], ["why quicksort splits"])


class TestTheAgencyBudget(unittest.TestCase):
    def test_directive_strength_never_exceeds_the_cap(self):
        for text in ("do it", "x", "You must do this now and nothing else.", "a " * 200):
            self.assertLessEqual(G.gamma(text), G.GAMMA_CAP, text[:20])

    def test_varied_text_is_less_directive_than_a_single_word(self):
        varied = G.gamma("some find this useful, others read it differently, and a third view exists")
        self.assertLess(varied, G.gamma("must"))

    def test_empty_text_is_not_directive(self):
        self.assertEqual(G.gamma(""), 0.0)

    def test_a_review_flags_text_at_the_cap(self):
        # Until 2026-11-22 this used "must": one word sat at the cap only because gamma was the entropy half
        # alone. With agency's single measure one word is SHORT_TEXT_GAMMA (0.45), and a real command is at the cap.
        out = G.review("You must meditate every morning. It is the only way.")
        self.assertTrue(any(f["duty"] == "agency budget" for f in out["findings"]), out)

    def test_review_and_agency_agree_on_the_same_words(self):
        # the drift found while writing docs/API.md: review said 0.0 where agency said 0.85
        from symbolics import agency
        for text in ("You must meditate every morning. It is the only way.", "a a b",
                     "You might sit with it, or you could try the opposite.", "breathe, breathe, breathe"):
            self.assertEqual(G.review(text)["directive_strength"], round(agency.directive_strength(text), 4), text)

    def test_zero_and_one_are_fractions_and_just_outside_is_not(self):
        # governance.py:91, 0 <= value <= 1: both ends are allowed (found when chained comparisons began to be
        # mutated, 2026-11-22). By hand: 0 x 0.5 / 1 is 0.0%, and 1 x 1 / 2 is 50.0%.
        self.assertEqual(G.confidence(0, 0.5, 1), 0.0)
        self.assertEqual(G.confidence(1, 1, 2), 50.0)
        for bad in (-0.01, 1.01):
            with self.assertRaises(G.GovernanceError):
                G.confidence(bad, 0.5, 1)

    def test_counts_are_whole_numbers(self):
        # Outside review, 2026-11-22: confidence(0.5, 0.5, True) and (..., 1.9) were both read as 1 alternative
        for bad in (True, 1.9, 2.0, "2"):
            with self.assertRaises(G.GovernanceError, msg=repr(bad)):
                G.confidence(0.5, 0.5, bad)
            with self.assertRaises(G.GovernanceError, msg=repr(bad)):
                G.rank(formally_defined=True, independent_practitioners=bad)
        self.assertEqual(G.confidence(0.5, 0.5, 2), 12.5)           # by hand: 0.25 / 2 = 12.5%
        self.assertEqual(G.rank(formally_defined=True, independent_practitioners=None)["inputs"]
                         ["independent_practitioners"], 0)

    def test_the_spellings_metrics_uses_are_symbols_too(self):
        # Outside review, 2026-11-22: metrics.py spells Keter and Tifereth; governance knew only Kether and Tiphareth
        self.assertEqual(G.is_ontological("Balance is Tifereth. Origin is Keter."), ["is Tifereth", "is Keter"])

    def test_every_defined_spelling_is_a_symbol(self):
        # 2026-11-23: the Sephiroth now come from symbolics.address.SEPHIROTH, in every spelling and in Hebrew
        from symbolics.address import HEBREW_SPELLINGS, SEPHIROTH
        for s in SEPHIROTH:
            for n in (*s.spellings, *(h for h, name in HEBREW_SPELLINGS.items() if name == s.name)):
                with self.subTest(name=n):
                    self.assertEqual(G.is_ontological(f"Anger is {n}."), [f"is {n}"])
                    self.assertEqual(G.is_ontological(f"{n} means anger."), [f"{n} means"])
                    self.assertEqual(G.is_ontological(f"Anger is {n}, on this map."), [])
        self.assertEqual(G.is_ontological("Anger is Gevurahs."), [])      # a whole word only
        self.assertEqual(G.is_ontological("Anger is גבורות."), [])         # a whole Hebrew word only
        self.assertEqual(G.is_ontological("Anger is גְּבוּרָה."), ["is גבורה"])   # with vowel points too
        self.assertEqual(G.is_ontological("כעס is גבורה, on this map."), [])

    def test_a_hedge_excuses_only_its_own_sentence(self):
        # Outside review, 2026-11-22: the "lens" of a camera, a sentence earlier, excused the claim
        self.assertEqual(G.is_ontological("I wiped my camera lens. Anger is Geburah."), ["is Geburah"])
        self.assertEqual(G.is_ontological("Anger is Geburah. That reads as one reading."), ["is Geburah"])
        self.assertEqual(G.is_ontological("Under the Kabbalistic lens, anger is Geburah."), [])
        self.assertEqual(G.is_ontological("Anger is Geburah, on this map."), [])

    def test_a_hedge_is_a_whole_word(self):
        self.assertEqual(G.is_ontological("Anger is Geburah, says the lensmaker."), ["is Geburah"])

    def test_true_is_not_a_fraction(self):
        for name in ("evidence_quality", "pattern_coherence"):
            kw = {"evidence_quality": 0.5, "pattern_coherence": 0.5, "alternatives": 2, name: True}
            with self.assertRaises(G.GovernanceError):
                G.confidence(**kw)


class TestReviewingProse(unittest.TestCase):
    def test_it_finds_both_the_identity_and_the_missing_falsifier(self):
        out = G.review("Anger is Geburah and that is simply what it means.")
        duties = {f["duty"] for f in out["findings"]}
        self.assertIn("provisional proviso", duties)
        self.assertIn("empirical falsifiability", duties)
        self.assertFalse(out["clean"])

    def test_hedged_prose_is_clean(self):
        out = G.review("Under the Kabbalistic lens this reads as Geburah, which is one reading among several.")
        self.assertTrue(out["clean"], out["findings"])

    def test_ordinary_prose_is_clean(self):
        self.assertTrue(G.review("The vault holds 969 notes and 896 claims were verified.")["clean"])

    def test_strict_raises_instead_of_reporting(self):
        with self.assertRaises(G.GovernanceError):
            G.review("Anger is Geburah.", strict=True)

    def test_the_report_puts_the_uncertainty_with_the_claim(self):
        text = G.report(G.claim("X reads as Geburah under the lens", 0.6, 0.7, 3, FALSIFIER, lens="kab"))
        self.assertIn(G.PROVISIONAL, text)
        self.assertIn("14.0%", text)
        self.assertIn("falsified by:", text)
        self.assertIn("3 alternative", text)


if __name__ == "__main__":
    unittest.main()


class TestTheConfidenceRanking(unittest.TestCase):
    """The framework's own 4-rank scale (verification-standards.md), which is a different question from the
    percentage: the percentage says how well-evidenced a reading is, the rank says what kind of evidence
    exists at all. Ground truth is that document's stated criteria, typed out here."""

    def test_the_four_ranks_and_why_each_is_not_higher(self):
        self.assertEqual(G.rank()["rank"], 1)
        self.assertEqual(G.rank(formally_defined=True)["rank"], 2)
        self.assertEqual(G.rank(formally_defined=True, independent_practitioners=3)["rank"], 3)
        self.assertEqual(G.rank(formally_defined=True, independent_practitioners=3,
                                computationally_modelled=True)["rank"], 4)

    def test_three_practitioners_is_the_threshold_not_two(self):
        self.assertEqual(G.rank(formally_defined=True, independent_practitioners=2)["rank"], 2)
        self.assertIn("asks for three", G.rank(formally_defined=True, independent_practitioners=2)
                      ["not_higher_because"])

    def test_a_computational_model_without_replication_is_not_rank_4(self):
        """Modelling something does not make practitioners reproduce it. This is the overclaim to avoid."""
        out = G.rank(formally_defined=True, independent_practitioners=0, computationally_modelled=True)
        self.assertEqual(out["rank"], 2)

    def test_repetition_without_formal_definition_stays_anecdote(self):
        out = G.rank(formally_defined=False, independent_practitioners=50, computationally_modelled=True)
        self.assertEqual(out["rank"], 1)
        self.assertIn("anecdote", out["not_higher_because"])

    def test_rank_4_states_no_reservation(self):
        self.assertNotIn("not_higher_because", G.rank(True, 3, True))

    def test_a_claim_carries_its_rank_and_the_report_shows_it(self):
        out = G.claim("X reads as Geburah under the lens", 0.6, 0.7, 3, FALSIFIER,
                      formally_defined=True, independent_practitioners=1)
        self.assertEqual(out["confidence_rank"]["rank"], 2)
        text = G.report(out)
        self.assertIn("rank 2 (Defined)", text)
        self.assertIn("not higher because", text)

    def test_the_four_hypothesis_duties_are_recorded(self):
        self.assertEqual(len(G.HYPOTHESIS_DUTIES), 4)
        joined = " ".join(G.HYPOTHESIS_DUTIES)
        for word in ("formally defined", "computationally implementable", "repeatable", "empirical"):
            self.assertIn(word, joined)


class TestTheGapsMutationFound(unittest.TestCase):
    """Added 2026-11-20 for the public repository: each test kills a mutant that survived the original suite.
    Ground truth is worked by hand in each docstring, not taken from the module."""

    def test_a_hedge_before_the_identity_excuses_it(self):
        """line 102, max(0, start - 110): a reading named before 'is Geburah' must be seen. Moving the window's
        start forward (start + 110) would miss it and flag a sentence the framework allows."""
        self.assertEqual(G.is_ontological("Under the Kabbalistic lens, anger is Geburah."), [])

    def test_a_hedge_after_the_identity_excuses_it(self):
        """line 102, end + 60: the window reaches past the match. Ending it before the match misses this."""
        self.assertEqual(G.is_ontological("Anger is Geburah, on this map."), [])

    def test_an_unhedged_identity_is_still_caught(self):
        """The other side of the two tests above: no hedge anywhere, so the identity is flagged. Also kills
        line 102's `text or ""` becoming `text and ""`, which would read every window as empty."""
        self.assertEqual(G.is_ontological("Anger is Geburah."), ["is Geburah"])
        self.assertEqual(G.is_ontological("Under the Kabbalistic lens, anger is Geburah."), [])

    def test_directive_strength_has_the_value_shannon_gives(self):
        """line 134, (c / total) * log2(c / total): for 'a a b', p = (2/3, 1/3), so
        H = -(2/3 log2 2/3 + 1/3 log2 1/3) = 0.918296 bits; two distinct words give H_max = 1; gamma = 1 - H =
        0.0817 to four places. Worked by hand from Shannon's definition."""
        self.assertEqual(G.gamma("a a b"), 0.0817)
        self.assertEqual(G.gamma("a b"), 0.0)          # all distinct: H = H_max, so no push at all

    def test_a_named_lens_is_kept_and_an_absent_one_is_called_unnamed(self):
        """line 190, lens or "unnamed"."""
        kw = dict(evidence_quality=0.5, pattern_coherence=0.5, alternatives=2,
                  falsifier="If anger is never observed under restriction, this reading is false.")
        self.assertEqual(G.claim("Anger reads as Geburah.", lens="Kabbalistic", **kw)["lens"], "Kabbalistic")
        self.assertEqual(G.claim("Anger reads as Geburah.", **kw)["lens"], "unnamed")

    def test_a_review_with_findings_is_reported_in_words(self):
        """line 234: the report of an unclean review lists every unmet duty."""
        r = G.review("Anger is Geburah.")
        self.assertFalse(r["clean"])
        text = G.report(r)
        self.assertTrue(text.startswith(f"{len(r['findings'])} duty/duties unmet:"), text)
        self.assertIn("provisional proviso", text)
        self.assertIn("-> say it reads as that, under a named lens", text)