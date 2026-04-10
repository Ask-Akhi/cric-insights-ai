"""
Circuit breaker for Gemini API quota.

When quota exhaustion is detected anywhere (orchestrator, llm_client, search_server),
the breaker opens and subsequent requests skip Gemini entirely, returning local-only
answers. The breaker auto-resets after a cooldown period.

This is the #1 fix for "daily usage limit" errors cascading across the app:
instead of every request hitting the API and burning through retries, we fail
instantly and serve whatever local data (Cricsheet) is available.

Usage:
    from backend.src.services.circuit_breaker import gemini_breaker
    if gemini_breaker.is_open:
        return local_only_answer()
    try:
        answer = call_gemini(...)
    except QuotaError:
        gemini_breaker.trip()
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

log = logging.getLogger("services.circuit_breaker")


@dataclass
class CircuitBreaker:
    """Simple time-based circuit breaker for API quota protection."""

    name: str = "gemini"
    cooldown_s: float = 300.0  # 5 min — re-probe after this
    _tripped_at: float = 0.0
    _trip_count: int = 0

    # ── Observability counters (reset on deploy) ──────────────
    total_trips: int = 0
    total_skipped: int = 0  # requests that saw open breaker and skipped Gemini

    @property
    def is_open(self) -> bool:
        """True when Gemini should NOT be called."""
        if self._tripped_at == 0:
            return False
        if time.monotonic() - self._tripped_at > self.cooldown_s:
            # Cooldown expired — close the breaker, allow a probe
            self._tripped_at = 0
            log.info("Circuit breaker [%s] closed — cooldown expired, allowing probe", self.name)
            return False
        return True

    def trip(self, reason: str = "") -> None:
        """Open the breaker — stop all Gemini calls."""
        self._tripped_at = time.monotonic()
        self._trip_count += 1
        self.total_trips += 1
        log.warning(
            "Circuit breaker [%s] TRIPPED (#%d) — Gemini calls blocked for %.0fs. Reason: %s",
            self.name, self._trip_count, self.cooldown_s, reason or "quota exhausted",
        )

    def record_skip(self) -> None:
        """Record that a request was served without Gemini because breaker is open."""
        self.total_skipped += 1

    def status(self) -> dict:
        """Return breaker state for /api/health or admin endpoints."""
        return {
            "name": self.name,
            "is_open": self.is_open,
            "total_trips": self.total_trips,
            "total_skipped": self.total_skipped,
            "cooldown_s": self.cooldown_s,
            "seconds_until_close": max(
                0, self.cooldown_s - (time.monotonic() - self._tripped_at)
            ) if self._tripped_at else 0,
        }


# ── Singleton ─────────────────────────────────────────────────────────────────
gemini_breaker = CircuitBreaker(name="gemini", cooldown_s=300.0)
