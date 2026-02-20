"""
CosmosDocumentStore — Cosmos DB NoSQL implementation of DocumentStore.

Wraps cosmos_helpers.get_or_create_container() and the Cosmos SDK's
synchronous methods with asyncio.to_thread() for non-blocking access.
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.cosmos_helpers import get_or_create_container


class CosmosDocumentStore:
    """Cosmos NoSQL implementation of DocumentStore."""

    def __init__(
        self,
        db_name: str,
        container_name: str,
        pk_path: str,
        *,
        ensure_created: bool = False,
    ):
        self._container = get_or_create_container(
            db_name, container_name, pk_path,
            ensure_created=ensure_created,
        )

    async def list(
        self,
        *,
        query: str | None = None,
        parameters: list[dict[str, Any]] | None = None,
        partition_key: str | None = None,
    ) -> list[dict[str, Any]]:
        q = query or "SELECT * FROM c"
        kwargs: dict = {"query": q}
        if parameters:
            kwargs["parameters"] = parameters
        if partition_key:
            kwargs["partition_key"] = partition_key
            kwargs["enable_cross_partition_query"] = False
        else:
            kwargs["enable_cross_partition_query"] = True
        return await asyncio.to_thread(
            lambda: list(self._container.query_items(**kwargs))
        )

    async def get(self, item_id: str, partition_key: str) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._container.read_item, item_id, partition_key=partition_key
        )

    async def upsert(self, item: dict[str, Any]) -> dict[str, Any]:
        return await asyncio.to_thread(self._container.upsert_item, item)

    async def delete(self, item_id: str, partition_key: str) -> None:
        await asyncio.to_thread(
            self._container.delete_item, item_id, partition_key=partition_key
        )
