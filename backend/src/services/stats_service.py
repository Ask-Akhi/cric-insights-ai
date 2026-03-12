from dataclasses import dataclass
from typing import Dict, Any
import polars as pl

@dataclass
class BatterInsights:
    avg_vs_opponent: Dict[str, float]
    first_innings_avg: float | None
    second_innings_avg: float | None
    venue_avg: Dict[str, float]
    struggles_vs_bowlers: Dict[str, Dict[str, float]]  # bowler -> metrics
    venue_boundaries: Dict[str, Dict[str, int]]  # venue -> {fours, sixes}
    expected_runs: float | None

@dataclass
class BowlerInsights:
    wickets_vs_team: Dict[str, int]
    wickets_at_venue: Dict[str, int]
    recent_form: float | None
    expected_wickets: float | None
    innings_split_wickets: Dict[str, int]  # first, second
    dismissals_vs_batters: Dict[str, int]
    likely_wickets: Dict[str, float]

class StatsService:
    def __init__(self, provider):
        self.provider = provider

    def compute_batter(self, player_name: str, venue: str | None = None, opponent: str | None = None) -> BatterInsights:
        df = self.provider.get_player_events(player_name)
        if df.is_empty():
            return BatterInsights({}, None, None, {}, {}, {}, None)
        # Batter-only rows
        bat = df.filter(pl.col("batter") == player_name)
        # Runs per match vs bowling_team
        by_team = bat.group_by(["bowling_team", "match_id"]).agg(pl.col("runs_off_bat").sum().alias("runs")).group_by("bowling_team").agg(pl.col("runs").mean())
        avg_vs_opponent = {row[0]: float(row[1]) if row[1] is not None else 0.0 for row in by_team.iter_rows()}
        # Innings split
        by_innings = bat.group_by("innings").agg(pl.col("runs_off_bat").sum().alias("runs"))
        first = by_innings.filter(pl.col("innings") == 1).select("runs").to_series().mean()
        second = by_innings.filter(pl.col("innings") == 2).select("runs").to_series().mean()
        # Venue averages
        by_venue = bat.group_by(["venue", "match_id"]).agg(pl.col("runs_off_bat").sum().alias("runs")).group_by("venue").agg(pl.col("runs").mean())
        venue_avg = {row[0]: float(row[1]) if row[1] is not None else 0.0 for row in by_venue.iter_rows()}
        # Struggles vs bowlers: dismissals and dot-ball rate
        bowl_events = df.filter(pl.col("bowler").is_not_null())
        dismissals = bowl_events.filter(pl.col("player_dismissed") == player_name).group_by("bowler").len().rename({"len": "dismissals"})
        dots = bat.filter(pl.col("runs_off_bat") == 0).group_by("bowler").len().rename({"len": "dots"})
        faced = bat.group_by("bowler").len().rename({"len": "balls"})
        struggles = dismissals.join(dots, on="bowler", how="outer").join(faced, on="bowler", how="outer").with_columns((pl.col("dots") / pl.col("balls")).fill_null(0).alias("dot_rate"))
        struggles_vs_bowlers = {}
        for row in struggles.iter_rows(named=True):
            struggles_vs_bowlers[row["bowler"]] = {"dismissals": int(row.get("dismissals") or 0), "dot_rate": float(row.get("dot_rate") or 0.0)}
        # Venue boundaries
        fours = bat.filter(pl.col("runs_off_bat") == 4).group_by(["venue"]).len().rename({"len": "fours"})
        sixes = bat.filter(pl.col("runs_off_bat") == 6).group_by(["venue"]).len().rename({"len": "sixes"})
        vb = fours.join(sixes, on="venue", how="outer")
        venue_boundaries = {row[0]: {"fours": int(row[1] or 0), "sixes": int(row[2] or 0)} for row in vb.iter_rows()}
        # Expected runs simple: recent 10 innings average
        recent = bat.sort(["match_id","innings"]).group_by(["match_id","innings"]).agg(pl.col("runs_off_bat").sum().alias("runs")).sort("match_id").tail(10)
        expected_runs = float(recent.select(pl.col("runs").mean()).item()) if recent.height > 0 else None
        return BatterInsights(avg_vs_opponent, float(first) if first is not None else None, float(second) if second is not None else None, venue_avg, struggles_vs_bowlers, venue_boundaries, expected_runs)

    def compute_bowler(self, player_name: str, venue: str | None = None, opponent: str | None = None) -> BowlerInsights:
        df = self.provider.get_player_events(player_name)
        if df.is_empty():
            return BowlerInsights({}, {}, None, None, {"first": 0, "second": 0}, {}, {})
        bowl = df.filter(pl.col("bowler") == player_name)
        # Wickets vs team
        wickets_vs_team = {row[0]: int(row[1]) for row in bowl.filter(pl.col("player_dismissed").is_not_null()).group_by("batting_team").len().iter_rows()}
        # Wickets at venue
        wickets_at_venue = {row[0]: int(row[1]) for row in bowl.filter(pl.col("player_dismissed").is_not_null()).group_by("venue").len().iter_rows()}
        # Recent form: last 10 matches wickets
        per_match = bowl.group_by("match_id").agg(pl.col("player_dismissed").is_not_null().sum().alias("wk")).sort("match_id")
        recent_wk = float(per_match.tail(10).select(pl.col("wk").mean()).item()) if per_match.height > 0 else None
        # Innings split wickets
        split = bowl.filter(pl.col("player_dismissed").is_not_null()).group_by("innings").len()
        first = split.filter(pl.col("innings") == 1).select("len").to_series().sum() or 0
        second = split.filter(pl.col("innings") == 2).select("len").to_series().sum() or 0
        # Dismissals vs batters
        dismissals_vs_batters = {row[0]: int(row[1]) for row in bowl.filter(pl.col("player_dismissed").is_not_null()).group_by("player_dismissed").len().iter_rows()}
        # Likely wickets: rank batters by dismissal rate (dismissals / balls faced)
        balls_vs_batter = bowl.group_by("batter").len().rename({"len": "balls"})
        dis_vs_batter = bowl.filter(pl.col("player_dismissed").is_not_null()).group_by("player_dismissed").len().rename({"player_dismissed": "batter", "len": "dismissals"})
        rates = balls_vs_batter.join(dis_vs_batter, on="batter", how="outer").with_columns((pl.col("dismissals") / pl.col("balls")).fill_null(0).alias("rate")).sort("rate", descending=True)
        likely_wickets = {row[0]: float(row[2] or 0.0) for row in rates.iter_rows()}
        return BowlerInsights(wickets_vs_team, wickets_at_venue, recent_wk, recent_wk, {"first": int(first), "second": int(second)}, dismissals_vs_batters, likely_wickets)
