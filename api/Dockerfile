# ============================================================================
# API Service — FastAPI backend for Autonomous Network NOC Demo
# Build context: parent directory (..) so we can copy scripts/agent_ids.json
# ============================================================================
FROM python:3.11-slim AS base

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Layer 1: Install dependencies (cached unless pyproject.toml changes)
COPY api/pyproject.toml api/uv.lock* ./
RUN uv sync --no-dev --no-install-project 2>/dev/null || \
    (uv pip compile pyproject.toml -o requirements.txt && uv pip install --system -r requirements.txt)

# Layer 2: Copy application code
COPY api/app ./app

# Layer 3: Copy agent_ids.json (may not exist on first deploy — that's OK)
# It gets created by provision_agents.py and injected via azd deploy
RUN mkdir -p /app/scripts
COPY scripts/agent_ids.json* /app/scripts/

# The container reads agent_ids from AGENT_IDS_PATH env var
ENV AGENT_IDS_PATH=/app/scripts/agent_ids.json

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
