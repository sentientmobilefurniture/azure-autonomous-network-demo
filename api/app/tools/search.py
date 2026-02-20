"""Search tools — query Azure AI Search indexes for runbooks and tickets."""

from typing import Annotated

import httpx
from pydantic import Field


async def search_runbooks(
    query: Annotated[str, Field(
        description="Search query for operational runbooks and procedures"
    )],
) -> str:
    """Search the runbook knowledge base for procedures and troubleshooting steps."""
    from app.paths import _graph_query_base
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{_graph_query_base()}/query/search",
            json={"agent": "RunbookKBAgent", "query": query, "top": 5},
        )
        resp.raise_for_status()
        return resp.text


async def search_tickets(
    query: Annotated[str, Field(
        description="Search query for historical incident tickets"
    )],
) -> str:
    """Search historical incident tickets for past resolutions and patterns."""
    from app.paths import _graph_query_base
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{_graph_query_base()}/query/search",
            json={"agent": "HistoricalTicketAgent", "query": query, "top": 5},
        )
        resp.raise_for_status()
        return resp.text
