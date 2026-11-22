# symbolics/

The core package. It uses only the Python standard library, and no file here may import a network library:
`symbolics/conformance.py` parses every module's source to check that (licence Article 9).

## How the pieces fit

```text
text or observables ──▶ metrics.py ──▶ address.py: Address (immutable)
                                              │
                                              ▼  a Lens reads it, never writes back
                                       address.py: Lens
                                              │
                                              ▼
                       ethics.py: emit()  (caveat, tradition, source, anchors; no ranking, no commands)
                                              │
                                              ▼
                                        a typed reading
```

`agency.py` measures how directive a piece of text is and caps it. `ledger.py` sorts claims into VERIFIED, FAILED
or UNTESTABLE. The rest are the checks that keep the repository honest about itself.

## The modules

### The reading path

| File | What it does |
|---|---|
| `reading.py` | The front door: `read(text)` runs the whole path below in one call and returns a `Record`; `readings()` reads with every lens; `lenses()` lists them. See `API.md`. |
| `metrics.py` | The measurement layer: text in, observables out (entropy, centroid scores, latency helpers). Every address it builds says in its own derivation what the measurement cannot see. |
| `address.py` | The address space: a three-axis point no tradition owns, and the read-only lenses that interpret one. |
| `ethics.py` | The gate every reading passes through. `check_request()` refuses requests about a third party and the undefined `transcend` operator; `emit()` refuses a reading without its caveat, tradition, source or anchors, and any that ranks a person or commands. It matches words and patterns, not meaning: see Known Limitations in the main README. |
| `agency.py` | The agency budget: directive strength (gamma) measured, capped at 0.85, disclosed and logged. It holds the one definition of the cap (`GAMMA_MAX`). `sovereign()` is the enforcement path: it softens, adds alternatives, and under a lower `gamma_max` withholds a reply still above it. |
| `interfaces.py` | The abstract contracts you implement to plug in your own parts: `SymbolicBackend`, `RuleEngine`, `MemoryStore`, `ExecutionSandbox`. See `ASSEMBLY_GUIDE.md`. |
| `family_f.py` | An exact solver over the 572 dihedral (D_22) permutations, used as independent ground truth, and a generator of few-shot cipher episodes. |

### Recording what is true

| File | What it does |
|---|---|
| `ledger.py` | The correspondence ledger: every claim is VERIFIED (a test backs it), FAILED (a test contradicts it) or UNTESTABLE (said so, not hidden). A ledger where everything is UNTESTABLE does not pass. |
| `ledger_history.py` | Run history for the ledger: how long since each claim was last checked. |
| `ledger_staleness.py` | Marks a ledger row stale when the code it checks has changed since. |

### Checks on the repository itself

Each runs as `python -m symbolics.<name>` and exits with an error when it fails. CI runs all of them.

| File | What it checks |
|---|---|
| `conformance.py` | The licence's executable duties (Articles 5.1(D), 6, 8 and 9). This is the official Conformance Suite. For Article 6 it re-measures what `sovereign()` actually lets reach a person, at the default cap and at a lower one. |
| `layers.py` | That every file `architecture/layers.json` names exists, and that every sentence in `architecture/intent.json` still appears word for word in its source. |
| `outgoing.py` | That no local home-folder path is about to be published, in the files or in any commit's patch or message. |
| `record.py` | That `LIBER_0.md` is only ever added to, by reading its git history. |
| `breaches.py` | That every FAILED or CORRECTED entry in `LIBER_0.md` names an existing guard, or a reason none can exist. |
| `mutate.py` | The mutation gate: changes comparisons, booleans and arithmetic in a module, one at a time, and reports every change the tests failed to catch. `python -B -m symbolics.mutate --module symbolics/ethics.py` |

## Before you change anything here

1. Read `STANDARD.md`, `ETHICS.md` and `AGENTS.md`.
2. Run `python -m symbolics.conformance` after any edit in this folder.
3. A module is not VERIFIED until its tests compare against an independent ground truth, cover the edge cases,
   and pass the mutation gate with every surviving mutant reported.
