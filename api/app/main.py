"""
FastAPI backend for Autonomous Network NOC Demo.

Serves:
  - REST API at /api/* (alert submission, agent listing)
  - MCP server at /mcp (Streamable HTTP for Foundry/Copilot clients)
  - Health check at /health

Run locally:
  cd api && uv run uvicorn app.main:app --reload --port 8000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import alert, agents

app = FastAPI(
    title="Autonomous Network NOC API",
    version="0.1.0",
    description="Backend API for the Autonomous Network NOC Demo",
)

# CORS — allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
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
