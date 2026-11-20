# AgentBase guard break-it record

What this file is: for each guard in `apis/`, the smallest change that disables it, the tests that
failed when that change was made, and the status that result supports. The terms follow
[`../STANDARD.md`](../STANDARD.md): a guard is VERIFIED only when a named test was seen to fail with the
guard disabled and to pass again once it was restored, and that test checks against something the
code under test did not produce.

How it was run: `breakit.py` (kept outside the repo, in the session scratchpad) applies one mutation,
runs `go test -count=1 ./apis/`, records every `--- FAIL` line, writes the original bytes back, and
at the end compares SHA-256 hashes of every `.go`, `.md`, `.mod` and `.sum` file with the hashes
taken before the run, then runs the suite once more. Date of the run: 2026-11-11, Go 1.27.4, windows/amd64.

## Results

| ID | Guard | Mutation | Test(s) that failed | Status |
|---|---|---|---|---|
| N1 | Replay: lookup of a used nonce | lookup condition forced false | TestTransact_SignedReplayRejectedLedgerUnchanged, TestMCP_TransactNonceArgument (both check the error says "replay"; the unique index still blocks the write) | VERIFIED |
| N2 | Replay: unique index on (agent_id, nonce) | index created non-unique | TestAgentNonces_UniqueIndexRejectsDuplicate | VERIFIED |
| N3 | Replay: lookup and index together | both of the above | TestTransact_SignedReplayRejectedLedgerUnchanged, TestTransact_ConcurrentReplayExactlyOnePosts, TestTransact_NonceIndependentPerAgent, TestMCP_TransactNonceArgument, TestAgentNonces_UniqueIndexRejectsDuplicate | VERIFIED |
| N4 | Nonce recorded inside the ledger transaction | `recordNonceTx` call removed | TestTransact_SignedReplayRejectedLedgerUnchanged, TestTransact_ConcurrentReplayExactlyOnePosts, TestTransact_NonceIndependentPerAgent, TestTransact_SignedFailsClosedWithoutNonceTable, TestMCP_TransactNonceArgument | VERIFIED |
| N5 | A signature needs agent_id, signature and nonce together | `nonce == ""` dropped from the check | TestTransact_SignedNeedsAllThreeAndValidNonce | VERIFIED (first run: nothing failed, see Findings) |
| N6 | Nonce alphabet and length | regex check replaced by `nonce == ""` | TestTransact_SignedNeedsAllThreeAndValidNonce | VERIFIED (first run: nothing failed, see Findings) |
| N7 | Signed payload includes the nonce | nonce left out of the payload | TestSigningPayload_GroundTruthBytes, TestTransact_SignatureBoundToNonceAndAgent | VERIFIED |
| N8 | Signed payload has exactly one parse | netstring replaced by `value|` | TestSigningPayload_GroundTruthBytes | VERIFIED |
| G1 | ed25519 verification result is honoured | `!Verify(...) && false` | TestIdentity_Ed25519SigningAndSignedTransact, TestTransact_SignatureBoundToNonceAndAgent | VERIFIED |
| P1 | Policy load error aborts | `return nil` on load error | TestEnforcePolicies_AbortsOnLoadError | VERIFIED |
| P2 | Unparseable stored policy aborts | parse error ignored | TestTransact_AbortsOnUnparseableStoredPolicy | VERIFIED (only after the test was made to check the reason, see Findings) |
| P3a | Cannot evaluate: unknown field is a violation | `holds` default returns true | TestConditionHolds_CannotEvaluateIsFalse | VERIFIED |
| P3b | Cannot evaluate: non-numeric value is a violation | `numCompare` parse error returns true | TestConditionHolds_CannotEvaluateIsFalse | VERIFIED |
| P3c | Cannot evaluate: unknown numeric operator is a violation | `numCompare` default returns true | TestConditionHolds_CannotEvaluateIsFalse | VERIFIED |
| P3d | Cannot evaluate: ordering operator on an account field is a violation | `strCompare` default returns true | TestConditionHolds_CannotEvaluateIsFalse | VERIFIED |
| P4 | `from_balance_after` balance error aborts | balance error ignored (balance reads as 0) | TestEnforcePolicies_AbortsOnBalanceError | VERIFIED (new test, see Findings) |
| H1 | Empty `AGENTBASE_HOOK_HOSTS` allows nothing | empty allowlist returns nil | TestValidateHookRegistration_Allowlist, TestValidateHookDispatch_BlocksIPv6Forms | VERIFIED |
| H2 | Allowlist checked again at dial time | dial-time check forced false | TestSafeWebhookClient_DialEnforcesAllowlist | VERIFIED (new test) |
| H3 | Blocked IP predicate, all ranges | `isBlockedIP` returns false | TestValidateHookDispatch_BlocksPrivate, TestValidateHookDispatch_BlocksIPv6Forms, TestSafeWebhookClient_DialRefusesBlockedAnswer, TestDispatchHooks_LogsSkippedHook | VERIFIED |
| H3a | Blocked IP: loopback | `IsLoopback` removed | TestValidateHookDispatch_BlocksPrivate, TestValidateHookDispatch_BlocksIPv6Forms, TestSafeWebhookClient_DialRefusesBlockedAnswer | VERIFIED |
| H3b | Blocked IP: private | `IsPrivate` removed | TestValidateHookDispatch_BlocksPrivate, TestValidateHookDispatch_BlocksIPv6Forms, TestDispatchHooks_LogsSkippedHook | VERIFIED |
| H3c | Blocked IP: link-local unicast | `IsLinkLocalUnicast` removed | TestValidateHookDispatch_BlocksPrivate, TestValidateHookDispatch_BlocksIPv6Forms, TestSafeWebhookClient_DialRefusesBlockedAnswer | VERIFIED |
| H3d | Blocked IP: link-local multicast | `IsLinkLocalMulticast` removed | TestValidateHookDispatch_BlocksIPv6Forms | VERIFIED (new test case, see Findings) |
| H3e | Blocked IP: unspecified | `IsUnspecified` removed | TestValidateHookDispatch_BlocksPrivate, TestValidateHookDispatch_BlocksIPv6Forms | VERIFIED |
| H4 | Blocked IP at dispatch validation | dispatch-time block forced false | TestValidateHookDispatch_BlocksPrivate, TestValidateHookDispatch_BlocksIPv6Forms, TestDispatchHooks_LogsSkippedHook | VERIFIED |
| H5 | Blocked IP at dial time (DNS rebinding) | dial-time block forced false | TestSafeWebhookClient_DialRefusesBlockedAnswer | VERIFIED (new test) |
| H6 | Dial uses the validated IP, not the name | dial `addr` instead of `ips[0]:port` | TestSafeWebhookClient_DialUsesValidatedIP | VERIFIED (new test and seam, see Findings) |
| H7 | Redirects refused | `CheckRedirect` returns nil | TestHooks_LiveDispatchCurrencyAndRedirectBlocked | VERIFIED |
| H8 | Skipped hook is logged with id and reason | warning removed | TestDispatchHooks_LogsSkippedHook | VERIFIED (new) |
| H9 | Hook URL not written to the log | URL redaction removed | TestDispatchHooks_LogsSkippedHook | VERIFIED (new) |
| A1 | Bearer: handler refuses an empty or whitespace key (403) | handler check forced false | TestRemoteAuthGuard_And_SSEPath | VERIFIED |
| A2 | Bearer: `checkBearer` refuses an empty or whitespace key by itself | key check forced false | TestCheckBearer_WhitespaceKeyDisables | VERIFIED (new test, see Findings) |
| A3 | Bearer: wrong key refused | comparison `>= 0` (always true) | TestCheckBearer, TestCheckBearer_WhitespaceKeyDisables, TestRemoteAuthGuard_And_SSEPath | VERIFIED |
| A4 | Bearer: empty token refused | empty-token check forced false | none | REDUNDANT: no behaviour change (see Findings) |
| A5 | Bearer: `Bearer ` prefix required | prefix check replaced by `TrimPrefix` | TestCheckBearer | VERIFIED |
| M1 | Amount: fractional rejected | `Trunc` check forced false | TestValidateAmount, TestValidateAmount_Reasons, TestTransact_RejectsFractionalAmount | VERIFIED |
| M2 | Amount: NaN and Inf rejected | finite check forced false | TestValidateAmount_Reasons | VERIFIED (new test, see Findings) |
| M3 | Amount: above 2^53 rejected | range check forced false | TestValidateAmount, TestValidateAmount_Reasons | VERIFIED |
| M4 | Amount: zero and negative rejected | sign check forced false | TestValidateAmount, TestValidateAmount_Reasons | VERIFIED |
| S1 | Self-transfer rejected | `from == to` check forced false | TestTransact_RejectsSelfTransferAndWhitespace | VERIFIED |

The redirect block (H7) is the one break-it the earlier agent recorded. Every other row was run here.

## Findings from the pass

Each of these is a case where disabling a guard left the suite green at first.

- **P2.** Disabling the parse check still aborted, because the zero-value condition reads as a
  violation, and the old test only checked that the transfer failed and named the rule. It now also
  checks that the error cites the unparseable condition.
- **P4.** No test reached the balance error path. Added `TestEnforcePolicies_AbortsOnBalanceError`.
  It drops the ledger table and uses a loose floor, so a balance silently read as 0 would pass.
- **H2, H5, H6.** The dial-time checks had no tests. Every hook test called `validateHookDispatch`
  first, and that function refuses the same inputs. Two package variables, `hookLookupIP` and
  `hookDial`, now let a test give a fake DNS answer and see the exact address that gets dialed.
  Production never reassigns them.
- **H3d.** Link-local multicast had no test case. Added IPv6 cases (`::1`, `fe80::1`, `fc00::1`,
  `ff02::1`, `::`) and the IPv4-mapped forms `::ffff:127.0.0.1` and `::ffff:10.0.0.1`.
- **A2.** `checkBearer`'s own empty-key check was only ever exercised with `""`, where a hash
  mismatch refuses anyway. With the key `"   "`, the header `Bearer    ` carries the token `"   "`,
  which matches. The handler refuses first today, so this is defence in depth. It now has a test.
- **A4. Not fixed, recorded.** An empty token can never match a non-empty key, and an empty key is
  refused earlier. So removing the empty-token check changes no outcome, and no test can observe it.
  It is redundant, and no test protects it.
- **M2.** NaN and Inf were already refused by the later checks: NaN fails the whole-number test, and
  +Inf fails the range test. So removing the finite check changed only the error message.
  `TestValidateAmount_Reasons` now pins the reason for each rejection.
- **N5, N6.** The first version of the test signed one fixed nonce and then sent other nonces. The
  signature check refused those before the nonce checks could matter. Each bad nonce is now validly
  signed over itself, and each refusal is checked by its message.

## Not covered

- Ranges that `isBlockedIP` does not block at all. Examples: 100.64.0.0/10 (shared address space),
  192.0.0.0/24, 198.18.0.0/15, multicast outside link-local, and IPv6 NAT64 `64:ff9b::/96`. These are
  gaps in the guard, not in the tests, and this pass did not change them.
- The dial-time check refuses a name if any answer is blocked, then dials only `ips[0]`. That is
  safe but has no fallback to a second public address. This is noted, not changed.
- The signature check is now inside the ledger transaction. If an agent's record is deleted mid-request,
  the transfer fails closed; there is no test for that ordering.
- Nonces are kept forever, so `agent_nonces` grows by one row per signed transfer, with no expiry
  or pruning.
- Whether `amount` is lost through JSON before `validateAmount` sees it. JSON cannot carry NaN or
  Inf, and a number above 2^53 is rounded by the JSON decoder first. Only the Go-level function is
  tested.
- The remote SSE transport is tested only at the handler level, with `httptest`. No test runs a
  real `serve` process with a key.

## The workspace (added 2026-11-12)

Same method, run by `ws_breakit.py` (also in the session scratchpad) over `apis/workspace.go`,
`apis/workspace_mcp.go`, `apis/link_windows.go` and `apis/mcp.go`, running `go test -count=1 -run "TestWS_|TestMCP_JSONRPC" ./apis/`
for each mutation. Ground truth: blob hashes from `git hash-object --no-filters` and the published
empty-blob hash, commits from `git rev-parse HEAD`, line numbers from files built in the test and
counted by hand, and the tools a server offers from its own `tools/list`. Date of the run:
2026-11-12, Go 1.27.4, windows/amd64. After the run every file matched its SHA-256 from before, and
the suite passed.

| ID | Guard | Mutation | Test(s) that failed | Status |
|---|---|---|---|---|
| W1 | Blob hash is git's | header written without its NUL | `TestWS_BlobHashMatchesGit`, `TestWS_RecordStoresTheFilesBlobHash` | VERIFIED |
| W2 | The quote must be in the named lines | check skipped | `TestWS_TheQuoteMustBeInTheNamedLines` | VERIFIED |
| W3 | Line 0 refused | lower bound removed | `TestWS_TheQuoteMustBeInTheNamedLines` | VERIFIED |
| W4 | Lines past the end refused | bound loosened by 5 | `TestWS_TheQuoteMustBeInTheNamedLines` | VERIFIED |
| W5 | CRLF files match like LF | `\r` kept at line ends | `TestWS_CRLFFileMatchesLikeLF` | VERIFIED |
| W6 | A CRLF quote is normalized | normalization removed | `TestWS_CRLFFileMatchesLikeLF` | VERIFIED |
| W7 | FRESH only when the blob is unchanged | always FRESH | `TestWS_RecallReportsEachAnchorState` | VERIFIED |
| W8 | Relocated lines are exact | line counter starts at 0 | `TestWS_RecallReportsEachAnchorState` | VERIFIED |
| W9 | A junction is a link | reparse tag not read (`return false`) | `TestWS_JunctionOutOfTheRootIsRefused` | VERIFIED |
| W10 | `..` refused before the walk | removed, Rel check left | none | REDUNDANT alone, see W12 |
| W11 | Resolved path stays under the root | removed, `..` check left | none | REDUNDANT alone, see W12 |
| W12 | W10 and W11 together | both removed | `TestWS_PathsStayInsideTheRoot` | VERIFIED |
| W13 | A directory is not a file | check skipped | `TestWS_PathsStayInsideTheRoot` | VERIFIED |
| W14 | File size limit | off by one | `TestWS_OversizeFileIsRefused` | VERIFIED |
| W15 | No result on a dirty tree | check skipped | `TestWS_ResultsNeedACleanTreeAndBelongToOneCommit` | VERIFIED |
| W16 | Untracked files make the tree dirty | `--untracked-files=no` | same | VERIFIED |
| W17 | The brief shows only this commit's results | commit filter removed | same | VERIFIED |
| W18 | The brief shows no results on a dirty tree | clean check removed | same | VERIFIED |
| W19 | A resolution is never written over | check skipped | `TestWS_UnknownsResolveOnceAndFindingsNever` | VERIFIED |
| W20 | Only an unknown is resolved | check skipped | same | VERIFIED |
| W21 | The brief shows the latest note | sort reversed | `TestWS_BriefShowsTheLatestNote` | VERIFIED |
| W22 | A project's root never changes | root overwritten | `TestWS_RegistrationRules` | VERIFIED |
| W23 | No workspace tools on the remote server | `EnableWorkspace` in the constructor | `TestWS_OnlyALocalServerHasTheWorkspaceTools` | VERIFIED |
| W24 | A fractional line is refused, not truncated | fraction check removed | `TestWS_MCPRefusesAFractionalLine` | VERIFIED |
| W25 | Kind is finding or unknown | any non-empty kind | `TestWS_UnknownsResolveOnceAndFindingsNever` | VERIFIED |
| W26 | The root is absolute | absolute check removed | `TestWS_RegistrationRules` | VERIFIED |
| W27 | Relocation takes the nearest occurrence | first occurrence taken | `TestWS_AShortQuoteMovesWithItsLineAndSaysWhenItCannotTell` | VERIFIED |
| W28 | The stored evidence lines are searched first | skipped | same | VERIFIED |
| W29 | Several occurrences are reported | count hidden | same | VERIFIED |
| W30 | Only a name-surrogate tag is a link (a cloud placeholder is a file) | any tag counts | `TestWS_OnlyNameSurrogateTagsAreLinks` | VERIFIED |
| W31 | Relocation is linear in the file | newlines recounted from the start per occurrence | `TestWS_ManyOccurrencesRecallInLinearTime` (20 s limit) | VERIFIED |
| W32 | An edit elsewhere is INTACT, not MOVED | INTACT check skipped | `TestWS_AnEditElsewhereLeavesTheEvidenceIntact` | VERIFIED |
| W33 | Each file is read once per recall | cache bypassed | `TestWS_RecallReadsEachFileOnce` | VERIFIED |
| W34 | `tested_at` must still be HEAD | check skipped | `TestWS_ResultsNeedACleanTreeAndBelongToOneCommit` | VERIFIED |
| W35 | A result needs the same ignored files present | ignored filter removed from the brief | `TestWS_AResultNeedsTheSameIgnoredFiles` | VERIFIED |
| W36 | A root below a junction registers | root resolved with `EvalSymlinks` again | `TestWS_ARootReachedThroughAJunctionWorks` | VERIFIED |
| W37 | `--workspace-only` removes the non-workspace tools | `DeleteTools` call removed | `TestWS_WorkspaceOnlyOffersTheWorkspaceToolsAndNothingElse` | VERIFIED |
| W38 | `--workspace-only` keeps the workspace tools | keep set ignored, every tool removed | `TestWS_WorkspaceOnlyOffersTheWorkspaceToolsAndNothingElse` | VERIFIED |

### Summaries, the compact brief and the usage log (2026-11-12)

Ground truth: file contents and changes made by the tests, so the state each summary should have is known;
commit counts from commits the test makes, checked with `git rev-list`; the bytes a call returned counted on
the client side, from the JSON-RPC answer. Each bug was planted, the named test was seen to fail, and every file
was restored byte for byte (sha256) with the suite passing again.

| ID | Guard | Planted bug | Test that fails | Status |
|---|---|---|---|---|
| W39 | A summary goes STALE when its file changes | blob not compared | `TestWS_ASummaryIsFreshUntilItsFileChanges` | VERIFIED |
| W40 | A summary must be shorter than its file | length check removed | `TestWS_SummaryRules` | VERIFIED |
| W41 | One summary per file, the newest | always a new row | `TestWS_SummaryRules` | VERIFIED |
| W42 | Lines are counted as an editor counts them | a final newline counted as a line | `TestWS_ASummaryIsFreshUntilItsFileChanges` | VERIFIED |
| W43 | The brief shows a claim's head, not the claim | whole claim in the brief | `TestWS_TheBriefShowsHeadsAndWhatChanged` | VERIFIED |
| W44 | A BROKEN finding is listed as needing attention | BROKEN left out | `TestWS_TheBriefShowsHeadsAndWhatChanged` | VERIFIED |
| W45 | A head is never cut inside a character | rune-boundary step skipped | `TestWS_HeadCutsOnARuneBoundary` | VERIFIED |
| W46 | Commits are counted from the last note | counted from HEAD | `TestWS_TheBriefCountsCommitsSinceTheLastNote` | VERIFIED |
| W47 | A note is at most 4000 bytes | the old 20000 limit | `TestWS_ANoteIsAtMost4000Bytes` | VERIFIED |
| W48 | The usage log holds sizes, never content | the arguments written | `TestWS_EveryWorkspaceCallIsMeasuredAndNothingElseIsWritten` | VERIFIED |
| W49 | The bytes returned are counted | text content not counted | `TestWS_EveryWorkspaceCallIsMeasuredAndNothingElseIsWritten` | VERIFIED |

Findings from this pass:

- **The first line count was one too many.** A file of 9 lines ending in a newline was reported as 10,
  because splitting on newlines leaves an empty piece after the last one. The test's 9 came from the file
  as written; the code now counts as an editor does. W42 guards it.
- **W45 first went uncaught, because the test was weak.** 200 two-byte letters put byte 160 exactly on a
  character boundary, so the unguarded cut was harmless there. The test now shifts the text by one byte
  and first checks that the cut does fall inside a character.

Findings from this pass:

- **A junction got through by accident.** Since Go 1.23, `filepath.EvalSymlinks` does not resolve a
  Windows junction, while `os.Open` goes straight through one, and a junction needs no privilege to
  create. The first version refused a junction only because `EvalSymlinks` happened to error on it.
  Every path component is now checked with `Lstat`, and a junction (`ModeIrregular`) or symlink is
  refused by name. W9 shows the test catches it.
- **A short quote was relocated to the wrong place.** Found in the live run over stdio, not by a test:
  a quote that occurs several times was relocated to its first occurrence. Relocation now searches
  the whole stored evidence lines first, then the quote nearest the old line, and reports
  `quote_occurs` when there is more than one place. When identical lines repeat, the position is a
  guess and the count says so; no test can make it more than that.

- **A code review of the first workspace commit (2026-11-12) found ten problems,** fixed in rows W30 to
  W36 and in the README: a quadratic relocation that could hang a recall; every finding marked MOVED by
  any edit to its file (now INTACT when its lines are untouched); a result recorded against a commit
  that was not the one tested (now `tested_at` must still be HEAD); results shown without the
  gitignored data they may have depended on (now keyed by the names of ignored files and folders);
  OneDrive placeholders refused as links (now the reparse tag is read); a root below a junction that
  could not be registered; a file read once per finding; an unused constant; and a tool count the
  README left unstated. Concurrent records were the eleventh worry: PocketBase serializes writes, and
  `TestWS_ConcurrentRecordsGetDistinctIDs` shows 16 at once get ids 1 to 16 with no error. W36 first
  went uncaught: the test made the root itself the junction, and `EvalSymlinks` only fails on a path
  through one. The test now puts the junction above the root, as in the finding.

Not covered here:

- `TestWS_SymlinkOutOfTheRootIsRefused` is skipped in this session: creating a symlink needs a
  privilege it does not have. The junction test covers the same check (`Lstat` on every component)
  for junctions only.
- A result is the caller's report. Nothing checks that the command was run, that the summary is what
  it printed, or that the tree was clean while it ran (only that it is clean, at `tested_at`, when the
  result is recorded). Ignored files are compared by name, not content.
- No test reads a real OneDrive placeholder: the tag rule is tested against Microsoft's published tag
  values, and the junction test shows the tag is read on a real reparse point.
- The workspace collections are created once. A database whose `ws_findings` or `ws_results` was
  created before the `context` or `ignored` field existed would not gain it; none exists outside tests
  yet.
- The `--workspace-only` branch in `main.go` has no Go test, since `main` is not under test. It was
  checked by hand on a built binary: `tools/list` returned 19 tools (13,140 bytes of definitions)
  without the flag and 8 (6,313 bytes) with it (RAN_ONLY). How many tokens that saves a client depends on
  how the client encodes tool definitions; only the byte sizes were measured. `--ws-usage` was also
  checked by hand on the built binary (RAN_ONLY): two sessions got two ids and the totals of their calls.
- Each file is read once per recall, but every recall reads every file a finding or summary names.
  Nothing is kept between recalls.
- Whether summaries save tokens is not measured. A summary saves reading only if it is good and is read
  instead of the file; the usage log measures what workspace calls cost, and only a comparison with the
  client's own token count for whole sessions can show a saving.
- A summary's quality is not checked by anything. FRESH means the file is the one summarized.
- A log that cannot be written never fails a call, so a missing log is silent: check the file exists
  before reading totals from it.
