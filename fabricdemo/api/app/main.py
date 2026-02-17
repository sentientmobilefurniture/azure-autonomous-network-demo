"""
FastAPI backend for Autonomous Network NOC Demo.

Serves:
  - REST API at /api/* (alert submission, agent listing)
  - Health check at /health

Run locally:
  cd api && uv run uvicorn app.main:app --reload --port 8000
"""

import logging
import os
import time as _time

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

# Configure logging BEFORE importing routers (logs.py adds a handler
# to the root logger at import time; if basicConfig runs after that,
# it becomes a no-op and the root level stays at WARNING).
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("app").setLevel(logging.DEBUG)

from app.routers import alert, agents, logs, config  # noqa: E402
from app.routers import fabric_provision  # noqa: E402
from app.routers import upload_jobs  # noqa: E402

# Load project-level config (CORS_ORIGINS, etc.)
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", "azure_config.env"))

app = FastAPI(
    title="Autonomous Network NOC API",
    version="0.1.0",
    description="Backend API for the Autonomous Network NOC Demo",
)

# CORS — configurable via CORS_ORIGINS env var (comma-separated list)
_cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount REST routers
app.include_router(alert.router)
app.include_router(agents.router)
app.include_router(logs.router)
app.include_router(config.router)
app.include_router(fabric_provision.router)
app.include_router(upload_jobs.router)

logger = logging.getLogger("app")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log every incoming request with timing info."""
    logger.info("▶ %s %s", request.method, request.url.path)
    t0 = _time.time()
    response = await call_next(request)
    elapsed_ms = (_time.time() - t0) * 1000
    if response.status_code >= 400:
        logger.warning(
            "◀ %s %s → %d  (%.0fms)",
            request.method, request.url.path, response.status_code, elapsed_ms,
        )
    else:
        logger.info(
            "◀ %s %s → %d  (%.0fms)",
            request.method, request.url.path, response.status_code, elapsed_ms,
        )
    return response


@app.get("/health")
async def health():
    """Simple health check."""
    return {"status": "ok", "service": "autonomous-network-noc-api"}
