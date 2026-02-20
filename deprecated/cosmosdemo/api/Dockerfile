# ============================================================================
# API Service — FastAPI backend for Autonomous Network NOC Demo
# Build context: parent directory (..) so we can copy scripts/agent_ids.json
# ============================================================================
FROM python:3.11-slim

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency manifest and install (same pattern as graph-query-api)
COPY api/pyproject.toml api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy application code
COPY api/app ./app

# Copy agent_ids.json (may not exist on first deploy — that's OK)
RUN mkdir -p /app/scripts
COPY scripts/agent_ids.json* /app/scripts/

# The container reads agent_ids from AGENT_IDS_PATH env var
ENV AGENT_IDS_PATH=/app/scripts/agent_ids.json

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
