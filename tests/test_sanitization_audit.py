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
SCAN_EXTS = (".py", ".md", ".json", ".toml", ".yml", ".yaml", ".txt", ".cfg", ".ini", ".go", ".mod", ".bat")
SKIP_DIRS = (".git", "__pycache__", ".venv", "venv", "build", "dist")


ALLOW = "allow "


def _denylist_lines(path):
    with open(path, encoding="utf-8") as fh:
        return [ln.strip() for ln in fh if ln.strip() and not ln.lstrip().startswith("#")]


def load_denylist(path=DENYLIST_PATH):
    """The compiled private patterns, or None when no denylist file exists here."""
    if not os.path.isfile(path):
        return None
    patterns = [ln for ln in _denylist_lines(path) if not ln.startswith(ALLOW)]
    return re.compile("|".join(f"(?:{p})" for p in patterns), re.IGNORECASE) if patterns else None


def load_allowances(path=DENYLIST_PATH):
    """Exact exceptions, also kept in the denylist file: a line `allow <repo-relative file> <regex>` lets a match
    stand on lines of THAT file that match the regex, and nowhere else. Added 2026-11-20 for the README's clone
    URL, which must name the maintainer's handle. Kept out of version control for the same reason as the denylist:
    an exception written here would have to spell out the name it excuses."""
    if not os.path.isfile(path):
        return []
    out = []
    for ln in _denylist_lines(path):
        if ln.startswith(ALLOW):
            parts = ln[len(ALLOW):].strip().split(None, 1)
            if len(parts) != 2:
                raise ValueError(f"malformed allowance (want: allow <file> <regex>): {ln!r}")
            out.append((parts[0].replace("\\", "/"), re.compile(parts[1])))
    return out


def allowed(rel, line, allowances):
    return any(rel == f and rx.search(line) for f, rx in allowances)


def _git_ignored(rels):
    """The subset of repository-relative paths that git ignores (.gitignore or .git/info/exclude), so never
    publishes. Empty when git is unavailable, which makes the scan cover everything: the safe direction."""
    if not rels or shutil.which("git") is None or not os.path.isdir(os.path.join(ROOT, ".git")):
        return set()
    # Bytes, not text=True: on Windows text mode turns each "\n" into "\r\n", git then reads "name\r" and matches
    # no ignore rule, and every file would be scanned (found 2026-11-20).
    p = subprocess.run(["git", "check-ignore", "--stdin"], cwd=ROOT, input=("\n".join(rels) + "\n").encode(),
                       capture_output=True)
    return {line.strip().replace("\\", "/") for line in p.stdout.decode("utf-8", "replace").splitlines()
            if line.strip()}


def scanned_files():
    """Every text file git would publish. Files git ignores are skipped (added 2026-11-20): a maintainer's local
    notes, such as a publishing checklist naming the maintainer's own paths, are never uploaded, and scanning them
    made the audit fail on text that cannot leak."""
    found = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.endswith(".egg-info")]
        for name in sorted(filenames):
            if name.endswith(SCAN_EXTS) or name in (".gitignore",):
                found.append(os.path.relpath(os.path.join(dirpath, name), ROOT).replace("\\", "/"))
    ignored = _git_ignored(found)
    for rel in found:
        if rel in ignored:
            continue
        with open(os.path.join(ROOT, rel), encoding="utf-8", errors="ignore") as fh:
            yield rel, fh.read()


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
        allowances = load_allowances()
        hits = []
        for rel, text in scanned_files():
            for idx, line in enumerate(text.splitlines(), 1):
                m = forbidden.search(line)
                if m and not allowed(rel, line, allowances):
                    hits.append(f"{rel}:{idx}: matched {m.group(0)!r}")
        self.assertEqual(hits, [], "Forbidden private identifiers remain:\n" + "\n".join(hits))

    def test_an_allowance_excuses_one_file_and_one_line_shape_only(self):
        # Ground truth by construction: a throwaway denylist with one pattern and one allowance.
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "deny")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("# comment\nsecretname\nallow README.md ^git clone https://example\\.org/secretname/\n")
            rx, allows = load_denylist(path), load_allowances(path)
            self.assertTrue(rx.search("SecretName here"))
            self.assertFalse(rx.search("allow README.md"))                  # the allow line is not a pattern
            line = "git clone https://example.org/secretname/repo.git"
            self.assertTrue(allowed("README.md", line, allows))
            self.assertFalse(allowed("docs/README.md", line, allows))       # another file
            self.assertFalse(allowed("README.md", "secretname elsewhere", allows))   # another line
            with open(path, "a", encoding="utf-8") as fh:
                fh.write("allow README.md\n")
            with self.assertRaises(ValueError):
                load_allowances(path)

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
        # Optional extras, named in pyproject.toml: NumPy for the engines and corpus, scikit-learn for the corpus's
        # comparisons, PyTorch for one corpus benchmark that says so when it is absent. Found 2026-11-20 by the first
        # CI run on a clean runner: this machine had all three installed, so their imports always resolved here.
        optional_third_party = {"numpy", "sklearn", "torch"}
        unresolved = []
        # corpus/ runs its files with its own subfolders on sys.path (see corpus/run_all_correspondence_ledgers.py
        # and corpus/run_corpus.py), so a bare `import x` there resolves to any corpus/<sub>/x.py.
        corpus = os.path.join(ROOT, "corpus")
        corpus_modules = set()
        for dirpath, dirnames, filenames in os.walk(corpus):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            corpus_modules.update(f[:-3] for f in filenames if f.endswith(".py"))
            corpus_modules.update(dirnames)

        for dirpath, dirnames, filenames in os.walk(ROOT):
            dirnames[:] = [d for d in dirnames if d not in (".git", "__pycache__", ".venv", "venv")]
            for name in sorted(filenames):
                if not name.endswith(".py"):
                    continue
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, ROOT)
                with open(full, encoding="utf-8") as fh:
                    tree = ast.parse(fh.read(), filename=full)
                in_corpus = rel.split(os.sep)[0] == "corpus"
                for node in ast.walk(tree):
                    if in_corpus and isinstance(node, (ast.Import, ast.ImportFrom)):
                        names = ([a.name for a in node.names] if isinstance(node, ast.Import)
                                 else [node.module] if node.module and node.level == 0 else [])
                        if all(n.split(".")[0] in corpus_modules for n in names):
                            continue
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
