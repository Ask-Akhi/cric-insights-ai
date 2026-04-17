"""
SQLModel table definitions — single source of truth for schema.
Used by ingest_cricsheet.py for migrations and by db/queries.py for type hints.

Runtime queries use asyncpg directly (faster than SQLModel session for
read-heavy workloads). SQLModel is used only for schema + Pydantic models.
"""
from __future__ import annotations

from typing import Optional
from sqlmodel import SQLModel, Field


class PlayerSeasonStats(SQLModel, table=True):
    """Pre-aggregated batting + bowling stats per player per team per season."""
    __tablename__ = "player_season_stats"

    player: str = Field(primary_key=True, max_length=120)
    team: str = Field(primary_key=True, max_length=80)
    season: str = Field(primary_key=True, max_length=20)
    format: str = Field(primary_key=True, max_length=20)

    # Batting
    bat_matches: int = 0
    runs: int = 0
    balls_faced: int = 0
    fours: int = 0
    sixes: int = 0
    avg: Optional[float] = None
    strike_rate: Optional[float] = None

    # Bowling
    bowl_matches: int = 0
    wickets: int = 0
    balls_bowled: int = 0
    runs_conceded: int = 0
    economy: Optional[float] = None
    bowling_avg: Optional[float] = None
    bowling_sr: Optional[float] = None


class HeadToHeadSummary(SQLModel, table=True):
    """Pre-aggregated win/loss history between two teams."""
    __tablename__ = "head_to_head_summary"

    team_a: str = Field(primary_key=True, max_length=80)
    team_b: str = Field(primary_key=True, max_length=80)
    format: str = Field(primary_key=True, max_length=20)

    team_a_wins: int = 0
    team_b_wins: int = 0
    no_result: int = 0
    total_matches: int = 0
    last_played: Optional[str] = None   # ISO date string

    # Last 5 match results as JSON string: "[{winner, date, venue, margin}, ...]"
    recent_results_json: Optional[str] = None


class MatchSummary(SQLModel, table=True):
    """One-row-per-match human-readable summary for pgvector semantic search."""
    __tablename__ = "match_summary"

    match_id: str = Field(primary_key=True, max_length=60)
    date: Optional[str] = None
    format: Optional[str] = None
    competition: Optional[str] = None
    team_a: Optional[str] = None
    team_b: Optional[str] = None
    venue: Optional[str] = None
    winner: Optional[str] = None
    margin: Optional[str] = None
    summary: str = ""           # text description for embedding
    # embedding column is managed raw by asyncpg / pgvector — not in SQLModel
    # to avoid the vector type dependency at schema-definition time


class RecentForm(SQLModel, table=True):
    """Last N matches per team — refreshed nightly."""
    __tablename__ = "recent_form"

    id: Optional[int] = Field(default=None, primary_key=True)
    team: str = Field(index=True, max_length=80)
    match_id: str = Field(max_length=60)
    date: Optional[str] = None
    format: Optional[str] = None
    opponent: str = Field(default="", max_length=80)
    venue: Optional[str] = None
    result: Optional[str] = None    # "won" | "lost" | "no result"
    margin: Optional[str] = None
