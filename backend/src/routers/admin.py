import os
import sys
import logging
import threading
import subprocess
import time
import pathlib
from typing import Optional

from fastapi import APIRouter, Query, HTTPException
from starlette.responses import JSONResponse

from ..providers.cricsheet_provider import CricsheetProvider, PARQUET_DIR, RAW_DIR

log = logging.getLogger(__name__)
router = APIRouter()

# Shared refresh state
_refresh_lock = threading.Lock()
_refresh_state: dict = {
    "running":     False,
    "started_at":  None,
    "finished_at": None,
    "success":     None,
    "error":       None,
}


def _require_key(key: Optional[str]) -> None:
    secret = os.environ.get("ADMIN_KEY", "")
    if not secret:
        raise HTTPException(status_code=503, detail="ADMIN_KEY not configured. Set it in Railway Variables.")
    if key != secret:
        raise HTTPException(status_code=403, detail="Invalid admin key.")


def _invalidate_providers() -> None:
    try:
        import backend.src.routers.matches as _m
        _m._provider = None  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        import backend.src.routers.players as _p
        _p._provider = None  # type: ignore[attr-defined]
    except Exception:
        pass


def _run_refresh() -> None:
    global _refresh_state
    _refresh_state["running"]    = True
    _refresh_state["started_at"] = time.time()
    _refresh_state["error"]      = None
    _refresh_state["success"]    = None

    try:
        # Remove stale zips so parse_cricsheet re-downloads fresh copies
        raw_dir = pathlib.Path(RAW_DIR)
        for zip_name in ("all_male_csv.zip", "all_female_csv.zip"):
            zip_path = raw_dir / zip_name
            if zip_path.exists():
                zip_path.unlink()
                log.info("Removed stale zip: %s", zip_path)

        repo_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
        )
        result = subprocess.run(
            [sys.executable, "-m",
             "backend.src.scripts.parse_cricsheet",
             "--gender", "male", "--download", "--force"],
            capture_output=True, text=True, timeout=900,
            cwd=repo_root,
        )
        if result.returncode == 0:
            log.info("Cricsheet refresh complete")
            _refresh_state["success"] = True
            _invalidate_providers()
        else:
            err = (result.stderr or result.stdout)[-800:]
            log.warning("Cricsheet refresh failed: %s", err)
            _refresh_state["success"] = False
            _refresh_state["error"]   = err
    except Exception as exc:
        log.exception("Refresh thread crashed")
        _refresh_state["success"] = False
        _refresh_state["error"]   = str(exc)
    finally:
        _refresh_state["running"]     = False
        _refresh_state["finished_at"] = time.time()


@router.get("/data-status")
def data_status(key: Optional[str] = Query(default=None)) -> dict:
    """Return dataset freshness. Requires ?key=ADMIN_KEY."""
    _require_key(key)
    try:
        p  = CricsheetProvider()
        p.load()
        lf = p.datasets.get("balls")
        if lf is None:
            return {"status": "empty", "match_count": 0,
                    "newest_match": None, "oldest_match": None,
                    "refresh": _refresh_state}
        df    = lf.select(["match_id", "start_date"]).unique(subset=["match_id"]).collect()
        dates = df.get_column("start_date").drop_nulls().sort(descending=True)
        return {
            "status":       "ok",
            "match_count":  len(df),
            "newest_match": str(dates[0])  if len(dates) > 0 else None,
            "oldest_match": str(dates[-1]) if len(dates) > 0 else None,
            "refresh":      _refresh_state,
        }
    except Exception as exc:
        return JSONResponse({"status": "error", "detail": str(exc)}, status_code=500)


@router.post("/refresh")
def trigger_refresh(key: Optional[str] = Query(default=None)) -> dict:
    """Kick off a background Cricsheet re-download. Requires ?key=ADMIN_KEY."""
    _require_key(key)
    with _refresh_lock:
        if _refresh_state["running"]:
            return {"queued": False,
                    "message": "Refresh already running. Poll /api/admin/data-status to track progress."}
        t = threading.Thread(target=_run_refresh, daemon=True, name="cricsheet-refresh")
        t.start()
    return {
        "queued":  True,
        "message": "Cricsheet refresh started in background. Poll /api/admin/data-status?key=... to track progress.",
    }