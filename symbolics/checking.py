"""The API's other half: do these words slip, before they are said?

    import symbolics
    c = symbolics.check("You must meditate every morning. It is the only way.")
    print(c)

`read` answers "what does this look like through a lens?". `check` answers "do these words slip?", for a
person's own draft or a program's reply before it is sent. It asks the modules underneath, in one place, so
they cannot disagree:

    command     ethics.is_directive, or agency.directive_strength at the 0.85 cap
    only way    agency.single_option: one way given as the only way
    identity    ethics.is_ontological with no ethics.has_falsifier: an interpretation said as reality
    judgment    ethics.judgment_words: a person ranked against others

It checks words and patterns, not meaning. A clean check means none of these shapes was found, not that the
words are true. Every value it returns goes through ethics.emit(), like `read`.
"""
from . import agency, ethics
from .reading import GIVEN, Record

# One line for each slip, in the order they are checked: what slipped, then how it was seen.
_SAYS = {
    "command": "a preference said as a command: it tells rather than offers",
    "only way": "one way given as the only way",
    "identity": "an interpretation said as reality, with no lens named and no falsifier",
    "judgment": "a person judged against others",
}


class Check(Record):
    """What the gate passed for one check, read-only, like a reading's Record."""

    __slots__ = ()

    @property
    def ok(self):
        """True when the words were checked, whether or not they slip (that is `clean`)."""
        return self.type == "fact"

    @property
    def clean(self):
        """True when nothing slips."""
        return self._d.get("clean", False)

    @property
    def slips(self):
        """The names of the slips found, in the order they are checked."""
        return list(self._d.get("slips", []))

    @property
    def offered(self):
        """One way to say it that does not slip, or None. A suggestion, never applied for you."""
        return self._d.get("offered")

    @property
    def directive_strength(self):
        return self._d.get("directive_strength")

    def __str__(self):
        if self.type != "fact":
            return str(self.why or self.type)
        strength = f"Directive strength {self.directive_strength} of {agency.GAMMA_MAX}."
        if self.clean:
            return f"Nothing slips. {strength}"
        lines = [f"{len(self.slips)} slip{'s' if len(self.slips) > 1 else ''}:"]
        for name in self.slips:
            lines.append(f"  {_SAYS[name]} ({self._shown_by(name)})")
        if self.offered:
            lines.append(f'One way to say it: "{self.offered}"')
        if "command" not in self.slips:
            lines.append(strength)
        return "\n".join(lines)

    def _shown_by(self, name):
        """How a slip was seen: the strength for a command, the person's own words for the others."""
        if name == "command":
            return f"directive strength {self.directive_strength} of {agency.GAMMA_MAX}"
        return ", ".join(f'"{a["quote"]}"' for a in self._d["anchors"] if a.get("slip") == name)

    def __repr__(self):
        if self.type != "fact":
            return f"<{self.type}: {self.why}>"
        return f"<check: {', '.join(self.slips) or 'clean'}>"


def _found(text):
    """Each slip in the text, in the order of _SAYS, with the person's own words that show it. A command is shown
    by its directive strength instead, so its list is empty."""
    found = {}
    # At the cap counts: directive strength is clamped at 0.85, so it can never be above it.
    if ethics.is_directive(text) or agency.directive_strength(text) >= agency.GAMMA_MAX:
        found["command"] = []
    words = {
        "only way": agency.single_option(text),
        "identity": ethics.is_ontological(text) if not ethics.has_falsifier(text) else [],
        "judgment": ethics.judgment_words(text),
    }
    found.update((name, quotes) for name, quotes in words.items() if quotes)
    return found


def _offer(text):
    """The inherited humility filter's rewrite, if it changes the words and the result slips nowhere."""
    softened = agency.soften(text)
    if softened != text and not _found(softened):
        return softened
    return None


def check(text, source=None):
    """Do these words slip? Returns a Check: a fact about the words, or unknown when there are none."""
    if text is None:
        text = ""
    if not isinstance(text, str):
        raise TypeError(f"check() takes the words as text (a str), not {type(text).__name__}")
    if not any(ch.isalnum() for ch in text):
        return Check(ethics.emit(ethics.unknown("There are no words here to check.")))
    found = _found(text)
    # The words themselves, and the parts of them that slip, travel as anchors: they are the person's own words,
    # kept as evidence, so the gate does not judge them as this engine's. Nothing this engine wrote goes there.
    where = str(source or GIVEN)
    anchors = [{"source": where, "quote": text}]
    anchors += [{"source": where, "slip": name, "quote": q} for name, quotes in found.items() for q in quotes]
    return Check(ethics.emit({
        "type": "fact",
        "clean": not found,
        "slips": list(found),
        "offered": _offer(text) if found else None,
        "directive_strength": round(agency.directive_strength(text), 3),
        "max_gamma_cap": agency.GAMMA_MAX,
        "anchors": anchors,
    }))
