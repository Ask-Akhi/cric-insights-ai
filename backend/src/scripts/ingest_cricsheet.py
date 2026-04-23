"""
ingest_cricsheet.py — Parquet → PostgreSQL nightly ingest job.

Run manually:
    python -m backend.src.scripts.ingest_cricsheet

Run as nightly cron (Render cron job or APScheduler):
    0 2 * * *  python -m backend.src.scripts.ingest_cricsheet

What it does:
  1. Reads existing Parquet files (same source as old Polars provider)
  2. Pre-aggregates player stats, h2h, recent form into DataFrames
  3. Upserts to PostgreSQL using asyncpg COPY + ON CONFLICT DO UPDATE
  4. Generates match summary text + optionally embeds with Gemini/OpenAI
  5. No Polars at query time — DB serves all runtime reads

Memory usage: ~150 MB peak during aggregation (runs offline, not on Render)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Load backend/.env so DATABASE_URL (and other vars) are available when
# running as `python -m backend.src.scripts.ingest_cricsheet` from repo root.
_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
if _ENV_PATH.exists():
    load_dotenv(_ENV_PATH)

import polars as pl

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger("ingest")

# ── Paths ─────────────────────────────────────────────────────────────────────
# ingest_cricsheet.py lives at backend/src/scripts/ingest_cricsheet.py
#   parents[0] = scripts/
#   parents[1] = src/
#   parents[2] = backend/
#   parents[3] = repo root
_REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = Path(os.environ.get("CRICSHEET_DATA_DIR",
                               str(_REPO_ROOT / "backend" / "src" / "data")))
PARQUET_DIR = DATA_DIR / "parquet" / "male"

DATABASE_URL = os.environ.get("DATABASE_URL", "")


# ── Load all Parquet files ────────────────────────────────────────────────────

def load_parquet() -> pl.LazyFrame:
    paths = sorted(PARQUET_DIR.glob("*.parquet"))
    if not paths:
        log.error("No parquet files found in %s", PARQUET_DIR)
        sys.exit(1)
    log.info("Loading %d parquet files from %s", len(paths), PARQUET_DIR)
    return pl.scan_parquet(str(PARQUET_DIR / "*.parquet"))


# ── Aggregation helpers ───────────────────────────────────────────────────────

def build_player_season_stats(lf: pl.LazyFrame) -> pl.DataFrame:
    """Pre-aggregate batting + bowling stats per player/team/season/format."""
    log.info("Aggregating player season stats …")

    # Rename match_type → format if needed
    cols = lf.schema.names()
    if "match_type" in cols and "format" not in cols:
        lf = lf.rename({"match_type": "format"})

    # ── Batting ──
    batting = (
        lf.filter(pl.col("runs_off_bat").is_not_null())
        .group_by(["batter", "batting_team", "season", "format"])
        .agg([
            pl.col("match_id").n_unique().alias("bat_matches"),
            pl.col("runs_off_bat").sum().alias("runs"),
            pl.col("runs_off_bat").count().alias("balls_faced"),
            (pl.col("runs_off_bat") == 4).sum().alias("fours"),
            (pl.col("runs_off_bat") == 6).sum().alias("sixes"),
            pl.col("player_dismissed").eq(pl.col("batter")).sum().alias("dismissals"),
        ])
        .rename({"batter": "player", "batting_team": "team"})
        .with_columns([
            pl.when(pl.col("dismissals") > 0)
              .then(pl.col("runs").cast(pl.Float64) / pl.col("dismissals"))
              .otherwise(None)
              .round(2).alias("avg"),
            pl.when(pl.col("balls_faced") > 0)
              .then(pl.col("runs").cast(pl.Float64) / pl.col("balls_faced") * 100)
              .otherwise(None)
              .round(2).alias("strike_rate"),
        ])
        .collect(streaming=True)
    )

    # ── Bowling ──
    bowling = (
        lf.filter(pl.col("bowler").is_not_null())
        .group_by(["bowler", "season", "format"])
        .agg([
            pl.col("match_id").n_unique().alias("bowl_matches"),
            pl.col("wicket_type").is_not_null().sum().alias("wickets"),
            pl.col("runs_off_bat").count().alias("balls_bowled"),
            (pl.col("runs_off_bat") + pl.col("extras").fill_null(0)).sum().alias("runs_conceded"),
        ])
        .with_columns([
            pl.when(pl.col("balls_bowled") > 0)
              .then(pl.col("runs_conceded").cast(pl.Float64) /
                    (pl.col("balls_bowled") / 6))
              .otherwise(None)
              .round(2).alias("economy"),
            pl.when(pl.col("wickets") > 0)
              .then(pl.col("runs_conceded").cast(pl.Float64) / pl.col("wickets"))
              .otherwise(None)
              .round(2).alias("bowling_avg"),
            pl.when(pl.col("wickets") > 0)
              .then(pl.col("balls_bowled").cast(pl.Float64) / pl.col("wickets"))
              .otherwise(None)
              .round(2).alias("bowling_sr"),
        ])
        .collect(streaming=True)
    )

    # Need team for bowling — join via batting_team of the bowler's match
    # Use a match-level team lookup
    team_lookup = (
        lf.select(["match_id", "bowler", "batting_team"])
        .filter(pl.col("bowler").is_not_null())
        .rename({"batting_team": "batting_team_raw"})
        # The bowling team is the other team — we'll approximate via bowler's
        # most common team association from batting data instead
        .group_by("bowler")
        .agg(pl.col("batting_team_raw").mode().first().alias("team"))
        .collect(streaming=True)
    )

    bowling = bowling.join(team_lookup, on="bowler", how="left").rename({"bowler": "player"})

    # ── Merge batting + bowling on player/team/season/format ──
    merged = batting.join(
        bowling.select(["player", "season", "format",
                        "bowl_matches", "wickets", "balls_bowled",
                        "runs_conceded", "economy", "bowling_avg", "bowling_sr"]),
        on=["player", "season", "format"],
        how="outer",
        coalesce=True,
    ).fill_null(0)

    log.info("Player season stats: %d rows", len(merged))
    return merged


def build_head_to_head(lf: pl.LazyFrame) -> pl.DataFrame:
    """Pre-aggregate win/loss summary per (team_a, team_b, format)."""
    log.info("Aggregating head-to-head summaries …")

    cols = lf.schema.names()
    if "match_type" in cols and "format" not in cols:
        lf = lf.rename({"match_type": "format"})

    # One row per match with team pair + winner
    matches = (
        lf.select(["match_id", "innings", "batting_team", "format",
                   "winner", "start_date"])
        .filter(pl.col("innings") == 1)
        .unique("match_id")
        .collect(streaming=True)
    )

    # We need both teams — get them from innings 1 and 2
    t1 = (
        lf.filter(pl.col("innings") == 1)
        .select(["match_id", "batting_team", "format", "winner", "start_date"])
        .unique("match_id")
        .rename({"batting_team": "team_a"})
        .collect(streaming=True)
    )
    t2 = (
        lf.filter(pl.col("innings") == 2)
        .select(["match_id", "batting_team"])
        .unique("match_id")
        .rename({"batting_team": "team_b"})
        .collect(streaming=True)
    )

    match_pairs = t1.join(t2, on="match_id", how="inner")

    # Normalise so team_a < team_b alphabetically
    match_pairs = match_pairs.with_columns([
        pl.when(pl.col("team_a") > pl.col("team_b"))
          .then(pl.col("team_b")).otherwise(pl.col("team_a")).alias("ta"),
        pl.when(pl.col("team_a") > pl.col("team_b"))
          .then(pl.col("team_a")).otherwise(pl.col("team_b")).alias("tb"),
    ]).drop(["team_a", "team_b"]).rename({"ta": "team_a", "tb": "team_b"})

    # Aggregate
    h2h = (
        match_pairs.group_by(["team_a", "team_b", "format"])
        .agg([
            pl.col("match_id").count().alias("total_matches"),
            (pl.col("winner") == pl.col("team_a")).sum().alias("team_a_wins"),
            (pl.col("winner") == pl.col("team_b")).sum().alias("team_b_wins"),
            pl.col("winner").is_null().sum().alias("no_result"),
            pl.col("start_date").max().alias("last_played"),
        ])
    )

    # Last 5 results per pair as JSON
    recent_json = (
        match_pairs.sort("start_date", descending=True)
        .group_by(["team_a", "team_b", "format"])
        .agg([
            pl.struct(["start_date", "winner"]).head(5).alias("recent")
        ])
        .with_columns(
            pl.col("recent").map_elements(
                lambda x: json.dumps([{"date": r["start_date"], "winner": r["winner"]}
                                       for r in x]),
                return_dtype=pl.Utf8
            ).alias("recent_results_json")
        )
        .drop("recent")
    )

    result = h2h.join(recent_json, on=["team_a", "team_b", "format"], how="left")
    log.info("Head-to-head: %d rows", len(result))
    return result


def build_recent_form(lf: pl.LazyFrame, last_n: int = 10) -> pl.DataFrame:
    """Build recent_form table — last N matches per team."""
    log.info("Building recent form …")

    cols = lf.schema.names()
    if "match_type" in cols and "format" not in cols:
        lf = lf.rename({"match_type": "format"})

    t1 = (
        lf.filter(pl.col("innings") == 1)
        .select(["match_id", "batting_team", "format", "winner", "start_date", "venue"])
        .unique("match_id")
        .rename({"batting_team": "team"})
        .collect(streaming=True)
    )
    t2 = (
        lf.filter(pl.col("innings") == 2)
        .select(["match_id", "batting_team"])
        .unique("match_id")
        .rename({"batting_team": "opponent"})
        .collect(streaming=True)
    )

    forms_t1 = t1.join(t2, on="match_id", how="left").with_columns([
        pl.when(pl.col("winner") == pl.col("team")).then(pl.lit("won"))
          .when(pl.col("winner").is_null()).then(pl.lit("no result"))
          .otherwise(pl.lit("lost")).alias("result"),
        pl.col("start_date").alias("date"),
    ])    # Do the same for team2 — note t1 has already been renamed: batting_team → team
    forms_t2 = t2.join(t1.select(["match_id", "team", "format",
                                   "winner", "start_date", "venue"])
                         .rename({"team": "opponent_t1"}),
                        on="match_id", how="left").rename(
        {"opponent": "team", "opponent_t1": "opponent"}
    ).with_columns([
        pl.when(pl.col("winner") == pl.col("team")).then(pl.lit("won"))
          .when(pl.col("winner").is_null()).then(pl.lit("no result"))
          .otherwise(pl.lit("lost")).alias("result"),
        pl.col("start_date").alias("date"),
    ])

    combined = pl.concat([forms_t1, forms_t2], how="diagonal")

    # Keep last N per team
    recent = (
        combined.sort("date", descending=True)
        .group_by("team")
        .head(last_n)
        .select(["team", "match_id", "date", "format", "opponent", "venue", "result"])
    )
    log.info("Recent form: %d rows", len(recent))
    return recent


def build_match_summaries(lf: pl.LazyFrame) -> pl.DataFrame:
    """Generate one text summary per match for pgvector embedding."""
    log.info("Building match summaries …")

    cols = lf.schema.names()
    if "match_type" in cols and "format" not in cols:
        lf = lf.rename({"match_type": "format"})

    t1 = (
        lf.filter(pl.col("innings") == 1)
        .select(["match_id", "batting_team", "format", "winner",
                 "start_date", "venue", "competition"])
        .unique("match_id")
        .rename({"batting_team": "team_a"})
        .collect(streaming=True)
    )
    t2 = (
        lf.filter(pl.col("innings") == 2)
        .select(["match_id", "batting_team"])
        .unique("match_id")
        .rename({"batting_team": "team_b"})
        .collect(streaming=True)
    )

    ms = t1.join(t2, on="match_id", how="left")

    def make_summary(row: dict) -> str:
        ta = row.get("team_a") or "Team A"
        tb = row.get("team_b") or "Team B"
        winner = row.get("winner") or "No result"
        date = row.get("start_date") or ""
        venue = row.get("venue") or ""
        fmt = row.get("format") or ""
        comp = row.get("competition") or ""
        return (
            f"{ta} vs {tb} {fmt} match"
            + (f" in {comp}" if comp else "")
            + (f" at {venue}" if venue else "")
            + (f" on {date}" if date else "")
            + f". Winner: {winner}."
        )

    summaries = ms.with_columns(
        pl.struct(ms.columns).map_elements(make_summary, return_dtype=pl.Utf8).alias("summary")
    ).select(["match_id", "start_date", "format", "competition",
              "team_a", "team_b", "venue", "winner", "summary"])

    log.info("Match summaries: %d rows", len(summaries))
    return summaries


# ── Phase 2 builders ──────────────────────────────────────────────────────────

def build_venue_stats(lf: pl.LazyFrame) -> pl.DataFrame:
    """Pre-aggregate venue stats: totals, 1st/2nd-inn avg, toss/chase win %."""
    log.info("Aggregating venue stats …")
    cols = lf.schema.names()
    if "match_type" in cols and "format" not in cols:
        lf = lf.rename({"match_type": "format"})

    # Per-innings totals (runs scored in that innings)
    inns_totals = (
        lf.filter(pl.col("venue").is_not_null() & pl.col("innings").is_in([1, 2]))
        .group_by(["match_id", "venue", "format", "innings"])
        .agg(
            (pl.col("runs_off_bat").fill_null(0) + pl.col("extras").fill_null(0))
                .sum().alias("inns_runs")
        )
        .collect(streaming=True)
    )

    first = inns_totals.filter(pl.col("innings") == 1) \
        .rename({"inns_runs": "first_inns"}) \
        .drop("innings")
    second = inns_totals.filter(pl.col("innings") == 2) \
        .rename({"inns_runs": "second_inns"}) \
        .drop(["innings", "venue", "format"])

    per_match = first.join(second, on="match_id", how="left")

    # Match-level info for toss/winner
    match_meta = (
        lf.filter(pl.col("venue").is_not_null())
        .select(["match_id", "venue", "format", "winner", "toss_winner",
                 "toss_decision", "start_date", "batting_team", "innings"])
        .filter(pl.col("innings") == 2)
        .unique("match_id")
        .rename({"batting_team": "chaser"})
        .drop("innings")
        .collect(streaming=True)
    )

    combined = per_match.join(
        match_meta.select(["match_id", "winner", "toss_winner",
                           "toss_decision", "start_date", "chaser"]),
        on="match_id", how="left"
    )

    # Flags
    combined = combined.with_columns([
        (pl.col("winner") == pl.col("chaser")).alias("is_chase_win"),
        (pl.col("winner") == pl.col("toss_winner")).alias("is_toss_win"),
        pl.col("winner").is_not_null().alias("has_result"),
    ])

    agg = (
        combined.group_by(["venue", "format"])
        .agg([
            pl.col("match_id").count().alias("total_matches"),
            pl.col("first_inns").mean().round(2).alias("avg_first_innings"),
            pl.col("second_inns").mean().round(2).alias("avg_second_innings"),
            pl.col("first_inns").max().alias("highest_total"),
            pl.col("first_inns").min().alias("lowest_total"),
            (pl.col("is_toss_win").cast(pl.Float64).mean() * 100)
                .round(2).alias("toss_win_pct"),
            (pl.col("is_chase_win").cast(pl.Float64).mean() * 100)
                .round(2).alias("chase_win_pct"),
            pl.col("start_date").max().alias("last_played"),
        ])
        .with_columns(
            (100.0 - pl.col("chase_win_pct")).alias("bat_first_win_pct")
        )
    )

    log.info("Venue stats: %d rows", len(agg))
    return agg


def build_batter_vs_bowler(lf: pl.LazyFrame, min_balls: int = 6) -> pl.DataFrame:
    """Aggregate ball-by-ball into batter x bowler head-to-head per format."""
    log.info("Aggregating batter vs bowler …")
    cols = lf.schema.names()
    if "match_type" in cols and "format" not in cols:
        lf = lf.rename({"match_type": "format"})

    agg = (
        lf.filter(pl.col("batter").is_not_null() & pl.col("bowler").is_not_null())
        .group_by(["batter", "bowler", "format"])
        .agg([
            pl.col("runs_off_bat").count().alias("balls"),
            pl.col("runs_off_bat").sum().alias("runs"),
            (pl.col("runs_off_bat") == 4).sum().alias("fours"),
            (pl.col("runs_off_bat") == 6).sum().alias("sixes"),
            (pl.col("player_dismissed") == pl.col("batter")).sum().alias("dismissals"),
        ])
        .filter(pl.col("balls") >= min_balls)
        .with_columns([
            pl.when(pl.col("balls") > 0)
              .then(pl.col("runs").cast(pl.Float64) / pl.col("balls") * 100)
              .otherwise(None).round(2).alias("strike_rate"),
            pl.when(pl.col("dismissals") > 0)
              .then(pl.col("runs").cast(pl.Float64) / pl.col("dismissals"))
              .otherwise(None).round(2).alias("avg"),
        ])
        .collect(streaming=True)
    )
    log.info("Batter vs bowler: %d rows", len(agg))
    return agg


def build_player_venue_stats(lf: pl.LazyFrame) -> pl.DataFrame:
    """Aggregate player performance at each venue (batting + bowling)."""
    log.info("Aggregating player venue stats …")
    cols = lf.schema.names()
    if "match_type" in cols and "format" not in cols:
        lf = lf.rename({"match_type": "format"})

    batting = (
        lf.filter(pl.col("batter").is_not_null() & pl.col("venue").is_not_null())
        .group_by(["batter", "venue", "format"])
        .agg([
            pl.col("match_id").n_unique().alias("innings"),
            pl.col("runs_off_bat").sum().alias("runs"),
            pl.col("runs_off_bat").count().alias("balls_faced"),
            (pl.col("player_dismissed") == pl.col("batter")).sum().alias("dismissals"),
        ])
        .rename({"batter": "player"})
        .with_columns([
            pl.when(pl.col("dismissals") > 0)
              .then(pl.col("runs").cast(pl.Float64) / pl.col("dismissals"))
              .otherwise(None).round(2).alias("avg"),
            pl.when(pl.col("balls_faced") > 0)
              .then(pl.col("runs").cast(pl.Float64) / pl.col("balls_faced") * 100)
              .otherwise(None).round(2).alias("strike_rate"),
        ])
        .drop("dismissals")
        .collect(streaming=True)
    )

    bowling = (
        lf.filter(pl.col("bowler").is_not_null() & pl.col("venue").is_not_null())
        .group_by(["bowler", "venue", "format"])
        .agg([
            pl.col("wicket_type").is_not_null().sum().alias("wickets"),
            pl.col("runs_off_bat").count().alias("balls_bowled"),
            (pl.col("runs_off_bat") + pl.col("extras").fill_null(0))
                .sum().alias("runs_conceded"),
        ])
        .rename({"bowler": "player"})
        .with_columns(
            pl.when(pl.col("balls_bowled") > 0)
              .then(pl.col("runs_conceded").cast(pl.Float64) /
                    (pl.col("balls_bowled") / 6))
              .otherwise(None).round(2).alias("economy")
        )
        .collect(streaming=True)
    )

    merged = batting.join(
        bowling, on=["player", "venue", "format"], how="outer", coalesce=True
    ).fill_null(0)
    log.info("Player venue stats: %d rows", len(merged))
    return merged


def build_player_form_recent(lf: pl.LazyFrame, last_n: int = 10) -> pl.DataFrame:
    """Rolling last-N-innings form per player per format."""
    log.info("Building player form recent (last %d innings) …", last_n)
    cols = lf.schema.names()
    if "match_type" in cols and "format" not in cols:
        lf = lf.rename({"match_type": "format"})

    # Batting: one row per (player, match, format)
    bat_match = (
        lf.filter(pl.col("batter").is_not_null())
        .group_by(["batter", "match_id", "format", "start_date"])
        .agg([
            pl.col("runs_off_bat").sum().alias("m_runs"),
            pl.col("runs_off_bat").count().alias("m_balls"),
            (pl.col("player_dismissed") == pl.col("batter")).sum().alias("m_out"),
        ])
        .sort("start_date", descending=True)
        .group_by(["batter", "format"])
        .head(last_n)
        .group_by(["batter", "format"])
        .agg([
            pl.col("m_runs").count().alias("innings"),
            pl.col("m_runs").sum().alias("runs"),
            pl.col("m_balls").sum().alias("balls_faced"),
            pl.col("m_out").sum().alias("dismissals"),
            (pl.col("m_runs") >= 50).sum().alias("fifties"),
            (pl.col("m_runs") >= 100).sum().alias("hundreds"),
        ])
        .rename({"batter": "player"})
        .with_columns([
            pl.when(pl.col("dismissals") > 0)
              .then(pl.col("runs").cast(pl.Float64) / pl.col("dismissals"))
              .otherwise(None).round(2).alias("avg"),
            pl.when(pl.col("balls_faced") > 0)
              .then(pl.col("runs").cast(pl.Float64) / pl.col("balls_faced") * 100)
              .otherwise(None).round(2).alias("strike_rate"),
        ])
        .drop("dismissals")
        .collect(streaming=True)
    )

    # Bowling: last N match-level figures
    bowl_match = (
        lf.filter(pl.col("bowler").is_not_null())
        .group_by(["bowler", "match_id", "format", "start_date"])
        .agg([
            pl.col("wicket_type").is_not_null().sum().alias("m_wkts"),
            pl.col("runs_off_bat").count().alias("m_balls_bowled"),
            (pl.col("runs_off_bat") + pl.col("extras").fill_null(0))
                .sum().alias("m_runs_conceded"),
        ])
        .sort("start_date", descending=True)
        .group_by(["bowler", "format"])
        .head(last_n)
        .group_by(["bowler", "format"])
        .agg([
            pl.col("m_wkts").sum().alias("wickets"),
            pl.col("m_balls_bowled").sum().alias("tot_balls"),
            pl.col("m_runs_conceded").sum().alias("tot_runs"),
        ])
        .rename({"bowler": "player"})
        .with_columns(
            pl.when(pl.col("tot_balls") > 0)
              .then(pl.col("tot_runs").cast(pl.Float64) /
                    (pl.col("tot_balls") / 6))
              .otherwise(None).round(2).alias("economy")
        )
        .drop(["tot_balls", "tot_runs"])
        .collect(streaming=True)
    )

    merged = bat_match.join(
        bowl_match, on=["player", "format"], how="outer", coalesce=True
    ).fill_null(0).with_columns(
        pl.lit(datetime.utcnow().isoformat()).alias("updated_at"),
        pl.lit(last_n).alias("last_n"),
    )
    log.info("Player form recent: %d rows", len(merged))
    return merged


# ── Upsert helpers ────────────────────────────────────────────────────────────

async def upsert_player_stats(pool, df: pl.DataFrame) -> None:
    sql = """
        INSERT INTO player_season_stats
            (player, team, season, format,
             bat_matches, runs, balls_faced, fours, sixes, avg, strike_rate,
             bowl_matches, wickets, balls_bowled, runs_conceded,
             economy, bowling_avg, bowling_sr)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18)
        ON CONFLICT (player, team, season, format) DO UPDATE SET
            bat_matches=EXCLUDED.bat_matches, runs=EXCLUDED.runs,
            balls_faced=EXCLUDED.balls_faced, fours=EXCLUDED.fours,
            sixes=EXCLUDED.sixes, avg=EXCLUDED.avg,
            strike_rate=EXCLUDED.strike_rate,
            bowl_matches=EXCLUDED.bowl_matches, wickets=EXCLUDED.wickets,
            balls_bowled=EXCLUDED.balls_bowled,
            runs_conceded=EXCLUDED.runs_conceded, economy=EXCLUDED.economy,            bowling_avg=EXCLUDED.bowling_avg, bowling_sr=EXCLUDED.bowling_sr
    """
    rows = df.to_dicts()
    data = [
        (
            r.get("player") or "", r.get("team") or "Unknown",
            str(r.get("season") or ""), str(r.get("format") or ""),
            int(r.get("bat_matches") or 0), int(r.get("runs") or 0),
            int(r.get("balls_faced") or 0), int(r.get("fours") or 0),
            int(r.get("sixes") or 0),
            float(r["avg"]) if r.get("avg") else None,
            float(r["strike_rate"]) if r.get("strike_rate") else None,
            int(r.get("bowl_matches") or 0), int(r.get("wickets") or 0),
            int(r.get("balls_bowled") or 0), int(r.get("runs_conceded") or 0),
            float(r["economy"]) if r.get("economy") else None,
            float(r["bowling_avg"]) if r.get("bowling_avg") else None,
            float(r["bowling_sr"]) if r.get("bowling_sr") else None,
        )
        for r in rows
        if r.get("player")   # skip rows with null player
    ]
    await pool.executemany(sql, data)
    log.info("Upserted %d player stat rows", len(data))


async def upsert_head_to_head(pool, df: pl.DataFrame) -> None:
    sql = """
        INSERT INTO head_to_head_summary
            (team_a, team_b, format, team_a_wins, team_b_wins,
             no_result, total_matches, last_played, recent_results_json)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
        ON CONFLICT (team_a, team_b, format) DO UPDATE SET
            team_a_wins=EXCLUDED.team_a_wins,
            team_b_wins=EXCLUDED.team_b_wins,
            no_result=EXCLUDED.no_result,
            total_matches=EXCLUDED.total_matches,            last_played=EXCLUDED.last_played,
            recent_results_json=EXCLUDED.recent_results_json
    """
    rows = df.to_dicts()
    data = [
        (
            r.get("team_a") or "", r.get("team_b") or "", str(r.get("format") or ""),
            int(r.get("team_a_wins") or 0), int(r.get("team_b_wins") or 0),
            int(r.get("no_result") or 0), int(r.get("total_matches") or 0),
            str(r["last_played"]) if r.get("last_played") else None,
            r.get("recent_results_json"),
        )
        for r in rows
        if r.get("team_a") and r.get("team_b")
    ]
    await pool.executemany(sql, data)
    log.info("Upserted %d h2h rows", len(data))


async def upsert_recent_form(pool, df: pl.DataFrame) -> None:
    # Truncate and reload (simpler than tracking deletes)
    await pool.execute("TRUNCATE TABLE recent_form RESTART IDENTITY")
    sql = """
        INSERT INTO recent_form (team, match_id, date, format, opponent, venue, result)
        VALUES ($1,$2,$3,$4,$5,$6,$7)
    """
    rows = df.to_dicts()
    data = [
        (
            r.get("team") or "", r.get("match_id") or "",
            str(r["date"]) if r.get("date") else None,
            str(r.get("format") or ""),
            r.get("opponent") or "",
            r.get("venue"),
            r.get("result"),
        )
        for r in rows
        if r.get("team") and r.get("match_id")
    ]
    await pool.executemany(sql, data)
    log.info("Inserted %d recent form rows", len(data))


async def upsert_match_summaries(pool, df: pl.DataFrame) -> None:
    sql = """
        INSERT INTO match_summary
            (match_id, date, format, competition, team_a, team_b, venue, winner, summary)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
        ON CONFLICT (match_id) DO UPDATE SET
            summary=EXCLUDED.summary,            team_a=EXCLUDED.team_a,
            team_b=EXCLUDED.team_b,
            winner=EXCLUDED.winner
    """
    rows = df.to_dicts()
    data = [
        (
            r.get("match_id") or "",
            str(r["start_date"]) if r.get("start_date") else None,
            str(r.get("format") or ""),
            r.get("competition"),
            r.get("team_a"), r.get("team_b"),
            r.get("venue"), r.get("winner"),
            r.get("summary") or "",
        )
        for r in rows
        if r.get("match_id")
    ]
    await pool.executemany(sql, data)
    log.info("Upserted %d match summary rows", len(data))


# ── Embedding (optional — skipped if no API key) ──────────────────────────────

async def embed_match_summaries(pool) -> None:
    """
    Generate and store embeddings for match summaries.
    Uses OpenAI text-embedding-3-small (cheap) or Gemini embedding-001.
    Skipped if no API key is set.
    """
    # Reject obvious placeholder values from .env templates
    def _valid(key: str | None) -> bool:
        return bool(key) and "your_" not in key.lower() and "here" not in key.lower()

    openai_key = os.getenv("OPENAI_API_KEY") if _valid(os.getenv("OPENAI_API_KEY")) else None
    gemini_key = os.getenv("GEMINI_API_KEY") if _valid(os.getenv("GEMINI_API_KEY")) else None

    if not (openai_key or gemini_key):
        log.info("No valid embedding API key set — skipping vector embedding step")
        return

    # Fetch rows missing embeddings
    rows = await pool.fetch(
        "SELECT match_id, summary FROM match_summary WHERE embedding IS NULL LIMIT 500"
    )
    if not rows:
        log.info("All match summaries already embedded")
        return

    log.info("Embedding %d match summaries …", len(rows))

    try:
        if openai_key:
            await _embed_openai(pool, rows)
        else:
            await _embed_gemini(pool, rows)
    except Exception as exc:
        log.warning("Embedding failed (non-fatal): %s", exc)


async def _embed_openai(pool, rows: list) -> None:
    from openai import AsyncOpenAI
    client = AsyncOpenAI()
    texts = [r["summary"] for r in rows]
    response = await client.embeddings.create(
        model="text-embedding-3-small",
        input=texts,
    )
    for i, r in enumerate(rows):
        vec = response.data[i].embedding
        await pool.execute(
            "UPDATE match_summary SET embedding = $1::vector WHERE match_id = $2",
            vec, r["match_id"]
        )
    log.info("Embedded %d summaries via OpenAI", len(rows))


async def _embed_gemini(pool, rows: list) -> None:
    import google.generativeai as genai
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    for r in rows:
        result = genai.embed_content(
            model="models/embedding-001",
            content=r["summary"],
            task_type="retrieval_document",
        )
        vec = result["embedding"]
        await pool.execute(
            "UPDATE match_summary SET embedding = $1::vector WHERE match_id = $2",            vec, r["match_id"]
        )
    log.info("Embedded %d summaries via Gemini", len(rows))


# ── Phase 2 upserts ───────────────────────────────────────────────────────────

async def upsert_venue_stats(pool, df: pl.DataFrame) -> None:
    await pool.execute("TRUNCATE TABLE venue_stats_agg")
    sql = """
        INSERT INTO venue_stats_agg
            (venue, format, total_matches, avg_first_innings, avg_second_innings,
             toss_win_pct, chase_win_pct, bat_first_win_pct,
             highest_total, lowest_total, last_played)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
    """
    data = []
    for r in df.to_dicts():
        if not r.get("venue"):
            continue
        data.append((
            r["venue"], str(r.get("format") or ""),
            int(r.get("total_matches") or 0),
            float(r["avg_first_innings"]) if r.get("avg_first_innings") is not None else None,
            float(r["avg_second_innings"]) if r.get("avg_second_innings") is not None else None,
            float(r["toss_win_pct"]) if r.get("toss_win_pct") is not None else None,
            float(r["chase_win_pct"]) if r.get("chase_win_pct") is not None else None,
            float(r["bat_first_win_pct"]) if r.get("bat_first_win_pct") is not None else None,
            int(r["highest_total"]) if r.get("highest_total") is not None else None,
            int(r["lowest_total"]) if r.get("lowest_total") is not None else None,
            str(r["last_played"]) if r.get("last_played") else None,
        ))
    await pool.executemany(sql, data)
    log.info("Upserted %d venue_stats_agg rows", len(data))


async def upsert_batter_vs_bowler(pool, df: pl.DataFrame) -> None:
    await pool.execute("TRUNCATE TABLE batter_vs_bowler")
    sql = """
        INSERT INTO batter_vs_bowler
            (batter, bowler, format, balls, runs, dismissals,
             fours, sixes, strike_rate, avg)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
    """
    data = []
    for r in df.to_dicts():
        if not r.get("batter") or not r.get("bowler"):
            continue
        data.append((
            r["batter"], r["bowler"], str(r.get("format") or ""),
            int(r.get("balls") or 0), int(r.get("runs") or 0),
            int(r.get("dismissals") or 0),
            int(r.get("fours") or 0), int(r.get("sixes") or 0),
            float(r["strike_rate"]) if r.get("strike_rate") is not None else None,
            float(r["avg"]) if r.get("avg") is not None else None,
        ))
    # Batch — batter_vs_bowler can be huge, so chunk
    BATCH = 5000
    for i in range(0, len(data), BATCH):
        await pool.executemany(sql, data[i:i+BATCH])
    log.info("Upserted %d batter_vs_bowler rows", len(data))


async def upsert_player_venue_stats(pool, df: pl.DataFrame) -> None:
    await pool.execute("TRUNCATE TABLE player_venue_stats")
    sql = """
        INSERT INTO player_venue_stats
            (player, venue, format, innings, runs, balls_faced, avg, strike_rate,
             wickets, balls_bowled, runs_conceded, economy)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
    """
    data = []
    for r in df.to_dicts():
        if not r.get("player") or not r.get("venue"):
            continue
        data.append((
            r["player"], r["venue"], str(r.get("format") or ""),
            int(r.get("innings") or 0), int(r.get("runs") or 0),
            int(r.get("balls_faced") or 0),
            float(r["avg"]) if r.get("avg") else None,
            float(r["strike_rate"]) if r.get("strike_rate") else None,
            int(r.get("wickets") or 0), int(r.get("balls_bowled") or 0),
            int(r.get("runs_conceded") or 0),
            float(r["economy"]) if r.get("economy") else None,
        ))
    BATCH = 5000
    for i in range(0, len(data), BATCH):
        await pool.executemany(sql, data[i:i+BATCH])
    log.info("Upserted %d player_venue_stats rows", len(data))


async def upsert_player_form_recent(pool, df: pl.DataFrame) -> None:
    await pool.execute("TRUNCATE TABLE player_form_recent")
    sql = """
        INSERT INTO player_form_recent
            (player, format, last_n, innings, runs, balls_faced,
             avg, strike_rate, fifties, hundreds, wickets, economy, updated_at)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
    """
    data = []
    for r in df.to_dicts():
        if not r.get("player"):
            continue
        data.append((
            r["player"], str(r.get("format") or ""),
            int(r.get("last_n") or 10),
            int(r.get("innings") or 0), int(r.get("runs") or 0),
            int(r.get("balls_faced") or 0),
            float(r["avg"]) if r.get("avg") else None,
            float(r["strike_rate"]) if r.get("strike_rate") else None,
            int(r.get("fifties") or 0), int(r.get("hundreds") or 0),
            int(r.get("wickets") or 0),
            float(r["economy"]) if r.get("economy") else None,
            str(r.get("updated_at") or datetime.utcnow().isoformat()),
        ))
    await pool.executemany(sql, data)
    log.info("Upserted %d player_form_recent rows", len(data))


# ── Main ──────────────────────────────────────────────────────────────────────

async def run_ingest() -> None:
    if not DATABASE_URL:
        log.error("DATABASE_URL not set — cannot ingest")
        sys.exit(1)

    import asyncpg
    url = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    pool = await asyncpg.create_pool(url, min_size=1, max_size=3,
                                      statement_cache_size=0)

    lf = load_parquet()

    player_df   = build_player_season_stats(lf)
    h2h_df      = build_head_to_head(lf)
    form_df     = build_recent_form(lf)
    summary_df  = build_match_summaries(lf)

    await upsert_player_stats(pool, player_df)
    await upsert_head_to_head(pool, h2h_df)
    await upsert_recent_form(pool, form_df)
    await upsert_match_summaries(pool, summary_df)
    await embed_match_summaries(pool)

    # ── Phase 2 ──────────────────────────────────────────────────────────
    try:
        venue_df        = build_venue_stats(lf)
        bvb_df          = build_batter_vs_bowler(lf)
        player_venue_df = build_player_venue_stats(lf)
        form_recent_df  = build_player_form_recent(lf)

        await upsert_venue_stats(pool, venue_df)
        await upsert_batter_vs_bowler(pool, bvb_df)
        await upsert_player_venue_stats(pool, player_venue_df)
        await upsert_player_form_recent(pool, form_recent_df)
    except Exception as exc:
        log.warning("Phase 2 aggregation failed (non-fatal): %s", exc)

    await pool.close()
    log.info("✅ Ingest complete — %s", datetime.utcnow().isoformat())


if __name__ == "__main__":
    asyncio.run(run_ingest())
