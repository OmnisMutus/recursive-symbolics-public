"""Reading a test suite's result honestly, and refusing to give a verdict when the evidence does not support one.

This exists because of a specific failure, made three times in one session by the agent this repository runs:

1. a wrapper script's per-component summary was reported as the suite's result. It counted a missing-dependency
   skip as a correctness failure, and it covered 24 of 40 test files, so a real failure never appeared;
2. an import harness reported 71 of 71 modules broken. The harness was broken, not the modules;
3. a record was called stale on the basis of its oldest entry, read from the tail of a newest-first file.

Each time the mistake was the same shape: a conclusion drawn from a layer above the evidence. The danger is
not the misreading itself, it is what follows, because the next step after "this is broken" is editing
somebody's working code.

So the rule here is that a verdict is withheld unless it is unambiguous:

- **GREEN** needs tests that ran and nothing else at all: no failures, no errors, **no skips**, no expected
  failures, no unexpected successes. A skip is not a verification, which is this project's own standard.
- **RED** needs a failure or an error that is not accounted for as expected.
- **UNCLEAR** is everything else, and it is a legitimate result rather than a fallback. Zero tests collected,
  any skip, any expected failure, a missing dependency, output this cannot parse: each one means the suite did
  not tell us what we wanted to know, and the honest move is to say so rather than to pick the nearer verdict.

`expected failures` matter most here. A suite can be designed to fail on purpose, and a framework that
registers known gaps will report failures that are not regressions. Treating those as breakage is how working
code gets "fixed". If this module sees any, it refuses GREEN and refuses RED, and says to go and read which
ones were expected.
"""
import re
import subprocess

GREEN, RED, UNCLEAR = "GREEN", "RED", "UNCLEAR"

RAN = re.compile(r"^Ran (\d+) tests? in ", re.M)
NO_TESTS = re.compile(r"^NO TESTS RAN", re.M)
OK = re.compile(r"^OK(?:\s*\((.*)\))?\s*$", re.M)
FAILED = re.compile(r"^FAILED\s*\((.*)\)\s*$", re.M)
COUNT = re.compile(r"(failures|errors|skipped|expected failures|unexpected successes)=(\d+)")
MISSING = re.compile(r"ModuleNotFoundError: No module named '([^']+)'")
# The environment refusing an operation is not the code failing. Demonstrated 2026-11-09: a suite's own
# self-test called Path.unlink() on its temporary file, which the bridge mount denies, and it reported three
# failures. The same files in a writable directory passed. A reader that scores that RED blames working code
# for where it was run, which is the precise failure this module exists to prevent.
DENIED = re.compile(r"(?:PermissionError|OSError).{0,80}?(?:Operation not permitted|Permission denied|"
                    r"Read-only file system)|\[Errno (?:1|13|30)\]", re.S)
SKIP_REASON = re.compile(r"skipped ['\"]([^'\"]{0,120})")
# A second real format, found in the ported corpus: hand-rolled scripts that print PASS: lines and their own
# summary instead of using unittest. Seven files in that corpus use it, and counting only the unittest ones
# under-reported the suite by seven files' worth of checks. A format this cannot read is a silent omission,
# which is the same failure as a misread, so a known format is better than a safe refusal.
OWN_SUMMARY = re.compile(r"^\s*SUMMARY:\s*(\d+)\s+passed,\s*(\d+)\s+failed", re.M)

FIELDS = ("failures", "errors", "skipped", "expected failures", "unexpected successes")


def parse(output):
    """Everything unittest's own summary says, with nothing inferred."""
    text = output or ""
    out = {k: 0 for k in FIELDS}
    ran = RAN.search(text)
    out["ran"] = int(ran.group(1)) if ran else 0
    out["saw_ran_line"] = bool(ran)
    out["no_tests_ran"] = bool(NO_TESTS.search(text))
    own = OWN_SUMMARY.search(text)
    out["own_summary"] = bool(own)
    if own and not ran:
        out["ran"] = int(own.group(1)) + int(own.group(2))
        out["failures"] = int(own.group(2))
        out["saw_ran_line"] = True          # this runner stated its own counts, which is what the line is for
    tail = FAILED.search(text) or OK.search(text)
    out["summary_line"] = (tail.group(0).strip() if tail else "")
    out["said_ok"] = bool(OK.search(text))
    out["said_failed"] = bool(FAILED.search(text))
    if tail and tail.group(1):
        for name, number in COUNT.findall(tail.group(1)):
            out[name] = int(number)
    out["missing_deps"] = sorted(set(MISSING.findall(text)))
    out["env_denied"] = bool(DENIED.search(text))
    out["skip_reasons"] = sorted(set(SKIP_REASON.findall(text)))[:8]
    return out


def verdict(parsed):
    """(verdict, [reasons]). UNCLEAR is a result, not a failure to produce one."""
    why = []
    if parsed.get("no_tests_ran"):
        return UNCLEAR, ["the runner collected no tests, so nothing was checked"]
    if not parsed.get("saw_ran_line"):
        return UNCLEAR, ["no 'Ran N tests' line, so this output is not a unittest result this can read"]
    if parsed.get("ran", 0) == 0:
        return UNCLEAR, ["zero tests ran"]
    if parsed.get("own_summary") and not (parsed.get("said_ok") or parsed.get("said_failed")):
        if parsed.get("failures"):
            return RED, [f"{parsed['failures']} of {parsed['ran']} checks failed, by the script's own summary"]
        return GREEN, [f"{parsed['ran']} check(s) passed, by the script's own summary"]
    if not (parsed.get("said_ok") or parsed.get("said_failed")):
        return UNCLEAR, ["the runner printed neither OK nor FAILED, so its own verdict is unknown"]
    if parsed.get("expected failures"):
        why.append(f"{parsed['expected failures']} test(s) are expected to fail, so a failure here may be "
                   f"deliberate. Read which ones before concluding anything is broken")
    if parsed.get("unexpected successes"):
        why.append(f"{parsed['unexpected successes']} test(s) passed that were registered as expected "
                   f"failures, which means a recorded gap may have been closed, or the registration is stale")
    if parsed.get("env_denied"):
        why.append("the environment refused an operation (permission, read-only, or no-delete), so this "
                   "describes where it ran and not the code. Re-run somewhere writable before concluding")
    if parsed.get("missing_deps"):
        why.append("dependencies are absent here, so the result describes this machine rather than the code: "
                   + ", ".join(parsed["missing_deps"]))
    if parsed.get("skipped"):
        why.append(f"{parsed['skipped']} test(s) skipped, and a skip is not a verification")
    if why:
        return UNCLEAR, why
    if parsed.get("failures") or parsed.get("errors"):
        return RED, [f"{parsed['failures']} failure(s) and {parsed['errors']} error(s), none of them "
                     f"accounted for as expected"]
    if parsed.get("said_failed"):
        return RED, ["the runner said FAILED without naming counts this could read"]
    return GREEN, [f"{parsed['ran']} test(s) ran, nothing failed, nothing skipped"]


def run(command, cwd=None, timeout=900):
    """Run a suite and report it. Never raises on a failing suite: a failing suite is a result."""
    try:
        done = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout,
                              shell=isinstance(command, str))
    except subprocess.TimeoutExpired:
        return {"verdict": UNCLEAR, "why": [f"the suite did not finish within {timeout}s"],
                "command": command, "cwd": cwd, "parsed": {}}
    except OSError as e:
        return {"verdict": UNCLEAR, "why": [f"could not run it: {e}"], "command": command, "cwd": cwd,
                "parsed": {}}
    text = (done.stderr or "") + (done.stdout or "")
    parsed = parse(text)
    parsed["exit_code"] = done.returncode
    kind, why = verdict(parsed)
    if kind == GREEN and done.returncode != 0:
        kind, why = UNCLEAR, [f"every count is clean but the runner exited {done.returncode}, so it is "
                              f"applying a rule of its own. Find out what before trusting either signal"]
    return {"verdict": kind, "why": why, "command": command, "cwd": cwd, "parsed": parsed,
            "tail": "\n".join(text.strip().splitlines()[-12:])}


def report(result):
    p = result.get("parsed") or {}
    lines = [f"{result['verdict']}: " + "; ".join(result["why"]),
             f"  ran {p.get('ran', 0)}, failures {p.get('failures', 0)}, errors {p.get('errors', 0)}, "
             f"skipped {p.get('skipped', 0)}, expected failures {p.get('expected failures', 0)}, "
             f"unexpected successes {p.get('unexpected successes', 0)}, exit {p.get('exit_code')}"]
    if p.get("summary_line"):
        lines.append(f"  the runner's own line: {p['summary_line']}")
    if result["verdict"] == UNCLEAR:
        lines.append("  Nothing should be edited on the strength of this. Read the suite's own output, or the "
                     "project's record of which failures are expected, first.")
    return "\n".join(lines)
