"""
Shared Gremlin helpers — client creation and retry logic.

Used by both router_ingest.py (ingestion) and backends/cosmosdb.py (queries).
"""

from __future__ import annotations

import logging
import time

from gremlin_python.driver import client, serializer
from gremlin_python.driver.protocol import GremlinServerError

from adapters.cosmos_config import (
    COSMOS_GREMLIN_ENDPOINT,
    COSMOS_GREMLIN_PRIMARY_KEY,
    COSMOS_GREMLIN_DATABASE,
)

logger = logging.getLogger(__name__)


def create_gremlin_client(
    graph_name: str,
    database: str = COSMOS_GREMLIN_DATABASE,
) -> client.Client:
    """Create a Gremlin WSS client for a specific graph.

    Args:
        graph_name: Target graph/collection name
        database: Cosmos DB Gremlin database name

    Returns:
        A connected gremlin_python Client
    """
    return client.Client(
        url=f"wss://{COSMOS_GREMLIN_ENDPOINT}:443/",
        traversal_source="g",
        username=f"/dbs/{database}/colls/{graph_name}",
        password=COSMOS_GREMLIN_PRIMARY_KEY,
        message_serializer=serializer.GraphSONSerializersV2d0(),
    )


def gremlin_submit_with_retry(
    c: client.Client,
    query: str,
    bindings: dict | None = None,
    retries: int = 3,
) -> list:
    """Submit a Gremlin query with retry on 429 (throttled) / 408 (timeout).

    Args:
        c: An active Gremlin client
        query: Gremlin traversal string
        bindings: Optional parameter bindings
        retries: Number of retry attempts

    Returns:
        Query result list
    """
    for attempt in range(1, retries + 1):
        try:
            return c.submit(message=query, bindings=bindings or {}).all().result()
        except GremlinServerError as e:
            status = getattr(e, "status_code", 0)
            if status in (429, 408) and attempt < retries:
                time.sleep(2 ** attempt)
                continue
            raise
