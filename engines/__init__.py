"""Standalone execution engines for Recursive Symbolics.

Keep imports lazy at package level so pure-stdlib modules (`safe_memory_boundary_engine`, `sovereign_wrapper`)
can be imported cleanly even without optional numerical extras like NumPy. The GGUF model workshop that used to
live here as `athanor.py` is now the `athanor/` package at the repository root.
"""

__all__ = [
    "engine_composition_loop",
    "recursive_attractor_engine",
    "safe_memory_boundary_engine",
    "sovereign_wrapper",
    "standalone_rca_sandbox",
]
