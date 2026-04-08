"""
MCP Server: Cricsheet Ball-by-Ball Data

Exposes cricket statistics as MCP tools. Wraps the existing
rag_service + stats_service into discoverable tools.
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("mcp.cricsheet")

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
    name="player_batting_stats",
    description=(
        "Get batting statistics for a cricket player from ball-by-ball data. "
        "Returns runs, average, strike rate, boundaries, innings count."
    ),
    parameters={
        "type": "object",
        "properties": {
            "player_name": {"type": "string", "description": "Player name or alias"},
            "format": {"type": "string", "enum": ["T20", "ODI", "Test", "All"], "default": "T20"},
        },
        "required": ["player_name"],
    },
)
def player_batting_stats(player_name: str, format: str = "T20") -> str:
    try:
        from backend.src.services.rag_service import build_rag_context
        context = build_rag_context(f"{player_name} batting stats", {"format": format})
        data = context.get("cricsheet_data", "")
        if not data:
            return f"No batting data found for '{player_name}' in {format} format."
        return f"## 🏏 {player_name} — Batting Stats ({format})\n\n{data}"
    except Exception as e:
        log.error("player_batting_stats failed: %s", e)
        return f"Error fetching batting stats: {e}"


@_tool(
    name="player_bowling_stats",
    description=(
        "Get bowling statistics for a cricket player from ball-by-ball data. "
        "Returns wickets, economy, average, dot ball %."
    ),
    parameters={
        "type": "object",
        "properties": {
            "player_name": {"type": "string", "description": "Player name or alias"},
            "format": {"type": "string", "enum": ["T20", "ODI", "Test", "All"], "default": "T20"},
        },
        "required": ["player_name"],
    },
)
def player_bowling_stats(player_name: str, format: str = "T20") -> str:
    try:
        from backend.src.services.rag_service import build_rag_context
        context = build_rag_context(f"{player_name} bowling stats economy wickets", {"format": format})
        data = context.get("cricsheet_data", "")
        if not data:
            return f"No bowling data found for '{player_name}' in {format} format."
        return f"## 🎳 {player_name} — Bowling Stats ({format})\n\n{data}"
    except Exception as e:
        log.error("player_bowling_stats failed: %s", e)
        return f"Error fetching bowling stats: {e}"


@_tool(
    name="head_to_head",
    description=(
        "Get head-to-head stats between a batter and a bowler. "
        "Returns runs scored, dismissals, strike rate in their matchups."
    ),
    parameters={
        "type": "object",
        "properties": {
            "batter": {"type": "string", "description": "Batter name"},
            "bowler": {"type": "string", "description": "Bowler name"},
            "format": {"type": "string", "enum": ["T20", "ODI", "Test", "All"], "default": "T20"},
        },
        "required": ["batter", "bowler"],
    },
)
def head_to_head(batter: str, bowler: str, format: str = "T20") -> str:
    try:
        from backend.src.services.rag_service import build_rag_context
        context = build_rag_context(f"{batter} vs {bowler} head to head", {"format": format})
        data = context.get("cricsheet_data", "")
        if not data:
            return f"No head-to-head data found for {batter} vs {bowler}."
        return f"## ⚔️ {batter} vs {bowler} ({format})\n\n{data}"
    except Exception as e:
        log.error("head_to_head failed: %s", e)
        return f"Error fetching head-to-head data: {e}"


@_tool(
    name="venue_stats",
    description=(
        "Get cricket ground/venue statistics. "
        "Returns average scores, pitch behaviour, toss trends."
    ),
    parameters={
        "type": "object",
        "properties": {
            "venue": {"type": "string", "description": "Venue name or city"},
            "format": {"type": "string", "enum": ["T20", "ODI", "Test", "All"], "default": "T20"},
        },
        "required": ["venue"],
    },
)
def venue_stats(venue: str, format: str = "T20") -> str:
    try:
        from backend.src.services.rag_service import build_rag_context
        context = build_rag_context(f"venue stats {venue}", {"format": format})
        data = context.get("cricsheet_data", "")
        if not data:
            return f"No venue data found for '{venue}'."
        return f"## 🏟️ Venue Stats — {venue} ({format})\n\n{data}"
    except Exception as e:
        log.error("venue_stats failed: %s", e)
        return f"Error fetching venue data: {e}"


@_tool(
    name="recent_form",
    description=(
        "Get a player's recent form — last N innings performance. "
        "Returns innings-by-innings scores, strike rates, and form trend."
    ),
    parameters={
        "type": "object",
        "properties": {
            "player_name": {"type": "string", "description": "Player name"},
            "format": {"type": "string", "enum": ["T20", "ODI", "Test", "All"], "default": "T20"},
        },
        "required": ["player_name"],
    },
)
def recent_form(player_name: str, format: str = "T20") -> str:
    try:
        from backend.src.services.rag_service import build_rag_context
        context = build_rag_context(f"{player_name} recent form last 10 innings", {"format": format})
        data = context.get("cricsheet_data", "")
        if not data:
            return f"No recent form data found for '{player_name}'."
        return f"## 📈 {player_name} — Recent Form ({format})\n\n{data}"
    except Exception as e:
        log.error("recent_form failed: %s", e)
        return f"Error fetching form data: {e}"


@_tool(
    name="team_matchup",
    description=(
        "Get team vs team historical matchup stats. "
        "Returns win/loss record, average scores, recent results."
    ),
    parameters={
        "type": "object",
        "properties": {
            "team_a": {"type": "string", "description": "First team name"},
            "team_b": {"type": "string", "description": "Second team name"},
            "format": {"type": "string", "enum": ["T20", "ODI", "Test", "All"], "default": "T20"},
        },
        "required": ["team_a", "team_b"],
    },
)
def team_matchup(team_a: str, team_b: str, format: str = "T20") -> str:
    try:
        from backend.src.services.rag_service import build_rag_context
        context = build_rag_context(f"{team_a} vs {team_b} head to head team record", {"format": format})
        data = context.get("cricsheet_data", "")
        if not data:
            return f"No matchup data found for {team_a} vs {team_b}."
        return f"## 🏆 {team_a} vs {team_b} ({format})\n\n{data}"
    except Exception as e:
        log.error("team_matchup failed: %s", e)
        return f"Error fetching team matchup: {e}"


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
