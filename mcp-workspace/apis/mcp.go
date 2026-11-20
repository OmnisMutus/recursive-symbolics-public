package apis

import (
	"context"
	"crypto/sha256"
	"crypto/subtle"
	"log/slog"
	"net/http"
	"os"
	"strings"
	"sync"

	"github.com/mark3labs/mcp-go/mcp"
	"github.com/mark3labs/mcp-go/server"
	"github.com/pocketbase/pocketbase/core"
)

// maxAmount is 2^53, the largest integer a float64 represents exactly.
const maxAmount = 1 << 53

// eventLedgerAfterCreate is the only event a hook may register for.
const eventLedgerAfterCreate = "ledger.after_create"

// AgentBaseMCPServer encapsulates the PocketBase application and MCP server instances.
type AgentBaseMCPServer struct {
	app       core.App
	mcpServer *server.MCPServer
	sseServer *server.SSEServer
	mu        sync.RWMutex
	wg        sync.WaitGroup
	logger    *slog.Logger // nil means s.app.Logger(); tests set it to capture output
	usage     *wsUsage     // nil: workspace calls are not logged (EnableWorkspace sets it)
}

// NewAgentBaseMCPServer initializes the server, registers the business tools,
// and wires the event-hook dispatcher into the PocketBase kernel.
func NewAgentBaseMCPServer(app core.App) *AgentBaseMCPServer {
	s := server.NewMCPServer(
		"AgentBase-Daemon",
		"1.0.0",
		server.WithLogging(),
	)

	abs := &AgentBaseMCPServer{
		app:       app,
		mcpServer: s,
	}

	abs.registerTools()
	abs.registerEventDispatchers()
	return abs
}

func toolText(msg string, err error) (*mcp.CallToolResult, error) {
	if err != nil {
		return mcp.NewToolResultError(err.Error()), nil
	}
	return mcp.NewToolResultText(msg), nil
}

func readOnlyHints(title string) []mcp.ToolOption {
	return []mcp.ToolOption{
		mcp.WithTitleAnnotation(title),
		mcp.WithReadOnlyHintAnnotation(true),
		mcp.WithDestructiveHintAnnotation(false),
		mcp.WithIdempotentHintAnnotation(true),
		mcp.WithOpenWorldHintAnnotation(false),
	}
}

func localMutateHints(title string, destructive, idempotent bool) []mcp.ToolOption {
	return []mcp.ToolOption{
		mcp.WithTitleAnnotation(title),
		mcp.WithReadOnlyHintAnnotation(false),
		mcp.WithDestructiveHintAnnotation(destructive),
		mcp.WithIdempotentHintAnnotation(idempotent),
		mcp.WithOpenWorldHintAnnotation(false),
	}
}

func (s *AgentBaseMCPServer) registerTools() {
	s.mcpServer.AddTool(mcp.NewTool("setup_business",
		append([]mcp.ToolOption{
			mcp.WithDescription("One-shot deployment of an autonomous business backend. Creates ledger, metadata, policy, hook, agent, and optional customers collections in a single transaction."),
			mcp.WithString("business_name", mcp.Required(), mcp.Description("Name of the business")),
			mcp.WithString("currency", mcp.Required(), mcp.Description("Base ledger currency (e.g., USD, EUR, SATS, USDC)")),
			mcp.WithString("customer_schema", mcp.Description("Optional comma-separated fields for customers collection, e.g. 'name:text,email:email,tier:select(free,pro)'")),
		}, localMutateHints("Setup Business", false, true)...)...,
	), func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		name, err := req.RequireString("business_name")
		if err != nil {
			return mcp.NewToolResultError(err.Error()), nil
		}
		curr, err := req.RequireString("currency")
		if err != nil {
			return mcp.NewToolResultError(err.Error()), nil
		}
		return toolText(s.doSetupBusinessWithSchema(name, curr, req.GetString("customer_schema", "")))
	})

	s.mcpServer.AddTool(mcp.NewTool("transact",
		mcp.WithDescription("Post an atomic double-entry transaction. Enforces registered policies. Amounts are whole numbers (smallest currency unit). Optionally verifies an ed25519 agent signature; a signed transfer needs agent_id, signature and nonce together, and each nonce is accepted once per agent. The signed bytes are the netstrings (len:value,) of: agentbase.transact.v2, agent_id, from_account, to_account, amount, memo, nonce."),
		mcp.WithString("from_account", mcp.Required(), mcp.Description("Debit account (e.g., 'customer:alice', 'expense:compute')")),
		mcp.WithString("to_account", mcp.Required(), mcp.Description("Credit account (e.g., 'revenue:subscriptions', 'vault:main')")),
		mcp.WithNumber("amount", mcp.Required(), mcp.Description("Positive whole number in the smallest currency unit (<= 2^53)")),
		mcp.WithString("memo", mcp.Description("Reference or purpose of transaction")),
		mcp.WithString("agent_id", mcp.Description("Optional registered agent ID when signing the transaction")),
		mcp.WithString("signature", mcp.Description("Optional 64-byte hex ed25519 signature over the v2 payload described above")),
		mcp.WithString("nonce", mcp.Description("Required with a signature: 1-128 chars of [A-Za-z0-9._:-], never reused by the same agent")),
		mcp.WithTitleAnnotation("Post Ledger Transaction"),
		mcp.WithReadOnlyHintAnnotation(false),
		mcp.WithDestructiveHintAnnotation(false),
		mcp.WithIdempotentHintAnnotation(false),
		mcp.WithOpenWorldHintAnnotation(true), // may dispatch registered webhooks
	), func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		fromAcc, err := req.RequireString("from_account")
		if err != nil {
			return mcp.NewToolResultError(err.Error()), nil
		}
		toAcc, err := req.RequireString("to_account")
		if err != nil {
			return mcp.NewToolResultError(err.Error()), nil
		}
		amount, err := req.RequireFloat("amount")
		if err != nil {
			return mcp.NewToolResultError(err.Error()), nil
		}
		return toolText(s.doSignedTransact(
			fromAcc,
			toAcc,
			amount,
			req.GetString("memo", ""),
			req.GetString("agent_id", ""),
			req.GetString("signature", ""),
			req.GetString("nonce", ""),
		))
	})

	s.mcpServer.AddTool(mcp.NewTool("query_ledger",
		append([]mcp.ToolOption{
			mcp.WithDescription("Calculate real-time net balance and journal entry counts for an account."),
			mcp.WithString("account", mcp.Required(), mcp.Description("Account name to inspect, or '*' for all accounts summary")),
		}, readOnlyHints("Query Ledger")...)...,
	), func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		acc, err := req.RequireString("account")
		if err != nil {
			return mcp.NewToolResultError(err.Error()), nil
		}
		return toolText(s.doQueryLedger(acc))
	})

	s.mcpServer.AddTool(mcp.NewTool("create_policy",
		append([]mcp.ToolOption{
			mcp.WithDescription("Register a hard server-side policy that aborts non-compliant transactions. Condition: '<field> <op> <value>'. field in {amount, from_balance_after, from_account, to_account, account}. Numeric fields allow <=,>=,<,>,==,!=; account fields allow only == or !=."),
			mcp.WithString("rule_name", mcp.Required(), mcp.Description("Unique identifier for policy")),
			mcp.WithString("condition", mcp.Required(), mcp.Description("e.g. 'amount <= 100000', 'from_balance_after >= 0', or 'to_account != vault:cold'")),
		}, localMutateHints("Create Policy", false, false)...)...,
	), func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		name, err := req.RequireString("rule_name")
		if err != nil {
			return mcp.NewToolResultError(err.Error()), nil
		}
		cond, err := req.RequireString("condition")
		if err != nil {
			return mcp.NewToolResultError(err.Error()), nil
		}
		return toolText(s.doCreatePolicy(name, cond))
	})

	s.mcpServer.AddTool(mcp.NewTool("list_policies",
		append([]mcp.ToolOption{
			mcp.WithDescription("List all active transaction guardrail policies."),
		}, readOnlyHints("List Policies")...)...,
	), func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		return toolText(s.doListPolicies())
	})

	s.mcpServer.AddTool(mcp.NewTool("delete_policy",
		append([]mcp.ToolOption{
			mcp.WithDescription("Delete an active policy rule by rule_name."),
			mcp.WithString("rule_name", mcp.Required(), mcp.Description("Unique identifier of policy to remove")),
		}, localMutateHints("Delete Policy", true, true)...)...,
	), func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		name, err := req.RequireString("rule_name")
		if err != nil {
			return mcp.NewToolResultError(err.Error()), nil
		}
		return toolText(s.doDeletePolicy(name))
	})

	s.mcpServer.AddTool(mcp.NewTool("deploy_hook",
		append([]mcp.ToolOption{
			mcp.WithDescription("Register an event hook that POSTs the new record to a webhook when it fires. Only event 'ledger.after_create' is accepted. URLs must be https (or http to localhost with AGENTBASE_ALLOW_HTTP_HOOKS=1) and the host must be in AGENTBASE_HOOK_HOSTS."),
			mcp.WithString("event", mcp.Required(), mcp.Description("Event signature; only 'ledger.after_create' is accepted")),
			mcp.WithString("action_webhook", mcp.Required(), mcp.Description("Target https URL to POST the record JSON to (host must be allowlisted)")),
		}, localMutateHints("Deploy Webhook", false, false)...)...,
	), func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		evt, err := req.RequireString("event")
		if err != nil {
			return mcp.NewToolResultError(err.Error()), nil
		}
		hook, err := req.RequireString("action_webhook")
		if err != nil {
			return mcp.NewToolResultError(err.Error()), nil
		}
		return toolText(s.doDeployHook(evt, hook))
	})

	s.mcpServer.AddTool(mcp.NewTool("list_hooks",
		append([]mcp.ToolOption{
			mcp.WithDescription("List all registered event hooks."),
		}, readOnlyHints("List Hooks")...)...,
	), func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		return toolText(s.doListHooks())
	})

	s.mcpServer.AddTool(mcp.NewTool("delete_hook",
		append([]mcp.ToolOption{
			mcp.WithDescription("Remove a registered event hook by its record ID."),
			mcp.WithString("id", mcp.Required(), mcp.Description("Hook record ID returned by deploy_hook or list_hooks")),
		}, localMutateHints("Delete Webhook", true, true)...)...,
	), func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		id, err := req.RequireString("id")
		if err != nil {
			return mcp.NewToolResultError(err.Error()), nil
		}
		return toolText(s.doDeleteHook(id))
	})

	s.mcpServer.AddTool(mcp.NewTool("register_agent",
		append([]mcp.ToolOption{
			mcp.WithDescription("Register a cryptographic ed25519 agent identity (32-byte hex public key)."),
			mcp.WithString("agent_id", mcp.Required(), mcp.Description("Unique identifier for the agent")),
			mcp.WithString("pubkey_hex", mcp.Required(), mcp.Description("64-character hex-encoded ed25519 public key")),
			mcp.WithString("role", mcp.Description("Optional role label (defaults to 'worker')")),
		}, localMutateHints("Register Agent Identity", false, false)...)...,
	), func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		id, err := req.RequireString("agent_id")
		if err != nil {
			return mcp.NewToolResultError(err.Error()), nil
		}
		pub, err := req.RequireString("pubkey_hex")
		if err != nil {
			return mcp.NewToolResultError(err.Error()), nil
		}
		return toolText(s.doRegisterAgent(id, pub, req.GetString("role", "")))
	})

	s.mcpServer.AddTool(mcp.NewTool("verify_signature",
		append([]mcp.ToolOption{
			mcp.WithDescription("Verify an ed25519 signature produced by a registered agent."),
			mcp.WithString("agent_id", mcp.Required(), mcp.Description("Registered agent identifier")),
			mcp.WithString("message", mcp.Required(), mcp.Description("Exact signed payload string")),
			mcp.WithString("signature", mcp.Required(), mcp.Description("128-character hex-encoded ed25519 signature")),
		}, readOnlyHints("Verify Agent Signature")...)...,
	), func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		id, err := req.RequireString("agent_id")
		if err != nil {
			return mcp.NewToolResultError(err.Error()), nil
		}
		msg, err := req.RequireString("message")
		if err != nil {
			return mcp.NewToolResultError(err.Error()), nil
		}
		sig, err := req.RequireString("signature")
		if err != nil {
			return mcp.NewToolResultError(err.Error()), nil
		}
		return toolText(s.doVerifySignature(id, msg, sig))
	})
}

// ServeStdio starts the MCP server over stdin/stdout for local agents.
func (s *AgentBaseMCPServer) ServeStdio() error {
	return server.ServeStdio(s.mcpServer)
}

// BindHTTP mounts SSE-based MCP endpoints onto PocketBase at /mcp/sse and /mcp/message.
func (s *AgentBaseMCPServer) BindHTTP(e *core.ServeEvent) {
	opts := []server.SSEOption{
		server.WithStaticBasePath("/mcp"),
	}
	if baseURL := strings.TrimSpace(os.Getenv("AGENTBASE_BASE_URL")); baseURL != "" {
		opts = append(opts, server.WithBaseURL(baseURL), server.WithUseFullURLForMessageEndpoint(true))
	} else {
		opts = append(opts, server.WithUseFullURLForMessageEndpoint(false))
	}

	s.mu.Lock()
	s.sseServer = server.NewSSEServer(s.mcpServer, opts...)
	sseHandler := s.sseServer.SSEHandler()
	msgHandler := s.sseServer.MessageHandler()
	s.mu.Unlock()

	apiKey := os.Getenv("AGENTBASE_API_KEY")

	e.Router.GET("/mcp/sse", bearerAuthMiddleware(apiKey, sseHandler))
	e.Router.POST("/mcp/message", bearerAuthMiddleware(apiKey, msgHandler))
}

func bearerAuthMiddleware(apiKey string, next http.Handler) func(c *core.RequestEvent) error {
	wrapped := bearerHTTPHandler(apiKey, next)
	return func(c *core.RequestEvent) error {
		wrapped.ServeHTTP(c.Response, c.Request)
		return nil
	}
}

// bearerHTTPHandler wraps a standard http.Handler with the same fail-closed auth
// semantics used on PocketBase routes so it can be directly tested via httptest.
func bearerHTTPHandler(apiKey string, next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if strings.TrimSpace(apiKey) == "" {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusForbidden)
			_, _ = w.Write([]byte(`{"error":"remote MCP disabled: set AGENTBASE_API_KEY to enable"}`))
			return
		}
		if !checkBearer(r.Header.Get("Authorization"), apiKey) {
			w.Header().Set("WWW-Authenticate", "Bearer")
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusUnauthorized)
			_, _ = w.Write([]byte(`{"error":"unauthorized: missing or invalid bearer token"}`))
			return
		}
		next.ServeHTTP(w, r)
	})
}

// checkBearer validates an "Authorization: Bearer <token>" header against key
// using SHA-256 constant-time comparison so key length cannot leak via timing.
func checkBearer(authHeader, key string) bool {
	if strings.TrimSpace(key) == "" {
		return false
	}
	const prefix = "Bearer "
	if !strings.HasPrefix(authHeader, prefix) {
		return false
	}
	token := authHeader[len(prefix):]
	if token == "" {
		return false
	}
	gotHash := sha256.Sum256([]byte(token))
	wantHash := sha256.Sum256([]byte(key))
	return subtle.ConstantTimeCompare(gotHash[:], wantHash[:]) == 1
}
