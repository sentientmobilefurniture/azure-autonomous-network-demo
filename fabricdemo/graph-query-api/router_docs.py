"""
Router: Generic document CRUD for Cosmos NoSQL containers.

Provides GET/PUT/DELETE at /query/docs/{container}/* so that other
services (e.g. the api service) can persist documents without
depending on the Cosmos SDK directly.

Only containers in ALLOWED_CONTAINERS can be accessed (security allowlist).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from stores import get_document_store

logger = logging.getLogger("graph-query-api.docs")

router = APIRouter(prefix="/query/docs", tags=["docs"])

DB_NAME = "scenarios"
PK_PATH = "/id"

# Only these containers can be accessed via this endpoint
ALLOWED_CONTAINERS = {"upload-jobs"}


def _get_store(container_name: str):
    if container_name not in ALLOWED_CONTAINERS:
        raise HTTPException(403, f"Container '{container_name}' is not accessible via this endpoint")
    return get_document_store(
        DB_NAME, container_name, PK_PATH, ensure_created=True,
    )


@router.get("/{container_name}")
async def list_docs(container_name: str, query: str | None = None) -> dict[str, Any]:
    """List documents in a container. Optional Cosmos SQL query."""
    store = _get_store(container_name)
    items = await store.list(query=query or "SELECT * FROM c ORDER BY c.created_at DESC")
    # Strip Cosmos system fields
    clean = [
        {k: v for k, v in item.items() if not k.startswith("_")}
        for item in items
    ]
    return {"items": clean}


@router.get("/{container_name}/{doc_id}")
async def get_doc(container_name: str, doc_id: str) -> dict[str, Any]:
    """Get a single document by ID."""
    store = _get_store(container_name)
    try:
        item = await store.get(doc_id, doc_id)
    except Exception:
        raise HTTPException(404, f"Document {doc_id} not found")
    return {k: v for k, v in item.items() if not k.startswith("_")}


@router.put("/{container_name}/{doc_id}")
async def upsert_doc(container_name: str, doc_id: str, request: Request) -> dict[str, Any]:
    """Upsert a document. Body is the full document JSON."""
    store = _get_store(container_name)
    body = await request.json()
    body["id"] = doc_id  # ensure ID matches path
    result = await store.upsert(body)
    return {k: v for k, v in result.items() if not k.startswith("_")}


@router.delete("/{container_name}/{doc_id}")
async def delete_doc(container_name: str, doc_id: str) -> dict[str, str]:
    """Delete a document by ID."""
    store = _get_store(container_name)
    try:
        await store.delete(doc_id, doc_id)
    except Exception:
        raise HTTPException(404, f"Document {doc_id} not found")
    return {"deleted": doc_id}
