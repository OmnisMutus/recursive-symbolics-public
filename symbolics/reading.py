"""The API: one call from words to a reading, with every check the layers below require.

    import symbolics
    r = symbolics.read("I kept rewriting the same paragraph and felt stuck.")
    print(r)

`read` does, in order, what a caller of the modules underneath has to remember to do: check the request
(ethics.check_request), measure (metrics.address_of), read through a lens (address.read, with the caveat), and
pass the result through the gate (ethics.emit). Every value it returns has gone through ethics.emit(). There is no
other way out of this module.

The answer is always a value: a reading, a refusal, or unknown. EthicsError still means a bug in this engine,
never something the person asking did, so it is not caught here.
"""
import copy
import re
from collections.abc import Mapping

from . import address, ethics, metrics

GIVEN = "given"         # the anchor's source when the caller does not say where the words came from


class NotARead(Exception):
    """Raised by raise_for_status() when the answer is not a reading. This is the person's answer, not a fault
    in the engine (that is ethics.EthicsError). The record is kept as .record."""

    def __init__(self, record):
        super().__init__(record.why or record.type)
        self.record = record


class Refused(NotARead):
    """The request was refused, for example because it asks about another person."""


class Unknown(NotARead):
    """There was nothing this engine could read."""


def _field(name, empty=None):
    """A read-only attribute for one field of the record: a copy, so changing it changes nothing in the record."""
    return property(lambda self: copy.deepcopy(self._d.get(name, empty)))


class Record(Mapping):
    """What the gate passed, read-only. `r.reads` and `r["reads"]` are the same value.

    Read-only all the way down: the record keeps its own deep copy, and every value handed out is a copy too, so
    changing r["address"] or r.anchors afterwards changes nothing in r. (2026-11-22: the first version copied only
    the top level, and a nested list or dict could be changed in place. An outside review found it.)
    """

    __slots__ = ("_d",)

    def __init__(self, emitted):
        object.__setattr__(self, "_d", copy.deepcopy(dict(emitted)))

    def __setattr__(self, name, value):
        raise AttributeError("a reading is read-only")

    def __getitem__(self, key):
        return copy.deepcopy(self._d[key])

    def __iter__(self):
        return iter(self._d)

    def __len__(self):
        return len(self._d)

    def as_dict(self):
        """A plain copy of the record, exactly as ethics.emit() passed it."""
        return copy.deepcopy(self._d)

    # the fields people reach for; None (or an empty list) where this kind of record has no such field
    type = _field("type")
    reads = _field("reads")
    candidates = _field("candidates", [])
    ask = _field("ask")
    tradition = _field("tradition")
    source = _field("source")
    caveat = _field("caveat")
    anchors = _field("anchors", [])
    why = _field("why")

    @property
    def ok(self):
        """True only for a reading, so a refusal can never pass for one."""
        return self.type == "reading"

    def raise_for_status(self):
        """Return this record if it is a reading; otherwise raise Refused or Unknown."""
        if self.ok:
            return self
        if self.type == "refusal":
            raise Refused(self)
        raise Unknown(self)

    @property
    def address(self):
        """The measured point, (severity_mercy, descent, entropy), or None."""
        a = self._d.get("address")
        return tuple(a[axis] for axis in address.AXES) if a else None

    def __str__(self):
        if self.type == "reading":
            lines = [f"Reads as {self.reads} under the {self.tradition} lens."]
            if self.ask:
                lines.append(self.ask)
            lines.append(self.caveat)
            return "\n".join(lines)
        return str(self.why or self.type)

    def __repr__(self):
        if self.type == "reading":
            return f"<reading: {self.reads}, {self.tradition}>"
        return f"<{self.type}: {self.why}>"


def lenses():
    """The lenses there are, by the name `read` takes."""
    return sorted(address.LENSES)


def _measured(text, source, lines):
    """The request check and the measurement, shared by read and readings. Returns (record, None) when there is
    nothing to read, or (None, state)."""
    if text is None:
        text = ""
    if not isinstance(text, str):
        # a caller's mistake, said plainly, rather than reading str(123) as if someone had written "123"
        raise TypeError(f"read() takes the words as text (a str), not {type(text).__name__}")
    refused = ethics.check_request(text)
    if refused is not None:
        return Record(ethics.emit(refused)), None
    if not re.search(r"\w", text):
        # no letters or digits at all: "", "   " and "..." are all nothing to read
        return Record(ethics.emit(ethics.unknown("There are no words here to read."))), None
    anchor = address.Anchor(str(source or GIVEN), text, tuple(lines or ()))
    return None, metrics.address_of(text, anchors=[anchor])


def read(text, lens="kabbalistic", source=None, lines=None):
    """One lens over the words. Returns a Record: a reading, a refusal, or unknown."""
    # A misspelt lens is the caller's mistake whatever the text is, so it is caught first, every time.
    if isinstance(lens, str) and lens.casefold() not in address.LENSES:
        raise ValueError(f"No lens called '{lens}'. Lenses: {', '.join(lenses())}.")
    done, state = _measured(text, source, lines)
    if done is not None:
        return done
    return Record(ethics.emit(address.read(state, lens, caveat=ethics.CAVEAT)))


def readings(text, source=None, lines=None):
    """Every lens over the same words, in lens-name order, so that no tradition goes first. A refusal or unknown
    is returned once, as a list of one."""
    done, state = _measured(text, source, lines)
    if done is not None:
        return [done]
    return [Record(ethics.emit(r)) for r in address.readings(state, caveat=ethics.CAVEAT)]
