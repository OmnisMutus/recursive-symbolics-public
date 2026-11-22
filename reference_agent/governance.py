"""The V2.0 Epistemic Governance Framework, applied to this agent's own output.

    "True symbolic systems do not believe their own symbols — they operate them with calibrated epistemic
     humility as maps, not territory."

The framework is the project's own, and this module is the enforcement rather than a restatement of it. The engine's
`ethics.emit()` is the model: a gate every return passes through, checking the one thing it can honestly
check, which is this agent's own words.

Four duties, each refusable:

**Confidence calibration.** A symbolic claim carries an explicit bound, from the framework's own formula:
confidence = (evidence quality x pattern coherence) / alternative hypotheses. Not a feeling, a quotient. The
inputs are stated so a reader can disagree with the inputs rather than the number.

**Empirical falsifiability.** Every symbolic mapping states what observation would kill it. A claim with no
falsifier is not a weak claim; it is not a claim, and this refuses it as such.

**The provisional proviso.** Correspondences are PROVISIONAL METAPHORS. Never ontological truths. A claim
that a thing *is* a sephirah is refused; that it *reads as* one, under a named lens, is not.

**Occam's filter.** Symbolic status is earned by explanatory power. A mapping that explains nothing the plain
description did not already explain is noise wearing a robe, and `occam()` says so.

Plus the agency budget inherited from the framework: directive strength capped at 0.85, so the agent offers
and does not command, with alternatives appended as the cap is approached. The cap is imported from
`symbolics.agency.GAMMA_MAX`, so there is one value in the repository (tests/test_one_cap.py checks this).

A note on what this cannot do. It reads text for the shapes of overclaiming. It cannot know whether a
correspondence is apt, and it does not try: a claim can pass every duty here and still be wrong about the
world. What it guarantees is that the claim arrives with its uncertainty attached, which is the only thing a
gate at the exit can guarantee.
"""
import re

from symbolics import agency

CORE_AXIOM = ("True symbolic systems do not believe their own symbols — they operate them with calibrated "
              "epistemic humility as maps, not territory.")
PROVISIONAL = "PROVISIONAL METAPHOR"
from symbolics.agency import GAMMA_MAX as GAMMA_CAP  # noqa: E402  the one 0.85 (licence Article 6), not a copy

# The framework's own Confidence Ranking (verification-standards.md). Distinct from the percentage: the
# percentage says how well-evidenced a reading is, the rank says what KIND of evidence exists at all. Rank 4
# needs both replication and a computational model, and almost nothing reaches it, which is the point of
# having the scale rather than a single number.
RANKS = {
    1: ("Speculative", "unstructured anecdotal report, lacking formal definition or controlled conditions"),
    2: ("Defined", "formally mapped as S = (L, N, P, C), but without multi-practitioner reproducibility"),
    3: ("Replicated", "formally defined and reproduced by at least three independent practitioners, yielding "
                      "consistent phenomenological or systemic patterns"),
    4: ("Computationally Verified", "replicated by practitioners and successfully modelled computationally, "
                                    "demonstrating predictable recursive attractors"),
}
# What the standard requires of a hypothesis before it is one at all.
HYPOTHESIS_DUTIES = ("formally defined in symbolic or mathematical notation",
                     "computationally implementable as an algorithmic sequence",
                     "repeatable from stated initial conditions",
                     "open to empirical testing, with documentable outcomes")

# Claiming identity between a thing and a symbol: what the Core Axiom forbids ("Anger is Geburah").
# Both directions count. "Anger is Geburah" and "Shin represents Fire" are the same move, and an earlier
# version of this pattern caught only the first, because it required the symbol to be the object.
# Keter and Tifereth added 2026-11-22 (outside review): symbolics/metrics.py spells them that way, so "Balance is Tifereth."
# was not seen as an identity claim.
SYMBOLS = (r"Kether|Keter|Chokmah|Binah|Chesed|Geburah|Tiphareth|Tifereth|Netzach|Hod|Yesod|Malkuth|Da'?ath|"
           r"Aleph|Beth|Gimel|Daleth|Heh|Vav|Vau|Zayin|Zain|Cheth|Teth|Yod|Kaph|Lamed|Mem|Nun|Samekh|"
           r"Ayin|Peh|Pe|Tzaddi|Qoph|Resh|Shin|Tav|Tau")
IS_VERB = r"(?:is|are|means|equals|represents|corresponds\s+to)"
ONTOLOGICAL = re.compile(
    rf"\b{IS_VERB}\s+(?:the\s+|a\s+|an\s+)?(?:{SYMBOLS})\b"      # a thing IS a symbol
    rf"|\b(?:{SYMBOLS})\b\s+{IS_VERB}\b",                        # a symbol IS a thing
    re.IGNORECASE)
# The same content, said as a reading rather than an identity. These are what the gate wants instead.
HEDGED = ("reads as", "reads like", "under the", "lens", "one reading", "provisional", "may be read",
          "corresponds, provisionally", "in this framework", "on this map", "treated as")
# A falsifier has to name an observation, not a feeling.
FALSIFIER_SHAPE = re.compile(
    r"\b(?:if|when|unless|were|should)\b.{0,200}?"
    r"\b(?:then|would|falsif\w*|refut\w*|disconfirm\w*|contradict\w*|fail\w*|wrong|incorrect|false|"
    r"invalid\w*|dies|die|break\w*|collaps\w*|does\s+not\s+hold|no\s+longer\s+holds)\b",
    re.IGNORECASE | re.S)


class GovernanceError(Exception):
    """This agent's own output broke a duty. Raised loudly: it is a bug here, not a user's problem."""


def confidence(evidence_quality, pattern_coherence, alternatives):
    """The framework's formula, as a percentage. Inputs 0..1, 0..1, and a count of rival hypotheses >= 1."""
    for name, value in (("evidence_quality", evidence_quality), ("pattern_coherence", pattern_coherence)):
        # bool is an int in Python, so True would pass as 1.0 without the first test (fixed 2026-11-22)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
            raise GovernanceError(f"{name} is a fraction from 0 to 1, so that a reader can argue with the "
                                  f"input rather than the output. Got {value!r}.")
    n = _whole("alternatives", alternatives)
    if n < 1:
        raise GovernanceError("alternatives is at least 1: there is always the hypothesis that the pattern "
                              "is coincidence, and leaving it out is how a quotient becomes a boast.")
    return round(100.0 * (float(evidence_quality) * float(pattern_coherence)) / n, 1)


def _whole(name, value):
    """A count: a whole number, or None for zero. True and 1.9 are refused rather than read as 1 (2026-11-22)."""
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int):
        raise GovernanceError(f"{name} is a whole number, so that it cannot be rounded quietly. Got {value!r}.")
    return value


# A hedge counts only as a whole word or phrase, and only in the same sentence as the claim it excuses
# (2026-11-22, an outside review: "I wiped my camera lens. Anger is Geburah." was excused by the "lens" of another sentence).
_HEDGE = re.compile(r"\b(?:" + "|".join(re.escape(h) for h in HEDGED) + r")\b", re.IGNORECASE)
_SENTENCE_END = re.compile(r"[.!?](?:\s|$)|\n")


def _sentence_around(text, start, end):
    """The sentence holding text[start:end]."""
    before = [m.end() for m in _SENTENCE_END.finditer(text, 0, start)]
    after = _SENTENCE_END.search(text, end)
    return text[before[-1] if before else 0:after.start() if after else len(text)]


def is_ontological(text):
    """Identity claims this framework forbids, minus the ones already said as a reading."""
    text = text or ""
    out = []
    for m in ONTOLOGICAL.finditer(text):
        if _HEDGE.search(_sentence_around(text, m.start(), m.end())):
            continue
        out.append(m.group(0).strip())
    return out


def has_falsifier(text):
    return bool(FALSIFIER_SHAPE.search(text or ""))


def occam(claim, explains, plain_explains):
    """Does symbolic status buy anything? `explains` and `plain_explains` are what each account covers."""
    gained = sorted(set(explains or ()) - set(plain_explains or ()))
    if gained:
        return {"keep": True, "why": "the symbolic reading accounts for " + ", ".join(gained)
                                     + ", which the plain description does not", "gained": gained}
    return {"keep": False, "gained": [],
            "why": f"the symbolic reading of {claim!r} explains nothing the plain description does not, so "
                   f"Occam's filter says leave it plain. Elevating it would add a layer and no power."}


def gamma(text, cap=GAMMA_CAP):
    """Directive strength, capped, from the one measure the repository has: agency.directive_strength, the
    higher of the entropy and the form readings. Until 2026-11-22 this was a second copy holding the entropy half
    only, so "You must meditate every morning. It is the only way." scored 0.0 here and 0.85 in agency. No words
    at all push nothing, so empty text is 0.0."""
    if not re.search(r"\w", text or ""):
        return 0.0
    return round(min(agency.directive_strength(text), float(cap)), 4)


def rank(formally_defined=False, independent_practitioners=0, computationally_modelled=False):
    """The framework's Confidence Ranking for a symbolic claim, with the reason it is not higher.

    This grades a claim about a symbolic transformation or a shift in consciousness. It does NOT grade
    software: "the suite passes" is not a Rank 4 observation, and reading it as one would be the overclaiming
    the standard exists to stop. A passing test is evidence about code, not about a correspondence.
    """
    n = max(0, _whole("independent_practitioners", independent_practitioners))
    if not formally_defined:
        held_back = "it is not formally defined, so it is anecdote however often it is repeated"
        got = 1
    elif n < 3:
        held_back = (f"only {n} independent practitioner(s) have reproduced it; Rank 3 asks for three")
        got = 2
    elif not computationally_modelled:
        held_back = "it is replicated but not modelled computationally, which Rank 4 asks for"
        got = 3
    else:
        held_back = ""
        got = 4
    name, criteria = RANKS[got]
    return {"rank": got, "name": name, "criteria": criteria,
            "inputs": {"formally_defined": bool(formally_defined), "independent_practitioners": n,
                       "computationally_modelled": bool(computationally_modelled)},
            **({"not_higher_because": held_back} if held_back else {})}


def claim(statement, evidence_quality, pattern_coherence, alternatives, falsifier, lens="",
          formally_defined=False, independent_practitioners=0, computationally_modelled=False):
    """A symbolic claim, governed. Raises rather than emitting one that breaks a duty."""
    text = str(statement or "").strip()
    if not text:
        raise GovernanceError("An empty statement cannot carry a confidence bound.")
    if not str(falsifier or "").strip():
        raise GovernanceError(f"No falsifier for {text!r}. A symbolic mapping states what observation would "
                              f"invalidate it; without one it is not a weak claim, it is not a claim.")
    if not has_falsifier(falsifier):
        raise GovernanceError(f"The falsifier for {text!r} names no observation. Say what would be seen, in "
                              f"the form 'if X is observed, this is false'.")
    bad = is_ontological(text)
    if bad:
        raise GovernanceError(
            f"{text!r} asserts an identity between a thing and a symbol ({', '.join(bad)}), which the Core "
            f"Axiom forbids. Say how it reads under a named lens instead: '... reads as Geburah under the "
            f"Kabbalistic lens', not '... is Geburah'.")
    pct = confidence(evidence_quality, pattern_coherence, alternatives)
    return {"type": "claim", "status": PROVISIONAL, "statement": text, "confidence_percent": pct,
            "inputs": {"evidence_quality": evidence_quality, "pattern_coherence": pattern_coherence,
                       "alternative_hypotheses": int(alternatives)},
            "falsifier": str(falsifier).strip(), "lens": lens or "unnamed",
            "confidence_rank": rank(formally_defined, independent_practitioners, computationally_modelled),
            "directive_strength": gamma(text), "cap": GAMMA_CAP, "axiom": CORE_AXIOM}


def review(text, strict=False):
    """What this agent's prose owes the framework, as findings. `strict` raises instead of reporting."""
    findings = []
    ont = is_ontological(text)
    if ont:
        findings.append({"duty": "provisional proviso", "problem": "identity asserted between a thing and a "
                         "symbol: " + ", ".join(sorted(set(ont))[:6]),
                         "fix": "say it reads as that, under a named lens"})
    if ont and not has_falsifier(text):
        findings.append({"duty": "empirical falsifiability",
                         "problem": "a symbolic mapping with no stated falsifier",
                         "fix": "add what observation would invalidate it"})
    g = gamma(text)
    if g >= GAMMA_CAP:
        findings.append({"duty": "agency budget", "problem": f"directive strength {g} is at the {GAMMA_CAP} "
                         f"cap", "fix": "offer alternatives, or say this is one reading among others"})
    if strict and findings:
        raise GovernanceError("; ".join(f["problem"] for f in findings))
    return {"type": "fact", "what": "governance review", "findings": findings,
            "directive_strength": g, "cap": GAMMA_CAP, "clean": not findings}


def report(governed):
    """A claim or a review, in words, with the uncertainty attached rather than appended."""
    if governed.get("type") == "claim":
        i = governed["inputs"]
        return "\n".join([
            f"[{governed['status']}] {governed['statement']}",
            f"  confidence {governed['confidence_percent']}%  "
            f"(evidence {i['evidence_quality']} x coherence {i['pattern_coherence']} / "
            f"{i['alternative_hypotheses']} alternative(s))",
            f"  lens: {governed['lens']}",
            f"  falsified by: {governed['falsifier']}",
            f"  rank {governed['confidence_rank']['rank']} ({governed['confidence_rank']['name']})"
            + (f", not higher because {governed['confidence_rank']['not_higher_because']}"
               if governed["confidence_rank"].get("not_higher_because") else ""),
            f"  directive strength {governed['directive_strength']} of {governed['cap']}"])
    if governed.get("clean"):
        return f"Nothing owed. Directive strength {governed['directive_strength']} of {governed['cap']}."
    return "\n".join([f"{len(governed['findings'])} duty/duties unmet:"]
                     + [f"  {f['duty']}: {f['problem']}\n    -> {f['fix']}" for f in governed["findings"]])
