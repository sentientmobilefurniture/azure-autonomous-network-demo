"""
MockDocumentStore — in-memory document store for testing.

Accepts and ignores factory args so it satisfies the same constructor
signature as CosmosDocumentStore.
"""

from __future__ import annotations

from typing import Any


class MockDocumentStore:
    """In-memory document store for testing."""

    def __init__(
        self,
        db_name: str = "",
        container_name: str = "",
        pk_path: str = "",
        *,
        ensure_created: bool = False,
    ):
        self._items: dict[str, dict[str, Any]] = {}

    async def list(
        self,
        *,
        query: str | None = None,
        parameters: list[dict[str, Any]] | None = None,
        partition_key: str | None = None,
    ) -> list[dict[str, Any]]:
        items = list(self._items.values())
        if partition_key:
            items = [i for i in items if i.get("_pk") == partition_key]
        return items

    async def get(self, item_id: str, partition_key: str) -> dict[str, Any]:
        if item_id not in self._items:
            raise KeyError(f"Item not found: {item_id}")
        return self._items[item_id]

    async def upsert(self, item: dict[str, Any]) -> dict[str, Any]:
        self._items[item["id"]] = item
        return item

    async def delete(self, item_id: str, partition_key: str) -> None:
        self._items.pop(item_id, None)
