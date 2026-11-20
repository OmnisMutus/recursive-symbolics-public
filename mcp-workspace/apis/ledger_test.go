package apis

import (
	"math"
	"strings"
	"testing"

	"github.com/pocketbase/pocketbase"
	"github.com/pocketbase/pocketbase/core"
)

// newTestServer builds an AgentBaseMCPServer backed by a fresh, bootstrapped
// PocketBase instance in a temp data dir. The DB is closed on cleanup so the
// temp dir can be removed on Windows.
func newTestServer(t *testing.T) *AgentBaseMCPServer {
	t.Helper()
	dir := t.TempDir()
	app := pocketbase.NewWithConfig(pocketbase.Config{DefaultDataDir: dir, HideStartBanner: true})
	if err := app.Bootstrap(); err != nil {
		t.Fatalf("bootstrap: %v", err)
	}
	s := NewAgentBaseMCPServer(app)
	t.Cleanup(func() { _ = app.ResetBootstrapState() })
	t.Cleanup(s.WaitHooks)
	return s
}

func mustSetup(t *testing.T, s *AgentBaseMCPServer) {
	t.Helper()
	if _, err := s.doSetupBusiness("TestCo", "USD"); err != nil {
		t.Fatalf("setup: %v", err)
	}
}

func ledgerRows(t *testing.T, s *AgentBaseMCPServer) []*core.Record {
	t.Helper()
	recs, err := s.app.FindAllRecords("ledger")
	if err != nil {
		t.Fatalf("read ledger: %v", err)
	}
	return recs
}

// item 6: a 5000 transaction against "amount <= 1000" leaves ZERO ledger rows.
func TestTransact_PolicyViolationLeavesZeroRows(t *testing.T) {
	s := newTestServer(t)
	mustSetup(t, s)
	if _, err := s.doCreatePolicy("cap", "amount <= 1000"); err != nil {
		t.Fatalf("create policy: %v", err)
	}
	if _, err := s.doTransact("customer:bob", "revenue:subs", 5000, "over cap"); err == nil {
		t.Fatal("expected the 5000 transaction to be aborted by policy")
	}
	if n := len(ledgerRows(t, s)); n != 0 {
		t.Fatalf("expected ZERO ledger rows after a blocked transaction, got %d", n)
	}
}

// item 6: a transaction under the cap writes exactly two rows that sum to zero.
func TestTransact_UnderCapWritesTwoRowsSummingZero(t *testing.T) {
	s := newTestServer(t)
	mustSetup(t, s)
	if _, err := s.doCreatePolicy("cap", "amount <= 1000"); err != nil {
		t.Fatalf("create policy: %v", err)
	}
	if _, err := s.doTransact("customer:alice", "revenue:subs", 500, "ok"); err != nil {
		t.Fatalf("expected the 500 transaction to post, got: %v", err)
	}
	rows := ledgerRows(t, s)
	if len(rows) != 2 {
		t.Fatalf("expected exactly 2 ledger rows, got %d", len(rows))
	}
	var sum float64
	for _, r := range rows {
		sum += r.GetFloat("amount")
	}
	if sum != 0 {
		t.Fatalf("expected the two rows to sum to zero, got %v", sum)
	}
}

// item 1a: a policy-load error other than a missing collection aborts the
// transaction (fail closed). We drop the data table but keep the collection
// metadata, so FindAllRecords errors while the collection still "exists".
func TestEnforcePolicies_AbortsOnLoadError(t *testing.T) {
	s := newTestServer(t)
	mustSetup(t, s)
	if _, err := s.app.DB().NewQuery("DROP TABLE policies").Execute(); err != nil {
		t.Fatalf("drop table: %v", err)
	}
	if err := s.enforcePolicies(s.app, 100, "a", "b"); err == nil {
		t.Fatal("expected enforcePolicies to abort (fail closed) when policies cannot be loaded")
	}
}

// item 1a (companion): a genuinely missing collection means "no policies" and
// is allowed, so enforcePolicies must NOT error before setup_business runs.
func TestEnforcePolicies_MissingCollectionAllows(t *testing.T) {
	s := newTestServer(t)
	if err := s.enforcePolicies(s.app, 100, "a", "b"); err != nil {
		t.Fatalf("expected no error when policies collection is absent, got: %v", err)
	}
}

// item 1b: an unparseable STORED condition aborts the transaction, naming the
// rule, and leaves no ledger rows. We corrupt a valid policy directly in the DB.
func TestTransact_AbortsOnUnparseableStoredPolicy(t *testing.T) {
	s := newTestServer(t)
	mustSetup(t, s)
	if _, err := s.doCreatePolicy("bad", "amount <= 1000"); err != nil {
		t.Fatalf("create policy: %v", err)
	}
	// Corrupt the stored condition to something with no operator at all.
	if _, err := s.app.DB().NewQuery("UPDATE policies SET condition='garbage no operator here'").Execute(); err != nil {
		t.Fatalf("corrupt policy: %v", err)
	}
	_, err := s.doTransact("a", "b", 100, "")
	if err == nil {
		t.Fatal("expected abort on an unparseable stored policy")
	}
	if !strings.Contains(err.Error(), "bad") {
		t.Errorf("expected the abort error to name the rule 'bad', got: %v", err)
	}
	// The reason must be the parse failure itself. Without this, disabling the
	// parse check still aborts (the zero-value condition reads as a violation),
	// so the guard under test was invisible to the suite.
	if !strings.Contains(err.Error(), "unparseable") {
		t.Errorf("expected the abort to cite the unparseable condition, got: %v", err)
	}
	if n := len(ledgerRows(t, s)); n != 0 {
		t.Fatalf("expected ZERO ledger rows after abort, got %d", n)
	}
}

// item 3: a second setup_business with a different currency reports the stored one.
func TestSetupBusiness_SecondCallReportsStored(t *testing.T) {
	s := newTestServer(t)
	if _, err := s.doSetupBusiness("First", "USD"); err != nil {
		t.Fatalf("first setup: %v", err)
	}
	msg, err := s.doSetupBusiness("Second", "EUR")
	if err != nil {
		t.Fatalf("second setup: %v", err)
	}
	if !strings.Contains(msg, "USD") {
		t.Errorf("expected the stored currency USD to be reported, got: %q", msg)
	}
	if strings.Contains(msg, "EUR initialized") || strings.Contains(msg, "Business 'Second' initialized") {
		t.Errorf("second setup must not report the new currency as initialized, got: %q", msg)
	}
	if got := s.baseCurrency(s.app); got != "USD" {
		t.Errorf("stored currency must remain USD, got %q", got)
	}
}

// item 2 (integration): deploy_hook refuses dangerous or non-allowlisted URLs,
// the wrong event, and accepts a well-formed allowlisted https URL.
func TestDeployHook_Registration(t *testing.T) {
	t.Setenv("AGENTBASE_HOOK_HOSTS", "hooks.example.com")
	t.Setenv("AGENTBASE_ALLOW_HTTP_HOOKS", "")
	s := newTestServer(t)
	mustSetup(t, s)

	refuse := []string{
		"http://169.254.169.254/",   // http + metadata IP, not allowlisted
		"http://127.0.0.1/",         // http + loopback, not allowlisted
		"https://evil.example.com/", // host not in allowlist
	}
	for _, u := range refuse {
		if _, err := s.doDeployHook(eventLedgerAfterCreate, u); err == nil {
			t.Errorf("deploy_hook should have refused %q", u)
		}
	}
	// Wrong event (item 2d).
	if _, err := s.doDeployHook("ledger.before_create", "https://hooks.example.com/"); err == nil {
		t.Error("deploy_hook should reject an event other than ledger.after_create")
	}
	// A well-formed, allowlisted https URL is accepted.
	if _, err := s.doDeployHook(eventLedgerAfterCreate, "https://hooks.example.com/webhook"); err != nil {
		t.Errorf("deploy_hook should accept an allowlisted https URL, got: %v", err)
	}
}

// item 2a: scheme enforcement at registration.
func TestValidateHookRegistration_Scheme(t *testing.T) {
	t.Setenv("AGENTBASE_ALLOW_HTTP_HOOKS", "")
	allow := map[string]bool{"hooks.example.com": true}
	if err := validateHookRegistration("https://hooks.example.com/", allow); err != nil {
		t.Errorf("https should be allowed, got: %v", err)
	}
	if err := validateHookRegistration("http://hooks.example.com/", allow); err == nil {
		t.Error("http should be refused without AGENTBASE_ALLOW_HTTP_HOOKS=1")
	}
	if err := validateHookRegistration("ftp://hooks.example.com/", allow); err == nil {
		t.Error("ftp should be refused")
	}
}

// item 2b: host allowlist enforcement at registration.
func TestValidateHookRegistration_Allowlist(t *testing.T) {
	if err := validateHookRegistration("https://hooks.example.com/", map[string]bool{}); err == nil {
		t.Error("an empty allowlist must refuse every URL")
	}
	if err := validateHookRegistration("https://hooks.example.com/", map[string]bool{"other.example.com": true}); err == nil {
		t.Error("a host not in the allowlist must be refused")
	}
	if err := validateHookRegistration("https://hooks.example.com/", map[string]bool{"hooks.example.com": true}); err != nil {
		t.Errorf("an allowlisted host must pass, got: %v", err)
	}
}

// item 2c: at dispatch, hosts resolving to private/loopback/link-local/
// unspecified addresses are refused unless explicitly allowlisted.
func TestValidateHookDispatch_BlocksPrivate(t *testing.T) {
	t.Setenv("AGENTBASE_ALLOW_HTTP_HOOKS", "")
	notListed := map[string]bool{"other.example.com": true}
	for _, u := range []string{
		"https://169.254.169.254/", // link-local (cloud metadata)
		"https://127.0.0.1/",       // loopback
		"https://10.0.0.1/",        // private
		"https://0.0.0.0/",         // unspecified
	} {
		err := validateHookDispatch(u, notListed)
		if err == nil {
			t.Errorf("dispatch should refuse %q", u)
			continue
		}
		if !strings.Contains(err.Error(), "blocked address") {
			t.Errorf("dispatch refusal for %q should cite the blocked address, got: %v", u, err)
		}
	}
	// Explicit allowlist entry is the documented override (item 2c).
	if err := validateHookDispatch("https://169.254.169.254/", map[string]bool{"169.254.169.254": true}); err != nil {
		t.Errorf("an explicitly allowlisted host should bypass the IP block, got: %v", err)
	}
	// A public address that is allowlisted passes.
	if err := validateHookDispatch("https://93.184.216.34/", map[string]bool{"93.184.216.34": true}); err != nil {
		t.Errorf("an allowlisted public address should pass, got: %v", err)
	}
}

// item 4: transaction ids are random hex, not time-based, and unique.
func TestNewTxHash_RandomUnique(t *testing.T) {
	a, err := newTxHash()
	if err != nil {
		t.Fatalf("newTxHash: %v", err)
	}
	b, err := newTxHash()
	if err != nil {
		t.Fatalf("newTxHash: %v", err)
	}
	if a == b {
		t.Error("two transaction ids must differ")
	}
	if !strings.HasPrefix(a, "tx_") || len(a) != len("tx_")+32 {
		t.Errorf("tx id must be tx_ + 32 hex chars, got %q", a)
	}
}

// item 5: amount validation rejects non-whole, out-of-range and non-finite.
func TestValidateAmount(t *testing.T) {
	ok := []float64{1, 500, 1 << 53}
	for _, a := range ok {
		if err := validateAmount(a); err != nil {
			t.Errorf("amount %v should be valid, got: %v", a, err)
		}
	}
	// Note: in IEEE-754 float64, (1<<53)+1 rounds down to 1<<53 (same bit pattern);
	// (1<<53)+2 is the first representable float64 strictly past 2^53.
	bad := []float64{0, -5, 1.5, 500.01, (1 << 53) + 2, math.NaN(), math.Inf(1), math.Inf(-1)}
	for _, a := range bad {
		if err := validateAmount(a); err == nil {
			t.Errorf("amount %v should be rejected", a)
		}
	}
}

// item 5 (integration): a fractional amount is rejected and writes no rows.
func TestTransact_RejectsFractionalAmount(t *testing.T) {
	s := newTestServer(t)
	mustSetup(t, s)
	if _, err := s.doTransact("a", "b", 10.5, ""); err == nil {
		t.Fatal("expected a fractional amount to be rejected")
	}
	if n := len(ledgerRows(t, s)); n != 0 {
		t.Fatalf("expected no ledger rows after a rejected amount, got %d", n)
	}
}
