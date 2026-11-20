package apis

import (
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"math"
	"regexp"
	"strconv"
	"strings"

	"github.com/pocketbase/dbx"
	"github.com/pocketbase/pocketbase/core"
)

var validFieldName = regexp.MustCompile(`^[a-zA-Z][a-zA-Z0-9_]{0,63}$`)

var reservedPocketBaseFields = map[string]bool{
	"id":             true,
	"created":        true,
	"updated":        true,
	"collectionid":   true,
	"collectionname": true,
	"expand":         true,
}

type balanceRow struct {
	Account string `db:"account" json:"account"`
	Balance int64  `db:"balance" json:"balance"`
	Entries int    `db:"entries" json:"entries"`
}

// baseCurrency reads the configured base currency from business_meta, or "BASE".
func (s *AgentBaseMCPServer) baseCurrency(app core.App) string {
	rec, err := app.FindFirstRecordByFilter("business_meta", "key = 'currency'")
	if err != nil || rec == nil {
		return "BASE"
	}
	if v := rec.GetString("value"); v != "" {
		return v
	}
	return "BASE"
}

// splitSchemaSpecs splits on top-level commas so commas inside select(a,b,c)
// are preserved.
func splitSchemaSpecs(raw string) ([]string, error) {
	var parts []string
	depth := 0
	start := 0
	for i := 0; i < len(raw); i++ {
		switch raw[i] {
		case '(':
			depth++
		case ')':
			depth--
			if depth < 0 {
				return nil, fmt.Errorf("unmatched ')' in customer_schema")
			}
		case ',':
			if depth == 0 {
				parts = append(parts, raw[start:i])
				start = i + 1
			}
		}
	}
	if depth != 0 {
		return nil, fmt.Errorf("unclosed '(' in customer_schema")
	}
	parts = append(parts, raw[start:])
	return parts, nil
}

// parseCustomerSchema converts compact 'field:type' specs into PocketBase fields.
// Supported types: text, email, number, bool, url, select(opt1,opt2,...).
func parseCustomerSchema(raw string) ([]core.Field, error) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return nil, nil
	}
	specs, err := splitSchemaSpecs(raw)
	if err != nil {
		return nil, err
	}
	seen := map[string]bool{}
	var fields []core.Field
	for _, spec := range specs {
		spec = strings.TrimSpace(spec)
		if spec == "" {
			return nil, fmt.Errorf("empty field entry in customer_schema")
		}
		colon := strings.IndexByte(spec, ':')
		if colon <= 0 {
			return nil, fmt.Errorf("invalid field spec %q; expected name:type", spec)
		}
		name := strings.TrimSpace(spec[:colon])
		typ := strings.TrimSpace(spec[colon+1:])
		if !validFieldName.MatchString(name) {
			return nil, fmt.Errorf("invalid field name %q", name)
		}
		lower := strings.ToLower(name)
		if reservedPocketBaseFields[lower] {
			return nil, fmt.Errorf("field name %q is reserved by PocketBase", name)
		}
		if seen[lower] {
			return nil, fmt.Errorf("duplicate field name %q in customer_schema", name)
		}
		seen[lower] = true

		switch {
		case typ == "text":
			fields = append(fields, &core.TextField{Name: name})
		case typ == "email":
			fields = append(fields, &core.EmailField{Name: name})
		case typ == "number":
			fields = append(fields, &core.NumberField{Name: name})
		case typ == "bool":
			fields = append(fields, &core.BoolField{Name: name})
		case typ == "url":
			fields = append(fields, &core.URLField{Name: name})
		case strings.HasPrefix(typ, "select(") && strings.HasSuffix(typ, ")"):
			inner := typ[len("select(") : len(typ)-1]
			var vals []string
			for _, v := range strings.Split(inner, ",") {
				if v = strings.TrimSpace(v); v != "" {
					vals = append(vals, v)
				}
			}
			if len(vals) == 0 {
				return nil, fmt.Errorf("select field %q must list at least one option", name)
			}
			fields = append(fields, &core.SelectField{Name: name, Values: vals, MaxSelect: 1})
		default:
			return nil, fmt.Errorf("unsupported field type %q for %q", typ, name)
		}
	}
	return fields, nil
}

func (s *AgentBaseMCPServer) doSetupBusiness(name, curr string) (string, error) {
	return s.doSetupBusinessWithSchema(name, curr, "")
}

func (s *AgentBaseMCPServer) doSetupBusinessWithSchema(name, curr, customerSchema string) (string, error) {
	name = strings.TrimSpace(name)
	curr = strings.TrimSpace(curr)
	if name == "" {
		return "", fmt.Errorf("business_name must not be empty")
	}
	if curr == "" {
		return "", fmt.Errorf("currency must not be empty")
	}
	extraFields, err := parseCustomerSchema(customerSchema)
	if err != nil {
		return "", err
	}

	existed := false
	err = s.app.RunInTransaction(func(txApp core.App) error {
		if _, e := txApp.FindCollectionByNameOrId("business_meta"); e == nil {
			existed = true
		}

		if _, e := txApp.FindCollectionByNameOrId("ledger"); e != nil {
			c := core.NewBaseCollection("ledger")
			c.Fields.Add(&core.TextField{Name: "account", Required: true})
			c.Fields.Add(&core.NumberField{Name: "amount", Required: true}) // debit (-) / credit (+)
			c.Fields.Add(&core.TextField{Name: "currency", Required: true})
			c.Fields.Add(&core.TextField{Name: "tx_hash", Required: true})
			c.Fields.Add(&core.TextField{Name: "memo"})
			if e := txApp.Save(c); e != nil {
				return fmt.Errorf("failed to create ledger: %w", e)
			}
		}

		if _, e := txApp.FindCollectionByNameOrId("business_meta"); e != nil {
			c := core.NewBaseCollection("business_meta")
			c.Fields.Add(&core.TextField{Name: "key", Required: true})
			c.Fields.Add(&core.TextField{Name: "value", Required: true})
			if e := txApp.Save(c); e != nil {
				return e
			}
			for k, v := range map[string]string{"name": name, "currency": curr} {
				r := core.NewRecord(c)
				r.Set("key", k)
				r.Set("value", v)
				if e := txApp.Save(r); e != nil {
					return e
				}
			}
		}

		if _, e := txApp.FindCollectionByNameOrId("policies"); e != nil {
			c := core.NewBaseCollection("policies")
			c.Fields.Add(&core.TextField{Name: "rule_name", Required: true})
			c.Fields.Add(&core.TextField{Name: "condition", Required: true})
			if e := txApp.Save(c); e != nil {
				return e
			}
		}

		if _, e := txApp.FindCollectionByNameOrId("hooks"); e != nil {
			c := core.NewBaseCollection("hooks")
			c.Fields.Add(&core.TextField{Name: "event", Required: true})
			c.Fields.Add(&core.TextField{Name: "action_webhook", Required: true})
			if e := txApp.Save(c); e != nil {
				return e
			}
		}

		if _, e := txApp.FindCollectionByNameOrId("agents"); e != nil {
			c := core.NewBaseCollection("agents")
			c.Fields.Add(&core.TextField{Name: "agent_id", Required: true})
			c.Fields.Add(&core.TextField{Name: "pubkey_hex", Required: true})
			c.Fields.Add(&core.TextField{Name: "role", Required: true})
			if e := txApp.Save(c); e != nil {
				return e
			}
		}

		// One row per (agent, nonce) ever accepted. The unique index is what
		// stops a replay even if two copies race; the lookup in recordNonceTx
		// only gives the clean error message.
		if _, e := txApp.FindCollectionByNameOrId("agent_nonces"); e != nil {
			c := core.NewBaseCollection("agent_nonces")
			c.Fields.Add(&core.TextField{Name: "agent_id", Required: true})
			c.Fields.Add(&core.TextField{Name: "nonce", Required: true})
			c.Fields.Add(&core.TextField{Name: "tx_hash", Required: true})
			c.AddIndex("idx_agent_nonces_agent_nonce", true, "agent_id, nonce", "")
			if e := txApp.Save(c); e != nil {
				return e
			}
		}

		if len(extraFields) > 0 {
			if _, e := txApp.FindCollectionByNameOrId("customers"); e != nil {
				c := core.NewBaseCollection("customers")
				for _, f := range extraFields {
					c.Fields.Add(f)
				}
				if e := txApp.Save(c); e != nil {
					return fmt.Errorf("failed to create customers collection: %w", e)
				}
			}
		}
		return nil
	})
	if err != nil {
		return "", fmt.Errorf("failed to initialize business: %w", err)
	}

	if existed {
		stored := s.baseCurrency(s.app)
		return fmt.Sprintf(
			"NOTE: A business already existed; it was left unchanged. Stored base currency: %s (the requested %q was ignored).",
			stored, curr), nil
	}
	if len(extraFields) > 0 {
		return fmt.Sprintf(
			"SUCCESS: Business '%s' initialized. Base currency: %s. Ledger, policy, hook, agent and customers (%d fields) collections ready.",
			name, curr, len(extraFields)), nil
	}
	return fmt.Sprintf(
		"SUCCESS: Business '%s' initialized. Base currency: %s. Ledger, policy, hook and agent collections ready.",
		name, curr), nil
}

// validateAmount enforces whole-number, in-range, finite amounts.
func validateAmount(amount float64) error {
	if math.IsNaN(amount) || math.IsInf(amount, 0) {
		return fmt.Errorf("amount must be a finite number")
	}
	if amount <= 0 {
		return fmt.Errorf("amount must be strictly greater than 0")
	}
	if amount != math.Trunc(amount) {
		return fmt.Errorf("amount must be a whole number (the smallest currency unit), got %s", formatAmount(amount))
	}
	if amount > maxAmount {
		return fmt.Errorf("amount exceeds the maximum of 2^53 (%d)", int64(maxAmount))
	}
	return nil
}

func formatAmount(amount float64) string {
	return strconv.FormatFloat(amount, 'f', -1, 64)
}

func newTxHash() (string, error) {
	var b [16]byte
	if _, err := rand.Read(b[:]); err != nil {
		return "", fmt.Errorf("could not generate a transaction id: %w", err)
	}
	return "tx_" + hex.EncodeToString(b[:]), nil
}

func (s *AgentBaseMCPServer) doTransact(fromAcc, toAcc string, amount float64, memo string) (string, error) {
	return s.doSignedTransact(fromAcc, toAcc, amount, memo, "", "", "")
}

func (s *AgentBaseMCPServer) doSignedTransact(fromAcc, toAcc string, amount float64, memo, agentID, sigHex, nonce string) (string, error) {
	fromAcc = strings.TrimSpace(fromAcc)
	toAcc = strings.TrimSpace(toAcc)
	if fromAcc == "" || toAcc == "" {
		return "", fmt.Errorf("from_account and to_account must not be empty")
	}
	if fromAcc == toAcc {
		return "", fmt.Errorf("from_account and to_account must differ (%q)", fromAcc)
	}
	if err := validateAmount(amount); err != nil {
		return "", err
	}
	agentID = strings.TrimSpace(agentID)
	signed := agentID != "" || strings.TrimSpace(sigHex) != "" || nonce != ""
	if signed {
		// A signed transfer needs all three. Accepting a signature without a
		// nonce would bring back the replay this check exists to stop.
		if agentID == "" || strings.TrimSpace(sigHex) == "" || nonce == "" {
			return "", fmt.Errorf("transaction aborted: a signed transfer needs agent_id, signature and nonce together")
		}
		if !validNonce.MatchString(nonce) {
			return "", fmt.Errorf("transaction aborted: nonce must be 1-128 characters from [A-Za-z0-9._:-]")
		}
	}

	txHash, err := newTxHash()
	if err != nil {
		return "", err
	}

	err = s.app.RunInTransaction(func(txApp core.App) error {
		col, e := txApp.FindCollectionByNameOrId("ledger")
		if e != nil {
			return fmt.Errorf("ledger not initialized; call setup_business first: %w", e)
		}
		if signed {
			payload := txSigningPayload(agentID, fromAcc, toAcc, amount, memo, nonce)
			if e := verifyAgentSignatureTx(txApp, agentID, payload, sigHex); e != nil {
				return e
			}
			if e := recordNonceTx(txApp, agentID, nonce, txHash); e != nil {
				return e
			}
		}
		if e := s.enforcePolicies(txApp, amount, fromAcc, toAcc); e != nil {
			return e
		}
		currency := s.baseCurrency(txApp)

		r1 := core.NewRecord(col)
		r1.Set("account", fromAcc)
		r1.Set("amount", -amount)
		r1.Set("currency", currency)
		r1.Set("tx_hash", txHash)
		r1.Set("memo", memo)
		if e := txApp.Save(r1); e != nil {
			return e
		}

		r2 := core.NewRecord(col)
		r2.Set("account", toAcc)
		r2.Set("amount", amount)
		r2.Set("currency", currency)
		r2.Set("tx_hash", txHash)
		r2.Set("memo", memo)
		return txApp.Save(r2)
	})
	if err != nil {
		return "", fmt.Errorf("transaction aborted: %w", err)
	}

	return fmt.Sprintf(
		"TRANSACTION POSTED: [Hash: %s] Transferred %s from [%s] to [%s]. Zero-balance invariant preserved.",
		txHash, formatAmount(amount), fromAcc, toAcc), nil
}

func (s *AgentBaseMCPServer) doQueryLedger(acc string) (string, error) {
	acc = strings.TrimSpace(acc)
	if acc == "" {
		return "", fmt.Errorf("account must not be empty (pass '*' for all accounts)")
	}
	if _, err := s.app.FindCollectionByNameOrId("ledger"); err != nil {
		return "", fmt.Errorf("ledger not initialized; call setup_business first")
	}

	results := []balanceRow{}
	query := s.app.DB().
		Select("account", "CAST(COALESCE(SUM(amount), 0) AS INTEGER) as balance", "COUNT(*) as entries").
		From("ledger")
	if acc != "*" {
		query = query.Where(dbx.HashExp{"account": acc})
	}
	query = query.GroupBy("account").OrderBy("account ASC")
	if err := query.All(&results); err != nil {
		return "", fmt.Errorf("failed to query ledger: %w", err)
	}
	out, _ := json.MarshalIndent(results, "", "  ")
	return string(out), nil
}
