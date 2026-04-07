# filepath: backend/src/services/llm_cache.py
"""
Centralised response cache for the Ask pipeline.

Used at the *router* level (before any LLM / LangGraph call) so identical
questions never cost a single token twice within the TTL window.

The existing per-function cache inside llm_client.py is kept for backward
compat but this module is the primary cost-saver.
"""
import hashlib
import time
import copy
import logging
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
CACHE_TTL = 1800        # 30 min — short enough for current-season freshness
CACHE_MAX_ENTRIES = 200  # evict oldest when full

# ── Storage ───────────────────────────────────────────────────────────────────
_store: Dict[str, Dict[str, Any]] = {}


def _make_key(prompt: str, grounded: bool, fmt: str = "") -> str:
    """Deterministic cache key from the user-visible inputs."""
    raw = f"{prompt.strip().lower()}|g={grounded}|f={fmt}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def get(prompt: str, grounded: bool, fmt: str = "") -> Optional[Dict[str, Any]]:
    """Return cached AskResponse dict or None."""
    key = _make_key(prompt, grounded, fmt)
    entry = _store.get(key)
    if entry is None:
        return None
    if time.time() - entry["ts"] > CACHE_TTL:
        _store.pop(key, None)
        return None
    log.info("ask-cache HIT key=%s prompt='%.50s'", key, prompt)
    return copy.deepcopy(entry["payload"])  # deep copy — caller mutates answer & lists


def put(prompt: str, grounded: bool, fmt: str, payload: Dict[str, Any]) -> None:
    """Store an AskResponse dict in cache."""
    if len(_store) >= CACHE_MAX_ENTRIES:
        oldest_key = min(_store, key=lambda k: _store[k]["ts"])
        _store.pop(oldest_key, None)
    key = _make_key(prompt, grounded, fmt)
    _store[key] = {"payload": payload, "ts": time.time()}
    log.info("ask-cache PUT key=%s prompt='%.50s'", key, prompt)


def invalidate_all() -> int:
    """Flush the entire cache. Returns number of evicted entries."""
    n = len(_store)
    _store.clear()
    return n


def stats() -> Dict[str, Any]:
    """Return cache diagnostics."""
    now = time.time()
    alive = sum(1 for e in _store.values() if now - e["ts"] <= CACHE_TTL)
    return {
        "entries": len(_store),
        "alive": alive,
        "expired": len(_store) - alive,
        "max_entries": CACHE_MAX_ENTRIES,
        "ttl_seconds": CACHE_TTL,
    }
