"""
Router: Fabric resource provisioning.

Wraps the fabric provisioning reference scripts with SSE progress
streaming. Lives in the API service (port 8000) under /api/fabric/*.

Provides endpoints for:
  - Full provisioning pipeline (workspace → lakehouse → eventhouse → ontology)
  - Individual component provisioning
  - Status checking

All operations stream SSE progress events using the same pattern as
the CosmosDB upload endpoints in graph-query-api.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import os
import tarfile
import tempfile
import uuid
from pathlib import Path
from typing import Any

import yaml
from azure.identity import DefaultAzureCredential
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

logger = logging.getLogger("app.fabric-provision")

router = APIRouter(prefix="/api/fabric", tags=["fabric-provisioning"])

# Concurrency guard — prevents duplicate resource creation from parallel requests
_fabric_provision_lock = asyncio.Lock()


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

FABRIC_API_URL = os.getenv("FABRIC_API_URL", "https://api.fabric.microsoft.com/v1")
FABRIC_SCOPE = os.getenv("FABRIC_SCOPE", "https://api.fabric.microsoft.com/.default")
FABRIC_WORKSPACE_ID = os.getenv("FABRIC_WORKSPACE_ID", "")
FABRIC_WORKSPACE_NAME = os.getenv("FABRIC_WORKSPACE_NAME", "AutonomousNetworkDemo")
FABRIC_CAPACITY_ID = os.getenv("FABRIC_CAPACITY_ID", "")
FABRIC_LAKEHOUSE_NAME = os.getenv("FABRIC_LAKEHOUSE_NAME", "NetworkTopologyLH")
FABRIC_EVENTHOUSE_NAME = os.getenv("FABRIC_EVENTHOUSE_NAME", "NetworkTelemetryEH")
FABRIC_ONTOLOGY_NAME = os.getenv("FABRIC_ONTOLOGY_NAME", "NetworkTopologyOntology")


def _resolve_asset_name(override: str | None, scenario_name: str, asset_type: str) -> str:
    """Resolve a Fabric asset name from explicit override, scenario name, or env default.

    Priority: 1) explicit override  2) scenario-derived  3) env var default
    """
    if override:
        return override
    if scenario_name:
        return f"{scenario_name}-{asset_type}"
    env_map = {
        "lakehouse": FABRIC_LAKEHOUSE_NAME,
        "eventhouse": FABRIC_EVENTHOUSE_NAME,
        "ontology": FABRIC_ONTOLOGY_NAME,
    }
    return env_map.get(asset_type, f"NetworkTopology{asset_type}")


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class FabricProvisionRequest(BaseModel):
    """Full provisioning pipeline request."""
    workspace_name: str = Field(default="", description="Workspace name (defaults to env var)")
    capacity_id: str = Field(default="", description="Fabric capacity ID (defaults to env var)")
    lakehouse_name: str = Field(default="", description="Lakehouse name (defaults to env var)")
    eventhouse_name: str = Field(default="", description="Eventhouse name (defaults to env var)")
    ontology_name: str = Field(default="", description="Ontology name (defaults to env var)")
    scenario_name: str = Field(default="telco-noc-fabric", description="Scenario to provision data from")


class LakehouseRequest(BaseModel):
    """Lakehouse-only provisioning request."""
    workspace_id: str = Field(default="", description="Workspace ID (defaults to env var)")
    lakehouse_name: str = Field(default="", description="Lakehouse name (defaults to env var)")
    scenario_name: str = Field(default="telco-noc-fabric", description="Scenario to provision data from")


class EventhouseRequest(BaseModel):
    """Eventhouse-only provisioning request."""
    workspace_id: str = Field(default="", description="Workspace ID (defaults to env var)")
    eventhouse_name: str = Field(default="", description="Eventhouse name (defaults to env var)")
    scenario_name: str = Field(default="telco-noc-fabric", description="Scenario to provision data from")


class OntologyRequest(BaseModel):
    """Ontology-only provisioning request."""
    workspace_id: str = Field(default="", description="Workspace ID (defaults to env var)")
    ontology_name: str = Field(default="", description="Ontology name (defaults to env var)")
    lakehouse_name: str = Field(default="", description="Lakehouse name for data bindings")


# ---------------------------------------------------------------------------
# Fabric API client (thin async wrapper)
# ---------------------------------------------------------------------------


class AsyncFabricClient:
    """Async wrapper around the Fabric REST API.

    Uses DefaultAzureCredential for authentication. Supports LRO
    (Long Running Operation) polling for create/update operations.
    """

    def __init__(self):
        self._credential = DefaultAzureCredential()
        self._client: Any = None

    async def _get_token(self) -> str:
        token = await asyncio.to_thread(
            self._credential.get_token, FABRIC_SCOPE,
        )
        return token.token

    async def _get_client(self):
        if self._client is None:
            import httpx
            self._client = httpx.AsyncClient(timeout=120.0)
        return self._client

    async def _headers(self) -> dict:
        token = await self._get_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def get(self, path: str, params: dict | None = None) -> dict:
        """GET request to Fabric API."""
        client = await self._get_client()
        headers = await self._headers()
        resp = await client.get(
            f"{FABRIC_API_URL}{path}",
            params=params,
            headers=headers,
        )
        if resp.status_code != 200:
            raise HTTPException(
                status_code=resp.status_code,
                detail=f"Fabric API GET {path} failed: {resp.text[:500]}",
            )
        return resp.json()

    async def post(self, path: str, body: dict | None = None) -> tuple[int, dict, dict]:
        """POST request to Fabric API. Returns (status, headers, body)."""
        client = await self._get_client()
        headers = await self._headers()
        resp = await client.post(
            f"{FABRIC_API_URL}{path}",
            json=body or {},
            headers=headers,
        )
        resp_body = {}
        if resp.text:
            try:
                resp_body = resp.json()
            except Exception:
                resp_body = {"raw": resp.text[:500]}
        return resp.status_code, dict(resp.headers), resp_body

    async def wait_for_lro(
        self,
        response_headers: dict,
        label: str = "operation",
        timeout: int = 300,
    ) -> dict | None:
        """Poll a Long Running Operation until completion.

        Fabric LROs return 202 with an operation ID in the
        x-ms-operation-id header or Location header.
        """
        op_id = response_headers.get("x-ms-operation-id", "")
        if not op_id:
            location = response_headers.get("location", "")
            if "/operations/" in location:
                op_id = location.split("/operations/")[-1].split("?")[0]

        if not op_id:
            logger.warning("No operation ID found for %s LRO", label)
            return None

        logger.info("Polling LRO for %s (operation: %s)", label, op_id)
        poll_interval = 5
        elapsed = 0

        while elapsed < timeout:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            try:
                result = await self.get(f"/operations/{op_id}")
                status = result.get("status", "").lower()

                if status == "succeeded":
                    logger.info("LRO %s completed successfully", label)
                    # Try to get the result
                    try:
                        return await self.get(f"/operations/{op_id}/result")
                    except Exception:
                        return result

                elif status in ("failed", "cancelled"):
                    error = result.get("error", {})
                    raise HTTPException(
                        status_code=500,
                        detail=f"LRO {label} {status}: {error}",
                    )

                logger.debug(
                    "LRO %s status: %s (elapsed: %ds)", label, status, elapsed,
                )
            except HTTPException:
                raise
            except Exception as exc:
                logger.warning("LRO poll error for %s: %s", label, exc)

        raise HTTPException(
            status_code=504,
            detail=f"LRO {label} timed out after {timeout}s",
        )

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None


# ---------------------------------------------------------------------------
# SSE helpers (matches graph-query-api pattern)
# ---------------------------------------------------------------------------


def _sse_event(event_type: str, data: dict) -> str:
    """Format an SSE event string."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


async def sse_provision_stream(work):
    """Wrap an async provisioning generator with standard SSE error handling.

    The work() async generator should yield SSE events and will be
    wrapped with try/except/finally for error handling and client cleanup.
    """
    client = AsyncFabricClient()
    try:
        async for event in work(client):
            yield event
    except HTTPException as exc:
        yield _sse_event("error", {"step": "error", "detail": str(exc.detail), "pct": -1})
    except Exception as exc:
        logger.exception("Fabric provisioning failed")
        yield _sse_event("error", {"step": "error", "detail": f"Unexpected error: {exc}", "pct": -1})
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# Generic find-or-create helper (replaces 4 specific functions)
# ---------------------------------------------------------------------------


async def _find_or_create(
    client: AsyncFabricClient,
    workspace_id: str,
    resource_type: str,
    display_name: str,
    create_body: dict,
    *,
    list_endpoint: str | None = None,
    type_filter: str | None = None,
    fallback_endpoint: str | None = None,
) -> str:
    """Generic find-or-create for Fabric workspace items.

    Args:
        client: Fabric API client
        workspace_id: Target workspace ID (empty for workspace-level operations)
        resource_type: Human label for logging (e.g. "lakehouse")
        display_name: Name to search for / create with
        create_body: POST body for creation
        list_endpoint: Dedicated list endpoint (e.g. "/workspaces/{id}/lakehouses")
        type_filter: Filter /items by type instead of using dedicated endpoint
        fallback_endpoint: Fallback list endpoint if primary fails (e.g. ontology)

    Returns:
        ID of the found or created item
    """
    # --- Find existing ---
    found_id: str | None = None

    if list_endpoint:
        try:
            data = await client.get(list_endpoint)
            for item in data.get("value", []):
                if item.get("displayName") == display_name:
                    found_id = item["id"]
                    break
        except Exception:
            if fallback_endpoint:
                data = await client.get(fallback_endpoint)
                for item in data.get("value", []):
                    if (not type_filter or item.get("type") == type_filter) and item.get("displayName") == display_name:
                        found_id = item["id"]
                        break
    elif type_filter:
        base = f"/workspaces/{workspace_id}/items" if workspace_id else "/items"
        data = await client.get(base)
        for item in data.get("value", []):
            if item.get("type") == type_filter and item.get("displayName") == display_name:
                found_id = item["id"]
                break

    if found_id:
        logger.info("Found existing %s: %s (%s)", resource_type, display_name, found_id)
        return found_id

    # --- Create ---
    create_url = list_endpoint or f"/workspaces/{workspace_id}/items"
    status, headers, resp_body = await client.post(create_url, create_body)

    if status == 201:
        new_id = resp_body.get("id", "")
        logger.info("Created %s: %s (%s)", resource_type, display_name, new_id)
        return new_id
    elif status == 202:
        result = await client.wait_for_lro(headers, f"create {resource_type}")
        return (result or {}).get("id", "")
    else:
        raise HTTPException(
            status_code=status,
            detail=f"Failed to create {resource_type}: {resp_body}",
        )


# Convenience wrappers for backward compatibility
async def _find_or_create_workspace(client: AsyncFabricClient, workspace_name: str, capacity_id: str) -> str:
    body: dict = {"displayName": workspace_name}
    if capacity_id:
        body["capacityId"] = capacity_id
    return await _find_or_create(
        client, "", "workspace", workspace_name, body,
        list_endpoint="/workspaces",
    )


async def _find_or_create_lakehouse(client: AsyncFabricClient, workspace_id: str, lakehouse_name: str) -> str:
    return await _find_or_create(
        client, workspace_id, "lakehouse", lakehouse_name,
        {"displayName": lakehouse_name},
        list_endpoint=f"/workspaces/{workspace_id}/lakehouses",
    )


async def _find_or_create_eventhouse(client: AsyncFabricClient, workspace_id: str, eventhouse_name: str) -> str:
    return await _find_or_create(
        client, workspace_id, "eventhouse", eventhouse_name,
        {"displayName": eventhouse_name},
        list_endpoint=f"/workspaces/{workspace_id}/eventhouses",
        type_filter="Eventhouse",
        fallback_endpoint=f"/workspaces/{workspace_id}/items",
    )


async def _find_or_create_ontology(client: AsyncFabricClient, workspace_id: str, ontology_name: str) -> str:
    return await _find_or_create(
        client, workspace_id, "ontology", ontology_name,
        {"displayName": ontology_name, "description": "Network topology ontology for Autonomous Network Demo"},
        list_endpoint=f"/workspaces/{workspace_id}/ontologies",
        type_filter="Ontology",
        fallback_endpoint=f"/workspaces/{workspace_id}/items",
    )


# ---------------------------------------------------------------------------
# Data path resolution (B0b)
# ---------------------------------------------------------------------------

SCENARIOS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "scenarios"


def _resolve_scenario_data(scenario_name: str) -> dict:
    """Resolve scenario_name → data directory paths and manifest."""
    scenario_dir = SCENARIOS_DIR / scenario_name
    if not scenario_dir.exists():
        raise ValueError(f"Scenario directory not found: {scenario_dir}")

    manifest = yaml.safe_load((scenario_dir / "scenario.yaml").read_text())
    paths = manifest.get("paths", {})

    entities_dir = scenario_dir / paths.get("entities", "data/entities")
    telemetry_dir = scenario_dir / paths.get("telemetry", "data/telemetry")

    return {
        "entities_dir": entities_dir,
        "telemetry_dir": telemetry_dir,
        "manifest": manifest,
    }


# ---------------------------------------------------------------------------
# B1: Lakehouse data upload (CSV → OneLake → delta tables)
# ---------------------------------------------------------------------------

ONELAKE_URL = "https://onelake.dfs.fabric.microsoft.com"

# Table names matching the CSV files in data/entities/
LAKEHOUSE_TABLES = [
    "DimCoreRouter", "DimTransportLink", "DimAggSwitch", "DimBaseStation",
    "DimBGPSession", "DimMPLSPath", "DimService", "DimSLAPolicy",
    "FactMPLSPathHops", "FactServiceDependency",
]


async def _upload_csvs_to_onelake(
    workspace_name: str, lakehouse_name: str, entities_dir: Path,
    on_progress=None,
) -> list[str]:
    """Upload CSV files to Lakehouse Files/ via OneLake ADLS Gen2 API."""
    from azure.storage.filedatalake import DataLakeServiceClient

    credential = DefaultAzureCredential()
    service_client = DataLakeServiceClient(ONELAKE_URL, credential=credential)
    fs_client = service_client.get_file_system_client(workspace_name)
    data_path = f"{lakehouse_name}.Lakehouse/Files"

    uploaded = []
    csv_files = sorted(entities_dir.glob("*.csv"))
    for i, csv_file in enumerate(csv_files):
        table_name = csv_file.stem
        remote_path = f"{data_path}/{csv_file.name}"
        dir_client = fs_client.get_directory_client(data_path)
        file_client = dir_client.get_file_client(csv_file.name)

        with open(csv_file, "rb") as f:
            await asyncio.to_thread(file_client.upload_data, f, overwrite=True)

        uploaded.append(table_name)
        if on_progress:
            pct = 20 + int((i + 1) / len(csv_files) * 20)  # 20-40%
            on_progress(f"Uploaded {csv_file.name}", pct)
        logger.info("Uploaded %s to OneLake", csv_file.name)

    return uploaded


async def _load_delta_tables(
    client: "AsyncFabricClient", workspace_id: str, lakehouse_id: str,
    table_names: list[str], on_progress=None,
) -> None:
    """Load CSV files from Lakehouse Files/ into managed delta tables."""
    for i, table_name in enumerate(table_names):
        relative_path = f"Files/{table_name}.csv"
        body = {
            "relativePath": relative_path,
            "pathType": "File",
            "mode": "Overwrite",
            "formatOptions": {"format": "Csv", "header": True, "delimiter": ","},
        }
        status, headers, resp = await client.post(
            f"/workspaces/{workspace_id}/lakehouses/{lakehouse_id}/tables/{table_name}/load",
            body,
        )
        if status == 202:
            await client.wait_for_lro(headers, f"Load table {table_name}")
        elif status not in (200, 201):
            logger.warning("Table load %s returned %d: %s", table_name, status, resp)

        if on_progress:
            pct = 40 + int((i + 1) / len(table_names) * 5)  # 40-45%
            on_progress(f"Loaded table {table_name}", pct)
        logger.info("Delta table loaded: %s", table_name)


# ---------------------------------------------------------------------------
# B2: Eventhouse KQL table creation + data ingest
# ---------------------------------------------------------------------------

TABLE_SCHEMAS = {
    "AlertStream": {
        "AlertId": "string", "Timestamp": "datetime",
        "SourceNodeId": "string", "SourceNodeType": "string",
        "AlertType": "string", "Severity": "string", "Description": "string",
        "OpticalPowerDbm": "real", "BitErrorRate": "real",
        "CPUUtilPct": "real", "PacketLossPct": "real",
    },
    "LinkTelemetry": {
        "LinkId": "string", "Timestamp": "datetime",
        "UtilizationPct": "real", "OpticalPowerDbm": "real",
        "BitErrorRate": "real", "LatencyMs": "real",
    },
}


async def _discover_kql_database(
    client: "AsyncFabricClient", workspace_id: str, eventhouse_id: str,
) -> dict:
    """Find the default KQL database auto-created with the Eventhouse."""
    data = await client.get(f"/workspaces/{workspace_id}/kqlDatabases")
    for db in data.get("value", []):
        props = db.get("properties", {})
        if props.get("parentEventhouseItemId") == eventhouse_id:
            return db
    dbs = data.get("value", [])
    if dbs:
        return dbs[0]
    raise ValueError("No KQL database found for eventhouse")


async def _create_kql_tables(query_uri: str, db_name: str) -> None:
    """Create KQL tables and CSV ingestion mappings."""
    from azure.kusto.data import KustoClient, KustoConnectionStringBuilder

    credential = DefaultAzureCredential()
    kcsb = KustoConnectionStringBuilder.with_azure_token_credential(query_uri, credential)
    kusto_client = KustoClient(kcsb)

    for table_name, schema in TABLE_SCHEMAS.items():
        columns = ", ".join(f"['{col}']: {dtype}" for col, dtype in schema.items())
        cmd = f".create-merge table {table_name} ({columns})"
        await asyncio.to_thread(kusto_client.execute_mgmt, db_name, cmd)
        logger.info("Created KQL table: %s", table_name)

        # CSV ingestion mapping
        mapping_name = f"{table_name}_csv_mapping"
        mapping_json = ", ".join(
            f'{{"Name": "{col}", "DataType": "{dtype}", "Ordinal": {i}}}'
            for i, (col, dtype) in enumerate(schema.items())
        )
        cmd = (
            f'.create-or-alter table {table_name} ingestion csv mapping '
            f"'{mapping_name}' '[{mapping_json}]'"
        )
        await asyncio.to_thread(kusto_client.execute_mgmt, db_name, cmd)
        logger.info("Created CSV mapping: %s", mapping_name)


async def _ingest_kql_data(
    query_uri: str, db_name: str, telemetry_dir: Path,
) -> None:
    """Ingest CSV files into KQL tables via queued ingestion with inline fallback."""
    from azure.kusto.data import KustoClient, KustoConnectionStringBuilder

    credential = DefaultAzureCredential()

    # Try queued ingestion first
    ingest_uri = query_uri.replace("https://", "https://ingest-")
    try:
        from azure.kusto.ingest import QueuedIngestClient, IngestionProperties
        from azure.kusto.data.data_format import DataFormat

        kcsb_ingest = KustoConnectionStringBuilder.with_azure_token_credential(
            ingest_uri, credential,
        )
        ingest_client = QueuedIngestClient(kcsb_ingest)

        for table_name in TABLE_SCHEMAS:
            csv_path = telemetry_dir / f"{table_name}.csv"
            if not csv_path.exists():
                logger.warning("Skipping %s — file not found", csv_path)
                continue

            mapping_name = f"{table_name}_csv_mapping"
            props = IngestionProperties(
                database=db_name,
                table=table_name,
                data_format=DataFormat.CSV,
                ingestion_mapping_reference=mapping_name,
                ignore_first_record=True,
            )
            await asyncio.to_thread(
                ingest_client.ingest_from_file, str(csv_path),
                ingestion_properties=props,
            )
            logger.info("Queued ingestion: %s", table_name)
        return
    except Exception as e:
        logger.warning("Queued ingestion failed (%s), falling back to inline", e)

    # Fallback: .ingest inline
    kcsb = KustoConnectionStringBuilder.with_azure_token_credential(query_uri, credential)
    kusto_client = KustoClient(kcsb)

    for table_name in TABLE_SCHEMAS:
        csv_path = telemetry_dir / f"{table_name}.csv"
        if not csv_path.exists():
            continue

        with open(csv_path) as f:
            lines = f.readlines()
        if len(lines) < 2:
            continue

        data_lines = [line.strip() for line in lines[1:] if line.strip()]
        batch_size = 500
        for start in range(0, len(data_lines), batch_size):
            batch = data_lines[start:start + batch_size]
            inline_data = "\n".join(batch)
            cmd = f".ingest inline into table {table_name} <|\n{inline_data}"
            await asyncio.to_thread(kusto_client.execute_mgmt, db_name, cmd)
        logger.info("Inline ingested: %s (%d rows)", table_name, len(data_lines))


# ---------------------------------------------------------------------------
# B3: Ontology definition (entity types, relationships, data bindings)
# ---------------------------------------------------------------------------

def _b64(obj: dict) -> str:
    return base64.b64encode(json.dumps(obj).encode()).decode()


def _duuid(seed: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, seed))


def _prop(pid: int, name: str, vtype: str = "String") -> dict:
    return {"id": str(pid), "name": name, "redefines": None,
            "baseTypeNamespaceType": None, "valueType": vtype}


# Entity type IDs
ET_CORE_ROUTER = 1000000000001
ET_TRANSPORT_LINK = 1000000000002
ET_AGG_SWITCH = 1000000000003
ET_BASE_STATION = 1000000000004
ET_BGP_SESSION = 1000000000005
ET_MPLS_PATH = 1000000000006
ET_SERVICE = 1000000000007
ET_SLA_POLICY = 1000000000008

# Property IDs
P_ROUTER_ID = 2000000000001; P_ROUTER_CITY = 2000000000003
P_ROUTER_REGION = 2000000000004; P_ROUTER_VENDOR = 2000000000005; P_ROUTER_MODEL = 2000000000006
P_LINK_ID = 2000000000011; P_LINK_TYPE = 2000000000013
P_CAPACITY_GBPS = 2000000000014; P_SOURCE_ROUTER_ID = 2000000000015; P_TARGET_ROUTER_ID = 2000000000016
P_SWITCH_ID = 2000000000031; P_SWITCH_CITY = 2000000000033; P_UPLINK_ROUTER_ID = 2000000000034
P_STATION_ID = 2000000000041; P_STATION_TYPE = 2000000000043
P_STATION_AGG_SWITCH = 2000000000044; P_STATION_CITY = 2000000000045
P_SESSION_ID = 2000000000051; P_PEER_A_ROUTER = 2000000000052; P_PEER_B_ROUTER = 2000000000053
P_AS_NUMBER_A = 2000000000054; P_AS_NUMBER_B = 2000000000055
P_PATH_ID = 2000000000061; P_PATH_TYPE = 2000000000063
P_SERVICE_ID = 2000000000071; P_SERVICE_TYPE = 2000000000073; P_CUSTOMER_NAME = 2000000000074
P_CUSTOMER_COUNT = 2000000000075; P_ACTIVE_USERS = 2000000000076
P_SLA_POLICY_ID = 2000000000081; P_SLA_SERVICE_ID = 2000000000082
P_AVAILABILITY_PCT = 2000000000083; P_MAX_LATENCY_MS = 2000000000084
P_PENALTY_PER_HOUR = 2000000000085; P_SLA_TIER = 2000000000086

# Relationship type IDs
R_CONNECTS_TO = 3000000000001; R_AGGREGATES_TO = 3000000000002; R_BACKHAULS_VIA = 3000000000003
R_ROUTES_VIA = 3000000000004; R_DEPENDS_ON = 3000000000005; R_GOVERNED_BY = 3000000000006
R_PEERS_OVER = 3000000000007


def _entity_type(et_id, name, props, id_prop_id):
    return {
        "id": str(et_id), "namespace": "usertypes", "baseEntityTypeId": None,
        "name": name, "entityIdParts": [str(id_prop_id)],
        "displayNamePropertyId": str(id_prop_id), "namespaceType": "Custom",
        "visibility": "Visible", "properties": props, "timeseriesProperties": [],
    }


ENTITY_TYPES = [
    _entity_type(ET_CORE_ROUTER, "CoreRouter", [
        _prop(P_ROUTER_ID, "RouterId"), _prop(P_ROUTER_CITY, "City"),
        _prop(P_ROUTER_REGION, "Region"), _prop(P_ROUTER_VENDOR, "Vendor"),
        _prop(P_ROUTER_MODEL, "Model"),
    ], P_ROUTER_ID),
    _entity_type(ET_TRANSPORT_LINK, "TransportLink", [
        _prop(P_LINK_ID, "LinkId"), _prop(P_LINK_TYPE, "LinkType"),
        _prop(P_CAPACITY_GBPS, "CapacityGbps", "BigInt"),
        _prop(P_SOURCE_ROUTER_ID, "SourceRouterId"), _prop(P_TARGET_ROUTER_ID, "TargetRouterId"),
    ], P_LINK_ID),
    _entity_type(ET_AGG_SWITCH, "AggSwitch", [
        _prop(P_SWITCH_ID, "SwitchId"), _prop(P_SWITCH_CITY, "City"),
        _prop(P_UPLINK_ROUTER_ID, "UplinkRouterId"),
    ], P_SWITCH_ID),
    _entity_type(ET_BASE_STATION, "BaseStation", [
        _prop(P_STATION_ID, "StationId"), _prop(P_STATION_TYPE, "StationType"),
        _prop(P_STATION_AGG_SWITCH, "AggSwitchId"), _prop(P_STATION_CITY, "City"),
    ], P_STATION_ID),
    _entity_type(ET_BGP_SESSION, "BGPSession", [
        _prop(P_SESSION_ID, "SessionId"), _prop(P_PEER_A_ROUTER, "PeerARouterId"),
        _prop(P_PEER_B_ROUTER, "PeerBRouterId"),
        _prop(P_AS_NUMBER_A, "ASNumberA", "BigInt"), _prop(P_AS_NUMBER_B, "ASNumberB", "BigInt"),
    ], P_SESSION_ID),
    _entity_type(ET_MPLS_PATH, "MPLSPath", [
        _prop(P_PATH_ID, "PathId"), _prop(P_PATH_TYPE, "PathType"),
    ], P_PATH_ID),
    _entity_type(ET_SERVICE, "Service", [
        _prop(P_SERVICE_ID, "ServiceId"), _prop(P_SERVICE_TYPE, "ServiceType"),
        _prop(P_CUSTOMER_NAME, "CustomerName"),
        _prop(P_CUSTOMER_COUNT, "CustomerCount", "BigInt"),
        _prop(P_ACTIVE_USERS, "ActiveUsers", "BigInt"),
    ], P_SERVICE_ID),
    _entity_type(ET_SLA_POLICY, "SLAPolicy", [
        _prop(P_SLA_POLICY_ID, "SLAPolicyId"), _prop(P_SLA_SERVICE_ID, "ServiceId"),
        _prop(P_AVAILABILITY_PCT, "AvailabilityPct", "Double"),
        _prop(P_MAX_LATENCY_MS, "MaxLatencyMs", "BigInt"),
        _prop(P_PENALTY_PER_HOUR, "PenaltyPerHourUSD", "BigInt"),
        _prop(P_SLA_TIER, "Tier"),
    ], P_SLA_POLICY_ID),
]

RELATIONSHIP_TYPES = [
    {"id": str(R_CONNECTS_TO), "namespace": "usertypes", "name": "connects_to", "namespaceType": "Custom",
     "source": {"entityTypeId": str(ET_TRANSPORT_LINK)}, "target": {"entityTypeId": str(ET_CORE_ROUTER)}},
    {"id": str(R_AGGREGATES_TO), "namespace": "usertypes", "name": "aggregates_to", "namespaceType": "Custom",
     "source": {"entityTypeId": str(ET_AGG_SWITCH)}, "target": {"entityTypeId": str(ET_CORE_ROUTER)}},
    {"id": str(R_BACKHAULS_VIA), "namespace": "usertypes", "name": "backhauls_via", "namespaceType": "Custom",
     "source": {"entityTypeId": str(ET_BASE_STATION)}, "target": {"entityTypeId": str(ET_AGG_SWITCH)}},
    {"id": str(R_ROUTES_VIA), "namespace": "usertypes", "name": "routes_via", "namespaceType": "Custom",
     "source": {"entityTypeId": str(ET_MPLS_PATH)}, "target": {"entityTypeId": str(ET_TRANSPORT_LINK)}},
    {"id": str(R_DEPENDS_ON), "namespace": "usertypes", "name": "depends_on", "namespaceType": "Custom",
     "source": {"entityTypeId": str(ET_SERVICE)}, "target": {"entityTypeId": str(ET_MPLS_PATH)}},
    {"id": str(R_GOVERNED_BY), "namespace": "usertypes", "name": "governed_by", "namespaceType": "Custom",
     "source": {"entityTypeId": str(ET_SLA_POLICY)}, "target": {"entityTypeId": str(ET_SERVICE)}},
    {"id": str(R_PEERS_OVER), "namespace": "usertypes", "name": "peers_over", "namespaceType": "Custom",
     "source": {"entityTypeId": str(ET_BGP_SESSION)}, "target": {"entityTypeId": str(ET_CORE_ROUTER)}},
]


def _lakehouse_binding(seed, table, bindings, workspace_id, lakehouse_id):
    return {
        "id": _duuid(seed),
        "dataBindingConfiguration": {
            "dataBindingType": "NonTimeSeries",
            "propertyBindings": [
                {"sourceColumnName": col, "targetPropertyId": str(pid)}
                for col, pid in bindings
            ],
            "sourceTableProperties": {
                "sourceType": "LakehouseTable",
                "workspaceId": workspace_id,
                "itemId": lakehouse_id,
                "sourceTableName": table,
            },
        },
    }


def _ctx(seed, table, src_bindings, tgt_bindings, workspace_id, lakehouse_id):
    return {
        "id": _duuid(seed),
        "dataBindingTable": {
            "sourceType": "LakehouseTable",
            "workspaceId": workspace_id,
            "itemId": lakehouse_id,
            "sourceTableName": table,
        },
        "sourceKeyRefBindings": [
            {"sourceColumnName": col, "targetPropertyId": str(pid)}
            for col, pid in src_bindings
        ],
        "targetKeyRefBindings": [
            {"sourceColumnName": col, "targetPropertyId": str(pid)}
            for col, pid in tgt_bindings
        ],
    }


def _build_ontology_definition(
    workspace_id: str, lakehouse_id: str, ontology_name: str,
) -> list[dict]:
    """Build the full ontology definition parts array."""
    lb = lambda seed, table, bindings: _lakehouse_binding(
        seed, table, bindings, workspace_id, lakehouse_id,
    )
    c = lambda seed, table, src, tgt: _ctx(
        seed, table, src, tgt, workspace_id, lakehouse_id,
    )

    # Static data bindings
    bindings: dict[int, list[dict]] = {
        ET_CORE_ROUTER: [lb("CoreRouter-static", "DimCoreRouter", [
            ("RouterId", P_ROUTER_ID), ("City", P_ROUTER_CITY),
            ("Region", P_ROUTER_REGION), ("Vendor", P_ROUTER_VENDOR), ("Model", P_ROUTER_MODEL),
        ])],
        ET_TRANSPORT_LINK: [lb("TransportLink-static", "DimTransportLink", [
            ("LinkId", P_LINK_ID), ("LinkType", P_LINK_TYPE),
            ("CapacityGbps", P_CAPACITY_GBPS),
            ("SourceRouterId", P_SOURCE_ROUTER_ID), ("TargetRouterId", P_TARGET_ROUTER_ID),
        ])],
        ET_AGG_SWITCH: [lb("AggSwitch-static", "DimAggSwitch", [
            ("SwitchId", P_SWITCH_ID), ("City", P_SWITCH_CITY), ("UplinkRouterId", P_UPLINK_ROUTER_ID),
        ])],
        ET_BASE_STATION: [lb("BaseStation-static", "DimBaseStation", [
            ("StationId", P_STATION_ID), ("StationType", P_STATION_TYPE),
            ("AggSwitchId", P_STATION_AGG_SWITCH), ("City", P_STATION_CITY),
        ])],
        ET_BGP_SESSION: [lb("BGPSession-static", "DimBGPSession", [
            ("SessionId", P_SESSION_ID), ("PeerARouterId", P_PEER_A_ROUTER),
            ("PeerBRouterId", P_PEER_B_ROUTER), ("ASNumberA", P_AS_NUMBER_A), ("ASNumberB", P_AS_NUMBER_B),
        ])],
        ET_MPLS_PATH: [lb("MPLSPath-static", "DimMPLSPath", [
            ("PathId", P_PATH_ID), ("PathType", P_PATH_TYPE),
        ])],
        ET_SERVICE: [lb("Service-static", "DimService", [
            ("ServiceId", P_SERVICE_ID), ("ServiceType", P_SERVICE_TYPE),
            ("CustomerName", P_CUSTOMER_NAME), ("CustomerCount", P_CUSTOMER_COUNT),
            ("ActiveUsers", P_ACTIVE_USERS),
        ])],
        ET_SLA_POLICY: [lb("SLAPolicy-static", "DimSLAPolicy", [
            ("SLAPolicyId", P_SLA_POLICY_ID), ("ServiceId", P_SLA_SERVICE_ID),
            ("AvailabilityPct", P_AVAILABILITY_PCT), ("MaxLatencyMs", P_MAX_LATENCY_MS),
            ("PenaltyPerHourUSD", P_PENALTY_PER_HOUR), ("Tier", P_SLA_TIER),
        ])],
    }

    # Contextualizations (relationship data bindings)
    contextualizations: dict[int, list[dict]] = {
        R_CONNECTS_TO: [
            c("connects_to-source", "DimTransportLink", [("LinkId", P_LINK_ID)], [("SourceRouterId", P_ROUTER_ID)]),
            c("connects_to-target", "DimTransportLink", [("LinkId", P_LINK_ID)], [("TargetRouterId", P_ROUTER_ID)]),
        ],
        R_AGGREGATES_TO: [c("aggregates_to", "DimAggSwitch", [("SwitchId", P_SWITCH_ID)], [("UplinkRouterId", P_ROUTER_ID)])],
        R_BACKHAULS_VIA: [c("backhauls_via", "DimBaseStation", [("StationId", P_STATION_ID)], [("AggSwitchId", P_SWITCH_ID)])],
        R_ROUTES_VIA: [c("routes_via", "FactMPLSPathHops", [("PathId", P_PATH_ID)], [("NodeId", P_LINK_ID)])],
        R_DEPENDS_ON: [c("depends_on", "FactServiceDependency", [("ServiceId", P_SERVICE_ID)], [("DependsOnId", P_PATH_ID)])],
        R_GOVERNED_BY: [c("governed_by", "DimSLAPolicy", [("SLAPolicyId", P_SLA_POLICY_ID)], [("ServiceId", P_SERVICE_ID)])],
        R_PEERS_OVER: [
            c("peers_over-a", "DimBGPSession", [("SessionId", P_SESSION_ID)], [("PeerARouterId", P_ROUTER_ID)]),
            c("peers_over-b", "DimBGPSession", [("SessionId", P_SESSION_ID)], [("PeerBRouterId", P_ROUTER_ID)]),
        ],
    }

    # Build parts array
    parts = [
        {"path": ".platform", "payload": _b64({"metadata": {"type": "Ontology", "displayName": ontology_name}}),
         "payloadType": "InlineBase64"},
        {"path": "definition.json", "payload": _b64({}), "payloadType": "InlineBase64"},
    ]

    for et in ENTITY_TYPES:
        et_id = et["id"]
        parts.append({"path": f"EntityTypes/{et_id}/definition.json", "payload": _b64(et), "payloadType": "InlineBase64"})
        for binding in bindings.get(int(et_id), []):
            parts.append({"path": f"EntityTypes/{et_id}/DataBindings/{binding['id']}.json",
                          "payload": _b64(binding), "payloadType": "InlineBase64"})

    for rel in RELATIONSHIP_TYPES:
        rel_id = rel["id"]
        parts.append({"path": f"RelationshipTypes/{rel_id}/definition.json", "payload": _b64(rel), "payloadType": "InlineBase64"})
        for ctx_item in contextualizations.get(int(rel_id), []):
            parts.append({"path": f"RelationshipTypes/{rel_id}/Contextualizations/{ctx_item['id']}.json",
                          "payload": _b64(ctx_item), "payloadType": "InlineBase64"})

    return parts


async def _apply_ontology_definition(
    client: "AsyncFabricClient", workspace_id: str, ontology_id: str, parts: list[dict],
) -> None:
    """Apply ontology definition via updateDefinition API."""
    body = {"definition": {"parts": parts}}
    status, headers, resp = await client.post(
        f"/workspaces/{workspace_id}/ontologies/{ontology_id}/updateDefinition",
        body,
    )
    if status == 202:
        await client.wait_for_lro(headers, "Update Ontology definition", timeout=600)
    elif status not in (200, 201):
        raise HTTPException(status_code=status, detail=f"Ontology update failed: {resp}")


# ---------------------------------------------------------------------------
# B4: Graph Model auto-discovery
# ---------------------------------------------------------------------------

async def _discover_graph_model(
    client: "AsyncFabricClient", workspace_id: str, ontology_name: str,
) -> str | None:
    """Find the auto-created Graph Model in the workspace."""
    try:
        data = await client.get(f"/workspaces/{workspace_id}/items")
        for item in data.get("value", []):
            if item.get("type") in ("GraphModel", "Graph"):
                if ontology_name.lower() in item["displayName"].lower():
                    return item["id"]
        # Fallback: return first graph item
        for item in data.get("value", []):
            if item.get("type") in ("GraphModel", "Graph"):
                return item["id"]
    except Exception as e:
        logger.warning("Graph Model discovery failed: %s", e)
    return None


def _write_env_var(key: str, value: str) -> None:
    """Write a key=value pair to azure_config.env (create or update)."""
    import re
    env_file = Path(__file__).resolve().parent.parent.parent.parent / "azure_config.env"
    content = env_file.read_text() if env_file.exists() else ""
    pattern = rf"^{re.escape(key)}=.*$"
    if re.search(pattern, content, re.MULTILINE):
        content = re.sub(pattern, f"{key}={value}", content, flags=re.MULTILINE)
    else:
        content = content.rstrip("\n") + f"\n{key}={value}\n"
    env_file.write_text(content)
    logger.info("Wrote %s=%s to azure_config.env", key, value)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/provision")
async def provision_fabric_resources(req: FabricProvisionRequest):
    """One-click Fabric provisioning pipeline.

    Steps:
      1. Create/find workspace (with capacity)
      2. Create Lakehouse + upload CSV data
      3. Create Eventhouse + ingest telemetry
      4. Create Ontology (graph model)

    Streams SSE progress events.
    """
    if _fabric_provision_lock.locked():
        raise HTTPException(
            status_code=409,
            detail="Fabric provisioning already in progress",
        )

    workspace_name = req.workspace_name or FABRIC_WORKSPACE_NAME
    capacity_id = req.capacity_id or FABRIC_CAPACITY_ID
    lakehouse_name = req.lakehouse_name or FABRIC_LAKEHOUSE_NAME
    eventhouse_name = req.eventhouse_name or FABRIC_EVENTHOUSE_NAME
    ontology_name = req.ontology_name or FABRIC_ONTOLOGY_NAME

    async def stream():
        async with _fabric_provision_lock:
            client = AsyncFabricClient()
            completed_steps: list[str] = []
            try:
                # B0b: Resolve scenario data paths
                scenario_data = _resolve_scenario_data(req.scenario_name)
                manifest = scenario_data["manifest"]
                graph_connector = manifest.get("data_sources", {}).get("graph", {}).get("connector", "")
                telemetry_connector = manifest.get("data_sources", {}).get("telemetry", {}).get("connector", "")

                # Step 1: Workspace — use existing ID if available, else find/create
                yield _sse_event("progress", {
                    "step": "workspace", "detail": "Setting up workspace…", "pct": 5,
                })
                if FABRIC_WORKSPACE_ID:
                    workspace_id = FABRIC_WORKSPACE_ID
                    logger.info("Using FABRIC_WORKSPACE_ID from env: %s", workspace_id)
                else:
                    workspace_id = await _find_or_create_workspace(
                        client, workspace_name, capacity_id,
                    )
                completed_steps.append("workspace")
                yield _sse_event("progress", {
                    "step": "workspace", "detail": f"Workspace ready: {workspace_id}", "pct": 10,
                })

                lakehouse_id = None
                eventhouse_id = None
                ontology_id = None
                graph_model_id = None

                # B5: Conditional — Lakehouse + Ontology if graph is fabric-gql
                if graph_connector == "fabric-gql":
                    # Step 2: Lakehouse
                    yield _sse_event("progress", {
                        "step": "lakehouse", "detail": "Preparing data storage…", "pct": 12,
                    })
                    lakehouse_id = await _find_or_create_lakehouse(
                        client, workspace_id, lakehouse_name,
                    )
                    completed_steps.append("lakehouse")
                    yield _sse_event("progress", {
                        "step": "lakehouse", "detail": f"Lakehouse ready: {lakehouse_id}", "pct": 20,
                    })

                    # Step 3: Upload CSVs to OneLake
                    yield _sse_event("progress", {
                        "step": "upload", "detail": "Uploading graph data…", "pct": 22,
                    })
                    entities_dir = scenario_data["entities_dir"]
                    uploaded = await _upload_csvs_to_onelake(
                        workspace_name, lakehouse_name, entities_dir,
                        on_progress=lambda msg, pct: None,  # SSE progress handled below
                    )
                    completed_steps.append("upload")
                    yield _sse_event("progress", {
                        "step": "upload",
                        "detail": f"Uploaded {len(uploaded)} files",
                        "pct": 40,
                    })

                    # Step 4: Load delta tables
                    yield _sse_event("progress", {
                        "step": "tables", "detail": "Configuring data tables…", "pct": 42,
                    })
                    await _load_delta_tables(client, workspace_id, lakehouse_id, uploaded)
                    completed_steps.append("tables")
                    yield _sse_event("progress", {
                        "step": "tables", "detail": "Delta tables loaded", "pct": 45,
                    })

                # B5: Conditional — Eventhouse if telemetry is fabric-kql
                if telemetry_connector == "fabric-kql":
                    yield _sse_event("progress", {
                        "step": "eventhouse", "detail": "Setting up telemetry database…", "pct": 48,
                    })
                    eventhouse_id = await _find_or_create_eventhouse(
                        client, workspace_id, eventhouse_name,
                    )
                    completed_steps.append("eventhouse")
                    yield _sse_event("progress", {
                        "step": "eventhouse", "detail": f"Eventhouse ready: {eventhouse_id}", "pct": 50,
                    })

                    # Discover KQL database
                    kql_db = await _discover_kql_database(client, workspace_id, eventhouse_id)
                    kql_db_name = kql_db["displayName"]
                    query_uri = kql_db.get("properties", {}).get("queryServiceUri", "")

                    if query_uri:
                        yield _sse_event("progress", {
                            "step": "kql_tables", "detail": "Loading telemetry data…", "pct": 55,
                        })
                        await _create_kql_tables(query_uri, kql_db_name)
                        await _ingest_kql_data(query_uri, kql_db_name, scenario_data["telemetry_dir"])
                        completed_steps.append("kql_ingest")
                        yield _sse_event("progress", {
                            "step": "kql_tables", "detail": "Telemetry data loaded", "pct": 65,
                        })
                    else:
                        logger.warning("No query URI for Eventhouse — KQL tables skipped")

                # Ontology (if graph is fabric-gql)
                if graph_connector == "fabric-gql":
                    yield _sse_event("progress", {
                        "step": "ontology", "detail": "Building graph ontology…", "pct": 68,
                    })
                    ontology_id = await _find_or_create_ontology(
                        client, workspace_id, ontology_name,
                    )
                    completed_steps.append("ontology_create")

                    # Apply full definition
                    yield _sse_event("progress", {
                        "step": "ontology_def", "detail": "Indexing — this may take a minute…", "pct": 75,
                    })
                    parts = _build_ontology_definition(workspace_id, lakehouse_id, ontology_name)
                    await _apply_ontology_definition(client, workspace_id, ontology_id, parts)
                    completed_steps.append("ontology_def")
                    yield _sse_event("progress", {
                        "step": "ontology_def", "detail": "Ontology indexed", "pct": 88,
                    })

                    # B4: Graph Model discovery
                    yield _sse_event("progress", {
                        "step": "graph_model", "detail": "Discovering graph model…", "pct": 92,
                    })
                    graph_model_id = await _discover_graph_model(client, workspace_id, ontology_name)
                    if graph_model_id:
                        completed_steps.append("graph_model")
                        # Write to env file
                        _write_env_var("FABRIC_GRAPH_MODEL_ID", graph_model_id)
                        yield _sse_event("progress", {
                            "step": "graph_model", "detail": f"Graph Model: {graph_model_id}", "pct": 98,
                        })
                    else:
                        yield _sse_event("progress", {
                            "step": "graph_model",
                            "detail": "Graph Model not yet visible — check Fabric portal",
                            "pct": 95,
                        })

                # Complete
                yield _sse_event("progress", {
                    "step": "done", "detail": "Almost done… ✓", "pct": 100,
                })
                yield _sse_event("complete", {
                    "workspace_id": workspace_id,
                    "lakehouse_id": lakehouse_id,
                    "eventhouse_id": eventhouse_id,
                    "ontology_id": ontology_id,
                    "graph_model_id": graph_model_id,
                    "completed": completed_steps,
                    "message": "Fabric provisioning complete.",
                })

            except HTTPException as exc:
                yield _sse_event("error", {
                    "step": "error",
                    "detail": str(exc.detail),
                    "error": str(exc.detail),
                    "pct": -1,
                    "retry_from": completed_steps[-1] if completed_steps else None,
                    "completed": completed_steps,
                })
            except Exception as exc:
                logger.exception("Fabric provisioning failed")
                yield _sse_event("error", {
                    "step": "error",
                    "detail": f"Unexpected error: {exc}",
                    "error": f"Unexpected error: {exc}",
                    "pct": -1,
                    "retry_from": completed_steps[-1] if completed_steps else None,
                    "completed": completed_steps,
                })
            finally:
                await client.close()

    return EventSourceResponse(stream())


@router.post("/provision/lakehouse")
async def provision_lakehouse(req: LakehouseRequest):
    """Provision just the Lakehouse component.

    Streams SSE progress events.
    """
    workspace_id = req.workspace_id or FABRIC_WORKSPACE_ID
    lakehouse_name = req.lakehouse_name or FABRIC_LAKEHOUSE_NAME

    if not workspace_id:
        raise HTTPException(
            status_code=400,
            detail="workspace_id is required (set FABRIC_WORKSPACE_ID or pass in request)",
        )

    async def _work(client):
        yield _sse_event("progress", {
            "step": "lakehouse",
            "detail": f"Finding or creating lakehouse '{lakehouse_name}'...",
            "pct": 10,
        })
        lakehouse_id = await _find_or_create_lakehouse(
            client, workspace_id, lakehouse_name,
        )
        yield _sse_event("complete", {
            "lakehouse_id": lakehouse_id,
            "message": f"Lakehouse '{lakehouse_name}' ready.",
        })

    return EventSourceResponse(sse_provision_stream(_work))


@router.post("/provision/eventhouse")
async def provision_eventhouse(req: EventhouseRequest):
    """Provision just the Eventhouse component.

    Streams SSE progress events.
    """
    workspace_id = req.workspace_id or FABRIC_WORKSPACE_ID
    eventhouse_name = req.eventhouse_name or FABRIC_EVENTHOUSE_NAME

    if not workspace_id:
        raise HTTPException(
            status_code=400,
            detail="workspace_id is required (set FABRIC_WORKSPACE_ID or pass in request)",
        )

    async def _work(client):
        yield _sse_event("progress", {
            "step": "eventhouse",
            "detail": f"Finding or creating eventhouse '{eventhouse_name}'...",
            "pct": 10,
        })
        eventhouse_id = await _find_or_create_eventhouse(
            client, workspace_id, eventhouse_name,
        )
        yield _sse_event("complete", {
            "eventhouse_id": eventhouse_id,
            "message": f"Eventhouse '{eventhouse_name}' ready.",
        })

    return EventSourceResponse(sse_provision_stream(_work))


@router.post("/provision/ontology")
async def provision_ontology(req: OntologyRequest):
    """Provision just the Ontology component.

    Streams SSE progress events.
    """
    workspace_id = req.workspace_id or FABRIC_WORKSPACE_ID
    ontology_name = req.ontology_name or FABRIC_ONTOLOGY_NAME

    if not workspace_id:
        raise HTTPException(
            status_code=400,
            detail="workspace_id is required (set FABRIC_WORKSPACE_ID or pass in request)",
        )

    async def _work(client):
        yield _sse_event("progress", {
            "step": "ontology",
            "detail": f"Finding or creating ontology '{ontology_name}'...",
            "pct": 10,
        })
        ontology_id = await _find_or_create_ontology(
            client, workspace_id, ontology_name,
        )
        yield _sse_event("complete", {
            "ontology_id": ontology_id,
            "message": f"Ontology '{ontology_name}' ready.",
        })

    return EventSourceResponse(sse_provision_stream(_work))


# ---------------------------------------------------------------------------
# Graph tarball → Fabric pipeline (V11E Task 6)
# ---------------------------------------------------------------------------


@router.post("/provision/graph")
async def provision_graph_from_tarball(
    file: UploadFile = File(...),
    workspace_id: str = Form(...),
    workspace_name: str = Form(...),
    lakehouse_name: str = Form(""),
    ontology_name: str = Form(""),
    scenario_name: str = Form(""),
):
    """Upload a graph tarball and run the full Lakehouse → Ontology → Graph Model pipeline.

    Accepts a .tar.gz containing entity CSVs (same layout as data/scenarios/*/entities/).
    Streams SSE progress events.
    """
    # Resolve asset names: explicit override > scenario-derived > env default
    lakehouse_name = _resolve_asset_name(lakehouse_name, scenario_name, "lakehouse")
    ontology_name = _resolve_asset_name(ontology_name, scenario_name, "ontology")
    if not file.filename or not (
        file.filename.endswith(".tar.gz") or file.filename.endswith(".tgz")
    ):
        raise HTTPException(400, "File must be a .tar.gz archive")

    if _fabric_provision_lock.locked():
        raise HTTPException(
            status_code=409,
            detail="Fabric provisioning already in progress",
        )

    content = await file.read()
    logger.info(
        "Graph tarball upload: %s (%d bytes), workspace=%s",
        file.filename, len(content), workspace_id,
    )

    async def _work(client: AsyncFabricClient):
        async with _fabric_provision_lock:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmppath = Path(tmpdir)

                # Step 1: Extract tarball
                yield _sse_event("progress", {
                    "step": "extract", "detail": "Extracting graph tarball…", "pct": 5,
                })
                with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as tar:
                    tar.extractall(tmppath, filter="data")

                # Find entities directory — check common layouts
                entities_dir = None
                for candidate in [
                    tmppath / "data" / "entities",
                    tmppath / "entities",
                ]:
                    if candidate.is_dir() and list(candidate.glob("*.csv")):
                        entities_dir = candidate
                        break
                # Also check one level down (tarball may have a root folder)
                if entities_dir is None:
                    for sub in tmppath.iterdir():
                        if sub.is_dir():
                            for candidate in [
                                sub / "data" / "entities",
                                sub / "entities",
                            ]:
                                if candidate.is_dir() and list(candidate.glob("*.csv")):
                                    entities_dir = candidate
                                    break
                        if entities_dir:
                            break

                if entities_dir is None:
                    # Fallback: if CSVs are at root of the tarball
                    csv_files = list(tmppath.glob("*.csv"))
                    if csv_files:
                        entities_dir = tmppath
                    else:
                        raise HTTPException(400, "No entity CSV files found in tarball")

                csv_count = len(list(entities_dir.glob("*.csv")))
                yield _sse_event("progress", {
                    "step": "extract",
                    "detail": f"Found {csv_count} CSV files",
                    "pct": 10,
                })

                # Step 2: Find or create Lakehouse
                yield _sse_event("progress", {
                    "step": "lakehouse", "detail": "Preparing Lakehouse…", "pct": 12,
                })
                lakehouse_id = await _find_or_create_lakehouse(
                    client, workspace_id, lakehouse_name,
                )
                yield _sse_event("progress", {
                    "step": "lakehouse",
                    "detail": f"Lakehouse ready: {lakehouse_id}",
                    "pct": 18,
                })

                # Step 3: Upload CSVs to OneLake
                yield _sse_event("progress", {
                    "step": "upload", "detail": "Uploading CSVs to Lakehouse…", "pct": 20,
                })
                uploaded = await _upload_csvs_to_onelake(
                    workspace_name, lakehouse_name, entities_dir,
                )
                yield _sse_event("progress", {
                    "step": "upload",
                    "detail": f"Uploaded {len(uploaded)} files to OneLake",
                    "pct": 40,
                })

                # Step 4: Load delta tables
                yield _sse_event("progress", {
                    "step": "tables", "detail": "Loading delta tables…", "pct": 42,
                })
                await _load_delta_tables(client, workspace_id, lakehouse_id, uploaded)
                yield _sse_event("progress", {
                    "step": "tables", "detail": "Delta tables loaded", "pct": 50,
                })

                # Step 5: Create/update Ontology
                yield _sse_event("progress", {
                    "step": "ontology", "detail": "Creating ontology…", "pct": 55,
                })
                ontology_id = await _find_or_create_ontology(
                    client, workspace_id, ontology_name,
                )
                yield _sse_event("progress", {
                    "step": "ontology",
                    "detail": f"Ontology ready: {ontology_id}",
                    "pct": 60,
                })

                # Step 6: Build and apply ontology definition
                yield _sse_event("progress", {
                    "step": "ontology_def", "detail": "Building ontology definition…", "pct": 65,
                })
                parts = _build_ontology_definition(workspace_id, lakehouse_id, ontology_name)
                await _apply_ontology_definition(client, workspace_id, ontology_id, parts)
                yield _sse_event("progress", {
                    "step": "ontology_def",
                    "detail": "Ontology definition applied",
                    "pct": 85,
                })

                # Step 7: Discover Graph Model
                yield _sse_event("progress", {
                    "step": "graph_model", "detail": "Discovering graph model…", "pct": 88,
                })
                graph_model_id = await _discover_graph_model(
                    client, workspace_id, ontology_name,
                )
                yield _sse_event("progress", {
                    "step": "graph_model",
                    "detail": f"Graph Model: {graph_model_id or 'pending'}",
                    "pct": 95,
                })

                # Complete — include fabric_resources for upstream to persist
                yield _sse_event("complete", {
                    "lakehouse_id": lakehouse_id,
                    "ontology_id": ontology_id,
                    "graph_model_id": graph_model_id,
                    "tables": uploaded,
                    "fabric_resources": {
                        "workspace_id": workspace_id,
                        "lakehouse_id": lakehouse_id,
                        "lakehouse_name": lakehouse_name,
                        "ontology_name": ontology_name,
                        "graph_model_id": graph_model_id or "",
                    },
                    "message": "Graph data loaded into Fabric successfully.",
                })

    return EventSourceResponse(sse_provision_stream(_work))


# ---------------------------------------------------------------------------
# Telemetry tarball → Fabric Eventhouse pipeline (V11E3)
# ---------------------------------------------------------------------------


@router.post("/provision/telemetry")
async def provision_telemetry_fabric(
    file: UploadFile = File(...),
    workspace_id: str = Form(...),
    workspace_name: str = Form(""),
    scenario_name: str = Form(""),
):
    """Upload a telemetry tarball and provision Eventhouse + KQL tables.

    Accepts a .tar.gz containing telemetry CSVs (AlertStream.csv, LinkTelemetry.csv).
    Streams SSE progress events.
    """
    if not file.filename or not (
        file.filename.endswith(".tar.gz") or file.filename.endswith(".tgz")
    ):
        raise HTTPException(400, "File must be a .tar.gz archive")

    if _fabric_provision_lock.locked():
        raise HTTPException(
            status_code=409,
            detail="Fabric provisioning already in progress",
        )

    content = await file.read()
    eventhouse_name = _resolve_asset_name("", scenario_name, "eventhouse")
    logger.info(
        "Telemetry tarball upload: %s (%d bytes), workspace=%s, eventhouse=%s",
        file.filename, len(content), workspace_id, eventhouse_name,
    )

    async def _work(client: AsyncFabricClient):
        async with _fabric_provision_lock:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmppath = Path(tmpdir)

                # Step 1: Extract tarball
                yield _sse_event("progress", {
                    "step": "telemetry", "detail": "Extracting telemetry tarball…", "pct": 5,
                })
                with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as tar:
                    tar.extractall(tmppath, filter="data")

                # Find telemetry directory containing CSV files
                telemetry_dir = None
                for candidate in [
                    tmppath / "data" / "telemetry",
                    tmppath / "telemetry",
                ]:
                    if candidate.is_dir() and list(candidate.glob("*.csv")):
                        telemetry_dir = candidate
                        break
                # Check one level down (tarball may have a root folder)
                if telemetry_dir is None:
                    for sub in tmppath.iterdir():
                        if sub.is_dir():
                            for candidate in [
                                sub / "data" / "telemetry",
                                sub / "telemetry",
                            ]:
                                if candidate.is_dir() and list(candidate.glob("*.csv")):
                                    telemetry_dir = candidate
                                    break
                        if telemetry_dir:
                            break
                # Fallback: CSVs at root
                if telemetry_dir is None:
                    csv_files = list(tmppath.glob("*.csv"))
                    if csv_files:
                        telemetry_dir = tmppath
                    else:
                        raise HTTPException(400, "No telemetry CSV files found in tarball")

                csv_count = len(list(telemetry_dir.glob("*.csv")))
                yield _sse_event("progress", {
                    "step": "telemetry",
                    "detail": f"Found {csv_count} telemetry CSV files",
                    "pct": 10,
                })

                # Step 2: Find or create Eventhouse
                yield _sse_event("progress", {
                    "step": "telemetry", "detail": f"Finding or creating Eventhouse '{eventhouse_name}'…", "pct": 15,
                })
                eventhouse_id = await _find_or_create_eventhouse(
                    client, workspace_id, eventhouse_name,
                )
                yield _sse_event("progress", {
                    "step": "telemetry",
                    "detail": f"Eventhouse ready: {eventhouse_id}",
                    "pct": 25,
                })

                # Step 3: Discover KQL database
                yield _sse_event("progress", {
                    "step": "telemetry", "detail": "Discovering KQL database…", "pct": 30,
                })
                kql_db = await _discover_kql_database(client, workspace_id, eventhouse_id)
                db_name = kql_db.get("displayName", "")
                kql_props = kql_db.get("properties", {})
                query_uri = kql_props.get("queryServiceUri", "") or kql_props.get("queryUri", "")
                if not query_uri:
                    raise HTTPException(500, "Could not discover KQL database query URI")
                yield _sse_event("progress", {
                    "step": "telemetry",
                    "detail": f"KQL database: {db_name}",
                    "pct": 40,
                })

                # Step 4: Create KQL tables
                yield _sse_event("progress", {
                    "step": "telemetry", "detail": "Creating KQL tables and mappings…", "pct": 45,
                })
                await _create_kql_tables(query_uri, db_name)
                yield _sse_event("progress", {
                    "step": "telemetry",
                    "detail": "KQL tables created",
                    "pct": 55,
                })

                # Step 5: Ingest telemetry data
                yield _sse_event("progress", {
                    "step": "telemetry", "detail": "Ingesting telemetry data into Eventhouse…", "pct": 60,
                })
                await _ingest_kql_data(query_uri, db_name, telemetry_dir)
                yield _sse_event("progress", {
                    "step": "telemetry",
                    "detail": "Telemetry data ingested",
                    "pct": 90,
                })

                # Complete
                yield _sse_event("complete", {
                    "eventhouse_id": eventhouse_id,
                    "eventhouse_name": eventhouse_name,
                    "kql_database": db_name,
                    "query_uri": query_uri,
                    "fabric_resources": {
                        "eventhouse_id": eventhouse_id,
                        "eventhouse_name": eventhouse_name,
                        "kql_database": db_name,
                        "query_uri": query_uri,
                    },
                    "message": f"Telemetry provisioned to Eventhouse '{eventhouse_name}' successfully.",
                })

    return EventSourceResponse(sse_provision_stream(_work))


@router.get("/status")
async def fabric_status() -> dict:
    """Check current Fabric provisioning status based on env vars."""
    return {
        "configured": bool(FABRIC_WORKSPACE_ID),
        "workspace_id": FABRIC_WORKSPACE_ID,
        "workspace_name": FABRIC_WORKSPACE_NAME,
        "capacity_id": FABRIC_CAPACITY_ID,
        "lakehouse_name": FABRIC_LAKEHOUSE_NAME,
        "eventhouse_name": FABRIC_EVENTHOUSE_NAME,
        "ontology_name": FABRIC_ONTOLOGY_NAME,
    }
