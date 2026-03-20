from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
import os
import logging
import time

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

_START_TIME = time.time()

from .routers import players, matches, insights, ask

DIST_DIR = os.environ.get(
    "FRONTEND_DIST",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist"))
)

app = FastAPI(title="Cric Insights API")

# ── No-cache middleware for HTML responses ──────────────────────────────────
class NoCacheHTMLMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        ct = response.headers.get("content-type", "")
        if "text/html" in ct:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            response.headers["Pragma"] = "no-cache"
        return response

app.add_middleware(NoCacheHTMLMiddleware)

@app.on_event("startup")
async def startup_event():
    port = os.environ.get("PORT", "8002")
    log.info(f"🚀 Cric Insights API starting on PORT={port}")
    log.info(f"📁 FRONTEND_DIST={DIST_DIR} exists={os.path.isdir(DIST_DIR)}")
    if not os.environ.get("GEMINI_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
        log.warning("⚠️  No LLM API key found — set GEMINI_API_KEY or OPENAI_API_KEY in Railway Variables")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(players.router, prefix="/api/players", tags=["players"])
app.include_router(matches.router, prefix="/api/matches", tags=["matches"])
app.include_router(insights.router, prefix="/api/insights", tags=["insights"])
app.include_router(ask.router, prefix="/api/ask", tags=["ask"])

@app.get("/api/health")
def health():
    uptime = round(time.time() - _START_TIME, 1)
    return {
        "status": "ok",
        "uptime_seconds": uptime,
        "port": os.environ.get("PORT", "8080"),
        "frontend_dist": DIST_DIR,
        "frontend_ok": os.path.isdir(DIST_DIR),
    }

@app.get("/health")
def health_root():
    """Alias at /health in case Railway probes without /api prefix."""
    return {"status": "ok", "uptime_seconds": round(time.time() - _START_TIME, 1)}

if os.path.isdir(DIST_DIR):
    app.mount("/", StaticFiles(directory=DIST_DIR, html=True), name="frontend")
