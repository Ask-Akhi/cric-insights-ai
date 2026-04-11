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


@_tool(    name="top_players",
    description=(
        "Rank the top N cricket players by a batting or bowling metric from Cricsheet data. "
        "Use this for queries like 'top 5 T20 batters by strike rate', "
        "'best bowlers by economy in ODI', 'most runs in IPL', etc. "
        "Metrics: batting — strike_rate, runs, average, sixes, fours; "
        "bowling — economy, wickets, average, strike_rate."
    ),
    parameters={
        "type": "object",
        "properties": {
            "metric":    {"type": "string",
                          "description": "Metric to rank by: strike_rate | runs | average | sixes | fours | economy | wickets",
                          "enum": ["strike_rate", "runs", "average", "sixes", "fours", "economy", "wickets"]},
            "role":      {"type": "string", "enum": ["batting", "bowling"], "default": "batting"},
            "format":    {"type": "string", "enum": ["T20", "ODI", "Test", "All"], "default": "T20"},
            "top_n":     {"type": "integer", "default": 10, "minimum": 3, "maximum": 25},
            "min_innings": {"type": "integer", "default": 30,
                            "description": "Minimum innings/matches to qualify (filters out small samples)"},
        },
        "required": ["metric"],
    },
)
def top_players(
    metric: str = "strike_rate",
    role: str = "batting",
    format: str = "T20",
    top_n: int = 10,    min_innings: int = 30,
) -> str:
    """Rank players by a metric directly from Cricsheet ball-by-ball data."""
    try:
        import polars as pl
        from backend.src.services.rag_service import _get_provider
        from backend.src.core.config import FORMAT_EXPANSION, MAJOR_T20_FORMATS

        provider = _get_provider()
        if not provider.has_data:
            return "No Cricsheet data available."

        lf = provider.datasets.get("balls")
        if lf is None:
            return "No data available."

        # Format filter — for T20 rankings use MAJOR_T20_FORMATS to exclude
        # Associate-level T20s ("T20" format code) where bowlers post 3.x economies
        # against weaker batters, polluting the leaderboard with unknown names.
        if format != "All":
            if format == "T20":
                allowed = MAJOR_T20_FORMATS
            else:
                allowed = FORMAT_EXPANSION.get(format, [format])
            lf = lf.filter(pl.col("format").is_in(allowed))

        if role == "batting":
            # Aggregate per batter — apply min_innings AND min_runs to avoid
            # obscure players with tiny samples dominating strike-rate rankings.
            MIN_RUNS = 500  # must have scored at least 500 runs to qualify
            bat = (
                lf.group_by("batter")
                .agg([
                    pl.col("match_id").n_unique().alias("innings"),
                    pl.col("runs_off_bat").sum().alias("runs"),
                    pl.col("runs_off_bat").count().alias("balls"),
                    pl.col("runs_off_bat").filter(pl.col("runs_off_bat") == 4).count().alias("fours"),
                    pl.col("runs_off_bat").filter(pl.col("runs_off_bat") == 6).count().alias("sixes"),
                    pl.col("player_dismissed").is_not_null().sum().alias("dismissals"),
                ])
                .filter(
                    (pl.col("innings") >= min_innings) &
                    (pl.col("runs") >= MIN_RUNS)
                )
                .with_columns([
                    (pl.col("runs") / pl.col("balls") * 100).round(1).alias("strike_rate"),
                    (pl.col("runs") / (pl.col("dismissals") + 0.001)).round(1).alias("average"),
                ])
                .collect()
            )

            sort_col = {
                "strike_rate": "strike_rate",
                "runs": "runs",
                "average": "average",
                "sixes": "sixes",
                "fours": "fours",
            }.get(metric, "strike_rate")

            top = bat.sort(sort_col, descending=True).head(top_n)

            metric_label = {
                "strike_rate": "SR", "runs": "Runs",
                "average": "Avg", "sixes": "6s", "fours": "4s",
            }.get(metric, metric)

            # Build header — skip metric col if it duplicates a fixed column
            fixed_cols = ["Runs", "Innings", "SR", "Avg"]
            show_metric_col = metric_label not in fixed_cols
            if show_metric_col:
                header = f"| # | Player | {metric_label} | Runs | Inn | SR | Avg |"
                sep    = f"|---|--------|{'-'*(len(metric_label)+2)}|------|-----|----|----|"
            else:
                header = "| # | Player | Runs | Inn | SR | Avg |"
                sep    = "|---|--------|------|-----|----|----|"

            lines = [
                f"## 🏏 Top {top_n} {format} Batters by {metric_label}\n",
                header, sep,
            ]
            for i, row in enumerate(top.iter_rows(named=True), 1):
                if show_metric_col:
                    val = row[sort_col]
                    lines.append(
                        f"| {i} | {row['batter']} | **{val}** | "
                        f"{row['runs']} | {row['innings']} | "
                        f"{row['strike_rate']} | {row['average']} |"
                    )
                else:
                    # metric IS one of the fixed columns — bold it inline
                    runs_s = f"**{row['runs']}**" if metric_label == "Runs" else str(row['runs'])
                    inn_s  = str(row['innings'])
                    sr_s   = f"**{row['strike_rate']}**" if metric_label == "SR" else str(row['strike_rate'])
                    avg_s  = f"**{row['average']}**" if metric_label == "Avg" else str(row['average'])
                    lines.append(f"| {i} | {row['batter']} | {runs_s} | {inn_s} | {sr_s} | {avg_s} |")

            lines.append(f"\n*Min {min_innings} innings · {MIN_RUNS}+ runs. Source: Cricsheet.*")
            return "\n".join(lines)

        else:  # bowling
            MIN_WICKETS = 75   # must have 75+ wickets (filters Associates/low-volume bowlers)
            MIN_BALLS   = 900  # must have bowled 150+ overs in major T20 cricket
            bowl = (
                lf.filter(pl.col("bowler").is_not_null())
                .group_by("bowler")
                .agg([
                    pl.col("match_id").n_unique().alias("matches"),
                    pl.col("runs_off_bat").sum().alias("runs_conceded"),
                    (pl.col("wides").is_null() | (pl.col("wides") == 0)).sum().alias("legal_balls"),
                    pl.col("player_dismissed").is_not_null().sum().alias("wickets"),
                ])
                .filter(
                    (pl.col("matches") >= min_innings) &
                    (pl.col("wickets") >= MIN_WICKETS) &
                    (pl.col("legal_balls") >= MIN_BALLS)
                )
                .with_columns([
                    (pl.col("runs_conceded") / (pl.col("legal_balls") / 6 + 0.001)).round(2).alias("economy"),
                    (pl.col("runs_conceded") / (pl.col("wickets") + 0.001)).round(1).alias("average"),
                    (pl.col("legal_balls") / (pl.col("wickets") + 0.001)).round(1).alias("strike_rate"),
                ])
                .collect()
            )

            sort_col = {
                "economy": "economy",
                "wickets": "wickets",
                "average": "average",
                "strike_rate": "strike_rate",
            }.get(metric, "economy")
            # For economy/average/SR, lower is better
            descending = metric in ("wickets",)

            top = bowl.sort(sort_col, descending=descending).head(top_n)
            metric_label = {
                "economy": "Econ", "wickets": "Wkts",
                "average": "Avg", "strike_rate": "SR",
            }.get(metric, metric)

            # Build header — skip metric col if it duplicates a fixed column
            fixed_cols_b = ["Wkts", "Matches", "Econ", "Avg"]
            show_metric_col = metric_label not in fixed_cols_b
            if show_metric_col:
                header = f"| # | Player | {metric_label} | Wkts | Matches | Econ | Avg |"
                sep    = f"|---|--------|{'-'*(len(metric_label)+2)}|------|---------|------|-----|"
            else:
                header = "| # | Player | Wkts | Matches | Econ | Avg |"
                sep    = "|---|--------|------|---------|------|-----|"

            lines = [
                f"## 🎳 Top {top_n} {format} Bowlers by {metric_label}\n",
                header, sep,
            ]
            for i, row in enumerate(top.iter_rows(named=True), 1):
                if show_metric_col:
                    val = row[sort_col]
                    lines.append(
                        f"| {i} | {row['bowler']} | **{val}** | "
                        f"{row['wickets']} | {row['matches']} | "
                        f"{row['economy']} | {row['average']} |"
                    )
                else:
                    wkts_s = f"**{row['wickets']}**" if metric_label == "Wkts" else str(row['wickets'])
                    mat_s  = str(row['matches'])
                    econ_s = f"**{row['economy']}**" if metric_label == "Econ" else str(row['economy'])
                    avg_s  = f"**{row['average']}**" if metric_label == "Avg" else str(row['average'])
                    lines.append(f"| {i} | {row['bowler']} | {wkts_s} | {mat_s} | {econ_s} | {avg_s} |")

            lines.append(f"\n*Min {min_innings} matches · {MIN_WICKETS}+ wkts · {MIN_BALLS//6}+ overs · major T20 formats only. Source: Cricsheet.*")
            return "\n".join(lines)

    except Exception as e:
        log.error("top_players failed: %s", e)
        return f"Error fetching top players: {e}"


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
