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

# Global lock so only one thread downloads/parses at a time
_DOWNLOAD_LOCK = threading.Lock()
# Track download state: None = not started, True = succeeded, False = failed
_DOWNLOAD_RESULT: bool | None = None
# Set to True while a download thread is running — prevents duplicate threads
_DOWNLOAD_RUNNING = False

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

    def _ensure_data(self):
        """Fire a one-shot daemon thread to download Cricsheet data if missing.

        Returns immediately — the health endpoint is NEVER blocked.
        The download runs in the background; the first few API calls that need
        data will get empty results until it completes (~2-4 min on Railway).

        Improvements over the original:
        - Allows retry if a previous download FAILED (not just "started")
        - Tracks success/failure state for health endpoint visibility
        """
        global _DOWNLOAD_RUNNING, _DOWNLOAD_RESULT
        if self._collect_parquet_paths():
            _DOWNLOAD_RESULT = True  # data exists (baked at build or prior download)
            return

        with _DOWNLOAD_LOCK:
            # Re-check after lock acquisition
            if self._collect_parquet_paths():
                _DOWNLOAD_RESULT = True
                return
            # Don't start a new thread if one is already running
            if _DOWNLOAD_RUNNING:
                return
            # If a previous download failed, allow retry
            if _DOWNLOAD_RESULT is True:
                return
            _DOWNLOAD_RUNNING = True

        def _run_download():
            global _DOWNLOAD_RUNNING, _DOWNLOAD_RESULT
            log.info("📥 No Cricsheet data found — downloading male dataset in background …")
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
                    log.info("✅ Cricsheet download complete — data now available")
                    _DOWNLOAD_RESULT = True
                else:
                    log.warning("⚠️  Cricsheet download failed:\n%s", result.stderr[-500:])
                    _DOWNLOAD_RESULT = False
            except Exception as e:
                log.warning("⚠️  Cricsheet download error: %s", e)
                _DOWNLOAD_RESULT = False
            finally:
                _DOWNLOAD_RUNNING = False

        t = threading.Thread(target=_run_download, daemon=True, name="cricsheet-download")
        t.start()

    def load(self):
        os.makedirs(RAW_DIR, exist_ok=True)
        os.makedirs(PARQUET_DIR, exist_ok=True)

        # Download data lazily if no parquet files exist yet
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

    @property
    def has_data(self) -> bool:
        """True when parquet data is loaded and available for queries."""
        if not self.loaded:
            return False
        return "balls" in self.datasets

    @staticmethod
    def data_status() -> dict:
        """Return data availability status for health/admin endpoints."""
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
            from ..core.config import FORMAT_EXPANSION
            allowed = FORMAT_EXPANSION.get(fmt, [fmt])
            q = q.filter(pl.col("format").is_in(allowed))
        return q.collect()

    def get_head_to_head(self, team_a: str, team_b: str,
                         fmt: str | None = None) -> pl.DataFrame:
        """Matches where both team_a and team_b appear (handles renamed teams)."""
        if not self.loaded:
            self.load()
        lf = self.datasets.get("balls")
        if lf is None:
            return pl.DataFrame()

        # Expand team names to include historical variants (e.g. RCB Bangalore/Bengaluru)
        from ..core.config import expand_team_names
        names_a = expand_team_names(team_a)
        names_b = expand_team_names(team_b)
        all_names = list(set(names_a + names_b))

        q = lf.filter(pl.col("batting_team").is_in(all_names))
        if fmt:
            from ..core.config import FORMAT_EXPANSION
            allowed = FORMAT_EXPANSION.get(fmt, [fmt])
            q = q.filter(pl.col("format").is_in(allowed))
        df = q.collect()
        if df.is_empty():
            return df
        match_teams = (
            df.group_by("match_id")
            .agg(pl.col("batting_team").unique().alias("teams"))
        )
        # A match counts if it has at least one name variant from each side
        both_ids = []
        for row in match_teams.iter_rows(named=True):
            teams_in_match = set(row["teams"])
            has_a = bool(teams_in_match & set(names_a))
            has_b = bool(teams_in_match & set(names_b))
            if has_a and has_b:
                both_ids.append(row["match_id"])
        if not both_ids:
            return pl.DataFrame()
        return df.filter(pl.col("match_id").is_in(both_ids))
