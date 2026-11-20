package apis

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"log/slog"
	"math"
	"net"
	"strings"
	"sync"
	"testing"

	"github.com/pocketbase/pocketbase/core"
)

// These tests were written during the break-it pass (STANDARD.md): each one
// exists because disabling a guard left the earlier suite green.

// A failure to compute the sender's balance must abort, not read as zero.
func TestEnforcePolicies_AbortsOnBalanceError(t *testing.T) {
	s := newTestServer(t)
	mustSetup(t, s)
	// Loose enough that a balance silently read as 0 would pass (0 - 1 >= -1000000).
	if _, err := s.doCreatePolicy("floor", "from_balance_after >= -1000000"); err != nil {
		t.Fatalf("policy: %v", err)
	}
	if _, err := s.app.DB().NewQuery("DROP TABLE ledger").Execute(); err != nil {
		t.Fatalf("drop ledger: %v", err)
	}
	err := s.enforcePolicies(s.app, 1, "a", "b")
	if err == nil || !strings.Contains(err.Error(), "could not compute balance") {
		t.Fatalf("expected fail-closed balance error, got: %v", err)
	}
}

// fakeNet swaps the hook resolver and dialer for the test and records every
// address the client tries to dial.
type fakeNet struct {
	mu     sync.Mutex
	dialed []string
}

var errFakeDial = errors.New("fake dial: recorded, not connected")

func installFakeNet(t *testing.T, answers map[string][]net.IP) *fakeNet {
	t.Helper()
	f := &fakeNet{}
	oldLookup, oldDial := hookLookupIP, hookDial
	hookLookupIP = func(host string) ([]net.IP, error) {
		if ips, ok := answers[host]; ok {
			return ips, nil
		}
		return nil, fmt.Errorf("fake resolver: no answer for %q", host)
	}
	hookDial = func(ctx context.Context, network, addr string) (net.Conn, error) {
		f.mu.Lock()
		f.dialed = append(f.dialed, addr)
		f.mu.Unlock()
		return nil, errFakeDial
	}
	t.Cleanup(func() { hookLookupIP, hookDial = oldLookup, oldDial })
	return f
}

func (f *fakeNet) dials() []string {
	f.mu.Lock()
	defer f.mu.Unlock()
	return append([]string(nil), f.dialed...)
}

// The dial goes to the IP that was checked, not back to the hostname (which
// would let the OS resolve again and land somewhere else).
func TestSafeWebhookClient_DialUsesValidatedIP(t *testing.T) {
	t.Setenv("AGENTBASE_ALLOW_HTTP_HOOKS", "")
	f := installFakeNet(t, map[string][]net.IP{"pin.invalid": {net.ParseIP("93.184.216.34")}})
	c := safeWebhookClient(map[string]bool{"pin.invalid": true})
	_, err := c.Post("https://pin.invalid/hook", "application/json", strings.NewReader("{}"))
	if err == nil {
		t.Fatal("expected the fake dial error")
	}
	if got := f.dials(); len(got) != 1 || got[0] != "93.184.216.34:443" {
		t.Fatalf("dialed %v, want exactly [93.184.216.34:443]", got)
	}
}

// DNS rebinding: a name that resolves to a blocked address at dial time is
// refused before any connection, even if every answer but one is public.
func TestSafeWebhookClient_DialRefusesBlockedAnswer(t *testing.T) {
	t.Setenv("AGENTBASE_ALLOW_HTTP_HOOKS", "")
	for name, ips := range map[string][]net.IP{
		"loop.invalid":  {net.ParseIP("127.0.0.1")},
		"mixed.invalid": {net.ParseIP("93.184.216.34"), net.ParseIP("169.254.169.254")},
		"v6.invalid":    {net.ParseIP("::1")},
	} {
		f := installFakeNet(t, map[string][]net.IP{name: ips})
		c := safeWebhookClient(map[string]bool{name: true})
		_, err := c.Post("https://"+name+"/hook", "application/json", strings.NewReader("{}"))
		if err == nil || !strings.Contains(err.Error(), "blocked address") {
			t.Errorf("%s: expected blocked-address refusal, got: %v", name, err)
		}
		if d := f.dials(); len(d) != 0 {
			t.Errorf("%s: dialed %v, want no dial", name, d)
		}
	}
}

// The dial-time allowlist check is independent of the earlier validation:
// a client built with an empty allowlist dials nothing.
func TestSafeWebhookClient_DialEnforcesAllowlist(t *testing.T) {
	f := installFakeNet(t, map[string][]net.IP{"pin.invalid": {net.ParseIP("93.184.216.34")}})
	c := safeWebhookClient(map[string]bool{})
	if _, err := c.Post("https://pin.invalid/hook", "application/json", strings.NewReader("{}")); err == nil {
		t.Fatal("expected refusal with an empty allowlist")
	}
	if d := f.dials(); len(d) != 0 {
		t.Fatalf("dialed %v with an empty allowlist", d)
	}
}

// IPv6 and IPv4-mapped forms of blocked ranges, which the earlier test did
// not cover.
func TestValidateHookDispatch_BlocksIPv6Forms(t *testing.T) {
	t.Setenv("AGENTBASE_ALLOW_HTTP_HOOKS", "")
	notListed := map[string]bool{"other.example.com": true}
	for _, u := range []string{
		"https://[::1]/",              // loopback
		"https://[fe80::1]/",          // link-local unicast
		"https://[fc00::1]/",          // unique local (private)
		"https://[ff02::1]/",          // link-local multicast
		"https://[::]/",               // unspecified
		"https://[::ffff:127.0.0.1]/", // IPv4-mapped loopback
		"https://[::ffff:10.0.0.1]/",  // IPv4-mapped private
	} {
		err := validateHookDispatch(u, notListed)
		if err == nil || !strings.Contains(err.Error(), "blocked address") {
			t.Errorf("dispatch should refuse %q as blocked, got: %v", u, err)
		}
	}
	// An empty allowlist refuses even a public literal at dispatch.
	if err := validateHookDispatch("https://93.184.216.34/", map[string]bool{}); err == nil {
		t.Error("an empty allowlist must refuse at dispatch too")
	}
}

// checkBearer must refuse a whitespace-only key on its own, not only via the
// handler: with key "   ", the header "Bearer    " carries the token "   ".
func TestCheckBearer_WhitespaceKeyDisables(t *testing.T) {
	for _, key := range []string{" ", "   ", "\t"} {
		if checkBearer("Bearer "+key, key) {
			t.Errorf("whitespace key %q accepted a matching whitespace token", key)
		}
	}
	// Leading/trailing whitespace is part of the token: no silent trimming.
	if checkBearer("Bearer  real-key", "real-key") {
		t.Error("token with an extra leading space must not match")
	}
}

// Each rejection gives its own reason, so disabling one check is visible
// even when a later check would also have refused the value.
func TestValidateAmount_Reasons(t *testing.T) {
	for _, tc := range []struct {
		amount float64
		reason string
	}{
		{math.NaN(), "finite"},
		{math.Inf(1), "finite"},
		{math.Inf(-1), "finite"},
		{0, "greater than 0"},
		{-5, "greater than 0"},
		{1.5, "whole number"},
		{(1 << 53) + 2, "2^53"},
		{1e300, "2^53"},
	} {
		err := validateAmount(tc.amount)
		if err == nil || !strings.Contains(err.Error(), tc.reason) {
			t.Errorf("amount %v: want error mentioning %q, got: %v", tc.amount, tc.reason, err)
		}
	}
}

// Step 4: a hook that fails dispatch validation is skipped with a warning that
// names the hook and the reason, and the log never carries the payload or
// the hook URL (which may contain a token).
func TestDispatchHooks_LogsSkippedHook(t *testing.T) {
	t.Setenv("AGENTBASE_HOOK_HOSTS", "hooks.example.com")
	t.Setenv("AGENTBASE_ALLOW_HTTP_HOOKS", "1")

	// A port nothing listens on, for the dispatch-failed path.
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	deadAddr := ln.Addr().String()
	ln.Close()

	s := newTestServer(t)
	mustSetup(t, s)
	var buf bytes.Buffer
	var bufMu sync.Mutex
	s.logger = slog.New(slog.NewTextHandler(&lockedWriter{w: &buf, mu: &bufMu}, nil))

	col, err := s.app.FindCollectionByNameOrId("hooks")
	if err != nil {
		t.Fatalf("hooks collection: %v", err)
	}
	insert := func(u string) string {
		r := core.NewRecord(col)
		r.Set("event", eventLedgerAfterCreate)
		r.Set("action_webhook", u)
		if err := s.app.Save(r); err != nil {
			t.Fatalf("insert hook %q: %v", u, err)
		}
		return r.Id
	}
	// Inserted directly: registration would refuse these, but a stored row can
	// still go bad later (allowlist changed, DNS changed, DB edited).
	blockedID := insert("https://10.0.0.1/hook?token=SECRETMARK1")
	badParseID := insert("https://hooks.example.com/%zz?token=SECRETMARK2")
	t.Setenv("AGENTBASE_HOOK_HOSTS", "hooks.example.com,127.0.0.1")
	deadID := insert("http://" + deadAddr + "/hook?token=SECRETMARK3")

	if _, err := s.doTransact("a", "b", 5, "PAYLOADMARK"); err != nil {
		t.Fatalf("transact: %v", err)
	}
	s.WaitHooks()

	bufMu.Lock()
	out := buf.String()
	bufMu.Unlock()

	for _, want := range []string{
		"webhook skipped: failed dispatch validation",
		"hook_id=" + blockedID, "blocked address",
		"hook_id=" + badParseID, "invalid URL escape",
		"webhook dispatch failed", "hook_id=" + deadID,
	} {
		if !strings.Contains(out, want) {
			t.Errorf("log missing %q\nlog:\n%s", want, out)
		}
	}
	for _, leak := range []string{"PAYLOADMARK", "SECRETMARK1", "SECRETMARK2", "SECRETMARK3"} {
		if strings.Contains(out, leak) {
			t.Errorf("log leaked %q\nlog:\n%s", leak, out)
		}
	}
	// Two ledger rows fire the dispatcher twice: one skip line per bad hook per row.
	if n := strings.Count(out, "hook_id="+blockedID); n != 2 {
		t.Errorf("expected 2 skip lines for the blocked hook, got %d", n)
	}
}

type lockedWriter struct {
	w  *bytes.Buffer
	mu *sync.Mutex
}

func (l *lockedWriter) Write(p []byte) (int, error) {
	l.mu.Lock()
	defer l.mu.Unlock()
	return l.w.Write(p)
}
