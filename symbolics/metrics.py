"""The measurement layer: observables in, an address out.

address.py defines a space; this module is the only thing that puts a point in it from something observed. The
observables are the ones Computational Kabbalah names:

    section 1   latency, read as a complexity class, relative to the person's own baseline and never absolute
    section 2   symbolic entropy H_s of the text itself
    (and)       the keyword centroids of the framework's own sandbox, which score a text against each Sephirah

INHERITED. SEPHIROT_CENTROIDS and the scoring are the framework's own, kept to the formula: cosine similarity
between token counts and centroid counts, plus 0.15 per token that shares a four-letter stem with a centroid
word, capped at 1.0. One thing is deliberately left out: the reference implementation multiplies each score by a
weight its learning engine has accumulated over past sessions. Here scores are reproducible, so the same text
always gives the same address, and a stateful weight would make an address depend on history nobody can inspect.
With the weights at their defaults, which is where a fresh engine starts, the two agree exactly.

A LIMITATION THAT HAS TO BE STATED, BECAUSE THE ARCHITECTURE CLAIMS OTHERWISE. address.py's seam says an address
is tradition-free and a lens is the interpretation. That holds for everything downstream of this module. It does
not hold for the measurement itself: the only derivation available today runs through a keyword table named
after the Sephiroth, and the pillars and levels below are the Tree's. So the axes are tradition-neutral in what
they mean, and tradition-derived in how they are currently computed, and every address this module builds says
so in its own derivation. A second, independent derivation (one that does not pass through a Kabbalistic table)
is the thing that would make the seam true at both ends.
"""
import math
import re
import statistics
from collections import Counter

from . import address

# The framework's own centroids, unchanged.
SEPHIROT_CENTROIDS = {
    "Keter": ["crown", "source", "will", "direction", "origin", "pure", "intent", "primary", "primal", "infinite",
              "monad", "purpose", "teleos", "zenith", "supreme"],
    "Chokmah": ["wisdom", "vision", "quicksort", "pivot", "idea", "flash", "intuition", "spark", "creative",
                "genius", "inspiration", "swift", "eureka", "breakthrough"],
    "Binah": ["understanding", "structure", "architecture", "constraint", "logic", "container", "matrix", "format",
              "rule", "framework", "boundary", "system", "schema"],
    "Daath": ["abyss", "cavity", "hole", "gap", "paradox", "void", "crisis", "anomaly", "lag", "exception", "trap",
              "mystery", "confused", "stuck", "lost", "dissonance"],
    "Chesed": ["expansion", "flow", "unbounded", "endless", "grace", "generous", "abundance", "kindness", "mercy",
               "growth", "freedom", "vast", "radiant", "open"],
    "Geburah": ["rigid", "stuck", "restriction", "judgment", "severe", "harsh", "paralysis", "rules", "strict",
                "anger", "critical", "cut", "block", "burnout", "stress"],
    "Tifereth": ["balance", "harmony", "integration", "beauty", "synthesis", "centered", "heart", "peace",
                 "coherence", "merge", "weave", "calm", "alignment", "equilibrium"],
    "Netzach": ["grind", "persistence", "endurance", "repeat", "victory", "stubborn", "linear", "passion", "drive",
                "continuous", "keep", "struggle", "grit", "hustle"],
    "Hod": ["detail", "documentation", "meticulous", "process", "syntax", "craft", "precise", "specificity",
            "step", "code", "bug", "trace", "fix", "audit", "refactor"],
    "Yesod": ["foundation", "subconscious", "buffer", "habit", "staging", "queue", "reflection", "dream", "mirror",
              "memory", "latent", "psychological", "storage", "cache"],
    "Malkuth": ["hungry", "eat", "food", "body", "tired", "sleep", "physical", "manifestation", "action", "output",
                "hardware", "execution", "world", "sensory", "pain", "exhausted"],
}
STEM_HIT = 0.15
STEM = 4

# Where the measurement places each name. The Tree's own geometry: Severity on the left, Mercy on the right, and
# the numbers in order down the middle. Da'ath has no number, so it sits with Binah's level on the middle pillar.
PILLAR = {"Binah": 0, "Geburah": 0, "Hod": 0,
          "Keter": 1, "Daath": 1, "Tifereth": 1, "Yesod": 1, "Malkuth": 1,
          "Chokmah": 2, "Chesed": 2, "Netzach": 2}
PILLAR_AT = {0: 150, 1: address.MID, 2: 850}
LEVEL = {"Keter": 1, "Chokmah": 2, "Binah": 3, "Daath": 3, "Chesed": 4, "Geburah": 5, "Tifereth": 6,
         "Netzach": 7, "Hod": 8, "Yesod": 9, "Malkuth": 10}

CAVEAT_LATENCY = ("Latency is a proxy. A long pause is contemplation, an interruption, or a cat on the keyboard, "
                  "and this cannot tell them apart.")
CAVEAT_DERIVATION = ("Computed through a keyword table named after the Sephiroth, so the measurement is "
                     "tradition-derived even though the axis is not.")


def address_tokens(text):
    """The words of a text, lower-cased, in order."""
    return re.findall(r"\b\w+\b", (text or "").lower())


def _cosine(a, b):
    """How alike two word-count tables are: 1.0 when they point the same way, 0.0 when they share no word."""
    dot = sum(a[w] * b[w] for w in set(a) & set(b))
    size_a = math.sqrt(sum(v ** 2 for v in a.values()))
    size_b = math.sqrt(sum(v ** 2 for v in b.values()))
    return dot / (size_a * size_b) if size_a and size_b else 0.0


def scores(text):
    """Each Sephirah's score for a text: the framework's own measure, without the learning weight.

    One deliberate difference from the framework's reference implementation (2026-11-21): a stem hit needs both
    the token and the centroid word to have at least STEM letters. The reference compared prefixes both ways with
    no length check, so a one-letter word such as "I" was a prefix of every centroid word starting with "i" and
    scored Keter, Chokmah and Tifereth on its own. Exact matches of short words still count, through the cosine.
    tests/test_metrics.py keeps the reference fixture and checks this difference against it, text by text.
    """
    tokens = address_tokens(text)
    counts = Counter(tokens)
    out = {}
    for name, centroid in SEPHIROT_CENTROIDS.items():
        cosine = _cosine(counts, Counter(centroid))
        stems = 0.0
        for t in tokens:
            # With both words at least STEM letters long, "one starts with the other's stem" is one test.
            if len(t) >= STEM and any(len(w) >= STEM and t[:STEM] == w[:STEM] for w in centroid):
                stems += STEM_HIT
        out[name] = round(min(1.0, cosine + stems), 3)
    return out


def entropy(text):
    """Symbolic entropy H_s, normalized to 0-1000 for the address space.

    0 is one token repeated (nothing new); 1000 is every token distinct. This is the quantity agency.py's
    inherited gamma is one minus, except that gamma is clamped at 0.85 and this is not, because an axis should
    not inherit a ceiling meant for a directivity budget.
    """
    tokens = address_tokens(text)
    if len(tokens) <= 1:
        return address.MID            # nothing to measure; the middle says so without pretending
    counts = Counter(tokens)
    if len(counts) == 1:
        return address.clamp(0)       # one word repeated: nothing new
    probs = [c / len(tokens) for c in counts.values()]
    h = -sum(p * math.log2(p) for p in probs)
    return address.clamp(h / math.log2(len(counts)) * address.HIGH)    # divided by the most it could be


def _weighted_average(pairs):
    """The average of (value, score) pairs, each value weighted by its score; the middle when nothing scored."""
    pairs = [(value, score) for value, score in pairs if score > 0]
    if not pairs:
        return address.MID
    total = sum(score for _, score in pairs)
    return address.clamp(sum(value * score for value, score in pairs) / total)


def severity_mercy(score_map):
    """Where the scored names sit across the pillars, weighted by their scores."""
    return _weighted_average((PILLAR_AT[PILLAR[n]], s) for n, s in score_map.items())


def descent(score_map):
    """How far down the Tree the scored names sit, weighted by their scores: origin at 0, manifest at 1000."""
    return _weighted_average(((LEVEL[n] - 1) / 9 * address.HIGH, s) for n, s in score_map.items())


def address_of(text, anchors=()):
    """An address for a piece of text, with how every axis was derived and the words it rests on."""
    s = scores(text)
    named = sorted(((v, k) for k, v in s.items() if v > 0), reverse=True)
    top = ", ".join(f"{k} {v}" for v, k in named[:3]) or "nothing scored"
    return address.at(
        severity_mercy=severity_mercy(s),
        descent=descent(s),
        entropy=entropy(text),
        derivation={
            "severity_mercy": f"scores across the pillars ({top}). {CAVEAT_DERIVATION}",
            "descent": f"scores down the levels ({top}). {CAVEAT_DERIVATION}",
            "entropy": f"symbolic entropy of {len(address_tokens(text))} tokens",
        },
        anchors=anchors,
    )


# ---------------------------------------------------------------- latency, as Computational Kabbalah reads it
CLASSES = (("O(1)", "Chesed", "instant, unimpeded"),
           ("O(log n)", "Tifereth", "balanced deliberation"),
           ("O(n)", "Netzach", "a linear slog, deep processing or saturation"),
           ("O(n^2)", "Geburah", "stalling or repeating; a stuck state"))


def latency(seconds, baseline=None):
    """A pause, read as a complexity class relative to the person's OWN baseline, never in absolute seconds.

    `baseline` is the median of their earlier pauses; given a list of pauses, the median of those. Returns the
    class, the Sephirotic reading Computational Kabbalah section 1 gives it, and the caveat, which travels with
    it because the number means much less than it looks like it does.
    """
    if isinstance(seconds, bool) or isinstance(baseline, bool):
        raise TypeError("latency arguments must be numeric, not bool.")
    if isinstance(seconds, (list, tuple)):
        if not seconds:
            raise ValueError("Give at least one pause, in seconds.")
        if any(isinstance(s, bool) for s in seconds):
            raise TypeError("latency pauses must be numeric, not bool.")
        baseline = baseline if baseline is not None else statistics.median(seconds)
        seconds = seconds[-1]
    if baseline in (None, 0):
        raise ValueError("A latency reading needs the person's own baseline; absolute seconds mean nothing here.")
    ratio = float(seconds) / float(baseline)
    index = 0 if ratio <= 1.2 else 1 if ratio <= 2.0 else 2 if ratio <= 4.0 else 3
    name, reading, what = CLASSES[index]
    return {"type": "fact", "class": name, "ratio": round(ratio, 2), "reads_as": reading, "means": what,
            "method": "the person's own median pause, not absolute seconds", "caveat": CAVEAT_LATENCY}
