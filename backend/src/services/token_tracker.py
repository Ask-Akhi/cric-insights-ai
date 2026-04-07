"""
Lightweight daily token-usage tracker with cost estimation.

Stores in-memory (resets on deploy / restart) — good enough for monitoring
without needing a DB.  Call `record()` after every LLM response and
`get_usage()` from the /api/token-usage endpoint.
"""
import time
import logging
from collections import defaultdict
from datetime import date, datetime
from typing import Any, Dict

log = logging.getLogger(__name__)

# ── Approximate pricing (USD per 1M tokens, Gemini 2.x Flash family) ─────────
# Source: https://ai.google.dev/pricing  (as of 2026-Q1)
_COST_PER_1M = {
    "gemini-2.5-flash":        {"input": 0.15, "output": 0.60},
    "gemini-2.0-flash":        {"input": 0.10, "output": 0.40},
    "gemini-2.0-flash-001":    {"input": 0.10, "output": 0.40},
    "gemini-2.0-flash-lite":   {"input": 0.075, "output": 0.30},
    "gemini-2.0-flash-lite-001": {"input": 0.075, "output": 0.30},
    "_default":                {"input": 0.15, "output": 0.60},
}

# ── Storage (keyed by date string YYYY-MM-DD) ────────────────────────────────
_daily: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
    "requests": 0,
    "cache_hits": 0,
    "input_tokens_est": 0,
    "output_tokens_est": 0,
    "cost_usd_est": 0.0,
    "by_model": defaultdict(lambda: {"requests": 0, "input_tokens": 0, "output_tokens": 0}),
    "by_intent": defaultdict(int),
    "errors": 0,
})

_boot_time = time.time()


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English text."""
    return max(1, len(text) // 4)


def record(
    *,
    model: str = "gemini-2.5-flash",
    prompt: str = "",
    response: str = "",
    intent: str = "general",
    cached: bool = False,
    error: bool = False,
    grounded: bool = False,
) -> None:
    """Record a single LLM interaction."""
    today = date.today().isoformat()
    d = _daily[today]

    d["requests"] += 1
    if cached:
        d["cache_hits"] += 1
        return  # no tokens spent
    if error:
        d["errors"] += 1

    in_tok = _estimate_tokens(prompt)
    out_tok = _estimate_tokens(response)

    d["input_tokens_est"] += in_tok
    d["output_tokens_est"] += out_tok

    pricing = _COST_PER_1M.get(model, _COST_PER_1M["_default"])
    cost = (in_tok * pricing["input"] + out_tok * pricing["output"]) / 1_000_000
    d["cost_usd_est"] += cost

    m = d["by_model"][model]
    m["requests"] += 1
    m["input_tokens"] += in_tok
    m["output_tokens"] += out_tok

    d["by_intent"][intent] += 1


def get_usage(day: str | None = None) -> Dict[str, Any]:
    """Return usage stats for a given day (default: today)."""
    day = day or date.today().isoformat()
    d = _daily.get(day)
    if not d:
        return {"day": day, "requests": 0, "message": "No data for this day."}
    return {
        "day": day,
        "requests": d["requests"],
        "cache_hits": d["cache_hits"],
        "cache_hit_rate": f"{d['cache_hits'] / max(d['requests'], 1) * 100:.1f}%",
        "input_tokens_est": d["input_tokens_est"],
        "output_tokens_est": d["output_tokens_est"],
        "total_tokens_est": d["input_tokens_est"] + d["output_tokens_est"],
        "cost_usd_est": round(d["cost_usd_est"], 6),
        "errors": d["errors"],
        "by_model": dict(d["by_model"]),
        "by_intent": dict(d["by_intent"]),
        "uptime_hours": round((time.time() - _boot_time) / 3600, 2),
    }


def get_all_days() -> Dict[str, Any]:
    """Return a summary across all tracked days."""
    total_requests = sum(d["requests"] for d in _daily.values())
    total_cost = sum(d["cost_usd_est"] for d in _daily.values())
    total_cache_hits = sum(d["cache_hits"] for d in _daily.values())
    return {
        "days_tracked": len(_daily),
        "total_requests": total_requests,
        "total_cache_hits": total_cache_hits,
        "total_cost_usd_est": round(total_cost, 6),
        "uptime_hours": round((time.time() - _boot_time) / 3600, 2),
        "daily": {day: get_usage(day) for day in sorted(_daily.keys())},
    }
