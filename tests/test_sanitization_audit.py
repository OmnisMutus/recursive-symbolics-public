"""Automated sanitization & import-hygiene audit.

Guarantees that the repository contains:
1. Zero local home-folder paths (checked everywhere, by symbolics.outgoing's scanner).
2. Zero maintainer-private identifiers, checked against a denylist that lives OUTSIDE version control.
3. Zero broken Python imports across all core, engine, example, and test files (except explicitly optional numpy).

Why the denylist is not in this file: a list of the private names a public repository must never contain is
itself a list of those names. Publishing it would leak exactly what it guards. So the patterns are read from a
local, gitignored file (default `.sanitize-denylist` at the repository root, or the path in the
SANITIZE_DENYLIST environment variable): one case-insensitive regex per line, `#` for comments.

A clone without that file reports the private check as SKIPPED, visibly, never as a pass. If the file exists it
must be ignored by git, or the audit fails: a denylist that could be committed is not doing its job.
"""

from __future__ import annotations

import ast
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import unittest

from symbolics import outgoing

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DENYLIST_PATH = os.environ.get("SANITIZE_DENYLIST") or os.path.join(ROOT, ".sanitize-denylist")
SCAN_EXTS = (".py", ".md", ".json", ".toml", ".yml", ".yaml", ".txt", ".cfg", ".ini")
SKIP_DIRS = (".git", "__pycache__", ".venv", "venv", "build", "dist")


def load_denylist(path=DENYLIST_PATH):
    """The compiled private patterns, or None when no denylist file exists here."""
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        patterns = [ln.strip() for ln in fh if ln.strip() and not ln.lstrip().startswith("#")]
    return re.compile("|".join(f"(?:{p})" for p in patterns), re.IGNORECASE) if patterns else None


def scanned_files():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.endswith(".egg-info")]
        for name in sorted(filenames):
            if name.endswith(SCAN_EXTS) or name in (".gitignore",):
                full = os.path.join(dirpath, name)
                with open(full, encoding="utf-8", errors="ignore") as fh:
                    yield os.path.relpath(full, ROOT).replace("\\", "/"), fh.read()


class TestSanitizationAudit(unittest.TestCase):
    def test_no_home_folder_paths_in_repository(self):
        path_hits = []
        for rel, text in scanned_files():
            for line_no, user, _sample in outgoing.scan(text):
                # test_outgoing.py purposefully constructs synthetic "ada"/"grace" path strings to test outgoing.scan
                if rel == "tests/test_outgoing.py" and user in ("ada", "grace"):
                    continue
                path_hits.append(f"{rel}:{line_no}: path username {user!r}")
        self.assertEqual(path_hits, [], "Home-folder path leaks remain:\n" + "\n".join(path_hits))

    def test_no_private_identifiers_from_local_denylist(self):
        forbidden = load_denylist()
        if forbidden is None:
            self.skipTest(f"no private denylist at {DENYLIST_PATH}; maintainer-only check not run")
        hits = []
        for rel, text in scanned_files():
            for idx, line in enumerate(text.splitlines(), 1):
                m = forbidden.search(line)
                if m:
                    hits.append(f"{rel}:{idx}: matched {m.group(0)!r}")
        self.assertEqual(hits, [], "Forbidden private identifiers remain:\n" + "\n".join(hits))

    def test_local_denylist_can_never_be_committed(self):
        if not os.path.isfile(DENYLIST_PATH):
            self.skipTest("no local denylist present")
        if shutil.which("git") is None or not os.path.isdir(os.path.join(ROOT, ".git")):
            self.skipTest("not a git checkout")
        rel = os.path.relpath(DENYLIST_PATH, ROOT)
        if rel.startswith(".."):
            return  # lives outside the repository: git cannot pick it up
        tracked = subprocess.run(["git", "ls-files", "--error-unmatch", rel], cwd=ROOT, capture_output=True)
        self.assertNotEqual(tracked.returncode, 0, f"{rel} is TRACKED by git; remove it from the index now")
        ignored = subprocess.run(["git", "check-ignore", "-q", rel], cwd=ROOT, capture_output=True)
        self.assertEqual(ignored.returncode, 0, f"{rel} is not gitignored; add it to .gitignore")

    def test_all_python_files_parse_and_resolve_internal_imports(self):
        if ROOT not in sys.path:
            sys.path.insert(0, ROOT)
        stdlib = getattr(sys, "stdlib_module_names", frozenset())
        local_roots = {"symbolics", "engines", "examples", "tests"}
        optional_third_party = {"numpy"}
        unresolved = []

        for dirpath, dirnames, filenames in os.walk(ROOT):
            dirnames[:] = [d for d in dirnames if d not in (".git", "__pycache__", ".venv", "venv")]
            for name in sorted(filenames):
                if not name.endswith(".py"):
                    continue
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, ROOT)
                with open(full, encoding="utf-8") as fh:
                    tree = ast.parse(fh.read(), filename=full)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            top = alias.name.split(".")[0]
                            if top in stdlib or top in optional_third_party:
                                continue
                            # Engine scripts support running either as module or script; check inside engines/ too
                            if importlib.util.find_spec(top) is None and not os.path.exists(
                                os.path.join(ROOT, "engines", f"{top}.py")
                            ):
                                unresolved.append(f"{rel}: import {alias.name}")
                    elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                        top = node.module.split(".")[0]
                        if top in stdlib or top in optional_third_party:
                            continue
                        if top in local_roots:
                            if importlib.util.find_spec(node.module) is None:
                                unresolved.append(f"{rel}: from {node.module} import ...")
                        elif os.path.exists(os.path.join(ROOT, "engines", f"{top}.py")):
                            continue
                        elif importlib.util.find_spec(top) is None:
                            unresolved.append(f"{rel}: from {node.module} import ...")

        self.assertEqual(unresolved, [], "Unresolved imports detected:\n" + "\n".join(unresolved))


if __name__ == "__main__":
    unittest.main()
