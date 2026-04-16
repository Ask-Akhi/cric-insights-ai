# ─── Stage 1: Build React frontend ───────────────────────────────────────────
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
# Copy postinstall scripts before npm ci so they exist when postinstall runs
COPY frontend/scripts/ ./scripts/
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ─── Stage 2: Python app + Cricsheet data baked in ────────────────────────────
FROM python:3.12-slim

# System deps — curl for healthcheck only
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Environment ──────────────────────────────────────────────────────────────
ENV LLM_PROVIDER=gemini \
    LLM_MODEL=gemini-2.0-flash \
    CRICSHEET_DATA_DIR=/app/data/cricsheet \
    CRICSHEET_REFRESH_HOURS=6 \
    FRONTEND_DIST=/app/frontend/dist \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    POLARS_MAX_THREADS=1 \
    PIP_NO_CACHE_DIR=1

# ── Python deps — production only (no pytest, no pyarrow) ─────────────────────
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# ── Frontend ──────────────────────────────────────────────────────────────────
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

# ── Backend source ────────────────────────────────────────────────────────────
COPY backend/ ./backend/

# ── Cricsheet data: downloaded at BUILD time ──────────────────────────────────
# The zip is ~80 MB and parquet output is ~30 MB — fits in Railway build memory.
# This eliminates the lazy-download race condition where the first N requests
# get empty data and fall through to Gemini (causing timeouts + quota burn).
# The raw CSVs + zip are deleted after parsing to keep the image lean.
RUN python -u backend/src/scripts/parse_cricsheet.py --gender male --download \
    && echo "✅ Cricsheet data baked into image" \
    && rm -rf /app/data/cricsheet/raw \
    && echo "🗑️ Cleaned up raw CSVs to save image space" \
    || echo "⚠️  Cricsheet parse failed — app will retry lazily at startup"

# ── Healthcheck ───────────────────────────────────────────────────────────────
HEALTHCHECK --interval=20s --timeout=10s --start-period=90s --retries=5 \
    CMD curl -f http://localhost:${PORT:-8080}/api/health || curl -f http://localhost:8080/api/health || exit 1

# ── Single uvicorn worker — Railway hobby = 512 MB; 2+ workers = OOM ──────────
CMD ["sh", "-c", "exec uvicorn backend.src.main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1 --log-level warning --timeout-keep-alive 30 --limit-concurrency 20"]
