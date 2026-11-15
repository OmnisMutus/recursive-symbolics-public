"""Standalone verification for symbolics/family_f.py (D_22 dihedral solver & gate).

Ground truth:
1. Published 22-letter Atbash and Albam pipe tables (TorahCalc / classical gematria cipher reference).
2. Attested traditional letter transformations (YHWH -> Atbash = מצפץ; Avgad = כוזו).
3. Non-abelian dihedral group D_22 conjugation/commutator checks by direct character lookup.
4. Verification gate invariants: approval never upgrades CONTRADICTED or UNCHECKED to VERIFIED.
"""

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


if __name__ == "__main__":
    unittest.main()
