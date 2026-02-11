"""
FastAPI backend for Autonomous Network NOC Demo.

Serves:
  - REST API at /api/* (alert submission, agent listing)
  - MCP server at /mcp (Streamable HTTP for Foundry/Copilot clients)
  - Health check at /health

Run locally:
  cd api && uv run uvicorn app.main:app --reload --port 8000
"""

import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import alert, agents

# Load project-level config (CORS_ORIGINS, etc.)
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", "azure_config.env"))

app = FastAPI(
    title="Autonomous Network NOC API",
    version="0.1.0",
    description="Backend API for the Autonomous Network NOC Demo",
)

# CORS — configurable via CORS_ORIGINS env var (comma-separated list)
_cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173")
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


@app.get("/health")
async def health():
    """Simple health check."""
    return {"status": "ok", "service": "autonomous-network-noc-api"}
