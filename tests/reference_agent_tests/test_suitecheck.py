"""Reading a suite's result honestly (suitecheck.py).

Ground truth, in the order STANDARD.md asks for it:

1. INDEPENDENT REFERENCE. REAL below is verbatim runner output from another project on this machine on
   2026-11-09, with the verdict each one deserves written beside it. It was typed from what those runners
   actually printed, not from this module. Three of the rows are the exact outputs that were misread earlier
   that day, which is why this module exists.
2. A SECOND IMPLEMENTATION. None is needed: the thing under test is the reading of a runner's own words, and
   the runner is the second implementation. What is asserted is that this module never contradicts it and
   never goes beyond it.
3. BY HAND. Each row's counts are written out, so a reader can check the verdict against the numbers without
   running anything.

The rule under test, in one line: a verdict is withheld unless the evidence is unambiguous, and a skip, an
expected failure or a missing dependency makes it ambiguous.
"""
import os
import shutil
import sys
import tempfile
import unittest

from reference_agent import suitecheck

G, R, U = suitecheck.GREEN, suitecheck.RED, suitecheck.UNCLEAR

# (what it was, the runner's output, the verdict it deserves, a phrase the reason must contain)
REAL = [
    ("solo/tests, all 40 files",
     "Ran 463 tests in 9.912s\n\nOK\n", G, "nothing skipped"),
    ("test_run_all_correspondence_ledgers: a stale baseline",
     "FAIL: test_real_ledgers_match_current_known_baseline\nAssertionError: 16 != 15\n"
     "Ran 11 tests in 6.346s\n\nFAILED (failures=1)\n", R, "failure"),
    ("test_reconstructed_frameworks_comparison: PyTorch absent",
     "test_x ... skipped 'PyTorch not installed in this environment -- see module docstring'\n"
     "Ran 6 tests in 0.000s\n\nOK (skipped=6)\n", U, "not a verification"),
    ("a suite with registered expected failures",
     "Ran 11 tests in 1.0s\n\nFAILED (failures=1, expected failures=2)\n", U, "may be deliberate"),
    ("a recorded gap that has closed",
     "Ran 11 tests in 1.0s\n\nOK (unexpected successes=1)\n", U, "stale"),
    ("a wrapper's own prose summary, which is not a suite result",
     "    23 of 24 engines are implemented and correctness-verified\n", U, "not a unittest result"),
    ("nothing collected",
     "NO TESTS RAN\n", U, "collected no tests"),
    ("a module that would not import",
     "ModuleNotFoundError: No module named 'standalone_rca_sandbox'\n"
     "Ran 0 tests in 0.000s\n\nFAILED (errors=1)\n", U, "zero tests"),
]


class TestTheRealOutputs(unittest.TestCase):
    def test_every_row(self):
        for what, text, expected, phrase in REAL:
            kind, why = suitecheck.verdict(suitecheck.parse(text))
            self.assertEqual(kind, expected, f"{what}: got {kind}, {why}")
            self.assertTrue(any(phrase in w for w in why), f"{what}: {why} lacks {phrase!r}")

    def test_green_is_the_only_verdict_that_claims_anything(self):
        """UNCLEAR must say so in words, because the next step after a wrong 'broken' is editing working code."""
        result = {"verdict": U, "why": ["6 test(s) skipped, and a skip is not a verification"],
                  "parsed": {"ran": 6, "skipped": 6}}
        text = suitecheck.report(result)
        self.assertIn("Nothing should be edited", text)

    def test_counts_come_from_the_runners_own_line(self):
        p = suitecheck.parse("Ran 20 tests in 1s\n\nFAILED (failures=2, errors=1, skipped=3, "
                             "expected failures=4, unexpected successes=5)\n")
        self.assertEqual((p["ran"], p["failures"], p["errors"], p["skipped"]), (20, 2, 1, 3))
        self.assertEqual((p["expected failures"], p["unexpected successes"]), (4, 5))

    def test_a_missing_dependency_is_named_not_treated_as_breakage(self):
        kind, why = suitecheck.verdict(suitecheck.parse(
            "ModuleNotFoundError: No module named 'sklearn'\nRan 5 tests in 1s\n\nOK (skipped=4)\n"))
        self.assertEqual(kind, U)
        self.assertTrue(any("sklearn" in w for w in why), why)

    def test_a_clean_run_that_exits_nonzero_is_unclear(self):
        """A runner applying a rule of its own, such as treating skips as not-verified, must not read GREEN."""
        out = suitecheck.run([sys.executable, "-c",
                              "import sys;sys.stderr.write('Ran 3 tests in 0.1s\\n\\nOK\\n');sys.exit(1)"])
        self.assertEqual(out["verdict"], U)
        self.assertTrue(any("exited 1" in w for w in out["why"]), out["why"])

    def test_a_failing_suite_is_a_result_not_an_exception(self):
        out = suitecheck.run([sys.executable, "-c",
                              "import sys;sys.stderr.write('Ran 1 test in 0s\\n\\nFAILED (failures=1)\\n')"])
        self.assertEqual(out["verdict"], R)

    def test_a_command_that_cannot_run_is_unclear(self):
        self.assertEqual(suitecheck.run(["/nonexistent/runner"])["verdict"], U)



if __name__ == "__main__":
    unittest.main()


class TestTheCorpusOwnFormat(unittest.TestCase):
    """Seven files in the ported corpus print their own summary instead of using unittest. Counting only the
    unittest files under-reported that suite by seven files' worth of checks, which is a silent omission and
    the same class of error as a misread. Ground truth: the real output of corpus/tests/test_dht_rca_node.py
    on 2026-11-09."""

    REAL = ("  PASS: _get_bucket_index matches bit_length()-1 ground truth near power-of-two distances\n"
            "  PASS: find_closest_nodes returns same top-5 order as independent sort\n\n"
            "  SUMMARY: 10 passed, 0 failed (out of 10 correctness checks)\n")

    def test_its_own_summary_is_read(self):
        p = suitecheck.parse(self.REAL)
        self.assertEqual((p["ran"], p["failures"]), (10, 0))
        self.assertEqual(suitecheck.verdict(p)[0], G)

    def test_a_failure_in_that_format_is_red(self):
        kind, why = suitecheck.verdict(suitecheck.parse(
            "  SUMMARY: 8 passed, 2 failed (out of 10 correctness checks)\n"))
        self.assertEqual(kind, R)
        self.assertIn("2 of 10", why[0])

    def test_a_wrappers_prose_still_gets_no_verdict(self):
        """The guard that matters: a per-engine rollup is not a suite result, whatever it claims."""
        for prose in ("    23 of 24 engines are implemented and correctness-verified\n",
                      "    15 of 17 tool scripts are correctness-verified\n",
                      "  VERIFIED -> tests/test_x.py passed in 107.5 ms\n"):
            self.assertEqual(suitecheck.verdict(suitecheck.parse(prose))[0], U, prose)

    def test_unittest_output_still_wins_when_both_appear(self):
        both = "SUMMARY: 1 passed, 0 failed\nRan 5 tests in 1s\n\nFAILED (failures=3)\n"
        p = suitecheck.parse(both)
        self.assertEqual((p["ran"], p["failures"]), (5, 3))
        self.assertEqual(suitecheck.verdict(p)[0], R)


class TestTheEnvironmentIsNotTheCode(unittest.TestCase):
    """Ground truth: the real output of corpus/tools/debugger.py on 2026-11-09, run inside a mount that
    denies deletion. Its self-test calls Path.unlink() on its own temporary file, fails, and the suite reports
    three failures. The same files in a writable directory pass. Scoring that RED blames working code for
    where it was run."""

    REAL = ("2026-11-09 19:41:48,899 |    ERROR | Self-test failure: [Errno 1] Operation not permitted: "
            "'/sessions/.../corpus/tools/temp_feedback_log.jsonl'\n    tmp_log.unlink()\n"
            "Ran 24 tests in 0.5s\n\nFAILED (failures=3)\n")

    def test_a_denied_operation_is_not_a_failure(self):
        kind, why = suitecheck.verdict(suitecheck.parse(self.REAL))
        self.assertEqual(kind, U)
        self.assertTrue(any("environment refused" in w for w in why), why)
        self.assertTrue(any("where it ran" in w for w in why), why)

    def test_a_genuine_failure_is_still_red(self):
        """The guard must not swallow real failures: no denial in this output."""
        kind, _why = suitecheck.verdict(suitecheck.parse(
            "FAIL: test_baseline\nAssertionError: 16 != 15\nRan 11 tests in 6.3s\n\nFAILED (failures=1)\n"))
        self.assertEqual(kind, R)

    def test_read_only_and_permission_denied_count_too(self):
        for phrase in ("OSError: [Errno 30] Read-only file system: '/x'",
                       "PermissionError: [Errno 13] Permission denied: '/y'"):
            p = suitecheck.parse(phrase + "\nRan 2 tests in 0s\n\nFAILED (failures=1)\n")
            self.assertTrue(p["env_denied"], phrase)
            self.assertEqual(suitecheck.verdict(p)[0], U, phrase)


class TestTheGapsMutationFound(unittest.TestCase):
    """Added 2026-11-20 for the public repository: each test kills a mutant that survived the original suite."""

    def test_unittest_failed_beats_a_script_summary_that_says_all_passed(self):
        """line 91, both mutants: when the runner's own FAILED line is present, its counts decide, even if a
        script's SUMMARY line claims nothing failed. Ground truth: the FAILED line names one failure."""
        text = "SUMMARY: 5 passed, 0 failed\nRan 5 tests in 0.1s\n\nFAILED (failures=1)\n"
        kind, why = suitecheck.verdict(suitecheck.parse(text))
        self.assertEqual(kind, R, why)
        self.assertIn("1 failure(s)", why[0])

    def test_a_result_printed_to_stdout_is_read(self):
        """line 132, (done.stdout or ""): unittest writes to stderr, but other runners print to stdout."""
        out = suitecheck.run([sys.executable, "-c", "print('Ran 2 tests in 0.1s\\n\\nOK')"])
        self.assertEqual(out["verdict"], G, out["why"])
        self.assertEqual(out["parsed"]["ran"], 2)

    def test_a_failing_suite_that_exits_1_stays_red(self):
        """line 136: only a GREEN with a nonzero exit becomes UNCLEAR. A real failing run exits 1, and that is
        still a plain RED, not an ambiguity."""
        out = suitecheck.run([sys.executable, "-c",
                              "import sys;sys.stderr.write('Ran 1 test in 0s\\n\\nFAILED (failures=1)\\n');sys.exit(1)"])
        self.assertEqual(out["verdict"], R, out["why"])

    def test_the_report_prints_the_parsed_counts(self):
        """line 144, result.get("parsed") or {}: the report carries the runner's numbers."""
        result = {"verdict": U, "why": ["6 test(s) skipped, and a skip is not a verification"],
                  "parsed": {"ran": 6, "skipped": 6, "exit_code": 0, "summary_line": "OK (skipped=6)"}}
        text = suitecheck.report(result)
        self.assertIn("ran 6, failures 0, errors 0, skipped 6", text)
        self.assertIn("the runner's own line: OK (skipped=6)", text)