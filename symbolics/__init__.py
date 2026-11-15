"""Recursive Symbolics: constitutional and fixed-point symbolic transformation engine.

Core architecture:
    observable input -> address (computed) -> lens (chosen) -> reading (interpretation)

Every module in ``symbolics`` uses standard-library Python only and imports zero network libraries.
"""

from .interfaces import (
    ConvergenceTrace,
    CycleDetectedError,
    ExecutionSandbox,
    InMemoryLedgerStore,
    MemoryStore,
    RecursionLimitError,
    RewriteStep,
    RuleEngine,
    SymbolicBackend,
    SymbolicState,
)

__all__ = [
    "ConvergenceTrace",
    "CycleDetectedError",
    "ExecutionSandbox",
    "InMemoryLedgerStore",
    "MemoryStore",
    "RecursionLimitError",
    "RewriteStep",
    "RuleEngine",
    "SymbolicBackend",
    "SymbolicState",
]
