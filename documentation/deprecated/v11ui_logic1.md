# V11 UI Revamp — Fabric Logic Audit

> **Date:** 2026-02-16
> **Scope:** Audit the Fabric experience described in v11fabricUIRevamp.md against
> the actual backend implementation and resource model.
> **Verdict:** The plan has **the right instincts but wrong details**. The resource 
> hierarchy, the "what gets provisioned" flow, the health/connection distinction, and
> the per-scenario provisioning model all need corrections. Several backend changes
> are required.

---

## 1. The Real Fabric Resource Hierarchy

The plan's ConnectionsDrawer wireframe implies a flat structure: workspace, ontologies,
eventhouses. The actual dependency chain is deeper and more nuanced:

```
Fabric Capacity (pre-existing, NOT managed by the app)
  └── Workspace
        ├── Lakehouse        ← holds CSV entity data (graph nodes/edges as tables)
        │     └── Tables/Files uploaded via OneLake or Fabric API
        ├── Eventhouse       ← holds streaming telemetry data
        │     └── KQL Database  ← query surface for telemetry (NOT created by provision)
        │           └── Tables (ingested from EventStream — NOT automated)
        └── Ontology         ← defines the graph schema
              └── Graph Model  ← binds to Lakehouse data to create queryable graph (NOT created by provision)
```

**What the plan gets wrong:**

| Plan says | Reality |
|-----------|---------|
| "Ontologies: 2 \| Eventhouses: 1" in the Fabric section | Missing: Lakehouses. A Lakehouse is a **core resource** — it's where entity CSVs live. The plan never mentions Lakehouse in the ConnectionsDrawer. |
| Graph Models shown "under" ontology | Graph Models are **workspace-level items** in the Fabric API, not nested under ontologies. The discovery endpoint `list_graph_models(ontology_id)` ignores the `ontology_id` parameter entirely — it lists all workspace-level GraphModel items regardless. |
| "Provision Resources" creates everything needed | Provision creates 4 **empty containers** (workspace, lakehouse, eventhouse, ontology) but does NOT: upload CSV data to the lakehouse, create a Graph Model, create a KQL database, populate the ontology schema, or set up EventStreams. |
| Lakehouses not mentioned anywhere | Lakehouse discovery endpoint exists (`GET /query/fabric/lakehouses`) but the frontend never calls it. |

---

## 2. The Logical Flow: How a User Actually Gets to a Working Fabric Scenario

The plan's "I want to set up Fabric" user flow skips critical steps. Here's what
must actually happen:

```
Step 1: CONNECT — Establish workspace connection
   User sets FABRIC_WORKSPACE_ID env var (a pre-existing Fabric workspace)
   The app can now discover what's in that workspace

Step 2: DISCOVER — See what's already there
   Open ConnectionsDrawer → expand Fabric
   The app lists: ontologies, lakehouses, eventhouses, graph models, KQL databases
   These may already exist (user provisioned them externally) or may be empty

Step 3: PROVISION (optional) — Create empty resource containers
   Click "Provision Resources" → the pipeline creates:
     • Lakehouse (container for CSV data)
     • Eventhouse (container for streaming telemetry)
     • Ontology (container for graph schema)
   These are EMPTY. No data is loaded. No graph model is created.

Step 4: UPLOAD DATA — Actually populate the resources
   This is the tarball upload. But for Fabric scenarios, the tarball upload
   flow is fundamentally different:
     • Graph data → must go to Lakehouse (currently NOT implemented)
     • Telemetry data → may go to Eventhouse (currently NOT implemented)
     • OR telemetry stays on CosmosDB NoSQL (current telco-noc-fabric approach)
   The FabricGQLBackend.ingest() raises NotImplementedError

Step 5: CREATE GRAPH MODEL — Must happen in Fabric portal (or via API we don't support)
   After Lakehouse has data, someone creates a Graph Model that binds to the
   Lakehouse tables to create a queryable GQL endpoint.
   FABRIC_GRAPH_MODEL_ID must then be set.

Step 6: CREATE SCENARIO — Only now can a Fabric scenario work
   User creates scenario with graph_connector: "fabric-gql"
   The scenario config references workspace_id and graph_model_id
   GQL queries execute via the Graph Model REST API
```

**The plan's user flow ("I want to create a Fabric scenario") says:**

```
1. Click 🔌 → verify Fabric is Connected + resources provisioned
2. Click [ScenarioChip ▾] → "+ New Scenario"
3. "Where should graph data live?" → select Fabric card
4. Upload tarballs → scenario saved with graph_connector: "fabric-gql"
5. Scenario chip shows [factory-demo · Fabric ▾] with cyan badge
```

**Problem:** Step 4 can't work. `FabricGQLBackend.ingest()` throws
`NotImplementedError`. The tarball upload flow assumes CosmosDB Gremlin
ingestion. For Fabric, data must reach a Lakehouse, and a Graph Model
must be created from it before GQL queries can execute.

---

## 3. Specific Issues in v11fabricUIRevamp.md

### Issue F1: ConnectionsDrawer shows wrong Fabric resource inventory

**Plan says (Change 4 wireframe):**
```
│  ● Microsoft Fabric    ✓  ⌄                   │
│    Workspace: telecom-ws                       │
│    Ontologies: 2  │  Eventhouses: 1            │
│                                                │
│    ┌── Ontology ───────────────────────────┐   │
│    │ telecom-ontology (3 models)       [▾] │   │
│    └───────────────────────────────────────┘   │
│    ┌── Eventhouses ────────────────────────┐   │
│    │ telecom-eh  │  Type: Eventhouse       │   │
│    └───────────────────────────────────────┘   │
```

**Should be:**
```
│  ● Microsoft Fabric    ✓  ⌄                   │
│    Workspace: telecom-ws                       │
│                                                │
│    ┌── Resources ──────────────────────────┐   │
│    │ ▸ Lakehouses (1)                      │   │
│    │   └─ NetworkTopologyLH                │   │
│    │ ▸ Eventhouses (1)                     │   │
│    │   └─ NetworkTelemetryEH               │   │
│    │ ▸ Ontologies (1)                      │   │
│    │   └─ NetworkTopologyOntology          │   │
│    │ ▸ Graph Models (1)                    │   │
│    │   └─ telco-noc-fabric-topology        │   │
│    │ ▸ KQL Databases (0)                   │   │
│    └───────────────────────────────────────┘   │
│                                                │
│    [Provision Resources]  [Refresh]            │
```

**Why:** Lakehouses, Graph Models, and KQL Databases are all real resources
that users need to see. The discovery endpoints for all five exist. The plan
currently omits three of them completely.

### Issue F2: "Ontology (3 models)" implies ontology-model nesting that doesn't exist

The plan shows "telecom-ontology (3 models)" as if Graph Models are children of
Ontologies. In the Fabric API, Graph Models are workspace-level items. The
discovery code confirms this — `list_graph_models(ontology_id)` ignores the
`ontology_id` parameter and lists all workspace Graph Models.

Graph Models conceptually relate to Ontologies (an ontology defines the schema,
a model is a queryable instance), but the API doesn't nest them.

**Fix:** Show Graph Models as a separate expandable section, not nested under
Ontology.

### Issue F3: Missing Lakehouse from the resource model and discovery flow

The plan never mentions Lakehouse in the ConnectionsDrawer wireframes. But:
- `GET /query/fabric/lakehouses` endpoint exists and works
- The provision pipeline creates a Lakehouse as step 2 (20-35%)
- The Lakehouse is where CSV entity data must live for the Ontology/Graph Model
  to work
- The provision request model has `lakehouse_name` as a parameter

Lakehouse is arguably the most important Fabric resource for the data flow —
it's where the actual graph data lives.

### Issue F4: "Provision Resources" description is misleading

The plan says provisioning creates resources in the Fabric workspace and shows an
85% progress bar with "Creating ontology...". But the provision pipeline creates
**empty containers only**:

- Workspace: found or created
- Lakehouse: found or created (empty — no CSV data uploaded)
- Eventhouse: found or created (empty — no KQL database, no EventStream)  
- Ontology: found or created (empty — no schema, no graph model)

The plan should be explicit that provisioning creates the infrastructure scaffolding;
data loading is a separate step. The UI label should say something like "Provision
Infrastructure" or "Create Fabric Resources" with a note that data upload is still
needed.

### Issue F5: `FABRIC_CONFIGURED` requires `FABRIC_GRAPH_MODEL_ID` — but this doesn't exist until much later

From `fabric_config.py`:
```python
FABRIC_CONFIGURED = bool(
    os.getenv("FABRIC_WORKSPACE_ID") and os.getenv("FABRIC_GRAPH_MODEL_ID")
)
```

The health endpoint returns `configured: true` only when BOTH are set. But
`FABRIC_GRAPH_MODEL_ID` is the ID of a Graph Model that can only exist after:
1. A Lakehouse exists with data
2. An Ontology exists with a schema
3. Someone creates a Graph Model (currently manual)

This means:
- The ConnectionsDrawer will show Fabric as "Not configured" even when the
  workspace is reachable and resources are provisioned
- A user can't use the provision pipeline unless they've already somehow set
  `FABRIC_GRAPH_MODEL_ID` (chicken-and-egg, just a different chicken)

**The plan's ConnectionsDrawer "Not configured" hint says:** "Set FABRIC_WORKSPACE_ID
and FABRIC_GRAPH_MODEL_ID env vars." But these represent two completely different
lifecycle stages:
- `FABRIC_WORKSPACE_ID`: Set once, early. "I have a Fabric workspace."
- `FABRIC_GRAPH_MODEL_ID`: Set late, after data is loaded and model is created.
  "I have a working graph endpoint."

### Issue F6: Backend chooser card says "Requires Fabric workspace setup via Connections panel first"

This is correct directionally but incomplete. The actual prerequisites are:
1. `FABRIC_WORKSPACE_ID` set (workspace exists)
2. Lakehouse created and populated with CSV data
3. Ontology created with schema
4. Graph Model created (currently manual in Fabric portal)
5. `FABRIC_GRAPH_MODEL_ID` set

The card implies "just set up in Connections panel" — but Connections panel can only
do step 1-3 (and even step 2 is just creating an empty lakehouse, not loading data).

### Issue F7: `data.items` response parsing bug not documented with the other 3 bugs

The frontend hook reads `data.items` from discovery responses:
```typescript
setOntologies(data.items || []);       // line 84
setGraphModels(data.items || []);      // line 99
setEventhouses(data.items || []);      // line 113
```

But the backend returns a **flat array** (the router has `response_model=list[FabricItem]`).
There is no `.items` wrapper — the response IS the array. This means all discovery
lists in the UI are always empty.

This is a **4th bug** (call it B4) that should be listed alongside B1-B3.

### Issue F8: The plan doesn't address the scenario.yaml per-component connector model

Looking at the scenario YAML files, a scenario can mix backends:
```yaml
# telco-noc-fabric/scenario.yaml
data_sources:
  graph:
    connector: "fabric-gql"      # Graph on Fabric
  telemetry:
    connector: "cosmosdb-nosql"  # Telemetry on CosmosDB
```

This means "Where should graph data live?" is only half the story. The user isn't
choosing a single backend — they're choosing the graph backend. Telemetry might
stay on CosmosDB even for a "Fabric scenario". And in theory, the reverse could
be true: graph on Cosmos, telemetry on Eventhouse/KQL.

The plan conflates "Fabric scenario" with `graph_connector: 'fabric-gql'`, which is
correct for the current implementation (telemetry is always CosmosDB NoSQL). But the
ConnectionsDrawer and provisioning UI need to be aware that only **some** resources
are relevant for a given scenario, depending on what connectors it uses.

### Issue F9: Selective provisioning not represented in the UI

The provision pipeline always creates workspace + lakehouse + eventhouse + ontology.
But a scenario might only need:
- Ontology + Lakehouse (graph on Fabric, telemetry on CosmosDB) — the current
  telco-noc-fabric scenario
- Eventhouse only (graph on CosmosDB, telemetry on Fabric KQL) — hypothetical
  but architecturally valid
- All three (graph + telemetry both on Fabric) — full Fabric scenario

The backend already supports individual provisioning endpoints:
- `POST /api/fabric/provision/lakehouse`
- `POST /api/fabric/provision/eventhouse`
- `POST /api/fabric/provision/ontology`

But the ConnectionsDrawer wireframe only shows a single "Provision Resources" button
that runs the full pipeline. There's no way to provision selectively.

---

## 4. The Correct Connection → Discovery → Provision → Upload Flow

Here's what the UI should actually represent:

```
┌────────────────────────────────────────────────────────────────────┐
│                                                                    │
│  PHASE 1: CONNECTION (env vars, pre-app)                          │
│  ──────────────────────────────────────                            │
│  Set FABRIC_WORKSPACE_ID → Fabric appears in ConnectionsDrawer     │
│  as "Connected" (partial — workspace reachable, no graph model     │
│  configured yet)                                                   │
│                                                                    │
│  PHASE 2: DISCOVERY (ConnectionsDrawer)                            │
│  ─────────────────────────────────────                             │
│  Open Connections → expand Fabric → see workspace resources:       │
│    Lakehouses: (0 | N)                                            │
│    Eventhouses: (0 | N)                                           │
│    Ontologies: (0 | N)                                            │
│    Graph Models: (0 | N)                                          │
│    KQL Databases: (0 | N)                                         │
│                                                                    │
│  PHASE 3: PROVISIONING (ConnectionsDrawer)                         │
│  ────────────────────────────────────────                          │
│  [Provision All] — creates lakehouse + eventhouse + ontology       │
│  Or individual: [+ Lakehouse] [+ Eventhouse] [+ Ontology]         │
│  These are EMPTY containers. No data is loaded.                   │
│                                                                    │
│  PHASE 4: DATA UPLOAD (AddScenarioModal or external)               │
│  ──────────────────────────────────────────────                    │
│  For Fabric graph scenarios:                                       │
│    ❌ Standard tarball upload → Gremlin ingest (NotImplementedError)│
│    ✓ Lakehouse CSV upload (not yet implemented in app)             │
│    ✓ Manual upload via Fabric portal / OneLake                     │
│                                                                    │
│  PHASE 5: GRAPH MODEL CREATION (external, currently)               │
│  ──────────────────────────────────────────────                    │
│  Create Graph Model in Fabric portal that binds to Lakehouse data  │
│  Set FABRIC_GRAPH_MODEL_ID env var                                 │
│  Now FABRIC_CONFIGURED=True, GQL queries work                      │
│                                                                    │
│  PHASE 6: SCENARIO CREATION (AddScenarioModal)                     │
│  ────────────────────────────────────────────                      │
│  Select "Fabric" in backend chooser                                │
│  Upload runbooks/tickets (these still go to Blob/Search normally)  │
│  graph_connector set to "fabric-gql"                               │
│  Scenario works — GQL queries hit Fabric Graph Model               │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

---

## 5. Required Backend Changes

### B-1: Split `FABRIC_CONFIGURED` into two levels

**File:** `graph-query-api/adapters/fabric_config.py`

```python
# Current:
FABRIC_CONFIGURED = bool(
    os.getenv("FABRIC_WORKSPACE_ID") and os.getenv("FABRIC_GRAPH_MODEL_ID")
)

# Should be:
FABRIC_WORKSPACE_CONNECTED = bool(os.getenv("FABRIC_WORKSPACE_ID"))
FABRIC_QUERY_READY = bool(
    os.getenv("FABRIC_WORKSPACE_ID") and os.getenv("FABRIC_GRAPH_MODEL_ID")
)

# Backward compat alias:
FABRIC_CONFIGURED = FABRIC_QUERY_READY
```

**Why:** "Is the workspace reachable?" and "Can I execute GQL queries?" are different
states. The ConnectionsDrawer needs to know the former; the query backend needs the
latter.

**Impact:**
- `GET /query/fabric/health` should return both: `{workspace_connected: bool,
  query_ready: bool, workspace_id: str, graph_model_id: str}`
- Discovery endpoints (`/ontologies`, `/lakehouses`, etc.) should gate on
  `FABRIC_WORKSPACE_CONNECTED`, not `FABRIC_CONFIGURED`
- The `FabricGQLBackend.execute_query()` should gate on `FABRIC_QUERY_READY`
- The ConnectionsDrawer shows "Connected" when workspace is connected but can
  indicate "Graph queries not ready — no Graph Model ID configured"

### B-2: Fix health endpoint to return richer status

**File:** `graph-query-api/router_fabric_discovery.py`

```python
# Current:
@router.get("/health")
async def fabric_health() -> dict:
    return {
        "configured": FABRIC_CONFIGURED,
        "workspace_id": FABRIC_WORKSPACE_ID,
    }

# Should be:
@router.get("/health")
async def fabric_health() -> dict:
    return {
        "workspace_connected": FABRIC_WORKSPACE_CONNECTED,
        "query_ready": FABRIC_QUERY_READY,
        "workspace_id": FABRIC_WORKSPACE_ID,
        "graph_model_id": FABRIC_GRAPH_MODEL_ID or None,
        "ontology_id": FABRIC_ONTOLOGY_ID or None,
    }
```

### B-3: Add discovery endpoints to `GET /api/services/health`

**File:** New route (as specified in the plan)

The services health endpoint needs to reflect Fabric's **two-level** status:

```json
{
  "name": "Microsoft Fabric",
  "type": "Graph Database",
  "group": "optional",
  "status": "partial",
  "details": "Workspace connected. Graph Model ID not configured — set FABRIC_GRAPH_MODEL_ID to enable GQL queries.",
  "sub_status": {
    "workspace": "connected",
    "graph_model": "not_configured",
    "lakehouse": "found",
    "eventhouse": "not_found",
    "ontology": "found"
  }
}
```

Three possible states: `"not_configured"` (no workspace ID), `"partial"` (workspace
but no graph model), `"connected"` (fully ready).

### B-4: Fix `data.items` response parsing (Bug B4)

**File:** `frontend/src/hooks/useFabricDiscovery.ts`

```typescript
// Current (broken):
setOntologies(data.items || []);

// Fix — backend returns flat array, not {items: [...]}:
setOntologies(Array.isArray(data) ? data : []);
```

Same fix for `graphModels` and `eventhouses`.

### B-5: Consider Lakehouse data upload API (future)

**File:** New endpoint in `api/app/routers/fabric_provision.py`

Currently `FabricGQLBackend.ingest()` raises `NotImplementedError`. For the
tarball upload to work with Fabric graph scenarios, we'd need:

```
POST /api/fabric/upload-lakehouse-data
  body: { workspace_id, lakehouse_id, csv_files[] }
  streams: SSE progress
```

This uploads CSV files to the Lakehouse via OneLake/Fabric API. Without this,
Fabric graph scenarios require manual data loading in the Fabric portal.

**For V11:** Document this as a known gap. Show a clear message in the
AddScenarioModal when Fabric is selected: "Graph data must be loaded into
your Fabric Lakehouse separately. Runbooks and tickets are uploaded normally."

### B-6: Missing Fabric env vars in azure_config.env.template

**File:** `azure_config.env.template`

Currently has zero `FABRIC_*` variables. Need to add:

```env
# -- Microsoft Fabric (optional) -------------------------------------------
# FABRIC_WORKSPACE_ID=                # Fabric workspace GUID
# FABRIC_GRAPH_MODEL_ID=              # Graph Model GUID (after data load)
# FABRIC_WORKSPACE_NAME=AutonomousNetworkDemo
# FABRIC_CAPACITY_ID=                 # Fabric capacity GUID (for provisioning)
# FABRIC_ONTOLOGY_ID=                 # Ontology GUID (after provisioning)
# FABRIC_ONTOLOGY_NAME=NetworkTopologyOntology
# FABRIC_LAKEHOUSE_NAME=NetworkTopologyLH
# FABRIC_EVENTHOUSE_NAME=NetworkTelemetryEH
```

---

## 6. Required Frontend Changes (beyond what the plan already covers)

### F-1: Update ConnectionsDrawer wireframe to show all 5 resource types

Add Lakehouses, Graph Models, and KQL Databases to the Fabric expanded section.
Show counts for each. The `useFabricDiscovery` hook needs to call the existing
`/query/fabric/lakehouses` and `/query/fabric/kql-databases` endpoints (already
implemented on the backend, never used by frontend).

### F-2: Update `useFabricDiscovery` hook to fetch all resource types

Add `fetchLakehouses()` and `fetchKqlDatabases()` to the hook. Both endpoints
exist in the backend.

### F-3: Show connection level, not binary Connected/Not configured

For the Fabric row in ConnectionsDrawer:

```
❌ Not configured     → No FABRIC_WORKSPACE_ID
⚠ Partially ready    → Workspace connected, but no FABRIC_GRAPH_MODEL_ID
✓ Connected           → Both set, GQL queries work
```

### F-4: AddScenarioModal Fabric card needs honest prerequisite list

Instead of just "Requires Fabric workspace setup via Connections panel first",
the card should show:

```
Microsoft Fabric
GraphQL endpoint
────────────────
Prerequisites:
  ✓ Workspace connected        (FABRIC_WORKSPACE_ID)
  ✓ Lakehouse with data         (loaded via Fabric portal)
  ✓ Graph Model created         (FABRIC_GRAPH_MODEL_ID)

Note: Runbooks and tickets upload normally.
Graph data must be loaded into your Fabric Lakehouse separately.
```

With the checklist items reflecting real state (green check if endpoint returns true).

### F-5: Acknowledge that tarball upload partially works for Fabric scenarios

When `graph_connector === 'fabric-gql'`, the AddScenarioModal upload flow should:
- **Skip** the graph data upload slot (or grey it out with "Graph data managed via
  Fabric Lakehouse")
- **Keep** telemetry, runbooks, tickets, prompts upload slots (these still use
  CosmosDB NoSQL, Blob, AI Search respectively — independent of graph backend)
- Show an explanatory note: "Graph topology data lives in your Fabric Lakehouse.
  Upload telemetry, runbooks, tickets, and prompts below."

---

## 7. Corrected User Flows

### "I want to set up Fabric" (corrected)

```
1. Set FABRIC_WORKSPACE_ID env var (pre-existing workspace) + redeploy
2. Click 🔌 Connections → expand Fabric
3. See: "Workspace connected. Graph queries not ready."
4. See resource inventory: Lakehouses (0), Eventhouses (0), Ontologies (0), ...
5. Click "Provision Resources" → creates empty Lakehouse + Eventhouse + Ontology
6. Load CSV data into Lakehouse (currently: Fabric portal. Future: API upload)
7. Create Graph Model in Fabric portal that binds Lakehouse tables
8. Set FABRIC_GRAPH_MODEL_ID env var + redeploy (or API update in future)
9. Connections now shows: "Connected ✓" — GQL queries ready
```

### "I want to create a Fabric scenario" (corrected)

```
1. Prerequisites: workspace connected, Lakehouse populated, Graph Model created
2. Click 🔌 → verify Fabric is "Connected ✓" (not just "Workspace connected")
3. Click [ScenarioChip ▾] → "+ New Scenario"
4. "Where should graph data live?" → select Fabric card
   Card shows all prerequisites met ✓
5. Upload runbooks + tickets + telemetry normally (graph slot greyed out)
6. Scenario saved with graph_connector: "fabric-gql"
7. Chip shows [factory-demo · Fabric ▾] with cyan badge
8. GQL queries execute against Fabric Graph Model
```

---

## 8. Summary of All Changes Needed

### Backend (5 changes)

| # | Change | File | Effort |
|---|--------|------|--------|
| B-1 | Split `FABRIC_CONFIGURED` into `WORKSPACE_CONNECTED` + `QUERY_READY` | `adapters/fabric_config.py` | Low |
| B-2 | Richer health endpoint (workspace_connected, query_ready, resource IDs) | `router_fabric_discovery.py` | Low |
| B-3 | Fabric sub-status in `GET /api/services/health` | New service health route | Med |
| B-4 | Fix `data.items` parsing (Bug B4 — discovery lists always empty) | `useFabricDiscovery.ts` | Low |
| B-6 | Add `FABRIC_*` vars to `azure_config.env.template` | `azure_config.env.template` | Low |

### Frontend (5 changes)

| # | Change | File | Effort |
|---|--------|------|--------|
| F-1 | ConnectionsDrawer shows all 5 resource types | `ConnectionsDrawer.tsx` | Med |
| F-2 | Hook fetches lakehouses + KQL databases | `useFabricDiscovery.ts` | Low |
| F-3 | Three-level Fabric status (not configured / partial / connected) | `ConnectionsDrawer.tsx`, `ServiceHealthSummary.tsx` | Low |
| F-4 | Backend chooser shows honest prerequisite checklist | `AddScenarioModal.tsx` | Med |
| F-5 | Grey out graph upload slot for Fabric scenarios | `AddScenarioModal.tsx` | Low |

### Documentation / deferred (2 items)

| # | Item | Notes |
|---|------|-------|
| B-5 | Lakehouse CSV upload API | Future (V12?). For now, manual via Fabric portal. Document the gap clearly. |
| — | Graph Model creation API | Not available in Fabric public API (as of writing). Manual step. Document. |

---

## 9. Impact on v11fabricUIRevamp.md

The following sections of the plan need amendments:

1. **Change 4 (ConnectionsDrawer)** — Update Fabric expanded section wireframe to
   show all 5 resource types. Remove "Ontology (3 models)" nesting. Add "Graph
   queries ready/not ready" status line.

2. **Change 7 (Backend chooser)** — Fabric card needs richer prerequisites. Grey
   out unless `query_ready` is true (not just `configured`). Show what's missing.

3. **Task 1 (Bug fixes)** — Add Bug B4 (data.items parsing).

4. **Task 2 (services health endpoint)** — Add sub-status for Fabric with
   per-resource breakdown.

5. **Task 5 (ConnectionsDrawer)** — Add lakehouse + KQL database + graph model
   sections. Call all 5 discovery endpoints.

6. **Task 8 (AddScenarioModal)** — Grey out graph upload slot for Fabric. Show
   "Graph data managed via Fabric Lakehouse" note.

7. **User flows** — Rewrite "I want to set up Fabric" and "I want to create a
   Fabric scenario" to reflect the actual multi-phase lifecycle.

8. **Edge cases** — Add edge case for "workspace connected but graph model not
   configured" (the most common intermediate state).

---

## 10. Key Principles for the Fabric UX

1. **Workspace is the connection, not the full Fabric integration.** Setting
   `FABRIC_WORKSPACE_ID` connects to Fabric. Everything else is progressive
   discovery and setup within that workspace.

2. ~~**Provisioning creates infrastructure, not data.** The "Provision" button
   creates empty containers. Data loading is a separate concern.~~
   **CORRECTED:** See §11 Fact-Check. The reference scripts provision 
   comprehensively — including data upload and full ontology definition.
   The API route is a stub that should be extended.

3. ~~**Graph Model is the linchpin.** Without `FABRIC_GRAPH_MODEL_ID`, no GQL
   queries can execute. This is the true enablement gate, not just workspace
   connectivity.~~
   **CORRECTED:** Graph Models are auto-created by Fabric when an ontology
   with full data bindings is created. The reference `provision_ontology.py`
   discovers the auto-created Graph Model and writes `FABRIC_GRAPH_MODEL_ID`
   to azure_config.env. The gate is correct, but the "manual creation" framing
   was wrong.

4. **Scenarios mix and match connectors.** A "Fabric scenario" uses Fabric for
   graph BUT may use CosmosDB for telemetry. The UI should not treat Fabric as
   all-or-nothing.

5. ~~**Show the lifecycle, don't hide the gaps.** The honest path is:
   connect → discover → provision infrastructure → load data (manual) →
   create graph model (manual) → set graph model ID → create scenario.~~
   **CORRECTED:** The honest path per the reference implementation is:
   connect → provision (creates resources + uploads data + creates ontology
   with bindings → Graph Model auto-created) → create scenario. The "manual"
   steps I described were artifacts of the current API stub being incomplete,
   not inherent Fabric limitations.

---

## 11. Fact-Check Against Reference Implementation

> **Source:** `fabric_implementation_references/` — the authoritative reference
> implementation from which the actual project was adapted.
>
> **Date:** 2026-02-16
> **Verdict:** Several claims in this audit were **wrong or misleading**. The
> reference implementation provisions comprehensively (data upload, full ontology,
> auto Graph Model). The actual project's API route is a simplified stub.

---

### Claims that were WRONG

#### ❌ F4: "Provision creates empty containers only — no data uploaded"

**What I said:** Provisioning creates empty containers (workspace, lakehouse,
eventhouse, ontology). No CSV data is uploaded, no KQL tables created, no
ontology schema populated.

**Reality from reference scripts:**

| Script | What it actually does |
|--------|---------------------|
| `provision_lakehouse.py` | Creates workspace + lakehouse, **uploads 10 CSV files** to OneLake via ADLS Gen2 API, then **loads each CSV into a managed delta table** via the Lakehouse Tables API |
| `provision_eventhouse.py` | Creates eventhouse, discovers the auto-created KQL database, **creates 2 KQL tables** (AlertStream, LinkTelemetry) with full schemas, **ingests CSV data** via Kusto SDK queued ingestion (with streaming fallback) |
| `provision_ontology.py` | Creates ontology with **full definition**: 8 entity types, 7 relationship types, static data bindings to Lakehouse tables, contextualizations (relationship data bindings). **935 lines** of comprehensive ontology definition |

**Correction:** The reference implementation does a **complete provisioning** —
resources + data + schema. The actual project's `fabric_provision.py` API route
is a **stub** that only creates empty containers. The fix is to extend the API
route to match the reference, not to document "empty containers" as expected
behavior.

#### ❌ "Graph Model creation is manual / currently not automated"

**What I said (§2 Step 5):** "Create Graph Model in Fabric portal (or via API
we don't support). FABRIC_GRAPH_MODEL_ID must then be set."

**Reality:** When you create an ontology with full entity types + data bindings
+ contextualizations, **Fabric auto-creates a Graph Model**. The reference
`provision_ontology.py` (lines 887-908):

```python
graph_item = client.find_graph_model(WORKSPACE_ID, ONTOLOGY_NAME)
if graph_item:
    graph_id = graph_item["id"]
    env_updates["FABRIC_GRAPH_MODEL_ID"] = graph_id
```

The script discovers the auto-created Graph Model and writes the ID to
azure_config.env. The code even notes: *"Graph is auto-refreshed by ontology
create/update."*

**Correction:** Graph Model creation is automatic when the ontology is created
properly with data bindings. It appears "manual" in the current project only
because the API route creates an empty ontology (no definition parts). The fix
is to include the full ontology definition in the provision pipeline.

#### ❌ "KQL database is NOT created by provision" (§1 hierarchy diagram)

**What I said:** `KQL Database ← query surface for telemetry (NOT created by
provision)`

**Reality:** The KQL database is auto-created when an Eventhouse is created.
`provision_eventhouse.py` discovers it via `find_kql_database()` and saves
`FABRIC_KQL_DB_ID` and `FABRIC_KQL_DB_NAME`. It then creates tables IN the
KQL database and ingests data.

**Correction:** KQL databases are auto-created with Eventhouses, not manual.

#### ❌ "EventStreams not automated"

**What I implied:** Telemetry data ingestion requires EventStreams which are
not automated.

**Reality:** The reference uses direct CSV ingestion via `azure-kusto-ingest`
SDK (queued ingestion with streaming inline fallback). No EventStreams needed
for batch/historical data. EventStreams are only relevant for real-time
streaming, which is a separate concern.

#### ❌ B-5: "Lakehouse data upload not implemented — future"

**What I said:** "For V11: Document this as a known gap."

**Reality:** The reference `provision_lakehouse.py` has a complete
implementation: `upload_csvs_to_onelake()` uploads CSVs via Azure Storage
DataLake SDK, then `load_table()` loads each CSV into a managed delta table
via the Lakehouse Tables API. 10 tables are uploaded.

**Correction:** The implementation exists in the reference scripts. The gap
is only that the API route doesn't expose this functionality. Porting it to
the API endpoint is straightforward, not a "future V12" concern.

#### ❌ "populate_fabric_config.py not mentioned"

The reference includes `populate_fabric_config.py` — a standalone script that
discovers all Fabric workspace items (Lakehouse, Eventhouse, KQL Database,
Ontology) and writes their IDs to azure_config.env. It even discovers AI
Foundry Fabric connections. This addresses the "post-provisioning env var
update" concern completely.

---

### Claims that were CORRECT

| Claim | Status | Notes |
|-------|--------|-------|
| F1: ConnectionsDrawer missing Lakehouses, Graph Models, KQL Databases | ✅ Correct | Reference confirms these are real resources. All should be shown. |
| F2: Ontology-Model nesting doesn't exist in Fabric API | ✅ Correct | Reference `find_graph_model()` searches workspace-level items, not ontology children. |
| F3: Lakehouse missing from UI resource model | ✅ Correct | Reference confirms Lakehouse is a core resource for CSV entity data. |
| F5: Two lifecycle stages for FABRIC_CONFIGURED | ⚠️ Partially correct | The split is architecturally valid for a UI, but the reference sidesteps it by running scripts sequentially. Both IDs get set during provisioning. |
| F7: `data.items` response parsing bug (B4) | ✅ Correct | Unrelated to reference — this is a frontend bug. |
| F8: Per-component connector model | ✅ Correct | Reference confirms `GRAPH_BACKEND` env var selects backend independently. |
| F9: No selective provisioning in UI | ✅ Correct | Reference scripts are individual CLI scripts. API could expose individual endpoints. |
| B-1: Split FABRIC_CONFIGURED | ⚠️ Still valid for UI | For a web UI with progressive disclosure, workspace_connected vs query_ready is still useful, even though the reference scripts set both during provisioning. |
| B-2: Richer health endpoint | ✅ Correct | |
| B-4: Fix data.items parsing | ✅ Correct | |
| B-6: Fabric vars missing from azure_config.env.template | ✅ Correct | The actual project's template has ZERO Fabric vars. The reference template has ~25. |

---

### Corrected Understanding: The Real Provisioning Flow

The reference implementation's provisioning order (from README):

```
1. azd up                        → Azure infra + graph-query-api deployed
2. provision_lakehouse.py         → Workspace + Lakehouse + CSV upload + delta tables
3. provision_eventhouse.py        → Eventhouse + KQL DB auto-created + tables + CSV ingest
4. provision_ontology.py          → Full ontology (8 entities, 7 relationships, bindings)
                                    → Graph Model auto-created by Fabric
                                    → FABRIC_GRAPH_MODEL_ID written to env
5. populate_fabric_config.py      → Discover all IDs → write to azure_config.env
6. assign_fabric_role.py          → Grant Container App identity workspace access
```

After step 4, `FABRIC_WORKSPACE_ID` AND `FABRIC_GRAPH_MODEL_ID` are both set.
`FABRIC_CONFIGURED = True`. GQL queries work immediately.

The current project's API route (`fabric_provision.py`) only does steps 2-4
**without data upload or ontology definition**, which is why everything appeared
"empty" and "manual".

---

### Impact on v11fabricUIRevamp.md Changes

| Original recommendation | Revised recommendation |
|------------------------|----------------------|
| Label provision as "Create Fabric Resources" with "data upload needed" caveat | Provision should upload data and create full ontology — match reference implementation |
| B-5: Lakehouse upload as "future V12" | Port reference `upload_csvs_to_onelake()` + `load_table()` into API route for V11 |
| Graph Model creation as "manual in Fabric portal" | Remove this claim — ontology with bindings auto-creates Graph Model |
| 6-phase user flow (connect → discover → provision → upload manual → model manual → scenario) | Simplify to: connect → provision (full) → create scenario. Provisioning IS data loading. |
| F-4: "Graph data must be loaded separately" disclaimer | Instead: provision pipeline handles data upload automatically |
| F-5: Grey out graph upload for Fabric | Instead: show "Graph data provisioned via Fabric pipeline" (already done) |

---

### Root Cause of My Errors

I audited the **actual project's API route** (`fabric_provision.py`, 654 lines)
which is a simplified adaptation that creates empty containers. I treated it
as the source of truth for "what provisioning does." I should have checked the
reference implementation first — the 3 standalone scripts (totaling ~1700 lines)
that do the full provisioning including data upload, ontology definition, and
auto Graph Model discovery.

The actual project's API route needs to be extended to match the reference
implementation, not documented as intentionally limited.
