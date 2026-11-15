"""Standalone execution engines for Recursive Symbolics.

Keep imports lazy at package level so pure-stdlib modules (`athanor`, `safe_memory_boundary_engine`,
`sovereign_wrapper`) can be imported cleanly even without optional numerical extras like NumPy.
"""

__all__ = [
    "athanor",
    "engine_composition_loop",
    "recursive_attractor_engine",
    "safe_memory_boundary_engine",
    "sovereign_wrapper",
    "standalone_rca_sandbox",
]
