from fastapi import APIRouter, Query
from typing import Optional, List
from pydantic import BaseModel
from ..providers.cricsheet_provider import CricsheetProvider
from ..providers.live_provider import fetch_live_matches, get_live_source
import polars as pl

router = APIRouter()

_provider: CricsheetProvider | None = None

def _get_provider() -> CricsheetProvider:
    global _provider
    if _provider is None:
        _provider = CricsheetProvider()
        _provider.load()
    return _provider


class MatchInput(BaseModel):
    format: str
    venue: str
    date: str
    team_a: str
    team_b: str
    squad_a: List[str]
    squad_b: List[str]


@router.get("/venues")
def list_venues(q: str | None = None, limit: int = 20):
    """Return distinct venue names, optionally filtered by query string."""
    provider = _get_provider()
    lf = provider.datasets.get("balls")
    if lf is None:
        return {"venues": []}
    vq = lf.select(pl.col("venue")).filter(pl.col("venue").is_not_null()).unique()
    if q:
        vq = vq.filter(pl.col("venue").str.to_lowercase().str.contains(q.lower()))
    venues = vq.sort("venue").limit(limit).collect().get_column("venue").to_list()
    return {"venues": venues}


@router.get("/teams")
def list_teams(q: str | None = None, limit: int = 20):
    """Return distinct team names from batting_team."""
    provider = _get_provider()
    lf = provider.datasets.get("balls")
    if lf is None:
        return {"teams": []}
    tq = lf.select(pl.col("batting_team").alias("team")).filter(pl.col("team").is_not_null()).unique()
    if q:
        tq = tq.filter(pl.col("team").str.to_lowercase().str.contains(q.lower()))
    teams = tq.sort("team").limit(limit).collect().get_column("team").to_list()
    return {"teams": teams}


@router.get("/")
def list_matches(
    format: Optional[str] = Query(None),
    team: Optional[str] = Query(None),
    venue: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
):
    provider = _get_provider()
    matches = provider.get_matches(formats=[format] if format else None)
    if not matches:
        return {"matches": [], "count": 0}

    import polars as pl
    df = pl.DataFrame(matches)
    if team:
        # Filter matches where the team appears as winner, toss_winner, or batting_team
        lf_balls = provider.datasets.get("balls")
        if lf_balls is not None:
            team_lower = team.lower()
            match_ids_with_team = (
                lf_balls.filter(
                    pl.col("batting_team").str.to_lowercase().str.contains(team_lower)
                )
                .select("match_id")
                .unique()
                .collect()
                .get_column("match_id")
                .to_list()
            )
            df = df.filter(pl.col("match_id").is_in(match_ids_with_team))
        else:
            df = df.filter(
                pl.col("winner").str.to_lowercase().str.contains(team.lower())
                | pl.col("toss_winner").str.to_lowercase().str.contains(team.lower())
            )
    if venue:
        df = df.filter(
            pl.col("venue").str.to_lowercase().str.contains(venue.lower())
        )

    df = df.head(limit)
    return {"matches": df.to_dicts(), "count": df.height}


@router.get("/venue/{venue_name}")
def venue_summary(venue_name: str, format: Optional[str] = Query(None)):
    """Aggregated stats for a venue from ball-by-ball data."""
    provider = _get_provider()
    df = provider.get_venue_stats(venue_name, fmt=format)
    if df.is_empty():
        return {"venue": venue_name, "found": False}

    matches = df.select(pl.col("match_id").n_unique()).item()
    by_innings = (
        df.group_by(["match_id", "innings"])
        .agg(pl.col("runs_off_bat").sum().alias("runs"))
        .group_by("innings")
        .agg(pl.col("runs").mean().alias("avg_runs"))
        .sort("innings")
    )
    avg_1st = None
    avg_2nd = None
    for row in by_innings.iter_rows(named=True):
        if row["innings"] == 1:
            avg_1st = round(float(row["avg_runs"]), 1)
        elif row["innings"] == 2:
            avg_2nd = round(float(row["avg_runs"]), 1)

    top_scorers = (
        df.group_by("batter")
        .agg(pl.col("runs_off_bat").sum().alias("runs"))
        .sort("runs", descending=True)
        .head(5)
        .to_dicts()
    )
    top_wicket_takers = (
        df.filter(pl.col("player_dismissed").is_not_null())
        .group_by("bowler")
        .len()
        .rename({"len": "wickets"})
        .sort("wickets", descending=True)
        .head(5)
        .to_dicts()
    )

    return {
        "venue": venue_name,
        "found": True,
        "matches": matches,
        "avg_first_innings_runs": avg_1st,
        "avg_second_innings_runs": avg_2nd,
        "top_scorers": top_scorers,
        "top_wicket_takers": top_wicket_takers,
    }


@router.get("/h2h")
def head_to_head(
    team_a: str = Query(...),
    team_b: str = Query(...),
    format: Optional[str] = Query(None),
):
    """Head-to-head match summary between two teams."""
    provider = _get_provider()
    df = provider.get_head_to_head(team_a, team_b, fmt=format)
    if df.is_empty():
        return {"team_a": team_a, "team_b": team_b, "found": False, "matches": 0}

    total = df.select(pl.col("match_id").n_unique()).item()
    wins_a = df.filter(pl.col("winner") == team_a).select(pl.col("match_id").n_unique()).item()
    wins_b = df.filter(pl.col("winner") == team_b).select(pl.col("match_id").n_unique()).item()
    RUNOUT_TYPES = ["run out", "retired hurt", "retired out", "obstructing the field"]

    top_bat_a = (
        df.filter(pl.col("batting_team") == team_a)
        .group_by("batter")
        .agg(pl.col("runs_off_bat").sum().alias("runs"))
        .sort("runs", descending=True)
        .head(5)
        .to_dicts()
    )
    top_bat_b = (
        df.filter(pl.col("batting_team") == team_b)
        .group_by("batter")
        .agg(pl.col("runs_off_bat").sum().alias("runs"))
        .sort("runs", descending=True)
        .head(5)
        .to_dicts()
    )
    # Top wicket-takers for each team (bowling against the other)
    top_bowl_a = (
        df.filter(
            (pl.col("batting_team") == team_b)
            & pl.col("player_dismissed").is_not_null()
            & ~pl.col("wicket_type").is_in(RUNOUT_TYPES)
        )
        .group_by("bowler")
        .len()
        .rename({"len": "wickets"})
        .sort("wickets", descending=True)
        .head(5)
        .to_dicts()
    )
    top_bowl_b = (
        df.filter(
            (pl.col("batting_team") == team_a)
            & pl.col("player_dismissed").is_not_null()
            & ~pl.col("wicket_type").is_in(RUNOUT_TYPES)
        )
        .group_by("bowler")
        .len()
        .rename({"len": "wickets"})
        .sort("wickets", descending=True)
        .head(5)
        .to_dicts()
    )

    return {
        "team_a": team_a,
        "team_b": team_b,
        "found": True,
        "matches": total,
        "wins_a": wins_a,
        "wins_b": wins_b,
        "top_batters_a": top_bat_a,
        "top_batters_b": top_bat_b,
        "top_bowlers_a": top_bowl_a,
        "top_bowlers_b": top_bowl_b,
    }


@router.get("/recent")
def recent_matches(
    format: Optional[str] = Query(None),
    limit: int = Query(10, le=50),
):
    """
    Return the most recent/live matches.
    - If CRICAPI_KEY / SPORTMONKS_KEY / RAPIDAPI_KEY env var is set → uses that live API.
    - Otherwise → falls back to Cricsheet static snapshot (up to Jan 2026).
    Set one of those keys in Railway Variables to enable live data.
    """
    source = get_live_source()

    # ── Live API path ──────────────────────────────────────────────────────────
    if source != "cricsheet":
        live_matches, src = fetch_live_matches(format_filter=format, limit=limit)
        if live_matches:
            return {
                "matches": live_matches,
                "count": len(live_matches),
                "source": src,
                "live": True,
                "data_note": f"Live data via {src}",
            }
        # Live API returned nothing (rate limit / error) — fall through to Cricsheet

    # ── Cricsheet static fallback ──────────────────────────────────────────────
    provider = _get_provider()

    # Map UI tab labels → all matching Cricsheet format codes
    FORMAT_MAP: dict[str, list[str]] = {
        "T20":  ["T20", "IT20", "IPL", "BBL", "CPL", "PSL", "BPL", "LPL",
                 "SA20", "SAT", "WPL", "MLC", "ILT", "SSM", "NTB", "WBB",
                 "MLT", "NPL", "WCL", "WTB", "RLC", "MCL", "CCH", "CTC",
                 "MDM", "FRB", "HND", "RHF", "PKS", "IPO", "IPT",
                 "MCT", "WOD", "CEC", "SMA"],
        "ODI":  ["ODI", "ODC", "ODM"],
        "Test": ["Test", "WTC", "WTB"],
    }

    fmt_codes = FORMAT_MAP.get(format or "", [format] if format else None)  # type: ignore[arg-type]
    raw = provider.get_matches(formats=fmt_codes)
    if not raw:
        return {
            "matches": [], "count": 0, "source": "cricsheet", "live": False,
            "data_note": "No matches found for this format in the Cricsheet dataset.",
        }

    df = pl.DataFrame(raw)
    df = (
        df.filter(pl.col("start_date").is_not_null())
        .sort("start_date", descending=True)
        .head(limit)
    )

    # Resolve both teams from ball-by-ball data
    lf_balls = provider.datasets.get("balls")
    match_teams: dict = {}
    if lf_balls is not None and not df.is_empty():
        ids = df.get_column("match_id").to_list()
        teams_df = (
            lf_balls
            .filter(pl.col("match_id").is_in(ids))
            .select(["match_id", "batting_team", "innings"])
            .unique()
            .collect()
        )
        for mid in ids:
            rows = teams_df.filter(pl.col("match_id") == mid).sort("innings")
            match_teams[mid] = rows.get_column("batting_team").unique().to_list()

    latest_date = df.get_column("start_date").max() if not df.is_empty() else "unknown"

    results = []
    for row in df.iter_rows(named=True):
        mid = row.get("match_id")
        teams = match_teams.get(mid, [])
        results.append({
            "match_id": mid,
            "team1": teams[0] if len(teams) > 0 else (row.get("toss_winner") or ""),
            "team2": teams[1] if len(teams) > 1 else "",
            "winner": row.get("winner") or "",
            "venue": row.get("venue") or "",
            "date": str(row.get("start_date") or ""),
            "format": row.get("format") or format or "",
            "competition": row.get("competition") or "",
            "status": "recent",
            "score": "",
        })

    return {
        "matches": results,
        "count": len(results),
        "source": "cricsheet",
        "live": False,
        "data_note": f"Cricsheet snapshot — latest match: {latest_date}. Set CRICAPI_KEY in Railway Variables for live data.",
        "latest_date": str(latest_date),
    }


@router.post("/")
def create_match(match: MatchInput):
    return {"received": match.model_dump()}
