"""
Single source of truth for all configuration.
Every tunable lives here. Override via environment variables or .env file.

Usage:
    from backend.src.core.config import settings
    timeout = settings.tier1_timeout_s
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "../../.env"))


@dataclass(frozen=True)
class Settings:
    """App-wide settings. Reads from env vars with sensible defaults."""

    # ── LLM ────────────────────────────────────────────────
    llm_provider: str = field(
        default_factory=lambda: os.getenv("LLM_PROVIDER", "gemini")
    )
    llm_model: str = field(
        default_factory=lambda: os.getenv("LLM_MODEL", "gemini-2.0-flash")
    )
    gemini_api_key: str = field(
        default_factory=lambda: os.getenv("GEMINI_API_KEY", "")
    )
    openai_api_key: str = field(
        default_factory=lambda: os.getenv("OPENAI_API_KEY", "")
    )    # ── Timeouts (seconds) ─────────────────────────────────
    render_wall_s: int = 60          # Render/container hard-kill wall time
    railway_wall_s: int = 60         # kept for backward-compat aliases
    tier1_timeout_s: int = 44
    tier2_budget_s: int = 44
    non_grounded_timeout_s: int = 52
    frontend_timeout_s: int = 58    # ── Cache ──────────────────────────────────────────────
    ask_cache_ttl_s: int = 1800
    ask_cache_max: int = 50          # reduced from 200 — each entry holds a full response dict
    rag_cache_ttl_s: int = 600
    llm_cache_ttl_s: int = 1800
    llm_cache_max: int = 50          # reduced from 200 — keeps peak in-process RAM bounded
    live_cache_ttl_s: int = 30       # live score context — short TTL

    # ── Token limits ───────────────────────────────────────
    max_tokens_simple: int = 1024
    max_tokens_medium: int = 2048
    max_tokens_complex: int = 4096
    max_tokens_grounded: int = 4096
    max_tokens_default: int = 8192
    max_prompt_chars: int = 12000
    max_prompt_chars_grounded: int = 6000

    # ── MCP ────────────────────────────────────────────────
    mcp_enabled: bool = field(
        default_factory=lambda: os.getenv("MCP_ENABLED", "true").lower() == "true"
    )
    mcp_tool_timeout_s: int = 10
    mcp_max_context_tokens: int = 6000
    mcp_llm_fallback_min_words: int = 4  # min words before LLM tool-picker fires    # ── Admin ──────────────────────────────────────────────
    admin_key: str = field(
        default_factory=lambda: os.getenv("ADMIN_KEY", "")
    )

    # ── Data ───────────────────────────────────────────────
    cricsheet_data_dir: str = field(
        default_factory=lambda: os.getenv("CRICSHEET_DATA_DIR", "./data/cricsheet")
    )
    cricsheet_refresh_hours: float = field(
        default_factory=lambda: float(os.getenv("CRICSHEET_REFRESH_HOURS", "6"))
    )


settings = Settings()

# ── Shared format expansion lists ─────────────────────────────────────────────
# Cricsheet stores T20 franchise leagues under their league name (IPL, BBL, etc.)
# rather than "T20". Any code that filters by "T20" must include these.
T20_FORMATS: list[str] = [
    "T20", "T20I", "IT20",  # international / generic
    "IPL", "BBL", "CPL", "PSL", "BPL", "LPL",  # franchise leagues
    "MLC", "SA20", "ILT20", "WPL",  # newer leagues
]

# Major T20 formats only — used for ranking queries to exclude Associate-level
# T20s ("T20" format code) where unrepresentative stats (e.g. 3.2 economy)
# come from bowling against weak Associate batting line-ups.
# "IT20" = Full-member T20 internationals; "T20" = Associate T20Is (excluded).
MAJOR_T20_FORMATS: list[str] = [
    "IT20",  # full-member T20Is (India, Australia, England, Pakistan, etc.)
    "IPL", "BBL", "CPL", "PSL", "LPL",  # elite franchise leagues
    "MLC", "SA20", "ILT20", "WPL",      # newer top-tier leagues
    # Note: BPL excluded — quality mixed; "T20" (Associate) deliberately excluded
]

FORMAT_EXPANSION: dict[str, list[str]] = {
    "T20":  T20_FORMATS,
    "ODI":  ["ODI", "ODI Women"],
    "Test": ["Test", "Test Women"],
}

# ── Team name aliases ─────────────────────────────────────────────────────────
# Cricsheet data uses historical team names; franchises rename over time.
# Maps a canonical name → all variants that appear in the data.
TEAM_NAME_VARIANTS: dict[str, list[str]] = {
    "Royal Challengers Bengaluru": ["Royal Challengers Bengaluru", "Royal Challengers Bangalore"],
    "Royal Challengers Bangalore": ["Royal Challengers Bengaluru", "Royal Challengers Bangalore"],
    "Delhi Capitals": ["Delhi Capitals", "Delhi Daredevils"],
    "Delhi Daredevils": ["Delhi Capitals", "Delhi Daredevils"],
    "Punjab Kings": ["Punjab Kings", "Kings XI Punjab"],
    "Kings XI Punjab": ["Punjab Kings", "Kings XI Punjab"],
    "Rising Pune Supergiant": ["Rising Pune Supergiant", "Rising Pune Supergiants"],
    "Rising Pune Supergiants": ["Rising Pune Supergiant", "Rising Pune Supergiants"],
}


def expand_team_names(team: str) -> list[str]:
    """Return all Cricsheet variants for a team name, or [team] if no aliases."""
    return TEAM_NAME_VARIANTS.get(team, [team])
