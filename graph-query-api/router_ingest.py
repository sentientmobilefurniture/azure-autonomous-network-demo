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
import logging
import os
import tarfile
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml
from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from gremlin_python.driver import client, serializer
from gremlin_python.driver.protocol import GremlinServerError

from config import (
    get_credential,
)
from adapters.cosmos_config import (
    COSMOS_GREMLIN_ENDPOINT,
    COSMOS_GREMLIN_PRIMARY_KEY,
    COSMOS_GREMLIN_DATABASE,
    COSMOS_GREMLIN_GRAPH,
    COSMOS_NOSQL_ENDPOINT,
)

logger = logging.getLogger("graph-query-api.ingest")

router = APIRouter(prefix="/query", tags=["scenarios"])


# ---------------------------------------------------------------------------
# Manifest normalization (backward compat: v1.0 → v2.0 schema)
# ---------------------------------------------------------------------------


def _normalize_manifest(manifest: dict) -> dict:
    """Normalize old-format manifest to the v2.0 data_sources format.

    Supports both old (cosmos: / search_indexes:) and new (data_sources:)
    formats. If data_sources already exists, returns as-is.
    """
    if "data_sources" in manifest:
        return manifest  # already new format

    ds: dict = {}
    cosmos = manifest.get("cosmos", {})
    sc_name = manifest.get("name", "")

    if cosmos.get("gremlin"):
        gremlin_cfg = cosmos["gremlin"]
        graph_name = gremlin_cfg.get("graph", "topology")
        # Old format used unprefixed names — add scenario prefix
        if sc_name and not graph_name.startswith(sc_name):
            graph_name = f"{sc_name}-{graph_name}"
        ds["graph"] = {
            "connector": "cosmosdb-gremlin",
            "config": {
                "database": gremlin_cfg.get("database", "networkgraph"),
                "graph": graph_name,
                "partition_key": "/partitionKey",
            },
            "schema_file": "graph_schema.yaml",
        }

    if cosmos.get("nosql"):
        nosql_cfg = cosmos["nosql"]
        ds["telemetry"] = {
            "connector": "cosmosdb-nosql",
            "config": {
                "database": nosql_cfg.get("database", "telemetry"),
                "container_prefix": sc_name,
                "containers": nosql_cfg.get("containers", []),
            },
        }

    old_indexes = manifest.get("search_indexes", [])
    if old_indexes:
        si: dict = {}
        for idx in old_indexes:
            key = idx.get("container", idx["name"].split("-")[0])
            si[key] = {
                "index_name": f"{sc_name}-{idx['name']}" if sc_name and not idx["name"].startswith(sc_name) else idx["name"],
                "source": idx.get("source", ""),
                "blob_container": idx.get("container", key),
            }
        ds["search_indexes"] = si

    manifest["data_sources"] = ds
    return manifest


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
# ARM NoSQL container creation (shared databases)
# ---------------------------------------------------------------------------


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

    from azure.mgmt.cosmosdb import CosmosDBManagementClient
    mgmt = CosmosDBManagementClient(get_credential(), sub_id)

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



# ---------------------------------------------------------------------------
# Endpoints — listing, deletion
# ---------------------------------------------------------------------------

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
                    from azure.mgmt.cosmosdb import CosmosDBManagementClient
                    from azure.identity import DefaultAzureCredential
                    mgmt = CosmosDBManagementClient(DefaultAzureCredential(), sub_id)
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

from sse_helpers import SSEProgress, sse_upload_response
from cosmos_helpers import get_cosmos_client


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


def _resolve_scenario_name(
    tmppath: Path, override: str | None, fallback: str = "default",
) -> str:
    """Resolve scenario name: override > scenario.yaml > fallback."""
    if override:
        return override
    for root, _dirs, files in os.walk(tmppath):
        if "scenario.yaml" in files:
            m = yaml.safe_load(Path(root, "scenario.yaml").read_text())
            return m.get("name", fallback)
    return fallback


# ── graph ─────────────────────────────────────────────────────────────────


def _prepare_vertices_from_schema(schema: dict, data_dir: Path) -> list[dict]:
    """Convert graph_schema.yaml vertex definitions + CSV data → flat dicts."""
    vertices = []
    for vdef in schema.get("vertices", []):
        csv_path = data_dir / vdef["csv_file"]
        if not csv_path.exists():
            continue
        rows = _read_csv(csv_path)
        for row in rows:
            props = {}
            for p in vdef.get("properties", []):
                if p in row:
                    props[p] = row[p]
            vertices.append({
                "label": vdef["label"],
                "id": row[vdef["id_column"]],
                "partition_key": vdef["partition_key"],
                "properties": props,
            })
    return vertices


def _prepare_edges_from_schema(schema: dict, data_dir: Path) -> list[dict]:
    """Convert graph_schema.yaml edge definitions + CSV data → flat dicts."""
    edges = []
    for edef in schema.get("edges", []):
        csv_path = data_dir / edef["csv_file"]
        if not csv_path.exists():
            continue
        rows = _read_csv(csv_path)
        # Apply optional filter
        rf = edef.get("filter")
        if rf:
            negate = rf.get("negate", False)
            rows = [
                r for r in rows
                if (r.get(rf["column"]) != rf["value"]) == negate
            ]
        src, tgt = edef["source"], edef["target"]
        for row in rows:
            props = {}
            for ep in edef.get("properties", []):
                if "column" in ep:
                    props[ep["name"]] = row[ep["column"]]
                elif "value" in ep:
                    props[ep["name"]] = ep["value"]
            edges.append({
                "label": edef["label"],
                "source": {
                    "label": src["label"],
                    "property": src["property"],
                    "value": row[src["column"]],
                },
                "target": {
                    "label": tgt["label"],
                    "property": tgt["property"],
                    "value": row[tgt["column"]],
                },
                "properties": props,
            })
    return edges


@router.post("/upload/graph", summary="Upload graph data only")
async def upload_graph(
    file: UploadFile = File(...),
    scenario_name: str | None = Query(
        default=None, description="Override scenario name from scenario.yaml"
    ),
):
    """Upload a tarball containing scenario.yaml + graph_schema.yaml + data/entities/*.csv.
    Loads vertices and edges into Cosmos Gremlin. Returns SSE progress.
    If scenario_name is provided, it overrides the name from scenario.yaml."""
    if not file.filename or not (
        file.filename.endswith(".tar.gz") or file.filename.endswith(".tgz")
    ):
        raise HTTPException(400, "File must be a .tar.gz archive")

    content = await file.read()
    logger.info(
        "Graph upload: %s (%d bytes), scenario_name=%s",
        file.filename, len(content), scenario_name,
    )

    async def work(progress: SSEProgress):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            scenario_dir = _extract_tar(content, tmppath)

            manifest = yaml.safe_load((scenario_dir / "scenario.yaml").read_text())
            manifest = _normalize_manifest(manifest)
            schema = yaml.safe_load((scenario_dir / "graph_schema.yaml").read_text())
            sc_name = scenario_name or manifest["name"]

            # Persist full config if agents section present (Phase 8)
            if "agents" in manifest:
                from config_store import save_scenario_config
                await save_scenario_config(sc_name, manifest)
                progress.emit("config", f"Saved scenario config for '{sc_name}'", 12)

            # Extract metadata for frontend passthrough
            scenario_metadata = {
                "display_name": manifest.get("display_name"),
                "description": manifest.get("description"),
                "use_cases": manifest.get("use_cases"),
                "example_questions": manifest.get("example_questions"),
                "graph_styles": manifest.get("graph_styles"),
                "domain": manifest.get("domain"),
            }

            graph_cfg = manifest.get("data_sources", {}).get("graph", {}).get("config", {})
            gremlin_graph = graph_cfg.get("graph", f"{sc_name}-topology")
            data_dir = scenario_dir / schema.get("data_dir", "data/entities")

            progress.emit("graph", "Preparing graph data from schema...", 15)

            # Transform schema + CSV → generic dicts
            vertices = _prepare_vertices_from_schema(schema, data_dir)
            edges = _prepare_edges_from_schema(schema, data_dir)

            progress.emit(
                "graph",
                f"Prepared {len(vertices)} vertices, {len(edges)} edges",
                20,
            )

            # Use GraphBackend.ingest() instead of raw Gremlin calls
            from backends import get_backend_for_graph

            backend = get_backend_for_graph(gremlin_graph)

            def progress_adapter(message: str, current: int, total: int):
                pct = 20 + int(current / max(total, 1) * 75)
                progress.emit("graph", message, pct)

            result = await backend.ingest(
                vertices, edges,
                graph_name=gremlin_graph,
                graph_database=COSMOS_GREMLIN_DATABASE,
                on_progress=progress_adapter,
            )

            total_v = result["vertices_loaded"]
            total_e = result["edges_loaded"]
            progress.emit(
                "done",
                f"Graph loaded: {total_v} vertices, {total_e} edges → {gremlin_graph}",
                100,
            )
            progress.complete({
                "scenario": sc_name,
                "graph": gremlin_graph,
                "vertices": total_v,
                "edges": total_e,
                "errors": result.get("errors", []),
                "scenario_metadata": scenario_metadata,
            })

    return sse_upload_response(work, error_label="graph upload")


# ── telemetry ─────────────────────────────────────────────────────────────


@router.post("/upload/telemetry", summary="Upload telemetry data only")
async def upload_telemetry(
    file: UploadFile = File(...),
    scenario_name: str | None = Query(
        default=None, description="Override scenario name from scenario.yaml"
    ),
):
    """Upload a tarball containing scenario.yaml + data/telemetry/*.csv.
    Loads into Cosmos NoSQL. Runs entirely in a background thread.
    If scenario_name is provided, it overrides the name from scenario.yaml."""
    if not file.filename or not (
        file.filename.endswith(".tar.gz") or file.filename.endswith(".tgz")
    ):
        raise HTTPException(400, "File must be a .tar.gz archive")

    content = await file.read()
    logger.info(
        "Telemetry upload: %s (%d bytes), scenario_name=%s",
        file.filename, len(content), scenario_name,
    )

    async def work(progress: SSEProgress):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            scenario_dir = _extract_tar(content, tmppath)

            manifest = yaml.safe_load((scenario_dir / "scenario.yaml").read_text())
            manifest = _normalize_manifest(manifest)
            sc_name = scenario_name or manifest["name"]

            # Persist full config if agents section present (Phase 8)
            if "agents" in manifest:
                from config_store import save_scenario_config
                await save_scenario_config(sc_name, manifest)

            telemetry_cfg = manifest.get("data_sources", {}).get("telemetry", {}).get("config", {})

            nosql_db = telemetry_cfg.get("database", "telemetry")
            containers_config = telemetry_cfg.get("containers", [])
            telemetry_dir = scenario_dir / manifest.get(
                "paths", {},
            ).get("telemetry", "data/telemetry")

            if not COSMOS_NOSQL_ENDPOINT:
                progress.error("COSMOS_NOSQL_ENDPOINT not configured")
                return

            progress.emit(
                "telemetry",
                f"Loading into shared database '{nosql_db}' (scenario prefix '{sc_name}')...",
                10,
            )

            for cdef in containers_config:
                cdef["original_name"] = cdef["name"]
                cdef["name"] = f"{sc_name}-{cdef['name']}"

            await asyncio.to_thread(
                _ensure_nosql_containers, nosql_db, containers_config, progress.emit,
            )

            def _load():
                cosmos = get_cosmos_client()
                db = cosmos.get_database_client(nosql_db)
                for ci, cdef in enumerate(containers_config):
                    cname = cdef["name"]
                    original_name = cdef.get("original_name", cname)
                    csv_file = cdef.get("csv_file", f"{original_name}.csv")
                    csv_path = telemetry_dir / csv_file
                    if not csv_path.exists():
                        progress.emit("telemetry", f"⚠ {csv_file} not found — skipping", 20)
                        continue
                    pct = 20 + int(70 * ci / max(len(containers_config), 1))
                    progress.emit("telemetry", f"Loading {cname}...", pct)
                    container = db.get_container_client(cname)
                    rows = _read_csv(csv_path)
                    progress.emit("telemetry", f"Upserting {len(rows)} docs into {cname}...", pct + 10)
                    for row in rows:
                        for nf in cdef.get("numeric_fields", []):
                            if nf in row and row[nf]:
                                try:
                                    row[nf] = float(row[nf])
                                except (ValueError, TypeError):
                                    pass
                        id_field = cdef.get("id_field")
                        if id_field and id_field in row:
                            row["id"] = row[id_field]
                        elif "id" not in row:
                            keys = list(row.keys())
                            row["id"] = f"{row.get(keys[0], '')}-{row.get(keys[1], '')}"
                        container.upsert_item(row)
                    progress.emit("telemetry", f"✓ {cname}: {len(rows)} docs", pct + 20)
                return len(containers_config)

            count = await asyncio.to_thread(_load)
            progress.emit("done", f"Telemetry loaded: {count} containers → {nosql_db}", 100)
            progress.complete({
                "scenario": sc_name, "database": nosql_db, "containers": count,
            })

    return sse_upload_response(work, error_label="telemetry upload")


# ── shared knowledge-file upload (runbooks + tickets) ─────────────────────


async def _upload_knowledge_files(
    content: bytes,
    scenario_default: str,
    scenario_override: str | None,
    file_ext: str,
    type_label: str,
    progress: SSEProgress,
) -> None:
    """Shared logic for runbooks (.md) and tickets (.txt) upload to blob + AI Search."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as tar:
            tar.extractall(tmppath, filter="data")

        sc_name = _resolve_scenario_name(tmppath, scenario_override, scenario_default)

        matched_files = list(tmppath.rglob(f"*{file_ext}"))
        if not matched_files:
            progress.error(f"No {file_ext} files found in archive")
            return

        progress.emit(type_label, f"Found {len(matched_files)} {type_label} files", 10)

        storage_account = os.getenv("STORAGE_ACCOUNT_NAME", "")
        ai_search = os.getenv("AI_SEARCH_NAME", "")
        if not storage_account:
            progress.error("STORAGE_ACCOUNT_NAME not configured")
            return

        container_name = f"{sc_name}-{type_label}"
        index_name = f"{sc_name}-{type_label}-index"

        def _upload_and_index():
            from services.blob_uploader import upload_files_to_blob

            upload_files_to_blob(
                container_name,
                matched_files,
                on_progress=lambda msg: progress.emit(type_label, msg, 50),
            )

            if ai_search:
                progress.emit(type_label, f"Creating search index '{index_name}'...", 60)
                from search_indexer import create_search_index

                result = create_search_index(
                    index_name=index_name,
                    container_name=container_name,
                    on_progress=lambda msg: progress.emit(type_label, msg, 80),
                )
                return result
            return {"index_name": index_name, "status": "blob_only"}

        result = await asyncio.to_thread(_upload_and_index)
        progress.emit("done", f"{type_label.title()} indexed: {index_name}", 100)
        progress.complete({"scenario": sc_name, "index": index_name, **result})


@router.post("/upload/runbooks", summary="Upload runbooks only")
async def upload_runbooks(
    file: UploadFile = File(...),
    scenario: str = "default",
    scenario_name: str | None = Query(
        default=None,
        description="Override scenario name (takes priority over scenario.yaml and scenario param)",
    ),
):
    """Upload a tarball of .md runbook files. Uploads to blob + creates AI Search index.
    If scenario_name is provided, it overrides both the scenario param and scenario.yaml."""
    if not file.filename or not (
        file.filename.endswith(".tar.gz") or file.filename.endswith(".tgz")
    ):
        raise HTTPException(400, "File must be a .tar.gz archive")

    content = await file.read()
    logger.info(
        "Runbooks upload: %s (%d bytes), scenario=%s, scenario_name=%s",
        file.filename, len(content), scenario, scenario_name,
    )

    async def work(progress: SSEProgress):
        await _upload_knowledge_files(
            content, scenario, scenario_name,
            file_ext=".md", type_label="runbooks", progress=progress,
        )

    return sse_upload_response(work, error_label="runbooks upload")


@router.post("/upload/tickets", summary="Upload tickets only")
async def upload_tickets(
    file: UploadFile = File(...),
    scenario: str = "default",
    scenario_name: str | None = Query(
        default=None,
        description="Override scenario name (takes priority over scenario.yaml and scenario param)",
    ),
):
    """Upload a tarball of .txt ticket files. Uploads to blob + creates AI Search index.
    If scenario_name is provided, it overrides both the scenario param and scenario.yaml."""
    if not file.filename or not (
        file.filename.endswith(".tar.gz") or file.filename.endswith(".tgz")
    ):
        raise HTTPException(400, "File must be a .tar.gz archive")

    content = await file.read()
    logger.info(
        "Tickets upload: %s (%d bytes), scenario=%s, scenario_name=%s",
        file.filename, len(content), scenario, scenario_name,
    )

    async def work(progress: SSEProgress):
        await _upload_knowledge_files(
            content, scenario, scenario_name,
            file_ext=".txt", type_label="tickets", progress=progress,
        )

    return sse_upload_response(work, error_label="tickets upload")


# ── prompts ───────────────────────────────────────────────────────────────

# Legacy hardcoded prompt-to-agent mapping (backward compatibility).
# Config-driven scenarios use the agents[].instructions_file field instead.
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


def _build_prompt_agent_map_from_config(config: dict) -> dict[str, str]:
    """Build filename → agent_role mapping from scenario config agents section.

    For each agent in config['agents'], maps its instructions_file basename
    to the agent's role. Handles both single files and directories
    (compose_with_connector).

    Returns:
        Dict mapping prompt filename → agent role string.
    """
    mapping: dict[str, str] = {}
    for agent_def in config.get("agents", []):
        role = agent_def.get("role", agent_def["name"])
        instr = agent_def.get("instructions_file", "")
        if not instr:
            continue
        # Directory reference (ends with /) → store directory name as key
        if instr.endswith("/"):
            dir_name = instr.rstrip("/").split("/")[-1]
            mapping[f"__dir__{dir_name}"] = role
        else:
            # Single file → map basename
            fname = instr.split("/")[-1]
            mapping[fname] = role
    return mapping


def _get_composed_agents_from_config(config: dict) -> dict[str, dict]:
    """Extract agents that use compose_with_connector from config.

    Returns:
        Dict mapping directory name → agent config dict.
    """
    result: dict[str, dict] = {}
    for agent_def in config.get("agents", []):
        if agent_def.get("compose_with_connector"):
            instr = agent_def.get("instructions_file", "")
            if instr.endswith("/"):
                dir_name = instr.rstrip("/").split("/")[-1]
                result[dir_name] = agent_def
    return result


def _resolve_connector_for_agent(agent_def: dict, config: dict) -> str:
    """Determine which data source connector an agent uses.

    Looks at the agent's tools to find the first tool that references a
    data source, then returns that data source's connector type.
    """
    ds = config.get("data_sources", {})
    for tool_def in agent_def.get("tools", []):
        if tool_def.get("type") == "openapi":
            template = tool_def.get("spec_template", "")
            if template == "graph" and "graph" in ds:
                return ds["graph"].get("connector", "cosmosdb-gremlin")
            if template == "telemetry" and "telemetry" in ds:
                return ds["telemetry"].get("connector", "cosmosdb-nosql")
    return "cosmosdb-gremlin"


@router.post("/upload/prompts", summary="Upload prompts to Cosmos DB")
async def upload_prompts(
    file: UploadFile = File(...),
    scenario_name: str | None = Query(
        default=None, description="Override scenario name from scenario.yaml"
    ),
):
    """Upload a tarball of .md prompt files. Stores in Cosmos platform-config.prompts.
    If scenario_name is provided, it overrides the name from scenario.yaml."""
    if not file.filename or not (
        file.filename.endswith(".tar.gz") or file.filename.endswith(".tgz")
    ):
        raise HTTPException(400, "File must be a .tar.gz archive")

    content = await file.read()
    logger.info(
        "Prompts upload: %s (%d bytes), scenario_name=%s",
        file.filename, len(content), scenario_name,
    )

    async def work(progress: SSEProgress):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as tar:
                tar.extractall(tmppath, filter="data")

            sc_name = _resolve_scenario_name(tmppath, scenario_name)

            all_md = list(tmppath.rglob("*.md"))
            if not all_md:
                progress.error("No .md prompt files found in archive")
                return

            progress.emit("prompts", f"Found {len(all_md)} .md files for scenario '{sc_name}'", 10)

            if not COSMOS_NOSQL_ENDPOINT:
                progress.error("COSMOS_NOSQL_ENDPOINT not configured")
                return

            # Try to load scenario config for config-driven prompt mapping
            scenario_config: dict | None = None
            try:
                from config_store import fetch_scenario_config
                scenario_config = await fetch_scenario_config(sc_name)
                progress.emit("prompts", "Using config-driven prompt mapping", 12)
            except Exception:
                progress.emit("prompts", "No scenario config — using legacy prompt mapping", 12)

            # Build prompt-to-agent mapping
            if scenario_config and scenario_config.get("agents"):
                config_prompt_map = _build_prompt_agent_map_from_config(scenario_config)
                composed_agents = _get_composed_agents_from_config(scenario_config)
            else:
                config_prompt_map = {}
                composed_agents = {}

            def _store():
                from cosmos_helpers import get_or_create_container

                container = get_or_create_container(
                    "prompts", sc_name, "/agent", ensure_created=True,
                )
                stored = []

                # Derive graph name for placeholder substitution
                graph_name = f"{sc_name}-topology"

                def _sub(text: str) -> str:
                    """Replace {graph_name} and {scenario_prefix} placeholders."""
                    return text.replace("{graph_name}", graph_name).replace("{scenario_prefix}", sc_name)

                # Find prompts dir (parent of graph_explorer/ or where prompt .md files live)
                prompts_dir = None
                for md in all_md:
                    if md.name in PROMPT_AGENT_MAP or md.name in config_prompt_map:
                        prompts_dir = md.parent
                        break
                if not prompts_dir:
                    prompts_dir = all_md[0].parent

                # Determine which directories are composed (from config or legacy)
                composed_dir_names = set(composed_agents.keys()) if composed_agents else {"graph_explorer"}

                # Store individual prompts
                for md_file in all_md:
                    # Skip files in composed directories — handled separately
                    if md_file.parent.name in composed_dir_names:
                        continue

                    # Resolve agent role: config-driven first, then legacy fallback
                    agent = config_prompt_map.get(md_file.name) or PROMPT_AGENT_MAP.get(md_file.name)
                    if not agent:
                        continue

                    txt = _sub(md_file.read_text())
                    existing = list(container.query_items(
                        query=(
                            "SELECT c.version FROM c "
                            "WHERE c.agent = @a AND c.scenario = @s AND c.name = @n "
                            "ORDER BY c.version DESC"
                        ),
                        parameters=[
                            {"name": "@a", "value": agent},
                            {"name": "@s", "value": sc_name},
                            {"name": "@n", "value": md_file.stem},
                        ],
                        enable_cross_partition_query=False,
                    ))
                    nv = (existing[0]["version"] + 1) if existing else 1
                    did = f"{sc_name}__{md_file.stem}__v{nv}"
                    container.upsert_item({
                        "id": did, "agent": agent, "scenario": sc_name,
                        "name": md_file.stem, "version": nv, "content": txt,
                        "description": f"Uploaded from {sc_name}-prompts.tar.gz",
                        "tags": [sc_name, agent], "is_active": True, "deleted": False,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "created_by": "ui-upload",
                    })
                    stored.append(did)
                    progress.emit(
                        "prompts",
                        f"Stored {agent}: {md_file.name} (v{nv})",
                        20 + len(stored) * 8,
                    )

                # Compose prompts from subdirectories
                for dir_name in composed_dir_names:
                    comp_dir = prompts_dir / dir_name
                    if not comp_dir.exists():
                        for d in tmppath.rglob(dir_name):
                            if d.is_dir():
                                comp_dir = d
                                break
                    if not comp_dir.exists():
                        continue

                    # Determine agent role for this directory
                    agent_role = config_prompt_map.get(f"__dir__{dir_name}", dir_name)

                    # Determine which language file to use
                    if dir_name in composed_agents and scenario_config:
                        agent_def = composed_agents[dir_name]
                        connector = _resolve_connector_for_agent(agent_def, scenario_config)
                        language_suffix = connector.split("-")[-1]  # "gremlin", "nosql", "kusto"
                        language_file = f"language_{language_suffix}.md"
                    else:
                        # Legacy: always use gremlin
                        language_file = "language_gremlin.md"

                    # Collect all .md files, skip non-matching language files
                    parts = []
                    for pf in sorted(comp_dir.glob("*.md")):
                        if pf.name.startswith("language_") and pf.name != language_file:
                            continue
                        parts.append(pf.read_text())

                    if parts:
                        composed = _sub("\n\n---\n\n".join(parts))
                        existing = list(container.query_items(
                            query=(
                                "SELECT c.version FROM c "
                                f"WHERE c.agent = @a "
                                "AND c.scenario = @s AND c.name = @n "
                                "ORDER BY c.version DESC"
                            ),
                            parameters=[
                                {"name": "@a", "value": agent_role},
                                {"name": "@s", "value": sc_name},
                                {"name": "@n", "value": dir_name},
                            ],
                            enable_cross_partition_query=False,
                        ))
                        nv = (existing[0]["version"] + 1) if existing else 1
                        did = f"{sc_name}__{dir_name}__v{nv}"
                        container.upsert_item({
                            "id": did, "agent": agent_role, "scenario": sc_name,
                            "name": dir_name, "version": nv, "content": composed,
                            "description": f"Composed from {dir_name}/ ({sc_name})",
                            "tags": [sc_name, agent_role, "composed"],
                            "is_active": True, "deleted": False,
                            "created_at": datetime.now(timezone.utc).isoformat(),
                            "created_by": "ui-upload",
                        })
                        stored.append(did)
                        progress.emit("prompts", f"Stored {agent_role} (composed from {dir_name}/, v{nv})", 90)

                return stored

            stored = await asyncio.to_thread(_store)
            progress.emit("done", f"Stored {len(stored)} prompts for '{sc_name}'", 100)
            progress.complete({
                "scenario": sc_name,
                "prompts_stored": len(stored),
                "ids": stored,
            })

    return sse_upload_response(work, error_label="prompts upload")
