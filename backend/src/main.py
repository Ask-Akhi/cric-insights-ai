from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
from .routers import players, matches, insights

app = FastAPI(title="Cric Insights API")

# CORS for local browser access
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

# Health
@app.get("/api/health")
def health():
    return {"status": "ok"}

# Serve static frontend
FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend"))
DIST_DIR = os.path.join(FRONTEND_DIR, "dist")
if os.path.isdir(DIST_DIR):
    # Prefer built assets from Vite
    app.mount("/", StaticFiles(directory=DIST_DIR, html=True), name="frontend")
elif os.path.isdir(FRONTEND_DIR):
    # Fallback to raw frontend folder (expects dev server normally)
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
