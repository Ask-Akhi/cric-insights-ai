"""
MCP Client — tool discovery + call routing across all servers.

All servers run in-process (no stdio overhead). The client
provides a unified interface for the orchestrator.
"""
from __future__ import annotations

import logging
from typing import Any

from ..core.result import ToolResult
from ..core.token_utils import count_tokens

log = logging.getLogger("mcp.client")

# ── Server registry ────────────────────────────────────────────────────────────
# Lazy-imported to avoid circular deps and keep startup fast.

_SERVERS: list[dict[str, Any]] | None = None


def _load_servers() -> list[dict[str, Any]]:
    """Lazy-load all MCP servers and collect their tool manifests."""
    global _SERVERS
    if _SERVERS is not None:
        return _SERVERS

    from .servers import cricsheet_server, live_server, search_server

    _SERVERS = [
        {
            "name": "cricsheet",
            "module": cricsheet_server,
            "tools": cricsheet_server.list_tools(),
            "priority": 1,    # cheapest — local data
        },
        {
            "name": "live",
            "module": live_server,
            "tools": live_server.list_tools(),
            "priority": 2,    # API calls but cached
        },
        {
            "name": "search",
            "module": search_server,
            "tools": search_server.list_tools(),
            "priority": 10,   # expensive — LLM + web search
        },
    ]
    total = sum(len(s["tools"]) for s in _SERVERS)
    log.info("MCP client loaded %d tools from %d servers", total, len(_SERVERS))
    return _SERVERS


def list_all_tools() -> list[dict[str, Any]]:
    """Return flat list of all tool descriptors across all servers."""
    servers = _load_servers()
    result = []
    for s in servers:
        for t in s["tools"]:
            result.append({**t, "_server": s["name"], "_priority": s["priority"]})
    return result


def get_tool(name: str) -> dict[str, Any] | None:
    """Look up a single tool by name."""
    for t in list_all_tools():
        if t["name"] == name:
            return t
    return None


def call_tool(name: str, arguments: dict | None = None) -> ToolResult:
    """
    Route a tool call to the correct server and return a ToolResult.
    """
    arguments = arguments or {}
    servers = _load_servers()

    for s in servers:
        for t in s["tools"]:
            if t["name"] == name:
                try:
                    raw = s["module"].call_tool(name, arguments)
                    return ToolResult(
                        tool_name=name,
                        data=raw,
                        source=s["name"],
                        tokens_estimate=count_tokens(raw),
                    )
                except Exception as e:
                    log.error("Tool %s failed: %s", name, e)
                    return ToolResult(
                        tool_name=name,
                        data="",
                        source=s["name"],
                        error=str(e),
                    )

    return ToolResult(
        tool_name=name,
        data="",
        error=f"Unknown tool: {name}",
    )


def tools_by_server(server_name: str) -> list[dict[str, Any]]:
    """Return tools for a specific server."""
    servers = _load_servers()
    for s in servers:
        if s["name"] == server_name:
            return s["tools"]
    return []
