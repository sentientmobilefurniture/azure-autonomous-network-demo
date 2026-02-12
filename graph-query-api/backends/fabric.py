"""
Fabric GraphModel backend — GQL queries via Fabric REST API.

Implements the GraphBackend protocol for GRAPH_BACKEND=fabric.
Uses a persistent httpx.AsyncClient for connection pooling and wraps
synchronous credential.get_token() in asyncio.to_thread() to avoid
blocking the event loop.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

import httpx
from fastapi import HTTPException

from config import (
    FABRIC_API,
    FABRIC_SCOPE,
    WORKSPACE_ID,
    GRAPH_MODEL_ID,
    credential,
)

logger = logging.getLogger("graph-query-api")


# ---------------------------------------------------------------------------
# Persistent HTTP client
# ---------------------------------------------------------------------------

_http_client: httpx.AsyncClient | None = None


def _get_http_client() -> httpx.AsyncClient:
    """Return a persistent httpx.AsyncClient (lazy-created)."""
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=60.0)
    return _http_client


# ---------------------------------------------------------------------------
# Fabric REST API helpers
# ---------------------------------------------------------------------------


async def _fabric_headers() -> dict[str, str]:
    """Get Fabric auth headers (non-blocking token acquisition)."""
    token = await asyncio.to_thread(credential.get_token, FABRIC_SCOPE)
    return {"Authorization": f"Bearer {token.token}", "Content-Type": "application/json"}


async def _execute_gql(
    query: str,
    workspace_id: str = "",
    graph_model_id: str = "",
    max_retries: int = 3,
) -> dict:
    """Execute a GQL query with retry on 429 (fully async)."""
    ws = workspace_id or WORKSPACE_ID
    gm = graph_model_id or GRAPH_MODEL_ID
    url = (
        f"{FABRIC_API}/workspaces/{ws}"
        f"/GraphModels/{gm}/executeQuery"
    )
    body = {"query": query}

    logger.info("GQL request to %s", url)
    logger.debug("GQL query:\n%s", query)

    client = _get_http_client()

    for attempt in range(1, max_retries + 1):
        headers = await _fabric_headers()
        t0 = time.time()
        r = await client.post(url, headers=headers, json=body, params={"beta": "True"})
        elapsed_ms = (time.time() - t0) * 1000
        logger.info(
            "GQL response: status=%d  elapsed=%.0fms  attempt=%d/%d",
            r.status_code, elapsed_ms, attempt, max_retries,
        )

        if r.status_code == 200:
            payload = r.json()
            # Fabric returns HTTP 200 even for GQL errors — check body status
            status_code = payload.get("status", {}).get("code", "")
            if status_code and not status_code.startswith("0"):
                cause = payload.get("status", {}).get("cause", {})
                err_desc = cause.get("description", payload["status"].get("description", "unknown GQL error"))
                logger.error(
                    "GQL logical error (status=%s): %s\nFull query:\n%s\nFull response body:\n%s",
                    status_code, err_desc, query, r.text[:2000],
                )
                raise HTTPException(status_code=400, detail=f"GQL error ({status_code}): {err_desc}")
            # Log result summary
            result_data = payload.get("result", payload)
            row_count = len(result_data.get("data", []))
            col_count = len(result_data.get("columns", []))
            logger.info("GQL success: %d columns, %d rows", col_count, row_count)
            return payload

        if r.status_code == 429 and attempt < max_retries:
            retry_after = int(r.headers.get("Retry-After", "0"))
            if not retry_after:
                try:
                    msg = r.json().get("message", "")
                    if "until:" in msg:
                        ts_str = msg.split("until:")[1].strip().rstrip(")")
                        ts_str = ts_str.replace("(UTC", "").strip()
                        blocked_until = datetime.strptime(ts_str, "%m/%d/%Y %I:%M:%S %p")
                        blocked_until = blocked_until.replace(tzinfo=timezone.utc)
                        wait = (blocked_until - datetime.now(timezone.utc)).total_seconds()
                        retry_after = max(int(wait) + 1, 3)
                except Exception:
                    logger.debug("Could not parse Retry-After timestamp from 429 body, using fallback")
            retry_after = max(retry_after, 10 * attempt)
            logger.info("429 rate-limited, retrying in %ds (attempt %d/%d)", retry_after, attempt, max_retries)
            await asyncio.sleep(retry_after)
            continue

        # Non-retryable error
        logger.error(
            "GQL non-retryable error: HTTP %d\nQuery:\n%s\nResponse body:\n%s",
            r.status_code, query, r.text[:2000],
        )
        raise HTTPException(
            status_code=r.status_code,
            detail=f"Fabric GraphModel API error (HTTP {r.status_code}): {r.text[:1000]}",
        )

    raise HTTPException(status_code=429, detail="Rate-limited after max retries")


# ---------------------------------------------------------------------------
# Backend class
# ---------------------------------------------------------------------------


class FabricGraphBackend:
    """Graph backend using Fabric GraphModel REST API (GQL)."""

    async def execute_query(self, query: str, **kwargs) -> dict:
        """Execute a GQL query against Fabric GraphModel.

        Keyword args:
            workspace_id: Fabric workspace GUID (falls back to env var)
            graph_model_id: GraphModel item GUID (falls back to env var)
        """
        workspace_id = kwargs.get("workspace_id", "") or WORKSPACE_ID
        graph_model_id = kwargs.get("graph_model_id", "") or GRAPH_MODEL_ID

        if not workspace_id or not graph_model_id:
            raise HTTPException(
                status_code=400,
                detail="workspace_id and graph_model_id are required (via request body or env vars)",
            )

        raw = await _execute_gql(query, workspace_id, graph_model_id)

        # Normalise Fabric API response shape
        result = raw.get("result", raw)
        return {
            "columns": result.get("columns", []),
            "data": result.get("data", []),
        }

    async def close(self) -> None:
        """Close the persistent httpx client."""
        global _http_client
        if _http_client is not None and not _http_client.is_closed:
            await _http_client.aclose()
            _http_client = None
