package main

import (
	"fmt"
	"log"
	"os"
	"path/filepath"
	"slices"

	"agentbase/apis"

	"github.com/pocketbase/pocketbase"
	"github.com/pocketbase/pocketbase/core"
)

func main() {
	app := pocketbase.New()

	// --- the workspace's usage, per session ---------------------------------------
	// Reads ws_usage.jsonl in the data directory and prints it; opens no database.
	if slices.Contains(os.Args, "--ws-usage") {
		rep, err := apis.UsageReport(filepath.Join(app.DataDir(), "ws_usage.jsonl"))
		if err != nil {
			log.Fatalf("no usage to report: %v", err)
		}
		fmt.Print(rep)
		return
	}

	// --- stdio MCP mode -------------------------------------------------------
	// Intercept BEFORE the cobra/serve machinery so we never spin up the web
	// server. We still Bootstrap() so the embedded DB and hooks are live.
	if slices.Contains(os.Args, "--mcp") {
		if err := app.Bootstrap(); err != nil {
			log.Fatalf("bootstrap failed: %v", err)
		}
		mcpServer := apis.NewAgentBaseMCPServer(app)
		// The workspace tools read files under registered project roots, so they
		// exist only here, in local stdio mode, never on the remote endpoint.
		mcpServer.EnableWorkspace()
		// --workspace-only offers the workspace tools alone, for sessions that do not use the ledger.
		if slices.Contains(os.Args, "--workspace-only") {
			mcpServer.WorkspaceOnly()
		}
		if err := mcpServer.ServeStdio(); err != nil {
			log.Fatalf("MCP stdio server terminated: %v", err)
		}
		return
	}

	// --- standard web server + remote SSE MCP --------------------------------
	app.OnServe().BindFunc(func(e *core.ServeEvent) error {
		mcpServer := apis.NewAgentBaseMCPServer(app)
		mcpServer.BindHTTP(e)
		return e.Next()
	})

	if err := app.Start(); err != nil {
		log.Fatal(err)
	}
}
