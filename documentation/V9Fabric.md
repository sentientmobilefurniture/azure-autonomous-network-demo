# Fabric Integration — Implementation Plan

> **Created:** 2026-02-15
> **Last audited:** 2026-02-15
> **Status:** ⬜ Not Started
> **Goal:** Add Microsoft Fabric as an alternative graph backend to CosmosDB,
> allowing users to toggle between backends in the UI, browse Fabric
> ontologies/eventhouses, query graph topology via GQL, and bind agents
> to Fabric data sources — all without redeploying the app.

---

## Requirements (Original)

1. Manually provide a Fabric workspace ID
2. Read all available ontologies and provide as a list for graph explorer agent
3. Select the desired ontology
4. Read all available eventhouses and provide as a list for telemetry agent
5. Query graph to retrieve topology and display it using the graph visualizer module
6. Graph Explorer and Graph telemetry agent will be bound with Fabric data connection — So a connection to the fabric workspace must be created
7. In Data sources settings menu... Have a checkbox. Add a first tab basically to choose which backend will be used. To choose whether using a cosmosDB backend or fabric backend. Clicking it will grey out the cosmosDB tabs and ungrey the fabric tab. In total there are four tabs now.
8. Agents will be able to query the fabric ontology freely.

---

## Implementation Status

| Phase | Status | Scope |
|-------|--------|-------|
| **Phase 1:** Backend plumbing — config & enum | ⬜ Not started | `config.py`, `backends/__init__.py`, `azure_config.env.template` |
| **Phase 2:** Fabric graph backend | ⬜ Not started | `backends/fabric.py` (NEW) |
| **Phase 3:** Fabric discovery endpoints | ⬜ Not started | `router_fabric.py` (NEW), `main.py` |
| **Phase 4:** Fabric OpenAPI spec & agent provisioner | ⬜ Not started | `openapi/fabric.yaml` (NEW), `agent_provisioner.py`, `api/app/routers/config.py` |
| **Phase 5:** Frontend — backend toggle & Fabric settings tab | ⬜ Not started | `SettingsModal.tsx`, `ScenarioContext.tsx`, `useFabric.ts` (NEW) |
| **Phase 6:** End-to-end integration testing | ⬜ Not started | Manual verification, mock Fabric mode |

### Deviations From Plan

| # | Plan Said | What Was Done | Rationale |
|---|-----------|---------------|-----------|
| D-1 | — | — | — |

### Extra Work Not In Plan

- {None yet}

---

## Table of Contents

- [Requirements (Original)](#requirements-original)
- [Codebase Conventions & Context](#codebase-conventions--context)
- [Overview of Changes](#overview-of-changes)
- [Key Design Decisions](#key-design-decisions)
- [Item 1: Backend Plumbing](#item-1-backend-plumbing)
- [Item 2: Fabric Graph Backend](#item-2-fabric-graph-backend)
- [Item 3: Fabric Discovery Endpoints](#item-3-fabric-discovery-endpoints)
- [Item 4: Agent Provisioner Changes](#item-4-agent-provisioner-changes)
- [Item 5: Frontend Backend Toggle & Fabric Tab](#item-5-frontend-backend-toggle--fabric-tab)
- [Implementation Phases](#implementation-phases)
- [File Change Inventory](#file-change-inventory)
- [Edge Cases & Validation](#edge-cases--validation)
- [Migration & Backwards Compatibility](#migration--backwards-compatibility)

---

## Codebase Conventions & Context

### Request Routing

| URL prefix | Proxied to | Config |
|------------|-----------|--------|
| `/api/*` | API service on `:8000` | `vite.config.ts` L31-36 (dev), `nginx.conf.template` L17-27 (prod) |
| `/query/*` | graph-query-api on `:8100` | `vite.config.ts` L41-51 (dev), `nginx.conf.template` L17-27 (prod — same `/api/` proxy covers both in prod via unified container) |
| `/health` | API service on `:8000` | `vite.config.ts` L37-40 |

> **⚠️ Production routing:** In the deployed container, nginx proxies **all** `/api/` traffic to the API backend. The graph-query-api is accessed internally by `OpenApiTool` agents using `GRAPH_QUERY_API_URI` env var (e.g., `https://<container-app-hostname>`). Frontend calls to `/query/*` go through the **same** nginx → API backend path. New Fabric endpoints at `/query/fabric/*` must follow this pattern.

### Naming Conventions

| Concept | Example | Derivation |
|---------|---------|-----------|
| Graph name | `"cloud-outage-topology"` | User-chosen scenario name + `-topology` suffix |
| Scenario prefix | `"cloud-outage"` | `graph_name.rsplit("-", 1)[0]` — used to derive telemetry containers, prompts |
| Telemetry container | `"cloud-outage-AlertStream"` | `{prefix}-{ContainerName}` within shared `telemetry` DB |
| Search index | `"cloud-outage-runbooks-index"` | `{prefix}-runbooks-index` |
| Prompts container | `"cloud-outage"` | Same as prefix, inside shared `prompts` DB |

> **Fabric analogy:** Fabric mode replaces graph_name with ontology ID + graph model ID. No name-based derivation — IDs come from Fabric REST API.

### Import & Code Style Conventions

```python
# Backend modules use lazy imports inside factory functions
# to avoid importing unused SDKs:
def get_backend_for_graph(graph_name, backend_type=None):
    bt = backend_type or GRAPH_BACKEND
    if bt == GraphBackendType.COSMOSDB:
        from .cosmosdb import CosmosDBGremlinBackend  # lazy
        ...

# Config uses module-level os.getenv() with defaults:
COSMOS_GREMLIN_ENDPOINT = os.getenv("COSMOS_GREMLIN_ENDPOINT", "")

# Credential is lazy-initialised (not module-level):
_credential = None
def get_credential():
    global _credential
    if _credential is None:
        _credential = DefaultAzureCredential()
    return _credential
```

### Data Format Conventions

| Convention | Format | Where Used |
|-----------|--------|------------|
| Graph query response | `{"columns": [...], "data": [...]}` | `router_graph.py`, OpenAPI specs, agent consumption |
| Topology response | `{"nodes": [...], "edges": [...], "meta": {...}}` | `router_topology.py`, frontend `useTopology.ts` |
| SSE progress events | `event: progress\ndata: {"step": "...", "detail": "..."}\n\n` | `/api/config/apply`, provisioning, upload endpoints |
| Per-request graph routing | `X-Graph` header → `ScenarioContext` via `get_scenario_context()` dependency | All `/query/*` routers |
| Backend cache key | `"{backend_type}:{graph_name}"` | `backends/__init__.py` `_backend_cache` |

---

## Overview of Changes

| # | Item | Category | Impact | Effort |
|---|------|----------|--------|--------|
| 1 | Backend plumbing (config, enum, env vars) | Backend | High — foundation for everything | Small |
| 2 | `FabricGraphBackend` — `execute_query()` + `get_topology()` via Fabric GQL REST | Backend | High — core query path | Large |
| 3 | Fabric discovery endpoints (ontologies, eventhouses) | Backend | Medium — enables UI dropdowns | Medium |
| 4 | Fabric OpenAPI spec + agent provisioner changes | Backend | High — agents can query Fabric | Medium |
| 5 | Frontend backend toggle + Fabric settings tab | Frontend | High — user-facing backend switch | Large |

### Dependency Graph

```
Phase 1 (config/enum) ──┐
                         ├──▶ Phase 2 (FabricGraphBackend)
                         │       │
                         │       ├──▶ Phase 4 (OpenAPI + provisioner)
                         │       │
                         ├──▶ Phase 3 (discovery endpoints)
                         │       │
                         └───────┴──▶ Phase 5 (frontend)
                                          │
                                          └──▶ Phase 6 (E2E testing)
```

Phase 1 is prerequisite for all others. Phases 2 and 3 can be parallelized.
Phase 4 depends on Phase 2 (needs working backend). Phase 5 depends on Phase 3
(needs discovery endpoints) and Phase 1 (needs config types). Phase 6 is final.

### UX Audit Summary

| Area | Finding | Severity |
|------|---------|----------|
| Backend toggle | No existing UI for switching backends — must be added to Data Sources tab | High |
| Fabric settings | No ontology/eventhouse selectors exist — must be built from scratch | High |
| Loading states | Ontology/eventhouse listing can be slow (Fabric REST) — needs loading spinner | Medium |
| Error feedback | Fabric auth failures need clear messaging (credential scope, workspace access) | Medium |
| Greyed-out tabs | Inactive backend's controls must be visually disabled, not hidden (per requirement) | Medium |

---

## Key Design Decisions

### Decision 1: Agent tool strategy — `OpenApiTool` proxy (Option A)

**Chosen:** Keep the `OpenApiTool` → `graph-query-api` proxy pattern for Fabric.

**Rationale:**
- Architectural consistency — same pattern as CosmosDB
- Single query path for both agents and frontend visualization
- `FabricTool` is opaque (can't control query shape) and unproven inside `ConnectedAgentTool` sub-agents
- `graph-query-api` already has the `GraphBackend` Protocol; adding Fabric is natural
- OpenAPI spec can document GQL syntax for agent prompt engineering

**Implication:** Need `backends/fabric.py` implementing full `GraphBackend` Protocol + `openapi/fabric.yaml` with GQL-specific schema.

### Decision 2: Query language — GQL for Fabric backend

The Fabric Graph Model supports GQL natively via its REST API. The `backends/fabric.py` backend will:
- Accept GQL query strings (not Gremlin) in `execute_query()`
- Call `POST https://api.fabric.microsoft.com/v1/workspaces/{id}/graphqlapis/{model_id}/graphql` (or equivalent endpoint)
- Agent prompts for Fabric mode will use GQL syntax instead of Gremlin

### Decision 3: Telemetry backend — Fabric Eventhouse/KQL when in Fabric mode

When `GRAPH_BACKEND=fabric`, telemetry queries will use Eventhouse (KQL) instead of Cosmos NoSQL. This requires:
- A new `FabricTelemetryBackend` or an extension of `router_telemetry.py` to dispatch KQL queries
- Eventhouse connection details (KQL cluster URI, database name) from env vars or Fabric discovery

### Decision 4: Scenario context extension for Fabric

`ScenarioContext` will be extended with optional Fabric fields:

```python
@dataclass
class ScenarioContext:
    # Existing fields (unchanged)
    graph_name: str
    gremlin_database: str
    telemetry_database: str
    telemetry_container_prefix: str
    prompts_database: str
    prompts_container: str
    backend_type: GraphBackendType
    # NEW: Fabric routing fields (None when backend_type != FABRIC)
    fabric_workspace_id: str | None = None
    fabric_ontology_id: str | None = None
    fabric_graph_model_id: str | None = None
    fabric_eventhouse_id: str | None = None
    fabric_kql_uri: str | None = None
```

### Decision 5: Frontend tab structure — 4 tabs with backend selector in Data Sources

Per requirement 7: The Data Sources tab will have a backend toggle (CosmosDB / Fabric radio) at the top. Below the toggle, the active backend's settings render and the inactive backend's settings are visually greyed. Tab bar becomes: **Scenarios | Data Sources | Fabric | Upload**.

Alternatively (simpler): Keep 3 tabs but sub-divide Data Sources with a toggle. The requirement says "four tabs" so we'll add a dedicated **Fabric** tab that greys out when CosmosDB is selected, and the existing **Data Sources** tab greys out when Fabric is selected.

**Final tab structure:**
```
[ Scenarios ] [ Data Sources ] [ Fabric ] [ Upload ]
                  ↑ greyed if        ↑ greyed if
                  Fabric active     CosmosDB active
```

A backend selector appears at the very top of the modal content area (above the tabs or as a global toggle), determining which of the two data tabs is active.

---

## Item 1: Backend Plumbing

### Current State

- `GraphBackendType` enum in `config.py` (line 27-29) has only `COSMOSDB` and `MOCK`
- `GRAPH_BACKEND` global reads `GRAPH_BACKEND` env var, defaults to `"cosmosdb"`
- `ScenarioContext` dataclass (lines 80-95) has no Fabric fields
- `BACKEND_REQUIRED_VARS` (lines 126-133) maps only `COSMOSDB` and `MOCK`
- `backends/__init__.py` factory functions handle only `COSMOSDB` and `MOCK`
- `azure_config.env.template` has no Fabric variables

**Problem:** No Fabric backend type exists in the enum, config, or routing.

### Target State

- `GraphBackendType` gains `FABRIC = "fabric"`
- `config.py` gains Fabric-specific env vars (`FABRIC_API`, `FABRIC_SCOPE`, `FABRIC_WORKSPACE_ID`, `FABRIC_GRAPH_MODEL_ID`, `FABRIC_ONTOLOGY_ID`)
- `ScenarioContext` gains optional Fabric routing fields
- `BACKEND_REQUIRED_VARS` maps `FABRIC` to required vars
- `backends/__init__.py` dispatches to `FabricGraphBackend` for `FABRIC`
- `azure_config.env.template` gains Fabric section

### Backend Changes

#### `graph-query-api/config.py` — Add FABRIC enum + env vars + context fields

```python
# Current:
class GraphBackendType(str, Enum):
    COSMOSDB = "cosmosdb"
    MOCK = "mock"

# New:
class GraphBackendType(str, Enum):
    COSMOSDB = "cosmosdb"
    FABRIC = "fabric"
    MOCK = "mock"
```

```python
# NEW: Fabric env vars (after Cosmos Gremlin section)
# ---------------------------------------------------------------------------
# Fabric settings (used by GRAPH_BACKEND=fabric)
# ---------------------------------------------------------------------------

FABRIC_API = os.getenv("FABRIC_API_URL", "https://api.fabric.microsoft.com/v1")
FABRIC_SCOPE = os.getenv("FABRIC_SCOPE", "https://api.fabric.microsoft.com/.default")
FABRIC_WORKSPACE_ID = os.getenv("FABRIC_WORKSPACE_ID", "")
FABRIC_ONTOLOGY_ID = os.getenv("FABRIC_ONTOLOGY_ID", "")
FABRIC_GRAPH_MODEL_ID = os.getenv("FABRIC_GRAPH_MODEL_ID", "")
FABRIC_EVENTHOUSE_ID = os.getenv("FABRIC_EVENTHOUSE_ID", "")
FABRIC_KQL_URI = os.getenv("FABRIC_KQL_URI", "")
FABRIC_CONNECTION_NAME = os.getenv("FABRIC_CONNECTION_NAME", "")
```

```python
# ScenarioContext extension:
@dataclass
class ScenarioContext:
    graph_name: str
    gremlin_database: str
    telemetry_database: str
    telemetry_container_prefix: str
    prompts_database: str
    prompts_container: str
    backend_type: GraphBackendType
    # Fabric routing (only populated when backend_type == FABRIC)
    fabric_workspace_id: str | None = None
    fabric_ontology_id: str | None = None
    fabric_graph_model_id: str | None = None
    fabric_eventhouse_id: str | None = None
    fabric_kql_uri: str | None = None
```

```python
# get_scenario_context() — add Fabric fields when backend is FABRIC:
def get_scenario_context(
    x_graph: str | None = Header(default=None, alias="X-Graph"),
) -> ScenarioContext:
    graph_name = x_graph or COSMOS_GREMLIN_GRAPH
    prefix = graph_name.rsplit("-", 1)[0] if "-" in graph_name else graph_name

    fabric_fields = {}
    if GRAPH_BACKEND == GraphBackendType.FABRIC:
        fabric_fields = {
            "fabric_workspace_id": FABRIC_WORKSPACE_ID,
            "fabric_ontology_id": FABRIC_ONTOLOGY_ID,
            "fabric_graph_model_id": FABRIC_GRAPH_MODEL_ID,
            "fabric_eventhouse_id": FABRIC_EVENTHOUSE_ID,
            "fabric_kql_uri": FABRIC_KQL_URI,
        }

    return ScenarioContext(
        graph_name=graph_name,
        gremlin_database=COSMOS_GREMLIN_DATABASE,
        telemetry_database="telemetry",
        telemetry_container_prefix=prefix,
        prompts_database="prompts",
        prompts_container=prefix,
        backend_type=GRAPH_BACKEND,
        **fabric_fields,
    )
```

```python
# BACKEND_REQUIRED_VARS — add FABRIC entry:
BACKEND_REQUIRED_VARS: dict[GraphBackendType, tuple[str, ...]] = {
    GraphBackendType.FABRIC: (
        "FABRIC_WORKSPACE_ID",
        "FABRIC_GRAPH_MODEL_ID",
    ),
    GraphBackendType.COSMOSDB: (
        "COSMOS_GREMLIN_ENDPOINT",
        "COSMOS_GREMLIN_PRIMARY_KEY",
    ),
    GraphBackendType.MOCK: (),
}
```

> **⚠️ Implementation note:** The reference codebase uses eager module-level `credential = DefaultAzureCredential()`. The current codebase uses lazy `get_credential()`. Stick with the lazy pattern — Fabric SDK calls will use `get_credential()`.

#### `graph-query-api/backends/__init__.py` — Add FABRIC dispatch

```python
# In get_backend():
elif bt == GraphBackendType.FABRIC:
    from .fabric import FabricGraphBackend
    return FabricGraphBackend()

# In get_backend_for_context():
if ctx.backend_type == GraphBackendType.FABRIC:
    cache_key = f"fabric:{ctx.fabric_workspace_id}:{ctx.fabric_graph_model_id}"
    # ...same cache pattern...

# In get_backend_for_graph():
elif bt == GraphBackendType.FABRIC:
    from .fabric import FabricGraphBackend
    _backend_cache[cache_key] = FabricGraphBackend(
        workspace_id=..., graph_model_id=...
    )
```

> **⚠️ Implementation note:** Fabric backend cache key should include workspace_id + graph_model_id (not graph_name, which is meaningless for Fabric). The `get_backend_for_context()` method needs special handling — it can pull IDs from `ScenarioContext.fabric_*` fields.

#### `azure_config.env.template` — Add Fabric section

```bash
# --- Fabric Integration (optional — only when GRAPH_BACKEND=fabric) ---
# Fabric workspace ID (from portal or Fabric API)
FABRIC_WORKSPACE_ID=
# Fabric ontology ID (discovered via /query/fabric/ontologies)
FABRIC_ONTOLOGY_ID=
# Fabric graph model ID (auto-created with ontology)
FABRIC_GRAPH_MODEL_ID=
# Fabric eventhouse ID (discovered via /query/fabric/eventhouses)
FABRIC_EVENTHOUSE_ID=
# KQL cluster URI for eventhouse queries
FABRIC_KQL_URI=
# AI Foundry connection name for Fabric (used by FabricTool in agents)
FABRIC_CONNECTION_NAME=
```

---

## Item 2: Fabric Graph Backend

### Current State

- `backends/cosmosdb.py` implements `GraphBackend` Protocol using Gremlin SDK
- `backends/mock.py` implements the Protocol with static data
- No `backends/fabric.py` exists
- Reference codebase has a `FabricGraphBackend` import in `__init__.py` but **no actual `fabric.py` file**

**Problem:** No Fabric query execution exists. Must implement `execute_query()` (GQL) and `get_topology()` (GQL → nodes/edges).

### Target State

`backends/fabric.py` — full `GraphBackend` implementation using Fabric REST API for GQL queries.

### Backend Changes

#### `graph-query-api/backends/fabric.py` — **NEW** (~200 lines)

```python
"""
Fabric Graph Backend — executes GQL queries against Microsoft Fabric GraphQL API.

Uses the Fabric REST API:
  POST /v1/workspaces/{workspace_id}/graphqlapis/{graph_model_id}/graphql

Auth: DefaultAzureCredential with scope "https://api.fabric.microsoft.com/.default"
"""

from __future__ import annotations

import logging
import httpx

from config import (
    FABRIC_API, FABRIC_SCOPE, FABRIC_WORKSPACE_ID, FABRIC_GRAPH_MODEL_ID,
    get_credential,
)

logger = logging.getLogger("graph-query-api.fabric")


class FabricGraphBackend:
    """GraphBackend implementation for Microsoft Fabric GQL."""

    def __init__(
        self,
        workspace_id: str | None = None,
        graph_model_id: str | None = None,
    ):
        self.workspace_id = workspace_id or FABRIC_WORKSPACE_ID
        self.graph_model_id = graph_model_id or FABRIC_GRAPH_MODEL_ID
        self._client: httpx.AsyncClient | None = None

    def _get_token(self) -> str:
        """Get a bearer token for Fabric API."""
        cred = get_credential()
        token = cred.get_token(FABRIC_SCOPE)
        return token.token

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=60.0)
        return self._client

    async def execute_query(self, query: str, **kwargs) -> dict:
        """Execute a GQL query against the Fabric GraphQL API.

        Args:
            query: A GQL query string.

        Returns:
            {"columns": [...], "data": [...]} matching the GraphBackend Protocol.
        """
        client = await self._get_client()
        url = f"{FABRIC_API}/workspaces/{self.workspace_id}/graphqlapis/{self.graph_model_id}/graphql"
        token = self._get_token()

        resp = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={"query": query},
        )
        resp.raise_for_status()
        result = resp.json()

        # Transform GraphQL response → {columns, data} protocol format
        if "errors" in result:
            return {"columns": [], "data": [], "error": str(result["errors"])}

        data_key = next(iter(result.get("data", {})), None)
        rows = result.get("data", {}).get(data_key, []) if data_key else []
        if not isinstance(rows, list):
            rows = [rows]

        columns = []
        if rows:
            columns = [{"name": k, "type": type(v).__name__} for k, v in rows[0].items()]

        return {"columns": columns, "data": rows}

    async def get_topology(
        self,
        query: str | None = None,
        vertex_labels: list[str] | None = None,
    ) -> dict:
        """Query Fabric ontology for topology visualization.

        If no query is provided, fetches all entities and relationships.
        Returns {"nodes": [...], "edges": [...]}.
        """
        # If custom GQL query provided, execute it and convert
        if query:
            result = await self.execute_query(query)
            # Caller is responsible for shaping result
            return {"nodes": result.get("data", []), "edges": []}

        # Default: introspect ontology for all entity types and relationships
        # This query shape depends on the actual ontology schema —
        # implementer must adapt to the specific ontology definition.
        # Placeholder GQL for topology:
        gql = """
        {
          __schema {
            queryType { fields { name } }
          }
        }
        """
        # Step 1: Discover entity types via introspection
        # Step 2: Query each entity type for nodes
        # Step 3: Query relationship types for edges
        # Implementation depends on ontology structure — see ⚠️ note below
        ...

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._client.aclose())
            except RuntimeError:
                asyncio.run(self._client.aclose())
            self._client = None
```

> **⚠️ Implementation note:** The `get_topology()` method's default query depends entirely on the Fabric ontology schema. The ontology defines entity types (e.g., Router, Switch, Link) and relationship types. The implementer must:
> 1. Use GQL introspection (`__schema`) to discover available types
> 2. Build per-type queries like `{ routers { id label properties... } }`
> 3. Build relationship queries to extract edges
> 4. Map results to `{nodes: [{id, label, properties}], edges: [{id, source, target, label, properties}]}`
>
> This is the single hardest piece of the implementation. Start with a simple hard-coded query for a known ontology, then generalize.

> **⚠️ Implementation note:** `httpx` is used for async HTTP (already in `pyproject.toml` via other dependencies). If not present, add `httpx>=0.27.0` to `graph-query-api/pyproject.toml`.

---

## Item 3: Fabric Discovery Endpoints

### Current State

- No endpoints exist for browsing Fabric workspace contents
- Requirements 2 and 4 demand listing ontologies and eventhouses for dropdown selectors
- The reference has provisioning scripts in `scripts/fabric/` that call `GET /v1/workspaces/{id}/items` but no API endpoints

**Problem:** Frontend needs to discover available Fabric ontologies and eventhouses to populate selectors.

### Target State

New router `router_fabric.py` with:
- `GET /query/fabric/ontologies?workspace_id=...` — list ontologies
- `GET /query/fabric/eventhouses?workspace_id=...` — list eventhouses
- `GET /query/fabric/graph-models?workspace_id=...&ontology_id=...` — list graph models for an ontology

### Backend Changes

#### `graph-query-api/router_fabric.py` — **NEW** (~120 lines)

```python
"""
Router: /query/fabric/* — Fabric workspace discovery endpoints.

Provides listing of ontologies, eventhouses, and graph models
from a Fabric workspace, for frontend dropdown population.
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from config import FABRIC_API, FABRIC_SCOPE, FABRIC_WORKSPACE_ID, get_credential

logger = logging.getLogger("graph-query-api.fabric")

router = APIRouter(prefix="/query/fabric", tags=["fabric"])


class FabricItem(BaseModel):
    id: str
    display_name: str
    type: str
    description: str | None = None


class FabricListResponse(BaseModel):
    items: list[FabricItem]
    workspace_id: str


async def _fabric_list_items(workspace_id: str, item_type: str) -> list[dict]:
    """Call Fabric REST API to list items of a given type in a workspace."""
    import httpx

    cred = get_credential()
    token = cred.get_token(FABRIC_SCOPE)

    async with httpx.AsyncClient(timeout=30.0) as client:
        url = f"{FABRIC_API}/workspaces/{workspace_id}/items"
        resp = await client.get(
            url,
            params={"type": item_type},
            headers={"Authorization": f"Bearer {token.token}"},
        )
        if resp.status_code == 404:
            raise HTTPException(404, f"Workspace {workspace_id} not found")
        if resp.status_code == 403:
            raise HTTPException(403, "Access denied — check Fabric workspace permissions")
        resp.raise_for_status()
        return resp.json().get("value", [])


@router.get("/ontologies", response_model=FabricListResponse)
async def list_ontologies(
    workspace_id: str = Query(default=None),
):
    """List all ontologies in a Fabric workspace."""
    ws_id = workspace_id or FABRIC_WORKSPACE_ID
    if not ws_id:
        raise HTTPException(400, "workspace_id required (param or FABRIC_WORKSPACE_ID env var)")

    items = await _fabric_list_items(ws_id, "GraphQLApi")  # or "Ontology"
    return FabricListResponse(
        workspace_id=ws_id,
        items=[
            FabricItem(
                id=item["id"],
                display_name=item.get("displayName", item["id"]),
                type="ontology",
                description=item.get("description"),
            )
            for item in items
        ],
    )


@router.get("/eventhouses", response_model=FabricListResponse)
async def list_eventhouses(
    workspace_id: str = Query(default=None),
):
    """List all eventhouses in a Fabric workspace."""
    ws_id = workspace_id or FABRIC_WORKSPACE_ID
    if not ws_id:
        raise HTTPException(400, "workspace_id required (param or FABRIC_WORKSPACE_ID env var)")

    items = await _fabric_list_items(ws_id, "Eventhouse")
    return FabricListResponse(
        workspace_id=ws_id,
        items=[
            FabricItem(
                id=item["id"],
                display_name=item.get("displayName", item["id"]),
                type="eventhouse",
                description=item.get("description"),
            )
            for item in items
        ],
    )


@router.get("/graph-models", response_model=FabricListResponse)
async def list_graph_models(
    workspace_id: str = Query(default=None),
    ontology_id: str = Query(default=None),
):
    """List graph models. Currently returns graph model IDs associated with ontologies."""
    ws_id = workspace_id or FABRIC_WORKSPACE_ID
    if not ws_id:
        raise HTTPException(400, "workspace_id required")

    # Graph models are associated with ontologies via the ontology definition
    # For now, list all GraphQLApi items (each has a graph model)
    items = await _fabric_list_items(ws_id, "GraphQLApi")
    return FabricListResponse(
        workspace_id=ws_id,
        items=[
            FabricItem(
                id=item["id"],
                display_name=item.get("displayName", item["id"]),
                type="graph-model",
            )
            for item in items
            if not ontology_id or item["id"] == ontology_id
        ],
    )
```

> **⚠️ Implementation note:** The Fabric REST API item type strings may differ from what's documented. Verify the exact `type` parameter for ontologies — it could be `"GraphQLApi"`, `"Ontology"`, or `"GraphModel"`. The reference scripts use `GET /v1/workspaces/{id}/items` without a type filter and then filter client-side. If the type parameter is unreliable, filter client-side:
> ```python
> all_items = await _fabric_list_items(ws_id, None)
> ontologies = [i for i in all_items if i.get("type") == "Ontology"]
> ```

#### `graph-query-api/main.py` — Register new router

```python
# Add import:
from router_fabric import router as fabric_router

# Add to app includes (after other routers):
app.include_router(fabric_router)
```

---

## Item 4: Agent Provisioner Changes

### Current State

- `scripts/agent_provisioner.py` uses `OPENAPI_SPEC_MAP` (line 38) mapping `"cosmosdb"` and `"mock"` to YAML files
- `_load_openapi_spec()` substitutes `{base_url}` and `{graph_name}` in the YAML
- `provision_all()` creates `GraphExplorerAgent` with `OpenApiTool` pointing to `/query/graph` spec
- `TelemetryAgent` uses `OpenApiTool` pointing to `/query/telemetry` spec
- No `"fabric"` entry in any map

**Problem:** When `GRAPH_BACKEND=fabric`, agents need a Fabric-specific OpenAPI spec that documents GQL query syntax instead of Gremlin.

### Target State

- New `openapi/fabric.yaml` with GQL query schema and Fabric-specific descriptions
- `OPENAPI_SPEC_MAP` gains `"fabric"` entry
- `GRAPH_TOOL_DESCRIPTIONS` gains `"fabric"` entry
- Telemetry spec for Fabric uses KQL syntax instead of Cosmos SQL

### Backend Changes

#### `graph-query-api/openapi/fabric.yaml` — **NEW** (~160 lines)

```yaml
openapi: "3.0.3"
info:
  title: Graph Query API (Fabric Backend)
  version: "0.5.0"
  description: |
    Micro-API for executing GQL queries against Microsoft Fabric Ontology.
    Used by Foundry agents via OpenApiTool.
    Backend: Microsoft Fabric GraphQL API
servers:
  - url: "{base_url}"
    description: Deployed Container App

paths:
  /query/graph:
    post:
      operationId: query_graph
      summary: Execute a GQL query against the Fabric Ontology graph
      description: |
        Submits a GQL (Graph Query Language) query to Microsoft Fabric.
        Returns columns and data rows from the network ontology.
        Use GQL syntax (not Gremlin). Example:
          { routers { routerId name location status } }
          { transportLinks(filter: {status: "DOWN"}) { linkId endpoints bandwidth } }
      parameters:
        - name: X-Graph
          in: header
          required: true
          schema:
            type: string
            enum: ["{graph_name}"]
          description: |
            The graph context for routing. Always use the value shown.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - query
              properties:
                query:
                  type: string
                  description: |
                    A GQL query string for the Fabric ontology.
                    Uses GraphQL-like syntax. Query entity types and their
                    properties. Use filters for targeted results.
      responses:
        "200":
          description: Query results
          content:
            application/json:
              schema:
                type: object
                properties:
                  columns:
                    type: array
                    items:
                      type: object
                      properties:
                        name: { type: string }
                        type: { type: string }
                  data:
                    type: array
                    items:
                      type: object
                  error:
                    type: string
                    nullable: true

  /query/telemetry:
    post:
      operationId: query_telemetry
      summary: Execute a KQL query against Fabric Eventhouse telemetry
      description: |
        Submits a KQL (Kusto Query Language) query to a Fabric Eventhouse.
        Returns telemetry data from KQL tables.
        Use KQL syntax (not Cosmos SQL). Example:
          AlertStream | where Severity == "CRITICAL" | top 10 by Timestamp desc
          LinkTelemetry | where LinkId == "LINK-001" | summarize avg(Utilization) by bin(Timestamp, 1h)
      parameters:
        - name: X-Graph
          in: header
          required: true
          schema:
            type: string
            enum: ["{graph_name}"]
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - query
              properties:
                query:
                  type: string
                  description: |
                    A KQL query string for the Fabric Eventhouse.
                container_name:
                  type: string
                  description: |
                    The KQL table to query (e.g., "AlertStream", "LinkTelemetry").
      responses:
        "200":
          description: Query results
          content:
            application/json:
              schema:
                type: object
                properties:
                  columns: { type: array, items: { type: object } }
                  rows: { type: array, items: { type: object } }
                  error: { type: string, nullable: true }
```

#### `scripts/agent_provisioner.py` — Add Fabric entries

```python
# Add to OPENAPI_SPEC_MAP:
OPENAPI_SPEC_MAP = {
    "cosmosdb": OPENAPI_DIR / "cosmosdb.yaml",
    "fabric": OPENAPI_DIR / "fabric.yaml",
    "mock": OPENAPI_DIR / "mock.yaml",
}

# Add to GRAPH_TOOL_DESCRIPTIONS:
GRAPH_TOOL_DESCRIPTIONS = {
    "cosmosdb": "Execute a Gremlin query against Azure Cosmos DB...",
    "fabric": "Execute a GQL query against Microsoft Fabric Ontology to explore topology and relationships.",
    "mock": "Query the topology graph (offline mock mode).",
}
```

#### `api/app/routers/config.py` — Support Fabric in config apply

```python
# In ConfigApplyRequest, add optional Fabric fields:
class ConfigApplyRequest(BaseModel):
    graph: str = "topology"
    runbooks_index: str = "runbooks-index"
    tickets_index: str = "tickets-index"
    prompt_scenario: str | None = None
    prompts: dict[str, str] | None = None
    # NEW: Fabric-specific overrides
    backend_type: str | None = None  # "cosmosdb" | "fabric" | None (use env default)
    fabric_workspace_id: str | None = None
    fabric_ontology_id: str | None = None
    fabric_graph_model_id: str | None = None
```

> **⚠️ Implementation note:** The `graph_backend` variable in the provisioning flow (line 201) reads from `os.getenv("GRAPH_BACKEND")`. When the frontend sends `backend_type: "fabric"`, we need to pass that through to `provision_all()` instead of the env var. This allows runtime backend switching without restarting the container.

---

## Item 5: Frontend Backend Toggle & Fabric Tab

### Current State

- `SettingsModal.tsx` (745 lines) has 3 tabs: `scenarios`, `datasources`, `upload`
- Tab type is `type Tab = 'scenarios' | 'datasources' | 'upload'`
- Data Sources tab shows Cosmos-specific dropdowns (graph, runbooks index, tickets index, prompt set)
- `ScenarioContext.tsx` manages `activeGraph`, `activeRunbooksIndex`, `activeTicketsIndex`, `activePromptSet`
- No concept of backend type in frontend state

**Problem:** No way to toggle between CosmosDB and Fabric, no Fabric settings UI, no ontology/eventhouse discovery.

### Target State

```
┌──────────────────────────────────────────────────────────────┐
│ Settings                                                  ✕  │
│                                                              │
│ Backend: ○ CosmosDB  ● Fabric                                │
│                                                              │
│ [ Scenarios ] [ Data Sources ] [ Fabric ] [ Upload ]         │
│                 (greyed out)      (active)                    │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│ ┌─ Fabric Settings ────────────────────────────────────────┐ │
│ │                                                          │ │
│ │ Workspace ID                                             │ │
│ │ ┌──────────────────────────────────────────────────────┐ │ │
│ │ │ abc12345-...                                         │ │ │
│ │ └──────────────────────────────────────────────────────┘ │ │
│ │                                                          │ │
│ │ Ontology                              [🔄 Refresh]      │ │
│ │ ┌──────────────────────────────────────────────────────┐ │ │
│ │ │ ▼ telco-network-ontology                             │ │ │
│ │ └──────────────────────────────────────────────────────┘ │ │
│ │                                                          │ │
│ │ Eventhouse                            [🔄 Refresh]      │ │
│ │ ┌──────────────────────────────────────────────────────┐ │ │
│ │ │ ▼ telco-eventhouse                                   │ │ │
│ │ └──────────────────────────────────────────────────────┘ │ │
│ │                                                          │ │
│ │ [ Load Topology ]  [ Provision Agents ]                  │ │
│ │                                                          │ │
│ └──────────────────────────────────────────────────────────┘ │
│                                                              │
│                                                   [ Close ]  │
└──────────────────────────────────────────────────────────────┘
```

### Frontend Changes

#### `context/ScenarioContext.tsx` — Add backend type + Fabric state

```tsx
// Add to ScenarioState interface:
interface ScenarioState {
  // ... existing fields ...

  /** Active backend type */
  activeBackendType: 'cosmosdb' | 'fabric';
  /** Fabric workspace ID */
  fabricWorkspaceId: string;
  /** Fabric ontology ID */
  fabricOntologyId: string;
  /** Fabric graph model ID */
  fabricGraphModelId: string;
  /** Fabric eventhouse ID */
  fabricEventhouseId: string;
  /** Setters */
  setActiveBackendType: (type: 'cosmosdb' | 'fabric') => void;
  setFabricWorkspaceId: (id: string) => void;
  setFabricOntologyId: (id: string) => void;
  setFabricGraphModelId: (id: string) => void;
  setFabricEventhouseId: (id: string) => void;
}
```

```tsx
// In ScenarioProvider, add state:
const [activeBackendType, setActiveBackendType] = useState<'cosmosdb' | 'fabric'>(
  () => (localStorage.getItem('activeBackendType') as 'cosmosdb' | 'fabric') || 'cosmosdb',
);
const [fabricWorkspaceId, setFabricWorkspaceId] = useState(
  () => localStorage.getItem('fabricWorkspaceId') || '',
);
const [fabricOntologyId, setFabricOntologyId] = useState(
  () => localStorage.getItem('fabricOntologyId') || '',
);
const [fabricGraphModelId, setFabricGraphModelId] = useState(
  () => localStorage.getItem('fabricGraphModelId') || '',
);
const [fabricEventhouseId, setFabricEventhouseId] = useState(
  () => localStorage.getItem('fabricEventhouseId') || '',
);

// Persist to localStorage on change
useEffect(() => {
  localStorage.setItem('activeBackendType', activeBackendType);
}, [activeBackendType]);
// ... repeat for each fabric field ...
```

#### `hooks/useFabric.ts` — **NEW** (~80 lines)

```tsx
/**
 * Hook for Fabric workspace discovery — fetching ontologies and eventhouses.
 */
import { useState, useCallback } from 'react';

interface FabricItem {
  id: string;
  display_name: string;
  type: string;
  description?: string;
}

export function useFabric() {
  const [ontologies, setOntologies] = useState<FabricItem[]>([]);
  const [eventhouses, setEventhouses] = useState<FabricItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchOntologies = useCallback(async (workspaceId: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/query/fabric/ontologies?workspace_id=${encodeURIComponent(workspaceId)}`);
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const data = await res.json();
      setOntologies(data.items);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchEventhouses = useCallback(async (workspaceId: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/query/fabric/eventhouses?workspace_id=${encodeURIComponent(workspaceId)}`);
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const data = await res.json();
      setEventhouses(data.items);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  return { ontologies, eventhouses, loading, error, fetchOntologies, fetchEventhouses };
}
```

#### `SettingsModal.tsx` — Add backend toggle, Fabric tab, 4-tab layout

```tsx
// Change Tab type:
type Tab = 'scenarios' | 'datasources' | 'fabric' | 'upload';

// Add backend toggle above tab bar (inside header):
<div className="flex items-center gap-4 px-6 mt-2">
  <span className="text-xs text-text-muted">Backend:</span>
  {(['cosmosdb', 'fabric'] as const).map((bt) => (
    <label key={bt} className="flex items-center gap-1.5 cursor-pointer">
      <input
        type="radio"
        name="backend"
        value={bt}
        checked={activeBackendType === bt}
        onChange={() => setActiveBackendType(bt)}
        className="accent-brand"
      />
      <span className={`text-sm ${activeBackendType === bt ? 'text-text-primary' : 'text-text-muted'}`}>
        {bt === 'cosmosdb' ? 'CosmosDB' : 'Fabric'}
      </span>
    </label>
  ))}
</div>

// Tab bar — grey out inactive backend's tab:
{(['scenarios', 'datasources', 'fabric', 'upload'] as Tab[]).map((t) => {
  const disabled =
    (t === 'datasources' && activeBackendType === 'fabric') ||
    (t === 'fabric' && activeBackendType === 'cosmosdb');
  return (
    <button
      key={t}
      onClick={() => !disabled && setTab(t)}
      disabled={disabled}
      className={`px-4 py-2 text-sm rounded-t-md transition-colors ${
        tab === t
          ? 'bg-neutral-bg1 text-text-primary border-t border-x border-white/10'
          : disabled
          ? 'text-text-muted/40 cursor-not-allowed'
          : 'text-text-muted hover:text-text-secondary'
      }`}
    >
      {t === 'scenarios' ? 'Scenarios' :
       t === 'datasources' ? 'Data Sources' :
       t === 'fabric' ? 'Fabric' : 'Upload'}
    </button>
  );
})}

// Fabric tab content:
{tab === 'fabric' && (
  <>
    {/* Workspace ID input */}
    <div className="bg-neutral-bg1 rounded-lg border border-white/5 p-4 space-y-3">
      <label className="text-xs text-text-muted block mb-1">Fabric Workspace ID</label>
      <input
        type="text"
        value={fabricWorkspaceId}
        onChange={(e) => setFabricWorkspaceId(e.target.value)}
        placeholder="Enter Fabric workspace ID..."
        className="w-full bg-neutral-bg2 border border-white/10 rounded px-3 py-1.5 text-sm text-text-primary"
      />
    </div>

    {/* Ontology selector */}
    <div className="bg-neutral-bg1 rounded-lg border border-white/5 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-blue-400" />
          <span className="text-sm font-medium text-text-primary">Ontology</span>
        </div>
        <button
          onClick={() => fabricWorkspaceId && fetchOntologies(fabricWorkspaceId)}
          disabled={!fabricWorkspaceId || fabricLoading}
          className="text-xs text-brand hover:text-brand/80 disabled:text-text-muted/40"
        >
          🔄 Refresh
        </button>
      </div>
      <select
        value={fabricOntologyId}
        onChange={(e) => setFabricOntologyId(e.target.value)}
        className="w-full bg-neutral-bg2 border border-white/10 rounded px-3 py-1.5 text-sm text-text-primary"
      >
        <option value="">Select ontology...</option>
        {ontologies.map((o) => (
          <option key={o.id} value={o.id}>{o.display_name}</option>
        ))}
      </select>
    </div>

    {/* Eventhouse selector */}
    <div className="bg-neutral-bg1 rounded-lg border border-white/5 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-purple-400" />
          <span className="text-sm font-medium text-text-primary">Eventhouse</span>
        </div>
        <button
          onClick={() => fabricWorkspaceId && fetchEventhouses(fabricWorkspaceId)}
          disabled={!fabricWorkspaceId || fabricLoading}
          className="text-xs text-brand hover:text-brand/80 disabled:text-text-muted/40"
        >
          🔄 Refresh
        </button>
      </div>
      <select
        value={fabricEventhouseId}
        onChange={(e) => setFabricEventhouseId(e.target.value)}
        className="w-full bg-neutral-bg2 border border-white/10 rounded px-3 py-1.5 text-sm text-text-primary"
      >
        <option value="">Select eventhouse...</option>
        {eventhouses.map((e) => (
          <option key={e.id} value={e.id}>{e.display_name}</option>
        ))}
      </select>
    </div>

    {/* Action buttons */}
    <div className="flex gap-3">
      <ActionButton
        label="Load Topology"
        icon="🔗"
        description="Fetch graph from Fabric ontology"
        onClick={async () => {
          // POST to /query/topology with Fabric context
          const res = await fetch('/query/topology', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-Graph': fabricOntologyId || 'fabric',
            },
            body: JSON.stringify({}),
          });
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          const data = await res.json();
          return `${data.meta?.node_count ?? '?'} nodes, ${data.meta?.edge_count ?? '?'} edges`;
        }}
      />
      <ActionButton
        label="Provision Agents"
        icon="🤖"
        description="Bind agents to Fabric data sources"
        onClick={async () => {
          const res = await fetch('/api/config/apply', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              graph: fabricOntologyId || 'fabric',
              runbooks_index: activeRunbooksIndex,
              tickets_index: activeTicketsIndex,
              backend_type: 'fabric',
              fabric_workspace_id: fabricWorkspaceId,
              fabric_ontology_id: fabricOntologyId,
              fabric_graph_model_id: fabricGraphModelId,
            }),
          });
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          let lastMsg = '';
          await consumeSSE(res, {
            onProgress: (d) => { lastMsg = d.detail; },
            onError: (d) => { throw new Error(d.error); },
          });
          return lastMsg || 'Agents provisioned (Fabric)';
        }}
      />
    </div>

    {fabricError && <p className="text-xs text-status-error">{fabricError}</p>}
  </>
)}
```

> **⚠️ Implementation note:** When the user toggles from CosmosDB to Fabric:
> 1. Auto-switch to the Fabric tab (force `setTab('fabric')`)
> 2. Persist `activeBackendType` to localStorage
> 3. Existing scenario-derived bindings remain but are ignored when Fabric is active
> 4. The Scenarios tab still works for both backends (scenarios are metadata, not backend-specific)

### UX Enhancements

#### 5a. Auto-fetch on workspace ID entry

**Problem:** User must manually click "Refresh" after entering workspace ID.

**Fix:** Debounce `fetchOntologies()` and `fetchEventhouses()` to fire 500ms after workspace ID changes (if it looks like a valid UUID).

```tsx
useEffect(() => {
  if (fabricWorkspaceId.length === 36 && tab === 'fabric') {
    const timer = setTimeout(() => {
      fetchOntologies(fabricWorkspaceId);
      fetchEventhouses(fabricWorkspaceId);
    }, 500);
    return () => clearTimeout(timer);
  }
}, [fabricWorkspaceId, tab]);
```

**Why:** Reduces clicks, matches user expectation that entering an ID "does something."

#### 5b. Loading spinner during Fabric discovery

**Problem:** Fabric REST calls may take 2-5s. No feedback during this time.

**Fix:** Show a spinner next to the dropdown while `fabricLoading` is true.

```tsx
{fabricLoading && (
  <span className="text-xs text-text-muted animate-pulse">Loading...</span>
)}
```

**Why:** Prevents users from thinking the UI is frozen.

#### 5c. Backend toggle auto-tab-switch

**Problem:** User toggles to Fabric but is still looking at the (now greyed) Data Sources tab.

**Fix:** When toggling backend, auto-switch to the corresponding tab.

```tsx
const handleBackendChange = (bt: 'cosmosdb' | 'fabric') => {
  setActiveBackendType(bt);
  setTab(bt === 'fabric' ? 'fabric' : 'datasources');
};
```

**Why:** Reduces confusion. The greyed tab won't respond to clicks.

---

## Implementation Phases

### Phase 1: Backend Plumbing — Config & Enum

> Independent — prerequisite for all other phases.

**Files to modify:**
- `graph-query-api/config.py` — Add `FABRIC` to enum, Fabric env vars, `ScenarioContext` fields, `get_scenario_context()` changes, `BACKEND_REQUIRED_VARS`
- `graph-query-api/backends/__init__.py` — Add `FABRIC` branches to `get_backend()`, `get_backend_for_context()`, `get_backend_for_graph()`
- `graph-query-api/main.py` — Add lifespan check for Fabric vars
- `azure_config.env.template` — Add Fabric section

**Verification:**
- `GRAPH_BACKEND=fabric uv run python -c "from config import GRAPH_BACKEND; print(GRAPH_BACKEND)"` → prints `GraphBackendType.FABRIC`
- **App starts without crash** when `GRAPH_BACKEND=fabric` and required vars are missing (warns but doesn't exit)
- Existing `GRAPH_BACKEND=cosmosdb` and `GRAPH_BACKEND=mock` still work

### Phase 2: Fabric Graph Backend

> Depends on Phase 1. Can parallelize with Phase 3.

**Files to create:**
- `graph-query-api/backends/fabric.py` — `FabricGraphBackend` class (~200 lines)

**Files to modify:**
- `graph-query-api/pyproject.toml` — Add `httpx>=0.27.0` if not present

**Verification:**
- Unit test: Mock Fabric REST API, call `execute_query("{ routers { id } }")`, verify `{columns, data}` response
- Integration test (with real Fabric workspace): `GRAPH_BACKEND=fabric` + valid workspace/model IDs → `POST /query/graph` with GQL returns data
- `POST /query/topology` with `X-Graph: fabric` → returns `{nodes, edges, meta}`
- Backend cache: Two requests with same workspace/model → same backend instance

### Phase 3: Fabric Discovery Endpoints

> Depends on Phase 1. Can parallelize with Phase 2.

**Files to create:**
- `graph-query-api/router_fabric.py` — Discovery router (~120 lines)

**Files to modify:**
- `graph-query-api/main.py` — Register `fabric_router`

**Verification:**
- `GET /query/fabric/ontologies?workspace_id=<valid>` → returns list of ontologies
- `GET /query/fabric/eventhouses?workspace_id=<valid>` → returns list of eventhouses
- `GET /query/fabric/ontologies` (no workspace, no env var) → 400 error with clear message
- `GET /query/fabric/ontologies?workspace_id=<invalid>` → 404 error
- All existing endpoints unaffected

### Phase 4: Fabric OpenAPI Spec & Agent Provisioner

> Depends on Phase 2 (need working backend to validate queries).

**Files to create:**
- `graph-query-api/openapi/fabric.yaml` — GQL + KQL OpenAPI spec (~160 lines)

**Files to modify:**
- `scripts/agent_provisioner.py` — Add `"fabric"` to `OPENAPI_SPEC_MAP` and `GRAPH_TOOL_DESCRIPTIONS`
- `api/app/routers/config.py` — Add `backend_type` + Fabric fields to `ConfigApplyRequest`, pass through to provisioner

**Verification:**
- `GRAPH_BACKEND=fabric POST /api/config/apply` → SSE stream shows 5 agents provisioned with Fabric spec
- GraphExplorerAgent created with `OpenApiTool` containing GQL-documented `/query/graph` endpoint
- TelemetryAgent created with `OpenApiTool` containing KQL-documented `/query/telemetry` endpoint
- `GRAPH_BACKEND=cosmosdb POST /api/config/apply` → still works identically (regression test)

### Phase 5: Frontend — Backend Toggle & Fabric Tab

> Depends on Phase 1 (types) and Phase 3 (discovery endpoints).

**Files to create:**
- `frontend/src/hooks/useFabric.ts` — Fabric discovery hook (~80 lines)

**Files to modify:**
- `frontend/src/context/ScenarioContext.tsx` — Add `activeBackendType`, Fabric state fields, localStorage persistence
- `frontend/src/components/SettingsModal.tsx` — 4-tab layout, backend toggle, Fabric tab content

**Verification:**
- Open Settings → see backend radio buttons (CosmosDB selected by default)
- Toggle to Fabric → Data Sources tab greys out, Fabric tab activates
- Enter workspace ID → ontologies and eventhouses populate after 500ms
- Select ontology → "Load Topology" button works
- Click "Provision Agents" → SSE stream completes
- Refresh page → backend toggle persists (localStorage)
- Toggle back to CosmosDB → Fabric tab greys out, Data Sources tab works
- **All existing Scenarios/Upload functionality unchanged**

### Phase 6: End-to-End Integration Testing

> Depends on all previous phases.

**Verification:**
- Full flow: Start app → toggle to Fabric → enter workspace ID → select ontology → load topology → see graph in visualizer → provision agents → send chat message → agent queries Fabric → response shows in UI
- Switching backends: Start with CosmosDB scenario → toggle to Fabric → toggle back → CosmosDB scenario still works
- Mock mode: `GRAPH_BACKEND=mock` → everything still works (no regressions)

---

## File Change Inventory

| File | Action | Phase | Changes |
|------|--------|-------|---------|
| `graph-query-api/config.py` | MODIFY | 1 | Add `FABRIC` enum, Fabric env vars, `ScenarioContext` fields, update `get_scenario_context()`, `BACKEND_REQUIRED_VARS` |
| `graph-query-api/backends/__init__.py` | MODIFY | 1 | Add `FABRIC` branches to all factory/cache functions |
| `graph-query-api/main.py` | MODIFY | 1, 3 | Add Fabric var check in lifespan, register `fabric_router` |
| `azure_config.env.template` | MODIFY | 1 | Add Fabric env var section (~10 lines) |
| `graph-query-api/backends/fabric.py` | **CREATE** | 2 | `FabricGraphBackend` class (~200 lines) |
| `graph-query-api/router_fabric.py` | **CREATE** | 3 | Discovery endpoints: ontologies, eventhouses (~120 lines) |
| `graph-query-api/openapi/fabric.yaml` | **CREATE** | 4 | OpenAPI spec for GQL + KQL (~160 lines) |
| `scripts/agent_provisioner.py` | MODIFY | 4 | Add `"fabric"` to `OPENAPI_SPEC_MAP`, `GRAPH_TOOL_DESCRIPTIONS` |
| `api/app/routers/config.py` | MODIFY | 4 | Add Fabric fields to `ConfigApplyRequest`, pass `backend_type` to provisioner |
| `frontend/src/hooks/useFabric.ts` | **CREATE** | 5 | Fabric discovery hook (~80 lines) |
| `frontend/src/context/ScenarioContext.tsx` | MODIFY | 5 | Add `activeBackendType`, Fabric state, localStorage |
| `frontend/src/components/SettingsModal.tsx` | MODIFY | 5 | 4-tab layout, backend toggle, Fabric tab content |

### Files NOT Changed

- `graph-query-api/backends/cosmosdb.py` — CosmosDB backend is unchanged; Fabric is a parallel implementation
- `graph-query-api/backends/mock.py` — Mock backend unchanged
- `graph-query-api/router_graph.py` — Existing router dispatches via `get_backend_for_context()` which already handles backend type; no changes needed
- `graph-query-api/router_topology.py` — Same dispatch pattern; works with any `GraphBackend` implementation
- `graph-query-api/router_telemetry.py` — Initially unchanged; KQL telemetry support is a follow-up (Phase 4 OpenAPI handles agent-side; direct UI telemetry queries are a stretch goal)
- `graph-query-api/openapi/cosmosdb.yaml` — Unchanged
- `graph-query-api/openapi/mock.yaml` — Unchanged
- `frontend/src/hooks/useScenarios.ts` — Scenarios are backend-agnostic metadata; no changes needed
- `frontend/src/hooks/useTopology.ts` — Topology hook uses `getQueryHeaders()` which already includes `X-Graph`; works with Fabric backend automatically
- `frontend/src/components/AddScenarioModal.tsx` — Scenario creation is independent of backend type
- `scripts/fabric/` (reference provisioning scripts) — Not ported in v9; these handle Fabric resource provisioning (lakehouse, eventhouse, ontology creation) which is done manually per requirement 1

---

## Cross-Cutting UX Gaps

### Gap 1: Telemetry queries in Fabric mode

**Current state:** Telemetry router uses Cosmos NoSQL (SQL syntax). Fabric telemetry uses Eventhouse (KQL syntax). The `router_telemetry.py` only supports Cosmos SQL.

**Where this matters for the current plan:** When `GRAPH_BACKEND=fabric`, the telemetry agent gets a KQL-documented OpenAPI spec (Phase 4) but the backend endpoint still expects Cosmos SQL.

**Recommendation:** Either (a) extend `router_telemetry.py` with a conditional KQL path using `azure-kusto-data` SDK, or (b) create a separate `/query/fabric/telemetry` endpoint for KQL, or (c) route KQL queries through the same endpoint with backend detection.

**Scope:** Fast-follow — agent-side works via OpenAPI spec but direct UI telemetry is deferred.

### Gap 2: Prompt set compatibility with Fabric mode

**Current state:** Prompts are stored in Cosmos DB with scenario-specific containers. Fabric mode doesn't have the same scenario name derivation.

**Where this matters:** Prompt loading in `api/app/routers/config.py` derives scenario from graph name. Fabric ontology ID is not a valid scenario name.

**Recommendation:** Allow explicit `prompt_scenario` in `ConfigApplyRequest` (already exists). Frontend Fabric tab should have a prompt set dropdown identical to the CosmosDB Data Sources tab.

**Scope:** In scope (Phase 5) — add prompt set selector to Fabric tab.

### Gap 3: Graph visualizer GQL response format

**Current state:** `useTopology.ts` expects `{nodes: [{id, label, properties}], edges: [{source, target, label}]}`. Fabric GQL responses have different shapes.

**Where this matters:** `FabricGraphBackend.get_topology()` must map Fabric GQL results to this exact format.

**Recommendation:** The mapping logic in `backends/fabric.py` must be thorough. Test with actual Fabric ontology output.

**Scope:** In scope (Phase 2) — core implementation concern.

---

## UX Priority Matrix

| Priority | Enhancement | Item | Effort | Impact |
|----------|------------|------|--------|--------|
| **P0** | Backend toggle (radio buttons) | 5 | Small | High — core requirement |
| **P0** | 4-tab layout with greying | 5 | Small | High — core requirement |
| **P0** | Workspace ID input | 5 | Tiny | High — foundation for Fabric |
| **P0** | Ontology dropdown (from discovery) | 5 | Small | High — requirement 2, 3 |
| **P0** | Eventhouse dropdown (from discovery) | 5 | Small | High — requirement 4 |
| **P0** | Provision Agents with Fabric config | 5 | Medium | High — requirement 6 |
| **P1** | Auto-fetch on workspace ID entry | 5a | Tiny | Medium — reduces clicks |
| **P1** | Loading spinner during discovery | 5b | Tiny | Medium — feedback |
| **P1** | Auto-tab-switch on backend toggle | 5c | Tiny | Medium — reduces confusion |
| **P2** | Prompt set selector in Fabric tab | 5 | Small | Medium — completeness |
| **P2** | Fabric connection status indicator | 5 | Small | Medium — confidence |
| **P3** | KQL telemetry queries via UI | Gap 1 | Large | Low — agents handle it |
| **Backlog** | Fabric resource provisioning from UI | — | Large | Low — manual per req 1 |

### Implementation Notes

- **P0 items** are requirements from the original spec. Must be in the same PR as Phase 5.
- **P1 items** are small polish (~5 lines each) that should be included in Phase 5.
- **P2 items** can be separate small PRs after the core Fabric feature lands.
- **P3/Backlog items** are separate work streams.

---

## Edge Cases & Validation

### Backend Plumbing (Item 1)

**Invalid GRAPH_BACKEND value:** If env var is set to `"fabric"` but the string enum doesn't match, Python raises `ValueError`. Current pattern: `GraphBackendType(os.getenv("GRAPH_BACKEND", "cosmosdb").lower())`. Adding `"fabric"` to the enum handles this. No special edge case.

**Missing Fabric env vars:** When `GRAPH_BACKEND=fabric` but `FABRIC_WORKSPACE_ID` is empty, the lifespan warning fires. Requests to `/query/graph` will fail with `HTTPException(500, "workspace_id not configured")`. This is acceptable — same as CosmosDB with missing endpoint.

### Fabric Graph Backend (Item 2)

**Fabric API rate limiting:** Fabric REST API may return `429 Too Many Requests`. `FabricGraphBackend` should implement retry with exponential backoff (use `httpx` transport with retries or `tenacity`).

**Credential expiry:** `DefaultAzureCredential.get_token()` returns tokens valid ~1 hour. The `_get_token()` method calls `get_token()` on every request — `DefaultAzureCredential` handles caching and refresh internally. No manual token management needed.

**GQL query syntax errors:** Fabric GraphQL API returns `{"errors": [...]}` for malformed queries. The backend correctly returns `{"columns": [], "data": [], "error": "..."}` which the agent will see and retry with corrected syntax.

**Empty ontology:** If the selected ontology has no entities, `get_topology()` returns `{"nodes": [], "edges": []}`. Frontend handles empty graph gracefully (existing behavior).

**Large graph responses:** Fabric ontologies can have thousands of entities. GQL pagination (if supported by Fabric) should be used. If not, cap results at ~5000 nodes to avoid browser memory issues.

### Fabric Discovery (Item 3)

**No Fabric access:** If the service principal/managed identity doesn't have Fabric workspace access, the REST API returns `403`. The endpoint returns `HTTPException(403, "Access denied — check Fabric workspace permissions")`.

**Empty workspace:** If workspace has no ontologies or eventhouses, returns `{"items": [], "workspace_id": "..."}`. Frontend shows empty dropdown — acceptable.

**Invalid workspace ID format:** Fabric API returns `404` for malformed UUIDs. Endpoint propagates as 404.

### Agent Provisioner (Item 4)

**Fabric OpenAPI spec not found:** If `openapi/fabric.yaml` is missing, `_load_openapi_spec()` will raise `FileNotFoundError`. The `OPENAPI_SPEC_MAP` must point to the correct path.

**FabricTool vs OpenApiTool fallback:** If the team later decides to switch to `FabricTool`, the agent provisioner code path is isolated to a single function. The change would be: replace `OpenApiTool(spec=fabric_spec)` with `FabricTool(connection_id=fabric_connection_name)`. No architectural impact.

### Frontend (Item 5)

**Stale localStorage:** If a user's localStorage has `activeBackendType: "fabric"` but the backend doesn't support it (app redeployed without Fabric), the frontend will attempt to load the Fabric tab. The Fabric discovery calls will fail gracefully (error state), and the user can toggle back to CosmosDB.

**Concurrent backend toggle:** If user rapidly toggles between backends, the last toggle wins (React state batching). No race condition.

**Workspace ID formatting:** UUIDs are 36 characters. The auto-fetch debounce checks `length === 36` before firing. Partial UUIDs don't trigger unnecessary API calls.

---

## Migration & Backwards Compatibility

### Existing Data

No existing data migration required. Fabric is an additive new backend. All CosmosDB data (graphs, telemetry, scenarios, prompts) remains unchanged.

### API Surface Compatibility

All API changes are **additive**:
- New enum value `GraphBackendType.FABRIC` — existing `COSMOSDB` and `MOCK` unchanged
- New optional fields on `ScenarioContext` — all default to `None`, no breakage
- New optional fields on `ConfigApplyRequest` — Pydantic models with defaults
- New router `/query/fabric/*` — new endpoints, no conflict with existing
- New OpenAPI spec `fabric.yaml` — separate file, no change to existing specs

### Gradual Adoption

1. **Phase 1-3 can deploy without frontend changes** — backend supports Fabric but UI doesn't expose it. Users can set `GRAPH_BACKEND=fabric` in env var for testing.
2. **Phase 5 enables UI toggle** — users can switch at runtime. CosmosDB remains the default.
3. **No forced migration** — `GRAPH_BACKEND=cosmosdb` continues to work exactly as before.

### Rollback Plan

- Remove `FABRIC` from `GraphBackendType` enum and delete `backends/fabric.py`, `router_fabric.py`, `openapi/fabric.yaml`
- Remove Fabric fields from `ScenarioContext` and `ConfigApplyRequest`
- Revert `SettingsModal.tsx` to 3-tab layout
- No data cleanup needed — Fabric stores nothing in CosmosDB
- **Feature flag alternative:** Instead of enum, add `FABRIC_ENABLED=true/false` env var that gates the Fabric code paths. Simpler rollback without code removal.
