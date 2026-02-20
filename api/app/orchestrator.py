"""
Orchestrator bridge — runs the Foundry Orchestrator agent in a background
thread and yields SSE events via an async generator.

The Azure AI Agents SDK uses a synchronous callback-based streaming API
(AgentEventHandler). This module bridges it to async SSE by:
  1. Running the agent stream in a daemon thread
  2. Pushing SSE-shaped dicts to an asyncio.Queue from the callbacks
  3. Yielding from the queue in an async generator for EventSourceResponse

Falls back to stub responses when the orchestrator isn't configured
(missing env vars or no agents provisioned in Foundry).
"""

import asyncio
import ast
import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timezone
from typing import AsyncGenerator

import app.paths  # noqa: F401  # side-effect: loads .env
from app.agent_ids import load_agent_ids, get_agent_names

logger = logging.getLogger(__name__)

# Cached credential singleton — shared with agent_ids module
_credential = None

def _get_credential():
    global _credential
    if _credential is None:
        from azure.identity import DefaultAzureCredential
        _credential = DefaultAzureCredential()
    return _credential


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def is_configured() -> bool:
    """Check whether the Foundry orchestrator is ready to use."""
    if not os.environ.get("PROJECT_ENDPOINT"):
        return False
    if not os.environ.get("AI_FOUNDRY_PROJECT_NAME"):
        return False
    try:
        data = load_agent_ids()
        if not data.get("orchestrator", {}).get("id"):
            return False
    except Exception:
        return False
    return True


def _load_orchestrator_id() -> str:
    return load_agent_ids()["orchestrator"]["id"]


def _load_agent_names() -> dict[str, str]:
    """Map of agent_id → display name for resolving connected-agent calls."""
    return get_agent_names()


def _get_project_client():
    """Create an AIProjectClient with the project-scoped endpoint."""
    from azure.ai.projects import AIProjectClient

    endpoint = os.environ.get("PROJECT_ENDPOINT", "")
    project_name = os.environ.get("AI_FOUNDRY_PROJECT_NAME", "")
    if not endpoint or not project_name:
        raise RuntimeError(
            "PROJECT_ENDPOINT and AI_FOUNDRY_PROJECT_NAME must be set"
        )
    endpoint = endpoint.rstrip("/")
    # Ensure endpoint uses services.ai.azure.com and has /api/projects/ path
    if "/api/projects/" not in endpoint:
        endpoint = endpoint.replace("cognitiveservices.azure.com", "services.ai.azure.com")
        endpoint = f"{endpoint}/api/projects/{project_name}"
    return AIProjectClient(endpoint=endpoint, credential=_get_credential())


# ---------------------------------------------------------------------------
# SSE event generator — GUTTED (Phase 03 Task 01)
#
# The duplicated SSEEventHandler classes and both run_orchestrator /
# run_orchestrator_session functions have been deleted.
# Rebuilt as a single unified handler in Task 03.
# ---------------------------------------------------------------------------

async def run_orchestrator_session(
    alert_text: str,
    cancel_event: threading.Event = None,
    existing_thread_id: str = None,
) -> AsyncGenerator[dict, None]:
    """Stub — replaced in Phase 03 Task 03."""
    raise NotImplementedError(
        "run_orchestrator_session gutted — see phase_03 task 03"
    )
    yield  # make it a generator
