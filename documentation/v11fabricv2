# Fabric Integration — V11 Revised Plan (Config-Native Architecture)

> **Created:** 2026-02-16
> **Audited:** 2026-02-16 (cross-referenced against `fabric_implementation_references/` and V10 codebase)
> **Status:** ⬜ Not Started
> **Depends on:** V10 — Config-Driven Multi-Agent Orchestration (in progress)
> **Supersedes:** `V11Fabric.md` (service-separation architecture — abandoned)
> **Goal:** Add Microsoft Fabric as an alternative graph + telemetry backend,
> integrated as **additional connectors** within the existing config-driven
> architecture — no new services, no directory renames, no new ports.

---

## The Core Insight

The V10 config-driven architecture already solves the hard problems:

- **Backend Registry** (`backends/__init__.py`) — string-keyed, auto-registration,
  per-graph caching. Adding a Fabric backend = one new file + one `register_backend()` call.
- **Connector-aware provisioner** (`agent_provisioner.py`) — reads `data_sources.graph.connector`
  from `scenario.yaml` to select OpenAPI spec templates. Adding Fabric = one new connector
  key + one new template.
- **GraphBackend Protocol** — `execute_query()`, `get_topology()`, `ingest()`, `close()`.
  A Fabric implementation satisfies the same protocol. The router doesn't change.
- **OpenAPI Spec Templating** — `{query_language_description}` already parameterises
  the query language per connector. Fabric GQL is just another query language description.
- **Composed prompts** — `graph_explorer/language_gremlin.md` already shows the pattern.
  Add `language_gql.md` and the prompt composition logic picks the right file per connector.
- **ScenarioContext** — per-request context derived from `X-Graph` header. Fabric scenarios
  use the same header, same routing, same everything.

**Fabric is not a new architecture. It's a new row in the config.**

A Fabric scenario's `scenario.yaml` simply declares:

```yaml
data_sources:
  graph:
    connector: "fabric-gql"
    config:
      workspace_id: "${FABRIC_WORKSPACE_ID}"
      graph_model_id: "${FABRIC_GRAPH_MODEL_ID}"
      graph: "telco-noc-fabric-topology"
  telemetry:
    connector: "fabric-kql"
    config:
      eventhouse_query_uri: "${EVENTHOUSE_QUERY_URI}"
      kql_database: "${FABRIC_KQL_DB_NAME}"
      container_prefix: "telco-noc-fabric"
      containers:
        - name: AlertStream
          # ...
        - name: LinkTelemetry
          # ...
```

The platform reads the connector type, instantiates the right backend, templates
the right OpenAPI spec, composes the right prompt language file, and everything
flows through the existing `/query/graph`, `/query/telemetry`, `/query/topology`
endpoints. CosmosDB and Fabric scenarios coexist — the user switches between them
the same way they switch between any two scenarios.

---

## What Changed From V11Fabric.md

| V11Fabric.md (abandoned) | This plan |
|--------------------------|-----------|
| New `fabric-graph-api` service on port 8200 | No new service. Fabric backend lives inside `graph-query-api` as `backends/fabric.py` |
| New `/fabric/*` URL prefix in nginx | No nginx changes. Fabric uses existing `/query/*` endpoints |
| Directory rename `graph-query-api` → `cosmosdb-graph-api` | No rename. The service was always backend-agnostic by design (post-V10) |
| Two supervisord processes, two Dockerfiles | No supervisord changes. Same 3-process container |
| Separate `pyproject.toml`, `config.py`, `models.py` | Fabric config goes in `adapters/fabric_config.py`. Shared models in existing `models.py` |
| Frontend health-checks two services, `/fabric/*` vs `/query/*` routing | Frontend is scenario-aware — it sends `X-Graph` header, backend dispatch is automatic |
| Complex frontend "backend selector" dropdown | No dropdown. User selects a scenario. If that scenario uses `fabric-gql`, the Fabric backend is used. Transparent. |
| 6 implementation phases | 4 phases, smaller scope, fewer files |
| ~15 files to create/modify | ~8 files to create/modify |

**Why this is better:**

1. **Zero infrastructure changes.** Nginx, supervisord, Dockerfile, `deploy.sh`, `azure.yaml` — untouched.
2. **Zero frontend routing changes.** The frontend already sends `X-Graph` and calls `/query/*`. It doesn't care which backend handles the query.
3. **True coexistence.** A CosmosDB scenario and a Fabric scenario are just two entries in the scenario list. Switch between them like switching between any two scenarios.
4. **Backend selection is per-request, not per-deployment.** The Backend Registry caches backends per `(backend_type, graph_name)`. Multiple backends can be active simultaneously.
5. **Smaller blast radius.** Fabric code is isolated in `backends/fabric.py` + `adapters/fabric_config.py`. If it fails, only Fabric scenarios are affected.

---

## Requirements

### From V11Fabric.md (retained, reframed)

1. Fabric workspace ID provided via env var or scenario config
2. Read available ontologies — **Fabric discovery endpoint** (new router)
3. Select desired ontology — **via scenario config or UI Fabric Setup**
4. Read available eventhouses — **Fabric discovery endpoint**
5. Query graph topology and display via graph visualizer — **via existing `/query/topology`**
6. Graph Explorer and Telemetry agents bound to Fabric — **via OpenAPI spec templates**
7. Backend selection in Settings — **replaced by scenario selection** (the scenario's connector determines the backend, no manual toggle needed)
8. Agents query Fabric ontology freely — **via OpenApiTool with GQL language description**

### New requirements (this plan)

9. **Per-scenario backend coexistence:** A user can have `telco-noc` (CosmosDB) and `telco-noc-fabric` (Fabric) loaded simultaneously and switch between them.
10. **Fabric provisioning scripts as orchestrated API** — reuse existing reference scripts via API endpoints in the API service (same pattern as CosmosDB upload SSE).
11. **GQL prompt composition** — `language_gql.md` added to graph_explorer prompt directory, selected based on connector type.
12. **KQL telemetry backend** — Fabric Eventhouse KQL queries through the existing `/query/telemetry` endpoint via a new `FabricKQLBackend` (or extending the telemetry router to support connector dispatch).
13. **Graceful degradation** — if Fabric env vars are missing, Fabric-connector scenarios show a clear error at query time (not at startup). Non-Fabric scenarios are completely unaffected.

---

## Architecture: How It Fits

### Before (V10 — CosmosDB only)

```
scenario.yaml                    graph-query-api (:8100)
  data_sources:                    backends/
    graph:                           __init__.py  (registry)
      connector: "cosmosdb-gremlin"  cosmosdb.py  (CosmosDBGremlinBackend)
    telemetry:                       mock.py      (MockGraphBackend)
      connector: "cosmosdb-nosql"
```

### After (V11 — CosmosDB + Fabric)

```
scenario.yaml                    graph-query-api (:8100)
  data_sources:                    backends/
    graph:                           __init__.py  (registry — 3 backends)
      connector: "fabric-gql"       cosmosdb.py  (CosmosDBGremlinBackend)
    telemetry:                       fabric.py    (FabricGQLBackend)      ← NEW
      connector: "fabric-kql"       mock.py      (MockGraphBackend)
                                   adapters/
                                     cosmos_config.py
                                     fabric_config.py                    ← NEW
```

### Request Flow (Fabric scenario)

```
Browser                          nginx (:80)              graph-query-api (:8100)
  │                                │                         │
  │  POST /query/topology          │                         │
  │  X-Graph: telco-fabric-topo    │                         │
  │ ──────────────────────────────►│──────────────────────► │
  │                                │   proxy_pass :8100      │
  │                                │                         │  get_scenario_context()
  │                                │                         │    → ctx.backend_type = "fabric-gql"
  │                                │                         │    → ctx.graph_name = "telco-fabric-topo"
  │                                │                         │
  │                                │                         │  get_backend_for_context(ctx)
  │                                │                         │    → registry["fabric-gql"]
  │                                │                         │    → FabricGQLBackend(graph_name=...)
  │                                │                         │
  │                                │                         │  backend.get_topology()
  │                                │                         │    → Fabric REST API (GQL MATCH/RETURN)
  │                                │                         │    → parse → {nodes, edges, meta}
  │  ◄─────────────────────────────│◄──────────────────────  │
  │  {nodes, edges, meta}          │                         │
```

The flow is **identical** to a CosmosDB request — only the backend implementation differs.

### What Changes vs What Doesn't

| Layer | Changes? | Detail |
|-------|----------|--------|
| nginx.conf | **No** | Same `/query/*` proxy |
| supervisord.conf | **No** | Same 3 processes |
| Dockerfile | **No** | Same build (Fabric deps added to `graph-query-api/pyproject.toml`) |
| `deploy.sh` | **No** | Maybe add Fabric env var echo in local instructions |
| `azure.yaml` | **No** | Same service definition |
| `vite.config.ts` | **No** | Same `/query` proxy |
| `graph-query-api/main.py` | **No** | Routers already use `get_backend_for_context()` |
| `graph-query-api/router_graph.py` | **No** | Already dispatches via `get_backend_for_context(ctx)` |
| `graph-query-api/router_topology.py` | **No** | Already dispatches via `get_backend_for_context(ctx)` |
| `graph-query-api/config.py` | **Small** | `BACKEND_REQUIRED_VARS` gets a `"fabric-gql"` entry |
| `graph-query-api/backends/__init__.py` | **Small** | Auto-register `FabricGQLBackend` |
| `graph-query-api/backends/fabric.py` | **New** | The actual Fabric GQL implementation |
| `graph-query-api/adapters/fabric_config.py` | **New** | Fabric env var reads |
| `graph-query-api/pyproject.toml` | **Small** | Add `httpx` dependency |
| `openapi/templates/graph.yaml` | **No** | Already templated with `{query_language_description}` |
| `scripts/agent_provisioner.py` | **Small** | Update `CONNECTOR_OPENAPI_VARS["fabric"]` to GQL + add `GRAPH_TOOL_DESCRIPTIONS["fabric"]` |
| Frontend | **Small** | Fabric Setup tab in Settings (for discovery), upload adapts for Fabric — but core routing is unchanged |

---

## Implementation Plan

### Phase 0: Fabric Backend (`backends/fabric.py` + `adapters/fabric_config.py`)

**Scope:** Implement `FabricGQLBackend` satisfying the existing `GraphBackend` Protocol.

#### 0a. `graph-query-api/adapters/fabric_config.py` — Fabric env vars

```python
"""Fabric-specific environment variable reads.

Follows the same adapter pattern as cosmos_config.py.
Imported only by backends/fabric.py — no pollution of shared config.
"""

import os

FABRIC_API_URL = os.getenv("FABRIC_API_URL", "https://api.fabric.microsoft.com/v1")
FABRIC_SCOPE = os.getenv("FABRIC_SCOPE", "https://api.fabric.microsoft.com/.default")
FABRIC_WORKSPACE_ID = os.getenv("FABRIC_WORKSPACE_ID", "")
FABRIC_GRAPH_MODEL_ID = os.getenv("FABRIC_GRAPH_MODEL_ID", "")
FABRIC_WORKSPACE_NAME = os.getenv("FABRIC_WORKSPACE_NAME", "")
FABRIC_ONTOLOGY_ID = os.getenv("FABRIC_ONTOLOGY_ID", "")
FABRIC_ONTOLOGY_NAME = os.getenv("FABRIC_ONTOLOGY_NAME", "")

# Eventhouse / KQL (for future telemetry)
FABRIC_EVENTHOUSE_ID = os.getenv("FABRIC_EVENTHOUSE_ID", "")
FABRIC_EVENTHOUSE_NAME = os.getenv("FABRIC_EVENTHOUSE_NAME", "")
FABRIC_KQL_DB_ID = os.getenv("FABRIC_KQL_DB_ID", "")
FABRIC_KQL_DB_NAME = os.getenv("FABRIC_KQL_DB_NAME", "")
EVENTHOUSE_QUERY_URI = os.getenv("EVENTHOUSE_QUERY_URI", "")

# Readiness check
FABRIC_CONFIGURED = bool(
    os.getenv("FABRIC_WORKSPACE_ID") and os.getenv("FABRIC_GRAPH_MODEL_ID")
)
```

#### 0b. `graph-query-api/backends/fabric.py` — FabricGQLBackend

Implements the `GraphBackend` Protocol using the Fabric REST API for GQL queries.

```python
"""
Fabric GQL graph backend.

Executes GQL (ISO Graph Query Language) queries against Microsoft Fabric
Graph Models via the REST API. Response format is normalised to the same
{columns, data} / {nodes, edges} shapes as CosmosDBGremlinBackend.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable

import httpx
from fastapi import HTTPException

from config import get_credential
from adapters.fabric_config import (
    FABRIC_API_URL,
    FABRIC_SCOPE,
    FABRIC_WORKSPACE_ID,
    FABRIC_GRAPH_MODEL_ID,
    FABRIC_CONFIGURED,
)

logger = logging.getLogger("graph-query-api.fabric")


class FabricGQLBackend:
    """GraphBackend implementation for Fabric GQL."""

    def __init__(self, graph_name: str = "__default__"):
        self._graph_name = graph_name
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=120.0)
        return self._client

    async def _get_token(self) -> str:
        credential = get_credential()
        token = await asyncio.to_thread(
            credential.get_token, FABRIC_SCOPE
        )
        return token.token

    async def execute_query(self, query: str, **kwargs) -> dict:
        """Execute a GQL query against Fabric Graph Model REST API.

        GQL uses MATCH/RETURN syntax (ISO GQL), NOT GraphQL.
        Example: MATCH (r:CoreRouter) RETURN r.RouterId, r.Hostname

        Endpoint:
            POST /workspaces/{id}/GraphModels/{model_id}/executeQuery?beta=True

        Response shape (Fabric):
            {"status": {...}, "result": {"columns": [...], "data": [...]}}

        We return the normalised: {"columns": [...], "data": [...]}
        """
        if not FABRIC_CONFIGURED:
            raise HTTPException(
                status_code=503,
                detail="Fabric backend not configured. Set FABRIC_WORKSPACE_ID "
                       "and FABRIC_GRAPH_MODEL_ID environment variables.",
            )

        workspace_id = kwargs.get("workspace_id") or FABRIC_WORKSPACE_ID
        graph_model_id = kwargs.get("graph_model_id") or FABRIC_GRAPH_MODEL_ID

        url = (
            f"{FABRIC_API_URL}/workspaces/{workspace_id}"
            f"/GraphModels/{graph_model_id}/executeQuery?beta=True"
        )
        token = await self._get_token()
        client = self._get_client()

        # Retry with exponential backoff for 429s
        max_retries = 5
        for attempt in range(max_retries):
            response = await client.post(
                url,
                json={"query": query},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
            )

            if response.status_code == 429:
                wait = 15 * (attempt + 1)
                logger.warning("Fabric API 429 — retrying in %ds (attempt %d/%d)",
                               wait, attempt + 1, max_retries)
                await asyncio.sleep(wait)
                # Re-acquire token in case it expired during wait
                token = await self._get_token()
                continue

            if response.status_code != 200:
                detail = response.text[:500]
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Fabric GQL query failed: {detail}",
                )

            body = response.json()
            result = body.get("result", body)
            return {
                "columns": result.get("columns", []),
                "data": result.get("data", []),
            }

        raise HTTPException(status_code=429, detail="Fabric API rate limit — retries exhausted")

    async def get_topology(
        self,
        query: str | None = None,
        vertex_labels: list[str] | None = None,
    ) -> dict:
        """Fetch graph topology for visualisation.

        Default GQL query fetches all nodes and edges.
        Returns normalised {nodes, edges} format.
        """
        if query is None:
            query = "MATCH (n) OPTIONAL MATCH (n)-[r]->(m) RETURN n, r, m"

        result = await self.execute_query(query)

        # Parse GQL tabular results into nodes/edges topology format
        nodes_by_id: dict[str, dict] = {}
        edges: list[dict] = []

        for row in result.get("data", []):
            # GQL returns columns like n, r, m — each is a graph element
            for col_name, value in row.items():
                if value is None:
                    continue
                if isinstance(value, dict):
                    elem_type = value.get("_type", "node")
                    if elem_type == "relationship" or "_source" in value or "_target" in value:
                        edge = {
                            "id": value.get("_id", f"e-{len(edges)}"),
                            "source": value.get("_source", ""),
                            "target": value.get("_target", ""),
                            "label": value.get("_label", ""),
                            "properties": {
                                k: v for k, v in value.items()
                                if not k.startswith("_")
                            },
                        }
                        edges.append(edge)
                    else:
                        node_id = value.get("_id", str(id(value)))
                        if node_id not in nodes_by_id:
                            label = value.get("_label", value.get("_labels", ["Unknown"])[0]
                                              if isinstance(value.get("_labels"), list) else "Unknown")
                            # Apply vertex_labels filter
                            if vertex_labels and label not in vertex_labels:
                                continue
                            nodes_by_id[node_id] = {
                                "id": node_id,
                                "label": label,
                                "properties": {
                                    k: v for k, v in value.items()
                                    if not k.startswith("_")
                                },
                            }

        return {
            "nodes": list(nodes_by_id.values()),
            "edges": edges,
        }

    async def ingest(
        self,
        vertices: list[dict],
        edges: list[dict],
        *,
        graph_name: str,
        graph_database: str,
        on_progress: Callable[[str, int, int], None] | None = None,
    ) -> dict:
        """Fabric graph data is loaded via Lakehouse + Ontology, not direct ingest.

        Raises NotImplementedError — data loading for Fabric uses the
        provisioning scripts (Lakehouse CSV upload + Ontology creation).
        """
        raise NotImplementedError(
            "Fabric graphs are populated via Lakehouse + Ontology provisioning, "
            "not direct ingest. Use the Fabric provisioning pipeline."
        )

    def close(self) -> None:
        if self._client and not self._client.is_closed:
            # V10's close_all_backends() checks inspect.isawaitable(result)
            # and awaits it. Return the coroutine so it gets awaited properly.
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._client.aclose())
            except RuntimeError:
                # No event loop — try sync close (shouldn't happen in prod)
                pass
            self._client = None

    async def aclose(self) -> None:
        """Async cleanup — preferred path. Called by close_all_backends()."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
```

#### 0c. Register the backend — `backends/__init__.py`

Add auto-registration alongside the existing CosmosDB and Mock registrations:

```python
# At the bottom of __init__.py, alongside existing registrations:

try:
    from .fabric import FabricGQLBackend
    register_backend("fabric-gql", FabricGQLBackend)
except ImportError:
    import logging
    logging.getLogger("graph-query-api").warning(
        "FabricGQLBackend not available (missing httpx?)"
    )
```

#### 0d. Update `config.py` — Add `fabric-gql` to `BACKEND_REQUIRED_VARS`

```python
BACKEND_REQUIRED_VARS: dict[str, tuple[str, ...]] = {
    "cosmosdb": ("COSMOS_GREMLIN_ENDPOINT", "COSMOS_GREMLIN_PRIMARY_KEY"),
    "fabric-gql": ("FABRIC_WORKSPACE_ID", "FABRIC_GRAPH_MODEL_ID"),  # NEW
    "mock": (),
}
```

#### 0e. Update `graph-query-api/pyproject.toml` — Add `httpx`

```toml
dependencies = [
    # ... existing ...
    "httpx>=0.27.0",  # Fabric REST API client
]
```

#### 0f. Update `config.py` — Backend type resolution from scenario config

Currently `ScenarioContext.backend_type` is always set to `GRAPH_BACKEND` (the global env var).
For per-scenario backend selection, the backend type needs to come from the scenario's
config store when available.

> **⚠️ CRITICAL BUG found during audit:** `get_scenario_context()` is a **synchronous**
> FastAPI dependency, but `fetch_scenario_config()` is `async def`. You cannot call
> `await` inside a sync function. Two approaches:
>
> **Option A (recommended):** Make `get_scenario_context()` async — FastAPI supports
> async dependencies natively. All routers using `Depends(get_scenario_context)` will
> continue to work because they're already async.
>
> **Option B:** Use an in-process sync cache (populated by a startup task or by the
> upload pipeline) instead of calling the async Cosmos-backed config store at request
> time. E.g., a module-level dict updated whenever a scenario is uploaded.
>
> Option A is simpler and correct:

**Approach (Option A):** Make `get_scenario_context()` async and call the async config
store. FastAPI resolves async dependencies correctly.

```python
async def get_scenario_context(
    x_graph: str | None = Header(default=None, alias="X-Graph"),
) -> ScenarioContext:
    graph_name = x_graph or COSMOS_GREMLIN_GRAPH
    prefix = graph_name.rsplit("-", 1)[0] if "-" in graph_name else graph_name

    # Per-scenario backend resolution: check config store for connector type
    backend_type = GRAPH_BACKEND  # default
    try:
        from config_store import fetch_scenario_config
        config = await fetch_scenario_config(prefix)
        connector = (config.get("data_sources", {})
                          .get("graph", {})
                          .get("connector", ""))
        if connector:
            # Map connector name to backend registry key
            # "cosmosdb-gremlin" → "cosmosdb", "fabric-gql" → "fabric-gql"
            CONNECTOR_TO_BACKEND = {
                "cosmosdb-gremlin": "cosmosdb",
                "fabric-gql": "fabric-gql",
                "mock": "mock",
            }
            backend_type = CONNECTOR_TO_BACKEND.get(connector, connector)
    except (ValueError, Exception):
        pass  # No config in store — use env var default

    return ScenarioContext(
        graph_name=graph_name,
        graph_database=COSMOS_GREMLIN_DATABASE,
        telemetry_database="telemetry",
        telemetry_container_prefix=prefix,
        prompts_database="prompts",
        prompts_container=prefix,
        backend_type=backend_type,
    )
```

> **Performance note:** `fetch_scenario_config()` uses `DocumentStore` which has internal
> caching. The config is fetched once and cached in the store's container cache. This adds
> a ~1ms overhead per request (in-memory hit after first fetch). If this becomes a concern,
> add an in-process LRU cache keyed on `prefix`. Note: making `get_scenario_context()`
> async has no performance downside — FastAPI runs async dependencies on the event loop
> without thread-pool overhead (unlike sync dependencies which use `run_in_threadpool()`).

**Files changed in Phase 0:**

| File | Change type |
|------|-------------|
| `graph-query-api/adapters/fabric_config.py` | **New** |
| `graph-query-api/backends/fabric.py` | **New** |
| `graph-query-api/backends/__init__.py` | Small addition (register) |
| `graph-query-api/config.py` | Small addition (BACKEND_REQUIRED_VARS + per-scenario resolution) |
| `graph-query-api/pyproject.toml` | Small addition (httpx) |

**Files NOT changed:** `main.py`, `router_graph.py`, `router_topology.py`, `nginx.conf`,
`supervisord.conf`, `Dockerfile`, `deploy.sh`, `azure.yaml`, `vite.config.ts`. None of
the infrastructure or routing layer needs modification.

---

### Phase 1: Agent Integration (OpenAPI + Prompts)

**Scope:** Let Foundry agents query Fabric via the existing `OpenApiTool` pattern.

#### 1a. `CONNECTOR_OPENAPI_VARS` — Add `fabric-gql` connector

In `scripts/agent_provisioner.py`, the `CONNECTOR_OPENAPI_VARS` dict maps connector
types to the placeholder values injected into OpenAPI spec templates. **The
`"fabric"` key already exists** but currently describes KQL — update it to GQL:

> **⚠️ Bug found during audit:** The existing `CONNECTOR_OPENAPI_VARS["fabric"]`
> describes KQL ("Submits a KQL query against the topology data stored in
> Microsoft Fabric"). This is **wrong** — KQL is for telemetry (Eventhouse).
> The graph query language for Fabric Ontology/GraphModel is **GQL** (ISO GQL).
> The code below fixes this.
>
> **⚠️ Key naming:** `_build_tools_from_config()` does `connector.split("-")[0]`
> to look up the key. `"fabric-gql"` → `"fabric"`. So the key must be `"fabric"`,
> not `"fabric-gql"`.

```python
# ⚠️  AUDIT NOTE: The CONNECTOR_OPENAPI_VARS key must be "fabric" (not
# "fabric-gql") because _build_tools_from_config() does:
#   connector.split("-")[0]   →  "fabric-gql" → "fabric"
# A "fabric" entry already exists in agent_provisioner.py but its
# query_language_description incorrectly says KQL — update it to GQL:

CONNECTOR_OPENAPI_VARS = {
    "cosmosdb": {
        "query_language_description": (
            "Gremlin traversal language. Use string-based queries like "
            "g.V().has('label','CoreRouter').valueMap(true)."
        ),
    },
    "fabric": {                                                        # UPDATE existing entry
        "query_language_description": (
            "GQL (ISO Graph Query Language). Uses MATCH/RETURN syntax. "
            "Example: MATCH (r:CoreRouter) RETURN r.RouterId, r.Hostname. "
            "Do NOT use GraphQL syntax — GQL is a different language. "
            "Relationships use arrow syntax: MATCH (a)-[r:connects_to]->(b). "
            "Filter with WHERE: MATCH (r:CoreRouter) WHERE r.Region = 'Sydney' "
            "RETURN r.RouterId."
        ),
        "telemetry_query_language_description": (
            "Submits a KQL query against telemetry data stored in "
            "Microsoft Fabric Eventhouse."
        ),
    },
    "mock": {
        "query_language_description": (
            "Natural language query — describe what you want to find."
        ),
    },
}
```

The existing `graph.yaml` template already has `{query_language_description}` — no spec
template changes needed. The provisioner injects the GQL description when the scenario's
connector is `fabric-gql`.

#### 1b. Composed prompt — `language_gql.md`

Add to the graph_explorer prompt directory (alongside existing `language_gremlin.md`,
`language_mock.md`):

**`data/scenarios/telco-noc-fabric/data/prompts/graph_explorer/language_gql.md`**

> **⚠️ Audit fix:** This file belongs in the **Fabric scenario** directory
> (`telco-noc-fabric/`), not `telco-noc/`. The `telco-noc` scenario uses
> `cosmosdb-gremlin` and has no need for a GQL language file. The reference
> implementation at `fabric_implementation_references/data/prompts/graph_explorer/language_gql.md`
> contains a **much richer version** (106 lines) with all 7 relationship query examples,
> multi-hop patterns, and critical rules like "Never use `LOWER()`". Use the reference
> version instead of the simplified one below.

```markdown
## Query Language: GQL (ISO Graph Query Language)

You query the graph using **GQL** — ISO/IEC 39075, the standard Graph Query Language.
This is NOT GraphQL. GQL uses MATCH/RETURN syntax similar to Cypher.

### Syntax reference

- **Match nodes:** `MATCH (n:CoreRouter) RETURN n.RouterId, n.Hostname`
- **Match edges:** `MATCH (a:CoreRouter)-[r:connects_to]->(b:CoreRouter) RETURN a, r, b`
- **Filter:** `MATCH (n:CoreRouter) WHERE n.Region = 'Sydney' RETURN n`
- **Aggregate:** `MATCH (n:CoreRouter) RETURN COUNT(n)`
- **Multi-hop:** `MATCH (a)-[*1..3]->(b) RETURN a, b`
- **Optional match:** `MATCH (n) OPTIONAL MATCH (n)-[r]->(m) RETURN n, r, m`

### Important rules

1. Property names are **case-sensitive** and match the ontology schema exactly.
2. Node labels correspond to entity types in the ontology (e.g., `CoreRouter`, `TransportLink`).
3. Relationship labels correspond to relationship types (e.g., `connects_to`, `routes_via`).
4. Always use RETURN to specify which properties you want — avoid `RETURN *` for efficiency.
5. If you get a syntax error, read the error message carefully and fix the query.
```

The prompt composition logic in `router_ingest.py` already handles the `graph_explorer/`
directory — it joins `core_instructions.md` + `core_schema.md` + `language_*.md`. For
Fabric scenarios, the correct language file is **already auto-selected** by the existing
connector-aware logic:

- `connector: "cosmosdb-gremlin"` → `"gremlin".split("-")[-1]` → `language_gremlin.md`
- `connector: "fabric-gql"` → `"fabric-gql".split("-")[-1]` → `language_gql.md`  ✓
- `connector: "mock"` → `language_mock.md`

> **⚠️ Audit finding:** The plan previously referenced a
> `_compose_graph_explorer_prompt()` function — **this function does not exist**.
> Prompt composition is handled inline within the `upload_prompts()` endpoint in
> `router_ingest.py` (around line 1000). The existing code already uses
> `_resolve_connector_for_agent()` → `connector.split("-")[-1]` → `language_{suffix}.md`,
> which means **no code change is needed in `router_ingest.py`** for Fabric — just
> adding the `language_gql.md` file to the scenario's `prompts/graph_explorer/` directory
> is sufficient.

**Implementation:** No code change needed. The existing language selection logic in
`upload_prompts()` already handles `"fabric-gql"` correctly:

```python
# Existing code in router_ingest.py (around line 1000):
connector = _resolve_connector_for_agent(agent_def, scenario_config)
language_suffix = connector.split("-")[-1]  # "gremlin", "nosql", "gql"
language_file = f"language_{language_suffix}.md"
# Then skips non-matching language_ files during glob
```

#### 1c. Fabric scenario YAML template

Create a reference `scenario.yaml` for Fabric-based scenarios:

**`data/scenarios/telco-noc-fabric/scenario.yaml`**

```yaml
name: telco-noc-fabric
display_name: "Australian Telco NOC — Fibre Cut (Fabric Backend)"
description: >
  Same investigation scenario as telco-noc, but graph data is served from
  Microsoft Fabric (Lakehouse + Ontology + GQL) instead of CosmosDB Gremlin.
version: "2.0"
domain: telecommunications

use_cases:
  # Same as telco-noc...

example_questions:
  # Same as telco-noc...

paths:
  entities: data/entities
  graph_schema: graph_schema.yaml
  telemetry: data/telemetry
  runbooks: data/knowledge/runbooks
  tickets: data/knowledge/tickets
  prompts: data/prompts
  default_alert: data/prompts/alert_storm.md

data_sources:
  graph:
    connector: "fabric-gql"
    config:
      workspace_id: "${FABRIC_WORKSPACE_ID}"
      graph_model_id: "${FABRIC_GRAPH_MODEL_ID}"
      graph: "telco-noc-fabric-topology"
    schema_file: "graph_schema.yaml"

  telemetry:
    connector: "cosmosdb-nosql"          # Telemetry stays CosmosDB for now
    config:                              # (Phase 3 adds fabric-kql option)
      database: "telemetry"
      container_prefix: "telco-noc-fabric"
      containers:
        - name: AlertStream
          partition_key: /SourceNodeType
          csv_file: AlertStream.csv
          id_field: AlertId
          numeric_fields: [OpticalPowerDbm, BitErrorRate, CPUUtilPct, PacketLossPct]
        - name: LinkTelemetry
          partition_key: /LinkId
          csv_file: LinkTelemetry.csv
          id_field: null
          numeric_fields: [UtilizationPct, OpticalPowerDbm, BitErrorRate, LatencyMs]

  search_indexes:
    runbooks:
      index_name: "telco-noc-fabric-runbooks-index"
      source: "data/knowledge/runbooks"
      blob_container: "runbooks"
    tickets:
      index_name: "telco-noc-fabric-tickets-index"
      source: "data/knowledge/tickets"
      blob_container: "tickets"

agents:
  - name: "GraphExplorerAgent"
    role: "graph_explorer"
    model: "gpt-4.1"
    instructions_file: "prompts/graph_explorer/"
    compose_with_connector: true
    tools:
      - type: "openapi"
        spec_template: "graph"
        keep_path: "/query/graph"

  - name: "TelemetryAgent"
    role: "telemetry"
    model: "gpt-4.1"
    instructions_file: "prompts/foundry_telemetry_agent_v2.md"
    tools:
      - type: "openapi"
        spec_template: "telemetry"
        keep_path: "/query/telemetry"

  - name: "RunbookKBAgent"
    role: "runbook"
    model: "gpt-4.1"
    instructions_file: "prompts/foundry_runbook_kb_agent.md"
    tools:
      - type: "azure_ai_search"
        index_key: "runbooks"

  - name: "HistoricalTicketAgent"
    role: "ticket"
    model: "gpt-4.1"
    instructions_file: "prompts/foundry_historical_ticket_agent.md"
    tools:
      - type: "azure_ai_search"
        index_key: "tickets"

  - name: "Orchestrator"
    role: "orchestrator"
    model: "gpt-4.1"
    instructions_file: "prompts/foundry_orchestrator_agent.md"
    is_orchestrator: true
    connected_agents:
      - "GraphExplorerAgent"
      - "TelemetryAgent"
      - "RunbookKBAgent"
      - "HistoricalTicketAgent"

graph_styles:
  node_types:
    # Same styles as telco-noc — the visualisation doesn't care about backend
    CoreRouter:    { color: "#38BDF8", size: 28, icon: "router" }
    AggSwitch:     { color: "#FB923C", size: 22, icon: "switch" }
    BaseStation:   { color: "#A78BFA", size: 18, icon: "antenna" }
    TransportLink: { color: "#3B82F6", size: 16, icon: "link" }
    MPLSPath:      { color: "#C084FC", size: 14, icon: "path" }
    Service:       { color: "#CA8A04", size: 20, icon: "service" }
    SLAPolicy:     { color: "#FB7185", size: 12, icon: "policy" }
    BGPSession:    { color: "#F472B6", size: 14, icon: "session" }
```

Note: the `agents:` section is **identical** to `telco-noc`. The only differences are:
1. `data_sources.graph.connector: "fabric-gql"` (instead of `"cosmosdb-gremlin"`)
2. `data_sources.graph.config` has `workspace_id` + `graph_model_id` (instead of `database` + `graph`)
3. Scenario `name` and resource prefixes use `telco-noc-fabric`

The agents, tools, prompts, and question patterns are the same. The system handles
the difference automatically through connector-aware dispatching.

**Files changed in Phase 1:**

| File | Change type |
|------|-------------|
| `scripts/agent_provisioner.py` | Small update (`CONNECTOR_OPENAPI_VARS["fabric"]` GQL description + `GRAPH_TOOL_DESCRIPTIONS["fabric"]`) |
| `graph-query-api/router_ingest.py` | **No change needed** (existing `connector.split("-")[-1]` logic handles `"fabric-gql"` → `language_gql.md` automatically) |
| `data/scenarios/telco-noc-fabric/scenario.yaml` | **New** (reference scenario) |
| `data/scenarios/telco-noc-fabric/data/prompts/graph_explorer/language_gql.md` | **New** (prompt — copy from `fabric_implementation_references/` reference) |

---

### Phase 2: Fabric Discovery + Provisioning API

**Scope:** Let users discover Fabric resources and provision Fabric infrastructure from
the UI, reusing the reference scripts from `fabric_implementation_references/scripts/fabric/`.

#### 2a. Fabric discovery router — `graph-query-api/router_fabric_discovery.py`

Provides endpoints for the frontend to list available Fabric resources (ontologies,
eventhouses, graph models) for populating dropdown selectors in the Settings modal.

```python
"""
Router: Fabric resource discovery.

Lists ontologies, graph models, and eventhouses in the configured
Fabric workspace. Used by the frontend Settings modal for resource
selection.

All endpoints are under /query/fabric/* and are proxied through
the existing /query/* nginx location block — no nginx changes needed.
"""

router = APIRouter(prefix="/query/fabric", tags=["fabric-discovery"])

@router.get("/ontologies")
async def list_ontologies() -> list[FabricItem]:
    """List ontologies in the workspace."""
    ...

@router.get("/ontologies/{ontology_id}/models")
async def list_graph_models(ontology_id: str) -> list[FabricItem]:
    """List graph models in an ontology."""
    ...

@router.get("/eventhouses")
async def list_eventhouses() -> list[FabricItem]:
    """List eventhouses in the workspace."""
    ...

@router.get("/health")
async def fabric_health() -> dict:
    """Check Fabric backend readiness."""
    return {"configured": FABRIC_CONFIGURED, "workspace_id": FABRIC_WORKSPACE_ID}
```

> **Note the URL prefix:** `/query/fabric/*` — this routes through the existing
> `/query/*` nginx location block to `graph-query-api` on port 8100. No new
> nginx location needed. The discovery endpoints live in the same service as
> the graph backend because they share credentials and config.

#### 2b. Fabric provisioning endpoints — `api/app/routers/fabric_provision.py`

Long-running Fabric provisioning operations (create workspace, lakehouse, eventhouse,
ontology) stay in the **API service** (`/api/fabric/*`) because they're orchestration
operations analogous to agent provisioning. They wrap the reference scripts with SSE
progress streaming.

```python
"""
Router: Fabric resource provisioning.

Wraps the fabric provisioning reference scripts with SSE progress streaming.
Lives in the API service (port 8000) under /api/fabric/*.
"""

router = APIRouter(prefix="/api/fabric", tags=["fabric-provisioning"])

@router.post("/provision")
async def provision_fabric_resources(req: FabricProvisionRequest) -> EventSourceResponse:
    """One-click Fabric provisioning pipeline:
    1. Create/find workspace (with capacity)
    2. Create Lakehouse + upload CSV data
    3. Create Eventhouse + ingest telemetry
    4. Create Ontology (graph model)
    5. Assign roles
    Streams SSE progress events.
    """
    ...

@router.post("/provision/lakehouse")
async def provision_lakehouse(req: LakehouseRequest) -> EventSourceResponse:
    """Provision just the Lakehouse component."""
    ...

@router.post("/provision/eventhouse")
async def provision_eventhouse(req: EventhouseRequest) -> EventSourceResponse:
    """Provision just the Eventhouse component."""
    ...

@router.post("/provision/ontology")
async def provision_ontology(req: OntologyRequest) -> EventSourceResponse:
    """Provision just the Ontology component."""
    ...
```

#### 2c. Mount the discovery router in `graph-query-api/main.py`

```python
from router_fabric_discovery import router as fabric_discovery_router
app.include_router(fabric_discovery_router)
```

This is the only change to `main.py` — adding one router include. The existing
request logging middleware, CORS, lifespan, and all other routers are unchanged.

**Files changed in Phase 2:**

| File | Change type |
|------|-------------|
| `graph-query-api/router_fabric_discovery.py` | **New** |
| `graph-query-api/main.py` | Small addition (mount router) |
| `api/app/routers/fabric_provision.py` | **New** |
| `api/app/main.py` | Small addition (mount router) |

---

### Phase 3: Frontend — Fabric Setup + Adaptive Upload (Deferred)

**Scope:** Frontend changes needed to configure and provision Fabric from the UI.
This phase is **lower priority** because Fabric scenarios can be fully functional
without these UI additions — users configure Fabric via env vars and upload data
via the provisioning scripts.

#### 3a. Fabric Setup tab in SettingsModal

When the active scenario uses a `fabric-gql` connector (detectable from saved scenario
config), the Settings modal shows a **Fabric Setup** tab alongside the existing
Scenarios and Data Sources tabs. This tab provides:

- Workspace ID display (from env var or scenario config)
- Ontology selector dropdown (populated from `/query/fabric/ontologies`)
- Graph Model selector dropdown (populated from `/query/fabric/ontologies/{id}/models`)
- Eventhouse selector dropdown (populated from `/query/fabric/eventhouses`)
- "Provision Fabric Resources" button → calls `POST /api/fabric/provision` with SSE progress

#### 3b. Adaptive upload in AddScenarioModal

When the user is creating a Fabric scenario, the upload slots adapt:
- **Graph upload** → replaced with "Lakehouse CSV" upload (or hidden, since Fabric graph
  data comes from the provisioning pipeline, not tarball upload)
- **Telemetry upload** → replaced with "Eventhouse CSV" upload (or uses existing telemetry
  upload if CosmosDB NoSQL is still used for telemetry)
- **Runbooks/Tickets/Prompts** → unchanged (these use AI Search and CosmosDB regardless)

#### 3c. Backend indicator in scenario UI

Small UX addition: the ScenarioChip and scenario list show the backend type as a subtle
badge (e.g., "CosmosDB" or "Fabric") so users know which backend each scenario uses
without opening Settings.

**Files changed in Phase 3:**

| File | Change type |
|------|-------------|
| `frontend/src/components/SettingsModal.tsx` | Medium change (add Fabric Setup tab) |
| `frontend/src/components/AddScenarioModal.tsx` | Medium change (adaptive upload slots) |
| `frontend/src/components/ScenarioChip.tsx` | Small change (backend badge) |
| `frontend/src/hooks/useFabricDiscovery.ts` | **New** (Fabric API hooks) |

---

## Scenario YAML: Side-by-Side Comparison

### CosmosDB scenario (existing)

```yaml
data_sources:
  graph:
    connector: "cosmosdb-gremlin"
    config:
      database: "networkgraph"
      graph: "telco-noc-topology"
      partition_key: "/partitionKey"
  telemetry:
    connector: "cosmosdb-nosql"
    config:
      database: "telemetry"
      container_prefix: "telco-noc"
      containers: [...]
```

### Fabric scenario (new)

```yaml
data_sources:
  graph:
    connector: "fabric-gql"
    config:
      workspace_id: "${FABRIC_WORKSPACE_ID}"
      graph_model_id: "${FABRIC_GRAPH_MODEL_ID}"
      graph: "telco-noc-fabric-topology"
  telemetry:
    connector: "cosmosdb-nosql"          # Can use CosmosDB for telemetry
    config:                              # even when graph is Fabric
      database: "telemetry"
      container_prefix: "telco-noc-fabric"
      containers: [...]
```

### Hybrid scenario (future)

```yaml
data_sources:
  graph:
    connector: "fabric-gql"
    config:
      workspace_id: "${FABRIC_WORKSPACE_ID}"
      graph_model_id: "${FABRIC_GRAPH_MODEL_ID}"
      graph: "cloud-outage-fabric-topology"
  telemetry:
    connector: "fabric-kql"              # Both graph AND telemetry on Fabric
    config:
      eventhouse_query_uri: "${EVENTHOUSE_QUERY_URI}"
      kql_database: "NetworkTelemetryDB"
      container_prefix: "cloud-outage-fabric"
      containers: [...]
```

The architecture supports any mix. Backend selection is per-data-source, per-scenario.

---

## Dependency Graph

```
V10 Phases 0–7 (backend registry, DocumentStore) ──┐
                                                     │
V10 Phases 8–9 (config provisioner, OpenAPI tmpl) ──┤
                                                     │
V11 Phase 0 (backends/fabric.py + config)           │
  ├── adapters/fabric_config.py                      │  Independent of V10
  ├── backends/fabric.py                             │  (uses existing Protocol)
  ├── backends/__init__.py (register)                │
  ├── config.py (per-scenario backend resolution)    │
  └── pyproject.toml (httpx)                         │
                                                     │
V11 Phase 1 (agent integration) ◄───────────────────┘
  ├── agent_provisioner.py (CONNECTOR_OPENAPI_VARS)    Requires V10 Ph 8-9
  ├── router_ingest.py (language file selection)
  ├── language_gql.md (prompt)
  └── telco-noc-fabric/scenario.yaml (reference)
                                                     
V11 Phase 2 (discovery + provisioning API)
  ├── router_fabric_discovery.py                       Independent — can run
  └── api/.../fabric_provision.py                      in parallel with Ph 1

V11 Phase 3 (frontend — deferred)
  └── SettingsModal, AddScenarioModal, hooks           Requires Ph 1 + 2
```

**Critical path:** Phase 0 → Phase 1 → test end-to-end with Fabric scenario.
Phases 2 and 3 are nice-to-have and can be deferred indefinitely — Fabric works
fully without them (just configure via env vars + scripts instead of UI).

---

## File Change Inventory

### New Files (6)

| File | Phase | Lines (est.) | Description |
|------|-------|-------------|-------------|
| `graph-query-api/adapters/fabric_config.py` | 0 | ~30 | Fabric env var reads |
| `graph-query-api/backends/fabric.py` | 0 | ~180 | FabricGQLBackend implementation |
| `graph-query-api/router_fabric_discovery.py` | 2 | ~120 | Fabric resource discovery endpoints |
| `api/app/routers/fabric_provision.py` | 2 | ~200 | Fabric provisioning SSE endpoints |
| `data/scenarios/telco-noc-fabric/scenario.yaml` | 1 | ~120 | Reference Fabric scenario |
| `data/scenarios/telco-noc-fabric/data/prompts/graph_explorer/language_gql.md` | 1 | ~110 | GQL prompt fragment (copy from reference impl) |

### Modified Files (5)

| File | Phase | Change size | Description |
|------|-------|------------|-------------|
| `graph-query-api/backends/__init__.py` | 0 | +6 lines | Register `FabricGQLBackend` |
| `graph-query-api/config.py` | 0 | +20 lines | `BACKEND_REQUIRED_VARS` entry + async per-scenario backend resolution |
| `graph-query-api/pyproject.toml` | 0 | +1 line | Add `httpx` dependency |
| `graph-query-api/main.py` | 2 | +2 lines | Mount fabric discovery router |
| `scripts/agent_provisioner.py` | 1 | +10 lines | Update `CONNECTOR_OPENAPI_VARS["fabric"]` GQL description + add `GRAPH_TOOL_DESCRIPTIONS["fabric"]` |

### Untouched Files (everything else)

No changes to: `nginx.conf`, `supervisord.conf`, `Dockerfile`, `deploy.sh`, `azure.yaml`,
`vite.config.ts`, `router_graph.py`, `router_topology.py`, `router_telemetry.py`,
`router_prompts.py`, `router_scenarios.py`, `router_interactions.py`, `router_ingest.py`,
`cosmos_helpers.py`, `sse_helpers.py`, `models.py`, any frontend component (until Phase 3).

**Total: ~11 files touched (6 new + 5 modified), ~590 lines of new code.**

Compare to V11Fabric.md: ~25+ files touched, 2000+ lines, infrastructure changes everywhere.

---

## Edge Cases & Validation

### Fabric env vars missing

If `FABRIC_WORKSPACE_ID` or `FABRIC_GRAPH_MODEL_ID` are not set:
- `FabricGQLBackend.execute_query()` raises `HTTPException(503)` with a clear message
- This is caught by `router_graph.py`'s exception handler and returned as
  `GraphQueryResponse(error="...")` — the agent reads the error and knows Fabric isn't configured
- Non-Fabric scenarios are completely unaffected (they never instantiate `FabricGQLBackend`)

### Mixed backends in same deployment

A deployment has `GRAPH_BACKEND=cosmosdb` (default) and Fabric env vars also set:
- Scenario `telco-noc` uses `connector: "cosmosdb-gremlin"` → CosmosDB backend ✓
- Scenario `telco-noc-fabric` uses `connector: "fabric-gql"` → Fabric backend ✓
- Both work simultaneously via the per-request backend dispatch in `get_backend_for_context()`
- Backend Registry caches `"cosmosdb:telco-noc-topology"` and `"fabric-gql:telco-noc-fabric-topology"` independently

### Fabric API rate limiting (429)

The `FabricGQLBackend` implements retry with exponential backoff (5 retries, 15s × attempt),
matching the pattern from the reference implementation (`test_gql_query.py`).

### Token refresh during long operations

AAD tokens expire after ~60 minutes. The backend re-acquires the token after each 429 retry
wait period, and the lazy `get_credential()` + `credential.get_token()` pattern handles
refresh automatically.

### Graph topology parsing

GQL returns tabular results, not a native node/edge structure. `get_topology()` parses
the results by examining column values for graph element markers (`_type`, `_id`, `_label`,
`_source`, `_target`). This may need adjustment based on actual Fabric GQL response
format — the reference implementation should be used to validate the parsing logic during
Phase 0 testing.

### Ingest not supported

`FabricGQLBackend.ingest()` raises `NotImplementedError`. This is correct — Fabric graph
data is loaded via the Lakehouse + Ontology provisioning pipeline, not through direct
vertex/edge insertion. The upload UI should detect this and show the appropriate
provisioning workflow instead of the tarball upload flow.

---

## Gap Analysis

### Gap 1: Telemetry on Fabric (KQL)

The current plan keeps telemetry on CosmosDB NoSQL even for Fabric scenarios. A future
enhancement would add a `FabricKQLBackend` for the telemetry path, so a scenario could
declare `telemetry.connector: "fabric-kql"` and query Eventhouse data directly. This
would require:

- A `TelemetryBackend` Protocol (analogous to `GraphBackend`)
- `backends/fabric_kql.py` implementation using the Kusto SDK or REST API
- Telemetry router dispatch via connector type (like graph already does)
- `CONNECTOR_OPENAPI_VARS` entry for KQL query language description

This is a natural Phase 3+ extension and doesn't block core Fabric integration.

### Gap 2: Fabric graph data upload via UI

CosmosDB scenarios upload graph data as `.tar.gz` tarballs via `POST /query/upload/graph`.
Fabric scenarios load data via the Lakehouse + Ontology provisioning pipeline (CSV uploads
to OneLake, table creation, ontology binding). The Phase 2 provisioning API provides this
capability, but the upload flow in the AddScenarioModal needs adaptation (Phase 3).

Until Phase 3, Fabric data is loaded via the provisioning scripts or the provisioning API
endpoints directly.

### Gap 3: `get_topology()` response format validation

The `FabricGQLBackend.get_topology()` parsing logic is based on expected GQL result
format. The actual Fabric GQL response shape should be validated against the reference
implementation during Phase 0 development. The reference `test_gql_query.py` in
`fabric_implementation_references/` is the authoritative source.

### Gap 4: Shared concerns (prompts, scenarios, interactions) still require CosmosDB

Prompts, scenarios, and interactions are stored in CosmosDB NoSQL via the `DocumentStore`
Protocol. In a Fabric-only deployment (no CosmosDB), these features won't work. This is
acceptable — Fabric replaces the graph topology backend, not the entire data platform.
A future `FabricDocumentStore` could use Lakehouse tables for document storage, but this
is out of scope.

### Gap 5: Env var substitution in scenario.yaml

The Fabric scenario YAML uses `${FABRIC_WORKSPACE_ID}` syntax for env var references.
The current `_normalize_manifest()` doesn't perform env var substitution. Options:
- The `FabricGQLBackend` reads workspace/model IDs from its own config adapter as
  defaults, and the YAML values are documentation-only
- Add a `_substitute_env_vars(config)` pass to the manifest loader
- The user sets the actual IDs in the YAML (no substitution needed)

**Recommended:** The YAML values are defaults/documentation. The backend always checks
`adapters/fabric_config.py` env vars first, then falls back to YAML config values.
This matches the CosmosDB pattern where `COSMOS_GREMLIN_DATABASE` env var overrides
the YAML config.

---

## Migration & Backwards Compatibility

### Existing scenarios unaffected

All existing `cosmosdb-gremlin` and `mock` scenarios work exactly as before. The Fabric
backend is only instantiated when a scenario's `data_sources.graph.connector` is
`"fabric-gql"`. The `GRAPH_BACKEND` env var default remains `"cosmosdb"`.

### V10 prerequisite

Phase 0 can start as soon as V10 Phase 7 (Backend Registry) is complete. Phase 1
requires V10 Phases 8-9 (config-driven provisioner + OpenAPI templating). These
are sequenced in the V10 implementation plan.

### No breaking changes

No environment variables are removed. No API endpoints change their contract. No
frontend API calls change. Fabric is purely additive.

---

## Implementation Effort Comparison

| Metric | V11Fabric.md (old) | This plan |
|--------|-------------------|-----------|
| New files | ~15 | 6 |
| Modified files | ~15 | 5 |
| New lines of code | ~2000+ | ~590 |
| Infrastructure changes | Dockerfile, supervisord, nginx, deploy.sh, azure.yaml, vite.config | None |
| New service processes | 1 (port 8200) | 0 |
| New URL prefixes | `/fabric/*` | 0 (uses `/query/*`) |
| Frontend routing changes | Major (dual-backend routing) | None (until Phase 3) |
| Risk of breaking existing functionality | Medium (directory rename, port changes) | Very low (additive only) |
| Time to first working Fabric query | ~3 weeks (all 6 phases) | ~3 days (Phase 0 only) |

---

## Audit Findings (2026-02-16)

Cross-referenced this plan against the actual `fabric_implementation_references/` codebase
and the current V10 `autonomous-network-demo/` codebase. All findings below have been
fixed inline in the plan. This section serves as a changelog and reference for reviewers.

### 🔴 Critical — Would cause runtime failures

| # | Finding | Location | Fix applied |
|---|---------|----------|-------------|
| C1 | **Async/sync mismatch in `get_scenario_context()`**: Plan called `fetch_scenario_config()` (which is `async def`) from a **sync** function. Would fail at runtime: `TypeError: coroutine was never awaited`. | Phase 0f | Made `get_scenario_context()` `async def`. FastAPI supports async dependencies natively. |
| C2 | **`CONNECTOR_OPENAPI_VARS` key mismatch**: Plan used key `"fabric-gql"` but `_build_tools_from_config()` does `connector.split("-")[0]` → `"fabric"`. The provisioner would find no matching entry, falling back to empty vars and producing an OpenAPI spec with unsubstituted `{query_language_description}` placeholder. | Phase 1a | Changed key to `"fabric"` (matching existing code). |
| C3 | **Existing `CONNECTOR_OPENAPI_VARS["fabric"]` has wrong language**: Currently says "KQL (Kusto Query Language) query against the topology data". KQL is for Eventhouse telemetry. Fabric graph uses **GQL** (ISO Graph Query Language). Agents would be told to write KQL queries against a GQL endpoint. | Phase 1a | Updated description to GQL. |

### 🟡 Medium — Incorrect assumptions / phantom code references

| # | Finding | Location | Fix applied |
|---|---------|----------|-------------|
| M1 | **`_compose_graph_explorer_prompt()` doesn't exist**: Plan referenced this function 3 times and proposed modifying it. The actual prompt composition is inline within `upload_prompts()` in `router_ingest.py` (~line 1000). | Phase 1b | Removed reference. Documented that existing `connector.split("-")[-1]` logic already handles `"fabric-gql"` → `language_gql.md` with zero code changes. |
| M2 | **`language_gql.md` placed in wrong scenario**: Plan placed it at `telco-noc/data/prompts/graph_explorer/language_gql.md`, but `telco-noc` uses `cosmosdb-gremlin`. | Phase 1b | Moved to `telco-noc-fabric/data/prompts/graph_explorer/language_gql.md`. |
| M3 | **Simplified `language_gql.md` vs reference**: Plan's version is ~30 lines. The reference at `fabric_implementation_references/data/prompts/graph_explorer/language_gql.md` is 106 lines with all 7 relationship examples, multi-hop patterns, and critical rules like "Never use `LOWER()`". | Phase 1b | Added note to copy from reference implementation. |
| M4 | **`router_ingest.py` listed as modified file**: Plan said "+8 lines" change needed. Actually, **no change is needed** — the existing `_resolve_connector_for_agent()` + `connector.split("-")[-1]` logic already handles Fabric connectors. | Phase 1 table | Removed from modified files list. |
| M5 | **`close()` method doesn't interop with V10 shutdown**: V10's `close_all_backends()` calls `backend.close()` and checks `inspect.isawaitable(result)`. The original plan's `close()` used fire-and-forget `create_task()`, meaning the async client might not be closed before process exit. | Phase 0b | Added `aclose()` async method as preferred path. |

### 🟢 Low — Missing items / incomplete coverage

| # | Finding | Location | Fix applied |
|---|---------|----------|-------------|
| L1 | **Missing `GRAPH_TOOL_DESCRIPTIONS["fabric"]`**: `agent_provisioner.py` has `GRAPH_TOOL_DESCRIPTIONS` with only `"cosmosdb"` and `"mock"` keys. Fabric agent provisioning may use this for tool descriptions. | Phase 1a | Added to files changed table. |
| L2 | **`GraphQueryRequest` has no `workspace_id`/`graph_model_id`**: Plan's `execute_query()` accepts these via `**kwargs`, but `router_graph.py` passes only `req.query`. The kwargs will always be empty. This is fine if `fabric_config.py` env vars are used as defaults (which the code does), but the kwargs path is dead code. | Phase 0b | No fix needed — env var defaults are correct. Noted for awareness. |
| L3 | **Env var substitution gap is misleading**: Scenario YAML has `${FABRIC_WORKSPACE_ID}` but no substitution engine exists. Since the backend reads from `adapters/fabric_config.py` directly, the YAML values are never actually used. Consider removing them or documenting them as "documentation-only". | Gap 5 | Already addressed in Gap 5 — no change. |
| L4 | **Phase 2b provisioning estimate is optimistic**: Plan estimates ~200 lines for `fabric_provision.py`. But `provision_ontology.py` alone is 935 lines with complex schema definitions, data bindings, and contextualizations. Wrapping all provisioning scripts in SSE-streaming API endpoints is a multi-day effort, not a few-hour task. | Phase 2b | No inline fix — noted here for planning. |
| L5 | **Reference impl uses `GraphBackendType` enum**: `fabric_implementation_references/graph-query-api/config.py` uses `GraphBackendType(str, Enum)` with `FABRIC = "fabric"` (not `"fabric-gql"`). V10 codebase removed the enum in favour of plain strings. The registry key `"fabric-gql"` in V10's registry is not wrong, but differs from the reference's `"fabric"`. Backend registry key and connector name are different lookup paths (`"fabric-gql"` for registry via `CONNECTOR_TO_BACKEND`, `"fabric"` for `CONNECTOR_OPENAPI_VARS` via `.split("-")[0]`). This dual-key system works but is subtle — future contributors may be confused. | Phase 0 | No fix — inherent in V10's architecture. Noted for awareness. |
| L6 | **No `router_telemetry.py` adapter for Fabric KQL**: Plan correctly defers this to Gap 1 / Phase 3+, but the `telemetry_query_language_description` in `CONNECTOR_OPENAPI_VARS["fabric"]` is already set to KQL. If a `fabric-kql` telemetry connector is added later, the provisioner will need the telemetry description only — the graph description would not apply. | Gap 1 | No fix needed now — deferred. |
| L7 | **Fabric API 429 retry may be insufficient during ontology indexing**: `SETUP_FABRIC.md` documents 20-90 minute ontology indexing periods. The plan's 5-retry / 15s-per-attempt backoff (max ~225s) will exhaust during long indexing. This is acceptable for normal operations but users should be warned about post-provisioning delays. | Edge Cases | No fix — documented in Gap 3 for awareness. |
| L8 | **`get_topology()` default query has no pagination**: `MATCH (n) OPTIONAL MATCH (n)-[r]->(m) RETURN n, r, m` returns ALL nodes and ALL edges. For large graphs this could be extremely slow or hit API response size limits. Consider adding `LIMIT` or requiring callers to specify a query. | Phase 0b | No fix — the CosmosDB backend has the same issue. Noted for awareness. |

### Summary of changes applied to the plan

| Change | Type | Lines affected |
|--------|------|---------------|
| Added audit metadata to header | Header | +1 line |
| Fixed `CONNECTOR_OPENAPI_VARS` key from `"fabric-gql"` to `"fabric"` | C2, C3 | Phase 1a code block |
| Made `get_scenario_context()` async | C1 | Phase 0f code block |
| Removed phantom `_compose_graph_explorer_prompt()` reference | M1 | Phase 1b narrative |
| Moved `language_gql.md` to correct scenario directory | M2 | Phase 1b, Phase 1 table, file inventory |
| Added note about reference impl's richer `language_gql.md` | M3 | Phase 1b |
| Removed `router_ingest.py` from modified files | M4 | Phase 1 table, file inventory |
| Added `aclose()` method to `FabricGQLBackend` | M5 | Phase 0b code block |
| Added `GRAPH_TOOL_DESCRIPTIONS["fabric"]` to Phase 1 scope | L1 | Phase 1 table |
| Added this audit findings section | — | End of document |
