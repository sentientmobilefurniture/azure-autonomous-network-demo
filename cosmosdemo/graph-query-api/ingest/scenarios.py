"""Scenario listing, deletion, and AI Search index listing endpoints."""

from __future__ import annotations

import asyncio
import logging
import os

from fastapi import APIRouter, HTTPException

from adapters.cosmos_config import (
    COSMOS_GREMLIN_DATABASE,
    COSMOS_GREMLIN_ENDPOINT,
    COSMOS_GREMLIN_GRAPH,
    COSMOS_GREMLIN_PRIMARY_KEY,
)
from gremlin_helpers import create_gremlin_client, gremlin_submit_with_retry

logger = logging.getLogger("graph-query-api.ingest")

router = APIRouter()


@router.get("/scenarios", summary="List loaded scenarios")
async def list_scenarios():
    """List all scenarios by querying known Gremlin graphs.

    Uses key-based Gremlin auth (no DefaultAzureCredential event loop issues).
    First tries ARM to list graphs, falls back to querying known graph names directly.
    """
    if not COSMOS_GREMLIN_ENDPOINT or not COSMOS_GREMLIN_PRIMARY_KEY:
        return {"scenarios": [], "error": "Gremlin not configured"}

    try:
        def _list_graphs():
            """Discover graphs and count vertices — all sync, runs in thread."""
            graph_names = set()

            sub_id = os.getenv("AZURE_SUBSCRIPTION_ID", "")
            rg = os.getenv("AZURE_RESOURCE_GROUP", "")
            account_name = COSMOS_GREMLIN_ENDPOINT.split(".")[0]

            if sub_id and rg:
                try:
                    from cosmos_helpers import get_mgmt_client
                    mgmt = get_mgmt_client()
                    for g in mgmt.gremlin_resources.list_gremlin_graphs(rg, account_name, COSMOS_GREMLIN_DATABASE):
                        graph_names.add(g.name)
                except Exception as e:
                    logger.warning("ARM graph listing failed, falling back to known names: %s", e)

            if not graph_names:
                graph_names.add(COSMOS_GREMLIN_GRAPH)

            results = []
            for gname in sorted(graph_names):
                vcount = 0
                try:
                    c = create_gremlin_client(gname)
                    r = c.submit("g.V().count()").all().result()
                    vcount = r[0] if r else 0
                    c.close()
                except Exception as e:
                    logger.debug("Could not query graph %s: %s", gname, e)
                    vcount = -1

                results.append({
                    "graph_name": gname,
                    "vertex_count": vcount,
                    "has_data": vcount > 0,
                })
            return results

        scenario_list = await asyncio.to_thread(_list_graphs)
        return {"scenarios": scenario_list}

    except Exception as e:
        logger.exception("Failed to list scenarios")
        return {"scenarios": [], "error": str(e)}


@router.delete("/scenario/{graph_name}", summary="Delete a scenario's data")
async def delete_scenario(graph_name: str):
    """Drop all vertices and edges from a scenario's graph."""
    if not COSMOS_GREMLIN_ENDPOINT or not COSMOS_GREMLIN_PRIMARY_KEY:
        raise HTTPException(503, "Gremlin not configured")

    try:
        c = create_gremlin_client(graph_name)
        gremlin_submit_with_retry(c, "g.V().drop()")
        c.close()

        # Invalidate topology cache for this graph
        from router_topology import invalidate_topology_cache
        invalidate_topology_cache(graph_name)

        return {"status": "cleared", "graph": graph_name}
    except Exception as e:
        raise HTTPException(500, f"Failed to clear graph: {e}")


@router.get("/indexes", summary="List AI Search indexes")
async def list_indexes():
    """List all AI Search indexes available for agent configuration.

    Groups indexes by type (runbooks, tickets, other) for the Settings UI.
    """
    from config import AI_SEARCH_NAME, get_credential

    if not AI_SEARCH_NAME:
        return {"indexes": [], "error": "AI_SEARCH_NAME not configured"}

    try:
        def _list_indexes():
            from azure.search.documents.indexes import SearchIndexClient
            from azure.search.documents import SearchClient

            endpoint = f"https://{AI_SEARCH_NAME}.search.windows.net"
            client = SearchIndexClient(endpoint=endpoint, credential=get_credential())
            indexes = list(client.list_indexes())
            result = []
            for idx in indexes:
                idx_name = idx.name
                idx_type = "other"
                if "runbook" in idx_name.lower():
                    idx_type = "runbooks"
                elif "ticket" in idx_name.lower():
                    idx_type = "tickets"
                try:
                    sc = SearchClient(endpoint=endpoint, index_name=idx_name, credential=get_credential())
                    count = sc.get_document_count()
                except Exception:
                    count = None
                result.append({"name": idx_name, "type": idx_type, "document_count": count, "fields": len(idx.fields) if idx.fields else 0})
            return result

        indexes = await asyncio.to_thread(_list_indexes)
        return {"indexes": indexes}
    except Exception as e:
        logger.exception("Failed to list AI Search indexes")
        return {"indexes": [], "error": str(e)}
