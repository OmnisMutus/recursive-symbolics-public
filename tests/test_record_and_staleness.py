"""Dedicated tests for symbolics/record.py, symbolics/ledger_history.py, and symbolics/ledger_staleness.py.

Ground truth:
1. Real `git` CLI commits in an isolated TemporaryDirectory repository.
2. Exact UTC timestamp arithmetic via datetime.timedelta.
"""
import datetime
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from symbolics import ledger_history as lh
from symbolics import ledger_staleness as ls
from symbolics import record as rec


def _git(cwd: Path, *args: str) -> str:
    res = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True)
    return res.stdout.strip()


def _init_git_repo(root: Path) -> None:
    _git(root, "init")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test User")


class TestRecordAppendOnly(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name)
        _init_git_repo(self.repo)
        self.liber = self.repo / "LIBER_0.md"
        self.liber.write_text("line one\nline two\n", encoding="utf-8")
        _git(self.repo, "add", "LIBER_0.md")
        _git(self.repo, "commit", "-m", "init record")

    def test_erased_detects_replacements_and_deletions_only(self):
        self.assertEqual(rec.erased("a\nb\n", "a\nb\nc\n"), [])
        self.assertEqual(rec.erased("a\nb\n", "a\n"), ["b"])
        self.assertEqual(rec.erased("a\nb\n", "a\nchanged\n"), ["b"])

    def test_append_only_commit_passes_and_uncommitted_erasure_fails(self):
        self.liber.write_text("line zero\nline one\nline two\n", encoding="utf-8")
        _git(self.repo, "add", "LIBER_0.md")
        _git(self.repo, "commit", "-m", "append top")
        clean = rec.check(repo=str(self.repo))
        self.assertTrue(clean["ok"])
        self.assertIn("Every commit only added lines.", rec.report(clean))

        self.liber.write_text("line zero\nline two\n", encoding="utf-8")
        res = rec.check(repo=str(self.repo))
        self.assertFalse(res["ok"])
        self.assertEqual(res["uncommitted"], ["line one"])
        self.assertNotIn("Every commit only added lines.", rec.report(res))

    def test_committed_erasure_fails_unless_accepted_in_guards(self):
        self.liber.write_text("line one\n", encoding="utf-8")
        _git(self.repo, "add", "LIBER_0.md")
        _git(self.repo, "commit", "-m", "erase line two")
        sha = _git(self.repo, "rev-parse", "HEAD")

        res_unaccepted = rec.check(repo=str(self.repo))
        self.assertFalse(res_unaccepted["ok"])
        self.assertFalse(res_unaccepted["edits"][0]["recorded"])

        guards_dir = self.repo / "architecture"
        guards_dir.mkdir()
        other_sha = "0000000" if not sha.startswith("0000000") else "1111111"
        (guards_dir / "guards.json").write_text(
            json.dumps({"record_edits": {"accepted": [{"commit": other_sha, "why": "other"}]}}),
            encoding="utf-8",
        )
        res_other = rec.check(repo=str(self.repo))
        self.assertFalse(res_other["ok"])
        self.assertFalse(res_other["edits"][0]["recorded"])

        (guards_dir / "guards.json").write_text(
            json.dumps({"record_edits": {"accepted": [{"commit": sha[:7], "why": "test"}]}}),
            encoding="utf-8",
        )
        res_accepted = rec.check(repo=str(self.repo))
        self.assertTrue(res_accepted["ok"])
        self.assertTrue(res_accepted["edits"][0]["recorded"])


class TestLedgerHistory(unittest.TestCase):
    def test_missing_file_returns_empty_and_roundtrip_saves(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "history.json"
            self.assertEqual(lh.load_history(p), {})
            t0 = datetime.datetime(2026, 1, 1, 12, 0, tzinfo=datetime.timezone.utc)
            hist, prev = lh.record_run({}, [("a.py", 3, 0, 1, 4)], now=t0)
            self.assertIsNone(prev["a.py"])
            lh.save_history(hist, p)
            loaded = lh.load_history(p)
            self.assertEqual(loaded["a.py"]["verified"], 3)
            self.assertEqual(lh.days_since(loaded["a.py"], now=t0 + datetime.timedelta(days=31)), 31.0)
            report = lh.format_freshness_report(
                {"a.py": loaded["a.py"], "b.py": None},
                stale_threshold_days=30.0,
                now=t0 + datetime.timedelta(days=31),
            )
            self.assertIn("[STALE", report)
            self.assertIn("first recorded run", report)
            exact_boundary = lh.format_freshness_report(
                {"a.py": loaded["a.py"]},
                stale_threshold_days=30.0,
                now=t0 + datetime.timedelta(days=30),
            )
            self.assertNotIn("[STALE", exact_boundary)


class TestLedgerStaleness(unittest.TestCase):
    def test_staleness_against_real_git_commits(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            target = repo / "mod.py"
            target.write_text("x = 1\n", encoding="utf-8")
            target2 = repo / "mod2.py"
            target2.write_text("y = 2\n", encoding="utf-8")
            _git(repo, "add", "mod.py", "mod2.py")
            _git(repo, "commit", "-m", "add mod")
            commit_utc = ls.get_last_commit_utc("mod.py", repo_root=repo)
            self.assertIsNotNone(commit_utc)

            targets = {"demo_ledger.py": ["mod.py", "mod2.py"]}
            no_base = ls.compute_staleness_flags({}, target_files=targets, repo_root=repo)
            self.assertFalse(no_base["demo_ledger.py"]["has_baseline"])

            exact_hist = {"demo_ledger.py": {"last_run_utc": commit_utc.isoformat()}}
            exact = ls.compute_staleness_flags(exact_hist, target_files=targets, repo_root=repo)
            self.assertFalse(exact["demo_ledger.py"]["changed_since_check"])
            self.assertEqual(exact["demo_ledger.py"]["most_recent_change_file"], "mod.py")

            fresh_hist = {"demo_ledger.py": {"last_run_utc": (commit_utc + datetime.timedelta(seconds=60)).isoformat()}}
            fresh = ls.compute_staleness_flags(fresh_hist, target_files=targets, repo_root=repo)
            self.assertFalse(fresh["demo_ledger.py"]["changed_since_check"])

            stale_hist = {"demo_ledger.py": {"last_run_utc": (commit_utc - datetime.timedelta(seconds=60)).isoformat()}}
            stale = ls.compute_staleness_flags(stale_hist, target_files=targets, repo_root=repo)
            self.assertTrue(stale["demo_ledger.py"]["changed_since_check"])
            self.assertIn("[REVIEW SUGGESTED]", ls.format_staleness_report(stale))


if __name__ == "__main__":
    unittest.main()
