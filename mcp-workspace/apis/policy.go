package apis

import (
	"encoding/json"
	"fmt"
	"strconv"
	"strings"

	"github.com/pocketbase/dbx"
	"github.com/pocketbase/pocketbase/core"
)

type condition struct {
	field string
	op    string
	value string
}

type policySummary struct {
	RuleName  string `json:"rule_name"`
	Condition string `json:"condition"`
}

// opsLongestFirst lists operators so that, at a given position, a 2-char
// operator is matched before its 1-char prefix ("<=" before "<").
var opsLongestFirst = []string{"<=", ">=", "==", "!=", "<", ">"}

// parseCondition splits on the LEFTMOST operator position, taking the longest
// operator at that position, and validates the field/op/value combination so
// invalid policies are rejected at creation.
func parseCondition(raw string) (condition, error) {
	pos, matched := -1, ""
	for i := 0; i < len(raw) && pos == -1; i++ {
		for _, op := range opsLongestFirst {
			if strings.HasPrefix(raw[i:], op) {
				pos, matched = i, op
				break
			}
		}
	}
	if pos == -1 {
		return condition{}, fmt.Errorf("no recognized operator in %q", raw)
	}
	field := strings.TrimSpace(raw[:pos])
	value := strings.TrimSpace(raw[pos+len(matched):])
	if value == "" {
		return condition{}, fmt.Errorf("missing value in %q", raw)
	}
	switch field {
	case "amount", "from_balance_after":
		if _, e := strconv.ParseFloat(value, 64); e != nil {
			return condition{}, fmt.Errorf("%s condition needs a numeric value, got %q", field, value)
		}
	case "from_account", "to_account", "account":
		if matched != "==" && matched != "!=" {
			return condition{}, fmt.Errorf("account field %q allows only == or !=, not %q", field, matched)
		}
	default:
		return condition{}, fmt.Errorf("unknown field %q", field)
	}
	return condition{field: field, op: matched, value: value}, nil
}

// doCreatePolicy validates and persists a uniquely named policy.
func (s *AgentBaseMCPServer) doCreatePolicy(name, cond string) (string, error) {
	name = strings.TrimSpace(name)
	if name == "" {
		return "", fmt.Errorf("rule_name must not be empty")
	}
	if _, perr := parseCondition(cond); perr != nil {
		return "", fmt.Errorf("invalid condition: %w", perr)
	}
	col, err := s.app.FindCollectionByNameOrId("policies")
	if err != nil {
		return "", fmt.Errorf("policies collection not initialized; call setup_business first")
	}
	existing, err := s.app.FindFirstRecordByFilter("policies", "rule_name = {:name}", dbx.Params{"name": name})
	if err == nil && existing != nil {
		return "", fmt.Errorf("policy [%s] already exists; call delete_policy first before replacing it", name)
	}
	rec := core.NewRecord(col)
	rec.Set("rule_name", name)
	rec.Set("condition", cond)
	if err := s.app.Save(rec); err != nil {
		return "", fmt.Errorf("failed to persist policy: %w", err)
	}
	return fmt.Sprintf("POLICY ACTIVE: Rule [%s] persisted and enforced in-kernel: '%s'", name, cond), nil
}

// doListPolicies returns all active policy rules as formatted JSON.
func (s *AgentBaseMCPServer) doListPolicies() (string, error) {
	if _, err := s.app.FindCollectionByNameOrId("policies"); err != nil {
		return "", fmt.Errorf("policies collection not initialized; call setup_business first")
	}
	recs, err := s.app.FindAllRecords("policies")
	if err != nil {
		return "", fmt.Errorf("failed to list policies: %w", err)
	}
	out := make([]policySummary, 0, len(recs))
	for _, r := range recs {
		out = append(out, policySummary{
			RuleName:  r.GetString("rule_name"),
			Condition: r.GetString("condition"),
		})
	}
	raw, _ := json.MarshalIndent(out, "", "  ")
	return string(raw), nil
}

// doDeletePolicy removes a named policy rule.
func (s *AgentBaseMCPServer) doDeletePolicy(name string) (string, error) {
	name = strings.TrimSpace(name)
	if name == "" {
		return "", fmt.Errorf("rule_name must not be empty")
	}
	if _, err := s.app.FindCollectionByNameOrId("policies"); err != nil {
		return "", fmt.Errorf("policies collection not initialized; call setup_business first")
	}
	rec, err := s.app.FindFirstRecordByFilter("policies", "rule_name = {:name}", dbx.Params{"name": name})
	if err != nil || rec == nil {
		return "", fmt.Errorf("policy [%s] not found", name)
	}
	if err := s.app.Delete(rec); err != nil {
		return "", fmt.Errorf("failed to delete policy [%s]: %w", name, err)
	}
	return fmt.Sprintf("POLICY DELETED: Rule [%s] removed", name), nil
}

// accountBalanceTx computes the exact current net balance of account inside txApp.
func accountBalanceTx(txApp core.App, account string) (float64, error) {
	var row struct {
		Bal float64 `db:"bal"`
	}
	err := txApp.DB().
		Select("COALESCE(SUM(amount), 0) as bal").
		From("ledger").
		Where(dbx.HashExp{"account": account}).
		One(&row)
	return row.Bal, err
}

// enforcePolicies loads all policies and aborts the transaction on any
// violation. It fails CLOSED: a load error other than a missing collection
// aborts, and an unparseable stored condition aborts.
func (s *AgentBaseMCPServer) enforcePolicies(txApp core.App, amount float64, from, to string) error {
	if _, e := txApp.FindCollectionByNameOrId("policies"); e != nil {
		return nil // collection does not exist: no policies, allow
	}
	recs, err := txApp.FindAllRecords("policies")
	if err != nil {
		return fmt.Errorf("could not load policies; aborting (fail closed): %w", err)
	}

	var fromBalAfter *float64
	for _, r := range recs {
		c, perr := parseCondition(r.GetString("condition"))
		if perr != nil {
			return fmt.Errorf("policy [%s] has an unparseable condition %q; aborting (fail closed): %v",
				r.GetString("rule_name"), r.GetString("condition"), perr)
		}
		if c.field == "from_balance_after" {
			if fromBalAfter == nil {
				curBal, berr := accountBalanceTx(txApp, from)
				if berr != nil {
					return fmt.Errorf("could not compute balance for %q; aborting (fail closed): %w", from, berr)
				}
				after := curBal - amount
				fromBalAfter = &after
			}
			if !c.holdsBalance(*fromBalAfter) {
				return fmt.Errorf("policy violation [%s]: '%s' (post-tx balance %.0f)",
					r.GetString("rule_name"), r.GetString("condition"), *fromBalAfter)
			}
			continue
		}
		if !c.holds(amount, from, to) {
			return fmt.Errorf("policy violation [%s]: '%s'", r.GetString("rule_name"), r.GetString("condition"))
		}
	}
	return nil
}

func (c condition) holdsBalance(balanceAfter float64) bool {
	if c.field != "from_balance_after" {
		return false
	}
	return numCompare(balanceAfter, c.op, c.value)
}

// holds reports whether the transaction satisfies the condition. Any case it
// cannot evaluate returns false (a violation), never true.
func (c condition) holds(amount float64, from, to string) bool {
	switch c.field {
	case "amount":
		return numCompare(amount, c.op, c.value)
	case "from_account":
		return strCompare(from, c.op, c.value)
	case "to_account":
		return strCompare(to, c.op, c.value)
	case "account": // applies to BOTH endpoints
		return strCompare(from, c.op, c.value) && strCompare(to, c.op, c.value)
	default:
		return false
	}
}

func numCompare(got float64, op, rawWant string) bool {
	want, err := strconv.ParseFloat(rawWant, 64)
	if err != nil {
		return false
	}
	switch op {
	case "<=":
		return got <= want
	case ">=":
		return got >= want
	case "<":
		return got < want
	case ">":
		return got > want
	case "==":
		return got == want
	case "!=":
		return got != want
	default:
		return false
	}
}

func strCompare(got, op, want string) bool {
	switch op {
	case "==":
		return got == want
	case "!=":
		return got != want
	default:
		return false
	}
}
