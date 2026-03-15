import os
from typing import Iterable, List, Dict
import polars as pl

from .base import BaseDataProvider

_default_data = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DATA_DIR = os.environ.get("CRICSHEET_DATA_DIR", _default_data)
RAW_DIR = os.path.join(DATA_DIR, "raw")
PARQUET_DIR = os.path.join(DATA_DIR, "parquet")

# Columns that must exist in every loaded LazyFrame
REQUIRED_COLS = [
    "match_id", "gender", "season", "start_date", "venue", "city",
    "format",           # aliased from match_type on load
    "competition", "toss_winner", "toss_decision", "winner",
    "innings", "over", "batting_team", "batter", "non_striker", "bowler",
    "runs_off_bat", "extras", "wides", "noballs", "byes", "legbyes",
    "penalties", "wicket_type", "player_dismissed",
]


class CricsheetProvider(BaseDataProvider):
    def __init__(self):
        self.loaded = False
        self.datasets: Dict[str, pl.LazyFrame] = {}

    def _collect_parquet_paths(self) -> List[str]:
        paths = []
        for root, _, files in os.walk(PARQUET_DIR):
            for f in files:
                if f.endswith(".parquet"):
                    paths.append(os.path.join(root, f))
        return sorted(paths)

    def load(self):
        os.makedirs(RAW_DIR, exist_ok=True)
        os.makedirs(PARQUET_DIR, exist_ok=True)

        paths = self._collect_parquet_paths()
        if not paths:
            self.loaded = True
            return

        frames = []
        for p in paths:
            try:
                lf = pl.scan_parquet(p)
                schema = lf.collect_schema().names()

                # Rename match_type → format (parse_cricsheet.py writes "match_type")
                if "match_type" in schema and "format" not in schema:
                    lf = lf.rename({"match_type": "format"})
                    schema = [("format" if c == "match_type" else c) for c in schema]

                # Inject missing columns as nulls so concat works
                for col in REQUIRED_COLS:
                    if col not in schema:
                        lf = lf.with_columns(pl.lit(None).cast(pl.Utf8).alias(col))

                frames.append(lf)
            except Exception:
                continue

        if not frames:
            self.loaded = True
            return

        lf = pl.concat(frames, how="diagonal_relaxed")
        self.datasets["balls"] = lf
        self.loaded = True

    # ── Public API ──────────────────────────────────────────────────────────

    def get_matches(self, formats: Iterable[str] | None = None):
        if not self.loaded:
            self.load()
        lf = self.datasets.get("balls")
        if lf is None:
            return []
        q = lf.select([
            "match_id", "format", "competition", "venue", "city",
            "gender", "season", "start_date", "toss_winner",
            "toss_decision", "winner",
        ]).unique(subset=["match_id"])
        if formats:
            q = q.filter(pl.col("format").is_in(list(formats)))
        return q.sort("start_date", descending=True).collect().to_dict(as_series=False)

    def get_player_events(self, player_name: str) -> pl.DataFrame:
        if not self.loaded:
            self.load()
        lf = self.datasets.get("balls")
        if lf is None:
            return pl.DataFrame()
        # First try exact match (fast path)
        q = lf.filter(
            (pl.col("batter") == player_name)
            | (pl.col("bowler") == player_name)
            | (pl.col("player_dismissed") == player_name)
        )
        df = q.collect()
        if not df.is_empty():
            return df
        # Fallback: case-insensitive substring match on batter/bowler columns
        name_lower = player_name.lower()
        q2 = lf.filter(
            pl.col("batter").str.to_lowercase().str.contains(name_lower)
            | pl.col("bowler").str.to_lowercase().str.contains(name_lower)
        )
        return q2.collect()

    def list_players(self, q: str | None = None, limit: int = 100) -> List[str]:
        """Return distinct player names (batters + bowlers), optionally filtered."""
        if not self.loaded:
            self.load()
        lf = self.datasets.get("balls")
        if lf is None:
            return []
        batters = lf.select(pl.col("batter").alias("name")).unique()
        bowlers = lf.select(pl.col("bowler").alias("name")).unique()
        combined = (
            pl.concat([batters, bowlers], how="vertical")
            .filter(pl.col("name").is_not_null())
            .unique()
            .sort("name")
        )
        if q:
            combined = combined.filter(
                pl.col("name").str.to_lowercase().str.contains(q.lower())
            )
        return combined.limit(limit).collect().get_column("name").to_list()

    def get_venue_stats(self, venue: str, fmt: str | None = None) -> pl.DataFrame:
        """Ball-by-ball rows for a specific venue."""
        if not self.loaded:
            self.load()
        lf = self.datasets.get("balls")
        if lf is None:
            return pl.DataFrame()
        q = lf.filter(pl.col("venue").str.to_lowercase().str.contains(venue.lower()))
        if fmt:
            q = q.filter(pl.col("format") == fmt)
        return q.collect()

    def get_head_to_head(self, team_a: str, team_b: str,
                         fmt: str | None = None) -> pl.DataFrame:
        """Matches where both team_a and team_b appear."""
        if not self.loaded:
            self.load()
        lf = self.datasets.get("balls")
        if lf is None:
            return pl.DataFrame()
        q = lf.filter(
            (pl.col("batting_team") == team_a) | (pl.col("batting_team") == team_b)
        )
        if fmt:
            q = q.filter(pl.col("format") == fmt)
        df = q.collect()
        if df.is_empty():
            return df
        match_teams = (
            df.group_by("match_id")
            .agg(pl.col("batting_team").unique().alias("teams"))
        )
        both = match_teams.filter(
            pl.col("teams").list.contains(team_a)
            & pl.col("teams").list.contains(team_b)
        ).get_column("match_id")
        return df.filter(pl.col("match_id").is_in(both))
