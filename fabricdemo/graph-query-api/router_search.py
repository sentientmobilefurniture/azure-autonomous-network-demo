"""
Router: AI Search Query — query runbooks and tickets indexes directly.

Provides direct access to Azure AI Search indexes so the frontend
can display actual search results (document chunks, relevance scores)
rather than relying on the agent's synthesized summary.

Endpoints:
  POST /query/search  — search an AI Search index
"""

from __future__ import annotations

import asyncio
import logging
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import DATA_SOURCES, AI_SEARCH_NAME, get_credential

logger = logging.getLogger("graph-query-api.search")

router = APIRouter(prefix="/query", tags=["search"])

AI_SEARCH_API_VERSION = "2024-07-01"

# Map agent names to their search index config key
_AGENT_INDEX_MAP = {
    "RunbookKBAgent": "runbooks",
    "HistoricalTicketAgent": "tickets",
}


def _get_search_endpoint() -> str:
    """Resolve the AI Search endpoint URL."""
    endpoint = os.getenv("AZURE_SEARCH_ENDPOINT", "")
    if not endpoint and AI_SEARCH_NAME:
        endpoint = f"https://{AI_SEARCH_NAME}.search.windows.net"
    return endpoint


class SearchRequest(BaseModel):
    agent: str
    query: str
    top: int = 10


class SearchHit(BaseModel):
    score: float
    title: str = ""
    content: str = ""
    chunk_id: str = ""


class SearchResponse(BaseModel):
    hits: list[SearchHit] = []
    total: int = 0
    index_name: str = ""
    error: str | None = None


@router.post("/search", response_model=SearchResponse, summary="Query an AI Search index directly")
async def search_index(req: SearchRequest):
    """Execute a hybrid search against a runbooks or tickets index."""
    index_key = _AGENT_INDEX_MAP.get(req.agent)
    if not index_key:
        raise HTTPException(
            status_code=400,
            detail=f"Agent '{req.agent}' has no associated search index. "
            f"Supported: {list(_AGENT_INDEX_MAP.keys())}",
        )

    search_indexes = DATA_SOURCES.get("search_indexes", {})
    index_config = search_indexes.get(index_key, {})
    index_name = index_config.get("index_name", "")
    if not index_name:
        return SearchResponse(error=f"No index configured for '{index_key}'")

    endpoint = _get_search_endpoint()
    if not endpoint:
        return SearchResponse(error="AI Search endpoint not configured")

    logger.info("Searching index=%s for agent=%s query=%.100s", index_name, req.agent, req.query)

    try:
        import httpx

        # Get auth token
        search_key = os.getenv("AZURE_SEARCH_KEY", "")
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if search_key:
            headers["api-key"] = search_key
        else:
            cred = get_credential()
            token = await asyncio.to_thread(
                cred.get_token, "https://search.azure.com/.default"
            )
            headers["Authorization"] = f"Bearer {token.token}"

        # Full-text search (not vector — we don't have an embedding model handy)
        search_body = {
            "search": req.query,
            "top": req.top,
            "queryType": "simple",
            "searchMode": "any",
            "select": "*",
        }

        url = f"{endpoint}/indexes/{index_name}/docs/search?api-version={AI_SEARCH_API_VERSION}"

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=search_body, headers=headers)

        if resp.status_code != 200:
            detail = resp.text[:500]
            logger.warning("Search failed: HTTP %d — %s", resp.status_code, detail)
            return SearchResponse(
                index_name=index_name,
                error=f"Search failed (HTTP {resp.status_code}): {detail}",
            )

        data = resp.json()
        raw_hits = data.get("value", [])

        hits: list[SearchHit] = []
        for h in raw_hits:
            score = h.get("@search.score", 0.0)
            # AI Search documents may have various field names — try common ones
            title = (
                h.get("title", "")
                or h.get("Title", "")
                or h.get("metadata_storage_name", "")
                or h.get("chunk_id", "")
                or ""
            )
            content = (
                h.get("chunk", "")
                or h.get("content", "")
                or h.get("Content", "")
                or h.get("text", "")
                or ""
            )
            chunk_id = h.get("chunk_id", "") or h.get("id", "") or ""

            hits.append(SearchHit(
                score=score,
                title=title,
                content=content[:2000],  # Cap for payload size
                chunk_id=chunk_id,
            ))

        total = data.get("@odata.count", len(hits))
        logger.info("Search returned %d hits from index=%s", len(hits), index_name)

        return SearchResponse(
            hits=hits,
            total=total,
            index_name=index_name,
        )

    except Exception as e:
        logger.exception("Search query failed for index=%s", index_name)
        return SearchResponse(
            index_name=index_name,
            error=f"Search error: {type(e).__name__}: {e}",
        )
