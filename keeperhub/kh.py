"""Minimal KeeperHub MCP client over plain HTTP JSON-RPC.

Exists because the documented ways in do not work everywhere: `claude mcp add` and
the official Claude plugin both use OAuth browser sign-in, which cannot complete in a
remote container, a CI runner, or anywhere else without a local browser -- i.e. most
places an autonomous agent actually runs. The headless organisation API key (kh_...)
works fine against the same endpoint; it is just not surfaced in onboarding or the
plugin.

Usage:
    export KEEPERHUB_API_KEY=kh_...
    python3 keeperhub/kh.py tools                 # list available tools
    python3 keeperhub/kh.py call <tool> '<json>'  # invoke a tool
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

ENDPOINT = "https://app.keeperhub.com/mcp"


_session: dict = {"id": None, "n": 0}


def _post(payload: dict, key: str) -> str:
    req = urllib.request.Request(ENDPOINT, data=json.dumps(payload).encode(),
                                 method="POST", headers={
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        # The server negotiates SSE unless JSON is explicitly acceptable too.
        "Accept": "application/json, text/event-stream",
        # Required. The edge rejects the default "Python-urllib/3.x" agent with a
        # bare 403 and no body -- verified by reproducing it with curl -A. Any
        # conventional agent string passes. Worth knowing before blaming your key.
        "User-Agent": "keeperhub-probe/1.0",
        # Every call after initialize must carry the session id handed back in the
        # Mcp-Session-Id response header, or the server answers 400 Bad Request.
        **({"Mcp-Session-Id": _session["id"]} if _session["id"] else {}),
    })
    with urllib.request.urlopen(req, timeout=120) as r:
        if not _session["id"]:
            _session["id"] = r.headers.get("mcp-session-id")
        return r.read().decode()


def rpc(method: str, params: dict | None = None, key: str | None = None) -> dict:
    key = key or os.environ.get("KEEPERHUB_API_KEY")
    if not key:
        raise SystemExit("error: set KEEPERHUB_API_KEY (Settings > API Keys > Organisation)")

    if not _session["id"]:
        _post({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "keeperhub-probe", "version": "1.0"}}}, key)

    _session["n"] += 1
    raw = _post({"jsonrpc": "2.0", "id": _session["n"], "method": method,
                 "params": params or {}}, key)

    # Streamable-HTTP transports may answer with SSE framing even for unary calls.
    if raw.lstrip().startswith(("event:", "data:")):
        raw = "".join(l[5:].strip() for l in raw.splitlines() if l.startswith("data:"))

    out = json.loads(raw)
    if "error" in out:
        raise RuntimeError(f"{method} failed: {out['error']}")
    return out.get("result", {})


def call_tool(name: str, args: dict) -> str:
    """Invoke a tool and flatten its content blocks to text."""
    res = rpc("tools/call", {"name": name, "arguments": args})
    parts = [c.get("text", "") for c in res.get("content", []) if c.get("type") == "text"]
    text = "\n".join(p for p in parts if p)
    if res.get("isError"):
        raise RuntimeError(f"tool {name} returned an error: {text}")
    return text


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cmd = sys.argv[1]

    if cmd == "tools":
        for t in rpc("tools/list").get("tools", []):
            desc = (t.get("description") or "").split("\n")[0][:88]
            print(f"  {t['name']:<28} {desc}")
        return 0

    if cmd == "call":
        if len(sys.argv) < 3:
            print("usage: kh.py call <tool> '<json args>'", file=sys.stderr)
            return 2
        args = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
        print(call_tool(sys.argv[2], args))
        return 0

    print(f"unknown command {cmd!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
