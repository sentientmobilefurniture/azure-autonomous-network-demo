# Fabric Integration — Implementation Plan

> **Created:** 2026-02-15
> **Last audited:** 2026-02-15 (third audit — Fabric API accuracy, GQL endpoint/response format corrections, item type fixes)
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
7. ~~In Data sources settings menu... Have a checkbox. Add a first tab basically to choose which backend will be used. To choose whether using a cosmosDB backend or fabric backend. Clicking it will grey out the cosmosDB tabs and ungrey the fabric tab. In total there are four tabs now.~~ **Revised (UI/UX audit):** A backend dropdown at the top of Settings modal selects CosmosDB or Fabric. The tab bar **adapts contextually** — `[Scenarios] [Data Sources] [Upload]` for CosmosDB, `[Scenarios] [Fabric Setup] [Upload]` for Fabric. No greyed-out tabs (poor UX). See Decision 5 for rationale.
8. Agents will be able to query the fabric ontology freely.

### Requirements Added (UI/UX Audit)

9. **Fabric resource provisioning from UI:** The UI can provision Fabric capacity, Lakehouse, Eventhouse, and Ontology via SSE-streamed API endpoints wrapping the reference scripts in `fabric_implementation_references/scripts/fabric/`. Same progress-bar UX as CosmosDB data uploads. This replaces the requirement to run provisioning scripts manually.
10. **Adaptive "Add Scenario" modal:** When the Fabric backend is selected, the AddScenarioModal changes its upload slots from CosmosDB-specific formats (.tar.gz for graph/telemetry) to Fabric-specific formats (CSVs for Lakehouse tables, CSVs for Eventhouse tables). Shared slots (runbooks, tickets, prompts) remain the same regardless of backend.
11. **Manual Fabric data upload:** The Upload tab adapts to show Lakehouse CSV upload + Eventhouse CSV upload when Fabric is selected, mirroring the CosmosDB upload pattern with the same drag-and-drop, progress-bar UX.
12. **One-click Fabric bootstrapping:** A "Provision Fabric Resources" button on the Fabric Setup tab runs the full provisioning pipeline (capacity attach → workspace create → lakehouse create + populate → eventhouse create + ingest → ontology create) with step-by-step SSE progress, so the user can go from zero to a working Fabric backend in a single action.

---

## Implementation Status

| Phase | Status | Scope |
|-------|--------|-------|
| **Phase 1:** Backend plumbing — config & enum | ⬜ Not started | `config.py`, `backends/__init__.py`, `azure_config.env.template` |
| **Phase 2:** Fabric graph backend | ⬜ Not started | `backends/fabric.py` (NEW) |
| **Phase 3:** Fabric discovery endpoints | ⬜ Not started | `router_fabric.py` (NEW), `main.py` |
| **Phase 3.5:** Fabric provisioning API | ⬜ Not started | `api/app/routers/fabric_provision.py` (NEW), wraps reference scripts |
| **Phase 4:** Fabric OpenAPI spec & agent provisioner | ⬜ Not started | `openapi/fabric.yaml` (NEW), `agent_provisioner.py`, `api/app/routers/config.py` |
| **Phase 5:** Frontend — adaptive backend UI | ⬜ Not started | `SettingsModal.tsx`, `AddScenarioModal.tsx`, `ScenarioContext.tsx`, `useFabric.ts` (NEW) |
| **Phase 6:** End-to-end integration testing | ⬜ Not started | Manual verification, mock Fabric mode |

### Deviations From Plan

| # | Plan Said | What Was Done | Rationale |
|---|-----------|---------------|-----------|
| D-1 | `/query/*` has no prod proxy (nginx.conf.template) | Removed false warning. Production uses root `nginx.conf` (Dockerfile L57) which already proxies `/query/*` | `nginx.conf.template` is for standalone frontend only; unified container uses `nginx.conf` |
| D-2 | 7 Fabric env vars in `config.py` | Expanded to ~30 env vars matching `fabric_implementation_references/azure_config.env` | Reference implementation uses many more vars (capacity, lakehouse, KQL DB, connection names). Incomplete list would cause implementation gaps |
| D-3 | `FABRIC_KQL_URI` env var name | Renamed to `EVENTHOUSE_QUERY_URI` everywhere | Reference implementation uses `EVENTHOUSE_QUERY_URI`. Consistency with reference avoids confusion |
| D-4 | Fabric routing via X-Graph header + ScenarioContext fields | `workspace_id` + `graph_model_id` passed in request body (GraphQueryRequest) instead | Reference implementation passes IDs in request body. X-Graph header still used for Cosmos-backed services (prompts, telemetry). Graph queries use body IDs. |
| D-5 | `router_graph.py` listed under "Files NOT Changed" | Moved to changed files (Phase 2) | Must pass `workspace_id`/`graph_model_id` from request body to backend. Reference `router_graph.py` does this. |
| D-6 | `models.py` not mentioned | Added to Phase 1 changes | `GraphQueryRequest` needs `workspace_id` + `graph_model_id` fields (matching reference `models.py`) |
| D-7 | No mention of Fabric Data Agent rejection | Added explicit rejection in Decision 1 | User confirmed: use graph-query-api proxy pattern, not Fabric Data Agent |
| D-8 | GQL endpoint: `/graphqlapis/{id}/graphql` | Corrected to `/GraphModels/{id}/executeQuery?beta=True` | Reference `test_gql_query.py` (working, tested) uses this endpoint. The `/graphqlapis/` path does not exist in the current Fabric REST API |
| D-9 | Response format: standard GraphQL `{"data": {...}}` | Corrected to Fabric-specific: `{"status": {...}, "result": {"columns": [...], "data": [...]}}` | Reference `test_gql_query.py` parses this format. No GraphQL-style `errors` array — errors are in `status.code` |
| D-10 | Ontology item type: `"GraphQLApi"` via `/items?type=GraphQLApi` | Corrected to `"Ontology"` via dedicated `/workspaces/{id}/ontologies` endpoint | Reference `provision_ontology.py` uses `/ontologies` sub-resource. `"GraphQLApi"` is not a valid Fabric item type |
| D-11 | Graph model discovery via generic `/items` endpoint | Corrected to dedicated `/workspaces/{id}/GraphModels` endpoint | Reference uses this to find auto-created GraphModel items. Falls back to filtering `/items` for type `"GraphModel"` or `"Graph"` |
| D-12 | GQL syntax examples: `{ routers { id } }` (GraphQL style) | Corrected to MATCH/RETURN syntax: `MATCH (r:CoreRouter) RETURN r.RouterId` | GQL (ISO GQL) uses MATCH/RETURN, not GraphQL curly-brace syntax. Reference sample queries confirm this |
| D-13 | `get_topology()` uses `__schema` introspection | Removed. GQL doesn't support `__schema`. Use Fabric REST `/ontologies/{id}` to discover types | GQL is not GraphQL — it has no introspection query. Entity types must be discovered via the Fabric REST API |
| D-14 | No 429/rate-limit handling in `execute_query()` | Added retry loop with exponential backoff (5 retries, 15s × attempt minimum) + JSON body timestamp parsing | Reference `test_gql_query.py` implements this pattern (5 retries, 15s × attempt, parses `"until:"` timestamp from 429 body). Reference ARCHITECTURE.md describes a planned 3-retry / 10s-minimum pattern for the async `fabric.py` — we follow `test_gql_query.py` (proven/tested) and adapt it for async `httpx`. |
| D-15 | Module-level `credential = DefaultAzureCredential()` (reference pattern) | Use lazy `get_credential()` everywhere | Reference `config.py` creates credential at import time. CONCERNS.md documents this crashes `GRAPH_BACKEND=mock` (no identity available in offline demos). Current codebase already uses lazy pattern — stick with it |
| D-16 | ~30 Fabric env vars | Expanded to ~35 to include `FABRIC_DATA_AGENT_ID`, `FABRIC_DATA_AGENT_API_VERSION`, `GRAPH_DATA_AGENT_ID`, `TELEMETRY_DATA_AGENT_ID` | Reference `collect_fabric_agents.py` discovers and writes these. Needed if Data Agent fallback path is ever added |

---

## Table of Contents

- [Requirements (Original)](#requirements-original)
- [Codebase Conventions & Context](#codebase-conventions--context)
- [Overview of Changes](#overview-of-changes)
- [Key Design Decisions](#key-design-decisions)
- [Item 1: Backend Plumbing](#item-1-backend-plumbing)
- [Item 2: Fabric Graph Backend](#item-2-fabric-graph-backend)
- [Item 3: Fabric Discovery Endpoints](#item-3-fabric-discovery-endpoints)
- [Item 3.5: Fabric Provisioning API](#item-35-fabric-provisioning-api)
- [Item 4: Agent Provisioner Changes](#item-4-agent-provisioner-changes)
- [Item 5: Frontend — Adaptive Backend UI](#item-5-frontend--adaptive-backend-ui)
- [Implementation Phases](#implementation-phases)
- [File Change Inventory](#file-change-inventory)
- [Edge Cases & Validation](#edge-cases--validation)
- [Migration & Backwards Compatibility](#migration--backwards-compatibility)

---

## Codebase Conventions & Context

### Request Routing

| URL prefix | Proxied to | Config |
|------------|-----------|--------|
| `/api/*` | API service on `:8000` | `vite.config.ts` L32-34 (dev), `nginx.conf` L18-30 (prod) |
| `/query/*` | graph-query-api on `:8100` | `vite.config.ts` L40-50 (dev), `nginx.conf` L43-55 (prod) |
| `/health` | API service on `:8000` | `vite.config.ts` L36-38 (dev), `nginx.conf` L33-38 (prod) |

> **Note:** Production uses `nginx.conf` (root-level, copied by Dockerfile L63), which **already proxies** `/query/*` to `:8100` with 600s timeout and SSE support. A separate `frontend/nginx.conf.template` exists for standalone frontend Container App deployments (uses `envsubst` + `${API_BACKEND_URL}`) and lacks `/query/*`, but this is irrelevant to the unified container deployment. New Fabric endpoints at `/query/fabric/*` are automatically covered by the existing `/query/` location block.

### Naming Conventions

| Concept | Example | Derivation |
|---------|---------|-----------|
| Graph name | `"cloud-outage-topology"` | User-chosen scenario name + `-topology` suffix |
| Scenario prefix | `"cloud-outage"` | `graph_name.rsplit("-", 1)[0]` — used to derive telemetry containers, prompts |
| Telemetry container | `"cloud-outage-AlertStream"` | `{prefix}-{ContainerName}` within shared `telemetry` DB |
| Search index | `"cloud-outage-runbooks-index"` | `{prefix}-runbooks-index` |
| Prompts container | `"cloud-outage"` | Same as prefix, inside shared `prompts` DB |

> **Fabric routing:** In Fabric mode, graph data is resolved via `FABRIC_WORKSPACE_ID` + `FABRIC_GRAPH_MODEL_ID` from env vars (not from X-Graph header derivation). The `X-Graph` header is still sent by the frontend for telemetry/prompts container routing (those remain in Cosmos even in Fabric mode), but graph queries pass `workspace_id` and `graph_model_id` in the request body — matching the reference implementation's `GraphQueryRequest` model. The `FabricGraphBackend` reads these IDs to call the Fabric REST API at `POST /v1/workspaces/{id}/GraphModels/{id}/executeQuery?beta=True`.

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
| 3.5 | Fabric provisioning API (wrap reference scripts as SSE endpoints) | Backend | High — one-click bootstrapping | Medium |
| 4 | Fabric OpenAPI spec + agent provisioner changes | Backend | High — agents can query Fabric | Medium |
| 5 | Frontend adaptive backend UI + scenario modal adaptation | Frontend | High — user-facing backend switch | Large |

### Dependency Graph

```
Phase 1 (config/enum) ──┐
                         ├──▶ Phase 2 (FabricGraphBackend)
                         │       │
                         │       ├──▶ Phase 4 (OpenAPI + provisioner)
                         │       │
                         ├──▶ Phase 3 (discovery endpoints)
                         │       │
                         ├──▶ Phase 3.5 (provisioning API) ◀── depends on Phase 1 (config/env vars)
                         │       │
                         └───────┴──▶ Phase 5 (frontend)
                                          │
                                          └──▶ Phase 6 (E2E testing)
```

Phase 1 is prerequisite for all others. Phases 2 and 3 can be parallelized.
Phase 3.5 depends on Phase 1 (needs config/env vars) but is independent of Phase 3 —
it wraps reference provisioning scripts directly, not discovery endpoints. Phase 4 depends on
Phase 2 (needs working backend). Phase 5 depends on Phases 3 and 3.5 (needs
discovery and provisioning endpoints). Phase 6 is final.

### UX Audit Summary

| Area | Finding | Severity |
|------|---------|----------|
| Backend toggle | No existing UI for switching backends — a backend dropdown at top of Settings modal is the cleanest approach | High |
| ~~Greyed-out tabs~~ | ~~Inactive backend's controls must be visually disabled, not hidden (per req 7)~~ **Revised:** Greyed-out tabs are poor UX — the tab bar should **adapt contextually** (different tabs for each backend). Simpler, cleaner, no dead UI elements. | **Revised → N/A** |
| Fabric settings | No ontology/eventhouse selectors exist — must be built from scratch | High |
| Add Scenario modal | **Not adapted for Fabric.** CosmosDB uploads .tar.gz archives; Fabric uploads CSVs to Lakehouse/Eventhouse. Upload slots must change based on selected backend. | **High (was missing)** |
| Fabric provisioning | Reference scripts exist but require CLI execution. Wrapping them as SSE API endpoints enables one-click provisioning from the UI with progress feedback. | **High (was missing)** |
| Upload tab | Upload tab shows CosmosDB-specific upload boxes. Must adapt to show Lakehouse/Eventhouse CSV uploads when Fabric is selected. | **High (was missing)** |
| Loading states | Ontology/eventhouse listing can be slow (Fabric REST) — needs loading spinner | Medium |
| Error feedback | Fabric auth failures need clear messaging (credential scope, workspace access) | Medium |

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

**Implication:** Need `backends/fabric.py` implementing full `GraphBackend` Protocol + `openapi/fabric.yaml` with GQL MATCH/RETURN syntax documentation.

### Decision 2: Query language — GQL for Fabric backend

The Fabric Graph Model supports GQL natively via its REST API (beta). The `backends/fabric.py` backend will:
- Accept GQL query strings (not Gremlin) in `execute_query()` — GQL uses `MATCH`/`RETURN` syntax (e.g., `MATCH (r:CoreRouter) RETURN r.RouterId, r.City LIMIT 10`)
- Call `POST https://api.fabric.microsoft.com/v1/workspaces/{id}/GraphModels/{model_id}/executeQuery?beta=True`
- Handle the Fabric-specific response format: `{"status": {"code": ..., "description": ...}, "result": {"columns": [...], "data": [...]}}`
- Implement retry with exponential backoff for HTTP 429 (rate limiting) — the Fabric executeQuery API rate-limits aggressively, especially on lower-SKU capacities
- Agent prompts for Fabric mode will use GQL MATCH/RETURN syntax instead of Gremlin

### Decision 3: Telemetry backend — Fabric Eventhouse/KQL when in Fabric mode (DEFERRED)

When `GRAPH_BACKEND=fabric`, telemetry queries **should** use Eventhouse (KQL) instead of Cosmos NoSQL. However, full KQL dispatch is **not in scope** for this plan. This plan adds:
- A **501 guard clause** in `router_telemetry.py` that returns a clear error when `GRAPH_BACKEND=fabric` (Phase 2, 3 lines)
- A **KQL-documented OpenAPI spec** for the telemetry agent (Phase 4) — the agent can use KQL syntax in prompts, but the actual KQL execution backend is a follow-up work item

The full implementation would require:
- A new `FabricTelemetryBackend` or an extension of `router_telemetry.py` to dispatch KQL queries via `azure-kusto-data` SDK
- Eventhouse connection details (KQL cluster URI, database name) from env vars or Fabric discovery

> **⚠️ This means telemetry queries will NOT work in Fabric mode until the follow-up KQL dispatch is implemented.** Agents will receive a clear 501 error and can communicate this to the user. Graph topology queries and agent-driven graph exploration work fully.

### Decision 4: Fabric routing — request body IDs (not X-Graph header)

Fabric does **not** use the `X-Graph` header for graph routing. Instead, `workspace_id` and `graph_model_id` are passed as fields in the `GraphQueryRequest` body, defaulting to env vars `FABRIC_WORKSPACE_ID` / `FABRIC_GRAPH_MODEL_ID` when omitted. This mirrors the reference implementation’s approach.

The `X-Graph` header is **still sent** by the frontend because prompts and telemetry remain in Cosmos even in Fabric mode — those routers need the scenario prefix. But graph routers in Fabric mode ignore `X-Graph` and use the body IDs.

`ScenarioContext` will be extended with optional Fabric fields for routers that need them:  

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
    eventhouse_query_uri: str | None = None
```

### Decision 5: Frontend tab structure — context-adaptive 3-tab layout (**REVISED**)

> **Original requirement 7** called for 4 tabs with greyed-out inactive tabs.
> After UI/UX audit, this is **rejected** in favour of context-adaptive tabs.

**Problem with greyed tabs:** Users see UI they can't interact with. It creates visual noise, invites confusion ("why is this greyed?"), and wastes space. A disabled tab that does nothing when clicked is a dead UI element — its only purpose is to tell you what you *can't* do, which is poor UX.

**Chosen: Context-adaptive 3-tab layout with backend dropdown.**

A backend dropdown (styled as a segmented control) sits at the top of the Settings modal, above the tab bar. The tab bar structure **changes based on the selected backend**:

```
Backend: [ CosmosDB ▾ ]                        Backend: [ Fabric ▾ ]

[ Scenarios ] [ Data Sources ] [ Upload ]      [ Scenarios ] [ Fabric Setup ] [ Upload ]
       ↓              ↓             ↓                ↓              ↓              ↓
  Scenario list   CosmosDB      CosmosDB        Scenario list  Workspace ID    Lakehouse CSV
  + Add button    dropdowns     .tar.gz          + Add button   Ontology sel.   Eventhouse CSV
  (shared)        (graph,       archives         (ADAPTED -     Eventhouse sel. Prompts upload
                  runbooks,                      different      Provision btn   Runbooks/Tickets
                  tickets,                       upload slots)  Agent binding   (shared with Cosmos)
                  prompts)
```

**Key UX principles:**
1. **No dead UI** — every visible element is interactive
2. **Tab labels change** — "Data Sources" becomes "Fabric Setup" (clear labelling)
3. **Shared Scenarios tab** — scenarios are metadata; the **AddScenarioModal adapts** its upload slots based on the selected backend
4. **Upload tab adapts** — shows Lakehouse/Eventhouse CSV uploads for Fabric, .tar.gz uploads for CosmosDB
5. **Backend selection persists** — stored in localStorage, survives page refresh

**AddScenarioModal adaptation:**

| Upload Slot | CosmosDB Mode | Fabric Mode |
|-------------|---------------|-------------|
| Graph Data | `.tar.gz` → graph-query-api Gremlin ingest | Lakehouse CSVs (Dim*.csv) → OneLake + delta tables |
| Telemetry | `.tar.gz` → Cosmos NoSQL containers | Eventhouse CSVs (AlertStream, LinkTelemetry) → KQL ingest |
| Runbooks | `.tar.gz` → AI Search index | `.tar.gz` → AI Search index *(unchanged)* |
| Tickets | `.tar.gz` → AI Search index | `.tar.gz` → AI Search index *(unchanged)* |
| Prompts | `.tar.gz` → Cosmos prompts DB | `.tar.gz` → Cosmos prompts DB *(unchanged — prompts stay in Cosmos even in Fabric mode)* |

> **Rationale:** Runbooks, tickets, and prompts are AI Search / Cosmos resources, not graph data. They are backend-agnostic and use the same upload path regardless of whether the graph backend is CosmosDB or Fabric. Only graph topology data and telemetry data change based on backend.

### Decision 6: Capacity provisioning is an ARM operation

Fabric capacity creation and management (create, suspend, resume, scale up/down) is an **Azure Resource Manager (ARM) operation**, NOT a Fabric REST API call. The Fabric REST API (`api.fabric.microsoft.com/v1`) manages workspace-level resources (lakehouses, eventhouses, ontologies), but capacity itself is an ARM resource managed via:

- `azure-mgmt-fabric` SDK (`FabricMgmtClient.fabric_capacities.begin_create_or_update()`)
- Azure CLI / Bicep / ARM templates (used by `azd up` in the `infra/` directory)

The `FABRIC_CAPACITY_ID` env var is populated during `azd up` (ARM deployment). The Phase 3.5 provisioning pipeline accepts `capacity_id` as input — it does NOT create the capacity. Users must have capacity pre-provisioned via `azd up` or the Azure Portal. This is consistent with the reference implementation where capacity is provisioned in the Bicep/`azd` step, not by the Python scripts.

Key `azure-mgmt-fabric` patterns (from SDK reference):
- All mutating operations are LRO — always call `.result()` on pollers
- Always set `tier="Fabric"` when specifying `CapacitySku`
- Suspend unused capacities to stop billing (`begin_suspend()`)
- Use `DefaultAzureCredential` for authentication

### Decision 7: Fabric provisioning from UI

**Chosen:** Wrap reference provisioning scripts as SSE-streamed API endpoints.

**Rationale:**
- Reference scripts in `fabric_implementation_references/scripts/fabric/` already implement the full provisioning pipeline (lakehouse, eventhouse, ontology)
- The app already has an established SSE progress pattern (`event: progress\ndata: {...}`) used by upload endpoints
- Running provisioning from the UI with progress feedback is dramatically better UX than requiring CLI execution
- The provisioning logic can be extracted into a shared Python module imported by both the API router and the standalone scripts

**Provisioning flow exposed via UI:**

```
┌─ Fabric Setup tab ──────────────────────────────────────────┐
│                                                              │
│  ❶ Capacity ID:  [___________________________] (or from env)│
│  ❷ Workspace:    [___________________________] (name/ID)    │
│                                                              │
│  [ 🚀 Provision Fabric Resources ]                           │
│     ├── Creating workspace...              ✓                 │
│     ├── Creating Lakehouse...              ✓                 │
│     ├── Uploading CSVs to OneLake...       ✓ (10/10 tables)  │
│     ├── Loading delta tables...            ▶ (7/10)          │
│     ├── Creating Eventhouse...             ○                 │
│     ├── Creating KQL tables...             ○                 │
│     ├── Ingesting telemetry CSVs...        ○                 │
│     └── Creating Ontology...               ○                 │
│                                                              │
│  ❸ Ontology:     [▼ NetworkTopologyOntology    ] [🔄]       │
│  ❹ Eventhouse:   [▼ NetworkTelemetryEH         ] [🔄]       │
│                                                              │
│  [ Load Topology ]  [ Provision Agents ]                     │
└──────────────────────────────────────────────────────────────┘
```

After provisioning completes, the ontology/eventhouse dropdowns auto-populate. The user selects their resources and clicks "Provision Agents" to bind agents to Fabric.

---

## Item 1: Backend Plumbing

### Current State

- `GraphBackendType` enum in `config.py` (lines 25-27) has only `COSMOSDB` and `MOCK`
- `GRAPH_BACKEND` global reads `GRAPH_BACKEND` env var, defaults to `"cosmosdb"`
- `ScenarioContext` dataclass (lines 71-101) has no Fabric fields
- `BACKEND_REQUIRED_VARS` (lines 121-126) maps only `COSMOSDB` and `MOCK`
- `backends/__init__.py` factory functions handle only `COSMOSDB` and `MOCK`
- `azure_config.env.template` has no Fabric variables (66 lines total)
- `azure_config.env` (live) has **no** Fabric env vars — they must be added manually or populated by reference provisioning scripts
- `models.py` `GraphQueryRequest` has only `query: str` — no `workspace_id` or `graph_model_id` fields

**Problem:** No Fabric backend type exists in the enum, config, routing, or request models.

### Target State

- `GraphBackendType` gains `FABRIC = "fabric"`
- `config.py` gains Fabric-specific env vars (full list matching reference `azure_config.env` — see below)
- `ScenarioContext` gains optional Fabric routing fields
- `BACKEND_REQUIRED_VARS` maps `FABRIC` to required vars
- `backends/__init__.py` dispatches to `FabricGraphBackend` for `FABRIC`
- `models.py` `GraphQueryRequest` gains `workspace_id` + `graph_model_id` fields (matching reference implementation)
- `azure_config.env.template` gains full Fabric section

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
# Env var names match those in fabric_implementation_references/azure_config.env
# ---------------------------------------------------------------------------

# Core API settings
FABRIC_API = os.getenv("FABRIC_API_URL", "https://api.fabric.microsoft.com/v1")
FABRIC_SCOPE = os.getenv("FABRIC_SCOPE", "https://api.fabric.microsoft.com/.default")

# Provisioning / capacity
FABRIC_SKU = os.getenv("FABRIC_SKU", "F8")
FABRIC_CAPACITY_ID = os.getenv("FABRIC_CAPACITY_ID", "")
AZURE_FABRIC_ADMIN = os.getenv("AZURE_FABRIC_ADMIN", "")

# Workspace
FABRIC_WORKSPACE_ID = os.getenv("FABRIC_WORKSPACE_ID", "")
FABRIC_WORKSPACE_NAME = os.getenv("FABRIC_WORKSPACE_NAME", "")

# Lakehouse
FABRIC_LAKEHOUSE_ID = os.getenv("FABRIC_LAKEHOUSE_ID", "")
FABRIC_LAKEHOUSE_NAME = os.getenv("FABRIC_LAKEHOUSE_NAME", "")

# Ontology / Graph Model
FABRIC_ONTOLOGY_ID = os.getenv("FABRIC_ONTOLOGY_ID", "")
FABRIC_ONTOLOGY_NAME = os.getenv("FABRIC_ONTOLOGY_NAME", "")
FABRIC_GRAPH_MODEL_ID = os.getenv("FABRIC_GRAPH_MODEL_ID", "")

# Eventhouse / KQL
FABRIC_EVENTHOUSE_ID = os.getenv("FABRIC_EVENTHOUSE_ID", "")
FABRIC_EVENTHOUSE_NAME = os.getenv("FABRIC_EVENTHOUSE_NAME", "")
FABRIC_KQL_DB_ID = os.getenv("FABRIC_KQL_DB_ID", "")
FABRIC_KQL_DB_NAME = os.getenv("FABRIC_KQL_DB_NAME", "")
FABRIC_KQL_DB_DEFAULT = os.getenv("FABRIC_KQL_DB_DEFAULT", "NetworkDB")
EVENTHOUSE_QUERY_URI = os.getenv("EVENTHOUSE_QUERY_URI", "")  # KQL cluster URI

# Agent connections (Foundry connection names for Fabric-bound agents)
FABRIC_CONNECTION_NAME = os.getenv("FABRIC_CONNECTION_NAME", "")
GRAPH_FABRIC_CONNECTION_NAME = os.getenv("GRAPH_FABRIC_CONNECTION_NAME", "")
TELEMETRY_FABRIC_CONNECTION_NAME = os.getenv("TELEMETRY_FABRIC_CONNECTION_NAME", "")
```

> **Naming reconciliation:** The reference `azure_config.env` uses `EVENTHOUSE_QUERY_URI` for the KQL cluster URI. Earlier drafts of this plan used `FABRIC_KQL_URI` — we adopt the reference name `EVENTHOUSE_QUERY_URI` for consistency. All env var names match `fabric_implementation_references/azure_config.env`.

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
    eventhouse_query_uri: str | None = None
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
            "eventhouse_query_uri": EVENTHOUSE_QUERY_URI,
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

#### `graph-query-api/models.py` — Add Fabric routing fields to GraphQueryRequest

```python
# Match the reference implementation in fabric_implementation_references/graph-query-api/models.py:
class GraphQueryRequest(BaseModel):
    query: str
    workspace_id: str = ""    # NEW: Fabric workspace ID (defaults to env var)
    graph_model_id: str = ""  # NEW: Fabric graph model ID (defaults to env var)
```

> **⚠️ Implementation note:** These fields default to `""` and are ignored by the CosmosDB/mock backends. The `FabricGraphBackend.execute_query()` reads them (falling back to env vars when empty). The `router_graph.py` must pass them through: `backend.execute_query(req.query, workspace_id=req.workspace_id, graph_model_id=req.graph_model_id)`. This matches the reference implementation exactly.

#### `azure_config.env.template` — Add Fabric section

```bash
# --- Fabric Integration (optional — only when GRAPH_BACKEND=fabric) ---
# Full variable list matches fabric_implementation_references/azure_config.env

# Provisioning / capacity
FABRIC_SKU=F8
AZURE_FABRIC_ADMIN=
FABRIC_CAPACITY_ID=

# Core API settings
FABRIC_API_URL=https://api.fabric.microsoft.com/v1
FABRIC_SCOPE=https://api.fabric.microsoft.com/.default

# Workspace
FABRIC_WORKSPACE_ID=
FABRIC_WORKSPACE_NAME=

# Lakehouse
FABRIC_LAKEHOUSE_ID=
FABRIC_LAKEHOUSE_NAME=

# Ontology / Graph Model
FABRIC_ONTOLOGY_ID=
FABRIC_ONTOLOGY_NAME=
FABRIC_GRAPH_MODEL_ID=

# Eventhouse / KQL
FABRIC_EVENTHOUSE_ID=
FABRIC_EVENTHOUSE_NAME=
FABRIC_KQL_DB_ID=
FABRIC_KQL_DB_NAME=
FABRIC_KQL_DB_DEFAULT=NetworkDB
EVENTHOUSE_QUERY_URI=

# Agent connections
FABRIC_CONNECTION_NAME=
GRAPH_FABRIC_CONNECTION_NAME=
TELEMETRY_FABRIC_CONNECTION_NAME=

# Data agents (auto-populated by collect_fabric_agents.py)
FABRIC_DATA_AGENT_ID=
FABRIC_DATA_AGENT_API_VERSION=
GRAPH_DATA_AGENT_ID=
TELEMETRY_DATA_AGENT_ID=
```

---

## Item 2: Fabric Graph Backend

### Current State

- `backends/cosmosdb.py` implements `GraphBackend` Protocol using Gremlin SDK
- `backends/mock.py` implements the Protocol with static data
- No `backends/fabric.py` exists
- Reference codebase has a `FabricGraphBackend` import in `__init__.py` but **no actual `fabric.py` file** — the only working GQL execution code is in `scripts/testing_scripts/test_gql_query.py`

**Problem:** No Fabric query execution exists. Must implement `execute_query()` (GQL via `/GraphModels/{id}/executeQuery?beta=True`) and `get_topology()` (GQL → nodes/edges).

### Target State

`backends/fabric.py` — full `GraphBackend` implementation using Fabric REST API for GQL queries.

### Backend Changes

#### `graph-query-api/backends/fabric.py` — **NEW** (~200 lines)

```python
"""
Fabric Graph Backend — executes GQL queries against Microsoft Fabric GraphModel Execute Query (beta) API.

Uses the Fabric REST API (beta):
  POST /v1/workspaces/{workspace_id}/GraphModels/{graph_model_id}/executeQuery?beta=True

Auth: DefaultAzureCredential with scope "https://api.fabric.microsoft.com/.default"

Response format: {"status": {"code": ..., "description": ...}, "result": {"columns": [...], "data": [...]}}
Rate limiting: Returns 429 with Retry-After header — must implement retry with exponential backoff
"""

from __future__ import annotations

import logging
import httpx

from config import (
    FABRIC_API, FABRIC_SCOPE, FABRIC_WORKSPACE_ID, FABRIC_GRAPH_MODEL_ID,
    EVENTHOUSE_QUERY_URI, get_credential,
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
        """Execute a GQL query against the Fabric GraphModel Execute Query (beta) API.

        Uses: POST /v1/workspaces/{id}/GraphModels/{id}/executeQuery?beta=True

        GQL syntax uses MATCH/RETURN (not GraphQL). Example:
          MATCH (r:CoreRouter) RETURN r.RouterId, r.City LIMIT 10

        Args:
            query: A GQL query string (MATCH/RETURN syntax).
            **kwargs: Optional workspace_id, graph_model_id overrides
                      (passed from GraphQueryRequest body fields).

        Returns:
            {"columns": [...], "data": [...]} matching the GraphBackend Protocol.
        """
        # Allow per-request ID overrides from request body (reference pattern)
        ws_id = kwargs.get("workspace_id") or self.workspace_id
        model_id = kwargs.get("graph_model_id") or self.graph_model_id

        client = await self._get_client()
        url = f"{FABRIC_API}/workspaces/{ws_id}/GraphModels/{model_id}/executeQuery"
        token = self._get_token()

        for attempt in range(1, 6):  # max 5 retries for 429
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                params={"beta": "True"},
                json={"query": query},
            )

            if resp.status_code == 429:
                # Parse Retry-After header first
                retry_after = int(resp.headers.get("Retry-After", "0"))
                # Fallback: parse Fabric's JSON body timestamp ("until: M/D/YYYY H:M:S AM/PM (UTC)")
                if not retry_after:
                    try:
                        from datetime import datetime, timezone
                        msg = resp.json().get("message", "")
                        if "until:" in msg:
                            ts_str = msg.split("until:")[1].strip().rstrip(")")
                            ts_str = ts_str.replace("(UTC", "").strip()
                            blocked_until = datetime.strptime(ts_str, "%m/%d/%Y %I:%M:%S %p")
                            blocked_until = blocked_until.replace(tzinfo=timezone.utc)
                            wait = (blocked_until - datetime.now(timezone.utc)).total_seconds()
                            retry_after = max(int(wait) + 1, 3)
                    except Exception:
                        pass
                retry_after = max(retry_after, 15 * attempt)  # at least 15s × attempt
                if attempt < 5:
                    import asyncio
                    logger.warning(f"Rate-limited (429). Waiting {retry_after}s (attempt {attempt}/5)")
                    await asyncio.sleep(retry_after)
                    token = self._get_token()  # refresh token
                    continue
                return {"columns": [], "data": [], "error": "Rate limit exceeded after 5 retries"}

            break

        # For non-429 errors (400 bad GQL syntax, 403, 500, etc.), catch and
        # return as error payload — the router uses the error-as-200 pattern
        # to allow the LLM agent to read and self-correct.
        if resp.status_code != 200:
            return {"columns": [], "data": [], "error": f"Fabric API error (HTTP {resp.status_code}): {resp.text[:500]}"}
        raw = resp.json()

        # Fabric executeQuery returns: {"status": {...}, "result": {"columns": [...], "data": [...]}}
        status = raw.get("status", {})
        if status.get("code", "").lower() not in ("", "ok", "success"):
            return {"columns": [], "data": [], "error": status.get("description", str(status))}

        result = raw.get("result", {})
        columns = result.get("columns", [])
        data = result.get("data", [])

        return {"columns": columns, "data": data}

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

        # Default: query all nodes and relationships using GQL MATCH/RETURN syntax.
        # The ontology schema defines entity types (CoreRouter, TransportLink, etc.)
        # and relationship types (connects_to, etc.).
        #
        # GQL does NOT support GraphQL-style introspection (__schema).
        # To discover types, use the Fabric REST API:
        #   GET /v1/workspaces/{id}/ontologies/{ontology_id}
        # Then query each entity type for nodes and relationship type for edges.
        #
        # Example queries against the Network Topology ontology:
        #   MATCH (n) RETURN LABELS(n) AS type, count(n) AS cnt GROUP BY type
        #   MATCH (r:CoreRouter) RETURN r.RouterId AS id, r.City AS city
        #   MATCH (l:TransportLink)-[:connects_to]->(r:CoreRouter) RETURN l.LinkId, r.RouterId
        #
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

> **⚠️ Implementation note:** The `get_topology()` method's default query depends entirely on the Fabric ontology schema. The ontology defines entity types (e.g., CoreRouter, AggSwitch, TransportLink) and relationship types (e.g., connects_to). The implementer must:
> 1. Use the Fabric REST API `GET /v1/workspaces/{id}/ontologies/{ontology_id}` to discover available entity types (GQL does **not** support GraphQL-style `__schema` introspection)
> 2. Build per-type GQL queries like `MATCH (r:CoreRouter) RETURN r.RouterId AS id, r.City AS city, r.Region AS region`
> 3. Build relationship queries: `MATCH (a)-[rel]->(b) RETURN a, type(rel) AS relType, b`
> 4. Map results to `{nodes: [{id, label, properties}], edges: [{id, source, target, label, properties}]}`
>
> This is the single hardest piece of the implementation. Start with a simple hard-coded query for a known ontology, then generalize.

> **⚠️ Implementation note:** `httpx` is used for async HTTP calls in the backend. It is **not** currently in any project `pyproject.toml` and **must be added** to `graph-query-api/pyproject.toml` as `httpx>=0.27.0`. Alternatively, `requests` (sync, used by the reference provisioning scripts) could be used via `asyncio.to_thread()` — similar to how `router_telemetry.py` wraps sync Cosmos SDK calls. The async `httpx` approach is preferred for the backend to avoid blocking the event loop.

#### `graph-query-api/router_graph.py` — Pass Fabric IDs through to backend

The existing `router_graph.py` must pass request body fields to the backend so `FabricGraphBackend` can use per-request workspace/model overrides:

```python
# Current (simplified):
result = await backend.execute_query(req.query)

# New — pass through Fabric routing fields:
result = await backend.execute_query(
    req.query,
    workspace_id=req.workspace_id,
    graph_model_id=req.graph_model_id,
)
```

This matches the reference implementation's `router_graph.py` exactly. For CosmosDB/mock backends, the extra `**kwargs` are harmlessly ignored by the existing `execute_query()` signatures.

> **⚠️ Implementation note — Error-as-200 pattern:** The reference `router_graph.py` wraps ALL backend calls in a try/except and returns HTTP 200 with an `error` field in the `GraphQueryResponse` body — it NEVER raises HTTP 4xx/5xx to the caller. This is critical for LLM agent self-correction: `OpenApiTool` treats non-200 responses as tool failures (opaque to the LLM), but 200 + error payload lets the agent read the error message, fix the query syntax, and retry. Ensure `router_graph.py` catches `NotImplementedError`, `HTTPException`, and generic `Exception` around the `backend.execute_query()` call, returning `GraphQueryResponse(error=f"...")` in each case. The reference implementation shows this exact pattern.

---

## Item 3: Fabric Discovery Endpoints

### Current State

- No endpoints exist for browsing Fabric workspace contents
- Requirements 2 and 4 demand listing ontologies and eventhouses for dropdown selectors
- The reference codebase (`fabric_implementation_references/scripts/fabric/`) has provisioning scripts that call `GET /v1/workspaces/{id}/items` but no API endpoints exist in the main project

**Problem:** Frontend needs to discover available Fabric ontologies and eventhouses to populate selectors.

### Target State

New router `router_fabric.py` with:
- `GET /query/fabric/ontologies?workspace_id=...` — list ontologies (via `/workspaces/{id}/ontologies`)
- `GET /query/fabric/eventhouses?workspace_id=...` — list eventhouses (via `/workspaces/{id}/eventhouses`)
- `GET /query/fabric/graph-models?workspace_id=...` — list graph models (via `/workspaces/{id}/GraphModels`)

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
    """Call Fabric REST API to list items of a given type in a workspace.

    Uses type-specific sub-resource endpoints where available:
      - "Ontology"    → GET /workspaces/{id}/ontologies
      - "Eventhouse"  → GET /workspaces/{id}/eventhouses
      - "GraphModel"  → GET /workspaces/{id}/GraphModels
      - "Lakehouse"   → GET /workspaces/{id}/lakehouses
    Falls back to GET /workspaces/{id}/items for other types.
    """
    import httpx

    cred = get_credential()
    token = cred.get_token(FABRIC_SCOPE)

    # Fabric provides dedicated sub-resource endpoints for key item types
    sub_resource_map = {
        "Ontology": "ontologies",
        "Eventhouse": "eventhouses",
        "GraphModel": "GraphModels",
        "Lakehouse": "lakehouses",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        sub_resource = sub_resource_map.get(item_type)
        if sub_resource:
            url = f"{FABRIC_API}/workspaces/{workspace_id}/{sub_resource}"
            resp = await client.get(
                url,
                headers={"Authorization": f"Bearer {token.token}"},
            )
        else:
            url = f"{FABRIC_API}/workspaces/{workspace_id}/items"
            resp = await client.get(
                url,
                params={"type": item_type} if item_type else {},
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

    items = await _fabric_list_items(ws_id, "Ontology")
    # Fabric has a dedicated /ontologies sub-resource endpoint.
    # Each ontology auto-creates a corresponding GraphModel item —
    # use the /graph-models endpoint or /workspaces/{id}/GraphModels to find them.
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
):
    """List graph models in a Fabric workspace.

    Graph models are auto-created by Fabric when an ontology is created.
    They have item type "GraphModel" (or "Graph" in some API versions).
    Uses the dedicated /workspaces/{id}/GraphModels endpoint.
    """
    ws_id = workspace_id or FABRIC_WORKSPACE_ID
    if not ws_id:
        raise HTTPException(400, "workspace_id required")

    items = await _fabric_list_items(ws_id, "GraphModel")
    return FabricListResponse(
        workspace_id=ws_id,
        items=[
            FabricItem(
                id=item["id"],
                display_name=item.get("displayName", item["id"]),
                type="graph-model",
            )
            for item in items
        ],
    )
```

> **⚠️ Implementation note:** The Fabric REST API has **dedicated sub-resource endpoints** for key item types — use `/workspaces/{id}/ontologies` for ontologies, `/workspaces/{id}/eventhouses` for eventhouses, and `/workspaces/{id}/GraphModels` for graph models. The generic `/workspaces/{id}/items?type=...` endpoint works as a fallback for other types. The reference provisioning scripts use both patterns. Item type strings used in the Fabric API: `"Ontology"`, `"GraphModel"` (or `"Graph"`), `"Eventhouse"`, `"Lakehouse"`, `"KQLDatabase"`.

> **⚠️ Implementation note — Pagination:** The Fabric REST API uses `continuationUri` / `continuationToken` for paginated responses. The discovery endpoints above fetch only the first page. For workspaces with many items, this will silently omit results. The reference `populate_fabric_config.py` also has this limitation (takes `[0]` of each list — first-match assumption). Add pagination loop if production use cases require listing more than ~100 items per type. At minimum, log a warning if the response contains a `continuationUri`.

#### `graph-query-api/main.py` — Register new router

```python
# Add import:
from router_fabric import router as fabric_router

# Add to app includes (after other routers):
app.include_router(fabric_router)
```

---

## Item 3.5: Fabric Provisioning API

### Current State

- Reference provisioning scripts exist at `fabric_implementation_references/scripts/fabric/`:
  - `provision_lakehouse.py` — creates workspace, lakehouse, uploads CSVs via OneLake, loads delta tables
  - `provision_eventhouse.py` — creates eventhouse, KQL tables, ingests CSV data via queued ingestion
  - `provision_ontology.py` — creates ontology with entity types, relationships, data bindings
  - `populate_fabric_config.py` — discovers Fabric items and writes IDs to `azure_config.env`
  - `_config.py` — shared configuration (paths, Fabric API constants)
- These scripts are standalone CLI tools — they cannot be called from the UI
- They use `requests` (sync) and `azure.identity.DefaultAzureCredential`
- They write progress to stdout with `print()` statements

**Problem:** Users must SSH/CLI into the machine to provision Fabric resources. The existing upload UX (drag-drop + SSE progress) sets expectations for a similar experience with Fabric provisioning.

### Target State

New API router `api/app/routers/fabric_provision.py` that exposes the provisioning pipeline as SSE-streamed endpoints, plus CSV upload endpoints for Lakehouse and Eventhouse data.

### Backend Changes

#### `api/app/routers/fabric_provision.py` — **NEW** (~300 lines)

Wraps the provisioning logic from the reference scripts into FastAPI SSE endpoints:

```python
"""
Router: /api/fabric/* — Fabric resource provisioning and data upload.

Provides:
  POST /api/fabric/provision        — Full provisioning pipeline (SSE)
  POST /api/fabric/upload-lakehouse — Upload CSVs to Lakehouse delta tables (SSE)
  POST /api/fabric/upload-eventhouse — Upload CSVs to Eventhouse KQL tables (SSE)

All endpoints stream progress via SSE using the same event format as
existing upload endpoints (event: progress, event: error, event: complete).
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger("api.fabric_provision")

router = APIRouter(prefix="/api/fabric", tags=["fabric-provision"])


class ProvisionRequest(BaseModel):
    capacity_id: str
    workspace_name: str = "AutonomousNetworkDemo"
    scenario_name: str = "cloud-outage"


@router.post("/provision")
async def provision_fabric_resources(
    request: ProvisionRequest,
):
    # ProvisionRequest is a Pydantic model (JSON body), NOT Form data.
    # The frontend sends JSON via fetch() — Form(...) would be incompatible.
    capacity_id = request.capacity_id
    workspace_name = request.workspace_name
    scenario_name = request.scenario_name
    """
    Full Fabric provisioning pipeline with SSE progress streaming.

    Steps:
    1. Create/find workspace (attach to capacity)
    2. Create Lakehouse
    3. Upload scenario CSVs to OneLake (from data/lakehouse/)
    4. Load CSVs as managed delta tables
    5. Create Eventhouse
    6. Create KQL tables (AlertStream, LinkTelemetry)
    7. Ingest scenario CSVs from data/eventhouse/
    8. Create Ontology with entity types + data bindings
    9. Update azure_config.env with discovered IDs

    Returns SSE stream with progress events.
    """
    async def generate():
        # Each step emits: event: progress\ndata: {"step": "...", "detail": "...", "pct": N}\n\n
        # On error: event: error\ndata: {"error": "..."}\n\n
        # On completion: event: complete\ndata: {"workspace_id": "...", ...}\n\n
        ...

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/upload-lakehouse")
async def upload_lakehouse_csvs(
    files: list[UploadFile] = File(...),
    scenario_name: str = Form(default=""),
    workspace_id: str = Form(default=""),
    lakehouse_id: str = Form(default=""),
):
    """
    Upload CSV files to Lakehouse → OneLake → delta tables.

    Accepts multiple CSV files (Dim*.csv, Fact*.csv).
    Each file is:
    1. Uploaded to OneLake Files via DataLakeServiceClient
    2. Loaded as a managed delta table via Lakehouse Tables API

    Returns SSE stream with per-file progress.

    Implementation note: Reuses logic from provision_lakehouse.py
    FabricClient._upload_to_onelake() and _load_table().
    """
    async def generate():
        ...

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/upload-eventhouse")
async def upload_eventhouse_csvs(
    files: list[UploadFile] = File(...),
    scenario_name: str = Form(default=""),
    workspace_id: str = Form(default=""),
    eventhouse_id: str = Form(default=""),
):
    """
    Upload CSV files to Eventhouse KQL tables.

    Accepts CSV files matching known table schemas (AlertStream, LinkTelemetry).
    Each file is ingested via azure-kusto-ingest QueuedIngestClient.

    Returns SSE stream with per-file progress.

    Implementation note: Reuses logic from provision_eventhouse.py
    _create_table_if_not_exists() and _ingest_csv().
    """
    async def generate():
        ...

    return StreamingResponse(generate(), media_type="text/event-stream")
```

> **⚠️ Implementation note — Shared provisioning module:**
> Rather than duplicating the provisioning logic from the reference scripts, extract the core logic into a shared module importable by both the API router and the standalone scripts:
>
> ```
> scripts/fabric/
>   _config.py            ← existing shared config
>   _provisioner.py       ← NEW: extracted provisioning logic (classes, no CLI)
>   provision_lakehouse.py  ← CLI wrapper: imports from _provisioner.py
>   provision_eventhouse.py ← CLI wrapper: imports from _provisioner.py
>   provision_ontology.py   ← CLI wrapper: imports from _provisioner.py
> ```
>
> The API router imports from `_provisioner.py` and wraps each step in SSE event emission.
> This avoids code duplication and keeps the standalone scripts functional for CLI use.
>
> **⚠️ Cross-project import:** The API service (`api/`) and provisioning scripts (`scripts/fabric/`) are separate Python projects. To import `_provisioner.py` from the API router, either:
> 1. **Symlink** `scripts/fabric/` into `api/app/services/fabric/` at build time (Dockerfile)
> 2. **Copy** the shared module into the API package during Docker build
> 3. **Mount** a shared volume in docker-compose
> 4. **Use `sys.path.insert()`** in the API router to add `scripts/fabric/` to the Python path
>
> Option 1 (symlink in Dockerfile) is recommended — it keeps a single source of truth and works with the existing build pipeline.

> **⚠️ Implementation note — Dependencies:**
> The provisioning endpoints require additional packages in `api/pyproject.toml`:
> - `azure-storage-file-datalake` (OneLake upload via `DataLakeServiceClient`)
> - `azure-kusto-data` + `azure-kusto-ingest` (Eventhouse KQL ingest)
> - `requests` (already present)
>
> These are the same packages used by the standalone provisioning scripts.

> **⚠️ Implementation note — OneLake URL:** CSV uploads to Lakehouse go through OneLake's ADLS Gen2 endpoint at `https://onelake.dfs.fabric.microsoft.com`. The reference `provision_lakehouse.py` uses `DataLakeServiceClient("https://onelake.dfs.fabric.microsoft.com", credential=DefaultAzureCredential())` to upload files to `{workspace_id}/{lakehouse_id}/Files/`. This is NOT the same as the Fabric REST API base URL (`https://api.fabric.microsoft.com/v1`). The provisioning code must use both endpoints — Fabric REST for item creation/management, OneLake ADLS Gen2 for file uploads.

#### `api/app/main.py` — Register provisioning router

```python
from app.routers.fabric_provision import router as fabric_provision_router
app.include_router(fabric_provision_router)
```

### Provisioning Flow Diagram

```
User clicks "🚀 Provision All Resources" on Fabric Setup tab
                    │
                    ▼
        POST /api/fabric/provision
          { capacity_id, workspace_name, scenario_name }
                    │
                    ▼ SSE stream
    ┌───────────────────────────────────┐
    │ Step 1: Create/find workspace     │ → event: progress {step: "workspace", pct: 10}
    │ Step 2: Create Lakehouse          │ → event: progress {step: "lakehouse", pct: 20}
    │ Step 3: Upload CSVs to OneLake    │ → event: progress {step: "onelake-upload", pct: 30-50}
    │ Step 4: Load delta tables         │ → event: progress {step: "delta-tables", pct: 50-65}
    │ Step 5: Create Eventhouse         │ → event: progress {step: "eventhouse", pct: 70}
    │ Step 6: Create KQL tables         │ → event: progress {step: "kql-tables", pct: 75}
    │ Step 7: Ingest Eventhouse CSVs    │ → event: progress {step: "kql-ingest", pct: 80-90}
    │ Step 8: Create Ontology           │ → event: progress {step: "ontology", pct: 95}
    │ Step 9: Update config             │ → event: complete {workspace_id, lakehouse_id, ...}
    └───────────────────────────────────┘
                    │
                    ▼
    Frontend auto-populates workspace ID, fetches ontologies/eventhouses
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
    Micro-API for executing GQL queries against Microsoft Fabric Graph Model.
    Used by Foundry agents via OpenApiTool.
    Backend: Microsoft Fabric GraphModel Execute Query (beta) API
    GQL uses MATCH/RETURN syntax (ISO GQL), not GraphQL.
servers:
  - url: "{base_url}"
    description: Deployed Container App

paths:
  /query/graph:
    post:
      operationId: query_graph
      summary: Execute a GQL query against the Fabric Graph Model
      description: |
        Submits a GQL (Graph Query Language) query to Microsoft Fabric.
        Returns columns and data rows from the network ontology.
        Use GQL MATCH/RETURN syntax (not Gremlin, not GraphQL). Examples:
          MATCH (r:CoreRouter) RETURN r.RouterId, r.City, r.Region LIMIT 10
          MATCH (l:TransportLink)-[:connects_to]->(r:CoreRouter) RETURN r.RouterId, l.LinkId, l.LinkType LIMIT 10
          MATCH (n) RETURN LABELS(n) AS type, count(n) AS cnt GROUP BY type ORDER BY cnt DESC
      parameters:
        - name: X-Graph
          in: header
          required: false
          schema:
            type: string
          description: |
            Scenario context for telemetry/prompts routing (Cosmos).
            Not used for Fabric graph queries — use workspace_id/graph_model_id in body instead.
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
                    A GQL query string for the Fabric Graph Model.
                    Uses MATCH/RETURN syntax (ISO GQL, not GraphQL).
                    Examples:
                      MATCH (r:CoreRouter) RETURN r.RouterId, r.City LIMIT 10
                      MATCH (n) RETURN LABELS(n) AS type, count(n) AS cnt GROUP BY type
                workspace_id:
                  type: string
                  description: |
                    Fabric workspace ID. Defaults to FABRIC_WORKSPACE_ID env var if omitted.
                graph_model_id:
                  type: string
                  description: |
                    Fabric graph model ID. Defaults to FABRIC_GRAPH_MODEL_ID env var if omitted.
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
    "fabric": "Execute a GQL query against the Fabric GraphModel to explore network topology and relationships.",
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

## Item 5: Frontend — Adaptive Backend UI

### Current State

- `SettingsModal.tsx` (~675 lines) has 3 tabs: `scenarios`, `datasources`, `upload`
- Tab type is `type Tab = 'scenarios' | 'datasources' | 'upload'`
- Data Sources tab shows Cosmos-specific dropdowns (graph, runbooks index, tickets index, prompt set)
- `AddScenarioModal.tsx` (~685 lines) has 5 fixed upload slots: graph, telemetry, runbooks, tickets, prompts — all `.tar.gz` files uploaded to CosmosDB/AI Search endpoints
- `ScenarioContext.tsx` (~160 lines) manages `activeGraph`, `activeRunbooksIndex`, `activeTicketsIndex`, `activePromptSet`
- No concept of backend type in frontend state

**Problems:**
1. No way to toggle between CosmosDB and Fabric
2. No Fabric settings UI, no ontology/eventhouse discovery
3. AddScenarioModal upload slots are CosmosDB-specific — Fabric needs Lakehouse CSVs + Eventhouse CSVs
4. Upload tab is CosmosDB-specific
5. No provisioning UI for Fabric resources

### Target State — Context-Adaptive Settings Modal

The Settings modal adapts its tab bar and tab content based on backend selection:

```
┌──────────────────────────────────────────────────────────────┐
│ Settings                                                  ✕  │
│                                                              │
│ Backend: [▾ Fabric    ]  ← dropdown / segmented control      │
│                                                              │
│ [ Scenarios ] [ Fabric Setup ] [ Upload ]                    │
│                   (active)                                    │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│ ┌─ Fabric Setup ───────────────────────────────────────────┐ │
│ │                                                          │ │
│ │ Capacity ID  [env: FABRIC_CAPACITY_ID or manual]         │ │
│ │ Workspace    [env: FABRIC_WORKSPACE_ID or manual]        │ │
│ │                                                          │ │
│ │ ┌─ Provision Fabric Resources ─────────────────────────┐ │ │
│ │ │  ✓ Creating workspace                                │ │ │
│ │ │  ✓ Creating Lakehouse                                │ │ │
│ │ │  ✓ Uploading CSVs to OneLake (10/10 tables)          │ │ │
│ │ │  ▶ Loading delta tables (7/10)                       │ │ │
│ │ │  ○ Creating Eventhouse                               │ │ │
│ │ │  ○ Creating KQL tables + ingesting CSVs              │ │ │
│ │ │  ○ Creating Ontology                                 │ │ │
│ │ │  [ 🚀 Provision ]                                    │ │ │
│ │ └──────────────────────────────────────────────────────┘ │ │
│ │                                                          │ │
│ │ Ontology      [▼ NetworkTopologyOntology     ] [🔄]     │ │
│ │ Eventhouse    [▼ NetworkTelemetryEH           ] [🔄]     │ │
│ │ Prompt Set    [▼ cloud-outage                 ]          │ │
│ │                                                          │ │
│ │ [ Load Topology ]  [ Provision Agents ]                  │ │
│ └──────────────────────────────────────────────────────────┘ │
│                                                              │
│                                                   [ Close ]  │
└──────────────────────────────────────────────────────────────┘
```

**When CosmosDB is selected** (existing behaviour, unchanged):

```
┌──────────────────────────────────────────────────────────────┐
│ Settings                                                  ✕  │
│                                                              │
│ Backend: [▾ CosmosDB  ]                                      │
│                                                              │
│ [ Scenarios ] [ Data Sources ] [ Upload ]                    │
│                                                              │
│   ... exactly the same as current implementation ...         │
└──────────────────────────────────────────────────────────────┘
```

### Target State — Adaptive AddScenarioModal

When the user clicks "+" (Add Scenario), the modal detects `activeBackendType` and shows different upload slots:

```
┌─ New Scenario (Fabric) ─────────────────────────────────────┐
│                                                              │
│  Scenario Name: [cloud-outage________________]               │
│                                                              │
│  ┌─ Upload Slots ─────────────────────────────────────────┐  │
│  │                                                        │  │
│  │  🔗 Graph Data (Lakehouse CSVs)           [Drop CSVs]  │  │
│  │     DimCoreRouter.csv  ✓                               │  │
│  │     DimTransportLink.csv  ✓                            │  │
│  │     DimAggSwitch.csv  ✓                                │  │
│  │     ... (all Dim*.csv + FactMPLSPathHops.csv, etc.)    │  │
│  │                                                        │  │
│  │  📊 Telemetry (Eventhouse CSVs)           [Drop CSVs]  │  │
│  │     AlertStream.csv  ✓                                 │  │
│  │     LinkTelemetry.csv  ✓                               │  │
│  │                                                        │  │
│  │  📋 Runbooks (.tar.gz)    ← same as CosmosDB           │  │
│  │  🎫 Tickets (.tar.gz)     ← same as CosmosDB           │  │
│  │  📝 Prompts (.tar.gz)     ← same as CosmosDB           │  │
│  │                                                        │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│                              [ Cancel ]  [ Upload & Save ]   │
└──────────────────────────────────────────────────────────────┘
```

**Key differences from CosmosDB AddScenarioModal:**

| Aspect | CosmosDB Mode | Fabric Mode |
|--------|---------------|-------------|
| Graph slot | Single `.tar.gz` → `/query/upload/graph` | Multiple CSVs → `/api/fabric/upload-lakehouse` |
| Telemetry slot | Single `.tar.gz` → `/query/upload/telemetry` | Multiple CSVs → `/api/fabric/upload-eventhouse` |
| Graph slot accepts | `.tar.gz` | `.csv` (multiple files) |
| Telemetry slot accepts | `.tar.gz` | `.csv` (multiple files) |
| Runbooks | `.tar.gz` → AI Search *(unchanged)* | `.tar.gz` → AI Search *(unchanged)* |
| Tickets | `.tar.gz` → AI Search *(unchanged)* | `.tar.gz` → AI Search *(unchanged)* |
| Prompts | `.tar.gz` → Cosmos prompts DB *(unchanged)* | `.tar.gz` → Cosmos prompts DB *(unchanged)* |
| Upload endpoint | `/query/upload/{slot}` | Graph/Telemetry: `/api/fabric/upload-{target}`, rest unchanged |

### Target State — Adaptive Upload Tab

The standalone Upload tab (for loading data into an existing scenario) also adapts:

**CosmosDB mode** (unchanged):
```
[ Graph .tar.gz ]  [ Telemetry .tar.gz ]  [ Runbooks ]  [ Tickets ]
```

**Fabric mode:**
```
[ Lakehouse CSVs ]  [ Eventhouse CSVs ]  [ Runbooks ]  [ Tickets ]
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
  /** Fabric capacity ID (for provisioning) */
  fabricCapacityId: string;
  /** Setters */
  setActiveBackendType: (type: 'cosmosdb' | 'fabric') => void;
  setFabricWorkspaceId: (id: string) => void;
  setFabricOntologyId: (id: string) => void;
  setFabricGraphModelId: (id: string) => void;
  setFabricEventhouseId: (id: string) => void;
  setFabricCapacityId: (id: string) => void;
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
const [fabricCapacityId, setFabricCapacityId] = useState(
  () => localStorage.getItem('fabricCapacityId') || '',
);

// Persist to localStorage on change
useEffect(() => {
  localStorage.setItem('activeBackendType', activeBackendType);
}, [activeBackendType]);
// ... repeat for each fabric field ...
```

#### `hooks/useFabric.ts` — **NEW** (~120 lines, expanded from original 80)

```tsx
/**
 * Hook for Fabric workspace discovery AND provisioning.
 */
import { useState, useCallback } from 'react';
import { consumeSSE } from '../utils/sseStream';

interface FabricItem {
  id: string;
  display_name: string;
  type: string;
  description?: string;
}

interface ProvisionStep {
  step: string;
  status: 'pending' | 'running' | 'done' | 'error';
  detail?: string;
}

export function useFabric() {
  const [ontologies, setOntologies] = useState<FabricItem[]>([]);
  const [eventhouses, setEventhouses] = useState<FabricItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [provisionSteps, setProvisionSteps] = useState<ProvisionStep[]>([]);
  const [provisioning, setProvisioning] = useState(false);

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

  /** SSE-streamed provisioning: capacity → workspace → lakehouse → eventhouse → ontology */
  const provisionAll = useCallback(async (capacityId: string, workspaceName?: string) => {
    setProvisioning(true);
    setProvisionSteps([]);
    setError(null);
    try {
      const res = await fetch('/api/fabric/provision', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          capacity_id: capacityId,
          workspace_name: workspaceName || 'AutonomousNetworkDemo',
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await consumeSSE(res, {
        onProgress: (d) => {
          setProvisionSteps(prev => {
            const updated = [...prev];
            const existing = updated.findIndex(s => s.step === d.step);
            if (existing >= 0) {
              updated[existing] = { ...updated[existing], status: 'done', detail: d.detail };
            } else {
              // Mark previous as done, add new as running
              if (updated.length) updated[updated.length - 1].status = 'done';
              updated.push({ step: d.step, status: 'running', detail: d.detail });
            }
            return updated;
          });
        },
        onError: (d) => { setError(d.error); },
        onComplete: () => {
          setProvisionSteps(prev => prev.map(s => ({ ...s, status: 'done' as const })));
        },
      });
    } catch (e) {
      setError(String(e));
    } finally {
      setProvisioning(false);
    }
  }, []);

  return {
    ontologies, eventhouses, loading, error,
    fetchOntologies, fetchEventhouses,
    provisionSteps, provisioning, provisionAll,
  };
}
```

#### `SettingsModal.tsx` — Context-adaptive tab layout

```tsx
// Tab type adapts based on backend:
type CosmosTab = 'scenarios' | 'datasources' | 'upload';
type FabricTab = 'scenarios' | 'fabricsetup' | 'upload';
type Tab = CosmosTab | FabricTab;

// Compute visible tabs based on backend:
const visibleTabs: { key: Tab; label: string }[] =
  activeBackendType === 'fabric'
    ? [
        { key: 'scenarios', label: 'Scenarios' },
        { key: 'fabricsetup', label: 'Fabric Setup' },
        { key: 'upload', label: 'Upload' },
      ]
    : [
        { key: 'scenarios', label: 'Scenarios' },
        { key: 'datasources', label: 'Data Sources' },
        { key: 'upload', label: 'Upload' },
      ];

// Backend dropdown above tab bar:
<div className="flex items-center gap-3 px-6 mt-2">
  <span className="text-xs text-text-muted">Backend:</span>
  <select
    value={activeBackendType}
    onChange={(e) => {
      const bt = e.target.value as 'cosmosdb' | 'fabric';
      setActiveBackendType(bt);
      // Auto-switch to the appropriate settings tab
      setTab(bt === 'fabric' ? 'fabricsetup' : 'datasources');
    }}
    className="bg-neutral-bg1 border border-white/10 rounded px-2 py-1 text-sm text-text-primary"
  >
    <option value="cosmosdb">CosmosDB</option>
    <option value="fabric">Fabric</option>
  </select>
</div>

// Tab bar — render only visible tabs (no greyed-out dead UI):
<div className="flex px-6 mt-3 gap-1">
  {visibleTabs.map(({ key, label }) => (
    <button
      key={key}
      onClick={() => setTab(key)}
      className={`px-4 py-2 text-sm rounded-t-md transition-colors ${
        tab === key
          ? 'bg-neutral-bg1 text-text-primary border-t border-x border-white/10'
          : 'text-text-muted hover:text-text-secondary'
      }`}
    >
      {label}
    </button>
  ))}
</div>
```

**Fabric Setup tab content** (replaces the old "Fabric tab"):

```tsx
{tab === 'fabricsetup' && (
  <>
    {/* Capacity + Workspace inputs */}
    <div className="bg-neutral-bg1 rounded-lg border border-white/5 p-4 space-y-3">
      <label className="text-xs text-text-muted block mb-1">Fabric Capacity ID</label>
      <input
        type="text"
        value={fabricCapacityId}
        onChange={(e) => setFabricCapacityId(e.target.value)}
        placeholder="From azure_config.env or enter manually..."
        className="w-full bg-neutral-bg2 border border-white/10 rounded px-3 py-1.5 text-sm"
      />
      <label className="text-xs text-text-muted block mb-1">Fabric Workspace ID</label>
      <input
        type="text"
        value={fabricWorkspaceId}
        onChange={(e) => setFabricWorkspaceId(e.target.value)}
        placeholder="Enter workspace ID or provision below..."
        className="w-full bg-neutral-bg2 border border-white/10 rounded px-3 py-1.5 text-sm"
      />
    </div>

    {/* Provisioning section — one-click Fabric bootstrapping */}
    <div className="bg-neutral-bg1 rounded-lg border border-white/5 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-text-primary">Provision Fabric Resources</span>
        <span className="text-xs text-text-muted">Workspace → Lakehouse → Eventhouse → Ontology</span>
      </div>

      {provisionSteps.length > 0 && (
        <div className="space-y-1.5">
          {provisionSteps.map((s, i) => (
            <div key={i} className="flex items-center gap-2 text-xs">
              <span>{s.status === 'done' ? '✓' : s.status === 'running' ? '▶' : '○'}</span>
              <span className={s.status === 'done' ? 'text-status-success' : 'text-text-secondary'}>
                {s.step}
              </span>
              {s.detail && <span className="text-text-muted ml-auto">{s.detail}</span>}
            </div>
          ))}
        </div>
      )}

      <button
        onClick={() => provisionAll(fabricCapacityId)}
        disabled={!fabricCapacityId || provisioning}
        className="w-full px-4 py-2 text-sm bg-brand/20 text-brand rounded hover:bg-brand/30
                   disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        {provisioning ? 'Provisioning...' : '🚀 Provision All Resources'}
      </button>
    </div>

    {/* Ontology + Eventhouse selectors (from discovery) */}
    {/* ... same ontology/eventhouse dropdowns as before, with auto-fetch ... */}

    {/* Prompt set selector — shared with CosmosDB path */}
    <div className="bg-neutral-bg1 rounded-lg border border-white/5 p-4 space-y-3">
      <div className="flex items-center gap-2">
        <span className="h-2 w-2 rounded-full bg-green-400" />
        <span className="text-sm font-medium text-text-primary">Prompt Set</span>
      </div>
      <select
        value={activePromptSet}
        onChange={(e) => setActivePromptSet(e.target.value)}
        className="w-full bg-neutral-bg2 border border-white/10 rounded px-3 py-1.5 text-sm"
      >
        <option value="">Select prompt set...</option>
        {promptScenarios.map((p) => (
          <option key={p.scenario} value={p.scenario}>{p.scenario} ({p.prompt_count})</option>
        ))}
      </select>
    </div>

    {/* Action buttons */}
    <div className="flex gap-3">
      <ActionButton label="Load Topology" icon="🔗"
        description="Fetch graph from Fabric ontology"
        onClick={async () => { /* ... POST /query/topology with Fabric headers ... */ }} />
      <ActionButton label="Provision Agents" icon="🤖"
        description="Bind agents to Fabric data sources"
        onClick={async () => { /* ... POST /api/config/apply with backend_type=fabric ... */ }} />
    </div>

    {fabricError && <p className="text-xs text-status-error">{fabricError}</p>}
  </>
)}
```

> **⚠️ Implementation note:** When the user changes the backend dropdown:
> 1. Auto-switch to the corresponding settings tab (`fabricsetup` or `datasources`)
> 2. Persist `activeBackendType` to localStorage
> 3. Existing scenario-derived bindings remain but are ignored when Fabric is active
> 4. The Scenarios tab still works for both backends — but the AddScenarioModal adapts (see below)
> 5. If the current tab doesn't exist in the new backend's tab set (e.g., user was on `fabricsetup` and switched to CosmosDB), auto-redirect to the first settings tab

#### `AddScenarioModal.tsx` — Adapt upload slots based on backend

```tsx
// Import backend type from context:
const { activeBackendType } = useScenarioContext();

// Define slot configurations per backend:
const COSMOS_SLOTS: SlotDef[] = [
  { key: 'graph', label: 'Graph Data', icon: '🔗', endpoint: '/query/upload/graph', accept: '.tar.gz,.tgz' },
  { key: 'telemetry', label: 'Telemetry', icon: '📊', endpoint: '/query/upload/telemetry', accept: '.tar.gz,.tgz' },
  { key: 'runbooks', label: 'Runbooks', icon: '📋', endpoint: '/query/upload/runbooks', accept: '.tar.gz,.tgz' },
  { key: 'tickets', label: 'Tickets', icon: '🎫', endpoint: '/query/upload/tickets', accept: '.tar.gz,.tgz' },
  { key: 'prompts', label: 'Prompts', icon: '📝', endpoint: '/query/upload/prompts', accept: '.tar.gz,.tgz' },
];

const FABRIC_SLOTS: SlotDef[] = [
  { key: 'graph', label: 'Lakehouse (Graph CSVs)', icon: '🔗',
    endpoint: '/api/fabric/upload-lakehouse', accept: '.csv',
    hint: 'Drop Dim*.csv and Fact*.csv files for Lakehouse delta tables',
    multiFile: true },
  { key: 'telemetry', label: 'Eventhouse (Telemetry CSVs)', icon: '📊',
    endpoint: '/api/fabric/upload-eventhouse', accept: '.csv',
    hint: 'Drop AlertStream.csv, LinkTelemetry.csv for KQL ingest',
    multiFile: true },
  { key: 'runbooks', label: 'Runbooks', icon: '📋', endpoint: '/query/upload/runbooks', accept: '.tar.gz,.tgz' },
  { key: 'tickets', label: 'Tickets', icon: '🎫', endpoint: '/query/upload/tickets', accept: '.tar.gz,.tgz' },
  { key: 'prompts', label: 'Prompts', icon: '📝', endpoint: '/query/upload/prompts', accept: '.tar.gz,.tgz' },
];

// Select active slots:
const SLOT_DEFS = activeBackendType === 'fabric' ? FABRIC_SLOTS : COSMOS_SLOTS;
```

> **Key UX detail:** The Fabric graph/telemetry slots accept **multiple CSV files** (not a single archive). The drop zone shows a file list with individual status indicators. The upload endpoint receives all CSVs for a category, uploads them to OneLake, and creates/loads delta tables (lakehouse) or ingests into KQL tables (eventhouse) with SSE progress.

> **⚠️ Implementation note — AddScenarioModal multi-drop zone:** The existing multi-file drop zone (line ~420 of `AddScenarioModal.tsx`) hard-codes `input.accept = '.tar.gz,.tgz'`. When `activeBackendType === 'fabric'`, this must change to `'.csv'` for graph/telemetry slots but remain `'.tar.gz,.tgz'` for runbooks/tickets/prompts. The simplest approach: use `.csv,.tar.gz,.tgz` as the global accept filter and let file-slot assignment logic (the `detectSlot()` function) handle routing. Note that `detectSlot()` currently parses `.tar.gz` filename patterns (`name-graph.tar.gz`) — it must be extended to recognize CSV filenames like `DimCoreRouter.csv` → Lakehouse slot, `AlertStream.csv` → Eventhouse slot.

#### `SettingsModal.tsx` Upload tab — adapt based on backend

```tsx
{tab === 'upload' && (
  activeBackendType === 'fabric' ? (
    // Fabric upload boxes: Lakehouse + Eventhouse + Runbooks + Tickets
    <div className="space-y-3">
      <UploadBox
        label="Lakehouse Data (Graph CSVs)"
        icon="🔗"
        hint="Dim*.csv, Fact*.csv → Lakehouse delta tables"
        endpoint="/api/fabric/upload-lakehouse"
        accept=".csv"
      />
      <UploadBox
        label="Eventhouse Data (Telemetry CSVs)"
        icon="📊"
        hint="AlertStream.csv, LinkTelemetry.csv → KQL tables"
        endpoint="/api/fabric/upload-eventhouse"
        accept=".csv"
      />
      <UploadBox label="Runbooks" icon="📋" hint="Upload .tar.gz"
        endpoint="/query/upload/runbooks" accept=".tar.gz,.tgz" />
      <UploadBox label="Tickets" icon="🎫" hint="Upload .tar.gz"
        endpoint="/query/upload/tickets" accept=".tar.gz,.tgz" />
    </div>
  ) : (
    // CosmosDB upload boxes (existing — unchanged)
    <div className="space-y-3">
      <UploadBox label="Graph Data" icon="🔗" hint="Upload .tar.gz"
        endpoint="/query/upload/graph" accept=".tar.gz,.tgz" />
      <UploadBox label="Telemetry" icon="📊" hint="Upload .tar.gz"
        endpoint="/query/upload/telemetry" accept=".tar.gz,.tgz" />
      <UploadBox label="Runbooks" icon="📋" hint="Upload .tar.gz"
        endpoint="/query/upload/runbooks" accept=".tar.gz,.tgz" />
      <UploadBox label="Tickets" icon="🎫" hint="Upload .tar.gz"
        endpoint="/query/upload/tickets" accept=".tar.gz,.tgz" />
    </div>
  )
)}
```

### UX Enhancements

#### 5a. Auto-fetch on workspace ID entry

**Problem:** User must manually click "Refresh" after entering workspace ID.

**Fix:** Debounce `fetchOntologies()` and `fetchEventhouses()` to fire 500ms after workspace ID changes (if it looks like a valid UUID).

```tsx
useEffect(() => {
  if (fabricWorkspaceId.length === 36 && tab === 'fabricsetup') {
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

#### 5c. Backend dropdown auto-tab-switch

**Problem:** User switches backend but is viewing a tab that doesn't exist in the new layout.

**Fix:** When changing backend, auto-switch to the corresponding settings tab.

```tsx
const handleBackendChange = (bt: 'cosmosdb' | 'fabric') => {
  setActiveBackendType(bt);
  setTab(bt === 'fabric' ? 'fabricsetup' : 'datasources');
};
```

**Why:** The user's intent when switching backends is to configure that backend. Take them directly there.

#### 5d. Post-provisioning auto-populate

**Problem:** After one-click provisioning completes, user must manually refresh dropdowns.

**Fix:** After `provisionAll()` SSE stream completes successfully, auto-fire `fetchOntologies()` and `fetchEventhouses()` with the newly created workspace ID.

```tsx
// In useFabric provisionAll() onComplete handler:
onComplete: (data) => {
  if (data.workspace_id) {
    // Auto-update workspace ID and populate dropdowns
    setFabricWorkspaceId(data.workspace_id);
    fetchOntologies(data.workspace_id);
    fetchEventhouses(data.workspace_id);
  }
}
```

**Why:** After provisioning, the user's next action is selecting resources. Don't make them click Refresh.

---

## Implementation Phases

### Phase 1: Backend Plumbing — Config & Enum

> Independent — prerequisite for all other phases.

**Files to modify:**
- `graph-query-api/config.py` — Add `FABRIC` to enum, Fabric env vars, `ScenarioContext` fields, `get_scenario_context()` changes, `BACKEND_REQUIRED_VARS`
- `graph-query-api/backends/__init__.py` — Add `FABRIC` branches to `get_backend()`, `get_backend_for_context()`, `get_backend_for_graph()`
- `graph-query-api/models.py` — Add `workspace_id`, `graph_model_id` fields to `GraphQueryRequest`
- `graph-query-api/main.py` — Add lifespan check for Fabric vars
- `azure_config.env.template` — Add Fabric section (~30 vars, matching reference)

**Verification:**
- `GRAPH_BACKEND=fabric uv run python -c "from config import GRAPH_BACKEND; print(GRAPH_BACKEND)"` → prints `GraphBackendType.FABRIC`
- **App starts without crash** when `GRAPH_BACKEND=fabric` and required vars are missing (warns but doesn't exit)
- Existing `GRAPH_BACKEND=cosmosdb` and `GRAPH_BACKEND=mock` still work

### Phase 2: Fabric Graph Backend

> Depends on Phase 1. Can parallelize with Phase 3.

**Files to create:**
- `graph-query-api/backends/fabric.py` — `FabricGraphBackend` class (~200 lines)

**Files to modify:**
- `graph-query-api/pyproject.toml` — Add `httpx>=0.27.0` (not currently a dependency)
- `graph-query-api/router_graph.py` — Pass `workspace_id` + `graph_model_id` from request body to `backend.execute_query()`
- `graph-query-api/router_telemetry.py` — Add 501 guard clause for `GRAPH_BACKEND=fabric` (see Gap 1)

**Verification:**
- Unit test: Mock Fabric REST API, call `execute_query("MATCH (r:CoreRouter) RETURN r.RouterId")`, verify `{columns, data}` response
- Integration test (with real Fabric workspace): `GRAPH_BACKEND=fabric` + valid workspace/model IDs → `POST /query/graph` with GQL MATCH/RETURN query returns data
- `POST /query/topology` → returns `{nodes, edges, meta}`
- Backend cache: Two requests with same workspace/model → same backend instance

### Phase 3: Fabric Discovery Endpoints

> Depends on Phase 1. Can parallelize with Phase 2.

**Files to create:**
- `graph-query-api/router_fabric.py` — Discovery router (~120 lines)

**Files to modify:**
- `graph-query-api/main.py` — Register `fabric_router`

> **Note:** Production `nginx.conf` (root-level) already proxies `/query/*` to `:8100` — no nginx changes needed. New `/query/fabric/*` routes are automatically covered.

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

### Phase 3.5: Fabric Provisioning API

> Depends on Phase 1 (needs config/env vars). Independent of Phase 3.

**Files to create:**
- `api/app/routers/fabric_provision.py` — Provisioning + CSV upload endpoints (~300 lines)
- `scripts/fabric/_provisioner.py` — Extracted shared provisioning logic (refactored from standalone scripts)

**Important:** The provisioning pipeline must include `assign_fabric_role.py` as a late step (after ontology creation) to grant the Container App managed identity Contributor access to the Fabric workspace. Without this, deployed apps cannot authenticate to Fabric REST API. Requires `GRAPH_QUERY_API_PRINCIPAL_ID` env var.

**Files to modify:
- `api/app/main.py` — Register `fabric_provision_router`
- `api/pyproject.toml` — Add `azure-storage-file-datalake`, `azure-kusto-data`, `azure-kusto-ingest`
- `scripts/fabric/provision_lakehouse.py` — Refactor to import from `_provisioner.py` (thin CLI wrapper)
- `scripts/fabric/provision_eventhouse.py` — Refactor to import from `_provisioner.py` (thin CLI wrapper)
- `scripts/fabric/provision_ontology.py` — Refactor to import from `_provisioner.py` (thin CLI wrapper)

**Verification:**
- `POST /api/fabric/provision { capacity_id: "..." }` → SSE stream completes all 8 steps, `azure_config.env` updated
- `POST /api/fabric/upload-lakehouse` with CSV files → tables created in Lakehouse
- `POST /api/fabric/upload-eventhouse` with CSV files → data ingested into KQL tables
- Standalone scripts still work: `uv run provision_lakehouse.py` → same result as before refactor
- Missing capacity ID → 400 error with helpful message

### Phase 5: Frontend — Adaptive Backend UI

> Depends on Phase 1 (types), Phase 3 (discovery endpoints), and Phase 3.5 (provisioning endpoints).

**Files to create:**
- `frontend/src/hooks/useFabric.ts` — Fabric discovery + provisioning hook (~120 lines)

**Files to modify:**
- `frontend/src/context/ScenarioContext.tsx` — Add `activeBackendType`, Fabric state fields, `fabricCapacityId`, localStorage persistence
- `frontend/src/components/SettingsModal.tsx` — Context-adaptive tab layout, backend dropdown, Fabric Setup tab, adaptive Upload tab
- `frontend/src/components/AddScenarioModal.tsx` — Backend-aware upload slot definitions (COSMOS_SLOTS vs FABRIC_SLOTS), multi-file CSV support for Fabric graph/telemetry slots

**Verification:**
- Open Settings → backend dropdown shows "CosmosDB" (default)
- Switch to "Fabric" → tab bar changes to `[Scenarios] [Fabric Setup] [Upload]`
- **No greyed-out tabs** — only relevant tabs are shown
- Fabric Setup tab: capacity/workspace inputs, provision button, ontology/eventhouse dropdowns
- Add Scenario (with Fabric selected) → modal shows Lakehouse CSV + Eventhouse CSV slots instead of .tar.gz
- Drag CSV files into Lakehouse slot → upload with progress, delta tables created
- Upload tab (Fabric) → shows Lakehouse/Eventhouse CSV upload boxes
- Switch back to CosmosDB → tab bar restores to `[Scenarios] [Data Sources] [Upload]`
- CosmosDB Add Scenario → original 5-slot .tar.gz upload (unchanged)
- Refresh page → backend selection persists (localStorage)
- **All existing CosmosDB functionality unchanged**

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
| `graph-query-api/config.py` | MODIFY | 1 | Add `FABRIC` enum, Fabric env vars (~30 vars matching reference), `ScenarioContext` fields, update `get_scenario_context()`, `BACKEND_REQUIRED_VARS` |
| `graph-query-api/backends/__init__.py` | MODIFY | 1 | Add `FABRIC` branches to all factory/cache functions |
| `graph-query-api/models.py` | MODIFY | 1 | Add `workspace_id`, `graph_model_id` fields to `GraphQueryRequest` (matching reference) |
| `graph-query-api/main.py` | MODIFY | 1, 3 | Add Fabric var check in lifespan, register `fabric_router` |
| `azure_config.env.template` | MODIFY | 1 | Add Fabric env var section (~30 lines, matching `fabric_implementation_references/azure_config.env`) |
| `graph-query-api/backends/fabric.py` | **CREATE** | 2 | `FabricGraphBackend` class (~200 lines) |
| `graph-query-api/pyproject.toml` | MODIFY | 2 | Add `httpx>=0.27.0` dependency |
| `graph-query-api/router_telemetry.py` | MODIFY | 2 | Add 501 guard clause for `GRAPH_BACKEND=fabric` (3 lines — see Gap 1) |
| `graph-query-api/router_graph.py` | MODIFY | 2 | Pass `workspace_id` + `graph_model_id` from request body to `backend.execute_query()` |
| `scripts/fabric/_provisioner.py` | **CREATE** | 3.5 | Shared provisioning logic extracted from standalone scripts |
| `scripts/fabric/provision_lakehouse.py` | MODIFY | 3.5 | Refactor to thin CLI wrapper importing from `_provisioner.py` |
| `scripts/fabric/provision_eventhouse.py` | MODIFY | 3.5 | Refactor to thin CLI wrapper importing from `_provisioner.py` |
| `scripts/fabric/provision_ontology.py` | MODIFY | 3.5 | Refactor to thin CLI wrapper importing from `_provisioner.py` |
| `api/app/main.py` | MODIFY | 3.5 | Register `fabric_provision_router` |
| `api/pyproject.toml` | MODIFY | 3.5 | Add `azure-storage-file-datalake`, `azure-kusto-data`, `azure-kusto-ingest` |
| `graph-query-api/openapi/fabric.yaml` | **CREATE** | 4 | OpenAPI spec for GQL + KQL (~160 lines) |
| `scripts/agent_provisioner.py` | MODIFY | 4 | Add `"fabric"` to `OPENAPI_SPEC_MAP`, `GRAPH_TOOL_DESCRIPTIONS` |
| `api/app/routers/config.py` | MODIFY | 4 | Add Fabric fields to `ConfigApplyRequest`, pass `backend_type` to provisioner |
| `frontend/src/hooks/useFabric.ts` | **CREATE** | 5 | Fabric discovery + provisioning hook (~120 lines) |
| `frontend/src/context/ScenarioContext.tsx` | MODIFY | 5 | Add `activeBackendType`, Fabric state, `fabricCapacityId`, localStorage |
| `frontend/src/components/SettingsModal.tsx` | MODIFY | 5 | Context-adaptive tab layout, backend dropdown, Fabric Setup tab, adaptive Upload tab |
| `frontend/src/components/AddScenarioModal.tsx` | MODIFY | 5 | Backend-aware upload slots (COSMOS_SLOTS / FABRIC_SLOTS), multi-file CSV support, `detectSlot()` extended for CSV filenames, multi-drop zone `accept` filter |
| `frontend/src/hooks/useScenarios.ts` | MODIFY | 5 | `selectScenario()` must pass `backend_type` + Fabric IDs to `/api/config/apply` when `activeBackendType === 'fabric'` |
| `frontend/src/utils/sseStream.ts` | MODIFY | 5 | `uploadWithSSE()` must support `File[]` (multi-file upload) for Fabric CSV slots |
| `frontend/src/types/index.ts` | MODIFY | 5 | `SlotKey` union type needs Fabric-specific keys or the SLOT_DEFS must adapt dynamically |

### Files NOT Changed

- `graph-query-api/backends/cosmosdb.py` — CosmosDB backend is unchanged; Fabric is a parallel implementation
- `graph-query-api/backends/mock.py` — Mock backend unchanged
- `graph-query-api/router_topology.py` — Dispatches via `get_backend_for_context()` which handles backend type; works with any `GraphBackend` implementation. `get_topology()` is part of the Protocol.
- `graph-query-api/openapi/cosmosdb.yaml` — Unchanged
- `graph-query-api/openapi/mock.yaml` — Unchanged
- `nginx.conf` (root) — Already proxies `/query/*` to `:8100`; no changes needed for Fabric
- `frontend/nginx.conf.template` — Only used for standalone frontend deployments, not the unified container. Not relevant.
- `frontend/src/hooks/useScenarios.ts` — Scenarios are backend-agnostic metadata; **minor change needed:** `selectScenario()` calls `POST /api/config/apply` with `{ graph, runbooks_index, tickets_index, prompt_scenario }` — when `activeBackendType === 'fabric'`, it must also pass `backend_type: 'fabric'`, `fabric_workspace_id`, `fabric_ontology_id`, `fabric_graph_model_id` so agent provisioning uses the Fabric OpenAPI spec
- `frontend/src/hooks/useTopology.ts` — Topology hook uses `getQueryHeaders()` which includes `X-Graph`; works with Fabric backend automatically (Fabric graph routing uses request body IDs, not the header)

> **⚠️ Implementation note — Telemetry in Fabric mode:** Reference implementation runs telemetry queries via Cosmos NoSQL even when `GRAPH_BACKEND=fabric` — only graph queries change backend. V9 correctly defers KQL dispatch (Decision 3) but the 501 guard clause must only apply to the telemetry agent's KQL queries, NOT to existing Cosmos SQL telemetry queries from the `X-Graph` header pathway. If users have telemetry data in both Cosmos (from CosmosDB scenarios) and Eventhouse, the router needs to differentiate. The simplest approach: 501 guard only fires when `GRAPH_BACKEND=fabric` AND NO Cosmos NoSQL data exists for the given scenario prefix. Otherwise, let the existing Cosmos SQL path handle it.

---

## Cross-Cutting UX Gaps

### Gap 1: Telemetry queries in Fabric mode

**Current state:** Telemetry router uses Cosmos NoSQL (SQL syntax). Fabric telemetry uses Eventhouse (KQL syntax). The `router_telemetry.py` only supports Cosmos SQL.

**Where this matters for the current plan:** When `GRAPH_BACKEND=fabric`, the telemetry agent gets a KQL-documented OpenAPI spec (Phase 4) but the backend endpoint still expects Cosmos SQL. **This means the telemetry agent will send KQL to an endpoint that only speaks Cosmos SQL — it will fail at runtime.** The error recovery path (“read the error, fix your query”) won’t help because the endpoint fundamentally can’t execute KQL.

**Recommendation:** At minimum, add a backend-type check at the top of `router_telemetry.py` that returns a clear 501 error: `"KQL telemetry queries not yet implemented for Fabric backend. Use the Eventhouse KQL endpoint directly."` This prevents silent/confusing failures. Full KQL dispatch via `azure-kusto-data` SDK is the proper follow-up.

**Scope:** In scope (Phase 2) — the guard clause (3 lines) is added in Phase 2. Full KQL dispatch is a separate work item.

### Gap 2: Prompt set compatibility with Fabric mode

**Current state:** Prompts are stored in Cosmos DB with scenario-specific containers. Fabric mode doesn't have the same scenario name derivation.

**Where this matters:** Prompt loading in `api/app/routers/config.py` derives scenario from graph name. Fabric ontology ID is not a valid scenario name.

**Recommendation:** Allow explicit `prompt_scenario` in `ConfigApplyRequest` (already exists). Frontend Fabric tab should have a prompt set dropdown identical to the CosmosDB Data Sources tab.

**Scope:** In scope (Phase 5) — add prompt set selector to Fabric tab.

### Gap 3: Graph visualizer GQL response format

**Current state:** `useTopology.ts` expects `{nodes: [{id, label, properties}], edges: [{source, target, label}]}`. Fabric executeQuery API returns tabular data: `{"status": {...}, "result": {"columns": [...], "data": [...]}}` — a flat table of rows, not a node/edge graph.

**Where this matters:** `FabricGraphBackend.get_topology()` must:\n1. Execute multiple GQL MATCH/RETURN queries (one per entity type, plus relationship queries)\n2. Map each entity row to a `TopologyNode` with `id`, `label`, `properties`\n3. Map relationship results to `TopologyEdge` with `source`, `target`, `label`\n4. The entity types and their ID fields depend on the specific ontology schema

**Recommendation:** The mapping logic in `backends/fabric.py` must be thorough. Start with a hard-coded mapping for the known Network Topology ontology (CoreRouter→RouterId, TransportLink→LinkId, etc.), then generalize using ontology definition introspection via the Fabric REST API. Test with actual Fabric ontology output.

**Scope:** In scope (Phase 2) — core implementation concern.

### Gap 7: Ontology schema drift

**Current state (from reference):** The Fabric ontology definition in `provision_ontology.py` may NOT include all relationships defined in the YAML schema file. Known gaps:
- `Service→AggSwitch` and `Service→BaseStation` edges exist in the schema YAML but are **missing from the Fabric ontology** definition

**Where this matters:** GQL queries that traverse missing relationship types will return empty results (not errors). The `get_topology()` implementation must be aware of which edges are actually present.

**Recommendation:** Audit `provision_ontology.py` entity/relationship definitions against the scenario schema YAML before implementation. Document the ontology→schema mapping explicitly. Time-series bindings are **explicitly out of scope** — telemetry data is queried directly via KQL against Eventhouse, not through the ontology graph.

**Scope:** Phase 2 (topology mapping), Phase 3.5 (ontology provisioning) — awareness item.

### Gap 9: UploadBox single-file limitation for Fabric CSV uploads

**Current state:** The `UploadBox` component in `SettingsModal.tsx` accepts a **single file** via `<input type="file">` (no `multiple` attribute). The `handleFile` callback takes one `File`. Fabric Lakehouse/Eventhouse uploads require **multiple CSV files** (e.g., 10+ Dim*.csv for Lakehouse, 2+ for Eventhouse).

**Where this matters:** The Upload tab's Fabric mode (`UploadBox` for "Lakehouse CSVs" and "Eventhouse CSVs") needs multi-file support but the current component can't do this. The `uploadWithSSE()` utility also sends a single file as FormData.

**Recommendation:** Either:
1. Create a new `MultiFileUploadBox` component that accepts `multiple` files, sends them as `FormData` with `files[]` field name, and shows per-file progress within the SSE stream
2. Or extend `UploadBox` with an optional `multiple?: boolean` prop that changes `<input>` to `multiple`, collects all files, and calls `uploadWithSSE` with a modified FormData containing all files

The `uploadWithSSE` utility must also be extended to support `File[]` in addition to single `File`.

**Scope:** Phase 5 — must be resolved before the Fabric Upload tab works.

### Gap 10: `assign_fabric_role.py` not included in provisioning pipeline

**Current state:** The reference implementation requires `assign_fabric_role.py` to grant the Container App's managed identity `Contributor` role on the Fabric workspace. Without this, the deployed Container App cannot authenticate to the Fabric REST API at runtime.

**Where this matters:** Phase 3.5's "Provision All Resources" button runs workspace/lakehouse/eventhouse/ontology creation but does NOT call `assign_fabric_role.py`. After provisioning succeeds, the deployed app still can't query Fabric because the Container App identity has no workspace access.

**Recommendation:** Add `assign_fabric_role.py` as Step 9 in the provisioning pipeline (after ontology creation). Requires `GRAPH_QUERY_API_PRINCIPAL_ID` env var (the Container App's managed identity object ID, populated by `azd up`). If this env var is not set, skip the step with a warning (acceptable for local dev where `DefaultAzureCredential` uses the developer's own identity).

**Scope:** Phase 3.5 — must be included in the provisioning pipeline.

### Gap 11: Graph indexing delay (20-90 minutes) after ontology creation

**Current state:** Reference CONCERNS.md documents that after `provision_ontology.py` creates/updates an ontology, the Fabric GraphModel indexing process takes **20-90 minutes** before GQL queries return data. During this window, `executeQuery` returns empty results or errors.

**Where this matters:** After the one-click provisioning pipeline completes (Phase 3.5), the user clicks "Load Topology" expecting to see the graph. If they do this immediately, they get an empty graph with no explanation why.

**Recommendation:**
1. Add an SSE event at the end of provisioning: `event: warning\ndata: {"message": "Graph indexing in progress. Topology queries may return empty results for 20-90 minutes."}\n\n`
2. The Fabric Setup tab should show a persistent info banner: "Graph indexing may take 20-90 min after ontology creation"
3. `FabricGraphBackend.get_topology()` should detect the "empty but not error" state and return a descriptive `meta.warning` field

**Scope:** Phase 2 (backend warning) + Phase 5 (UI banner).

### Gap 8: `FABRIC_KQL_DB_NAME` vs display name

**Current state:** The reference `populate_fabric_config.py` discovers the KQL database's actual name by calling `GET /workspaces/{id}/kqlDatabases/{db_id}` and extracting `properties.databaseName` — this is the real KQL database name used in Kusto connection strings, and **may differ** from the item's `displayName`. The `FABRIC_KQL_DB_NAME` env var should hold `properties.databaseName`, NOT `displayName`.

**Where this matters:** Using `displayName` instead of `properties.databaseName` in KQL connection strings will cause "database not found" errors.

**Recommendation:** Ensure `populate_fabric_config.py` (and Phase 3.5's config update step) writes `properties.databaseName` to `FABRIC_KQL_DB_NAME`. The existing reference script does this correctly.

**Scope:** Phase 3.5 — correctness item.

### ~~Gap 4~~ → Resolved: AddScenarioModal not adapted for Fabric

**Original gap:** The plan excluded `AddScenarioModal.tsx` from changes, stating "Scenario creation is independent of backend type." This was incorrect — Fabric data (Lakehouse CSVs, Eventhouse CSVs) uses different formats and upload endpoints than CosmosDB (.tar.gz archives).

**Resolution:** AddScenarioModal now adapts upload slots based on `activeBackendType` (see Item 5). `COSMOS_SLOTS` vs `FABRIC_SLOTS` provide different endpoint, accept, and hint configurations. Shared slots (runbooks, tickets, prompts) remain unchanged.

### ~~Gap 5~~ → Resolved: No Fabric provisioning from UI

**Original gap:** Plan said provisioning scripts "handle Fabric resource provisioning which is done manually per requirement 1."

**Resolution:** New Phase 3.5 wraps provisioning scripts as SSE-streamed API endpoints. One-click "Provision Fabric Resources" button on Fabric Setup tab (see Item 3.5 and Decision 7).

### Gap 6: Cosmos DB still required in Fabric mode

**Where this matters:** Even with `GRAPH_BACKEND=fabric`, prompts are stored in Cosmos NoSQL (`prompts` database), runbooks/tickets are in AI Search + Blob Storage, and the `X-Graph` header still drives container routing for these stores. Users may assume "Fabric mode" means no Cosmos dependency — this is incorrect.

**Recommendation:** Document explicitly that Fabric mode replaces **only graph topology data and telemetry** with Fabric resources. Prompts, runbooks, tickets, and scenario metadata remain in Cosmos/AI Search. `COSMOS_NOSQL_ENDPOINT` must still be configured even in Fabric mode. The Fabric Setup tab should show a note: "Prompts and knowledge bases are stored in Cosmos DB / AI Search regardless of graph backend."

**Scope:** In scope (Phase 5) — add info text to Fabric Setup tab.

---

## UX Priority Matrix

| Priority | Enhancement | Item | Effort | Impact |
|----------|------------|------|--------|--------|
| **P0** | Backend dropdown (context-adaptive) | 5 | Small | High — core requirement |
| **P0** | Context-adaptive tab layout (no greyed tabs) | 5 | Small | High — clean UX, better than greyed tabs |
| **P0** | Workspace ID input | 5 | Tiny | High — foundation for Fabric |
| **P0** | Ontology dropdown (from discovery) | 5 | Small | High — requirement 2, 3 |
| **P0** | Eventhouse dropdown (from discovery) | 5 | Small | High — requirement 4 |
| **P0** | Provision Agents with Fabric config | 5 | Medium | High — requirement 6 |
| **P0** | Adaptive AddScenarioModal (CSV slots for Fabric) | 5 | Medium | High — requirement 10 |
| **P0** | Adaptive Upload tab (Lakehouse/Eventhouse CSVs) | 5 | Small | High — requirement 11 |
| **P0** | One-click Fabric provisioning (SSE) | 3.5 | Medium | High — requirement 12 |
| **P1** | Auto-fetch on workspace ID entry | 5a | Tiny | Medium — reduces clicks |
| **P1** | Loading spinner during discovery | 5b | Tiny | Medium — feedback |
| **P1** | Backend dropdown auto-tab-switch | 5c | Tiny | Medium — already built into adaptive layout |
| **P1** | Post-provisioning auto-populate dropdowns | 5d | Tiny | Medium — seamless flow |
| **P1** | Prompt set selector in Fabric Setup tab | 5 | Small | Medium — completeness |
| **P2** | Fabric connection status indicator | 5 | Small | Medium — confidence |
| **P3** | KQL telemetry queries via UI | Gap 1 | Large | Low — agents handle it |

### Implementation Notes

- **P0 items** are core requirements. Must all be in the same PR as Phases 3.5 + 5.
- **P1 items** are small polish (~5 lines each) that should be included in Phase 5 — they're cheap and greatly improve the flow.
- **P2 items** can be separate small PRs after the core Fabric feature lands.
- **P3 items** are separate work streams.
- The old "Backlog: Fabric resource provisioning from UI" is now **P0** via Phase 3.5.

---

## Edge Cases & Validation

### Backend Plumbing (Item 1)

**Invalid GRAPH_BACKEND value:** If env var is set to `"fabric"` but the string enum doesn't match, Python raises `ValueError`. Current pattern: `GraphBackendType(os.getenv("GRAPH_BACKEND", "cosmosdb").lower())`. Adding `"fabric"` to the enum handles this. No special edge case.

**Missing Fabric env vars:** When `GRAPH_BACKEND=fabric` but `FABRIC_WORKSPACE_ID` is empty, the lifespan warning fires. Requests to `/query/graph` will fail with `HTTPException(500, "workspace_id not configured")`. This is acceptable — same as CosmosDB with missing endpoint.

### Fabric Graph Backend (Item 2)

**Fabric API rate limiting:** Fabric executeQuery API returns `429 Too Many Requests` aggressively, especially on lower-SKU capacities (e.g., F4). The `FabricGraphBackend.execute_query()` code above already implements retry with exponential backoff (up to 5 retries, minimum 15s × attempt). This matches the pattern in the reference `test_gql_query.py`.

**Credential expiry:** `DefaultAzureCredential.get_token()` returns tokens valid ~1 hour. The `_get_token()` method calls `get_token()` on every request — `DefaultAzureCredential` handles caching and refresh internally. No manual token management needed.

**GQL query syntax errors:** The Fabric executeQuery API returns `{"status": {"code": "BadRequest", "description": "..."}, "result": null}` for malformed GQL. The backend extracts the error description and returns `{"columns": [], "data": [], "error": "..."}` which the agent will see and retry with corrected syntax.

**Empty ontology:** If the selected ontology has no entities, `get_topology()` returns `{"nodes": [], "edges": []}`. Frontend handles empty graph gracefully (existing behavior).

**Large graph responses:** Fabric ontologies can have thousands of entities. GQL pagination (if supported by Fabric) should be used. If not, cap results at ~5000 nodes to avoid browser memory issues.

### Fabric Discovery (Item 3)

**No Fabric access:** If the service principal/managed identity doesn't have Fabric workspace access, the REST API returns `403`. The endpoint returns `HTTPException(403, "Access denied — check Fabric workspace permissions")`.

**Empty workspace:** If workspace has no ontologies or eventhouses, returns `{"items": [], "workspace_id": "..."}`. Frontend shows empty dropdown — acceptable.

**Invalid workspace ID format:** Fabric API returns `404` for malformed UUIDs. Endpoint propagates as 404.

### Fabric Provisioning API (Item 3.5)

**Capacity not found:** If `capacity_id` is invalid or the user lacks permissions, workspace creation fails at step 1. SSE stream emits `event: error` with a clear message ("Capacity not found or access denied"). Frontend shows error inline.

**Partial provisioning failure:** If provisioning fails mid-pipeline (e.g., Lakehouse created but Eventhouse creation fails), the SSE stream reports which steps succeeded and where it failed. The next provisioning attempt should detect existing resources (idempotency) — the reference scripts' `create_or_find_*` patterns support this.

**Long-running operations:** Fabric workspace and Lakehouse creation use long-running operations (LRO) with `202 Accepted` + operation polling. The `_wait_for_lro()` pattern from the reference scripts handles this with configurable timeout (default 300s). SSE progress events continue streaming during the poll wait.

**CSV file validation:** `upload-lakehouse` and `upload-eventhouse` endpoints should validate that uploaded CSVs match expected table schemas before attempting delta table creation or KQL ingestion. Return clear error if CSV columns don't match.

**Concurrent provisioning:** If two users trigger provisioning simultaneously, Fabric API may reject the second request (workspace name conflict). Surface the Fabric API error message directly.

### Agent Provisioner (Item 4)

**Fabric OpenAPI spec not found:** If `openapi/fabric.yaml` is missing, `_load_openapi_spec()` will raise `FileNotFoundError`. The `OPENAPI_SPEC_MAP` must point to the correct path.

**FabricTool vs OpenApiTool fallback:** If the team later decides to switch to `FabricTool`, the agent provisioner code path is isolated to a single function. The change would be: replace `OpenApiTool(spec=fabric_spec)` with `FabricTool(connection_id=fabric_connection_name)`. No architectural impact.

### Frontend (Item 5)

**Stale localStorage:** If a user's localStorage has `activeBackendType: "fabric"` but the backend doesn't support it (app redeployed without Fabric), the frontend will attempt to show Fabric Setup tab. The Fabric discovery calls will fail gracefully (error state), and the user can switch back to CosmosDB via the dropdown.

**Concurrent backend toggle:** If user rapidly toggles between backends, the last toggle wins (React state batching). No race condition. Tab bar re-renders cleanly because it's driven by `visibleTabs` which is a pure function of `activeBackendType`.

**Workspace ID formatting:** UUIDs are 36 characters. The auto-fetch debounce checks `length === 36` before firing. Partial UUIDs don't trigger unnecessary API calls.

**AddScenarioModal backend mismatch:** If `activeBackendType` changes while AddScenarioModal is open, the slot definitions change. `useEffect` on `open` resets all slots, so re-opening the modal always reflects the current backend. If the modal is already open and backend changes externally (unlikely UX path), the modal should detect the change and reset slots with a warning.

**Multi-file CSV upload in Fabric mode:** The Lakehouse and Eventhouse slots accept multiple CSV files. The upload endpoint receives all files as `FormData` with `files[]` field. If one file fails validation (wrong schema), the endpoint rejects the entire batch — user must fix and retry. Individual file progress is tracked within the SSE stream.

**Tab persistence across backend switch:** When switching from Fabric to CosmosDB, if the active tab was `fabricsetup`, it auto-switches to `datasources`. If the active tab was `scenarios` or `upload` (shared tabs), it stays on that tab. No jarring navigation.

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
- New router `/api/fabric/*` — provisioning + upload endpoints, no conflict with existing
- New OpenAPI spec `fabric.yaml` — separate file, no change to existing specs

### Gradual Adoption

1. **Phase 1-3 can deploy without frontend changes** — backend supports Fabric but UI doesn't expose it. Users can set `GRAPH_BACKEND=fabric` in env var for testing.
2. **Phase 3.5 enables provisioning via API** — can be tested via curl/Postman before UI is ready.
3. **Phase 5 enables full UI** — users can switch backends, provision Fabric resources, and upload data all from the UI. CosmosDB remains the default.
4. **No forced migration** — `GRAPH_BACKEND=cosmosdb` continues to work exactly as before.

### Rollback Plan

- Remove `FABRIC` from `GraphBackendType` enum and delete `backends/fabric.py`, `router_fabric.py`, `fabric_provision.py`, `openapi/fabric.yaml`
- Remove Fabric fields from `ScenarioContext` and `ConfigApplyRequest`
- Revert `SettingsModal.tsx` and `AddScenarioModal.tsx` to pre-Fabric state (remove adaptive slot logic)
- No data cleanup needed — Fabric stores nothing in CosmosDB
- Standalone provisioning scripts (`scripts/fabric/`) remain functional regardless of rollback
- **Feature flag alternative:** Instead of enum, add `FABRIC_ENABLED=true/false` env var that gates the Fabric code paths. Simpler rollback without code removal. Frontend hides the backend dropdown when `FABRIC_ENABLED=false`.
