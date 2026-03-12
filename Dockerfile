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
    supervisor \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /var/log /app/data/cricsheet

# Set working dir
WORKDIR /app

# Default env vars (overridden at runtime via -e or platform secrets)
ENV LLM_PROVIDER=gemini \
    LLM_MODEL=gemini-2.0-flash-lite \
    CRICSHEET_DATA_DIR=/app/data/cricsheet \
    PYTHONUNBUFFERED=1

# Copy Python requirements and install
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy built frontend from stage 1
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

# Copy backend source (includes ui/ subdirectory)
COPY backend/ ./backend/

# Copy supervisor config
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Expose ports
# 8000 = FastAPI (internal), 8502 = Streamlit, 80 = Nginx (optional)
EXPOSE 8001 8502

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8001/api/health || exit 1

# Start both services via supervisor
CMD ["supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
