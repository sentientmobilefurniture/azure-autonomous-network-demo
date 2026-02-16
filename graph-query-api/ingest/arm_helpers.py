"""ARM management-plane helpers for provisioning Cosmos containers."""

from __future__ import annotations

import logging
import os

from adapters.cosmos_config import COSMOS_NOSQL_ENDPOINT

logger = logging.getLogger("graph-query-api.ingest")


def _ensure_nosql_containers(
    db_name: str,
    containers_config: list[dict],
    emit,
) -> None:
    """Create NoSQL containers via ARM (management plane).

    The database is assumed to pre-exist (created by Bicep).
    Only containers are created here for speed (~5-10s each vs 20-30s for DB).
    """
    account_name = COSMOS_NOSQL_ENDPOINT.replace("https://", "").split(".")[0]
    sub_id = os.getenv("AZURE_SUBSCRIPTION_ID", "")
    rg = os.getenv("AZURE_RESOURCE_GROUP", "")
    if not sub_id or not rg:
        raise RuntimeError("AZURE_SUBSCRIPTION_ID/AZURE_RESOURCE_GROUP not set")

    from cosmos_helpers import get_mgmt_client
    mgmt = get_mgmt_client()

    for cdef in containers_config:
        cname = cdef["name"]
        pk_path = cdef.get("partition_key", "/id")
        emit("telemetry", f"Creating container '{cname}'...", 15)
        try:
            mgmt.sql_resources.begin_create_update_sql_container(
                rg, account_name, db_name, cname,
                {"resource": {"id": cname, "partitionKey": {"paths": [pk_path], "kind": "Hash"}}},
            ).result()
        except Exception as e:
            if "Conflict" not in str(e):
                raise
            # Container already exists — fine
