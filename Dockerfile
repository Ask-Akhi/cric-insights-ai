# ─── Stage 1: Build React frontend ───────────────────────────────────────────
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ─── Stage 2: Python app (lean — no Cricsheet download at build time) ─────────
FROM python:3.12-slim

# System deps — curl for healthcheck only
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Environment ──────────────────────────────────────────────────────────────
ENV LLM_PROVIDER=gemini \
    LLM_MODEL=gemini-2.5-flash \
    CRICSHEET_DATA_DIR=/app/data/cricsheet \
    FRONTEND_DIST=/app/frontend/dist \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    POLARS_MAX_THREADS=2 \
    PIP_NO_CACHE_DIR=1

# ── Python deps — production only (no pytest, no pyarrow) ─────────────────────
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# ── Frontend ──────────────────────────────────────────────────────────────────
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

# ── Backend source ────────────────────────────────────────────────────────────
COPY backend/ ./backend/

# ── Cricsheet data: NOT downloaded at build time ──────────────────────────────
# Downloading ~400 MB + parsing at build time bloats the image and causes OOM
# on Railway 512 MB containers. Instead, data is downloaded lazily on first
# request via CricsheetProvider._ensure_data().
# To pre-bake data: set BUILD_CRICSHEET=1 and redeploy (needs Railway Pro plan).
RUN if [ "${BUILD_CRICSHEET:-0}" = "1" ]; then \
      python -u backend/src/scripts/parse_cricsheet.py --gender male --download \
      && echo "✅ Cricsheet data baked into image" \
      || echo "⚠️  Cricsheet parse failed"; \
    else \
      echo "⏭  Skipping Cricsheet download (lazy mode) — data fetched on first request"; \
    fi

# ── Healthcheck ───────────────────────────────────────────────────────────────
HEALTHCHECK --interval=20s --timeout=10s --start-period=90s --retries=5 \
    CMD curl -f http://localhost:${PORT:-8080}/api/health || curl -f http://localhost:8080/api/health || exit 1

# ── Single uvicorn worker — Railway hobby = 512 MB; 2+ workers = OOM ──────────
CMD ["sh", "-c", "exec uvicorn backend.src.main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1 --log-level warning --timeout-keep-alive 30 --limit-concurrency 20"]
