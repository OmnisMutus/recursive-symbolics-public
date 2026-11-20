package apis

import (
	"context"
	"fmt"
	"math"
	"path/filepath"

	"github.com/mark3labs/mcp-go/mcp"
)

// wsTools are the workspace tool names, in the order they are registered.
var wsTools = []string{"ws_register_project", "ws_record", "ws_recall", "ws_resolve", "ws_note", "ws_result", "ws_brief", "ws_summarize"}

// wholeArg reads a required whole number. mcp-go's RequireInt truncates 3.7 to 3, which would quietly
// move an anchor, so a fraction is refused here instead.
func wholeArg(req mcp.CallToolRequest, key string) (int, error) {
	v, err := req.RequireFloat(key)
	if err != nil {
		return 0, err
	}
	if math.IsNaN(v) || math.IsInf(v, 0) || v != math.Trunc(v) || v < 0 || v > 1e9 {
		return 0, fmt.Errorf("%s must be a whole number from 0 to 1000000000, got %v", key, v)
	}
	return int(v), nil
}

func errResult(err error) (*mcp.CallToolResult, error) {
	return mcp.NewToolResultError(err.Error()), nil
}

// WorkspaceOnly removes every tool that is not a workspace tool. A session that only keeps its own work
// does not need the ledger, policy, hook or identity tools, and every tool offered costs each session
// the tokens of its description. Call it after EnableWorkspace.
func (s *AgentBaseMCPServer) WorkspaceOnly() {
	keep := map[string]bool{}
	for _, n := range wsTools {
		keep[n] = true
	}
	var drop []string
	for name := range s.mcpServer.ListTools() {
		if !keep[name] {
			drop = append(drop, name)
		}
	}
	s.mcpServer.DeleteTools(drop...)
}

// EnableWorkspace registers the workspace tools. They read files under a registered project root, so
// main.go calls this only in local stdio mode; the remote SSE endpoint never has them.
func (s *AgentBaseMCPServer) EnableWorkspace() {
	if s.usage == nil {
		s.usage = newUsage(filepath.Join(s.app.DataDir(), "ws_usage.jsonl"))
	}
	s.addWS(mcp.NewTool("ws_register_project",
		mcp.WithDescription("Register a project: a name and the absolute path of its root folder. Findings are anchored to files under that root. A project's root is never changed once registered."),
		mcp.WithString("name", mcp.Required(), mcp.Description("Short name, e.g. 'agentbase'")),
		mcp.WithString("root", mcp.Required(), mcp.Description("Absolute path of the project's root folder")),
	), func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		name, err := req.RequireString("name")
		if err != nil {
			return errResult(err)
		}
		root, err := req.RequireString("root")
		if err != nil {
			return errResult(err)
		}
		return toolText(s.doRegisterProject(name, root))
	})

	s.addWS(mcp.NewTool("ws_record",
		mcp.WithDescription("Record a finding, or an open question (kind 'unknown'), with its evidence: a file under the project root, a line range, and words quoted exactly from those lines. Refused if the quote is not there. The file's git blob hash is stored, so a later recall says whether the evidence has changed."),
		mcp.WithString("project", mcp.Required()),
		mcp.WithString("kind", mcp.Required(), mcp.Description("'finding' or 'unknown'")),
		mcp.WithString("claim", mcp.Required(), mcp.Description("What you concluded, or the open question")),
		mcp.WithString("path", mcp.Required(), mcp.Description("File path relative to the project root, with / separators")),
		mcp.WithNumber("line_start", mcp.Required(), mcp.Description("First line of the evidence, from 1")),
		mcp.WithNumber("line_end", mcp.Required(), mcp.Description("Last line of the evidence")),
		mcp.WithString("quote", mcp.Required(), mcp.Description("Words copied exactly from those lines")),
		mcp.WithString("by", mcp.Description("Who is recording, e.g. 'claude-code'. Defaults to 'agent'.")),
	), func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		vals := map[string]string{}
		for _, k := range []string{"project", "kind", "claim", "path", "quote"} {
			v, err := req.RequireString(k)
			if err != nil {
				return errResult(err)
			}
			vals[k] = v
		}
		a, err := wholeArg(req, "line_start")
		if err != nil {
			return errResult(err)
		}
		b, err := wholeArg(req, "line_end")
		if err != nil {
			return errResult(err)
		}
		return toolText(s.doRecord(vals["project"], vals["kind"], vals["claim"], vals["path"], a, b, vals["quote"], req.GetString("by", "")))
	})

	s.addWS(mcp.NewTool("ws_recall", append([]mcp.ToolOption{
		mcp.WithDescription("Findings and unknowns for a project, each with the state of its evidence now: FRESH (file unchanged), INTACT (file changed elsewhere, evidence lines unchanged in place), MOVED (file changed, quote still there, now_at gives the lines), BROKEN (quote gone), GONE (file gone). Also the file summaries: FRESH (read it instead of the file) or STALE (the file changed: read the file). FRESH means unchanged, not right."),
		mcp.WithString("project", mcp.Required()),
		mcp.WithString("path_prefix", mcp.Description("Only findings and summaries whose path starts with this")),
	}, readOnlyHints("Recall Findings")...)...,
	), func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		p, err := req.RequireString("project")
		if err != nil {
			return errResult(err)
		}
		return toolText(s.doRecall(p, req.GetString("path_prefix", "")))
	})

	s.addWS(mcp.NewTool("ws_resolve",
		mcp.WithDescription("Close an open unknown with what was found. The question is kept; the resolution is added and never written over."),
		mcp.WithString("project", mcp.Required()),
		mcp.WithNumber("id", mcp.Required(), mcp.Description("The unknown's id from ws_recall or ws_brief")),
		mcp.WithString("resolution", mcp.Required()),
		mcp.WithString("by", mcp.Description("Who is resolving it")),
	), func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		p, err := req.RequireString("project")
		if err != nil {
			return errResult(err)
		}
		id, err := wholeArg(req, "id")
		if err != nil {
			return errResult(err)
		}
		r, err := req.RequireString("resolution")
		if err != nil {
			return errResult(err)
		}
		return toolText(s.doResolve(p, id, r, req.GetString("by", "")))
	})

	s.addWS(mcp.NewTool("ws_note",
		mcp.WithDescription("Leave a note for the next session: what is done, what is next, what not to trust. At most 4000 bytes: every ws_brief shows the latest one. Notes are only added, never changed."),
		mcp.WithString("project", mcp.Required()),
		mcp.WithString("text", mcp.Required()),
		mcp.WithString("by", mcp.Description("Who is leaving it")),
	), func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		p, err := req.RequireString("project")
		if err != nil {
			return errResult(err)
		}
		t, err := req.RequireString("text")
		if err != nil {
			return errResult(err)
		}
		return toolText(s.doNote(p, t, req.GetString("by", "")))
	})

	s.addWS(mcp.NewTool("ws_result",
		mcp.WithDescription("Record the outcome of a command (a test suite, a check). Refused unless tested_at is still HEAD and the working tree has no uncommitted or untracked change. Shown by ws_brief only at that commit and while the same files are gitignored-present. That the tree was clean while the command ran is your word: run on a clean tree."),
		mcp.WithString("project", mcp.Required()),
		mcp.WithString("command", mcp.Required(), mcp.Description("The command as run, e.g. 'go test -race ./apis/'")),
		mcp.WithString("outcome", mcp.Required(), mcp.Description("'pass' or 'fail'")),
		mcp.WithString("summary", mcp.Required(), mcp.Description("The counts as printed, e.g. '46 passed'")),
		mcp.WithString("env", mcp.Description("Anything about the environment that can change the outcome, e.g. 'go1.27.4 no-symlinks'. The OS and architecture are added.")),
		mcp.WithString("by", mcp.Description("Who ran it")),
		mcp.WithString("tested_at", mcp.Required(), mcp.Description("The commit you ran against: git rev-parse HEAD, taken before running")),
	), func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		vals := map[string]string{}
		for _, k := range []string{"project", "command", "outcome", "summary", "tested_at"} {
			v, err := req.RequireString(k)
			if err != nil {
				return errResult(err)
			}
			vals[k] = v
		}
		return toolText(s.doResult(vals["project"], vals["command"], vals["outcome"], vals["summary"],
			req.GetString("env", ""), req.GetString("by", ""), vals["tested_at"]))
	})

	s.addWS(mcp.NewTool("ws_brief", append([]mcp.ToolOption{
		mcp.WithDescription("Start here. One call: the commit, whether the tree is clean, the last note and commits since it, open unknowns and findings whose evidence moved or broke (each by id and the head of its claim; ws_recall gives all of it), counts by state, which file summaries went stale, and results at this commit."),
		mcp.WithString("project", mcp.Required()),
	}, readOnlyHints("Project Brief")...)...,
	), func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		p, err := req.RequireString("project")
		if err != nil {
			return errResult(err)
		}
		return toolText(s.doBrief(p))
	})

	s.addWS(mcp.NewTool("ws_summarize",
		mcp.WithDescription("Store what a file is (its purpose, main parts, where its guards are), so a later session reads the summary instead of the file. Tied to the file's blob hash: FRESH while unchanged, STALE once it changes. Must be shorter than the file; at most 2000 bytes. Replaces the file's earlier summary."),
		mcp.WithString("project", mcp.Required()),
		mcp.WithString("path", mcp.Required(), mcp.Description("File path relative to the project root, with / separators")),
		mcp.WithString("summary", mcp.Required()),
		mcp.WithString("by", mcp.Description("Who is summarizing")),
	), func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		vals := map[string]string{}
		for _, k := range []string{"project", "path", "summary"} {
			v, err := req.RequireString(k)
			if err != nil {
				return errResult(err)
			}
			vals[k] = v
		}
		return toolText(s.doSummarize(vals["project"], vals["path"], vals["summary"], req.GetString("by", "")))
	})
}
