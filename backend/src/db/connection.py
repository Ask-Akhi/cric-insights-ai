"""
asyncpg connection pool — one pool per process, lazy-initialised.

Uses DATABASE_URL env var (Supabase / Neon / any Postgres).
Falls back gracefully when the DB is not configured — every caller
should check `is_db_available()` first.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

log = logging.getLogger(__name__)

_pool = None
_db_available: Optional[bool] = None   # None = untested, True/False = result


async def get_pool():
    """
    Return the asyncpg connection pool.
    Creates it on first call. Returns None if DATABASE_URL is not set
    or the connection fails — callers must handle None gracefully.
    """
    global _pool, _db_available

    if _db_available is False:
        return None          # already failed — don't retry every request
    if _pool is not None:
        return _pool

    url = os.getenv("DATABASE_URL", "")
    if not url:
        if _db_available is None:
            log.info("DATABASE_URL not set — running without PostgreSQL (Polars mode)")
        _db_available = False
        return None

    try:
        import asyncpg  # lazy import — not installed in pure-Polars mode

        # asyncpg doesn't accept the postgres+asyncpg:// scheme
        url = url.replace("postgresql+asyncpg://", "postgresql://")

        _pool = await asyncpg.create_pool(
            url,
            min_size=1,
            max_size=5,         # keep low for Render Starter 512 MB
            command_timeout=15, # per-query timeout
            statement_cache_size=0,  # required by Supabase PgBouncer
        )
        _db_available = True
        log.info("✅ PostgreSQL pool created (min=1 max=5)")
        return _pool

    except Exception as exc:
        log.warning("PostgreSQL unavailable — falling back to Polars: %s", exc)
        _db_available = False
        return None


async def close_pool() -> None:
    """Gracefully close the pool on app shutdown."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        log.info("PostgreSQL pool closed")


def is_db_available() -> bool:
    """
    Synchronous check — True only after a successful get_pool() call.
    Use this in health endpoints and fallback guards.
    """
    return _db_available is True
