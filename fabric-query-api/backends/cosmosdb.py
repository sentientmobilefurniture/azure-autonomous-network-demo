"""
Azure Cosmos DB for Apache Gremlin backend — PLACEHOLDER.

Set GRAPH_BACKEND=cosmosdb to select this backend. Currently raises
NotImplementedError. Full implementation will use gremlinpython SDK
(see custom_skills/azure-cosmosdb-gremlin-py/ for reference).
"""

from __future__ import annotations


class CosmosDBGremlinBackend:
    """Graph backend using Azure Cosmos DB for Apache Gremlin."""

    async def execute_query(self, query: str, **kwargs) -> dict:
        """Execute a Gremlin query against Cosmos DB.

        Not yet implemented — set GRAPH_BACKEND=fabric to use Fabric GraphModel.
        """
        raise NotImplementedError(
            "Cosmos DB Gremlin backend not yet implemented. "
            "Set GRAPH_BACKEND=fabric to use Fabric GraphModel."
        )

    def close(self) -> None:
        pass
