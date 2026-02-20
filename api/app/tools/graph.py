"""Graph topology query tool — executes GQL queries via the graph backend."""

from typing import Annotated

import httpx
from pydantic import Field


async def graph_topology_query(
    query: Annotated[str, Field(description=(
        "GQL query against the network topology graph. Uses MATCH/RETURN syntax. "
        "Example: MATCH (r:CoreRouter) RETURN r.RouterId, r.Hostname. "
        "Relationships: MATCH (a)-[r:connects_to]->(b) RETURN a.RouterId, b.RouterId."
    ))],
) -> str:
    """Execute a GQL graph query against the network topology."""
    from app.paths import _graph_query_base
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{_graph_query_base()}/query/graph",
            json={"query": query},
        )
        resp.raise_for_status()
        return resp.text
