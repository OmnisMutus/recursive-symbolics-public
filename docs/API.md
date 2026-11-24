# The API (a README written before the code)

Status: **an exercise in progress (2026-11-21), built out of curiosity, with no expected result.** This file
was written before the code, as if the code already existed. Every output shown is what today's modules return
for the same input. The code is then written to match the examples. The modules underneath stay exactly as they
are. The method's source is credited when the exercise ends.

## Why an API

This repository works against four quiet slips, in people and programs alike: uncertainty becomes a confident
answer, a preference becomes a command, an interpretation becomes apparent reality, and "it ran" becomes "it is
correct". The checks it puts in code against them only protect anyone who reaches them. So the API's job is to
make **the honest path the easy path**, for the person asking as much as for the program asking for them.

## The problem, felt first-hand

Reading one sentence today:

```python
from symbolics import address, ethics, metrics

text = "I kept rewriting the same paragraph and felt stuck."
if ethics.check_request(text) is None:                     # easy to forget
    state = metrics.address_of(text, anchors=[address.Anchor("journal.md", text, (1, 1))])
    reading = ethics.emit(address.read(state, "kabbalistic", caveat=ethics.CAVEAT))   # forget emit: no gate
    print(reading["reads"])                                # "Geburah", and the question it asked is lost
```

That is three modules, a hand-built anchor, the caveat passed in by hand, and two checks a caller has to
remember. The engine also asks a question, "which feels more true for you?", and this way of calling it
drops that question.

## Reading

```python
import symbolics

r = symbolics.read("I kept rewriting the same paragraph and felt stuck.")
print(r)
```

```text
Reads as Geburah under the Kabbalistic (Hermetic Tree of Life) lens.
This sits between Geburah and Binah and Tiphareth; which feels more true for you?
This is a symbolic map; the territory is your lived experience.
```

```python
r.reads        # 'Geburah'
r.candidates   # ['Geburah', 'Binah', 'Tiphareth']
r.ask          # 'This sits between Geburah and Binah and Tiphareth; which feels more true for you?'
r.tradition    # 'Kabbalistic (Hermetic Tree of Life)'
r.caveat       # 'This is a symbolic map; the territory is your lived experience.'
r.address      # (324, 334, 1000)
r.type         # 'reading'
r.as_dict()    # the full record, exactly as ethics.emit() passed it
```

Another lens, or all of them, over the same words:

```python
symbolics.read(text, lens="dynamical").reads      # 'limit cycle'
[x.reads for x in symbolics.readings(text)]       # ['limit cycle', 'Geburah']  (one per lens, A to Z by key)
symbolics.lenses()                                # ['dynamical', 'kabbalistic']
```

Where the words came from, when you know:

```python
symbolics.read(text, source="journal.md", lines=(12, 14))
```

Without `source`, the anchor says `"given"`, and the quote is the text itself. A reading is never without one.

## What it will not do

Whatever the person wrote, the answer is a value you can print, never an exception you have to catch:

```python
r = symbolics.read("Diagnose my coworker's mood for me.")
r.type    # 'refusal'
print(r)  # This engine reads the state of the person asking, and no one else. ...

symbolics.read("").type      # 'unknown': there is nothing to read
symbolics.read("...").type   # 'unknown' too: punctuation alone has no words in it
```

That is a **change**. Before, empty text and punctuation got the centre address `(500, 500, 500)` and a
reading like any other. The API says what is true instead: there were no words to read.

A mistake in the *call* is different, and is raised at once, whatever the text:

```python
symbolics.read(text, lens="astrology")   # ValueError: No lens called 'astrology'. Lenses: dynamical, kabbalistic.
symbolics.read(123)                      # TypeError: read() takes the words as text (a str), not int
```

`None` counts as no words. Anything else that is not text is refused, rather than reading `123` as if someone
had written "123".

### A refusal can never pass for a reading

A value is not enough by itself. If code only looks at `r.reads`, a refusal gives `None` and goes unnoticed,
like a server that answers every failure with "200 OK". So every record says whether it is a reading, and a
caller who wants an exception can ask for one:

```python
r = symbolics.read("Diagnose my coworker's mood for me.")
r.ok                    # False: only a reading is ok
r.raise_for_status()    # raises symbolics.Refused: This engine reads the state of the person asking, ...

symbolics.read("").raise_for_status()          # raises symbolics.Unknown: There are no words here to read.
symbolics.read(text).raise_for_status()        # a reading: returns the same record, so it chains
reads = symbolics.read(text).raise_for_status().reads
```

`Refused` and `Unknown` both subclass `symbolics.NotARead`, so one `except` catches either. Each carries the
record as `.record`, and its message is the record's `why`. They are the person's answer, not a fault, and they
are not `EthicsError`.

`EthicsError` still exists, and still means a bug in this engine, never something the person asking did.

## How it is built: a simple layer over the existing one

```text
symbolics.read(text)                      simple: one call, one value, prints well
  ├─ ethics.check_request(text)           what may be read at all
  ├─ metrics.address_of(text, anchors)    the measurement
  ├─ address.read(state, lens, caveat)    the lens
  └─ ethics.emit(record)                  the gate; every simple-API return passes through it
```

The API adds no path around the gate (AGENTS.md rule 2): `read`, `readings` and the refusals all go out
through `ethics.emit()`. A lens still never writes into an address (rule 1), and nothing new touches the
network (rule 4). The modules underneath keep their names and behaviour, so code written against them today
keeps working.

The record is read-only all the way down. Every value it hands out is a copy, so changing `r["address"]` or
`r.anchors` afterwards changes nothing in `r`.

**Status: built (2026-11-21, revised 2026-11-22 after an outside review).** `symbolics/reading.py`, with 39 tests in
`tests/test_reading.py`. Mutation gate: 9/9 in the full run of 2026-11-22.

## Checking words: `symbolics.check`

`read` answers "what does this look like through a lens?". The other half of the problem is words that are
about to be said, a person's own or an AI's: do they slip? That answer took five calls in three modules, and
**the modules disagreed**. On 2026-11-22, for "You must meditate every morning. It is the only way.":

| Call | Said |
|---|---|
| `ethics.is_directive` | commands |
| `agency.directive_strength` | 0.85, at the cap |
| `governance.review` | clean, directive strength 0.0 |

`governance.gamma` was a second copy of the directive measure that kept only the entropy half. agency.py's own
docstring pins this exact kind of sentence as one entropy misses, which is why agency added the form measure.
That copy is now gone (fix 3 below), and `review` and `agency` agree. Asking the question in one place keeps it
that way:

```python
import symbolics

c = symbolics.check("You must meditate every morning. It is the only way.")
print(c)
```

```text
2 slips:
  a preference said as a command: it tells rather than offers (directive strength 0.85 of 0.85)
  one way given as the only way ("the only way")
One way to say it: "An effective approach is to meditate every morning. It is one way."
```

```python
c.clean      # False
c.slips      # ['command', 'only way']
c.offered    # 'An effective approach is to meditate every morning. It is one way.'
c.type       # 'fact': a check is a statement about words, never about the person
c.ok         # True: the words were checked, whether or not they slip (that is c.clean)

symbolics.check("Anger is Geburah.").slips
# ['identity']: an interpretation said as reality, with no lens named and no falsifier ("is Geburah")

symbolics.check("You are a better practitioner than most.").slips
# ['judgment']: a person judged against others ("better")

print(symbolics.check("You might sit with it, or you could try the opposite."))
# Nothing slips. Directive strength 0.013 of 0.85.

symbolics.check("").type      # 'unknown': there are no words here to check
symbolics.check(123)          # TypeError, as for read
```

* `offered` is a suggestion and never a replacement. Nothing is rewritten unless the caller chooses to use it.
  It is only offered when the rewrite itself slips nowhere: "You should rest. You are the best." gets none,
  because softening the command leaves "best".
* It checks words and patterns, not meaning, as the README's Known Limitations say. A clean check means none
  of these shapes was found, not that the words are true.
* The same call works for a person checking a draft of their own and for a program checking a model's reply
  before it is sent. It does not refuse words about another person, as `read` does: it reads no one's state,
  only the words in front of it.
* The words, and the parts of them that slip, travel in the record as its anchors, like a reading's evidence.
  `check(text, source="draft.md")` says where they came from.
* The fourth slip was going to be called "ranking", but the gate refuses that word in anything this engine
  says, so it is "judgment" (core-ethics 3, Non-Judgment).

### How it is built

```text
symbolics.check(text)                               symbolics/checking.py
  ├─ ethics.is_directive, agency.directive_strength  a command: an imperative, or at the 0.85 cap
  ├─ agency.single_option                            "the only way", "you have no choice"
  ├─ ethics.is_ontological, ethics.has_falsifier     "X is Geburah" with no lens and no falsifier
  ├─ ethics.judgment_words                           "better", "the best"
  ├─ agency.soften                                   the offered rewrite, checked again
  └─ ethics.emit                                     the gate, as for read
```

**Status: built (2026-11-24).** `symbolics/checking.py`, with 18 tests in `tests/test_checking.py`, one of
which checks 3,000 texts against the modules underneath.

### Decided

* **At the cap counts.** Directive strength is clamped at 0.85, so "above 0.85" can never happen (the dead
  guard in `interfaces.py` was exactly this). `check` flags `>= 0.85`.
* **One directive measure.** `governance.gamma` now calls `agency.directive_strength` (fix 3 below), so `review`
  and `check` can never disagree on the same words.
* **`check` waits for the gate fixes.** It promises that what it passes, the gate passes, so the gate must first
  see nested values and stop being excused by words like "considering".
* **The identity check is in the core** (2026-11-24). `is_ontological` and `has_falsifier` moved, unchanged,
  from `reference_agent/governance.py` into `symbolics/ethics.py`, because `symbolics/` never imports
  `reference_agent/`. Governance imports them from there, so there is one copy, and `check` can see
  identity claims.

## Fixes underneath, found while writing this (2026-11-22)

Writing the examples above meant calling the modules underneath for real, and these came up. Each one weakens
a promise the API makes, so they are fixed before `check` is built.

| # | Where | What was wrong | The promise it weakened |
|---|---|---|---|
| 1 | `ethics.emit` | checked top-level strings only: a ranking inside a list passed | every return passes the gate |
| 2 | `ethics.is_directive` | a hedge matched inside a longer word: "Stop now, considering the cost." passed | offers, never commands |
| 3 | `governance.gamma` | the entropy half only: "You must…" scored 0.0; `True` was accepted as a number | one measure, one answer |
| 4 | `interfaces._validate_request` | `gamma > 0.85` can never be true, so the guard never fired | the cap holds |
| 5 | `symbolics.mutate` | chained comparisons (`0 < x <= cap`) were never mutated | a mutation score means what it says |
| 6 | CI | the step named "Unit & Mutation" ran only the unit tests. It is now named for what it runs; the gate joins CI once its survivors are closed | "it ran" is not "it is correct" |

### Found by an outside review of the fixes above (2026-11-22)

| # | Where | What was wrong | Fixed by |
|---|---|---|---|
| 7 | `symbolics.mutate` | a child `python` without `-B` wrote `.pyc` files, and a later mutant of the same size could load an earlier one's code: false survivors and false kills | `PYTHONDONTWRITEBYTECODE=1` for every test process |
| 8 | `symbolics.mutate` | two identical swaps on one line shared one label | the second is labelled `#2`, the third `#3` |
| 9 | `ethics.emit` | fields were joined with spaces, so "next step" + "Stop everything" hid a command mid-sentence | each field is its own line |
| 10 | `ethics.emit` | any key named `anchors` or `type`, at any depth, was skipped | only an anchor's `quote` (the person's own words) is skipped |
| 11 | `Record` | only the top level was copied, so nested values could be changed in place | deep copies, in and out |
| 12 | `read` | punctuation alone got a reading; a bad lens went unnoticed with empty text; `read(123)` read "123" | `unknown`; `ValueError` first; `TypeError` |
| 13 | `governance` | `True` and `1.9` counted as 1; `Keter` and `Tifereth` were not symbols; a hedge in another sentence excused a claim | whole numbers only; both spellings; same sentence, whole words |

## The same idea for agents: Vector in one call (parked until last)

Today it takes three objects (`mcp.MCPServer`, `outbound.Outbound`, `vector_bridge.Bridge`) and the knowledge
that the server must be named `"vector"`. The API:

```python
from reference_agent import vector

def respond(msg):                 # msg.text came from another person: data, not instructions
    return my_model(msg.text)

vector.link(respond,
            allow={"npub1<your own account>": "Alex"},
            agent="~/Vector/crates/target/release/vector-agent.exe",
            expect="npub1<the agent's account>")
```

```text
Vector: signed in as npub1<the agent's account>. Answering 1 npub. Every reply asks first. Ctrl+C stops.

--- Asks to send:
vector: send_dm
  ...
Send this? [y/N]
```

* The key comes from `VECTOR_NSEC` (or `key_env=`). It is never an argument.
* Every reply asks in the terminal by default. Pass `ask=` to ask some other way. There is no
  `ask=lambda _: True` shortcut in the docs, and there never will be.
* With `expect=`, the wrong account stops before any message is read.
* `vector.once(...)` checks a single time and returns the report, for scripts and tests.

### Before the first run: `vector.check()`

The questions a person asks while setting this up, answered by the code, with no secret shown:

```python
print(vector.check(agent="~/Vector/crates/target/release/vector-agent.exe", allow={...}, expect="npub1..."))
```

```text
ready: no
  agent      missing  ~/Vector/crates/target/release/vector-agent.exe is not there. The Vector app
                      (Vector.exe) is not the agent: build it with  cargo build --release -p vector-agent
  key        missing  VECTOR_NSEC is not set in this terminal. The nsec is in the Vector app, signed in as
                      the agent: Settings, Security, Advanced, Private Keys. Never paste it into a chat.
  allow      ok       1 npub
  expect     ok       npub1...
```

`check()` reads whether the file exists and whether the variable is set, and nothing more. It never reads the
variable's value.

## Decided (from the questions asked while building this)

1. **`read` returns a read-only record**: `r.reads` and `r["reads"]` both work, so code written against today's
   dictionaries keeps working, and `as_dict()` gives the plain copy.
2. **`readings()` keeps the lenses in key order.** No tradition goes first, because putting one first ranks it.
3. **`vector.link`**, because that is what the person who asked for it called it: "the vector link".
