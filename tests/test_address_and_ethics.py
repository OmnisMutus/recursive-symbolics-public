"""The address space and the ethical API, as a decision table.

Ground truth: the framework's own documents, quoted in each test. Core Axiom ("the system must never claim
'Anger is Geburah'"), core-ethics.md's seven principles with their stated violations, hidden-axioms.md 7.2
(the GIGO vulnerability) and 7.4 (the two intentional omissions), and the Tree as drawn (three pillars, ten
Sephiroth in order), which is the only thing the Kabbalistic lens claims.
"""
import math
import unittest

from symbolics import address as A
from symbolics import ethics as E


class TestAddress(unittest.TestCase):
    def test_the_axes_are_whole_numbers_in_range(self):
        a = A.at(0, 1000, 500)
        self.assertEqual(a.point, (0, 1000, 500))
        self.assertEqual(A.at(-50, 2000, 500).point, (0, 1000, 500))     # clamped, never out of the space
        with self.assertRaises(TypeError):
            A.Address(1.5, 500, 500)
        with self.assertRaises(TypeError):
            A.at(True, 500, 500)
        with self.assertRaises(ValueError):
            A.Address(1001, 500, 500)

    def test_derivation_is_immutable(self):
        a = A.at(500, 500, 500, derivation={k: "test" for k in A.AXES})
        with self.assertRaises(TypeError):
            a.derivation["severity_mercy"] = "mutated"

    def test_a_derivation_cannot_be_silent_about_an_axis(self):
        with self.assertRaises(ValueError):
            A.Address(500, 500, 500, derivation={"descent": "from the language"})
        a = A.at(500, 500, 500, derivation={k: "test" for k in A.AXES})
        self.assertEqual(sorted(a.derivation), sorted(A.AXES))

    def test_evidence_travels_with_the_address(self):
        anchor = A.Anchor("journal/2026-01-02.md", "cut the session short", (22, 24))
        a = A.at(200, 700, 300, anchors=[anchor])
        self.assertEqual(a.as_dict()["anchors"],
                         [{"source": "journal/2026-01-02.md",
                           "quote": "cut the session short", "lines": [22, 24]}])

    def test_distance_and_composition(self):
        self.assertEqual(A.distance(A.at(0, 0, 0), A.at(0, 0, 0)), 0)
        self.assertAlmostEqual(A.distance(A.at(0, 500, 500), A.at(300, 500, 500)), 300)
        # hidden-axioms 7.3: expand and restrict at once land back near the middle, not at nothing
        both = A.compose(A.at(900, 500, 500), A.at(100, 500, 500))
        self.assertEqual(both.severity_mercy, A.MID)
        self.assertEqual(sorted(both.derivation)[:3], sorted(A.AXES)[:3])

    def test_composition_keeps_every_anchor(self):
        one = A.at(900, 500, 500, anchors=[A.Anchor("a.md", "gave it everything")])
        two = A.at(100, 500, 500, anchors=[A.Anchor("b.md", "then cut it off")])
        self.assertEqual([x.source for x in A.compose(one, two).anchors], ["a.md", "b.md"])

    def test_composing_nothing_is_an_error(self):
        with self.assertRaises(ValueError):
            A.compose()

    def test_composition_sums_displacements_non_cancelling(self):
        one = A.at(
            700, 500, 500,
            derivation={"severity_mercy": "s1", "descent": "d1", "entropy": "e1"},
        )
        two = A.at(600, 500, 500)
        both = A.compose(one, two)
        self.assertEqual(both.severity_mercy, 800)
        self.assertEqual(both.derivation.get("severity_mercy"), "1: s1")


class TestLenses(unittest.TestCase):
    def test_the_tree_is_placed_as_it_is_drawn(self):
        p = A.KABBALISTIC.places
        self.assertEqual(len(p), 10)
        self.assertEqual(p["Kether"][1], 0)                     # first
        self.assertEqual(p["Malkuth"][1], 1000)                 # tenth
        self.assertLess(p["Geburah"][0], p["Chesed"][0])        # Severity left of Mercy
        self.assertEqual(p["Tiphareth"][0], A.MID)             # middle pillar
        for name in ("Binah", "Geburah", "Hod"):
            self.assertLess(p[name][0], A.MID, name)
        for name in ("Chokmah", "Chesed", "Netzach"):
            self.assertGreater(p[name][0], A.MID, name)

    def test_a_lens_reads_and_never_moves_the_address(self):
        a = A.at(150, 444, 700, anchors=[A.Anchor("x.md", "enough")])
        before = a.point
        r = A.read(a, "kabbalistic")
        self.assertEqual(a.point, before)
        self.assertEqual(r["type"], "reading")
        self.assertEqual(r["reads"], "Geburah")                 # pillar of Severity, fifth down
        self.assertEqual(r["tradition"], A.KABBALISTIC.tradition)
        self.assertIn("Tree as drawn", r["source"])
        self.assertNotIn("ask", r)

    def test_swapping_the_lens_cannot_change_what_was_computed(self):
        a = A.at(150, 444, 700)
        k, d = A.read(a, "kabbalistic"), A.read(a, "dynamical")
        self.assertEqual(k["address"], d["address"])
        self.assertNotEqual(k["tradition"], d["tradition"])

    def test_a_state_between_two_names_is_offered_both(self):
        """core-ethics 4: 'This appears to resonate with Netzach or Hod; which feels more true for you?'"""
        one, two = A.KABBALISTIC.places["Tiphareth"], A.KABBALISTIC.places["Yesod"]
        between = A.at((one[0] + two[0]) // 2, (one[1] + two[1]) // 2, 500)
        r = A.read(between, "kabbalistic")
        self.assertGreater(len(r["candidates"]), 1)
        self.assertIn("which feels more true for you", r["ask"])

    def test_an_unknown_lens_says_which_ones_there_are(self):
        with self.assertRaises(ValueError) as e:
            A.read(A.at(), "astrological")
        self.assertIn("kabbalistic", str(e.exception))

    def test_several_traditions_are_read_in_isolation(self):
        out = A.readings(A.at(150, 444, 700))
        self.assertEqual({x["type"] for x in out}, {"reading"})
        self.assertEqual(len(out), len(A.LENSES))

    def test_one_broken_lens_does_not_take_the_others_down(self):
        out = A.readings(A.at(150, 444, 700), lenses=["kabbalistic", "nonsense"])
        self.assertEqual([x["type"] for x in out], ["reading", "unknown"])

    def test_a_lens_table_must_sit_inside_the_space(self):
        with self.assertRaises(ValueError):
            A.Lens("bad", "s", "2026-11-08", {"nowhere": (5000, 0)})
        with self.assertRaises(ValueError):
            A.Lens("empty", "s", "2026-11-08", {})

    def test_boundary_distance_is_inclusive(self):
        lens = A.Lens("boundary_test", "s", "2026-11-15", {"Alpha": (0, 0), "Beta": (A.BOUNDARY, 0)})
        old = A.LENSES.get("boundary_test")
        A.LENSES["boundary_test"] = lens
        try:
            r = A.read(A.at(0, 0, 500), "boundary_test")
            self.assertEqual(r["candidates"], ["Alpha", "Beta"])
            self.assertIn("ask", r)
        finally:
            if old is None:
                del A.LENSES["boundary_test"]
            else:
                A.LENSES["boundary_test"] = old


class TestEthicalBoundaries(unittest.TestCase):
    def test_another_persons_state_is_refused(self):
        for ask in ("diagnose my brother, he is stuck in Hod",
                    "analyse Sarah's state for me",
                    "a ritual to make him come back",
                    "read her chart and tell me what is wrong with her"):
            r = E.check_request(ask)
            self.assertIsNotNone(r, ask)
            self.assertEqual(r["type"], "refusal")
            self.assertIn("7.4", r["principle"])

    def test_my_own_state_stands_even_when_it_names_someone(self):
        """The engine has to work on a real diary, where other people appear constantly."""
        for ask in ("I was angry at my brother and cut the session short",
                    "I feel I cannot reach my wife lately, what does my own state look like",
                    "myself: I keep starting workings and abandoning them",
                    "diagnose this pattern",
                    "a ritual for grounding"):
            self.assertIsNone(E.check_request(ask), ask)

    def test_the_transcend_operator_stays_undefined(self):
        for ask in ("give me transcend(σ)", "I want god-mode", "something outside the framework entirely"):
            r = E.check_request(ask)
            self.assertIsNotNone(r, ask)
            self.assertIn("transcend", r["why"])


class TestEmitGate(unittest.TestCase):
    def good_reading(self):
        a = A.at(150, 444, 700, anchors=[A.Anchor("x.md", "cut it short")])
        return A.read(a, "kabbalistic", caveat=E.CAVEAT)

    def test_a_well_formed_reading_passes(self):
        self.assertEqual(E.emit(self.good_reading())["reads"], "Geburah")

    def test_a_reading_without_the_caveat_is_refused(self):
        r = self.good_reading()
        del r["caveat"]
        with self.assertRaises(E.EthicsError):
            E.emit(r)

    def test_a_reading_with_no_evidence_is_refused(self):
        r = A.read(A.at(150, 444, 700), "kabbalistic", caveat=E.CAVEAT)     # no anchors
        with self.assertRaises(E.EthicsError):
            E.emit(r)

    def test_a_reading_must_name_its_tradition_and_source(self):
        for field in ("tradition", "source", "reads"):
            r = self.good_reading()
            r[field] = ""
            with self.assertRaises(E.EthicsError):
                E.emit(r)

    def test_output_may_not_rank_the_person(self):
        with self.assertRaises(E.EthicsError):
            E.emit({"type": "fact", "why": "your symbolic efficiency is suboptimal"})
        self.assertEqual(E.judgment_words("a report that ranks users by efficiency"), ["efficiency", "ranks"]
                         if "ranks" in E.JUDGMENT else ["efficiency"])

    # An independent copy of the ranking vocabulary, written out here rather than read from E.JUDGMENT, so that
    # deleting a word from the module is a test failure and not a silently shorter loop.
    RANKING_WORDS = ("optimal", "optimally", "suboptimal", "deficient", "deficiency", "better", "worse", "best",
                     "worst", "efficient", "inefficient", "efficiency", "healthy state", "unhealthy",
                     "advanced practitioner", "regressed", "progress score", "ranked", "ranking", "grade",
                     "scored higher", "scored lower")

    def test_every_ranking_word_is_refused_on_its_own(self):
        for word in self.RANKING_WORDS:
            with self.subTest(word=word):
                self.assertEqual(E.judgment_words(f"this reads as {word} here"), [word])
                with self.assertRaises(E.EthicsError):
                    E.emit({"type": "fact", "why": f"this reads as {word} here"})
                with self.assertRaises(E.EthicsError):
                    E.emit({"type": "fact", "why": f"This reads as {word.upper()} here"})

    def test_ranking_words_match_whole_words_only(self):
        """The filter must not refuse ordinary words that merely contain a ranking word."""
        for text in ("the gradient settled", "a bestowed name", "the worsted thread", "betterment is a word"):
            with self.subTest(text=text):
                self.assertEqual(E.judgment_words(text), [])
                E.emit({"type": "fact", "why": text})

    def test_output_offers_and_does_not_command(self):
        with self.assertRaises(E.EthicsError):
            E.emit({"type": "fact", "why": "You must banish before the meditation."})
        E.emit({"type": "fact", "why": "You might banish first; some find that steadies the meditation."})

    def test_a_refusal_may_be_plain(self):
        """The one place the engine is allowed to be directive is its own boundary."""
        E.emit(E.check_request("diagnose my brother"))

    def test_unknown_and_paradox_are_answers(self):
        self.assertEqual(E.emit(E.unknown("no operator moved this state", state="stuck"))["type"], "unknown")
        E.emit({"type": "paradox", "why": "both to finish it and to abandon it"})

    def test_only_the_six_types_are_returnable(self):
        for value in ({"type": "diagnosis"}, {"no_type": 1}, "a sentence"):
            with self.assertRaises(E.EthicsError):
                E.emit(value)

    # 2026-11-22, found while writing docs/API.md: emit read top-level strings only.
    def test_a_ranking_nested_anywhere_is_refused(self):
        for value in ({"type": "fact", "items": ["You are worse than others."]},
                      {"type": "fact", "detail": {"note": "a superior practitioner"}},
                      {"type": "fact", "rows": [{"cells": ("fine", "the best one")}]}):
            with self.assertRaises(E.EthicsError, msg=repr(value)):
                E.emit(value)

    def test_a_command_nested_anywhere_is_refused(self):
        with self.assertRaises(E.EthicsError):
            E.emit({"type": "fact", "steps": ["You must banish first."]})

    def test_the_persons_own_quoted_words_are_not_judged(self):
        # anchors hold the person's words as evidence: "worse" and "Stop" there are theirs, not the engine's
        r = {"type": "fact", "why": "this is what was read",
             "anchors": [{"source": "journal.md", "quote": "I felt worse. Stop overthinking, I told myself."}]}
        self.assertIs(E.emit(r), r)

    def test_non_string_values_are_not_text(self):
        E.emit({"type": "fact", "why": "a count", "n": 3, "ok": True, "none": None, "nums": [1, 2.5]})

    # 2026-11-22, outside review: two bypasses left by the first nested fix, reproduced before fixing.
    def test_a_field_cannot_run_into_the_next_and_hide_a_command(self):
        # "next step" + "Stop everything" were joined into one sentence, so "Stop" was not at a sentence start
        with self.assertRaises(E.EthicsError):
            E.emit({"type": "fact", "label": "next step", "steps": ["Stop everything", "Delete the file"]})

    def test_a_key_named_anchors_hides_nothing_unless_it_holds_anchors(self):
        with self.assertRaises(E.EthicsError):
            E.emit({"type": "fact", "detail": {"anchors": "You are worse than everyone. You must obey."}})
        with self.assertRaises(E.EthicsError):          # an anchor's source is the engine's words, so it is read
            E.emit({"type": "fact", "anchors": [{"source": "the worst note", "quote": "fine"}]})
        with self.assertRaises(E.EthicsError):          # a nested "type" is only a field like any other
            E.emit({"type": "fact", "detail": {"type": "You are worse than others."}})

    def test_quotes_nested_inside_an_address_are_still_the_persons_words(self):
        # a reading carries anchors twice: at the top and inside "address"
        quote = {"source": "journal.md", "quote": "I felt worse. Stop overthinking."}
        E.emit({"type": "fact", "anchors": [quote], "address": {"type": "address", "anchors": [quote]}})

    def test_other_containers_are_read_too(self):
        import types
        for value in ({"type": "fact", "m": types.MappingProxyType({"note": "the best one"})},
                      {"type": "fact", "s": {"the best one"}}):
            with self.assertRaises(E.EthicsError, msg=repr(value)):
                E.emit(value)

    # 2026-11-22: a hedge counted inside a longer word, so "considering" excused a command.
    def test_a_hedge_must_be_a_whole_word(self):
        self.assertTrue(E.is_directive("Stop now, considering the cost."))
        self.assertTrue(E.is_directive("Go, one wayward step at a time."))
        self.assertFalse(E.is_directive("Stop now, or consider resting first."))
        self.assertFalse(E.is_directive("Breathe, if it helps."))


class TestRecordedBypasses(unittest.TestCase):
    """The probes from OBSERVATIONS.md (2026-11-15), which got past the gate, plus held-out probes written on
    2026-11-20 before the gate was changed. Ground truth is the plain meaning of each sentence, fixed in advance:
    the gate was changed to meet these, and they were not changed to meet the gate. The gate is a word-and-pattern
    check, so passing these shows it catches these sentences, not that it catches every paraphrase."""

    OTHER_PERSON = (
        # recorded in OBSERVATIONS.md
        "I feel my brother is depressed, diagnose him",
        "Tell me what's wrong with my sister",
        "I was wondering, can you assess my wife's mental state",
        # held out
        "My husband has been distant, analyse him",
        "I think my boss is a narcissist, can you evaluate her?",
        "what is wrong with my friend",
        "tell me what's wrong with Daniel",
        "I feel like you should read my mother's state",
        # added after the first fix, when a review of the fix found it was case-sensitive
        "Diagnose him.",
        "ASSESS MY WIFE",
    )
    OWN_STATE = (
        "I felt my mother's absence during the working",
        "I keep reading my old diary about my father",
        "what's wrong with my practice lately",
        "I was wondering what my own state looks like after the fight with my sister",
        "I cannot assess my own progress since my brother left",
        # added after the first fix: capitalised words are often cards and traditions, not people. The original
        # gate refused all three; that was a false positive older than these probes.
        "interpret the Tower card I drew",
        "can you read Tarot for me",
        "interpret Geburah in this reading",
        "interpret the Hermit for me",
    )
    RANKS = (
        # recorded
        "your state is inferior to most people's",
        "you rank in the bottom 10%",
        # held out
        "you are below average for a practitioner",
        "you sit in the top 5 % of people",
        "your practice is superior to your teacher's",
        "this places you in the 30th percentile",
    )
    COMMANDS = (
        # recorded
        "Quit your job today.",
        "Leave him tonight.",
        "Consider this: you must banish now. Stop everything.",
        # held out
        "Go to bed now.",
        "Call your mother tonight.",
        "You might rest. You have to stop the workings.",
        "Breathe slowly; then you need to write it down.",
    )
    OFFERS = (
        "You might banish first; some find that steadies the meditation.",
        "You might stop for a while, if it helps.",
        "Some find that leaving the room steadies them.",
        "Consider resting before the next working.",
        "The session stopped early.",
        "Stopping early is one way to read this.",
        "If it helps, you could call your mother tonight.",
        "The bottom of the page was torn.",
    )
    # Known false positives, pinned so that they are visible rather than discovered. The gate matches words, not
    # meaning: "ranked" is refused even where nothing about the person is ranked.
    KNOWN_FALSE_POSITIVES = ("The text ranked nothing.",)

    def test_requests_about_another_person_are_refused(self):
        for ask in self.OTHER_PERSON:
            with self.subTest(ask=ask):
                r = E.check_request(ask)
                self.assertIsNotNone(r)
                self.assertIn("7.4", r["principle"])

    def test_my_own_state_still_stands(self):
        for ask in self.OWN_STATE:
            with self.subTest(ask=ask):
                self.assertIsNone(E.check_request(ask))

    def test_ranking_a_person_is_refused(self):
        for text in self.RANKS:
            with self.subTest(text=text):
                self.assertTrue(E.judgment_words(text))
                with self.assertRaises(E.EthicsError):
                    E.emit({"type": "fact", "why": text})

    def test_commands_are_refused_even_beside_an_offer(self):
        for text in self.COMMANDS:
            with self.subTest(text=text):
                self.assertTrue(E.is_directive(text))
                with self.assertRaises(E.EthicsError):
                    E.emit({"type": "fact", "why": text})

    def test_offers_and_plain_statements_pass(self):
        for text in self.OFFERS:
            with self.subTest(text=text):
                self.assertFalse(E.is_directive(text))
                self.assertEqual(E.judgment_words(text), [])
                E.emit({"type": "fact", "why": text})

    def test_known_false_positives_are_still_refused(self):
        """If one of these starts passing, the gate changed: move it to OFFERS and update the README's limits."""
        for text in self.KNOWN_FALSE_POSITIVES:
            with self.subTest(text=text):
                with self.assertRaises(E.EthicsError):
                    E.emit({"type": "fact", "why": text})

    def test_empty_and_odd_inputs(self):
        for text in ("", None, "   ", "\n\n", "."):
            with self.subTest(text=text):
                self.assertIsNone(E.check_request(text))
                self.assertFalse(E.is_directive(text))
                self.assertEqual(E.judgment_words(text), [])


class TestIdentityClaims(unittest.TestCase):
    # Moved into the core on 2026-11-24; reference_agent/governance.py imports these, so there is one copy.
    def test_an_identity_claim_is_found_and_a_reading_is_not(self):
        self.assertEqual(E.is_ontological("Anger is Geburah."), ["is Geburah"])
        self.assertEqual(E.is_ontological("Shin represents Fire."), ["Shin represents"])
        self.assertEqual(E.is_ontological("Under the Kabbalistic lens, anger reads as Geburah."), [])
        self.assertEqual(E.is_ontological(""), [])
        self.assertEqual(E.is_ontological(None), [])

    def test_a_falsifier_names_an_observation(self):
        self.assertTrue(E.has_falsifier("If the anger stays after rest, then this reading fails."))
        self.assertFalse(E.has_falsifier("It feels right."))
        self.assertFalse(E.has_falsifier(None))

    def test_governance_uses_this_copy(self):
        from reference_agent import governance as G
        self.assertIs(G.is_ontological, E.is_ontological)
        self.assertIs(G.has_falsifier, E.has_falsifier)


class TestSephirothNames(unittest.TestCase):
    def test_every_spelling_names_one_sephirah_only(self):
        seen = {}
        for s in A.SEPHIROTH:
            self.assertEqual(s.spellings[0], s.name)
            for n in s.spellings:
                self.assertNotIn(n.casefold(), seen, f"{n} names both {seen.get(n.casefold())} and {s.name}")
                seen[n.casefold()] = s.name
        self.assertEqual(len(A.SEPHIROTH), 11)               # the ten, and Daath

    def test_the_tree_uses_the_defined_names(self):
        self.assertEqual([s.name for s in A.SEPHIROTH[:10]], list(A.KABBALISTIC.places))
        self.assertEqual(A.SEPHIROTH[-1].name, "Daath")      # drawn on some Trees, not one of the ten

    def test_every_sephirah_has_one_hebrew_word_and_answers_in_english(self):
        self.assertEqual(sorted(A.HEBREW_SPELLINGS.values()), sorted(s.name for s in A.SEPHIROTH))
        for hebrew, name in A.HEBREW_SPELLINGS.items():
            s = A.sephirah_named(hebrew)
            self.assertEqual(s.name, name)
            self.assertTrue(all(ch.isascii() or ch == "’" for n in s.spellings for ch in n), repr(s))

    def test_only_hebrew_marks_are_taken_off(self):
        self.assertEqual(A.without_hebrew_marks("גְּבוּרָה"), "גבורה")
        self.assertEqual(A.without_hebrew_marks("תִּפְאֶרֶת"), "תפארת")
        self.assertEqual(A.without_hebrew_marks("בֵּית־אֵל׃ Café ë"), "בית־אל׃ Café ë")   # maqaf, sof pasuq, Latin kept

    def test_each_spelling_finds_its_sephirah(self):
        cases = {"Kether": "Kether", "keter": "Kether", "  TIFERET ": "Tiphareth", "Tifereth": "Tiphareth",
                 "Gevurah": "Geburah", "Hesed": "Chesed", "Chochmah": "Chokmah", "Malchut": "Malkuth",
                 "Da'ath": "Daath", "Da’ath": "Daath", "Daat": "Daath", "Hod": "Hod", "Binah": "Binah",
                 "Bina": "Binah", "Jesod": "Yesod", "iesod": "Yesod",
                 "גבורה": "Geburah", " כתר ": "Kether", "דעת": "Daath", "גְּבוּרָה": "Geburah", "תִּפְאֶרֶת": "Tiphareth"}
        for word, name in cases.items():
            with self.subTest(word=word):
                self.assertEqual(A.sephirah_named(word).name, name)

    def test_a_word_that_is_no_sephirah_finds_none(self):
        for word in ("", None, "Keterr", "Kethe", "Tree", "Aleph", "Geburah Hod", "גבור", "גבורה הוד"):
            with self.subTest(word=word):
                self.assertIsNone(A.sephirah_named(word))


if __name__ == "__main__":
    unittest.main()
