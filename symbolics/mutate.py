"""Automated AST mutation gate with SHA-256 receipt verification (pure stdlib).

Systematically mutates comparison (<, <=, >, >=, ==, !=), boolean (and, or),
and arithmetic (+, -, *) AST nodes on an isolated temporary copy of the target
repository (never modifying the original source files on disk), verifies the
unmutated baseline passes first, executes each mutant in a separate `python -B`
subprocess, and exits non-zero if any unexempted mutant survives or errors.
"""

from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

TARGETS: Dict[str, str] = {
    "symbolics/agency.py": "tests.test_agency",
    "symbolics/address.py": "tests.test_address_and_ethics",
    "symbolics/ethics.py": "tests.test_address_and_ethics",
    "symbolics/interfaces.py": "tests.test_interfaces_and_examples",
    "symbolics/metrics.py": "tests.test_metrics",
    "symbolics/ledger.py": "tests.test_ledger",
    "symbolics/family_f.py": "tests.test_family_f",
    "symbolics/conformance.py": "tests.conformance.test_conformance",
    "symbolics/layers.py": "tests.test_layers",
    "symbolics/outgoing.py": "tests.test_outgoing",
    "symbolics/record.py": "tests.test_record_and_staleness",
    "symbolics/breaches.py": "tests.test_breaches",
    "symbolics/mutate.py": "tests.test_mutate",
    "symbolics/ledger_history.py": "tests.test_record_and_staleness",
    "symbolics/ledger_staleness.py": "tests.test_record_and_staleness",
    "engines/safe_memory_boundary_engine.py": "tests.test_safe_memory_boundary_engine",
    "engines/sovereign_wrapper.py": "tests.test_sovereign_wrapper",
    "engines/recursive_attractor_engine.py": "tests.test_recursive_attractor_engine",
    "engines/engine_composition_loop.py": "tests.test_engine_composition_loop",
    "engines/standalone_rca_sandbox.py": "tests.test_standalone_rca_sandbox",
    "athanor/workshop.py": ("tests.athanor_tests.test_athanor", "tests.athanor_tests.test_review_regressions"),
    "athanor/gguf.py": ("tests.athanor_tests.test_athanor", "tests.athanor_tests.test_review_regressions"),
    "athanor/codec.py": ("tests.athanor_tests.test_athanor", "tests.athanor_tests.test_review_regressions"),
    "athanor/edits.py": ("tests.athanor_tests.test_athanor", "tests.athanor_tests.test_review_regressions"),
    "reference_agent/outbound.py": ("tests.reference_agent_tests.test_mcp",
                                    "tests.reference_agent_tests.test_agentbase_mcp"),
    "reference_agent/mcp.py": ("tests.reference_agent_tests.test_mcp",
                               "tests.reference_agent_tests.test_agentbase_mcp"),
    "reference_agent/suitecheck.py": "tests.reference_agent_tests.test_suitecheck",
    "reference_agent/vector_bridge.py": "tests.reference_agent_tests.test_vector_bridge",
    "symbolics/reading.py": "tests.test_reading",
    "reference_agent/governance.py": "tests.reference_agent_tests.test_governance",
    "examples/algebra_simplifier.py": "tests.test_interfaces_and_examples",
    "examples/propositional_reducer.py": "tests.test_interfaces_and_examples",
}

CMP_SWAPS = {
    ast.Lt: ast.LtE,
    ast.LtE: ast.Lt,
    ast.Gt: ast.GtE,
    ast.GtE: ast.Gt,
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
}

BIN_SWAPS = {
    ast.Add: ast.Sub,
    ast.Sub: ast.Add,
    ast.Mult: ast.Add,
}


class BaselineFailure(RuntimeError):
    """Raised when the unmutated baseline test suite fails."""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _test_module_path(root: Path, test_mod: str) -> Optional[Path]:
    rel = Path(*test_mod.split(".")).with_suffix(".py")
    candidate = root / rel
    return candidate if candidate.exists() else None


def collect_mutants(tree: ast.Module, limit: int = 0) -> List[Tuple[int, str, ast.AST, str]]:
    """Collect AST mutation sites in traversal order. limit=0 means uncapped."""
    mutants: List[Tuple[int, str, ast.AST, str]] = []
    for node in ast.walk(tree):
        lineno = getattr(node, "lineno", 0)
        if isinstance(node, ast.Compare):
            if isinstance(node.left, ast.Name) and node.left.id == "__name__":
                continue
            # Every operator of a chain is its own mutant (fixed 2026-11-22: chains such as 0 < x <= cap were
            # skipped, so a bound written that way was never tested).
            for i, op in enumerate(node.ops):
                op_type = type(op)
                if op_type not in CMP_SWAPS:
                    continue
                mutants.append((lineno, f"{op_type.__name__}->{CMP_SWAPS[op_type].__name__}", node, f"cmp:{i}"))
        elif isinstance(node, ast.BinOp) and type(node.op) in BIN_SWAPS:
            op_type = type(node.op)
            mutants.append((lineno, f"{op_type.__name__}->{BIN_SWAPS[op_type].__name__}", node, "bin"))
        elif isinstance(node, ast.BoolOp):
            new_op = ast.Or if isinstance(node.op, ast.And) else ast.And
            mutants.append((lineno, f"{type(node.op).__name__}->{new_op.__name__}", node, "boolop"))
    # Two mutants with the same line and the same swap would share one label, so an exemption could not say which
    # it meant. The first keeps the plain label (so recorded exemptions still match); a later one gets " #2",
    # " #3", in the order the tree is walked. Added 2026-11-22, after an outside review.
    labelled = []
    count: Dict[Tuple[int, str], int] = {}
    for lineno, desc, node, kind in mutants:
        count[(lineno, desc)] = count.get((lineno, desc), 0) + 1
        n = count[(lineno, desc)]
        labelled.append((lineno, desc if n == 1 else f"{desc} #{n}", node, kind))
    # The cap is applied once, at the end: the same first `limit` sites, with one comparison to test.
    return labelled[:limit] if limit > 0 else labelled


def load_exemptions(root: Path) -> set[str]:
    guards_path = root / "architecture" / "mutation_guards.json"
    if not guards_path.exists():
        return set()
    try:
        data = json.loads(guards_path.read_text(encoding="utf-8"))
        return set(data.get("equivalent_mutants", []))
    except (OSError, ValueError):
        return set()


def _copy_workspace(src: Path, dst: Path) -> None:
    shutil.copytree(
        src,
        dst,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc", ".venv", "venv"),
    )


def _test_modules(test_mod) -> List[str]:
    """One test module name, or several (a tuple or list): a file tested from more than one place is mutated
    against all of them, so a mutant counts as surviving only if no test anywhere catches it."""
    mods = [test_mod] if isinstance(test_mod, str) else list(test_mod)
    if not mods or not all(isinstance(m, str) and m for m in mods):
        raise ValueError(f"test module(s) must be one or more non-empty names, got {test_mod!r}")
    return mods


def _mutant_source(tree: ast.Module, index: int, limit: int) -> Tuple[int, str, str]:
    """The source of mutant number `index`: (its line, what was swapped, the mutated code).

    Each mutant starts from a fresh copy of the tree, so no swap is ever left over from the one before.
    """
    copied = copy.deepcopy(tree)
    lineno, desc, node, kind = collect_mutants(copied, limit=limit)[index]
    if kind.startswith("cmp:"):
        i = int(kind.split(":", 1)[1])
        node.ops[i] = CMP_SWAPS[type(node.ops[i])]()
    elif kind == "bin":
        node.op = BIN_SWAPS[type(node.op)]()
    elif kind == "boolop":
        node.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
    return lineno, desc, ast.unparse(copied)


# No .pyc anywhere in the sandbox, child processes included (fixed 2026-11-22, found in an outside review). -B
# covers only the first process; a test that starts `python` without -B wrote a .pyc, and a .pyc is trusted when
# the source has the same size and the same mtime second. A one-character swap keeps the size, so the next mutant
# could run the previous mutant's code: false survivors and false kills both.
def _run_tests(sandbox_root: Path, test_mods: List[str], timeout: int, *extra: str):
    return subprocess.run(
        [sys.executable, "-B", "-m", "unittest", *test_mods, *extra],
        cwd=str(sandbox_root),
        capture_output=True,
        encoding="utf-8", errors="replace",     # test output can hold Hebrew; the Windows codepage cannot
        timeout=timeout,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )


def _receipt(relpath: str, test_mods: List[str], root: Path, module_bytes: bytes, total: int, outcome: dict) -> dict:
    """The result, with SHA-256 fingerprints of the module, its tests, and the result itself."""
    test_paths = [_test_module_path(root, m) for m in test_mods]
    test_sha = _sha256_bytes(b"".join(p.read_bytes() for p in test_paths)) if all(test_paths) else None
    result = {
        "module": relpath,
        "test_module": test_mods[0] if len(test_mods) == 1 else " ".join(test_mods),
        "killed": outcome["killed"],
        "total": total,
        "survivors": outcome["survivors"],
        "exempted": outcome["exempted"],
        "timeouts": outcome["timeouts"],
        "errors": outcome["errors"],
        "module_sha256": _sha256_bytes(module_bytes),
        "test_sha256": test_sha,
    }
    result["receipt_sha256"] = _sha256_bytes(json.dumps(result, sort_keys=True).encode("utf-8"))
    return result


def mutate_module(
    relpath: str,
    test_mod,
    *,
    root: Path = REPO_ROOT,
    limit: int = 0,
    timeout: int = 8,
    exemptions: Optional[set[str]] = None,
) -> dict:
    """Run automated AST mutation testing on an isolated temporary copy and return results + SHA-256 receipt.

    The steps: copy the repository somewhere temporary, check the tests pass on the unchanged code, then for each
    mutant write it over the copy, run the tests, sort the outcome, and put the original back.
    """
    test_mods = _test_modules(test_mod)
    module_bytes = (root / relpath).read_bytes()
    tree = ast.parse(module_bytes.decode("utf-8"))
    total = len(collect_mutants(tree, limit=limit))
    exempt = exemptions or set()
    outcome = {"killed": 0, "survivors": [], "exempted": [], "timeouts": [], "errors": []}

    with tempfile.TemporaryDirectory() as tmp:
        sandbox_root = Path(tmp) / "repo"
        _copy_workspace(root, sandbox_root)
        sandbox_file = sandbox_root / relpath
        sandbox_file.chmod(0o644)            # writable in the copy, even if the original is read-only

        baseline = _run_tests(sandbox_root, test_mods, max(timeout, 15))
        if baseline.returncode != 0:
            raise BaselineFailure(
                f"Baseline tests failed for {' '.join(test_mods)} (rc={baseline.returncode}):\n"
                f"{(baseline.stdout + baseline.stderr).strip()}"
            )

        unchanged = sandbox_file.read_bytes()
        for index in range(total):
            lineno, desc, source = _mutant_source(tree, index, limit)
            label = f"{relpath}:{lineno} ({desc})"
            try:
                sandbox_file.write_text(source, encoding="utf-8", newline="\n")
                try:
                    returncode = _run_tests(sandbox_root, test_mods, timeout, "--failfast").returncode
                except subprocess.TimeoutExpired:
                    outcome["timeouts"].append(label)
                    outcome["killed"] += 1            # a mutant that hangs the tests has been noticed
                    continue
                if returncode == 0:                   # the tests passed with the bug in: it survived
                    outcome["exempted" if label in exempt else "survivors"].append(label)
                elif returncode == 2:
                    outcome["errors"].append(f"{label}: runner usage error")
                else:
                    outcome["killed"] += 1
            finally:
                sandbox_file.write_bytes(unchanged)

    return _receipt(relpath, test_mods, root, module_bytes, total, outcome)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Automated AST mutation gate with SHA-256 receipts.")
    parser.add_argument("--module", help="Relative path of a single module to mutate (e.g. symbolics/ledger.py).")
    parser.add_argument("--limit", type=int, default=0, help="Optional cap per module (0 = uncapped, default).")
    args = parser.parse_args(argv)

    exemptions = load_exemptions(REPO_ROOT)
    if args.module:
        norm = args.module.replace("\\", "/")
        if norm not in TARGETS:
            print(f"Unknown module {norm!r}. Known: {', '.join(sorted(TARGETS))}")
            return 2
        selected = {norm: TARGETS[norm]}
    else:
        selected = TARGETS

    total_killed = 0
    total_mutants = 0
    all_survivors: List[str] = []
    all_errors: List[str] = []

    for relpath, test_mod in selected.items():
        res = mutate_module(relpath, test_mod, root=REPO_ROOT, limit=args.limit, exemptions=exemptions)
        total_killed += res["killed"]
        total_mutants += res["total"]
        all_survivors.extend(res["survivors"])
        all_errors.extend(res["errors"])
        print(
            f"{relpath}: {res['killed']}/{res['total']} killed "
            f"(exempt={len(res['exempted'])}, timeouts={len(res['timeouts'])}, sha={res['receipt_sha256'][:12]})"
        )

    print(f"\nTOTAL: {total_killed}/{total_mutants} killed ({len(all_survivors)} unexempted survivors)")
    if all_errors:
        print("ERRORS:")
        for err in all_errors:
            print(f"  {err}")
    if all_survivors:
        print("SURVIVORS:")
        for s in all_survivors:
            print(f"  {s}")
    return 1 if (all_survivors or all_errors) else 0


if __name__ == "__main__":
    raise SystemExit(main())
