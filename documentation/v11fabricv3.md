# V11 UI Revamp + Fabric Experience — Working Plan

> **Created:** 2026-02-16
> **Status:** 🔶 In progress — Phases B, C, D, E, F remain
> **Completed:** v11fabricprepa (bug fixes, config), v11fabricprepb (health endpoint,
> hook expansion, concurrency lock, ScenarioChip menu), v11d (AgentBar, resizable
> panels, gear removal, SettingsModal deletion)
> **UX audit:** 2026-02-16 — 10 issues identified and resolved in-doc (see below)

---

## UX Audit Summary (2026-02-16)

Key changes applied to this plan after UI/UX review:

| # | Issue | Resolution |
|---|-------|------------|
| 1 | **Phase ordering backwards** — Phase B (backend) was HIGH, Phase C (UI to trigger it) was MEDIUM. Users can't use the backend without the UI. | Phase C elevated to HIGH. C4+C6 ship alongside Phase B. |
| 2 | **ConnectionsDrawer conflated two intents** — health monitoring AND Fabric setup wizard in one drawer. | Split into **ServiceHealthPopover** (lightweight, read-only) and **FabricSetupWizard** (focused 3-step stepper modal). |
| 3 | **Too many surfaces** — user bounced between 4+ modals with no clear navigation path. | Consolidated: Wizard replaces ConnectionsDrawer+FabricSetupModal. ScenarioManagerModal simplified to list+switch. |
| 4 | **No bridge between provisioning and scenario creation** — after provisioning, user had to manually find ScenarioChip → New Scenario. | Wizard Step 3 bridges directly to AddScenarioModal with Fabric pre-selected. |
| 5 | **Graph upload "greyed out" is confusing** — disabled drop zone implies something is broken. | Replaced with positive **confirmation card**: "\u2713 Loaded from Fabric Lakehouse" |
| 6 | **EmptyState ignored Fabric** — first-time Fabric users got generic Cosmos onboarding. | Dual-path EmptyState with Cosmos and Fabric cards. Fabric-aware checklist when workspace is partially configured. |
| 7 | **Progress labels too technical** — "Finding/creating lakehouse", "Loading delta tables". | Two-layer labels: internal (logs) vs user-facing ("Setting up workspace\u2026", "Uploading graph data\u2026"). |
| 8 | **No error recovery UX** — provisioning failures showed static error, no guidance on retry. | Idempotent retry (skips completed steps). "Retry" button with explanation of what will/won't re-run. |
| 9 | **ScenarioManagerModal too dense** — inline buttons for re-upload, re-provision, Fabric re-provision cluttered every row. | Actions moved behind per-row \u22ee menu. Modal reduced from ~400 to ~280 lines. |
| 10 | **Actionable section buried** — Fabric setup buried below 5 read-only status rows in ConnectionsDrawer. | Eliminated by splitting into separate surfaces. Fabric Wizard is its own entry point. |

### Codebase incongruences fixed (second pass)

| # | Issue | Fix |
|---|-------|-----|
| 11 | **Phantom `<BindingCard>` reference** \u2014 listed as building block but doesn't exist in codebase. | Removed from building blocks. ScenarioManagerModal uses `<ModalShell>` only. |
| 12 | **`triggerProvisioning()` confused with Fabric provisioning** \u2014 D5 said "Uses `triggerProvisioning()`" for Fabric re-provisioning, but that function provisions *agents* (`/api/config/apply`), not Fabric resources. | Fixed: D5 now opens FabricSetupWizard at Step 2. Added callout box distinguishing agent vs Fabric provisioning. |
| 13 | **Wizard Step 1 unusable before Phase F** \u2014 `POST /api/fabric/connect` doesn't exist until Phase F. Step 1 had no fallback behavior specified. | Step 1 now shows env var status as read-only + guidance. Input form disabled until F2 ships. |
| 14 | **Wizard mount behavior unspecified** \u2014 no description of how Wizard determines which step to show on open. | Added mount behavior: calls `checkHealth()` + `fetchAll()`, selects step based on health state. |
| 15 | **Two `AddScenarioModal` instances** \u2014 rendered in both `App.tsx` and `ScenarioChip.tsx`. Wizard Step 3 CTA didn't specify which instance to open or how to pass `fabricPreSelected`. | Added prop threading note: lift `addModalOpen` + `fabricPreSelected` to shared state. |
| 16 | **EmptyState needed new props** \u2014 currently only accepts `{ onUpload }`, plan's Fabric-aware version needed health state, callbacks, and scenario list. | Added explicit new prop requirements block. |
| 17 | **Health endpoint location** \u2014 plan didn't specify that `/query/fabric/health` lives in `graph-query-api`, not `api/`. | Added endpoint path + service location note. |
### Final bug sweep (third pass)

| # | Issue | Fix |
|---|-------|-----|
| 18 | **`useFabricDiscovery.checkHealth()` only reads `configured`** — ignores `workspace_connected` and `query_ready` fields that the backend returns. Wizard step logic relies on these. | Documented required hook extension: parse + expose `workspaceConnected` and `queryReady` as separate state fields. Tagged as Phase C prerequisite. |
| 19 | **`consumeSSE` error handler doesn't support `retry_from`** — passes only `{ error: string }`, losing retry metadata from the error recovery payload. | Documented required SSE handler extension: widen error type to include `retry_from` and `completed` fields. Tagged as Phase B prerequisite. |
| 20 | **Duplicate line in C6** — "Add `<ServiceHealthSummary />`" appeared twice. | Removed duplicate. |
| 21 | **ModalShell `max-w-2xl` baked in** — Wizard needs wider layout but Tailwind specificity prevents simple override. | Added note: Wizard passes `className="!max-w-3xl"` (Tailwind `!important` prefix). |
---

## 1. What's Already Done

Phase A is complete. All frontend hook bugs are fixed, Fabric config is split into
two lifecycle stages (`FABRIC_WORKSPACE_CONNECTED` / `FABRIC_QUERY_READY`), discovery
endpoints gate on workspace-only, the health endpoint returns 5 fields, the upload
guard rejects graph uploads for Fabric scenarios, env template has all FABRIC_* vars,
pip dependencies are installed, the concurrency lock is in place, `fetchLakehouses()`
and `fetchKqlDatabases()` are wired into the hook, and the ScenarioChip has backend
badges and a "⊞ Manage scenarios…" item (handler not yet wired).

v11d removed the gear button, deleted SettingsModal.tsx and 3 of 4 settings/ tab files,
created AgentBar/AgentCard for agent visibility, moved HealthDot into AgentBar, added
FabricSetupModal.tsx (wraps the remaining FabricSetupTab.tsx), and wired resizable panels.

### Available building blocks

- `<ModalShell>` — modal chrome (backdrop, header, close, footer)
- `<ProgressBar>` — reusable progress bar
- `useClickOutside` — click-outside hook
- `useScenarioUpload` — upload orchestration (state machine, file slots, sequential uploads)
- `useFabricDiscovery` — Fabric workspace discovery + provisioning (health, ontologies, graph models, eventhouses, lakehouses, KQL databases, `runProvisionPipeline()`)

> **⚠ Hook gap:** `useFabricDiscovery.checkHealth()` currently only reads
> `data.configured` and exposes a single rolled-up `healthy: boolean | null`.
> The backend returns `workspace_connected` and `query_ready` but the hook
> **ignores them**. The Wizard's step-selection logic needs these fields.
> **Required fix (Phase C prerequisite):** extend `checkHealth()` to parse and
> expose `workspace_connected` and `query_ready` as separate state fields:
>
> ```ts
> const [workspaceConnected, setWorkspaceConnected] = useState<boolean | null>(null);
> const [queryReady, setQueryReady] = useState<boolean | null>(null);
> // In checkHealth:
> setHealthy(data.workspace_connected === true);
> setWorkspaceConnected(data.workspace_connected ?? false);
> setQueryReady(data.query_ready ?? false);
> ```
- `triggerProvisioning()` — shared SSE call for **agent provisioning** (`POST /api/config/apply`). NOT for Fabric resource provisioning.
- `savedScenarios` / `activeScenarioRecord` / `refreshScenarios()` / `scenariosLoading` — in ScenarioContext
- `_find_or_create()` — generic Fabric resource finder/creator in `fabric_provision.py`
- `sse_provision_stream()` — SSE wrapper for provision endpoints
- `_fabric_provision_lock` — asyncio.Lock inside `stream()` generator with fast-reject
- `acquire_fabric_token()` — shared Fabric auth in `backends/fabric.py`

> **Important distinction:** `triggerProvisioning()` provisions **agents** via
> `/api/config/apply`. Fabric **resource** provisioning uses
> `useFabricDiscovery.runProvisionPipeline()` which calls `/api/fabric/provision`.
> These are separate operations and should not be confused.

> **Note:** `<BindingCard>` does not exist yet — if needed for ScenarioManagerModal,
> it must be created as a new component.

### Current health endpoint response

**Endpoint:** `GET /query/fabric/health` (lives in `graph-query-api/router_fabric_discovery.py`,
not in the `api/` service). **Frontend caller:** `useFabricDiscovery.checkHealth()`.

```json
{
  "configured": true,
  "workspace_connected": true,
  "query_ready": false,
  "workspace_id": "...",
  "graph_model_id": null
}
```

Three UI states derive from this:

| State | Condition | Display |
|---|---|---|
| Not configured | `workspace_connected === false` | ○ "Not configured" |
| Partially ready | `workspace_connected && !query_ready` | ⚠ "Workspace connected" |
| Connected | `workspace_connected && query_ready` | ● "Connected ✓" |

---

## 2. Remaining Problems

| # | Problem | Resolution |
|---|---------|------------|
| P2 | Fabric settings only accessible when a Fabric scenario is active (chicken-and-egg). Header's "⬡ Fabric" button is conditional on `isFabricScenario`. | Phase C — Fabric Setup Wizard accessible from Header, EmptyState, and AddScenarioModal. Independent of active scenario. |
| P3 | Provision pipeline creates empty containers only — no data upload, no ontology definition, no Graph Model discovery. | Phase B — port reference scripts into `fabric_provision.py`. |
| P4 | No backend chooser in AddScenarioModal — users can't select Fabric when creating a scenario. | Phase D — backend chooser cards in AddScenarioModal. |
| P5 | No visibility into service-level health (CosmosDB, Blob, AI Search, Foundry, Fabric). HealthDot in AgentBar only shows API status. | Phase C — `GET /api/services/health` + ServiceHealthPopover (lightweight). |
| P7 | Full-screen "Validating scenario…" overlay blocks UI for up to 5s on startup. | Phase C — non-blocking startup with skeleton chip + crossfade. |
| P8 | Provisioning creates ALL Fabric resources unconditionally, ignoring what the scenario actually needs. | Phase B — conditional execution based on scenario connectors. |
| P9 | No error recovery UX — provisioning failures show a static error with no guidance on retry safety. | Phase B — idempotent retry (skip completed steps) + "Retry from step N" button. |
| P10 | EmptyState doesn't acknowledge Fabric — first-time Fabric users see identical onboarding to Cosmos users. | Phase D — Fabric-aware EmptyState with dual-path onboarding. |
| P11 | Too many surfaces — user bounces between ConnectionsDrawer, ScenarioManagerModal, AddScenarioModal, FabricSetupModal. Each context switch = cognitive load. | Consolidate: Fabric Setup Wizard (focused stepper), ServiceHealthPopover (lightweight), ScenarioManagerModal (list + switch only). |

---

## 3. Target Fabric Flow

Four phases, zero manual steps. Each gates on the previous one.
**UX principle:** every phase ends with a CTA that bridges to the next phase —
the user never has to figure out "what do I do next?".

```
PHASE 1: CONNECT
  ├── Option A: Set FABRIC_WORKSPACE_ID in azure_config.env + redeploy
  ├── Option B: Fabric Setup Wizard (Step 1) → POST /api/fabric/connect
  │     → persists to config store → runtime reload (no restart)
  ├── Gate: workspace reachable
  ├── UI: Wizard advances to Step 2
  └── Entry points: Header 🔌 button, EmptyState, AddScenarioModal disabled card

PHASE 2: DISCOVER + PROVISION (combined — user doesn't need to see these separately)
  ├── Wizard Step 2 auto-discovers existing resources on load
  ├── Shows what exists vs what needs creating (checkmarks vs empty)
  ├── Single CTA: "Set Up Resources" (or "All resources ready ✓" if already done)
  ├── Progress shows user-facing labels (not internal step names):
  │     "Setting up workspace…" → "Uploading graph data…" →
  │     "Configuring tables…" → "Building graph ontology…" →
  │     "Indexing (may take a minute)…" → "Almost done…"
  ├── Idempotent: safe to retry — skips completed steps automatically
  ├── Creates resources AND uploads data AND defines schemas
  ├── Discovers auto-created Graph Model ID → updates config
  └── Gate: FABRIC_GRAPH_MODEL_ID available

PHASE 3: CREATE SCENARIO (bridge CTA from Phase 2 completion)
  ├── Wizard Step 3: "Resources ready ✓ — Create your first Fabric scenario"
  ├── CTA opens AddScenarioModal with Fabric backend pre-selected
  ├── Graph slot replaced with confirmation card: ✓ "Graph topology loaded from Fabric Lakehouse"
  ├── Upload telemetry, runbooks, tickets, prompts normally
  └── Scenario saved with graph_connector: "fabric-gql"

PHASE 4: INVESTIGATE (automatic)
  ├── Scenario created → agents auto-provision → investigation ready
  └── No manual step — just the normal flow
```

### Conditional provisioning matrix

| `graph.connector` | `telemetry.connector` | Provisions |
|---|---|---|
| `fabric-gql` | `cosmosdb-nosql` | Workspace + Lakehouse (w/ data) + Ontology (w/ full def) |
| `fabric-gql` | `fabric-kql` | Workspace + Lakehouse + Eventhouse + Ontology |
| `cosmosdb-gremlin` | `fabric-kql` | Workspace + Eventhouse only |
| `cosmosdb-gremlin` | `cosmosdb-nosql` | Nothing — pure Cosmos, no Fabric needed |

---

## 4. Phase B: Provision Pipeline Completion

**Priority: HIGH — the biggest remaining task (~3 days)**
**File:** `api/app/routers/fabric_provision.py` (596 lines currently)

The pipeline creates empty resource containers. The reference scripts at
`fabric_implementation_references/scripts/fabric/` (~1700 lines across 3 files)
create resources **with data**. Port that logic into the SSE-streamed API endpoint.

### What to implement

**B1: Lakehouse data upload** — After `_find_or_create(... "Lakehouse" ...)`:
- `_upload_csvs_to_onelake(workspace_id, lakehouse_id)` — upload 10 CSVs via
  `DataLakeServiceClient` (ADLS Gen2 API). Source: `data/scenarios/telco-noc/data/entities/*.csv`
- `_load_delta_tables(workspace_id, lakehouse_id)` — one Lakehouse Tables API call per CSV
- Reference: `provision_lakehouse.py`

**B2: Eventhouse KQL table creation + data ingest** — After `_find_or_create(... "Eventhouse" ...)`:
- `_discover_kql_database(workspace_id, eventhouse_id)` — auto-created with Eventhouse
- `_create_kql_tables(kql_uri, db_name)` — `.create-merge table` for `AlertStream`, `LinkTelemetry`
- `_ingest_kql_data(kql_uri, db_name)` — `QueuedIngestClient` with inline fallback
- Source: `data/scenarios/telco-noc/data/telemetry/*.csv`
- Reference: `provision_eventhouse.py`

**B3: Ontology full definition** — After `_find_or_create(... "Ontology" ...)`:
- `_build_ontology_definition(workspace_id, lakehouse_id, eventhouse_id)` — 8 entity types,
  7 relationship types, static data bindings (entity → Lakehouse column mappings),
  contextualizations (relationship → junction table mappings)
- `_apply_ontology_definition(workspace_id, ontology_id, definition)` — PUT call
- Wait for ontology indexing (can take minutes)
- Reference: `provision_ontology.py` (935 lines)

**B4: Graph Model auto-discovery + config write**
- `_discover_graph_model(workspace_id, ontology_name)` — find auto-created Graph Model
- Write `FABRIC_GRAPH_MODEL_ID` to config (env file now, config store after Phase F)

**B5: Conditional execution** — Read scenario config from config store:
- `graph.connector == "fabric-gql"` → run Lakehouse + Ontology steps
- `telemetry.connector == "fabric-kql"` → run Eventhouse step
- Always create workspace

### SSE progress events

Two layers: **internal labels** (for logs/debugging) and **user-facing labels** (shown in UI).
The UI only shows the user-facing column.

| Range | Internal (logs) | User-Facing (UI) |
|-------|-----------------|-------------------|
| 0-10% | Finding/creating workspace | Setting up workspace… |
| 10-20% | Finding/creating lakehouse | Preparing data storage… |
| 20-40% | Uploading CSVs to OneLake (N files) | Uploading graph data… (N/10 files) |
| 40-45% | Loading delta tables | Configuring data tables… |
| 45-55% | Finding/creating eventhouse (if needed) | Setting up telemetry database… |
| 55-65% | Creating KQL tables + ingesting data | Loading telemetry data… |
| 65-80% | Creating ontology with full definition | Building graph ontology… |
| 80-90% | Waiting for ontology indexing | Indexing — this may take a minute… |
| 90-95% | Discovering Graph Model | Discovering graph model… |
| 95-100% | Writing config + done | Almost done… ✓ |

### Error recovery

Provisioning is **idempotent** — every step checks if the resource already exists
before creating. On failure:
1. Backend returns `{"retry_from": "step_name", "completed": ["workspace", "lakehouse", ...]}` in the error payload
2. UI shows: "Provisioning stopped at 'Building graph ontology'. Previously completed steps will be skipped."
3. CTA: **"Retry"** (not "Provision" — avoids ambiguity about whether it's safe to click)
4. On retry, pipeline fast-forwards through completed steps (progress bar jumps to resume point)

> **⚠ SSE handler gap:** `consumeSSE()` in `sseStream.ts` only extracts
> `parsed.error` as a flat string — the `onError` handler type is
> `(data: { error: string }) => void`. It does **not** read `retry_from`
> or `completed` from the error payload.
> **Required fix (Phase B prerequisite):** extend the SSE error type:
>
> ```ts
> // sseStream.ts — extend error handler
> onError?: (data: { error: string; retry_from?: string; completed?: string[] }) => void;
>
> // In consumeSSE error branch:
> handlers.onError?.({
>   error: parsed.error,
>   retry_from: parsed.retry_from,
>   completed: parsed.completed,
> });
> ```
>
> And `useFabricDiscovery.runProvisionPipeline()` must forward these
> fields to its own `provisionError` / `provisionState` so the Wizard
> can display the "Retry from step N" info.

---

## 5. Phase C: Startup + Navigation Restructure

**Priority: HIGH — the UI surface must exist before Phase B's backend is useful (~2 days)**

> **UX rationale:** Phase B builds provisioning logic, but without Phase C there's
> no accessible UI to trigger it (P2 chicken-and-egg). Ship C4 (Fabric Setup Wizard)
> and C6 (Header entry point) at minimum alongside Phase B.

### C1: Non-blocking startup
**File:** `App.tsx`

Remove the full-screen `z-[100]` "Validating scenario…" overlay. ScenarioContext
already has `savedScenarios`, `activeScenarioRecord`, `scenariosLoading`, and
`refreshScenarios()`. Use skeleton chip while loading, crossfade to null if persisted
scenario was deleted.

### C2: Skeleton chip + crossfade
**File:** `ScenarioChip.tsx`

Show a shimmer placeholder while `scenariosLoading` is true. Wire the "⊞ Manage
scenarios…" handler to open ScenarioManagerModal (Phase D).

### C3: Aggregate services health endpoint
**File:** New route (location TBD)

`GET /api/services/health` — polls real endpoints (Cosmos health, Blob health, etc.),
Fabric uses the health endpoint from BE-3. Cached 30s server-side.

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

### C4: Fabric Setup Wizard (replaces ConnectionsDrawer for Fabric)
**File:** New `FabricSetupWizard.tsx` (~350 lines)

A **focused stepper modal** (not a drawer) for the Fabric setup flow. Uses `<ModalShell>`.
3 steps — each gates on the previous one. The wizard is the **single surface** for
all Fabric configuration, replacing the overloaded ConnectionsDrawer concept.

> **ModalShell sizing:** ModalShell defaults to `max-w-2xl`. The Wizard should pass
> `className="!max-w-3xl"` (Tailwind `!important` prefix) to override. The wider
> layout accommodates the Step 2 resource checklist and progress bar comfortably.

> **Why a wizard, not a drawer?** The original ConnectionsDrawer tried to be both a
> health dashboard AND a Fabric setup flow. These are different intents with different
> audiences. Health monitoring is passive/ambient (→ popover). Fabric setup is active/
> sequential (→ wizard). Separating them reduces cognitive load.

**Entry points:** Header 🔌 button (when Fabric not ready), EmptyState Fabric card,
AddScenarioModal disabled Fabric card's "Set up Fabric" link.

```
┌───────────────────────────────────────────────────────────────┐
│  Set Up Microsoft Fabric                                 ✕  │
│                                                              │
│  ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄  │
│  ● Connect        ○ Provision        ○ Create Scenario       │
│  ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄  │
│                                                              │
│  [ Step content here — see states below ]                    │
│                                                              │
│                                              [Next →]        │
└───────────────────────────────────────────────────────────────┘
```

**Step 1: Connect** — workspace ID input + Connect button.
Calls `POST /api/fabric/connect` (Phase F). **Before Phase F ships:** Step 1
translates to a read-only status view — if `FABRIC_WORKSPACE_ID` env var is set,
show "✓ Connected via environment config" and skip to Step 2. If not set, show
guidance: "Set FABRIC_WORKSPACE_ID in azure_config.env and redeploy." The input
form activates only after Phase F ships the runtime config endpoint.
On success → auto-advance to Step 2.

```
│  STEP 1: Connect to Fabric Workspace                         │
│                                                              │
│  Workspace ID                                                │
│  ┌────────────────────────────────────────────────────┐      │
│  │  e.g. 12345678-abcd-...                            │      │
│  └────────────────────────────────────────────────────┘      │
│                                                              │
│  ⓘ Find this in your Fabric portal → Workspace settings     │
│                                                              │
│                                     [Connect & Continue →]   │
```

**Step 2: Provision** — auto-discovers existing resources on load. Shows what
exists (✓) vs what needs creating (○). Single CTA.

```
│  STEP 2: Provision Resources                                 │
│                                                              │
│    Workspace: telecom-ws                            ✓        │
│                                                              │
│    Resources needed:                                         │
│    ✓ Lakehouse          telecom-noc-lakehouse                │
│    ○ Ontology           (will be created)                    │
│    ○ Graph Model        (auto-created with ontology)         │
│    ─ Eventhouse         (not needed for this config)         │
│                                                              │
│    [Set Up Resources]                                        │
│                                                              │
│    ┌─ Progress (when running) ──────────────────────┐        │
│    │  ██████████░░░░░░  65%                          │        │
│    │  Building graph ontology…                       │        │
│    └─────────────────────────────────────────────────┘        │
│                                                              │
│    On completion: "All resources ready ✓"                    │
│                                     [Continue →]             │
```

**Step 3: Create Scenario** — bridge CTA into AddScenarioModal.

```
│  STEP 3: Create Your Fabric Scenario                         │
│                                                              │
│    ✓ Workspace connected                                     │
│    ✓ Lakehouse provisioned with graph data                   │
│    ✓ Ontology defined and indexed                            │
│    ✓ Graph Model discovered                                  │
│                                                              │
│    Everything is ready. Create a scenario to start            │
│    investigating with AI agents.                             │
│                                                              │
│                               [Create Fabric Scenario →]     │
```

Clicking the CTA closes the wizard and opens AddScenarioModal with
`selectedBackend === "fabric-gql"` pre-selected.

> **Prop threading for pre-selection:** The Wizard sets shared state (e.g. a ref
> or context flag `fabricPreSelected`) before closing. The `AddScenarioModal`
> instance in `App.tsx` reads this flag on open to initialize `selectedBackend`.
> Both `App.tsx` and `ScenarioChip.tsx` render `AddScenarioModal` — the Wizard
> should open the one in `App.tsx` (via a shared `setAddModalOpen` callback
> passed through context or lifted state).

**Re-entry behavior:** If the wizard is opened when Fabric is already fully
configured (workspace + graph model available), it opens directly to Step 3
with all checkmarks green. The user can click "Back" to review/re-provision.

**Mount behavior:** On open, the wizard calls `useFabricDiscovery.checkHealth()`
+ `fetchAll()` to populate resource lists. It determines the initial step:
- `workspaceConnected === false` → Step 1
- `workspaceConnected && !queryReady` → Step 2
- `queryReady === true` → Step 3

> These fields (`workspaceConnected`, `queryReady`) come from the extended
> `useFabricDiscovery` hook — see the hook gap note in Section 1.

### C4b: ServiceHealthPopover (lightweight status — replaces the health-dashboard side of ConnectionsDrawer)
**File:** New `ServiceHealthPopover.tsx` (~120 lines)

A **compact popover** (not a full drawer) anchored to the ServiceHealthSummary in the
Header. Read-only status list. No configuration controls — just "what's up/down".

```
┌─────────────────────────────────┐
│  Services                  ↻    │
│                                 │
│  ● CosmosDB Gremlin       ✓    │
│  ● CosmosDB NoSQL         ✓    │
│  ● Blob Storage            ✓    │
│  ● Azure AI Foundry       ✓    │
│  ● Azure AI Search        ✓    │
│  ⚠ Microsoft Fabric       ⚠    │
│    Workspace connected.         │
│    Graph Model not configured.  │
│    → Set up Fabric              │  ← link opens Wizard
│                                 │
│  Last checked: 12s ago          │
└─────────────────────────────────┘
```

The "→ Set up Fabric" link opens the Fabric Setup Wizard (C4).

### C5: ServiceHealthSummary
**File:** New `ServiceHealthSummary.tsx` (~60 lines)

Shows "5/5 Services" in Header with aggregate color. Polls `GET /api/services/health`
every 30s. Clickable → opens ServiceHealthPopover (C4b).

### C6: Update Header
**File:** `Header.tsx` (42 lines)

- Add `<ServiceHealthSummary />` (opens ServiceHealthPopover)
- Add 🔌 Fabric button (opens FabricSetupWizard) — always present in Header
  when `FABRIC_WORKSPACE_ID` is configured (env var or config store). Styled
  as a subtle icon when Fabric is fully ready (clickable → Wizard Step 3 review).
  Styled as an amber attention badge when partially ready. Hidden only when
  Fabric is completely unconfigured (no env var, no config store entry).
  EmptyState's "Connect Fabric" card covers the unconfigured case.
- Remove the conditional "⬡ Fabric" button (absorbed into the above)

Visual stack: Header → AgentBar → ProvisioningBanner → content.

---

## 6. Phase D: Scenario Creation Flow

**Priority: MEDIUM — completes Fabric scenario creation path (~1.5 days)**

### D1: ScenarioManagerModal
**File:** New `ScenarioManagerModal.tsx` (~280 lines)

Built from scratch using `<ModalShell>`. **Single responsibility:
list, switch, and delete scenarios.** Opened by ScenarioChip's "⊞ Manage scenarios…" item.

> **UX principle:** Keep the list view clean. Complex actions (re-upload, re-provision)
live behind a per-row "⋮" menu or expand-on-click detail, not inline buttons that
clutter every row.

```
┌─────────────────────────────────────────────────────────────┐
│  Manage Scenarios                                       ✕  │
│                                                             │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ ● telco-noc            Cosmos │ 18v  8p │        ⋮     ││
│  │ ○ telco-noc-fabric     Fabric │ 18v  8p │        ⋮     ││
│  │ ○ cloud-outage         Cosmos │ 12v  5p │        ⋮     ││
│  └─────────────────────────────────────────────────────────┘│
│                                                             │
│  ⋮ menu actions (per row):                                  │
│    • Switch to this scenario                                │
│    • Re-provision agents                                    │
│    • Re-upload data → (submenu: Telemetry, Runbooks, etc.)  │
│    • Re-provision Fabric resources (Fabric scenarios only)   │
│    • Delete scenario                                        │
│                                                             │
│                                        [+ New Scenario]     │
└─────────────────────────────────────────────────────────────┘
```

For Fabric scenarios, the re-upload submenu hides "Graph" (managed via Lakehouse).
For Cosmos scenarios, "Graph" appears normally. "Re-provision Fabric resources"
only appears for Fabric scenarios and opens the Fabric Setup Wizard at Step 2.

### D2: Backend chooser in AddScenarioModal
**File:** `AddScenarioModal.tsx` (514 lines)

Add "Where should graph data live?" selector before upload slots. Integrates with
`useScenarioUpload` hook.

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
└──────────────────────────────────────────────────────┘
```

Fabric card disabled when `query_ready === false`. Shows inline hint:
"Fabric not ready — [Set up Fabric →]" (link opens FabricSetupWizard).
When Fabric is selected: graph upload slot replaced with confirmation card (D3).

### D3: Replace graph upload slot with confirmation card for Fabric
**Files:** `AddScenarioModal.tsx`, `useScenarioUpload.ts`

When `selectedBackend === "fabric-gql"`, **replace** the graph file slot (don't just
grey it out — a disabled drop zone is confusing). Show a positive confirmation card:

```
┌──────────────────────────────────────────────────────┐
│  🗸 Graph Topology                                    │
│  ──────────────────────────────────────               │
│  ✓ Loaded from Fabric Lakehouse                       │
│  No upload needed — graph data is managed by Fabric.  │
└──────────────────────────────────────────────────────┘
```

This turns a "disabled" feeling into a "handled for you" feeling.

### D4: Hide Graph from re-upload dropdown for Fabric scenarios
**File:** `ScenarioManagerModal.tsx`

Check `graph_connector` on the scenario record. If `"fabric-gql"`, omit "Graph"
from the re-upload dropdown.

### D5: Re-provision Fabric Resources button
**File:** `ScenarioManagerModal.tsx`

Show for Fabric scenarios only. Opens the FabricSetupWizard at Step 2.

> **⚠ NOT `triggerProvisioning()`** — that function provisions *agents* via
> `/api/config/apply`. Fabric resource provisioning uses
> `useFabricDiscovery.runProvisionPipeline()` via `/api/fabric/provision`.

### D6: Interactive EmptyState (Fabric-aware)
**File:** `EmptyState.tsx`

Replace passive emoji steps with a **dual-path onboarding** that acknowledges both
Cosmos and Fabric users. The current EmptyState is backend-agnostic, which means
a first-time Fabric user sees no hint that they should connect a workspace first.

> **New props required:** Currently EmptyState only accepts `{ onUpload: () => void }`.
> The Fabric-aware version needs additional props:
> - `fabricHealth: { configured: boolean; workspace_connected: boolean; query_ready: boolean } | null`
>   (from `useFabricDiscovery.checkHealth()` or the services health endpoint)
> - `onFabricSetup: () => void` (opens FabricSetupWizard)
> - `savedScenarios: SavedScenario[]` (to show scenario picker in the "has scenarios" variant)
> - `onSelectScenario: (id: string) => void`

**When Fabric is partially configured** (workspace connected, not provisioned):
```
┌───────────────────────────────────────────────────────────┐
│                                                           │
│  Get started                                              │
│                                                           │
│  ⚠ Fabric workspace connected — resources not yet set up  │
│                                                           │
│  ✓ API connected                                          │
│  ✓ Workspace connected (telecom-ws)                       │
│  ○ Provision Fabric resources                             │
│  ○ Create a scenario                                      │
│  ○ Investigate with AI agents                             │
│                                                           │
│  [Set Up Fabric →]           [Or: Upload Cosmos Scenario] │
│                                                           │
└───────────────────────────────────────────────────────────┘
```

**When no backend preference is clear** (Fabric not configured):
```
┌───────────────────────────────────────────────────────────┐
│                                                           │
│  Get started                                              │
│                                                           │
│  ┌──────────────────────┐  ┌──────────────────────┐      │
│  │  📂 Upload Scenario  │  │  ⬡ Connect Fabric    │      │
│  │  CosmosDB + Blob     │  │  Graph via Lakehouse  │      │
│  │  ─────────────────   │  │  ─────────────────    │      │
│  │  Upload 5 data packs │  │  Connect workspace,   │      │
│  │  and start            │  │  provision resources  │      │
│  │  investigating.      │  │  and create scenario. │      │
│  │                      │  │                       │      │
│  │  [Get Started →]     │  │  [Connect Fabric →]   │      │
│  └──────────────────────┘  └──────────────────────┘      │
│                                                           │
└───────────────────────────────────────────────────────────┘
```

**When scenarios exist but none selected:** Show inline scenario picker + checklist
(API connected ✓, N scenarios available ✓, select scenario ○, agents provisioned ○)
with CTA button.

---

### Known constraints for Phase C+D

| Constraint | Impact | Resolution |
|------------|--------|------------|
| `AddScenarioModal` is rendered in **two places**: `ScenarioChip.tsx` and `App.tsx`. Both manage their own `open` state. | Wizard Step 3 needs to open the modal with Fabric pre-selected — must use a shared open trigger. | Lift `addModalOpen` + `fabricPreSelected` into ScenarioContext or a shared ref. Wizard sets both, `App.tsx` instance reads them. |
| `FabricSetupTab` props don't include `lakehouses` or `kqlDatabases` (though `useFabricDiscovery` hook exposes them). | The old tab only showed ontologies, graph models, and eventhouses. | FabricSetupWizard uses `useFabricDiscovery` directly — not the old tab props. All resource types available. |
| `AddScenarioModal` doesn't use `<ModalShell>` — it has its own modal chrome (backdrop, dialog, header, footer). | D2 (backend chooser) adds to this modal. Consider extracting into ModalShell for consistency, or leave as-is (it has upload-specific Escape blocking that ModalShell doesn't support). | Leave as-is for now. The Escape-during-upload blocking is important. |
| Before Phase F, `POST /api/fabric/connect` doesn't exist. | Wizard Step 1 can't actually connect a workspace at runtime. | Step 1 shows env var status as read-only. The input form is wired but disabled until F2 ships. |

---

## 7. Phase E: Polish + Cleanup

| Task | Files | Effort |
|------|-------|--------|
| E1: Modal/panel animations (framer-motion) | All modals | Low (2hr) |
| E2: Toast notification system | New utility | Medium (2hr) |
| E3: Delete `FabricSetupTab.tsx` + `FabricSetupModal.tsx` (after Wizard absorbs them) + cleanup stale refs: "SettingsModal" in `ModalShell.tsx` docstring, `sseStream.ts`, `triggerProvisioning.ts` | 5 files | Low (30min) |
| E4: Accessibility (focus trap, aria-live, keyboard nav for Wizard stepper, popover, modals) | All modals | Medium (3hr) |
| E5: Update architecture docs | docs | Low (1hr) |

---

## 8. Phase F: Full Fabric Feature Parity

**Priority: MEDIUM — completes the Fabric story (~3 days)**

### F1: Runtime Fabric config via config store
**File:** `adapters/fabric_config.py`

Currently all Fabric env vars are read once at module import time — changing a workspace
ID or Graph Model ID requires a restart. Store Fabric config in CosmosDB via the
existing config store. Read per-request with 60s TTL cache, fall back to env vars.

```python
async def get_fabric_config() -> dict:
    """Config store (cached 60s) → env var fallback."""
    ...

def invalidate_fabric_cache():
    """Force fresh read after config write."""
    ...
```

Discovery endpoints and `FabricGQLBackend` call `await get_fabric_config()` instead
of reading module-level constants.

### F2: `POST /api/fabric/connect`
**File:** New `fabric_config_api.py`

Allows FabricSetupWizard (Step 1) to connect a Fabric workspace without editing env vars.

```python
@router.post("/api/fabric/connect")
async def connect_fabric_workspace(req: FabricConnectRequest):
    # 1. Validate workspace exists (GET /workspaces/{id})
    # 2. Write to config store
    # 3. Invalidate Fabric config cache (F1)
    # 4. Return {workspace_connected: true, workspace_name: "..."}

class FabricConnectRequest(BaseModel):
    workspace_id: str
    capacity_id: str = ""
```

Also add `PUT /api/fabric/config` for updating any Fabric config value at runtime
(used by provision pipeline to write `FABRIC_GRAPH_MODEL_ID` after auto-discovery).

### F3: Workspace setup UI in FabricSetupWizard Step 1
**File:** `FabricSetupWizard.tsx`

Wire the workspace ID / capacity ID input form to `POST /api/fabric/connect`.
On success, auto-advance wizard to Step 2 (Provision).

### F4: `FabricKQLBackend` for telemetry
**File:** New `backends/fabric_kql.py` (~150 lines)

Queries Fabric Eventhouse KQL databases via Kusto REST API. Enables
`telemetry.connector: "fabric-kql"` in scenario.yaml.

```python
class FabricKQLBackend:
    async def execute_query(self, query: str, **kwargs) -> dict:
        # Endpoint: EVENTHOUSE_QUERY_URI/v1/rest/query
        # Body: {"db": kql_db_name, "csl": query}
        # Auth: DefaultAzureCredential(scope=FABRIC_SCOPE)
        ...
```

Register as `"fabric-kql"` in `backends/__init__.py`.

### F5: Telemetry router dispatch by connector type
**File:** `router_telemetry.py`

Currently always queries CosmosDB NoSQL. Add connector-aware dispatch:
1. Read `data_sources.telemetry.connector` from scenario config
2. `"fabric-kql"` → `FabricKQLBackend`
3. `"cosmosdb-nosql"` → existing CosmosDB path

### F6: KQL telemetry agent integration
**File:** `agent_provisioner.py`

Wire the telemetry spec template when `telemetry.connector == "fabric-kql"`.
`CONNECTOR_OPENAPI_VARS["fabric"]` already has the KQL language description.

### F7: Fabric Data Agent discovery
**File:** `fabric_config_api.py` or `router_fabric_discovery.py`

```python
@router.get("/api/fabric/data-agents")
async def list_fabric_data_agents():
    """Discover Data Agent items in workspace."""
    ...

@router.post("/api/fabric/data-agents/assign")
async def assign_data_agent(req: DataAgentAssignRequest):
    """Assign a Data Agent to a role (graph or telemetry)."""
    ...
```

Reference: `fabric_implementation_references/scripts/fabric/collect_fabric_agents.py`

### F8: Data Agent UI in FabricSetupWizard
**File:** `FabricSetupWizard.tsx`

Show discovered Data Agents with role assignment dropdowns in the Wizard's
Step 2 (Provision) section, below the resource list.

### F9: Provision pipeline writes config to store
**File:** `fabric_provision.py`

After F2 exists, the provision pipeline writes `FABRIC_GRAPH_MODEL_ID` to config store
via `PUT /api/fabric/config` instead of to the env file.

---

## 9. Edge Cases

| Scenario | Behavior |
|----------|----------|
| **Workspace connected, Graph Model not yet available** | ServiceHealthPopover: "⚠ Workspace connected" with "→ Set up Fabric" link. FabricSetupWizard opens at Step 2. AddScenarioModal: Fabric card disabled with "Set up Fabric →" link. Cosmos scenarios unaffected. |
| **User uploads graph data to a Fabric scenario** | `POST /query/upload/graph` checks `graph_connector → "fabric-gql"` → raises `ValueError` streamed as SSE error: "Graph topology managed via Fabric provisioning pipeline." Other uploads (telemetry, runbooks, tickets, prompts) work normally. |
| **fabric-gql + cosmosdb-nosql (primary pattern)** | Provisioning creates Lakehouse + Ontology, skips Eventhouse. Graph slot replaced with confirmation card in upload modal. Telemetry goes to CosmosDB. |
| **Fabric env vars not set at all** | Services health: Fabric = `"not_configured"` in optional group. ServiceHealthPopover shows no Fabric line (excluded from count). EmptyState shows dual-path cards. Fabric card disabled in AddScenarioModal. Ambient health: "5/5 Services". Pure CosmosDB experience. |
| **Mixed deployment (Cosmos + Fabric configured)** | Both backends active via per-request dispatch. Backend chooser shows both options. Users switch between Cosmos and Fabric scenarios freely. |
| **Persisted scenario was deleted** | App starts from localStorage (looks normal). Background validation detects missing → crossfade to null. No overlay, no spinner. |
| **Service degrades during investigation** | Ambient "5/5" updates to "4/5" (amber) on next 30s poll. Click → ServiceHealthPopover shows which service is down. No popup. |
| **Provisioning fails mid-pipeline** | Error message shows which step failed + what completed. "Retry" button resumes from failure point (idempotent). Completed steps shown as ✓. |
| **fabric-gql + fabric-kql (full Fabric)** | Provisioning creates all resources. Telemetry via `FabricKQLBackend`. Agent gets KQL language description. |
| **Dynamic config (Phase F)** | Config store (60s TTL cache) overrides env vars. `POST /api/fabric/connect` and provision auto-discovery take effect without restart. |
| **Wizard re-entry when already configured** | Opens at Step 3 with all checkmarks green. User can "Back" to review/re-provision. |

---

## 10. File Change Summary

### New (7)

| File | Phase |
|------|-------|
| `frontend/src/components/FabricSetupWizard.tsx` | C |
| `frontend/src/components/ServiceHealthSummary.tsx` | C |
| `frontend/src/components/ServiceHealthPopover.tsx` | C |
| `frontend/src/components/ScenarioManagerModal.tsx` | D |
| Backend services health endpoint (location TBD) | C |
| `graph-query-api/backends/fabric_kql.py` | F |
| `api/app/routers/fabric_config_api.py` | F |

### Heavy edits (1)

| File | Phase | Change |
|------|-------|--------|
| `fabric_provision.py` (596 lines) | B | +~800 lines: data upload, ontology def, graph model discovery, conditional execution, idempotent retry |

### Medium edits (5)

| File | Phase | Change |
|------|-------|--------|
| `AddScenarioModal.tsx` (514 lines) | D | Backend chooser cards, graph upload → confirmation card for Fabric |
| `Header.tsx` (42 lines) | C | Add ServiceHealthSummary + 🔌 Fabric button, remove "⬡ Fabric" button |
| `ScenarioChip.tsx` | C+D | Skeleton state, wire ⊞ handler to ScenarioManagerModal |
| `App.tsx` | C | Remove overlay, add crossfade |
| `router_telemetry.py` | F | Connector-aware dispatch |

### Small edits (5)

| File | Phase | Change |
|------|-------|--------|
| `adapters/fabric_config.py` | F | Dynamic config layer (config store + TTL cache) |
| `EmptyState.tsx` | D | Dual-path onboarding (Cosmos card + Fabric card) |
| `backends/__init__.py` | F | Register `fabric-kql` |
| `agent_provisioner.py` | F | KQL telemetry spec wiring |
| `useScenarioUpload.ts` | D | Fabric backend awareness (graph slot swap) |

### Delete (Phase E)

| File | Reason |
|------|--------|
| `settings/FabricSetupTab.tsx` | Absorbed by FabricSetupWizard |
| `FabricSetupModal.tsx` | Absorbed by FabricSetupWizard |
| Stale "SettingsModal" comments in `ModalShell.tsx`, `sseStream.ts`, `triggerProvisioning.ts` | Dead references |
