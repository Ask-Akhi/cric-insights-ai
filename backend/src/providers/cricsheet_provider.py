import os
from typing import Iterable, List, Dict
import polars as pl

from .base import BaseDataProvider

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
RAW_DIR = os.path.join(DATA_DIR, "raw")
PARQUET_DIR = os.path.join(DATA_DIR, "parquet")

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
        return paths

    def load(self):
        os.makedirs(RAW_DIR, exist_ok=True)
        os.makedirs(PARQUET_DIR, exist_ok=True)
        paths = self._collect_parquet_paths()
        if not paths:
            # No data yet
            self.loaded = True
            return
        # Build a single lazy scan
        lf = pl.concat([pl.scan_parquet(p) for p in paths])
        # Ensure expected columns exist
        expected = [
            "match_id","season","start_date","gender","format","competition","venue","city","country",
            "batting_team","bowling_team","innings","ball","batter","non_striker","bowler","runs_off_bat","extras",
            "wides","noballs","byes","legbyes","penalties","wicket_type","player_dismissed"
        ]
        for col in expected:
            if col not in lf.columns:
                lf = lf.with_columns(pl.lit(None).alias(col))
        self.datasets["balls"] = lf
        self.loaded = True

    def get_matches(self, formats: Iterable[str] | None = None):
        if not self.loaded:
            self.load()
        lf = self.datasets.get("balls")
        if lf is None:
            return []
        q = lf.select([
            pl.col("match_id"), pl.col("format"), pl.col("competition"), pl.col("venue"), pl.col("city"), pl.col("country"),
            pl.col("season"), pl.col("start_date"), pl.col("gender"),
        ]).unique()
        if formats:
            q = q.filter(pl.col("format").is_in(list(formats)))
        return q.collect().to_dict(as_series=False)

    def get_player_events(self, player_name: str):
        if not self.loaded:
            self.load()
        lf = self.datasets.get("balls")
        if lf is None:
            return pl.DataFrame()
        q = lf.filter((pl.col("batter") == player_name) | (pl.col("bowler") == player_name) | (pl.col("player_dismissed") == player_name))
        return q.collect()
