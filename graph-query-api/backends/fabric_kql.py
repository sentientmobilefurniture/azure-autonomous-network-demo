"""
Fabric KQL telemetry backend.

Sends KQL queries directly to a Fabric Eventhouse via the azure-kusto-data SDK.
Used when scenario.yaml specifies `telemetry.connector: "fabric-kql"`.

Reference: fabric_implementation_references/scripts/testing_scripts/test_kql_query.py
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger("graph-query-api.fabric-kql")


class FabricKQLBackend:
    """Telemetry backend for Fabric Eventhouse.

    Sends KQL queries directly to the Eventhouse via KustoClient.
    Returns results in the same {columns, rows} format as CosmosDB NoSQL.

    Eventhouse query URI and KQL DB name are discovered at runtime
    via fabric_discovery.py instead of being read from env vars.
    """

    def __init__(self):
        self._client = None
        self._last_uri = None  # track URI to rebuild client if it changes

    def _get_client(self):
        from fabric_discovery import get_fabric_config
        cfg = get_fabric_config()
        uri = cfg.eventhouse_query_uri

        # Rebuild client if URI changed (e.g., after cache refresh)
        if self._client is None or self._last_uri != uri:
            from config import get_credential
            from azure.kusto.data import KustoClient, KustoConnectionStringBuilder

            credential = get_credential()
            kcsb = KustoConnectionStringBuilder.with_azure_token_credential(
                uri, credential,
            )
            self._client = KustoClient(kcsb)
            self._last_uri = uri
        return self._client

    async def execute_query(self, query: str, **kwargs) -> dict:
        """Execute a KQL query against the Eventhouse.

        Concurrency is bounded by the shared FabricThrottleGate.
        Returns: {"columns": [...], "rows": [...]}
        """
        from fabric_discovery import get_fabric_config, is_kql_ready
        from backends.fabric_throttle import get_fabric_gate

        if not is_kql_ready():
            return {"error": True, "detail": "KQL backend not configured — Eventhouse not discovered"}

        cfg = get_fabric_config()
        client = self._get_client()
        db = kwargs.get("database") or cfg.kql_db_name

        gate = get_fabric_gate()
        await gate.acquire()

        try:
            response = await asyncio.to_thread(client.execute, db, query)
            primary = response.primary_results[0] if response.primary_results else None
            if primary is None:
                await gate.record_success()
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
            await gate.record_success()
            return {"columns": columns, "rows": rows}
        except Exception as e:
            logger.error("KQL query failed: %s", e)
            # Check if it's a capacity error
            err_str = str(e).lower()
            if "429" in err_str or "throttl" in err_str or "capacity" in err_str:
                await gate.record_server_error()
            return {"error": True, "detail": str(e)}
        finally:
            gate.release()

    async def ping(self) -> dict:
        """Health check — run a minimal KQL management command."""
        query = ".show tables | take 1"
        import time
        t0 = time.time()
        try:
            from fabric_discovery import is_kql_ready, get_fabric_config
            if not is_kql_ready():
                return {"ok": False, "query": query, "detail": "KQL backend not configured — Eventhouse not discovered", "latency_ms": 0}
            cfg = get_fabric_config()
            client = self._get_client()
            db = cfg.kql_db_name
            response = await asyncio.to_thread(client.execute, db, query)
            latency = int((time.time() - t0) * 1000)
            return {"ok": True, "query": query, "detail": "tables accessible", "latency_ms": latency}
        except Exception as e:
            latency = int((time.time() - t0) * 1000)
            return {"ok": False, "query": query, "detail": str(e), "latency_ms": latency}

    def close(self) -> None:
        if self._client:
            self._client = None
