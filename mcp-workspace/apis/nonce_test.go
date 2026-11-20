package apis

import (
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"strings"
	"sync"
	"testing"

	"github.com/pocketbase/pocketbase/core"
)

// testAgent registers a fresh ed25519 identity and returns a signer for it.
func testAgent(t *testing.T, s *AgentBaseMCPServer, id string) func(from, to string, amount float64, memo, nonce string) string {
	t.Helper()
	pub, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatalf("keygen: %v", err)
	}
	if _, err := s.doRegisterAgent(id, hex.EncodeToString(pub), ""); err != nil {
		t.Fatalf("register %s: %v", id, err)
	}
	return func(from, to string, amount float64, memo, nonce string) string {
		return hex.EncodeToString(ed25519.Sign(priv, []byte(txSigningPayload(id, from, to, amount, memo, nonce))))
	}
}

func nonceRows(t *testing.T, s *AgentBaseMCPServer) []*core.Record {
	t.Helper()
	recs, err := s.app.FindAllRecords("agent_nonces")
	if err != nil {
		t.Fatalf("read agent_nonces: %v", err)
	}
	return recs
}

// The signed bytes are pinned against a literal written by hand from the
// netstring definition ("<byte length>:<value>,"), not computed by the code.
// "agentbase.transact.v2" is 21 bytes.
func TestSigningPayload_GroundTruthBytes(t *testing.T) {
	got := txSigningPayload("bot", "a", "b", 250, "m", "n1")
	want := "21:agentbase.transact.v2,3:bot,1:a,1:b,3:250,1:m,2:n1,"
	if got != want {
		t.Fatalf("payload bytes:\n got %q\nwant %q", got, want)
	}
	// Empty memo still occupies its slot, so it cannot shift into the nonce.
	if got, want := txSigningPayload("bot", "a", "b", 1, "", "n1"), "21:agentbase.transact.v2,3:bot,1:a,1:b,1:1,0:,2:n1,"; got != want {
		t.Fatalf("empty memo:\n got %q\nwant %q", got, want)
	}
	// The v1 join made these two different transfers sign identical bytes.
	if txSigningPayload("bot", "x|y", "z", 5, "m", "n") == txSigningPayload("bot", "x", "y|z", 5, "m", "n") {
		t.Fatal("payloads for different account splits must differ")
	}
	// Multi-byte memo: length is bytes, not runes ("é" is 2 bytes in UTF-8).
	if got := txSigningPayload("bot", "a", "b", 1, "é", "n"); !strings.Contains(got, ",2:é,") {
		t.Fatalf("memo length must count bytes, got %q", got)
	}
}

// Step 2 core: the identical signed request a second time is refused, and
// the ledger and the nonce table are exactly as the first call left them.
func TestTransact_SignedReplayRejectedLedgerUnchanged(t *testing.T) {
	s := newTestServer(t)
	mustSetup(t, s)
	sign := testAgent(t, s, "bot-a")
	sig := sign("customer:alice", "revenue:subs", 300, "inv-7", "n-1")

	if _, err := s.doSignedTransact("customer:alice", "revenue:subs", 300, "inv-7", "bot-a", sig, "n-1"); err != nil {
		t.Fatalf("first signed transfer: %v", err)
	}
	before := ledgerRows(t, s)
	if len(before) != 2 {
		t.Fatalf("expected 2 rows after first transfer, got %d", len(before))
	}

	_, err := s.doSignedTransact("customer:alice", "revenue:subs", 300, "inv-7", "bot-a", sig, "n-1")
	if err == nil {
		t.Fatal("REPLAY ACCEPTED: the same signed request posted twice")
	}
	if !strings.Contains(err.Error(), "replay") {
		t.Errorf("replay error should say replay, got: %v", err)
	}
	after := ledgerRows(t, s)
	if len(after) != 2 {
		t.Fatalf("ledger changed on replay: %d rows, want 2", len(after))
	}
	for i := range before {
		if before[i].Id != after[i].Id || before[i].GetFloat("amount") != after[i].GetFloat("amount") {
			t.Fatalf("ledger row %d changed on replay", i)
		}
	}
	if n := len(nonceRows(t, s)); n != 1 {
		t.Fatalf("expected 1 recorded nonce, got %d", n)
	}
}

func TestTransact_FreshNoncePasses(t *testing.T) {
	s := newTestServer(t)
	mustSetup(t, s)
	sign := testAgent(t, s, "bot-a")
	for i, n := range []string{"n-1", "n-2", "2026-11-11T22:00:00.000Z"} {
		sig := sign("a", "b", 10, "same memo", n)
		if _, err := s.doSignedTransact("a", "b", 10, "same memo", "bot-a", sig, n); err != nil {
			t.Fatalf("nonce %q: %v", n, err)
		}
		if got := len(ledgerRows(t, s)); got != 2*(i+1) {
			t.Fatalf("after nonce %q: %d rows, want %d", n, got, 2*(i+1))
		}
	}
}

// A nonce belongs to one agent: bot-b may use "n-1" after bot-a did, and
// bot-a still may not reuse it.
func TestTransact_NonceIndependentPerAgent(t *testing.T) {
	s := newTestServer(t)
	mustSetup(t, s)
	signA := testAgent(t, s, "bot-a")
	signB := testAgent(t, s, "bot-b")

	if _, err := s.doSignedTransact("a", "b", 5, "", "bot-a", signA("a", "b", 5, "", "n-1"), "n-1"); err != nil {
		t.Fatalf("bot-a n-1: %v", err)
	}
	if _, err := s.doSignedTransact("a", "b", 5, "", "bot-b", signB("a", "b", 5, "", "n-1"), "n-1"); err != nil {
		t.Fatalf("bot-b reusing bot-a's nonce value must be independent, got: %v", err)
	}
	if _, err := s.doSignedTransact("a", "b", 5, "", "bot-a", signA("a", "b", 5, "", "n-1"), "n-1"); err == nil {
		t.Fatal("bot-a reused n-1 and it was accepted")
	}
	if n := len(ledgerRows(t, s)); n != 4 {
		t.Fatalf("expected 4 rows, got %d", n)
	}
}

// A signature cannot be bound to someone else's nonce: changing the nonce
// changes the signed bytes, so the old signature no longer verifies.
func TestTransact_SignatureBoundToNonceAndAgent(t *testing.T) {
	s := newTestServer(t)
	mustSetup(t, s)
	signA := testAgent(t, s, "bot-a")
	testAgent(t, s, "bot-b")
	sig := signA("a", "b", 5, "", "n-1")
	if _, err := s.doSignedTransact("a", "b", 5, "", "bot-a", sig, "n-2"); err == nil {
		t.Fatal("signature for n-1 accepted with nonce n-2")
	}
	if _, err := s.doSignedTransact("a", "b", 5, "", "bot-b", sig, "n-1"); err == nil {
		t.Fatal("bot-a's signature accepted for bot-b")
	}
	if n := len(ledgerRows(t, s)) + len(nonceRows(t, s)); n != 0 {
		t.Fatalf("expected nothing written, got %d rows", n)
	}
}

func TestTransact_SignedNeedsAllThreeAndValidNonce(t *testing.T) {
	s := newTestServer(t)
	mustSetup(t, s)
	sign := testAgent(t, s, "bot-a")
	good := sign("a", "b", 5, "", "n-1")
	// Missing parts: each must be refused for being incomplete, not because a
	// later check happens to catch it too.
	for _, tc := range []struct{ agent, sig, nonce string }{
		{"bot-a", sign("a", "b", 5, "", ""), ""}, // validly signed with no nonce: the old replayable form
		{"", "", "n-1"},                          // nonce alone
		{"bot-a", "", "n-1"},                     // no signature
		{"", good, "n-1"},                        // no agent
	} {
		_, err := s.doSignedTransact("a", "b", 5, "", tc.agent, tc.sig, tc.nonce)
		if err == nil || !strings.Contains(err.Error(), "agent_id, signature and nonce together") {
			t.Errorf("agent=%q sig=%t nonce=%q: want the all-three refusal, got: %v", tc.agent, tc.sig != "", tc.nonce, err)
		}
	}
	// Bad nonces, each validly signed over itself, so only the alphabet and
	// length check stands between them and the ledger.
	for _, bad := range []string{" n-1", "n|1", "n\n1", strings.Repeat("x", 129)} {
		_, err := s.doSignedTransact("a", "b", 5, "", "bot-a", sign("a", "b", 5, "", bad), bad)
		if err == nil || !strings.Contains(err.Error(), "nonce must be") {
			t.Errorf("nonce %q: want the alphabet/length refusal, got: %v", bad, err)
		}
	}
	if n := len(ledgerRows(t, s)) + len(nonceRows(t, s)); n != 0 {
		t.Fatalf("expected nothing written, got %d rows", n)
	}
	// 128 characters is the inclusive upper bound.
	n128 := strings.Repeat("x", 128)
	if _, err := s.doSignedTransact("a", "b", 5, "", "bot-a", sign("a", "b", 5, "", n128), n128); err != nil {
		t.Fatalf("128-char nonce should pass: %v", err)
	}
}

// A transfer that fails for another reason (here a policy) rolls back its
// nonce row too, so the nonce is not burned and the ledger is untouched.
func TestTransact_RejectedTransferDoesNotBurnNonce(t *testing.T) {
	s := newTestServer(t)
	mustSetup(t, s)
	if _, err := s.doCreatePolicy("cap", "amount <= 100"); err != nil {
		t.Fatalf("policy: %v", err)
	}
	sign := testAgent(t, s, "bot-a")
	if _, err := s.doSignedTransact("a", "b", 500, "", "bot-a", sign("a", "b", 500, "", "n-1"), "n-1"); err == nil {
		t.Fatal("over-cap transfer posted")
	}
	if n := len(nonceRows(t, s)); n != 0 {
		t.Fatalf("aborted transfer left %d nonce rows", n)
	}
	if _, err := s.doSignedTransact("a", "b", 50, "", "bot-a", sign("a", "b", 50, "", "n-1"), "n-1"); err != nil {
		t.Fatalf("nonce from the aborted transfer should still be usable: %v", err)
	}
}

// Many copies of one signed request at once: exactly one posts.
func TestTransact_ConcurrentReplayExactlyOnePosts(t *testing.T) {
	s := newTestServer(t)
	mustSetup(t, s)
	sign := testAgent(t, s, "bot-a")
	sig := sign("a", "b", 7, "race", "n-race")

	const copies = 16
	var wg sync.WaitGroup
	var mu sync.Mutex
	ok := 0
	for i := 0; i < copies; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			if _, err := s.doSignedTransact("a", "b", 7, "race", "bot-a", sig, "n-race"); err == nil {
				mu.Lock()
				ok++
				mu.Unlock()
			}
		}()
	}
	wg.Wait()
	if ok != 1 {
		t.Fatalf("%d of %d concurrent copies posted, want exactly 1", ok, copies)
	}
	if n := len(ledgerRows(t, s)); n != 2 {
		t.Fatalf("expected 2 ledger rows, got %d", n)
	}
}

// The unique index is the last line: even a write that skips recordNonceTx's
// lookup cannot store the same (agent, nonce) twice.
func TestAgentNonces_UniqueIndexRejectsDuplicate(t *testing.T) {
	s := newTestServer(t)
	mustSetup(t, s)
	col, err := s.app.FindCollectionByNameOrId("agent_nonces")
	if err != nil {
		t.Fatalf("agent_nonces missing: %v", err)
	}
	save := func(agent, nonce string) error {
		r := core.NewRecord(col)
		r.Set("agent_id", agent)
		r.Set("nonce", nonce)
		r.Set("tx_hash", "tx_test")
		return s.app.Save(r)
	}
	if err := save("bot-a", "n-1"); err != nil {
		t.Fatalf("first insert: %v", err)
	}
	if err := save("bot-a", "n-1"); err == nil {
		t.Fatal("unique index allowed a duplicate (agent, nonce)")
	}
	if err := save("bot-b", "n-1"); err != nil {
		t.Fatalf("same nonce for another agent must be allowed: %v", err)
	}
}

// A database created before agent_nonces existed fails closed on signed
// transfers until setup_business is run again, which adds the collection.
func TestTransact_SignedFailsClosedWithoutNonceTable(t *testing.T) {
	s := newTestServer(t)
	mustSetup(t, s)
	sign := testAgent(t, s, "bot-a")
	col, err := s.app.FindCollectionByNameOrId("agent_nonces")
	if err != nil {
		t.Fatalf("agent_nonces missing: %v", err)
	}
	if err := s.app.Delete(col); err != nil {
		t.Fatalf("drop agent_nonces: %v", err)
	}
	if _, err := s.doSignedTransact("a", "b", 5, "", "bot-a", sign("a", "b", 5, "", "n-1"), "n-1"); err == nil {
		t.Fatal("signed transfer posted with no nonce table")
	}
	if n := len(ledgerRows(t, s)); n != 0 {
		t.Fatalf("expected 0 rows, got %d", n)
	}
	if _, err := s.doSetupBusiness("TestCo", "USD"); err != nil {
		t.Fatalf("re-run setup: %v", err)
	}
	if _, err := s.doSignedTransact("a", "b", 5, "", "bot-a", sign("a", "b", 5, "", "n-1"), "n-1"); err != nil {
		t.Fatalf("after re-running setup the signed transfer should post: %v", err)
	}
}

// The nonce reaches doSignedTransact through the MCP tool argument.
func TestMCP_TransactNonceArgument(t *testing.T) {
	s := newTestServer(t)
	mustSetup(t, s)
	sign := testAgent(t, s, "bot-a")
	call := func(id int) string {
		msg := fmt.Sprintf(`{"jsonrpc":"2.0","id":%d,"method":"tools/call","params":{"name":"transact","arguments":{
			"from_account":"a","to_account":"b","amount":9,"memo":"m","agent_id":"bot-a","signature":%q,"nonce":"n-1"}}}`,
			id, sign("a", "b", 9, "m", "n-1"))
		b, _ := json.Marshal(s.mcpServer.HandleMessage(context.Background(), json.RawMessage(msg)))
		return string(b)
	}
	if out := call(1); !strings.Contains(out, "TRANSACTION POSTED") {
		t.Fatalf("first call: %s", out)
	}
	if out := call(2); !strings.Contains(out, "replay") {
		t.Fatalf("second call should be refused as a replay: %s", out)
	}
}
