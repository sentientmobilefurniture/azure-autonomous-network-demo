# V11 UI Revamp + Fabric Experience — Consolidated Working Plan

> **Created:** 2026-02-16
> **Status:** 🔶 In progress (v11fabricprepa.md + v11fabricprepb.md implemented)
> **Depends on:** V11 Fabric Integration (v11fabricv2.md — Phases 0–3, implemented)
> **Assumes:** v11refactor.md has been completed (codebase is cleaner/restructured)
> **Scope:** Fix the broken Fabric UX end-to-end. Backend bug fixes, provision
> pipeline completion, UI restructure (kill SettingsModal, add ConnectionsDrawer),
> and a coherent Fabric lifecycle from connection → provisioning → scenario creation.
> **Sources:** v11ui_logic1.md, v11ui_logic2.md, v11ui_logic3.md (audits),
> v11fabricv2.md (implemented backend), fabric_implementation_references/ (ground truth)

---

## 1. Current State of the World

v11fabricv2.md was implemented. The Fabric backend is wired up:
- `backends/fabric.py` — FabricGQLBackend (execute_query, get_topology) ✅
- `adapters/fabric_config.py` — env var reads + `FABRIC_CONFIGURED` flag ✅
- `backends/__init__.py` — registered as `"fabric-gql"` ✅
- `router_fabric_discovery.py` — 6 discovery endpoints ✅
- `config.py` — per-scenario backend dispatch via `get_scenario_context()` ✅
- `api/routers/fabric_provision.py` — provision pipeline + individual endpoints ✅
- `useFabricDiscovery.ts` — frontend hook ✅
- `SettingsModal.tsx` — Fabric tab (conditional on active scenario) ✅
- `telco-noc-fabric/scenario.yaml` — reference Fabric scenario ✅
- `agent_provisioner.py` — Fabric GQL entries in CONNECTOR_OPENAPI_VARS ✅

**But the experience is broken.** Four bugs in the frontend hook (one was fixed by the
refactor), a chicken-and-egg Fabric tab, an incomplete provision pipeline, and no
coherent UX flow from "I have no Fabric" to "I have a working Fabric scenario."

### What the refactor (v11refactor.md) changed

All 50 refactor items are complete. Every file compiles cleanly (TypeScript 0 errors,
Python 0 errors). Key changes affecting this plan:

| Refactor item | Current state | Impact on this plan |
|---|---|---|
| #7: `<BindingCard>` extracted | `BindingCard.tsx` exists, 5 inline blocks replaced in SettingsModal | ScenarioManagerModal can reuse it |
| #12: Fabric `_get_token()` deduplicated | `acquire_fabric_token()` in `backends/fabric.py`, imported by `router_fabric_discovery.py` | BE-2 uses shared helper |
| #15: Generic `_find_or_create()` | `_find_or_create()` in `fabric_provision.py` (586 lines total now), 4 functions delegate to it | Phase B data-upload steps slot in cleanly |
| #16: SSE log broadcast dedup | `log_broadcaster.py` shared module, both services use it | — |
| #19: SSE provision boilerplate | `sse_provision_stream()` wrapper in `fabric_provision.py` | Phase B's new pipeline steps use it |
| #27: `<ProgressBar>` extracted | `ProgressBar.tsx` exists | Reusable in ConnectionsDrawer provision progress |
| #28: `<ModalShell>` extracted | `ModalShell.tsx` exists | ScenarioManagerModal uses it |
| #29: Provisioning SSE dedup | `triggerProvisioning.ts` exists | ConnectionsDrawer provision button uses it |
| #31: `router_ingest.py` split | `ingest/` package with 7 modules; `router_ingest.py` is 2-line re-export | Upload guard (BE-4) goes into `ingest/graph_ingest.py` |
| #32: SettingsModal split | `settings/` dir with 4 tab components; SettingsModal is 201 lines | ScenarioManagerModal composes from tab pieces |
| #33: Upload orchestration extracted | `useScenarioUpload.ts` exists; AddScenarioModal is 514 lines | Backend chooser integrates with this hook |
| #37: `aclose()` deleted | Dead code removed from `backends/fabric.py` | — |
| #40: Unused Fabric env vars deleted | Only `FABRIC_CONFIGURED`, `FABRIC_WORKSPACE_ID`, `FABRIC_GRAPH_MODEL_ID`, `FABRIC_API_URL`, `FABRIC_SCOPE` remain | ⚠️ Phase B must re-add vars needed by provision pipeline |
| #43: Mock data to JSON | `mock_topology.json` fixture, `mock.py` loads from it | — |
| #44: Context promotion | `savedScenarios`, `activeScenarioRecord`, `refreshScenarios()` in `ScenarioContext.tsx` | Phase C startup is largely done — context has the data |
| #46: Persist config to disk | `_save_config()` with atomic writes; loads from `active_config.json` on startup | Fabric provisioning config writes use this pattern |
| #48: Provisioning concurrency guard | `asyncio.Lock` in `config.py` `apply_config()` | Fabric provisioning respects the same lock pattern |

---

## 2. The Problems

### P1: ~~Four bugs in useFabricDiscovery.ts~~ ✅ Fixed by v11fabricprepa.md

| # | Bug | Status |
|---|-----|--------|
| ~~B1~~ | ~~`checkHealth()` reads `data.status === 'ok'` but backend returns `{configured: bool}`~~ | ✅ Fixed — now checks `data.configured === true` |
| ~~B2~~ | ~~`runProvisionPipeline()` calls `/api/fabric/provision/pipeline` but route is `/api/fabric/provision`~~ | ✅ Fixed — correct URL |
| ~~B3~~ | ~~Stale closure: `provisionState` in both callback body and dep array~~ | ✅ Fixed by refactor |
| ~~B4~~ | ~~Discovery reads `data.items \|\| []` but backend returns flat `list[FabricItem]`~~ | ✅ Fixed — `Array.isArray(data) ? data : []` |
| ~~B5~~ | ~~Discovery endpoints gate on `FABRIC_CONFIGURED` (requires BOTH workspace ID AND graph model ID)~~ | ✅ Fixed — gates on `FABRIC_WORKSPACE_CONNECTED` |

### P2: Fabric tab is invisible until you already have a Fabric scenario

```typescript
isFabricScenario = activeScenarioRecord?.graph_connector === 'fabric-gql'
```

You need Fabric resources to create a Fabric scenario, but you need a Fabric scenario
to see the Fabric Setup tab where you'd provision those resources.

### P3: Provision pipeline creates empty containers only

The `fabric_provision.py` API route creates workspace + lakehouse + eventhouse + ontology
as **empty shells**. It does NOT:
- Upload CSV data to the lakehouse
- Create KQL tables or ingest telemetry into the eventhouse
- Define entity types, relationships, or data bindings in the ontology
- Discover the auto-created Graph Model

The reference implementation (`fabric_implementation_references/scripts/fabric/`) does
ALL of this. The API route is a stub that needs to be completed.

### P4: No backend chooser in AddScenarioModal

Users have no way to choose between Cosmos and Fabric when creating a scenario. The
`graph_connector` is auto-detected from tarball metadata — but Fabric scenarios don't
upload graph tarballs (data goes through Lakehouse provisioning), so there's nothing
to detect from.

### P5: No visibility into connected services

The only health indicator is a small green dot labeled "API" checking `/health`. No way
to see CosmosDB, Blob, AI Search, Foundry, or Fabric status. No connections panel.

### P6: The ⚙ gear is a junk drawer

SettingsModal is split into `settings/` tab components (201 lines shell + 4 tab files)
but it's still behind a gear icon with no discoverability. The `FabricSetupTab.tsx` is
conditionally hidden. Users have to hunt through tabs.

### P7: Startup loading overlay blocks the UI

Full-screen dark overlay "Validating scenario..." for up to 5s. Hostile.

### P8: Provisioning is unconditional

`POST /api/fabric/provision` always creates ALL resources (workspace + lakehouse +
eventhouse + ontology) regardless of what the scenario actually needs. A scenario
using Fabric for graph but CosmosDB for telemetry doesn't need an eventhouse.

---

## 3. The End-to-End Fabric Flow (What Must Exist)

This is the logical lifecycle. Each phase gates on the previous one.

```
PHASE 1: CONNECT
  ├── Option A: User sets FABRIC_WORKSPACE_ID in azure_config.env + redeploy
  ├── Option B: User enters workspace ID in ConnectionsDrawer → POST /api/fabric/connect
  │     → persists to config store → runtime reload (no restart needed)
  ├── Gate: workspace reachable
  └── UI: ConnectionsDrawer shows Fabric as "⚠ Workspace connected"

PHASE 2: DISCOVER
  ├── User opens ConnectionsDrawer → expands Fabric
  ├── App lists what exists: Lakehouses, Eventhouses, Ontologies, Graph Models,
  │   KQL Databases (may be empty — that's fine, shows what needs provisioning)
  ├── Gate: discovery endpoints return resource lists
  └── UI: Shows counts and names for each resource type

PHASE 3: PROVISION (scenario-aware, comprehensive)
  ├── User clicks "Provision Resources" (optionally with an active scenario)
  ├── Pipeline reads scenario.yaml to determine what's needed:
  │     graph: fabric-gql → Lakehouse + Ontology
  │     telemetry: cosmosdb-nosql → skip Eventhouse
  │     telemetry: fabric-kql → Eventhouse + KQL tables
  ├── Pipeline creates resources AND uploads data AND defines schemas:
  │     Lakehouse: create → upload CSVs to OneLake → load into delta tables
  │     Eventhouse: create → discover KQL DB → create tables → ingest CSVs
  │     Ontology: create with FULL definition (entity types, relationships,
  │       data bindings, contextualizations) → Graph Model auto-created
  ├── Pipeline discovers auto-created Graph Model ID → updates config
  ├── Gate: required resources populated, FABRIC_GRAPH_MODEL_ID available
  └── UI: ConnectionsDrawer upgrades to "● Connected ✓"

PHASE 4: CREATE SCENARIO
  ├── User opens AddScenarioModal → selects Fabric backend card
  ├── Card shows live prerequisite checklist (workspace ✓, graph model ✓)
  ├── Graph upload slot greyed out ("Graph data managed via Fabric Lakehouse")
  ├── User uploads: telemetry, runbooks, tickets, prompts normally
  ├── Scenario saved with graph_connector: "fabric-gql"
  ├── Gate: scenario exists with valid connector
  └── UI: Chip shows [telco-noc-fabric · Fabric ▾] with cyan badge
```

### Key correction from the audit documents

The old v11fabricv3.md described a 6-phase flow with 2 manual steps (load data into
Lakehouse via portal, create Graph Model manually). This was based on auditing the
**stub API route** which only creates empty containers. The reference implementation
at `fabric_implementation_references/scripts/fabric/` proves these are automatable:

| Old plan (wrong) | Corrected (per reference scripts) |
|---|---|
| Provision creates empty containers | Provision creates resources + uploads data + defines full ontology |
| Data must be manually loaded into Lakehouse via portal | `provision_lakehouse.py` uploads 10 CSVs via OneLake ADLS Gen2 + loads delta tables |
| Graph Model must be manually created in portal | Auto-created when ontology has data bindings; discovered by `find_graph_model()` |
| `FABRIC_GRAPH_MODEL_ID` must be manually set as env var | Pipeline discovers and writes it to azure_config.env automatically |
| KQL database is not created by provision | Auto-created with Eventhouse; `provision_eventhouse.py` creates tables + ingests data |
| 6 phases, 2 manual | 4 phases, 0 manual |

### Conditional provisioning matrix

| `graph.connector` | `telemetry.connector` | Provisions |
|---|---|---|
| `fabric-gql` | `cosmosdb-nosql` | Workspace + Lakehouse (w/ data) + Ontology (w/ full def) |
| `fabric-gql` | `fabric-kql` | Workspace + Lakehouse + Eventhouse + Ontology |
| `cosmosdb-gremlin` | `fabric-kql` | Workspace + Eventhouse only |
| `cosmosdb-gremlin` | `cosmosdb-nosql` | Nothing — pure Cosmos, no Fabric needed |

---

## 4. Backend Changes Required

### BE-1: Split `FABRIC_CONFIGURED` into two lifecycle stages ✅ _(implemented by v11fabricprepa.md)_

**File:** `graph-query-api/adapters/fabric_config.py`

~~Currently: `FABRIC_CONFIGURED = bool(WORKSPACE_ID and GRAPH_MODEL_ID)`.~~

**Done.** Added `FABRIC_WORKSPACE_CONNECTED`, `FABRIC_QUERY_READY`, kept
`FABRIC_CONFIGURED = FABRIC_QUERY_READY` as backward-compat alias. Also re-added
provisioning constants: `FABRIC_WORKSPACE_NAME`, `FABRIC_LAKEHOUSE_NAME`,
`FABRIC_EVENTHOUSE_NAME`, `FABRIC_ONTOLOGY_NAME`, `FABRIC_CAPACITY_ID`.

### BE-2: Discovery endpoints gate on workspace-only ✅ _(implemented by v11fabricprepa.md)_

**File:** `graph-query-api/router_fabric_discovery.py`

**Done.** `_fabric_get()` now checks `FABRIC_WORKSPACE_CONNECTED` instead of
`FABRIC_CONFIGURED`. Import updated. Error message updated to reference only
`FABRIC_WORKSPACE_ID`.

GQL query execution (`FabricGQLBackend.execute_query()`) keeps gating on `FABRIC_QUERY_READY`.

> **Refactor note:** `acquire_fabric_token()` lives in `backends/fabric.py` and is
> imported by `router_fabric_discovery.py`. The shared helper is already in place.

### BE-3: Richer health endpoint ✅ _(implemented by v11fabricprepb.md)_

**File:** `graph-query-api/router_fabric_discovery.py`

~~Current: `{"configured": bool, "workspace_id": str}`~~

**Done.** Health endpoint now returns 5 fields: `configured`, `workspace_connected`,
`query_ready`, `workspace_id`, `graph_model_id`. Added `FABRIC_GRAPH_MODEL_ID` to
import block. `FABRIC_QUERY_READY` (previously imported but unused) is now wired in.
`ontology_id` was dropped — `FABRIC_ONTOLOGY_ID` doesn't exist in `fabric_config.py`
(only `FABRIC_ONTOLOGY_NAME`); can be added when BE-7 (dynamic config) is implemented.

Three UI states derive from this:
| State | Condition | Display |
|---|---|---|
| Not configured | `workspace_connected === false` | ○ "Not configured" |
| Partially ready | `workspace_connected && !query_ready` | ⚠ "Workspace connected. Graph queries not ready." |
| Connected | `workspace_connected && query_ready` | ● "Connected ✓" |

### BE-4: Upload guard for Fabric scenarios ✅ _(implemented by v11fabricprepa.md)_

**File:** `graph-query-api/ingest/graph_ingest.py`

**Done.** Two guards added:
1. Manifest connector check — if `data_sources.graph.connector == "fabric-gql"`,
   raises `ValueError` (streamed as SSE error event by `sse_upload_response` wrapper).
2. Safety-net `try/except NotImplementedError` around `backend.ingest()` for the
   case where the global `GRAPH_BACKEND` env var forces a Fabric backend.

Both fire before the v11c `invalidate_topology_cache()` call, so no conflict.

### BE-5: `GET /api/services/health` — aggregate service health

**File:** New route in `api/app/routers/` or `graph-query-api/`

Returns grouped status for all configured Azure services:
```json
{
  "services": [
    {"name": "CosmosDB Gremlin", "group": "core", "status": "connected"},
    {"name": "CosmosDB NoSQL", "group": "core", "status": "connected"},
    {"name": "Blob Storage", "group": "core", "status": "connected"},
    {"name": "Azure AI Foundry", "group": "ai", "status": "connected"},
    {"name": "Azure AI Search", "group": "ai", "status": "connected"},
    {"name": "Microsoft Fabric", "group": "optional", "status": "partial",
     "details": "Workspace connected. Graph Model not configured.",
     "sub_status": {
       "workspace": "connected",
       "graph_model": "not_configured",
       "lakehouse": "found",
       "eventhouse": "not_found",
       "ontology": "found"
     }}
  ],
  "summary": {"total": 6, "connected": 5, "partial": 1, "error": 0}
}
```

Cached 30s server-side. Polls real endpoints (Cosmos health, Blob health, etc.).
Fabric uses the improved health endpoint from BE-3.

### BE-6: Add FABRIC_* vars to azure_config.env.template ✅ _(implemented by v11fabricprepa.md)_

**File:** `azure_config.env.template`

**Done.** Added 13 commented-out `FABRIC_*` vars including `FABRIC_API_URL` and
`FABRIC_SCOPE` (which were missing from the original plan but exist in `fabric_config.py`).

### BE-7: Runtime Fabric config via config store

**Files:** `graph-query-api/adapters/fabric_config.py`, new `api/app/routers/fabric_config_api.py`

Currently all Fabric env vars are read once at module import time. This means connecting
a Fabric workspace or updating a Graph Model ID requires a full backend restart. For
in-app workspace setup (BE-8) and post-provisioning Graph Model discovery to take effect
immediately, config must be dynamic.

**Fix:** Store Fabric config in CosmosDB via the existing `DocumentStore` / config store
infrastructure. Read per-request with a short TTL cache (60s), falling back to env vars.

```python
# adapters/fabric_config.py — add dynamic read layer
import functools, time

_fabric_config_cache: dict = {}
_cache_ts: float = 0.0
_CACHE_TTL = 60.0  # seconds

async def get_fabric_config() -> dict:
    """Return current Fabric config. Reads from config store (cached 60s),
    falls back to env vars for anything not in the store."""
    global _fabric_config_cache, _cache_ts
    if time.monotonic() - _cache_ts < _CACHE_TTL and _fabric_config_cache:
        return _fabric_config_cache
    try:
        from config_store import fetch_scenario_config
        stored = await fetch_scenario_config("__fabric__")
        _fabric_config_cache = {**_env_defaults(), **stored}
    except Exception:
        _fabric_config_cache = _env_defaults()
    _cache_ts = time.monotonic()
    return _fabric_config_cache

def invalidate_fabric_cache():
    """Call after writing new config to force a fresh read."""
    global _cache_ts
    _cache_ts = 0.0
```

Discovery endpoints and `FabricGQLBackend` call `await get_fabric_config()` instead
of reading module-level constants. The module-level constants become fallback defaults.

### BE-8: `POST /api/fabric/connect` — in-app workspace connection

**File:** New `api/app/routers/fabric_config_api.py`

Allows the ConnectionsDrawer to connect a Fabric workspace without editing env vars
or restarting the backend.

```python
@router.post("/api/fabric/connect")
async def connect_fabric_workspace(req: FabricConnectRequest):
    """Persist workspace ID to config store. Validates workspace is reachable."""
    # 1. Validate workspace exists (GET /workspaces/{id})
    # 2. Write to config store: {workspace_id, workspace_name, capacity_id}
    # 3. Invalidate Fabric config cache (BE-7)
    # 4. Return {workspace_connected: true, workspace_name: "..."}

class FabricConnectRequest(BaseModel):
    workspace_id: str
    capacity_id: str = ""  # optional — needed for provisioning
```

Also add `PUT /api/fabric/config` for updating any Fabric config value at runtime
(used by the provision pipeline to write `FABRIC_GRAPH_MODEL_ID` after auto-discovery
instead of writing to azure_config.env).

### BE-9: `FabricKQLBackend` — telemetry queries via Eventhouse

**File:** New `graph-query-api/backends/fabric_kql.py`

Implements a telemetry backend that queries Fabric Eventhouse KQL databases via the
Kusto REST API. This enables `telemetry.connector: "fabric-kql"` in scenario.yaml.

```python
class FabricKQLBackend:
    """Telemetry backend for Fabric Eventhouse KQL queries."""

    async def execute_query(self, query: str, **kwargs) -> dict:
        """Execute a KQL query against Eventhouse.
        Endpoint: EVENTHOUSE_QUERY_URI/v1/rest/query
        Body: {"db": kql_db_name, "csl": query}
        Auth: DefaultAzureCredential(scope=FABRIC_SCOPE)
        """
        ...

    async def close(self):
        ...
```

**Registration:**
```python
# backends/__init__.py
from .fabric_kql import FabricKQLBackend
register_backend("fabric-kql", FabricKQLBackend)
```

**Telemetry router dispatch:** Currently `router_telemetry.py` always queries
CosmosDB NoSQL directly. Add connector-aware dispatch (same pattern as graph router):
1. Read `data_sources.telemetry.connector` from scenario config
2. If `fabric-kql` → use `FabricKQLBackend`
3. If `cosmosdb-nosql` → use existing CosmosDB NoSQL path

**Agent integration:** `CONNECTOR_OPENAPI_VARS["fabric"]` already has
`telemetry_query_language_description` set to KQL. The provisioner just needs to
wire the telemetry spec template when the telemetry connector is `fabric-kql`.

### BE-10: Fabric Data Agent discovery and assignment

**File:** New endpoint in `api/app/routers/fabric_config_api.py` or `graph-query-api/router_fabric_discovery.py`

Port the logic from `fabric_implementation_references/scripts/fabric/collect_fabric_agents.py`:
discover Fabric Data Agent artifacts in the workspace and allow assignment to roles.

```python
@router.get("/api/fabric/data-agents")
async def list_fabric_data_agents():
    """Discover Fabric Data Agent items in the workspace.
    Searches for item types: DataAgent, DataAgentDefinition, Agent, AISkill.
    Returns list of {id, display_name, type, description}."""
    ...

@router.post("/api/fabric/data-agents/assign")
async def assign_data_agent(req: DataAgentAssignRequest):
    """Assign a discovered Data Agent to a role (graph or telemetry).
    Writes GRAPH_DATA_AGENT_ID or TELEMETRY_DATA_AGENT_ID to config store."""
    ...

class DataAgentAssignRequest(BaseModel):
    agent_id: str
    role: Literal["graph", "telemetry"]
```

The ConnectionsDrawer's Fabric section shows discovered Data Agents with role
assignment dropdowns.

---

## 5. Provision Pipeline Completion (The Critical Fix)

### The gap

`api/app/routers/fabric_provision.py` (586 lines) creates empty resource
containers. The reference scripts (3 files, ~1700 lines total) create resources **with data**.

The generic `_find_or_create()` helper and `sse_provision_stream()` SSE wrapper are
already in place (refactors #15, #19). The file is lean and the helpers are directly
reusable for extending the pipeline.

The API route's docstring even says "Create Lakehouse + upload CSV data" and "Create
Eventhouse + ingest telemetry" — but neither is implemented. This is the single
biggest fix needed for the Fabric experience to work end-to-end.

### What the reference scripts actually do

**`provision_lakehouse.py`** — Workspace + Lakehouse + Data
1. Find or create workspace (with capacity)
2. Find or create lakehouse
3. Upload 10 CSVs to OneLake via `DataLakeServiceClient` (ADLS Gen2 API)
4. Load each CSV into a managed delta table via Lakehouse Tables API
5. Write `FABRIC_WORKSPACE_ID`, `FABRIC_LAKEHOUSE_ID` to azure_config.env

**`provision_eventhouse.py`** — Eventhouse + KQL DB + Data
1. Find or create eventhouse
2. Discover auto-created KQL database
3. Create 2 KQL tables (`AlertStream`, `LinkTelemetry`) via `.create-merge table`
4. Create CSV ingestion mappings
5. Ingest CSVs via `QueuedIngestClient` (with inline fallback)
6. Write `FABRIC_EVENTHOUSE_ID`, `FABRIC_KQL_DB_ID`, `EVENTHOUSE_QUERY_URI` to env

**`provision_ontology.py`** (935 lines!) — Full Ontology + Graph Model
1. Find or create ontology
2. Build full ontology definition with:
   - 8 entity types (CoreRouter, TransportLink, AggSwitch, BaseStation, etc.)
   - 7 relationship types (connects_to, aggregates_to, backhauls_via, etc.)
   - Static data bindings (entity → Lakehouse table column mappings)
   - Contextualizations (relationship → junction table mappings)
3. PUT the complete ontology definition via Fabric API
4. Wait for indexing (ontology refresh can take minutes)
5. Discover auto-created Graph Model via `find_graph_model()`
6. Write `FABRIC_ONTOLOGY_ID`, `FABRIC_GRAPH_MODEL_ID` to azure_config.env

### The fix

Extend `fabric_provision.py` to port the reference scripts' logic into the SSE-streamed
API endpoints. This is the biggest code change in the plan. The approach:

The generic `_find_or_create()` helper and `sse_provision_stream()` wrapper are already
in place. New data-upload functions slot cleanly into the existing pipeline structure.

1. **Re-add needed Fabric env vars** — Refactor #40 deleted them, but the provision
   pipeline needs: `FABRIC_WORKSPACE_NAME`, `FABRIC_LAKEHOUSE_NAME`,
   `FABRIC_EVENTHOUSE_NAME`, `FABRIC_ONTOLOGY_NAME`. Re-add to `adapters/fabric_config.py`
   with the same defaults as the reference implementation.

2. **Lakehouse step** — After `_find_or_create(... resource_type="Lakehouse" ...)`, add:
   - `_upload_csvs_to_onelake(workspace_id, lakehouse_id)` — ported from reference
   - `_load_delta_tables(workspace_id, lakehouse_id)` — one API call per CSV
   - CSV source: `data/scenarios/telco-noc/data/entities/*.csv` (the Fabric scenario
     reuses `telco-noc`'s entity CSVs — `telco-noc-fabric/data/entities/` does not exist;
     the provision pipeline must resolve to the base scenario's data directory or
     the CSVs must be copied/symlinked into the Fabric scenario)

3. **Eventhouse step** — After `_find_or_create(... resource_type="Eventhouse" ...)`, add:
   - `_discover_kql_database(workspace_id, eventhouse_id)` — auto-created
   - `_create_kql_tables(kql_uri, db_name)` — `.create-merge table` commands
   - `_ingest_kql_data(kql_uri, db_name)` — queued + inline fallback
   - CSV source: `data/scenarios/telco-noc/data/telemetry/*.csv` (same note — Fabric
     scenario has no telemetry CSVs of its own)

4. **Ontology step** — After `_find_or_create(... resource_type="Ontology" ...)`, add:
   - `_build_ontology_definition(workspace_id, lakehouse_id, eventhouse_id)` — ported
   - `_apply_ontology_definition(workspace_id, ontology_id, definition)` — PUT call
   - `_discover_graph_model(workspace_id, ontology_name)` — find auto-created
   - `_update_config(FABRIC_GRAPH_MODEL_ID=graph_model_id)` — write to env

5. **Conditional execution** — Read `scenario_name` from `FabricProvisionRequest`:
   - Load scenario config from config store
   - If `graph.connector === "fabric-gql"` → run Lakehouse + Ontology steps
   - If `telemetry.connector === "fabric-kql"` → run Eventhouse step
   - Always create workspace (it's the container for everything)

6. **Respect provisioning concurrency guard** — Refactor #48 added an `asyncio.Lock`
   to `config.py` for agent provisioning. Fabric provisioning should use its own lock
   (or the same one) to prevent concurrent provision requests from conflicting.

### New dependencies

```toml
# api/pyproject.toml — add:
"azure-storage-file-datalake>=12.14.0"   # OneLake CSV upload
"azure-kusto-ingest>=4.3.0"              # Eventhouse KQL ingestion
```

### SSE progress events (expanded)

The current pipeline streams 4 progress events (workspace 0-15%, lakehouse 15-35%,
eventhouse 35-65%, ontology 65-100%). With data upload, expand to finer granularity:

```
  0-10%   Finding/creating workspace
 10-20%   Finding/creating lakehouse
 20-40%   Uploading CSVs to OneLake (10 files, progress per file)
 40-45%   Loading delta tables
 45-55%   Finding/creating eventhouse (if needed)
 55-65%   Creating KQL tables + ingesting data (if needed)
 65-80%   Creating ontology with full definition
 80-90%   Waiting for ontology indexing
 90-95%   Discovering Graph Model
 95-100%  Writing config + done
```

### Effort estimate

This is the largest single task — porting ~1200 lines of reference script logic into
the async SSE-streamed API endpoint. Estimate: **2-3 days** for a developer familiar
with the reference codebase. The logic is well-understood (reference scripts work);
the challenge is async adaptation + SSE progress integration. The existing
`_find_or_create()` and `sse_provision_stream()` helpers save ~200 lines of
boilerplate vs. writing from scratch.

---

## 6. UI Design

### Overview: What replaces what

```
BEFORE                                AFTER
──────                                ─────
Header:                               Header:
  ◆ Title  [ScenarioChip ▾]  •API ⚙    ◆ Title  [ScenarioChip ▾]  •5/5  🔌

⚙ → SettingsModal (201-line shell)    ScenarioChip dropdown:
  ├─ ScenarioSettingsTab.tsx             ├─ Scenario quick-select
  ├─ DataSourceSettingsTab.tsx           ├─ + New Scenario
  ├─ UploadSettingsTab.tsx               ├─ ✦ Custom mode
  └─ FabricSetupTab.tsx (hidden!)       ├─ ⊞ Manage scenarios… → ScenarioManagerModal
                                         └─ AddScenarioModal (with backend chooser)

                                       🔌 → ConnectionsDrawer (slide-over)
                                         ├─ Service health grid (grouped by role)
                                         ├─ Expandable rows with details
                                         └─ Fabric section (3-state, 5 resource types, provision)

Loading overlay (blocks UI 5s)         Non-blocking startup:
  "Validating scenario..."               Init from localStorage → background validate
```

Available building blocks from the completed refactor:
- `<ModalShell>` — modal chrome wrapper (backdrop, header, close, footer)
- `<ProgressBar>` — reusable progress bar component
- `<BindingCard>` — data-source binding card
- `useClickOutside` — click-outside hook
- `useScenarioUpload` — upload orchestration (state machine, file slots, sequential uploads)
- `triggerProvisioning()` — shared SSE provisioning call
- `savedScenarios` / `activeScenarioRecord` / `refreshScenarios()` — in ScenarioContext
- Split tab components in `settings/` — composable for ScenarioManagerModal

### Change 1: Kill the ⚙ gear — extend the ScenarioChip dropdown

Remove the gear button. Add "⊞ Manage scenarios…" to the ScenarioChip dropdown
as a bottom menu item. Add backend badge to the chip: `[telecom-v3 · Cosmos ▾]`.

**ScenarioChip dropdown:**
```
┌───────────────────────────────────────┐
│  ● telecom-v3        Cosmos   42v    │  ← active
│  ○ fabric-demo       Fabric   18v    │  ← cyan badge
│  ○ edge-test         Cosmos   12v    │
│ ─────────────────────────────────────│
│  ✦ Custom mode                       │
│  + New Scenario                      │
│ ─────────────────────────────────────│
│  ⊞ Manage scenarios…                 │
└───────────────────────────────────────┘
```

### Change 2: Ambient service health + Connections button

Replace `<HealthDot label="API" />` with `<ServiceHealthSummary />`:
- Shows "5/5 Services" with green/amber/red aggregate color
- Polls `GET /api/services/health` every 30s
- Clickable → opens ConnectionsDrawer

Add 🔌 connections button with status dot overlay → also opens ConnectionsDrawer.

### Change 3: ConnectionsDrawer — slide-over panel

Right-edge slide-over (420px). Services grouped by role. Expandable detail rows.

```
┌──────────────────────────┬───────────────────────────────┐
│                          │  CONNECTIONS              ✕  │
│  (main app still         │                              │
│   visible, dimmed)       │  CORE INFRASTRUCTURE         │
│                          │  ● CosmosDB Gremlin    ✓  › │
│                          │  ● CosmosDB NoSQL      ✓  › │
│                          │  ● Blob Storage        ✓  › │
│                          │                              │
│                          │  AI SERVICES                 │
│                          │  ● Azure AI Foundry    ✓  › │
│                          │  ● Azure AI Search     ✓  › │
│                          │                              │
│                          │  GRAPH BACKEND (OPTIONAL)    │
│                          │  ⚠ Microsoft Fabric   ⚠  ⌄ │
│                          │  [ Fabric expanded section ] │
│                          │                              │
│                          │  Last checked: 12s ago  [↻] │
└──────────────────────────┴───────────────────────────────┘
```

### Change 3a: Fabric section in ConnectionsDrawer — 3 states

**State A: Not configured (no FABRIC_WORKSPACE_ID)**
```
│  ○ Microsoft Fabric    —  ⌄                              │
│    ┌────────────────────────────────────────────────────┐ │
│    │ Connect to a Fabric Workspace                     │ │
│    │                                                   │ │
│    │ Workspace ID: [________________________________]  │ │
│    │ Capacity ID:  [________________________________]  │ │
│    │                                                   │ │
│    │ ℹ Find these in Fabric portal under               │ │
│    │   workspace settings → About.                     │ │
│    │                                                   │ │
│    │          [Connect]                                │ │
│    └────────────────────────────────────────────────────┘ │
```

Connecting calls `POST /api/fabric/connect` (BE-8). Config is persisted to the
config store and takes effect immediately via runtime reload (BE-7) — no restart.

**State B: Workspace connected, Graph Model not yet available**
```
│  ⚠ Microsoft Fabric    ⚠  ⌄                              │
│    Workspace: telecom-ws                                  │
│    Status: Workspace connected. Graph queries not ready.  │
│                                                           │
│    ▸ Lakehouses (1)                                       │
│      └─ NetworkTopologyLH                                 │
│    ▸ Eventhouses (0)                                      │
│    ▸ Ontologies (1)                                       │
│      └─ NetworkTopologyOntology                           │
│    ▸ Graph Models (0)        ← this is why it's partial   │
│    ▸ KQL Databases (0)                                    │
│                                                           │
│    Active: telco-noc-fabric                               │
│    Graph: fabric-gql → needs Lakehouse + Ontology         │
│    Telemetry: cosmosdb-nosql → Eventhouse not needed      │
│                                                           │
│    [Provision Required Resources]  [Refresh]              │
```

**State C: Fully connected**
```
│  ● Microsoft Fabric    ✓  ⌄                               │
│    Workspace: telecom-ws                                   │
│    Status: Connected. GQL queries ready.                   │
│                                                            │
│    ▸ Lakehouses (1)                                        │
│      └─ NetworkTopologyLH                                  │
│    ▸ Eventhouses (1)                                       │
│      └─ NetworkTelemetryEH                                 │
│    ▸ Ontologies (1)                                        │
│      └─ NetworkTopologyOntology                            │
│    ▸ Graph Models (1)                                      │
│      └─ telco-noc-fabric-topology                          │
│    ▸ KQL Databases (1)                                     │
│      └─ NetworkTelemetryKQL                                │
│                                                            │
│    ▸ Data Agents (2)                                       │
│      └─ GraphDataAgent     [role: graph     ▾]             │
│      └─ TelemetryDataAgent [role: telemetry ▾]             │
│                                                            │
│    [Provision Resources]  [Refresh]                        │
```

**Key difference from old plan:** Shows ALL 5 resource types plus Data Agents (old plan only showed
ontologies + eventhouses). Graph Models shown as workspace-level items, NOT nested under ontologies.
Data Agents are discoverable and assignable to roles directly from the drawer.

### Change 4: ScenarioManagerModal (replaces SettingsModal)

SettingsModal is already split into `settings/` tab components:
`ScenarioSettingsTab.tsx`, `DataSourceSettingsTab.tsx`, `UploadSettingsTab.tsx`,
`FabricSetupTab.tsx`. The shell is 201 lines. ScenarioManagerModal is built by
**composing the existing tab pieces** + `<ModalShell>` wrapper.

Simplified from 4 tabs to 2 (`Scenarios | Upload`). Kill DataSourceSettingsTab (inline
bindings on scenario rows via `<BindingCard>`). Kill FabricSetupTab (moved to
ConnectionsDrawer).

Fabric-aware scenario rows:
```
│ ○ telco-noc-fabric      Fabric │ 18v  8p │ ⋮   │
│   Graph: fabric-gql (Fabric Lakehouse)            │
│   Telemetry: cosmosdb-nosql (CosmosDB)            │
│                                                    │
│   [Re-provision Agents]  [Re-upload data ▾]        │
│                          ├─ Telemetry              │  ← Graph hidden
│                          ├─ Runbooks               │     for Fabric
│                          ├─ Tickets                │
│                          └─ Prompts                │
│   [Re-provision Fabric Resources]                  │  ← Fabric-specific
```

For Cosmos scenarios, the "Graph" option appears in the re-upload dropdown normally.

### Change 5: Backend chooser in AddScenarioModal

Add "Where should graph data live?" selector before the upload slots.

Upload orchestration is in `useScenarioUpload.ts` (514-line modal, down from 699).
The backend chooser state (`selectedBackend`) integrates with this hook, which already
manages upload state, file slots, and sequential uploads.

```
┌──────────────────────────────────────────────────────┐
│  WHERE SHOULD GRAPH DATA LIVE?                       │
│                                                      │
│  ┌──────────────────────────┐  ┌───────────────────┐│
│  │  Azure CosmosDB          │  │  Microsoft Fabric ││
│  │  Gremlin graph database  │  │  GraphQL endpoint ││
│  │  ────────────────────    │  │  ────────────────  ││
│  │  ✓ Default option        │  │  Prerequisites:   ││
│  │  ✓ Fully managed via     │  │  ✓ Workspace      ││
│  │    tarball upload        │  │  ✓ Graph Model     ││
│  │                          │  │                    ││
│  │  [● Selected]            │  │  [○ Select]        ││
│  └──────────────────────────┘  └───────────────────┘│
│                                                      │
│  ℹ Not sure? Use CosmosDB — it's the default and     │
│    requires no additional setup.                      │
└──────────────────────────────────────────────────────┘
```

Fabric card disabled when `query_ready === false`. Shows live prerequisite checklist.
When Fabric selected: graph upload slot greyed out, shows "Graph data managed via
Fabric Lakehouse."

### Change 6: Non-blocking startup

`ScenarioContext.tsx` already has `savedScenarios`, `activeScenarioRecord`,
`scenariosLoading`, and `refreshScenarios()`. The init-from-localStorage and
background-validation patterns are implemented. What remains is removing the
blocking overlay and adding the skeleton chip + crossfade.

- Skeleton chip while `scenariosLoading` (from context)
- If persisted scenario was deleted → crossfade to null
- Remove the full-screen dark overlay entirely

### Change 7: Interactive EmptyState

Replace passive emoji steps with live onboarding checklist reflecting real state:
API connected ✓, N scenarios available ✓, select scenario ○, agents provisioned ○.
Inline scenario picker + CTA button.

---

## 7. Frontend Changes Inventory

### In `useFabricDiscovery.ts` (hook — bug fixes + expansion)

| # | Change | Detail |
|---|--------|--------|
| FE-1 | ~~Fix B1: health check~~ | ✅ **Done (v11fabricprepa)** — `data.configured === true` (interim fix against current backend; will update to `data.workspace_connected` after BE-3) |
| FE-2 | ~~Fix B2: provision URL~~ | ✅ **Done (v11fabricprepa)** — `/api/fabric/provision` |
| FE-3 | ~~Fix B3: stale closure~~ | **Already fixed by refactor** — replaced with `receivedTerminalEvent` flag |
| FE-4 | ~~Fix B4: discovery parsing~~ | ✅ **Done (v11fabricprepa)** — `Array.isArray(data) ? data : []` in all 3 fetch functions |
| FE-5 | ~~Add `fetchLakehouses()`~~ | ✅ **Done (v11fabricprepb)** — `lakehouses` state + `fetchLakehouses()` added |
| FE-6 | ~~Add `fetchKqlDatabases()`~~ | ✅ **Done (v11fabricprepb)** — `kqlDatabases` state + `fetchKqlDatabases()` added |
| FE-7 | ~~Update `fetchAll()`~~ | ✅ **Done (v11fabricprepb)** — includes lakehouses + KQL databases in `Promise.all` |

### New components

| Component | Size est. | Description |
|-----------|-----------|-------------|
| `ConnectionsDrawer.tsx` | ~320 lines | Slide-over with grouped services + Fabric section (workspace setup UI + Data Agent section). Uses `<ModalShell>`, `<ProgressBar>`. |
| `ServiceHealthSummary.tsx` | ~60 lines | "N/M Services" ambient indicator in header |
| `ScenarioManagerModal.tsx` | ~400 lines | Composed from existing `settings/` tab components + `<ModalShell>` + `<BindingCard>` |

### Modified components

| Component | Changes |
|-----------|---------|
| `Header.tsx` | ~~Remove ⚙ gear~~ ✅ Done (v11d) — add ServiceHealthSummary + 🔌 button. Header is now 43 lines with AgentBar. |
| `ScenarioChip.tsx` | ~~Add "⊞ Manage" action~~ ✅ Done (v11fabricprepb), ~~backend badge~~ ✅ Done (v11d). Remaining: skeleton state. Uses `useClickOutside`. |
| `AddScenarioModal.tsx` (514 lines) | Add backend chooser cards, grey out graph upload. Integrates with `useScenarioUpload`. |
| `EmptyState.tsx` | Replace passive text with interactive checklist |
| `ScenarioContext.tsx` | Has `savedScenarios`/`scenariosLoading`/`activeScenarioRecord`. Remaining: crossfade support. |
| `App.tsx` | Remove `!scenarioReady` overlay (L90-109), add crossfade + slim banner. `resetInvestigation()` already wired. |

### Deleted

| Component | Reason |
|-----------|--------|
| `SettingsModal.tsx` | Replaced by ScenarioManagerModal + ConnectionsDrawer |

---

## 8. Implementation Phases

### Phase A: Bug fixes + backend config (unblocks everything)

**Priority: CRITICAL — do first**

| Task | Files | Effort |
|------|-------|--------|
| A1: Fix 4 remaining bugs in useFabricDiscovery.ts (B1, B2, B4, B5) | `useFabricDiscovery.ts` | ✅ Done (v11fabricprepa) |
| A2: Split FABRIC_CONFIGURED (BE-1) + re-add needed env vars | `adapters/fabric_config.py` | ✅ Done (v11fabricprepa) |
| A3: Discovery gates on workspace-only (BE-2) | `router_fabric_discovery.py` | ✅ Done (v11fabricprepa) |
| A4: Richer health endpoint (BE-3) | `router_fabric_discovery.py` | ✅ Done (v11fabricprepb) |
| A5: Upload guard for Fabric scenarios (BE-4) | `ingest/graph_ingest.py` | ✅ Done (v11fabricprepa) |
| A6: Add FABRIC_* to env template (BE-6) | `azure_config.env.template` | ✅ Done (v11fabricprepa) |

**After Phase A:** ✅ **All 6 tasks done** (v11fabricprepa + v11fabricprepb).

### Phase B: Provision pipeline completion

**Priority: HIGH — the biggest Fabric-specific fix**

| Task | Files | Effort |
|------|-------|--------|
| B0: Re-add needed Fabric env vars deleted by refactor #40 | `adapters/fabric_config.py` | ✅ Done (v11fabricprepa) |
| B1: Lakehouse data upload (CSV → OneLake → delta tables) | `fabric_provision.py` | Medium (1 day) |
| B2: Eventhouse KQL table creation + data ingest | `fabric_provision.py` | Medium (1 day) |
| B3: Ontology full definition (8 entities, 7 rels, bindings) | `fabric_provision.py` | High (1 day) |
| B4: Graph Model auto-discovery + config write | `fabric_provision.py` | Low (2hr) |
| B5: Conditional execution (read scenario config, skip unneeded resources) | `fabric_provision.py` | Medium (3hr) |
| B6: Add azure-storage-file-datalake + azure-kusto-ingest deps | `api/pyproject.toml` | ✅ Done (v11fabricprepa) |
| B7: Add provisioning concurrency lock (or reuse refactor #48's pattern) | `fabric_provision.py` | ✅ Done (v11fabricprepb) — `_fabric_provision_lock` with fast-reject + lock inside `stream()` generator |

**After Phase B:** Provision pipeline creates resources WITH data. Ontology has full
definition. Graph Model is auto-created and discovered. `FABRIC_GRAPH_MODEL_ID` is
set automatically. The end-to-end Fabric flow works. ~3 days total.

The `_find_or_create()` helper with its `list_endpoint`, `type_filter`, and
`fallback_endpoint` parameters already handles all the Fabric API endpoint variations.
The `sse_provision_stream()` wrapper handles SSE error/completion boilerplate.

### Phase C: Startup + navigation restructure

**Priority: MEDIUM — independent of Fabric, improves overall UX**

| Task | Files | Effort |
|------|-------|--------|
| C1: Non-blocking startup (remove overlay, add crossfade) | `App.tsx` | Low (1hr) — context already has savedScenarios/activeScenarioRecord |
| C2: Skeleton chip + crossfade | `ScenarioChip.tsx` | Low (1hr) |
| C3: Add services health endpoint (BE-5) | New router | Medium (3hr) |
| C4: Create ConnectionsDrawer | New `ConnectionsDrawer.tsx` | Medium (4hr) — uses `<ModalShell>`, `<ProgressBar>`, `triggerProvisioning()` |
| C5: Create ServiceHealthSummary | New `ServiceHealthSummary.tsx` | Low (1hr) |
| C6: Update Header (~~remove gear~~ ✅ v11d, add health + connections) | `Header.tsx` | Low (1hr) — Header now 43 lines, gear already gone, AgentBar in place |
| C7: ~~Extend ScenarioChip dropdown (add ⊞ Manage, backend badge)~~ | `ScenarioChip.tsx` | ✅ Done — "⊞ Manage" added (v11fabricprepb), backend badge added (v11d). Remaining: skeleton state only. |

**After Phase C:** Clean header. Ambient service health. ConnectionsDrawer with
Fabric 3-state display and all 5 resource types. ~1.5 days total (reduced from 2
due to refactor pre-work).

### Phase D: Scenario creation flow

**Priority: MEDIUM — completes the Fabric scenario creation path**

| Task | Files | Effort |
|------|-------|--------|
| D1: ScenarioManagerModal (compose from tab pieces) | New `ScenarioManagerModal.tsx` | Medium (3hr) — uses `<ModalShell>`, `<BindingCard>`, existing tab components |
| D2: Backend chooser in AddScenarioModal | `AddScenarioModal.tsx` (514 lines) | Medium (2hr) — integrates with `useScenarioUpload` |
| D3: Grey out graph upload for Fabric scenarios | `AddScenarioModal.tsx` / `useScenarioUpload.ts` | Low (1hr) |
| D4: Hide Graph from re-upload dropdown for Fabric scenarios | `ScenarioManagerModal.tsx` | Low (30min) |
| D5: Add "Re-provision Fabric Resources" button for Fabric scenarios | `ScenarioManagerModal.tsx` | Low (1hr) — uses `triggerProvisioning()` |
| D6: Interactive EmptyState | `EmptyState.tsx` | Medium (2hr) |

**After Phase D:** Full scenario lifecycle works for both Cosmos and Fabric. ~1.5 days
(reduced from 1.5 — no change, but individual tasks are cleaner).

### Phase E: Polish + cleanup

| Task | Files | Effort |
|------|-------|--------|
| E1: Modal/panel animations (framer-motion) | All drawers/modals | Low (2hr) |
| E2: Toast notification system | New utility | Medium (2hr) |
| E3: Delete SettingsModal (201-line shell) + settings/ tab files + cleanup imports | `SettingsModal.tsx`, `settings/*.tsx` | Low (1hr) |
| E4: Accessibility (focus trap, aria-live, keyboard nav) | All modals/drawers | Medium (3hr) |
| E5: Update architecture docs | `frontend-architecture.md` etc. | Low (1hr) |

### Phase F: Full Fabric feature parity (previously deferred)

**Priority: MEDIUM — completes the Fabric story. No deferments.**

| Task | Files | Effort |
|------|-------|--------|
| F1: Runtime Fabric config via config store (BE-7) | `adapters/fabric_config.py`, config store | Medium (4hr) |
| F2: `POST /api/fabric/connect` endpoint (BE-8) | New `fabric_config_api.py` | Medium (3hr) |
| F3: Workspace setup UI in ConnectionsDrawer State A | `ConnectionsDrawer.tsx` | Medium (2hr) |
| F4: `FabricKQLBackend` for telemetry (BE-9) | New `backends/fabric_kql.py` | Medium (1 day) |
| F5: Telemetry router dispatch by connector type | `router_telemetry.py` | Medium (3hr) |
| F6: KQL telemetry agent integration (provisioner update) | `agent_provisioner.py` | Low (1hr) |
| F7: Fabric Data Agent discovery endpoint (BE-10) | `fabric_config_api.py` or `router_fabric_discovery.py` | Medium (3hr) |
| F8: Data Agent UI in ConnectionsDrawer (list + role assignment) | `ConnectionsDrawer.tsx` | Medium (2hr) |
| F9: Update provision pipeline to write config to store (not env file) | `fabric_provision.py` | Low (1hr) — uses `PUT /api/fabric/config` from BE-8 |

**After Phase F:** Complete Fabric integration. In-app workspace setup, KQL telemetry
queries, runtime config reload, and Data Agent management — all without restart.
~3 days total.

---

## 9. User Flows

### "I want to set up Fabric" (corrected)

```
1. Click 🔌 Connections → expand Fabric
2. See "Not connected" → enter Workspace ID + Capacity ID → click [Connect]
   → POST /api/fabric/connect validates workspace → config persisted → no restart
3. See: "⚠ Workspace connected. Graph queries not ready."
4. See empty resource inventory: Lakehouses (0), Ontologies (0), etc.
5. Select or create a scenario with fabric-gql connector
6. Click "Provision Required Resources"
   → Pipeline creates Lakehouse + uploads CSVs + creates delta tables
   → Pipeline creates Ontology with full definition
   → Graph Model auto-created, ID written to config store (runtime update)
7. Connections now shows: "● Connected ✓" with all resources populated
8. Data Agents section shows discovered agents with role assignment
9. Ready to investigate — GQL queries work
```

Alternative path: set FABRIC_WORKSPACE_ID in azure_config.env + redeploy. Start at step 3.

### "I want to create a Fabric scenario" (corrected)

```
1. Prerequisite: Fabric shows "● Connected ✓" in ConnectionsDrawer
2. Click [ScenarioChip ▾] → "+ New Scenario"
3. "Where should graph data live?" → select Fabric card
   Card shows: ✓ All prerequisites met
4. Graph upload slot greyed out — "Graph data managed via Fabric Lakehouse"
5. Upload telemetry, runbooks, tickets, prompts normally
6. Scenario saved with graph_connector: "fabric-gql"
7. Chip shows [telco-noc-fabric · Fabric ▾] with cyan badge
```

### "I want to see what's connected" (new)

```
1. Glance at header: "5/5 Services" (green) — all good
   — OR — "4/5 Services" (amber) — something's off
2. Click 🔌 or the health summary → ConnectionsDrawer slides open
3. Services grouped: Core (Cosmos Gremlin ✓, Cosmos NoSQL ✓, Blob ✓),
   AI (Foundry ✓, Search ✓), Optional (Fabric ⚠)
4. Expand Fabric → see detailed resource inventory
5. Close drawer, continue investigating
```

---

## 10. Edge Cases

### Workspace connected but Graph Model not yet available

The most common intermediate state. A user who just provisioned resources
but the ontology indexing hasn't completed yet, or who hasn't run provisioning.

- ConnectionsDrawer: "⚠ Workspace connected. Graph queries not ready."
- Discovery endpoints work — user can see lakehouses, ontologies, etc.
- Provisioning works — user can create resources
- AddScenarioModal: Fabric card disabled with checklist showing what's missing
- Existing Cosmos scenarios completely unaffected

### User tries to upload graph data to a Fabric scenario

- `POST /query/upload/graph` checks scenario's graph_connector
- Returns HTTP 400: "This scenario uses Fabric for graph data. Graph topology
  is managed via the Fabric provisioning pipeline."
- UI shows toast with this message
- Telemetry, runbooks, tickets, prompts uploads still work normally

### fabric-gql graph + cosmosdb-nosql telemetry (primary Fabric pattern)

The `telco-noc-fabric` scenario. Provisioning creates Lakehouse + Ontology,
skips Eventhouse. Upload flow: graph slot disabled, telemetry goes to CosmosDB.

### Fabric env vars not set at all

- `/api/services/health` returns Fabric as `"not_configured"` in optional group
- ConnectionsDrawer shows Fabric greyed out with setup hint
- Fabric card disabled in AddScenarioModal
- Ambient health shows "5/5 Services" — Fabric doesn't count when not configured
- Pure CosmosDB experience, zero Fabric UI surface

### Mixed deployment (Cosmos + Fabric both configured)

- Both backends active simultaneously via per-request dispatch
- ConnectionsDrawer shows all services healthy
- Backend chooser in AddScenarioModal shows both options
- Users switch between Cosmos and Fabric scenarios like any two scenarios

### Persisted scenario was deleted in backend

- App starts with persisted scenario from localStorage (looks normal)
- Background validation detects missing → crossfade to null
- No dark overlay, no spinner — smooth transition to EmptyState

### Service degrades during investigation

- Ambient "5/5 Services" updates to "4/5 Services" (amber) on next 30s poll
- User notices color/count change without interruption
- Click to open ConnectionsDrawer → see which service is down
- No popup, no modal — ambient awareness only

### fabric-gql graph + fabric-kql telemetry (full Fabric scenario)

A scenario with both graph and telemetry on Fabric. Provisioning creates all
resources: Workspace + Lakehouse + Eventhouse + Ontology. Telemetry queries
go through `FabricKQLBackend` instead of CosmosDB NoSQL. The telemetry agent
gets a KQL language description in its OpenAPI spec.

### Dynamic Fabric config works at runtime

Fabric config (workspace ID, graph model ID, etc.) is stored in the config store
and read per-request with a 60s TTL cache. Changes via `POST /api/fabric/connect`
or the provision pipeline's auto-discovery take effect without restart. Manual env
var changes still work as fallback defaults but are overridden by config store values.

---

## 11. File Change Inventory

> **Codebase state after refactor:** SettingsModal is 201 lines (shell) with 4 tab
> files in `settings/`. AddScenarioModal is 514 lines with `useScenarioUpload.ts`
> extracted. `router_ingest.py` is a 2-line re-export; actual code in `ingest/`
> package (7 modules). `fabric_provision.py` is 586 lines with generic
> `_find_or_create()` and `sse_provision_stream()`. Shared components exist:
> `ModalShell`, `ProgressBar`, `BindingCard`, `useClickOutside`,
> `triggerProvisioning`, `useScenarioUpload`. ScenarioContext has
> `savedScenarios`/`activeScenarioRecord`/`refreshScenarios()`. Config persists to
> `active_config.json` with atomic writes.

### New Files (6)

| File | Phase | Size est. |
|------|-------|-----------|
| `frontend/src/components/ConnectionsDrawer.tsx` | C+F | ~320 lines (workspace setup UI + Data Agent section) |
| `frontend/src/components/ServiceHealthSummary.tsx` | C | ~60 lines |
| `frontend/src/components/ScenarioManagerModal.tsx` | D | ~400 lines |
| Backend services health endpoint (location TBD) | C | ~80 lines |
| `graph-query-api/backends/fabric_kql.py` | F | ~150 lines |
| `api/app/routers/fabric_config_api.py` | F | ~120 lines |

### Heavily Modified (2)

| File | Phase | Change |
|------|-------|--------|
| `api/app/routers/fabric_provision.py` (597 lines) | B | +~800 lines (data upload, ontology def, graph model discovery, conditional execution). Uses existing `_find_or_create()` and `sse_provision_stream()`. Concurrency lock ✅ Done (v11fabricprepb). |
| `adapters/fabric_config.py` | ~~A+B~~+F | ~~Split FABRIC_CONFIGURED + re-add env vars~~ ✅ Done (v11fabricprepa) + add dynamic config layer (Phase F) |

### Medium Edits (5)

| File | Phase | Change |
|------|-------|--------|
| `AddScenarioModal.tsx` (514 lines) | D | +backend chooser cards, integration with `useScenarioUpload` hook |
| `Header.tsx` | C | ~~Remove gear~~ ✅ Done (v11d). Add ServiceHealthSummary + connections button. Header now 43 lines with AgentBar. |
| `ScenarioChip.tsx` | C | ~~Add manage action~~ ✅ Done (v11fabricprepb), ~~badge~~ ✅ Done (v11d). Remaining: skeleton state only. |
| `App.tsx` | C | Remove overlay, add crossfade + slim loading banner |
| `router_telemetry.py` | F | Connector-aware dispatch (cosmosdb-nosql vs fabric-kql) |

### Small Edits (7)

| File | Phase | Change |
|------|-------|--------|
| `useFabricDiscovery.ts` | ~~A~~ | ~~5 bug fixes~~ ✅ Done (v11fabricprepa) + ~~2 new fetch methods~~ ✅ Done (v11fabricprepb) |
| `router_fabric_discovery.py` | ~~A~~+F | ~~Gate change~~ ✅ Done (v11fabricprepa) + ~~richer health~~ ✅ Done (v11fabricprepb) + data agent discovery |
| `ingest/graph_ingest.py` | ~~A~~ | ~~Upload guard for Fabric scenarios~~ ✅ Done (v11fabricprepa) |
| `azure_config.env.template` | ~~A~~ | ~~Add FABRIC_* vars~~ ✅ Done (v11fabricprepa) |
| `EmptyState.tsx` | D | Interactive checklist |
| `backends/__init__.py` | F | Register `fabric-kql` backend |
| `agent_provisioner.py` | F | KQL telemetry spec wiring for fabric-kql connector |

### Deleted

| File | Phase | Reason |
|------|-------|--------|
| `SettingsModal.tsx` (201-line shell) | E | Replaced by ScenarioManagerModal |
| `settings/*.tsx` (4 tab files) | E | Functionality moved to ScenarioManagerModal + ConnectionsDrawer |

---

## 12. Summary: Does the Fabric Experience Make Sense End-to-End?

**After this plan: Yes.** The flow is:

1. **CONNECT** — Enter workspace ID in ConnectionsDrawer (or set env var) → partial connection visible
2. **DISCOVER** — Expand Fabric → see all 5 resource types (works before Graph Model exists)
3. **PROVISION** — Scenario-aware button → creates resources WITH data → ontology auto-creates
   Graph Model → pipeline discovers it → config updated → Fabric upgrades to "Connected ✓"
4. **CREATE SCENARIO** — Backend chooser → Fabric card with live prereqs → grey out graph
   upload → save with fabric-gql → cyan badge

No manual steps. No portal visits. No hand-editing env vars after initial workspace setup.
In-app workspace connection, KQL telemetry, runtime config, and Data Agent management
are all included — nothing deferred.






