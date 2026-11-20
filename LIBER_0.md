# LIBER 0

*A working record, in the tradition of the magical diary: what was tried in this repository, what actually
happened, and what was learned. It is only ever added to. Two checks hold it to that:*

- `python -m symbolics.record` reads the file's git history and fails on any commit that changed or deleted a
  line, unless the Maintainer has named that commit in `architecture/guards.json`.
- `python -m symbolics.breaches` fails on any entry recorded as FAILED or CORRECTED that does not name the test
  now guarding against it, or give a reason no test can.

*For dated field notes that read as prose, see [OBSERVATIONS.md](OBSERVATIONS.md). This file is the structured
record those notes are checked against.*

---

## The One Rule

Record what actually happened, not what should have happened. An entry that says "this failed, here is the exact
error, here is what I learned" is worth more than an entry that only records successes. Corrections of earlier
entries are added as new entries, never as edits that erase what was originally believed: the record of having
been wrong, and of how it was caught, is the useful part.

The one exception is removing what must not be kept, such as a key or a private path. Only the Maintainer makes
that removal, the removal is itself recorded as a new entry, and its commit is named in `architecture/guards.json`.

## Entry Format

New entries go at the top of the Entries section, newest first.

```
### [Date]: [Short title]

**Attempted:** what was being tried.
**Result:** what actually happened: VERIFIED / FAILED / OPEN / CORRECTED, as applies. Include the specific
evidence (test count, exact error, commit hash), not just a summary judgment.
**Guard:** the test that now catches this, as path/to/test_file.py::test_name (several separated by commas),
or "none: <the reason no test can>". Required when the Result says FAILED or CORRECTED.
**Notes:** anything worth a future entry checking back against this one.
```

---

## Entries

### 2026-11-20: a lower cap was reported but not enforced, and Article 6's check only tested a clamp

**Attempted:** Two further points from the same outside review.

**Result:** CORRECTED, both.

1. `agency.sovereign(gamma_max=0.5)` softened and added alternatives only at the global thresholds (0.70 and 0.40),
   then labelled a reply above 0.5 `BREACHED` and returned it anyway; the comment beside it said this "cannot
   happen", which was true only at the default cap. Now both thresholds come down to the requested cap, and a reply
   still above it is withheld: the person gets a refusal saying so, and the reply is kept in
   `sovereignty_metadata["withheld"]`, never returned as the answer. At the default cap nothing changes. Shown with
   measured values: the imperative probe (0.600) was never softened under a 0.5 cap before; a repeated word that
   stays at 0.561 after both steps is now withheld at 0.5 and sent at 0.6.
2. `symbolics/conformance.py` checked Article 6 with `agency.cap(measured) <= 0.85`, which any clamp satisfies. It
   now runs the probe through `sovereign()`, re-measures what would reach the person instead of trusting the
   metadata, and checks it at the default cap and at 0.5. An implementation without `sovereign()` is NOT_IMPLEMENTED.
   Writing the check exposed a hole in its first version: a bare string returned under the lower cap counted as
   "withheld". Only a refusal record counts now.

Mutation: `agency.py` 40 of 42 (2 equivalents in `entropy_gamma`, recorded with reasons, both older than this
change), `conformance.py` 21 of 21. Full suite 574 tests OK on Python 3.14 and 3.11; the suite conforms, and now
prints the effective limits (default 0.18, at 0.5 cap 0.3).

**Guard:** tests/test_agency.py::test_a_reply_still_over_the_cap_is_withheld_not_returned, tests/test_agency.py::test_a_lower_cap_softens_what_the_default_would_let_through, tests/conformance/test_conformance.py::test_directivity_checks_what_actually_reaches_the_person, tests/conformance/test_conformance.py::test_a_bare_string_or_an_unreadable_record_is_not_withheld

**Notes:** The review also asked for conformance to assert that the core and the reference agent agree on the cap.
That check lives in `tests/test_one_cap.py` instead: `symbolics/` is the core and imports nothing from the packages
built on it, and keeping it that way matters more than where the assertion sits. The test fails on the same
condition the review described.

### 2026-11-20: the 0.85 cap had two definitions; now it has one, and a test keeps it that way

**Attempted:** Close a drift path an outside review pointed at: rules written down in more than one place.

**Result:** CORRECTED. The licence's directive cap (Article 6, 0.85) was defined twice: `symbolics/agency.py`
(`GAMMA_MAX`) and `reference_agent/governance.py` (`GAMMA_CAP = 0.85`, a copy). Changing one would have left the
other behind, and nothing would have failed: the `layers` check compares files and quoted sentences, not constants.
`governance.py` now imports `GAMMA_MAX` (on the same line, so no mutation label moved; a docstring line added above
did move two, now updated). `tests/test_one_cap.py` parses every module in `symbolics`, `engines`,
`reference_agent`, `athanor` and `examples`, and fails if any of them other than `agency.py` binds a name or a
default argument to 0.85. Before trusting it, the test shows its scanner finds a planted copy in each form, and it
found the old line (line 40) when the copy was put back in memory. Full suite 565 tests OK on Python 3.14 and 3.11;
`governance.py` mutation 32 of 34, 2 exempt, 0 survivors.

**Guard:** tests/test_one_cap.py::test_only_agency_defines_it, tests/test_one_cap.py::test_the_modules_that_use_a_cap_hold_agencys_own

**Notes:** Two other duplications from the same review stay open: the ledger framework exists in `symbolics/` and in
`corpus/ledgers/` (nearly the same code), and `symbolic_api.json` exists in two versions that differ. The corpus copies
are its own history and were left alone on purpose; whether to make the core the single source for them is a
separate decision. `symbolics/conformance.py` still writes 0.85 in its comparison, on purpose: that is the licence's
number used as the check's own reference.

### 2026-11-20: a new test compared a float sum exactly, and Python 3.11 disagreed in the last bit

**Attempted:** The second CI run (44836872430), after the two fixes below.

**Result:** CORRECTED. `corpus` and `workspace` passed; `test` failed on Python 3.11 in a test added today,
`test_it_gives_up_after_the_last_try_and_raises_the_lock`: `AssertionError: 2.2500000000000004 != 2.25`. The test
compared the sum of nine float waits with one product. Since Python 3.12, `sum()` uses compensated summation and the
two agree exactly, which is why it passed on this machine (3.14). The code was right; the test was too exact in the
wrong place. It now compares the list of waits one by one, which is also stronger. Checked before pushing: the full
suite passes on CPython 3.11.15 and on 3.14, 561 tests each, 4 skipped.

**Guard:** tests/athanor_tests/test_review_regressions.py::test_it_gives_up_after_the_last_try_and_raises_the_lock

**Notes:** Run a new test on the oldest supported Python before pushing, not only on the newest.

### 2026-11-20: the first CI run, on a clean Linux runner, found two things this machine could not

**Attempted:** Publish the repository and run CI for the first time (run 44834253000).

**Result:** CORRECTED. The `corpus` job passed; `test` and `workspace` failed, each for a reason that only a clean
machine or Linux could show:

1. `tests/test_sanitization_audit.py` reported 11 unresolved imports: the corpus's optional scikit-learn and
   PyTorch. This machine had both installed, so they always resolved here. They are now listed as optional extras
   beside NumPy, as `pyproject.toml` already declares them.
2. `mcp-workspace/apis/workspace_test.go`: `TestWS_SymlinkOutOfTheRootIsRefused` failed because the server refused
   the symlink with "goes through a link (link.txt)", while the test expected "outside the project root". The
   behaviour is right and stricter (every path component is checked for links before anything is resolved, as
   the junction test already expects); the expectation predates that check. The test had only ever been skipped
   here, because this Windows machine cannot create symlinks without extra rights.

**Guard:** tests/test_sanitization_audit.py::test_all_python_files_parse_and_resolve_internal_imports, mcp-workspace/apis/workspace_test.go

**Notes:** A test that is always skipped where it is written is not evidence; CI is the first place it runs. The
athanor planted-bug check (two symlink cases) is the other example in this repository, and it runs in CI too.

### 2026-11-20: athanor retries a file Windows reports as held by another program

**Attempted:** Fix the `WinError 32` failures seen twice in the athanor tests inside the mutation gate.

**Result:** CORRECTED. Both tracebacks were the same failure: renaming or deleting a file athanor had just written,
while another program (most likely a virus scanner or the search indexer) briefly held it. The first also showed a
second fault: the clean-up after the failed rename hit the same lock, and its error replaced the first one.
`athanor/workshop.py` now sends every such rename and remove through one helper that retries only Windows sharing
and lock violations (codes 32 and 33), up to 10 tries with growing waits (at most 2.25 s), and raises everything
else at once. Nowhere else does an `OSError` carry `winerror`, so nothing is retried outside Windows. Five tests
simulate the locks and count the calls and waits; the mutation gate kills all 5 new mutants (`workshop.py` 72 of 73,
the 73rd the listed Windows-branch equivalent, its label moved from line 21 to 53). Full suite 560 tests OK, 4
skipped; 467 OK with NumPy blocked; every gate passes.

**Guard:** tests/athanor_tests/test_review_regressions.py::test_a_held_file_is_retried_until_it_is_free, tests/athanor_tests/test_review_regressions.py::test_no_other_error_is_retried, tests/athanor_tests/test_review_regressions.py::test_a_held_clean_up_does_not_hide_the_first_error

**Notes:** The lock itself was never reproduced on purpose (0 failures in 24 runs, before and after), so what is
verified is the handling of the error, not that it will not happen. The separate intermittent error in
`tests/test_outgoing.py`, also in a temporary folder and also never caught with a traceback, is not addressed by
this; it is a different code path (git, not athanor).

### 2026-11-20: the ported modules pass the mutation gate, and the gate itself was tested for the first time

**Attempted:** Close the OPEN entry below: kill or explain all 108 mutants that survived in the 8 ported Python
modules.

**Result:** VERIFIED for the mutation gate, with numbers:

- `symbolics/mutate.py` now lets a file name several test modules, so a mutant survives only if no test anywhere
  kills it. Re-run that way, 6 survivors in `reference_agent/mcp.py` and 2 in `athanor/workshop.py` turned out to be
  caught by their other test file. `mutate.py` had never been a target of itself; added, it showed 4 survivors of
  its own (the `--limit` boundary, `+` and `and` mutants that were never really applied, and an exit code CI relies
  on). Now 20 of 20.
- The rest were real gaps: no test checked a boundary (an F16 value of exactly 65504, an MXFP4 exponent of exactly
  2 or 254, a string ending exactly at the end of the file, a file of exactly 2,000,000 bytes), a message's
  content, a crafted bad record, or a summary's numbers. New test classes kill each one and say which line it
  guards: `TestTheGapsMutationFound` and `TestTheClientGapsMutationFound` in `tests/reference_agent_tests/`;
  `TestCodecBoundaries`, `TestEditsGaps`, `TestGgufGaps` and `TestWorkshopGaps` in
  `tests/athanor_tests/test_athanor.py`.
- 8 mutants are equivalent and are listed, each with its reason, in `architecture/mutation_guards.json`: two in
  `governance.py`, one in `mcp.py`, three in `codec.py`, one in `gguf.py`, one in `workshop.py`.
- Final run, every module against all of its test modules: `reference_agent/` 109 of 112 killed, `athanor/` 166 of
  171, `symbolics/mutate.py` 20 of 20; 0 unexempted survivors. Full suite 555 tests, OK, 4 skipped; every gate,
  `go vet`, `go test`, and athanor's planted-bug check (12 of 13 here, the 13th needs symlinks) pass.

**Notes:** Twice during this work the unmutated athanor tests failed inside the gate with `WinError 32` (a file in
use by another process, in a temporary folder), and did not fail in 18 runs outside it or in fresh copies. A failed
baseline only stops a run, which is safe. A flake during a mutant's run would count as a kill, which is not, so on
this machine a kill is slightly weaker evidence than it looks; CI runs on Linux. The same class of Windows lock is the
likeliest cause of the unexplained `errors=1` recorded earlier today, still not confirmed.

### 2026-11-20: three agent tools ported from a private agent, and the mutation gate not yet passed

**Attempted:** Bring the generic parts of a private agent into this repository under plain names, leaving
everything personal behind: `athanor/` (GGUF model workshop, replacing the single-file `engines/athanor.py`),
`reference_agent/` (approval gate, MCP client, suite reader, governance gate) and `mcp-workspace/` (the Go MCP
server with evidence-anchored memory). Every mention of the maintainer by name was rewritten, and modules tied to
the private notes, library or persona were not ported.

**Result:** OPEN. What passed: the full suite (497 tests, 4 skipped: 2 need symlinks, 2 need a `config.json`), 435
tests with NumPy blocked and nothing failing, `go vet` and `go test` for the server, the gate's live tests against the
built server binary, athanor's planted-bug check at 12 of 13 (the 13th needs symlinks, which this Windows machine
does not allow; it is the same 12 of 13 in the original copy), the leak scan with the private denylist, and every CI
gate. What did not pass: this repository's mutation gate, run with `python -B -m symbolics.mutate --module <file>`
on each of the 8 ported Python modules. 175 of 283 mutants killed, 108 survived, so none of these modules is
VERIFIED here. The gate runs one test module per file, so survivors in `athanor/gguf.py` and `athanor/workshop.py`
(also tested by `test_review_regressions.py` and `breakit.py`) and in `reference_agent/outbound.py` (also tested by
`test_agentbase_mcp.py`) may be killed by those; that was not checked. The surviving mutants, verbatim:

- `reference_agent/governance.py` 26/34: 135 (Gt->GtE), 190 (Or->And), 234 (Add->Sub), 134 (Mult->Add),
  102 (Or->And), 102 (Add->Sub), 134 (Add->Sub), 102 (Sub->Add)
- `reference_agent/suitecheck.py` 15/20: 91 (And->Or), 136 (And->Or), 144 (Or->And), 132 (Or->And), 91 (Or->And)
- `reference_agent/outbound.py` 24/29: 241 (And->Or), 238 (And->Or), 145 (Gt->GtE), 170 (Or->And), 267 (Or->And)
- `reference_agent/mcp.py` 14/29, 1 timeout: 197 (Or->And), 38 (Or->And), 168 (Add->Sub), 187 (And->Or),
  201 (Or->And), 201 (Or->And), 137 (Or->And), 148 (Gt->GtE), 184 (Or->And), 197 (Or->And), 203 (Or->And),
  177 (And->Or), 197 (Or->And), 150 (Or->And), 163 (Or->And)
- `athanor/gguf.py` 25/61, 1 timeout: 23 (Mult->Add), 23 (Mult->Add), 119 (Or->And), 121 (Or->And), 191 (And->Or),
  235 (Eq->NotEq), 237 (Eq->NotEq), 44 (Gt->GtE), 105 (Or->And), 119 (LtE->Lt), 121 (Lt->LtE), 121 (Gt->GtE),
  127 (Or->And), 131 (Or->And), 135 (Or->And), 148 (GtE->Gt), 152 (GtE->Gt), 164 (Or->And), 171 (Add->Sub),
  44 (Sub->Add), 105 (LtE->Lt), 131 (LtE->Lt), 137 (Add->Sub), 152 (GtE->Gt), 166 (Or->And), 188 (LtE->Lt),
  226 (Or->And), 55 (NotEq->Eq), 137 (Add->Sub), 188 (Add->Sub), 238 (Or->And), 251 (Eq->NotEq), 58 (Mult->Add),
  177 (Mult->Add), 58 (Sub->Add), 185 (Mult->Add)
- `athanor/codec.py` 16/23: 68 (GtE->Gt), 53 (Gt->GtE), 63 (Lt->LtE), 63 (Gt->GtE), 12 (Lt->LtE), 70 (Lt->LtE),
  70 (Gt->GtE)
- `athanor/edits.py` 12/19: 33 (Or->And), 33 (Gt->GtE), 37 (And->Or), 56 (Lt->LtE), 70 (And->Or), 25 (Sub->Add),
  60 (Sub->Add)
- `athanor/workshop.py` 43/68: 21 (Eq->NotEq), 61 (Or->And), 238 (And->Or), 254 (Or->And), 257 (Or->And),
  272 (Add->Sub), 343 (Or->And), 237 (Add->Sub), 257 (Lt->LtE), 257 (LtE->Lt), 257 (Gt->GtE), 265 (NotEq->Eq),
  224 (Add->Sub), 257 (Add->Sub), 273 (And->Or), 298 (Or->And), 298 (NotEq->Eq), 298 (NotEq->Eq), 408 (Eq->NotEq),
  409 (And->Or), 273 (Add->Sub), 282 (Eq->NotEq), 409 (Gt->GtE), 409 (Eq->NotEq), 230 (Add->Sub)

**Notes:** The Go server's guards have their own break-it record in `mcp-workspace/STANDARD.md`, from the original
copy (2026-11-11); it was not re-run here. Next: run each module's survivors against all of its test modules, then
for each one still alive either add a test that kills it or show it is equivalent and list it in
`architecture/mutation_guards.json`.

### 2026-11-20: the intermittent test error named, its cause still unknown; and CI would have failed without NumPy

**Attempted:** Check every statement in README.md against the code, and run the core suite the way a clean CI
runner would, without NumPy.

**Result:** OPEN for the first part. With NumPy blocked, one run reported `FAILED (errors=1, skipped=2)`, and this
time the error was named: `tests/test_outgoing.py::test_upstream_branch_limits_outgoing_range_to_unpushed_commits`,
a test that pushes to a temporary local git repository. It passed 6 of 6 times on its own and the full suite passed
8 of 8 times afterwards, so no traceback was captured. A Windows temporary-folder cleanup race is a plausible cause,
not a verified one; it is the most likely source of the earlier unexplained `errors=1` too.

The second part is fixed. Without NumPy, `tests/test_recursive_attractor_engine.py` and
`tests/test_engine_composition_loop.py` could not even be imported, and CI's `test` job never installed NumPy, so the
first push would have failed CI. Both modules now report themselves as skipped when NumPy is missing, and CI
installs NumPy so they run. README.md also called the attractor engine's NumPy "optional"; it is required.

**Notes:** If the outgoing test errors again, keep the traceback before rerunning.

### 2026-11-20: a test that passed only when its output was piped

**Attempted:** Run the full suite (`python -m unittest discover -s tests`) directly in a terminal.

**Result:** CORRECTED. 1 of 374 failed: `test_colorize_returns_plain_text_when_not_a_tty` asserted
`self.assertFalse(sys.stdout.isatty())`, which is only true when output is piped or captured. Every earlier run that
reported 374 OK had piped its output, so none of them could see this. The engine was right; the test's assumption
was wrong. The test now supplies a non-terminal stdout and a terminal stdout itself, and checks both branches.
After the fix: 374 OK in a real terminal and 374 OK piped.

**Guard:** tests/test_standalone_rca_sandbox.py::test_colorize_returns_plain_text_when_not_a_tty

**Notes:** One earlier piped run that same day reported `FAILED (errors=1)` and could not be reproduced in six
reruns. That was an error, not this failure, and a piped run cannot trip this test, so its cause is still unknown.

### 2026-11-20: eight recorded ethics-gate bypasses closed, and a test folder that had never run

**Attempted:** Rerun every bypass of `ethics.check_request()` and `ethics.emit()` recorded in OBSERVATIONS.md
against the current gate, and close the ones that still got through.

**Result:** CORRECTED. All eight still got through before the fix: requests aimed at another person behind a
self-description, rankings phrased as placements ("top 5%"), and commands placed in a second sentence or phrased as
obligations ("you should"). The gate now checks one sentence at a time and recognises those forms. Each recorded
sentence is pinned in `tests/test_address_and_ethics.py` (class `TestRecordedBypasses`), along with a known false
positive that is still refused. Separately, `tests/conformance/` had no `__init__.py`, so its tests were never
collected by `unittest discover`; adding it raised the suite from 325 to 342 tests.

**Guard:** tests/test_address_and_ethics.py::test_requests_about_another_person_are_refused, tests/test_address_and_ethics.py::test_ranking_a_person_is_refused, tests/test_address_and_ethics.py::test_commands_are_refused_even_beside_an_offer, tests/conformance/__init__.py

**Notes:** The gate still matches words and patterns, not meaning; README.md lists this under Known Limitations.
A new paraphrase can get through, and when one is found it belongs in a new entry here with its own test.

### 2026-11-20: the record opened in the public repository

**Attempted:** Bring the practice of an append-only record into the public repository, with the two checks that
hold it: `symbolics/record.py` (only additions in git history) and `symbolics/breaches.py` (every breach names its
guard).

**Result:** VERIFIED for the mechanism: both checks run against this file and its guard list, and both have tests
on toy records and toy git repositories where the right answer is known by construction. The record itself starts
here. Earlier history from before the public release is not carried over; the public field notes from that time are
in OBSERVATIONS.md.

**Notes:** `architecture/guards.json` starts empty: no old entries needing a guard beside them, and no accepted
in-place edits.
