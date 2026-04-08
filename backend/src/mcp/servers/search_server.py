"""
MCP Server: Web Search (Gemini Grounded)

Last-resort tool — only invoked when Cricsheet + live data are insufficient.
Wraps the existing get_llm_response_grounded() from llm_client.py.
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("mcp.search")

TOOLS: list[dict[str, Any]] = []


def _tool(name: str, description: str, parameters: dict):
    """Decorator to register a function as an MCP tool."""
    def decorator(fn):
        TOOLS.append({
            "name": name,
            "description": description,
            "parameters": parameters,
            "handler": fn,
        })
        return fn
    return decorator


@_tool(
    name="web_search",
    description=(
        "Search the web for current cricket information using Google Search grounding. "
        "Use ONLY when local Cricsheet data and live scores are insufficient. "
        "Good for: current tournament standings, breaking news, transfer rumours, "
        "rule changes, upcoming schedule details."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query. Be specific for best results.",
            },
        },
        "required": ["query"],
    },
)
def web_search(query: str) -> str:
    try:
        from backend.src.services.llm_client import get_llm_response_grounded

        result = get_llm_response_grounded(query, {})
        if not result or result.startswith("❌"):
            return f"Web search returned no useful results for: {query}"
        return f"## 🌐 Web Search Results\n\n{result}"
    except Exception as e:
        log.error("web_search failed: %s", e)
        return f"Error performing web search: {e}"


def list_tools() -> list[dict[str, Any]]:
    return [
        {"name": t["name"], "description": t["description"], "inputSchema": t["parameters"]}
        for t in TOOLS
    ]


def call_tool(name: str, arguments: dict) -> str:
    for t in TOOLS:
        if t["name"] == name:
            return t["handler"](**arguments)
    return f"Unknown tool: {name}"
