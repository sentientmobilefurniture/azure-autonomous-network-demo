"""Telemetry KQL query tool — executes KQL against Fabric Eventhouse."""

from typing import Annotated

import httpx
from pydantic import Field


async def telemetry_kql_query(
    query: Annotated[str, Field(description=(
        "KQL query against network telemetry and alert data. Start with table name + pipe operators. "
        "Tables: AlertStream, LinkTelemetry. "
        "Example: AlertStream | where Severity == 'Critical' | take 10"
    ))],
) -> str:
    """Execute a KQL query against network telemetry and alert data."""
    from app.paths import _graph_query_base
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{_graph_query_base()}/query/telemetry",
            json={"query": query},
        )
        resp.raise_for_status()
        return resp.text
