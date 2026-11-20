package apis

// The workspace: what an agent working on a project needs from a backend so it
// does not spend its tokens re-discovering what it already knew.
//
//   - A finding is a claim stored with its evidence: a file, a line range, the
//     quoted words, and the git blob hash of the file when the claim was made.
//     Recall checks the hash again, so a finding whose evidence changed says so.
//     FRESH means the evidence is unchanged. It never means the claim is right.
//   - An unknown is a finding that is an open question. It is closed by a
//     resolution, which is added, never written over the question.
//   - A note is what one session leaves for the next.
//   - A result is the outcome of a command at one commit, recorded only when
//     the working tree is clean, so the commit names exactly what was tested.
//
// These tools read files, so they are registered only by EnableWorkspace,
// which main.go calls in local stdio mode. The remote SSE endpoint never has them.

import (
	"crypto/sha1"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"sort"
	"strings"
	"unicode/utf8"

	"github.com/pocketbase/dbx"
	"github.com/pocketbase/pocketbase/core"
)

const (
	wsMaxFileBytes = 4 << 20
	wsMaxClaim     = 2000
	wsMaxQuote     = 2000
	wsMaxNote      = 20000
	wsMaxName      = 128
	wsMaxCommand   = 500
	wsMaxSummary   = 2000
	wsMaxEnv       = 200
	wsMaxBy        = 64
	wsBriefList    = 20
	wsMaxContext   = 8000
	// A note is read whole by every ws_brief, so it is kept short. The stored field allows wsMaxNote, so notes
	// left before this limit existed still load.
	wsNoteLimit = 4000
	// A summary is what a session reads instead of the file, so it must stay much shorter than the file.
	wsMaxFileSummary = 2000
	// How much of a claim ws_brief shows; the whole claim is one ws_recall away.
	wsHeadMax = 160
)

// Anchor states reported by recall.
const (
	stateFresh  = "FRESH"  // the file's blob hash is the one recorded
	stateIntact = "INTACT" // the file changed elsewhere; the evidence lines are unchanged, at the same lines
	stateMoved  = "MOVED"  // the file changed, the quote is still in it (lines given)
	stateBroken = "BROKEN" // the file changed and the quote is no longer in it
	stateGone   = "GONE"   // the file is not there
	stateStale  = "STALE"  // a summary whose file changed since it was written: read the file again
)

var wsKinds = map[string]bool{"finding": true, "unknown": true}
var wsOutcomes = map[string]bool{"pass": true, "fail": true}

// gitBlobHash is what `git hash-object --no-filters` prints for these bytes.
func gitBlobHash(content []byte) string {
	h := sha1.New()
	fmt.Fprintf(h, "blob %d\x00", len(content))
	h.Write(content)
	return hex.EncodeToString(h.Sum(nil))
}

// splitLines splits on \n and drops a trailing \r from each line, so a file
// with CRLF endings is matched the same way as one with LF.
func splitLines(content []byte) []string {
	lines := strings.Split(string(content), "\n")
	for i, l := range lines {
		lines[i] = strings.TrimSuffix(l, "\r")
	}
	return lines
}

func normalizeQuote(q string) string {
	return strings.ReplaceAll(q, "\r\n", "\n")
}

// findQuote returns the 1-based line range of the occurrence of quote whose
// first line is nearest to line near (the earlier one on a tie), and how many
// occurrences there are. 0, 0, 0 means none. A short quote can occur many
// times, and the first one in the file is often not the one that moved.
func findQuote(lines []string, quote string, near int) (start, end, count int) {
	text := strings.Join(lines, "\n")
	best := -1
	line, counted := 1, 0 // line is the line number of text[counted]
	for from := 0; from <= len(text); {
		i := strings.Index(text[from:], quote)
		if i < 0 {
			break
		}
		at := from + i
		line += strings.Count(text[counted:at], "\n") // each byte is counted once in all
		counted = at
		count++
		if best < 0 || absInt(line-near) < absInt(best-near) {
			best = line
		}
		from = at + 1
	}
	if count == 0 {
		return 0, 0, 0
	}
	return best, best + strings.Count(quote, "\n"), count
}

func absInt(v int) int {
	if v < 0 {
		return -v
	}
	return v
}

func boundedName(field, v string) (string, error) {
	v = strings.TrimSpace(v)
	if v == "" {
		return "", fmt.Errorf("%s must not be empty", field)
	}
	if len(v) > wsMaxName {
		return "", fmt.Errorf("%s is %d bytes, over the limit of %d", field, len(v), wsMaxName)
	}
	return v, nil
}

func boundedText(field, v string, max int) (string, error) {
	if strings.TrimSpace(v) == "" {
		return "", fmt.Errorf("%s must not be empty", field)
	}
	if len(v) > max {
		return "", fmt.Errorf("%s is %d bytes, over the limit of %d", field, len(v), max)
	}
	return v, nil
}

func byLabel(by string) (string, error) {
	by = strings.TrimSpace(by)
	if by == "" {
		return "agent", nil
	}
	if len(by) > wsMaxBy {
		return "", fmt.Errorf("by is %d bytes, over the limit of %d", len(by), wsMaxBy)
	}
	return by, nil
}

// ensureWorkspace creates the workspace collections the first time they are needed.
func ensureWorkspace(txApp core.App) error {
	if _, e := txApp.FindCollectionByNameOrId("ws_projects"); e != nil {
		c := core.NewBaseCollection("ws_projects")
		c.Fields.Add(&core.TextField{Name: "name", Required: true, Max: wsMaxName})
		c.Fields.Add(&core.TextField{Name: "root", Required: true, Max: 4096})
		c.AddIndex("idx_ws_projects_name", true, "name", "")
		if e := txApp.Save(c); e != nil {
			return e
		}
	}
	if _, e := txApp.FindCollectionByNameOrId("ws_findings"); e != nil {
		c := core.NewBaseCollection("ws_findings")
		c.Fields.Add(&core.TextField{Name: "project", Required: true, Max: wsMaxName})
		c.Fields.Add(&core.NumberField{Name: "seq", Required: true, OnlyInt: true})
		c.Fields.Add(&core.TextField{Name: "kind", Required: true, Max: 16})
		c.Fields.Add(&core.TextField{Name: "claim", Required: true, Max: wsMaxClaim})
		c.Fields.Add(&core.TextField{Name: "path", Required: true, Max: 4096})
		c.Fields.Add(&core.NumberField{Name: "line_start", Required: true, OnlyInt: true})
		c.Fields.Add(&core.NumberField{Name: "line_end", Required: true, OnlyInt: true})
		c.Fields.Add(&core.TextField{Name: "quote", Required: true, Max: wsMaxQuote})
		c.Fields.Add(&core.TextField{Name: "blob", Required: true, Max: 40})
		c.Fields.Add(&core.TextField{Name: "by", Required: true, Max: wsMaxBy})
		c.Fields.Add(&core.TextField{Name: "resolution", Max: wsMaxClaim})
		c.Fields.Add(&core.TextField{Name: "context", Max: wsMaxContext})
		c.AddIndex("idx_ws_findings_project_seq", true, "project, seq", "")
		if e := txApp.Save(c); e != nil {
			return e
		}
	}
	if _, e := txApp.FindCollectionByNameOrId("ws_notes"); e != nil {
		c := core.NewBaseCollection("ws_notes")
		c.Fields.Add(&core.TextField{Name: "project", Required: true, Max: wsMaxName})
		c.Fields.Add(&core.NumberField{Name: "seq", Required: true, OnlyInt: true})
		c.Fields.Add(&core.TextField{Name: "text", Required: true, Max: wsMaxNote})
		c.Fields.Add(&core.TextField{Name: "by", Required: true, Max: wsMaxBy})
		c.Fields.Add(&core.TextField{Name: "commit"})
		c.AddIndex("idx_ws_notes_project_seq", true, "project, seq", "")
		if e := txApp.Save(c); e != nil {
			return e
		}
	}
	if _, e := txApp.FindCollectionByNameOrId("ws_results"); e != nil {
		c := core.NewBaseCollection("ws_results")
		c.Fields.Add(&core.TextField{Name: "project", Required: true, Max: wsMaxName})
		c.Fields.Add(&core.TextField{Name: "command", Required: true, Max: wsMaxCommand})
		c.Fields.Add(&core.TextField{Name: "commit", Required: true, Max: 64})
		c.Fields.Add(&core.TextField{Name: "env", Required: true, Max: wsMaxEnv + 64})
		c.Fields.Add(&core.TextField{Name: "outcome", Required: true, Max: 8})
		c.Fields.Add(&core.TextField{Name: "summary", Required: true, Max: wsMaxSummary})
		c.Fields.Add(&core.TextField{Name: "by", Required: true, Max: wsMaxBy})
		c.Fields.Add(&core.TextField{Name: "ignored", Max: 64})
		c.AddIndex("idx_ws_results_key", true, "project, command, commit, env, ignored", "")
		if e := txApp.Save(c); e != nil {
			return e
		}
	}
	// Added after the first four, and created on its own, so a database made before it existed gains it.
	if _, e := txApp.FindCollectionByNameOrId("ws_summaries"); e != nil {
		c := core.NewBaseCollection("ws_summaries")
		c.Fields.Add(&core.TextField{Name: "project", Required: true, Max: wsMaxName})
		c.Fields.Add(&core.TextField{Name: "path", Required: true, Max: 4096})
		c.Fields.Add(&core.TextField{Name: "text", Required: true, Max: wsMaxFileSummary})
		c.Fields.Add(&core.TextField{Name: "blob", Required: true, Max: 40})
		c.Fields.Add(&core.NumberField{Name: "lines", OnlyInt: true})
		c.Fields.Add(&core.TextField{Name: "by", Required: true, Max: wsMaxBy})
		c.AddIndex("idx_ws_summaries_path", true, "project, path", "")
		if e := txApp.Save(c); e != nil {
			return e
		}
	}
	return nil
}

func (s *AgentBaseMCPServer) projectRoot(app core.App, project string) (string, error) {
	if _, e := app.FindCollectionByNameOrId("ws_projects"); e != nil {
		return "", fmt.Errorf("no project called %q: register it first with ws_register_project", project)
	}
	rec, err := app.FindFirstRecordByFilter("ws_projects", "name = {:n}", dbx.Params{"n": project})
	if err != nil || rec == nil {
		return "", fmt.Errorf("no project called %q: register it first with ws_register_project", project)
	}
	return rec.GetString("root"), nil
}

// resolveInRoot turns a project-relative path into an absolute one inside root.
// Nothing below root is followed: a link anywhere on the way is refused.
// What lies above root (say, root reached through a junction) is the
// registering person's choice and is not looked at.
func resolveInRoot(root, rel string) (abs, clean string, err error) {
	rel = strings.TrimSpace(rel)
	if rel == "" {
		return "", "", errors.New("path must not be empty")
	}
	if filepath.IsAbs(rel) || filepath.VolumeName(rel) != "" || strings.HasPrefix(rel, "/") || strings.HasPrefix(rel, `\`) {
		return "", "", fmt.Errorf("path %q must be relative to the project root", rel)
	}
	clean = filepath.Clean(filepath.FromSlash(rel))
	if clean == ".." || strings.HasPrefix(clean, ".."+string(filepath.Separator)) {
		return "", "", fmt.Errorf("path %q leaves the project root", rel)
	}
	// No part of the path may be a link. Since Go 1.23, EvalSymlinks does not
	// resolve a Windows junction while os.Open goes straight through one, so
	// each component is Lstat'ed and, where needed, its reparse tag read
	// (isLink). A cloud placeholder is a reparse point too, and is a file.
	walked := root
	for _, part := range strings.Split(clean, string(filepath.Separator)) {
		walked = filepath.Join(walked, part)
		info, err := os.Lstat(walked)
		if err != nil {
			return "", "", err
		}
		if isLink(walked, info) {
			return "", "", fmt.Errorf("path %q goes through a link (%s); links are not followed", rel, filepath.ToSlash(strings.TrimPrefix(walked, root+string(filepath.Separator))))
		}
	}
	joined := filepath.Join(root, clean)
	inside, err := filepath.Rel(root, joined)
	if err != nil || inside == ".." || strings.HasPrefix(inside, ".."+string(filepath.Separator)) || filepath.IsAbs(inside) {
		return "", "", fmt.Errorf("path %q resolves outside the project root", rel)
	}
	return joined, filepath.ToSlash(clean), nil
}

func readBounded(abs string) ([]byte, error) {
	f, err := os.Open(abs)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	info, err := f.Stat()
	if err != nil {
		return nil, err
	}
	if info.IsDir() {
		return nil, errors.New("is a directory, not a file")
	}
	data, err := io.ReadAll(io.LimitReader(f, wsMaxFileBytes+1))
	if err != nil {
		return nil, err
	}
	if len(data) > wsMaxFileBytes {
		return nil, fmt.Errorf("is over the %d byte limit", wsMaxFileBytes)
	}
	return data, nil
}

// gitState returns HEAD and whether the working tree has any change git reports.
var gitState = func(root string) (commit string, clean bool, err error) {
	out, err := exec.Command("git", "-C", root, "rev-parse", "--verify", "HEAD").Output()
	if err != nil {
		return "", false, errors.New("the project root is not a git repository with a commit")
	}
	commit = strings.TrimSpace(string(out))
	st, err := exec.Command("git", "-C", root, "status", "--porcelain", "--untracked-files=normal").Output()
	if err != nil {
		return commit, false, errors.New("git status failed in the project root")
	}
	return commit, strings.TrimSpace(string(st)) == "", nil
}

// ignoredDigest names what git ignores in the working tree, by path only, with
// ignored folders listed once (--directory). Tests can read ignored data (a
// downloaded corpus, a built index), and a fresh clone does not have it, so a
// result recorded with it present is not shown where it is absent. Contents
// are not hashed: a changed ignored file with the same name goes unnoticed.
var ignoredDigest = func(root string) (string, error) {
	out, err := exec.Command("git", "-C", root, "ls-files", "--others", "--ignored", "--exclude-standard", "--directory").Output()
	if err != nil {
		return "", errors.New("git ls-files failed in the project root")
	}
	names := strings.Fields(strings.ReplaceAll(string(out), "\r", ""))
	sort.Strings(names)
	sum := sha256.Sum256([]byte(strings.Join(names, "\n")))
	return hex.EncodeToString(sum[:8]), nil
}

func nextSeq(txApp core.App, collection, project string) (int, error) {
	recs, err := txApp.FindRecordsByFilter(collection, "project = {:p}", "-seq", 1, 0, dbx.Params{"p": project})
	if err != nil {
		return 0, err
	}
	if len(recs) == 0 {
		return 1, nil
	}
	return recs[0].GetInt("seq") + 1, nil
}

func (s *AgentBaseMCPServer) doRegisterProject(name, root string) (string, error) {
	name, err := boundedName("name", name)
	if err != nil {
		return "", err
	}
	root = strings.TrimSpace(root)
	if root == "" || !filepath.IsAbs(root) {
		return "", fmt.Errorf("root %q must be an absolute path", root)
	}
	// Not EvalSymlinks: since Go 1.23 it fails on a path through a junction,
	// and a root reached through one is a legitimate choice.
	real := filepath.Clean(root)
	if info, err := os.Stat(real); err != nil || !info.IsDir() {
		return "", fmt.Errorf("root %q is not a directory", root)
	}
	var note string
	err = s.app.RunInTransaction(func(txApp core.App) error {
		if err := ensureWorkspace(txApp); err != nil {
			return err
		}
		c, err := txApp.FindCollectionByNameOrId("ws_projects")
		if err != nil {
			return err
		}
		if rec, e := txApp.FindFirstRecordByFilter("ws_projects", "name = {:n}", dbx.Params{"n": name}); e == nil && rec != nil {
			if rec.GetString("root") == real {
				note = "already registered with this root"
				return nil
			}
			return fmt.Errorf("project %q is already registered with a different root; a project's root is never changed", name)
		}
		r := core.NewRecord(c)
		r.Set("name", name)
		r.Set("root", real)
		return txApp.Save(r)
	})
	if err != nil {
		return "", err
	}
	if note != "" {
		return fmt.Sprintf("OK: project %q %s.", name, note), nil
	}
	return fmt.Sprintf("OK: project %q registered.", name), nil
}

func (s *AgentBaseMCPServer) doRecord(project, kind, claim, path string, lineStart, lineEnd int, quote, by string) (string, error) {
	project, err := boundedName("project", project)
	if err != nil {
		return "", err
	}
	kind = strings.TrimSpace(kind)
	if !wsKinds[kind] {
		return "", fmt.Errorf("kind %q must be finding or unknown", kind)
	}
	if claim, err = boundedText("claim", claim, wsMaxClaim); err != nil {
		return "", err
	}
	if quote, err = boundedText("quote", normalizeQuote(quote), wsMaxQuote); err != nil {
		return "", err
	}
	if by, err = byLabel(by); err != nil {
		return "", err
	}
	if lineStart < 1 || lineEnd < lineStart {
		return "", fmt.Errorf("lines %d-%d are not a range: line_start must be at least 1 and line_end at least line_start", lineStart, lineEnd)
	}
	root, err := s.projectRoot(s.app, project)
	if err != nil {
		return "", err
	}
	abs, clean, err := resolveInRoot(root, path)
	if err != nil {
		return "", err
	}
	content, err := readBounded(abs)
	if err != nil {
		return "", fmt.Errorf("%s: %v", clean, err)
	}
	lines := splitLines(content)
	if lineEnd > len(lines) {
		return "", fmt.Errorf("%s has %d lines, so lines %d-%d do not exist", clean, len(lines), lineStart, lineEnd)
	}
	if !strings.Contains(strings.Join(lines[lineStart-1:lineEnd], "\n"), quote) {
		if a, b, _ := findQuote(lines, quote, lineStart); a > 0 {
			return "", fmt.Errorf("the quote is not in %s lines %d-%d; it is at lines %d-%d", clean, lineStart, lineEnd, a, b)
		}
		return "", fmt.Errorf("the quote is not in %s at all; a finding must quote the words it rests on", clean)
	}
	blob := gitBlobHash(content)
	// The whole evidence lines, kept so that a later recall can find where they
	// moved even when the quote alone occurs in several places.
	context := strings.Join(lines[lineStart-1:lineEnd], "\n")
	if len(context) > wsMaxContext {
		context = ""
	}

	var seq int
	err = s.app.RunInTransaction(func(txApp core.App) error {
		if err := ensureWorkspace(txApp); err != nil {
			return err
		}
		c, err := txApp.FindCollectionByNameOrId("ws_findings")
		if err != nil {
			return err
		}
		if seq, err = nextSeq(txApp, "ws_findings", project); err != nil {
			return err
		}
		r := core.NewRecord(c)
		r.Set("project", project)
		r.Set("seq", seq)
		r.Set("kind", kind)
		r.Set("claim", claim)
		r.Set("path", clean)
		r.Set("line_start", lineStart)
		r.Set("line_end", lineEnd)
		r.Set("quote", quote)
		r.Set("blob", blob)
		r.Set("context", context)
		r.Set("by", by)
		return txApp.Save(r)
	})
	if err != nil {
		return "", err
	}
	return fmt.Sprintf("OK: %s #%d recorded against %s lines %d-%d (blob %s).", kind, seq, clean, lineStart, lineEnd, blob[:12]), nil
}

// doSummarize stores what a file is, for a later session to read instead of the file. It is tied to the file's
// blob hash: while the file is unchanged the summary is FRESH; once it changes the summary is STALE and the
// file must be read again. One summary per file: a new one replaces the old, since it describes the file as
// it is now. FRESH means the file is the one that was summarized, never that the summary is right.
func (s *AgentBaseMCPServer) doSummarize(project, path, text, by string) (string, error) {
	project, err := boundedName("project", project)
	if err != nil {
		return "", err
	}
	if text, err = boundedText("summary", text, wsMaxFileSummary); err != nil {
		return "", err
	}
	if by, err = byLabel(by); err != nil {
		return "", err
	}
	root, err := s.projectRoot(s.app, project)
	if err != nil {
		return "", err
	}
	abs, clean, err := resolveInRoot(root, path)
	if err != nil {
		return "", err
	}
	content, err := readBounded(abs)
	if err != nil {
		return "", fmt.Errorf("%s: %v", clean, err)
	}
	if len(text) >= len(content) {
		return "", fmt.Errorf("the summary is %d bytes and %s is %d: a summary must be shorter than the file it saves reading", len(text), clean, len(content))
	}
	// Lines as an editor counts them: a final newline ends the last line, it does not start another.
	blob, lines := gitBlobHash(content), strings.Count(string(content), "\n")
	if len(content) > 0 && content[len(content)-1] != '\n' {
		lines++
	}
	replaced := false
	err = s.app.RunInTransaction(func(txApp core.App) error {
		if err := ensureWorkspace(txApp); err != nil {
			return err
		}
		c, err := txApp.FindCollectionByNameOrId("ws_summaries")
		if err != nil {
			return err
		}
		r, err := txApp.FindFirstRecordByFilter("ws_summaries", "project = {:p} && path = {:f}", dbx.Params{"p": project, "f": clean})
		if err != nil {
			r = core.NewRecord(c)
			r.Set("project", project)
			r.Set("path", clean)
		} else {
			replaced = true
		}
		r.Set("text", text)
		r.Set("blob", blob)
		r.Set("lines", lines)
		r.Set("by", by)
		return txApp.Save(r)
	})
	if err != nil {
		return "", err
	}
	verb := "stored"
	if replaced {
		verb = "replaced"
	}
	return fmt.Sprintf("OK: summary of %s %s (blob %s, %d lines). FRESH while the file is unchanged.", clean, verb, blob[:12], lines), nil
}

type summarized struct {
	Path    string `json:"path"`
	State   string `json:"state"`
	Lines   int    `json:"lines"`
	Summary string `json:"summary"`
	By      string `json:"by"`
}

// summaryRows returns the summaries under a path prefix, each checked against its file now.
func (s *AgentBaseMCPServer) summaryRows(project, root, prefix string, files map[string]*fileView) ([]summarized, error) {
	out := []summarized{}
	if _, e := s.app.FindCollectionByNameOrId("ws_summaries"); e != nil {
		return out, nil
	}
	recs, err := s.app.FindRecordsByFilter("ws_summaries", "project = {:p}", "path", 0, 0, dbx.Params{"p": project})
	if err != nil {
		return nil, err
	}
	prefix = filepath.ToSlash(strings.TrimSpace(prefix))
	for _, r := range recs {
		if prefix != "" && !strings.HasPrefix(r.GetString("path"), prefix) {
			continue
		}
		v := viewFile(root, r.GetString("path"), files)
		state := stateFresh
		switch {
		case v.gone:
			state = stateGone
		case v.blob != r.GetString("blob"):
			state = stateStale
		}
		out = append(out, summarized{Path: r.GetString("path"), State: state, Lines: r.GetInt("lines"),
			Summary: r.GetString("text"), By: r.GetString("by")})
	}
	return out, nil
}

type recalled struct {
	ID         int    `json:"id"`
	Kind       string `json:"kind"`
	Claim      string `json:"claim"`
	Path       string `json:"path"`
	Lines      string `json:"lines"`
	State      string `json:"state"`
	Now        string `json:"now_at,omitempty"`
	Places     int    `json:"quote_occurs,omitempty"` // set when the quote is in more than one place now
	Open       bool   `json:"open,omitempty"`
	Resolution string `json:"resolution,omitempty"`
	By         string `json:"by"`
}

// fileView is one file as recall sees it, read and hashed once per recall
// however many findings point at it.
type fileView struct {
	gone  bool
	blob  string
	lines []string
}

// wsReadFile is readBounded, as a variable so a test can count the reads.
var wsReadFile = readBounded

func viewFile(root, path string, cache map[string]*fileView) *fileView {
	if v, ok := cache[path]; ok {
		return v
	}
	v := &fileView{gone: true}
	if abs, _, err := resolveInRoot(root, path); err == nil {
		if content, err := wsReadFile(abs); err == nil {
			v = &fileView{blob: gitBlobHash(content), lines: splitLines(content)}
		}
	}
	cache[path] = v
	return v
}

// anchorState checks one finding's evidence against the file as it is now.
// INTACT: the file changed, but the evidence lines are exactly as recorded, at
// the same lines. For MOVED, now is the occurrence nearest the original line,
// and places is how many occurrences there are when there is more than one,
// so a reader knows the relocation is a guess among several.
func anchorState(v *fileView, rec *core.Record) (state, now string, places int) {
	if v.gone {
		return stateGone, "", 0
	}
	if v.blob == rec.GetString("blob") {
		return stateFresh, "", 0
	}
	lines := v.lines
	a0, b0 := rec.GetInt("line_start"), rec.GetInt("line_end")
	if ctx := rec.GetString("context"); ctx != "" && b0 <= len(lines) && strings.Join(lines[a0-1:b0], "\n") == ctx {
		return stateIntact, "", 0
	}
	if ctx := rec.GetString("context"); ctx != "" {
		if a, b, n := findQuote(lines, ctx, rec.GetInt("line_start")); a > 0 {
			if n == 1 {
				n = 0
			}
			return stateMoved, fmt.Sprintf("%d-%d", a, b), n
		}
	}
	if a, b, n := findQuote(lines, rec.GetString("quote"), rec.GetInt("line_start")); a > 0 {
		if n == 1 {
			n = 0
		}
		return stateMoved, fmt.Sprintf("%d-%d", a, b), n
	}
	return stateBroken, "", 0
}

func (s *AgentBaseMCPServer) recallRows(project, prefix string, openOnly bool, limit int, files map[string]*fileView) ([]recalled, map[string]int, error) {
	root, err := s.projectRoot(s.app, project)
	if err != nil {
		return nil, nil, err
	}
	counts := map[string]int{stateFresh: 0, stateIntact: 0, stateMoved: 0, stateBroken: 0, stateGone: 0}
	if _, e := s.app.FindCollectionByNameOrId("ws_findings"); e != nil {
		return []recalled{}, counts, nil
	}
	recs, err := s.app.FindRecordsByFilter("ws_findings", "project = {:p}", "seq", 0, 0, dbx.Params{"p": project})
	if err != nil {
		return nil, nil, err
	}
	prefix = filepath.ToSlash(strings.TrimSpace(prefix))
	out := []recalled{}
	for _, r := range recs {
		if prefix != "" && !strings.HasPrefix(r.GetString("path"), prefix) {
			continue
		}
		open := r.GetString("kind") == "unknown" && r.GetString("resolution") == ""
		state, now, places := anchorState(viewFile(root, r.GetString("path"), files), r)
		counts[state]++
		if openOnly && !open {
			continue
		}
		if limit > 0 && len(out) >= limit {
			continue
		}
		out = append(out, recalled{
			ID: r.GetInt("seq"), Kind: r.GetString("kind"), Claim: r.GetString("claim"),
			Path: r.GetString("path"), Lines: fmt.Sprintf("%d-%d", r.GetInt("line_start"), r.GetInt("line_end")),
			State: state, Now: now, Places: places, Open: open, Resolution: r.GetString("resolution"), By: r.GetString("by"),
		})
	}
	return out, counts, nil
}

func (s *AgentBaseMCPServer) doRecall(project, prefix string) (string, error) {
	project, err := boundedName("project", project)
	if err != nil {
		return "", err
	}
	root, err := s.projectRoot(s.app, project)
	if err != nil {
		return "", err
	}
	files := map[string]*fileView{}
	rows, _, err := s.recallRows(project, prefix, false, 0, files)
	if err != nil {
		return "", err
	}
	sums, err := s.summaryRows(project, root, prefix, files)
	if err != nil {
		return "", err
	}
	b, _ := json.Marshal(recallOut{Findings: rows, Summaries: sums})
	return string(b), nil
}

type recallOut struct {
	Findings  []recalled   `json:"findings"`
	Summaries []summarized `json:"summaries"`
}

func (s *AgentBaseMCPServer) doResolve(project string, id int, resolution, by string) (string, error) {
	project, err := boundedName("project", project)
	if err != nil {
		return "", err
	}
	if resolution, err = boundedText("resolution", resolution, wsMaxClaim); err != nil {
		return "", err
	}
	if by, err = byLabel(by); err != nil {
		return "", err
	}
	if _, err := s.projectRoot(s.app, project); err != nil {
		return "", err
	}
	err = s.app.RunInTransaction(func(txApp core.App) error {
		if err := ensureWorkspace(txApp); err != nil {
			return err
		}
		rec, err := txApp.FindFirstRecordByFilter("ws_findings", "project = {:p} && seq = {:s}", dbx.Params{"p": project, "s": id})
		if err != nil || rec == nil {
			return fmt.Errorf("no finding #%d in project %q", id, project)
		}
		if rec.GetString("kind") != "unknown" {
			return fmt.Errorf("#%d is a finding, not an unknown; only an unknown is resolved", id)
		}
		if rec.GetString("resolution") != "" {
			return fmt.Errorf("unknown #%d is already resolved; a resolution is never written over", id)
		}
		rec.Set("resolution", fmt.Sprintf("%s (by %s)", resolution, by))
		return txApp.Save(rec)
	})
	if err != nil {
		return "", err
	}
	return fmt.Sprintf("OK: unknown #%d resolved.", id), nil
}

func (s *AgentBaseMCPServer) doNote(project, text, by string) (string, error) {
	project, err := boundedName("project", project)
	if err != nil {
		return "", err
	}
	if text, err = boundedText("text", text, wsNoteLimit); err != nil {
		return "", err
	}
	if by, err = byLabel(by); err != nil {
		return "", err
	}
	root, err := s.projectRoot(s.app, project)
	if err != nil {
		return "", err
	}
	commit, _, _ := gitState(root)
	var seq int
	err = s.app.RunInTransaction(func(txApp core.App) error {
		if err := ensureWorkspace(txApp); err != nil {
			return err
		}
		c, err := txApp.FindCollectionByNameOrId("ws_notes")
		if err != nil {
			return err
		}
		if seq, err = nextSeq(txApp, "ws_notes", project); err != nil {
			return err
		}
		r := core.NewRecord(c)
		r.Set("project", project)
		r.Set("seq", seq)
		r.Set("text", text)
		r.Set("by", by)
		r.Set("commit", commit)
		return txApp.Save(r)
	})
	if err != nil {
		return "", err
	}
	return fmt.Sprintf("OK: note #%d left.", seq), nil
}

func resultEnv(env string) (string, error) {
	env = strings.TrimSpace(env)
	if len(env) > wsMaxEnv {
		return "", fmt.Errorf("env is %d bytes, over the limit of %d", len(env), wsMaxEnv)
	}
	host := runtime.GOOS + "/" + runtime.GOARCH
	if env == "" {
		return host, nil
	}
	return host + " " + env, nil
}

func (s *AgentBaseMCPServer) doResult(project, command, outcome, summary, env, by, testedAt string) (string, error) {
	project, err := boundedName("project", project)
	if err != nil {
		return "", err
	}
	if command, err = boundedText("command", strings.TrimSpace(command), wsMaxCommand); err != nil {
		return "", err
	}
	outcome = strings.TrimSpace(outcome)
	if !wsOutcomes[outcome] {
		return "", fmt.Errorf("outcome %q must be pass or fail", outcome)
	}
	if summary, err = boundedText("summary", summary, wsMaxSummary); err != nil {
		return "", err
	}
	if env, err = resultEnv(env); err != nil {
		return "", err
	}
	if by, err = byLabel(by); err != nil {
		return "", err
	}
	root, err := s.projectRoot(s.app, project)
	if err != nil {
		return "", err
	}
	commit, clean, err := gitState(root)
	if err != nil {
		return "", err
	}
	if !clean {
		return "", errors.New("the working tree has uncommitted or untracked changes, so no commit names what was tested; commit or stash first")
	}
	// The commit the caller says it ran against must still be HEAD. This catches a
	// commit made between running and recording. It cannot catch a run on a dirty
	// tree that was cleaned before recording: that the tree was clean when the
	// command ran is the caller's word, and the tool description says so.
	testedAt = strings.TrimSpace(testedAt)
	if testedAt == "" {
		return "", errors.New("tested_at must be the commit you ran against (git rev-parse HEAD before running)")
	}
	if testedAt != commit {
		return "", fmt.Errorf("tested_at %s is not HEAD %s: the commit changed since the command ran, so this result does not describe HEAD", testedAt, commit[:12])
	}
	ignored, err := ignoredDigest(root)
	if err != nil {
		return "", err
	}
	replaced := false
	err = s.app.RunInTransaction(func(txApp core.App) error {
		if err := ensureWorkspace(txApp); err != nil {
			return err
		}
		c, err := txApp.FindCollectionByNameOrId("ws_results")
		if err != nil {
			return err
		}
		r, e := txApp.FindFirstRecordByFilter("ws_results",
			"project = {:p} && command = {:c} && commit = {:h} && env = {:e} && ignored = {:i}",
			dbx.Params{"p": project, "c": command, "h": commit, "e": env, "i": ignored})
		if e == nil && r != nil {
			replaced = true
		} else {
			r = core.NewRecord(c)
			r.Set("project", project)
			r.Set("command", command)
			r.Set("commit", commit)
			r.Set("env", env)
			r.Set("ignored", ignored)
		}
		r.Set("outcome", outcome)
		r.Set("summary", summary)
		r.Set("by", by)
		return txApp.Save(r)
	})
	if err != nil {
		return "", err
	}
	verb := "recorded"
	if replaced {
		verb = "replaced the earlier result"
	}
	return fmt.Sprintf("OK: %s %s at %s on %s, %s.", command, outcome, commit[:12], env, verb), nil
}

type briefResult struct {
	Command string `json:"command"`
	Env     string `json:"env"`
	Outcome string `json:"outcome"`
	Summary string `json:"summary"`
	By      string `json:"by"`
}

type briefNote struct {
	ID     int    `json:"id"`
	Text   string `json:"text"`
	By     string `json:"by"`
	Commit string `json:"at_commit,omitempty"`
}

// briefItem is a finding as the brief shows it: where it is, what state its evidence is in, and the head of its
// claim. The whole claim is one ws_recall (path_prefix = path) away.
type briefItem struct {
	ID    int    `json:"id"`
	Path  string `json:"path"`
	Lines string `json:"lines"`
	State string `json:"state"`
	Now   string `json:"now_at,omitempty"`
	Head  string `json:"head"`
	More  bool   `json:"more,omitempty"` // the claim goes on past the head
}

type briefSummaries struct {
	Fresh int      `json:"fresh"`
	Stale []string `json:"stale"` // the file changed since it was summarized: read it again
	Gone  []string `json:"gone"`
}

type brief struct {
	Project        string         `json:"project"`
	Commit         string         `json:"commit,omitempty"`
	Clean          bool           `json:"clean"`
	Git            string         `json:"git,omitempty"`
	LastNote       *briefNote     `json:"last_note"`
	Notes          int            `json:"notes"`
	CommitsSince   *int           `json:"commits_since_last_note,omitempty"`
	OpenUnknowns   []briefItem    `json:"open_unknowns"`
	NeedsAttention []briefItem    `json:"needs_attention"` // MOVED, BROKEN or GONE, open or not resolved
	Anchors        map[string]int `json:"anchors"`
	Summaries      briefSummaries `json:"summaries"`
	Results        []briefResult  `json:"results_at_this_commit"`
	Caveat         string         `json:"caveat"`
}

// head is the first sentence of a claim, cut at wsHeadMax bytes on a rune boundary.
func head(claim string) (string, bool) {
	h := claim
	for _, sep := range []string{". ", "? ", "! ", "\n"} {
		if i := strings.Index(h, sep); i >= 0 {
			h = h[:i+1]
		}
	}
	h = strings.TrimSpace(h)
	if len(h) > wsHeadMax {
		cut := wsHeadMax
		for cut > 0 && !utf8.RuneStart(h[cut]) {
			cut--
		}
		h = strings.TrimSpace(h[:cut])
	}
	return h, h != strings.TrimSpace(claim)
}

func itemOf(r recalled) briefItem {
	h, more := head(r.Claim)
	return briefItem{ID: r.ID, Path: r.Path, Lines: r.Lines, State: r.State, Now: r.Now, Head: h, More: more}
}

// commitsSince counts the commits from one commit to HEAD, for "how much has changed since the last note".
var commitsSince = func(root, from string) (int, error) {
	out, err := exec.Command("git", "-C", root, "rev-list", "--count", from+"..HEAD").Output()
	if err != nil {
		return 0, err
	}
	var n int
	_, err = fmt.Sscanf(strings.TrimSpace(string(out)), "%d", &n)
	return n, err
}

func (s *AgentBaseMCPServer) doBrief(project string) (string, error) {
	project, err := boundedName("project", project)
	if err != nil {
		return "", err
	}
	root, err := s.projectRoot(s.app, project)
	if err != nil {
		return "", err
	}
	b := brief{Project: project, OpenUnknowns: []briefItem{}, NeedsAttention: []briefItem{}, Results: []briefResult{},
		Summaries: briefSummaries{Stale: []string{}, Gone: []string{}},
		Caveat:    "FRESH and INTACT mean a finding's evidence is unchanged, not that the claim is right. A result is the report of whoever ran it: shown only at the commit it names and with the same ignored files present, but that the tree was clean while it ran is their word."}
	commit, clean, gerr := gitState(root)
	if gerr != nil {
		b.Git = gerr.Error()
	} else {
		b.Commit, b.Clean = commit, clean
	}
	if _, e := s.app.FindCollectionByNameOrId("ws_notes"); e == nil {
		notes, err := s.app.FindRecordsByFilter("ws_notes", "project = {:p}", "-seq", 0, 0, dbx.Params{"p": project})
		if err != nil {
			return "", err
		}
		b.Notes = len(notes)
		if len(notes) > 0 {
			n := notes[0]
			b.LastNote = &briefNote{ID: n.GetInt("seq"), Text: n.GetString("text"), By: n.GetString("by"), Commit: n.GetString("commit")}
			if c := b.LastNote.Commit; c != "" && b.Commit != "" {
				if k, err := commitsSince(root, c); err == nil {
					b.CommitsSince = &k
				}
			}
		}
	}
	files := map[string]*fileView{}
	rows, counts, err := s.recallRows(project, "", false, 0, files)
	if err != nil {
		return "", err
	}
	b.Anchors = counts
	for _, r := range rows {
		if r.Open && len(b.OpenUnknowns) < wsBriefList {
			b.OpenUnknowns = append(b.OpenUnknowns, itemOf(r))
		}
		changed := r.State == stateMoved || r.State == stateBroken || r.State == stateGone
		if changed && r.Resolution == "" && len(b.NeedsAttention) < wsBriefList {
			b.NeedsAttention = append(b.NeedsAttention, itemOf(r))
		}
	}
	sums, err := s.summaryRows(project, root, "", files)
	if err != nil {
		return "", err
	}
	for _, x := range sums {
		switch x.State {
		case stateFresh:
			b.Summaries.Fresh++
		case stateStale:
			if len(b.Summaries.Stale) < wsBriefList {
				b.Summaries.Stale = append(b.Summaries.Stale, x.Path)
			}
		case stateGone:
			if len(b.Summaries.Gone) < wsBriefList {
				b.Summaries.Gone = append(b.Summaries.Gone, x.Path)
			}
		}
	}
	if b.Commit != "" && b.Clean {
		ignored, ierr := ignoredDigest(root)
		if _, e := s.app.FindCollectionByNameOrId("ws_results"); e == nil && ierr == nil {
			res, err := s.app.FindRecordsByFilter("ws_results", "project = {:p} && commit = {:h} && ignored = {:i}", "command", wsBriefList, 0,
				dbx.Params{"p": project, "h": b.Commit, "i": ignored})
			if err != nil {
				return "", err
			}
			for _, r := range res {
				b.Results = append(b.Results, briefResult{Command: r.GetString("command"), Env: r.GetString("env"),
					Outcome: r.GetString("outcome"), Summary: r.GetString("summary"), By: r.GetString("by")})
			}
		}
	}
	out, _ := json.Marshal(b)
	return string(out), nil
}
