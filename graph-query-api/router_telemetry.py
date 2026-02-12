"""
Router: POST /query/telemetry — KQL queries against the Fabric Eventhouse.

Extracted verbatim from the original main.py. No changes to logic.
"""

from __future__ import annotations

import asyncio
import logging
import threading

from azure.kusto.data import KustoClient, KustoConnectionStringBuilder
from azure.kusto.data.exceptions import KustoServiceError
from fastapi import APIRouter

from config import EVENTHOUSE_QUERY_URI, KQL_DB_NAME, credential
from models import TelemetryQueryRequest, TelemetryQueryResponse

logger = logging.getLogger("graph-query-api")

router = APIRouter()

# ---------------------------------------------------------------------------
# KQL helpers (moved verbatim from main.py)
# ---------------------------------------------------------------------------

_kusto_lock = threading.Lock()
_kusto_client: KustoClient | None = None
_kusto_client_uri: str = ""


def _get_kusto_client(uri: str) -> KustoClient:
    """Return a cached KustoClient if the URI matches, otherwise create a new one (thread-safe)."""
    global _kusto_client, _kusto_client_uri
    with _kusto_lock:
        if _kusto_client is None or uri != _kusto_client_uri:
            kcsb = KustoConnectionStringBuilder.with_azure_token_credential(uri, credential)
            _kusto_client = KustoClient(kcsb)
            _kusto_client_uri = uri
        return _kusto_client


def close_telemetry_backend() -> None:
    """Close the cached KustoClient (called during app lifespan shutdown)."""
    global _kusto_client
    with _kusto_lock:
        if _kusto_client is not None:
            try:
                _kusto_client.close()
            except Exception:
                pass
            _kusto_client = None


def _execute_kql(
    query: str,
    eventhouse_query_uri: str = "",
    kql_db_name: str = "",
) -> dict:
    """Execute a KQL query and return structured results."""
    import time as _time
    uri = eventhouse_query_uri or EVENTHOUSE_QUERY_URI
    db = kql_db_name or KQL_DB_NAME
    logger.info("KQL request: db=%s  uri=%s", db, uri)
    logger.debug("KQL query:\n%s", query)
    client = _get_kusto_client(uri)
    t0 = _time.time()
    response = client.execute(db, query)
    elapsed_ms = (_time.time() - t0) * 1000
    primary = response.primary_results[0] if response.primary_results else None
    if primary is None:
        logger.warning("KQL returned no primary results (%.0fms)", elapsed_ms)
        return {"columns": [], "rows": []}

    columns = [
        {"name": col.column_name, "type": col.column_type}
        for col in primary.columns
    ]
    rows = []
    for row in primary:
        row_dict = {}
        for col in primary.columns:
            val = row[col.column_name]
            if hasattr(val, "isoformat"):
                val = val.isoformat()
            row_dict[col.column_name] = val
        rows.append(row_dict)

    logger.info("KQL success: %d columns, %d rows  (%.0fms)", len(columns), len(rows), elapsed_ms)
    return {"columns": columns, "rows": rows}


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post(
    "/query/telemetry",
    response_model=TelemetryQueryResponse,
    summary="Execute a KQL query against the Fabric Eventhouse",
    description=(
        "Submits a KQL query to the Fabric Eventhouse (NetworkDB). "
        "Returns columns and rows of telemetry or alert data. "
        "If the query has a syntax error, the response will contain an "
        "'error' field with the details — read it, fix your query, and retry."
    ),
)
async def query_telemetry(req: TelemetryQueryRequest):
    logger.info(
        "POST /query/telemetry — query=%.200s  uri=%s  db=%s",
        req.query, req.eventhouse_query_uri or EVENTHOUSE_QUERY_URI, req.kql_db_name or KQL_DB_NAME,
    )
    uri = req.eventhouse_query_uri or EVENTHOUSE_QUERY_URI
    db = req.kql_db_name or KQL_DB_NAME
    if not uri or not db:
        # Config error — return as error payload so the agent LLM sees it
        return TelemetryQueryResponse(
            columns=[],
            rows=[],
            error="eventhouse_query_uri and kql_db_name are required (via request body or env vars)",
        )
    try:
        result = await asyncio.to_thread(
            _execute_kql, req.query, eventhouse_query_uri=uri, kql_db_name=db,
        )
    except KustoServiceError as e:
        logger.warning("KQL query error (returning 200 with error body): %s", e)
        return TelemetryQueryResponse(
            columns=[],
            rows=[],
            error=f"KQL query error: {e}. Read the error, fix the query syntax, and retry.",
        )
    except Exception as e:
        logger.exception("KQL backend error (returning 200 with error body)")
        return TelemetryQueryResponse(
            columns=[],
            rows=[],
            error=f"KQL backend error: {type(e).__name__}: {e}. Try simplifying the query and retry.",
        )
    return TelemetryQueryResponse(columns=result["columns"], rows=result["rows"])
