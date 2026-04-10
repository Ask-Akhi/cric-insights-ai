"""
Periodic Cricsheet data refresh scheduler.

Runs a background asyncio task that re-downloads Cricsheet data every
CRICSHEET_REFRESH_HOURS (default: 6).  After a successful refresh the
singleton CricsheetProvider is hot-reloaded so new queries immediately
see fresh data — no restart required.

The scheduler is:
  • Non-blocking — runs in a daemon thread via the existing _run_refresh()
  • Idempotent — skips if a refresh is already running
  • Graceful — cancelled cleanly on app shutdown via lifespan
  • Observable — exposes schedule_status() for health/admin endpoints

Configure via environment variables:
  CRICSHEET_REFRESH_HOURS  — interval between refreshes (default 6, 0 = disabled)
  ADMIN_KEY                — required by the refresh logic (already in env)
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Optional

log = logging.getLogger("cricsheet.scheduler")

# ── State ─────────────────────────────────────────────────────────────────────
_task: Optional[asyncio.Task] = None
_schedule_state: dict = {
    "enabled": False,
    "interval_hours": 0,
    "last_run_at": None,
    "next_run_at": None,
    "runs_completed": 0,
    "last_success": None,
}


def _refresh_interval_s() -> float:
    """Return refresh interval in seconds from env, or 0 if disabled."""
    try:
        hours = float(os.environ.get("CRICSHEET_REFRESH_HOURS", "6"))
    except (ValueError, TypeError):
        hours = 6.0
    return max(0, hours * 3600)


async def _scheduler_loop() -> None:
    """Main loop — sleeps for the configured interval, then triggers refresh."""
    interval = _refresh_interval_s()
    if interval <= 0:
        log.info("Cricsheet auto-refresh disabled (CRICSHEET_REFRESH_HOURS=0)")
        _schedule_state["enabled"] = False
        return

    _schedule_state["enabled"] = True
    _schedule_state["interval_hours"] = round(interval / 3600, 2)
    log.info(
        "Cricsheet auto-refresh enabled — every %.1f hours (%.0fs)",
        interval / 3600, interval,
    )

    # Wait for the first interval before refreshing — the Docker build already
    # bakes fresh data, so the first refresh only needs to happen later.
    while True:
        _schedule_state["next_run_at"] = time.time() + interval
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            log.info("Cricsheet scheduler cancelled — shutting down")
            return

        log.info("⏰ Scheduled Cricsheet data refresh starting …")
        _schedule_state["last_run_at"] = time.time()

        try:
            success = await _do_refresh()
            _schedule_state["runs_completed"] += 1
            _schedule_state["last_success"] = success
            if success:
                log.info("✅ Scheduled Cricsheet refresh completed successfully")
            else:
                log.warning("⚠️  Scheduled Cricsheet refresh finished with errors")
        except Exception as exc:
            log.exception("Scheduled Cricsheet refresh crashed: %s", exc)
            _schedule_state["last_success"] = False


async def _do_refresh() -> bool:
    """Run the refresh in a thread (reuses admin.py logic)."""
    from ..routers.admin import _refresh_state, _refresh_lock, _run_refresh
    import threading

    # Skip if a manual or previous scheduled refresh is already running
    with _refresh_lock:
        if _refresh_state["running"]:
            log.info("Refresh already in progress — skipping scheduled run")
            return _refresh_state.get("success") or False

    # Run _run_refresh in a thread (it's sync + subprocess-based)
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _run_refresh)

    return _refresh_state.get("success") or False


# ── Public API ────────────────────────────────────────────────────────────────

def start(loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
    """Start the scheduler. Call once during app lifespan startup."""
    global _task
    if _task is not None:
        return  # already started

    interval = _refresh_interval_s()
    if interval <= 0:
        log.info("Cricsheet auto-refresh disabled (CRICSHEET_REFRESH_HOURS=0)")
        _schedule_state["enabled"] = False
        return

    # Set state eagerly so schedule_status() returns correct info immediately
    _schedule_state["enabled"] = True
    _schedule_state["interval_hours"] = round(interval / 3600, 2)

    _loop = loop or asyncio.get_event_loop()
    _task = _loop.create_task(_scheduler_loop(), name="cricsheet-refresh-scheduler")
    log.info("Cricsheet refresh scheduler task created (every %.1fh)", interval / 3600)


async def stop() -> None:
    """Cancel the scheduler task. Call during app lifespan shutdown."""
    global _task
    if _task is not None and not _task.done():
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        log.info("Cricsheet refresh scheduler stopped")
    _task = None


def schedule_status() -> dict:
    """Return current scheduler state for health/admin endpoints."""
    return {
        **_schedule_state,
        "last_run_ago_s": (
            round(time.time() - _schedule_state["last_run_at"], 1)
            if _schedule_state["last_run_at"] else None
        ),
        "next_run_in_s": (
            round(_schedule_state["next_run_at"] - time.time(), 1)
            if _schedule_state["next_run_at"] else None
        ),
    }
