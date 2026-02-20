"""
Alert router — POST /api/alert

Accepts a NOC alert and returns a streamed SSE response with agent progress.
Connects to the real Foundry Orchestrator agent when configured,
falls back to stub responses for frontend development.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.orchestrator import is_configured, run_orchestrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["alert"])


class AlertRequest(BaseModel):
    """Incoming NOC alert payload."""
    text: str = Field(
        ...,
        description="The alert text to send to the Orchestrator",
        min_length=1,
        max_length=10_000,
    )


def _load_stub_agent_names() -> list[str]:
    """Read agent names via Foundry discovery; fall back to generic placeholders."""
    try:
        from app.agent_ids import get_agent_list
        agents = get_agent_list()
        return [a["name"] for a in agents if not a.get("is_orchestrator")]
    except Exception:
        return ["Agent1", "Agent2"]


async def _stub_event_generator(alert_text: str):
    """Stub SSE generator — simulates orchestrator steps with fake data."""
    yield {
        "event": "run_start",
        "data": json.dumps({
            "run_id": "run_stub_001",
            "alert": alert_text,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }),
    }

    agents = _load_stub_agent_names()
    for i, agent in enumerate(agents, 1):
        await asyncio.sleep(0.5)
        yield {
            "event": "step_start",
            "data": json.dumps({"step": i, "agent": agent}),
        }
        await asyncio.sleep(0.5)
        yield {
            "event": "step_complete",
            "data": json.dumps({
                "step": i,
                "agent": agent,
                "duration": f"{0.5 + i * 0.1:.1f}s",
                "query": f"Stub query for {agent}",
                "response": f"Stub response from {agent}",
            }),
        }

    yield {
        "event": "message",
        "data": json.dumps({
            "text": (
                "## Incident Summary\n\n"
                "**Alert:** " + alert_text + "\n\n"
                "This is a **stub response**. The real orchestrator is not configured.\n\n"
                "Run `provision_agents.py` to create agents in AI Foundry."
            ),
        }),
    }

    yield {
        "event": "run_complete",
        "data": json.dumps({"steps": len(agents), "tokens": 0, "time": "2.0s"}),
    }


@router.post("/alert")
async def submit_alert(req: AlertRequest):
    """Submit a NOC alert. Returns an SSE stream of orchestrator progress."""
    if is_configured():
        logger.info("Using real orchestrator for alert: %s", req.text[:80])
        return EventSourceResponse(run_orchestrator(req.text))
    else:
        logger.info("Orchestrator not configured — using stub for: %s", req.text[:80])
        return EventSourceResponse(_stub_event_generator(req.text))
