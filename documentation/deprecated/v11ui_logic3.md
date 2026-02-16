# V11 UI Revamp — Fabric Flow Coherence Audit

> **Created:** 2026-02-16
> **Scope:** Final coherence audit of `v11fabricUIRevamp.md` against the required
> logical flow: create connection → see workspace → discover resources → upload data
> → conditional deployment. Incorporates findings from `v11ui_logic1.md` (resource
> model), `v11ui_logic2.md` (gaps), and direct code inspection.
> **Verdict:** The document describes a plausible Fabric UX but **omits the staged
> lifecycle** that makes the experience coherent. The flow from "I have no Fabric"
> to "I have a working Fabric scenario" requires 6 distinct phases, and the document
> collapses them into 2 (provision → create scenario). Five bugs exist in the
> frontend hook (not 3), and conditional provisioning is absent from both the UI
> plan and the backend. This audit prescribes the exact corrections needed.

---

## 1. The Required Logical Flow

This is the end-to-end lifecycle a user must traverse. Each phase has a gate — you
can't proceed until the previous phase's gate is passed.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ PHASE 1: CONNECT                                                           │
│ Gate: FABRIC_WORKSPACE_ID set → workspace reachable                        │
│ How:  Env var at deploy time (v11). Future: UI input in ConnectionsDrawer. │
│ UI:   ConnectionsDrawer shows Fabric row as "Connected (partial)"          │
├─────────────────────────────────────────────────────────────────────────────┤
│ PHASE 2: DISCOVER                                                          │
│ Gate: Discovery endpoints return resource lists                            │
│ How:  Auto — open ConnectionsDrawer, expand Fabric                         │
│ UI:   Shows: Lakehouses (N), Eventhouses (N), Ontologies (N),              │
│              Graph Models (N), KQL Databases (N)                           │
├─────────────────────────────────────────────────────────────────────────────┤
│ PHASE 3: PROVISION (optional — resources may already exist)                │
│ Gate: Required resources exist (empty containers)                          │
│ How:  "Provision Resources" button — CONDITIONAL on scenario needs         │
│ UI:   Shows which resources will be created, which skipped                 │
├─────────────────────────────────────────────────────────────────────────────┤
│ PHASE 4: LOAD DATA (manual — outside app in v11)                           │
│ Gate: Lakehouse has CSV data (graph entities + edges)                       │
│ How:  Fabric portal / OneLake / future API upload                          │
│ UI:   ConnectionsDrawer shows lakehouse with data status                   │
├─────────────────────────────────────────────────────────────────────────────┤
│ PHASE 5: GRAPH MODEL (manual — outside app in v11)                         │
│ Gate: FABRIC_GRAPH_MODEL_ID set → GQL queries work                         │
│ How:  Create Graph Model in Fabric portal, set env var                     │
│ UI:   ConnectionsDrawer status upgrades to "Connected ✓"                   │
├─────────────────────────────────────────────────────────────────────────────┤
│ PHASE 6: CREATE SCENARIO                                                   │
│ Gate: Scenario saved with graph_connector: "fabric-gql"                    │
│ How:  AddScenarioModal → select Fabric backend → upload non-graph data     │
│ UI:   Scenario chip shows [name · Fabric ▾] with cyan badge               │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Key insight: the document only describes Phases 3 and 6.** Phases 1, 2, 4, 5 are
missing or hand-waved. This makes the experience feel like a magic leap from "not
configured" to "working Fabric scenario" — which is not what happens.

---

## 2. What `v11fabricUIRevamp.md` Gets Right

| Area | Assessment |
|------|------------|
| Fabric placed under "Graph Backend (Optional)" in service grouping | ✓ Correct |
| Workspace shown as root entity in ConnectionsDrawer | ✓ Correct |
| Bug B1-B3 correctly identified | ✓ Confirmed in code |
| Fabric card greyed out when not configured in AddScenarioModal | ✓ Correct |
| `graph_connector` saved via `saveScenarioMeta()` | ✓ Matches backend |
| Fabric card Fabric card text: "Requires Fabric workspace setup" | ✓ Directionally correct |
| "Not configured" state with env var hint | ✓ Present (but incomplete) |
| Individual provision endpoints for lakehouse/eventhouse/ontology | ✓ Exist in backend |

---

## 3. What `v11fabricUIRevamp.md` Gets Wrong or Omits

### Issue 1: No connection setup flow (Phase 1 missing)

**Document says (Change 4, unconfigured state):**
```
│  ○ Microsoft Fabric    —  ⌄ │
│    Not configured.           │
│    Set FABRIC_WORKSPACE_ID   │
│    and FABRIC_GRAPH_MODEL_ID │
│    env vars.                 │
```

**Problem:** "Set env vars" is a deployment instruction, not a UX flow. The user is
staring at the ConnectionsDrawer, and the only guidance is "go edit deployment config."
There's no in-app path from unconfigured to connected.

**What should exist:** A workspace ID input within the ConnectionsDrawer for the
unconfigured state:

```
│  ○ Microsoft Fabric    —  ⌄                     │
│    ┌──────────────────────────────────────────┐  │
│    │ Connect to a Fabric Workspace            │  │
│    │                                          │  │
│    │ Workspace ID: [________________________] │  │
│    │                                          │  │
│    │ ℹ Find this in Fabric portal under       │  │
│    │   workspace settings → About.            │  │
│    │                                          │  │
│    │          [Connect]                       │  │
│    └──────────────────────────────────────────┘  │
```

**For v11, this is optional.** Acceptable to document the env-var path and defer UI
setup to v12. But the document must acknowledge the gap explicitly — currently it
treats this as self-evident.

**Backend impact:** If implemented, needs `POST /api/fabric/connect` or `PUT /api/fabric/config`
that persists workspace ID to config store and dynamically updates `FABRIC_WORKSPACE_CONNECTED`.
See Issue 7 for the config reload problem.

### Issue 2: Lakehouses completely missing from ConnectionsDrawer

**Document wireframe shows:** Ontologies + Eventhouses.

**Missing:** Lakehouses, Graph Models, KQL Databases.

The backend has discovery endpoints for all five resource types:
- `GET /query/fabric/ontologies` ✓ (shown in wireframe)
- `GET /query/fabric/lakehouses` ✗ (never called, never shown)
- `GET /query/fabric/eventhouses` ✓ (shown in wireframe)
- `GET /query/fabric/ontologies/{id}/models` → actually lists workspace-level graph models
- `GET /query/fabric/kql-databases` ✗ (never called, never shown)

Lakehouse is the **most important** Fabric resource for the data flow — it's where
graph entity CSVs live. Omitting it from the UI hides the primary data store.

**Fix:** Show all five resource types in the Fabric expanded section:

```
│  ● Microsoft Fabric    ✓  ⌄                    │
│    Workspace: telecom-ws                        │
│                                                 │
│    ▸ Lakehouses (1)                             │
│      └─ NetworkTopologyLH                       │
│    ▸ Eventhouses (1)                            │
│      └─ NetworkTelemetryEH                      │
│    ▸ Ontologies (1)                             │
│      └─ NetworkTopologyOntology                 │
│    ▸ Graph Models (1)                           │
│      └─ telco-noc-fabric-topology               │
│    ▸ KQL Databases (0)                          │
│                                                 │
│    [Provision Resources]  [Refresh]             │
```

**Backend change:** None — all endpoints exist. Frontend hook needs to call
`fetchLakehouses()` and `fetchKqlDatabases()` (new methods).

### Issue 3: Ontology-model nesting doesn't match the API

**Document shows:** "telecom-ontology (3 models)" — as if models are children of ontologies.

**Reality:** `GET /query/fabric/ontologies/{ontology_id}/models` ignores `ontology_id`
entirely — it lists all workspace-level `GraphModel` items. Models are workspace-level
resources, not ontology children.

**Fix:** Show Graph Models as a separate top-level section in the resource list
(see wireframe in Issue 2). Remove the "(3 models)" suffix from ontology items.

### Issue 4: "Provision Resources" is unconditional — no scenario awareness

**Document shows:** A single "Provision Resources" button that runs the full pipeline.

**Problem:** The backend always creates all four resources (workspace + lakehouse +
eventhouse + ontology) regardless of what the active scenario actually needs.

Consider the permutations from `scenario.yaml`:

| `data_sources.graph.connector` | `data_sources.telemetry.connector` | Actually needs |
|------|-------|------|
| `fabric-gql` | `cosmosdb-nosql` | Lakehouse + Ontology (no Eventhouse) |
| `cosmosdb-gremlin` | `fabric-kql` (future) | Eventhouse only (no Lakehouse/Ontology) |
| `fabric-gql` | `fabric-kql` (future) | All three resources |
| `cosmosdb-gremlin` | `cosmosdb-nosql` | Nothing — pure Cosmos |

The current `telco-noc-fabric` scenario uses `fabric-gql` for graph + `cosmosdb-nosql`
for telemetry. Provisioning creates an eventhouse it doesn't use.

**Fix in the document:** Show scenario-aware provisioning:

```
│    Active: telco-noc-fabric                           │
│    Graph: fabric-gql → Lakehouse + Ontology           │
│    Telemetry: cosmosdb-nosql → (no Eventhouse)        │
│                                                       │
│    [Provision Required Resources]                     │
│    Will create: Lakehouse, Ontology                   │
│    Will skip: Eventhouse (telemetry uses CosmosDB)    │
```

When no scenario is active, show "Provision All" with a note explaining what each
resource is for.

**Backend change required:** Yes. `POST /api/fabric/provision` already accepts
`scenario_name` in `FabricProvisionRequest` but **ignores it entirely**. The endpoint
needs to:
1. If `scenario_name` provided, load scenario config from config store
2. Read `data_sources.graph.connector` and `data_sources.telemetry.connector`
3. Skip lakehouse + ontology if graph isn't `fabric-gql`
4. Skip eventhouse if telemetry isn't `fabric-kql`
5. Always create workspace (it's the container)

### Issue 5: Upload flow is broken for Fabric scenarios

**Document's user flow ("I want to create a Fabric scenario"):**
```
4. Upload tarballs → scenario saved with graph_connector: "fabric-gql"
```

**What actually happens:**

The upload endpoint `POST /query/upload/graph` calls `backend.ingest()`. When the
backend is `FabricGQLBackend`, `ingest()` raises:

```python
raise NotImplementedError(
    "Fabric graphs are populated via Lakehouse + Ontology provisioning, "
    "not direct ingest. Use the Fabric provisioning pipeline."
)
```

The user gets a 500 error. No helpful message, no graceful degradation.

**But wait — it's worse.** The backend selection (`get_backend_for_graph()`) uses
the **global** `GRAPH_BACKEND` env var, not the per-scenario connector from
`scenario.yaml`. So if the global env var is `cosmosdb` (the default), a Fabric
scenario's graph tarball will be pushed to CosmosDB Gremlin — wrong destination. If
the global env var is `fabric-gql`, ALL scenarios (including pure Cosmos ones) will
try to push to Fabric and crash.

**The actual Fabric graph data flow is:**
CSV files → Lakehouse (via Fabric portal / OneLake) → Ontology maps tables to entities
→ Graph Model binds ontology to data → GQL queries work.

This is fundamentally different from the Cosmos flow (CSV → Gremlin ingest).

**Fix in the document:**

For Fabric scenarios, the upload flow must be different:

```
Cosmos scenario:                     Fabric scenario:
1. [Upload Graph] → Gremlin         1. [Graph Upload disabled]
2. [Upload Telemetry] → CosmosDB      ↳ "Graph data managed in Fabric Lakehouse"
3. [Upload Runbooks] → Blob/Search   2. [Upload Telemetry] → CosmosDB ✓
4. [Upload Tickets] → Blob/Search    3. [Upload Runbooks] → Blob/Search ✓
5. [Upload Prompts] → Blob           4. [Upload Tickets] → Blob/Search ✓
                                     5. [Upload Prompts] → Blob ✓
```

- In AddScenarioModal: grey out graph upload when `selectedBackend === 'fabric-gql'`
- In ScenarioManagerModal: "Re-upload data" dropdown hides "Graph" for Fabric
  scenarios; shows "Re-provision Fabric graph" instead
- Show note: "Graph topology data lives in your Fabric Lakehouse. Upload it via
  the Fabric portal."

**Backend change required:** Yes — two changes:

1. **Upload guard:** `POST /query/upload/graph` should check `scenario.data_sources.graph.connector`.
   If `fabric-gql`, return 400 with helpful message: "This scenario uses Fabric for
   graph data. Upload CSV data to your Fabric Lakehouse directly or use the
   provisioning pipeline." Don't let it reach `NotImplementedError`.

2. **Per-scenario backend selection:** `get_backend_for_graph()` currently reads a
   global env var. For per-scenario connector dispatch, it should read the scenario's
   `data_sources.graph.connector` from the config store. (This may already be handled
   by the X-Graph header routing described in `v11fabricv2.md`, but the upload path
   doesn't use it.)

### Issue 6: `FABRIC_CONFIGURED` is a binary gate that hides a two-stage lifecycle

**Current code (`fabric_config.py`):**
```python
FABRIC_CONFIGURED = bool(
    os.getenv("FABRIC_WORKSPACE_ID") and os.getenv("FABRIC_GRAPH_MODEL_ID")
)
```

This conflates two very different states:
- "I can reach the workspace" (`FABRIC_WORKSPACE_ID` set) — enables discovery + provisioning
- "I can execute GQL queries" (`FABRIC_GRAPH_MODEL_ID` set) — enables scenario creation

The problem: all discovery endpoints gate on `FABRIC_CONFIGURED`. Without a Graph Model
ID, you can't even list what's in the workspace — even though that listing is exactly
what you need to set up Fabric in the first place.

**Fix (backend):** Split into two flags:

```python
FABRIC_WORKSPACE_CONNECTED = bool(os.getenv("FABRIC_WORKSPACE_ID"))
FABRIC_QUERY_READY = bool(
    os.getenv("FABRIC_WORKSPACE_ID") and os.getenv("FABRIC_GRAPH_MODEL_ID")
)

# Backward compat
FABRIC_CONFIGURED = FABRIC_QUERY_READY
```

- Discovery endpoints gate on `FABRIC_WORKSPACE_CONNECTED` (can list resources)
- `FabricGQLBackend.execute_query()` gates on `FABRIC_QUERY_READY` (can run GQL)
- Health endpoint returns both: `{workspace_connected, query_ready, workspace_id, graph_model_id}`

**Fix (document):** ConnectionsDrawer shows three states, not two:

| State | Condition | Display |
|-------|-----------|---------|
| Not configured | No `FABRIC_WORKSPACE_ID` | ○ Fabric — "Not configured" + setup hint |
| Partially ready | Workspace only, no Graph Model | ⚠ Fabric — "Workspace connected. Graph queries not ready." |
| Connected | Both IDs set | ● Fabric — "Connected ✓" |

The "partially ready" state is the most common intermediate state — a user who just
provisioned resources but hasn't created a Graph Model yet. The document doesn't
acknowledge this state at all.

### Issue 7: No dynamic config reload

**Problem:** `FABRIC_CONFIGURED` (and all Fabric env vars) are evaluated once at
module import time. If a future `POST /api/fabric/connect` endpoint sets a workspace
ID, the backend won't recognize it until restart.

**For v11:** Accept this limitation. The document should clearly state that Fabric
setup requires deployment config changes + container/app restart. A future version
can add runtime config via the config store.

**Add to Edge Cases section:**
> "Fabric workspace ID changes at runtime" — not supported in v11. Fabric env vars
> are read at startup. Changing them requires redeploying the backend container.

### Issue 8: Bug count is wrong — there are 5 bugs, not 3

The document lists 3 bugs (B1-B3). There are actually 5:

| # | Bug | Location | Impact |
|---|-----|----------|--------|
| B1 | Health check: `data.status === 'ok'` but backend returns `{configured: bool}` | `useFabricDiscovery.ts` | Fabric always shows unhealthy |
| B2 | Provision URL: frontend calls `/api/fabric/provision/pipeline` but route is `/api/fabric/provision` | `useFabricDiscovery.ts` | Provision always 404s |
| B3 | Stale closure: `provisionState` in both body and dep array | `useFabricDiscovery.ts` | Completion detection unreliable |
| **B4** | **Discovery response parsing: frontend reads `data.items` but backend returns raw `list[FabricItem]`** | **`useFabricDiscovery.ts`** | **All discovery lists always empty** |
| **B5** | **Discovery endpoints gate on `FABRIC_CONFIGURED` (requires Graph Model ID) instead of workspace-only** | **`router_fabric_discovery.py`** | **Can't discover resources until fully configured (chicken-and-egg)** |

B4 means that even after B1 is fixed and health shows "connected", expanding the
Fabric section will show 0 ontologies, 0 eventhouses, 0 everything — because the
response is a flat array, not `{items: [...]}`.

B5 means that even with a workspace ID set, all discovery endpoints return 503
"Fabric backend not configured" until `FABRIC_GRAPH_MODEL_ID` is also set.

### Issue 9: AddScenarioModal prerequisite checklist is too shallow

**Document says:** "Requires Fabric workspace setup via Connections panel first"

**Actual prerequisites for a working Fabric scenario:**
1. ✓/✗ `FABRIC_WORKSPACE_ID` set (workspace reachable)
2. ✓/✗ Lakehouse exists with CSV data loaded
3. ✓/✗ Ontology exists with schema defined
4. ✓/✗ Graph Model created (binds lakehouse data → queryable GQL)
5. ✓/✗ `FABRIC_GRAPH_MODEL_ID` set

The document's single-line text hides a 5-step setup process.

**Fix:** The Fabric card in AddScenarioModal should show a live prerequisite
checklist when prerequisites aren't met:

```
│  Microsoft Fabric                              │
│  GraphQL endpoint                              │
│  ────────────────                              │
│  Prerequisites:                                │
│    ✓ Workspace connected                       │
│    ✗ Graph Model not configured                │
│    ↳ Create a Graph Model in Fabric portal     │
│      and set FABRIC_GRAPH_MODEL_ID             │
│                                                │
│  [○ Not available]                             │
```

When all prerequisites pass:
```
│  ● Microsoft Fabric                            │
│  GraphQL endpoint                              │
│  ────────────────                              │
│  ✓ All prerequisites met                       │
│                                                │
│  [● Selected]                                  │
```

**Backend change:** The health endpoint needs to return richer status (see Issue 6
fix) so the frontend can render this checklist.

---

## 4. The Corrected ConnectionsDrawer Wireframe

### State A: Not configured (no workspace ID)

```
│  ○ Microsoft Fabric    —  ⌄                              │
│    ┌────────────────────────────────────────────────────┐ │
│    │ Not connected.                                    │ │
│    │                                                   │ │
│    │ Set FABRIC_WORKSPACE_ID in deployment config      │ │
│    │ and restart the backend.                          │ │
│    │                                                   │ │
│    │ ℹ Find your workspace ID in Fabric portal under   │ │
│    │   workspace settings → About.                    │ │
│    └────────────────────────────────────────────────────┘ │
```

### State B: Workspace connected, Graph Model not set

```
│  ⚠ Microsoft Fabric    ⚠ partial  ⌄                      │
│    Workspace: telecom-ws                                  │
│    Status: Workspace connected. Graph queries not ready.  │
│    ↳ Create a Graph Model in Fabric portal, then set      │
│      FABRIC_GRAPH_MODEL_ID env var.                       │
│                                                           │
│    ▸ Lakehouses (1)                                       │
│      └─ NetworkTopologyLH                                 │
│    ▸ Eventhouses (0)                                      │
│    ▸ Ontologies (1)                                       │
│      └─ NetworkTopologyOntology                           │
│    ▸ Graph Models (0)        ← this is why it's partial   │
│    ▸ KQL Databases (0)                                    │
│                                                           │
│    [Provision Resources]  [Refresh]                       │
```

### State C: Fully connected

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
│    [Provision Resources]  [Refresh]                        │
```

### Provision button with scenario awareness

When an active scenario exists:

```
│    Active scenario: telco-noc-fabric                       │
│    Graph: fabric-gql → needs Lakehouse + Ontology          │
│    Telemetry: cosmosdb-nosql → no Eventhouse needed        │
│                                                            │
│    [Provision Required Resources]                          │
│    Will create: Lakehouse, Ontology                        │
│    Will skip: Eventhouse (telemetry uses CosmosDB NoSQL)   │
```

When no active scenario:

```
│    No active scenario.                                     │
│    [Provision All Resources]                               │
│    Will create: Lakehouse, Eventhouse, Ontology            │
```

---

## 5. Corrected User Flows

### "I want to set up Fabric" (corrected — replaces lines ~720-730)

```
1. Set FABRIC_WORKSPACE_ID in deployment config (azure_config.env)
2. Redeploy/restart backend
3. Click 🔌 Connections → expand Fabric
4. See: "⚠ Workspace connected. Graph queries not ready."
5. See empty resource inventory: Lakehouses (0), Ontologies (0), etc.
6. Click "Provision Resources" → creates empty Lakehouse + Ontology
   (+ Eventhouse only if scenario needs it)
7. Load CSV data into Lakehouse (Fabric portal → OneLake → upload CSV)
8. Create Graph Model in Fabric portal (bind Lakehouse tables to graph)
9. Set FABRIC_GRAPH_MODEL_ID in deployment config + redeploy
10. Connections now shows: "● Connected ✓"
```

### "I want to create a Fabric scenario" (corrected — replaces lines ~732-736)

```
1. Prerequisite: Fabric shows "Connected ✓" in 🔌 (workspace + graph model)
2. Click [ScenarioChip ▾] → "+ New Scenario"
3. "Where should graph data live?" → select Fabric card
   Card shows: ✓ All prerequisites met
4. Upload tarballs: telemetry, runbooks, tickets, prompts
   (graph upload slot greyed out — "Graph data managed via Fabric Lakehouse")
5. Scenario saved with graph_connector: "fabric-gql"
6. Chip shows [telco-noc-fabric · Fabric ▾] with cyan badge
```

### "I already uploaded data to a Cosmos scenario and want to switch to Fabric"

```
This is not a supported transition in v11.
Cosmos graph data lives in CosmosDB Gremlin.
Fabric graph data lives in a Lakehouse.
To switch backends, create a new scenario with the Fabric backend.
The document should not imply you can "switch" a scenario's backend.
```

---

## 6. Corrected ScenarioManagerModal — Fabric Scenario Rows

For a Fabric scenario's expanded row:

```
│ ○ telco-noc-fabric      Fabric │ 18v  8p │ ⋮   │   │
│   Graph: fabric-gql (Fabric Lakehouse)           │   │
│   Telemetry: cosmosdb-nosql (CosmosDB)           │   │
│   Runbooks: telco-noc-fabric-runbooks-index      │   │
│   Tickets: telco-noc-fabric-tickets-index        │   │
│   Updated: 2026-02-14                            │   │
│                                                  │   │
│   [Re-provision Agents]  [Re-upload data ▾]      │   │
│                          ├─ Telemetry             │   │ ← Graph is hidden
│                          ├─ Runbooks              │   │
│                          ├─ Tickets               │   │
│                          └─ Prompts               │   │
│   [Re-provision Fabric Resources]                 │   │ ← Fabric-specific
```

For a pure Cosmos scenario:

```
│ ● telco-noc             Cosmos │ 42v 12p │ ⋮   │   │
│   Graph: cosmosdb-gremlin (CosmosDB)             │   │
│   Telemetry: cosmosdb-nosql (CosmosDB)           │   │
│   Runbooks: telco-noc-runbooks-index             │   │
│   ...                                            │   │
│                                                  │   │
│   [Re-provision Agents]  [Re-upload data ▾]      │   │
│                          ├─ Graph                 │   │ ← present for Cosmos
│                          ├─ Telemetry             │   │
│                          ├─ Runbooks              │   │
│                          ├─ Tickets               │   │
│                          └─ Prompts               │   │
```

---

## 7. Full Bug List (5 bugs, not 3)

### B1: Health check response mismatch

| | |
|---|---|
| **Frontend** | `data.status === 'ok'` → sets `healthy = true` |
| **Backend** | Returns `{"configured": true|false, "workspace_id": "..."}` — no `status` field |
| **Impact** | Fabric always shows unhealthy (healthy is never set to true) |
| **Fix** | `healthy = data.configured === true` (or `data.workspace_connected` after B-5 split) |

### B2: Provision endpoint URL mismatch

| | |
|---|---|
| **Frontend** | Calls `POST /api/fabric/provision/pipeline` |
| **Backend** | Route is `POST /api/fabric/provision` (no `/pipeline` suffix) |
| **Impact** | Provision always 404s |
| **Fix** | Change URL to `/api/fabric/provision` |

### B3: Stale closure in provision callback

| | |
|---|---|
| **Frontend** | `provisionState` in both callback body and useCallback dep array |
| **Impact** | Completion detection unreliable |
| **Fix** | Remove `provisionState` from deps; use local `completed` flag |

### B4: Discovery response parsing mismatch (NEW)

| | |
|---|---|
| **Frontend** | `setOntologies(data.items \|\| [])` — reads `.items` property |
| **Backend** | Returns raw `list[FabricItem]` — the response IS the array, not `{items: [...]}` |
| **Impact** | All discovery lists (ontologies, graph models, eventhouses) always empty |
| **Fix** | `setOntologies(Array.isArray(data) ? data : [])` — same for all three |

### B5: Discovery gates on full configuration instead of workspace-only (NEW)

| | |
|---|---|
| **Backend** | `_fabric_get()` checks `FABRIC_CONFIGURED` which requires BOTH `FABRIC_WORKSPACE_ID` AND `FABRIC_GRAPH_MODEL_ID` |
| **Impact** | Can't list resources until fully configured. Can't discover what needs to be provisioned. Chicken-and-egg. |
| **Fix** | Discovery endpoints gate on `FABRIC_WORKSPACE_CONNECTED` (workspace ID only). GQL query execution gates on `FABRIC_QUERY_READY` (both IDs). |

---

## 8. All Required Backend Changes

### Must-fix (blocks the documented user flow)

| # | Change | File(s) | Effort | Impact |
|---|--------|---------|--------|--------|
| BE-1 | Split `FABRIC_CONFIGURED` into `WORKSPACE_CONNECTED` + `QUERY_READY` | `adapters/fabric_config.py` | Low | Unblocks discovery before Graph Model exists |
| BE-2 | Discovery endpoints gate on `WORKSPACE_CONNECTED` not `CONFIGURED` | `router_fabric_discovery.py` | Low | Allows resource listing during setup |
| BE-3 | Richer health endpoint: `{workspace_connected, query_ready, workspace_id, graph_model_id}` | `router_fabric_discovery.py` | Low | Frontend can render 3-state Fabric status |
| BE-4 | Upload guard: check scenario connector before calling `backend.ingest()` | `router_ingest.py` | Low | Returns 400 with message instead of crashing with NotImplementedError |
| BE-5 | Conditional provisioning: read scenario config, skip unneeded resources | `fabric_provision.py` | Med | Don't create eventhouses for graph-only-on-Fabric scenarios |

### Should-fix (improves UX but not blocking)

| # | Change | File(s) | Effort | Impact |
|---|--------|---------|--------|--------|
| BE-6 | Add `FABRIC_*` vars to `azure_config.env.template` | `azure_config.env.template` | Low | Users can see what's configurable |
| BE-7 | Fabric sub-status in `GET /api/services/health` (3 states + per-resource breakdown) | New service health route | Med | ConnectionsDrawer shows partial/connected |

### Deferred to v12

| # | Change | Effort | Reason |
|---|--------|--------|--------|
| BE-8 | Lakehouse CSV upload API (upload graph data to Lakehouse via API) | High | Complex Fabric API; manual upload via portal is acceptable for v11 |
| BE-9 | Graph Model creation API | High | May not be available in Fabric public REST API |
| BE-10 | Runtime config reload / `POST /api/fabric/connect` | Med | Env vars + restart is acceptable for v11 |
| BE-11 | Per-scenario backend dispatch in upload path (read connector from config store, not global env var) | Med | Current global `GRAPH_BACKEND` env var works for single-backend deployments |

---

## 9. All Required Frontend Changes

### In `useFabricDiscovery.ts` (hook)

| # | Change | Lines |
|---|--------|-------|
| FE-1 | Fix B1: `healthy = data.configured === true` (or `data.workspace_connected`) | ~69 |
| FE-2 | Fix B2: URL `/api/fabric/provision/pipeline` → `/api/fabric/provision` | ~136 |
| FE-3 | Fix B3: Remove `provisionState` from deps | ~130-163 |
| FE-4 | Fix B4: `data.items \|\| []` → `Array.isArray(data) ? data : []` for all lists | ~84, ~99, ~113 |
| FE-5 | Add `fetchLakehouses()` — call `GET /query/fabric/lakehouses` | New |
| FE-6 | Add `fetchKqlDatabases()` — call `GET /query/fabric/kql-databases` | New |
| FE-7 | Update `fetchAll()` to include lakehouses and KQL databases | ~120 |

### In `ConnectionsDrawer.tsx` (new, from the plan)

| # | Change |
|---|--------|
| FE-8 | Show 3-state Fabric status: not configured / partial / connected |
| FE-9 | Show all 5 resource types (lakehouses, eventhouses, ontologies, graph models, KQL databases) |
| FE-10 | Show scenario-aware provision button (what will be created/skipped) |
| FE-11 | Show "Graph queries not ready" warning when workspace connected but no Graph Model |

### In `AddScenarioModal.tsx`

| # | Change |
|---|--------|
| FE-12 | Fabric card shows live prerequisite checklist (workspace ✓/✗, graph model ✓/✗) |
| FE-13 | Fabric card disabled unless `query_ready` (not just `configured`) |
| FE-14 | When Fabric selected: grey out graph upload slot, show "Graph data managed via Fabric Lakehouse" |

### In `ScenarioManagerModal.tsx` (refactored from SettingsModal)

| # | Change |
|---|--------|
| FE-15 | For Fabric scenarios: hide "Graph" from "Re-upload data" dropdown |
| FE-16 | For Fabric scenarios: add "Re-provision Fabric Resources" button |

---

## 10. Corrected Edge Cases (additions/modifications to the plan)

### Workspace connected but Graph Model not configured (NEW — most common intermediate state)

- ConnectionsDrawer: "⚠ Workspace connected. Graph queries not ready."
- Discovery works — user can see lakehouses, ontologies, etc.
- Provisioning works — user can create empty containers
- AddScenarioModal: Fabric card disabled with checklist showing what's missing
- Existing (Cosmos) scenarios unaffected
- Ambient health: Fabric not counted toward "N/M Services" total if not configured.
  (Same behavior as documented for "Fabric env vars not set")

### User tries to upload graph data to a Fabric scenario (NEW)

- `POST /query/upload/graph` checks scenario connector
- Returns 400: "This scenario uses Fabric for graph data. Upload CSV data to your
  Fabric Lakehouse directly or use the provisioning pipeline."
- UI shows toast with this message
- Telemetry, runbooks, tickets, prompts uploads still work

### Scenario has `fabric-gql` graph but `cosmosdb-nosql` telemetry (existing scenario pattern)

- This is the `telco-noc-fabric` scenario. It's the primary Fabric pattern.
- Provisioning should create Lakehouse + Ontology, skip Eventhouse
- Upload flow: graph slot disabled, telemetry/runbooks/tickets/prompts normal
- ConnectionsDrawer provision button shows what will be created/skipped

### Scenario has `cosmosdb-gremlin` graph but `fabric-kql` telemetry (future, hypothetical)

- This would need an Eventhouse + KQL Database, not a Lakehouse + Ontology
- Provisioning should create Eventhouse only, skip Lakehouse + Ontology
- Upload flow: graph uploads normally to CosmosDB, telemetry slot may need
  different handling (route to Eventhouse vs CosmosDB)
- **For v11:** Document as a known future pattern. Don't block on it.

---

## 11. Specific Amendments to `v11fabricUIRevamp.md`

### Change 4 (ConnectionsDrawer) — 6 amendments

1. **Add 3 Fabric states** (not configured / partial / connected) to the wireframe
2. **Add all 5 resource types** to the Fabric expanded section (lakehouses, eventhouses,
   ontologies, graph models, KQL databases)
3. **Remove** "(3 models)" suffix from ontology items (graph models are workspace-level)
4. **Add** scenario-aware provision button with will-create/will-skip labels
5. **Add** "Graph queries not ready" warning in partial state
6. **Add** "Not connected" setup hint with workspace ID explanation (not just "set env vars")

### Change 7 (Backend chooser in AddScenarioModal) — 2 amendments

1. **Replace** "Requires Fabric workspace setup" with live prerequisite checklist
2. **Disable** Fabric card when `query_ready === false` (not just `configured === false`)

### Change 8 (Bug fixes) — 1 amendment

1. **Add** B4 (discovery response parsing) and B5 (discovery gating) to the bug list

### Implementation Plan Phase A — 3 amendments

1. **Add** Task 1b: Fix B4 and B5 (discovery bugs)
2. **Add** Task 2b: Split `FABRIC_CONFIGURED` into two-level flags (BE-1, BE-2, BE-3)
3. **Add** Task 2c: Upload guard for Fabric scenarios (BE-4)
4. **Add** Task 2d: Conditional provisioning (BE-5) — can be Phase B if needed

### Implementation Plan Phase D — 1 amendment

1. **Add** to Task 8: Grey out graph upload for Fabric scenarios (FE-14)

### User Flows section — 2 amendments

1. **Rewrite** "I want to set up Fabric" with the 10-step corrected flow
2. **Rewrite** "I want to create a Fabric scenario" with the 6-step corrected flow

### Edge Cases section — 3 additions

1. **Add** "Workspace connected but Graph Model not configured"
2. **Add** "User tries to upload graph data to Fabric scenario"
3. **Add** "Scenario has fabric-gql graph but cosmosdb-nosql telemetry"

---

## 12. Summary: Does the Fabric Experience Make Sense?

**As currently written: No.** The document describes a plausible end state but lacks
the staged lifecycle that gets you there. Specifically:

| What the user expects | What the document describes | What the code does |
|---|---|---|
| Create a connection | "Set env vars" (one line) | Env vars at deploy time, no UI |
| See workspace contents | Ontologies + Eventhouses | Missing lakehouses, graph models, KQL databases. Discovery is broken (B4, B5). |
| Upload data | "Upload tarballs" | Graph upload crashes for Fabric (NotImplementedError). No guard. |
| Deploy based on scenario needs | "Provision Resources" (one button) | Always creates all 4 resources regardless of scenario |
| Track setup progress | Not addressed | Two-stage lifecycle (workspace-only vs fully-ready) not shown |

**After the corrections in this audit:** Yes. The flow becomes:

1. **CONNECT** → workspace ID in env vars (or future UI) → partial connection
2. **DISCOVER** → expand Fabric in ConnectionsDrawer → see all 5 resource types
3. **PROVISION** → scenario-aware button → creates only what's needed
4. **LOAD DATA** → manual via Fabric portal (documented, not hidden)
5. **ENABLE** → set Graph Model ID → full connection
6. **CREATE SCENARIO** → Fabric card with live prereq checklist → upload non-graph data

The 5 backend changes (BE-1 through BE-5) and 16 frontend changes (FE-1 through FE-16)
are individually small (mostly Low effort). The most complex is BE-5 (conditional
provisioning, Medium effort). None require architectural changes — they're corrections
to existing code, not new capabilities.

---

## 13. Priority Order for Implementation

```
Priority 1 — Bug fixes (unblocks all Fabric UI):
  B1 (health check), B2 (provision URL), B3 (stale closure),
  B4 (discovery parsing), B5 (discovery gating)
  
Priority 2 — Backend config split (2 hours):
  BE-1, BE-2, BE-3 (split FABRIC_CONFIGURED, update gates, richer health)

Priority 3 — Upload guard (1 hour):  
  BE-4 (check connector before ingest, return 400)

Priority 4 — Frontend Fabric section (ConnectionsDrawer, during Phase C):
  FE-8 through FE-11 (3-state, all resources, scenario-aware provision)

Priority 5 — Conditional provisioning (half day):
  BE-5 (read scenario config, skip unneeded resources)

Priority 6 — AddScenarioModal Fabric flow (during Phase D):
  FE-12 through FE-14 (prereq checklist, disabled card, grey out graph upload)

Priority 7 — ScenarioManagerModal Fabric rows (during Phase C):
  FE-15, FE-16 (hide graph upload, add re-provision button)
```
