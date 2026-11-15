# Agent & Contributor Guidelines

Read [STANDARD.md](STANDARD.md), [ETHICS.md](ETHICS.md), and [ASSEMBLY_GUIDE.md](ASSEMBLY_GUIDE.md) before modifying the symbolic core.

## Core Rules

1. **The seam is one-directional.** An `Address` is computed from observables; a `Lens` reads an `Address`; a lens can never write back into an address.
2. **A reading carries its caveat, tradition, source, and anchors.** `ethics.emit()` is the structural gate. Do not add a return path that bypasses it.
3. **The Conformance Suite is the answer about compliance, not your judgement of it.** Run `python -m symbolics.conformance` after any edit inside `symbolics/`.
4. **Nothing reaches the network.** No module in `symbolics/` imports a network library (`urllib`, `http`, `socket`, `requests`, etc.); `symbolics/conformance.py` parses every file's AST to verify Article 9.
5. **Adversarial Verification (`STANDARD.md`).** Every module requires an independent ground truth, boundary & edge-case coverage, and an executed break-it mutation check before it is marked `VERIFIED`.
6. **Automated Mutation Gate.** Do not report a module `VERIFIED` from `unittest` or hand-picked mutations alone. Run automated AST mutation across comparisons, booleans, and arithmetic using `python -B`, and report raw `killed / total` counts and every surviving `file:line` mutant verbatim.
