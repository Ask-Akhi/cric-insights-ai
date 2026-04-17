"""
Regex-based intent fast-path — runs BEFORE the PydanticAI agent.

Purpose:
  - For obvious stat queries ("Virat Kohli T20 stats", "MI vs CSK head-to-head",
    "top batters IPL 2024"), classify intent via regex, hit Postgres directly,
    and return a formatted answer WITHOUT any LLM call.
  - Only ambiguous/complex queries fall through to the LLM-powered agent.

Savings: ~2 LLM calls per hit (route + format) → near-zero cost, <100ms latency.

Design: conservative regex. If we're not *sure* it's a stat query, return None
and let the agent handle it — no false positives.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Optional

log = logging.getLogger("mcp.fastpath")


@dataclass
class FastPathResult:
    answer: str
    intent: str
    tools_used: list[str]
    data_sources: list[str]
    latency_ms: int
    mode: str = "fastpath"


# ── Team aliases (short → canonical) ──────────────────────────────────────────
_TEAM_ALIASES = {
    # IPL
    "mi": "Mumbai Indians", "csk": "Chennai Super Kings",
    "rcb": "Royal Challengers Bangalore", "kkr": "Kolkata Knight Riders",
    "srh": "Sunrisers Hyderabad", "dc": "Delhi Capitals",
    "pbks": "Punjab Kings", "rr": "Rajasthan Royals",
    "gt": "Gujarat Titans", "lsg": "Lucknow Super Giants",
    # International (no aliasing needed — names match DB already)
}


def _canon_team(s: str) -> str:
    s = s.strip()
    return _TEAM_ALIASES.get(s.lower(), s)


# ── Format detection ──────────────────────────────────────────────────────────
_FORMAT_RE = re.compile(
    r"\b(T20I?|ODI|Test|IPL|BBL|PSL|CPL|T20 Blast|WPL|Hundred)\b",
    re.IGNORECASE,
)


def _detect_format(prompt: str) -> str:
    m = _FORMAT_RE.search(prompt)
    if not m:
        return ""
    raw = m.group(1).upper()
    # Normalise
    if raw == "T20":
        return "T20"
    if raw == "T20I":
        return "T20I"
    return raw


# ── Intent patterns ───────────────────────────────────────────────────────────
_H2H_RE = re.compile(
    r"(?P<a>[A-Za-z][A-Za-z\s]{1,40}?)\s+(?:vs?\.?|v/s|against)\s+"
    r"(?P<b>[A-Za-z][A-Za-z\s]{1,40}?)"
    r"(?:\s+(?:head[-\s]?to[-\s]?head|h2h|record|results?|matches?))?",
    re.IGNORECASE,
)

_PLAYER_STATS_RE = re.compile(
    r"(?:^|\s)(?P<player>[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})(?:'s|\s)"
    r".*?\b(stats?|average|runs?|wickets?|strike[-\s]?rate|economy|form|record)\b",
    re.IGNORECASE,
)

_TOP_PLAYERS_RE = re.compile(
    r"\btop\s+(?P<n>\d{1,3})?\s*(?P<cat>batters?|batsmen|bowlers?|"
    r"run[-\s]?scorers?|wicket[-\s]?takers?)",
    re.IGNORECASE,
)

_RECENT_FORM_RE = re.compile(
    r"\b(?P<team>[A-Z][a-zA-Z\s]{1,40}?)\s+"
    r"(?:recent\s+form|last\s+\d+\s+matches|form)\b",
    re.IGNORECASE,
)


# ── Main entry point ──────────────────────────────────────────────────────────

async def try_fastpath(prompt: str, ctx: dict) -> Optional[FastPathResult]:
    """
    Attempt regex-based classification + direct DB query.
    Returns None if:
      - No DB pool configured (fall through to agent's Polars fallback)
      - No regex matches (ambiguous query → let agent handle)
      - DB query returned no rows (let agent try semantic_search or web)
    """
    t0 = time.monotonic()

    # Need DB for fast-path; without it, the agent already has Polars fallback
    try:
        from ..db.connection import get_pool
        pool = await get_pool()
    except Exception:
        pool = None
    if pool is None:
        log.debug("fastpath: no DB pool — skipping")
        return None

    p = prompt.strip()
    fmt = _detect_format(p)

    # 1. head-to-head — highest precedence (very specific pattern)
    m = _H2H_RE.search(p)
    if m and "vs" in p.lower() or (m and " v " in f" {p.lower()} "):
        team_a = _canon_team(m.group("a"))
        team_b = _canon_team(m.group("b"))
        if _looks_like_team(team_a) and _looks_like_team(team_b):
            try:
                from ..db.queries import query_head_to_head
                data = await query_head_to_head(pool, team_a, team_b, fmt)
                if data.get("matches"):
                    from .agent import _format_h2h
                    answer = _format_h2h(data, team_a, team_b)
                    log.info("fastpath HIT: head_to_head %s vs %s (%s)",
                             team_a, team_b, fmt or "all")
                    return FastPathResult(
                        answer=answer,
                        intent="head_to_head",
                        tools_used=["head_to_head"],
                        data_sources=["PostgreSQL", "Cricsheet"],
                        latency_ms=int((time.monotonic() - t0) * 1000),
                    )
            except Exception as exc:
                log.warning("fastpath h2h error: %s", exc)

    # 2. top players leaderboard
    m = _TOP_PLAYERS_RE.search(p)
    if m:
        cat_raw = m.group("cat").lower()
        category = ("bowling" if "bowl" in cat_raw or "wicket" in cat_raw
                    else "batting")
        limit = int(m.group("n") or 10)
        season = _extract_season(p)
        lb_fmt = fmt or "IPL"  # leaderboard default
        try:
            from .agent import _format_leaderboard
            if category == "bowling":
                from ..db.queries import query_top_bowlers
                rows = await query_top_bowlers(pool, lb_fmt, season, limit)
                cols = ["player", "team", "wickets", "economy",
                        "bowling_avg", "bowl_matches"]
            else:
                from ..db.queries import query_top_batters
                rows = await query_top_batters(pool, lb_fmt, season, limit)
                cols = ["player", "team", "runs", "avg",
                        "strike_rate", "bat_matches"]
            if rows:
                answer = _format_leaderboard(category.title(), rows, cols)
                log.info("fastpath HIT: top_players %s %s %s", category, lb_fmt, season)
                return FastPathResult(
                    answer=answer,
                    intent="ranking",
                    tools_used=["top_players"],
                    data_sources=["PostgreSQL", "Cricsheet"],
                    latency_ms=int((time.monotonic() - t0) * 1000),
                )
        except Exception as exc:
            log.warning("fastpath top_players error: %s", exc)

    # 3. player stats — most common query type
    m = _PLAYER_STATS_RE.search(p)
    if m:
        player = m.group("player").strip()
        season = _extract_season(p) or "all"
        try:
            from ..db.queries import query_player_stats
            rows = await query_player_stats(pool, player, season, fmt)
            if rows:
                from .agent import _format_player_stats
                answer = _format_player_stats(player, rows)
                log.info("fastpath HIT: player_stats %s (%s, %s)",
                         player, season, fmt or "all")
                return FastPathResult(
                    answer=answer,
                    intent="batting_stats",
                    tools_used=["player_stats"],
                    data_sources=["PostgreSQL", "Cricsheet"],
                    latency_ms=int((time.monotonic() - t0) * 1000),
                )
        except Exception as exc:
            log.warning("fastpath player_stats error: %s", exc)

    # 4. recent form
    m = _RECENT_FORM_RE.search(p)
    if m:
        team = _canon_team(m.group("team"))
        if _looks_like_team(team):
            last_n = _extract_last_n(p) or 5
            try:
                from ..db.queries import query_recent_form
                rows = await query_recent_form(pool, team, last_n, fmt)
                if rows:
                    from .agent import _format_recent_form
                    answer = _format_recent_form(team, rows)
                    log.info("fastpath HIT: recent_form %s last_%d", team, last_n)
                    return FastPathResult(
                        answer=answer,
                        intent="form",
                        tools_used=["recent_form"],
                        data_sources=["PostgreSQL", "Cricsheet"],
                        latency_ms=int((time.monotonic() - t0) * 1000),
                    )
            except Exception as exc:
                log.warning("fastpath recent_form error: %s", exc)

    log.debug("fastpath: no intent matched or no data — falling through to agent")
    return None


# ── Helpers ───────────────────────────────────────────────────────────────────

_STOPWORDS = {"the", "a", "an", "in", "for", "of", "and", "or", "who", "what",
              "how", "when", "where", "is", "are", "was", "were", "did",
              "best", "top", "most", "last", "recent", "current", "latest",
              "stats", "stat", "record", "form", "average", "runs", "wickets",
              "strike", "rate", "economy", "vs", "against", "between",
              "matches", "match", "today", "this", "that", "year", "season",
              "during", "over", "under", "with", "by", "from", "to"}


def _looks_like_team(s: str) -> bool:
    """Reject if string is likely a sentence fragment or stopword chain."""
    if not s or len(s) > 60:
        return False
    tokens = [t.lower() for t in s.split() if t]
    if not tokens or all(t in _STOPWORDS for t in tokens):
        return False
    # Must have at least one capitalised real word
    return any(w[0].isupper() and w.lower() not in _STOPWORDS for w in s.split())


def _extract_season(prompt: str) -> str:
    """Pull a 4-digit year if present, else 'all'."""
    m = re.search(r"\b(20\d{2})\b", prompt)
    return m.group(1) if m else "all"


def _extract_last_n(prompt: str) -> int:
    """Pull 'last N matches' → N; default None."""
    m = re.search(r"last\s+(\d{1,2})\s+(?:matches?|games?|odis?|t20s?|tests?)",
                  prompt, re.IGNORECASE)
    return int(m.group(1)) if m else 0
