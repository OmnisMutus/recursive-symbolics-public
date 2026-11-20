# .github/workflows/

`ci.yml` runs on every push and pull request to `main`. It has three jobs.

**`test`**, on Python 3.10, 3.11, 3.12 and 3.13, with full git history (the record and leak checks read it):

0. installs NumPy, so the two engine test modules that need it run instead of being skipped
1. `python examples/quickstart.py`
2. `python -m symbolics.conformance`
3. `python -m symbolics.layers`
4. `python -m symbolics.record` and `python -m symbolics.breaches`
5. `python -m symbolics.outgoing`
6. `python -m unittest discover -s tests -v`
7. `python tests/athanor_tests/breakit.py`: athanor's planted-bug check. All 13 bugs must be caught; two of them
   need symlinks, which the Linux runner allows

**`workspace`**: sets up Go from `mcp-workspace/go.mod`, then in `mcp-workspace/` runs `go vet ./...`,
`go test -count=1 ./...` and `go build`, and finally runs `tests/reference_agent_tests/test_agentbase_mcp.py`
against the binary it just built, so the approval gate is checked against the real server.

**`corpus`**, on Python 3.12: installs NumPy and scikit-learn, then runs the corpus's three runners from
`corpus/` (`test_all_engines.py`, `run_all_correspondence_ledgers.py`, `run_corpus.py`).

Every step must exit without an error for the run to pass. To check before you push, run the same commands
locally from the repository root.
