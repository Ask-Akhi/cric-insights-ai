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
        default_factory=lambda: os.getenv("LLM_MODEL", "gemini-2.5-flash")
    )
    gemini_api_key: str = field(
        default_factory=lambda: os.getenv("GEMINI_API_KEY", "")
    )
    openai_api_key: str = field(
        default_factory=lambda: os.getenv("OPENAI_API_KEY", "")
    )

    # ── Timeouts (seconds) ─────────────────────────────────
    railway_wall_s: int = 60
    tier1_timeout_s: int = 44
    tier2_budget_s: int = 44
    non_grounded_timeout_s: int = 52
    frontend_timeout_s: int = 58

    # ── Cache ──────────────────────────────────────────────
    ask_cache_ttl_s: int = 1800
    ask_cache_max: int = 200
    rag_cache_ttl_s: int = 600
    llm_cache_ttl_s: int = 1800
    llm_cache_max: int = 100
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
    mcp_llm_fallback_min_words: int = 4  # min words before LLM tool-picker fires

    # ── Admin ──────────────────────────────────────────────
    admin_key: str = field(
        default_factory=lambda: os.getenv("ADMIN_KEY", "")
    )

    # ── Data ───────────────────────────────────────────────
    cricsheet_data_dir: str = field(
        default_factory=lambda: os.getenv("CRICSHEET_DATA_DIR", "./data/cricsheet")
    )


settings = Settings()
