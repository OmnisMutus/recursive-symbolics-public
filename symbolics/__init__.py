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
from .checking import Check, check
from .reading import NotARead, Record, Refused, Unknown, lenses, read, readings

__all__ = [
    "read",
    "readings",
    "lenses",
    "check",
    "Check",
    "Record",
    "NotARead",
    "Refused",
    "Unknown",
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
