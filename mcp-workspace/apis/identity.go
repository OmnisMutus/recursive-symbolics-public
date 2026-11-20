package apis

import (
	"crypto/ed25519"
	"encoding/hex"
	"errors"
	"fmt"
	"regexp"
	"strconv"
	"strings"

	"github.com/pocketbase/dbx"
	"github.com/pocketbase/pocketbase/core"
)

func decodePubKey(pubkeyHex string) (ed25519.PublicKey, error) {
	raw, err := hex.DecodeString(strings.TrimSpace(pubkeyHex))
	if err != nil {
		return nil, fmt.Errorf("invalid pubkey hex: %w", err)
	}
	if len(raw) != ed25519.PublicKeySize {
		return nil, fmt.Errorf("ed25519 public key must be %d bytes (%d hex chars), got %d bytes",
			ed25519.PublicKeySize, ed25519.PublicKeySize*2, len(raw))
	}
	return ed25519.PublicKey(raw), nil
}

func decodeSignature(sigHex string) ([]byte, error) {
	sig, err := hex.DecodeString(strings.TrimSpace(sigHex))
	if err != nil {
		return nil, fmt.Errorf("invalid signature hex: %w", err)
	}
	if len(sig) != ed25519.SignatureSize {
		return nil, fmt.Errorf("ed25519 signature must be %d bytes (%d hex chars), got %d bytes",
			ed25519.SignatureSize, ed25519.SignatureSize*2, len(sig))
	}
	return sig, nil
}

// txSigningDomain tags the signed payload so a signature made for a transfer
// cannot be presented as a signature over any other kind of message.
const txSigningDomain = "agentbase.transact.v2"

// validNonce bounds what a client may send as a nonce. Any value is fine as
// long as the same agent never uses it twice; the bound keeps rows small.
var validNonce = regexp.MustCompile(`^[A-Za-z0-9._:-]{1,128}$`)

// netstring encodes s as "<byte length>:<s>,". A sequence of netstrings has
// exactly one parse, which the old "from|to|amount|memo" join did not: the
// transfers "a|b" -> "c" and "a" -> "b|c" produced the same signed bytes.
func netstring(s string) string {
	return strconv.Itoa(len(s)) + ":" + s + ","
}

// txSigningPayload is the exact byte string an agent signs to authorize a
// transfer. It binds the agent, both accounts, the amount, the memo and a
// nonce the agent must never reuse. Accounts are the trimmed values transact
// stores; memo and nonce are used as sent.
func txSigningPayload(agentID, fromAcc, toAcc string, amount float64, memo, nonce string) string {
	var b strings.Builder
	for _, f := range []string{txSigningDomain, agentID, fromAcc, toAcc, formatAmount(amount), memo, nonce} {
		b.WriteString(netstring(f))
	}
	return b.String()
}

// errNonceReused is returned when an agent presents a nonce it already used.
var errNonceReused = errors.New("nonce already used by this agent; replay rejected")

// recordNonceTx rejects a nonce the agent has used before and records it.
// It must run inside the same transaction as the ledger write, so a replay
// either finds the earlier row or fails on the unique index; in both cases
// the whole transfer rolls back.
func recordNonceTx(txApp core.App, agentID, nonce, txHash string) error {
	col, err := txApp.FindCollectionByNameOrId("agent_nonces")
	if err != nil {
		return fmt.Errorf("agent_nonces collection not initialized; call setup_business again (fail closed)")
	}
	if existing, err := txApp.FindFirstRecordByFilter("agent_nonces",
		"agent_id = {:a} && nonce = {:n}", dbx.Params{"a": agentID, "n": nonce}); err == nil && existing != nil {
		return errNonceReused
	}
	rec := core.NewRecord(col)
	rec.Set("agent_id", agentID)
	rec.Set("nonce", nonce)
	rec.Set("tx_hash", txHash)
	if err := txApp.Save(rec); err != nil {
		return fmt.Errorf("could not record nonce (fail closed): %w", err)
	}
	return nil
}

func (s *AgentBaseMCPServer) doRegisterAgent(agentID, pubkeyHex, role string) (string, error) {
	agentID = strings.TrimSpace(agentID)
	if agentID == "" {
		return "", fmt.Errorf("agent_id must not be empty")
	}
	role = strings.TrimSpace(role)
	if role == "" {
		role = "worker"
	}
	pub, err := decodePubKey(pubkeyHex)
	if err != nil {
		return "", err
	}
	normalizedHex := hex.EncodeToString(pub)

	col, err := s.app.FindCollectionByNameOrId("agents")
	if err != nil {
		return "", fmt.Errorf("agents collection not initialized; call setup_business first")
	}
	if existing, err := s.app.FindFirstRecordByFilter("agents", "agent_id = {:id}", dbx.Params{"id": agentID}); err == nil && existing != nil {
		return "", fmt.Errorf("agent [%s] already registered", agentID)
	}
	rec := core.NewRecord(col)
	rec.Set("agent_id", agentID)
	rec.Set("pubkey_hex", normalizedHex)
	rec.Set("role", role)
	if err := s.app.Save(rec); err != nil {
		return "", fmt.Errorf("failed to register agent [%s]: %w", agentID, err)
	}
	return fmt.Sprintf("AGENT REGISTERED: [%s] role=%s pubkey=%s", agentID, role, normalizedHex), nil
}

func verifyAgentSignatureTx(app core.App, agentID, message, sigHex string) error {
	agentID = strings.TrimSpace(agentID)
	if agentID == "" {
		return fmt.Errorf("agent_id is required for signature verification")
	}
	sig, err := decodeSignature(sigHex)
	if err != nil {
		return err
	}
	if _, err := app.FindCollectionByNameOrId("agents"); err != nil {
		return fmt.Errorf("agents collection not initialized; call setup_business first")
	}
	rec, err := app.FindFirstRecordByFilter("agents", "agent_id = {:id}", dbx.Params{"id": agentID})
	if err != nil || rec == nil {
		return fmt.Errorf("unknown agent [%s]; verification failed (fail closed)", agentID)
	}
	pub, err := decodePubKey(rec.GetString("pubkey_hex"))
	if err != nil {
		return fmt.Errorf("stored public key for agent [%s] is invalid (fail closed): %w", agentID, err)
	}
	if !ed25519.Verify(pub, []byte(message), sig) {
		return fmt.Errorf("invalid ed25519 signature for agent [%s]", agentID)
	}
	return nil
}

func (s *AgentBaseMCPServer) doVerifySignature(agentID, message, sigHex string) (string, error) {
	if err := verifyAgentSignatureTx(s.app, agentID, message, sigHex); err != nil {
		return "", err
	}
	return fmt.Sprintf("SIGNATURE VERIFIED: valid ed25519 signature for agent [%s]", strings.TrimSpace(agentID)), nil
}
