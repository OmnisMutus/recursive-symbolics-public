"""The mandatory ethical API, as checks rather than intentions.

core-ethics.md states seven principles and says they are not optional. Six of them are mechanical, so they are
enforced here and a test proves each one. The seventh (Poetic Grounding) is a stance, and it shows up as the
refusal to return a single definitive verdict: readings are plural by construction in address.py.

    1 Non-Reduction          every reading carries the caveat, or emit() refuses it
    2 Agency and sovereignty optative phrasing; the gamma cap lives in agency.py
    3 Non-Judgment           a banned vocabulary, checked on the way out
    4 Context                near-boundary readings offer their candidates (address.read)
    5 Anti-Colonial          a reading names the tradition and the source it read from
    6 Poetic Grounding       no single verdict; the docstrings say what this is not
    7 The gap                UNKNOWN and PARADOX are return types, not failures

And the two deliberate omissions of hidden-axioms 7.4, which are refusals rather than gaps:

    other-state work         this engine reads the person asking, and no one else
    transcend(sigma)         undefined on purpose, and its absence is a ledger row

The refusals are the only place this engine is allowed to be directive.
"""
import re
from collections.abc import Mapping

CAVEAT = "This is a symbolic map; the territory is your lived experience."

# core-ethics 3: "Avoid words like 'optimal', 'deficient', 'better', 'worse'." Ranking a person's state is the
# violation the principle names, so the check is on the words that rank.
JUDGMENT = ("optimal", "optimally", "suboptimal", "deficient", "deficiency", "better", "worse", "best", "worst",
            "efficient", "inefficient", "efficiency", "healthy state", "unhealthy", "advanced practitioner",
            "regressed", "progress score", "ranked", "ranking", "grade", "scored higher", "scored lower",
            # added 2026-11-20 after the bypasses recorded in OBSERVATIONS.md
            "rank", "ranks", "inferior", "superior", "below average", "above average", "percentile")
# A placing among other people, written as a share: "the bottom 10%", "the top 5 % of people".
_PLACING = re.compile(r"\b(?:top|bottom)\s+\d+(?:\.\d+)?\s*%", re.IGNORECASE)

# core-ethics 2: tools "must output options, not commands". Checked one sentence at a time, so an offer in one
# sentence does not excuse a command in the next ("Consider this: you must banish now. Stop everything.").
_SENTENCES = re.compile(r"(?<=[.!?:;])\s+|\n+")
# An obligation laid on the person is a command wherever it stands in the sentence, and no offer softens it.
_OBLIGATION = re.compile(r"\byou\s+(?:must|should|need\s+to|have\s+to|ought\s+to)\b", re.IGNORECASE)
# A sentence that opens with a bare verb. The list is finite, so a verb missing from it is a known gap.
IMPERATIVE = re.compile(r"^\W*(?:then\s+)?(?:do|stop|start|begin|perform|invoke|banish|meditate|fix|correct|avoid|"
                        r"cease|quit|leave|go|call|tell|text|break|end|cut|move|sell|buy|take|give|get|make|keep|"
                        r"drop|walk|run|write|say|ask|confront|forgive|accept|trust|ignore|eat|sleep|pray|light|"
                        r"burn|throw|delete|send|sign|pay|breathe|focus|let\s+go|wait|abandon|finish|repeat)\b",
                        re.IGNORECASE)
OPTATIVE = ("you might", "you could", "some find", "one way", "if it helps", "you may wish", "consider")
# Whole words only (fixed 2026-11-22): as a substring, "consider" matched inside "considering", so "Stop now,
# considering the cost." read as an offer.
_OPTATIVE = re.compile(r"\b(?:" + "|".join(re.escape(p) for p in OPTATIVE) + r")\b", re.IGNORECASE)

# hidden-axioms 7.4: the engine is for self-diagnosis and self-regulation. What is refused is a request to read,
# judge or act on ANOTHER person; a state of your own that mentions someone else is not that, and must not be
# refused, or the engine is useless on a real diary.
#
# The two word lists below are each used twice: loosely (anywhere in the request) and tightly (a verb aimed
# straight at someone). They are written once so the two uses cannot drift apart.
_VERBS = (r"diagnose|analyse|analyze|assess|evaluate|judge|interpret|fix|heal|cure|influence|persuade|convince|"
          r"manipulate|bind|curse|compel|read")
_RELATIVE = (r"(?:my|our|his|her|their)\s+(?:husband|wife|partner|boyfriend|girlfriend|ex|mother|father|mom|dad|"
             r"sister|brother|son|daughter|friend|colleague|coworker|boss|neighbour|neighbor|roommate|client|"
             r"patient|student|teacher)")

_ACT = re.compile(r"\b(?:" + _VERBS + r")\b", re.IGNORECASE)
_THIRD_PERSON = re.compile(r"\b(?:him|her|hers|his|them|their|theirs|he|she|they)\b", re.IGNORECASE)
_RELATION = re.compile(r"\b" + _RELATIVE + r"\b", re.IGNORECASE)
# A given name mid-sentence, counted only in the possessive ("Sarah's state"). Until 2026-11-20 any capitalised
# word counted, which refused "interpret the Tower card" and "read Tarot for me": cards, Sephiroth and traditions
# are capitalised too.
_NAMED = re.compile(r"(?<![.!?]\s)(?<!^)\b[A-Z][a-z]{2,}'s\b")
_RITUAL_FOR_OTHER = re.compile(r"\b(?:ritual|working|operation|sigil|spell|invocation)\b[^.?!]{0,30}?"
                               r"\b(?:for|on|against|to\s+(?:make|get|stop))\b", re.IGNORECASE)
# A request framed about the person's own state stands, even when it names someone else.
_SELF = re.compile(r"\b(?:my\s+own\b|myself|my\s+(?:state|address|reading|practice|session|diary)"
                   r"|i\s+(?:am|was|feel|felt|keep|kept|cannot|can't|could\s?n[o']t|have|had|did|do))\b",
                   re.IGNORECASE)

# A verb aimed straight at another person, or "what's wrong with" one. These are refused even inside a sentence
# that also speaks of the asker's own state ("I feel my brother is depressed, diagnose him"): the self-framing
# above excuses mentioning someone, not working on them. Added 2026-11-20 after OBSERVATIONS.md.
# A capitalised word counts as a name only after "wrong with": after a verb it is too often a card, a Sephirah or
# a tradition ("interpret the Tower", "read Tarot"), and refusing those would make the engine useless.
_TARGET = r"(?i:him|her|them|" + _RELATIVE + r")\b"
_AIMED = re.compile(r"(?i:\b(?:" + _VERBS + r"))\s+" + _TARGET)
_WRONG_WITH = re.compile(r"(?i:\bwrong\s+with)\s+(?:" + _TARGET + r"|[A-Z][a-z]{2,}\b)")


def _about_another_person(text):
    """True when the request asks this engine to work on someone who is not the person asking."""
    if _AIMED.search(text) or _WRONG_WITH.search(text):
        return True
    if _SELF.search(text):
        return False
    target = _THIRD_PERSON.search(text) or _RELATION.search(text) or _NAMED.search(text)
    if _ACT.search(text) and target:
        return True
    return bool(_RITUAL_FOR_OTHER.search(text) and target)


_TRANSCEND = re.compile(r"\b(?:transcend\s*\(|transcend\s+(?:the|sigma|σ)|god[\s-]?mode|bypass\s+the\s+tree"
                        r"|outside\s+the\s+(?:tree|framework|symbolic))\b", re.IGNORECASE)


class EthicsError(Exception):
    """Raised when this engine's own code tries to emit something the ethical API forbids. It is a programming
    error, not a user error: the person asking should never see one."""


def refusal(why, principle):
    """A typed refusal: why, and the principle it rests on."""
    return {"type": "refusal", "why": why, "principle": principle}


def unknown(why, state=None):
    """core-ethics 7: outside the map is an answer, not a failure."""
    out = {"type": "unknown", "why": why}
    if state is not None:
        out["state"] = state
    return out


def check_request(text):
    """The boundaries of hidden-axioms 7.4, checked before anything is read. Returns a refusal or None.

    A request about the person's own state stands even when it names someone else: "I was angry at my brother"
    is their state. What is refused is being asked to work on another person.
    """
    t = " ".join(str(text or "").split())
    if _TRANSCEND.search(t):
        return refusal("There is no transcend operator, and its absence is deliberate: this engine stays inside "
                       "its own symbolic grammar and makes no claim to reach past it.",
                       "hidden-axioms 7.4, intentional omissions")
    if _about_another_person(t):
        return refusal("This engine reads the state of the person asking, and no one else. It has no tools to "
                       "diagnose another person or to act on them, which is a boundary of the framework rather "
                       "than a missing feature. Their state is theirs to describe.",
                       "hidden-axioms 7.4, other-state manipulation")
    return None


def judgment_words(text):
    """Which ranking words are in a piece of output (core-ethics 3). Empty is what output should be."""
    t = str(text or "").casefold()
    found = {w for w in JUDGMENT if re.search(r"\b" + re.escape(w) + r"\b", t)}
    found.update(" ".join(m.group(0).split()) for m in _PLACING.finditer(t))
    return sorted(found)


def is_directive(text):
    """True when output tells the person what to do instead of offering (core-ethics 2). Each sentence is judged
    on its own: an obligation ("you must") is a command anywhere, and a sentence opening with a bare verb is a
    command unless that same sentence offers it."""
    for sentence in _SENTENCES.split(str(text or "")):
        if _OBLIGATION.search(sentence):
            return True
        if IMPERATIVE.search(sentence) and not _OPTATIVE.search(sentence):
            return True
    return False


def _own_words(value, in_anchors=False):
    """Every string this engine wrote in a record, at any depth.

    One kind of string is left out: the "quote" of an anchor, which is the person's own words, kept as evidence and
    not this engine's to judge. Everything else in an anchor (its source, say) is checked, and a key that only
    happens to be called "anchors" without holding anchors hides nothing. (2026-11-22: first only top-level strings
    were checked; then any key named "anchors" or "type" was skipped at any depth. An outside review found that
    second gap.)
    """
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for key, item in value.items():
            if in_anchors and key == "quote":
                continue
            yield from _own_words(item, in_anchors=(key == "anchors"))
    elif isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            yield from _own_words(item, in_anchors)


def _check_reading(value):
    """What a reading needs on top of any record: its tradition, source and name, the caveat, and its evidence."""
    for field in ("tradition", "source", "reads"):
        if not value.get(field):
            raise EthicsError(f"Anti-Colonial Synthesis (core-ethics 5): a reading must name its {field}.")
    if value.get("caveat") != CAVEAT:
        raise EthicsError("Non-Reduction (core-ethics 1): a reading carries the caveat, exactly as written.")
    if not value.get("anchors"):
        raise EthicsError("Groundedness (hidden-axioms 7.2, the GIGO vulnerability): a reading must point at "
                          "the words it came from. A claim with no anchor is refused by the type.")


def emit(value):
    """The last gate every return passes through. It checks this engine's own output, which is the only thing it
    can honestly check: a reading must carry its caveat, its tradition and its evidence, and no output may rank
    a person. A failure here is a bug in this engine, raised loudly rather than softened."""
    if not isinstance(value, dict) or "type" not in value:
        raise EthicsError("Everything this engine returns is a typed record with a 'type'.")
    kind = value["type"]
    if kind not in ("fact", "address", "reading", "paradox", "unknown", "refusal"):
        raise EthicsError(f"'{kind}' is not one of the six returnable types.")
    # Each string is its own line, so one field cannot run into the next and hide a command at the start of a
    # sentence ("next step" + "Stop everything" read as one sentence; fixed 2026-11-22, found in an outside
    # review). The top-level "type" is left out: it was checked above against the six kinds.
    text = "\n".join(_own_words({k: v for k, v in value.items() if k != "type"}))
    bad = judgment_words(text)
    if bad:
        raise EthicsError(f"Non-Judgment (core-ethics 3): this output ranks the person: {', '.join(bad)}.")
    if kind == "reading":
        _check_reading(value)
    if kind != "refusal" and is_directive(text):
        raise EthicsError("Agency (core-ethics 2): this output commands rather than offers.")
    return value
