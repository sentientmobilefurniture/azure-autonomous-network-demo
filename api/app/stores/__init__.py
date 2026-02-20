"""
DocumentStore — backend-agnostic document CRUD + query protocol.

Provides:
  - DocumentStore Protocol (abstract interface)
  - Registry + factory function (get_document_store)
  - Auto-registers CosmosDocumentStore on import

Usage:
    from stores import get_document_store, DocumentStore

    store = get_document_store("interactions", "interactions", "/scenario")
    items = await store.list(query="SELECT * FROM c", parameters=[...])
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable, Any


@runtime_checkable
class DocumentStore(Protocol):
    """Backend-agnostic document CRUD + query interface."""

    async def list(
        self,
        *,
        query: str | None = None,
        parameters: list[dict[str, Any]] | None = None,
        partition_key: str | None = None,
    ) -> list[dict[str, Any]]:
        """List/query documents. If query is None, return all.

        Args:
            query: Cosmos SQL query string (e.g. "SELECT * FROM c WHERE c.x = @x")
            parameters: Parameterized query values (e.g. [{"name": "@x", "value": 1}]).
                        Always use parameters instead of f-string interpolation.
            partition_key: Scope query to a single partition (avoids cross-partition cost).
        """
        ...

    async def get(
        self,
        item_id: str,
        partition_key: str,
    ) -> dict[str, Any]:
        """Get a single document by ID + partition key."""
        ...

    async def upsert(
        self,
        item: dict[str, Any],
    ) -> dict[str, Any]:
        """Insert or update a document."""
        ...

    async def delete(
        self,
        item_id: str,
        partition_key: str,
    ) -> None:
        """Delete a document by ID + partition key."""
        ...


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_document_store_registry: dict[str, type] = {}


def register_document_store(name: str, cls: type) -> None:
    """Register a DocumentStore implementation by name."""
    _document_store_registry[name] = cls


def get_document_store(
    db_name: str,
    container_name: str,
    partition_key_path: str,
    *,
    backend_type: str | None = None,
    ensure_created: bool = False,
) -> DocumentStore:
    """Factory that returns the appropriate DocumentStore implementation.

    Args:
        db_name: Database name (e.g. "interactions", "scenarios")
        container_name: Container name within the database
        partition_key_path: Cosmos partition key path (e.g. "/scenario")
        backend_type: Override store type. Defaults to 'cosmosdb-nosql'.
                      Must match a registered store name.
        ensure_created: If True, create DB/container via ARM on first access.
    """
    bt = backend_type or "cosmosdb-nosql"
    if bt not in _document_store_registry:
        raise ValueError(
            f"Unknown document store: {bt}. "
            f"Available: {list(_document_store_registry)}"
        )
    return _document_store_registry[bt](
        db_name, container_name, partition_key_path,
        ensure_created=ensure_created,
    )


# ---------------------------------------------------------------------------
# Auto-register at module load
# ---------------------------------------------------------------------------

from .cosmos_nosql import CosmosDocumentStore  # noqa: E402

register_document_store("cosmosdb-nosql", CosmosDocumentStore)
