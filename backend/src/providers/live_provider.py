"""
Live cricket data provider abstraction.

Priority order (first key found wins):
  1. RAPIDAPI_KEY       → Cricbuzz via RapidAPI (free 500 req/day — most reliable)
                          Host: cricbuzz-cricket.p.rapidapi.com
                          Sign up: https://rapidapi.com/cricketapilive/api/cricbuzz-cricket
  2. SPORTMONKS_KEY     → Sportmonks.com (paid, most comprehensive)
  3. CRICAPI_KEY        → CricAPI.com (free 100 req/day — basic)
  4. <none>             → falls back to Cricsheet static data

Set the key as a Railway environment variable. No code changes needed to switch providers.
"""
from __future__ import annotations
import os
import logging
import time
from typing import Any

import httpx

log = logging.getLogger(__name__)

# ── Read keys from environment ─────────────────────────────────────────────────
CRICAPI_KEY    = os.getenv("CRICAPI_KEY", "")
SPORTMONKS_KEY = os.getenv("SPORTMONKS_KEY", "")
RAPIDAPI_KEY   = os.getenv("RAPIDAPI_KEY", "")

# Simple in-process cache so we don't burn free-tier quota on every ticker refresh
_CACHE: dict[str, tuple[float, Any]] = {}
_CACHE_TTL = 120  # seconds


def _cached(key: str, ttl: int = _CACHE_TTL):
    """Return cached value if still fresh, else None."""
    if key in _CACHE:
        ts, val = _CACHE[key]
        if time.time() - ts < ttl:
            return val
    return None


def _store(key: str, val: Any):
    _CACHE[key] = (time.time(), val)


# ── Shared match shape ─────────────────────────────────────────────────────────
def _match(
    match_id: str = "",
    team1: str = "",
    team2: str = "",
    score: str = "",
    winner: str = "",
    status: str = "recent",   # 'live' | 'recent' | 'upcoming'
    venue: str = "",
    date: str = "",
    format: str = "",
    competition: str = "",
) -> dict:
    return dict(
        match_id=match_id, team1=team1, team2=team2, score=score,
        winner=winner, status=status, venue=venue, date=date,
        format=format, competition=competition,
    )


# ── CricAPI provider (https://www.cricapi.com) ─────────────────────────────────
# Free plan: 100 requests/day. Paid: 10k+/day.
# Docs: https://cricapi.com/how-to-use-cricket-api/

def _fmt_cricapi(match_type: str) -> str:
    """Map CricAPI match_type to our T20/ODI/Test label."""
    mt = match_type.lower()
    if "test" in mt:
        return "Test"
    if "odi" in mt or "one day" in mt:
        return "ODI"
    return "T20"


def fetch_cricapi_live(format_filter: str | None = None) -> list[dict]:
    """
    Fetch current matches from CricAPI.
    Endpoint: GET https://api.cricapi.com/v1/currentMatches?apikey=KEY
    """
    cache_key = f"cricapi_live_{format_filter}"
    cached = _cached(cache_key)
    if cached is not None:
        return cached

    try:
        url = "https://api.cricapi.com/v1/currentMatches"
        r = httpx.get(url, params={"apikey": CRICAPI_KEY, "offset": 0}, timeout=8)
        r.raise_for_status()
        data = r.json()

        matches = []
        for m in data.get("data", []):
            fmt = _fmt_cricapi(m.get("matchType", ""))
            if format_filter and fmt != format_filter:
                continue

            # Score string: combine both team scores
            scores = m.get("score", [])
            score_str = "  ".join(
                f"{s.get('inning','').split(' Inning')[0]}: {s.get('r',0)}/{s.get('w',0)} ({s.get('o',0)} ov)"
                for s in scores
            ) if scores else ""

            status_raw = m.get("status", "").lower()
            if "live" in status_raw or "progress" in status_raw:
                status = "live"
            elif "upcoming" in status_raw or "yet" in status_raw:
                status = "upcoming"
            else:
                status = "recent"

            matches.append(_match(
                match_id=m.get("id", ""),
                team1=m.get("teams", ["", ""])[0] if m.get("teams") else "",
                team2=m.get("teams", ["", ""])[1] if m.get("teams") and len(m["teams"]) > 1 else "",
                score=score_str,
                winner=m.get("matchWinner", ""),
                status=status,
                venue=m.get("venue", ""),
                date=m.get("date", ""),
                format=fmt,
                competition=m.get("series_id", ""),
            ))

        _store(cache_key, matches)
        log.info(f"CricAPI: fetched {len(matches)} matches")
        return matches

    except Exception as e:
        log.warning(f"CricAPI fetch failed: {e}")
        return []


def fetch_cricapi_recent(format_filter: str | None = None, limit: int = 12) -> list[dict]:
    """
    Fetch recently completed matches from CricAPI.
    Endpoint: GET https://api.cricapi.com/v1/matches?apikey=KEY
    """
    cache_key = f"cricapi_recent_{format_filter}_{limit}"
    cached = _cached(cache_key)
    if cached is not None:
        return cached

    try:
        url = "https://api.cricapi.com/v1/matches"
        r = httpx.get(url, params={"apikey": CRICAPI_KEY, "offset": 0}, timeout=8)
        r.raise_for_status()
        data = r.json()

        matches = []
        for m in data.get("data", []):
            fmt = _fmt_cricapi(m.get("matchType", ""))
            if format_filter and fmt != format_filter:
                continue
            if m.get("matchStarted") and not m.get("matchEnded"):
                status = "live"
            elif not m.get("matchStarted"):
                status = "upcoming"
            else:
                status = "recent"

            scores = m.get("score", [])
            score_str = "  ".join(
                f"{s.get('inning','').split(' Inning')[0]}: {s.get('r',0)}/{s.get('w',0)} ({s.get('o',0)} ov)"
                for s in scores
            ) if scores else ""

            matches.append(_match(
                match_id=m.get("id", ""),
                team1=m.get("teams", ["", ""])[0] if m.get("teams") else "",
                team2=m.get("teams", ["", ""])[1] if m.get("teams") and len(m["teams"]) > 1 else "",
                score=score_str,
                winner=m.get("matchWinner", ""),
                status=status,
                venue=m.get("venue", ""),
                date=m.get("date", ""),
                format=fmt,
                competition=m.get("name", ""),
            ))
            if len(matches) >= limit:
                break

        _store(cache_key, matches)
        log.info(f"CricAPI recent: fetched {len(matches)} matches")
        return matches

    except Exception as e:
        log.warning(f"CricAPI recent fetch failed: {e}")
        return []


# ── Sportmonks provider (https://sportmonks.com/cricket-api) ──────────────────
# Paid only. Best quality — live scores, scorecards, player stats, odds.
# Docs: https://docs.sportmonks.com/cricket

def _fmt_sportmonks(league_name: str) -> str:
    n = league_name.lower()
    if "test" in n:
        return "Test"
    if "one day" in n or " odi" in n:
        return "ODI"
    return "T20"


def fetch_sportmonks_live(format_filter: str | None = None) -> list[dict]:
    """
    Fetch live fixtures from Sportmonks.
    Endpoint: GET https://cricket.sportmonks.com/api/v2.0/livescores
    """
    cache_key = f"sportmonks_live_{format_filter}"
    cached = _cached(cache_key)
    if cached is not None:
        return cached

    try:
        url = "https://cricket.sportmonks.com/api/v2.0/livescores"
        r = httpx.get(
            url,
            params={"api_token": SPORTMONKS_KEY, "include": "localteam,visitorteam,league,scoreboards"},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()

        matches = []
        for m in data.get("data", []):
            league = m.get("league", {}).get("name", "")
            fmt = _fmt_sportmonks(league)
            if format_filter and fmt != format_filter:
                continue

            local = m.get("localteam", {}).get("name", "")
            visitor = m.get("visitorteam", {}).get("name", "")

            # Build score from scoreboards
            scoreboards = m.get("scoreboards", {}).get("data", [])
            score_parts = []
            for sb in scoreboards:
                team = local if sb.get("team_id") == m.get("localteam_id") else visitor
                score_parts.append(f"{team}: {sb.get('total', 0)}/{sb.get('wickets', 0)} ({sb.get('overs', 0)} ov)")
            score_str = "  ".join(score_parts)

            winner_id = m.get("winner_team_id")
            winner = local if winner_id == m.get("localteam_id") else (visitor if winner_id else "")

            matches.append(_match(
                match_id=str(m.get("id", "")),
                team1=local,
                team2=visitor,
                score=score_str,
                winner=winner,
                status="live",
                venue=m.get("venue", {}).get("name", "") if isinstance(m.get("venue"), dict) else "",
                date=str(m.get("starting_at", ""))[:10],
                format=fmt,
                competition=league,
            ))

        _store(cache_key, matches)
        log.info(f"Sportmonks: fetched {len(matches)} live matches")
        return matches

    except Exception as e:
        log.warning(f"Sportmonks fetch failed: {e}")
        return []


# ── RapidAPI / Cricbuzz provider (RECOMMENDED — most reliable) ─────────────
# Free tier: 500 req/day on Cricbuzz-Cricket API via RapidAPI.
# Sign up: https://rapidapi.com/cricketapilive/api/cricbuzz-cricket
# Set env var: RAPIDAPI_KEY=your_key_here
# RapidAPI also works for the older cricket-live-data host as fallback.

RAPIDAPI_CRICBUZZ_HOST = "cricbuzz-cricket.p.rapidapi.com"


def fetch_cricbuzz_live(format_filter: str | None = None) -> list[dict]:
    """
    Fetch live + recent matches from Cricbuzz via RapidAPI.
    Endpoint: GET /matches/v1/live  (also tries /recent)
    """
    cache_key = f"cricbuzz_live_{format_filter}"
    cached = _cached(cache_key)
    if cached is not None:
        return cached

    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": RAPIDAPI_CRICBUZZ_HOST,
    }

    matches: list[dict] = []

    # Try live matches first, then recent
    for endpoint in ("/matches/v1/live", "/matches/v1/recent"):
        if len(matches) >= 12:
            break
        try:
            r = httpx.get(
                f"https://{RAPIDAPI_CRICBUZZ_HOST}{endpoint}",
                headers=headers,
                timeout=8,
            )
            if r.status_code == 403:
                log.warning(f"Cricbuzz RapidAPI 403 — check your RAPIDAPI_KEY subscription")
                break
            r.raise_for_status()
            data = r.json()

            # Cricbuzz wraps results in typeMatches → seriesMatches → seriesAdWrapper → matches
            for type_block in data.get("typeMatches", []):
                match_type = type_block.get("matchType", "")  # e.g. "International", "League"
                for series in type_block.get("seriesMatches", []):
                    wrapper = series.get("seriesAdWrapper") or series
                    series_name = wrapper.get("seriesName", "")
                    for m in wrapper.get("matches", []):
                        mi = m.get("matchInfo", {})
                        ms = m.get("matchScore", {})

                        fmt = _fmt_cricbuzz(mi.get("matchFormat", ""), series_name)
                        if format_filter and fmt != format_filter:
                            continue

                        team1 = mi.get("team1", {}).get("teamName", "")
                        team2 = mi.get("team2", {}).get("teamName", "")

                        # Build score string from innings scores
                        score_parts = []
                        for tid, tkey in [(mi.get("team1", {}).get("teamId"), "team1Score"),
                                          (mi.get("team2", {}).get("teamId"), "team2Score")]:
                            ts = ms.get(tkey, {})
                            if ts:
                                for inn in ["inngs1", "inngs2"]:
                                    ig = ts.get(inn, {})
                                    if ig and ig.get("runs") is not None:
                                        overs = ig.get("overs", "")
                                        tname = team1 if tkey == "team1Score" else team2
                                        score_parts.append(
                                            f"{tname}: {ig.get('runs', 0)}/{ig.get('wickets', 0)}"
                                            + (f" ({overs} ov)" if overs else "")
                                        )
                        score_str = "  ".join(score_parts)

                        status_raw = mi.get("status", "").lower()
                        state = mi.get("state", "").lower()
                        if state == "live" or "in progress" in status_raw:
                            status = "live"
                        elif "upcoming" in status_raw or state == "preview":
                            status = "upcoming"
                        else:
                            status = "recent"

                        # Winner from status string (Cricbuzz puts it there)
                        status_str = mi.get("status", "")
                        winner = ""
                        for tname in [team1, team2]:
                            if tname and f"{tname} won" in status_str:
                                winner = tname
                                break

                        matches.append(_match(
                            match_id=str(mi.get("matchId", "")),
                            team1=team1,
                            team2=team2,
                            score=score_str,
                            winner=winner,
                            status=status,
                            venue=mi.get("venueInfo", {}).get("ground", ""),
                            date=str(mi.get("startDate", ""))[:10],
                            format=fmt,
                            competition=series_name,
                        ))

        except Exception as e:
            log.warning(f"Cricbuzz ({endpoint}) fetch failed: {e}")

    _store(cache_key, matches)
    log.info(f"Cricbuzz: fetched {len(matches)} matches (filter={format_filter})")
    return matches


def _fmt_cricbuzz(match_format: str, series_name: str = "") -> str:
    """Map Cricbuzz matchFormat string → T20 / ODI / Test."""
    mf = match_format.upper()
    sn = series_name.lower()
    if mf in ("TEST", "FTEST"):
        return "Test"
    if mf in ("ODI", "ODM"):
        return "ODI"
    if mf in ("T20", "IT20", "T20I"):
        return "T20"
    # Fall back to series name heuristics
    if "test" in sn:
        return "Test"
    if "one day" in sn or " odi" in sn:
        return "ODI"
    return "T20"


# ── Public interface — auto-selects provider ───────────────────────────────────

def get_live_source() -> str:
    """Return which live provider is active, or 'cricsheet' if none configured."""
    if RAPIDAPI_KEY:
        return "rapidapi"      # Cricbuzz via RapidAPI — most reliable, 500 req/day free
    if SPORTMONKS_KEY:
        return "sportmonks"
    if CRICAPI_KEY:
        return "cricapi"
    return "cricsheet"


def fetch_live_matches(format_filter: str | None = None, limit: int = 12) -> tuple[list[dict], str]:
    """
    Fetch live/recent matches from whichever provider is configured.
    Returns (matches, source_name).
    """
    source = get_live_source()

    if source == "cricapi":
        live = fetch_cricapi_live(format_filter)
        if not live:
            live = fetch_cricapi_recent(format_filter, limit)
        return live[:limit], "cricapi"

    if source == "sportmonks":
        return fetch_sportmonks_live(format_filter)[:limit], "sportmonks"

    if source == "rapidapi":
        return fetch_cricbuzz_live(format_filter)[:limit], "rapidapi"

    return [], "cricsheet"  # caller falls back to Cricsheet
