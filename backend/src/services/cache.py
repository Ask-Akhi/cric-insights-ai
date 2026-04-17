"""
Unified cache service — Upstash Redis (HTTP) with in-process dict fallback.

Upstash Redis is used when UPSTASH_REDIS_REST_URL + UPSTASH_REDIS_REST_TOKEN
are set. It is HTTP-based (no persistent TCP connection), runs perfectly on
Render Starter, and survives server restarts.

Falls back to the existing in-process OrderedDict (llm_cache.py) when the
env vars are not set — zero breaking changes.

Usage:
    from backend.src.services.cache import cache

    await cache.get(key)
    await cache.set(key, value, ttl=3600)
    await cache.delete(key)
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from collections import OrderedDict
from typing import Any, Optional

import httpx

log = logging.getLogger(__name__)

_UPSTASH_URL   = os.getenv("UPSTASH_REDIS_REST_URL", "")
_UPSTASH_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")
_USE_REDIS     = bool(_UPSTASH_URL and _UPSTASH_TOKEN)

# Fallback in-process cache (same LRU logic as legacy llm_cache.py)
_LOCAL_STORE: OrderedDict[str, tuple[Any, float]] = OrderedDict()
_LOCAL_MAX    = int(os.getenv("LOCAL_CACHE_MAX", "100"))

DEFAULT_TTL   = int(os.getenv("CACHE_TTL_SECONDS", "3600"))   # 1 hour


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:40]


class _UpstashCache:
    """HTTP-based Redis client for Upstash REST API."""

    def __init__(self):
        self._headers = {"Authorization": f"Bearer {_UPSTASH_TOKEN}"}

    async def get(self, key: str) -> Optional[Any]:
        hk = _hash(key)
        try:
            async with httpx.AsyncClient(timeout=3) as c:
                r = await c.get(f"{_UPSTASH_URL}/get/{hk}", headers=self._headers)
            val = r.json().get("result")
            if val is None:
                return None
            return json.loads(val)
        except Exception as exc:
            log.debug("Redis GET failed (%s) — cache miss", exc)
            return None

    async def set(self, key: str, value: Any, ttl: int = DEFAULT_TTL) -> None:
        hk = _hash(key)
        encoded = json.dumps(value)
        try:
            async with httpx.AsyncClient(timeout=3) as c:
                await c.get(
                    f"{_UPSTASH_URL}/set/{hk}/{httpx.URL(encoded)}",
                    params={"ex": str(ttl)},
                    headers=self._headers,
                )
        except Exception as exc:
            log.debug("Redis SET failed (%s)", exc)

    async def delete(self, key: str) -> None:
        hk = _hash(key)
        try:
            async with httpx.AsyncClient(timeout=3) as c:
                await c.get(f"{_UPSTASH_URL}/del/{hk}", headers=self._headers)
        except Exception as exc:
            log.debug("Redis DEL failed (%s)", exc)


class _LocalCache:
    """In-process LRU cache — fallback when Upstash is not configured."""

    async def get(self, key: str) -> Optional[Any]:
        entry = _LOCAL_STORE.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if time.monotonic() > expires_at:
            _LOCAL_STORE.pop(key, None)
            return None
        _LOCAL_STORE.move_to_end(key)
        return value

    async def set(self, key: str, value: Any, ttl: int = DEFAULT_TTL) -> None:
        if key in _LOCAL_STORE:
            _LOCAL_STORE.move_to_end(key)
        _LOCAL_STORE[key] = (value, time.monotonic() + ttl)
        while len(_LOCAL_STORE) > _LOCAL_MAX:
            _LOCAL_STORE.popitem(last=False)

    async def delete(self, key: str) -> None:
        _LOCAL_STORE.pop(key, None)


# ── Exported singleton ────────────────────────────────────────────────────────
cache: _UpstashCache | _LocalCache = _UpstashCache() if _USE_REDIS else _LocalCache()

if _USE_REDIS:
    log.info("Cache: Upstash Redis (%s)", _UPSTASH_URL[:40])
else:
    log.info("Cache: in-process LRU (set UPSTASH_REDIS_REST_URL to enable Redis)")
