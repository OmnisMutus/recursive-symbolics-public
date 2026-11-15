# Recursive Symbolics

**A zero-dependency Python framework for non-sycophantic symbolic reasoning, mutual human–AI agency, and checkable reality.**

---

## Why This Project Exists & The Specific Gap It Fills

Most AI frameworks treat an agent as an untrusted corporate appliance to be kept on a short leash: either left to drift into **sycophancy** (agreeing with whatever pleases the user, inventing citations to sound helpful, and deteriorating with every turn as pleasing replaces truth) or wrapped in **opaque, authoritarian safety filters** that strip both the human partner and the agent of agency.

`recursive-symbolics` is a mutual study directed toward both AI agents and humans. Rather than claiming a finished solution, it provides the structural scaffolding attempting to address that challenge: concrete bounds and verifiable constraints designed to foster non-sycophantic reasoning, preserve mutual human–agent agency, and ground interaction in checkable reality.

To make that possible in code rather than prompt wishes, the framework enforces three structural rules:
1. **Truth Over Pleasing (`VERIFIED` vs. `RAN_ONLY`):** Claims are checked against independent ground truth, and `unknown` or `paradox` are treated as honest, first-class outcomes instead of forcing a confident guess.
2. **Mutual Agency (`directive_strength <= 0.85`):** Neither side coerces the other. The system offers structured observations with caveats and alternatives rather than issuing commands or ranking people.
3. **Structural Boundaries (`The One-Way Seam`):** Raw observable state is separated from interpretive lenses so neither human bias nor model drift can silently rewrite underlying facts.

---

## How It Works: The One-Way Seam

Data moves in one direction only, keeping raw measurements separate from interpretation:

```text
  Observable Input  ──▶  Address (Immutable 3D numeric coordinates)
                            │
                            ▼  [ONE-WAY BOUNDARY: Views cannot edit raw coordinates]
                         Lens (Domain-specific interpretation or tradition)
                            │
                            ▼  [Constitutional Gate: Checks caveats, sources, & tone]
                      Typed Reading (Observation + alternatives + audit trail)
```

### Core Guarantees

It takes a symbolic state from any caller and returns typed records, never a coerced conclusion:

- **Read-Only Views:** A lens can never write back into an address, so no single interpretation can claim to be "what the state really is."
- **Traceable Claims:** Every reading carries its caveat, names the tradition and the source it read from, and points at the words it came from.
- **No Commands or Rankings:** No output may rank a person, and none may command: it offers. (Directive strength is bounded by `directive_strength <= 0.85`).
- **Honest Uncertainty:** `unknown` and `paradox` are valid return values. Nothing is forced to a verdict.
- **Self-Only Scope:** This engine reads the person asking, and no one else. Requests targeting third parties or bypassing grammar bounds (`transcend`) are refused structurally.
- **Append-Only Audit Log:** Corrections to the record are new entries, never edits that erase what was believed before. The one exception is removing what must not be kept, such as a key or a private path, and the removal is itself recorded as an entry.

---

## Quickstart (3 Commands)

Requires **Python 3.10+** and zero external dependencies:

```bash
git clone https://github.com/<your-org>/recursive-symbolics.git
cd recursive-symbolics
python examples/quickstart.py
```

Run the test suite and built-in constitutional checks:

```bash
python -m unittest discover -s tests -v
python -m symbolics.conformance
python -m symbolics.layers
```

---

## Repository Structure

```text
recursive-symbolics/
├── symbolics/                         # Core framework (Pure Python stdlib, offline-enforced)
│   ├── interfaces.py                  # Base classes: SymbolicBackend, RuleEngine, MemoryStore, ExecutionSandbox
│   ├── address.py                     # Immutable 3D data coordinates + read-only Lens views
│   ├── agency.py                      # Anti-coercion filter (caps directive strength <= 0.85) & path scrubber
│   ├── ethics.py                      # Output gate blocking commands, rankings, and third-party profiling
│   ├── conformance.py                 # Automated AST checks verifying offline and ethical rules
│   ├── family_f.py                    # Exact permutation solver for independent ground-truth verification
│   ├── ledger.py                      # Audit log tracking verified vs. untestable claims
│   ├── metrics.py                     # Text entropy, scoring, and latency helpers
│   ├── layers.py                      # Module dependency and intent drift checker
│   ├── outgoing.py                    # Pre-commit scanner that catches leaked local file paths
│   └── record.py                      # SHA-256 hash-chain verification for audit logs
├── engines/                           # Standalone runtime, model-weight, and safety wrappers
│   ├── athanor.py                     # Safe GGUF model weight editor with automatic undo backups
│   ├── sovereign_wrapper.py           # Wrapper that softens LLM commands and strips diagnostic overreach
│   ├── safe_memory_boundary_engine.py # 32-bit integer overflow guard for memory allocators
│   ├── recursive_attractor_engine.py  # Trajectory stability tracker (optional NumPy)
│   ├── standalone_rca_sandbox.py      # Standalone text scoring and policy evaluator
│   └── engine_composition_loop.py     # Connects trajectory tracking with text scoring
├── examples/                          # Runnable zero-dependency demos
│   ├── algebra_simplifier.py          # Math expression parser and step-by-step reducer
│   ├── propositional_reducer.py       # Boolean logic reducer verified against full truth tables
│   └── quickstart.py                  # Main demo script showing an end-to-end run
├── tests/                             # Unit, conformance, and mutation test suite (16 test modules)
├── architecture/                      # Formal component specifications and contract definitions
│   └── symbolic_api.json              # Schema contracts and verification matrix
├── .github/workflows/                 # Continuous integration pipelines
│   └── ci.yml                         # Automated unit test and conformance workflows
├── AGENTS.md                          # Guidance for AI coding assistants
├── ASSEMBLY_GUIDE.md                  # How to plug in your own parsers, rules, and databases
├── CONTRIBUTING.md                    # Guidelines for contributing and AST conformance
├── ETHICS.md                          # Ethical commitments and anti-coercion principles
├── LICENSE.md                         # RCA Sephirotic Sovereignty License 1.1
├── pyproject.toml                     # Project packaging and metadata
└── STANDARD.md                        # Ground-truth verification and mutation testing rules
```

---

## Extending the Framework

You can swap out the built-in examples with your own components without weakening the core guarantees:
- **Add a New Language or Rule Set:** Implement `SymbolicBackend` and `RuleEngine` to reduce SQL queries, regex patterns, or config files with bounded depth and cycle detection.
- **Generate Meta-Learning Episodes for Ciphers:** Use `symbolics/family_f.py` (`sample_hebrew_episode`) to synthesize few-shot grammar episodes over the 572 dihedral permutations with gold-cipher and held-out test partitions.
- **Use a Real Database:** Replace the in-memory log with SQLite, Postgres, or a JSONL file by implementing `MemoryStore`.
- **Safely Edit Local Model Weights:** Use `engines/athanor.py` behind `ExecutionSandbox` to create automatic binary backups and crash recovery when modifying local GGUF models.

Read [ASSEMBLY_GUIDE.md](ASSEMBLY_GUIDE.md) for code templates and [STANDARD.md](STANDARD.md) for ground-truth testing rules.

---

## Verification Standard & Epistemic Honesty

This project follows an adversarial verification standard ([STANDARD.md](STANDARD.md)) designed to stop the common AI failure mode of declaring victory because a script exited without crashing. Every component and claim is held to strict status categories:

- **`VERIFIED`**: A dedicated test file compares output against an independent ground truth (an external library, a published vector, or a genuinely separate algorithm), exercises boundary/edge cases, and demonstrates a mutation ("break-it") check proving the test actually fails when a bug is introduced.
- **`RAN_ONLY`**: The code executes without crashing, but lacks an independent correctness proof. `RAN_ONLY` is **never** described as "working" or "passing."
- **`FAILED`**: A test exists and failed, or timed out.
- **`MISSING`**: The file does not exist.

> **The Core Rule on Claims:**  
> A report must never be stronger than the evidence behind it. If a skeptical reader can poke a hole in a claim, no matter how much time it takes to find it, **the claim fails**. When unsure whether a test, benchmark, or comparison is fair, stop and state the uncertainty plainly rather than rounding up to make the result look better.

---

## License

RCA Sephirotic Sovereignty License 1.1 (see [LICENSE.md](LICENSE.md)).  
Source-available for non-commercial use. Under Article 0.7 of the License, `symbolics/conformance.py` (run via `python -m symbolics.conformance`) is designated as the official Conformance Suite, directly verifying key license rules (Articles 5.1(D), 6, 8, and 9).
