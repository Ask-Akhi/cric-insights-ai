from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
import logging

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

from .routers import players, matches, insights, ask

# Resolve frontend dist dir early so it's available everywhere
DIST_DIR = os.environ.get(
    "FRONTEND_DIST",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist"))
)

app = FastAPI(title="Cric Insights API")

@app.on_event("startup")
async def startup_event():
    port = os.environ.get("PORT", "8002")
    log.info(f"🚀 Cric Insights API starting on PORT={port}")
    log.info(f"📁 FRONTEND_DIST={DIST_DIR} exists={os.path.isdir(DIST_DIR)}")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(players.router, prefix="/api/players", tags=["players"])
app.include_router(matches.router, prefix="/api/matches", tags=["matches"])
app.include_router(insights.router, prefix="/api/insights", tags=["insights"])
app.include_router(ask.router, prefix="/api/ask", tags=["ask"])

# Health — must be registered BEFORE the catch-all static mount
@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "port": os.environ.get("PORT", "8002"),
        "frontend_dist": DIST_DIR,
        "frontend_ok": os.path.isdir(DIST_DIR),
    }

# Serve static frontend — registered last so API routes take priority
if os.path.isdir(DIST_DIR):
    app.mount("/", StaticFiles(directory=DIST_DIR, html=True), name="frontend")
