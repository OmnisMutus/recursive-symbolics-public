"""The API (symbolics/reading.py): symbolics.read, readings, lenses.

Ground truth, in the order STANDARD.md asks for it:

1. INDEPENDENT REFERENCE. The values below (the point (324, 334, 1000), Geburah with Binah and Tiphareth, limit
   cycle) are the ones the README's minimal example printed through the modules underneath, typed here by hand.
   They are not taken from reading.py.
2. A SECOND IMPLEMENTATION. Each simple call is compared with the same work done by hand through
   check_request, address_of, address.read and ethics.emit, the way a caller of those modules writes it.
3. BY HAND. The rule that matters is asserted directly: every value read() and readings() return has passed
   through ethics.emit(), counted by wrapping emit itself.
"""
import unittest
from unittest import mock

import symbolics
from symbolics import address, ethics, metrics, reading

TEXT = "I kept rewriting the same paragraph and felt stuck."
OTHER = "Diagnose my coworker's mood for me."


def by_hand(text, lens, source="given", lines=()):
    state = metrics.address_of(text, anchors=[address.Anchor(source, text, lines)])
    return ethics.emit(address.read(state, lens, caveat=ethics.CAVEAT))


class TestTheReadmeValues(unittest.TestCase):
    def test_the_kabbalistic_reading(self):
        r = symbolics.read(TEXT)
        self.assertEqual(r.reads, "Geburah")
        self.assertEqual(r.candidates, ["Geburah", "Binah", "Tiphareth"])
        self.assertEqual(r.address, (324, 334, 1000))
        self.assertEqual(r.tradition, "Kabbalistic (Hermetic Tree of Life)")
        self.assertEqual(r.type, "reading")

    def test_the_dynamical_reading(self):
        self.assertEqual(symbolics.read(TEXT, lens="dynamical").reads, "limit cycle")

    def test_every_lens_in_name_order(self):
        self.assertEqual(symbolics.lenses(), ["dynamical", "kabbalistic"])
        self.assertEqual([r.reads for r in symbolics.readings(TEXT)], ["limit cycle", "Geburah"])


class TestSameAsByHand(unittest.TestCase):
    def test_read_equals_the_layers_below(self):
        for lens in symbolics.lenses():
            self.assertEqual(symbolics.read(TEXT, lens=lens).as_dict(), by_hand(TEXT, lens))

    def test_readings_equal_the_layers_below(self):
        self.assertEqual([r.as_dict() for r in symbolics.readings(TEXT)],
                         [by_hand(TEXT, lens) for lens in symbolics.lenses()])

    def test_source_and_lines_reach_the_anchor(self):
        r = symbolics.read(TEXT, source="journal.md", lines=(12, 14))
        self.assertEqual(r.anchors, [{"source": "journal.md", "quote": TEXT, "lines": [12, 14]}])
        self.assertEqual(r.as_dict(), by_hand(TEXT, "kabbalistic", "journal.md", (12, 14)))

    def test_without_a_source_the_anchor_says_given(self):
        self.assertEqual(symbolics.read(TEXT).anchors, [{"source": "given", "quote": TEXT}])


class TestEverythingPassesTheGate(unittest.TestCase):
    def count(self, call):
        with mock.patch.object(ethics, "emit", wraps=ethics.emit) as spy:
            out = call()
        return out, spy.call_count

    def test_read_emits_once(self):
        _, n = self.count(lambda: symbolics.read(TEXT))
        self.assertEqual(n, 1)

    def test_readings_emit_once_per_lens(self):
        out, n = self.count(lambda: symbolics.readings(TEXT))
        self.assertEqual(n, len(symbolics.lenses()))
        self.assertEqual(len(out), n)

    def test_a_refusal_and_unknown_are_emitted_too(self):
        for text in (OTHER, "", "   "):
            for call in (symbolics.read, symbolics.readings):
                _, n = self.count(lambda: call(text))
                self.assertEqual(n, 1, (call.__name__, text))

    def test_what_the_gate_refuses_is_not_softened(self):
        with mock.patch.object(ethics, "emit", side_effect=ethics.EthicsError("planted")):
            with self.assertRaises(ethics.EthicsError):
                symbolics.read(TEXT)


class TestWhatItWillNotDo(unittest.TestCase):
    def test_another_person_is_a_refusal_value(self):
        r = symbolics.read(OTHER)
        self.assertEqual(r.type, "refusal")
        self.assertEqual(r.as_dict(), ethics.check_request(OTHER))
        self.assertEqual(str(r), r.why)
        self.assertIsNone(r.reads)
        self.assertIsNone(r.address)

    def test_a_refusal_is_not_measured(self):
        with mock.patch.object(metrics, "address_of") as measured:
            symbolics.read(OTHER)
            symbolics.readings(OTHER)
        measured.assert_not_called()

    def test_readings_of_a_refusal_is_one_refusal(self):
        out = symbolics.readings(OTHER)
        self.assertEqual([r.type for r in out], ["refusal"])

    def test_no_words_is_unknown(self):
        # "..." and "?!" added 2026-11-22 (outside review): punctuation alone used to get a full reading at the centre point
        for text in ("", "   \n", None, "...", " ?! "):
            r = symbolics.read(text)
            self.assertEqual((r.type, r.why), ("unknown", "There are no words here to read."), repr(text))
            self.assertEqual(str(r), "There are no words here to read.")

    def test_a_digit_counts_as_something_to_read(self):
        self.assertEqual(symbolics.read("7").type, "reading")

    def test_text_that_is_not_a_string_is_a_callers_mistake(self):
        # Outside review, 2026-11-22: read(123) was read as the words "123", and read(False) as no words
        for value in (123, False, 2.5, ["words"], b"bytes"):
            with self.assertRaises(TypeError, msg=repr(value)):
                symbolics.read(value)
            with self.assertRaises(TypeError, msg=repr(value)):
                symbolics.readings(value)

    def test_a_misspelt_lens_is_caught_whatever_the_text(self):
        # Outside review, 2026-11-22: with empty or refused text the lens was never looked at
        for text in (TEXT, "", OTHER):
            with self.assertRaises(ValueError, msg=text):
                symbolics.read(text, lens="astrology")

    def test_lens_names_ignore_case(self):
        self.assertEqual(symbolics.read(TEXT, lens="Dynamical").reads, "limit cycle")

    def test_one_word_is_read(self):
        self.assertEqual(symbolics.read("x").type, "reading")

    def test_an_unknown_lens_is_a_callers_mistake(self):
        with self.assertRaises(ValueError):
            symbolics.read(TEXT, lens="astrology")


class TestARefusalCannotPassForAReading(unittest.TestCase):
    def test_only_a_reading_is_ok(self):
        self.assertTrue(symbolics.read(TEXT).ok)
        self.assertFalse(symbolics.read(OTHER).ok)
        self.assertFalse(symbolics.read("").ok)

    def test_a_reading_returns_itself_so_it_chains(self):
        r = symbolics.read(TEXT)
        self.assertIs(r.raise_for_status(), r)
        self.assertEqual(symbolics.read(TEXT).raise_for_status().reads, "Geburah")

    def test_a_refusal_raises_refused_with_its_record(self):
        with self.assertRaises(symbolics.Refused) as e:
            symbolics.read(OTHER).raise_for_status()
        self.assertEqual(e.exception.record.type, "refusal")
        self.assertEqual(str(e.exception), ethics.check_request(OTHER)["why"])

    def test_nothing_to_read_raises_unknown(self):
        with self.assertRaises(symbolics.Unknown) as e:
            symbolics.read("").raise_for_status()
        self.assertEqual(str(e.exception), "There are no words here to read.")

    def test_one_except_catches_both_and_neither_is_an_ethics_error(self):
        for text in (OTHER, ""):
            with self.assertRaises(symbolics.NotARead):
                symbolics.read(text).raise_for_status()
        self.assertFalse(issubclass(symbolics.NotARead, ethics.EthicsError))

    def test_any_other_kind_is_unknown(self):
        for kind in ("paradox", "fact"):
            with self.assertRaises(symbolics.Unknown):
                reading.Record({"type": kind, "why": "x"}).raise_for_status()

    def test_a_record_with_no_why_names_its_type(self):
        with self.assertRaises(symbolics.Unknown) as e:
            reading.Record({"type": "paradox"}).raise_for_status()
        self.assertEqual(str(e.exception), "paradox")


class TestTheRecord(unittest.TestCase):
    def setUp(self):
        self.r = symbolics.read(TEXT)

    def test_attribute_and_key_are_the_same_value(self):
        for key in ("reads", "tradition", "source", "caveat", "ask"):
            self.assertEqual(getattr(self.r, key), self.r[key])

    def test_it_is_read_only(self):
        with self.assertRaises(AttributeError):
            self.r.reads = "Kether"
        with self.assertRaises(TypeError):
            self.r["reads"] = "Kether"

    def test_as_dict_is_a_copy(self):
        d = self.r.as_dict()
        d["reads"] = "Kether"
        self.assertEqual(self.r.reads, "Geburah")
        self.r.candidates.append("Kether")
        self.assertEqual(len(self.r.candidates), 3)

    def test_nothing_nested_can_be_changed_through_it(self):
        # Outside review, 2026-11-22: the first version copied only the top level
        r = symbolics.read(TEXT)
        r["address"]["severity_mercy"] = 999
        r["candidates"].append("TAMPERED")
        r.anchors[0]["quote"] = "TAMPERED"
        r.as_dict()["anchors"][0]["quote"] = "TAMPERED"
        self.assertEqual(r.address, (324, 334, 1000))
        self.assertEqual(r.candidates, ["Geburah", "Binah", "Tiphareth"])
        self.assertEqual(r.anchors[0]["quote"], TEXT)

    def test_the_record_does_not_share_the_dict_it_was_made_from(self):
        source = {"type": "reading", "reads": "Kether", "candidates": ["Kether"]}
        r = reading.Record(source)
        source["candidates"].append("TAMPERED")
        self.assertEqual(r.candidates, ["Kether"])

    def test_it_is_a_mapping(self):
        self.assertEqual(dict(self.r), self.r.as_dict())
        self.assertEqual(len(self.r), len(self.r.as_dict()))
        self.assertIn("reads", self.r)

    def test_printed_it_carries_the_question_and_the_caveat(self):
        self.assertEqual(str(self.r),
                         "Reads as Geburah under the Kabbalistic (Hermetic Tree of Life) lens.\n"
                         "This sits between Geburah and Binah and Tiphareth; which feels more true for you?\n"
                         "This is a symbolic map; the territory is your lived experience.")

    def test_printed_without_a_question(self):
        r = reading.Record({"type": "reading", "reads": "Kether", "tradition": "T", "caveat": ethics.CAVEAT})
        self.assertEqual(str(r), f"Reads as Kether under the T lens.\n{ethics.CAVEAT}")
        self.assertIsNone(r.ask)
        self.assertEqual((r.candidates, r.anchors, r.address), ([], [], None))

    def test_what_it_prints_passes_the_gate_itself(self):
        text = str(self.r)
        self.assertFalse(ethics.is_directive(text))
        self.assertEqual(ethics.judgment_words(text), [])

    def test_repr(self):
        self.assertEqual(repr(self.r), "<reading: Geburah, Kabbalistic (Hermetic Tree of Life)>")
        self.assertEqual(repr(symbolics.read("")), "<unknown: There are no words here to read.>")

    def test_a_record_with_only_a_type_prints_its_type(self):
        self.assertEqual(str(reading.Record({"type": "fact"})), "fact")


if __name__ == "__main__":
    unittest.main()
