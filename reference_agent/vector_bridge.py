"""Answering Vector DMs: the inbound half of the Vector link.

mcp.py lets the agent call Vector's `vector-agent`, and outbound.py stands in front of every call that sends.
Neither one notices when someone writes to the agent. This module does: it reads `get_new_messages`, decides
which messages the agent may see at all, asks the agent for a reply, and sends the reply through the gate.

The idea comes from another project's Vector bridge, which polls the same queue and ranks senders by role.
This is written from scratch, and differs from that design on purpose in three ways:

1. **A stranger's words never reach the model.** Only npubs in `allow_npubs` are passed to `respond`. Anyone
   else's message is *held*: the report says who wrote and how long it was, never what it said. That keeps
   a stranger from steering the agent with text it was never meant to read (prompt injection by DM).
2. **Every reply waits for a yes.** A reply is `send_dm`, and outbound.py asks for it like any other send.
   With nobody there to ask, the reply is refused and kept as a draft in the report. This module adds no
   exception to the gate. To change that, edit outbound.NO_YES_NEEDED, which is the Maintainer's decision.
3. **DMs only.** In a community channel, vector-agent's README does not say which field names the sender, so
   a group message cannot be checked against `allow_npubs`. Group messages are skipped and counted.

`respond(incoming)` is how the agent is asked. It takes an `Incoming` and returns the reply text, or None
for no reply. This module knows nothing about models. Text from `Incoming.text` came from another person, so
the caller should hand it to the model as data, not as instructions.

Nothing here writes message text to disk. The report is returned to the caller, and the gate's log records
digests only (outbound.py).
"""
import json
import re
import time
from collections import OrderedDict, namedtuple

NPUB = re.compile(r"^npub1[02-9ac-hj-np-z]{58}$")
MIN_EVERY = 2.0             # seconds between polls, at least, so the queue is never hammered
MAX_REPLY = 8000            # characters; a longer reply is not sent, rather than cut where nobody chose
SEEN_LIMIT = 1000           # message ids remembered, so a message delivered twice is answered once

Incoming = namedtuple("Incoming", "chat_id msg_id sender text attachments")


def check_npubs(npubs):
    """The allowlist as a frozenset. Anything that is not a well-formed npub is an error, not a skip."""
    out = set()
    for n in npubs or ():
        n = str(n).strip()
        if not NPUB.match(n):
            raise ValueError(f"not an npub: {n[:20]!r} (an npub is 'npub1' and 58 more bech32 characters)")
        out.add(n)
    return frozenset(out)


def parse_queue(text):
    """vector-agent's get_new_messages answer as a list of dicts. Anything else is an error."""
    try:
        rows = json.loads(text or "[]")
    except ValueError as e:
        raise ValueError(f"get_new_messages did not answer JSON: {e}") from None
    if not isinstance(rows, list):
        raise ValueError("get_new_messages did not answer a list")
    return [r for r in rows if isinstance(r, dict)]


def new_report():
    return {"received": 0, "mine": 0, "group": 0, "empty": 0, "duplicate": 0, "held": [], "no_reply": 0,
            "sent": 0, "declined": 0, "refused": 0, "too_long": [], "drafts": [], "errors": []}


class Bridge:
    """One Vector account, answered by one agent. `server` is an mcp.MCPServer named "vector"."""

    def __init__(self, server, gate, respond, allow_npubs, max_reply=MAX_REPLY):
        if not callable(respond):
            raise TypeError("respond must be callable: it is how the agent is asked for a reply")
        if max_reply < 1:
            raise ValueError("max_reply must be at least 1")
        self.server = server
        self.gate = gate
        self.respond = respond
        self.allow = check_npubs(allow_npubs)
        self.max_reply = int(max_reply)
        self._seen = OrderedDict()

    def _first_time(self, msg_id):
        if not msg_id:
            return True                     # no id to remember it by: it cannot be told apart from another
        if msg_id in self._seen:
            return False
        self._seen[msg_id] = True
        if len(self._seen) > SEEN_LIMIT:
            self._seen.popitem(last=False)
        return True

    def poll_once(self):
        """Read the queue once and answer what may be answered. Returns the report."""
        rep = new_report()
        got = self.gate.call(self.server, "get_new_messages", {})
        if not got.get("sent"):
            rep["errors"].append(f"get_new_messages was not allowed: {got.get('why')}")
            return rep
        try:
            rows = parse_queue((got.get("result") or {}).get("text"))
        except ValueError as e:
            rep["errors"].append(str(e))
            return rep
        for row in rows:
            rep["received"] += 1
            self._one(row, rep)
        return rep

    def _one(self, row, rep):
        if row.get("mine"):
            rep["mine"] += 1
            return
        if row.get("is_group"):
            rep["group"] += 1
            return
        chat_id = str(row.get("chat_id") or "")
        text = str(row.get("content") or "")
        if not chat_id or not text.strip():
            rep["empty"] += 1
            return
        msg_id = str(row.get("id") or "")
        if not self._first_time(msg_id):
            rep["duplicate"] += 1
            return
        if chat_id not in self.allow:
            rep["held"].append({"from": chat_id, "chars": len(text), "id": msg_id})
            return
        names = [str(a.get("name") or "") for a in row.get("attachments") or () if isinstance(a, dict)]
        msg = Incoming(chat_id, msg_id, chat_id, text, tuple(names))
        try:
            reply = self.respond(msg)
        except Exception as e:
            rep["errors"].append(f"respond failed for {msg_id or chat_id}: {e}")
            return
        reply = "" if reply is None else str(reply)
        if not reply.strip():
            rep["no_reply"] += 1
            return
        if len(reply) > self.max_reply:
            rep["too_long"].append({"to": chat_id, "chars": len(reply), "limit": self.max_reply})
            return
        out = self.gate.call(self.server, "send_dm", {"to_npub": chat_id, "content": reply})
        if out.get("sent"):
            rep["sent"] += 1
        elif out.get("why") == "declined":
            rep["declined"] += 1
        else:
            rep["refused"] += 1
            rep["drafts"].append({"to": chat_id, "content": reply, "why": out.get("why")})

    def run(self, every=5.0, rounds=None, on_report=None, sleep=time.sleep):
        """Poll every `every` seconds (at least MIN_EVERY), `rounds` times or until interrupted."""
        every = max(MIN_EVERY, float(every))
        done = 0
        while rounds is None or done < rounds:
            rep = self.poll_once()
            done += 1
            if on_report is not None:
                on_report(rep)
            if rounds is None or done < rounds:
                sleep(every)
        return done
