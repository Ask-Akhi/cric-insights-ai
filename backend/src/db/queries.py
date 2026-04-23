"""
asyncpg query helpers — all hot read paths live here.

Design rules:
  - Every function accepts a pool argument (injected by the agent).
  - Every function returns plain dicts / lists — not asyncpg Record objects.
  - No ORM overhead: raw parameterised SQL only.
  - All queries target pre-aggregated views/tables — no row scanning.
"""
from __future__ import annotations

import json
import logging
from typing import Any

log = logging.getLogger(__name__)


# ── Head-to-head ──────────────────────────────────────────────────────────────

async def query_head_to_head(
    pool, team_a: str, team_b: str, fmt: str = ""
) -> dict[str, Any]:
    """
    Return win/loss summary between team_a and team_b.
    Tries both orderings (team_a/team_b and team_b/team_a).
    """
    sql = """
        SELECT team_a, team_b, format, team_a_wins, team_b_wins,
               no_result, total_matches, last_played, recent_results_json
        FROM head_to_head_summary
        WHERE ((team_a ILIKE $1 AND team_b ILIKE $2)
            OR (team_a ILIKE $2 AND team_b ILIKE $1))
    """
    args: list[Any] = [team_a, team_b]
    if fmt:
        sql += " AND format ILIKE $3"
        args.append(fmt)
    sql += " ORDER BY total_matches DESC LIMIT 5"

    rows = await pool.fetch(sql, *args)
    results = []
    for r in rows:
        row = dict(r)
        if row.get("recent_results_json"):
            try:
                row["recent_results"] = json.loads(row["recent_results_json"])
            except Exception:
                row["recent_results"] = []
        results.append(row)
    return {"matches": results}


# ── Player stats ──────────────────────────────────────────────────────────────

async def query_player_stats(
    pool, player: str, season: str = "all", fmt: str = "",
    since_year: int | None = None,
) -> list[dict[str, Any]]:
    """
    Return batting + bowling season aggregates for a player.
    Uses ILIKE for fuzzy name matching (handles partial names).
    - season: exact season string e.g. "2023", or "all"
    - since_year: if set, returns seasons >= this year (e.g. last 2 years)
    """
    sql = """
        SELECT player, team, season, format,
               bat_matches, runs, balls_faced, fours, sixes, avg, strike_rate,
               bowl_matches, wickets, balls_bowled, runs_conceded,
               economy, bowling_avg, bowling_sr
        FROM player_season_stats
        WHERE player ILIKE $1
    """
    args: list[Any] = [f"%{player}%"]
    if season != "all":
        sql += f" AND season = ${len(args)+1}"
        args.append(season)
    if since_year is not None:
        sql += f" AND CAST(season AS INTEGER) >= ${len(args)+1}"
        args.append(since_year)
    if fmt:
        sql += f" AND format ILIKE ${len(args)+1}"
        args.append(fmt)
    sql += " ORDER BY season DESC, runs DESC LIMIT 30"

    rows = await pool.fetch(sql, *args)
    return [dict(r) for r in rows]


# ── Recent form ───────────────────────────────────────────────────────────────

async def query_recent_form(
    pool, team: str, last_n: int = 5, fmt: str = ""
) -> list[dict[str, Any]]:
    """Return the last N matches for a team from the recent_form table."""
    sql = """
        SELECT team, match_id, date, format, opponent, venue, result, margin
        FROM recent_form
        WHERE team ILIKE $1
    """
    args: list[Any] = [f"%{team}%"]
    if fmt:
        sql += " AND format ILIKE $2"
        args.append(fmt)
    sql += f" ORDER BY date DESC LIMIT ${len(args)+1}"
    args.append(last_n)

    rows = await pool.fetch(sql, *args)
    return [dict(r) for r in rows]


# ── Semantic search (pgvector) ────────────────────────────────────────────────

async def query_semantic_search(
    pool, embedding: list[float], limit: int = 5
) -> list[dict[str, Any]]:
    """
    Cosine similarity search over match_summary.embedding (pgvector).
    Requires the pgvector extension and the embedding column to be populated.
    Falls back to empty list if the column doesn't exist yet.
    """
    try:
        sql = """
            SELECT match_id, date, format, competition, team_a, team_b,
                   venue, winner, summary,
                   1 - (embedding <=> $1::vector) AS similarity
            FROM match_summary
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> $1::vector
            LIMIT $2
        """
        rows = await pool.fetch(sql, embedding, limit)
        return [dict(r) for r in rows]
    except Exception as exc:
        log.warning("semantic_search failed (pgvector not ready?): %s", exc)
        return []


async def query_match_summary_text(
    pool, query: str, limit: int = 5
) -> list[dict[str, Any]]:
    """
    Fallback full-text search when pgvector embeddings are not yet populated.
    Uses Postgres tsvector / plainto_tsquery.
    """
    sql = """
        SELECT match_id, date, format, team_a, team_b, venue, winner, summary
        FROM match_summary
        WHERE to_tsvector('english', summary) @@ plainto_tsquery('english', $1)
        ORDER BY date DESC
        LIMIT $2
    """
    try:
        rows = await pool.fetch(sql, query, limit)
        return [dict(r) for r in rows]
    except Exception as exc:
        log.warning("full-text search failed: %s", exc)
        return []


# ── Top players leaderboard ───────────────────────────────────────────────────

async def query_top_batters(
    pool, fmt: str = "IPL", season: str = "all", limit: int = 10
) -> list[dict[str, Any]]:
    sql = """
        SELECT player, team, season, format, runs, avg, strike_rate, bat_matches
        FROM player_season_stats
        WHERE runs > 0
    """
    args: list[Any] = []
    if fmt:
        sql += f" AND format ILIKE ${len(args)+1}"
        args.append(fmt)
    if season != "all":
        sql += f" AND season = ${len(args)+1}"
        args.append(season)
    sql += f" ORDER BY runs DESC LIMIT ${len(args)+1}"
    args.append(limit)

    rows = await pool.fetch(sql, *args)
    return [dict(r) for r in rows]


async def query_top_bowlers(
    pool, fmt: str = "IPL", season: str = "all", limit: int = 10
) -> list[dict[str, Any]]:
    sql = """
        SELECT player, team, season, format, wickets, economy, bowling_avg, bowl_matches
        FROM player_season_stats
        WHERE wickets > 0
    """
    args: list[Any] = []
    if fmt:
        sql += f" AND format ILIKE ${len(args)+1}"
        args.append(fmt)
    if season != "all":
        sql += f" AND season = ${len(args)+1}"
        args.append(season)
    sql += f" ORDER BY wickets DESC LIMIT ${len(args)+1}"
    args.append(limit)

    rows = await pool.fetch(sql, *args)
    return [dict(r) for r in rows]


# -- Venue stats ------------------------------------------------------------

async def query_venue_stats(
    pool, venue: str, fmt: str = "", last_n: int = 20
) -> dict[str, Any]:
    """
    Aggregate stats for a given venue from match_summary:
      - total matches, recent results
      - winner distribution (who wins most here)
      - format breakdown
    Uses ILIKE fuzzy match on venue.
    """
    try:
        sql = """
            SELECT match_id, date, format, team_a, team_b, winner, margin, summary
            FROM match_summary
            WHERE venue ILIKE $1
        """
        args: list[Any] = [f"%{venue}%"]
        if fmt:
            sql += f" AND format ILIKE ${len(args)+1}"
            args.append(fmt)
        sql += f" ORDER BY date DESC LIMIT ${len(args)+1}"
        args.append(last_n)

        rows = await pool.fetch(sql, *args)
        matches = [dict(r) for r in rows]

        winners: dict[str, int] = {}
        for m in matches:
            w = (m.get("winner") or "").strip()
            if w:
                winners[w] = winners.get(w, 0) + 1
        top_winners = sorted(winners.items(), key=lambda x: x[1], reverse=True)[:5]

        fmt_counts: dict[str, int] = {}
        for m in matches:
            f = (m.get("format") or "Unknown").strip()
            fmt_counts[f] = fmt_counts.get(f, 0) + 1

        return {
            "venue": venue,
            "total_matches": len(matches),
            "recent": matches[:10],
            "top_winners": top_winners,            "format_breakdown": fmt_counts,
        }
    except Exception as exc:
        log.warning("query_venue_stats failed: %s", exc)
        return {
            "venue": venue,
            "total_matches": 0,
            "recent": [],
            "top_winners": [],
            "format_breakdown": {},
        }


# -- Phase 2: venue_stats_agg (pre-aggregated, fast) ------------------------

async def query_venue_stats_agg(
    pool, venue: str, fmt: str = ""
) -> list[dict[str, Any]]:
    """Pre-aggregated venue stats: 1st/2nd innings avg, toss/chase %, totals."""
    try:
        sql = """
            SELECT venue, format, total_matches,
                   avg_first_innings, avg_second_innings,
                   toss_win_pct, chase_win_pct, bat_first_win_pct,
                   highest_total, lowest_total, last_played
            FROM venue_stats_agg
            WHERE venue ILIKE $1
        """
        args: list[Any] = [f"%{venue}%"]
        if fmt:
            sql += f" AND format ILIKE ${len(args)+1}"
            args.append(fmt)
        sql += " ORDER BY total_matches DESC LIMIT 5"
        rows = await pool.fetch(sql, *args)
        return [dict(r) for r in rows]
    except Exception as exc:
        log.warning("query_venue_stats_agg failed: %s", exc)
        return []


# -- Phase 2: batter vs bowler ---------------------------------------------

async def query_batter_vs_bowler(
    pool, batter: str, bowler: str, fmt: str = ""
) -> list[dict[str, Any]]:
    """Head-to-head stats between a batter and a bowler."""
    try:
        sql = """
            SELECT batter, bowler, format, balls, runs, dismissals,
                   fours, sixes, strike_rate, avg
            FROM batter_vs_bowler
            WHERE batter ILIKE $1 AND bowler ILIKE $2
        """
        args: list[Any] = [f"%{batter}%", f"%{bowler}%"]
        if fmt:
            sql += f" AND format ILIKE ${len(args)+1}"
            args.append(fmt)
        sql += " ORDER BY balls DESC LIMIT 10"
        rows = await pool.fetch(sql, *args)
        return [dict(r) for r in rows]
    except Exception as exc:
        log.warning("query_batter_vs_bowler failed: %s", exc)
        return []


# -- Phase 2: player at venue ----------------------------------------------

async def query_player_at_venue(
    pool, player: str, venue: str, fmt: str = ""
) -> list[dict[str, Any]]:
    """Player performance at a specific venue (batting + bowling)."""
    try:
        sql = """
            SELECT player, venue, format, innings, runs, balls_faced,
                   avg, strike_rate, wickets, balls_bowled, runs_conceded, economy
            FROM player_venue_stats
            WHERE player ILIKE $1 AND venue ILIKE $2
        """
        args: list[Any] = [f"%{player}%", f"%{venue}%"]
        if fmt:
            sql += f" AND format ILIKE ${len(args)+1}"
            args.append(fmt)
        sql += " ORDER BY innings DESC LIMIT 10"
        rows = await pool.fetch(sql, *args)
        return [dict(r) for r in rows]
    except Exception as exc:
        log.warning("query_player_at_venue failed: %s", exc)
        return []


# -- Phase 2: player rolling form ------------------------------------------

async def query_player_form_recent(
    pool, player: str, fmt: str = ""
) -> list[dict[str, Any]]:
    """Rolling last-N-innings form for a player."""
    try:
        sql = """
            SELECT player, format, last_n, innings, runs, balls_faced,
                   avg, strike_rate, fifties, hundreds, wickets, economy, updated_at
            FROM player_form_recent
            WHERE player ILIKE $1
        """
        args: list[Any] = [f"%{player}%"]
        if fmt:
            sql += f" AND format ILIKE ${len(args)+1}"
            args.append(fmt)
        sql += " ORDER BY runs DESC LIMIT 5"
        rows = await pool.fetch(sql, *args)
        return [dict(r) for r in rows]
    except Exception as exc:
        log.warning("query_player_form_recent failed: %s", exc)
        return []
