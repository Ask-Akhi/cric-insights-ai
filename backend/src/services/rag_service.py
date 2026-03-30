"""
RAG (Retrieval-Augmented Generation) service.
Enriches the LLM context with Cricsheet ball-by-ball stats:
  - Per-player batting/bowling stats
  - Venue ground records (avg scores, top performers)
  - Head-to-head team history
  - Per-player fantasy prediction data (expected runs/wickets, form, venue avg)
"""
from __future__ import annotations
import re
from typing import Any, Dict, List, Optional

from ..routers.players import PLAYER_ALIASES

_ALIAS_KEYS: List[str] = sorted(PLAYER_ALIASES.keys(), key=len, reverse=True)

# Match player names even when followed by possessive 's or 's (e.g. "Kohli's", "Kohlis")
_PLAYER_RE = re.compile(
    r'(?<!\w)(' + '|'.join(re.escape(k) for k in _ALIAS_KEYS) + r")(?:'?s)?(?!\w)",
    re.IGNORECASE,
)

_CRICKET_KEYWORDS = {
    "cricket", "ipl", "t20", "odi", "test match", "wicket", "batting",
    "bowling", "run", "over", "innings", "batter", "bowler", "fielding",
    "six", "four", "century", "fifty", "stumped", "lbw", "caught",
    "squad", "team", "match", "series", "world cup", "pitch", "crease",
    "powerplay", "death over", "spinner", "pacer", "all-rounder",
    "fantasy", "captain", "player", "stats", "average", "strike rate",
    "economy", "yorker", "googly", "wrist spin", "off spin", "leg spin",
    "drs", "umpire", "review", "boundary",
}

# ── Known T20I / international team aliases ─────────────────────────────────
_TEAM_ALIASES: Dict[str, str] = {
    "india": "India", "ind": "India",
    "australia": "Australia", "aus": "Australia",
    "england": "England", "eng": "England",
    "pakistan": "Pakistan", "pak": "Pakistan",
    "new zealand": "New Zealand", "nz": "New Zealand",
    "south africa": "South Africa", "sa": "South Africa",
    "west indies": "West Indies", "wi": "West Indies",
    "sri lanka": "Sri Lanka", "sl": "Sri Lanka",
    "bangladesh": "Bangladesh", "ban": "Bangladesh",
    "afghanistan": "Afghanistan", "afg": "Afghanistan",
    "zimbabwe": "Zimbabwe", "zim": "Zimbabwe",
    "ireland": "Ireland", "ire": "Ireland",
    "scotland": "Scotland", "scot": "Scotland",
    "netherlands": "Netherlands", "ned": "Netherlands",
    "uae": "United Arab Emirates",
    "nepal": "Nepal",
    "oman": "Oman",
    "namibia": "Namibia",
    # IPL teams
    "mumbai indians": "Mumbai Indians", "mi": "Mumbai Indians",
    "chennai super kings": "Chennai Super Kings", "csk": "Chennai Super Kings",
    "royal challengers bangalore": "Royal Challengers Bangalore", "rcb": "Royal Challengers Bangalore",
    "kolkata knight riders": "Kolkata Knight Riders", "kkr": "Kolkata Knight Riders",
    "sunrisers hyderabad": "Sunrisers Hyderabad", "srh": "Sunrisers Hyderabad",
    "rajasthan royals": "Rajasthan Royals", "rr": "Rajasthan Royals",
    "delhi capitals": "Delhi Capitals", "dc": "Delhi Capitals",
    "punjab kings": "Punjab Kings", "pbks": "Punjab Kings",
    "lucknow super giants": "Lucknow Super Giants", "lsg": "Lucknow Super Giants",
    "gujarat titans": "Gujarat Titans", "gt": "Gujarat Titans",
}

# Sorted longest-first so multi-word aliases match before short ones
_TEAM_KEYS: List[str] = sorted(_TEAM_ALIASES.keys(), key=len, reverse=True)
_TEAM_RE = re.compile(
    r'(?<!\w)(' + '|'.join(re.escape(k) for k in _TEAM_KEYS) + r')(?!\w)',
    re.IGNORECASE,
)

# Common venue keywords to detect ground mentions
_VENUE_PATTERNS = [
    r'\bat\s+([A-Z][A-Za-z\s]+(?:Stadium|Ground|Oval|Park|Arena|Bowl|Gardens?|Field))',
    r'([A-Z][A-Za-z\s]+(?:Stadium|Ground|Oval|Park|Arena|Bowl|Gardens?|Field))',
]
_VENUE_RE = re.compile('|'.join(_VENUE_PATTERNS))


def detect_players_in_prompt(prompt: str) -> List[str]:
    found: List[str] = []
    seen: set = set()
    for m in _PLAYER_RE.finditer(prompt):
        alias = m.group(1).lower()
        canonical = PLAYER_ALIASES.get(alias)
        if canonical and canonical not in seen:
            found.append(canonical)
            seen.add(canonical)
    return found


def detect_teams_in_prompt(prompt: str) -> List[str]:
    """Return up to 2 canonical team names found in the prompt."""
    found: List[str] = []
    seen: set = set()
    for m in _TEAM_RE.finditer(prompt):
        alias = m.group(1).lower()
        canonical = _TEAM_ALIASES.get(alias)
        if canonical and canonical not in seen:
            found.append(canonical)
            seen.add(canonical)
            if len(found) == 2:
                break
    return found


def detect_venue_in_prompt(prompt: str) -> Optional[str]:
    """Return the first venue/ground name found in the prompt."""
    m = _VENUE_RE.search(prompt)
    if m:
        return (m.group(1) or m.group(2) or "").strip()
    return None


def is_cricket_question(prompt: str) -> bool:
    lower = prompt.lower()
    if any(kw in lower for kw in _CRICKET_KEYWORDS):
        return True
    if _PLAYER_RE.search(prompt):
        return True
    return False


def _format_batter(player: str, data: Dict[str, Any], fmt: str) -> str:
    lines = [f"CRICSHEET BATTER STATS - {player} ({fmt}):"]
    lines.append(
        f"  Matches={data['total_matches']}  Runs={data['total_runs']}  "
        f"Avg={data['average']}  SR={data['strike_rate']}  "
        f"4s={data['fours']}  6s={data['sixes']}"
    )
    if data.get("format_runs"):
        s = ", ".join(f"{r['format']}:{r['runs']}runs/{r['matches']}M" for r in data["format_runs"])
        lines.append(f"  By format: {s}")
    if data.get("runs_per_match"):
        recent = data["runs_per_match"][-5:]
        s = ", ".join(f"{r['runs']}({r['balls']}b)" for r in recent)
        lines.append(f"  Last 5 innings: {s}")
    if data.get("dismissals"):
        s = ", ".join(f"{d['type']}:{d['count']}" for d in data["dismissals"])
        lines.append(f"  Dismissal types: {s}")
    return "\n".join(lines)


def _format_bowler(player: str, data: Dict[str, Any], fmt: str) -> str:
    lines = [f"CRICSHEET BOWLER STATS - {player} ({fmt}):"]
    lines.append(
        f"  Matches={data['total_matches']}  Wickets={data['total_wickets']}  "
        f"Avg={data['average']}  Econ={data['economy']}  SR={data['strike_rate']}"
    )
    if data.get("format_wickets"):
        s = ", ".join(f"{r['format']}:{r['wickets']}W/{r['matches']}M" for r in data["format_wickets"])
        lines.append(f"  By format: {s}")
    if data.get("wickets_per_match"):
        recent = data["wickets_per_match"][-5:]
        s = ", ".join(f"{r['wickets']}W(econ:{r['economy']})" for r in recent)
        lines.append(f"  Last 5 matches: {s}")
    return "\n".join(lines)


def fetch_player_context(player_names: List[str], fmt: str = "T20") -> str:
    if not player_names:
        return ""
    try:
        from ..routers.players import get_player_stats
    except Exception:
        return ""
    blocks: List[str] = []
    for player in player_names[:3]:
        try:
            result = get_player_stats(player_name=player, format=fmt)
            if not result.get("found"):
                continue
            batter = result.get("batter")
            bowler = result.get("bowler")
            if batter:
                blocks.append(_format_batter(player, batter, fmt))
            if bowler:
                blocks.append(_format_bowler(player, bowler, fmt))
        except Exception:
            continue
    return "\n\n".join(blocks)


def fetch_venue_context(venue: str, fmt: str = "T20") -> str:
    """Fetch and format venue/ground records from Cricsheet."""
    try:
        import polars as pl
        from ..providers.cricsheet_provider import CricsheetProvider
        provider = CricsheetProvider()
        provider.load()
        df = provider.get_venue_stats(venue, fmt=fmt)
        if df.is_empty():
            return ""

        matches = df.select(pl.col("match_id").n_unique()).item()
        by_innings = (
            df.group_by(["match_id", "innings"])
            .agg(pl.col("runs_off_bat").sum().alias("runs"))
            .group_by("innings")
            .agg(pl.col("runs").mean().alias("avg_runs"))
            .sort("innings")
        )
        avg_1st = avg_2nd = None
        for row in by_innings.iter_rows(named=True):
            if row["innings"] == 1:
                avg_1st = round(float(row["avg_runs"]), 1)
            elif row["innings"] == 2:
                avg_2nd = round(float(row["avg_runs"]), 1)

        top_scorers = (
            df.group_by("batter")
            .agg(pl.col("runs_off_bat").sum().alias("runs"))
            .sort("runs", descending=True).head(5).to_dicts()
        )
        top_wickets = (
            df.filter(pl.col("player_dismissed").is_not_null())
            .group_by("bowler").len().rename({"len": "wickets"})
            .sort("wickets", descending=True).head(5).to_dicts()
        )

        lines = [f"CRICSHEET VENUE RECORD - {venue} ({fmt}, {matches} matches):"]
        if avg_1st:
            lines.append(f"  Avg 1st innings score: {avg_1st}")
        if avg_2nd:
            lines.append(f"  Avg 2nd innings score: {avg_2nd}")
        if top_scorers:
            s = ", ".join(f"{r['batter']}({r['runs']})" for r in top_scorers)
            lines.append(f"  Top run-scorers at venue: {s}")
        if top_wickets:
            s = ", ".join(f"{r['bowler']}({r['wickets']}W)" for r in top_wickets)
            lines.append(f"  Top wicket-takers at venue: {s}")
        return "\n".join(lines)
    except Exception:
        return ""


def fetch_h2h_context(team_a: str, team_b: str, fmt: str = "T20") -> str:
    """Fetch and format head-to-head history between two teams."""
    try:
        import polars as pl
        from ..providers.cricsheet_provider import CricsheetProvider
        provider = CricsheetProvider()
        provider.load()
        df = provider.get_head_to_head(team_a, team_b, fmt=fmt)
        if df.is_empty():
            return ""

        total = df.select(pl.col("match_id").n_unique()).item()
        wins_a = df.filter(pl.col("winner") == team_a).select(pl.col("match_id").n_unique()).item()
        wins_b = df.filter(pl.col("winner") == team_b).select(pl.col("match_id").n_unique()).item()

        top_bat_a = (
            df.filter(pl.col("batting_team") == team_a)
            .group_by("batter").agg(pl.col("runs_off_bat").sum().alias("runs"))
            .sort("runs", descending=True).head(3).to_dicts()
        )
        top_bat_b = (
            df.filter(pl.col("batting_team") == team_b)
            .group_by("batter").agg(pl.col("runs_off_bat").sum().alias("runs"))
            .sort("runs", descending=True).head(3).to_dicts()
        )

        lines = [
            f"CRICSHEET H2H - {team_a} vs {team_b} ({fmt}, {total} matches):",
            f"  {team_a} wins: {wins_a}  |  {team_b} wins: {wins_b}  |  No result: {total - wins_a - wins_b}",
        ]
        if top_bat_a:
            s = ", ".join(f"{r['batter']}({r['runs']})" for r in top_bat_a)
            lines.append(f"  Top {team_a} batters H2H: {s}")
        if top_bat_b:
            s = ", ".join(f"{r['batter']}({r['runs']})" for r in top_bat_b)
            lines.append(f"  Top {team_b} batters H2H: {s}")
        return "\n".join(lines)
    except Exception:
        return ""


def fetch_fantasy_prediction_context(player_names: List[str], venue: Optional[str], fmt: str = "T20") -> str:
    """
    Build a MARKDOWN TABLE of player fantasy predictions:
    | Player | Team | Role | Expected Runs | Expected Wickets | Est. Fantasy Pts | Pick Reason |
    
    Returns pre-formatted table so it always renders (not truncated).
    """
    if not player_names:
        return ""
    try:
        import polars as pl
        from ..providers.cricsheet_provider import CricsheetProvider
        provider = CricsheetProvider()
        provider.load()
        lf = provider.datasets.get("balls")
        if lf is None:
            return ""
    except Exception:
        return ""

    rows: List[dict] = []

    for player in player_names[:12]:  # cap at 12 for table size
        try:
            df = provider.get_player_events(player)
            if df.is_empty():
                continue

            # Detect role (batter, bowler, both)
            has_bat = not df.filter(pl.col("batter") == player).is_empty()
            has_bowl = not df.filter(pl.col("bowler") == player).is_empty()
            role = "Bat/Bowl" if (has_bat and has_bowl) else ("Bowler" if has_bowl else "Batter")
            
            exp_runs_str = "-"
            exp_wk_str = "-"
            exp_pts = 0
            pick_reason = ""

            # ── Batting prediction ────────────────────────────────────────
            if has_bat:
                bat = df.filter(pl.col("batter") == player)
                per_innings = (
                    bat.group_by(["match_id", "innings"])
                    .agg(pl.col("runs_off_bat").sum().alias("runs"))
                    .sort("match_id")
                )
                career_avg = float(per_innings["runs"].mean()) if per_innings.height > 0 else 0.0
                recent_avg = float(per_innings.tail(10)["runs"].mean()) if per_innings.height >= 3 else career_avg
                
                exp_runs = round(recent_avg * 0.7 + career_avg * 0.3, 1)
                bonus = 10 if exp_runs >= 50 else (20 if exp_runs >= 100 else 0)
                exp_pts_bat = round(exp_runs + bonus, 1)
                exp_runs_str = str(exp_runs)
                exp_pts += exp_pts_bat
                
                if recent_avg > career_avg * 1.1:
                    pick_reason = "Good form"

            # ── Bowling prediction ────────────────────────────────────────
            if has_bowl:
                bowl = df.filter(pl.col("bowler") == player)
                per_match_wk = (
                    bowl.group_by("match_id")
                    .agg(pl.col("player_dismissed").is_not_null().sum().alias("wk"))
                    .sort("match_id")
                )
                career_wk_avg = float(per_match_wk["wk"].mean()) if per_match_wk.height > 0 else 0.0
                recent_wk_avg = float(per_match_wk.tail(10)["wk"].mean()) if per_match_wk.height >= 3 else career_wk_avg
                
                exp_wk = round(recent_wk_avg * 0.7 + career_wk_avg * 0.3, 2)
                exp_pts_bowl = round(exp_wk * 25, 1)
                exp_wk_str = str(exp_wk)
                exp_pts += exp_pts_bowl
                
                if not pick_reason and recent_wk_avg > career_wk_avg * 1.1:
                    pick_reason = "Bowling form"

            if not pick_reason:
                pick_reason = "Consistent" if exp_pts > 0 else "Emerging"

            rows.append({
                "player": player,
                "team": "TBD",  # Would need team-player mapping; skip for now
                "role": role,
                "exp_runs": exp_runs_str,
                "exp_wk": exp_wk_str,
                "exp_pts": round(exp_pts, 1),
                "reason": pick_reason,
            })

        except Exception:
            continue

    # ── Build markdown table ──────────────────────────────────────────────────
    if not rows:
        return ""
    
    # Sort by expected fantasy pts descending
    rows.sort(key=lambda r: r["exp_pts"], reverse=True)
    
    table_lines = [
        "## Player Predictions Table",
        "",
        "| Player | Role | Expected Runs | Expected Wickets | Est. Fantasy Pts | Pick Reason |",
        "|---|---|---|---|---|---|",
    ]
    
    for row in rows:
        table_lines.append(
            f"| {row['player']} | {row['role']} | {row['exp_runs']} | {row['exp_wk']} | {row['exp_pts']} | {row['reason']} |"
        )
    
    return "\n".join(table_lines)


def build_rag_context(prompt: str, context: Dict[str, Any]) -> Dict[str, Any]:
    enriched = dict(context)
    fmt = str(context.get("format", "T20"))
    enriched["_is_cricket"] = is_cricket_question(prompt)

    # ── Detect entities ───────────────────────────────────────────────────────
    players = detect_players_in_prompt(prompt)
    teams   = detect_teams_in_prompt(prompt)
    venue   = detect_venue_in_prompt(prompt)

    cricsheet_blocks: List[str] = []

    # ── Player stats ──────────────────────────────────────────────────────────
    if players:
        stats_text = fetch_player_context(players, fmt=fmt)
        if stats_text:
            cricsheet_blocks.append(stats_text)
        enriched["detected_players"] = ", ".join(players)

    # ── Fantasy prediction data ───────────────────────────────────────────────
    is_fantasy_or_predict = any(
        kw in prompt.lower()
        for kw in ("fantasy", "predict", "top scorer", "top run", "expected", "who will score", "xi")
    )
    if is_fantasy_or_predict and players:
        fantasy_text = fetch_fantasy_prediction_context(players, venue, fmt=fmt)
        if fantasy_text:
            cricsheet_blocks.append(fantasy_text)

    # ── Venue/ground context ──────────────────────────────────────────────────
    if venue:
        venue_text = fetch_venue_context(venue, fmt=fmt)
        if venue_text:
            cricsheet_blocks.append(venue_text)
        enriched["venue"] = venue
    elif teams and len(teams) >= 1:
        # No explicit venue — try to fetch H2H which implies some ground context
        pass

    # ── Head-to-head context ──────────────────────────────────────────────────
    if len(teams) >= 2:
        h2h_text = fetch_h2h_context(teams[0], teams[1], fmt=fmt)
        if h2h_text:
            cricsheet_blocks.append(h2h_text)
        enriched["teams"] = f"{teams[0]} vs {teams[1]}"
    elif len(teams) == 1:
        enriched["teams"] = teams[0]

    if cricsheet_blocks:
        enriched["cricsheet_data"] = "\n\n".join(cricsheet_blocks)

    return enriched
