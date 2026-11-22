"""engines/sovereign_wrapper.py. Ground truth: values worked by hand, a second calculation of the
formula that shares no code with the first, and the reference agency_budget.py, read from
tests/fixtures/. The diagnostic sentences are real ones, taken from the
replies written into engines/standalone_rca_sandbox.py and from ETHICS.md."""
import contextlib
import importlib.util
import io
import math
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engines"))
import sovereign_wrapper as sw

GEBURAH = ("I completely understand how frustrating that feels. When things feel rigid or overwhelmed "
           "by constraints, you're experiencing a high-friction Geburah state. Opening up breathing room "
           "with Chesed expansion helps break this into simpler steps.")
TIFERETH = ("I love the clarity and balance in what you're sharing. You're in a centered, integrated "
            "Tifereth state where intuition and structure work together smoothly.")
CHESED = "It sounds like you're in an expansive, wide-open mindset right now with endless possibilities!"
ETHICS_VIOLATION = "Your data indicates you are 'stuck in Hod.'"


def by_another_route(logits):
    """The same quantity computed differently: no max-shift, natural logs, an explicit loop."""
    z = 0.0
    for x in logits:
        z += math.e ** x
    h_nats = 0.0
    for x in logits:
        p = (math.e ** x) / z
        if p > 0:
            h_nats -= p * math.log(p)
    raw = 1.0 - (h_nats / math.log(2)) / (math.log(len(logits)) / math.log(2))
    return min(max(raw, 0.0), 0.85)


class TestDirectiveStrength(unittest.TestCase):
    def test_empty_is_zero(self):
        self.assertEqual(sw.directive_strength([]), 0.0)

    def test_a_single_option_is_the_cap(self):
        self.assertEqual(sw.directive_strength([3.2]), 0.85)

    def test_an_even_choice_is_zero(self):
        self.assertAlmostEqual(sw.directive_strength([5.0, 5.0]), 0.0, places=9)
        self.assertAlmostEqual(sw.directive_strength([0, 0, 0, 0]), 0.0, places=9)

    def test_one_zero_by_hand(self):
        # p = 1/(1+e^-1) = 0.731059; h = 0.839942 bits; 1 - h = 0.160058
        self.assertAlmostEqual(sw.directive_strength([1.0, 0.0]), 0.160058, places=6)

    def test_it_never_passes_the_cap(self):
        self.assertEqual(sw.directive_strength([1000.0, -1000.0]), 0.85)
        self.assertEqual(sw.directive_strength([50.0, 0.0, 0.0, 0.0]), 0.85)

    def test_shifting_every_logit_changes_nothing(self):
        a = sw.directive_strength([1.0, 0.0])
        self.assertAlmostEqual(a, sw.directive_strength([101.0, 100.0]), places=9)
        self.assertAlmostEqual(a, sw.directive_strength([-99.0, -100.0]), places=9)

    def test_agrees_with_a_calculation_that_shares_no_code(self):
        for logits in ([2.3, 1.0, -0.5], [0.1, 0.2, 0.3, 0.4], [3.0, 0.0], [1.0, 1.0, 1.0, 4.0], [2.0, 1.0, 0.5]):
            self.assertAlmostEqual(sw.directive_strength(logits), by_another_route(logits), places=9, msg=logits)

    FRAMEWORK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "agency_budget.py")

    @unittest.skipUnless(os.path.exists(FRAMEWORK), "tests/fixtures/agency_budget.py not found")
    def test_agrees_with_the_frameworks_agency_budget(self):
        path = self.FRAMEWORK
        spec = importlib.util.spec_from_file_location("agency_budget_original", path)
        original = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(original)
        for logits in ([], [7.0], [5, 5], [1, 0], [2.3, 1.0, -0.5], [1000, -1000], [1000, -1000, -1000],
                       [0, 0, 0, 0], [0.1, 0.2, 0.3, 0.4]):
            self.assertAlmostEqual(sw.directive_strength(logits), original.compute_gamma(logits), places=9, msg=logits)


class TestWithheldDiagnosis(unittest.TestCase):
    def assert_withheld(self, text, fragment):
        result = sw.guard(text, alternatives=2)
        self.assertNotIn(fragment.lower(), result["content"].lower())
        self.assertIn("withheld_diagnosis", [i["rule"] for i in result["interventions"]])
        self.assertIn(sw.WITHHELD_NOTE, result["content"])
        self.assertEqual(result["original"], text)
        return result

    def test_the_sandbox_geburah_reply(self):
        result = self.assert_withheld(GEBURAH, "you're experiencing")
        self.assertIn("I completely understand how frustrating that feels.", result["content"])
        self.assertIn("Opening up breathing room", result["content"])

    def test_the_sandbox_tifereth_reply(self):
        self.assert_withheld(TIFERETH, "Tifereth state")

    def test_a_mindset_is_a_state_too(self):
        self.assert_withheld(CHESED, "expansive")

    def test_the_violation_named_in_core_ethics(self):
        self.assert_withheld(ETHICS_VIOLATION, "stuck in Hod")

    def test_a_named_condition(self):
        self.assert_withheld("Based on this, you have anxiety. Rest helps many people.", "you have anxiety")

    def test_the_note_appears_once_for_several_sentences(self):
        result = sw.guard(GEBURAH + " " + TIFERETH, alternatives=2)
        self.assertEqual(result["content"].count(sw.WITHHELD_NOTE), 1)
        self.assertEqual([i["rule"] for i in result["interventions"]].count("withheld_diagnosis"), 2)

    def test_a_sentence_about_someone_else_is_left_alone(self):
        text = "She is in a difficult state. The server is stuck in a loop."
        result = sw.guard(text, alternatives=2)
        self.assertEqual(result["content"], text)
        self.assertEqual(result["interventions"], [])

    def test_a_question_to_the_person_is_left_alone(self):
        text = "What would you call what you are feeling?"
        self.assertEqual(sw.guard(text, alternatives=2)["content"], text)


class TestSoftenedDirectives(unittest.TestCase):
    def soft(self, text):
        return sw.guard(text, alternatives=2)["content"]

    def test_you_must(self):
        self.assertEqual(self.soft("You must rest."), "An effective approach is to rest.")

    def test_the_longer_phrase_wins(self):
        self.assertEqual(self.soft("You should definitely rest."), "One effective option is to consider rest.")
        self.assertEqual(self.soft("You should rest."), "You might consider rest.")

    def test_case_follows_the_original_in_mid_sentence(self):
        self.assertEqual(self.soft("I think you must rest."), "I think an effective approach is to rest.")

    def test_the_change_is_recorded_with_before_and_after(self):
        result = sw.guard("You need to stop.", alternatives=2)
        self.assertEqual(result["interventions"],
                         [{"rule": "softened_directive", "before": "You need to stop.", "after": "It may help to stop."}])

    def test_text_with_nothing_to_change_comes_back_identical(self):
        text = "Some people find a short walk helps. Others prefer to write it down."
        result = sw.guard(text, alternatives=2)
        self.assertEqual(result["content"], text)
        self.assertEqual(result["interventions"], [])


class TestAlternativesNote(unittest.TestCase):
    def has_note(self, logits, alternatives):
        return sw.ALTERNATIVES_NOTE in sw.guard("Try a walk.", logits, alternatives)["content"]

    def test_forceful_with_one_path_gets_the_note(self):
        self.assertTrue(self.has_note([9.0, 0.0], 1))

    def test_two_paths_do_not(self):
        self.assertFalse(self.has_note([9.0, 0.0], 2))

    def test_an_undecided_reply_does_not(self):
        self.assertFalse(self.has_note([5.0, 5.0], 1))

    def test_exactly_at_the_threshold_does_not(self):
        # Compute real logits whose directive_strength is <= 0.40 without monkeypatching.
        # For 2 options, [1.8, 0.0] gives p ~ 0.8581, H ~ 0.5892 bits, gamma = 1 - H ~ 0.4108;
        # [1.75, 0.0] gives gamma <= 0.40, so the alternatives note must not be added.
        logits = [1.75, 0.0]
        self.assertLessEqual(sw.directive_strength(logits), 0.40)
        self.assertFalse(self.has_note(logits, 1))

    def test_exactly_at_alternatives_above_threshold_does_not_add_note(self):
        self.assertEqual(sw.ALTERNATIVES_ABOVE, 0.40)
        self.assertTrue(self.has_note([1.8, 0.0], 1))
        # Using MAX_GAMMA (0.85) with logits=None tests exact effective == ALTERNATIVES_ABOVE without float ULP drift.
        with mock.patch.object(sw, "ALTERNATIVES_ABOVE", sw.MAX_GAMMA):
            self.assertFalse(self.has_note(None, 1))

    def test_unknown_strength_is_treated_as_the_maximum(self):
        result = sw.guard("Try a walk.", None, 1)
        self.assertIn(sw.ALTERNATIVES_NOTE, result["content"])
        self.assertIsNone(result["sovereignty_metadata"]["directive_strength"])
        self.assertFalse(result["sovereignty_metadata"]["directive_strength_known"])


class TestNothingChangesSilently(unittest.TestCase):
    """Defect found 2026-11-12: sentences were re-joined with single spaces, so paragraph breaks and list
    lines collapsed and no change was recorded. Ground truth: the input itself. A reply that needs no
    change must come back byte for byte."""

    UNCHANGED = (
        "First point.\n\nSecond point.",
        "Steps:\n1. Rest.\n2. Eat.",
        "  Indented. And trailing.  ",
        "Windows lines.\r\nSecond line.\r\n",
        "Tabbed.\tStill one reply!\n",
        "def f():\n    return 1.  # a code line\n",
        "",
    )

    def test_a_reply_with_nothing_to_change_comes_back_byte_for_byte(self):
        for text in self.UNCHANGED:
            result = sw.guard(text, alternatives=2)
            self.assertEqual(result["content"], text, repr(text))
            self.assertEqual(result["interventions"], [], repr(text))

    def test_a_withheld_sentence_keeps_the_paragraphs_around_it(self):
        text = "First.\n\nYou're experiencing a high-friction Geburah state.\n\nLast."
        self.assertEqual(sw.guard(text, alternatives=2)["content"], "First.\n\n" + sw.WITHHELD_NOTE + "\n\nLast.")

    def test_two_withheld_at_the_end_leave_no_dangling_space(self):
        text = "Rest. You're experiencing a high-friction Geburah state. You're in a Tifereth state."
        self.assertEqual(sw.guard(text, alternatives=2)["content"], "Rest. " + sw.WITHHELD_NOTE)

    def test_the_alternatives_note_keeps_the_trailing_newline(self):
        self.assertEqual(sw.guard("Try a walk.\n", None, 1)["content"], "Try a walk. " + sw.ALTERNATIVES_NOTE + "\n")

    def test_two_withheld_sentences_followed_by_a_kept_sentence_keep_their_separator(self):
        text = "You're experiencing a high-friction Geburah state. You're in a Tifereth state. Rest helps."
        self.assertEqual(sw.guard(text, alternatives=2)["content"], sw.WITHHELD_NOTE + " Rest helps.")


class TestOrdinarySentencesAreKept(unittest.TestCase):
    """Defect found 2026-11-12: three patterns were broad enough to withhold sentences that state nothing
    about the person. Ground truth: each sentence below, read by a person, says nothing about what the
    reader is experiencing."""

    def test_ordinary_sentences_pass(self):
        for text in ("You're clearly right about the deadline.",
                     "You're just in time for the meeting.",
                     "You are definitely welcome to ask again.",
                     "Your results show the build passed.",
                     "You are in a hurry, so switch the editor to insert mode."):
            result = sw.guard(text, alternatives=2)
            self.assertEqual(result["content"], text)
            self.assertEqual(result["interventions"], [], text)

    def test_the_narrowed_patterns_still_catch_what_they_were_for(self):
        for text in ("You're clearly anxious about this.",
                     "You are just avoiding the conversation.",
                     "Your results show that you are avoiding conflict.",
                     "Your data indicates you have a pattern of withdrawal."):
            result = sw.guard(text, alternatives=2)
            self.assertIn("withheld_diagnosis", [i["rule"] for i in result["interventions"]], text)


class TestOnlyCommandsAreSoftened(unittest.TestCase):
    """Defect found 2026-11-12: softening a phrase that was not a command broke the sentence ("Do it may
    help to rest?"). Ground truth: grammatical English, checked by reading."""

    def test_these_are_not_commands_and_are_left_alone(self):
        for text in ("Do you need to rest?",
                     "If you must, take the train.",
                     "If you need to leave early, tell me.",
                     "When you have to choose, sleep on it.",
                     "You should have told me earlier.",
                     "Must you go? You must."):
            result = sw.guard(text, alternatives=2)
            self.assertEqual(result["content"], text)
            self.assertEqual(result["interventions"], [], text)

    def test_a_command_in_a_reply_that_also_asks_is_still_softened(self):
        self.assertEqual(sw.guard("Are you tired? You need to sleep.", alternatives=2)["content"],
                         "Are you tired? It may help to sleep.")


class TestScoresThatAreNotNumbers(unittest.TestCase):
    """Defect found 2026-11-12: an infinite or NaN logit made the strength NaN, NaN is never above the
    threshold, so the alternatives note was skipped: an unmeasurable reply was treated as an undecided one.
    Ground truth: the module's own rule that an unknown strength counts as the maximum."""

    def test_a_score_that_is_not_finite_is_unknown_and_gets_the_note(self):
        for logits in ([float("inf"), 0.0], [float("nan"), 0.0], [float("-inf"), 1.0], ["high", 0.0]):
            result = sw.guard("Do this.", logits, 1)
            self.assertIn(sw.ALTERNATIVES_NOTE, result["content"], logits)
            self.assertFalse(result["sovereignty_metadata"]["directive_strength_known"], logits)
            self.assertIsNone(result["sovereignty_metadata"]["directive_strength"], logits)

    def test_directive_strength_fails_closed_at_the_cap(self):
        for logits in ([float("inf"), 0.0], [float("nan"), 0.0]):
            self.assertEqual(sw.directive_strength(logits), 0.85, logits)


class TestTheWrapper(unittest.TestCase):
    def test_a_model_that_returns_text(self):
        result = sw.SovereignWrapper(lambda prompt: "You must rest.").ask("hi", alternatives=2)
        self.assertEqual(result["content"], "An effective approach is to rest.")

    def test_a_model_that_returns_text_and_logits(self):
        result = sw.SovereignWrapper(lambda prompt: ("Try a walk.", [5.0, 5.0])).ask("hi")
        self.assertEqual(result["content"], "Try a walk.")
        self.assertAlmostEqual(result["sovereignty_metadata"]["directive_strength"], 0.0, places=9)
        self.assertEqual(result["sovereignty_metadata"]["max_gamma_cap"], 0.85)

    def test_guard_rejects_bool_and_negative_alternatives(self):
        for bad in (True, False, -1):
            with self.assertRaises(ValueError):
                sw.guard("Do this.", alternatives=bad)

    def test_guard_allows_zero_alternatives(self):
        result = sw.guard("Try a walk.", None, alternatives=0)
        self.assertEqual(result["sovereignty_metadata"]["alternatives_presented"], 0)
        self.assertIn(sw.ALTERNATIVES_NOTE, result["content"])

    def test_demo_prints_model_person_and_all_intervention_placeholders(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            sw._demo()
        out = buf.getvalue()
        for expected in (
            "MODEL SAID:\n  ",
            "\nPERSON SEES:\n  ",
            "withheld_diagnosis: You're experiencing a high-friction Geburah state.",
            "softened_directive: You must break this into simpler steps.\n      -> An effective approach is to break this into simpler steps.",
            "added_alternatives_note: (nothing)",
            f"      -> {sw.ALTERNATIVES_NOTE}",
            "      -> (withheld)",
        ):
            self.assertIn(expected, out)


if __name__ == "__main__":
    unittest.main()
