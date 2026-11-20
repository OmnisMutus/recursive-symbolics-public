"""A minimal MCP client over stdio, so this agent can call tools another program provides.

The case this was written for is Vector's own `vector-agent`, which runs a Vector (Nostr) account as an MCP
server and offers DMs, communities and Mini App sessions as tools. Writing a Nostr client here would have
meant websockets, Schnorr signing over secp256k1 and encrypted direct messages; calling theirs means
newline-delimited JSON-RPC over a pipe. So this module is deliberately small and knows nothing about Nostr.

What it does: start the server as a child process, do the `initialize` handshake, list its tools, call them,
and stop it. What it does not do: decide whether a call is allowed. That belongs to outbound.py, because a
tool that sends a message to another person is not the same kind of act as one that reads a chat, and the
server cannot make that judgement for us. Nothing here is wired to a model; tools.py asks the gate.

The server's key lives in its environment and never passes through this process' arguments or any file this
writes. `env_keys` names the variables to forward from this process' own environment, so a missing key is an
error that says which variable is unset rather than a server that starts without an identity.
"""
import json
import os
import subprocess
import threading
import time

PROTOCOL = "2025-06-18"
CLIENT = {"name": "reference-agent", "version": "1"}


class MCPError(RuntimeError):
    """A server that failed to start, answered an error, or stopped answering."""


class MCPServer:
    """One MCP server, started on demand and stopped with `close()`."""

    def __init__(self, command, args=(), env_keys=(), cwd=None, timeout=30.0, name=""):
        self.command = command
        self.args = list(args)
        self.env_keys = list(env_keys)
        self.cwd = cwd or None
        self.timeout = float(timeout)
        self.name = name or os.path.basename(str(command))
        self.proc = None
        self.server_info = {}
        self._id = 0
        self._stderr = []
        self._drainer = None
        self._lock = threading.Lock()

    # ---------- process ----------
    def _env(self):
        env = dict(os.environ)
        missing = [k for k in self.env_keys if not os.environ.get(k)]
        if missing:
            raise MCPError(f"{self.name}: these environment variables are unset: {', '.join(missing)}. "
                           f"The server needs them and this agent never stores them.")
        return env

    def _drain(self, stream):
        for raw in iter(stream.readline, b""):
            line = raw.decode("utf-8", "replace").rstrip()
            if line:
                self._stderr.append(line)
                del self._stderr[:-40]

    def start(self):
        if self.proc:
            return self
        env = self._env()
        try:
            self.proc = subprocess.Popen([self.command, *self.args], stdin=subprocess.PIPE,
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                         cwd=self.cwd, env=env, bufsize=0)
        except OSError as e:
            raise MCPError(f"{self.name}: cannot start {self.command!r}: {e}") from e
        self._drainer = threading.Thread(target=self._drain, args=(self.proc.stderr,), daemon=True)
        self._drainer.start()
        try:
            out = self._rpc("initialize", {"protocolVersion": PROTOCOL, "capabilities": {},
                                           "clientInfo": CLIENT})
            self.server_info = out.get("serverInfo") or {}
            self._notify("notifications/initialized")
        except BaseException:
            # A failed start raises out of __enter__, so __exit__ never runs and nobody else would close it.
            self.close()
            raise
        return self

    def close(self):
        """Stop the server and release all three pipes. Safe to call twice."""
        proc = self.proc
        if not proc:
            return
        for step in (proc.stdin.close, proc.terminate):
            try:
                step()
            except Exception:
                pass
        try:
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
                proc.wait(timeout=5)
            except Exception:
                pass
        # The process has ended, so the stderr reader meets end of file and returns. It is joined before stderr
        # is closed because closing a pipe under a thread still blocked reading it is not safe on every
        # platform. If a grandchild still holds stderr open the reader stays blocked, and stderr is left to it.
        drainer, self._drainer = self._drainer, None
        if drainer is not None:
            drainer.join(timeout=5)
        pipes = [proc.stdout]
        if drainer is None or not drainer.is_alive():
            pipes.append(proc.stderr)
        for pipe in pipes:
            try:
                pipe.close()
            except Exception:
                pass
        self.proc = None

    def __enter__(self):
        return self.start()

    def __exit__(self, *_exc):
        self.close()

    # ---------- transport ----------
    def _send(self, message):
        line = json.dumps(message, ensure_ascii=False).encode("utf-8") + b"\n"
        try:
            self.proc.stdin.write(line)
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError) as e:
            raise MCPError(f"{self.name} stopped: {e}. {self.stderr_tail()}") from e

    def _notify(self, method, params=None):
        self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def _rpc(self, method, params=None, timeout=None):
        if not self.proc:
            raise MCPError(f"{self.name} is not running.")
        with self._lock:
            self._id += 1
            want = self._id
            self._send({"jsonrpc": "2.0", "id": want, "method": method, "params": params or {}})
            deadline = time.monotonic() + (timeout or self.timeout)
            while True:
                if time.monotonic() > deadline:
                    raise MCPError(f"{self.name}: no answer to {method} in "
                                   f"{timeout or self.timeout:.0f}s. {self.stderr_tail()}")
                raw = self.proc.stdout.readline()
                if not raw:
                    raise MCPError(f"{self.name} closed its output during {method}. {self.stderr_tail()}")
                try:
                    msg = json.loads(raw.decode("utf-8", "replace"))
                except ValueError:
                    continue                    # a line that is not JSON-RPC is the server's own noise
                if msg.get("id") != want:
                    continue                    # a notification, or an answer we are not waiting for
                if "error" in msg:
                    err = msg["error"] or {}
                    raise MCPError(f"{self.name}: {method} refused: "
                                   f"{err.get('message') or err} (code {err.get('code')})")
                return msg.get("result") or {}

    def stderr_tail(self, lines=3):
        tail = self._stderr[-lines:]
        return ("Last from the server: " + " | ".join(tail)) if tail else "The server said nothing."

    # ---------- tools ----------
    def tools(self):
        """Every tool the server offers, as {name, description, inputSchema}."""
        out, cursor, found = [], None, []
        while True:
            page = self._rpc("tools/list", {"cursor": cursor} if cursor else {})
            found = page.get("tools") or []
            out += [t for t in found if isinstance(t, dict) and t.get("name")]
            cursor = page.get("nextCursor")
            if not cursor:
                return out

    def call(self, name, arguments=None, timeout=None):
        """One tool call. Returns {text, structured, is_error, raw}."""
        out = self._rpc("tools/call", {"name": name, "arguments": arguments or {}}, timeout)
        parts = []
        for item in out.get("content") or []:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
            elif isinstance(item, dict):
                parts.append(f"[{item.get('type')}]")
        return {"text": "\n".join(parts).strip(), "structured": out.get("structuredContent"),
                "is_error": bool(out.get("isError")), "raw": out}


def from_config(cfg, which):
    """A server described in config.json under "mcp", not started."""
    block = ((cfg or {}).get("mcp") or {}).get(which) or {}
    if not block.get("command"):
        raise MCPError(f'No "command" for MCP server {which!r} in config.json under "mcp".')
    return MCPServer(command=os.path.expanduser(str(block["command"])),
                     args=block.get("args") or (), env_keys=block.get("env_keys") or (),
                     cwd=os.path.expanduser(str(block["cwd"])) if block.get("cwd") else None,
                     timeout=float(block.get("timeout") or 30), name=which)
