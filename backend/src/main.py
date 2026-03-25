from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, FileResponse
from contextlib import asynccontextmanager
import os
import logging
import time

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

_START_TIME = time.time()

DIST_DIR = os.environ.get(
    "FRONTEND_DIST",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist"))
)

# ── Lifespan (replaces deprecated @app.on_event) ─────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    port = os.environ.get("PORT", "8080")
    log.info("Cric Insights API ready on PORT=%s uptime=%.1fs", port, time.time() - _START_TIME)
    log.info("FRONTEND_DIST=%s exists=%s", DIST_DIR, os.path.isdir(DIST_DIR))
    if not os.environ.get("GEMINI_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
        log.warning("No LLM API key set — add GEMINI_API_KEY in Railway Variables")
    yield  # application runs here

app = FastAPI(title="Cric Insights API", lifespan=lifespan)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── No-cache middleware for HTML ──────────────────────────────────────────────
class NoCacheHTMLMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        ct = response.headers.get("content-type", "")
        if "text/html" in ct:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            response.headers["Pragma"] = "no-cache"
        return response

app.add_middleware(NoCacheHTMLMiddleware)

# ── Health endpoints — registered FIRST so they always respond ────────────────
@app.get("/api/health")
@app.get("/health")
def health():
    return {
        "status": "ok",
        "uptime_seconds": round(time.time() - _START_TIME, 1),
        "port": os.environ.get("PORT", "8080"),
        "frontend_ok": os.path.isdir(DIST_DIR),
    }

# ── Routers — wrapped in try/except so a bad import never kills the process ───
try:
    from .routers import players, matches, insights, ask  # noqa: E402
    app.include_router(players.router,  prefix="/api/players",  tags=["players"])
    app.include_router(matches.router,  prefix="/api/matches",  tags=["matches"])
    app.include_router(insights.router, prefix="/api/insights", tags=["insights"])
    app.include_router(ask.router,      prefix="/api/ask",      tags=["ask"])
    log.info("All routers registered successfully.")
except Exception as _router_err:
    log.error("Router import failed: %s — API routes unavailable, health still OK", _router_err)

# ── Serve React frontend static assets ───────────────────────────────────────
if os.path.isdir(DIST_DIR):
    _assets_dir = os.path.join(DIST_DIR, "assets")
    if os.path.isdir(_assets_dir):
        app.mount("/assets", StaticFiles(directory=_assets_dir), name="assets")

    _INDEX = os.path.join(DIST_DIR, "index.html")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        candidate = os.path.join(DIST_DIR, full_path)
        if full_path and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(_INDEX)
