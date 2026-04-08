"""
Stdio MCP Server — JSON-RPC interface for Claude Desktop / Cursor.

Run with:
    python -m backend.src.mcp.servers

Protocol: JSON-RPC 2.0 over stdin/stdout (one JSON object per line).

Supported methods:
    tools/list         → list all available tools
    tools/call         → call a tool by name with arguments
    initialize         → handshake (returns server info)
    notifications/*    → ignored (no-op)
"""
from __future__ import annotations

import json
import sys
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stderr,  # logs go to stderr, JSON-RPC goes to stdout
)
log = logging.getLogger("mcp.stdio")


def _load_all_tools() -> list[dict]:
    """Load tool manifests from all servers."""
    from . import cricsheet_server, live_server, search_server

    tools = []
    for server in (cricsheet_server, live_server, search_server):
        tools.extend(server.list_tools())
    return tools


def _call_tool(name: str, arguments: dict) -> str:
    """Route a tool call to the correct server."""
    from . import cricsheet_server, live_server, search_server

    for server in (cricsheet_server, live_server, search_server):
        for t in server.TOOLS:
            if t["name"] == name:
                return server.call_tool(name, arguments)
    return json.dumps({"error": f"Unknown tool: {name}"})


def _handle_request(req: dict) -> dict | None:
    """Process a single JSON-RPC request and return a response (or None for notifications)."""
    method = req.get("method", "")
    req_id = req.get("id")
    params = req.get("params", {})

    # Notifications (no id) → no response
    if req_id is None:
        log.debug("Notification: %s", method)
        return None

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {
                    "name": "cric-insights-mcp",
                    "version": "1.0.0",
                },
            },
        }

    if method == "tools/list":
        tools = _load_all_tools()
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": tools},
        }

    if method == "tools/call":
        name = params.get("name", "")
        arguments = params.get("arguments", {})
        try:
            result_text = _call_tool(name, arguments)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": result_text}],
                    "isError": False,
                },
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": f"Error: {e}"}],
                    "isError": True,
                },
            }

    # Unknown method
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main() -> None:
    """Run the stdio JSON-RPC server loop."""
    log.info("Cric Insights MCP stdio server starting...")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            req = json.loads(line)
        except json.JSONDecodeError as e:
            err_resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {e}"},
            }
            sys.stdout.write(json.dumps(err_resp) + "\n")
            sys.stdout.flush()
            continue

        response = _handle_request(req)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
