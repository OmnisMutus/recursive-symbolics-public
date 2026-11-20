# corpus/protocols/

Protocols built from already-tested parts: each file takes a stage of a written procedure, or two verified
engines, and makes it something code can check.

**The "Consciousness Upgrade" pipeline.** A pasted four-stage procedure, with each stage grounded as its own
module and tested on its own, then composed:

| Stage | File |
|---|---|
| 1. Declare a self-signature | `consciousness_upgrade_self_signature.py` |
| 2. Prune insoluble constraints | `consciousness_upgrade_constraint_pruner.py` |
| 3. Pattern transparency | `consciousness_upgrade_pattern_registry.py` |
| 4. Groundedness / levity | `consciousness_upgrade_groundedness.py` |
| All four composed | `consciousness_upgrade_pipeline.py` |

The name is the procedure's own. What the code checks is the formal, testable reading of each stage (register B
in [`../docs/PHILOSOPHICAL_AND_ENGINEERING_BOUNDARIES.md`](../docs/PHILOSOPHICAL_AND_ENGINEERING_BOUNDARIES.md)),
not a claim about consciousness.

**Engine composition.**

| File | What it does |
|---|---|
| `engine_composition_loop.py` | Wires two verified engines so one's output is the other's input. |
| `engine_composition_robustness_check.py` | The follow-up its report asked for: whether the reported convergence to one Chesed / Binah cycle is robust, or an artifact of one wording choice and one tie-break. |

The hand verifications and reports are in [`../docs/`](../docs/README_DOCS.md); the tests are in
[`../tests/`](../tests/README.md).
