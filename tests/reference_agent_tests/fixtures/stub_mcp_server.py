"""A stand-in MCP server over stdio, so the client is tested without Vector's binary.

It answers initialize, tools/list (in two pages, to exercise the cursor) and tools/call, and it records every
call it was asked to make into the file named by STUB_CALLS. That file is what proves the gate: a declined
call must leave no line in it.
"""
import json
import os
import sys

TOOLS = [
    {"name": "my_npub", "description": "This account's npub."},
    {"name": "get_messages", "description": "A chat's recent messages."},
    {"name": "send_dm", "description": "Send an encrypted DM."},
    {"name": "send_file", "description": "Send a file as an encrypted DM attachment."},
    {"name": "brand_new_tool", "description": "Something this client has never heard of."},
]


def record(name, args):
    path = os.environ.get("STUB_CALLS")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"name": name, "arguments": args}) + "\n")


def main():
    if os.environ.get("STUB_DIE") == "1":
        sys.exit(3)
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            msg = json.loads(raw)
        except ValueError:
            continue
        method, mid = msg.get("method"), msg.get("id")
        if mid is None:
            continue                                  # a notification
        if method == "initialize":
            out = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}},
                   "serverInfo": {"name": "stub", "version": "0"}}
        elif method == "tools/list":
            cursor = (msg.get("params") or {}).get("cursor")
            out = {"tools": TOOLS[:2], "nextCursor": "p2"} if not cursor else {"tools": TOOLS[2:]}
        elif method == "tools/call":
            p = msg.get("params") or {}
            name, args = p.get("name"), p.get("arguments") or {}
            record(name, args)
            if name == "boom":
                print(json.dumps({"jsonrpc": "2.0", "id": mid,
                                  "error": {"code": -32000, "message": "no such tool"}}), flush=True)
                continue
            out = {"content": [{"type": "text", "text": f"ok:{name}:{json.dumps(args, sort_keys=True)}"}]}
        else:
            print(json.dumps({"jsonrpc": "2.0", "id": mid,
                              "error": {"code": -32601, "message": "unknown method"}}), flush=True)
            continue
        print(json.dumps({"jsonrpc": "2.0", "id": mid, "result": out}), flush=True)


if __name__ == "__main__":
    main()
