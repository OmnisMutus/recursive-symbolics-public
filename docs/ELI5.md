# Recursive Symbolics, explained simply

This is the whole repository in plain words. No background needed. Each section says what a part is, the
everyday picture that helps, and where it lives, so you can go and look.

---

## The one-sentence version

It is a toolkit that helps a person and a program **not fool themselves or each other**, built so that the
rules are checked by code rather than promised in a document.

---

## The problem it works on

Everyone, people and AIs alike, slips in the same four ways: being unsure but sounding sure, turning a wish into
an order, mistaking an opinion for a fact, and thinking "it ran" means "it works". An eager AI helper does it to
please you; that is called **sycophancy**. Tell one that some coincidences feel like a sign, and it may agree
that they are, that you are special, and that it understands you like nobody else. That feels like being
understood, but nothing was checked. People do it to themselves all the time: when an
idea feels right to them, they treat it as if it had been checked.

The usual fix is a stern guard that blocks things. That stops some harm, but it also takes the decision away from
you.

This project tries a third way:

- **Truth over pleasing.** A claim only counts if something independent checked it.
- **Nobody bosses anybody.** The system *offers* readings with caveats and alternatives. It never orders you
  around and never ranks you against other people.
- **Facts and opinions are kept apart**, so an interpretation can never quietly rewrite what was measured.

---

## How a reading is made: the one-way door

Think of a thermometer and a weather presenter.

1. The **thermometer** measures. In the code this measurement is an **Address**: three numbers, fixed once made.
   (`symbolics/metrics.py` measures, `symbolics/address.py` holds the Address.)
2. A **lens** is the presenter: one way of describing what the numbers mean, from one tradition. A lens can read
   the thermometer, but it can **never change the reading**. The door only opens one way. Swap the presenter and the
   temperature stays the same.
3. Before anything reaches you it passes a **gate** (`symbolics/ethics.py`). The gate checks that the reading:
   - says it is only one reading (a caveat),
   - names the tradition and the source it came from,
   - points at the exact words it was based on,
   - does not rank you, and does not give you orders.

   If any of that is missing, the gate refuses.

Two answers are always allowed: **"unknown"** and **"paradox"**. Being honestly unsure is a valid result here, not a
failure.

There is one more rule: **it only reads the person asking.** Ask it to diagnose your friend, and it refuses.

**Being honest about the gate:** it checks words and sentence patterns, not meaning. It catches every trick it has
been shown (they are pinned in the tests), but a new way of phrasing an order can still slip through. It also
refuses a few harmless sentences. Both are written down in the README under "Known Limitations".

---

## The push meter: how bossy is a sentence?

Some sentences push ("Do this now."). Some leave room ("One option is..."). The project measures that push and calls
it **directive strength**, a number from 0 to 1. It is capped at **0.85**, so the system can suggest strongly but can
never reach a pure command. When a reply gets close to the cap, alternatives are added.

You can also ask for a *stricter* cap, say 0.5. Then a pushy reply is softened and given alternatives sooner, and if
it is still too pushy after that, it is **held back**: you get a short note saying so, instead of the reply. The 0.85
is written down in exactly one place, so it cannot quietly end up different in two parts of the code.

The meter counts word patterns, not real pressure, so it is a rough guide, not a lie detector.

Where: `symbolics/agency.py`.

---

## How the project decides something is true

This is the heart of it. Imagine a school with strict marking rules.

| Mark | What it means |
|---|---|
| **VERIFIED** | A test compared the answer with an independent source (a real library, a published value, or a sum done by hand), tried the tricky edge cases, *and* was shown to fail when someone broke the code on purpose |
| **RAN_ONLY** | The code ran without crashing. That is all. It is never called "working" |
| **FAILED** | A test ran and failed |
| **MISSING** | The file is not there |

The rule above all others: **a report must never be stronger than the evidence behind it.**

Where: `STANDARD.md`.

### Breaking things on purpose (mutation testing)

How do you know a smoke alarm works? You hold a match under it.

`symbolics/mutate.py` does that to the code. It makes one tiny change at a time, such as turning `<` into `<=` or
`+` into `-`, and runs the tests. If the tests still pass, they were not really checking that spot. That spot is a
**survivor**, and it means a test is missing.

Some changes cannot make any difference (like changing a rule for a case that can never happen). Those are listed,
each with the reason, in `architecture/mutation_guards.json`, so anyone can argue with the reason.

### The claims ledger

A **ledger** is a notebook that sorts claims into three piles: **VERIFIED** (a test backs it), **FAILED** (a test
contradicts it) and **UNTESTABLE** (nobody can check this, and it says so out loud). A ledger where *everything* is
untestable refuses to call itself a success.

Where: `symbolics/ledger.py`.

---

## The diary that can only grow

`LIBER_0.md` is the project's diary: what was tried, what actually happened, and what was learned, including every
mistake. Its rule: **you may add pages, but never tear one out or rewrite it.** A mistake is fixed by writing a new
entry, so the record of having been wrong stays.

Two checks hold it to that:

- `symbolics/record.py` reads the diary's history in git and complains if any old line was changed.
- `symbolics/breaches.py` looks at every entry that says FAILED or CORRECTED and checks that it names the test now
  guarding against the same mistake. A mistake that left no guard behind is flagged.

`OBSERVATIONS.md` holds longer dated notes in plain prose.

---

## The self-checks (the robot that checks the robots)

The project checks *itself*, every time, with small programs. Each prints a clear yes or no.

| Command | Plain question it answers |
|---|---|
| `python -m symbolics.conformance` | Does the code still obey the licence's rules (no network, no ranking, self-only, the 0.85 cap)? |
| `python -m symbolics.layers` | Does every file the project map mentions really exist, and do its quoted promises still match the README word for word? |
| `python -m symbolics.outgoing` | Is anyone about to publish a private file path by accident? |
| `python -m symbolics.record` | Has the diary only ever grown? |
| `python -m symbolics.breaches` | Does every recorded mistake name its guard? |
| `python -m unittest discover -s tests` | Do all the tests pass? |

There is also a **leak scan** (`tests/test_sanitization_audit.py`) that looks for private names using a list kept
*off* the internet, because publishing a list of secret words would publish the secrets.

**CI** (`.github/workflows/ci.yml`) runs all of this on GitHub every time someone pushes, on a clean Linux machine.
That matters: a clean machine finds things your own computer hides, such as a library you happen to have installed.

---

## The map of the project

`architecture/` holds the project's description of itself, in a form a program can check:

- `layers.json`: which file does which job, arranged in layers named after the Kabbalistic Tree of Life, each with
  a plain role (Intent, Design, Expansion, Boundary, and so on). The names are a map for people, not a claim about
  how code works.
- `intent.json`: the project's purpose and promises, each **copied word for word** from the README. If someone
  rewords a promise in the README, a check fails until the two agree again.
- `guards.json`: notes about diary entries that sit *beside* the diary, because the diary itself cannot be edited.
- `symbolic_api.json`: the vocabulary of symbols (spheres, paths, letters, correspondences). Reference only.

---

## The examples (start here if you code)

`examples/` holds two small, complete programs:

- an **algebra simplifier** that turns `(x + 0) * 1 + y - y + --x` into `2 * x`, one rule at a time, and then
  checks the answer by plugging in numbers;
- a **logic simplifier** that does the same for true/false formulas and checks the answer against every possible
  combination.

`python examples/quickstart.py` runs everything end to end. These show the pattern you would copy
to plug in your own rules: small steps, a limit on how many, a check that the answer really is right.

---

## The engines

`engines/` holds standalone programs that sit beside the core:

- **Sovereign wrapper**: sits between an AI model and a person. It holds back sentences that tell you what you are
  feeling as if it were fact, softens orders into options, and adds "there are other readings" when a reply pushes
  only one path. The original reply is always kept beside the edited one.
- **Safe memory boundary**: refuses a memory request whose size would overflow a number and wrap around, a classic
  security bug.
- **Attractor engine**: tracks whether a repeated process settles down, loops, or runs away. Needs NumPy.
- **Text sandbox**: an interactive toy that scores text against the ten spheres. Try `/eval your text here`.

---

## The tools for AI agents

Three folders apply the same honesty rules to an AI agent that is doing work:

### `reference_agent/`: the approval gate

Picture a parent holding the "send" button on a child's message. Every tool call that would **send, post or change
something other people can see** is shown in full and waits for a human's yes. A tool the gate has never heard of
counts as "sends", to be safe. Files can only be sent from folders on an approved list, checked before anyone is
even asked. Every decision is written to a log.

It also has an **honest test-result reader**: it only says "green" when the test runner's own words are
unambiguous, and otherwise says "unclear" and why (something was skipped, nothing ran, a library was missing).

### `mcp-workspace/`: a memory that keeps its receipts

An AI agent forgets everything between sessions. This Go program gives it a notebook, with one rule: **every note
must quote the exact lines of the file it is about.** When the agent comes back, each note is re-checked against
the file:

- **FRESH**: the file has not changed.
- **INTACT**: the file changed elsewhere, but the quoted lines are still exactly there.
- **MOVED**: the quote is still in the file, on different lines.
- **BROKEN**: the quote is gone, so the note can no longer be trusted.
- **GONE**: the file itself is gone.

FRESH means the evidence is unchanged, *not* that the note was right.

### `athanor/`: looking inside the model

You cannot easily ask a model *why* it behaves a certain way. athanor lets you experiment instead: make a copy of a
local model file, switch off one of its "experts" or turn one part up or down, test the copy, then undo. It never
touches the original, saves the old bytes before every change, and can recover if the computer crashes halfway
through.

---

## The practice corpus

`corpus/` is the training ground where the testing habits were learned: 24 practice programs (machine learning, a
peer-to-peer network node, a 3D renderer, a drone controller and more), each checked against independent answers.

On top of that sits a **symbolic layer**: ideas from Kabbalah and dynamical systems, held to the same standard
wherever that is possible, and openly marked **untestable** where it is not. The corpus keeps three kinds of claim
strictly apart:

- **A**: what a tradition says (checkable as "the text says this");
- **B**: what can be proven in the code's own maths (the only kind the tests check);
- **C**: claims about mind or reality itself, which no code can test, and which are named as such and set aside.

New to it? Start with `corpus/studies/README.md`. It needs NumPy (and scikit-learn for one comparison).

---

## What it does *not* claim

- The gate reads words, not meaning. A clever new phrasing can get through.
- "Self-only" is a refusal, not a guarantee: nothing stops someone describing another person as if it were
  themselves.
- Passing tests is evidence about **code**, never proof that a symbolic correspondence is "true".
- A test that is always skipped on your machine is not evidence until it has run somewhere else.

---

## Where to go next

| If you want to... | Read |
|---|---|
| run it | the "Quick start" section of [README.md](../README.md) |
| plug in your own parts | [ASSEMBLY_GUIDE.md](ASSEMBLY_GUIDE.md) |
| know what counts as proof | [STANDARD.md](../STANDARD.md) |
| know what it refuses | [ETHICS.md](ETHICS.md) |
| contribute | [CONTRIBUTING.md](../CONTRIBUTING.md) and [AGENTS.md](../AGENTS.md) |
| see what went wrong and how it was caught | [LIBER_0.md](../LIBER_0.md) and [OBSERVATIONS.md](../OBSERVATIONS.md) |
| explore any folder | the `README.md` inside it |

The licence is the RCA Sephirotic Sovereignty License 1.1 ([LICENSE.md](../LICENSE.md)): the source is open to read and
free for non-commercial use.
