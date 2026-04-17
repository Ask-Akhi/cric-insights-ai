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
            "UPDATE match_summary SET embedding = $1::vector WHERE match_id = $2",
            vec, r["match_id"]
        )
    log.info("Embedded %d summaries via Gemini", len(rows))


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

    await pool.close()
    log.info("✅ Ingest complete — %s", datetime.utcnow().isoformat())


if __name__ == "__main__":
    asyncio.run(run_ingest())
