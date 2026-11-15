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
    "symbolics/ledger_history.py": "tests.test_record_and_staleness",
    "symbolics/ledger_staleness.py": "tests.test_record_and_staleness",
    "engines/safe_memory_boundary_engine.py": "tests.test_safe_memory_boundary_engine",
    "engines/sovereign_wrapper.py": "tests.test_sovereign_wrapper",
    "engines/recursive_attractor_engine.py": "tests.test_recursive_attractor_engine",
    "engines/engine_composition_loop.py": "tests.test_engine_composition_loop",
    "engines/standalone_rca_sandbox.py": "tests.test_standalone_rca_sandbox",
    "engines/athanor.py": "tests.test_athanor",
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
        if limit > 0 and len(mutants) >= limit:
            break
        lineno = getattr(node, "lineno", 0)
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            op_type = type(node.ops[0])
            if op_type in CMP_SWAPS:
                if isinstance(node.left, ast.Name) and node.left.id == "__name__":
                    continue
                mutants.append((lineno, f"{op_type.__name__}->{CMP_SWAPS[op_type].__name__}", node, "cmp"))
        elif isinstance(node, ast.BinOp) and type(node.op) in BIN_SWAPS:
            op_type = type(node.op)
            mutants.append((lineno, f"{op_type.__name__}->{BIN_SWAPS[op_type].__name__}", node, "bin"))
        elif isinstance(node, ast.BoolOp):
            new_op = ast.Or if isinstance(node.op, ast.And) else ast.And
            mutants.append((lineno, f"{type(node.op).__name__}->{new_op.__name__}", node, "boolop"))
    return mutants


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


def mutate_module(
    relpath: str,
    test_mod: str,
    *,
    root: Path = REPO_ROOT,
    limit: int = 0,
    timeout: int = 8,
    exemptions: Optional[set[str]] = None,
) -> dict:
    """Run automated AST mutation testing on an isolated temporary copy and return results + SHA-256 receipt."""
    orig_path = root / relpath
    orig_bytes = orig_path.read_bytes()
    orig_text = orig_bytes.decode("utf-8")
    tree = ast.parse(orig_text)
    specs = collect_mutants(tree, limit=limit)
    exempt = exemptions or set()

    killed = 0
    timeouts: List[str] = []
    errors: List[str] = []
    survivors: List[str] = []
    exempted: List[str] = []

    with tempfile.TemporaryDirectory() as tmp:
        sandbox_root = Path(tmp) / "repo"
        _copy_workspace(root, sandbox_root)
        sandbox_file = sandbox_root / relpath
        # Ensure writable inside temp sandbox even if original file is read-only.
        sandbox_file.chmod(0o644)

        baseline = subprocess.run(
            [sys.executable, "-B", "-m", "unittest", test_mod],
            cwd=str(sandbox_root),
            capture_output=True,
            text=True,
            timeout=max(timeout, 15),
        )
        if baseline.returncode != 0:
            raise BaselineFailure(
                f"Baseline tests failed for {test_mod} (rc={baseline.returncode}):\n"
                f"{(baseline.stdout + baseline.stderr).strip()}"
            )

        sandbox_orig_bytes = sandbox_file.read_bytes()
        for idx in range(len(specs)):
            m_tree = copy.deepcopy(tree)
            m_specs = collect_mutants(m_tree, limit=limit)
            lineno, desc, target_node, kind = m_specs[idx]
            if kind == "cmp":
                target_node.ops[0] = CMP_SWAPS[type(target_node.ops[0])]()
            elif kind == "bin":
                target_node.op = BIN_SWAPS[type(target_node.op)]()
            elif kind == "boolop":
                target_node.op = ast.Or() if isinstance(target_node.op, ast.And) else ast.And()

            mutated_src = ast.unparse(m_tree)
            label = f"{relpath}:{lineno} ({desc})"
            try:
                sandbox_file.write_text(mutated_src, encoding="utf-8", newline="\n")
                try:
                    res = subprocess.run(
                        [sys.executable, "-B", "-m", "unittest", test_mod, "--failfast"],
                        cwd=str(sandbox_root),
                        capture_output=True,
                        text=True,
                        timeout=timeout,
                    )
                    if res.returncode == 0:
                        if label in exempt:
                            exempted.append(label)
                        else:
                            survivors.append(label)
                    elif res.returncode == 2:
                        errors.append(f"{label}: runner usage error")
                    else:
                        killed += 1
                except subprocess.TimeoutExpired:
                    timeouts.append(label)
                    killed += 1
            finally:
                sandbox_file.write_bytes(sandbox_orig_bytes)

    test_path = _test_module_path(root, test_mod)
    test_sha = _sha256_bytes(test_path.read_bytes()) if test_path else None
    mod_sha = _sha256_bytes(orig_bytes)
    receipt_payload = json.dumps(
        {
            "module": relpath,
            "module_sha256": mod_sha,
            "test_module": test_mod,
            "test_sha256": test_sha,
            "killed": killed,
            "total": len(specs),
            "survivors": survivors,
            "exempted": exempted,
            "timeouts": timeouts,
            "errors": errors,
        },
        sort_keys=True,
    ).encode("utf-8")

    return {
        "module": relpath,
        "test_module": test_mod,
        "killed": killed,
        "total": len(specs),
        "survivors": survivors,
        "exempted": exempted,
        "timeouts": timeouts,
        "errors": errors,
        "module_sha256": mod_sha,
        "test_sha256": test_sha,
        "receipt_sha256": _sha256_bytes(receipt_payload),
    }


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
