from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
import os
import logging
import time
import asyncio

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

_START_TIME = time.time()
_READY = False   # flips True once all routers are loaded

DIST_DIR = os.environ.get(
    "FRONTEND_DIST",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist"))
)

app = FastAPI(title="Cric Insights API")

# ── CORS ────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── No-cache middleware for HTML ─────────────────────────────────────────────
class NoCacheHTMLMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        ct = response.headers.get("content-type", "")
        if "text/html" in ct:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            response.headers["Pragma"] = "no-cache"
        return response

app.add_middleware(NoCacheHTMLMiddleware)

# ── Health endpoint registered FIRST — responds instantly ───────────────────
@app.get("/api/health")
@app.get("/health")
def health():
    uptime = round(time.time() - _START_TIME, 1)
    return {
        "status": "ok",
        "ready": _READY,
        "uptime_seconds": uptime,
        "port": os.environ.get("PORT", "8080"),
        "frontend_ok": os.path.isdir(DIST_DIR),
    }

# ── Load routers in background so health passes immediately ─────────────────
def _load_routers():
    global _READY
    try:
        from .routers import players, matches, insights, ask
        app.include_router(players.router, prefix="/api/players", tags=["players"])
        app.include_router(matches.router, prefix="/api/matches", tags=["matches"])
        app.include_router(insights.router, prefix="/api/insights", tags=["insights"])
        app.include_router(ask.router, prefix="/api/ask", tags=["ask"])
        _READY = True
        log.info(f"✅ All routers loaded — uptime {round(time.time()-_START_TIME,1)}s")
    except Exception as e:
        log.error(f"❌ Router load failed: {e}")

@app.on_event("startup")
async def startup_event():
    port = os.environ.get("PORT", "8080")
    log.info(f"🚀 Cric Insights API starting on PORT={port}")
    log.info(f"📁 FRONTEND_DIST={DIST_DIR} exists={os.path.isdir(DIST_DIR)}")
    if not os.environ.get("GEMINI_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
        log.warning("⚠️  No LLM API key — set GEMINI_API_KEY in Railway Variables")
    # Load routers in a thread so the event loop (and health endpoint) stay free
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _load_routers)

# ── Serve React frontend ─────────────────────────────────────────────────────
if os.path.isdir(DIST_DIR):
    app.mount("/", StaticFiles(directory=DIST_DIR, html=True), name="frontend")
