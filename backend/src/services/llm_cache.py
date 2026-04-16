"""
Centralised response cache for the Ask pipeline.

Used at the *router* level (before any LLM / LangGraph call) so identical
questions never cost a single token twice within the TTL window.

The existing per-function cache inside llm_client.py is kept for backward
compat but this module is the primary cost-saver.
"""
import hashlib
import re
import time
import copy
import logging
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
CACHE_TTL = 1800        # 30 min — short enough for current-season freshness
CACHE_MAX_ENTRIES = 50   # evict oldest when full (low for 512 MB containers)

# ── Storage ───────────────────────────────────────────────────────────────────
_store: Dict[str, Dict[str, Any]] = {}

# ── Player name normalization ─────────────────────────────────────────────────
# Common aliases → canonical. This dramatically increases cache hit rate:
# "Kohli batting stats", "virat kohli batting stats", "V Kohli batting stats"
# all map to the same key.
_PLAYER_NORMALIZE: dict[str, str] = {
    "kohli": "virat kohli", "vk": "virat kohli", "v kohli": "virat kohli", "king kohli": "virat kohli",
    "rohit": "rohit sharma", "hitman": "rohit sharma", "ro": "rohit sharma",
    "bumrah": "jasprit bumrah", "boom": "jasprit bumrah", "jb": "jasprit bumrah",
    "dhoni": "ms dhoni", "msd": "ms dhoni", "thala": "ms dhoni",
    "babar": "babar azam", "williamson": "kane williamson",
    "smith": "steve smith", "warner": "david warner",
    "root": "joe root", "stokes": "ben stokes",
    "gill": "shubman gill", "pant": "rishabh pant",
    "jadeja": "ravindra jadeja", "ashwin": "r ashwin", "siraj": "mohammed siraj",
    "rashid": "rashid khan",
}


def _normalize_query(prompt: str) -> str:
    """Normalize query for higher cache hit rate.

    - lowercase + collapse whitespace
    - strip punctuation (? . , !)
    - normalize common player name aliases
    """
    q = prompt.strip().lower()
    q = re.sub(r"[?.!,;:'\"-]+", " ", q)   # strip punctuation
    q = re.sub(r"\s+", " ", q).strip()       # collapse whitespace

    # Replace known aliases with canonical names.
    # Process longer aliases first (e.g. "king kohli" before "kohli").
    # Skip if the canonical name is already present (avoid double-replacement).
    for alias, canonical in sorted(_PLAYER_NORMALIZE.items(), key=lambda x: -len(x[0])):
        if canonical in q:
            continue  # canonical already present — don't double-replace
        q = re.sub(r"\b" + re.escape(alias) + r"\b", canonical, q)

    return q


def _make_key(prompt: str, grounded: bool, fmt: str = "") -> str:
    """Deterministic cache key from the user-visible inputs."""
    normalized = _normalize_query(prompt)
    raw = f"{normalized}|g={grounded}|f={fmt}"
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
