from fastapi import APIRouter
import polars as pl
from ..providers.cricsheet_provider import CricsheetProvider

router = APIRouter()

_provider: CricsheetProvider | None = None

def _get_provider() -> CricsheetProvider:
    global _provider
    if _provider is None:
        _provider = CricsheetProvider()
        _provider.load()
    return _provider

@router.get("/")
def list_players(q: str | None = None, limit: int = 100):
    provider = _get_provider()
    players = provider.list_players(q=q, limit=limit)
    return {"players": players, "query": q, "count": len(players)}

@router.get("/{player_name}/stats")
def get_player_stats(player_name: str):
    """Return structured chart-ready stats for a player."""
    provider = _get_provider()
    df = provider.get_player_events(player_name)

    if df.is_empty():
        return {"player": player_name, "found": False, "batter": None, "bowler": None}

    # Resolve the canonical name from actual data (handles fuzzy-match fallback).
    # Pick the most-frequent batter name that matches; fall back to input.
    candidate_batters = df.filter(
        pl.col("batter").str.to_lowercase().str.contains(player_name.lower())
    ).get_column("batter").drop_nulls().to_list()
    canonical = max(set(candidate_batters), key=candidate_batters.count) if candidate_batters else player_name
    # If no batter rows, try the bowler column
    if not candidate_batters:
        candidate_bowlers = df.filter(
            pl.col("bowler").str.to_lowercase().str.contains(player_name.lower())
        ).get_column("bowler").drop_nulls().to_list()
        canonical = max(set(candidate_bowlers), key=candidate_bowlers.count) if candidate_bowlers else player_name

    # ── Batter stats ────────────────────────────────────────────
    bat = df.filter(pl.col("batter") == canonical)
    batter_data = None
    if bat.height > 0:
        # Runs per match (last 20)
        rpm = (
            bat.group_by(["match_id", "start_date"])
            .agg(
                pl.col("runs_off_bat").sum().alias("runs"),
                pl.len().alias("balls"),
            )
            .sort("start_date")
            .tail(20)
        )
        runs_per_match = [
            {"match": str(r["start_date"])[:10], "runs": int(r["runs"]), "balls": int(r["balls"])}
            for r in rpm.iter_rows(named=True)
        ]
        # Runs by format
        by_format = (
            bat.group_by("format")
            .agg(
                pl.col("runs_off_bat").sum().alias("runs"),
                pl.col("match_id").n_unique().alias("matches"),
            )
        )
        format_runs = [
            {"format": r["format"], "runs": int(r["runs"]), "matches": int(r["matches"])}
            for r in by_format.iter_rows(named=True)
        ]
        # Dismissal types
        dismissed = df.filter(pl.col("player_dismissed") == canonical)
        dismissal_counts = (
            dismissed.group_by("wicket_type").len()
            if dismissed.height > 0 else pl.DataFrame({"wicket_type": [], "len": []})
        )
        dismissals = [
            {"type": r["wicket_type"] or "unknown", "count": int(r["len"])}
            for r in dismissal_counts.iter_rows(named=True)
            if r["wicket_type"]
        ]
        # Summary
        total_runs = int(bat.select(pl.col("runs_off_bat").sum()).item() or 0)
        total_balls = bat.height
        total_matches = bat.select(pl.col("match_id").n_unique()).item()
        fours = bat.filter(pl.col("runs_off_bat") == 4).height
        sixes = bat.filter(pl.col("runs_off_bat") == 6).height

        batter_data = {
            "total_runs": total_runs,
            "total_balls": total_balls,
            "total_matches": int(total_matches),
            "strike_rate": round(total_runs / total_balls * 100, 1) if total_balls > 0 else 0,
            "average": round(total_runs / max(dismissed.height, 1), 1),
            "fours": fours,
            "sixes": sixes,
            "runs_per_match": runs_per_match,
            "format_runs": format_runs,
            "dismissals": dismissals,
        }

    # ── Bowler stats ────────────────────────────────────────────
    bowl = df.filter(pl.col("bowler") == canonical)
    bowler_data = None
    if bowl.height > 0:
        # Exclude run outs — those are not credited to the bowler
        wickets = bowl.filter(
            pl.col("player_dismissed").is_not_null()
            & pl.col("wicket_type").is_not_null()
            & ~pl.col("wicket_type").is_in(["run out", "retired hurt", "retired out", "obstructing the field"])
        )
        # Wickets per match (last 20)
        wpm = (
            bowl.group_by(["match_id", "start_date"])
            .agg(
                (
                    pl.col("player_dismissed").is_not_null()
                    & ~pl.col("wicket_type").is_in(["run out", "retired hurt", "retired out"])
                ).sum().alias("wickets"),
                pl.col("runs_off_bat").sum().alias("runs_conceded"),
                pl.len().alias("balls"),
            )
            .sort("start_date")
            .tail(20)
        )
        wickets_per_match = [
            {
                "match": str(r["start_date"])[:10],
                "wickets": int(r["wickets"]),
                "economy": round(r["runs_conceded"] / (r["balls"] / 6), 1) if r["balls"] > 0 else 0,
            }
            for r in wpm.iter_rows(named=True)
        ]
        # Wickets by format
        by_format_w = (
            bowl.group_by("format")
            .agg(
                (
                    pl.col("player_dismissed").is_not_null()
                    & ~pl.col("wicket_type").is_in(["run out", "retired hurt", "retired out"])
                ).sum().alias("wickets"),
                pl.col("match_id").n_unique().alias("matches"),
            )
        )
        format_wickets = [
            {"format": r["format"], "wickets": int(r["wickets"]), "matches": int(r["matches"])}
            for r in by_format_w.iter_rows(named=True)
        ]
        total_wickets = wickets.height
        total_runs_c = int(bowl.select(pl.col("runs_off_bat").sum()).item() or 0)
        total_balls_b = bowl.height
        overs = total_balls_b / 6

        bowler_data = {
            "total_wickets": total_wickets,
            "total_balls": total_balls_b,
            "total_matches": int(bowl.select(pl.col("match_id").n_unique()).item()),
            "economy": round(total_runs_c / overs, 2) if overs > 0 else 0,
            "average": round(total_runs_c / max(total_wickets, 1), 1),
            "strike_rate": round(total_balls_b / max(total_wickets, 1), 1),
            "wickets_per_match": wickets_per_match,
            "format_wickets": format_wickets,
        }

    return {"player": canonical, "found": True, "batter": batter_data, "bowler": bowler_data}
