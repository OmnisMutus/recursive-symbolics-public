"""The symbolic address space: a point no tradition owns, and the lenses that read one.

The framework's own claim (Core Axiom, "The User's Choice") is that it supplies syntax and the user supplies
semantics. That is a seam, and this module is the seam:

    observable input -> address (computed) -> lens (chosen) -> reading (interpretation)

An address is three numbers from 0 to 1000. A lens turns an address into one tradition's words. The rules that
make the claim true rather than decorative:

- a lens may never write back into an address: read() takes an address and returns words, and nothing else;
- swapping lenses cannot move the address, so no reading is ever "what the state really is";
- every reading names the tradition it read from and carries its caveat, so "anger is Geburah" is not expressible.
  The engine can only say: at this address, the Kabbalistic lens reads Geburah.

The axes, chosen because each is computable from something observable:

    severity_mercy   0 restriction, cutting, boundary     1000 expansion, giving, dissolution
    descent          0 origin, undifferentiated           1000 manifest, particular, embodied
    entropy          0 repetitive, locked                 1000 sprawling, chaotic

Three axes, not ten. The ten Sephiroth are not axes; they are what one lens reads at a region of the space.
Where an address came from travels with it (`derivation`), and so does the evidence (`anchors`), because a
reading that cannot point at the words it came from is refused elsewhere in this engine.
"""
import dataclasses
import math
import re
import types

AXES = ("severity_mercy", "descent", "entropy")
LOW, HIGH = 0, 1000
MID = (LOW + HIGH) // 2
BOUNDARY = 90             # two candidate readings this close together are both offered, never one chosen silently


def clamp(value):
    """A number rounded to a whole one and held inside the space, 0 to 1000."""
    if isinstance(value, bool):
        raise TypeError("Address axis value must be numeric, not bool.")
    return max(LOW, min(HIGH, int(round(float(value)))))


@dataclasses.dataclass(frozen=True)
class Anchor:
    """The evidence a claim rests on: where it came from, and the words themselves."""
    source: str                     # a note path, a file, "spoken", whatever the caller can name
    quote: str
    lines: tuple = ()               # (first, last), 1-based, when the source has lines

    def as_dict(self):
        d = {"source": self.source, "quote": self.quote}
        if self.lines:
            d["lines"] = list(self.lines)
        return d


@dataclasses.dataclass(frozen=True)
class Address:
    severity_mercy: int
    descent: int
    entropy: int
    derivation: dict = dataclasses.field(default_factory=dict)      # axis -> how it was computed
    anchors: tuple = ()                                             # Anchor, the words behind it

    def __post_init__(self):
        for axis in AXES:
            value = getattr(self, axis)
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(f"{axis} must be a whole number from {LOW} to {HIGH}.")
            if not LOW <= value <= HIGH:
                raise ValueError(f"{axis} is {value}; the axes run from {LOW} to {HIGH}.")
        missing = [a for a in AXES if a not in self.derivation]
        if self.derivation and missing:
            raise ValueError(f"derivation given but silent about: {', '.join(missing)}. "
                             "Say how every axis was computed, or give none.")
        object.__setattr__(self, "derivation", types.MappingProxyType(dict(self.derivation)))
        object.__setattr__(self, "anchors", tuple(self.anchors))

    @property
    def point(self):
        """The three axis values, in AXES order."""
        return tuple(getattr(self, a) for a in AXES)

    def as_dict(self):
        d = {"type": "address", **{a: getattr(self, a) for a in AXES}}
        if self.derivation:
            d["derivation"] = dict(self.derivation)
        if self.anchors:
            d["anchors"] = [a.as_dict() for a in self.anchors]
        return d


def at(severity_mercy=MID, descent=MID, entropy=MID, derivation=None, anchors=()):
    """An address, clamped, with its derivation and evidence."""
    return Address(clamp(severity_mercy), clamp(descent), clamp(entropy),
                   dict(derivation or {}), tuple(anchors))


def distance(a, b):
    """How far apart two addresses are, in the space's own units (Euclidean over the three axes)."""
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a.point, b.point)))


def compose(*addresses, note=""):
    """Two or more demands on one state, as the framework's unmapped cross-operator interference (hidden-axioms
    7.3): the axes are summed around the middle and clamped, so expand and restrict at once land back near the
    centre rather than cancelling into nothing. The composition keeps every derivation and every anchor, because
    a composite reading has to be traceable to both sides."""
    if not addresses:
        raise ValueError("Give at least one address to compose.")
    values = [clamp(MID + sum(getattr(x, axis) - MID for x in addresses)) for axis in AXES]

    # Each axis keeps every side's account of itself, numbered by position: "1: ... | 2: ...".
    parts = {}
    for i, x in enumerate(addresses, 1):
        for axis, how in x.derivation.items():
            parts.setdefault(axis, []).append(f"{i}: {how}")
    derivation = {axis: " | ".join(hows) for axis, hows in parts.items()}
    for axis in AXES:
        derivation.setdefault(axis, f"composed from {len(addresses)} addresses")
    if note:
        derivation["note"] = note

    anchors = tuple(a for x in addresses for a in x.anchors)
    return Address(*values, derivation=derivation, anchors=anchors)


# ---------------------------------------------------------------- lenses
@dataclasses.dataclass(frozen=True)
class Lens:
    """One tradition's words for regions of the space. A table, a source and a date: adding a tradition is
    adding one of these, and the engine never learns a tradition, it reads one.

    `places` is {name: (severity_mercy, descent)}; entropy is reported, never used to choose a name, because no
    tradition in the framework places its names along a chaos axis.
    """
    tradition: str
    source: str
    dated: str
    places: dict
    note: str = ""

    def __post_init__(self):
        if not self.places:
            raise ValueError(f"The {self.tradition} lens has no places.")
        for name, where in self.places.items():
            if len(where) != 2 or not all(LOW <= v <= HIGH for v in where):
                raise ValueError(f"{self.tradition}: '{name}' sits outside the space at {where}.")


@dataclasses.dataclass(frozen=True)
class Sephirah:
    """One Sephirah's names: the one this code uses, and every English spelling of it."""

    name: str
    spellings: tuple


# Each Sephirah once, the way a name is defined once in code and its aliases point to it. English spells the
# Hebrew several ways: the Golden Dawn wrote Kether and Tiphareth, modern romanisation writes Keter and Tiferet,
# and this repository uses both. Every spelling in a row names the same Sephirah; the first is `name`.
# Daath is listed last: it is drawn on some Trees but is not one of the ten. The Hebrew each row spells, and what
# the word means, are in docs/SEPHIROTH.md: support for the reader, never shown as output.
SEPHIROTH = tuple(Sephirah(row[0], row) for row in [
    ("Kether", "Keter"),
    ("Chokmah", "Chochmah", "Chokhmah", "Hokhmah", "Hokmah"),
    ("Binah",),
    ("Chesed", "Hesed", "Khesed"),
    ("Geburah", "Gevurah", "Gebura", "Gevura"),
    ("Tiphareth", "Tifereth", "Tiferet", "Tiphereth", "Tipheret"),
    ("Netzach", "Netsach", "Nezach"),
    ("Hod",),
    ("Yesod",),
    ("Malkuth", "Malchut", "Malkhut", "Malchuth"),
    ("Daath", "Da'ath", "Da’ath", "Da'at", "Daat"),
])

# The Hebrew word each name spells, so a Sephirah written in Hebrew is recognised too. This is for reading what
# someone wrote, never for output: the code always answers with the English name, because not everyone reads
# Hebrew. The same table, with what each word means, is in docs/SEPHIROTH.md.
HEBREW_SPELLINGS = {
    "כתר": "Kether", "חכמה": "Chokmah", "בינה": "Binah", "חסד": "Chesed", "גבורה": "Geburah",
    "תפארת": "Tiphareth", "נצח": "Netzach", "הוד": "Hod", "יסוד": "Yesod", "מלכות": "Malkuth", "דעת": "Daath",
}

# Hebrew vowel points and cantillation marks. They sit on the letters, so גְּבוּרָה and גבורה are one word once
# they are taken off. Hebrew punctuation in the same Unicode block (maqaf, paseq, sof pasuq) is kept.
_HEBREW_MARKS = re.compile("[֑-ׇֽֿׁׂׅׄ]")


def without_hebrew_marks(text):
    """The text with Hebrew vowel points and cantillation taken off; everything else is left as it was."""
    return _HEBREW_MARKS.sub("", text)


def sephirah_named(word):
    """The Sephirah this word spells, in any English spelling and any case, or in Hebrew; None if it spells none."""
    word = without_hebrew_marks(word or "").strip()
    word = HEBREW_SPELLINGS.get(word, word).casefold()
    for s in SEPHIROTH:
        if word in (spelling.casefold() for spelling in s.spellings):
            return s
    return None


# The Tree as it is drawn: the three pillars across, the ten numbers down. Severity on the left, Mercy on the
# right, the middle pillar between them; Kether first and Malkuth tenth. Nothing here is a claim about what any
# Sephirah means, only where the diagram puts it.
_PILLAR = {"severity": 150, "middle": MID, "mercy": 850}
_TREE = [("Kether", "middle", 1), ("Chokmah", "mercy", 2), ("Binah", "severity", 3),
         ("Chesed", "mercy", 4), ("Geburah", "severity", 5), ("Tiphareth", "middle", 6),
         ("Netzach", "mercy", 7), ("Hod", "severity", 8), ("Yesod", "middle", 9), ("Malkuth", "middle", 10)]

KABBALISTIC = Lens(
    tradition="Kabbalistic (Hermetic Tree of Life)",
    source="the Tree as drawn in the Golden Dawn and Thelemic sources: three pillars, ten Sephiroth in order",
    dated="2026-11-08",
    places={name: (_PILLAR[pillar], clamp((level - 1) / 9 * HIGH)) for name, pillar, level in _TREE},
    note="Position on the diagram only. Which Sephirah a state 'is' is not a question this engine answers.",
)

DYNAMICAL = Lens(
    tradition="dynamical systems",
    source="Mathemathical-foundation.md: fixed points, limit cycles, strange attractors",
    dated="2026-11-08",
    places={"fixed point": (MID, 100), "limit cycle": (MID, MID), "strange attractor": (MID, 900),
            "contraction": (120, MID), "diffusion": (880, MID)},
    note="A reading of the state's shape, not a measurement of a trajectory: that needs a sequence, not a point.",
)

LENSES = {"kabbalistic": KABBALISTIC, "dynamical": DYNAMICAL}


def _lens(lens):
    """A Lens, given one or the name of one ("kabbalistic", "dynamical", any case)."""
    if not isinstance(lens, str):
        return lens
    try:
        return LENSES[lens.casefold()]
    except KeyError:
        raise ValueError(f"No lens called '{lens}'. Lenses: {', '.join(sorted(LENSES))}.") from None


def read(address, lens=KABBALISTIC, caveat=None):
    """What one lens reads at an address. Returns a reading, never a verdict.

    Two names closer together than BOUNDARY are both offered, in the framework's own words (core-ethics 4):
    the engine asks which feels true rather than choosing for the person.
    """
    lens = _lens(lens)
    here = (address.severity_mercy, address.descent)
    # Nearest first; a tie in distance goes to the name that sorts first, so the same address always reads the same.
    ranked = sorted((math.dist(here, where), name) for name, where in lens.places.items())
    nearest_distance, nearest = ranked[0]
    candidates = [name for d, name in ranked if d - nearest_distance <= BOUNDARY]
    out = {"type": "reading", "tradition": lens.tradition, "source": lens.source, "lens_dated": lens.dated,
           "reads": nearest, "candidates": candidates, "distance": round(nearest_distance, 1),
           "entropy": address.entropy, "address": address.as_dict(),
           "anchors": [a.as_dict() for a in address.anchors]}
    if len(candidates) > 1:
        out["ask"] = (f"This sits between {' and '.join(candidates)}; which feels more true for you?")
    if lens.note:
        out["lens_note"] = lens.note
    if caveat:
        out["caveat"] = caveat
    return out


def readings(address, lenses=None, caveat=None):
    """Several traditions over one address, each worked out on its own so that no reading can colour another
    (the isolation the framework's anti-echo policy asks for, applied inside a single call). A lens that fails
    carries its own error and the others still stand."""
    out = []
    for key in (lenses or sorted(LENSES)):
        try:
            out.append(read(address, key, caveat=caveat))
        except Exception as e:                      # one tradition's broken table is not the others' problem
            out.append({"type": "unknown", "tradition": str(key), "why": f"{type(e).__name__}: {e}"})
    return out
