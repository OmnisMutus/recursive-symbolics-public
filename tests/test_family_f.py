"""Standalone verification for symbolics/family_f.py (D_22 dihedral solver & gate).

Ground truth:
1. Published 22-letter Atbash and Albam pipe tables (TorahCalc / classical gematria cipher reference).
2. Attested traditional letter transformations (YHWH -> Atbash = מצפץ; Avgad = כוזו).
3. Non-abelian dihedral group D_22 conjugation/commutator checks by direct character lookup.
4. Verification gate invariants: approval never upgrades CONTRADICTED or UNCHECKED to VERIFIED.
"""

import random
import re
import unittest

from symbolics import family_f as F


ATBASH_TABLE_MD = """
| א | ת |
| ב | ש |
| ג | ר |
| ד | ק |
| ה | צ |
| ו | פ |
| ז | ע |
| ח | ס |
| ט | נ |
| י | מ |
| כ | ל |
| ל | כ |
| מ | י |
| נ | ט |
| ס | ח |
| ע | ז |
| פ | ו |
| צ | ה |
| ק | ד |
| ר | ג |
| ש | ב |
| ת | א |
"""

ALBAM_TABLE_MD = """
| א | ל |
| ב | מ |
| ג | נ |
| ד | ס |
| ה | ע |
| ו | פ |
| ז | צ |
| ח | ק |
| ט | ר |
| י | ש |
| כ | ת |
| ל | א |
| מ | ב |
| נ | ג |
| ס | ד |
| ע | ה |
| פ | ו |
| צ | ז |
| ק | ח |
| ר | ט |
| ש | י |
| ת | כ |
"""


def _parse_two_col_table(md_text):
    mapping = {}
    for line in md_text.splitlines():
        m = re.match(r"^\|\s*([א-ת])\s*\|\s*([א-ת])\s*\|", line.strip())
        if m:
            mapping[m.group(1)] = m.group(2)
    return mapping


class TestFamilyFDeterministicSolver(unittest.TestCase):
    def test_matches_published_cipher_tables_and_attested_pairs(self):
        atbash_map = _parse_two_col_table(ATBASH_TABLE_MD)
        albam_map = _parse_two_col_table(ALBAM_TABLE_MD)
        self.assertEqual(len(atbash_map), 22)
        self.assertEqual(len(albam_map), 22)

        atbash_rule = F.RULE_BY_NAME["Atbash"]
        albam_rule = F.RULE_BY_NAME["Albam"]
        for ch, target in atbash_map.items():
            self.assertEqual(atbash_rule.apply(ch), target)
        for ch, target in albam_map.items():
            self.assertEqual(albam_rule.apply(ch), target)

        self.assertEqual(atbash_rule.apply("אהבה"), "תצשצ")
        self.assertEqual(atbash_rule.apply("שלום"), "בכפי")
        self.assertEqual(albam_rule.apply("אחד"), "לקס")

        atbash_c1 = [r.name for r in F.matching_rules([("יהוה", "מצפץ")]) if r.complexity == 1]
        avgad_c1 = [r.name for r in F.matching_rules([("יהוה", "כוזו")]) if r.complexity == 1]
        self.assertEqual(atbash_c1, ["Atbash"])
        self.assertEqual(avgad_c1, ["Avgad"])
        self.assertEqual(F.RULE_BY_NAME["Reverse_Avgad"].apply("כוזו"), "יהוה")

        # Boundaries: total group size, niqqud stripping, empty/non-Hebrew/None inputs
        self.assertEqual(len(F.DIHEDRAL_RULES), 44)
        self.assertEqual(len(F.ALL_RULES), 44 * len(F.POSITIONAL_NAMES))
        self.assertEqual(atbash_rule.apply("שָׁלוֹם"), "בכפי")
        self.assertIsNone(atbash_rule.apply(""))
        self.assertIsNone(atbash_rule.apply("ascii 123"))
        self.assertEqual(F.normalize_hebrew(None), "")

    def test_positional_transformations_and_edges(self):
        self.assertEqual(F.apply_positional("אבג דהו", "reverse"), "והד גבא")
        self.assertEqual(F.apply_positional("אבגד", "rotate_1"), "בגדא")
        self.assertEqual(F.apply_positional("אבגד", "rotate_3"), "דאבג")
        self.assertIsNone(F.apply_positional("אבגד", "rotate_4"))
        self.assertIsNone(F.apply_positional("אבגד הו", "rotate_1"))
        self.assertEqual(F.apply_positional("אנא בכח גדולת", "notariqon_initials"), "אבג")
        self.assertEqual(F.apply_positional("אנא בכח גדולת", "notariqon_finals"), "אחת")
        self.assertIsNone(F.apply_positional("יחיד", "notariqon_initials"))
        self.assertEqual(F.apply_positional("אבג דהו", "interleave"), "אדבהגו")
        self.assertIsNone(F.apply_positional("אב דהו", "interleave"))

    def test_non_abelian_dihedral_commutator_and_involution(self):
        # Atbash is an involution on normalized Hebrew letters (final forms -> base forms)
        atbash = F.RULE_BY_NAME["Atbash"]
        for sample in ("אמת", "בראשית", "שלום"):
            self.assertEqual(atbash.apply(atbash.apply(sample)), F.normalize_hebrew(sample))
        # Reflection and shift(1) do not commute in D_22: Atbash(Avgad(א)) != Avgad(Atbash(א))
        avgad = F.RULE_BY_NAME["Avgad"]
        self.assertNotEqual(atbash.apply(avgad.apply("א")), avgad.apply(atbash.apply("א")))

    def test_verification_gate_never_accepts_contradicted_or_unchecked(self):
        study_atbash = [("אהבה", "תצשצ"), ("שלום", "בכפי")]
        ver = F.check_outputs(study_atbash, [("יהוה", "מצפץ")], approved=False)
        self.assertEqual(ver["results"][0]["status"], "VERIFIED")
        self.assertEqual(ver["results"][0]["checker_output"], "מצפצ")

        # CONTRADICTED stays CONTRADICTED even when approved=True
        con = F.check_outputs(study_atbash, [("יהוה", "כוזו")], approved=True)
        self.assertTrue(con["approved"])
        self.assertEqual(con["results"][0]["status"], "CONTRADICTED")
        self.assertEqual(con["results"][0]["checker_output"], "מצפצ")

        # Ambiguous study set stays UNCHECKED even with approval
        amb = F.check_outputs([("א", "ת")], [("ב", "ש")], approved=True)
        self.assertEqual(amb["results"][0]["status"], "UNCHECKED")
        self.assertEqual(amb["results"][0]["reason"], "ambiguous_study")
        self.assertEqual(set(amb["results"][0]["candidates"]), {"א", "ש"})

        # Out-of-family study set returns UNCHECKED
        oof = F.check_outputs([("אב", "גא"), ("גד", "הד")], [("יהוה", "מצפץ")], approved=True)
        self.assertEqual(oof["matched_rules"], [])
        self.assertEqual(oof["results"][0]["status"], "UNCHECKED")
        self.assertIsNone(oof["results"][0]["checker_output"])

    def test_sample_hebrew_episode_generates_valid_training_and_eval_sets(self):
        import random
        rng = random.Random(1337)
        grammar, study, query = F.sample_hebrew_episode(rng, n_study=10, n_query=6)
        self.assertEqual(len(study), 10)
        self.assertEqual(len(query), 6)
        self.assertGreaterEqual(len(grammar.ops), 2)
        self.assertLessEqual(len(grammar.ops), 3)

        # Confirm every sample input executes through the grammar to its expected output
        for toks, expected in study + query:
            self.assertEqual(grammar.interpret(toks), expected)

        # Confirm no gold ciphers or held-out words leak into training
        self.assertFalse(grammar.has_gold_or_held_out_composition())
        for toks, expected in study + query:
            for t in toks:
                if t in grammar.ops:
                    continue
                self.assertFalse(F.is_held_out_word(t))
                self.assertNotIn(t, F.ATTESTED_WORDS)


# ---- Added 2026-11-22: the first whole run of the mutation gate left 52 mutants alive in family_f.py ----------
# Each test below names the line it guards. Expected values are worked out by hand from the letter table
# (א=0 ב=1 ג=2 ד=3 ה=4 ו=5 ז=6 ח=7 ט=8 י=9 כ=10 ... ת=21), never taken from the code under test.

class FakeRng:
    """A stand-in for random.Random whose every choice is known: the last item, the lowest count, a fixed draw."""

    def __init__(self, draw=0.0):
        self.draw = draw

    def choice(self, seq):
        return list(seq)[-1]

    def choices(self, seq, k=1):
        return [list(seq)[-1]] * k

    def randint(self, low, high):
        return low

    def random(self):
        return self.draw


def rule(name):
    return F.RULE_BY_NAME[name]


class TestPositionalEdges(unittest.TestCase):
    def test_notariqon_takes_two_to_four_words_inclusive(self):
        # lines 127 and 131: 2 <= len(words) <= 4, both ends included
        self.assertEqual(F.apply_positional("אב גד", "notariqon_initials"), "אג")
        self.assertEqual(F.apply_positional("אב גד הו זח", "notariqon_initials"), "אגהז")
        self.assertEqual(F.apply_positional("אב גד", "notariqon_finals"), "בד")
        self.assertEqual(F.apply_positional("אב גד הו זח", "notariqon_finals"), "בדוח")
        for pos in ("notariqon_initials", "notariqon_finals"):
            self.assertIsNone(F.apply_positional("אב", pos))
            self.assertIsNone(F.apply_positional("אב גד הו זח טי", pos))

    def test_boustrophedon_needs_three_rows_of_equal_length(self):
        # line 139: len(r1) == len(r2) == len(r3); each row may be the odd one out
        for text in ("אבג דה וזח", "אב גדה וז", "אב גד הוז"):
            self.assertIsNone(F.apply_positional(text, "boustrophedon"), text)

    def test_boustrophedon_reads_the_middle_row_backwards(self):
        # lines 143-145. Length 3: column i is r1[i] + r2[2 - i] + r3[i].
        # "אבג דהו זחט": i=0 א+ו+ז, i=1 ב+ה+ח, i=2 ג+ד+ט
        self.assertEqual(F.apply_positional("אבג דהו זחט", "boustrophedon"), "אוז בהח גדט")
        # length 2: i=0 א+ד+ה, i=1 ב+ג+ו
        self.assertEqual(F.apply_positional("אב גד הו", "boustrophedon"), "אדה בגו")
        # length 1: the three letters, one column
        self.assertEqual(F.apply_positional("א ב ג", "boustrophedon"), "אבג")


class TestRuleNamesAndOrder(unittest.TestCase):
    def test_complexity_counts_each_part_that_is_not_identity(self):
        # line 160
        self.assertEqual(rule("id").complexity, 0)
        self.assertEqual(rule("Atbash").complexity, 1)
        self.assertEqual(rule("reverse").complexity, 1)
        self.assertEqual(rule("Atbash+reverse").complexity, 2)

    def test_names(self):
        # lines 164 and 168
        self.assertEqual(F.Rule("id", 1, 0, "id").name, "id")
        self.assertEqual(F.Rule("Atbash", -1, 21, "id").name, "Atbash")
        self.assertEqual(F.Rule("id", 1, 0, "reverse").name, "reverse")
        self.assertEqual(F.Rule("Atbash", -1, 21, "reverse").name, "Atbash+reverse")

    def test_order_puts_plus_shifts_before_reflections(self):
        # line 186: within one complexity and positional reading, sign +1 comes before -1, then by shift
        names = [r.name for r in F.ALL_RULES]
        self.assertEqual(names[:4], ["id", "Avgad", "shift_2", "shift_3"])
        self.assertLess(names.index("Reverse_Avgad"), names.index("reflect_0"))
        self.assertEqual(names.index("reflect_0"), 22)      # id, then 21 plus shifts (1..21), then reflect_0

    def test_there_are_571_rules_besides_identity(self):
        # line 382: 44 substitutions x 13 readings = 572, less the identity
        self.assertEqual(len(F._NON_TRIVIAL_RULES), 571)
        self.assertNotIn(rule("id"), F._NON_TRIVIAL_RULES)

    def test_distinct_outputs_drops_none_and_repeats(self):
        # line 211: rotate_3 on a three-letter word is None; the same output twice is listed once
        self.assertEqual(F._distinct_outputs([rule("rotate_3"), rule("id"), rule("id")], "אבג"), ["אבג"])


class TestProposalsAndChecks(unittest.TestCase):
    def test_the_default_proposal_is_the_simplest_rules_output(self):
        # lines 301-302. יהוה -> כוזו is Avgad (+1: י9->כ10, ה4->ו5, ו5->ז6), so אדני -> בהסכ
        out = F.tzeruf_apply([("יהוה", "כוזו")], ["אדני"])
        self.assertEqual(out["results"][0]["proposed"], "בהסכ")
        self.assertEqual(out["results"][0]["status"], "VERIFIED")

    def test_a_model_must_answer_every_query(self):
        # line 307
        with self.assertRaises(ValueError):
            F.tzeruf_apply([("יהוה", "כוזו")], ["אדני", "אב"], model_predict=lambda s, q: ["בהסכ"])
        out = F.tzeruf_apply([("יהוה", "כוזו")], ["אדני"], model_predict=lambda s, q: ["בהסכ"])
        self.assertEqual(out["results"][0]["status"], "VERIFIED")

    def test_held_out_is_one_word_in_five_by_hash(self):
        # line 321: the definition, applied by hand to two words
        import hashlib
        for word, held in (("גד", True), ("אב", False)):
            by_hand = int(hashlib.sha256(word.encode("utf-8")).hexdigest()[:8], 16) % 5 == 0
            self.assertEqual(by_hand, held, word)
            self.assertEqual(F.is_held_out_word(word), held, word)


class TestGrammarSampling(unittest.TestCase):
    def test_only_a_reflection_with_reverse_is_held_out(self):
        # line 341: sign -1 AND pos reverse
        self.assertTrue(F.HebrewGrammar({"a": rule("reflect_3+reverse")}).has_gold_or_held_out_composition())
        self.assertFalse(F.HebrewGrammar({"a": rule("reflect_3")}).has_gold_or_held_out_composition())
        self.assertFalse(F.HebrewGrammar({"a": rule("shift_2+reverse")}).has_gold_or_held_out_composition())

    def test_operators_are_named_from_op1(self):
        # line 389
        self.assertEqual(sorted(F.sample_hebrew_grammar(random.Random(1), n_ops=2).ops), ["op1", "op2"])

    def test_notariqon_with_two_words_uses_both(self):
        # line 397: len(words) >= 2
        gr = F.HebrewGrammar({"op1": rule("notariqon_initials")})
        self.assertEqual(F._candidate_tokens(FakeRng(), gr, ["אב", "גד"]), ("גד", "גד", "op1"))

    def test_interleave_and_boustrophedon_draw_equal_length_words(self):
        # lines 399 and 407
        words = ["אב", "גדה"]
        self.assertEqual(F._candidate_tokens(FakeRng(), F.HebrewGrammar({"op1": rule("interleave")}), words),
                         ("גדה", "גדה", "op1"))
        self.assertEqual(F._candidate_tokens(FakeRng(), F.HebrewGrammar({"op1": rule("boustrophedon")}), words),
                         ("גדה", "גדה", "גדה", "op1"))

    def test_rotation_draws_only_words_longer_than_its_step(self):
        # line 418: len(w) > k. FakeRng picks the last word, which is exactly as long as the step.
        gr = F.HebrewGrammar({"op1": rule("rotate_2")})
        self.assertEqual(F._candidate_tokens(FakeRng(draw=1.0), gr, ["אבגד", "הו"]), ("אבגד", "op1"))

    def test_a_second_operator_must_fit_the_word(self):
        # line 424: id/reverse always fit; rotate_k fits only a word longer than k
        gr = F.HebrewGrammar({"op1": rule("reverse"), "op2": rule("rotate_3")})
        # FakeRng picks op2 (rotate_3) first; the word "אבג" has 3 letters, so only op1 may follow
        self.assertEqual(F._candidate_tokens(FakeRng(draw=0.0), gr, ["אבג"]), ("אבג", "op2", "op1"))

    def test_a_second_operator_follows_only_below_the_draw_threshold(self):
        # line 426: random() < 0.35
        gr = F.HebrewGrammar({"op1": rule("reverse")})
        self.assertEqual(F._candidate_tokens(FakeRng(draw=0.3499), gr, ["אבג"]), ("אבג", "op1", "op1"))
        self.assertEqual(F._candidate_tokens(FakeRng(draw=0.35), gr, ["אבג"]), ("אבג", "op1"))

    def test_a_rotation_needs_a_word_longer_than_its_step(self):
        # line 437: max_len <= k is infeasible
        gr = F.HebrewGrammar({"op1": rule("rotate_3")})
        self.assertFalse(F._grammar_feasible_for_pool(gr, ["אבג"]))
        self.assertTrue(F._grammar_feasible_for_pool(gr, ["אבגד"]))

    def test_sampled_grammars_never_use_a_gold_cipher(self):
        # line 465, over fixed seeds
        for seed in range(40):
            gr, _, _ = F.sample_hebrew_episode(random.Random(seed), n_study=2, n_query=1)
            self.assertFalse(gr.has_gold_or_held_out_composition(), seed)


class TestEpisodeLimits(unittest.TestCase):
    def test_words_of_two_to_eight_letters_are_eligible(self):
        # line 455: 2 <= len <= 8. None of these words is held out, so only its length decides.
        for word in ("א", "בגדהוזחטי"):                  # 1 and 9 letters: nothing eligible
            self.assertFalse(F.is_held_out_word(word))
            with self.assertRaises(ValueError, msg=word):
                F.sample_hebrew_episode(random.Random(0), word_pool=[word], n_study=1, n_query=0)
        for word in ("אב", "אבגדהוזח"):                  # 2 and 8 letters: eligible
            self.assertFalse(F.is_held_out_word(word))
            gr, study, _ = F.sample_hebrew_episode(random.Random(0), word_pool=[word], n_study=1, n_query=0)
            self.assertEqual(len(study), 1)

    def test_too_few_queries_is_an_error_even_when_study_is_full(self):
        # line 486: len(study) < n_study OR len(query) < n_query
        with self.assertRaises(RuntimeError):
            F.sample_hebrew_episode(random.Random(0), n_study=0, n_query=3, max_tries=0)


class TestSolverInput(unittest.TestCase):
    def test_study_entries(self):
        # lines 496 and 501
        self.assertEqual(F._normalize_study_pairs([("אב", "גד")]), [("אב", "גד")])
        self.assertEqual(F._normalize_study_pairs([{"input": "אב", "output": "גד"}]), [("אב", "גד")])
        self.assertIsNone(F._normalize_study_pairs(["אב"]))              # a two-letter string is not a pair
        self.assertIsNone(F._normalize_study_pairs([["א", "ב", "ג"]]))
        self.assertIsNone(F._normalize_study_pairs([("אב", "  ")]))
        self.assertIsNone(F._normalize_study_pairs([("", "גד")]))

    def test_a_and_b_are_a_pair_only_when_both_are_given(self):
        # line 510
        self.assertEqual(F._parse_tzeruf_text("", "אב", "גד"), ([("אב", "גד")], []))
        self.assertEqual(F._parse_tzeruf_text("", "אב", None), ([], []))
        self.assertEqual(F._parse_tzeruf_text("", "אב", "  "), ([], []))
        self.assertEqual(F._parse_tzeruf_text("", None, "גד"), ([], []))

    def test_a_pair_in_text_needs_both_sides(self):
        # line 519
        self.assertEqual(F._parse_tzeruf_text("אב=גד הו", None, None), ([("אב", "גד")], ["הו"]))
        self.assertEqual(F._parse_tzeruf_text("אב=", None, None), ([], []))
        self.assertEqual(F._parse_tzeruf_text("=גד", None, None), ([], []))

    def test_study_given_with_a_and_b_or_text_adds_them(self):
        # line 543: text, or a and b both given
        out = F.solve_tzeruf(study=[["יהוה", "כוזו"]], a="אב", b="בג")
        self.assertEqual(len(out["study"]), 2)
        out = F.solve_tzeruf(study=[["יהוה", "כוזו"]], text="אדני")
        self.assertEqual([r["query"] for r in out["results"]], ["אדני"])
        out = F.solve_tzeruf(study=[["יהוה", "כוזו"]], a="אב")
        self.assertEqual(len(out["study"]), 1)

    def test_proposed_must_match_the_queries(self):
        # line 557
        self.assertIn("error", F.solve_tzeruf(a="יהוה", b="כוזו", queries=["אדני"], proposed=["x", "y"]))
        out = F.solve_tzeruf(a="יהוה", b="כוזו", queries=["אדני"], proposed=["בהסכ"])
        self.assertEqual(out["status"], "VERIFIED")

    def test_overall_status(self):
        # line 572: every result VERIFIED gives VERIFIED; one UNCHECKED among them gives UNCHECKED
        both = F.solve_tzeruf(a="יהוה", b="כוזו", queries=["אדני", "אב"])
        self.assertEqual([r["status"] for r in both["results"]], ["VERIFIED", "VERIFIED"])
        self.assertEqual(both["status"], "VERIFIED")
        mixed = F.solve_tzeruf(a="יהוה", b="כוזו", queries=["אדני", "1"])
        self.assertEqual([r["status"] for r in mixed["results"]], ["VERIFIED", "UNCHECKED"])
        self.assertEqual(mixed["status"], "UNCHECKED")

    def test_with_no_queries_one_matching_rule_is_verified(self):
        # line 576: exactly one rule left is VERIFIED; more than one is UNCHECKED
        one = F.solve_tzeruf(a="יהוה", b="כוזו")
        self.assertEqual((one["rule_count"], one["status"]), (1, "VERIFIED"))
        many = F.solve_tzeruf(a="א", b="א")
        self.assertGreater(many["rule_count"], 1)
        self.assertEqual(many["status"], "UNCHECKED")


if __name__ == "__main__":
    unittest.main()
