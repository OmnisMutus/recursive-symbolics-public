package apis

// Usage log for the workspace tools: one JSON line per call in ws_usage.jsonl, in the data directory, with the
// tool, the project, the bytes the call sent and the bytes it returned, and a session id that is new each time
// the server starts (a local MCP server is started once per client session). No arguments or answers are
// written, only their sizes. It measures what the workspace costs a session, so whether it saves anything can
// be checked instead of assumed. It cannot see what a session reads by other means: compare its totals with the
// client's own token count for the session.

import (
	"bufio"
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"sort"
	"strings"
	"sync"
	"time"

	"github.com/mark3labs/mcp-go/mcp"
	"github.com/mark3labs/mcp-go/server"
)

type wsUsage struct {
	mu      sync.Mutex
	path    string
	session string
}

type usageLine struct {
	Time    string `json:"t"`
	Session string `json:"session"`
	Tool    string `json:"tool"`
	Project string `json:"project,omitempty"`
	In      int    `json:"in"`
	Out     int    `json:"out"`
	Error   bool   `json:"error,omitempty"`
}

func newUsage(path string) *wsUsage {
	b := make([]byte, 6)
	_, _ = rand.Read(b)
	return &wsUsage{path: path, session: hex.EncodeToString(b)}
}

// resultBytes is the size of what a call returned to the client: the text of every text item.
func resultBytes(res *mcp.CallToolResult) int {
	if res == nil {
		return 0
	}
	n := 0
	for _, c := range res.Content {
		switch t := c.(type) {
		case mcp.TextContent:
			n += len(t.Text)
		case *mcp.TextContent:
			n += len(t.Text)
		}
	}
	return n
}

// addWS registers a workspace tool with its calls logged. A failure to write the log never fails the call.
func (s *AgentBaseMCPServer) addWS(tool mcp.Tool, h server.ToolHandlerFunc) {
	name := tool.Name
	s.mcpServer.AddTool(tool, func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		res, err := h(ctx, req)
		if s.usage != nil {
			in, _ := json.Marshal(req.GetArguments())
			project := req.GetString("project", req.GetString("name", ""))
			s.usage.write(usageLine{Time: time.Now().UTC().Format(time.RFC3339), Session: s.usage.session, Tool: name,
				Project: project, In: len(in), Out: resultBytes(res), Error: err != nil || (res != nil && res.IsError)})
		}
		return res, err
	})
}

func (u *wsUsage) write(l usageLine) {
	b, err := json.Marshal(l)
	if err != nil {
		return
	}
	u.mu.Lock()
	defer u.mu.Unlock()
	f, err := os.OpenFile(u.path, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o600)
	if err != nil {
		return
	}
	defer f.Close()
	_, _ = f.Write(append(b, '\n'))
}

// UsageReport reads a usage log and gives, per session, the calls and the bytes in and out, with the bytes
// out per tool. Lines that are not usage lines are counted and skipped, never guessed at.
func UsageReport(path string) (string, error) {
	f, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer f.Close()
	type sess struct {
		first, last    string
		calls, in, out int
		byTool         map[string]int
	}
	sessions := map[string]*sess{}
	bad := 0
	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 64*1024), 1<<20)
	for sc.Scan() {
		var l usageLine
		if json.Unmarshal(sc.Bytes(), &l) != nil || l.Session == "" || l.Tool == "" {
			bad++
			continue
		}
		x := sessions[l.Session]
		if x == nil {
			x = &sess{first: l.Time, byTool: map[string]int{}}
			sessions[l.Session] = x
		}
		x.last = l.Time
		x.calls++
		x.in += l.In
		x.out += l.Out
		x.byTool[l.Tool] += l.Out
	}
	if err := sc.Err(); err != nil {
		return "", err
	}
	ids := make([]string, 0, len(sessions))
	for id := range sessions {
		ids = append(ids, id)
	}
	sort.Slice(ids, func(i, j int) bool { return sessions[ids[i]].first < sessions[ids[j]].first })
	var b strings.Builder
	if len(ids) == 0 {
		b.WriteString("No workspace calls recorded.\n")
	}
	for _, id := range ids {
		x := sessions[id]
		tools := make([]string, 0, len(x.byTool))
		for t := range x.byTool {
			tools = append(tools, t)
		}
		sort.Strings(tools)
		parts := make([]string, 0, len(tools))
		for _, t := range tools {
			parts = append(parts, fmt.Sprintf("%s %d", t, x.byTool[t]))
		}
		fmt.Fprintf(&b, "%s  %s to %s  %d calls  %d bytes in, %d bytes out  (out by tool: %s)\n",
			id, x.first, x.last, x.calls, x.in, x.out, strings.Join(parts, ", "))
	}
	if bad > 0 {
		fmt.Fprintf(&b, "%d lines were not usage lines and were skipped.\n", bad)
	}
	return b.String(), nil
}
