from fastapi import APIRouter, Query
from typing import Optional, List
from pydantic import BaseModel
from ..providers.cricsheet_provider import CricsheetProvider
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
        # Filter by winner or toss_winner containing team name
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

    top_bat_a = (
        df.filter(pl.col("batting_team") == team_a)
        .group_by("batter")
        .agg(pl.col("runs_off_bat").sum().alias("runs"))
        .sort("runs", descending=True)
        .head(3)
        .to_dicts()
    )
    top_bat_b = (
        df.filter(pl.col("batting_team") == team_b)
        .group_by("batter")
        .agg(pl.col("runs_off_bat").sum().alias("runs"))
        .sort("runs", descending=True)
        .head(3)
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
    }


@router.post("/")
def create_match(match: MatchInput):
    return {"received": match.model_dump()}
