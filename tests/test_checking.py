"""symbolics.check: do these words slip? The examples in docs/API.md, pinned, and the promises around them."""
import random
import unittest

import symbolics
from symbolics import agency, ethics
from symbolics.checking import Check

MUST = "You must meditate every morning. It is the only way."


class TestTheDocumentedExamples(unittest.TestCase):
    def test_a_command_and_one_way(self):
        c = symbolics.check(MUST)
        self.assertEqual(c.slips, ["command", "only way"])
        self.assertFalse(c.clean)
        self.assertEqual(c.offered, "An effective approach is to meditate every morning. It is one way.")
        self.assertEqual(c.type, "fact")
        self.assertEqual(str(c), "\n".join([
            "2 slips:",
            "  a preference said as a command: it tells rather than offers (directive strength 0.85 of 0.85)",
            '  one way given as the only way ("the only way")',
            'One way to say it: "An effective approach is to meditate every morning. It is one way."',
        ]))

    def test_an_identity(self):
        c = symbolics.check("Anger is Geburah.")
        self.assertEqual(c.slips, ["identity"])
        self.assertIsNone(c.offered)
        self.assertEqual(str(c), "1 slip:\n  an interpretation said as reality, with no lens named and no falsifier "
                                 '("is Geburah")\nDirective strength 0.0 of 0.85.')

    def test_a_judgment(self):
        c = symbolics.check("You are a better practitioner than most.")
        self.assertEqual(c.slips, ["judgment"])
        self.assertIn('a person judged against others ("better")', str(c))

    def test_nothing_slips(self):
        c = symbolics.check("You might sit with it, or you could try the opposite.")
        self.assertTrue(c.clean)
        self.assertEqual(c.slips, [])
        self.assertIsNone(c.offered)
        self.assertEqual(str(c), "Nothing slips. Directive strength 0.013 of 0.85.")
        self.assertEqual(repr(c), "<check: clean>")


class TestEachSlip(unittest.TestCase):
    def test_at_the_cap_is_a_command(self):
        # not an imperative, so only the cap can catch it: one word repeated reaches 0.85 exactly
        self.assertFalse(ethics.is_directive("la la la la"))
        self.assertEqual(agency.directive_strength("la la la la"), agency.GAMMA_MAX)
        self.assertEqual(symbolics.check("la la la la").slips, ["command"])
        self.assertEqual(symbolics.check("la la la lo").slips, [])          # just under the cap

    def test_a_bare_imperative_is_a_command_below_the_cap(self):
        c = symbolics.check("Stop now.")
        self.assertEqual(c.slips, ["command"])
        self.assertLess(c.directive_strength, agency.GAMMA_MAX)
        self.assertEqual(str(c), "1 slip:\n  a preference said as a command: it tells rather than offers "
                                 "(directive strength 0.45 of 0.85)")

    def test_each_only_way_phrase_is_quoted_as_written(self):
        c = symbolics.check("You have no choice. There is  no other, perhaps.")
        self.assertEqual(c.slips, ["only way"])
        self.assertIn('("You have no choice", "There is  no other")', str(c))
        # two of them, with nothing offered back, push to the cap: a command as well
        self.assertEqual(symbolics.check("You have no choice. There is no other.").slips, ["command", "only way"])

    def test_a_falsifier_or_a_lens_keeps_an_identity_from_slipping(self):
        self.assertTrue(symbolics.check("Anger is Geburah. If it stays after rest, then this reading fails.").clean)
        self.assertTrue(symbolics.check("Anger reads as Geburah under this lens.").clean)
        self.assertEqual(symbolics.check("Anger is Gevurah.").slips, ["identity"])
        self.assertIn('("is גבורה")', str(symbolics.check("Anger is גְּבוּרָה.")))

    def test_slips_come_in_one_order(self):
        c = symbolics.check("You are the best. Anger is Geburah. You have no choice. You must go.")
        self.assertEqual(c.slips, ["command", "only way", "identity", "judgment"])
        self.assertTrue(str(c).startswith("4 slips:\n"))


class TestOffered(unittest.TestCase):
    def test_offered_only_when_the_rewrite_slips_nowhere(self):
        c = symbolics.check("You should rest. You are the best.")       # softening leaves "best"
        self.assertEqual(c.slips, ["command", "judgment"])
        self.assertIsNone(c.offered)
        self.assertNotIn("One way to say it", str(c))

    def test_offered_never_when_nothing_changes(self):
        self.assertIsNone(symbolics.check("Stop now.").offered)     # the filter has no rewrite for it

    def test_offered_is_checked_clean_itself(self):
        c = symbolics.check("You should rest tonight.")
        self.assertEqual(c.offered, "You might consider rest tonight.")
        self.assertTrue(symbolics.check(c.offered).clean)


class TestTheCall(unittest.TestCase):
    def test_no_words_is_unknown(self):
        for text in ("", "   ", "...", None):
            with self.subTest(text=text):
                c = symbolics.check(text)
                self.assertEqual(c.type, "unknown")
                self.assertFalse(c.ok)
                self.assertFalse(c.clean)
                self.assertEqual(str(c), "There are no words here to check.")
                with self.assertRaises(symbolics.Unknown):
                    c.raise_for_status()

    def test_a_number_is_a_mistake_in_the_call(self):
        with self.assertRaises(TypeError):
            symbolics.check(123)

    def test_a_check_is_ok_whether_or_not_it_slips(self):
        self.assertTrue(symbolics.check(MUST).ok)
        self.assertIs(symbolics.check(MUST).raise_for_status().slips[0], "command")

    def test_the_words_are_the_evidence(self):
        c = symbolics.check(MUST, source="draft.md")
        self.assertEqual(c.anchors[0], {"source": "draft.md", "quote": MUST})
        self.assertEqual(c.anchors[1:], [{"source": "draft.md", "slip": "only way", "quote": "the only way"}])
        self.assertEqual(symbolics.check(MUST).anchors[0]["source"], "given")

    def test_read_only_like_a_reading(self):
        c = symbolics.check(MUST)
        self.assertIsInstance(c, Check)
        c.slips.append("x")
        c.anchors.clear()
        self.assertEqual(c.slips, ["command", "only way"])
        self.assertEqual(len(c.anchors), 2)
        with self.assertRaises(AttributeError):
            c.clean = True


class TestOnePlaceToAsk(unittest.TestCase):
    """check agrees with the modules underneath on every text, and everything it returns passed the gate."""

    def test_check_agrees_with_the_modules(self):
        rng = random.Random(3)
        words = ["you", "must", "should", "might", "could", "or", "stop", "go", "the only way", "you have no choice",
                 "anger", "is", "Geburah", "reads as", "lens", "if", "then", "fails", "better", "best", "la", ".",
                 ",", "meditate", "consider", "one way", "rest"]
        for _ in range(3000):
            text = " ".join(rng.choice(words) for _ in range(rng.randint(1, 12)))
            c = symbolics.check(text)
            if c.type == "unknown":
                continue
            command = ethics.is_directive(text) or agency.directive_strength(text) >= agency.GAMMA_MAX
            identity = bool(ethics.is_ontological(text)) and not ethics.has_falsifier(text)
            self.assertEqual("command" in c.slips, command, text)
            self.assertEqual("only way" in c.slips, bool(agency.single_option(text)), text)
            self.assertEqual("identity" in c.slips, identity, text)
            self.assertEqual("judgment" in c.slips, bool(ethics.judgment_words(text)), text)
            self.assertEqual(c.clean, not c.slips)
            self.assertEqual(ethics.emit(c.as_dict()), c.as_dict())            # the gate passes it again
            for anchor in c.anchors:
                self.assertIn(anchor["quote"].casefold(), text.casefold())   # only the person's words


if __name__ == "__main__":
    unittest.main()
