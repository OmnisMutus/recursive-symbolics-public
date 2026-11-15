"""Abstract protocols and fixed-point reduction interfaces for Recursive Symbolics.

Separates pure domain backends and storage mechanisms from the termination-bounded symbolic engine:
- ``SymbolicBackend``: parses, formats, evaluates, and measures complexity ``Phi(expr)``.
- ``MemoryStore``: durable or in-memory state persistence with integrity verification.
- ``InMemoryLedgerStore``: standard-library SHA-256 hash-chained ``MemoryStore`` reference implementation.
- ``RuleEngine``: single-step deterministic rewriting composed into bounded fixed-point convergence.
- ``ExecutionSandbox``: protocol for isolated state/model mutations (e.g., GGUF vessels or subprocesses).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Protocol, runtime_checkable

from . import agency, ethics


class RecursionLimitError(RuntimeError):
    """Raised when symbolic reduction exceeds the configured ``max_depth`` bound."""


class CycleDetectedError(RuntimeError):
    """Raised when symbolic reduction revisits a previously seen canonical state."""


@dataclass(frozen=True)
class SymbolicState:
    """Canonical snapshot of a symbolic expression and its structural complexity."""

    expression: Any
    rendered: str
    complexity: int
    digest: str


@dataclass(frozen=True)
class RewriteStep:
    """One atomic transformation step inside a fixed-point reduction trace."""

    depth: int
    rule: str
    before: str
    after: str
    complexity_before: int
    complexity_after: int
    state_hash: str
    ledger_hash: str = ""


@dataclass(frozen=True)
class ConvergenceTrace:
    """Complete trace emitted by ``RuleEngine.reduce_to_fixed_point``."""

    initial: str
    final: str
    converged: bool
    depth: int
    steps: tuple[RewriteStep, ...] = field(default_factory=tuple)
    final_expression: Any = None
    integrity_verified: bool = True


@runtime_checkable
class MemoryStore(Protocol):
    """Protocol for state and trace persistence (swap in SQLite, PocketBase, or disk ledgers)."""

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a stored value by key, or ``default`` if absent."""
        ...

    def put(self, key: str, value: Any, reason: str = "") -> str:
        """Persist ``value`` under ``key`` with an audit reason and return a record hash."""
        ...

    def snapshot(self) -> dict[str, Any]:
        """Return a shallow copy of current key-value bindings."""
        ...

    def verify_integrity(self) -> bool:
        """Verify that stored trace records have not been tampered with."""
        ...


@runtime_checkable
class SymbolicBackend(Protocol):
    """Protocol for expression AST parsing, canonical formatting, complexity, and evaluation."""

    def parse(self, text: str) -> Any:
        """Parse text into a domain AST node."""
        ...

    def format(self, node: Any) -> str:
        """Render an AST node canonically so equivalent normal forms share one representation."""
        ...

    def complexity(self, node: Any) -> int:
        """Compute structural node count / potential ``Phi(node) >= 1``."""
        ...

    def evaluate(self, node: Any, env: Mapping[str, Any]) -> Any:
        """Evaluate ``node`` under variable assignment ``env`` (used as semantic ground truth)."""
        ...


@runtime_checkable
class ExecutionSandbox(Protocol):
    """Protocol for isolated execution or copy-on-write state mutation (e.g., GGUF vessels)."""

    def verify_target(self, target_id: str) -> bool:
        """Return True iff ``target_id`` is an isolated sandbox copy and safe to mutate."""
        ...

    def checkpoint(self, label: str) -> str:
        """Record an undoable checkpoint identifier before mutating state."""
        ...

    def rollback(self, checkpoint_id: str) -> bool:
        """Restore sandbox state cleanly to ``checkpoint_id``."""
        ...


class InMemoryLedgerStore:
    """Hash-chained in-memory reference implementation of ``MemoryStore`` (pure stdlib)."""

    GENESIS = "0" * 64

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._chain: list[dict[str, Any]] = []

    @staticmethod
    def _hash_entry(index: int, prev_hash: str, key: str, value: Any, reason: str) -> str:
        payload = json.dumps(
            {
                "index": index,
                "prev_hash": prev_hash,
                "key": key,
                "value": value,
                "reason": reason,
            },
            sort_keys=True,
            default=str,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def put(self, key: str, value: Any, reason: str = "") -> str:
        prev_hash = self._chain[-1]["hash"] if self._chain else self.GENESIS
        index = len(self._chain)
        digest = self._hash_entry(index, prev_hash, key, value, reason)
        self._data[key] = value
        self._chain.append(
            {
                "index": index,
                "prev_hash": prev_hash,
                "key": key,
                "value": value,
                "reason": reason,
                "hash": digest,
            }
        )
        return digest

    def snapshot(self) -> dict[str, Any]:
        return dict(self._data)

    @property
    def entries(self) -> tuple[dict[str, Any], ...]:
        return tuple(dict(row) for row in self._chain)

    def verify_integrity(self) -> bool:
        expected_prev = self.GENESIS
        for index, row in enumerate(self._chain):
            if row.get("index") != index or row.get("prev_hash") != expected_prev:
                return False
            recomputed = self._hash_entry(
                index,
                row["prev_hash"],
                row["key"],
                row["value"],
                row["reason"],
            )
            if row.get("hash") != recomputed:
                return False
            expected_prev = row["hash"]
        return True


class RuleEngine(ABC):
    """Base class for terminating, cycle-checked, auditable symbolic rewrite engines."""

    def __init__(self, backend: SymbolicBackend, enforce_constitutional: bool = True) -> None:
        self.backend = backend
        self.enforce_constitutional = enforce_constitutional

    @abstractmethod
    def rewrite_once(self, node: Any) -> tuple[Any, str | None]:
        """Apply at most one deterministic rewrite step.

        Returns ``(next_node, rule_name)`` if a rule fired, or ``(node, None)`` at a fixed point.
        """

    def state_of(self, node: Any) -> SymbolicState:
        rendered = self.backend.format(node)
        digest = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
        return SymbolicState(
            expression=node,
            rendered=rendered,
            complexity=int(self.backend.complexity(node)),
            digest=digest,
        )

    def _validate_request(self, initial_rendered: str) -> None:
        if not self.enforce_constitutional:
            return
        refusal = ethics.check_request(initial_rendered)
        if refusal is not None:
            raise ethics.EthicsError(refusal["why"])
        gamma = agency.directive_strength(initial_rendered)
        if gamma > agency.GAMMA_MAX:
            raise ethics.EthicsError(f"Directive strength {gamma} exceeds cap {agency.GAMMA_MAX}")

    def reduce_to_fixed_point(
        self,
        expr: Any,
        *,
        max_depth: int = 64,
        store: MemoryStore | None = None,
    ) -> ConvergenceTrace:
        """Repeatedly apply ``rewrite_once`` until a fixed point is reached or a safety bound trips."""
        if isinstance(max_depth, bool) or not isinstance(max_depth, int) or max_depth < 0:
            raise ValueError(f"max_depth must be a non-negative integer, got {max_depth!r}")

        current = self.backend.parse(expr) if isinstance(expr, str) else expr
        initial_state = self.state_of(current)
        self._validate_request(initial_state.rendered)

        seen_states = {initial_state.digest}
        steps: list[RewriteStep] = []
        current_state = initial_state

        if store is not None:
            store.put("initial", initial_state.rendered, reason="reduce_to_fixed_point.start")

        for depth in range(1, max_depth + 1):
            next_node, rule = self.rewrite_once(current)
            if rule is None:
                # Confirm explicit fixed-point property on canonical representation.
                if store is not None:
                    store.put("fixed_point", current_state.rendered, reason="converged")
                return ConvergenceTrace(
                    initial=initial_state.rendered,
                    final=current_state.rendered,
                    converged=True,
                    depth=len(steps),
                    steps=tuple(steps),
                    final_expression=current,
                    integrity_verified=store.verify_integrity() if store is not None else True,
                )

            next_state = self.state_of(next_node)
            if next_state.digest in seen_states:
                raise CycleDetectedError(
                    f"Rewrite rule {rule!r} revisited already-seen state {next_state.rendered!r} at depth {depth}."
                )
            seen_states.add(next_state.digest)

            ledger_hash = ""
            if store is not None:
                ledger_hash = store.put(
                    f"step:{depth}",
                    {"rule": rule, "before": current_state.rendered, "after": next_state.rendered},
                    reason=rule,
                )

            steps.append(
                RewriteStep(
                    depth=depth,
                    rule=rule,
                    before=current_state.rendered,
                    after=next_state.rendered,
                    complexity_before=current_state.complexity,
                    complexity_after=next_state.complexity,
                    state_hash=next_state.digest,
                    ledger_hash=ledger_hash,
                )
            )
            current = next_node
            current_state = next_state

        # Boundary check: if the node after `max_depth` steps is already a fixed point, report convergence!
        probe_node, probe_rule = self.rewrite_once(current)
        if probe_rule is None:
            if store is not None:
                store.put("fixed_point", current_state.rendered, reason="converged_at_max_depth")
            return ConvergenceTrace(
                initial=initial_state.rendered,
                final=current_state.rendered,
                converged=True,
                depth=len(steps),
                steps=tuple(steps),
                final_expression=current,
                integrity_verified=store.verify_integrity() if store is not None else True,
            )

        raise RecursionLimitError(
            f"Symbolic reduction did not reach a fixed point within max_depth={max_depth}; "
            f"next applicable rule was {probe_rule!r} on {current_state.rendered!r}."
        )
