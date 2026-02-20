# V11 Fabric Experience — Implementation Plan

> **Status:** Phases B, C, D, E, F remain
> **Completed:** v11fabricprepa, v11fabricprepb, v11d

---

## Architecture

```
  ┌─────────────────────── PROVISIONING ────────────────────────┐
  │                                                             │
  │  Entity CSVs ──→ Lakehouse ──→ Ontology ──→ Graph Model    │
  │  (10 files)      (OneLake)    (8 entities,  (auto-created) │
  │                  (delta tbls)  7 relations)                 │
  │                                                             │
  │  Telemetry CSVs ──→ Eventhouse ──→ KQL Tables              │
  │  (2 files)          (Kusto)       (AlertStream,            │
  │                     (.ingest)      LinkTelemetry)           │
  └─────────────────────────────────────────────────────────────┘

  ┌─────────────────────── QUERYING ────────────────────────────┐
  │                                                             │
  │  GraphExplorerAgent ──→ /query/graph ──→ FabricGQLBackend   │
  │   (language_gql.md)                      POST /GraphModels/ │
  │                                          {id}/executeQuery  │
  │                                                             │
  │  TelemetryAgent ──→ /query/telemetry ──→ FabricKQLBackend   │
  │   (KQL instructions)                     KustoClient SDK    │
  │                                          → Eventhouse       │
  └─────────────────────────────────────────────────────────────┘
```

### Connector dispatch (already working)

| `scenario.yaml` connector | Backend class | Query language |
|---|---|---|
| `cosmosdb-gremlin` | `CosmosDBGremlinBackend` | Gremlin |
| `fabric-gql` | `FabricGQLBackend` | GQL (MATCH/RETURN) |
| `fabric-kql` | `FabricKQLBackend` (Phase F) | KQL |

Dispatch path: `scenario.yaml` → `config_store` → `config.py:CONNECTOR_TO_BACKEND` → `get_backend()`.

### What already works

- `FabricGQLBackend` in `graph-query-api/backends/fabric.py` — GQL → Fabric Graph Model REST API
- `agent_provisioner.py` — detects connector, swaps Gremlin↔GQL tool descriptions
- `graph_ingest.py` — rejects graph uploads when `connector == "fabric-gql"`
- `router_scenarios.py` — persists `graph_connector` field
- `config.py` — routes `fabric-gql` → `FabricGQLBackend`
- Health endpoint at `GET /query/fabric/health` returns `{ configured, workspace_connected, query_ready, workspace_id, graph_model_id }`

### What does NOT work yet

- **No `telco-noc-fabric` scenario directory** — no scenario.yaml with `fabric-gql`
- **`fabric_provision.py` creates empty containers only** — no CSV upload, no ontology definition
- **`fabric_provision.py` ignores `scenario_name`** — no data path resolution
- **Telemetry always queries Cosmos** — `router_telemetry.py` has no connector dispatch
- **Fabric provisioning is manual-only** — never auto-triggered from scenario creation
- **`useFabricDiscovery.checkHealth()` only reads `configured`** — ignores `workspace_connected` and `query_ready`
- **`consumeSSE` error handler drops retry metadata** — only passes `{ error: string }`
- **No UI entry point for Fabric setup** — Header button conditional on active Fabric scenario

---

## User Flow

```
Connect workspace → Provision resources → Create scenario → Investigate
     (Step 1)            (Step 2)             (Step 3)        (auto)
```

Entry points: Header 🔌 button, EmptyState Fabric card, AddScenarioModal "Set up Fabric" link.

---

## Phase B — Provision Pipeline

**Priority: HIGH (~3 days)**

### B0a: Create scenario data pack

**Create:** `data/scenarios/telco-noc-fabric/`

```
data/scenarios/telco-noc-fabric/
├── scenario.yaml
├── data/
│   ├── entities/     → symlink to ../telco-noc/data/entities/
│   ├── telemetry/    → symlink to ../telco-noc/data/telemetry/
│   └── prompts/      → symlink to ../telco-noc/data/prompts/
└── data/knowledge/
    ├── runbooks/      → symlink to ../telco-noc/data/knowledge/runbooks/
    └── tickets/       → symlink to ../telco-noc/data/knowledge/tickets/
```

**`scenario.yaml`** — copy `telco-noc/scenario.yaml` with these changes:

```yaml
name: telco-noc-fabric
display_name: "Australian Telco NOC — Fibre Cut (Fabric)"

data_sources:
  graph:
    connector: "fabric-gql"
    config:
      workspace_id: "${FABRIC_WORKSPACE_ID}"
      graph_model_id: "${FABRIC_GRAPH_MODEL_ID}"

  telemetry:
    connector: "cosmosdb-nosql"
    config:
      database: "telemetry"
      container_prefix: "telco-noc-fabric"

agents:
  - name: "GraphExplorerAgent"
    compose_with_connector: true    # selects language_gql.md
    # ... rest identical to telco-noc
```

### B0b: Data path resolver

**File:** `api/app/routers/fabric_provision.py`

Add helper function. All B1–B5 tasks use this to find CSVs.

```python
from pathlib import Path
import yaml

SCENARIOS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "scenarios"

def _resolve_scenario_data(scenario_name: str) -> dict:
    scenario_dir = SCENARIOS_DIR / scenario_name
    if not scenario_dir.exists():
        raise ValueError(f"Scenario directory not found: {scenario_dir}")

    manifest = yaml.safe_load((scenario_dir / "scenario.yaml").read_text())
    paths = manifest.get("paths", {})

    return {
        "entities_dir": scenario_dir / paths.get("entities", "data/entities"),
        "telemetry_dir": scenario_dir / paths.get("telemetry", "data/telemetry"),
        "manifest": manifest,
    }
```

Wire the existing `scenario_name` field in `FabricProvisionRequest` to call this resolver at the start of the provision pipeline.

### B1: Lakehouse data upload

**File:** `fabric_provision.py`  
**Reference:** `fabric_implementation_references/scripts/fabric/provision_lakehouse.py`  
**Insert after:** `_find_or_create(... "Lakehouse" ...)`

Add two functions:
- `_upload_csvs_to_onelake(workspace_id, lakehouse_id, entities_dir)` — upload all `*.csv` from `entities_dir` via `DataLakeServiceClient` (ADLS Gen2 API)
- `_load_delta_tables(workspace_id, lakehouse_id, table_names)` — one Lakehouse Tables API call per CSV to create managed delta tables

Source CSVs: 10 files in `data/scenarios/telco-noc-fabric/data/entities/`

### B2: Eventhouse data ingest

**File:** `fabric_provision.py`  
**Reference:** `fabric_implementation_references/scripts/fabric/provision_eventhouse.py`  
**Insert after:** `_find_or_create(... "Eventhouse" ...)`

Add three functions:
- `_discover_kql_database(workspace_id, eventhouse_id)` — get auto-created KQL DB
- `_create_kql_tables(kql_uri, db_name)` — `.create-merge table` for `AlertStream`, `LinkTelemetry`
- `_ingest_kql_data(kql_uri, db_name, telemetry_dir)` — `QueuedIngestClient` with inline fallback

Source CSVs: 2 files in `data/scenarios/telco-noc-fabric/data/telemetry/`

### B3: Ontology definition

**File:** `fabric_provision.py`  
**Reference:** `fabric_implementation_references/scripts/fabric/provision_ontology.py` (935 lines)  
**Insert after:** `_find_or_create(... "Ontology" ...)`

Add two functions:
- `_build_ontology_definition(workspace_id, lakehouse_id, eventhouse_id)` — 8 entity types, 7 relationship types, static data bindings, contextualizations
- `_apply_ontology_definition(workspace_id, ontology_id, definition)` — `PUT` call + wait for indexing

### B4: Graph Model discovery

**File:** `fabric_provision.py`

Add:
- `_discover_graph_model(workspace_id, ontology_name)` — find auto-created Graph Model
- Write `FABRIC_GRAPH_MODEL_ID` to env file (config store in Phase F)

### B5: Conditional execution

**File:** `fabric_provision.py`

Read `scenario_name` → resolve manifest → check connectors:
- `graph.connector == "fabric-gql"` → run B1 + B3 + B4
- `telemetry.connector == "fabric-kql"` → run B2
- Always run workspace creation

### B6: SSE error recovery

**File:** `frontend/src/utils/sseStream.ts`

Extend `SSEHandlers.onError` type:

```ts
onError?: (data: { error: string; retry_from?: string; completed?: string[] }) => void;
```

In `consumeSSE` error branch:
```ts
handlers.onError?.({
  error: parsed.error,
  retry_from: parsed.retry_from,
  completed: parsed.completed,
});
```

**File:** `frontend/src/hooks/useFabricDiscovery.ts`

Forward `retry_from` and `completed` from `onError` into `provisionError` state so the Wizard can display retry info.

### B7: Extend useFabricDiscovery health fields

**File:** `frontend/src/hooks/useFabricDiscovery.ts`

Add state + parse in `checkHealth()`:

```ts
const [workspaceConnected, setWorkspaceConnected] = useState<boolean | null>(null);
const [queryReady, setQueryReady] = useState<boolean | null>(null);

// In checkHealth():
setHealthy(data.workspace_connected === true);
setWorkspaceConnected(data.workspace_connected ?? false);
setQueryReady(data.query_ready ?? false);
```

Expose `workspaceConnected` and `queryReady` in the return object.

### SSE progress labels

| % | User-facing label |
|---|---|
| 0–10 | Setting up workspace… |
| 10–20 | Preparing data storage… |
| 20–40 | Uploading graph data… (N/10 files) |
| 40–45 | Configuring data tables… |
| 45–55 | Setting up telemetry database… |
| 55–65 | Loading telemetry data… |
| 65–80 | Building graph ontology… |
| 80–90 | Indexing — this may take a minute… |
| 90–95 | Discovering graph model… |
| 95–100 | Almost done… ✓ |

### Error recovery behavior

Every step is idempotent — checks if resource exists before creating. On failure:
1. Backend SSE error includes `retry_from` and `completed` array
2. UI shows which step failed + "Retry" button
3. On retry, pipeline skips completed steps (progress jumps to resume point)

---

## Phase C — UI Navigation

**Priority: HIGH (~2 days) — ship C4+C6 alongside Phase B**

### C1: Non-blocking startup

**File:** `frontend/src/App.tsx`

Remove the full-screen `z-[100]` "Validating scenario…" overlay. Use `scenariosLoading` from ScenarioContext to show skeleton chip while loading, crossfade to null if persisted scenario was deleted.

### C2: Skeleton chip

**File:** `frontend/src/components/ScenarioChip.tsx`

Show shimmer placeholder while `scenariosLoading === true`. Wire "⊞ Manage scenarios…" to open ScenarioManagerModal (Phase D).

### C3: Services health endpoint

**File:** New backend route (location TBD)

`GET /api/services/health` — checks Cosmos, Blob, AI Search, Foundry, Fabric. Cached 30s.

```json
{
  "services": [
    {"name": "CosmosDB Gremlin", "group": "core", "status": "connected"},
    {"name": "Microsoft Fabric", "group": "optional", "status": "partial",
     "sub_status": {"workspace": "connected", "graph_model": "not_configured"}}
  ],
  "summary": {"total": 6, "connected": 5, "partial": 1, "error": 0}
}
```

### C4: FabricSetupWizard

**File:** New `frontend/src/components/FabricSetupWizard.tsx` (~350 lines)

3-step stepper modal using `<ModalShell className="!max-w-3xl">`.

**On mount:** call `useFabricDiscovery.checkHealth()` + `fetchAll()`. Select initial step:
- `workspaceConnected === false` → Step 1
- `workspaceConnected && !queryReady` → Step 2
- `queryReady === true` → Step 3

**Step 1 — Connect:**
- Before Phase F: read-only. If `FABRIC_WORKSPACE_ID` env var is set → show "✓ Connected" → auto-skip to Step 2. If not set → show "Set FABRIC_WORKSPACE_ID in azure_config.env and redeploy."
- After Phase F: input form calls `POST /api/fabric/connect`

**Step 2 — Provision:**
- Auto-discover existing resources on load (✓ exists / ○ needs creating)
- CTA: "Set Up Resources" → calls `useFabricDiscovery.runProvisionPipeline()`
- Show progress bar with user-facing labels
- On completion: "All resources ready ✓" → "Continue →"

**Step 3 — Create Scenario:**
- Checklist summary (all ✓)
- CTA: "Create Fabric Scenario →" → closes wizard, opens AddScenarioModal with Fabric pre-selected

**Prop threading:** Lift `addModalOpen` + `fabricPreSelected` into ScenarioContext. Wizard sets both. AddScenarioModal in `App.tsx` reads them.

**Re-entry:** If already fully configured, opens at Step 3. "Back" button available to review.

### C4b: ServiceHealthPopover

**File:** New `frontend/src/components/ServiceHealthPopover.tsx` (~120 lines)

Compact popover anchored to ServiceHealthSummary. Read-only service status list. "→ Set up Fabric" link opens FabricSetupWizard.

### C5: ServiceHealthSummary

**File:** New `frontend/src/components/ServiceHealthSummary.tsx` (~60 lines)

Shows "5/5 Services" in Header. Polls `GET /api/services/health` every 30s. Click → opens ServiceHealthPopover.

### C6: Update Header

**File:** `frontend/src/components/Header.tsx`

- Add `<ServiceHealthSummary />`
- Add 🔌 Fabric button → opens FabricSetupWizard. Visible when `FABRIC_WORKSPACE_ID` is configured. Amber badge when partially ready, subtle when fully ready, hidden when unconfigured.
- Remove conditional "⬡ Fabric" button

---

## Phase D — Scenario Creation

**Priority: MEDIUM (~1.5 days)**

### D1: ScenarioManagerModal

**File:** New `frontend/src/components/ScenarioManagerModal.tsx` (~280 lines)

Uses `<ModalShell>`. Lists scenarios with per-row ⋮ menu:
- Switch to scenario
- Re-provision agents (calls `triggerProvisioning()` → `/api/config/apply`)
- Re-upload data → submenu (Telemetry, Runbooks, Tickets, Prompts; hides Graph for Fabric)
- Re-provision Fabric resources (Fabric only → opens Wizard Step 2)
- Delete scenario

Opened by ScenarioChip "⊞ Manage scenarios…".

### D2: Backend chooser in AddScenarioModal

**File:** `frontend/src/components/AddScenarioModal.tsx`

Add "Where should graph data live?" card selector before upload slots:
- **CosmosDB** card — default, always enabled
- **Fabric** card — enabled when `queryReady === true`, disabled with "Set up Fabric →" link otherwise

### D3: Graph upload → confirmation card

**Files:** `AddScenarioModal.tsx`, `frontend/src/hooks/useScenarioUpload.ts`

When `selectedBackend === "fabric-gql"`, replace the graph file slot with:
```
✓ Graph Topology — Loaded from Fabric Lakehouse
  No upload needed — graph data is managed by Fabric.
```

### D4: Hide Graph from re-upload

**File:** `ScenarioManagerModal.tsx`

If `scenario.graph_connector === "fabric-gql"`, omit "Graph" from re-upload submenu.

### D5: Re-provision Fabric button

**File:** `ScenarioManagerModal.tsx`

For Fabric scenarios: "Re-provision Fabric resources" → opens FabricSetupWizard at Step 2. Uses `runProvisionPipeline()` (NOT `triggerProvisioning()` — that's for agents).

### D6: Fabric-aware EmptyState

**File:** `frontend/src/components/EmptyState.tsx`

New props:
```ts
interface EmptyStateProps {
  onUpload: () => void;
  fabricHealth: { configured: boolean; workspace_connected: boolean; query_ready: boolean } | null;
  onFabricSetup: () => void;
  savedScenarios: SavedScenario[];
  onSelectScenario: (id: string) => void;
}
```

Three states:
1. **Fabric partially configured** — checklist + "Set Up Fabric →" CTA + "Or: Upload Cosmos Scenario" secondary
2. **No backend preference** — two cards: "Upload Scenario (Cosmos)" / "Connect Fabric"
3. **Scenarios exist, none selected** — inline scenario picker + CTA

---

## Phase E — Polish

| Task | Files | Effort |
|---|---|---|
| E1: Modal animations (framer-motion) | All modals | 2hr |
| E2: Toast notification system | New utility | 2hr |
| E3: Delete `FabricSetupTab.tsx`, `FabricSetupModal.tsx`, stale "SettingsModal" comments in `ModalShell.tsx`, `sseStream.ts`, `triggerProvisioning.ts` | 5 files | 30min |
| E4: Accessibility (focus trap, aria-live, keyboard nav) | All modals | 3hr |
| E5: Update architecture docs | docs | 1hr |

---

## Phase F — Full Fabric Parity

**Priority: MEDIUM (~3 days)**

### F1: Runtime Fabric config

**File:** `graph-query-api/adapters/fabric_config.py`

Replace module-level constants with config store reads (60s TTL cache, env var fallback):

```python
async def get_fabric_config() -> dict:
    """Config store (cached 60s) → env var fallback."""
    ...

def invalidate_fabric_cache():
    ...
```

### F2: Connect endpoint

**File:** New `api/app/routers/fabric_config_api.py`

```python
@router.post("/api/fabric/connect")
async def connect_fabric_workspace(req: FabricConnectRequest):
    # 1. Validate workspace (GET /workspaces/{id})
    # 2. Write to config store
    # 3. Invalidate cache
    # 4. Return {workspace_connected: true, workspace_name: "..."}

@router.put("/api/fabric/config")
async def update_fabric_config(req: dict):
    # Write any Fabric config key to store
    # Used by provision pipeline to write FABRIC_GRAPH_MODEL_ID
```

### F3: Wire Wizard Step 1

**File:** `FabricSetupWizard.tsx`

Wire input form to `POST /api/fabric/connect`. Auto-advance to Step 2 on success.

### F4: FabricKQLBackend

**File:** New `graph-query-api/backends/fabric_kql.py` (~150 lines)

**Reference:** `fabric_implementation_references/scripts/testing_scripts/test_kql_query.py`

```python
from azure.identity import DefaultAzureCredential
from azure.kusto.data import KustoClient, KustoConnectionStringBuilder

class FabricKQLBackend:
    def __init__(self):
        self._client: KustoClient | None = None

    def _get_client(self) -> KustoClient:
        if self._client is None:
            credential = DefaultAzureCredential()
            kcsb = KustoConnectionStringBuilder.with_azure_token_credential(
                EVENTHOUSE_QUERY_URI, credential
            )
            self._client = KustoClient(kcsb)
        return self._client

    async def execute_query(self, query: str, **kwargs) -> dict:
        import asyncio
        client = self._get_client()
        db = kwargs.get("database") or FABRIC_KQL_DB_NAME
        response = await asyncio.to_thread(client.execute, db, query)
        primary = response.primary_results[0] if response.primary_results else None
        if primary is None:
            return {"columns": [], "rows": []}

        columns = [
            {"name": col.column_name, "type": col.column_type}
            for col in primary.columns
        ]
        rows = []
        for row in primary:
            row_dict = {}
            for col in primary.columns:
                val = row[col.column_name]
                if hasattr(val, "isoformat"):
                    val = val.isoformat()
                row_dict[col.column_name] = val
            rows.append(row_dict)
        return {"columns": columns, "rows": rows}
```

Register as `"fabric-kql"` in `backends/__init__.py`.

### F5: Telemetry connector dispatch

**File:** `graph-query-api/router_telemetry.py`

Currently always uses Cosmos NoSQL. Add dispatch:
1. Read `data_sources.telemetry.connector` from scenario config
2. `"fabric-kql"` → `FabricKQLBackend`
3. `"cosmosdb-nosql"` → existing path

### F6: KQL agent integration

**File:** `scripts/agent_provisioner.py`

Wire telemetry spec template when `telemetry.connector == "fabric-kql"`. `CONNECTOR_OPENAPI_VARS["fabric"]` already has the KQL language description.

### F7: Provision writes to config store

**File:** `api/app/routers/fabric_provision.py`

After B4 discovers Graph Model ID, write via `PUT /api/fabric/config` instead of env file.

---

## Edge Cases

| Scenario | Behavior |
|---|---|
| Workspace connected, Graph Model not available | Wizard opens at Step 2. Fabric card disabled in AddScenarioModal. |
| User uploads graph data to Fabric scenario | Rejected by `graph_ingest.py` with SSE error. |
| `fabric-gql` + `cosmosdb-nosql` | Provisions Lakehouse + Ontology, skips Eventhouse. Telemetry goes to Cosmos. |
| Fabric not configured at all | Hidden from UI. Pure Cosmos experience. "5/5 Services" (Fabric excluded). |
| Mixed deployment | Both backends active. Backend chooser shows both options. |
| Persisted scenario deleted | Background validation detects → crossfade to null. No overlay. |
| Provisioning fails mid-pipeline | Shows failed step + completed steps. "Retry" skips completed. |
| Wizard re-entry when configured | Opens at Step 3. "Back" available. |

---

## File Change Summary

### New files

| File | Phase |
|---|---|
| `data/scenarios/telco-noc-fabric/` | B |
| `frontend/src/components/FabricSetupWizard.tsx` | C |
| `frontend/src/components/ServiceHealthSummary.tsx` | C |
| `frontend/src/components/ServiceHealthPopover.tsx` | C |
| `frontend/src/components/ScenarioManagerModal.tsx` | D |
| Backend services health endpoint (TBD location) | C |
| `graph-query-api/backends/fabric_kql.py` | F |
| `api/app/routers/fabric_config_api.py` | F |

### Heavy edits

| File | Phase | Change |
|---|---|---|
| `fabric_provision.py` | B | +~800 lines: path resolver, CSV upload, KQL ingest, ontology def, graph model discovery, conditional exec, idempotent retry |

### Medium edits

| File | Phase | Change |
|---|---|---|
| `AddScenarioModal.tsx` | D | Backend chooser, graph slot → confirmation card |
| `Header.tsx` | C | ServiceHealthSummary + 🔌 button, remove ⬡ button |
| `ScenarioChip.tsx` | C+D | Skeleton state, wire ⊞ handler |
| `App.tsx` | C | Remove overlay, add crossfade |
| `router_telemetry.py` | F | Connector dispatch |

### Small edits

| File | Phase | Change |
|---|---|---|
| `useFabricDiscovery.ts` | B | Expose `workspaceConnected`, `queryReady`; forward `retry_from` |
| `sseStream.ts` | B | Extend error type with `retry_from`, `completed` |
| `EmptyState.tsx` | D | New props, dual-path onboarding |
| `adapters/fabric_config.py` | F | Config store + TTL cache |
| `backends/__init__.py` | F | Register `fabric-kql` |
| `agent_provisioner.py` | F | KQL telemetry spec wiring |
| `useScenarioUpload.ts` | D | Fabric backend awareness |

### Delete (Phase E)

| File | Reason |
|---|---|
| `settings/FabricSetupTab.tsx` | Absorbed by FabricSetupWizard |
| `FabricSetupModal.tsx` | Absorbed by FabricSetupWizard |
| Stale "SettingsModal" comments in `ModalShell.tsx`, `sseStream.ts`, `triggerProvisioning.ts` | Dead references |
