from dataclasses import dataclass
from typing import Dict, Any
import polars as pl


@dataclass
class BatterInsights:
    avg_vs_opponent: Dict[str, float]
    first_innings_avg: float | None
    second_innings_avg: float | None
    venue_avg: Dict[str, float]
    struggles_vs_bowlers: Dict[str, Dict[str, float]]
    venue_boundaries: Dict[str, Dict[str, int]]
    expected_runs: float | None


@dataclass
class BowlerInsights:
    wickets_vs_team: Dict[str, int]
    wickets_at_venue: Dict[str, int]
    recent_form: float | None
    expected_wickets: float | None
    innings_split_wickets: Dict[str, int]
    dismissals_vs_batters: Dict[str, int]
    likely_wickets: Dict[str, float]


class StatsService:
    def __init__(self, provider):
        self.provider = provider

    def compute_batter(
        self,
        player_name: str,
        venue: str | None = None,
        opponent: str | None = None,
    ) -> BatterInsights:
        df = self.provider.get_player_events(player_name)
        if df.is_empty():
            return BatterInsights({}, None, None, {}, {}, {}, None)

        bat = df.filter(pl.col("batter") == player_name)

        # ── Runs vs opponent ────────────────────────────────────────────────
        # Derive opponent as the non-batting team: all batting_teams per match
        # that are NOT the player's own team (player's team = the batting_team
        # in rows where batter == player_name).
        player_team_per_match = (
            bat.group_by("match_id")
            .agg(pl.col("batting_team").first().alias("player_team"))
        )
        all_teams_per_match = (
            df.select(["match_id", "batting_team"]).unique()
        )
        vs_opp = (
            all_teams_per_match
            .join(player_team_per_match, on="match_id")
            .filter(pl.col("batting_team") != pl.col("player_team"))
            .join(
                bat.group_by("match_id").agg(
                    pl.col("runs_off_bat").sum().alias("runs")
                ),
                on="match_id",
            )
            .group_by("batting_team")
            .agg(pl.col("runs").mean().alias("avg"))
        )
        avg_vs_opponent: Dict[str, float] = {
            row[0]: float(row[1]) if row[1] is not None else 0.0
            for row in vs_opp.iter_rows()
        }

        # ── Innings split ────────────────────────────────────────────────────
        by_innings = bat.group_by("innings").agg(
            pl.col("runs_off_bat").sum().alias("runs")
        )
        first_s  = by_innings.filter(pl.col("innings") == 1)["runs"].mean()
        second_s = by_innings.filter(pl.col("innings") == 2)["runs"].mean()

        # ── Venue averages ───────────────────────────────────────────────────
        by_venue = (
            bat.group_by(["venue", "match_id"])
            .agg(pl.col("runs_off_bat").sum().alias("runs"))
            .group_by("venue")
            .agg(pl.col("runs").mean().alias("avg"))
        )
        venue_avg: Dict[str, float] = {
            row[0]: float(row[1]) if row[1] is not None else 0.0
            for row in by_venue.iter_rows()
        }

        # ── Struggles vs bowlers ─────────────────────────────────────────────
        dismissals = (
            df.filter(pl.col("player_dismissed") == player_name)
            .group_by("bowler").len().rename({"len": "dismissals"})
        )
        dots = (
            bat.filter(pl.col("runs_off_bat") == 0)
            .group_by("bowler").len().rename({"len": "dots"})
        )
        faced = bat.group_by("bowler").len().rename({"len": "balls"})
        struggles = (
            dismissals
            .join(dots,  on="bowler", how="full", coalesce=True)
            .join(faced, on="bowler", how="full", coalesce=True)
            .with_columns(
                (pl.col("dots").fill_null(0) / pl.col("balls").fill_null(1))
                .alias("dot_rate")
            )
        )
        struggles_vs_bowlers: Dict[str, Dict[str, float]] = {}
        for row in struggles.iter_rows(named=True):
            struggles_vs_bowlers[row["bowler"]] = {
                "dismissals": int(row.get("dismissals") or 0),
                "dot_rate":   float(row.get("dot_rate") or 0.0),
            }

        # ── Venue boundaries ─────────────────────────────────────────────────
        fours = bat.filter(pl.col("runs_off_bat") == 4).group_by("venue").len().rename({"len": "fours"})
        sixes = bat.filter(pl.col("runs_off_bat") == 6).group_by("venue").len().rename({"len": "sixes"})
        vb = fours.join(sixes, on="venue", how="full")
        venue_boundaries: Dict[str, Dict[str, int]] = {
            row[0]: {"fours": int(row[1] or 0), "sixes": int(row[2] or 0)}
            for row in vb.iter_rows()
        }

        # ── Expected runs ────────────────────────────────────────────────────
        recent = (
            bat.group_by(["match_id", "innings"])
            .agg(pl.col("runs_off_bat").sum().alias("runs"))
            .sort("match_id")
            .tail(10)
        )
        expected_runs = (
            float(recent["runs"].mean())
            if recent.height > 0 else None
        )

        return BatterInsights(
            avg_vs_opponent,
            float(first_s)  if first_s  is not None else None,
            float(second_s) if second_s is not None else None,
            venue_avg,
            struggles_vs_bowlers,
            venue_boundaries,
            expected_runs,
        )

    def compute_bowler(
        self,
        player_name: str,
        venue: str | None = None,
        opponent: str | None = None,
    ) -> BowlerInsights:
        df = self.provider.get_player_events(player_name)
        if df.is_empty():
            return BowlerInsights({}, {}, None, None, {"first": 0, "second": 0}, {}, {})

        bowl = df.filter(pl.col("bowler") == player_name)
        wk_rows = bowl.filter(pl.col("player_dismissed").is_not_null())

        # ── Wickets vs batting team ──────────────────────────────────────────
        wickets_vs_team: Dict[str, int] = {
            row[0]: int(row[1])
            for row in wk_rows.group_by("batting_team").len().iter_rows()
        }

        # ── Wickets at venue ─────────────────────────────────────────────────
        wickets_at_venue: Dict[str, int] = {
            row[0]: int(row[1])
            for row in wk_rows.group_by("venue").len().iter_rows()
        }

        # ── Recent form ──────────────────────────────────────────────────────
        per_match = (
            bowl.group_by("match_id")
            .agg(pl.col("player_dismissed").is_not_null().sum().alias("wk"))
            .sort("match_id")
        )
        recent_wk = (
            float(per_match.tail(10)["wk"].mean())
            if per_match.height > 0 else None
        )

        # ── Innings split ────────────────────────────────────────────────────
        split = wk_rows.group_by("innings").len()
        first_w  = split.filter(pl.col("innings") == 1)["len"].sum() or 0
        second_w = split.filter(pl.col("innings") == 2)["len"].sum() or 0

        # ── Dismissals vs batters ─────────────────────────────────────────────
        dismissals_vs_batters: Dict[str, int] = {
            row[0]: int(row[1])
            for row in wk_rows.group_by("player_dismissed").len().iter_rows()
        }

        # ── Likely wickets rate ──────────────────────────────────────────────
        balls_vs = bowl.group_by("batter").len().rename({"len": "balls"})
        dis_vs   = (
            wk_rows.group_by("player_dismissed").len()
            .rename({"player_dismissed": "batter", "len": "dismissals"})
        )
        rates = (
            balls_vs.join(dis_vs, on="batter", how="full", coalesce=True)
            .with_columns(
                (pl.col("dismissals").fill_null(0) / pl.col("balls").fill_null(1))
                .alias("rate")
            )
            .sort("rate", descending=True)
        )
        likely_wickets: Dict[str, float] = {
            row[0]: float(row[2] or 0.0) for row in rates.iter_rows()
        }

        return BowlerInsights(
            wickets_vs_team,
            wickets_at_venue,
            recent_wk,
            recent_wk,
            {"first": int(first_w), "second": int(second_w)},
            dismissals_vs_batters,
            likely_wickets,
        )
