"""The approval gate for anything that leaves this machine.

The agent this comes from does the same for the disk: a write is proposed, the diff is shown, and nothing
happens until the person says yes. This is the same discipline for the network. It exists because a messaging tool is not the same
kind of act as a file write and is worse in one specific way: a write can be reverted from git, and a
message that has reached a relay cannot be recalled.

The rule, in one line: a call that sends, publishes or changes something other people can see is shown in
full and waits for a yes; a call that only reads does not.

Three decisions make this safe rather than decorative.

**Unknown tools are outbound.** A server can add a tool in its next release. Classifying by a list of
senders would let that new tool through on the day it appears, so the list names the READ-ONLY tools and
everything else needs approval. Wrong in the safe direction: a new reader costs one approval, a new sender
costs nothing.

**A file send is checked against an allowlist of paths, not just approved.** Their own README says plainly
that `send_file` can send any file the agent's process can read. This process can read the person's notes, their
library and, if it were ever careless, a key file. So a path outside `outbound.allow_paths` is refused
before a human is ever asked, because an approval prompt is not a safety mechanism for a path nobody
intended to be sendable: a tired yes at the wrong moment is exactly the failure to design out. Approval
covers what was meant to be sendable; the allowlist covers what was not.

**The preview is the whole payload.** Not a summary, not the first line. If the text is going to a person,
the one approving reads what that person will read. For a file: the absolute path, its size and a digest, so the thing
approved is identified rather than described.

**A read-only list belongs to one server.** Each list below was written from one server's own source or
documentation (vector-agent's README; agentbase's Go handlers), so it holds for that server and no other. A second MCP server can offer a tool with the same name that does
something else entirely; matched on the name alone, its call would pass without a prompt. So the lists are
keyed by the server's name as config.json declares it ("mcp": {"vector": ...}), which the person running the agent controls, and not
by the name a server reports about itself, which the server controls. A server with no list of its own has
no read-only tools: every call it makes waits for a yes. Renaming the vector entry in config.json therefore
makes its reads ask too, which is the safe direction.

Every decision, yes or no, appends one line to the log. A refusal is as much a fact about the session as a
send.
"""
import hashlib
import json
import os
import re
import time

# The tools that only read. Everything not here needs approval, including a tool this list has never seen.
READ_ONLY = {
    # identity and listings
    "my_npub", "current_account", "list_accounts",
    # reading messages
    "get_new_messages", "list_chats", "get_messages", "sync_dms", "sync_community_channel",
    # reading people
    "get_profile", "load_profile", "get_blocked_users",
    # reading communities
    "list_communities", "list_pending_invites", "list_channels",
}

# agentbase (mcp-workspace/ in this repository, a Go MCP server over a local PocketBase ledger). Written by hand from its
# handlers in mcp-workspace/apis/business.go, policy.go, hooks.go and identity.go, not from the readOnlyHint the server
# reports about itself: these four only SELECT from the database or check a signature. Every other
# agentbase tool writes, and delete_policy in particular lets an agent remove its own guardrails.
AGENTBASE_READ_ONLY = {"query_ledger", "list_policies", "list_hooks", "verify_signature"}
# The agent's own memory (the Maintainer's decision, 2026-11-13): ws_brief and ws_recall read the workspace database, files under a
# registered project root and read-only git commands (agentbase apis/workspace_mcp.go), so it reads its own memory
# without asking.
AGENTBASE_READ_ONLY |= {"ws_brief", "ws_recall"}

# Writes that need no yes. Not reads, and not called reads: they change the workspace database, so each one is
# logged. The Maintainer decided on 2026-11-13 that the agent may write its own memory without asking. To make
# every workspace write wait for a yes, empty this set. Only these
# three: registering a project, recording a test result and replacing a file summary still wait.
NO_YES_NEEDED = {("agentbase", "ws_record"), ("agentbase", "ws_note"), ("agentbase", "ws_resolve")}
NO_YES_WHY = "the agent's own memory: the Maintainer decided on 2026-11-13 that it needs no yes"

# A "path" that is not a file being sent: ws_record's path is relative to a registered project root, and the local
# agentbase reads that file itself to check the quote. The send-a-file rule (allow_paths) does not apply to it.
LOCAL_PATH_ARGS = {("agentbase", "ws_record")}

# Which server each read-only list was written for: the key is the name config.json gives it under "mcp".
READ_ONLY_BY_SERVER = {"vector": READ_ONLY, "agentbase": AGENTBASE_READ_ONLY}

# Why a given call needs a yes. Anything unlisted is "not known to this gate", which still needs one.
REASONS = {
    "send_dm": "sends a message to another person, and it cannot be recalled once a relay has it",
    "send_file": "sends a file to another person, and it cannot be recalled once a relay has it",
    "send_community_message": "posts in a community channel where everyone in it will read it",
    "update_profile": "publishes this account's public profile to relays",
    "set_nickname": "changes a label stored for this account",
    "block_user": "publishes a change to this account's block list",
    "unblock_user": "publishes a change to this account's block list",
    "create_community": "creates a community owned by this account",
    "delete_community": "closes a community for good, and it cannot be undone",
    "leave_community": "leaves a community, and rejoining needs a new invite",
    "join_community": "joins a community, which makes this account visible to its members",
    "accept_pending_invite": "joins a community, which makes this account visible to its members",
    "edit_community_metadata": "changes what a community's members see",
    "add_account": "adds an identity to this agent's data directory",
    "swap_account": "switches which identity this agent acts as",
    # agentbase
    "transact": "moves money between ledger accounts and may fire registered webhooks to other machines",
    "setup_business": "creates the ledger, policy, hook and agent tables",
    "create_policy": "adds a guardrail that will refuse future transfers",
    "delete_policy": "removes a guardrail, which can let transfers through that it was there to stop",
    "deploy_hook": "registers a webhook that will send every ledger entry to another machine",
    "delete_hook": "removes a registered webhook",
    "register_agent": "registers a signing identity that can authorize transfers",
}

# ---------- keys must never be in the tree ----------
# The server's key lives in the environment. config.json names the VARIABLE, never the value, and nothing
# here writes a key anywhere. That is a claim about this repository, so it is checkable rather than asserted:
# scan() looks for the shapes a secret takes and a test runs it over the whole working tree.
KEY_SHAPES = (
    (re.compile(r"\bnsec1[qpzry9x8gf2tvdw0s3jn54khce6mua7l]{58}\b"), "a Nostr private key (nsec)"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"), "an API key of the sk- form"),
    (re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"), "a PEM private key"),
    (re.compile(r"\bghp_[A-Za-z0-9]{36}\b"), "a GitHub personal access token"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), "a Slack token"),
)
SKIP_DIRS = {".git", "__pycache__", "node_modules", "books", "reference", "index", "models", ".venv", "_to_delete"}
SKIP_SUFFIX = (".pdf", ".png", ".jpg", ".jpeg", ".gguf", ".7z", ".bundle", ".zip", ".wasm", ".pyc")


def looks_like_a_key(text):
    """Every secret-shaped thing in one piece of text, as [(what, the matched prefix)]."""
    found = []
    for shape, what in KEY_SHAPES:
        for m in shape.finditer(text or ""):
            found.append((what, m.group(0)[:12] + "..."))
    return found


def scan(root, skip_dirs=None, skip_suffix=None):
    """Every file in the tree holding something key-shaped, as [{file, what, shown}]. Run before pushing."""
    skip_dirs = SKIP_DIRS if skip_dirs is None else set(skip_dirs)
    skip_suffix = SKIP_SUFFIX if skip_suffix is None else tuple(skip_suffix)
    out = []
    for here, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for name in files:
            if name.lower().endswith(skip_suffix):
                continue
            path = os.path.join(here, name)
            try:
                if os.path.getsize(path) > 2_000_000:
                    continue
                with open(path, encoding="utf-8", errors="ignore") as fh:
                    text = fh.read()
            except OSError:
                continue
            for what, shown in looks_like_a_key(text):
                out.append({"file": os.path.relpath(path, root), "what": what, "shown": shown})
    return out


RECIPIENT_KEYS = ("to_npub", "npub", "channel_id", "community_id", "chat_id")
PATH_KEYS = ("file_path", "path")
CONTENT_KEYS = ("content", "text", "message", "about", "name", "description", "nickname")


def is_read_only(tool, server):
    """True only for a tool on the read-only list of THIS server. A same-named tool elsewhere is not read-only."""
    return tool in READ_ONLY_BY_SERVER.get(server or "", ())


def reason(tool, server):
    if is_read_only(tool, server):
        return ""
    if (server or "") not in READ_ONLY_BY_SERVER:
        return (f"comes from {server or 'a server with no name'}, which has no read-only list in this gate, so "
                f"every call it makes is treated as leaving the machine")
    return REASONS.get(tool) or ("is not a tool this gate knows, so it is treated as leaving the machine "
                                 "until someone classifies it")


def digest(text):
    return hashlib.sha256(text.encode("utf-8", "replace") if isinstance(text, str) else text).hexdigest()[:12]


def allowed_roots(cfg):
    roots = ((cfg or {}).get("outbound") or {}).get("allow_paths") or []
    out = []
    for r in roots:
        try:
            out.append(os.path.realpath(os.path.expanduser(str(r))))
        except Exception:
            continue
    return out


def check_path(path, cfg):
    """A file may be sent only from a declared root. Returns (ok, absolute_path, why_not)."""
    roots = allowed_roots(cfg)
    try:
        real = os.path.realpath(os.path.expanduser(str(path)))
    except Exception as e:
        return False, str(path), f"this path cannot be resolved: {e}"
    if not roots:
        return False, real, ('no "outbound": {"allow_paths": [...]} in config.json, so no file may be sent. '
                             "This is deliberate: the default is that nothing on this disk is sendable.")
    if not os.path.isfile(real):
        return False, real, "there is no file at this path"
    for root in roots:
        if real == root or real.startswith(root + os.sep):
            return True, real, ""
    return False, real, ("this path is outside every declared allow_paths root, so it is refused without "
                         "asking. Add its folder to outbound.allow_paths if it was meant to be sendable.")


def _file_line(real):
    try:
        size = os.path.getsize(real)
        with open(real, "rb") as fh:
            d = hashlib.sha256(fh.read()).hexdigest()[:12]
        return f"{real}\n  {size} bytes, sha256 {d}"
    except Exception as e:
        return f"{real}\n  cannot be read: {e}"


def preview(tool, arguments, cfg=None, server=""):
    """What this call would do, in full. The thing the person reads before deciding."""
    args = dict(arguments or {})
    lines = [f"{server + ': ' if server else ''}{tool}", f"  why this asks: {reason(tool, server)}"]
    to = [f"{k}={args[k]}" for k in RECIPIENT_KEYS if args.get(k)]
    if to:
        lines.append("  to: " + ", ".join(to))
    for key in PATH_KEYS:
        if args.get(key):
            ok, real, why = check_path(args[key], cfg)
            lines.append(f"  file: {_file_line(real)}")
            if not ok:
                lines.append(f"  REFUSED: {why}")
    body = [(k, str(args[k])) for k in CONTENT_KEYS if args.get(k)]
    for key, value in body:
        lines.append(f"  {key} ({len(value)} chars, sha256 {digest(value)}):")
        lines += ["    " + ln for ln in value.splitlines() or [""]]
    extra = {k: v for k, v in args.items()
             if k not in RECIPIENT_KEYS + PATH_KEYS + CONTENT_KEYS and v not in (None, "")}
    if extra:
        lines.append("  other arguments: " + json.dumps(extra, ensure_ascii=False)[:400])
    if not to and not body and not extra:
        lines.append("  no arguments")
    return "\n".join(lines)


class Outbound:
    """Every call to another program's tools goes through here.

    `ask` is how a yes is obtained: a callable taking the preview text and returning True or False. There is
    no default that says yes. In a session with nobody watching, `ask` is absent and every outbound call is
    refused, which is the only safe reading of an unanswered question.
    """

    def __init__(self, cfg=None, ask=None, log_path=None, require_approval=True):
        self.cfg = cfg or {}
        self.ask = ask
        block = (self.cfg.get("outbound") or {})
        self.require_approval = bool(block.get("require_approval", require_approval))
        self.log_path = log_path or block.get("log") or ""
        self.decisions = []

    def _log(self, row):
        self.decisions.append(row)
        if not self.log_path:
            return
        try:
            os.makedirs(os.path.dirname(os.path.expanduser(self.log_path)) or ".", exist_ok=True)
            with open(os.path.expanduser(self.log_path), "a", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        except Exception:
            pass                       # the log is a record, never the thing that stops the work

    def decide(self, tool, arguments=None, server=""):
        """(allowed, why, preview_text). Nothing is sent by this method."""
        args = dict(arguments or {})
        if is_read_only(tool, server):
            return True, "read-only", ""
        text = preview(tool, args, self.cfg, server)
        row = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "server": server, "tool": tool,
               "preview_digest": digest(text)}
        for key in PATH_KEYS:
            if args.get(key):
                if (server, tool) in LOCAL_PATH_ARGS:
                    continue
                ok, real, why = check_path(args[key], self.cfg)
                if not ok:
                    self._log({**row, "decision": "refused", "why": why, "path": real})
                    return False, why, text
        if (server, tool) in NO_YES_NEEDED:
            self._log({**row, "decision": "sent", "why": NO_YES_WHY})
            return True, NO_YES_WHY, text
        if not self.require_approval:
            self._log({**row, "decision": "sent", "why": "approval turned off in config.json"})
            return True, "approval turned off in config.json", text
        if not callable(self.ask):
            why = ("nobody is here to approve an outbound call, so it is refused. This is the gate working, "
                   "not a failure: an unanswered question is a no.")
            self._log({**row, "decision": "refused", "why": why})
            return False, why, text
        try:
            said_yes = bool(self.ask(text))
        except Exception as e:
            self._log({**row, "decision": "refused", "why": f"the approval step failed: {e}"})
            return False, f"the approval step failed, so nothing was sent: {e}", text
        self._log({**row, "decision": "sent" if said_yes else "declined",
                   "why": "approved" if said_yes else "declined"})
        return (True, "approved", text) if said_yes else (False, "declined", text)

    def call(self, server, tool, arguments=None):
        """Decide, then call the server only on a yes. `server` is an MCPServer."""
        name = getattr(server, "name", "")
        allowed, why, text = self.decide(tool, arguments, name)
        if not allowed:
            return {"sent": False, "why": why, "preview": text}
        out = server.call(tool, arguments)
        return {"sent": True, "why": why, "preview": text, "result": out}
