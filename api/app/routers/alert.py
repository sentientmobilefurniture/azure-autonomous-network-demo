"""
Alert router — POST /api/alert

Accepts a NOC alert and returns a streamed SSE response with agent progress.
Currently a hello-world stub that returns a canned response.
"""

import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

router = APIRouter(prefix="/api", tags=["alert"])


class AlertRequest(BaseModel):
    """Incoming NOC alert payload."""
    text: str = Field(..., description="The alert text to send to the Orchestrator")


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

    agents = ["TelemetryAgent", "GraphExplorerAgent", "RunbookKBAgent", "HistoricalTicketAgent"]
    for i, agent in enumerate(agents, 1):
        await asyncio.sleep(0.5)  # Simulate work
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
                "This is a stub response. The real orchestrator will be wired in later."
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
    return EventSourceResponse(_stub_event_generator(req.text))
