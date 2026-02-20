"""
Scenario ingest package — splits the monolithic router_ingest.py into
focused sub-modules.

Re-exports a single ``router`` for main.py / router_ingest.py to include.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/query", tags=["scenarios"])

# Import sub-routers — each defines its own APIRouter (no prefix)
from .graph_ingest import router as _graph_router
from .telemetry_ingest import router as _telemetry_router
from .knowledge_ingest import router as _knowledge_router
from .prompt_ingest import router as _prompt_router
from .scenarios import router as _scenarios_router

router.include_router(_graph_router)
router.include_router(_telemetry_router)
router.include_router(_knowledge_router)
router.include_router(_prompt_router)
router.include_router(_scenarios_router)

__all__ = ["router"]
