# Assembly & Integration Guide

This guide explains how to replace the zero-dependency reference implementations in `examples/` with domain-specific parsers, custom rewrite rules, persistent storage backends, or isolated execution engines while preserving the termination and epistemic contracts of `symbolics`.

---

## 1. Interfaces Overview (`symbolics/interfaces.py`)

`recursive-symbolics` decouples orchestration from domain logic through four clean standard-library contracts:

| Interface | Kind | Responsibility | Reference Implementation |
|---|---|---|---|
| `SymbolicBackend` | `Protocol` | `parse()`, `format()`, `complexity()`, `evaluate()` | `examples/algebra_simplifier.AlgebraBackend` |
| `RuleEngine` | `ABC` | `rewrite_once()` composed into bounded `reduce_to_fixed_point()` | `examples/propositional_reducer.PropositionalReducer` |
| `MemoryStore` | `Protocol` | `get()`, `put()`, `snapshot()`, `verify_integrity()` | `symbolics.interfaces.InMemoryLedgerStore` |
| `ExecutionSandbox` | `Protocol` | `verify_target()`, `checkpoint()`, `rollback()` | `engines.athanor` (GGUF vessel sandbox) |

All protocols are `@runtime_checkable` and use zero external dependencies.

---

## 2. Swapping In a Domain `SymbolicBackend` & `RuleEngine`

To add a new symbolic domain (e.g., SQL query canonicalizer, lambda-calculus reducer, regex optimizer, or configuration policy normalizer):

1. **Implement `SymbolicBackend`:**
   ```python
   from collections.abc import Mapping
   from typing import Any

   class MyDomainBackend:
       def parse(self, text: str) -> Any:
           ...  # Raise ValueError on malformed/empty input

       def format(self, node: Any) -> str:
           ...  # Canonical string rendering: equivalent normal forms MUST share one string

       def complexity(self, node: Any) -> int:
           ...  # Structural size metric Phi(node) >= 1

       def evaluate(self, node: Any, env: Mapping[str, Any]) -> Any:
           ...  # Independent ground-truth evaluator over sample environments
   ```

2. **Subclass `RuleEngine` and implement `rewrite_once(self, node)`:**
   ```python
   from symbolics.interfaces import RuleEngine

   class MyReducer(RuleEngine):
       def rewrite_once(self, node: Any) -> tuple[Any, str | None]:
           # Return (new_node, "rule_name") if a rule applies.
           # Return (node, None) when no rule applies (fixed point).
           ...
   ```

3. **Run via `reduce_to_fixed_point`:**
   ```python
   from symbolics.interfaces import InMemoryLedgerStore

   store = InMemoryLedgerStore()
   trace = MyReducer(MyDomainBackend()).reduce_to_fixed_point(
       "...", max_depth=64, store=store
   )
   ```

---

## 3. Replacing `MemoryStore` with Persistent Backends

`InMemoryLedgerStore` hashes every write as a SHA-256 chain (`index`, `prev_hash`, `key`, `value`, `reason`) in memory. To persist traces to SQLite, Postgres, or a JSONL append-only ledger:

1. Implement `get(key, default=None)`, `put(key, value, reason="") -> str`, `snapshot() -> dict`, and `verify_integrity() -> bool`.
2. Ensure `put()` computes hashes over **canonical JSON** (`json.dumps(..., sort_keys=True, default=str)`), links `prev_hash` to the prior record, and uses atomic temp-file replacement or transactions if backed by files (`engines/athanor.py::_replace_durable` demonstrates Windows + POSIX atomic durability).
3. Ensure `verify_integrity()` re-computes every link from `GENESIS` (`"0" * 64`) rather than trusting stored hashes alone, returning `False` on any chain mismatch or payload edit.

**Design Note: Structural Simplicity in State Commitments**  
We deliberately use standard-library SHA-256 hash chains rather than algebraic commitments or neural embeddings for audit persistence. As automated reasoning advances against structured algebraic formulations, simple collision-resistant hashes offer the cleanest, lowest-overhead verification guarantee.

---

## 4. Wiring Production Engines

### A. Deterministic Cipher & Symbolic Group Checking (`symbolics/family_f.py`)
`symbolics/family_f.py` implements an exact enumerator over the 44 dihedral permutations on $\mathbb{Z}_{22}$ composed with 13 positional readings (572 composite rules). Use `solve_tzeruf(study=..., queries=..., proposed=...)` as an offline neuro-symbolic verification gate:

- `"VERIFIED"`: Unique deduced rule or unanimous candidate outputs agree with `proposed`.
- `"CONTRADICTED"`: Deterministic rule yields a different output than `proposed` (even if `approved=True`!).
- `"UNCHECKED"`: Study pairs are ambiguous or outside Family-F.

### B. Copy-on-Write Model/Weight Vessels (`engines/athanor.py`)
When plugging local GGUF model inspection/mutation behind `ExecutionSandbox`:
1. Never mutate live Ollama blobs directly (`is_ollama_blob` refuses it).
2. Create an isolated vessel copy (`athanor.create(src, dest)`), which initializes `<vessel>.athanor/vessel.json`, `journal.jsonl`, and `undo/`.
3. Every tensor write saves `<id>.bin` before mutation and writes a `pending.json` crash-recovery marker (`_recover` rolls back or completes interrupted writes).

### C. Sovereignty Output Wrapper (`engines/sovereign_wrapper.py`)
Wrap any LLM or rule-output generator with `SovereignWrapper(model_fn)` to withhold diagnostic overreach sentences, soften coercive imperatives into options, cap `directive_strength <= 0.85`, and attach alternatives metadata alongside the unedited `original` string.

---

## 5. Required Engine & Verification Contracts

Every custom implementation plugged into `recursive-symbolics` **must** uphold these contracts:

| Contract | Rule | Enforcement Mechanism |
|---|---|---|
| **Idempotency & Fixed-Point Closure** | Terminating states satisfy `rewrite_once(x*) == (x*, None)`. | `RuleEngine.reduce_to_fixed_point` |
| **Termination Bounds** | Reductions must terminate within `max_depth` without revisiting states. | `RecursionLimitError` & visited-digest `CycleDetectedError` |
| **Type Safety on Bounds** | `bool` (`True`/`False`) must never slip past `int` validation for counts/depths. | Explicit `isinstance(val, bool)` rejection |
| **Zero-Network Core (`symbolics/`)** | Core symbolic modules must import no networking libraries (`socket`, `urllib`, `http`, `requests`, etc.). | `python -m symbolics.conformance` AST check (Article 9) |
| **One-Way Seam & Constitutional Gate** | Lenses never modify `Address` coordinates; readings pass `ethics.emit()` with caveat, tradition, source, and anchors; `gamma <= 0.85`. | `symbolics/address.py`, `symbolics/ethics.py`, `symbolics/agency.py` |
| **Independent Ground Truth (`STANDARD.md`)** | Never mark a backend `VERIFIED` by comparing it to itself. Compare against direct evaluation (`backend.evaluate`), truth tables, stdlib parsers, or independent libraries, and prove tests catch a realistic injected bug (mutation test). | `STANDARD.md` & `tests/test_interfaces_and_examples.py` |
