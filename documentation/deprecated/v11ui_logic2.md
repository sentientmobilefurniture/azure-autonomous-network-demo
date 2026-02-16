# V11 UI Revamp — Fabric Logic Audit

> **Created:** 2026-02-16
> **Scope:** Audit of `v11fabricUIRevamp.md` to verify the Fabric connection → workspace → resource discovery → data upload → conditional deployment flow is logically complete.
> **Verdict:** The document has **significant gaps** in the Fabric UX flow. The ConnectionsDrawer Fabric section is too shallow — it shows a flat list of resources but **does not describe the staged connection setup, conditional resource visibility, or scenario-aware provisioning** that the user expects.

---

## Expected Logical Flow (What Should Exist)

```
1. CREATE FABRIC CONNECTION
   └── User provides/confirms workspace ID
       └── Workspace is the minimum required entity
       └── Connection validated via /query/fabric/health

2. DRILL INTO CONNECTION (ConnectionsDrawer → Fabric expanded)
   └── Shows what exists in that workspace:
       ├── Ontologies (list from /query/fabric/ontologies)
       ├── Lakehouses (list from /query/fabric/lakehouses)
       ├── Eventhouses (list from /query/fabric/eventhouses)
       └── Graph Models (nested under ontology)

3. UPLOAD SCENARIO DATA (via tarball)
   └── scenario.yaml declares what's needed:
       ├── graph.connector = "fabric-gql" → needs ontology + lakehouse
       ├── telemetry.connector = "cosmosdb-nosql" → no eventhouse needed
       └── (future) telemetry.connector = "fabric-kql" → needs eventhouse

4. CONDITIONAL DEPLOYMENT (based on scenario.yaml)
   └── Only provision what the scenario actually needs:
       ├── Ontology + Lakehouse: always (if fabric-gql graph)
       ├── Eventhouse: only if telemetry.connector = "fabric-kql"
       └── Neither: if graph.connector = "cosmosdb-gremlin" (pure Cosmos)
```

---

## What the Document Currently Describes

### ConnectionsDrawer Fabric Section (Lines ~230–260)

The document shows this Fabric expanded view:

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
│                                                │
│    [Provision Resources]  [Refresh]            │
│    ────────────────────────────────────        │
│    Progress: ████████░░ 80%                    │
│    Creating ontology...                        │
```

**This is a flat snapshot of a healthy state.** It doesn't describe:

1. **How you get from "not configured" to "connected".** The unconfigured state says "Set FABRIC_WORKSPACE_ID and FABRIC_GRAPH_MODEL_ID env vars" — but env vars are a deployment concern, not a UI flow. There's no UI to create or select a workspace.

2. **Lakehouses are missing from the display.** The discovery API has `GET /query/fabric/lakehouses` and the provisioning pipeline creates a lakehouse, but the ConnectionsDrawer mockup doesn't show lakehouses at all.

3. **"Provision Resources" is unconditional.** The button doesn't know what the active scenario needs. It always runs the full pipeline (workspace → lakehouse → eventhouse → ontology) regardless of scenario.yaml.

4. **No scenario-awareness in the Fabric section.** The Fabric drawer shows workspace-level resources, but doesn't indicate which resources the current scenario actually uses or needs.

### "I want to set up Fabric" User Flow (Lines ~720–730)

```
1. Click 🔌 Connections
2. Expand Fabric row → see status
3. If configured: browse ontologies, provision resources
4. Health works (bug fixed)
5. Provision works (bug fixed)
6. Create scenario with Fabric chooser
```

**This flow skips the critical first step:** How does Fabric become "configured" in the first place? The document assumes Fabric is either configured (env vars set) or not, with no UI path to bridge the gap.

### "I want to create a Fabric scenario" User Flow (Lines ~732–736)

```
1. Click 🔌 → verify Fabric is Connected + resources provisioned
2. Click [ScenarioChip ▾] → "+ New Scenario"
3. "Where should graph data live?" → select Fabric card
4. Upload tarballs → scenario saved with graph_connector: "fabric-gql"
5. Scenario chip shows [factory-demo · Fabric ▾] with cyan badge
```

**Step 4 is misleading.** The current upload flow (`POST /query/upload/graph`) calls `backend.ingest()` which raises `NotImplementedError` for `FabricGQLBackend`. Fabric graph data goes through the provisioning pipeline (lakehouse CSV upload + ontology creation), not the standard upload flow.

---

## Gaps Found

### Gap 1: No Fabric Connection Setup UI

**Problem:** The only way to "connect" Fabric is to set `FABRIC_WORKSPACE_ID` and `FABRIC_GRAPH_MODEL_ID` environment variables at deployment time. There is no UI to:
- Enter a workspace ID manually
- Browse available workspaces (authenticated user's workspaces)
- Select a workspace and have it persist

**Impact:** The "create a Fabric connection → look deeper into it" flow doesn't exist. Users can't set up Fabric from the UI.

**Recommendation for the document:** Add a "Fabric Setup" sub-section within the ConnectionsDrawer for the unconfigured state:

```
│  ○ Microsoft Fabric    —  ⌄                    │
│    ┌──────────────────────────────────────────┐│
│    │ Connect to a Fabric Workspace            ││
│    │                                          ││
│    │ Workspace ID: [________________________] ││
│    │                                          ││
│    │ ℹ Found in portal.fabric.microsoft.com   ││
│    │   under workspace settings.              ││
│    │                                          ││
│    │          [Connect]                       ││
│    └──────────────────────────────────────────┘│
```

**Backend change needed:** A `POST /api/fabric/connect` endpoint (or `PUT /api/fabric/config`) that persists the workspace ID to server-side config (env var override, config store, or CosmosDB). The `FABRIC_CONFIGURED` flag should update dynamically, not require a restart.

### Gap 2: Lakehouses Missing from ConnectionsDrawer

**Problem:** The provisioning pipeline creates a lakehouse (step 2 of 4), and there's a discovery endpoint (`GET /query/fabric/lakehouses`), but the ConnectionsDrawer mockup only shows ontologies and eventhouses.

**Impact:** Users can't see whether their lakehouse exists, which breaks the "look deeper into the connection" flow.

**Recommendation for the document:** Add lakehouses to the Fabric expanded section:

```
│    Ontologies: 2  │  Lakehouses: 1  │  Eventhouses: 1   │
│                                                          │
│    ┌── Ontology ───────────────────────────────────┐     │
│    │ telecom-ontology (3 models)               [▾] │     │
│    └───────────────────────────────────────────────┘     │
│    ┌── Lakehouses ─────────────────────────────────┐     │
│    │ NetworkTopologyLH  │  Type: Lakehouse         │     │
│    └───────────────────────────────────────────────┘     │
│    ┌── Eventhouses ────────────────────────────────┐     │
│    │ telecom-eh  │  Type: Eventhouse               │     │
│    └───────────────────────────────────────────────┘     │
```

**Backend change needed:** None — `GET /query/fabric/lakehouses` already exists.

### Gap 3: Provisioning is Unconditional (Always Creates All 4 Resources)

**Problem:** The `POST /api/fabric/provision` endpoint always runs the full pipeline: workspace → lakehouse → eventhouse → ontology. It does not read `scenario.yaml` to determine which resources are actually needed.

Consider:
| Scenario Config | Actually Needs | Currently Provisions |
|----------------|----------------|---------------------|
| graph: `fabric-gql`, telemetry: `cosmosdb-nosql` | Workspace + Lakehouse + Ontology | Workspace + Lakehouse + **Eventhouse** + Ontology |
| graph: `cosmosdb-gremlin`, telemetry: `fabric-kql` (future) | Workspace + Eventhouse | Workspace + **Lakehouse** + Eventhouse + **Ontology** |
| graph: `fabric-gql`, telemetry: `fabric-kql` (future) | All 4 | All 4 ✓ |
| graph: `cosmosdb-gremlin`, telemetry: `cosmosdb-nosql` | None (no Fabric) | N/A |

**Impact:** The "Provision Resources" button in the document creates unnecessary resources. This isn't harmful (Fabric items are free to create) but it's confusing — users see an eventhouse they don't use, or an ontology they don't need.

**Recommendation for the document:** The ConnectionsDrawer should show provisioning as scenario-aware:

```
│    Active: telco-noc-fabric                              │
│    Graph: fabric-gql → needs Ontology + Lakehouse        │
│    Telemetry: cosmosdb-nosql → no Eventhouse needed      │
│                                                          │
│    [Provision Required Resources]                        │
│    Will create: Lakehouse, Ontology                      │
│    Will skip: Eventhouse (telemetry uses CosmosDB)       │
```

**Backend change needed:** Yes — the `POST /api/fabric/provision` endpoint should accept an optional `scenario_name` parameter (it already has this field in `FabricProvisionRequest` but ignores it for determining which resources to create). The endpoint should:
1. If `scenario_name` is provided, fetch the scenario config from the config store
2. Read `data_sources.graph.connector` and `data_sources.telemetry.connector`
3. Skip lakehouse + ontology if graph connector is not `fabric-gql`
4. Skip eventhouse if telemetry connector is not `fabric-kql`
5. Always create workspace (it's the container)

The individual provisioning endpoints (`/provision/lakehouse`, `/provision/eventhouse`, `/provision/ontology`) already exist for manual control — the full pipeline just needs to be made conditional.

### Gap 4: Upload Flow Broken for Fabric Scenarios

**Problem:** The document's user flow says "Upload tarballs → scenario saved with graph_connector: fabric-gql", but the upload endpoint (`POST /query/upload/graph`) calls `backend.ingest()` which **raises `NotImplementedError`** for `FabricGQLBackend`:

```python
async def ingest(self, vertices, edges, **kwargs):
    raise NotImplementedError(
        "Fabric graphs are populated via Lakehouse + Ontology provisioning, "
        "not direct ingest."
    )
```

The actual Fabric graph data flow is: CSV files → Lakehouse (via provisioning) → Ontology maps Lakehouse tables to graph entities. This is fundamentally different from the Cosmos flow (CSV → Gremlin ingest).

**Impact:** If a user follows the doc's flow — create scenario with Fabric backend, then upload graph tarball — the upload will fail.

**Recommendation for the document:** The Fabric scenario creation flow needs to be different from the Cosmos flow:

```
Cosmos scenario:                        Fabric scenario:
1. Create scenario                      1. Verify Fabric connected (🔌)
2. Upload graph tarball                 2. Create scenario (Fabric backend)
3. Upload telemetry tarball             3. Provision Fabric resources
4. Upload runbooks/tickets              4. Upload telemetry tarball (→ CosmosDB)
5. Provision agents                     5. Upload runbooks/tickets
6. Done                                 6. Provision agents
                                        7. Done
```

For Fabric scenarios, graph data ingestion happens during Step 3 (provisioning), not during a separate upload step. The document should:
- Modify the ScenarioManagerModal's "Re-upload data ▾" dropdown to hide the "Graph" option for Fabric scenarios
- Add a "Re-provision Fabric resources" button specifically for Fabric scenarios
- Note that telemetry upload still works (it goes to CosmosDB NoSQL regardless)

**Backend change needed:** The provisioning pipeline needs to handle CSV data upload to the lakehouse. Currently `POST /api/fabric/provision` creates the lakehouse but doesn't populate it with data. The `scenario_name` parameter exists but isn't used to locate and upload CSV files from the scenario's data directory.

### Gap 5: No Dynamic Fabric Config (Requires Restart)

**Problem:** `FABRIC_CONFIGURED` is evaluated at module load time:

```python
FABRIC_CONFIGURED = bool(FABRIC_WORKSPACE_ID and FABRIC_GRAPH_MODEL_ID)
```

If a user connects a Fabric workspace via a future UI (Gap 1), the backend would need to be restarted for the flag to update.

**Impact:** The ConnectionsDrawer can't show a live transition from "Not configured" to "Connected" without a server restart.

**Recommendation for the document:** Acknowledge this limitation or plan for runtime config updates. Options:
1. **Config store approach:** Store Fabric config in CosmosDB, read dynamically per-request instead of at startup
2. **Env var reload:** Add a `POST /api/fabric/reload-config` endpoint that re-reads env vars
3. **Accept the limitation:** Document that Fabric setup requires deployment config changes + restart (simpler, acceptable for v11)

**Backend change needed:** Depends on chosen approach. Option 3 (accept limitation) needs no backend change but the document should clearly state this.

---

## What the Document Gets Right

1. **Bug fixes (B1, B2, B3)** — Correctly identified and scoped. These are real bugs confirmed in the codebase.

2. **Fabric health → `data.configured === true`** — Matches the actual backend response format `{"configured": bool, "workspace_id": str}`.

3. **Individual provision endpoints exist** — The document can leverage `POST /api/fabric/provision/lakehouse`, `/eventhouse`, `/ontology` for granular provisioning.

4. **Fabric card greyed out when not configured** — Correctly described in AddScenarioModal (Change 7). The `/query/fabric/health` endpoint returns `configured: false` when env vars are missing.

5. **Service grouping** — Placing Fabric under "Graph Backend (Optional)" is correct — it's not a core dependency.

6. **Workspace as the root entity** — The ConnectionsDrawer shows "Workspace: telecom-ws" at the top of the Fabric section, correctly establishing workspace as the container.

---

## Summary of Needed Backend Changes

| Change | Priority | Effort | Description |
|--------|----------|--------|-------------|
| **Conditional provisioning** | High | Medium | `POST /api/fabric/provision` reads scenario config to skip unneeded resources | 
| **Lakehouse data upload during provisioning** | High | High | Provision pipeline uploads CSV from scenario data dir to lakehouse |
| **Runtime Fabric config** (optional) | Low | Medium | Dynamic config reload or config store for Fabric workspace/graph model IDs |
| **Fabric connect endpoint** (optional) | Medium | Low | `POST /api/fabric/connect` to persist workspace ID without restart |
| **Upload guard for Fabric scenarios** | Medium | Low | `POST /query/upload/graph` returns helpful error (not 500) when connector is `fabric-gql`, suggesting provisioning instead |

### Must-fix vs. nice-to-have for v11

**Must-fix (block the described user flow):**
1. Conditional provisioning — without this, provisioning creates unnecessary resources
2. Upload guard — without this, Fabric graph upload crashes with `NotImplementedError`

**Nice-to-have (improve UX but not blockers):**
3. Lakehouse data upload during provisioning — without this, users must manually load data into Fabric Lakehouse
4. Runtime Fabric config — without this, initial setup requires env vars + restart
5. Fabric connect endpoint — without this, workspace ID must be set in deployment config

---

## Recommended Document Changes

### 1. Add Fabric Connection Setup UI to ConnectionsDrawer (Change 4)

Under the "not configured" state, add workspace ID input + Connect button. Reference the backend endpoint needed.

### 2. Add Lakehouses to ConnectionsDrawer Fabric Section (Change 4)

List lakehouses alongside ontologies and eventhouses.

### 3. Make "Provision Resources" Scenario-Aware (Change 4)

Show what will be provisioned based on the active scenario's `data_sources` config. If no scenario is active, offer full provisioning with an explanation.

### 4. Fix Fabric Scenario Creation Flow (User Flows section)

Replace the current "Upload tarballs" step with "Provision Fabric resources" for Fabric scenarios. Clarify that graph data goes through provisioning (lakehouse), not upload.

### 5. Hide "Graph" from Re-upload Dropdown for Fabric Scenarios (Change 3)

In the ScenarioManagerModal expanded row, the "Re-upload data ▾" dropdown should conditionally hide "Graph" when the scenario's `graph_connector` is `fabric-gql`, and show "Re-provision Fabric graph" instead.

### 6. Add Backend Tasks to Phase A (Implementation Plan)

Phase A currently has 2 tasks (bug fixes + `/api/services/health`). Add:
- Task 2b: Conditional provisioning logic in `POST /api/fabric/provision`
- Task 2c: Upload guard in `POST /query/upload/graph` for Fabric scenarios (return 400 with helpful message)

### 7. Add Upload Guard to Edge Cases Section

Add an edge case for "User tries to upload graph data to a Fabric scenario":
- Show toast: "Fabric scenarios use provisioning for graph data. Use [Provision Resources] in Connections."
- Don't crash with `NotImplementedError`
