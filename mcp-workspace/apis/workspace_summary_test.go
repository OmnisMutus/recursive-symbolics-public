package apis

// Ground truth for summaries, the compact brief and the usage log, none of it from workspace.go:
//   - file contents and changes are made here, so whether a summary should be FRESH, STALE or GONE is known;
//   - commit counts come from commits this test makes, checked with git rev-list;
//   - the bytes a call returned are counted on the client side, from the JSON-RPC answer itself.

import (
	"bufio"
	"encoding/json"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"unicode/utf8"
)

func TestWS_ASummaryIsFreshUntilItsFileChanges(t *testing.T) {
	f := newWS(t)
	if _, err := f.s.doSummarize("demo", "src/demo.go", "Refund: caps a refund at the charge.", "test"); err != nil {
		t.Fatal(err)
	}
	got := f.summaries(t, "")
	if len(got) != 1 || got[0].State != stateFresh || got[0].Path != "src/demo.go" || got[0].Lines != 9 {
		t.Fatalf("after summarizing: %+v", got)
	}
	if b := f.brief(t); b.Summaries.Fresh != 1 || len(b.Summaries.Stale) != 0 {
		t.Fatalf("brief summaries: %+v", b.Summaries)
	}
	writeT(t, f.root, "src/demo.go", wsFile+"// one more line\n")
	if got := f.summaries(t, "src/"); got[0].State != stateStale {
		t.Fatalf("the file changed but the summary is %s", got[0].State)
	}
	if b := f.brief(t); b.Summaries.Fresh != 0 || len(b.Summaries.Stale) != 1 || b.Summaries.Stale[0] != "src/demo.go" {
		t.Fatalf("brief does not list the stale summary: %+v", b.Summaries)
	}
	if err := os.Remove(filepath.Join(f.root, "src", "demo.go")); err != nil {
		t.Fatal(err)
	}
	if got := f.summaries(t, ""); got[0].State != stateGone {
		t.Fatalf("the file is gone but the summary is %s", got[0].State)
	}
	if got := f.summaries(t, "other/"); len(got) != 0 {
		t.Fatalf("the prefix did not filter: %+v", got)
	}
}

func TestWS_SummaryRules(t *testing.T) {
	f := newWS(t)
	if _, err := f.s.doSummarize("demo", "src/demo.go", strings.Repeat("x", len(wsFile)), ""); err == nil ||
		!strings.Contains(err.Error(), "shorter than the file") {
		t.Fatalf("a summary as long as the file was accepted: %v", err)
	}
	writeT(t, f.root, "big.txt", strings.Repeat("line of text\n", 400))
	if _, err := f.s.doSummarize("demo", "big.txt", strings.Repeat("y", wsMaxFileSummary+1), ""); err == nil ||
		!strings.Contains(err.Error(), "over the limit") {
		t.Fatalf("a summary over the limit was accepted: %v", err)
	}
	if _, err := f.s.doSummarize("demo", "../outside.txt", "s", ""); err == nil {
		t.Fatal("a path outside the root was accepted")
	}
	for i, text := range []string{"first version", "second version"} {
		out, err := f.s.doSummarize("demo", "big.txt", text, "")
		if err != nil {
			t.Fatal(err)
		}
		if want := []string{"stored", "replaced"}[i]; !strings.Contains(out, want) {
			t.Fatalf("summary %d: %q does not say %s", i+1, out, want)
		}
	}
	got := f.summaries(t, "big.txt")
	if len(got) != 1 || got[0].Summary != "second version" {
		t.Fatalf("one summary per file, the latest: %+v", got)
	}
}

func TestWS_ADatabaseFromBeforeSummariesGainsThem(t *testing.T) {
	f := newWS(t)
	f.record(t, "finding", 3, 3, "Refund caps") // creates the collections, ws_summaries among them
	c, err := f.s.app.FindCollectionByNameOrId("ws_summaries")
	if err != nil {
		t.Fatal(err)
	}
	if err := f.s.app.Delete(c); err != nil { // the database as it was before this table existed
		t.Fatal(err)
	}
	if got := f.summaries(t, ""); len(got) != 0 {
		t.Fatalf("recall without the table: %+v", got)
	}
	if _, err := f.s.doSummarize("demo", "src/demo.go", "Refund caps refunds.", ""); err != nil {
		t.Fatalf("summarizing on an older database: %v", err)
	}
	if len(f.recall(t)) != 1 || len(f.summaries(t, "")) != 1 {
		t.Fatal("the older finding or the new summary is missing")
	}
}

func TestWS_TheBriefShowsHeadsAndWhatChanged(t *testing.T) {
	f := newWS(t)
	long := "Is a negative refund possible? If asked is below zero the function returns it unchanged, " +
		"which would pay the customer twice."
	if _, err := f.s.doRecord("demo", "unknown", long, "src/demo.go", 4, 4, "func Refund", ""); err != nil {
		t.Fatal(err)
	}
	f.record(t, "finding", 5, 5, "if asked > charge")
	b := f.brief(t)
	if len(b.OpenUnknowns) != 1 || b.OpenUnknowns[0].Head != "Is a negative refund possible?" || !b.OpenUnknowns[0].More {
		t.Fatalf("open unknown head: %+v", b.OpenUnknowns)
	}
	if strings.Contains(mustJSON(t, b), "pay the customer twice") {
		t.Fatal("the brief carries the whole claim")
	}
	if rows := f.recall(t); rows[0].Claim != long {
		t.Fatalf("recall lost the whole claim: %q", rows[0].Claim)
	}
	if len(b.NeedsAttention) != 0 {
		t.Fatalf("nothing changed, yet: %+v", b.NeedsAttention)
	}
	writeT(t, f.root, "src/demo.go", strings.Replace(wsFile, "if asked > charge", "if asked >= charge", 1))
	b = f.brief(t)
	if len(b.NeedsAttention) != 1 || b.NeedsAttention[0].ID != 2 || b.NeedsAttention[0].State != stateBroken {
		t.Fatalf("the broken finding is not listed: %+v", b.NeedsAttention)
	}
	if b.NeedsAttention[0].Head != "refunds never exceed the charge" || b.NeedsAttention[0].More {
		t.Fatalf("a short claim is its own head: %+v", b.NeedsAttention[0])
	}
}

func TestWS_HeadCutsOnARuneBoundary(t *testing.T) {
	// One ASCII byte, then two-byte letters with no sentence end: byte wsHeadMax (even) falls inside a letter.
	claim := "x" + strings.Repeat("א", 200)
	if utf8.RuneStart(claim[wsHeadMax]) {
		t.Fatal("the test text no longer puts the cut inside a character")
	}
	h, more := head(claim)
	if !more || len(h) > wsHeadMax || !strings.HasPrefix(claim, h) || !utf8.ValidString(h) {
		t.Fatalf("head %q (%d bytes), more %v", h, len(h), more)
	}
	if h, more := head("Short."); h != "Short." || more {
		t.Fatalf("short claim: %q %v", h, more)
	}
}

func TestWS_TheBriefCountsCommitsSinceTheLastNote(t *testing.T) {
	f := newWS(t)
	if b := f.brief(t); b.CommitsSince != nil {
		t.Fatalf("no note yet, but commits_since_last_note is %d", *b.CommitsSince)
	}
	if _, err := f.s.doNote("demo", "where things stand", ""); err != nil {
		t.Fatal(err)
	}
	noted := gitT(t, f.root, "rev-parse", "HEAD")
	for i := 0; i < 2; i++ {
		writeT(t, f.root, "n"+strconv.Itoa(i)+".txt", "x\n")
		gitT(t, f.root, "add", "-A")
		gitT(t, f.root, "commit", "-q", "-m", "after the note")
	}
	want, _ := strconv.Atoi(gitT(t, f.root, "rev-list", "--count", noted+"..HEAD"))
	if b := f.brief(t); b.CommitsSince == nil || *b.CommitsSince != want || want != 2 {
		t.Fatalf("commits since the note: %v, git says %d", b.CommitsSince, want)
	}
}

func TestWS_ANoteIsAtMost4000Bytes(t *testing.T) {
	f := newWS(t)
	if _, err := f.s.doNote("demo", strings.Repeat("n", wsNoteLimit), ""); err != nil {
		t.Fatalf("a note of exactly the limit: %v", err)
	}
	if _, err := f.s.doNote("demo", strings.Repeat("n", wsNoteLimit+1), ""); err == nil || !strings.Contains(err.Error(), "over the limit") {
		t.Fatalf("a note over the limit: %v", err)
	}
	if wsNoteLimit != 4000 {
		t.Fatalf("the limit the tool description states is 4000, the code has %d", wsNoteLimit)
	}
}

func readUsage(t *testing.T, path string) []usageLine {
	t.Helper()
	fh, err := os.Open(path)
	if err != nil {
		t.Fatal(err)
	}
	defer fh.Close()
	var out []usageLine
	sc := bufio.NewScanner(fh)
	for sc.Scan() {
		var l usageLine
		if err := json.Unmarshal(sc.Bytes(), &l); err != nil {
			t.Fatalf("not a usage line: %s", sc.Text())
		}
		out = append(out, l)
	}
	return out
}

func TestWS_EveryWorkspaceCallIsMeasuredAndNothingElseIsWritten(t *testing.T) {
	f := newWS(t)
	log := filepath.Join(t.TempDir(), "usage.jsonl")
	f.s.usage = newUsage(log)
	f.s.EnableWorkspace()
	secret := "a-distinctive-word-in-a-note"
	calls := []struct {
		tool string
		args map[string]any
	}{
		{"ws_note", map[string]any{"project": "demo", "text": "remember " + secret}},
		{"ws_summarize", map[string]any{"project": "demo", "path": "src/demo.go", "summary": "Refund caps refunds."}},
		{"ws_brief", map[string]any{"project": "demo"}},
		{"ws_recall", map[string]any{"project": "ghost"}}, // an error is measured too
	}
	var outBytes []int
	for _, c := range calls {
		text, _ := callWS(t, f.s, c.tool, c.args)
		outBytes = append(outBytes, len(text))
	}
	lines := readUsage(t, log)
	if len(lines) != len(calls) {
		t.Fatalf("%d calls, %d usage lines", len(calls), len(lines))
	}
	for i, l := range lines {
		if l.Tool != calls[i].tool || l.Out != outBytes[i] || l.Session != lines[0].Session || l.Session == "" {
			t.Fatalf("line %d: %+v; the client received %d bytes from %s", i, l, outBytes[i], calls[i].tool)
		}
		in, _ := json.Marshal(calls[i].args)
		if l.In != len(in) {
			t.Fatalf("line %d: in %d, the arguments are %d bytes", i, l.In, len(in))
		}
	}
	if !lines[3].Error || lines[0].Error || lines[0].Project != "demo" {
		t.Fatalf("error and project fields: %+v", lines)
	}
	raw, _ := os.ReadFile(log)
	if strings.Contains(string(raw), secret) || strings.Contains(string(raw), "Refund caps") {
		t.Fatal("the usage log holds what was said, not only its size")
	}
	rep, err := UsageReport(log)
	if err != nil {
		t.Fatal(err)
	}
	total := 0
	for _, n := range outBytes {
		total += n
	}
	if !strings.Contains(rep, lines[0].Session) || !strings.Contains(rep, "4 calls") ||
		!strings.Contains(rep, strconv.Itoa(total)+" bytes out") {
		t.Fatalf("report does not match the calls (total out %d):\n%s", total, rep)
	}
}

func TestWS_ALogThatCannotBeWrittenNeverFailsTheCall(t *testing.T) {
	f := newWS(t)
	f.s.usage = newUsage(filepath.Join(t.TempDir(), "no such folder", "usage.jsonl"))
	f.s.EnableWorkspace()
	if text, isErr := callWS(t, f.s, "ws_brief", map[string]any{"project": "demo"}); isErr {
		t.Fatalf("the brief failed because the log could not be written: %s", text)
	}
}

func TestWS_TheReportSkipsLinesItCannotRead(t *testing.T) {
	p := filepath.Join(t.TempDir(), "u.jsonl")
	body := `{"t":"2026-11-12T01:00:00Z","session":"aa","tool":"ws_brief","in":10,"out":300}` + "\nnot json\n" +
		`{"t":"2026-11-12T01:01:00Z","session":"aa","tool":"ws_recall","in":5,"out":700}` + "\n"
	if err := os.WriteFile(p, []byte(body), 0o600); err != nil {
		t.Fatal(err)
	}
	rep, err := UsageReport(p)
	if err != nil {
		t.Fatal(err)
	}
	for _, want := range []string{"2 calls", "15 bytes in, 1000 bytes out", "ws_brief 300", "ws_recall 700", "1 lines were not usage lines"} {
		if !strings.Contains(rep, want) {
			t.Fatalf("report lacks %q:\n%s", want, rep)
		}
	}
}

func mustJSON(t *testing.T, v any) string {
	t.Helper()
	b, err := json.Marshal(v)
	if err != nil {
		t.Fatal(err)
	}
	return string(b)
}
