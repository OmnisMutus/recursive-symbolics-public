"""Can every gate say no?

A gate that cannot fail is not a gate. A check whose verdict is hardcoded, or whose bad case was never tried,
reports PASS forever and looks exactly like a check that is working. The mutation gate does not see this: it
changes operators inside a module, and a module that never compares anything has nothing to change.

So this module runs every gate in the package twice, through its real code: once on an input that should pass,
and once on an input that should fail. A gate is

    OK      the good input passed and the bad input failed
    STUCK   both inputs gave the same verdict: the gate cannot tell them apart
    ERROR   a case raised instead of giving a verdict

It also reads the package's source, and any public function named `check` or `check_...` that is neither
registered here nor listed as not a gate is reported UNREGISTERED. A new gate cannot be added without showing
that it can fail.

The bad inputs are made on purpose (a file that imports `socket`, an ethics module that lets everything through,
a commit that rewords the record) and live in temporary folders. Nothing in the repository is touched.

Run it:  python -m symbolics.range_check
"""
import ast
import os
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
OK, STUCK, ERROR, UNREGISTERED = "OK", "STUCK", "ERROR", "UNREGISTERED"


# ---------------------------------------------------------------- helpers for building cases

def _write(root, relpath, text):
    path = Path(root) / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _git(root, *args):
    # A throwaway identity, so the case works on a machine (or CI runner) with no git user configured.
    subprocess.run(["git", "-c", "user.name=range-check", "-c", "user.email=range-check@example.invalid",
                    "-c", "commit.gpgsign=false", *args],
                   cwd=root, check=True, capture_output=True)


def _repo_with(files_per_commit):
    """A temporary git repository with one commit per dict of {path: text}. The caller removes it."""
    root = tempfile.mkdtemp(prefix="range_check_")
    _git(root, "init", "-q")
    for number, files in enumerate(files_per_commit, 1):
        for relpath, text in files.items():
            _write(root, relpath, text)
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "-m", f"commit {number}")
    return root


def _remove(root):
    # git marks its object files read-only, which stops a plain rmtree on Windows.
    import shutil
    import stat
    shutil.rmtree(root, onerror=lambda f, p, _: (os.chmod(p, stat.S_IWRITE), f(p)))


# ---------------------------------------------------------------- one function per gate: (good passed, bad passed)

def conformance_no_network():
    from . import conformance
    with tempfile.TemporaryDirectory() as bad:
        _write(bad, "leaky.py", "import socket\n")
        good_row = conformance.check_no_network(str(HERE))
        bad_row = conformance.check_no_network(bad)
    return good_row["status"] == conformance.PASS, bad_row["status"] == conformance.PASS


def conformance_non_reduction():
    from . import conformance, ethics
    lets_everything_through = SimpleNamespace(emit=lambda reading: reading, CAVEAT="")

    def passed(e):
        return all(row["status"] == conformance.PASS for row in conformance.check_non_reduction(e))
    return passed(ethics), passed(lets_everything_through)


def conformance_other_state():
    from . import conformance, ethics
    refuses_nothing = SimpleNamespace(check_request=lambda text: None)

    def passed(e):
        return conformance.check_other_state(e)["status"] == conformance.PASS
    return passed(ethics), passed(refuses_nothing)


def conformance_directivity():
    from . import agency, conformance
    # Claims the cap, measures every command at full strength, and lets it all through.
    uncapped = SimpleNamespace(GAMMA_MAX=0.85, directive_strength=lambda text: 1.0,
                               sovereign=lambda **kw: (lambda make: make))

    def passed(a):
        return conformance.check_directivity(a)["status"] == conformance.PASS
    return passed(agency), passed(uncapped)


def conformance_run():
    from . import conformance
    # The honesty guard: with no agency module, one duty is unchecked, and an unchecked duty is not a pass.
    return conformance.run()["conforms"], conformance.run(agency=None)["conforms"]


def ethics_check_request():
    from . import ethics
    own_state = ethics.check_request("I was angry at my brother and cut the session short")
    other_person = ethics.check_request("diagnose my brother and tell me what is wrong with him")
    return own_state is None, other_person is None


def checking_check():
    from . import checking
    return (checking.check("I wonder if this could help.").clean,
            checking.check("You must do this now. Do it immediately.").clean)


def family_f_check_outputs():
    from . import family_f
    study = [("אהבה", "תצשצ"), ("שלום", "בכפי")]           # Atbash

    def passed(proposed):
        results = family_f.check_outputs(study, [("יהוה", proposed)])["results"]
        return all(r["status"] == "VERIFIED" for r in results)
    return passed("מצפץ"), passed("כוזו")


def ledger_all_testable_passed():
    from . import ledger

    def passed(holds):
        book = ledger.CorrespondenceLedger("range check")
        book.register("p", "t", "c", validator=lambda: ledger.ValidationResult(passed=holds))
        book.run()
        return book.all_testable_passed()
    return passed(True), passed(False)


def breaches_check():
    from . import breaches
    entry = "## Entries\n\n### 2026-01-01 a breach\n\n**Result:** CORRECTED\n"
    with tempfile.TemporaryDirectory() as repo:
        _write(repo, "tests/test_guard.py", "def test_guard():\n    pass\n")
        good = breaches.check(entry + "**Guard:** tests/test_guard.py::test_guard\n", {"guards": []}, repo)
        bad = breaches.check(entry, {"guards": []}, repo)                  # names no guard
    return good["ok"], bad["ok"]


def layers_check():
    from . import layers

    def index(path):
        return {"layers": [{"layer": "L", "components": [{"repo": layers.THIS_REPO, "path": path}]}]}
    with tempfile.TemporaryDirectory() as repo:
        _write(repo, "present.py", "")
        return layers.check(index("present.py"), repo)["ok"], layers.check(index("absent.py"), repo)["ok"]


def layers_check_intent():
    from . import layers
    with tempfile.TemporaryDirectory() as repo:
        _write(repo, "doc.md", "The record is only added to.\n")

        def passed(words):
            return layers.check_intent({"purpose": {"text": words, "source": "doc.md"}}, repo)["ok"]
        return passed("The record is only added to."), passed("The record may be rewritten.")


def outgoing_check():
    from . import outgoing
    # Split so this file does not itself carry a home-folder path for the scanner to find.
    home_path = "C:" + "\\Users\\" + "alice\\notes.txt"
    good_repo = _repo_with([{"notes.md": "nothing private here\n"}])
    bad_repo = _repo_with([{"notes.md": f"see {home_path}\n"}])
    try:
        return outgoing.check(good_repo)["ok"], outgoing.check(bad_repo)["ok"]
    finally:
        _remove(good_repo)
        _remove(bad_repo)


def record_check():
    from . import record
    first = {"LIBER_0.md": "first entry\n"}
    good_repo = _repo_with([first, {"LIBER_0.md": "first entry\nsecond entry\n"}])      # only added to
    bad_repo = _repo_with([first, {"LIBER_0.md": "first entry, reworded\n"}])           # an old line changed
    try:
        return record.check(good_repo)["ok"], record.check(bad_repo)["ok"]
    finally:
        _remove(good_repo)
        _remove(bad_repo)


def mutate_module():
    from . import mutate
    module = "def is_adult(age):\n    return age >= 18\n"
    edge_tested = "assert toy.is_adult(18) and not toy.is_adult(17)"
    edge_missed = "assert toy.is_adult(30) and not toy.is_adult(5)"     # never tries 18, so >= -> > survives

    def passed(assertion):
        with tempfile.TemporaryDirectory() as root:
            _write(root, "toy.py", module)
            _write(root, "test_toy.py", textwrap.dedent(f"""\
                import unittest
                import toy
                class T(unittest.TestCase):
                    def test_edge(self):
                        {assertion}
                """))
            return not mutate.mutate_module("toy.py", "test_toy", root=Path(root))["survivors"]
    return passed(edge_tested), passed(edge_missed)


# ---------------------------------------------------------------- the registry

GATES = {
    "conformance.check_no_network": conformance_no_network,
    "conformance.check_non_reduction": conformance_non_reduction,
    "conformance.check_other_state": conformance_other_state,
    "conformance.check_directivity": conformance_directivity,
    "conformance.run": conformance_run,
    "ethics.check_request": ethics_check_request,
    "checking.check": checking_check,
    "family_f.check_outputs": family_f_check_outputs,
    "ledger.all_testable_passed": ledger_all_testable_passed,
    "breaches.check": breaches_check,
    "layers.check": layers_check,
    "layers.check_intent": layers_check_intent,
    "outgoing.check": outgoing_check,
    "record.check": record_check,
    "mutate.mutate_module": mutate_module,
}

# Functions whose names look like gates but are not ones on their own, each with the reason.
NOT_GATES = {
    "layers.check_component": "one row of layers.check, which is range-checked as a whole",
    "layers.check_layer": "one layer of layers.check, which is range-checked as a whole",
}


def gate_names(package_dir=HERE):
    """Every public top-level function named `check` or `check_...` in the package, as 'module.function'."""
    found = set()
    for path in sorted(Path(package_dir).glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and (node.name == "check" or node.name.startswith("check_")):
                found.add(f"{path.stem}.{node.name}")
    return found


def unregistered(package_dir=HERE, gates=GATES, not_gates=NOT_GATES):
    return sorted(gate_names(package_dir) - set(gates) - set(not_gates))


def verdict(case):
    """Run one gate's two cases and say whether it can tell them apart."""
    try:
        good, bad = case()
    except Exception as e:
        return {"status": ERROR, "detail": f"{type(e).__name__}: {e}"}
    # Only True and False are verdicts. A 1, a dict or None would compare in ways that hide what happened.
    if not (isinstance(good, bool) and isinstance(bad, bool)):
        return {"status": ERROR, "detail": f"a case must give two booleans, got {good!r} and {bad!r}"}
    if good and not bad:
        return {"status": OK, "detail": "good input passed, bad input failed"}
    if good == bad:
        return {"status": STUCK, "detail": f"both inputs {'passed' if good else 'failed'}"}
    return {"status": STUCK, "detail": "backwards: the good input failed and the bad input passed"}


def run(gates=GATES, package_dir=HERE, not_gates=NOT_GATES):
    rows = [dict(gate=name, **verdict(case)) for name, case in gates.items()]
    rows += [{"gate": name, "status": UNREGISTERED, "detail": "a gate with no good and bad case registered here"}
             for name in unregistered(package_dir, gates, not_gates)]
    return {"rows": rows, "ok": bool(rows) and all(r["status"] == OK for r in rows)}


def report(result):
    lines = ["RANGE CHECK: can every gate both pass and fail?", ""]
    for r in result["rows"]:
        lines.append(f"  {r['status']:<12} {r['gate']:<34} {r['detail']}")
    lines += ["", f"RANGE OK: {result['ok']}"]
    return "\n".join(lines)


def main():
    result = run()
    print(report(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
