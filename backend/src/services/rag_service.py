"""
RAG (Retrieval-Augmented Generation) service.
Enriches the LLM context with Cricsheet ball-by-ball stats:
  - Per-player batting/bowling stats
  - Venue ground records (avg scores, top performers)
  - Head-to-head team history
  - Per-player fantasy prediction data (expected runs/wickets, form, venue avg)

Cross-encoder reranking: context blocks are scored against the query and only
the top-k most relevant blocks are injected into the LLM prompt. This:
  - Reduces prompt length → faster LLM response
  - Improves answer quality (less noise in context)
  - Avoids hitting token budget limits on large squad queries
"""
from __future__ import annotations
import logging
import re
import time
import hashlib
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

# Cross-encoder reranker (pure Python, zero extra dependencies)
from .reranker import rerank_context_blocks, split_cricsheet_into_blocks

# ── Singleton CricsheetProvider — loaded ONCE per worker process ─────────────
# Every fetch_* function below re-used this instead of calling
# CricsheetProvider().load() which re-scans all parquet files each call.
_cricsheet_provider = None
_cricsheet_lock = None

def _get_provider():
    """Return the module-level singleton CricsheetProvider, loading it once.
    Reuses the players router's singleton if available to avoid double parquet load."""
    global _cricsheet_provider, _cricsheet_lock
    import threading
    if _cricsheet_lock is None:
        _cricsheet_lock = threading.Lock()
    if _cricsheet_provider is None:
        with _cricsheet_lock:
            if _cricsheet_provider is None:
                try:
                    # Prefer the already-loaded players router singleton
                    from ..routers.players import _get_provider as _players_provider
                    _cricsheet_provider = _players_provider()
                except Exception:
                    from ..providers.cricsheet_provider import CricsheetProvider
                    p = CricsheetProvider()
                    p.load()
                    _cricsheet_provider = p
    return _cricsheet_provider

# ── RAG-level cache: cache the fully-built rag context so repeated identical
#    queries (same prompt + same format) skip all Cricsheet I/O entirely.
#    Key = MD5 of (prompt + format). TTL = 10 minutes.
_RAG_CACHE: Dict[str, Dict] = {}
_RAG_CACHE_TTL = 600  # 10 minutes


def _rag_cache_key(prompt: str, fmt: str) -> str:
    return hashlib.md5(f"{prompt.strip().lower()}|{fmt}".encode()).hexdigest()


def _get_rag_cached(key: str) -> Dict | None:
    entry = _RAG_CACHE.get(key)
    if entry and (time.time() - entry["ts"]) < _RAG_CACHE_TTL:
        return entry["data"]
    return None


def _set_rag_cached(key: str, data: Dict) -> None:
    if len(_RAG_CACHE) >= 200:
        oldest = min(_RAG_CACHE, key=lambda k: _RAG_CACHE[k]["ts"])
        del _RAG_CACHE[oldest]
    _RAG_CACHE[key] = {"data": data, "ts": time.time()}

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
        provider = _get_provider()
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
        provider = _get_provider()
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


def _get_team_recent_players(team: str, fmt: str = "T20", limit: int = 11) -> List[str]:
    """Get the most recently active players for a team from Cricsheet data.

    Looks at the last 5 matches for the team and returns players who appeared
    most frequently (approximating the current squad).
    """
    try:
        import polars as pl
        provider = _get_provider()
        lf = provider.datasets.get("balls")
        if lf is None:
            return []

        # Find last 5 match_ids where this team batted
        team_lower = team.lower()
        matches = (
            lf.filter(pl.col("batting_team").str.to_lowercase().str.contains(team_lower))
            .filter(pl.col("format") == fmt)
            .select(["match_id", "start_date"])
            .unique(subset=["match_id"])
            .sort("start_date", descending=True)
            .head(5)
            .collect()
        )
        if matches.is_empty():
            # Fallback: try without format filter
            matches = (
                lf.filter(pl.col("batting_team").str.to_lowercase().str.contains(team_lower))
                .select(["match_id", "start_date"])
                .unique(subset=["match_id"])
                .sort("start_date", descending=True)
                .head(5)
                .collect()
            )
        if matches.is_empty():
            return []

        match_ids = matches.get_column("match_id").to_list()

        # Get all batters + bowlers from those matches who played for this team
        df = (
            lf.filter(pl.col("match_id").is_in(match_ids))
            .collect()
        )

        # Batters from this team
        batters = (
            df.filter(pl.col("batting_team").str.to_lowercase().str.contains(team_lower))
            .select(pl.col("batter").alias("player"))
        )
        # Bowlers bowling AGAINST this team are FROM the other team — we want
        # bowlers FROM this team, which means they bowled when the OTHER team batted
        bowlers = (
            df.filter(~pl.col("batting_team").str.to_lowercase().str.contains(team_lower))
            .select(pl.col("bowler").alias("player"))
        )

        combined = (
            pl.concat([batters, bowlers], how="vertical")
            .filter(pl.col("player").is_not_null())
            .group_by("player")
            .agg(pl.len().alias("appearances"))
            .sort("appearances", descending=True)
            .head(limit)
        )
        return combined.get_column("player").to_list()
    except Exception:
        return []


def _detect_player_team(player: str, team_a: str, team_b: str) -> str:
    """Determine which team a player belongs to from recent Cricsheet data."""
    try:
        import polars as pl
        provider = _get_provider()
        df = provider.get_player_events(player)
        if df.is_empty():
            return "?"

        # Check which team this player batted for most recently
        bat_df = df.filter(pl.col("batter") == player)
        if not bat_df.is_empty():
            last_team = (
                bat_df.sort("start_date", descending=True)
                .head(1)
                .get_column("batting_team")
                .to_list()[0]
            )
            if last_team:
                ta_lower = team_a.lower()
                tb_lower = team_b.lower()
                lt_lower = last_team.lower()
                if ta_lower in lt_lower or lt_lower in ta_lower:
                    return team_a
                if tb_lower in lt_lower or lt_lower in tb_lower:
                    return team_b
                return last_team
        return "?"
    except Exception:
        return "?"


def fetch_fantasy_prediction_context(
    player_names: List[str],
    venue: Optional[str],
    fmt: str = "T20",
    team_a: str = "",
    team_b: str = "",
) -> str:
    """
    Build a MARKDOWN TABLE of player fantasy predictions using an improved model:
      - Career avg + recent form (last 10) + venue factor + form trend
      - Correct milestone bonus logic
      - Team detection from Cricsheet data
      - Richer pick-reason labels

    Returns pre-formatted markdown table injected into RAG context.
    """
    if not player_names:
        return ""
    try:
        import polars as pl
        provider = _get_provider()
        lf = provider.datasets.get("balls")
        if lf is None:
            return ""
    except Exception:
        return ""

    # ── Pre-compute venue averages if venue is provided ───────────────────────
    venue_avg_runs: Optional[float] = None
    if venue:
        try:
            vdf = provider.get_venue_stats(venue, fmt=fmt)
            if not vdf.is_empty():
                venue_avg_runs = float(
                    vdf.group_by(["match_id", "innings"])
                    .agg(pl.col("runs_off_bat").sum().alias("runs"))
                    ["runs"].mean()
                )
        except Exception:
            pass

    rows: List[dict] = []

    for player in player_names[:14]:  # cap at 14 for table size
        try:
            df = provider.get_player_events(player)
            if df.is_empty():
                continue

            # Filter to format
            df_fmt = df.filter(pl.col("format") == fmt)
            if df_fmt.is_empty():
                df_fmt = df  # fallback to all formats if no data in this format

            # Detect role
            has_bat = not df_fmt.filter(pl.col("batter") == player).is_empty()
            has_bowl = not df_fmt.filter(pl.col("bowler") == player).is_empty()
            if has_bat and has_bowl:
                # Check balance — more bat innings than bowl innings?
                bat_count = df_fmt.filter(pl.col("batter") == player).select(pl.col("match_id").n_unique()).item()
                bowl_count = df_fmt.filter(pl.col("bowler") == player).select(pl.col("match_id").n_unique()).item()
                if bat_count > bowl_count * 2:
                    role = "BAT"
                elif bowl_count > bat_count * 2:
                    role = "BWL"
                else:
                    role = "AR"
            elif has_bowl:
                role = "BWL"
            else:
                role = "BAT"

            exp_runs = 0.0
            exp_wk = 0.0
            exp_pts = 0.0
            reasons: List[str] = []

            # ── Batting prediction (improved model) ───────────────────────
            if has_bat:
                bat = df_fmt.filter(pl.col("batter") == player)
                per_innings = (
                    bat.group_by(["match_id", "innings"])
                    .agg(pl.col("runs_off_bat").sum().alias("runs"))
                    .sort("match_id")
                )
                total_innings = per_innings.height
                if total_innings == 0:
                    career_avg = 0.0
                    recent_avg = 0.0
                else:
                    career_avg = float(per_innings["runs"].mean())
                    # Recent form: last 10 innings (or fewer if not enough data)
                    recent_n = min(10, total_innings)
                    recent = per_innings.tail(recent_n)
                    recent_avg = float(recent["runs"].mean())

                    # Form trend: compare last 5 vs previous 5
                    if total_innings >= 10:
                        last5 = float(per_innings.tail(5)["runs"].mean())
                        prev5 = float(per_innings.tail(10).head(5)["runs"].mean())
                        if last5 > prev5 * 1.15:
                            reasons.append("🔥 Hot form")
                        elif last5 < prev5 * 0.75:
                            reasons.append("📉 Dip in form")

                # Weighted prediction: recent 50%, career 30%, venue 20%
                venue_adj = 1.0
                if venue_avg_runs is not None and career_avg > 0:
                    # If venue avg is higher than overall T20 avg (~25), boost; else reduce
                    overall_avg = 25.0  # typical T20 innings avg
                    venue_adj = 0.8 + 0.4 * (venue_avg_runs / max(overall_avg, 1))
                    venue_adj = max(0.7, min(1.4, venue_adj))  # clamp

                exp_runs = round(recent_avg * 0.5 + career_avg * 0.3 + recent_avg * 0.2 * venue_adj, 1)

                # Fantasy points for batting (milestone bonuses fixed)
                if exp_runs >= 100:
                    bonus = 20
                elif exp_runs >= 50:
                    bonus = 10
                elif exp_runs >= 30:
                    bonus = 4
                else:
                    bonus = 0
                # SR bonus: Dream11 gives +6 for SR>170 in T20
                sr_bonus = 0
                if total_innings > 0:
                    total_balls = bat.select(pl.len()).item()
                    total_runs_raw = float(bat.select(pl.col("runs_off_bat").sum()).item())
                    if total_balls > 0:
                        career_sr = total_runs_raw / total_balls * 100
                        if career_sr > 170:
                            sr_bonus = 6
                        elif career_sr > 150:
                            sr_bonus = 4

                exp_pts += exp_runs + bonus + sr_bonus

            # ── Bowling prediction (improved model) ───────────────────────
            if has_bowl:
                bowl = df_fmt.filter(pl.col("bowler") == player)
                per_match_wk = (
                    bowl.group_by("match_id")
                    .agg(pl.col("player_dismissed").is_not_null().sum().alias("wk"))
                    .sort("match_id")
                )
                total_matches = per_match_wk.height
                if total_matches == 0:
                    career_wk_avg = 0.0
                    recent_wk_avg = 0.0
                else:
                    career_wk_avg = float(per_match_wk["wk"].mean())
                    recent_n = min(10, total_matches)
                    recent_wk_avg = float(per_match_wk.tail(recent_n)["wk"].mean())

                    if total_matches >= 10:
                        last5_wk = float(per_match_wk.tail(5)["wk"].mean())
                        prev5_wk = float(per_match_wk.tail(10).head(5)["wk"].mean())
                        if last5_wk > prev5_wk * 1.2:
                            reasons.append("🎯 Wicket-taking form")

                exp_wk = round(recent_wk_avg * 0.6 + career_wk_avg * 0.4, 2)

                # Economy-based bonus
                econ_bonus = 0
                total_bowl_balls = bowl.select(pl.len()).item()
                total_bowl_runs = float(bowl.select((pl.col("runs_off_bat") + pl.col("extras")).sum()).item())
                if total_bowl_balls > 0:
                    career_econ = total_bowl_runs / (total_bowl_balls / 6)
                    if career_econ < 7.0:
                        econ_bonus = 4
                    elif career_econ < 8.0:
                        econ_bonus = 2

                # Fantasy points for bowling (25 per wicket is Dream11 standard)
                exp_pts += round(exp_wk * 25 + econ_bonus, 1)

            # ── Determine pick reason ─────────────────────────────────────
            if not reasons:
                if exp_pts >= 40:
                    reasons.append("⭐ Premium pick")
                elif exp_pts >= 25:
                    reasons.append("✅ Consistent")
                else:
                    reasons.append("💡 Emerging")

            # ── Detect team ───────────────────────────────────────────────
            team_label = "?"
            if team_a and team_b:
                team_label = _detect_player_team(player, team_a, team_b)

            rows.append({
                "player": player,
                "team": team_label,
                "role": role,
                "exp_runs": str(exp_runs) if has_bat else "-",
                "exp_wk": str(exp_wk) if has_bowl else "-",
                "exp_pts": round(exp_pts, 1),
                "reason": " · ".join(reasons),
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
        "Here are the expected contributions from key players in this match:",
        "",
        "| Player | Team | Role | Exp. Runs | Exp. Wickets | Est. Fantasy Pts | Pick Reason |",
        "|--------|------|------|-----------|--------------|-----------------|-------------|",
    ]

    for row in rows:
        table_lines.append(
            f"| {row['player']} | {row['team']} | {row['role']} "
            f"| {row['exp_runs']} | {row['exp_wk']} | {row['exp_pts']} | {row['reason']} |"
        )

    # Captain / VC recommendation
    if len(rows) >= 2:
        table_lines.append("")
        table_lines.append(f"**Captain pick:** {rows[0]['player']} ({rows[0]['exp_pts']} pts)")
        table_lines.append(f"**Vice-Captain pick:** {rows[1]['player']} ({rows[1]['exp_pts']} pts)")

    return "\n".join(table_lines)


def build_rag_context(prompt: str, context: Dict[str, Any]) -> Dict[str, Any]:
    fmt = str(context.get("format", "T20"))

    # ── RAG-level cache: skip all Cricsheet I/O for identical recent queries ──
    # Include team_a/team_b in the cache key so different matchups don't collide
    team_a_ctx = str(context.get("team_a", ""))
    team_b_ctx = str(context.get("team_b", ""))
    cache_key = _rag_cache_key(f"{prompt}|{team_a_ctx}|{team_b_ctx}", fmt)
    cached = _get_rag_cached(cache_key)
    if cached is not None:
        # Merge cached RAG result with caller-provided context (format, grounded etc.)
        merged = dict(context)
        merged.update(cached)
        merged["_rag_cache_hit"] = True
        return merged

    enriched = dict(context)
    enriched["_is_cricket"] = is_cricket_question(prompt)

    # ── Detect entities ───────────────────────────────────────────────────────
    players = detect_players_in_prompt(prompt)
    teams   = detect_teams_in_prompt(prompt)
    venue   = detect_venue_in_prompt(prompt)

    # Also pick up team_a / team_b from the frontend context dict
    if team_a_ctx and team_a_ctx not in [t for t in teams]:
        ctx_teams = detect_teams_in_prompt(team_a_ctx)
        for t in ctx_teams:
            if t not in teams:
                teams.append(t)
    if team_b_ctx and team_b_ctx not in [t for t in teams]:
        ctx_teams = detect_teams_in_prompt(team_b_ctx)
        for t in ctx_teams:
            if t not in teams:
                teams.append(t)

    # Also pick up venue from context
    venue_ctx = str(context.get("venue", ""))
    if not venue and venue_ctx:
        venue = venue_ctx

    cricsheet_blocks: List[str] = []

    # ── Auto-detect players from team rosters when none in prompt ─────────────
    # This is the key fix: MatchPredict sends team names but no player names.
    # We look up the most recent squad for each team from Cricsheet data.
    is_fantasy_or_predict = any(
        kw in prompt.lower()
        for kw in ("fantasy", "predict", "top scorer", "top run", "expected",
                    "who will score", "xi", "winner", "who wins")
    )

    if not players and is_fantasy_or_predict and len(teams) >= 2:
        log.info("Auto-detecting squad players for %s vs %s", teams[0], teams[1])
        squad_a = _get_team_recent_players(teams[0], fmt=fmt, limit=11)
        squad_b = _get_team_recent_players(teams[1], fmt=fmt, limit=11)
        players = squad_a + squad_b
        if players:
            log.info("Auto-detected %d players from team rosters", len(players))

    # ── Player stats ──────────────────────────────────────────────────────────
    if players:
        # For prediction queries with many players, only fetch detailed stats for top 6
        stats_players = players[:6] if is_fantasy_or_predict and len(players) > 6 else players[:3]
        stats_text = fetch_player_context(stats_players, fmt=fmt)
        if stats_text:
            cricsheet_blocks.extend(split_cricsheet_into_blocks(stats_text))
        enriched["detected_players"] = ", ".join(players)

    # ── Fantasy / prediction data table ───────────────────────────────────────
    if is_fantasy_or_predict and players:
        fantasy_text = fetch_fantasy_prediction_context(
            players, venue, fmt=fmt,
            team_a=teams[0] if len(teams) >= 1 else "",
            team_b=teams[1] if len(teams) >= 2 else "",
        )
        if fantasy_text:
            cricsheet_blocks.append(fantasy_text)

    # ── Venue/ground context ──────────────────────────────────────────────────
    if venue:
        venue_text = fetch_venue_context(venue, fmt=fmt)
        if venue_text:
            cricsheet_blocks.append(venue_text)
        enriched["venue"] = venue

    # ── Head-to-head context ──────────────────────────────────────────────────
    if len(teams) >= 2:
        h2h_text = fetch_h2h_context(teams[0], teams[1], fmt=fmt)
        if h2h_text:
            cricsheet_blocks.append(h2h_text)
        enriched["teams"] = f"{teams[0]} vs {teams[1]}"
    elif len(teams) == 1:
        enriched["teams"] = teams[0]

    # ── Cross-encoder reranking ───────────────────────────────────────────────
    # Score every block against the query; keep only the top-k most relevant.
    # For prediction queries, allow more blocks (the table is large + important).
    top_k = 7 if is_fantasy_or_predict else 5
    if cricsheet_blocks:
        reranked = rerank_context_blocks(prompt, cricsheet_blocks, top_k=top_k)
        enriched["cricsheet_data"] = "\n\n".join(reranked)
        enriched["_reranked_blocks"] = len(reranked)

    # ── Cache the RAG result (excludes caller context like format/grounded) ───
    rag_only: Dict[str, Any] = {
        k: v for k, v in enriched.items()
        if k not in context  # only store keys we computed here
    }
    _set_rag_cached(cache_key, rag_only)

    return enriched
