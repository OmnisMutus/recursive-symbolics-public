"""The measurement layer (metrics.py).

Ground truth:

1. INDEPENDENT REFERENCE. `tests/fixtures/sephirot_scores.json`, produced by running the framework's own
   reference implementation of the centroid scoring over a set of texts and recording what it returned. The
   module under test did not produce these numbers.
2. BY HAND. The entropy bounds (one token repeated is 0, all distinct is 1000) and the pillar and level
   weightings, which are an average that can be computed on paper for a single scored name.
3. THE STATED LIMITATION. Every address this module builds must say in its own derivation that the measurement
   runs through a Kabbalistic keyword table, because the architecture's claim of a tradition-free address holds
   downstream of here and not inside it. A test asserts the caveat is present, so the honesty cannot be dropped
   by accident.
"""
import json
import os
import unittest

from symbolics import address as A
from symbolics import metrics as M

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "sephirot_scores.json")


def short_word_hits(tokens, centroid):
    """How many tokens matched a centroid word by a 4-letter stem under the reference rule (no length check) but
    not under metrics.py's rule (both words at least 4 letters). Counted here from the fixture's own stated
    formula, not by calling the module: the difference the code is allowed to have, and nothing else."""
    def matched(t, needs_length):
        return any((not needs_length or (len(t) >= 4 and len(w) >= 4)) and (t.startswith(w[:4]) or w.startswith(t[:4]))
                   for w in centroid)
    return sum(1 for t in tokens if matched(t, False) and not matched(t, True))


class TestInheritedScoring(unittest.TestCase):
    def test_agrees_with_the_reference_on_every_text(self):
        """Changed 2026-11-21: metrics.py no longer counts a stem hit for a word shorter than 4 letters (the reference
        let "I" match every centroid word starting with "i"). The reference fixture is kept as it was captured.
        For every text and every name: with no short-word stem hit involved the score equals the reference
        exactly; otherwise it is the reference minus 0.15 for each such hit. A reference already clipped at 1.0
        hides how far above 1.0 it was, so there the score is only bounded."""
        with open(FIXTURE, encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertGreaterEqual(len(data["vectors"]), 20)
        changed = 0
        for v in data["vectors"]:
            got, tokens = M.scores(v["text"]), M.address_tokens(v["text"])
            for name, ref in v["scores"].items():
                k = short_word_hits(tokens, M.SEPHIROT_CENTROIDS[name])
                where = f"{name}: {v['text'][:60]!r}"
                if k == 0:
                    self.assertEqual(got[name], ref, where)
                elif ref < 1.0:
                    changed += 1
                    self.assertEqual(got[name], round(ref - 0.15 * k, 3), where)
                else:
                    changed += 1
                    self.assertTrue(round(ref - 0.15 * k, 3) <= got[name] <= 1.0, where)
        self.assertEqual(changed, 9)          # counted when the rule changed; a different number means it moved

    def test_a_short_word_matches_nothing_by_stem(self):
        """The case that showed the problem: "I" alone used to score Keter, Chokmah and Tifereth 0.15 each."""
        self.assertEqual(sum(M.scores("I").values()), 0)
        self.assertEqual(sum(M.scores("i a an").values()), 0)

    def test_a_four_letter_stem_still_matches(self):
        """'rigidity' shares 'rigi' with Geburah's 'rigid' and is in no centroid, so its score is the stem hit alone."""
        s = M.scores("rigidity")
        self.assertEqual(s["Geburah"], M.STEM_HIT)
        self.assertEqual([n for n, v in s.items() if v], ["Geburah"])

    def test_a_short_centroid_word_counts_exactly_but_not_as_a_stem(self):
        """'cut' is in Geburah's centroid and three letters long: the word itself still scores through the cosine,
        but 'cute' (which starts with it) gets no stem hit from it."""
        self.assertGreater(M.scores("cut")["Geburah"], 0)
        self.assertEqual(M.scores("cute")["Geburah"], 0)

    def test_the_centroids_are_the_frameworks_own(self):
        self.assertEqual(len(M.SEPHIROT_CENTROIDS), 11)              # the ten and Da'ath
        self.assertIn("Daath", M.SEPHIROT_CENTROIDS)
        self.assertIn("abyss", M.SEPHIROT_CENTROIDS["Daath"])
        self.assertIn("cut", M.SEPHIROT_CENTROIDS["Geburah"])

    def test_scores_are_reproducible(self):
        """The reference multiplies by a weight its learning engine accumulates; this does not, so the same text
        always gives the same address rather than one that depends on history nobody can inspect."""
        text = "I cut the practice short, angry and rigid"
        first = M.scores(text)
        second = M.scores(text)
        self.assertEqual(first, second)
        self.assertGreater(first["Geburah"], 0)

    def test_nothing_scored_is_a_real_answer(self):
        self.assertEqual(set(M.scores("")), set(M.SEPHIROT_CENTROIDS))
        self.assertEqual(sum(M.scores("").values()), 0)


class TestEntropy(unittest.TestCase):
    def test_the_bounds_by_hand(self):
        self.assertEqual(M.entropy("om om om om"), 0)                     # one token repeated: nothing new
        self.assertEqual(M.entropy("alpha beta gamma delta"), 1000)       # all distinct: H = H_max
        self.assertEqual(M.entropy("one"), A.MID)                         # nothing to measure
        self.assertEqual(M.entropy(""), A.MID)

    def test_it_is_not_capped_like_the_directivity_budget(self):
        """agency.entropy_gamma clamps at 0.85 because a budget needs a ceiling. An axis must not inherit it."""
        from symbolics import agency
        self.assertEqual(agency.entropy_gamma("om om om om"), agency.GAMMA_MAX)
        self.assertEqual(M.entropy("om om om om"), 0)                     # the same text, uncapped, at the floor

    def test_in_between(self):
        middling = M.entropy("resh at dawn resh at noon resh at sunset")
        self.assertGreater(middling, 0)
        self.assertLess(middling, 1000)


class TestAxes(unittest.TestCase):
    def test_one_scored_name_lands_where_the_tree_puts_it(self):
        only = {"Geburah": 0.5}
        self.assertEqual(M.severity_mercy(only), 150)                     # the pillar of Severity
        self.assertEqual(M.descent(only), A.clamp((5 - 1) / 9 * 1000))    # fifth of ten
        self.assertEqual(M.severity_mercy({"Chesed": 0.5}), 850)          # the pillar of Mercy
        self.assertEqual(M.severity_mercy({"Tifereth": 0.5}), A.MID)      # the middle pillar

    def test_two_opposed_names_average_to_the_middle(self):
        self.assertEqual(M.severity_mercy({"Geburah": 0.5, "Chesed": 0.5}), A.MID)

    def test_nothing_scored_sits_in_the_middle_rather_than_at_zero(self):
        self.assertEqual(M.severity_mercy({}), A.MID)
        self.assertEqual(M.descent({}), A.MID)

    def test_names_that_scored_zero_carry_no_weight(self):
        """Added 2026-11-21 (metrics.py :130 and :139, s > 0): a real score map names every Sephirah, most at 0.
        Zero-scored names are left out, so a text that scores nothing still sits in the middle; counting them
        would divide by a total of zero."""
        nothing = M.scores("zzz qqq")
        self.assertEqual(set(nothing), set(M.SEPHIROT_CENTROIDS))
        self.assertEqual((M.severity_mercy(nothing), M.descent(nothing)), (A.MID, A.MID))
        self.assertEqual(M.descent({"Geburah": 0.5, "Keter": 0.0}), M.descent({"Geburah": 0.5}))


class TestAddressOf(unittest.TestCase):
    def test_a_real_sentence_reads_toward_severity(self):
        a = M.address_of("I cut the practice short, angry and rigid, could not settle at all")
        self.assertLess(a.severity_mercy, A.MID)
        self.assertEqual(sorted(a.derivation), sorted(list(A.AXES)))

    def test_the_derivation_names_what_scored_and_only_that(self):
        """Added 2026-11-21 (metrics.py :149 and :150): the derivation lists the names that scored, and says
        "nothing scored" when none did."""
        scored = M.address_of("stuck").derivation["descent"]
        self.assertIn("Geburah", scored)
        self.assertNotIn("Keter", scored)                                 # scored 0, so not listed
        self.assertNotIn("nothing scored", scored)
        self.assertIn("nothing scored", M.address_of("zzz qqq").derivation["descent"])

    def test_every_derivation_states_the_limitation(self):
        a = M.address_of("expansion and grace, abundance, open and vast")
        for axis in ("severity_mercy", "descent"):
            self.assertIn("tradition-derived", a.derivation[axis], axis)
        self.assertGreater(a.severity_mercy, A.MID)

    def test_the_words_it_rests_on_travel_with_it(self):
        anchor = A.Anchor("journal/2026-01-02.md", "cut the session short", (22, 24))
        a = M.address_of("I cut the practice short", anchors=[anchor])
        self.assertEqual(a.anchors[0].quote, "cut the session short")

    def test_what_it_produces_can_be_read_and_emitted(self):
        from symbolics import ethics as E
        a = M.address_of("rigid and stuck, could not move", anchors=[A.Anchor("x.md", "rigid and stuck")])
        reading = E.emit(A.read(a, "kabbalistic", caveat=E.CAVEAT))
        self.assertEqual(reading["type"], "reading")
        self.assertTrue(reading["anchors"])


class TestLatency(unittest.TestCase):
    def test_the_classes_are_relative_to_the_persons_own_baseline(self):
        self.assertEqual(M.latency(10, baseline=10)["class"], "O(1)")
        self.assertEqual(M.latency(18, baseline=10)["class"], "O(log n)")
        self.assertEqual(M.latency(35, baseline=10)["class"], "O(n)")
        self.assertEqual(M.latency(200, baseline=10)["class"], "O(n^2)")

    def test_each_boundary_belongs_to_the_faster_class(self):
        """Added 2026-11-21 (metrics.py :190, ratio <= 1.2, 2.0, 4.0): a pause exactly at a boundary stays in the
        class below it. 12/10, 20/10 and 40/10 are exact in floating point."""
        self.assertEqual(M.latency(12, baseline=10)["class"], "O(1)")
        self.assertEqual(M.latency(20, baseline=10)["class"], "O(log n)")
        self.assertEqual(M.latency(40, baseline=10)["class"], "O(n)")
        self.assertEqual(M.latency(41, baseline=10)["class"], "O(n^2)")

    def test_the_readings_are_the_ones_the_note_gives(self):
        self.assertEqual(M.latency(10, baseline=10)["reads_as"], "Chesed")
        self.assertEqual(M.latency(200, baseline=10)["reads_as"], "Geburah")

    def test_a_list_uses_its_own_median(self):
        out = M.latency([5, 5, 5, 40])
        self.assertEqual(out["class"], "O(n^2)")
        self.assertEqual(out["ratio"], 8.0)

    def test_absolute_seconds_are_refused(self):
        with self.assertRaises(ValueError):
            M.latency(30)
        with self.assertRaises(ValueError):
            M.latency([])

    def test_the_caveat_travels_with_the_number(self):
        self.assertIn("proxy", M.latency(10, baseline=10)["caveat"])
        self.assertIn("cat on the keyboard", M.latency(10, baseline=10)["caveat"])

    def test_bool_latency_arguments_are_refused(self):
        with self.assertRaises(TypeError):
            M.latency(True, baseline=10)
        with self.assertRaises(TypeError):
            M.latency(10, baseline=True)
        with self.assertRaises(TypeError):
            M.latency([True, 10])


if __name__ == "__main__":
    unittest.main()
