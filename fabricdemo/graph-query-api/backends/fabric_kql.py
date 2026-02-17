"""
Fabric KQL telemetry backend.

Sends KQL queries directly to a Fabric Eventhouse via the azure-kusto-data SDK.
Used when scenario.yaml specifies `telemetry.connector: "fabric-kql"`.

Reference: fabric_implementation_references/scripts/testing_scripts/test_kql_query.py
"""

from __future__ import annotations

import asyncio
import logging
import os

logger = logging.getLogger("graph-query-api.fabric-kql")

EVENTHOUSE_QUERY_URI = os.getenv("EVENTHOUSE_QUERY_URI", "")
FABRIC_KQL_DB_NAME = os.getenv("FABRIC_KQL_DB_NAME", "")


class FabricKQLBackend:
    """Telemetry backend for Fabric Eventhouse.

    Sends KQL queries directly to the Eventhouse via KustoClient.
    Returns results in the same {columns, rows} format as CosmosDB NoSQL.
    """

    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client is None:
            from azure.identity import DefaultAzureCredential
            from azure.kusto.data import KustoClient, KustoConnectionStringBuilder

            credential = DefaultAzureCredential()
            kcsb = KustoConnectionStringBuilder.with_azure_token_credential(
                EVENTHOUSE_QUERY_URI, credential,
            )
            self._client = KustoClient(kcsb)
        return self._client

    async def execute_query(self, query: str, **kwargs) -> dict:
        """Execute a KQL query against the Eventhouse.

        Returns: {"columns": [...], "rows": [...]}
        """
        if not EVENTHOUSE_QUERY_URI:
            return {"error": True, "detail": "EVENTHOUSE_QUERY_URI not configured"}

        client = self._get_client()
        db = kwargs.get("database") or FABRIC_KQL_DB_NAME

        try:
            response = await asyncio.to_thread(client.execute, db, query)
            primary = response.primary_results[0] if response.primary_results else None
            if primary is None:
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
            return {"columns": columns, "rows": rows}
        except Exception as e:
            logger.error("KQL query failed: %s", e)
            return {"error": True, "detail": str(e)}

    async def ping(self) -> dict:
        """Health check — run a minimal KQL management command."""
        query = ".show tables | take 1"
        import time
        t0 = time.time()
        try:
            if not EVENTHOUSE_QUERY_URI:
                return {"ok": False, "query": query, "detail": "EVENTHOUSE_QUERY_URI not configured", "latency_ms": 0}
            client = self._get_client()
            db = FABRIC_KQL_DB_NAME
            response = await asyncio.to_thread(client.execute, db, query)
            latency = int((time.time() - t0) * 1000)
            return {"ok": True, "query": query, "detail": "tables accessible", "latency_ms": latency}
        except Exception as e:
            latency = int((time.time() - t0) * 1000)
            return {"ok": False, "query": query, "detail": str(e), "latency_ms": latency}

    def close(self) -> None:
        if self._client:
            self._client = None
