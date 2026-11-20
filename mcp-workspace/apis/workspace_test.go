package apis

// Ground truth for the workspace, none of it from workspace.go:
//   - blob hashes come from `git hash-object --no-filters`, and commits from `git rev-parse HEAD`;
//   - line numbers and quotes come from files written here, whose contents are known by construction;
//   - which tools a server offers comes from its own tools/list over JSON-RPC.

import (
	"context"
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"testing"
	"time"
)

type wsFixture struct {
	s    *AgentBaseMCPServer
	root string
}

func gitT(t *testing.T, dir string, args ...string) string {
	t.Helper()
	out, err := exec.Command("git", append([]string{"-C", dir}, args...)...).CombinedOutput()
	if err != nil {
		t.Fatalf("git %v: %v\n%s", args, err, out)
	}
	return strings.TrimSpace(string(out))
}

func writeT(t *testing.T, root, rel, body string) {
	t.Helper()
	p := filepath.Join(root, filepath.FromSlash(rel))
	if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(p, []byte(body), 0o644); err != nil {
		t.Fatal(err)
	}
}

const wsFile = "package demo\n\n// Refund caps every refund at the original charge.\nfunc Refund(charge, asked int) int {\n\tif asked > charge {\n\t\treturn charge\n\t}\n\treturn asked\n}\n"

// newWS builds a git repository with one commit holding src/demo.go, and registers it as "demo".
func newWS(t *testing.T) wsFixture {
	t.Helper()
	s := newTestServer(t)
	root := t.TempDir()
	gitT(t, root, "init", "-q")
	gitT(t, root, "config", "user.email", "t@example.invalid")
	gitT(t, root, "config", "user.name", "t")
	gitT(t, root, "config", "commit.gpgsign", "false")
	gitT(t, root, "config", "core.autocrlf", "false")
	writeT(t, root, "src/demo.go", wsFile)
	gitT(t, root, "add", "-A")
	gitT(t, root, "commit", "-q", "-m", "start")
	if _, err := s.doRegisterProject("demo", root); err != nil {
		t.Fatalf("register: %v", err)
	}
	return wsFixture{s, root}
}

func (f wsFixture) record(t *testing.T, kind string, a, b int, quote string) string {
	t.Helper()
	out, err := f.s.doRecord("demo", kind, "refunds never exceed the charge", "src/demo.go", a, b, quote, "test")
	if err != nil {
		t.Fatalf("record: %v", err)
	}
	return out
}

func (f wsFixture) recall(t *testing.T) []recalled {
	t.Helper()
	raw, err := f.s.doRecall("demo", "")
	if err != nil {
		t.Fatalf("recall: %v", err)
	}
	var out recallOut
	if err := json.Unmarshal([]byte(raw), &out); err != nil || out.Findings == nil || out.Summaries == nil {
		t.Fatalf("recall json: %v (%s)", err, raw)
	}
	return out.Findings
}

func (f wsFixture) summaries(t *testing.T, prefix string) []summarized {
	t.Helper()
	raw, err := f.s.doRecall("demo", prefix)
	if err != nil {
		t.Fatalf("recall: %v", err)
	}
	var out recallOut
	if err := json.Unmarshal([]byte(raw), &out); err != nil {
		t.Fatalf("recall json: %v (%s)", err, raw)
	}
	return out.Summaries
}

func (f wsFixture) brief(t *testing.T) brief {
	t.Helper()
	raw, err := f.s.doBrief("demo")
	if err != nil {
		t.Fatalf("brief: %v", err)
	}
	var b brief
	if err := json.Unmarshal([]byte(raw), &b); err != nil {
		t.Fatalf("brief json: %v (%s)", err, raw)
	}
	return b
}

func TestWS_BlobHashMatchesGit(t *testing.T) {
	dir := t.TempDir()
	cases := map[string]string{"empty": "", "lf": wsFile, "crlf": strings.ReplaceAll(wsFile, "\n", "\r\n"), "utf8": "Malkuth מלכות\n"}
	for name, body := range cases {
		p := filepath.Join(dir, name)
		if err := os.WriteFile(p, []byte(body), 0o644); err != nil {
			t.Fatal(err)
		}
		want := gitT(t, dir, "hash-object", "--no-filters", p)
		if got := gitBlobHash([]byte(body)); got != want {
			t.Fatalf("%s: got %s, git says %s", name, got, want)
		}
	}
	// The published hash of the empty blob, independent of this machine's git.
	if got := gitBlobHash(nil); got != "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391" {
		t.Fatalf("empty blob: %s", got)
	}
}

func TestWS_RecordStoresTheFilesBlobHash(t *testing.T) {
	f := newWS(t)
	out := f.record(t, "finding", 5, 6, "if asked > charge {\n\t\treturn charge")
	want := gitT(t, f.root, "hash-object", "--no-filters", filepath.Join(f.root, "src", "demo.go"))
	if !strings.Contains(out, want[:12]) {
		t.Fatalf("record reported %q, git blob is %s", out, want)
	}
	rec, err := f.s.app.FindFirstRecordByFilter("ws_findings", "seq = 1")
	if err != nil || rec.GetString("blob") != want {
		t.Fatalf("stored blob %q, want %s (%v)", rec.GetString("blob"), want, err)
	}
}

func TestWS_TheQuoteMustBeInTheNamedLines(t *testing.T) {
	f := newWS(t)
	cases := []struct {
		name    string
		a, b    int
		quote   string
		wantErr string
	}{
		{"exact line", 3, 3, "Refund caps every refund", ""},
		{"spans two lines", 5, 6, "charge {\n\t\treturn", ""},
		{"last line of the file", 10, 10, "", "quote must not be empty"},
		{"in the file but not in those lines", 1, 2, "Refund caps", "it is at lines 3-3"},
		{"not in the file at all", 1, 9, "Refund doubles", "not in src/demo.go at all"},
		{"line 0", 0, 3, "Refund", "line_start must be at least 1"},
		{"end before start", 4, 3, "Refund", "line_end at least line_start"},
		{"past the end of the file", 9, 11, "}", "has 10 lines"},
		{"whitespace-only quote", 3, 3, "   ", "quote must not be empty"},
	}
	for _, c := range cases {
		_, err := f.s.doRecord("demo", "finding", "a claim", "src/demo.go", c.a, c.b, c.quote, "")
		if c.wantErr == "" && err != nil {
			t.Errorf("%s: refused: %v", c.name, err)
		}
		if c.wantErr != "" && (err == nil || !strings.Contains(err.Error(), c.wantErr)) {
			t.Errorf("%s: got %v, want an error containing %q", c.name, err, c.wantErr)
		}
	}
}

func TestWS_CRLFFileMatchesLikeLF(t *testing.T) {
	f := newWS(t)
	writeT(t, f.root, "src/win.txt", "first\r\nsecond line\r\nthird\r\n")
	if _, err := f.s.doRecord("demo", "finding", "c", "src/win.txt", 1, 2, "first\r\nsecond", ""); err != nil {
		t.Fatalf("CRLF quote over CRLF file: %v", err)
	}
	if _, err := f.s.doRecord("demo", "finding", "c", "src/win.txt", 2, 2, "second line", ""); err != nil {
		t.Fatalf("single CRLF line: %v", err)
	}
}

func TestWS_RecallReportsEachAnchorState(t *testing.T) {
	f := newWS(t)
	f.record(t, "finding", 3, 3, "Refund caps every refund") // will be MOVED
	f.record(t, "finding", 5, 5, "if asked > charge {")      // will be BROKEN
	writeT(t, f.root, "src/other.go", "package demo\n")
	if _, err := f.s.doRecord("demo", "finding", "c", "src/other.go", 1, 1, "package demo", ""); err != nil {
		t.Fatal(err) // will be GONE
	}
	writeT(t, f.root, "src/keep.go", "package keep\n")
	if _, err := f.s.doRecord("demo", "finding", "c", "src/keep.go", 1, 1, "package keep", ""); err != nil {
		t.Fatal(err) // stays FRESH
	}

	for _, r := range f.recall(t) {
		if r.State != stateFresh {
			t.Fatalf("before any change, #%d is %s", r.ID, r.State)
		}
	}

	// Two lines added above the comment, and the condition rewritten. By hand: the comment moves from 3 to 5.
	edited := strings.Replace(wsFile, "package demo\n", "package demo\n\nimport \"fmt\"\n", 1)
	edited = strings.Replace(edited, "if asked > charge {", "if charge < asked {", 1)
	writeT(t, f.root, "src/demo.go", edited)
	if err := os.Remove(filepath.Join(f.root, "src", "other.go")); err != nil {
		t.Fatal(err)
	}

	got := map[int]recalled{}
	for _, r := range f.recall(t) {
		got[r.ID] = r
	}
	want := map[int][2]string{1: {stateMoved, "5-5"}, 2: {stateBroken, ""}, 3: {stateGone, ""}, 4: {stateFresh, ""}}
	for id, w := range want {
		if got[id].State != w[0] || got[id].Now != w[1] {
			t.Errorf("#%d: got %s at %q, want %s at %q", id, got[id].State, got[id].Now, w[0], w[1])
		}
	}
	if b := f.brief(t); b.Anchors[stateFresh] != 1 || b.Anchors[stateMoved] != 1 || b.Anchors[stateBroken] != 1 || b.Anchors[stateGone] != 1 || b.Anchors[stateIntact] != 0 {
		t.Errorf("brief anchors: %v", b.Anchors)
	}
}

// Found in the live run: a short quote that occurs several times was relocated to its first occurrence,
// not to where it moved. The whole evidence lines are now kept and searched first.
func TestWS_AShortQuoteMovesWithItsLineAndSaysWhenItCannotTell(t *testing.T) {
	f := newWS(t)
	// By hand: "total" is on lines 1, 3 and 5, each line different. The finding is on line 5, "total c".
	// One line is added at the top, so "total c" is now on line 6, and it occurs once.
	body := "total a\nx\ntotal b\ny\ntotal c\n"
	writeT(t, f.root, "src/t.txt", body)
	if _, err := f.s.doRecord("demo", "finding", "c", "src/t.txt", 5, 5, "total", ""); err != nil {
		t.Fatal(err)
	}
	writeT(t, f.root, "src/t.txt", "new\n"+body)
	if r := f.recall(t)[0]; r.State != stateMoved || r.Now != "6-6" || r.Places != 0 {
		t.Fatalf("distinct lines: got %s at %q with %d places, want MOVED at 6-6 and no count", r.State, r.Now, r.Places)
	}

	// Three identical lines: there is no way to tell which one moved, so the count must say so.
	same := "total\nx\ntotal\ny\ntotal\n"
	writeT(t, f.root, "src/s.txt", same)
	if _, err := f.s.doRecord("demo", "finding", "c", "src/s.txt", 5, 5, "total", ""); err != nil {
		t.Fatal(err)
	}
	writeT(t, f.root, "src/s.txt", "new\n"+same)
	if r := f.recall(t)[1]; r.State != stateMoved || r.Places != 3 {
		t.Fatalf("identical lines: got %s with %d places, want MOVED with 3", r.State, r.Places)
	}

	// The line itself rewritten but the quote still there: found by the quote, nearest to the old line.
	// By hand: "total" is now on 2, 4 and 6 and the line "total c" is gone; nearest to 5 is a tie between
	// 4 and 6, and the earlier one wins.
	writeT(t, f.root, "src/t.txt", "new\ntotal a\nx\ntotal b\ny\ntotal C\n")
	if r := f.recall(t)[0]; r.State != stateMoved || r.Now != "4-4" || r.Places != 3 {
		t.Fatalf("rewritten line: got %s at %q with %d places", r.State, r.Now, r.Places)
	}

	// The refusal at record time names the nearest place: line 5 asked is "y"; "total" is on 2, 4 and 6.
	if _, err := f.s.doRecord("demo", "finding", "c", "src/t.txt", 5, 5, "total", ""); err == nil || !strings.Contains(err.Error(), "it is at lines 4-4") {
		t.Fatalf("record-time hint: %v", err)
	}
}

func TestWS_PathsStayInsideTheRoot(t *testing.T) {
	f := newWS(t)
	outside := filepath.Join(filepath.Dir(f.root), "outside.txt")
	if err := os.WriteFile(outside, []byte("secret\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { os.Remove(outside) })
	for _, p := range []string{"../outside.txt", "src/../../outside.txt", "..", outside, "/etc/passwd", `\outside.txt`, "", "   "} {
		if _, err := f.s.doRecord("demo", "finding", "c", p, 1, 1, "secret", ""); err == nil {
			t.Errorf("path %q was accepted", p)
		}
	}
	if _, err := f.s.doRecord("demo", "finding", "c", "src", 1, 1, "x", ""); err == nil || !strings.Contains(err.Error(), "directory") {
		t.Errorf("a directory was accepted: %v", err)
	}
	// A path that goes down and back up but stays inside is fine.
	if _, err := f.s.doRecord("demo", "finding", "c", "src/../src/demo.go", 3, 3, "Refund caps", ""); err != nil {
		t.Errorf("an inside path was refused: %v", err)
	}
}

func TestWS_SymlinkOutOfTheRootIsRefused(t *testing.T) {
	f := newWS(t)
	outsideDir := t.TempDir()
	if err := os.WriteFile(filepath.Join(outsideDir, "s.txt"), []byte("secret\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(filepath.Join(outsideDir, "s.txt"), filepath.Join(f.root, "link.txt")); err != nil {
		t.Skipf("cannot create a symlink here: %v", err)
	}
	// Corrected 2026-11-20: this expected "outside the project root", the message from before every path component
	// was checked for links. The link check now refuses first, as it does for a junction below. The test had
	// only ever been skipped (no symlink privilege on the Windows machine it was written on); Linux CI ran it.
	if _, err := f.s.doRecord("demo", "finding", "c", "link.txt", 1, 1, "secret", ""); err == nil || !strings.Contains(err.Error(), "goes through a link (link.txt)") {
		t.Fatalf("symlink out of the root: %v", err)
	}
}

// A directory junction needs no privilege on Windows, so unlike a symlink this test runs here. Go reads
// straight through a junction, which is why every path component is checked.
func TestWS_JunctionOutOfTheRootIsRefused(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("junctions are a Windows feature")
	}
	f := newWS(t)
	outsideDir := t.TempDir()
	if err := os.WriteFile(filepath.Join(outsideDir, "s.txt"), []byte("secret\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	if out, err := exec.Command("cmd", "/c", "mklink", "/J", filepath.Join(f.root, "junc"), outsideDir).CombinedOutput(); err != nil {
		t.Fatalf("mklink /J: %v %s", err, out)
	}
	if b, err := os.ReadFile(filepath.Join(f.root, "junc", "s.txt")); err != nil || string(b) != "secret\n" {
		t.Fatalf("the junction does not lead outside, so this test proves nothing: %q %v", b, err)
	}
	_, err := f.s.doRecord("demo", "finding", "c", "junc/s.txt", 1, 1, "secret", "")
	if err == nil || !strings.Contains(err.Error(), "goes through a link (junc)") {
		t.Fatalf("junction out of the root: %v", err)
	}
}

// Review finding: an edit elsewhere in a file reported every finding in it MOVED, with now_at equal to
// the old lines. By hand: a line appended at the end leaves line 3 exactly as it was.
func TestWS_AnEditElsewhereLeavesTheEvidenceIntact(t *testing.T) {
	f := newWS(t)
	f.record(t, "finding", 3, 3, "Refund caps every refund")
	writeT(t, f.root, "src/demo.go", wsFile+"\nfunc Extra() {}\n")
	if r := f.recall(t)[0]; r.State != stateIntact || r.Now != "" {
		t.Fatalf("append at the end: got %s at %q, want INTACT", r.State, r.Now)
	}
	// The evidence line itself changed in place: not INTACT any more.
	writeT(t, f.root, "src/demo.go", strings.Replace(wsFile, "every refund", "each refund", 1))
	if r := f.recall(t)[0]; r.State != stateBroken {
		t.Fatalf("evidence line rewritten: got %s, want BROKEN", r.State)
	}
	if b := f.brief(t); b.Anchors[stateIntact] != 0 || b.Anchors[stateBroken] != 1 {
		t.Fatalf("brief anchors: %v", b.Anchors)
	}
}

// Review finding: findQuote recounted newlines from the start of the file for every occurrence, which is
// quadratic. A 4 MiB file of "}" lines has about two million occurrences; the old code needed on the
// order of 10^12 byte scans for one recall.
func TestWS_ManyOccurrencesRecallInLinearTime(t *testing.T) {
	f := newWS(t)
	big := strings.Repeat("}\n", (wsMaxFileBytes-16)/2)
	writeT(t, f.root, "src/big.txt", "head\n"+big)
	if _, err := f.s.doRecord("demo", "finding", "c", "src/big.txt", 2, 2, "}", ""); err != nil {
		t.Fatal(err)
	}
	writeT(t, f.root, "src/big.txt", "head\nmore\n"+big)
	done := make(chan recalled, 1)
	go func() { done <- f.recall(t)[0] }()
	select {
	case r := <-done:
		if r.State != stateMoved || r.Now != "3-3" || r.Places != (wsMaxFileBytes-16)/2 {
			t.Fatalf("got %s at %q with %d places", r.State, r.Now, r.Places)
		}
	case <-time.After(20 * time.Second):
		t.Fatal("recall took over 20 seconds on one 4 MiB file")
	}
}

// Review finding: recall read and hashed a file once per finding. Three findings on one file must read it once.
func TestWS_RecallReadsEachFileOnce(t *testing.T) {
	f := newWS(t)
	for _, q := range []string{"Refund caps", "func Refund", "return asked"} {
		lines := splitLines([]byte(wsFile))
		a, _, _ := findQuote(lines, q, 1)
		if _, err := f.s.doRecord("demo", "finding", "c", "src/demo.go", a, a, q, ""); err != nil {
			t.Fatal(err)
		}
	}
	reads := 0
	real := wsReadFile
	wsReadFile = func(p string) ([]byte, error) { reads++; return real(p) }
	defer func() { wsReadFile = real }()
	if rows := f.recall(t); len(rows) != 3 || reads != 1 {
		t.Fatalf("%d findings, %d reads; want 3 findings and 1 read", len(rows), reads)
	}
}

// Review finding: a result recorded with gitignored data present was shown on a tree without it. By hand:
// data/ is ignored; the result is recorded with data/x.bin present; removing data/ hides it; restoring shows it.
func TestWS_AResultNeedsTheSameIgnoredFiles(t *testing.T) {
	f := newWS(t)
	writeT(t, f.root, ".gitignore", "data/\n")
	gitT(t, f.root, "add", ".gitignore")
	gitT(t, f.root, "commit", "-qm", "ignore data")
	head := gitT(t, f.root, "rev-parse", "HEAD")
	writeT(t, f.root, "data/x.bin", "corpus\n")
	if _, err := f.s.doResult("demo", "go test ./...", "pass", "3 passed", "", "", head); err != nil {
		t.Fatal(err)
	}
	if b := f.brief(t); len(b.Results) != 1 {
		t.Fatalf("with data present: %+v", b.Results)
	}
	if err := os.RemoveAll(filepath.Join(f.root, "data")); err != nil {
		t.Fatal(err)
	}
	if b := f.brief(t); !b.Clean || len(b.Results) != 0 {
		t.Fatalf("data removed, tree clean=%v, still shown: %+v", b.Clean, b.Results)
	}
	writeT(t, f.root, "data/x.bin", "corpus\n")
	if b := f.brief(t); len(b.Results) != 1 {
		t.Fatalf("data restored: %+v", b.Results)
	}
}

// Review finding: seq is max+1, so two writers at once might collide. PocketBase serializes write
// transactions, so they should not; this checks it with 16 at once.
func TestWS_ConcurrentRecordsGetDistinctIDs(t *testing.T) {
	f := newWS(t)
	var wg sync.WaitGroup
	errs := make(chan error, 16)
	for i := 0; i < 16; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			_, err := f.s.doRecord("demo", "finding", "c", "src/demo.go", 3, 3, "Refund caps", "")
			errs <- err
		}()
	}
	wg.Wait()
	close(errs)
	for err := range errs {
		if err != nil {
			t.Fatalf("a concurrent record failed: %v", err)
		}
	}
	ids := map[int]bool{}
	for _, r := range f.recall(t) {
		ids[r.ID] = true
	}
	for i := 1; i <= 16; i++ {
		if !ids[i] {
			t.Fatalf("ids %v, want 1..16 each once", ids)
		}
	}
}

// Review finding: a root reached through a junction could not be registered, because EvalSymlinks fails
// through a junction since Go 1.23. Registering through one, and recording under it, must work.
func TestWS_ARootReachedThroughAJunctionWorks(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("junctions are a Windows feature")
	}
	// The case from the review: the junction is above the root (C:\dev a junction, the repo C:\dev\x).
	// EvalSymlinks fails on a path through a junction, but not on the junction itself, so the root must
	// be below it for this test to mean anything.
	f := newWS(t)
	via := filepath.Join(t.TempDir(), "via")
	if out, err := exec.Command("cmd", "/c", "mklink", "/J", via, filepath.Dir(f.root)).CombinedOutput(); err != nil {
		t.Fatalf("mklink /J: %v %s", err, out)
	}
	through := filepath.Join(via, filepath.Base(f.root))
	if _, err := filepath.EvalSymlinks(through); err == nil {
		t.Log("EvalSymlinks resolved a path through a junction here; the old code would have passed too")
	}
	if _, err := f.s.doRegisterProject("through", through); err != nil {
		t.Fatalf("register through a junction: %v", err)
	}
	if _, err := f.s.doRecord("through", "finding", "c", "src/demo.go", 3, 3, "Refund caps", ""); err != nil {
		t.Fatalf("record under a junction root: %v", err)
	}
}

// Review finding: every ModeIrregular path was refused, which would include OneDrive cloud placeholders.
// The link test now reads the reparse tag. Ground truth: Microsoft's published tag values
// (winnt.h); bit 29 is the name-surrogate bit.
func TestWS_OnlyNameSurrogateTagsAreLinks(t *testing.T) {
	cases := map[string]struct {
		tag  uint32
		link bool
	}{
		"IO_REPARSE_TAG_MOUNT_POINT (junction)": {0xA0000003, true},
		"IO_REPARSE_TAG_SYMLINK":                {0xA000000C, true},
		"IO_REPARSE_TAG_CLOUD (OneDrive)":       {0x9000001A, false},
		"IO_REPARSE_TAG_CLOUD_3":                {0x9000301A, false},
		"IO_REPARSE_TAG_DEDUP":                  {0x80000013, false},
		"IO_REPARSE_TAG_APPEXECLINK":            {0x8000001B, false},
	}
	for name, c := range cases {
		if got := surrogateTagForTest(c.tag); got != c.link {
			t.Errorf("%s (0x%08X): link=%v, want %v", name, c.tag, got, c.link)
		}
	}
}

func TestWS_OversizeFileIsRefused(t *testing.T) {
	f := newWS(t)
	writeT(t, f.root, "big.txt", "x"+strings.Repeat("y", wsMaxFileBytes))
	if _, err := f.s.doRecord("demo", "finding", "c", "big.txt", 1, 1, "x", ""); err == nil || !strings.Contains(err.Error(), "byte limit") {
		t.Fatalf("oversize file: %v", err)
	}
}

func TestWS_UnknownsResolveOnceAndFindingsNever(t *testing.T) {
	f := newWS(t)
	f.record(t, "finding", 3, 3, "Refund caps")
	if _, err := f.s.doRecord("demo", "unknown", "is a negative refund possible?", "src/demo.go", 4, 4, "func Refund", ""); err != nil {
		t.Fatal(err)
	}
	if _, err := f.s.doRecord("demo", "guess", "c", "src/demo.go", 3, 3, "Refund", ""); err == nil {
		t.Fatal("kind 'guess' was accepted")
	}
	b := f.brief(t)
	if len(b.OpenUnknowns) != 1 || b.OpenUnknowns[0].ID != 2 {
		t.Fatalf("open unknowns: %+v", b.OpenUnknowns)
	}
	if _, err := f.s.doResolve("demo", 1, "x", ""); err == nil || !strings.Contains(err.Error(), "is a finding") {
		t.Fatalf("resolving a finding: %v", err)
	}
	if _, err := f.s.doResolve("demo", 9, "x", ""); err == nil || !strings.Contains(err.Error(), "no finding #9") {
		t.Fatalf("resolving a missing id: %v", err)
	}
	if _, err := f.s.doResolve("demo", 2, "yes, when asked is negative", "me"); err != nil {
		t.Fatal(err)
	}
	if _, err := f.s.doResolve("demo", 2, "no", "me"); err == nil || !strings.Contains(err.Error(), "already resolved") {
		t.Fatalf("second resolution: %v", err)
	}
	rows := f.recall(t)
	if rows[1].Claim != "is a negative refund possible?" || !strings.Contains(rows[1].Resolution, "yes, when asked is negative") || rows[1].Open {
		t.Fatalf("the question or its resolution was lost: %+v", rows[1])
	}
	if len(f.brief(t).OpenUnknowns) != 0 {
		t.Fatal("a resolved unknown is still open")
	}
}

func TestWS_BriefShowsTheLatestNote(t *testing.T) {
	f := newWS(t)
	if b := f.brief(t); b.LastNote != nil || b.Notes != 0 {
		t.Fatalf("a new project has a note: %+v", b.LastNote)
	}
	for _, n := range []string{"first", "second", "third"} {
		if _, err := f.s.doNote("demo", n, "s"+n); err != nil {
			t.Fatal(err)
		}
	}
	b := f.brief(t)
	if b.Notes != 3 || b.LastNote == nil || b.LastNote.Text != "third" || b.LastNote.ID != 3 || b.LastNote.By != "sthird" {
		t.Fatalf("brief: notes=%d last=%+v", b.Notes, b.LastNote)
	}
	if b.LastNote.Commit != gitT(t, f.root, "rev-parse", "HEAD") {
		t.Fatalf("note commit %q", b.LastNote.Commit)
	}
	if _, err := f.s.doNote("demo", "  ", ""); err == nil {
		t.Fatal("an empty note was accepted")
	}
}

func TestWS_ResultsNeedACleanTreeAndBelongToOneCommit(t *testing.T) {
	f := newWS(t)
	head := gitT(t, f.root, "rev-parse", "HEAD")
	host := runtime.GOOS + "/" + runtime.GOARCH

	writeT(t, f.root, "scratch.txt", "untracked\n")
	if _, err := f.s.doResult("demo", "go test ./...", "pass", "3 passed", "", "", head); err == nil || !strings.Contains(err.Error(), "uncommitted or untracked") {
		t.Fatalf("an untracked file did not block the result: %v", err)
	}
	os.Remove(filepath.Join(f.root, "scratch.txt"))
	writeT(t, f.root, "src/demo.go", wsFile+"// edit\n")
	if _, err := f.s.doResult("demo", "go test ./...", "pass", "3 passed", "", "", head); err == nil {
		t.Fatal("a modified file did not block the result")
	}
	gitT(t, f.root, "checkout", "--", "src/demo.go")

	if _, err := f.s.doResult("demo", "go test ./...", "pass", "3 passed", "", "", "0123456789abcdef0123456789abcdef01234567"); err == nil || !strings.Contains(err.Error(), "is not HEAD") {
		t.Fatalf("a result for another commit was accepted: %v", err)
	}
	if _, err := f.s.doResult("demo", "go test ./...", "pass", "3 passed", "", "", " "); err == nil || !strings.Contains(err.Error(), "tested_at") {
		t.Fatalf("a result without tested_at was accepted: %v", err)
	}
	if _, err := f.s.doResult("demo", "go test ./...", "maybe", "x", "", "", head); err == nil {
		t.Fatal("outcome 'maybe' was accepted")
	}
	if _, err := f.s.doResult("demo", "go test ./...", "fail", "1 failed", "go1.27", "a", head); err != nil {
		t.Fatal(err)
	}
	out, err := f.s.doResult("demo", "go test ./...", "pass", "3 passed", "go1.27", "b", head)
	if err != nil || !strings.Contains(out, "replaced") {
		t.Fatalf("same key again: %q %v", out, err)
	}
	if _, err := f.s.doResult("demo", "go test ./...", "fail", "symlink test failed", "go1.27 no-symlinks", "c", head); err != nil {
		t.Fatal(err)
	}

	b := f.brief(t)
	if b.Commit != head || !b.Clean || len(b.Results) != 2 {
		t.Fatalf("brief at %s clean=%v results=%+v", b.Commit, b.Clean, b.Results)
	}
	envs := map[string]string{}
	for _, r := range b.Results {
		envs[r.Env] = r.Outcome + " " + r.Summary
	}
	if envs[host+" go1.27"] != "pass 3 passed" || envs[host+" go1.27 no-symlinks"] != "fail symlink test failed" {
		t.Fatalf("results by env: %v", envs)
	}

	// A new commit: the old results no longer describe this tree, so the brief shows none.
	writeT(t, f.root, "src/demo.go", wsFile+"// next\n")
	gitT(t, f.root, "commit", "-qam", "next")
	if b := f.brief(t); len(b.Results) != 0 || b.Commit == head {
		t.Fatalf("results from the old commit shown at the new one: %+v", b.Results)
	}
	// And a dirty tree shows none either, even at the commit that has results.
	gitT(t, f.root, "checkout", "-q", head)
	writeT(t, f.root, "scratch.txt", "x\n")
	if b := f.brief(t); b.Clean || len(b.Results) != 0 {
		t.Fatalf("dirty tree showed results: clean=%v %+v", b.Clean, b.Results)
	}
}

func TestWS_RegistrationRules(t *testing.T) {
	f := newWS(t)
	if out, err := f.s.doRegisterProject("demo", f.root); err != nil || !strings.Contains(out, "already registered") {
		t.Fatalf("same root again: %q %v", out, err)
	}
	if _, err := f.s.doRegisterProject("demo", t.TempDir()); err == nil || !strings.Contains(err.Error(), "never changed") {
		t.Fatalf("a different root was accepted: %v", err)
	}
	for _, root := range []string{"relative/path", ".", "", filepath.Join(f.root, "src", "demo.go"), filepath.Join(f.root, "nope")} {
		if _, err := f.s.doRegisterProject("x", root); err == nil {
			t.Errorf("root %q was accepted", root)
		}
	}
	if _, err := f.s.doRecall("ghost", ""); err == nil || !strings.Contains(err.Error(), "register it first") {
		t.Fatalf("unregistered project: %v", err)
	}
	if _, err := f.s.doRegisterProject(strings.Repeat("n", wsMaxName+1), f.root); err == nil {
		t.Fatal("an over-long name was accepted")
	}
}

func listToolNames(t *testing.T, s *AgentBaseMCPServer) map[string]bool {
	t.Helper()
	resp := s.mcpServer.HandleMessage(context.Background(), json.RawMessage(`{"jsonrpc":"2.0","id":1,"method":"tools/list"}`))
	raw, _ := json.Marshal(resp)
	var d struct {
		Result struct {
			Tools []struct {
				Name string `json:"name"`
			} `json:"tools"`
		} `json:"result"`
	}
	if err := json.Unmarshal(raw, &d); err != nil {
		t.Fatal(err)
	}
	names := map[string]bool{}
	for _, tl := range d.Result.Tools {
		names[tl.Name] = true
	}
	return names
}

func TestWS_OnlyALocalServerHasTheWorkspaceTools(t *testing.T) {
	remote := newTestServer(t) // what BindHTTP serves: EnableWorkspace is never called
	for _, n := range wsTools {
		if listToolNames(t, remote)[n] {
			t.Fatalf("the remote server offers %s, which reads files", n)
		}
	}
	local := newTestServer(t)
	local.EnableWorkspace()
	names := listToolNames(t, local)
	for _, n := range wsTools {
		if !names[n] {
			t.Fatalf("the local server does not offer %s", n)
		}
	}
	if len(names) != 11+len(wsTools) {
		t.Fatalf("local server offers %d tools, want %d", len(names), 11+len(wsTools))
	}
}

func TestWS_WorkspaceOnlyOffersTheWorkspaceToolsAndNothingElse(t *testing.T) {
	s := newTestServer(t)
	s.EnableWorkspace()
	s.WorkspaceOnly()
	names := listToolNames(t, s)
	// Written out by hand, not taken from wsTools, so a change to that list is caught here.
	want := []string{"ws_register_project", "ws_record", "ws_recall", "ws_resolve", "ws_note", "ws_result", "ws_brief",
		"ws_summarize"}
	if len(names) != len(want) {
		t.Fatalf("workspace-only server offers %d tools %v, want exactly %v", len(names), names, want)
	}
	for _, n := range want {
		if !names[n] {
			t.Fatalf("workspace-only server does not offer %s", n)
		}
	}
	// The tools that stay still work.
	root := t.TempDir()
	if out, isErr := callWS(t, s, "ws_register_project", map[string]any{"name": "p", "root": root}); isErr {
		t.Fatalf("ws_register_project failed: %s", out)
	}
	if out, isErr := callWS(t, s, "ws_brief", map[string]any{"project": "p"}); isErr {
		t.Fatalf("ws_brief failed: %s", out)
	}
	// A removed tool is refused, not silently run.
	body, _ := json.Marshal(map[string]any{"jsonrpc": "2.0", "id": 9, "method": "tools/call",
		"params": map[string]any{"name": "query_ledger", "arguments": map[string]any{"account": "a"}}})
	raw, _ := json.Marshal(s.mcpServer.HandleMessage(context.Background(), body))
	if !strings.Contains(string(raw), `"error"`) || !strings.Contains(string(raw), "not found") {
		t.Fatalf("query_ledger on a workspace-only server: %s", raw)
	}
}

func callWS(t *testing.T, s *AgentBaseMCPServer, tool string, args map[string]any) (string, bool) {
	t.Helper()
	body, _ := json.Marshal(map[string]any{"jsonrpc": "2.0", "id": 9, "method": "tools/call",
		"params": map[string]any{"name": tool, "arguments": args}})
	resp := s.mcpServer.HandleMessage(context.Background(), body)
	raw, _ := json.Marshal(resp)
	var d struct {
		Result struct {
			Content []struct {
				Text string `json:"text"`
			} `json:"content"`
			IsError bool `json:"isError"`
		} `json:"result"`
	}
	if err := json.Unmarshal(raw, &d); err != nil || len(d.Result.Content) == 0 {
		t.Fatalf("tools/call %s: %s", tool, raw)
	}
	return d.Result.Content[0].Text, d.Result.IsError
}

func TestWS_MCPRefusesAFractionalLine(t *testing.T) {
	f := newWS(t)
	f.s.EnableWorkspace()
	args := map[string]any{"project": "demo", "kind": "finding", "claim": "c", "path": "src/demo.go",
		"line_start": 3.7, "line_end": 3, "quote": "Refund"}
	if text, isErr := callWS(t, f.s, "ws_record", args); !isErr || !strings.Contains(text, "whole number") {
		t.Fatalf("3.7 was accepted: %q", text)
	}
	args["line_start"] = 3
	if text, isErr := callWS(t, f.s, "ws_record", args); isErr {
		t.Fatalf("a valid call failed: %q", text)
	}
	if text, isErr := callWS(t, f.s, "ws_brief", map[string]any{"project": "demo"}); isErr || !strings.Contains(text, `"FRESH":1`) {
		t.Fatalf("brief over MCP: %q", text)
	}
}
