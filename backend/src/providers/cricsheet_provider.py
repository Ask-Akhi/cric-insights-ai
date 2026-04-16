import os
import logging
import threading
import subprocess
import sys
from typing import Iterable, List, Dict
import polars as pl

from .base import BaseDataProvider

log = logging.getLogger(__name__)

_default_data = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DATA_DIR = os.environ.get("CRICSHEET_DATA_DIR", _default_data)
RAW_DIR = os.path.join(DATA_DIR, "raw")
PARQUET_DIR = os.path.join(DATA_DIR, "parquet")

_DOWNLOAD_LOCK = threading.Lock()
_DOWNLOAD_RESULT: bool | None = None
_DOWNLOAD_RUNNING = False

REQUIRED_COLS = [
    "match_id", "gender", "season", "start_date", "venue", "city",
    "format",
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

    def _ensure_data(self):
        """Fire a one-shot daemon thread to download Cricsheet data if missing."""
        global _DOWNLOAD_RUNNING, _DOWNLOAD_RESULT
        if self._collect_parquet_paths():
            _DOWNLOAD_RESULT = True
            return

        with _DOWNLOAD_LOCK:
            if self._collect_parquet_paths():
                _DOWNLOAD_RESULT = True
                return
            if _DOWNLOAD_RUNNING:
                return
            if _DOWNLOAD_RESULT is True:
                return
            _DOWNLOAD_RUNNING = True

        def _run_download():
            global _DOWNLOAD_RUNNING, _DOWNLOAD_RESULT
            log.info("No Cricsheet data found - downloading male dataset in background")
            try:
                repo_root = os.path.abspath(
                    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
                )
                result = subprocess.run(
                    [sys.executable, "-m",
                     "backend.src.scripts.parse_cricsheet",
                     "--gender", "male", "--download"],
                    capture_output=True, text=True, timeout=600,
                    cwd=repo_root,
                )
                if result.returncode == 0:
                    log.info("Cricsheet download complete")
                    _DOWNLOAD_RESULT = True
                else:
                    log.warning("Cricsheet download failed: %s", result.stderr[-500:])
                    _DOWNLOAD_RESULT = False
            except Exception as e:
                log.warning("Cricsheet download error: %s", e)
                _DOWNLOAD_RESULT = False
            finally:
                _DOWNLOAD_RUNNING = False

        t = threading.Thread(target=_run_download, daemon=True, name="cricsheet-download")
        t.start()

    def load(self):
        os.makedirs(RAW_DIR, exist_ok=True)
        os.makedirs(PARQUET_DIR, exist_ok=True)
        self._ensure_data()

        paths = self._collect_parquet_paths()
        if not paths:
            self.loaded = True
            return

        frames = []
        for p in paths:
            try:
                lf = pl.scan_parquet(p)
                schema = lf.collect_schema().names()
                if "match_type" in schema and "format" not in schema:
                    lf = lf.rename({"match_type": "format"})
                    schema = [("format" if c == "match_type" else c) for c in schema]
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

    @property
    def has_data(self) -> bool:
        if not self.loaded:
            return False
        return "balls" in self.datasets

    @staticmethod
    def data_status() -> dict:
        return {
            "download_running": _DOWNLOAD_RUNNING,
            "download_result": _DOWNLOAD_RESULT,
            "parquet_dir": PARQUET_DIR,
            "parquet_files_exist": bool(
                any(f.endswith(".parquet") for _, _, files in os.walk(PARQUET_DIR) for f in files)
            ) if os.path.isdir(PARQUET_DIR) else False,
        }

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
        return q.sort("start_date", descending=True).collect(streaming=True).to_dict(as_series=False)

    # Slim column projection — avoids materialising the full wide parquet row for
    # every ball. Saves ~60-80% RAM on 512 MB Render starter containers.
    _SLIM_COLS = [
        "match_id", "format", "competition", "season", "start_date",
        "venue", "city", "innings", "over", "batting_team",
        "batter", "non_striker", "bowler",
        "runs_off_bat", "extras", "wides", "noballs",
        "wicket_type", "player_dismissed",
        "toss_winner", "toss_decision", "winner", "gender",
    ]

    # Hard row cap — prevents OOM when IPL team queries return 200k+ rows.
    _MAX_ROWS = 50_000

    def _slim(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        """Project only the columns downstream code actually uses."""
        available = lf.collect_schema().names()
        return lf.select([c for c in self._SLIM_COLS if c in available])

    def get_player_events(self, player_name: str) -> pl.DataFrame:
        if not self.loaded:
            self.load()
        lf = self.datasets.get("balls")
        if lf is None:
            return pl.DataFrame()
        lf_slim = self._slim(lf)
        q = lf_slim.filter(
            (pl.col("batter") == player_name)
            | (pl.col("bowler") == player_name)
            | (pl.col("player_dismissed") == player_name)
        )
        df = q.head(self._MAX_ROWS).collect(streaming=True)
        if not df.is_empty():
            return df
        # Fallback: case-insensitive substring match
        name_lower = player_name.lower()
        q2 = lf_slim.filter(
            pl.col("batter").str.to_lowercase().str.contains(name_lower)
            | pl.col("bowler").str.to_lowercase().str.contains(name_lower)
        )
        return q2.head(self._MAX_ROWS).collect(streaming=True)

    def list_players(self, q: str | None = None, limit: int = 100) -> List[str]:
        """Return distinct player names. Filter applied early to avoid RAM spikes."""
        if not self.loaded:
            self.load()
        lf = self.datasets.get("balls")
        if lf is None:
            return []
        lf_b = lf.select(pl.col("batter").alias("name"))
        lf_w = lf.select(pl.col("bowler").alias("name"))
        if q:
            q_lower = q.lower()
            lf_b = lf_b.filter(pl.col("name").str.to_lowercase().str.contains(q_lower))
            lf_w = lf_w.filter(pl.col("name").str.to_lowercase().str.contains(q_lower))
        combined = (
            pl.concat([lf_b, lf_w], how="vertical")
            .filter(pl.col("name").is_not_null())
            .unique()
            .sort("name")
            .limit(limit)
        )
        return combined.collect(streaming=True).get_column("name").to_list()

    def get_venue_stats(self, venue: str, fmt: str | None = None) -> pl.DataFrame:
        """Ball-by-ball rows for a specific venue."""
        if not self.loaded:
            self.load()
        lf = self.datasets.get("balls")
        if lf is None:
            return pl.DataFrame()
        lf_slim = self._slim(lf)
        q = lf_slim.filter(pl.col("venue").str.to_lowercase().str.contains(venue.lower()))
        if fmt:
            from ..core.config import FORMAT_EXPANSION
            allowed = FORMAT_EXPANSION.get(fmt, [fmt])
            q = q.filter(pl.col("format").is_in(allowed))
        return q.head(self._MAX_ROWS).collect(streaming=True)

    def get_head_to_head(self, team_a: str, team_b: str,
                         fmt: str | None = None) -> pl.DataFrame:
        """Head-to-head balls for two teams. Pure Polars semi-join — no iter_rows()."""
        if not self.loaded:
            self.load()
        lf = self.datasets.get("balls")
        if lf is None:
            return pl.DataFrame()

        from ..core.config import expand_team_names
        names_a = expand_team_names(team_a)
        names_b = expand_team_names(team_b)
        all_names = list(set(names_a + names_b))

        lf_slim = self._slim(lf)
        q = lf_slim.filter(pl.col("batting_team").is_in(all_names))
        if fmt:
            from ..core.config import FORMAT_EXPANSION
            allowed = FORMAT_EXPANSION.get(fmt, [fmt])
            q = q.filter(pl.col("format").is_in(allowed))

        # Identify match_ids where BOTH teams appear — stays lazy until collect().
        match_teams = (
            q.select("match_id", "batting_team")
            .unique()
            .with_columns([
                pl.col("batting_team").is_in(names_a).alias("_is_a"),
                pl.col("batting_team").is_in(names_b).alias("_is_b"),
            ])
            .group_by("match_id")
            .agg([
                pl.col("_is_a").any().alias("_has_a"),
                pl.col("_is_b").any().alias("_has_b"),
            ])
            .filter(pl.col("_has_a") & pl.col("_has_b"))
            .select("match_id")
        )

        return (
            q.join(match_teams, on="match_id", how="semi")
            .head(self._MAX_ROWS)
            .collect(streaming=True)
        )