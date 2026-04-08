"""
MCP Server: Live Cricket Data

Wraps live_provider.py (RapidAPI/Cricbuzz → Sportmonks → CricAPI → Cricsheet
fallback chain) into discoverable MCP tools for toss, playing XI, live scores,
and recent results.

These tools let the orchestrator answer time-sensitive queries without web search.
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("mcp.live")

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
    name="live_scores",
    description=(
        "Get current live cricket match scores. Returns ongoing matches with "
        "team names, scores, overs, venue, and match status."
    ),
    parameters={
        "type": "object",
        "properties": {
            "format": {
                "type": "string",
                "enum": ["T20", "ODI", "Test", ""],
                "default": "",
                "description": "Filter by match format. Empty string for all formats.",
            },
            "limit": {
                "type": "integer",
                "default": 10,
                "description": "Maximum number of matches to return.",
            },
        },
        "required": [],
    },
)
def live_scores(format: str = "", limit: int = 10) -> str:
    try:
        from backend.src.providers.live_provider import fetch_live_matches

        fmt_filter = format if format else None
        matches, source = fetch_live_matches(format_filter=fmt_filter, limit=limit)

        if not matches:
            return "No live or recent cricket matches found at the moment."

        live = [m for m in matches if m.get("status") == "live"]
        recent = [m for m in matches if m.get("status") != "live"]

        parts: list[str] = []
        parts.append(f"## 🏏 Live Cricket Scores (via {source})\n")

        if live:
            parts.append("### 🔴 Live Now\n")
            for m in live:
                parts.append(_format_match(m))

        if recent:
            parts.append("### 📋 Recent Results\n")
            for m in recent[:limit]:
                parts.append(_format_match(m))

        return "\n".join(parts)
    except Exception as e:
        log.error("live_scores failed: %s", e)
        return f"Error fetching live scores: {e}"


@_tool(
    name="recent_matches",
    description=(
        "Get recently completed cricket match results. Returns scores, winners, "
        "venues, and dates for recent matches."
    ),
    parameters={
        "type": "object",
        "properties": {
            "format": {
                "type": "string",
                "enum": ["T20", "ODI", "Test", ""],
                "default": "",
                "description": "Filter by match format.",
            },
            "team": {
                "type": "string",
                "default": "",
                "description": "Filter by team name (partial match).",
            },
            "limit": {
                "type": "integer",
                "default": 10,
                "description": "Maximum number of matches to return.",
            },
        },
        "required": [],
    },
)
def recent_matches(format: str = "", team: str = "", limit: int = 10) -> str:
    try:
        from backend.src.providers.live_provider import fetch_live_matches

        fmt_filter = format if format else None
        matches, source = fetch_live_matches(format_filter=fmt_filter, limit=max(limit, 20))

        if team:
            team_lower = team.lower()
            matches = [
                m for m in matches
                if team_lower in m.get("team1", "").lower()
                or team_lower in m.get("team2", "").lower()
            ]

        # Prefer recent/completed matches
        recent = [m for m in matches if m.get("status") in ("recent", "completed")]
        if not recent:
            recent = matches  # show whatever is available

        recent = recent[:limit]
        if not recent:
            filter_desc = f" for {team}" if team else ""
            filter_desc += f" ({format})" if format else ""
            return f"No recent matches found{filter_desc}."

        parts: list[str] = [f"## 📋 Recent Match Results (via {source})\n"]
        for m in recent:
            parts.append(_format_match(m))

        return "\n".join(parts)
    except Exception as e:
        log.error("recent_matches failed: %s", e)
        return f"Error fetching recent matches: {e}"


@_tool(
    name="toss_info",
    description=(
        "Get toss information for current or recent matches. Returns which team "
        "won the toss and what they chose (bat/bowl). Useful for match predictions."
    ),
    parameters={
        "type": "object",
        "properties": {
            "team": {
                "type": "string",
                "default": "",
                "description": "Filter by team name (partial match).",
            },
            "format": {
                "type": "string",
                "enum": ["T20", "ODI", "Test", ""],
                "default": "",
                "description": "Filter by match format.",
            },
        },
        "required": [],
    },
)
def toss_info(team: str = "", format: str = "") -> str:
    """
    Toss details from live/recent data. The live_provider match dict
    doesn't expose toss directly, but we can extract it from Cricsheet
    static data for recent matches and note it for live ones.
    """
    try:
        from backend.src.providers.live_provider import fetch_live_matches

        fmt_filter = format if format else None
        matches, source = fetch_live_matches(format_filter=fmt_filter, limit=20)

        if team:
            team_lower = team.lower()
            matches = [
                m for m in matches
                if team_lower in m.get("team1", "").lower()
                or team_lower in m.get("team2", "").lower()
            ]

        if not matches:
            return f"No matches found to show toss info{' for ' + team if team else ''}."

        # Try to enrich with toss data from Cricsheet parquet
        toss_data = _get_toss_data([m.get("match_id", "") for m in matches])

        parts: list[str] = [f"## 🪙 Toss Information (via {source})\n"]
        parts.append("| Match | Toss Winner | Decision | Venue | Date |")
        parts.append("|-------|-------------|----------|-------|------|")

        for m in matches[:10]:
            mid = m.get("match_id", "")
            toss = toss_data.get(mid, {})
            toss_winner = toss.get("toss_winner", "N/A")
            toss_decision = toss.get("toss_decision", "N/A")
            label = f"{m.get('team1', '?')} vs {m.get('team2', '?')}"
            venue = m.get("venue", "")
            date = m.get("date", "")
            parts.append(
                f"| {label} | {toss_winner} | {toss_decision} | {venue} | {date} |"
            )

        return "\n".join(parts)
    except Exception as e:
        log.error("toss_info failed: %s", e)
        return f"Error fetching toss information: {e}"


@_tool(
    name="match_status",
    description=(
        "Get the current status of a specific match or all matches involving a team. "
        "Returns whether the match is live, completed, or upcoming."
    ),
    parameters={
        "type": "object",
        "properties": {
            "team": {
                "type": "string",
                "description": "Team name to search for.",
            },
        },
        "required": ["team"],
    },
)
def match_status(team: str) -> str:
    try:
        from backend.src.providers.live_provider import fetch_live_matches

        matches, source = fetch_live_matches(limit=20)
        team_lower = team.lower()
        matches = [
            m for m in matches
            if team_lower in m.get("team1", "").lower()
            or team_lower in m.get("team2", "").lower()
        ]

        if not matches:
            return f"No current or recent matches found for '{team}'."

        parts: list[str] = [f"## 📊 Match Status for {team} (via {source})\n"]
        for m in matches:
            status_emoji = {"live": "🔴", "upcoming": "🔜", "recent": "✅"}.get(
                m.get("status", ""), "❓"
            )
            parts.append(
                f"- {status_emoji} **{m.get('team1', '?')} vs {m.get('team2', '?')}** "
                f"— {m.get('status', 'unknown').upper()}\n"
                f"  Score: {m.get('score', 'N/A') or 'N/A'}\n"
                f"  Venue: {m.get('venue', 'N/A')}, {m.get('date', '')}\n"
                f"  Format: {m.get('format', '')}, {m.get('competition', '')}"
            )
            if m.get("winner"):
                parts.append(f"  🏆 Winner: **{m['winner']}**")
            parts.append("")

        return "\n".join(parts)
    except Exception as e:
        log.error("match_status failed: %s", e)
        return f"Error fetching match status: {e}"


# ── Helpers ──────────────────────────────────────────────────────────────────


def _format_match(m: dict) -> str:
    """Format a single match dict into a readable markdown snippet."""
    status_emoji = {"live": "🔴", "upcoming": "🔜", "recent": "✅"}.get(
        m.get("status", ""), ""
    )
    label = f"{m.get('team1', '?')} vs {m.get('team2', '?')}"
    score = m.get("score", "") or "N/A"
    winner = f" — 🏆 {m['winner']}" if m.get("winner") else ""
    venue = m.get("venue", "")
    date = m.get("date", "")
    fmt = m.get("format", "")
    comp = m.get("competition", "")

    meta_parts = [x for x in [fmt, comp, venue, date] if x]
    meta = " | ".join(meta_parts)

    return f"- {status_emoji} **{label}**: {score}{winner}\n  {meta}\n"


def _get_toss_data(match_ids: list[str]) -> dict[str, dict]:
    """
    Try to fetch toss info from Cricsheet parquet data for given match IDs.
    Returns {match_id: {toss_winner, toss_decision}}.
    """
    if not match_ids:
        return {}
    try:
        from backend.src.providers.cricsheet_provider import CricsheetProvider
        import polars as pl

        provider = CricsheetProvider()
        provider.load()
        lf = provider.datasets.get("balls")
        if lf is None:
            return {}

        df = (
            lf.filter(pl.col("match_id").is_in(match_ids))
            .select(["match_id", "toss_winner", "toss_decision"])
            .unique(subset=["match_id"])
            .collect()
        )
        result = {}
        for row in df.iter_rows(named=True):
            result[row["match_id"]] = {
                "toss_winner": row.get("toss_winner", ""),
                "toss_decision": row.get("toss_decision", ""),
            }
        return result
    except Exception as e:
        log.debug("Could not fetch toss data from Cricsheet: %s", e)
        return {}


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
