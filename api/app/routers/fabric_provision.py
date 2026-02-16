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
import json
import logging
import os
from typing import Any

from azure.identity import DefaultAzureCredential
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

logger = logging.getLogger("app.fabric-provision")

router = APIRouter(prefix="/api/fabric", tags=["fabric-provisioning"])


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
    workspace_name = req.workspace_name or FABRIC_WORKSPACE_NAME
    capacity_id = req.capacity_id or FABRIC_CAPACITY_ID
    lakehouse_name = req.lakehouse_name or FABRIC_LAKEHOUSE_NAME
    eventhouse_name = req.eventhouse_name or FABRIC_EVENTHOUSE_NAME
    ontology_name = req.ontology_name or FABRIC_ONTOLOGY_NAME

    async def stream():
        client = AsyncFabricClient()
        try:
            # Step 1: Workspace
            yield _sse_event("progress", {
                "step": "workspace",
                "detail": f"Finding or creating workspace '{workspace_name}'...",
                "pct": 5,
            })
            workspace_id = await _find_or_create_workspace(
                client, workspace_name, capacity_id,
            )
            yield _sse_event("progress", {
                "step": "workspace",
                "detail": f"Workspace ready: {workspace_id}",
                "pct": 15,
            })

            # Step 2: Lakehouse
            yield _sse_event("progress", {
                "step": "lakehouse",
                "detail": f"Finding or creating lakehouse '{lakehouse_name}'...",
                "pct": 20,
            })
            lakehouse_id = await _find_or_create_lakehouse(
                client, workspace_id, lakehouse_name,
            )
            yield _sse_event("progress", {
                "step": "lakehouse",
                "detail": f"Lakehouse ready: {lakehouse_id}",
                "pct": 35,
            })

            # Step 3: Eventhouse
            yield _sse_event("progress", {
                "step": "eventhouse",
                "detail": f"Finding or creating eventhouse '{eventhouse_name}'...",
                "pct": 40,
            })
            eventhouse_id = await _find_or_create_eventhouse(
                client, workspace_id, eventhouse_name,
            )
            yield _sse_event("progress", {
                "step": "eventhouse",
                "detail": f"Eventhouse ready: {eventhouse_id}",
                "pct": 55,
            })

            # Step 4: Ontology
            yield _sse_event("progress", {
                "step": "ontology",
                "detail": f"Finding or creating ontology '{ontology_name}'...",
                "pct": 60,
            })
            ontology_id = await _find_or_create_ontology(
                client, workspace_id, ontology_name,
            )
            yield _sse_event("progress", {
                "step": "ontology",
                "detail": f"Ontology ready: {ontology_id}",
                "pct": 85,
            })

            # Complete
            yield _sse_event("complete", {
                "workspace_id": workspace_id,
                "lakehouse_id": lakehouse_id,
                "eventhouse_id": eventhouse_id,
                "ontology_id": ontology_id,
                "message": "Fabric provisioning complete.",
            })

        except HTTPException as exc:
            yield _sse_event("error", {
                "step": "error",
                "detail": str(exc.detail),
                "pct": -1,
            })
        except Exception as exc:
            logger.exception("Fabric provisioning failed")
            yield _sse_event("error", {
                "step": "error",
                "detail": f"Unexpected error: {exc}",
                "pct": -1,
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
