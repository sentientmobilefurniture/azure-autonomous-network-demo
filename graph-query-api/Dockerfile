FROM python:3.11-slim

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency manifest and install
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy application code
COPY *.py ./
COPY backends/ ./backends/
COPY openapi/ ./openapi/
COPY stores/ ./stores/
COPY adapters/ ./adapters/
COPY services/ ./services/

# Expose port
EXPOSE 8100

# Run with uvicorn
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8100"]
