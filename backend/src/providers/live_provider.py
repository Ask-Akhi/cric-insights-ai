"""
Live cricket data provider abstraction.

Priority order (first key found wins):
  1. RAPIDAPI_KEY       → Cricbuzz via RapidAPI (free 500 req/day — most reliable)
                          Host: cricbuzz-cricket.p.rapidapi.com
                          Sign up: https://rapidapi.com/cricketapilive/api/cricbuzz-cricket
  2. SPORTMONKS_KEY     → Sportmonks.com (paid, most comprehensive)
  3. CRICAPI_KEY        → CricAPI.com (free 100 req/day — basic)
  4. <none>             → free CricketData.org API (no key, 100 req/day) → Cricsheet static

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
# Free no-auth API from cricketdata.org — used when no paid key is set
CRICDATA_API_URL = "https://api.cricketdata.org/api/v1"

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

# Allow the host to be overridden via RAPIDAPI_HOST env var so users can
# switch between cricbuzz-cricket / cricket-live-data / etc without a code push.
RAPIDAPI_CRICBUZZ_HOST = os.getenv("RAPIDAPI_HOST", "cricbuzz-cricket.p.rapidapi.com")

# Known Cricbuzz-style RapidAPI hosts to auto-fallback through
_RAPIDAPI_HOSTS = [
    RAPIDAPI_CRICBUZZ_HOST,                      # user-configured / default
    "cricket-live-data.p.rapidapi.com",          # older popular alternative
    "cricbuzz-cricket2.p.rapidapi.com",          # newer version some accounts get
]


def _parse_cricbuzz_response(data: dict, format_filter: str | None, team_filter: str | None = None) -> list[dict]:
    """
    Parse the nested Cricbuzz API JSON into our flat match dicts.
    Handles both:
      typeMatches → seriesMatches → seriesAdWrapper → matches
      typeMatches → seriesMatches → seriesMatch → matches  (alternate shape)
    """
    import datetime as _dt
    results: list[dict] = []

    for type_block in data.get("typeMatches", []):
        for series in type_block.get("seriesMatches", []):
            # The wrapper key varies: seriesAdWrapper (ads version) or seriesMatch
            wrapper = series.get("seriesAdWrapper") or series.get("seriesMatch") or series
            series_name = wrapper.get("seriesName", "")
            match_list = wrapper.get("matches", [])

            for m in match_list:
                mi = m.get("matchInfo", {})
                ms = m.get("matchScore", {})
                if not mi:
                    continue

                fmt = _fmt_cricbuzz(mi.get("matchFormat", ""), series_name)
                if format_filter and fmt != format_filter:
                    continue

                team1 = mi.get("team1", {}).get("teamName", "") or mi.get("team1", {}).get("teamSName", "")
                team2 = mi.get("team2", {}).get("teamName", "") or mi.get("team2", {}).get("teamSName", "")

                # Build score string from innings
                score_parts = []
                for tkey, tname in [("team1Score", team1), ("team2Score", team2)]:
                    ts = ms.get(tkey) or {}
                    for inn in ["inngs1", "inngs2"]:
                        ig = ts.get(inn) or {}
                        if ig and ig.get("runs") is not None:
                            overs = ig.get("overs", "")
                            wkts = ig.get("wickets", 0)
                            wkts_str = f"/{wkts}" if wkts is not None else ""
                            score_parts.append(
                                f"{tname}: {ig.get('runs', 0)}{wkts_str}"
                                + (f" ({overs} ov)" if overs else "")
                            )
                score_str = "  ".join(score_parts)

                status_str = mi.get("status", "")
                status_raw = status_str.lower()
                state = mi.get("state", "").lower()
                if state in ("live", "in progress") or "in progress" in status_raw:
                    status = "live"
                elif state in ("preview", "upcoming") or "upcoming" in status_raw or "yet to" in status_raw:
                    status = "upcoming"
                else:
                    status = "recent"

                winner = ""
                for tname in [team1, team2]:
                    if tname and f"{tname} won" in status_str:
                        winner = tname
                        break

                # startDate is Unix ms timestamp
                raw_ts = mi.get("startDate", "")
                try:
                    match_date = _dt.datetime.utcfromtimestamp(int(raw_ts) / 1000).strftime("%Y-%m-%d")
                except Exception:
                    match_date = ""

                results.append(_match(
                    match_id=str(mi.get("matchId", "")),
                    team1=team1,
                    team2=team2,
                    score=score_str,
                    winner=winner,
                    status=status,
                    venue=mi.get("venueInfo", {}).get("ground", ""),
                    date=match_date,
                    format=fmt,
                    competition=series_name,
                ))
    return results


def fetch_cricbuzz_live(format_filter: str | None = None) -> list[dict]:
    """
    Fetch live + recent matches from Cricbuzz via RapidAPI.
    ALWAYS fetches both /live AND /recent endpoints and merges them so the
    ticker shows international recent results alongside any current live games.
    Deduplicates by match_id. Live matches sorted first, then recent by date desc.
    Auto-tries multiple known hosts if the primary returns 403/not-subscribed.
    Set RAPIDAPI_HOST env var to pin a specific host.
    """
    cache_key = f"cricbuzz_live_{format_filter}"
    cached = _cached(cache_key)
    if cached is not None:
        return cached

    all_matches: dict[str, dict] = {}   # match_id → match (deduplicates)
    tried_hosts: list[str] = []
    success_host: str | None = None

    # De-duplicate hosts while preserving order
    hosts_to_try = list(dict.fromkeys(_RAPIDAPI_HOSTS))

    for host in hosts_to_try:
        tried_hosts.append(host)
        headers = {"x-rapidapi-key": RAPIDAPI_KEY, "x-rapidapi-host": host}
        host_ok = False

        # ALWAYS hit both endpoints — live games + recent results both matter for the ticker
        for endpoint in ("/matches/v1/live", "/matches/v1/recent"):
            try:
                r = httpx.get(f"https://{host}{endpoint}", headers=headers, timeout=8)

                if r.status_code == 403:
                    log.warning(
                        f"Cricbuzz RapidAPI 403 on {host}{endpoint} — "
                        f"body: {r.text[:200]}. "
                        f"Check RAPIDAPI_KEY at rapidapi.com. "
                        f"Set RAPIDAPI_HOST env var if on a different host."
                    )
                    break  # This host is wrong — try next host

                if r.status_code == 429:
                    log.warning(f"Cricbuzz RapidAPI 429 rate-limit on {host}{endpoint} — skipping")
                    continue

                r.raise_for_status()
                data = r.json()
                top_keys = list(data.keys()) if isinstance(data, dict) else type(data).__name__
                log.info(f"Cricbuzz {host}{endpoint} → {r.status_code}, top keys: {top_keys}")

                batch = _parse_cricbuzz_response(data, format_filter)
                log.info(f"  parsed {len(batch)} matches from {endpoint}")

                # Merge by match_id — /live takes priority over /recent for same match
                for m in batch:
                    mid = m["match_id"]
                    if mid not in all_matches or m["status"] == "live":
                        all_matches[mid] = m

                host_ok = True

            except Exception as e:
                log.warning(f"Cricbuzz {host}{endpoint} failed: {type(e).__name__}: {e}")

        if host_ok:
            success_host = host
            log.info(f"Cricbuzz: {len(all_matches)} unique matches via {host}")
            break  # Got data from this host — don't try next host

    if not all_matches:
        log.warning(
            f"Cricbuzz: 0 matches after trying hosts {tried_hosts}. "
            f"RAPIDAPI_KEY set={bool(RAPIDAPI_KEY)}. Falling back to free provider."
        )

    # Sort: live first, then recent by date descending
    sorted_matches = sorted(
        all_matches.values(),
        key=lambda m: (0 if m["status"] == "live" else 1, m.get("date", ""), m.get("match_id", "")),
        reverse=False,
    )
    # Within live/recent groups, sort recent by date descending (newest first)
    live_m   = [m for m in sorted_matches if m["status"] == "live"]
    recent_m = sorted([m for m in sorted_matches if m["status"] != "live"],
                      key=lambda m: (m.get("date", ""), m.get("match_id", "")), reverse=True)
    final = live_m + recent_m

    _store(cache_key, final)
    return final


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


# ── CricketData.org — FREE, no API key required ────────────────────────────────
# Docs: https://cricketdata.org/  |  100 req/day on free tier, no auth needed
# Endpoint: GET https://api.cricketdata.org/api/v1/currentMatches?apikey=nokey

def fetch_cricketdata_free(format_filter: str | None = None, limit: int = 12) -> list[dict]:
    """
    Fetch current + recent matches from cricketdata.org with NO API key.
    Used as automatic fallback when no paid key is configured.
    """
    cache_key = f"cricdata_free_{format_filter}_{limit}"
    cached = _cached(cache_key, ttl=180)  # 3 min cache — save quota
    if cached is not None:
        return cached

    results: list[dict] = []
    # Try current matches first, then recently completed
    for endpoint in ["currentMatches", "matches"]:
        if len(results) >= limit:
            break
        try:
            r = httpx.get(
                f"{CRICDATA_API_URL}/{endpoint}",
                params={"apikey": "nokey", "offset": 0},
                timeout=8,
            )
            if r.status_code in (401, 403):
                # No-key access not allowed — skip silently
                break
            r.raise_for_status()
            data = r.json()

            for m in data.get("data", []):
                match_type = m.get("matchType", "t20")
                fmt = _fmt_cricapi(match_type)
                if format_filter and fmt != format_filter:
                    continue

                scores = m.get("score", [])
                score_str = "  ".join(
                    f"{s.get('inning','').split(' Inning')[0]}: "
                    f"{s.get('r',0)}/{s.get('w',0)} ({s.get('o',0)} ov)"
                    for s in scores
                ) if scores else ""

                started = m.get("matchStarted", False)
                ended = m.get("matchEnded", False)
                if started and not ended:
                    status = "live"
                elif not started:
                    status = "upcoming"
                else:
                    status = "recent"

                results.append(_match(
                    match_id=m.get("id", ""),
                    team1=(m.get("teams") or [""])[0],
                    team2=(m.get("teams") or ["", ""])[1] if len(m.get("teams") or []) > 1 else "",
                    score=score_str,
                    winner=m.get("matchWinner", ""),
                    status=status,
                    venue=m.get("venue", ""),
                    date=m.get("date", ""),
                    format=fmt,
                    competition=m.get("name", ""),
                ))
                if len(results) >= limit:
                    break

        except Exception as e:
            log.debug(f"CricketData.org ({endpoint}) fetch failed: {e}")

    _store(cache_key, results)
    if results:
        log.info(f"CricketData.org: fetched {len(results)} matches (no key)")
    return results


# ── Public interface — auto-selects provider ───────────────────────────────────

def get_live_source() -> str:
    """Return which live provider is active."""
    if RAPIDAPI_KEY:
        return "rapidapi"      # Cricbuzz via RapidAPI — most reliable, 500 req/day free
    if SPORTMONKS_KEY:
        return "sportmonks"
    if CRICAPI_KEY:
        return "cricapi"
    return "free"              # CricketData.org no-key fallback


def fetch_live_matches(format_filter: str | None = None, limit: int = 20) -> tuple[list[dict], str]:
    """
    Fetch live/recent matches from whichever provider is configured.
    Returns (matches, source_name).
    Default limit raised to 20 so the ticker shows a mix of live + recent international games.
    Always tries the free no-key fallback last so the ticker is never empty.
    """
    source = get_live_source()

    if source == "rapidapi":
        matches = fetch_cricbuzz_live(format_filter)[:limit]
        if matches:
            return matches, "Cricbuzz"

    if source == "sportmonks":
        matches = fetch_sportmonks_live(format_filter)[:limit]
        if matches:
            return matches, "Sportmonks"

    if source == "cricapi":
        matches = fetch_cricapi_live(format_filter)
        if not matches:
            matches = fetch_cricapi_recent(format_filter, limit)
        if matches:
            return matches[:limit], "CricAPI"

    # Free fallback — always tried when no paid key is set or paid key returns nothing
    matches = fetch_cricketdata_free(format_filter, limit)
    if matches:
        return matches, "CricketData"

    return [], "cricsheet"  # caller falls back to Cricsheet static data
