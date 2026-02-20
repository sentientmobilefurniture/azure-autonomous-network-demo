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
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

# Configure logging BEFORE importing routers (logs.py adds a handler
# to the root logger at import time; if basicConfig runs after that,
# it becomes a no-op and the root level stays at WARNING).
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("app").setLevel(logging.DEBUG)

from app.routers import agents, logs, config, sessions  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: recover orphaned sessions
    from app.session_manager import session_manager
    await session_manager.recover_from_cosmos()
    yield
    # Shutdown: no cleanup needed (sessions persist to Cosmos on finalize)


app = FastAPI(
    title="Autonomous Network NOC API",
    version="0.1.0",
    description="Backend API for the Autonomous Network NOC Demo",
    lifespan=lifespan,
)

# CORS — configurable via CORS_ORIGINS env var (comma-separated list)
_cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

# Mount REST routers
app.include_router(agents.router)
app.include_router(logs.router)
app.include_router(config.router)
app.include_router(sessions.router)

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


@app.get("/api/services/health")
async def services_health():
    """Service connectivity summary with real probes."""
    import httpx
    import asyncio

    async def _probe(name: str, check_fn):
        t0 = _time.time()
        try:
            result = await check_fn()
            latency = int((_time.time() - t0) * 1000)
            return {"name": name, "status": "connected", "details": result or "", "latency_ms": latency}
        except Exception as e:
            latency = int((_time.time() - t0) * 1000)
            return {"name": name, "status": "error", "details": str(e)[:200], "latency_ms": latency}

    # AI Foundry — try reaching the endpoint
    async def _check_foundry():
        ep = os.getenv("PROJECT_ENDPOINT", "")
        if not ep:
            raise Exception("PROJECT_ENDPOINT not configured")
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.get(ep.rstrip("/"))
        return os.getenv("AI_FOUNDRY_NAME", ep.split("//")[-1].split(".")[0])

    # AI Search — HEAD to the service endpoint
    async def _check_search():
        endpoint = os.getenv("AZURE_SEARCH_ENDPOINT", "") or os.getenv("AI_SEARCH_ENDPOINT", "")
        if not endpoint:
            raise Exception("AI Search endpoint not configured")
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{endpoint}/indexes?api-version=2024-07-01&$top=0",
                                    headers={"api-key": os.getenv("AZURE_SEARCH_KEY", "")})
            if resp.status_code >= 400:
                raise Exception(f"HTTP {resp.status_code}")
        return os.getenv("AI_SEARCH_NAME", endpoint.split("//")[-1].split(".")[0])

    # Cosmos DB — ping the database endpoint
    async def _check_cosmos():
        cosmos_ep = os.getenv("COSMOS_NOSQL_ENDPOINT", "")
        if not cosmos_ep:
            raise Exception("COSMOS_NOSQL_ENDPOINT not configured")
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.get(cosmos_ep.rstrip("/"))
        return "NoSQL interactions store"

    # Graph Query API — hit the new liveness probe
    async def _check_gql_api():
        gq = os.getenv("GRAPH_QUERY_API_URI", "http://localhost:8100")
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{gq.rstrip('/')}/query/health")
            if resp.status_code >= 400:
                raise Exception(f"HTTP {resp.status_code}")
        return "Fabric GQL"

    probes = await asyncio.gather(
        _probe("AI Foundry", _check_foundry),
        _probe("AI Search", _check_search),
        _probe("Cosmos DB", _check_cosmos),
        _probe("Graph Query API", _check_gql_api),
        return_exceptions=False,
    )

    services = list(probes)
    connected = sum(1 for s in services if s["status"] == "connected")
    error_count = sum(1 for s in services if s["status"] == "error")

    return {
        "services": services,
        "summary": {"total": len(services), "connected": connected, "error": error_count},
    }


@app.get("/api/services/models")
async def services_models():
    """List deployed model names from AI Foundry."""
    models = []

    model_name = os.getenv("MODEL_DEPLOYMENT_NAME", "")
    embedding_name = os.getenv("EMBEDDING_MODEL", "")
    if model_name:
        models.append({"name": model_name, "type": "llm", "status": "ready"})
    if embedding_name:
        models.append({"name": embedding_name, "type": "embedding", "status": "ready"})

    return {"models": models}
