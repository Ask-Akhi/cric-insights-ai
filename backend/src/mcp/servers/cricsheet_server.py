"""
MCP Server: Cricsheet Ball-by-Ball Data

Exposes cricket statistics as MCP tools.  Each tool calls the data
layer **directly** (get_player_stats, fetch_venue_context, etc.)
instead of routing through build_rag_context() which re-does entity
detection and fails on Cricsheet-format names like "V Kohli".
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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _format_batter_md(player: str, b: dict, fmt: str) -> str:
    """Format batter stats dict (from get_player_stats) as Markdown."""
    lines = [
        f"## 🏏 {player} — Batting Stats ({fmt})\n",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Matches | {b['total_matches']} |",
        f"| Runs | {b['total_runs']} |",
        f"| Average | {b['average']} |",
        f"| Strike Rate | {b['strike_rate']} |",
        f"| Fours | {b['fours']} |",
        f"| Sixes | {b['sixes']} |",
    ]
    if b.get("format_runs"):
        lines.append("\n**By Format:**")
        for r in b["format_runs"]:
            lines.append(f"- {r['format']}: {r['runs']} runs in {r['matches']} matches")
    if b.get("runs_per_match"):
        recent = b["runs_per_match"][-5:]
        lines.append("\n**Last 5 Innings:**")
        for r in recent:
            lines.append(f"- {r.get('match', '?')}: {r['runs']} ({r['balls']}b)")
    if b.get("dismissals"):
        lines.append("\n**Dismissal Types:**")
        for d in b["dismissals"]:
            lines.append(f"- {d['type']}: {d['count']}")
    return "\n".join(lines)


def _format_bowler_md(player: str, b: dict, fmt: str) -> str:
    """Format bowler stats dict (from get_player_stats) as Markdown."""
    lines = [
        f"## 🎳 {player} — Bowling Stats ({fmt})\n",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Matches | {b['total_matches']} |",
        f"| Wickets | {b['total_wickets']} |",
        f"| Average | {b['average']} |",
        f"| Economy | {b['economy']} |",
        f"| Strike Rate | {b['strike_rate']} |",
    ]
    if b.get("format_wickets"):
        lines.append("\n**By Format:**")
        for r in b["format_wickets"]:
            lines.append(f"- {r['format']}: {r['wickets']}W in {r['matches']} matches")
    if b.get("wickets_per_match"):
        recent = b["wickets_per_match"][-5:]
        lines.append("\n**Last 5 Matches:**")
        for r in recent:
            lines.append(f"- {r.get('match', '?')}: {r['wickets']}W (econ: {r['economy']})")
    return "\n".join(lines)


# ── Tools ─────────────────────────────────────────────────────────────────────

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
    """Fetch batting stats directly from get_player_stats (same path as right panel)."""
    try:
        from backend.src.routers.players import get_player_stats
        fmt_arg = None if format == "All" else format
        result = get_player_stats(player_name=player_name, format=fmt_arg)
        if not result.get("found"):
            return f"No batting data found for '{player_name}' in {format} format."
        batter = result.get("batter")
        if not batter:
            return f"'{player_name}' found but has no batting records in {format}."
        canonical = result.get("player", player_name)
        return _format_batter_md(canonical, batter, format)
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
    """Fetch bowling stats directly from get_player_stats (same path as right panel)."""
    try:
        from backend.src.routers.players import get_player_stats
        fmt_arg = None if format == "All" else format
        result = get_player_stats(player_name=player_name, format=fmt_arg)
        if not result.get("found"):
            return f"No bowling data found for '{player_name}' in {format} format."
        bowler = result.get("bowler")
        if not bowler:
            return f"'{player_name}' found but has no bowling records in {format}."
        canonical = result.get("player", player_name)
        return _format_bowler_md(canonical, bowler, format)
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
    """Fetch batter-vs-bowler head-to-head from raw Cricsheet data."""
    try:
        import polars as pl
        from backend.src.services.rag_service import _get_provider
        provider = _get_provider()
        if not provider.has_data:
            return "No head-to-head data available (data not loaded)."

        lf = provider.datasets.get("balls")
        if lf is None:
            return "No data available."

        q = lf.filter(
            (pl.col("batter") == batter) & (pl.col("bowler") == bowler)
        )
        if format != "All":
            if format == "T20":
                from backend.src.core.config import T20_FORMATS
                q = q.filter(pl.col("format").is_in(T20_FORMATS))
            else:
                q = q.filter(pl.col("format") == format)

        df = q.collect()
        if df.is_empty():
            return f"No head-to-head data found for {batter} vs {bowler} in {format}."

        runs = int(df.select(pl.col("runs_off_bat").sum()).item() or 0)
        balls = df.height
        dismissals = df.filter(pl.col("player_dismissed").is_not_null()).height
        sr = round(runs / balls * 100, 1) if balls > 0 else 0
        matches = df.select(pl.col("match_id").n_unique()).item()

        lines = [
            f"## ⚔️ {batter} vs {bowler} ({format})\n",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Matches | {matches} |",
            f"| Balls Faced | {balls} |",
            f"| Runs Scored | {runs} |",
            f"| Dismissals | {dismissals} |",
            f"| Strike Rate | {sr} |",
            f"| Average | {round(runs / max(dismissals, 1), 1)} |",
        ]
        return "\n".join(lines)
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
    """Fetch venue stats directly from rag_service.fetch_venue_context."""
    try:
        from backend.src.services.rag_service import fetch_venue_context
        fmt_arg = "" if format == "All" else format
        data = fetch_venue_context(venue, fmt=fmt_arg)
        if not data:
            return f"No venue data found for '{venue}' in {format} format."
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
    """Fetch recent form from get_player_stats (uses last N innings data)."""
    try:
        from backend.src.routers.players import get_player_stats
        fmt_arg = None if format == "All" else format
        result = get_player_stats(player_name=player_name, format=fmt_arg)
        if not result.get("found"):
            return f"No recent form data found for '{player_name}'."

        canonical = result.get("player", player_name)
        sections: list[str] = []

        batter = result.get("batter")
        if batter and batter.get("runs_per_match"):
            recent = batter["runs_per_match"][-10:]
            lines = [
                f"## 📈 {canonical} — Recent Batting Form ({format})\n",
                "| Match | Runs | Balls | SR |",
                "|-------|------|-------|----|",
            ]
            for r in recent:
                sr = round(r["runs"] / r["balls"] * 100, 1) if r["balls"] > 0 else 0
                lines.append(f"| {r.get('match', '?')} | {r['runs']} | {r['balls']} | {sr} |")
            avg_recent = round(sum(r["runs"] for r in recent) / len(recent), 1)
            lines.append(f"\n**Recent avg (last {len(recent)}): {avg_recent}**")
            lines.append(f"**Career average: {batter.get('average', '?')}**")
            sections.append("\n".join(lines))

        bowler = result.get("bowler")
        if bowler and bowler.get("wickets_per_match"):
            recent = bowler["wickets_per_match"][-10:]
            lines = [
                f"## 📈 {canonical} — Recent Bowling Form ({format})\n",
                "| Match | Wickets | Economy |",
                "|-------|---------|---------|",
            ]
            for r in recent:
                lines.append(f"| {r.get('match', '?')} | {r['wickets']} | {r['economy']} |")
            sections.append("\n".join(lines))

        return "\n\n".join(sections) if sections else f"No recent form data for '{player_name}'."
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
    """Fetch team matchup directly from rag_service.fetch_h2h_context."""
    try:
        from backend.src.services.rag_service import fetch_h2h_context
        fmt_arg = "" if format == "All" else format
        data = fetch_h2h_context(team_a, team_b, fmt=fmt_arg)
        if not data:
            return f"No matchup data found for {team_a} vs {team_b} in {format}."
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
