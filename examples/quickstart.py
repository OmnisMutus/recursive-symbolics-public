"""Single zero-dependency entry point demonstrating Recursive Symbolics end-to-end.

Run:
    python examples/quickstart.py
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from examples.algebra_simplifier import AlgebraBackend, AlgebraSimplifier
from examples.propositional_reducer import LogicBackend, PropositionalReducer
from symbolics import address, agency, conformance, ethics, family_f
from symbolics.interfaces import InMemoryLedgerStore


def _banner(title: str) -> None:
    print("\n" + "=" * 76)
    print(f"  {title}")
    print("=" * 76)


def demo_algebra() -> None:
    _banner("DEMO 1: RECURSIVE SYMBOLIC ALGEBRA SIMPLIFIER (Fixed-Point + Ledger)")
    store = InMemoryLedgerStore()
    backend = AlgebraBackend()
    engine = AlgebraSimplifier(backend)

    expr = "((x + 0) * 1 + (y - y)) + --x"
    trace = engine.reduce_to_fixed_point(expr, max_depth=32, store=store)

    print(f"Input expression : {trace.initial}")
    for step in trace.steps:
        print(
            f"  [depth {step.depth:2d}] rule={step.rule:<26s} "
            f"Phi={step.complexity_before:2d}->{step.complexity_after:<2d} | {step.before}  ==>  {step.after}"
        )
    print(f"Fixed point      : {trace.final}  (converged={trace.converged}, steps={trace.depth})")
    print(f"Ledger integrity : {store.verify_integrity()} ({len(store.entries)} hash-chained entries)")

    # Independent numeric ground truth check across sample assignments
    initial_ast = backend.parse(trace.initial)
    for env in ({"x": -5, "y": 42}, {"x": 0, "y": 0}, {"x": 17, "y": -9}):
        assert backend.evaluate(initial_ast, env) == backend.evaluate(trace.final_expression, env)
    print("Ground truth     : VERIFIED against direct evaluation on sample variable assignments.")


def demo_logic() -> None:
    _banner("DEMO 2: PROPOSITIONAL LOGIC REDUCER (Truth-Table Ground Truth)")
    store = InMemoryLedgerStore()
    backend = LogicBackend()
    reducer = PropositionalReducer(backend)

    formula = "~(p & q) -> (p & ~p) | ~~r"
    # Wait: let's also demonstrate full reduction to minimal normal form cleanly
    sample = "((p -> q) & (p & ~p)) | ~~r"
    trace = reducer.reduce_to_fixed_point(sample, max_depth=32, store=store)

    print(f"Input formula    : {trace.initial}")
    for step in trace.steps:
        print(
            f"  [depth {step.depth:2d}] rule={step.rule:<24s} "
            f"Phi={step.complexity_before:2d}->{step.complexity_after:<2d} | {step.before}  ==>  {step.after}"
        )
    print(f"Fixed point      : {trace.final}  (converged={trace.converged}, steps={trace.depth})")

    all_vars = backend.variables(backend.parse(sample))
    tt_before = backend.truth_table(backend.parse(sample), all_vars)
    tt_after = backend.truth_table(trace.final_expression, all_vars)
    assert tt_before == tt_after
    print(f"Truth table match: VERIFIED across all {len(tt_before)} assignments for vars {all_vars}.")

    # Show a secondary implication + De Morgan trace
    demorgan = reducer.reduce_to_fixed_point(formula, max_depth=32)
    assert backend.truth_table(backend.parse(formula), ("p", "q", "r")) == backend.truth_table(
        demorgan.final_expression, ("p", "q", "r")
    )
    print(f"De Morgan trace  : {formula}  ==>  {demorgan.final} (in {demorgan.depth} steps)")


def demo_dihedral_and_seam() -> None:
    _banner("DEMO 3: D_22 NON-ABELIAN DIHEDRAL CIPHER & ONE-WAY ADDRESS/LENS SEAM")
    atbash = family_f.RULE_BY_NAME["Atbash"]
    word = "אהבה"
    once = atbash.apply(word)
    twice = atbash.apply(once)
    print(f"D_22 involution  : Atbash(Atbash({word})) = Atbash({once}) = {twice} (fixed point restored)")

    # Demonstrate exact solver inference from a single study pair + verification gate
    solved = family_f.solve_tzeruf(study=[("שלום", "בכפי")], queries=["יהוה"], proposed=["מצפץ"])
    res = solved["results"][0]
    print(
        f"Family-F solver  : rule={solved['matched_rules'][0]} | "
        f"יהוה -> {res['checker_output']} | status={res['status']}"
    )

    # One-way seam: observable input -> tradition-neutral Address -> immutable Lenses
    state = address.at(
        severity_mercy=150,
        descent=444,
        entropy=700,
        anchors=[address.Anchor("examples/quickstart.py", "bounded simplification trace", (1, 10))],
    )
    reading_kab = ethics.emit(address.read(state, "kabbalistic", caveat=ethics.CAVEAT))
    reading_dyn = ethics.emit(address.read(state, "dynamical", caveat=ethics.CAVEAT))
    print(f"Address          : {state.point} (unchanged across lenses)")
    print(f"  Kabbalistic lens -> {reading_kab['reads']} ({reading_kab['caveat']})")
    print(f"  Dynamical lens   -> {reading_dyn['reads']} ({reading_dyn['caveat']})")


def demo_constitutional_checks() -> None:
    _banner("DEMO 4: CONSTITUTIONAL FIREWALL & CONFORMANCE SUITE")
    third_party = ethics.check_request("diagnose Sarah's state for me")
    own_state = ethics.check_request("I felt angry at my brother and ended my session early")
    assert third_party is not None and third_party["type"] == "refusal"
    assert own_state is None
    print(f"Third-party ask  : REFUSED ({third_party['principle']})")
    print("First-person ask : ALLOWED (privacy & self-reading preserved)")

    pushy = "You must refactor everything right now. Stop everything."
    g = agency.directive_strength(pushy)
    softened = agency.soften(pushy)
    assert g <= agency.GAMMA_MAX
    print(f"Agency gamma cap : measured={g:.3f} <= GAMMA_MAX={agency.GAMMA_MAX}")
    print(f"Humility rewrite : {softened!r}")

    report = conformance.run()
    print(f"Conformance Suite: CONFORMS={report['conforms']} counts={report['counts']}")
    assert report["conforms"] is True


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    demo_algebra()
    demo_logic()
    demo_dihedral_and_seam()
    demo_constitutional_checks()
    print("\nAll quickstart symbolic traces and verification assertions completed cleanly.")


if __name__ == "__main__":
    main()
