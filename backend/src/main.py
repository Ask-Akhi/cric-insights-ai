from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, FileResponse
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

app = FastAPI(title="Cric Insights API")

# ── CORS ─────────────────────────────────────────────────────────────────────
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

# ── Routers MUST be registered at module level — FastAPI cannot add routes after startup ──
from .routers import players, matches, insights, ask  # noqa: E402

app.include_router(players.router,  prefix="/api/players",  tags=["players"])
app.include_router(matches.router,  prefix="/api/matches",  tags=["matches"])
app.include_router(insights.router, prefix="/api/insights", tags=["insights"])
app.include_router(ask.router,      prefix="/api/ask",      tags=["ask"])

# ── Health endpoints — both paths, responds in <1s ───────────────────────────
@app.get("/api/health")
@app.get("/health")
def health():
    return {
        "status": "ok",
        "uptime_seconds": round(time.time() - _START_TIME, 1),
        "port": os.environ.get("PORT", "8080"),
        "frontend_ok": os.path.isdir(DIST_DIR),
    }

# ── Startup log ───────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    port = os.environ.get("PORT", "8080")
    log.info(f"🚀 Cric Insights API ready on PORT={port} — uptime={round(time.time()-_START_TIME,1)}s")
    log.info(f"📁 FRONTEND_DIST={DIST_DIR} exists={os.path.isdir(DIST_DIR)}")
    if not os.environ.get("GEMINI_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
        log.warning("⚠️  No LLM API key — set GEMINI_API_KEY in Railway Variables")

# ── Serve React frontend static assets (JS/CSS/icons) ────────────────────────
# Mount at /assets so API routes at /api/* are NEVER shadowed.
# StaticFiles with html=True on "/" intercepts ALL methods (including POST) → 405.
if os.path.isdir(DIST_DIR):
    _assets_dir = os.path.join(DIST_DIR, "assets")
    if os.path.isdir(_assets_dir):
        app.mount("/assets", StaticFiles(directory=_assets_dir), name="assets")

    # SPA catch-all: serve index.html for every non-API GET that has no other route.
    # Using a wildcard route keeps FastAPI's router in full control for /api/* paths.
    _INDEX = os.path.join(DIST_DIR, "index.html")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        # Serve real files that exist in DIST_DIR (e.g. manifest.json, sw.js, icons)
        candidate = os.path.join(DIST_DIR, full_path)
        if full_path and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(_INDEX)
