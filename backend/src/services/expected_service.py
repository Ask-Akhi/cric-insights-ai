from dataclasses import dataclass
from typing import Optional
import polars as pl


@dataclass
class ExpectedPerformance:
    expected_runs: Optional[float] = None
    expected_wickets: Optional[float] = None
    venue_factor: Optional[float] = None      # >1 favours batter/bowler at this venue
    opponent_factor: Optional[float] = None   # >1 favours player vs this opponent
    confidence: str = "low"                   # low / medium / high


class ExpectedService:
    def __init__(self, provider):
        self.provider = provider

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _recent_innings_avg(self, bat: pl.DataFrame, n: int = 10) -> Optional[float]:
        """Average runs per innings over last n innings."""
        if bat.is_empty():
            return None
        per_inn = (
            bat.group_by(["match_id", "innings"])
            .agg(pl.col("runs_off_bat").sum().alias("runs"))
            .sort(["match_id", "innings"])
        )
        tail = per_inn.tail(n)
        if tail.is_empty():
            return None
        return float(tail["runs"].mean())

    def _recent_wickets_avg(self, bowl: pl.DataFrame, n: int = 10) -> Optional[float]:
        """Average wickets per innings over last n bowling innings."""
        if bowl.is_empty():
            return None
        per_inn = (
            bowl.group_by(["match_id", "innings"])
            .agg(pl.col("player_dismissed").is_not_null().sum().alias("wk"))
            .sort(["match_id", "innings"])
        )
        tail = per_inn.tail(n)
        if tail.is_empty():
            return None
        return float(tail["wk"].mean())

    def _venue_bat_factor(self, bat: pl.DataFrame, venue: str) -> float:
        """Ratio: avg runs at venue / overall avg. Returns 1.0 if insufficient data."""
        if bat.is_empty() or not venue:
            return 1.0
        overall = bat.group_by(["match_id", "innings"]).agg(
            pl.col("runs_off_bat").sum().alias("r")
        )["r"].mean()
        at_venue = bat.filter(
            pl.col("venue").str.to_lowercase().str.contains(venue.lower())
        ).group_by(["match_id", "innings"]).agg(
            pl.col("runs_off_bat").sum().alias("r")
        )
        if at_venue.is_empty() or overall is None or overall == 0:
            return 1.0
        return float(at_venue["r"].mean() / overall)

    def _venue_bowl_factor(self, bowl: pl.DataFrame, venue: str) -> float:
        """Ratio: avg wickets at venue / overall avg. Returns 1.0 if insufficient data."""
        if bowl.is_empty() or not venue:
            return 1.0
        overall = bowl.group_by(["match_id", "innings"]).agg(
            pl.col("player_dismissed").is_not_null().sum().alias("w")
        )["w"].mean()
        at_venue = bowl.filter(
            pl.col("venue").str.to_lowercase().str.contains(venue.lower())
        ).group_by(["match_id", "innings"]).agg(
            pl.col("player_dismissed").is_not_null().sum().alias("w")
        )
        if at_venue.is_empty() or overall is None or overall == 0:
            return 1.0
        return float(at_venue["w"].mean() / overall)

    def _opponent_bat_factor(self, bat: pl.DataFrame, opponent: str) -> float:
        if bat.is_empty() or not opponent:
            return 1.0
        overall = bat.group_by(["match_id", "innings"]).agg(
            pl.col("runs_off_bat").sum().alias("r")
        )["r"].mean()
        vs = bat.filter(pl.col("bowling_team") == opponent).group_by(
            ["match_id", "innings"]
        ).agg(pl.col("runs_off_bat").sum().alias("r"))
        if vs.is_empty() or overall is None or overall == 0:
            return 1.0
        return float(vs["r"].mean() / overall)

    def _opponent_bowl_factor(self, bowl: pl.DataFrame, opponent: str) -> float:
        if bowl.is_empty() or not opponent:
            return 1.0
        overall = bowl.group_by(["match_id", "innings"]).agg(
            pl.col("player_dismissed").is_not_null().sum().alias("w")
        )["w"].mean()
        vs = bowl.filter(pl.col("batting_team") == opponent).group_by(
            ["match_id", "innings"]
        ).agg(pl.col("player_dismissed").is_not_null().sum().alias("w"))
        if vs.is_empty() or overall is None or overall == 0:
            return 1.0
        return float(vs["w"].mean() / overall)

    def _confidence(self, n_innings: int) -> str:
        if n_innings >= 20:
            return "high"
        if n_innings >= 8:
            return "medium"
        return "low"

    # ── Public API ──────────────────────────────────────────────────────────

    def estimate_batter(
        self,
        player_name: str,
        venue: str | None = None,
        opponent: str | None = None,
    ) -> ExpectedPerformance:
        df = self.provider.get_player_events(player_name)
        if df.is_empty():
            return ExpectedPerformance()

        bat = df.filter(pl.col("batter") == player_name)
        if bat.is_empty():
            return ExpectedPerformance()

        base = self._recent_innings_avg(bat, n=10)
        if base is None:
            return ExpectedPerformance()

        vf = self._venue_bat_factor(bat, venue or "")
        of = self._opponent_bat_factor(bat, opponent or "")
        expected = round(base * vf * of, 1)

        n_innings = bat.select(
            pl.struct("match_id", "innings").n_unique()
        ).item()

        return ExpectedPerformance(
            expected_runs=expected,
            venue_factor=round(vf, 3),
            opponent_factor=round(of, 3),
            confidence=self._confidence(n_innings),
        )

    def estimate_bowler(
        self,
        player_name: str,
        venue: str | None = None,
        opponent: str | None = None,
    ) -> ExpectedPerformance:
        df = self.provider.get_player_events(player_name)
        if df.is_empty():
            return ExpectedPerformance()

        bowl = df.filter(pl.col("bowler") == player_name)
        if bowl.is_empty():
            return ExpectedPerformance()

        base = self._recent_wickets_avg(bowl, n=10)
        if base is None:
            return ExpectedPerformance()

        vf = self._venue_bowl_factor(bowl, venue or "")
        of = self._opponent_bowl_factor(bowl, opponent or "")
        expected = round(base * vf * of, 2)

        n_innings = bowl.select(
            pl.struct("match_id", "innings").n_unique()
        ).item()

        return ExpectedPerformance(
            expected_wickets=expected,
            venue_factor=round(vf, 3),
            opponent_factor=round(of, 3),
            confidence=self._confidence(n_innings),
        )
