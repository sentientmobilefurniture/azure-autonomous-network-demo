"""
Scenario ingest router — upload a scenario zip and load into Cosmos DB.

POST /query/scenario/upload  — upload a scenario .tar.gz, ingest into Cosmos
GET  /query/scenarios        — list loaded scenarios (from Cosmos graphs)
DELETE /query/scenario/{name} — drop a scenario's graph + telemetry data

The upload endpoint streams SSE progress events so the frontend can show
step-by-step ingestion status.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import os
import tarfile
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml
from fastapi import APIRouter, File, UploadFile, HTTPException
from sse_starlette.sse import EventSourceResponse

from gremlin_python.driver import client, serializer
from gremlin_python.driver.protocol import GremlinServerError

from azure.cosmos import CosmosClient, PartitionKey
from azure.cosmos.exceptions import CosmosHttpResponseError

from config import (
    COSMOS_GREMLIN_ENDPOINT,
    COSMOS_GREMLIN_PRIMARY_KEY,
    COSMOS_GREMLIN_DATABASE,
    COSMOS_NOSQL_ENDPOINT,
    get_credential,
)

logger = logging.getLogger("graph-query-api.ingest")

router = APIRouter(prefix="/query", tags=["scenarios"])


# ---------------------------------------------------------------------------
# Gremlin helpers (extracted from provision_cosmos_gremlin.py)
# ---------------------------------------------------------------------------


def _gremlin_client(graph_name: str) -> client.Client:
    """Create a Gremlin WSS client for a specific graph."""
    return client.Client(
        url=f"wss://{COSMOS_GREMLIN_ENDPOINT}:443/",
        traversal_source="g",
        username=f"/dbs/{COSMOS_GREMLIN_DATABASE}/colls/{graph_name}",
        password=COSMOS_GREMLIN_PRIMARY_KEY,
        message_serializer=serializer.GraphSONSerializersV2d0(),
    )


def _gremlin_submit(c: client.Client, query: str, bindings: dict | None = None, retries: int = 3):
    """Submit a Gremlin query with retry on 429/408."""
    for attempt in range(1, retries + 1):
        try:
            return c.submit(message=query, bindings=bindings or {}).all().result()
        except GremlinServerError as e:
            status = getattr(e, "status_code", 0)
            if status in (429, 408) and attempt < retries:
                time.sleep(2 ** attempt)
                continue
            raise


def _read_csv(path: Path) -> list[dict]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# ARM graph creation
# ---------------------------------------------------------------------------


def _ensure_gremlin_graph(graph_name: str) -> None:
    """Create the Gremlin graph resource if it doesn't exist (ARM management plane)."""
    try:
        from azure.mgmt.cosmosdb import CosmosDBManagementClient

        # Derive account name from endpoint (e.g. "myaccount.gremlin.cosmos.azure.com" → "myaccount")
        account_name = COSMOS_GREMLIN_ENDPOINT.split(".")[0]
        sub_id = os.getenv("AZURE_SUBSCRIPTION_ID", "")
        rg = os.getenv("AZURE_RESOURCE_GROUP", "")

        if not sub_id or not rg:
            logger.warning("AZURE_SUBSCRIPTION_ID or AZURE_RESOURCE_GROUP not set — cannot create graph via ARM. "
                           "Assuming graph '%s' already exists.", graph_name)
            return

        mgmt = CosmosDBManagementClient(get_credential(), sub_id)
        logger.info("Creating Gremlin graph '%s' via ARM (if not exists)...", graph_name)
        mgmt.gremlin_resources.begin_create_update_gremlin_graph(
            rg, account_name, COSMOS_GREMLIN_DATABASE, graph_name,
            {
                "resource": {
                    "id": graph_name,
                    "partition_key": {"paths": ["/partitionKey"], "kind": "Hash"},
                },
                "options": {"autoscale_settings": {"max_throughput": 1000}},
            },
        ).result()
        logger.info("Graph '%s' ready.", graph_name)
    except Exception as e:
        logger.warning("ARM graph creation failed (may already exist): %s", e)


# ---------------------------------------------------------------------------
# Endpoints — listing, deletion
# ---------------------------------------------------------------------------


# @router.get("/scenarios", summary="List loaded scenarios")
# async def list_scenarios():

#     # 1. Read manifests
#     emit("parsing", "Reading scenario.yaml and graph_schema.yaml...", 5)
#     scenario_yaml = scenario_dir / "scenario.yaml"
#     graph_schema_yaml = scenario_dir / "graph_schema.yaml"

#     if not scenario_yaml.exists():
#         raise ValueError("scenario.yaml not found in uploaded archive")
#     if not graph_schema_yaml.exists():
#         raise ValueError("graph_schema.yaml not found in uploaded archive")

#     manifest = yaml.safe_load(scenario_yaml.read_text())
#     schema = yaml.safe_load(graph_schema_yaml.read_text())
#     scenario_name = manifest["name"]
#     display_name = manifest.get("display_name", scenario_name)

#     # Resolve data_dir relative to graph_schema.yaml
#     data_dir = graph_schema_yaml.parent / schema.get("data_dir", "data/entities")
#     if not data_dir.exists():
#         raise ValueError(f"data_dir '{schema.get('data_dir')}' not found in archive")

#     emit("parsing", f"Scenario: {display_name} ({scenario_name})", 10)

#     # 2. Determine graph/database names
#     cosmos_config = manifest.get("cosmos", {})
#     gremlin_graph = f"{scenario_name}-{cosmos_config.get('gremlin', {}).get('graph', 'topology')}"
#     nosql_db_name = f"{scenario_name}-{cosmos_config.get('nosql', {}).get('database', 'telemetry')}"
#     containers_config = cosmos_config.get("nosql", {}).get("containers", [])

#     # 3. Create Gremlin graph (ARM)
#     emit("infra", f"Ensuring Gremlin graph '{gremlin_graph}' exists...", 15)
#     await asyncio.to_thread(_ensure_gremlin_graph, gremlin_graph)

#     # 4. Load graph data
#     emit("graph", "Connecting to Cosmos Gremlin...", 20)
#     gremlin_c = await asyncio.to_thread(_gremlin_client, gremlin_graph)

#     try:
#         # Clear existing data
#         emit("graph", "Clearing existing graph data...", 22)
#         await asyncio.to_thread(_gremlin_submit, gremlin_c, "g.V().drop()")

#         # Load vertices
#         vertices = schema.get("vertices", [])
#         total_vertices = 0
#         for vi, vdef in enumerate(vertices):
#             label = vdef["label"]
#             csv_path = data_dir / vdef["csv_file"]
#             if not csv_path.exists():
#                 emit("graph", f"⚠ CSV not found: {vdef['csv_file']} — skipping {label}", 25)
#                 continue

#             rows = await asyncio.to_thread(_read_csv, csv_path)
#             pct = 25 + int(25 * vi / max(len(vertices), 1))
#             emit("graph", f"Loading {label} ({len(rows)} vertices)...", pct)

#             for row in rows:
#                 vertex_id = row[vdef["id_column"]]
#                 pk_value = vdef["partition_key"]
#                 props = vdef.get("properties", [])

#                 prop_parts = [".property('id', id_val)", ".property('partitionKey', pk_val)"]
#                 bindings = {"label_val": label, "id_val": vertex_id, "pk_val": pk_value}

#                 for pi, prop_name in enumerate(props):
#                     if prop_name in row:
#                         param = f"p{pi}"
#                         prop_parts.append(f".property('{prop_name}', {param})")
#                         bindings[param] = row[prop_name]

#                 query = "g.addV(label_val)" + "".join(prop_parts)
#                 await asyncio.to_thread(_gremlin_submit, gremlin_c, query, bindings)
#                 total_vertices += 1

#         # Load edges
#         edges = schema.get("edges", [])
#         total_edges = 0
#         for ei, edef in enumerate(edges):
#             elabel = edef["label"]
#             csv_path = data_dir / edef["csv_file"]
#             if not csv_path.exists():
#                 continue

#             rows = await asyncio.to_thread(_read_csv, csv_path)

#             # Apply filter
#             row_filter = edef.get("filter")
#             if row_filter:
#                 fcol = row_filter["column"]
#                 fval = row_filter["value"]
#                 negate = row_filter.get("negate", False)
#                 if negate:
#                     rows = [r for r in rows if r.get(fcol) != fval]
#                 else:
#                     rows = [r for r in rows if r.get(fcol) == fval]

#             pct = 50 + int(15 * ei / max(len(edges), 1))
#             emit("graph", f"Loading {elabel} edges ({len(rows)} rows)...", pct)

#             source = edef["source"]
#             target = edef["target"]
#             edge_props = edef.get("properties", [])

#             for row in rows:
#                 src_val = row[source["column"]]
#                 tgt_val = row[target["column"]]
#                 bindings = {"src_val": src_val, "tgt_val": tgt_val}

#                 query = (
#                     f"g.V().has('{source['label']}', '{source['property']}', src_val)"
#                     f".addE('{elabel}')"
#                     f".to(g.V().has('{target['label']}', '{target['property']}', tgt_val))"
#                 )

#                 for pi, prop in enumerate(edge_props):
#                     param = f"ep{pi}"
#                     if "column" in prop:
#                         bindings[param] = row[prop["column"]]
#                     elif "value" in prop:
#                         bindings[param] = prop["value"]
#                     else:
#                         continue
#                     query += f".property('{prop['name']}', {param})"

#                 await asyncio.to_thread(_gremlin_submit, gremlin_c, query, bindings)
#                 total_edges += 1

#         emit("graph", f"Graph loaded: {total_vertices} vertices, {total_edges} edges", 65)

#     finally:
#         gremlin_c.close()

#     # 5. Load telemetry (NoSQL)
#     if containers_config and COSMOS_NOSQL_ENDPOINT:
#         emit("telemetry", "Connecting to Cosmos NoSQL...", 70)
#         telemetry_dir = scenario_dir / manifest.get("paths", {}).get("telemetry", "data/telemetry")

#         def _load_all_telemetry():
#             """Run all NoSQL operations in a single thread (no event loop conflicts)."""
#             cosmos = CosmosClient(COSMOS_NOSQL_ENDPOINT, credential=get_credential())
#             db = cosmos.create_database_if_not_exists(nosql_db_name)

#             for ci, cdef in enumerate(containers_config):
#                 cname = cdef["name"]
#                 pk_path = cdef.get("partition_key", "/id")
#                 csv_file = cdef.get("csv_file", f"{cname}.csv")
#                 numeric_fields = cdef.get("numeric_fields", [])
#                 id_field = cdef.get("id_field")

#                 csv_path = telemetry_dir / csv_file
#                 if not csv_path.exists():
#                     emit("telemetry", f"⚠ CSV not found: {csv_file} — skipping {cname}", 72)
#                     continue

#                 pct = 72 + int(25 * ci / max(len(containers_config), 1))
#                 emit("telemetry", f"Loading {cname} from {csv_file}...", pct)

#                 container = db.create_container_if_not_exists(
#                     id=cname, partition_key=PartitionKey(path=pk_path),
#                 )

#                 rows = _read_csv(csv_path)
#                 emit("telemetry", f"Upserting {len(rows)} docs into {cname}...", pct + 5)

#                 for row in rows:
#                     for nf in numeric_fields:
#                         if nf in row and row[nf]:
#                             try:
#                                 row[nf] = float(row[nf])
#                             except (ValueError, TypeError):
#                                 pass
#                     if id_field and id_field in row:
#                         row["id"] = row[id_field]
#                     elif "id" not in row:
#                         keys = list(row.keys())
#                         row["id"] = f"{row.get(keys[0], '')}-{row.get(keys[1], '')}"

#                     container.upsert_item(row)

#                 emit("telemetry", f"✓ {cname}: {len(rows)} docs upserted", pct + 10)

#         await asyncio.to_thread(_load_all_telemetry)

#         emit("telemetry", f"Telemetry loaded into {nosql_db_name}", 92)
#     else:
#         emit("telemetry", "No telemetry containers or NoSQL endpoint not configured — skipping", 92)

#     # 6. Store prompts in Cosmos (if prompts directory exists in archive)
#     prompts_dir = scenario_dir / manifest.get("paths", {}).get("prompts", "data/prompts")
#     stored_prompts = []
#     if prompts_dir.exists() and COSMOS_NOSQL_ENDPOINT:
#         emit("prompts", "Storing prompts in Cosmos DB...", 94)

#         # Map prompt filenames to agent names
#         PROMPT_AGENT_MAP = {
#             "foundry_orchestrator_agent.md": "orchestrator",
#             "orchestrator.md": "orchestrator",
#             "foundry_telemetry_agent_v2.md": "telemetry",
#             "telemetry_agent.md": "telemetry",
#             "foundry_runbook_kb_agent.md": "runbook",
#             "runbook_agent.md": "runbook",
#             "foundry_historical_ticket_agent.md": "ticket",
#             "ticket_agent.md": "ticket",
#             "alert_storm.md": "default_alert",
#             "default_alert.md": "default_alert",
#         }

#         try:
#             from router_prompts import _get_prompts_container
#             prompts_container = _get_prompts_container()

#             for md_file in prompts_dir.glob("*.md"):
#                 agent = PROMPT_AGENT_MAP.get(md_file.name)
#                 if not agent:
#                     continue

#                 content = md_file.read_text()

#                 # Check existing versions
#                 query = (
#                     "SELECT c.version FROM c "
#                     "WHERE c.agent = @agent AND c.scenario = @scenario AND c.name = @name "
#                     "ORDER BY c.version DESC"
#                 )
#                 existing = list(prompts_container.query_items(
#                     query=query,
#                     parameters=[
#                         {"name": "@agent", "value": agent},
#                         {"name": "@scenario", "value": scenario_name},
#                         {"name": "@name", "value": md_file.stem},
#                     ],
#                     enable_cross_partition_query=False,
#                 ))
#                 next_version = (existing[0]["version"] + 1) if existing else 1
#                 doc_id = f"{scenario_name}/{md_file.stem}/v{next_version}"

#                 prompts_container.upsert_item({
#                     "id": doc_id,
#                     "agent": agent,
#                     "scenario": scenario_name,
#                     "name": md_file.stem,
#                     "version": next_version,
#                     "content": content,
#                     "description": f"Auto-imported from {scenario_name} upload",
#                     "tags": [scenario_name, agent],
#                     "is_active": True,
#                     "deleted": False,
#                     "created_at": datetime.now(timezone.utc).isoformat(),
#                     "created_by": "scenario-upload",
#                 })
#                 stored_prompts.append(doc_id)

#             # Handle graph_explorer composite prompt
#             ge_dir = prompts_dir / "graph_explorer"
#             if ge_dir.exists():
#                 parts = []
#                 for part_name in ["core_instructions.md", "core_schema.md", "language_gremlin.md"]:
#                     part_file = ge_dir / part_name
#                     if part_file.exists():
#                         parts.append(part_file.read_text())

#                 if parts:
#                     composed = "\n\n---\n\n".join(parts)
#                     existing = list(prompts_container.query_items(
#                         query="SELECT c.version FROM c WHERE c.agent = 'graph_explorer' AND c.scenario = @scenario AND c.name = 'graph_explorer' ORDER BY c.version DESC",
#                         parameters=[{"name": "@scenario", "value": scenario_name}],
#                         enable_cross_partition_query=False,
#                     ))
#                     next_version = (existing[0]["version"] + 1) if existing else 1
#                     doc_id = f"{scenario_name}/graph_explorer/v{next_version}"

#                     prompts_container.upsert_item({
#                         "id": doc_id,
#                         "agent": "graph_explorer",
#                         "scenario": scenario_name,
#                         "name": "graph_explorer",
#                         "version": next_version,
#                         "content": composed,
#                         "description": f"Composed from core_instructions + core_schema + language_gremlin ({scenario_name})",
#                         "tags": [scenario_name, "graph_explorer", "composed"],
#                         "is_active": True,
#                         "deleted": False,
#                         "created_at": datetime.now(timezone.utc).isoformat(),
#                         "created_by": "scenario-upload",
#                     })
#                     stored_prompts.append(doc_id)

#             emit("prompts", f"Stored {len(stored_prompts)} prompts in Cosmos", 97)
#         except Exception as e:
#             logger.warning("Failed to store prompts (non-fatal): %s", e)
#             emit("prompts", f"⚠ Prompt storage failed (non-fatal): {e}", 97)
#     else:
#         emit("prompts", "No prompts directory found or NoSQL not configured — skipping", 97)

#     # 7. Upload knowledge files to blob + create AI Search indexes
#     knowledge_dir = scenario_dir / manifest.get("paths", {}).get("runbooks", "data/knowledge/runbooks")
#     tickets_dir_path = scenario_dir / manifest.get("paths", {}).get("tickets", "data/knowledge/tickets")
#     runbooks_index_name = ""
#     tickets_index_name = ""
#     storage_account = os.getenv("STORAGE_ACCOUNT_NAME", "")
#     ai_search_name = os.getenv("AI_SEARCH_NAME", "")

#     if storage_account and ai_search_name:
#         try:
#             from azure.storage.blob import BlobServiceClient

#             blob_url = f"https://{storage_account}.blob.core.windows.net"
#             blob_service = BlobServiceClient(blob_url, credential=get_credential())

#             # Upload runbooks
#             if knowledge_dir.exists() and any(knowledge_dir.glob("*.md")):
#                 rb_container_name = f"{scenario_name}-runbooks"
#                 emit("knowledge", f"Uploading runbooks to blob container '{rb_container_name}'...", 80)
#                 try:
#                     blob_service.create_container(rb_container_name)
#                 except Exception:
#                     pass  # container may already exist

#                 for md_file in knowledge_dir.glob("*.md"):
#                     blob_client = blob_service.get_blob_client(rb_container_name, md_file.name)
#                     with open(md_file, "rb") as f:
#                         blob_client.upload_blob(f, overwrite=True)

#                 emit("knowledge", f"Uploaded {len(list(knowledge_dir.glob('*.md')))} runbook files", 83)

#                 # Create search index
#                 emit("knowledge", f"Creating AI Search index '{scenario_name}-runbooks-index'...", 85)
#                 try:
#                     from search_indexer import create_search_index as create_idx
#                     idx_result = await asyncio.to_thread(
#                         create_idx,
#                         index_name=f"{scenario_name}-runbooks-index",
#                         container_name=rb_container_name,
#                         on_progress=lambda msg: emit("knowledge", msg, 87),
#                     )
#                     runbooks_index_name = idx_result.get("index_name", "")
#                     emit("knowledge", f"Runbooks index: {idx_result.get('document_count', 0)} docs", 89)
#                 except Exception as e:
#                     logger.warning("Runbooks indexer failed (non-fatal): %s", e)
#                     emit("knowledge", f"⚠ Runbooks indexer failed: {e}", 89)

#             # Upload tickets
#             if tickets_dir_path.exists() and any(tickets_dir_path.glob("*.txt")):
#                 tk_container_name = f"{scenario_name}-tickets"
#                 emit("knowledge", f"Uploading tickets to blob container '{tk_container_name}'...", 90)
#                 try:
#                     blob_service.create_container(tk_container_name)
#                 except Exception:
#                     pass

#                 for txt_file in tickets_dir_path.glob("*.txt"):
#                     blob_client = blob_service.get_blob_client(tk_container_name, txt_file.name)
#                     with open(txt_file, "rb") as f:
#                         blob_client.upload_blob(f, overwrite=True)

#                 emit("knowledge", f"Uploaded {len(list(tickets_dir_path.glob('*.txt')))} ticket files", 93)

#                 # Create search index
#                 emit("knowledge", f"Creating AI Search index '{scenario_name}-tickets-index'...", 94)
#                 try:
#                     from search_indexer import create_search_index as create_idx
#                     idx_result = await asyncio.to_thread(
#                         create_idx,
#                         index_name=f"{scenario_name}-tickets-index",
#                         container_name=tk_container_name,
#                         on_progress=lambda msg: emit("knowledge", msg, 95),
#                     )
#                     tickets_index_name = idx_result.get("index_name", "")
#                     emit("knowledge", f"Tickets index: {idx_result.get('document_count', 0)} docs", 97)
#                 except Exception as e:
#                     logger.warning("Tickets indexer failed (non-fatal): %s", e)
#                     emit("knowledge", f"⚠ Tickets indexer failed: {e}", 97)

#         except Exception as e:
#             logger.warning("Knowledge upload failed (non-fatal): %s", e)
#             emit("knowledge", f"⚠ Knowledge upload failed: {e}", 97)
#     else:
#         if not storage_account:
#             emit("knowledge", "STORAGE_ACCOUNT_NAME not set — skipping blob upload", 97)
#         elif not ai_search_name:
#             emit("knowledge", "AI_SEARCH_NAME not set — skipping index creation", 97)

#     # 8. Done
#     result = {
#         "scenario": scenario_name,
#         "display_name": display_name,
#         "graph": gremlin_graph,
#         "telemetry_db": nosql_db_name,
#         "vertices": total_vertices,
#         "edges": total_edges,
#         "prompts": stored_prompts,
#         "runbooks_index": runbooks_index_name,
#         "tickets_index": tickets_index_name,
#     }
#     emit("done", f"Scenario '{display_name}' loaded successfully!", 100)
#     return result


# # ---------------------------------------------------------------------------
# # Endpoints
# # ---------------------------------------------------------------------------


# @router.post("/scenario/upload", summary="Upload and ingest a scenario")
# async def upload_scenario(file: UploadFile = File(...)):
#     """
#     Upload a scenario as a .tar.gz archive and ingest into Cosmos DB.

#     The archive must contain at least:
#       - scenario.yaml (scenario manifest)
#       - graph_schema.yaml (graph ontology)
#       - data/entities/*.csv (vertex + edge CSVs)
#       - data/telemetry/*.csv (telemetry CSVs)

#     Returns an SSE stream with progress events.
#     """
#     if not file.filename or not (file.filename.endswith(".tar.gz") or file.filename.endswith(".tgz")):
#         raise HTTPException(400, "File must be a .tar.gz archive")

#     # Read upload into memory
#     content = await file.read()
#     logger.info("Received scenario upload: %s (%d bytes)", file.filename, len(content))

#     async def event_generator():
#         progress: asyncio.Queue = asyncio.Queue()

#         with tempfile.TemporaryDirectory() as tmpdir:
#             tmppath = Path(tmpdir)

#             # Extract archive
#             try:
#                 with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as tar:
#                     tar.extractall(tmppath, filter="data")
#             except Exception as e:
#                 yield {"event": "error", "data": json.dumps({"error": f"Failed to extract archive: {e}"})}
#                 return

#             # Find scenario root (may be nested one level)
#             scenario_dir = tmppath
#             if not (scenario_dir / "scenario.yaml").exists():
#                 subdirs = [d for d in tmppath.iterdir() if d.is_dir()]
#                 for sd in subdirs:
#                     if (sd / "scenario.yaml").exists():
#                         scenario_dir = sd
#                         break

#             # Start ingestion in background
#             result_future: asyncio.Future = asyncio.get_event_loop().create_future()

#             async def run_ingest():
#                 try:
#                     result = await _ingest_scenario(scenario_dir, progress)
#                     result_future.set_result(result)
#                 except Exception as e:
#                     logger.exception("Ingestion failed")
#                     result_future.set_exception(e)
#                 finally:
#                     await progress.put(None)  # sentinel

#             task = asyncio.create_task(run_ingest())

#             # Stream progress events
#             while True:
#                 event = await progress.get()
#                 if event is None:
#                     break
#                 yield {"event": "progress", "data": json.dumps(event)}

#             # Final result or error
#             try:
#                 result = result_future.result()
#                 yield {"event": "complete", "data": json.dumps(result)}
#             except Exception as e:
#                 yield {"event": "error", "data": json.dumps({"error": str(e)})}

#             await task

#     return EventSourceResponse(event_generator())


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

            # Method 1: Try ARM listing
            sub_id = os.getenv("AZURE_SUBSCRIPTION_ID", "")
            rg = os.getenv("AZURE_RESOURCE_GROUP", "")
            account_name = COSMOS_GREMLIN_ENDPOINT.split(".")[0]

            if sub_id and rg:
                try:
                    from azure.mgmt.cosmosdb import CosmosDBManagementClient
                    from azure.identity import DefaultAzureCredential
                    mgmt = CosmosDBManagementClient(DefaultAzureCredential(), sub_id)
                    for g in mgmt.gremlin_resources.list_gremlin_graphs(rg, account_name, COSMOS_GREMLIN_DATABASE):
                        graph_names.add(g.name)
                except Exception as e:
                    logger.warning("ARM graph listing failed, falling back to known names: %s", e)

            # Method 2: If ARM failed or empty, try the default graph
            if not graph_names:
                graph_names.add(COSMOS_GREMLIN_GRAPH)

            # Count vertices for each graph
            results = []
            for gname in sorted(graph_names):
                vcount = 0
                try:
                    c = _gremlin_client(gname)
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
        c = _gremlin_client(graph_name)
        _gremlin_submit(c, "g.V().drop()")
        c.close()
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


# ---------------------------------------------------------------------------
# Per-type upload endpoints (decoupled from monolithic scenario upload)
# ---------------------------------------------------------------------------

def _extract_tar(content: bytes, tmppath: Path) -> Path:
    """Extract a tar.gz and return the scenario root directory."""
    with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as tar:
        tar.extractall(tmppath, filter="data")
    # Find scenario root (may be one level down)
    scenario_dir = tmppath
    if not (scenario_dir / "scenario.yaml").exists():
        for sd in tmppath.iterdir():
            if sd.is_dir() and (sd / "scenario.yaml").exists():
                return sd
    return scenario_dir


@router.post("/upload/graph", summary="Upload graph data only")
async def upload_graph(file: UploadFile = File(...)):
    """Upload a tarball containing scenario.yaml + graph_schema.yaml + data/entities/*.csv.
    Loads vertices and edges into Cosmos Gremlin. Returns SSE progress."""
    if not file.filename or not (file.filename.endswith(".tar.gz") or file.filename.endswith(".tgz")):
        raise HTTPException(400, "File must be a .tar.gz archive")

    content = await file.read()
    logger.info("Graph upload: %s (%d bytes)", file.filename, len(content))

    async def stream():
        progress: asyncio.Queue = asyncio.Queue()
        def emit(step, detail, pct):
            progress.put_nowait({"step": step, "detail": detail, "pct": pct})

        async def run():
            try:
                with tempfile.TemporaryDirectory() as tmpdir:
                    tmppath = Path(tmpdir)
                    scenario_dir = _extract_tar(content, tmppath)

                    manifest = yaml.safe_load((scenario_dir / "scenario.yaml").read_text())
                    schema = yaml.safe_load((scenario_dir / "graph_schema.yaml").read_text())
                    scenario_name = manifest["name"]
                    cosmos_cfg = manifest.get("cosmos", {})
                    gremlin_graph = f"{scenario_name}-{cosmos_cfg.get('gremlin', {}).get('graph', 'topology')}"
                    data_dir = scenario_dir / schema.get("data_dir", "data/entities")

                    emit("infra", f"Ensuring graph '{gremlin_graph}' exists...", 10)
                    await asyncio.to_thread(_ensure_gremlin_graph, gremlin_graph)

                    emit("graph", "Loading graph data...", 20)

                    def _load_graph():
                        """Run all Gremlin operations in a single thread."""
                        gremlin_c = _gremlin_client(gremlin_graph)
                        try:
                            emit("graph", "Clearing existing graph data...", 25)
                            _gremlin_submit(gremlin_c, "g.V().drop()")

                            total_v, total_e = 0, 0
                            vertices = schema.get("vertices", [])
                            for vi, vdef in enumerate(vertices):
                                csv_path = data_dir / vdef["csv_file"]
                                if not csv_path.exists():
                                    continue
                                rows = _read_csv(csv_path)
                                pct = 30 + int(30 * vi / max(len(vertices), 1))
                                emit("graph", f"Loading {vdef['label']} ({len(rows)} vertices)...", pct)
                                for row in rows:
                                    bindings = {"label_val": vdef["label"], "id_val": row[vdef["id_column"]], "pk_val": vdef["partition_key"]}
                                    props = []
                                    for pi, p in enumerate(vdef.get("properties", [])):
                                        if p in row:
                                            bindings[f"p{pi}"] = row[p]
                                            props.append(f".property('{p}', p{pi})")
                                    query = "g.addV(label_val).property('id', id_val).property('partitionKey', pk_val)" + "".join(props)
                                    _gremlin_submit(gremlin_c, query, bindings)
                                    total_v += 1

                            edges = schema.get("edges", [])
                            for ei, edef in enumerate(edges):
                                csv_path = data_dir / edef["csv_file"]
                                if not csv_path.exists():
                                    continue
                                rows = _read_csv(csv_path)
                                rf = edef.get("filter")
                                if rf:
                                    negate = rf.get("negate", False)
                                    rows = [r for r in rows if (r.get(rf["column"]) != rf["value"]) == negate]
                                pct = 60 + int(25 * ei / max(len(edges), 1))
                                emit("graph", f"Loading {edef['label']} edges ({len(rows)} rows)...", pct)
                                src, tgt = edef["source"], edef["target"]
                                for row in rows:
                                    bindings = {"src_val": row[src["column"]], "tgt_val": row[tgt["column"]]}
                                    q = f"g.V().has('{src['label']}', '{src['property']}', src_val).addE('{edef['label']}').to(g.V().has('{tgt['label']}', '{tgt['property']}', tgt_val))"
                                    for pi, ep in enumerate(edef.get("properties", [])):
                                        if "column" in ep:
                                            bindings[f"ep{pi}"] = row[ep["column"]]
                                        elif "value" in ep:
                                            bindings[f"ep{pi}"] = ep["value"]
                                        else:
                                            continue
                                        q += f".property('{ep['name']}', ep{pi})"
                                    _gremlin_submit(gremlin_c, q, bindings)
                                    total_e += 1

                            return total_v, total_e
                        finally:
                            gremlin_c.close()

                    total_v, total_e = await asyncio.to_thread(_load_graph)
                    emit("done", f"Graph loaded: {total_v} vertices, {total_e} edges → {gremlin_graph}", 100)
                    progress.put_nowait({"_result": {"scenario": scenario_name, "graph": gremlin_graph, "vertices": total_v, "edges": total_e}})
            except Exception as e:
                logger.exception("Graph upload failed")
                progress.put_nowait({"step": "error", "detail": str(e), "pct": -1})
            finally:
                progress.put_nowait(None)

        task = asyncio.create_task(run())
        while True:
            ev = await progress.get()
            if ev is None:
                break
            if "_result" in ev:
                yield {"event": "complete", "data": json.dumps(ev["_result"])}
            elif ev.get("step") == "error":
                yield {"event": "error", "data": json.dumps({"error": ev["detail"]})}
            else:
                yield {"event": "progress", "data": json.dumps(ev)}
        await task

    return EventSourceResponse(stream())


@router.post("/upload/telemetry", summary="Upload telemetry data only")
async def upload_telemetry(file: UploadFile = File(...)):
    """Upload a tarball containing scenario.yaml + data/telemetry/*.csv.
    Loads into Cosmos NoSQL. Runs entirely in a background thread."""
    if not file.filename or not (file.filename.endswith(".tar.gz") or file.filename.endswith(".tgz")):
        raise HTTPException(400, "File must be a .tar.gz archive")

    content = await file.read()
    logger.info("Telemetry upload: %s (%d bytes)", file.filename, len(content))

    async def stream():
        progress: asyncio.Queue = asyncio.Queue()
        def emit(step, detail, pct):
            progress.put_nowait({"step": step, "detail": detail, "pct": pct})

        async def run():
            try:
                with tempfile.TemporaryDirectory() as tmpdir:
                    tmppath = Path(tmpdir)
                    scenario_dir = _extract_tar(content, tmppath)

                    manifest = yaml.safe_load((scenario_dir / "scenario.yaml").read_text())
                    scenario_name = manifest["name"]
                    cosmos_cfg = manifest.get("cosmos", {})
                    nosql_db = f"{scenario_name}-{cosmos_cfg.get('nosql', {}).get('database', 'telemetry')}"
                    containers_config = cosmos_cfg.get("nosql", {}).get("containers", [])
                    telemetry_dir = scenario_dir / manifest.get("paths", {}).get("telemetry", "data/telemetry")

                    if not COSMOS_NOSQL_ENDPOINT:
                        emit("error", "COSMOS_NOSQL_ENDPOINT not configured", -1)
                        return

                    emit("telemetry", f"Loading into database '{nosql_db}'...", 10)

                    def _ensure_nosql_db_and_containers():
                        """Create NoSQL database + containers via ARM (management plane).
                        Data-plane RBAC doesn't cover database creation, so we use ARM."""
                        account_name = COSMOS_NOSQL_ENDPOINT.replace("https://", "").split(".")[0]
                        sub_id = os.getenv("AZURE_SUBSCRIPTION_ID", "")
                        rg = os.getenv("AZURE_RESOURCE_GROUP", "")
                        if not sub_id or not rg:
                            raise RuntimeError("AZURE_SUBSCRIPTION_ID/AZURE_RESOURCE_GROUP not set")

                        from azure.mgmt.cosmosdb import CosmosDBManagementClient
                        mgmt = CosmosDBManagementClient(get_credential(), sub_id)

                        # Create database
                        emit("telemetry", f"Creating database '{nosql_db}' via ARM...", 12)
                        try:
                            mgmt.sql_resources.begin_create_update_sql_database(
                                rg, account_name, nosql_db,
                                {"resource": {"id": nosql_db}},
                            ).result()
                        except Exception as e:
                            if "Conflict" not in str(e):
                                raise
                            # Database already exists — fine

                        # Create containers
                        for cdef in containers_config:
                            cname = cdef["name"]
                            pk_path = cdef.get("partition_key", "/id")
                            emit("telemetry", f"Creating container '{cname}'...", 15)
                            try:
                                mgmt.sql_resources.begin_create_update_sql_container(
                                    rg, account_name, nosql_db, cname,
                                    {"resource": {"id": cname, "partitionKey": {"paths": [pk_path], "kind": "Hash"}}},
                                ).result()
                            except Exception as e:
                                if "Conflict" not in str(e):
                                    raise

                    await asyncio.to_thread(_ensure_nosql_db_and_containers)

                    def _load():
                        cosmos = CosmosClient(COSMOS_NOSQL_ENDPOINT, credential=get_credential())
                        db = cosmos.get_database_client(nosql_db)
                        for ci, cdef in enumerate(containers_config):
                            cname = cdef["name"]
                            csv_file = cdef.get("csv_file", f"{cname}.csv")
                            csv_path = telemetry_dir / csv_file
                            if not csv_path.exists():
                                emit("telemetry", f"⚠ {csv_file} not found — skipping", 20)
                                continue
                            pct = 20 + int(70 * ci / max(len(containers_config), 1))
                            emit("telemetry", f"Loading {cname}...", pct)
                            container = db.get_container_client(cname)
                            rows = _read_csv(csv_path)
                            emit("telemetry", f"Upserting {len(rows)} docs into {cname}...", pct + 10)
                            for row in rows:
                                for nf in cdef.get("numeric_fields", []):
                                    if nf in row and row[nf]:
                                        try: row[nf] = float(row[nf])
                                        except: pass
                                id_field = cdef.get("id_field")
                                if id_field and id_field in row:
                                    row["id"] = row[id_field]
                                elif "id" not in row:
                                    keys = list(row.keys())
                                    row["id"] = f"{row.get(keys[0], '')}-{row.get(keys[1], '')}"
                                container.upsert_item(row)
                            emit("telemetry", f"✓ {cname}: {len(rows)} docs", pct + 20)
                        return len(containers_config)

                    count = await asyncio.to_thread(_load)
                    emit("done", f"Telemetry loaded: {count} containers → {nosql_db}", 100)
                    progress.put_nowait({"_result": {"scenario": scenario_name, "database": nosql_db, "containers": count}})
            except Exception as e:
                logger.exception("Telemetry upload failed")
                progress.put_nowait({"step": "error", "detail": str(e), "pct": -1})
            finally:
                progress.put_nowait(None)

        task = asyncio.create_task(run())
        while True:
            ev = await progress.get()
            if ev is None:
                break
            if "_result" in ev:
                yield {"event": "complete", "data": json.dumps(ev["_result"])}
            elif ev.get("step") == "error":
                yield {"event": "error", "data": json.dumps({"error": ev["detail"]})}
            else:
                yield {"event": "progress", "data": json.dumps(ev)}
        await task

    return EventSourceResponse(stream())


@router.post("/upload/runbooks", summary="Upload runbooks only")
async def upload_runbooks(file: UploadFile = File(...), scenario: str = "default"):
    """Upload a tarball of .md runbook files. Uploads to blob + creates AI Search index."""
    if not file.filename or not (file.filename.endswith(".tar.gz") or file.filename.endswith(".tgz")):
        raise HTTPException(400, "File must be a .tar.gz archive")

    content = await file.read()
    logger.info("Runbooks upload: %s (%d bytes), scenario=%s", file.filename, len(content), scenario)

    async def stream():
        progress: asyncio.Queue = asyncio.Queue()
        def emit(step, detail, pct):
            progress.put_nowait({"step": step, "detail": detail, "pct": pct})

        async def run():
            try:
                with tempfile.TemporaryDirectory() as tmpdir:
                    tmppath = Path(tmpdir)
                    with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as tar:
                        tar.extractall(tmppath, filter="data")

                    # Auto-detect scenario name from scenario.yaml if present
                    sc_name = scenario
                    for root, dirs, files in os.walk(tmppath):
                        if "scenario.yaml" in files:
                            m = yaml.safe_load(Path(root, "scenario.yaml").read_text())
                            sc_name = m.get("name", scenario)
                            break

                    # Find .md files
                    md_files = list(tmppath.rglob("*.md"))
                    if not md_files:
                        emit("error", "No .md files found in archive", -1)
                        return

                    emit("runbooks", f"Found {len(md_files)} runbook files", 10)

                    storage_account = os.getenv("STORAGE_ACCOUNT_NAME", "")
                    ai_search = os.getenv("AI_SEARCH_NAME", "")
                    if not storage_account:
                        emit("error", "STORAGE_ACCOUNT_NAME not configured", -1)
                        return

                    container_name = f"{sc_name}-runbooks"
                    index_name = f"{sc_name}-runbooks-index"

                    def _upload_and_index():
                        from azure.storage.blob import BlobServiceClient
                        blob_svc = BlobServiceClient(f"https://{storage_account}.blob.core.windows.net", credential=get_credential())
                        try: blob_svc.create_container(container_name)
                        except: pass

                        for f in md_files:
                            bc = blob_svc.get_blob_client(container_name, f.name)
                            with open(f, "rb") as fh:
                                bc.upload_blob(fh, overwrite=True)
                        emit("runbooks", f"Uploaded {len(md_files)} files to blob '{container_name}'", 50)

                        if ai_search:
                            emit("runbooks", f"Creating search index '{index_name}'...", 60)
                            from search_indexer import create_search_index
                            result = create_search_index(
                                index_name=index_name,
                                container_name=container_name,
                                on_progress=lambda msg: emit("runbooks", msg, 80),
                            )
                            return result
                        return {"index_name": index_name, "status": "blob_only"}

                    result = await asyncio.to_thread(_upload_and_index)
                    emit("done", f"Runbooks indexed: {index_name}", 100)
                    progress.put_nowait({"_result": {"scenario": sc_name, "index": index_name, **result}})
            except Exception as e:
                logger.exception("Runbooks upload failed")
                progress.put_nowait({"step": "error", "detail": str(e), "pct": -1})
            finally:
                progress.put_nowait(None)

        task = asyncio.create_task(run())
        while True:
            ev = await progress.get()
            if ev is None:
                break
            if "_result" in ev:
                yield {"event": "complete", "data": json.dumps(ev["_result"])}
            elif ev.get("step") == "error":
                yield {"event": "error", "data": json.dumps({"error": ev["detail"]})}
            else:
                yield {"event": "progress", "data": json.dumps(ev)}
        await task

    return EventSourceResponse(stream())


@router.post("/upload/tickets", summary="Upload tickets only")
async def upload_tickets(file: UploadFile = File(...), scenario: str = "default"):
    """Upload a tarball of .txt ticket files. Uploads to blob + creates AI Search index."""
    if not file.filename or not (file.filename.endswith(".tar.gz") or file.filename.endswith(".tgz")):
        raise HTTPException(400, "File must be a .tar.gz archive")

    content = await file.read()
    logger.info("Tickets upload: %s (%d bytes), scenario=%s", file.filename, len(content), scenario)

    async def stream():
        progress: asyncio.Queue = asyncio.Queue()
        def emit(step, detail, pct):
            progress.put_nowait({"step": step, "detail": detail, "pct": pct})

        async def run():
            try:
                with tempfile.TemporaryDirectory() as tmpdir:
                    tmppath = Path(tmpdir)
                    with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as tar:
                        tar.extractall(tmppath, filter="data")

                    sc_name = scenario
                    for root, dirs, files in os.walk(tmppath):
                        if "scenario.yaml" in files:
                            m = yaml.safe_load(Path(root, "scenario.yaml").read_text())
                            sc_name = m.get("name", scenario)
                            break

                    txt_files = list(tmppath.rglob("*.txt"))
                    if not txt_files:
                        emit("error", "No .txt files found in archive", -1)
                        return

                    emit("tickets", f"Found {len(txt_files)} ticket files", 10)

                    storage_account = os.getenv("STORAGE_ACCOUNT_NAME", "")
                    ai_search = os.getenv("AI_SEARCH_NAME", "")
                    if not storage_account:
                        emit("error", "STORAGE_ACCOUNT_NAME not configured", -1)
                        return

                    container_name = f"{sc_name}-tickets"
                    index_name = f"{sc_name}-tickets-index"

                    def _upload_and_index():
                        from azure.storage.blob import BlobServiceClient
                        blob_svc = BlobServiceClient(f"https://{storage_account}.blob.core.windows.net", credential=get_credential())
                        try: blob_svc.create_container(container_name)
                        except: pass

                        for f in txt_files:
                            bc = blob_svc.get_blob_client(container_name, f.name)
                            with open(f, "rb") as fh:
                                bc.upload_blob(fh, overwrite=True)
                        emit("tickets", f"Uploaded {len(txt_files)} files to blob '{container_name}'", 50)

                        if ai_search:
                            emit("tickets", f"Creating search index '{index_name}'...", 60)
                            from search_indexer import create_search_index
                            result = create_search_index(
                                index_name=index_name,
                                container_name=container_name,
                                on_progress=lambda msg: emit("tickets", msg, 80),
                            )
                            return result
                        return {"index_name": index_name, "status": "blob_only"}

                    result = await asyncio.to_thread(_upload_and_index)
                    emit("done", f"Tickets indexed: {index_name}", 100)
                    progress.put_nowait({"_result": {"scenario": sc_name, "index": index_name, **result}})
            except Exception as e:
                logger.exception("Tickets upload failed")
                progress.put_nowait({"step": "error", "detail": str(e), "pct": -1})
            finally:
                progress.put_nowait(None)

        task = asyncio.create_task(run())
        while True:
            ev = await progress.get()
            if ev is None:
                break
            if "_result" in ev:
                yield {"event": "complete", "data": json.dumps(ev["_result"])}
            elif ev.get("step") == "error":
                yield {"event": "error", "data": json.dumps({"error": ev["detail"]})}
            else:
                yield {"event": "progress", "data": json.dumps(ev)}
        await task

    return EventSourceResponse(stream())


# Prompt filename → agent name mapping
PROMPT_AGENT_MAP = {
    "foundry_orchestrator_agent.md": "orchestrator",
    "orchestrator.md": "orchestrator",
    "foundry_telemetry_agent_v2.md": "telemetry",
    "telemetry_agent.md": "telemetry",
    "foundry_runbook_kb_agent.md": "runbook",
    "runbook_agent.md": "runbook",
    "foundry_historical_ticket_agent.md": "ticket",
    "ticket_agent.md": "ticket",
    "alert_storm.md": "default_alert",
    "default_alert.md": "default_alert",
}


@router.post("/upload/prompts", summary="Upload prompts to Cosmos DB")
async def upload_prompts(file: UploadFile = File(...)):
    """Upload a tarball of .md prompt files. Stores in Cosmos platform-config.prompts."""
    if not file.filename or not (file.filename.endswith(".tar.gz") or file.filename.endswith(".tgz")):
        raise HTTPException(400, "File must be a .tar.gz archive")

    content = await file.read()
    logger.info("Prompts upload: %s (%d bytes)", file.filename, len(content))

    async def stream():
        progress: asyncio.Queue = asyncio.Queue()
        def emit(step, detail, pct):
            progress.put_nowait({"step": step, "detail": detail, "pct": pct})

        async def run():
            try:
                with tempfile.TemporaryDirectory() as tmpdir:
                    tmppath = Path(tmpdir)
                    with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as tar:
                        tar.extractall(tmppath, filter="data")

                    sc_name = "default"
                    for root, dirs, files in os.walk(tmppath):
                        if "scenario.yaml" in files:
                            m = yaml.safe_load(Path(root, "scenario.yaml").read_text())
                            sc_name = m.get("name", "default")
                            break

                    # Find all .md files
                    all_md = list(tmppath.rglob("*.md"))
                    if not all_md:
                        emit("error", "No .md prompt files found in archive", -1)
                        progress.put_nowait(None)
                        return

                    emit("prompts", f"Found {len(all_md)} .md files for scenario '{sc_name}'", 10)

                    if not COSMOS_NOSQL_ENDPOINT:
                        emit("error", "COSMOS_NOSQL_ENDPOINT not configured", -1)
                        progress.put_nowait(None)
                        return

                    def _store():
                        from router_prompts import _get_prompts_container
                        container = _get_prompts_container(sc_name, ensure_created=True)
                        stored = []

                        # Find prompts dir (parent of graph_explorer/ or where prompt .md files live)
                        prompts_dir = None
                        for md in all_md:
                            if md.name in PROMPT_AGENT_MAP:
                                prompts_dir = md.parent
                                break
                        if not prompts_dir:
                            prompts_dir = all_md[0].parent

                        # Store individual prompts
                        for md_file in all_md:
                            if md_file.parent.name == "graph_explorer":
                                continue  # handled separately below
                            agent = PROMPT_AGENT_MAP.get(md_file.name)
                            if not agent:
                                continue
                            txt = md_file.read_text()
                            existing = list(container.query_items(
                                query="SELECT c.version FROM c WHERE c.agent = @a AND c.scenario = @s AND c.name = @n ORDER BY c.version DESC",
                                parameters=[{"name": "@a", "value": agent}, {"name": "@s", "value": sc_name}, {"name": "@n", "value": md_file.stem}],
                                enable_cross_partition_query=False,
                            ))
                            nv = (existing[0]["version"] + 1) if existing else 1
                            did = f"{sc_name}__{md_file.stem}__v{nv}"
                            container.upsert_item({
                                "id": did, "agent": agent, "scenario": sc_name,
                                "name": md_file.stem, "version": nv, "content": txt,
                                "description": f"Uploaded from {sc_name}-prompts.tar.gz",
                                "tags": [sc_name, agent], "is_active": True, "deleted": False,
                                "created_at": datetime.now(timezone.utc).isoformat(), "created_by": "ui-upload",
                            })
                            stored.append(did)
                            emit("prompts", f"Stored {agent}: {md_file.name} (v{nv})", 20 + len(stored) * 8)

                        # Compose GraphExplorer from graph_explorer/ subdirectory
                        ge_dir = prompts_dir / "graph_explorer"
                        if not ge_dir.exists():
                            # Try finding it anywhere
                            for d in tmppath.rglob("graph_explorer"):
                                if d.is_dir():
                                    ge_dir = d
                                    break
                        if ge_dir.exists():
                            parts = []
                            for pn in ["core_instructions.md", "core_schema.md", "language_gremlin.md"]:
                                pf = ge_dir / pn
                                if pf.exists():
                                    parts.append(pf.read_text())
                            if parts:
                                composed = "\n\n---\n\n".join(parts)
                                existing = list(container.query_items(
                                    query="SELECT c.version FROM c WHERE c.agent = 'graph_explorer' AND c.scenario = @s AND c.name = 'graph_explorer' ORDER BY c.version DESC",
                                    parameters=[{"name": "@s", "value": sc_name}],
                                    enable_cross_partition_query=False,
                                ))
                                nv = (existing[0]["version"] + 1) if existing else 1
                                did = f"{sc_name}__graph_explorer__v{nv}"
                                container.upsert_item({
                                    "id": did, "agent": "graph_explorer", "scenario": sc_name,
                                    "name": "graph_explorer", "version": nv, "content": composed,
                                    "description": f"Composed from graph_explorer/ ({sc_name})",
                                    "tags": [sc_name, "graph_explorer", "composed"],
                                    "is_active": True, "deleted": False,
                                    "created_at": datetime.now(timezone.utc).isoformat(), "created_by": "ui-upload",
                                })
                                stored.append(did)
                                emit("prompts", f"Stored graph_explorer (composed, v{nv})", 90)

                        return stored

                    stored = await asyncio.to_thread(_store)
                    emit("done", f"Stored {len(stored)} prompts for '{sc_name}'", 100)
                    progress.put_nowait({"_result": {"scenario": sc_name, "prompts_stored": len(stored), "ids": stored}})
            except Exception as e:
                logger.exception("Prompts upload failed")
                progress.put_nowait({"step": "error", "detail": str(e), "pct": -1})
            finally:
                progress.put_nowait(None)

        task = asyncio.create_task(run())
        while True:
            ev = await progress.get()
            if ev is None:
                break
            if "_result" in ev:
                yield {"event": "complete", "data": json.dumps(ev["_result"])}
            elif ev.get("step") == "error":
                yield {"event": "error", "data": json.dumps({"error": ev["detail"]})}
            else:
                yield {"event": "progress", "data": json.dumps(ev)}
        await task

    return EventSourceResponse(stream())
