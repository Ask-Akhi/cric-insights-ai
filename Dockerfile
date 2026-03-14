# ─── Stage 1: Build React frontend ───────────────────────────────────────────
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ─── Stage 2: Python app + Supervisor ────────────────────────────────────────
FROM python:3.12-slim

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /app/data/cricsheet

# Set working dir
WORKDIR /app

# Default env vars (overridden at runtime via -e or platform secrets)
ENV LLM_PROVIDER=gemini \
    LLM_MODEL=gemini-2.5-flash \
    CRICSHEET_DATA_DIR=/app/data/cricsheet \
    FRONTEND_DIST=/app/frontend/dist \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

# Copy Python requirements and install
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy built frontend from stage 1
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

# Copy backend source (includes ui/ subdirectory)
COPY backend/ ./backend/

# Railway injects $PORT at runtime — do not hardcode EXPOSE, just bind to $PORT
# Healthcheck uses whatever port Railway assigned
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=5 \
    CMD curl -f http://localhost:${PORT:-8080}/api/health || exit 1

CMD ["sh", "-c", "exec python -m uvicorn backend.src.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
