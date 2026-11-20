package apis

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"net"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"

	"github.com/pocketbase/dbx"
	"github.com/pocketbase/pocketbase/core"
)

type hookSummary struct {
	ID            string `json:"id"`
	Event         string `json:"event"`
	ActionWebhook string `json:"action_webhook"`
}

func hookAllowlist() map[string]bool {
	out := map[string]bool{}
	for _, h := range strings.Split(os.Getenv("AGENTBASE_HOOK_HOSTS"), ",") {
		if h = strings.ToLower(strings.TrimSpace(h)); h != "" {
			out[h] = true
		}
	}
	return out
}

func allowHTTPHooks() bool { return os.Getenv("AGENTBASE_ALLOW_HTTP_HOOKS") == "1" }

func isLoopbackHost(host string) bool {
	if host == "localhost" {
		return true
	}
	if ip := net.ParseIP(host); ip != nil {
		return ip.IsLoopback()
	}
	return false
}

// isExplicitIPOrLocalOverride allows private/blocked IPs only when the caller
// explicitly allowlisted a literal IP (e.g. "169.254.169.254") or opted into
// localhost hooks via AGENTBASE_ALLOW_HTTP_HOOKS=1. Allowlisted DNS domains are
// still checked against blocked IPs so DNS rebinding cannot reach 127.0.0.1 or
// cloud metadata endpoints.
func isExplicitIPOrLocalOverride(host string, allow map[string]bool) bool {
	if !allow[host] {
		return false
	}
	if net.ParseIP(host) != nil {
		return true
	}
	return isLoopbackHost(host) && allowHTTPHooks()
}

func checkScheme(u *url.URL) error {
	switch u.Scheme {
	case "https":
		return nil
	case "http":
		if allowHTTPHooks() && isLoopbackHost(strings.ToLower(u.Hostname())) {
			return nil
		}
		return fmt.Errorf("http is only allowed for localhost with AGENTBASE_ALLOW_HTTP_HOOKS=1")
	default:
		return fmt.Errorf("only https webhook URLs are allowed (got scheme %q)", u.Scheme)
	}
}

func checkAllowlist(host string, allow map[string]bool) error {
	if len(allow) == 0 {
		return fmt.Errorf("no webhook hosts are allowed: set AGENTBASE_HOOK_HOSTS")
	}
	if !allow[host] {
		return fmt.Errorf("host %q is not in the AGENTBASE_HOOK_HOSTS allowlist", host)
	}
	return nil
}

func validateHookRegistration(rawURL string, allow map[string]bool) error {
	u, err := url.Parse(rawURL)
	if err != nil {
		return fmt.Errorf("invalid URL: %v", err)
	}
	host := strings.ToLower(u.Hostname())
	if host == "" {
		return fmt.Errorf("URL has no host")
	}
	if err := checkScheme(u); err != nil {
		return err
	}
	return checkAllowlist(host, allow)
}

func isBlockedIP(ip net.IP) bool {
	return ip.IsLoopback() || ip.IsPrivate() || ip.IsLinkLocalUnicast() ||
		ip.IsLinkLocalMulticast() || ip.IsUnspecified()
}

// hookLookupIP and hookDial are the only ways hook code reaches DNS and TCP.
// They are variables so tests can prove which address is actually dialed
// (the DNS pin) without a real resolver. Production never reassigns them.
var (
	hookLookupIP = net.LookupIP
	hookDial     = (&net.Dialer{Timeout: 4 * time.Second}).DialContext
)

func resolveHost(host string) ([]net.IP, error) {
	if ip := net.ParseIP(host); ip != nil {
		return []net.IP{ip}, nil
	}
	return hookLookupIP(host)
}

func validateHookDispatch(rawURL string, allow map[string]bool) error {
	u, err := url.Parse(rawURL)
	if err != nil {
		return fmt.Errorf("invalid URL: %w", err)
	}
	host := strings.ToLower(u.Hostname())
	if host == "" {
		return fmt.Errorf("URL has no host")
	}
	if err := checkScheme(u); err != nil {
		return err
	}
	if !isExplicitIPOrLocalOverride(host, allow) {
		ips, err := resolveHost(host)
		if err != nil {
			return fmt.Errorf("could not resolve host %q: %v", host, err)
		}
		for _, ip := range ips {
			if isBlockedIP(ip) {
				return fmt.Errorf("host %q resolves to a blocked address %s (private/loopback/link-local/unspecified)", host, ip)
			}
		}
	}
	return checkAllowlist(host, allow)
}

// safeWebhookClient returns an http.Client that:
// 1. Refuses all HTTP 3xx redirects (prevents redirect-to-internal SSRF).
// 2. Validates the resolved IP right at TCP Dial time and connects directly
//    to that verified IP (prevents DNS rebinding TOCTOU).
func safeWebhookClient(allow map[string]bool) *http.Client {
	tr := &http.Transport{
		DialContext: func(ctx context.Context, network, addr string) (net.Conn, error) {
			host, port, err := net.SplitHostPort(addr)
			if err != nil {
				return nil, err
			}
			lowerHost := strings.ToLower(host)
			if !allow[lowerHost] {
				return nil, fmt.Errorf("host %q is not in AGENTBASE_HOOK_HOSTS allowlist", lowerHost)
			}
			ips, err := resolveHost(lowerHost)
			if err != nil {
				return nil, err
			}
			if len(ips) == 0 {
				return nil, fmt.Errorf("no IP addresses resolved for %q", lowerHost)
			}
			override := isExplicitIPOrLocalOverride(lowerHost, allow)
			for _, ip := range ips {
				if !override && isBlockedIP(ip) {
					return nil, fmt.Errorf("host %q resolves to a blocked address %s (private/loopback/link-local/unspecified)", lowerHost, ip)
				}
			}
			return hookDial(ctx, network, net.JoinHostPort(ips[0].String(), port))
		},
	}
	return &http.Client{
		Timeout:   5 * time.Second,
		Transport: tr,
		CheckRedirect: func(req *http.Request, via []*http.Request) error {
			return http.ErrUseLastResponse
		},
	}
}

func (s *AgentBaseMCPServer) doDeployHook(event, hookURL string) (string, error) {
	if event != eventLedgerAfterCreate {
		return "", fmt.Errorf("unsupported event %q; only %q is accepted", event, eventLedgerAfterCreate)
	}
	if err := validateHookRegistration(hookURL, hookAllowlist()); err != nil {
		return "", err
	}
	col, err := s.app.FindCollectionByNameOrId("hooks")
	if err != nil {
		return "", fmt.Errorf("hooks collection not initialized; call setup_business first")
	}
	rec := core.NewRecord(col)
	rec.Set("event", event)
	rec.Set("action_webhook", hookURL)
	if err := s.app.Save(rec); err != nil {
		return "", fmt.Errorf("failed to persist hook: %w", err)
	}
	return fmt.Sprintf("HOOK REGISTERED: [%s] Event '%s' will dispatch to '%s'", rec.Id, event, hookURL), nil
}

func (s *AgentBaseMCPServer) doListHooks() (string, error) {
	if _, err := s.app.FindCollectionByNameOrId("hooks"); err != nil {
		return "", fmt.Errorf("hooks collection not initialized; call setup_business first")
	}
	recs, err := s.app.FindAllRecords("hooks")
	if err != nil {
		return "", fmt.Errorf("failed to list hooks: %w", err)
	}
	out := make([]hookSummary, 0, len(recs))
	for _, r := range recs {
		out = append(out, hookSummary{
			ID:            r.Id,
			Event:         r.GetString("event"),
			ActionWebhook: r.GetString("action_webhook"),
		})
	}
	raw, _ := json.MarshalIndent(out, "", "  ")
	return string(raw), nil
}

func (s *AgentBaseMCPServer) doDeleteHook(id string) (string, error) {
	id = strings.TrimSpace(id)
	if id == "" {
		return "", fmt.Errorf("hook id must not be empty")
	}
	if _, err := s.app.FindCollectionByNameOrId("hooks"); err != nil {
		return "", fmt.Errorf("hooks collection not initialized; call setup_business first")
	}
	rec, err := s.app.FindRecordById("hooks", id)
	if err != nil || rec == nil {
		return "", fmt.Errorf("hook [%s] not found", id)
	}
	if err := s.app.Delete(rec); err != nil {
		return "", fmt.Errorf("failed to delete hook [%s]: %w", id, err)
	}
	return fmt.Sprintf("HOOK DELETED: [%s] removed", id), nil
}

func (s *AgentBaseMCPServer) registerEventDispatchers() {
	s.app.OnRecordAfterCreateSuccess("ledger").BindFunc(func(e *core.RecordEvent) error {
		s.wg.Add(1)
		go func(rec *core.Record) {
			defer s.wg.Done()
			s.dispatchHooks(eventLedgerAfterCreate, rec)
		}(e.Record)
		return e.Next()
	})
}

// hookLog is where dispatch warnings go: the PocketBase logger unless a test
// has set s.logger.
func (s *AgentBaseMCPServer) hookLog() *slog.Logger {
	if s.logger != nil {
		return s.logger
	}
	return s.app.Logger()
}

// redactURLError drops the URL from an error before it is logged. Webhook URLs
// often carry a token in the path or query, and net/http and net/url both
// quote the full URL in their errors.
func redactURLError(err error) string {
	var ue *url.Error
	if errors.As(err, &ue) {
		return ue.Op + ": " + ue.Err.Error()
	}
	return err.Error()
}

// WaitHooks blocks until all in-flight asynchronous webhook dispatches finish.
func (s *AgentBaseMCPServer) WaitHooks() {
	s.wg.Wait()
}

func (s *AgentBaseMCPServer) dispatchHooks(event string, rec *core.Record) {
	recs, err := s.app.FindAllRecords("hooks", dbx.HashExp{"event": event})
	if err != nil || len(recs) == 0 {
		return
	}
	payload, err := json.Marshal(map[string]any{
		"event":    event,
		"account":  rec.GetString("account"),
		"amount":   rec.GetFloat("amount"),
		"currency": rec.GetString("currency"),
		"tx_hash":  rec.GetString("tx_hash"),
		"memo":     rec.GetString("memo"),
	})
	if err != nil {
		return
	}
	allow := hookAllowlist()
	client := safeWebhookClient(allow)
	for _, h := range recs {
		target := h.GetString("action_webhook")
		if target == "" {
			continue
		}
		if err := validateHookDispatch(target, allow); err != nil {
			// Log which hook and why, never the payload or the full URL.
			s.hookLog().Warn("webhook skipped: failed dispatch validation",
				"hook_id", h.Id, "reason", redactURLError(err))
			continue
		}
		resp, err := client.Post(target, "application/json", bytes.NewReader(payload))
		if err != nil {
			s.hookLog().Warn("webhook dispatch failed", "hook_id", h.Id, "error", redactURLError(err))
			continue
		}
		resp.Body.Close()
	}
}
