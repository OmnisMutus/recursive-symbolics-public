package apis

import "testing"

func TestParseCondition(t *testing.T) {
	cases := []struct {
		raw     string
		wantF   string
		wantOp  string
		wantVal string
		wantErr bool
	}{
		// Valid:
		{"amount <= 1000", "amount", "<=", "1000", false},
		{"amount>=50", "amount", ">=", "50", false},
		{"to_account != vault:cold", "to_account", "!=", "vault:cold", false},
		{"from_account == customer:alice", "from_account", "==", "customer:alice", false},
		{"account != vault:hot", "account", "!=", "vault:hot", false},
		{"amount < 10", "amount", "<", "10", false},
		{"amount > 10", "amount", ">", "10", false},
		{"amount == -5", "amount", "==", "-5", false},
		// Errors:
		{"balance <= 10", "", "", "", true},        // unknown field
		{"amount <= ", "", "", "", true},            // missing value
		{"amount 1000", "", "", "", true},           // no operator
		{"", "", "", "", true},                      // empty
		{"amount <= abc", "", "", "", true},         // item 1c: non-numeric amount value
		{"amount == ", "", "", "", true},            // missing value
		{"to_account < vault:x", "", "", "", true},  // item 1c: ordering op on account field
		{"from_account >= x", "", "", "", true},     // item 1c: ordering op on account field
		{"account > x", "", "", "", true},           // item 1c: ordering op on account field
	}
	for _, c := range cases {
		got, err := parseCondition(c.raw)
		if c.wantErr {
			if err == nil {
				t.Errorf("parseCondition(%q): expected error, got %+v", c.raw, got)
			}
			continue
		}
		if err != nil {
			t.Errorf("parseCondition(%q): unexpected error %v", c.raw, err)
			continue
		}
		if got.field != c.wantF || got.op != c.wantOp || got.value != c.wantVal {
			t.Errorf("parseCondition(%q) = {%q %q %q}, want {%q %q %q}",
				c.raw, got.field, got.op, got.value, c.wantF, c.wantOp, c.wantVal)
		}
	}
}

// TestParseConditionLeftmostLongest pins item 1e: split on the LEFTMOST
// operator position, longest operator at that position.
func TestParseConditionLeftmostLongest(t *testing.T) {
	// Longest-at-position: "<=" must win over "<", else value becomes "= 1000".
	c, err := parseCondition("amount <= 1000")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if c.op != "<=" || c.value != "1000" {
		t.Fatalf("longest-at-position: got op=%q value=%q, want <= / 1000", c.op, c.value)
	}

	// Leftmost-position: the "!=" at the left must be chosen even though "=="
	// appears later. A list-order parser would wrongly pick "==" first.
	c, err = parseCondition("from_account != a == b")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if c.field != "from_account" || c.op != "!=" || c.value != "a == b" {
		t.Fatalf("leftmost: got {%q %q %q}, want {from_account != a == b}", c.field, c.op, c.value)
	}
}

func TestConditionHolds_Amount(t *testing.T) {
	mk := func(op, val string) condition { return condition{field: "amount", op: op, value: val} }
	cases := []struct {
		cond   condition
		amount float64
		want   bool
	}{
		{mk("<=", "1000"), 500, true},
		{mk("<=", "1000"), 1000, true},
		{mk("<=", "1000"), 1001, false},
		{mk("<", "1000"), 1000, false},
		{mk(">=", "100"), 100, true},
		{mk(">=", "100"), 99, false},
		{mk(">", "0"), 0, false},
		{mk("==", "42"), 42, true},
		{mk("!=", "42"), 42, false},
		{mk("!=", "42"), 7, true},
	}
	for _, c := range cases {
		if got := c.cond.holds(c.amount, "", ""); got != c.want {
			t.Errorf("holds(amount=%v, %s %s) = %v, want %v",
				c.amount, c.cond.op, c.cond.value, got, c.want)
		}
	}
}

func TestConditionHolds_Accounts(t *testing.T) {
	// to_account != vault:cold  -> satisfied unless to == vault:cold
	deny := condition{field: "to_account", op: "!=", value: "vault:cold"}
	if deny.holds(100, "a", "vault:cold") {
		t.Error("expected violation when to_account == vault:cold")
	}
	if !deny.holds(100, "a", "revenue:subs") {
		t.Error("expected satisfied when to_account != vault:cold")
	}

	// from_account == customer:alice
	only := condition{field: "from_account", op: "==", value: "customer:alice"}
	if !only.holds(1, "customer:alice", "x") {
		t.Error("expected satisfied when from == customer:alice")
	}
	if only.holds(1, "customer:bob", "x") {
		t.Error("expected violation when from != customer:alice")
	}

	// account != vault:x applies to BOTH endpoints
	both := condition{field: "account", op: "!=", value: "vault:x"}
	if both.holds(1, "vault:x", "y") {
		t.Error("expected violation when from endpoint == vault:x")
	}
	if both.holds(1, "y", "vault:x") {
		t.Error("expected violation when to endpoint == vault:x")
	}
	if !both.holds(1, "y", "z") {
		t.Error("expected satisfied when neither endpoint == vault:x")
	}
}

// TestConditionHolds_CannotEvaluateIsFalse pins item 1d: any condition holds()
// cannot evaluate is a violation (false), never allowed (true).
func TestConditionHolds_CannotEvaluateIsFalse(t *testing.T) {
	// Non-numeric value for a numeric field: was previously allowed; now blocks.
	if (condition{field: "amount", op: "<=", value: "not-a-number"}).holds(999999, "a", "b") {
		t.Error("non-numeric amount value must be a violation (false), not allowed")
	}
	// Ordering operator on a string field cannot be evaluated: violation.
	if (condition{field: "to_account", op: "<", value: "zzz"}).holds(1, "a", "anything") {
		t.Error("ordering op on a string field must be a violation (false)")
	}
	if (condition{field: "from_account", op: ">=", value: "x"}).holds(1, "a", "b") {
		t.Error("ordering op on from_account must be a violation (false)")
	}
	// Unknown field cannot be evaluated: violation.
	if (condition{field: "mystery", op: "==", value: "x"}).holds(1, "a", "b") {
		t.Error("unknown field must be a violation (false)")
	}
	// Unknown operator on amount: violation.
	if (condition{field: "amount", op: "~", value: "10"}).holds(1, "a", "b") {
		t.Error("unknown operator must be a violation (false)")
	}
}

func TestCheckBearer(t *testing.T) {
	const key = "s3cr3t-token"
	cases := []struct {
		name   string
		header string
		key    string
		want   bool
	}{
		{"valid", "Bearer s3cr3t-token", key, true},
		{"wrong token", "Bearer nope", key, false},
		{"no prefix", "s3cr3t-token", key, false},
		{"lowercase scheme", "bearer s3cr3t-token", key, false},
		{"empty header", "", key, false},
		{"empty key disables", "Bearer s3cr3t-token", "", false}, // fail-closed
		{"empty token", "Bearer ", key, false},
		{"token is prefix of key", "Bearer s3cr3t", key, false},
		{"token has extra suffix", "Bearer s3cr3t-token-extra", key, false},
	}
	for _, c := range cases {
		if got := checkBearer(c.header, c.key); got != c.want {
			t.Errorf("%s: checkBearer(%q, %q) = %v, want %v", c.name, c.header, c.key, got, c.want)
		}
	}
}
