package apis

import (
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"sync"
	"testing"

	"github.com/mark3labs/mcp-go/server"
	"github.com/pocketbase/pocketbase/core"
)

func TestQueryLedger_LifecycleAndExactSum(t *testing.T) {
	s := newTestServer(t)

	// Pre-setup: clean error, no raw SQLite error leak.
	if _, err := s.doQueryLedger("*"); err == nil || strings.Contains(err.Error(), "no such table") {
		t.Fatalf("expected clean pre-setup error, got: %v", err)
	}

	mustSetup(t, s)

	// Empty ledger returns "[]", never "null".
	emptyOut, err := s.doQueryLedger("*")
	if err != nil {
		t.Fatalf("empty query_ledger: %v", err)
	}
	if strings.TrimSpace(emptyOut) != "[]" {
		t.Fatalf("expected empty JSON array [], got: %q", emptyOut)
	}

	// Whitespace account is rejected.
	if _, err := s.doQueryLedger("   "); err == nil {
		t.Fatal("expected whitespace account to be rejected")
	}

	// Independent ground truth: sum postings in Go and compare to SQLite query.
	if _, err := s.doTransact("customer:alice", "revenue:subs", 300, "p1"); err != nil {
		t.Fatalf("tx1: %v", err)
	}
	if _, err := s.doTransact("customer:alice", "revenue:subs", 250, "p2"); err != nil {
		t.Fatalf("tx2: %v", err)
	}
	if _, err := s.doTransact("revenue:subs", "expense:hosting", 100, "p3"); err != nil {
		t.Fatalf("tx3: %v", err)
	}

	raw, err := s.doQueryLedger("*")
	if err != nil {
		t.Fatalf("query all: %v", err)
	}
	var rows []balanceRow
	if err := json.Unmarshal([]byte(raw), &rows); err != nil {
		t.Fatalf("unmarshal balances: %v (raw=%s)", err, raw)
	}
	got := map[string]int64{}
	var netSum int64
	for _, r := range rows {
		got[r.Account] = r.Balance
		netSum += r.Balance
	}
	if netSum != 0 {
		t.Fatalf("double-entry invariant broken: net sum = %d, want 0", netSum)
	}
	if got["customer:alice"] != -550 || got["revenue:subs"] != 450 || got["expense:hosting"] != 100 {
		t.Fatalf("unexpected balances: %+v", got)
	}

	// Filtered single-account query.
	oneRaw, err := s.doQueryLedger("revenue:subs")
	if err != nil {
		t.Fatalf("query single: %v", err)
	}
	var one []balanceRow
	if err := json.Unmarshal([]byte(oneRaw), &one); err != nil {
		t.Fatalf("unmarshal single: %v", err)
	}
	if len(one) != 1 || one[0].Account != "revenue:subs" || one[0].Balance != 450 || one[0].Entries != 3 {
		t.Fatalf("unexpected single-account result: %+v", one)
	}
}

func TestTransact_RejectsSelfTransferAndWhitespace(t *testing.T) {
	s := newTestServer(t)
	mustSetup(t, s)

	for _, tc := range []struct {
		from string
		to   string
	}{
		{"vault:main", "vault:main"},
		{"  vault:main  ", "vault:main"},
		{"   ", "revenue:subs"},
		{"customer:alice", "   "},
	} {
		if _, err := s.doTransact(tc.from, tc.to, 100, ""); err == nil {
			t.Errorf("expected error for from=%q to=%q", tc.from, tc.to)
		}
	}
	if n := len(ledgerRows(t, s)); n != 0 {
		t.Fatalf("expected 0 ledger rows, got %d", n)
	}
}

func TestPolicyLifecycle_UniqueAndBalanceFloor(t *testing.T) {
	s := newTestServer(t)
	mustSetup(t, s)

	if _, err := s.doCreatePolicy("no_overdraft", "from_balance_after >= 0"); err != nil {
		t.Fatalf("create no_overdraft: %v", err)
	}
	// Duplicate rule_name must fail closed rather than stacking silently.
	if _, err := s.doCreatePolicy("no_overdraft", "from_balance_after >= 100"); err == nil {
		t.Fatal("expected duplicate rule_name to be rejected")
	}

	// Attempting to spend from unfunded account fails closed.
	if _, err := s.doTransact("operating:cash", "vendor:cloud", 500, "unfunded"); err == nil {
		t.Fatal("expected overdraft from unfunded account to be blocked")
	}
	if n := len(ledgerRows(t, s)); n != 0 {
		t.Fatalf("expected 0 ledger rows after blocked overdraft, got %d", n)
	}

	// Delete no_overdraft, seed operating:cash from equity:seed, then re-enable.
	if _, err := s.doDeletePolicy("no_overdraft"); err != nil {
		t.Fatalf("delete_policy: %v", err)
	}
	if _, err := s.doTransact("equity:seed", "operating:cash", 1000, "seed"); err != nil {
		t.Fatalf("seed cash: %v", err)
	}
	if _, err := s.doCreatePolicy("no_overdraft", "from_balance_after >= 0"); err != nil {
		t.Fatalf("recreate no_overdraft: %v", err)
	}

	// Boundary: spend exact balance (1000 -> post-tx balance 0) succeeds.
	if _, err := s.doTransact("operating:cash", "vendor:cloud", 1000, "exact"); err != nil {
		t.Fatalf("expected exact balance spend to succeed, got: %v", err)
	}
	// One past boundary: spend 1 more (post-tx balance -1) fails.
	if _, err := s.doTransact("operating:cash", "vendor:cloud", 1, "one over"); err == nil {
		t.Fatal("expected post-tx balance -1 to be blocked")
	}

	// list_policies shows our rule.
	listJSON, err := s.doListPolicies()
	if err != nil {
		t.Fatalf("list_policies: %v", err)
	}
	if !strings.Contains(listJSON, "no_overdraft") {
		t.Fatalf("expected no_overdraft in list_policies, got: %s", listJSON)
	}
}

func TestSetupBusiness_CustomerSchema(t *testing.T) {
	s := newTestServer(t)

	// Reserved or malformed schema specs must abort without creating collections.
	for _, bad := range []string{
		"id:text",
		"tier:select()",
		"bad_type:json_bomb",
		"no_colon",
		"dup:text,dup:email",
	} {
		if _, err := s.doSetupBusinessWithSchema("BadCo", "USD", bad); err == nil {
			t.Errorf("expected customer_schema %q to be rejected", bad)
		}
	}
	if _, err := s.app.FindCollectionByNameOrId("ledger"); err == nil {
		t.Fatal("failed setup should not have created ledger collection")
	}

	msg, err := s.doSetupBusinessWithSchema("SchemaCo", "USDC", "name:text,email:email,tier:select(free,pro),active:bool,site:url,credits:number")
	if err != nil {
		t.Fatalf("valid schema setup failed: %v", err)
	}
	if !strings.Contains(msg, "customers (6 fields)") {
		t.Fatalf("unexpected setup message: %q", msg)
	}

	col, err := s.app.FindCollectionByNameOrId("customers")
	if err != nil {
		t.Fatalf("customers collection missing: %v", err)
	}
	rec := core.NewRecord(col)
	rec.Set("name", "Alice")
	rec.Set("email", "alice@example.com")
	rec.Set("tier", "pro")
	rec.Set("active", true)
	rec.Set("site", "https://example.com")
	rec.Set("credits", 42)
	if err := s.app.Save(rec); err != nil {
		t.Fatalf("save customer record failed: %v", err)
	}
}

func TestIdentity_Ed25519SigningAndSignedTransact(t *testing.T) {
	s := newTestServer(t)
	mustSetup(t, s)

	pub, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatalf("keygen: %v", err)
	}
	pubHex := hex.EncodeToString(pub)

	if _, err := s.doRegisterAgent("billing-bot", pubHex, "treasurer"); err != nil {
		t.Fatalf("register_agent: %v", err)
	}
	// Duplicate agent_id must be rejected.
	if _, err := s.doRegisterAgent("billing-bot", pubHex, "admin"); err == nil {
		t.Fatal("expected duplicate agent_id to be rejected")
	}

	payload := txSigningPayload("billing-bot", "customer:alice", "revenue:subs", 250, "invoice-1", "n-1")
	sigHex := hex.EncodeToString(ed25519.Sign(priv, []byte(payload)))

	if _, err := s.doVerifySignature("billing-bot", payload, sigHex); err != nil {
		t.Fatalf("verify_signature failed on valid sig: %v", err)
	}
	if _, err := s.doVerifySignature("billing-bot", payload+"tampered", sigHex); err == nil {
		t.Fatal("expected tampered payload to fail signature check")
	}
	if _, err := s.doVerifySignature("ghost-bot", payload, sigHex); err == nil {
		t.Fatal("expected unknown agent to fail closed")
	}

	// Signed transaction with invalid sig must abort and write zero rows.
	if _, err := s.doSignedTransact("customer:alice", "revenue:subs", 250, "invoice-1", "billing-bot", strings.Repeat("00", 64), "n-1"); err == nil {
		t.Fatal("expected forged signature on transact to fail")
	}
	if n := len(ledgerRows(t, s)); n != 0 {
		t.Fatalf("expected 0 rows after forged sig, got %d", n)
	}

	// Valid signed transaction posts both rows.
	if _, err := s.doSignedTransact("customer:alice", "revenue:subs", 250, "invoice-1", "billing-bot", sigHex, "n-1"); err != nil {
		t.Fatalf("valid signed transact failed: %v", err)
	}
	if n := len(ledgerRows(t, s)); n != 2 {
		t.Fatalf("expected 2 ledger rows after valid signed tx, got %d", n)
	}
}

func TestHooks_LiveDispatchCurrencyAndRedirectBlocked(t *testing.T) {
	var mu sync.Mutex
	var received []map[string]any
	secretReached := false

	// Victim internal service that a redirect must NOT reach.
	victim := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		secretReached = true
		mu.Unlock()
		w.WriteHeader(http.StatusOK)
	}))
	defer victim.Close()

	// Hook server: /ok accepts POST JSON; /redir tries to 302-redirect to victim.
	hookSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/redir" {
			http.Redirect(w, r, victim.URL, http.StatusFound)
			return
		}
		var body map[string]any
		_ = json.NewDecoder(r.Body).Decode(&body)
		mu.Lock()
		received = append(received, body)
		mu.Unlock()
		w.WriteHeader(http.StatusOK)
	}))
	defer hookSrv.Close()

	u, _ := url.Parse(hookSrv.URL)
	t.Setenv("AGENTBASE_HOOK_HOSTS", u.Hostname())
	t.Setenv("AGENTBASE_ALLOW_HTTP_HOOKS", "1")

	s := newTestServer(t)
	if _, err := s.doSetupBusiness("HookCo", "SATS"); err != nil {
		t.Fatalf("setup: %v", err)
	}
	msg1, err := s.doDeployHook(eventLedgerAfterCreate, hookSrv.URL+"/ok")
	if err != nil {
		t.Fatalf("deploy ok hook: %v", err)
	}
	if _, err := s.doDeployHook(eventLedgerAfterCreate, hookSrv.URL+"/redir"); err != nil {
		t.Fatalf("deploy redir hook: %v", err)
	}

	if _, err := s.doTransact("customer:a", "revenue:b", 77, "hook-check"); err != nil {
		t.Fatalf("transact: %v", err)
	}
	s.WaitHooks()

	mu.Lock()
	gotCount := len(received)
	gotVictim := secretReached
	var firstPayload map[string]any
	if gotCount > 0 {
		firstPayload = received[0]
	}
	mu.Unlock()

	if gotVictim {
		t.Fatal("SSRF vulnerability: safeWebhookClient followed HTTP 302 redirect to victim server")
	}
	if gotCount != 2 {
		t.Fatalf("expected 2 webhook POSTs (one per ledger leg) to /ok, got %d", gotCount)
	}
	if firstPayload["currency"] != "SATS" {
		t.Errorf("expected webhook payload to include currency=SATS, got %v", firstPayload["currency"])
	}

	// Verify list_hooks + delete_hook.
	hooksJSON, err := s.doListHooks()
	if err != nil {
		t.Fatalf("list_hooks: %v", err)
	}
	if !strings.Contains(hooksJSON, "/ok") || !strings.Contains(hooksJSON, "/redir") {
		t.Fatalf("unexpected list_hooks output: %s", hooksJSON)
	}
	// Extract first hook ID from "[<id>]" in msg1.
	start := strings.IndexByte(msg1, '[') + 1
	end := strings.IndexByte(msg1, ']')
	if _, err := s.doDeleteHook(msg1[start:end]); err != nil {
		t.Fatalf("delete_hook: %v", err)
	}
}

func TestMCP_JSONRPC_EndToEnd(t *testing.T) {
	s := newTestServer(t)
	ctx := context.Background()

	// 1. initialize
	initResp := s.mcpServer.HandleMessage(ctx, json.RawMessage(`{
		"jsonrpc":"2.0","id":1,"method":"initialize",
		"params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}
	}`))
	initBytes, _ := json.Marshal(initResp)
	if !strings.Contains(string(initBytes), "AgentBase-Daemon") {
		t.Fatalf("unexpected initialize response: %s", initBytes)
	}

	// 2. tools/list must advertise all 11 tools with accurate MCP annotations
	listResp := s.mcpServer.HandleMessage(ctx, json.RawMessage(`{"jsonrpc":"2.0","id":2,"method":"tools/list"}`))
	listBytes, _ := json.Marshal(listResp)
	var listDecoded struct {
		Result struct {
			Tools []struct {
				Name        string `json:"name"`
				Annotations struct {
					ReadOnlyHint    bool `json:"readOnlyHint"`
					DestructiveHint bool `json:"destructiveHint"`
					OpenWorldHint   bool `json:"openWorldHint"`
				} `json:"annotations"`
			} `json:"tools"`
		} `json:"result"`
	}
	if err := json.Unmarshal(listBytes, &listDecoded); err != nil {
		t.Fatalf("unmarshal tools/list: %v", err)
	}
	toolByName := map[string]struct {
		ro, destr, open bool
	}{}
	for _, tl := range listDecoded.Result.Tools {
		toolByName[tl.Name] = struct{ ro, destr, open bool }{
			tl.Annotations.ReadOnlyHint,
			tl.Annotations.DestructiveHint,
			tl.Annotations.OpenWorldHint,
		}
	}
	for _, tool := range []string{
		"setup_business", "transact", "query_ledger",
		"create_policy", "list_policies", "delete_policy",
		"deploy_hook", "list_hooks", "delete_hook",
		"register_agent", "verify_signature",
	} {
		if _, ok := toolByName[tool]; !ok {
			t.Errorf("tools/list missing %q", tool)
		}
	}
	if a := toolByName["query_ledger"]; !a.ro || a.destr || a.open {
		t.Errorf("query_ledger annotations invalid: %+v", a)
	}
	if a := toolByName["transact"]; a.ro || a.destr || !a.open {
		t.Errorf("transact annotations invalid: %+v", a)
	}
	if a := toolByName["delete_policy"]; a.ro || !a.destr || a.open {
		t.Errorf("delete_policy annotations invalid: %+v", a)
	}

	// 3. tools/call setup_business -> transact -> query_ledger
	setupResp := s.mcpServer.HandleMessage(ctx, json.RawMessage(`{
		"jsonrpc":"2.0","id":3,"method":"tools/call",
		"params":{"name":"setup_business","arguments":{"business_name":"RPCCo","currency":"EUR"}}
	}`))
	if b, _ := json.Marshal(setupResp); !strings.Contains(string(b), "SUCCESS") {
		t.Fatalf("setup_business call failed: %s", b)
	}

	txResp := s.mcpServer.HandleMessage(ctx, json.RawMessage(`{
		"jsonrpc":"2.0","id":4,"method":"tools/call",
		"params":{"name":"transact","arguments":{"from_account":"client:x","to_account":"rev:y","amount":420}}
	}`))
	if b, _ := json.Marshal(txResp); !strings.Contains(string(b), "TRANSACTION POSTED") {
		t.Fatalf("transact call failed: %s", b)
	}

	qResp := s.mcpServer.HandleMessage(ctx, json.RawMessage(`{
		"jsonrpc":"2.0","id":5,"method":"tools/call",
		"params":{"name":"query_ledger","arguments":{"account":"rev:y"}}
	}`))
	if b, _ := json.Marshal(qResp); !strings.Contains(string(b), "420") {
		t.Fatalf("query_ledger call unexpected: %s", b)
	}
}

func TestRemoteAuthGuard_And_SSEPath(t *testing.T) {
	okHandler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	})

	// Unset or whitespace API key -> 403 Forbidden (fail closed).
	for _, k := range []string{"", "   "} {
		rec := httptest.NewRecorder()
		req := httptest.NewRequest(http.MethodGet, "/mcp/sse", nil)
		req.Header.Set("Authorization", "Bearer anything")
		bearerHTTPHandler(k, okHandler).ServeHTTP(rec, req)
		if rec.Code != http.StatusForbidden {
			t.Errorf("key=%q: expected 403, got %d", k, rec.Code)
		}
	}

	// Missing or invalid token -> 401 + WWW-Authenticate.
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/mcp/sse", nil)
	req.Header.Set("Authorization", "Bearer wrong")
	bearerHTTPHandler("real-key", okHandler).ServeHTTP(rec, req)
	if rec.Code != http.StatusUnauthorized || rec.Header().Get("WWW-Authenticate") != "Bearer" {
		t.Errorf("expected 401 with WWW-Authenticate=Bearer, got %d (%q)", rec.Code, rec.Header().Get("WWW-Authenticate"))
	}

	// Valid token -> 200 OK.
	rec = httptest.NewRecorder()
	req = httptest.NewRequest(http.MethodGet, "/mcp/sse", nil)
	req.Header.Set("Authorization", "Bearer real-key")
	bearerHTTPHandler("real-key", okHandler).ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", rec.Code)
	}

	// Verify SSEServer advertises /mcp/message (matching PocketBase route), not /message.
	s := newTestServer(t)
	sse := server.NewSSEServer(s.mcpServer,
		server.WithStaticBasePath("/mcp"),
		server.WithUseFullURLForMessageEndpoint(false),
	)
	if sse.CompleteSsePath() != "/mcp/sse" || sse.CompleteMessagePath() != "/mcp/message" {
		t.Errorf("unexpected SSE paths: sse=%q msg=%q", sse.CompleteSsePath(), sse.CompleteMessagePath())
	}
}
