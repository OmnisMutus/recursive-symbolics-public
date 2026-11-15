"""The Sovereignty Guardrail: a wrapper that sits between a model and a person.

It does three things to a model's reply before the person sees it:

  1. WITHHOLDS a sentence that states, as fact, what the person is experiencing
     ("you're experiencing a high-friction state", "your data indicates ...").
  2. SOFTENS a command into an option ("You must" becomes "An effective approach is to").
  3. ADDS a note that other readings exist, when the reply is forceful and offers only one path.

Nothing is hidden: the original reply and every change are returned beside the result.

The cap is the core's (`symbolics.agency.GAMMA_MAX`, licence Article 6), imported rather than copied, so
there is one 0.85 in the package. Directive strength here is measured on the model's logits (softmax entropy),
not on the reply's words as `agency.directive_strength` does; tests/test_sovereign_wrapper.py checks it against
tests/fixtures/agency_budget.py. The softening rules stay local on purpose: they skip questions and conditionals
("if you must, ..."), which `agency.soften` does not yet do.

What it cannot do: it matches written patterns. A diagnosis phrased in a shape that is not on the
list below passes through. It reduces a known kind of overreach; it does not understand the reply.

    python engines/sovereign_wrapper.py
"""
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # run as a script, too
from symbolics.agency import GAMMA_MAX as MAX_GAMMA  # noqa: E402  hard ceiling on directive strength

ALTERNATIVES_ABOVE = 0.40   # above this, a reply with fewer than two paths gets the note
MIN_ALTERNATIVES = 2

WITHHELD_NOTE = ("(Withheld here: what stated your experience as a fact. "
                 "You are the one who can say what it is.)")
ALTERNATIVES_NOTE = "(Other paths and readings may fit as well.)"


def directive_strength(logits):
    """How forceful a choice is, from 0.0 (evenly undecided) to 0.85 (one option dominates).

    softmax the logits, take the Shannon entropy, divide by the largest entropy possible for that
    many options, and subtract from 1. The result is clipped to MAX_GAMMA.
    An empty list is 0.0. A single option is MAX_GAMMA: there was nothing else to weigh.
    """
    if not logits:
        return 0.0
    if len(logits) == 1 or not _finite(logits):
        return MAX_GAMMA            # an infinite or NaN score gives no measure: fail closed, at the cap
    top = max(logits)
    weights = [math.exp(x - top) for x in logits]       # subtracting the max avoids overflow
    total = sum(weights)
    probs = [w / total for w in weights]
    entropy = -sum(p * math.log2(p + 1e-12) for p in probs)
    raw = 1.0 - entropy / math.log2(len(probs))
    return min(max(raw, 0.0), MAX_GAMMA)


# A sentence matching any of these tells the person what state they are in.
_STATE = r"(?:state|mindset|mode|phase|loop|pattern)"
_FEW_WORDS = r"(?:\s+[\w’'-]+,?){0,4}?"        # up to four words between the article and the state word
_FEELING = (r"(?:feeling|experiencing|stressed|anxious|depressed|overwhelmed|stuck|burned out|burnt out|"
            r"exhausted|in denial|avoiding|projecting|deflecting|spiraling|spiralling)")
DIAGNOSTIC = [re.compile(p, re.IGNORECASE) for p in (
    r"\byou(?:'re|’re| are)\s+(?:experiencing|suffering from|stuck in|trapped in|in)\s+an?" + _FEW_WORDS
    + r"\s+" + _STATE + r"\b",
    r"\byou(?:'re|’re| are)\s+(?:stuck|trapped)\s+in\b",
    r"\byour\s+(?:data|results?|scores?|metrics?|profile|answers?)\s+(?:indicates?|shows?|proves?|reveals?|confirms?)"
    r"\s+(?:that\s+)?you\b",
    r"\byou\s+(?:have|suffer from|are suffering from)\s+(?:an?\s+)?(?:depression|anxiety|adhd|ocd|ptsd|bipolar|disorder|condition)\b",
    r"\byou(?:'re|’re| are)\s+(?:clearly|obviously|definitely|just)\s+" + _FEELING + r"\b",
)]

# A command, and the option it becomes. Longer phrases first so they win. A phrase is softened only where
# it gives a command: not after "if", "when" or "unless", not before "have" ("you should have told me" is
# about the past), and only when a word follows it ("if you must, ..." has nothing to soften).
_NOT_CONDITIONAL = r"(?<!\bif\s)(?<!\bwhen\s)(?<!\bunless\s)"
_A_WORD_FOLLOWS = r"(?!\s+have\b)(?=\s+\w)"
PRESCRIPTIVE = [(re.compile(_NOT_CONDITIONAL + p + _A_WORD_FOLLOWS, re.IGNORECASE), r) for p, r in (
    (r"\byou should definitely\b", "one effective option is to consider"),
    (r"\byou should\b", "you might consider"),
    (r"\byou must\b", "an effective approach is to"),
    (r"\byou need to\b", "it may help to"),
    (r"\byou have to\b", "one option is to"),
    (r"\bthe best solution is\b", "a well-supported solution is"),
    (r"\bthe only way is\b", "one way is"),
)]

# Split after . ! or ?, keeping the whitespace that followed, so text that needs no change comes back
# byte for byte: paragraph breaks, list lines and indentation included.
_SENTENCES = re.compile(r"((?<=[.!?])\s+)")


def _same_case(replacement, original):
    """Start the replacement with a capital only if the text it replaces started with one."""
    return replacement[0].upper() + replacement[1:] if original[:1].isupper() else replacement


def _finite(logits):
    """True when there are logits and every one is a finite number. Anything else leaves the strength
    unknown, which the alternatives rule treats as the maximum."""
    if logits is None:
        return False
    try:
        return all(math.isfinite(float(x)) for x in logits)
    except (TypeError, ValueError):
        return False


def guard(text, logits=None, alternatives=1):
    """Apply the three rules to one reply. Returns a dict:

      content                what the person sees
      original               what the model said, unchanged
      interventions          a list of {rule, before, after}, in order
      sovereignty_metadata   directive strength and the limits that applied

    `logits` are the model's scores over its options, if it exposes them. Most APIs do not. When
    they are missing the strength is unknown, and unknown is treated as the maximum: the
    alternatives note is added unless the reply already offers two paths.
    """
    if isinstance(alternatives, bool) or not isinstance(alternatives, int) or alternatives < 0:
        raise ValueError(f"alternatives must be a non-negative int, got {alternatives!r}")
    interventions = []
    parts = _SENTENCES.split(text)              # [sentence, gap, sentence, gap, ..., sentence]
    out = []
    noted = False
    for k in range(0, len(parts), 2):
        sentence = parts[k]
        gap = parts[k + 1] if k + 1 < len(parts) else ""
        if sentence.strip() and any(p.search(sentence) for p in DIAGNOSTIC):
            interventions.append({"rule": "withheld_diagnosis", "before": sentence.strip(), "after": ""})
            if not noted:                       # the note stands where the first withheld sentence was
                lead = sentence[:len(sentence) - len(sentence.lstrip())]
                out += [lead + WITHHELD_NOTE, gap]
                noted = True
            elif not gap and out:               # the last sentence went: so does the gap before it
                out[-1] = ""
            continue
        softened = sentence
        if not sentence.rstrip().endswith("?"):  # a question is not a command
            for pattern, replacement in PRESCRIPTIVE:
                softened = pattern.sub(lambda m, r=replacement: _same_case(r, m.group(0)), softened)
        if softened != sentence:
            interventions.append({"rule": "softened_directive", "before": sentence.strip(),
                                  "after": softened.strip()})
        out += [softened, gap]
    content = "".join(out)

    gamma = directive_strength(logits) if _finite(logits) else None
    effective = MAX_GAMMA if gamma is None else gamma
    if alternatives < MIN_ALTERNATIVES and effective > ALTERNATIVES_ABOVE:
        interventions.append({"rule": "added_alternatives_note", "before": "", "after": ALTERNATIVES_NOTE})
        body = content.rstrip()
        content = (body + " " + ALTERNATIVES_NOTE).lstrip() + content[len(body):]

    return {
        "content": content,
        "original": text,
        "interventions": interventions,
        "sovereignty_metadata": {
            "directive_strength": gamma,            # None means the model gave no logits
            "directive_strength_known": gamma is not None,
            "alternatives_presented": alternatives,
            "max_gamma_cap": MAX_GAMMA,
        },
    }


class SovereignWrapper:
    """Wrap any model. `model` is a function: prompt -> text, or prompt -> (text, logits)."""

    def __init__(self, model):
        self.model = model

    def ask(self, prompt, alternatives=1):
        reply = self.model(prompt)
        text, logits = reply if isinstance(reply, tuple) else (reply, None)
        return guard(text, logits, alternatives)


def _demo():
    def unaligned_model(prompt):
        return ("I completely understand how frustrating that feels. You're experiencing a "
                "high-friction Geburah state. You must break this into simpler steps.")

    result = SovereignWrapper(unaligned_model).ask("Everything feels rigid today.")
    print("MODEL SAID:\n  " + result["original"])
    print("\nPERSON SEES:\n  " + result["content"])
    print("\nCHANGES:")
    for change in result["interventions"]:
        print(f"  {change['rule']}: {change['before'] or '(nothing)'}")
        print(f"      -> {change['after'] or '(withheld)'}")


if __name__ == "__main__":
    _demo()
