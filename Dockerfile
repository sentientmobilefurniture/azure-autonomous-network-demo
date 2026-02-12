# ============================================================================
# Unified Container — All 3 services in one container
#   - nginx (:80)          — React SPA + reverse proxy
#   - API uvicorn (:8000)  — FastAPI orchestrator (Foundry agents)
#   - Graph-query-api uvicorn (:8100) — Gremlin/telemetry queries
#
# Build context: project root (.)
# ============================================================================

# ── Stage 1: Build React frontend ──────────────────────────────────
FROM node:20-alpine AS frontend-build

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --silent

COPY frontend/ ./
RUN npm run build

# ── Stage 2: Python runtime + nginx + supervisord ──────────────────
FROM python:3.11-slim

# Install nginx and supervisord
RUN apt-get update && \
    apt-get install -y --no-install-recommends nginx supervisor && \
    rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# ── Graph-query-api dependencies ──────────────────────────────────
WORKDIR /app/graph-query-api
COPY graph-query-api/pyproject.toml graph-query-api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY graph-query-api/*.py ./
COPY graph-query-api/backends/ ./backends/
COPY graph-query-api/openapi/ ./openapi/

# ── API dependencies ──────────────────────────────────────────────
WORKDIR /app/api
COPY api/pyproject.toml api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY api/app/ ./app/

# Copy agent_ids.json (may not exist on first deploy)
RUN mkdir -p /app/scripts
COPY scripts/agent_ids.json* /app/scripts/

# ── Frontend static files ─────────────────────────────────────────
COPY --from=frontend-build /build/dist /usr/share/nginx/html

# ── Nginx config ──────────────────────────────────────────────────
RUN rm -f /etc/nginx/sites-enabled/default /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/default.conf

# ── Supervisord config ────────────────────────────────────────────
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# ── Environment ───────────────────────────────────────────────────
ENV AGENT_IDS_PATH=/app/scripts/agent_ids.json

EXPOSE 80

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
