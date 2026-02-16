# QOL Improvements — Implementation Plan

> **Created:** 2026-02-15
> **Last audited:** 2026-02-15 (including UX audit)
> **Status:** 🟡 In Progress
> **Goal:** Six quality-of-life improvements to speed up loading, improve observability,
> enhance graph interaction, track investigation history, and eliminate runtime ARM
> delays by pre-creating core databases at infrastructure provisioning time.
>
> **UX audit scope:** User experience, interaction design, visual polish, and intuitive feel.
> Cross-referenced the implementation plan against the live frontend codebase
> (App.tsx, MetricsBar, AddScenarioModal, GraphCanvas, InvestigationPanel, DiagnosisPanel,
> Header, styles, animation patterns) to identify gaps and propose improvements.

---

## Requirements (Original)

1. Topologies are currently added as new items in networkgraph db in cosmos-gremlin. Telemetry and prompts should go to a telemetry db and prompts db in cosmos gremlin nosql and be instantiated in scenario specific containers. This will speed up loading time
2. Scenario upload should have a timer so users can time the progress
3. Can we have the graph api container logs stream to a third pane in the header? Currently we have graph topology and fabric container log stream in there. Let's get the graph API log stream there too.
4. Can we have a graph pause/unpause so that it stops moving whenever mouse over it? May have to check custom_skills/react-force-graph-2d for details
5. Lets have a sidebar on the right side to track interactions. Those interactions should be saved and retrieved and stored in cosmosdb-gremlin-nosql in a db called interactions. Timestamps and scenario name displayed along with the query used. When clicked on, the steps and final diagnosis should be displayed in the main UI.
6. Let's create all the core DBs we will need in bicep, at azure provisioning stage, if we can. So we don't have to reinstantiate them.

---

## Implementation Status

| Phase | Status | Scope |
|-------|--------|-------|
| **Phase 1:** Pre-create Core DBs in Bicep | ✅ Done | `cosmos-gremlin.bicep` |
| **Phase 2:** Per-Scenario Containers (Shared DBs) | ✅ Done | `router_ingest.py`, `router_prompts.py`, `router_telemetry.py`, `router_scenarios.py`, `config.py`, `types/index.ts` |
| **Phase 3:** Upload Timer | ✅ Done | `AddScenarioModal.tsx` |
| **Phase 4:** Graph API Log Stream in MetricsBar | ✅ Done | `MetricsBar.tsx`, `TabbedLogStream.tsx`, `main.py` (graph-query-api) |
| **Phase 5:** Graph Pause/Unpause on Mouseover | ✅ Done | `GraphCanvas.tsx`, `GraphTopologyViewer.tsx`, `GraphToolbar.tsx` |
| **Phase 6:** Interaction History Sidebar | ✅ Done | `router_interactions.py`, `models.py`, `useInteractions.ts`, `InteractionSidebar.tsx`, `App.tsx`, `types/index.ts`, `cosmos-gremlin.bicep` |

---

## Table of Contents

- [Codebase Conventions & Routing Context](#codebase-conventions--routing-context)
- [Overview of Changes](#overview-of-changes)
- [Item 1: Per-Scenario Containers in Shared DBs](#item-1-per-scenario-containers-in-shared-dbs)
- [Item 2: Upload Timer](#item-2-upload-timer)
- [Item 3: Graph API Log Stream in MetricsBar](#item-3-graph-api-log-stream-in-metricsbar)
- [Item 4: Graph Pause/Unpause on Mouseover](#item-4-graph-pauseunpause-on-mouseover)
- [Item 5: Interaction History Sidebar](#item-5-interaction-history-sidebar)
- [Item 6: Pre-Create Core DBs in Bicep](#item-6-pre-create-core-dbs-in-bicep)
- [Implementation Phases](#implementation-phases)
- [File Change Inventory](#file-change-inventory)
- [Cross-Cutting UX Gaps](#cross-cutting-ux-gaps)
- [UX Priority Matrix](#ux-priority-matrix)
- [Edge Cases & Validation](#edge-cases--validation)
- [Migration & Backwards Compatibility](#migration--backwards-compatibility)

---

## Codebase Conventions & Routing Context

> **Read this section first** if you are implementing any phase below. These
> conventions are load-bearing — ignoring them will cause import errors, routing
> failures, or mismatched data.

### Request Routing

| URL prefix | Proxied to | Config |
|------------|-----------|--------|
| `/api/*` | API service on port **8000** | `vite.config.ts` L21-31 (dev), `nginx.conf` `/api/` block (prod) |
| `/query/*` | graph-query-api on port **8100** | `vite.config.ts` L44-53 (dev), `nginx.conf` `/query/` block (prod) |

Both proxy configs include SSE-compatible settings (`proxy_buffering off`,
`proxy_cache off`, SSE response headers). New routes under either prefix
automatically inherit this routing — **no proxy or nginx changes needed**.

### Scenario Naming

| Concept | Example | Where stored |
|---------|---------|-------------|
| **Base scenario name** | `"telco-noc"` | `ScenarioContext.activeScenario`, `localStorage`, interaction `scenario` field |
| **Graph name** | `"telco-noc-topology"` | Derived as `${name}-topology`, sent as `X-Graph` header |
| **Prefix extraction** | `"telco-noc"` | Backend: `graph_name.rsplit("-", 1)[0]` in `config.py` |

Upload endpoints (`router_ingest.py`) receive scenario names from the upload form's
`scenario_name` query param (or `scenario.yaml` manifest `name` field) — **not** from
the `X-Graph` header. The `X-Graph` header is used only for read-time query routing
via `ScenarioContext`.

### Frontend Import Conventions

The project aliases `react-resizable-panels` exports:

```tsx
import { Group as PanelGroup, Panel, Separator as PanelResizeHandle }
  from 'react-resizable-panels';
```

Follow this aliasing pattern in all new code. **Do not** import `PanelGroup` or
`PanelResizeHandle` directly — they are not the library's actual export names.

### CSS Resize Handles

| Class | Direction | Cursor | Used In |
|-------|-----------|--------|---------|
| `metrics-resize-handle` | Horizontal (col) | `col-resize` | `MetricsBar.tsx` — between panels |
| `vertical-resize-handle` | Vertical (row) | `row-resize` | `App.tsx` — between MetricsBar and content |

Both defined in `frontend/src/styles/globals.css`.

### SSE Event Format

Both backend log endpoints emit SSE events with `event: log`:
- API (port 8000): `api/app/routers/logs.py` — `yield {"event": "log", "data": ...}`
- Graph API (port 8100): `graph-query-api/main.py` — `yield f"event: log\ndata: ...\n\n"`

The `LogStream` component listens via `addEventListener('log', ...)` — **not**
`onmessage`. Any new SSE log endpoint must use the `event: log` naming to be picked up.

---

## Overview of Changes

| # | Item | Category | Impact | Effort |
|---|------|----------|--------|--------|
| 1 | Per-scenario containers in shared DBs | Backend (data architecture) | High — eliminates ~20-30s ARM delays per upload | Large |
| 2 | Upload timer | Frontend (UX) | Medium — user timing feedback | Small |
| 3 | Graph API log stream in MetricsBar | Frontend + backend (observability) | Medium — graph-query-api visibility | Small |
| 4 | Graph pause/unpause on mouseover | Frontend (graph interaction) | Medium — usability improvement | Small |
| 5 | Interaction history sidebar | Full-stack (new feature) | High — investigation persistence + history | Large |
| 6 | Pre-create core DBs in Bicep | Infrastructure (IaC) | High — eliminates runtime ARM DB creation | Medium |

### Dependency Graph

```
Phase 1 (Bicep DBs) ──┐
                       ├──▶ Phase 2 (Shared DBs) ──▶ Phase 6 (Interactions — needs interactions DB)
Phase 3 (Timer)        │
Phase 4 (Log Stream)   │    (independent)
Phase 5 (Graph Pause)  │    (independent)
```

Phases 1 and 2 are coupled: the Bicep changes create the databases that the shared-DB
refactor relies on. Phases 3, 4, and 5 are fully independent and can be done in any order.
Phase 6 (interaction sidebar) depends on Phase 1 (the `interactions` database must exist).

### UX Audit — Key Findings

The implementation plan is architecturally thorough and well-phased. The following
UX gaps were identified by cross-referencing each feature against its user-facing
behavior — micro-interactions, feedback loops, visual cues, and edge-case behaviors
that determine whether a feature feels polished or rough:

| Area | Finding | Severity |
|------|---------|----------|
| Upload Timer | Good foundation but missing ETA, per-step timing, and completion celebration | Medium |
| Log Stream 3-Panel | 3 equal panels will crowd the 36% right side; needs tabs or smart layout | High |
| Graph Pause | Mouse-leave resume is too abrupt; needs visual indicator and manual override | Medium |
| Interaction Sidebar | Missing search, empty state guidance, loading skeleton, and keyboard nav | Medium |
| Global | No toast/notification system for transient feedback | Medium |
| Global | Investigation/Diagnosis horizontal split is not resizable (hard `w-1/2`) | Low |
| Global | No keyboard accessibility for graph interactions | Low |
| Global | Final diagnosis appears all-at-once instead of streaming | Medium |

UX enhancements are integrated into each item below. See also [Cross-Cutting UX Gaps](#cross-cutting-ux-gaps) and [UX Priority Matrix](#ux-priority-matrix) at the end.

---

## Item 1: Per-Scenario Containers in Shared DBs

### Current State

Today, each scenario upload creates **new Cosmos NoSQL databases** via ARM management plane calls:

| Data Type | Current Resource | Created By |
|-----------|-----------------|------------|
| Telemetry | Database `{name}-telemetry` with per-container definitions | `router_ingest.py` `upload_telemetry` → `_ensure_nosql_db_and_containers()` |
| Prompts | Database `{name}-prompts`, container `prompts` (PK `/agent`) | `router_prompts.py` `_get_prompts_container()` |
| Scenarios | Database `scenarios`, container `scenarios` (PK `/id`) | `router_scenarios.py` `_get_scenarios_container()` |

**Problem:** ARM `begin_create_update_sql_database()` takes **20-30 seconds** per database.
Uploading a new scenario triggers 2 ARM creations (telemetry DB + prompts DB), adding
40-60 seconds of overhead. With 3 scenarios, that's 6 separate databases in the NoSQL
account — excessive when only a small amount of data per scenario exists.

The `scenarios` router already follows the correct pattern: one shared database with
one shared container.

### Target State

Use **shared databases** with **per-scenario containers**:

| Data Type | New Resource | Container Naming | Partition Key |
|-----------|-------------|-----------------|---------------|
| Telemetry | Shared DB `telemetry` | `{name}-AlertStream`, `{name}-PerformanceMetrics`, etc. | `/id` (same as today) |
| Prompts | Shared DB `prompts` | `{name}` (one container per scenario) | `/agent` (same as today) |
| Scenarios | Shared DB `scenarios` (unchanged) | `scenarios` (unchanged) | `/id` (unchanged) |

**Benefits:**
- No ARM database creation at upload time — databases pre-exist from Bicep (see Item 6)
- Only ARM **container** creation, which is faster (~5-10s vs 20-30s for database creation)
- Fewer total resources in the Cosmos account
- Clearer resource organization

### Backend Changes

#### `config.py` — ScenarioContext Update

The `ScenarioContext` currently derives `telemetry_database` from the graph name:

```python
# Current (line 100):
telemetry_db = f"{prefix}-telemetry"
```

**Change to** use the shared database name, with a new field for the container prefix:

```python
@dataclass
class ScenarioContext:
    graph_name: str              # e.g. "cloud-outage-topology"
    gremlin_database: str        # "networkgraph" (unchanged)
    telemetry_database: str      # "telemetry" (now ALWAYS the shared DB name)
    telemetry_container_prefix: str  # "cloud-outage" (NEW — used to find containers)
    prompts_database: str        # "prompts" (NEW — shared DB name)
    prompts_container: str       # "cloud-outage" (NEW — per-scenario container name)
    backend_type: GraphBackendType

def get_scenario_context(
    x_graph: str | None = Header(default=None, alias="X-Graph"),
) -> ScenarioContext:
    graph_name = x_graph or COSMOS_GREMLIN_GRAPH
    # Derive scenario prefix: "cloud-outage-topology" → "cloud-outage"
    # IMPORTANT: graph names MUST follow the "{scenario}-topology" convention.
    # If no hyphen exists, fall back to the full graph_name to avoid empty
    # prefixes which would produce invalid container names (e.g., "-AlertStream").
    prefix = graph_name.rsplit("-", 1)[0] if "-" in graph_name else graph_name

    return ScenarioContext(
        graph_name=graph_name,
        gremlin_database=COSMOS_GREMLIN_DATABASE,
        telemetry_database="telemetry",           # shared DB
        telemetry_container_prefix=prefix,         # scenario prefix for container lookup
        prompts_database="prompts",                # shared DB
        prompts_container=prefix,                  # scenario container name
        backend_type=GRAPH_BACKEND,
    )
```

#### `router_ingest.py` — Telemetry Upload Changes

**Current pattern** (`upload_telemetry`, ~line 873):
1. ARM: `begin_create_update_sql_database("{name}-telemetry")`
2. ARM: `begin_create_update_sql_container(...)` per container in `scenario.yaml`
3. Data plane: `upsert_item()` into each container

**New pattern:**
1. ~~ARM: create database~~ — **skip** (database `telemetry` pre-exists from Bicep)
2. ARM: `begin_create_update_sql_container("{name}-{container_name}")` — container name
   is now prefixed with the scenario name (e.g., `cloud-outage-AlertStream`)
3. Data plane: `upsert_item()` into `cloud-outage-AlertStream`, etc.

```python
# Old:
db_name = f"{scenario_name}-telemetry"
_ensure_nosql_db_and_containers(db_name, containers, emit)

# New:
db_name = "telemetry"   # shared DB — pre-created by Bicep
# Container names prefixed: "cloud-outage-AlertStream", "cloud-outage-PerformanceMetrics"
prefixed_containers = {f"{scenario_name}-{k}": v for k, v in containers.items()}
_ensure_nosql_containers(db_name, prefixed_containers, emit)
```

The `_ensure_nosql_db_and_containers()` function should be refactored into two parts:
- `_ensure_nosql_db(db_name)` — creates database if not exists (kept for backwards compat,
  but skipped when targeting the shared `telemetry` DB which already exists)
- `_ensure_nosql_containers(db_name, containers, emit)` — creates containers only

> **⚠️ Implementation note:** `_ensure_nosql_db_and_containers` is currently a **nested
> function** defined inside `upload_telemetry`'s `run()` coroutine (~line 915), not a
> module-level function. The refactoring must first **extract it** from the closure into
> a module-level helper (or two helpers) before splitting. The nested function closes
> over `cosmos_mgmt_client` and the NoSQL account name — those must be passed as
> parameters to the extracted functions.

#### `router_telemetry.py` — Query Changes

**Current:** Queries use `ctx.telemetry_database` (e.g., `cloud-outage-telemetry`) as
the database name and the container name from the request body (e.g., `AlertStream`).

**New:** Database is always `telemetry`. Container name becomes
`{ctx.telemetry_container_prefix}-{request.container_name}` (e.g., `cloud-outage-AlertStream`).

```python
# Old:
db = client.get_database_client(ctx.telemetry_database)
container = db.get_container_client(req.container_name)

# New:
db = client.get_database_client("telemetry")
container_name = f"{ctx.telemetry_container_prefix}-{req.container_name}" if ctx.telemetry_container_prefix else req.container_name
container = db.get_container_client(container_name)
```

#### `router_prompts.py` — Prompts Changes

**Current:** Each scenario gets its own database `{scenario}-prompts` with a `prompts` container.

**New:** All scenarios share the `prompts` database. Each scenario gets its own container
named `{scenario}` with PK `/agent`.

```python
# Old:
def _db_name_for_scenario(scenario: str) -> str:
    return f"{scenario}-prompts"

def _get_prompts_container(scenario: str, *, ensure_created: bool = True):
    db_name = _db_name_for_scenario(scenario)
    # ARM: create database db_name
    # ARM: create container "prompts" in db_name
    # Return container client for "prompts"

# New:
PROMPTS_DB = "prompts"

def _get_prompts_container(scenario: str, *, ensure_created: bool = True):
    # Database "prompts" pre-exists from Bicep — no ARM database creation needed
    # ARM: create container "{scenario}" in "prompts" DB (if ensure_created)
    # Return container client for "{scenario}"
```

**Container cache key changes:** Currently keyed by `f"{db_name}:{container_name}"`.
New key: `f"prompts:{scenario}"` (since DB is now always `prompts`).

#### `router_scenarios.py` — No Structural Change

The scenarios router already uses a shared `scenarios` database with a `scenarios`
container. No structural change needed. Only update: skip the ARM database creation
call since the `scenarios` database will be pre-created by Bicep (Item 6).

```python
# Old (in _get_scenarios_container):
# ARM: begin_create_update_sql_database("scenarios")  ← 20-30s on first call

# New:
# Database "scenarios" pre-exists from Bicep — skip ARM creation
# Only create container "scenarios" if it doesn't exist (fast, ~5s)
```

### Frontend Changes

#### `ScenarioContext.tsx`

Remove the `telemetry_database` derivation from the scenario name. The shared DB name
is constant (`telemetry`), so no frontend change is needed for the database routing —
this is entirely backend-driven via `X-Graph` header → `ScenarioContext` in `config.py`.

#### `types/index.ts` — `SavedScenario.resources`

Update the `resources` field in `SavedScenario` to reflect shared DBs.

> **⚠️ Backwards compatibility:** New fields MUST be optional (`?`) because existing
> scenario documents in Cosmos were saved without them. The backend should populate
> defaults when reading old documents (derive `telemetry_container_prefix` and
> `prompts_container` from the graph name using the same `rsplit` logic).

```typescript
resources: {
  graph: string;                     // "cloud-outage-topology" (unchanged)
  telemetry_database: string;        // "telemetry" (was "cloud-outage-telemetry")
  telemetry_container_prefix?: string; // "cloud-outage" (NEW — optional for back-compat)
  runbooks_index: string;            // unchanged
  tickets_index: string;             // unchanged
  prompts_database: string;          // "prompts" (was "cloud-outage-prompts")
  prompts_container?: string;        // "cloud-outage" (NEW — optional for back-compat)
};
```

### Naming Convention Update

| Data Type | Old Name | New Name |
|-----------|---------|---------|
| Telemetry DB | `cloud-outage-telemetry` | `telemetry` (shared) |
| Telemetry containers | `AlertStream`, `PerformanceMetrics` | `cloud-outage-AlertStream`, `cloud-outage-PerformanceMetrics` |
| Prompts DB | `cloud-outage-prompts` | `prompts` (shared) |
| Prompts container | `prompts` | `cloud-outage` |
| Scenarios DB | `scenarios` (unchanged) | `scenarios` (unchanged) |
| Scenarios container | `scenarios` (unchanged) | `scenarios` (unchanged) |

---

## Item 2: Upload Timer

### Current State

`AddScenarioModal.tsx` (620 lines) tracks upload progress via `overallPct` (0-100)
and `currentUploadStep` (text label), but has **no elapsed time display**. Users cannot
gauge how long the upload has been running or estimate completion time.

The `useInvestigation` hook already implements this pattern for investigations:
`startTimeRef.current = Date.now()` + elapsed calculation at completion (line 37).

### Target State

A running timer displayed in the upload progress section:

```
┌──────────────────────────────────────────────────────────────┐
│ Saving Scenario: cloud-outage                                │
│─────────────────────────────────────────────────────────────│
│                                                              │
│  ✓ Graph Data ····················· 42 vertices, 68 edges   │
│  ◉ Runbooks ······ ■■■■■■■□□□ 65% Creating search index...  │
│  ○ Tickets ······················· Waiting                   │
│  ○ Prompts ······················· Waiting                   │
│                                                              │
│  Overall: 2 of 5 ■■■■■■■■■■■□□□□ 40%   ⏱ 1m 23s            │
│                                                              │
│  [Cancel]                                                    │
└──────────────────────────────────────────────────────────────┘

After completion:
│  ✓ All uploads complete                    Total: 3m 47s     │
```

### Implementation

**Changes to `AddScenarioModal.tsx` only:**

1. **Add state/refs:**
```typescript
const uploadStartRef = useRef<number>(0);
const [elapsedSeconds, setElapsedSeconds] = useState(0);
const timerIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
```

2. **Start timer when upload begins** (in the `handleSave` function, **after** validation
   passes but **before** the first upload call). This avoids counting validation time —
   place the timer start after the early-return checks in `handleSave`, not at the top:
```typescript
// Place AFTER validation checks (e.g., file presence, name uniqueness) pass:
uploadStartRef.current = Date.now();
setElapsedSeconds(0);
timerIntervalRef.current = setInterval(() => {
  setElapsedSeconds(Math.floor((Date.now() - uploadStartRef.current) / 1000));
}, 1000);
```

3. **Stop timer on completion/error/cancel:**
```typescript
if (timerIntervalRef.current) {
  clearInterval(timerIntervalRef.current);
  timerIntervalRef.current = null;
}
// Final elapsed time stays displayed
```

4. **Cleanup on unmount:**
```typescript
useEffect(() => {
  return () => {
    if (timerIntervalRef.current) clearInterval(timerIntervalRef.current);
  };
}, []);
```

5. **Format and render:**
```typescript
function formatElapsed(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return m > 0 ? `${m}m ${s.toString().padStart(2, '0')}s` : `${s}s`;
}

// In the JSX progress section:
<span className="text-xs text-text-muted ml-auto">
  ⏱ {formatElapsed(elapsedSeconds)}
</span>
```

### UX Enhancements for Upload Timer

#### 2a. Per-Slot Timing

The plan shows elapsed time at the overall level only. Each file slot (graph, telemetry,
runbooks, tickets, prompts) can take wildly different durations. Show per-slot elapsed
time beside the slot's progress bar:

```
✓ Graph Data ················ 42 vertices, 68 edges     12s
◉ Runbooks ···· ■■■■■■■□□□ 65% Creating search index   1m 04s ← running
○ Tickets ····················· Waiting                  —
```

**Implementation:** Track `slotStartTime` in the `FileSlot` data structure. When upload
begins for a slot, record `Date.now()`. When it completes/errors, freeze the elapsed
time. The running slot shows a live counter; completed slots show their final duration.

**Why:** Users regularly report that "runbooks" is the slowest step. Per-slot timing
confirms which steps are bottlenecks and sets better expectations for future uploads.

#### 2b. Estimated Time Remaining

After the first slot completes, calculate a rough ETA based on the proportion of
`overallPct` achieved:

```
Overall: 2 of 5 ■■■■■■■■■□□□□□□ 40%   ⏱ 1m 23s   ~2m remaining
```

**Formula:** `eta = elapsed × (100 - pct) / pct`. Only show after `pct > 10%` to avoid
wild early estimates. Update ETA every 5 seconds (not every second — prevents jitter).

**Why:** A timer alone tells users "how long so far" but not "how much longer." An ETA
reduces anxiety during the 3-5 minute first-time uploads.

#### 2c. Completion Celebration Moment

**Enhancement:** Add a brief "success moment" before auto-close:
1. Timer stops → final elapsed time fades from normal to `text-status-success`
2. A subtle pulse animation on the overall progress bar (CSS `animate-pulse`
   with `bg-status-success` for 1 second)
3. Hold the modal open for **2.5 seconds** instead of 1.5 — let users register
   the final time

**Why:** Users invest 3-5 minutes watching this modal. A dismissive instant close
feels abrupt. The existing `framer-motion` spring pattern (`stiffness: 400,
damping: 17`) can be applied to the completion bar for visual cohesion.

#### 2d. Timer Visual Hierarchy

Place the timer right-aligned on the same line as the overall progress, using
the `text-text-muted` style initially, then `text-text-secondary` after 30 seconds.
Use `font-mono tabular-nums` so the timer digits don't cause layout shifts as they
change (e.g., "9s" → "10s" won't cause the surrounding text to jump):

```tsx
<div className="flex items-center justify-between mt-3">
  <span className="text-xs text-text-secondary">
    Overall: {completedSlots} of {totalSlots}
  </span>
  <span className={`text-xs font-mono tabular-nums ${
    elapsedSeconds > 30 ? 'text-text-secondary' : 'text-text-muted'
  }`}>
    ⏱ {formatElapsed(elapsedSeconds)}
  </span>
</div>
```

---

## Item 3: Graph API Log Stream in MetricsBar

### Current State

`MetricsBar.tsx` renders a 2-panel horizontal split:
1. **Panel 1 (64%):** `<GraphTopologyViewer>` — force-directed graph
2. **Panel 2 (36%):** `<LogStream url="/api/logs" title="API" />` — API (:8000) logs

The `LogStream` component is fully reusable — it accepts `url` and `title` props.

**Problem:** The graph-query-api (:8100) also has an SSE log endpoint at
`GET /api/logs`, but it's **shadowed by nginx routing**: nginx sends all `/api/*`
requests to port 8000 (the API service). The graph-query-api logs are only reachable
directly at `:8100/api/logs` in local dev, and are completely inaccessible through
nginx in production.

### Target State

Three panels in MetricsBar:
1. **Graph topology viewer** (50%)
2. **API log stream** (25%) — existing `/api/logs` from port 8000
3. **Graph API log stream** (25%) — new route `/query/logs` from port 8100

```
┌─────────────────────────────┬──────────────┬──────────────┐
│                             │  API Logs    │ Graph API    │
│    Graph Topology           │  (port 8000) │ Logs         │
│    Viewer                   │              │ (port 8100)  │
│                             │              │              │
└─────────────────────────────┴──────────────┴──────────────┘
```

### Implementation

#### 1. Graph-query-api: New Route `/query/logs`

The graph-query-api already has the SSE log infrastructure (`_log_sse_generator`,
`_SSELogHandler`, subscriber queue, ring buffer) — it's just exposed at `/api/logs`
which nginx shadows. **Add a duplicate route at `/query/logs`:**

```python
# graph-query-api/main.py — add alongside existing /api/logs route:

@app.get("/query/logs", summary="Stream graph-query-api logs via SSE (nginx-accessible)")
async def stream_logs_query_route():
    """Alias for /api/logs that's accessible through nginx's /query/* routing."""
    return StreamingResponse(
        _log_sse_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

This route goes through nginx's `/query/` location block → port 8100, avoiding the
`/api/` → port 8000 shadow.

#### 2. MetricsBar: Add Third Panel

```tsx
// frontend/src/components/MetricsBar.tsx

return (
  <div className="h-full px-6 py-3">
    <PanelGroup className="h-full">
      {/* Graph topology viewer */}
      <Panel defaultSize={50} minSize={20}>
        <div ref={graphPanelRef} className="h-full px-1">
          <GraphTopologyViewer width={graphSize.width} height={graphSize.height} />
        </div>
      </Panel>

      <PanelResizeHandle className="metrics-resize-handle" />

      {/* API logs (port 8000) */}
      <Panel defaultSize={25} minSize={10}>
        <div className="h-full px-1">
          <LogStream url="/api/logs" title="API" />
        </div>
      </Panel>

      <PanelResizeHandle className="metrics-resize-handle" />

      {/* Graph API logs (port 8100, via /query/logs) */}
      <Panel defaultSize={25} minSize={10}>
        <div className="h-full px-1">
          <LogStream url="/query/logs" title="Graph API" />
        </div>
      </Panel>
    </PanelGroup>
  </div>
);
```

#### 3. Vite Dev Proxy & nginx: No Changes Needed

The existing `/query` proxy in `vite.config.ts` already routes to `:8100` with SSE
support headers. The `/query/logs` path matches this prefix — **no change needed**.

The existing nginx `/query/` location block already has `proxy_buffering off` and
`proxy_cache off` for SSE support. The new `/query/logs` route will be handled
correctly by the existing config.

> **SSE event format:** Both backends (port 8000 `api/app/routers/logs.py` and port
> 8100 `graph-query-api/main.py`) emit SSE events with `event: log`. The `LogStream`
> component listens via `addEventListener('log', ...)` — NOT `onmessage`. The new
> `/query/logs` endpoint uses the same `_log_sse_generator()` which already emits
> `event: log`, so `LogStream` will receive events correctly with no changes.

### UX Enhancement: Tabbed Log Viewer Alternative

#### Layout Concern

The 50% / 25% / 25% split may crowd the log panels. On a 1920px screen, each log
panel gets roughly 480px — acceptable. But on a 1440px laptop, each panel gets 360px
— tight for log lines with long container names, timestamps, and JSON payloads.

#### Proposed Alternative: Tabs Instead of Side-by-Side

Instead of two narrow side-by-side log panels, use a **single log panel with tabs**:

```
┌──────────────────────────────────────┬─────────────────────┐
│                                      │ [API] [Graph API]   │
│    Graph Topology                    │ ──────────────────  │
│    Viewer                            │ 14:31:14 INFO ...   │
│                                      │ 14:31:15 DEBUG ...  │
│                                      │ 14:31:16 INFO ...   │
└──────────────────────────────────────┴─────────────────────┘
```

**Benefits:**
- Log panel retains its full 36% width — no cramping
- Tabs are a familiar pattern (VS Code terminal tabs, browser tabs)
- Users typically focus on one log stream at a time — side-by-side comparison is rare

**Implementation:**

```tsx
// New component: TabbedLogStream.tsx
interface TabbedLogStreamProps {
  streams: Array<{ url: string; title: string }>;
}

function TabbedLogStream({ streams }: TabbedLogStreamProps) {
  const [activeTab, setActiveTab] = useState(0);

  return (
    <div className="h-full flex flex-col">
      {/* Tab bar */}
      <div className="flex border-b border-white/10 px-2">
        {streams.map((s, i) => (
          <button
            key={s.url}
            onClick={() => setActiveTab(i)}
            className={`px-3 py-1.5 text-xs font-medium transition-colors ${
              activeTab === i
                ? 'text-brand border-b-2 border-brand'
                : 'text-text-muted hover:text-text-secondary'
            }`}
          >
            {s.title}
          </button>
        ))}
      </div>

      {/* Active log stream — keep all mounted for SSE continuity */}
      <div className="flex-1 min-h-0 relative">
        {streams.map((s, i) => (
          <div
            key={s.url}
            className={i === activeTab ? 'h-full' : 'hidden'}
          >
            <LogStream url={s.url} title={s.title} />
          </div>
        ))}
      </div>
    </div>
  );
}
```

**Critical detail:** All `LogStream` instances stay mounted (using `hidden` instead of
conditional rendering) so their SSE connections remain active and logs accumulate in
the background. Switching tabs is instant with no reconnect delay.

#### Alternative: Collapsible 3-Panel

If three panels are preferred for at-a-glance comparison, add a **collapse/expand**
toggle so users can hide the log panels entirely, giving the graph 100% width:

```
[Graph ▼] [API Logs ▼] [Graph API ▼]   ← panel headers with collapse toggles
```

#### Unread Indicator on Inactive Tab

When using tabs, add a subtle dot or count badge on the inactive tab to indicate
new log entries arrived while the user was looking at the other stream:

```
[API (3)] [Graph API ●]
```

Clear the indicator when the user switches to that tab. This prevents the "did I miss
anything?" anxiety that comes with hidden information.

---

## Item 4: Graph Pause/Unpause on Mouseover

### Current State

`GraphCanvas.tsx` renders `<ForceGraph2D>` with physics configured via:
- `d3AlphaDecay={0.02}`, `d3VelocityDecay={0.3}`, `cooldownTime={3000}`
- `enableNodeDrag={true}`

There is **no pause/resume logic**. The graph simulation runs continuously after data
loads, then cools down after 3 seconds. Node dragging temporarily "pins" the dragged
node but doesn't pause the overall simulation.

The `react-force-graph-2d` library's `ForceGraphMethods` ref exposes imperative methods
including `pauseAnimation()` and `resumeAnimation()`. However, **`pauseAnimation()`
stops the `requestAnimationFrame` render loop entirely**, meaning the canvas will not
repaint. This breaks node dragging: the user would drag a node but see nothing move
on screen until the animation resumes.

**Correct approach:** Instead of pausing the render loop, freeze the **d3 simulation**
by setting `alphaTarget(0)` and `alpha(0)`. This stops nodes from moving but keeps the
canvas rendering, so node drag, hover tooltips, and visual feedback all continue to work.

### Target State

When the user's mouse enters the graph canvas area, the simulation freezes (nodes
stop moving). When the mouse leaves, the simulation resumes. This makes it easier
for users to hover over specific nodes to read labels and inspect tooltips without
the graph layout shifting under their cursor. **Node dragging continues to work
normally while the simulation is frozen.**

### Implementation

#### `GraphCanvas.tsx` — Add Freeze/Unfreeze

Use the `cooldownTicks` prop to freeze the d3 simulation while keeping the render
loop alive. This is the correct approach — the library's `pauseAnimation()` method
stops the entire `requestAnimationFrame` loop, which would break node dragging and
hover tooltips. Controlling `cooldownTicks` via state freezes only the physics
simulation while the canvas continues repainting normally.

1. **Add frozen state and expose via imperative handle:**

```typescript
const [frozen, setFrozen] = useState(false);

export interface GraphCanvasHandle {
  zoomToFit: () => void;
  setFrozen: (frozen: boolean) => void;  // NEW
}

useImperativeHandle(ref, () => ({
  zoomToFit: () => fgRef.current?.zoomToFit(400, 40),
  setFrozen: (f: boolean) => {
    setFrozen(f);
    if (!f) fgRef.current?.d3ReheatSimulation();
  },
}), []);
```

2. **Control freeze via props on `ForceGraph2D`:**

```tsx
<ForceGraph2D
  ref={fgRef}
  cooldownTicks={frozen ? 0 : Infinity}
  cooldownTime={3000}  // constant — cooldownTicks controls freeze behavior
  // ... all existing props ...
/>
```

> **Note:** `cooldownTicks={0}` alone is sufficient to stop the simulation when frozen.
> When unfrozen, `cooldownTicks={Infinity}` defers to `cooldownTime={3000}`. Keep
> `cooldownTime` constant — toggling it alongside `cooldownTicks` is redundant.

2. **Add `onMouseEnter`/`onMouseLeave` props:**

```typescript
interface GraphCanvasProps {
  // ... existing props ...
  onMouseEnter?: () => void;   // NEW
  onMouseLeave?: () => void;   // NEW
}
```

3. **Wrap `ForceGraph2D` in a `<div>` with mouse handlers:**

```tsx
return (
  <div
    onMouseEnter={onMouseEnter}
    onMouseLeave={onMouseLeave}
    style={{ width, height }}
  >
    <ForceGraph2D
      ref={fgRef}
      // ... all existing props ...
    />
  </div>
);
```

#### `GraphTopologyViewer.tsx` — Wire Up Freeze/Unfreeze

```typescript
const canvasRef = useRef<GraphCanvasHandle>(null);
const [isPaused, setIsPaused] = useState(false);

const handleMouseEnter = useCallback(() => {
  canvasRef.current?.setFrozen(true);
  setIsPaused(true);
}, []);

const handleMouseLeave = useCallback(() => {
  canvasRef.current?.setFrozen(false);
  setIsPaused(false);
}, []);

// In the JSX:
<GraphCanvas
  ref={canvasRef}
  // ... existing props ...
  onMouseEnter={handleMouseEnter}
  onMouseLeave={handleMouseLeave}
/>
```

**Optional:** Show a subtle "⏸ Paused" indicator in `GraphToolbar.tsx` when `isPaused`
is true, so users understand why the graph stopped moving.

#### Edge Cases

- **Node dragging:** Works correctly because we freeze the simulation (stop ticking),
  not the render loop. The canvas continues to repaint, so dragged nodes move visually.
  Node drag pins `fx`/`fy` on the dragged node as usual.
- **Cooldown period:** If the graph hasn't finished its initial cooldown (3s after data
  load), freezing stops the layout mid-settling. This is acceptable — the user
  intentionally moused over to inspect nodes.
- **Touch devices:** `onMouseEnter`/`onMouseLeave` won't fire on touch. The graph
  behaves as before on touch devices — no regression.
- **Rapid mouse enter/leave:** `setFrozen` is idempotent — multiple `true` or `false`
  calls in sequence have no adverse effects.

### UX Enhancements for Graph Pause

#### 4a. Required "⏸ Paused" Visual Indicator

The "⏸ Paused" indicator should be **required**, not optional. Without it, users who
aren't aware of the pause-on-hover feature will think the graph is broken when it
freezes.

**Placement:** Bottom-right corner of the graph canvas, overlaying the graph.

**Styling:** Semi-transparent pill badge (`bg-white/10 backdrop-blur-sm text-text-muted`),
animates in with the existing `GraphTooltip` pattern (scale 0.95→1, 100ms). Small
enough to not obstruct graph content (height ~20px).

**Why:** The app already uses visual state indicators everywhere: `HealthDot` (green/red),
agent status dots (amber/green/red), provisioning banner. A "Paused" badge is consistent
with this language of state visibility.

#### 4b. Debounce Resume on Mouse-Leave

If a user's mouse briefly exits the canvas (e.g., moving to a nearby button), the graph
instantly resumes and the layout shifts. Add a **300ms debounce** on `onMouseLeave`
before calling `setFrozen(false)`:

```typescript
const resumeTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

const handleMouseEnter = useCallback(() => {
  if (resumeTimeoutRef.current) {
    clearTimeout(resumeTimeoutRef.current);
    resumeTimeoutRef.current = null;
  }
  canvasRef.current?.setFrozen(true);
  setIsPaused(true);
}, []);

const handleMouseLeave = useCallback(() => {
  resumeTimeoutRef.current = setTimeout(() => {
    canvasRef.current?.setFrozen(false);
    setIsPaused(false);
    resumeTimeoutRef.current = null;
  }, 300);
}, []);
```

**Why:** Without debounce, accidental mouse exits (common when reaching for the toolbar
above the graph or the resize handle below) cause jarring layout jumps.

> **Note:** This debounced version should **replace** the simple `handleMouseEnter`/
> `handleMouseLeave` in the `GraphTopologyViewer.tsx` section above. The simple
> version is shown first for clarity; use the debounced version in production.

#### 4c. Manual Pause/Resume Toggle in Toolbar

Add a pause/play button to `GraphToolbar` (alongside the existing zoom-to-fit ⤢ and
refresh ⟳ buttons):

```
[CoreRouter ● ] [BGPSession ● ] [Search... ] 42 nodes 68 edges [⏸] [⤢] [⟳]
```

This gives users **two ways** to pause:
1. **Implicit:** Mouse over the graph (auto-pause for inspection)
2. **Explicit:** Click the toolbar button (persistent pause for screenshots, presentations)

The explicit toggle overrides the implicit behavior: if the user manually pauses,
mouse-leave does NOT resume. Only clicking the toggle again (or the refresh button)
resumes.

**Why:** Mouse-hover pause is great for quick inspection, but users doing presentations
or taking screenshots need persistent pause without keeping the mouse over the graph.

#### 4d. Smooth Resume Transition

When the graph resumes after a pause, the sudden physics re-engagement can cause nodes
to jolt. Ease back into the simulation by lowering alpha or setting `d3AlphaDecay` to a
higher value (e.g., `0.05`) temporarily after resume, then reverting to `0.02` after
500ms. This dampens the post-pause settling quickly.

---

## Item 5: Interaction History Sidebar

### Current State

The app layout (`App.tsx`) is a 3-zone grid:
```
┌──────────────────────────────────────────────────────────────┐
│ Header                                                       │ Zone 1 (h-12 fixed)
├──────────────────────────────────────────────────────────────┤
│ MetricsBar (graph + logs)                                    │ Zone 2 (30%)
├───────────────────────┬──────────────────────────────────────┤
│ Investigation Panel   │ Diagnosis Panel                      │ Zone 3 (70%)
└───────────────────────┴──────────────────────────────────────┘
```

**No interaction tracking exists.** All investigation state is in-memory
(`useInvestigation` hook) and lost on page refresh. There is no persistence
of past investigations, no way to recall previous diagnoses.

### Target State

A collapsible right sidebar showing past interactions:

```
┌──────────────────────────────────────────────────────────────────┐
│ Header                                                           │
├──────────────────────────────────────────────────────┬───────────┤
│ MetricsBar (graph + logs)                            │ History   │
├───────────────────┬──────────────────────────────────┤ ┌───────┐ │
│ Investigation     │ Diagnosis                        │ │ 2m ago│ │
│ Panel             │ Panel                            │ │telco  │ │
│                   │                                  │ │VPN tu…│ │
│                   │                                  │ ├───────┤ │
│                   │                                  │ │ 1h ago│ │
│                   │                                  │ │cloud  │ │
│                   │                                  │ │Cool…  │ │
│                   │                                  │ └───────┘ │
└───────────────────┴──────────────────────────────────┴───────────┘
```

### Data Model

#### Cosmos NoSQL — `interactions` Database

| Property | Value |
|----------|-------|
| Account | Same NoSQL account (`{name}-nosql`) |
| Database | `interactions` |
| Container | `interactions` |
| Partition Key | `/scenario` |
| Throughput | Autoscale max 1000 RU/s (Azure autoscale minimum) |

The database + container are pre-created by Bicep (Item 6).

#### Document Schema

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "scenario": "telco-noc",
  "query": "14:31:14.259 CRITICAL VPN-ACME-CORP SERVICE_DEGRADATION VPN tunnel unreachable",
  "steps": [
    {
      "step": 1,
      "agent": "TelemetryAgent",
      "duration": "2.3s",
      "query": "SELECT * FROM c WHERE c.severity = 'CRITICAL'",
      "response": "Found 3 critical alerts...",
      "error": false
    },
    {
      "step": 2,
      "agent": "GraphExplorerAgent",
      "duration": "1.8s",
      "query": "g.V().has('status','down').bothE().otherV().path()",
      "response": "3 affected nodes found...",
      "error": false
    }
  ],
  "diagnosis": "## Root Cause Analysis\n\nThe VPN tunnel failure is caused by...",
  "run_meta": {
    "steps": 4,
    "time": "45s"
  },
  "created_at": "2026-02-15T14:31:00Z"
}
```

### Backend Changes

#### New File: `graph-query-api/router_interactions.py`

> **Routing context:** All `/query/*` paths are proxied to the graph-query-api
> service on port 8100 — by vite in dev (`vite.config.ts` proxy) and by nginx
> in production (`/query/` location block). New routes under `/query/` prefix
> automatically inherit this routing. No proxy or nginx config changes are needed.

> **Note:** Interaction endpoints use the scenario's **base name** (e.g.,
> `"telco-noc"`) directly as the `scenario` field and partition key. They do NOT
> use the `X-Graph` header or `ScenarioContext` dependency. The frontend's
> `activeScenario` (from `ScenarioContext.tsx`) already stores the base name — it
> is NOT the graph name (which would be `"telco-noc-topology"`).

```python
import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from azure.cosmos.exceptions import CosmosResourceNotFoundError

from models import InteractionSaveRequest

router = APIRouter(prefix="/query")

# --- Container setup (same pattern as router_scenarios.py) ---
_interactions_container = None

def _get_interactions_container(*, ensure_created: bool = True):
    """Get or create the interactions container in the shared 'interactions' DB."""
    global _interactions_container
    if _interactions_container is not None:
        return _interactions_container
    # Database "interactions" + container "interactions" pre-exist from Bicep
    # Just connect — no ARM calls needed
    # Cache the container client in _interactions_container

# --- Endpoints ---

@router.get("/interactions", summary="List past interactions")
async def list_interactions(
    scenario: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    """List interactions, optionally filtered by scenario.
    Returns newest first (ORDER BY c.created_at DESC).
    """
    container = _get_interactions_container(ensure_created=False)
    def _list():
        query = "SELECT * FROM c"
        params = []
        if scenario:
            query += " WHERE c.scenario = @scenario"
            params.append({"name": "@scenario", "value": scenario})
        query += " ORDER BY c.created_at DESC OFFSET 0 LIMIT @limit"
        params.append({"name": "@limit", "value": limit})
        # When filtering by scenario, route to single partition for efficiency.
        # Cross-partition query only needed for unfiltered listing.
        if scenario:
            return list(container.query_items(
                query=query, parameters=params,
                partition_key=scenario,
            ))
        else:
            return list(container.query_items(
                query=query, parameters=params,
                enable_cross_partition_query=True,
            ))
    items = await asyncio.to_thread(_list)
    return {"interactions": items}


@router.post("/interactions", summary="Save an interaction")
async def save_interaction(req: InteractionSaveRequest):
    """Save a completed investigation as an interaction record."""
    container = _get_interactions_container()
    doc = {
        "id": str(uuid.uuid4()),
        "scenario": req.scenario,
        "query": req.query,
        "steps": [s.model_dump() for s in req.steps],
        "diagnosis": req.diagnosis,
        "run_meta": req.run_meta.model_dump() if req.run_meta else None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    def _save():
        return container.upsert_item(doc)
    await asyncio.to_thread(_save)
    return doc


@router.get("/interactions/{interaction_id}", summary="Get a specific interaction")
async def get_interaction(interaction_id: str, scenario: str = Query(...)):
    """Get a specific interaction by ID. Requires scenario for partition key routing."""
    container = _get_interactions_container(ensure_created=False)
    def _get():
        try:
            return container.read_item(item=interaction_id, partition_key=scenario)
        except CosmosResourceNotFoundError:
            raise HTTPException(status_code=404, detail="Interaction not found")
    return await asyncio.to_thread(_get)


@router.delete("/interactions/{interaction_id}", summary="Delete an interaction")
async def delete_interaction(interaction_id: str, scenario: str = Query(...)):
    """Delete a specific interaction."""
    container = _get_interactions_container(ensure_created=False)
    def _delete():
        try:
            container.delete_item(item=interaction_id, partition_key=scenario)
        except CosmosResourceNotFoundError:
            raise HTTPException(status_code=404, detail="Interaction not found")
    await asyncio.to_thread(_delete)
    return {"deleted": interaction_id}
```

#### Pydantic Models (`graph-query-api/models.py`)

```python
class InteractionStep(BaseModel):
    step: int
    agent: str
    duration: str | None = None
    query: str | None = None
    response: str | None = None
    error: bool = False

class InteractionRunMeta(BaseModel):
    steps: int
    time: str

class InteractionSaveRequest(BaseModel):
    scenario: str
    query: str
    steps: list[InteractionStep]
    diagnosis: str
    run_meta: InteractionRunMeta | None = None
```

#### Mount in `graph-query-api/main.py`

```python
from router_interactions import router as interactions_router
app.include_router(interactions_router)
```

### Frontend Changes

#### New Types (`types/index.ts`)

```typescript
export interface Interaction {
  id: string;
  scenario: string;
  query: string;
  steps: StepEvent[];
  diagnosis: string;
  run_meta: RunMeta | null;
  created_at: string;
}
```

#### New Hook: `hooks/useInteractions.ts`

```typescript
export function useInteractions() {
  const [interactions, setInteractions] = useState<Interaction[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchInteractions = useCallback(async (scenario?: string) => {
    setLoading(true);
    try {
      const url = scenario
        ? `/query/interactions?scenario=${encodeURIComponent(scenario)}&limit=50`
        : '/query/interactions?limit=50';
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setInteractions(data.interactions ?? []);
    } catch (err) {
      console.error('Failed to fetch interactions:', err);
      // Don't clear existing interactions on error — keep stale data visible
    } finally {
      setLoading(false);
    }
  }, []);

  const saveInteraction = useCallback(async (interaction: {
    scenario: string;
    query: string;
    steps: StepEvent[];
    diagnosis: string;
    run_meta: RunMeta | null;
  }) => {
    try {
      const res = await fetch('/query/interactions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(interaction),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const saved = await res.json();
      setInteractions(prev => [saved, ...prev]);
      return saved;
    } catch (err) {
      console.error('Failed to save interaction:', err);
      return null;
    }
  }, []);

  const deleteInteraction = useCallback(async (id: string, scenario: string) => {
    try {
      const res = await fetch(
        `/query/interactions/${id}?scenario=${encodeURIComponent(scenario)}`,
        { method: 'DELETE' },
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setInteractions(prev => prev.filter(i => i.id !== id));
    } catch (err) {
      console.error('Failed to delete interaction:', err);
    }
  }, []);

  return { interactions, loading, fetchInteractions, saveInteraction, deleteInteraction };
}
```

#### New Component: `components/InteractionSidebar.tsx`

A collapsible right sidebar that:
1. Lists past interactions as cards (timestamp, scenario, truncated query)
2. Clicking a card loads its steps into `InvestigationPanel` and diagnosis into
   `DiagnosisPanel`
3. Has a collapse/expand toggle
4. Filters by active scenario (optional)
5. Shows empty state when no interactions exist

```tsx
interface InteractionSidebarProps {
  interactions: Interaction[];
  loading: boolean;
  onSelect: (interaction: Interaction) => void;
  onDelete: (id: string, scenario: string) => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
}

export function InteractionSidebar({
  interactions, loading, onSelect, onDelete,
  collapsed, onToggleCollapse,
}: InteractionSidebarProps) {
  return (
    <div className={`
      border-l border-white/10 bg-neutral-bg2 flex flex-col transition-all
      ${collapsed ? 'w-10' : 'w-72'}
    `}>
      {/* Header with collapse toggle */}
      <div className="h-10 flex items-center justify-between px-3 border-b border-white/10">
        {!collapsed && (
          <span className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
            History
          </span>
        )}
        <button onClick={onToggleCollapse} className="text-text-muted hover:text-text-primary">
          {collapsed ? '◀' : '▶'}
        </button>
      </div>

      {/* Interaction list */}
      {!collapsed && (
        <div className="flex-1 overflow-y-auto p-2 space-y-2">
          {loading && <p className="text-xs text-text-muted p-2">Loading...</p>}
          {!loading && interactions.length === 0 && (
            <p className="text-xs text-text-muted p-2 text-center">
              No past interactions yet.<br />
              Submit an alert to start.
            </p>
          )}
          {interactions.map(interaction => (
            <InteractionCard
              key={interaction.id}
              interaction={interaction}
              onClick={() => onSelect(interaction)}
              onDelete={() => onDelete(interaction.id, interaction.scenario)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
```

**`InteractionCard` sub-component:**

```tsx
interface InteractionCardProps {
  interaction: Interaction;
  onClick: () => void;
  onDelete: () => void;
}

function InteractionCard({ interaction, onClick, onDelete }: InteractionCardProps) {
  const timeAgo = formatTimeAgo(interaction.created_at); // e.g. "2m ago", "1h ago"

  return (
    <div
      onClick={onClick}
      className="group cursor-pointer rounded-lg border border-white/5 bg-neutral-bg3
                 p-2.5 hover:border-white/15 hover:bg-neutral-bg4 transition-colors"
    >
      {/* Header: timestamp + delete */}
      <div className="flex items-center justify-between mb-1">
        <span className="text-[10px] text-text-muted">{timeAgo}</span>
        <button
          onClick={(e) => { e.stopPropagation(); onDelete(); }}
          className="opacity-0 group-hover:opacity-100 text-text-muted hover:text-red-400
                     transition-opacity text-xs p-0.5"
          title="Delete"
        >
          ✕
        </button>
      </div>

      {/* Scenario badge */}
      <span className="inline-block text-[10px] font-medium px-1.5 py-0.5 rounded
                       bg-accent/15 text-accent mb-1">
        {interaction.scenario}
      </span>

      {/* Query preview */}
      <p className="text-xs text-text-secondary line-clamp-2 leading-relaxed">
        {interaction.query}
      </p>

      {/* Meta: step count + elapsed */}
      {interaction.run_meta && (
        <div className="mt-1.5 text-[10px] text-text-muted flex gap-2">
          <span>{interaction.run_meta.steps} steps</span>
          <span>{interaction.run_meta.time}</span>
        </div>
      )}
    </div>
  );
}

/** Format ISO timestamp to relative time (e.g. "2m ago", "3h ago", "1d ago") */
function formatTimeAgo(isoString: string): string {
  const seconds = Math.floor((Date.now() - new Date(isoString).getTime()) / 1000);
  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}
```

#### `App.tsx` — Layout Changes

Add the sidebar as a collapsible right panel beside the main content area:

```tsx
export default function App() {
  const { alert, setAlert, steps, thinking, finalMessage, errorMessage,
    running, runStarted, runMeta, submitAlert } = useInvestigation();
  const { interactions, loading: interactionsLoading, fetchInteractions,
    saveInteraction, deleteInteraction } = useInteractions();
  const { activeScenario } = useScenarioContext();

  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [viewingInteraction, setViewingInteraction] = useState<Interaction | null>(null);

  // Fetch interactions on mount and when scenario changes
  useEffect(() => {
    fetchInteractions(activeScenario ?? undefined);
  }, [activeScenario, fetchInteractions]);

  // Auto-save interaction when investigation completes.
  // Use a composite ref to capture the latest values at save-time,
  // avoiding stale closures while keeping the effect dependency list clean.
  const prevRunningRef = useRef(running);
  const latestValuesRef = useRef({ alert, steps, runMeta, activeScenario });
  useEffect(() => {
    latestValuesRef.current = { alert, steps, runMeta, activeScenario };
  });

  useEffect(() => {
    if (prevRunningRef.current && !running && finalMessage && latestValuesRef.current.activeScenario) {
      const { alert, steps, runMeta, activeScenario } = latestValuesRef.current;
      saveInteraction({
        scenario: activeScenario,
        query: alert,
        steps,
        diagnosis: finalMessage,
        run_meta: runMeta,
      });
    }
    prevRunningRef.current = running;
  }, [running, finalMessage, saveInteraction]);

  // When viewing a past interaction, override displayed data
  const displaySteps = viewingInteraction?.steps ?? steps;
  const displayDiagnosis = viewingInteraction?.diagnosis ?? finalMessage;
  const displayRunMeta = viewingInteraction?.run_meta ?? runMeta;

  // Clear viewing state when a new investigation starts
  useEffect(() => {
    if (running) setViewingInteraction(null);
  }, [running]);

  return (
    <motion.div className="h-screen flex flex-col bg-neutral-bg1" ...>
      <Header />
      <div className="flex-1 min-h-0 flex">
        {/* Main content area (existing layout) */}
        <div className="flex-1 min-w-0">
          <PanelGroup orientation="vertical" className="h-full">
            <Panel defaultSize={30} minSize={15}>
              <MetricsBar />
            </Panel>
            <PanelResizeHandle className="vertical-resize-handle" />
            <Panel defaultSize={70} minSize={20}>
              <div className="h-full flex min-h-0">
                <InvestigationPanel ... steps={displaySteps} runMeta={displayRunMeta} />
                <DiagnosisPanel finalMessage={displayDiagnosis} runMeta={displayRunMeta} ... />
              </div>
            </Panel>
          </PanelGroup>
        </div>

        {/* Interaction history sidebar */}
        <InteractionSidebar
          interactions={interactions}
          loading={interactionsLoading}
          onSelect={(i) => { setViewingInteraction(i); setAlert(i.query); }}
          onDelete={deleteInteraction}
          collapsed={sidebarCollapsed}
          onToggleCollapse={() => setSidebarCollapsed(!sidebarCollapsed)}
        />
      </div>
    </motion.div>
  );
}
```

#### Auto-Save Behavior

Interactions are **auto-saved** when an investigation completes successfully:
- Trigger: `running` transitions from `true` to `false` AND `finalMessage` is non-empty
  AND `activeScenario` is set
- The save happens in a `useEffect` that watches `running` and `finalMessage`
- Failed investigations (error, no diagnosis) are NOT saved
- Users cannot manually trigger a save — it's automatic

#### Viewing Historical Interactions

When a user clicks on an interaction card:
1. `viewingInteraction` state is set to the selected `Interaction` object
2. `InvestigationPanel` shows the historical steps (via `displaySteps`)
3. `DiagnosisPanel` shows the historical diagnosis (via `displayDiagnosis`)
4. The alert text is set to the historical query
5. A banner appears at the top of the investigation area: **"Viewing past interaction
   from {timeAgo}. [Clear]"** — clicking "Clear" resets `viewingInteraction` to null

Starting a new investigation automatically clears `viewingInteraction`.

### UX Enhancements for Interaction Sidebar

#### 5a. Loading Skeleton Instead of Text

Use a **skeleton loader** that matches the card shape instead of `<p>Loading...</p>`:

```tsx
{loading && (
  <div className="space-y-2 p-2">
    {[1, 2, 3].map(i => (
      <div key={i} className="h-20 rounded-lg bg-white/5 animate-pulse" />
    ))}
  </div>
)}
```

The app already uses `animate-pulse` for loading states (graph topology loader,
provisioning dot). Skeleton loaders communicate "content is coming" without the
abruptness of a text label.

#### 5b. Search / Filter in Sidebar

With 50 interactions loaded by default, scrolling to find a specific past investigation
is tedious. Add a search input at the top of the sidebar that filters interactions
client-side by matching against `query` text and `scenario` name. The input should use
the existing `.glass-input` class and match the toolbar search input in
`GraphTopologyViewer` (same font size, same placeholder pattern).

#### 5c. "Viewing Past Interaction" Banner Design

This is critical — users must always know whether they're looking at **live
investigation data** or **historical replay**.

**Proposed design:** A slim persistent banner at the top of the investigation area
(spanning both panels):

```
┌──────────────────────────────────────────────────────────────┐
│ ◀ Viewing interaction from 2 hours ago · telco-noc  [Clear] │ ← brand-subtle bg
├───────────────────────┬──────────────────────────────────────┤
│ Investigation Panel   │ Diagnosis Panel                      │
```

**Styling:** `bg-brand-subtle` (rgba(130,81,238,0.15)) with `border-brand/20` bottom
border — uses the same visual language as the `ProvisioningBanner` but with brand
color instead of amber. Includes arrow ◀ indicating "going back in time", relative
timestamp, scenario name badge, and "Clear" button to return to live state.

**Animation:** Slides down from the top (matching `ProvisioningBanner`'s entrance pattern).

#### 5d. Empty State That Teaches

Replace the minimal empty state with a more **educational and action-oriented** design:

Mirror the `DiagnosisPanel` empty state (centered diamond icon + title + subtitle)
for visual continuity. Use the same `text-text-muted` and `opacity-40` pattern.
Message: "History appears here. Submit an alert to start an investigation. Results
are auto-saved."

#### 5e. Interaction Card Enhancements

**a) Relative timestamps that auto-update:** Use `Intl.RelativeTimeFormat` or a simple
helper that re-renders every 60 seconds. After 24 hours, switch to absolute date format.

**b) Query preview with keyword highlighting:** If the query contains severity keywords
(CRITICAL, WARNING, ERROR), highlight them using the same colors as graph node status
dots: CRITICAL/ERROR → `text-status-error`, WARNING → `text-status-warning`.

**c) Step count + elapsed time badge:** Show `4 steps · 45s` in the card footer, giving
users a quick sense of investigation complexity before clicking.

**d) Hover preview tooltip:** On hover (300ms delay — matching `GraphTooltip` timing),
show a tooltip with the first 2 lines of the diagnosis text.

**e) Delete confirmation:** Don't delete on single click. Show a brief inline
confirmation ("Delete?" with ✓/✗ buttons) that auto-dismisses after 3 seconds.

#### 5f. Keyboard Navigation

The sidebar should support:
- `↑`/`↓` arrows to move between interaction cards
- `Enter` to select/view an interaction
- `Escape` to clear the viewing state
- `Delete` to trigger delete confirmation on the focused card

#### 5g. Auto-Save Feedback

Users should know when an auto-save happens. Add a transient indicator — flash the
sidebar header "History" text with a brief green tint + "+ Saved" text that fades
after 2 seconds:

```
History + Saved ✓   → (2s later) →   History
```

#### 5h. Sidebar Width Transition

The `InteractionSidebar` code sample above uses `transition-all` — change this to
`transition-[width]` to avoid transitioning unrelated properties (color, opacity, etc.).
Use `duration-200 ease-out` to match the app's standard 200ms animation timing:

```tsx
className={`
  border-l border-white/10 bg-neutral-bg2 flex flex-col
  transition-[width] duration-200 ease-out
  ${collapsed ? 'w-10' : 'w-72'}
`}
```

---

## Item 6: Pre-Create Core DBs in Bicep

### Current State

The Bicep module `cosmos-gremlin.bicep` currently creates:
- **Cosmos Gremlin account** with database `networkgraph` and graph `topology`
- **Cosmos NoSQL account** with database `telemetry` (empty — no containers)

All other databases are created at **runtime** via ARM management plane calls:
- `{scenario}-telemetry` — created by `router_ingest.py` on first telemetry upload
- `{scenario}-prompts` — created by `router_prompts.py` on first prompt access
- `scenarios` — created by `router_scenarios.py` on first scenario access

Each runtime ARM creation takes 20-30 seconds and requires `AZURE_SUBSCRIPTION_ID`
and `AZURE_RESOURCE_GROUP` env vars.

### Target State

Pre-create all core databases at `azd up` time:

| Account | Database | Created By | Contains |
|---------|----------|-----------|----------|
| Cosmos Gremlin | `networkgraph` | Bicep (existing) | Per-scenario graphs (`{name}-topology`) |
| Cosmos NoSQL | `telemetry` | Bicep (existing, empty) | Per-scenario containers (`{name}-AlertStream`, etc.) |
| Cosmos NoSQL | `scenarios` | **Bicep (NEW)** | `scenarios` container (PK `/id`) |
| Cosmos NoSQL | `prompts` | **Bicep (NEW)** | Per-scenario containers (`{name}`, PK `/agent`) |
| Cosmos NoSQL | `interactions` | **Bicep (NEW)** | `interactions` container (PK `/scenario`) |

### Bicep Changes

#### `infra/modules/cosmos-gremlin.bicep` — Add NoSQL Databases + Containers

Add 3 new database resources + 2 pre-created containers:

```bicep
// ─── Scenarios Database ──────────────────────────────────────────────────────

resource scenariosDatabase 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-11-15' = {
  name: 'scenarios'
  parent: cosmosNoSqlAccount
  properties: {
    resource: { id: 'scenarios' }
  }
}

resource scenariosContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-11-15' = {
  name: 'scenarios'
  parent: scenariosDatabase
  properties: {
    resource: {
      id: 'scenarios'
      partitionKey: { paths: ['/id'], kind: 'Hash', version: 2 }
    }
    options: { autoscaleSettings: { maxThroughput: 1000 } }  // Azure autoscale minimum
  }
}

// ─── Prompts Database (shared — per-scenario containers created at runtime) ─

resource promptsDatabase 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-11-15' = {
  name: 'prompts'
  parent: cosmosNoSqlAccount
  properties: {
    resource: { id: 'prompts' }
  }
}

// ─── Interactions Database ───────────────────────────────────────────────────

resource interactionsDatabase 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-11-15' = {
  name: 'interactions'
  parent: cosmosNoSqlAccount
  properties: {
    resource: { id: 'interactions' }
  }
}

resource interactionsContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-11-15' = {
  name: 'interactions'
  parent: interactionsDatabase
  properties: {
    resource: {
      id: 'interactions'
      partitionKey: { paths: ['/scenario'], kind: 'Hash', version: 2 }
      // Composite index for efficient ORDER BY c.created_at DESC queries.
      // Without this, cross-partition ORDER BY queries consume excessive RUs
      // and may return inconsistent ordering.
      indexingPolicy: {
        compositeIndexes: [
          [
            { path: '/scenario', order: 'ascending' }
            { path: '/created_at', order: 'descending' }
          ]
        ]
      }
      // Auto-expire interactions after 90 days to prevent unbounded growth.
      // Set to -1 (or remove) to disable TTL and keep interactions forever.
      defaultTtl: 7776000  // 90 days in seconds
    }
    options: { autoscaleSettings: { maxThroughput: 1000 } }  // Azure autoscale minimum
  }
}
```

**Note:** No containers pre-created for `telemetry` or `prompts` databases — those
are scenario-specific and created dynamically at upload time. Only the databases
themselves are pre-created to skip the slowest ARM operation (~20-30s per database).

The `scenarios` and `interactions` databases get their containers pre-created because
they have a fixed, known container structure.

#### Bicep Outputs

```bicep
output scenariosDatabaseName string = scenariosDatabase.name
output promptsDatabaseName string = promptsDatabase.name
output interactionsDatabaseName string = interactionsDatabase.name
```

#### `infra/main.bicep` — No Changes Needed

The new databases are hardcoded in the module (not parameterized) since their names
are fixed conventions.

### Backend Changes — Skip ARM Database Creation

After Bicep pre-creates the databases, runtime ARM calls to create them become
redundant. Update each router:

| Router | Change |
|--------|--------|
| `router_scenarios.py` | `_get_scenarios_container()` — skip ARM DB+container creation, just connect |
| `router_prompts.py` | `_get_prompts_container()` — skip ARM DB creation, only create per-scenario container |
| `router_ingest.py` | `upload_telemetry` — skip ARM DB creation, only create per-scenario containers |
| `router_interactions.py` (new) | `_get_interactions_container()` — just connect, no ARM needed |

---

## Implementation Phases

### Phase 1: Pre-Create Core DBs in Bicep

> Prerequisite for Phases 2 and 6. Can be done independently of Phases 3-5.

**Files to modify:**
- `infra/modules/cosmos-gremlin.bicep` — add `scenarios`, `prompts`, `interactions` databases + containers for `scenarios` and `interactions`

**Verification:**
- Run `azd up` and confirm all databases appear in Azure Portal
- Confirm `scenarios` and `interactions` containers are pre-created
- Confirm `telemetry` and `prompts` databases exist but have no containers yet

### Phase 2: Per-Scenario Containers (Shared DBs)

> Depends on Phase 1.

**Files to modify:**
- `graph-query-api/config.py` — add `telemetry_container_prefix`, `prompts_database`, `prompts_container` to `ScenarioContext`
- `graph-query-api/router_ingest.py` — refactor telemetry upload to use shared `telemetry` DB with prefixed containers
- `graph-query-api/router_prompts.py` — use shared `prompts` DB with per-scenario container named `{scenario}`
- `graph-query-api/router_telemetry.py` — prepend container prefix to container name in queries
- `graph-query-api/router_scenarios.py` — skip ARM database creation (pre-exists)
- `frontend/src/types/index.ts` — update `SavedScenario.resources` interface

**Verification:**
- Upload a scenario → confirm data goes to `telemetry` DB with `{name}-AlertStream` containers
- Confirm prompts go to `prompts` DB with `{name}` container
- Verify telemetry queries still work with the new container naming

### Phase 3: Upload Timer

> Independent. No dependencies.

**Files to modify:**
- `frontend/src/components/AddScenarioModal.tsx` — add timer state, interval, format helper, render

**Verification:**
- Open "+Add Scenario" → upload files → confirm timer counts up
- Confirm timer stops on completion/error/cancel
- Confirm elapsed time persists after completion

### Phase 4: Graph API Log Stream

> Independent. No dependencies.

**Files to modify:**
- `graph-query-api/main.py` — add `GET /query/logs` route
- `frontend/src/components/MetricsBar.tsx` — add third panel with `<LogStream url="/query/logs" title="Graph API" />`

**Verification:**
- Confirm 3 panels visible in MetricsBar
- Upload a scenario → confirm graph-query-api logs appear in "Graph API" panel
- Confirm API logs still appear in "API" panel
- Confirm panels are individually resizable

### Phase 5: Graph Pause/Unpause

> Independent. No dependencies.

**Files to modify:**
- `frontend/src/components/graph/GraphCanvas.tsx` — add simulation freeze via `cooldownTicks` prop; add `setFrozen` to handle; add mouse event props; wrap in `<div>`
- `frontend/src/components/GraphTopologyViewer.tsx` — wire mouse enter/leave callbacks

**Verification:**
- Load graph topology → confirm nodes animate
- Mouse over graph → confirm simulation freezes (nodes stop moving)
- Mouse out → confirm simulation resumes
- **Confirm node drag still works while frozen** (canvas must continue repainting)
- Confirm hover tooltips still work while frozen

### Phase 6: Interaction History Sidebar

> Depends on Phase 1 (interactions DB must exist).

**Files to create:**
- `graph-query-api/router_interactions.py` — CRUD endpoints (~180 lines)
- `frontend/src/hooks/useInteractions.ts` — fetch/save/delete (~80 lines)
- `frontend/src/components/InteractionSidebar.tsx` — sidebar UI (~200 lines)

**Files to modify:**
- `graph-query-api/main.py` — mount `interactions_router`
- `graph-query-api/models.py` — add interaction Pydantic models
- `frontend/src/types/index.ts` — add `Interaction` interface
- `frontend/src/App.tsx` — add sidebar to layout, auto-save, viewing state

**Verification:**
- Run investigation → confirm auto-saved after completion
- Open sidebar → confirm interaction card appears
- Click card → confirm steps + diagnosis display in main panels
- Delete → confirm removed
- Refresh page → confirm interactions persist

---

## File Change Inventory

| File | Action | Phase | Changes |
|------|--------|-------|---------|
| `infra/modules/cosmos-gremlin.bicep` | MODIFY | 1 | Add `scenarios` DB + container, `prompts` DB, `interactions` DB + container |
| `graph-query-api/config.py` | MODIFY | 2 | Add `telemetry_container_prefix`, `prompts_database`, `prompts_container` to `ScenarioContext` |
| `graph-query-api/router_ingest.py` | MODIFY | 2 | Skip DB creation; prefix container names with scenario name |
| `graph-query-api/router_prompts.py` | MODIFY | 2 | Use shared `prompts` DB; per-scenario container name |
| `graph-query-api/router_telemetry.py` | MODIFY | 2 | Prepend container prefix to container name |
| `graph-query-api/router_scenarios.py` | MODIFY | 2 | Skip ARM database creation |
| `frontend/src/types/index.ts` | MODIFY | 2, 6 | Update `SavedScenario.resources`; add `Interaction` interface |
| `frontend/src/components/AddScenarioModal.tsx` | MODIFY | 3 | Add timer (refs, interval, elapsed display) |
| `graph-query-api/main.py` | MODIFY | 4, 6 | Add `GET /query/logs`; mount `interactions_router` |
| `frontend/src/components/MetricsBar.tsx` | MODIFY | 4 | Add third `<Panel>` with Graph API `<LogStream>` (or `TabbedLogStream`) |
| `frontend/src/components/TabbedLogStream.tsx` | **CREATE** | 4 (UX) | Tabbed log viewer alternative to avoid 3-panel cramping (~60 lines) |
| `frontend/src/components/graph/GraphCanvas.tsx` | MODIFY | 5 | Add simulation freeze via cooldown props; mouse event props; wrapper div |
| `frontend/src/components/GraphTopologyViewer.tsx` | MODIFY | 5 | Wire mouse enter/leave; required "⏸ Paused" indicator; debounce resume |
| `frontend/src/components/graph/GraphToolbar.tsx` | MODIFY | 5 (UX) | Add manual pause/play toggle button |
| `graph-query-api/router_interactions.py` | **CREATE** | 6 | Interactions CRUD (~180 lines) |
| `graph-query-api/models.py` | MODIFY | 6 | Add `InteractionStep`, `InteractionRunMeta`, `InteractionSaveRequest` |
| `frontend/src/hooks/useInteractions.ts` | **CREATE** | 6 | Fetch, save, delete interactions (~80 lines) |
| `frontend/src/components/InteractionSidebar.tsx` | **CREATE** | 6 | Sidebar + InteractionCard (~200 lines) |
| `frontend/src/App.tsx` | MODIFY | 6 | Sidebar layout, auto-save, viewing state |

### Files NOT Changed

- `api/` — no changes to the API service (orchestrator, alert, config, logs)
- `scripts/agent_provisioner.py` — agent provisioning unchanged
- `nginx.conf` — existing `/query/` block handles `/query/logs` correctly
- `frontend/vite.config.ts` — existing `/query` proxy handles `/query/logs`
- `graph-query-api/search_indexer.py` — search pipeline unchanged
- `graph-query-api/backends/` — graph backends unchanged
- `frontend/src/context/ScenarioContext.tsx` — minimal/no changes (backend handles routing)

---

## Cross-Cutting UX Gaps

These are not tied to a specific QOL item but affect the overall feel of the app.
Addressing them alongside the QOL changes would significantly improve coherence.

### Gap 1: No Toast/Notification System

**Current state:** Feedback is exclusively inline (modal banners, component-level
error states, colored dots). There is no mechanism for **transient, global feedback**
— notifications that appear briefly and auto-dismiss.

**Where toasts would improve UX in the QOL plan:**
- Item 2: "Scenario uploaded successfully (3m 47s)" — currently a green banner
  inside the modal that auto-closes
- Item 5: "Investigation saved to history" — currently silent
- Item 5: "Interaction deleted" — currently silent
- Item 4: Edge case feedback: "Graph paused" (if pause fails or is disabled)

**Recommended library:** `sonner` (13KB, zero config, supports stacking, progress
bars, undo actions). Alternatively, build a minimal toast using `AnimatePresence`
+ a context provider — the app already has the animation infrastructure.

**Placement:** Bottom-right corner, above any sidebar, consistent with VS Code's
own notification position.

### Gap 2: Investigation/Diagnosis Split Not Resizable

The investigation panel and diagnosis panel are locked at 50/50 (`w-1/2`). The
vertical metrics/content split uses `react-resizable-panels`. This inconsistency
means users with long diagnoses can't expand the diagnosis panel, and users focused
on step-by-step debugging can't expand the investigation panel.

**Recommendation:** Replace `w-1/2` with a horizontal `PanelGroup` (same library
already installed). This is a small change with high usability payoff:

```tsx
<PanelGroup direction="horizontal" className="h-full">
  <Panel defaultSize={50} minSize={25}>
    <InvestigationPanel ... />
  </Panel>
  <PanelResizeHandle className="metrics-resize-handle" />
  <Panel defaultSize={50} minSize={25}>
    <DiagnosisPanel ... />
  </Panel>
</PanelGroup>
```

### Gap 3: Diagnosis Should Stream Incrementally

The current DiagnosisPanel shows the final diagnosis all-at-once when the SSE
`message` event fires. The backend already uses SSE, which can stream the diagnosis
token-by-token or paragraph-by-paragraph.

**Why this matters for QOL:** If the goal is to "enhance observation and improve UX"
(Items 3-5), the single biggest improvement to user perception of speed is streaming
the diagnosis as it's generated. Users see progress immediately instead of staring at
bouncing dots for 30+ seconds.

**This is out of scope for the current QOL plan** but should be logged as a fast-follow,
especially since the SSE infrastructure already exists.

### Gap 4: Graph Keyboard Accessibility

The graph currently has zero keyboard support: all interactions (hover, click, drag,
right-click) are mouse-only. While a full keyboard-accessible graph is a large effort,
the QOL plan's pause/resume feature (Item 4) should include:
- `Space` key to toggle pause/resume when the graph div has focus
- `Tab` to focus the graph div from the toolbar

This is a small addition to Item 4's scope that brings meaningful accessibility improvement.

---

## UX Priority Matrix

Ranked by **impact on intuitive feel** relative to implementation effort:

| Priority | Enhancement | QOL Item | Effort | Impact |
|----------|------------|----------|--------|--------|
| **P0** | Tabbed log viewer (avoid 3-panel cramping) | 3 | Small | High |
| **P0** | Required "Paused" badge on graph | 4 | Tiny | High |
| **P0** | "Viewing past interaction" banner design | 5 | Small | High |
| **P1** | Timer: `font-mono tabular-nums` (prevent layout shift) | 2 | Tiny | Medium |
| **P1** | Timer: per-slot elapsed time | 2 | Small | Medium |
| **P1** | Mouse-leave resume debounce (300ms) | 4 | Tiny | Medium |
| **P1** | Sidebar loading skeletons | 5 | Tiny | Medium |
| **P1** | Delete confirmation inline | 5 | Small | Medium |
| **P1** | Auto-save feedback indicator | 5 | Small | Medium |
| **P2** | Timer: ETA estimate | 2 | Small | Medium |
| **P2** | Manual pause/resume toolbar toggle | 4 | Small | Medium |
| **P2** | Sidebar search/filter | 5 | Small | Medium |
| **P2** | Card keyword highlighting | 5 | Tiny | Low |
| **P2** | Investigation/Diagnosis resizable split | Global | Small | Medium |
| **P3** | Toast notification system | Global | Medium | Medium |
| **P3** | Timer: completion celebration moment | 2 | Tiny | Low |
| **P3** | Sidebar keyboard navigation | 5 | Small | Low |
| **P3** | Unread badge on inactive log tab | 3 | Small | Low |
| **P3** | Smooth graph resume transition | 4 | Small | Low |
| **P3** | Sidebar hover preview tooltip | 5 | Small | Low |
| **Backlog** | Streaming diagnosis rendering | Global | Medium | High |
| **Backlog** | Graph keyboard accessibility (full) | 4 | Large | Medium |

### Implementation Notes

- **P0 items** should be implemented alongside their respective QOL phases. They
  prevent UX regressions (3-panel cramping) or are essential for feature
  comprehension (paused badge, viewing banner).
- **P1 items** are small polish additions that can be dropped in directly during
  implementation without architecture changes.
- **P2 items** are nice-to-haves that enhance the feature but don't block a good
  initial experience.
- **P3 items** are polish for post-launch iteration.
- **Backlog items** require separate work streams beyond the QOL scope.

---

## Edge Cases & Validation

### Per-Scenario Containers (Item 1)

**Container name length limit:** Cosmos NoSQL container names max 256 chars.
`{scenario}-{container}` worst case ~45 chars — well within limits.

**Collision risk:** Scenario names are unique (enforced by validation), so
`{scenario}-{container}` names are unique within the shared DB.

**Migration path:** Existing per-scenario databases remain accessible. New uploads
go to shared DBs. Gradual migration via re-upload. See Migration section.

### Upload Timer (Item 2)

**Timer precision:** 1-second granularity via `setInterval(1000)` is sufficient for
uploads taking 30s-5min.

**Unmount during upload:** Cleanup `useEffect` clears the interval.

### Graph API Logs (Item 3)

**SSE reconnection:** `LogStream` uses native `EventSource` with auto-reconnect.

**Log volume:** Graph-query-api generates fewer logs than the API. Ring buffer
(`deque(maxlen=100)`) limits memory.

### Graph Pause (Item 4)

**Simulation freeze vs render pause:** We freeze the d3 simulation (via `cooldownTicks`
prop), NOT the render loop (`pauseAnimation`). This ensures the canvas keeps repainting
so node drag, hover effects, and tooltips continue to work while the graph is frozen.

**Rapid mouse enter/leave:** `setFrozen` is idempotent — no adverse effects.

**Initial layout:** Freezing during cooldown stops the layout mid-settle. Acceptable —
mouse removal resumes with `d3ReheatSimulation()`.

**Touch devices:** No regression — `onMouseEnter`/`onMouseLeave` don't fire on touch.

### Interaction Sidebar (Item 5)

**Large history:** `limit=50` default prevents overloading. Older records remain
in Cosmos. A 90-day TTL on the container auto-prunes old interactions.

**Auto-save race condition:** All values captured at save-time (`alert`, `steps`,
`runMeta`, `activeScenario`) are stored in refs that are synced via dedicated
`useEffect` hooks. The save `useEffect` depends only on `[running, finalMessage,
saveInteraction]`, avoiding both stale closures and exhaustive-deps lint violations.

**Error handling:** All `fetch` calls in `useInteractions` are wrapped in
`try/catch/finally`. Network errors are logged to console. `setLoading(false)` is
always called via `finally` to prevent the sidebar from getting stuck in a loading state.

**Viewing vs. running:** Starting a new investigation clears `viewingInteraction`.

**Partition key:** Cross-scenario queries use `enable_cross_partition_query=True`.
Acceptable for < 1000 interactions. A composite index on `[scenario, created_at DESC]`
ensures efficient ordering.

### Pre-Create DBs in Bicep (Item 6)

**Idempotent:** Re-running `azd up` on existing deployments is a no-op for
already-existing databases.

**Existing deployments:** Get new databases on next `azd up`. No data loss.

---

## Migration & Backwards Compatibility

### Existing Per-Scenario Databases

Existing data in `{scenario}-telemetry` and `{scenario}-prompts` databases
**will not be migrated automatically**.

**Recommended approach: Gradual migration.** New uploads go to shared DBs. Old
data remains in old databases. Query code falls back to old DB naming if shared
DB containers don't exist. Re-uploading scenarios moves them to the new structure.

### Fallback Logic

During the transition period, query code should try the shared DB first, then
fall back to the old per-scenario DB:

```python
# In router_telemetry.py:
from azure.cosmos.exceptions import CosmosResourceNotFoundError

try:
    # Try shared DB with prefixed container
    container = db.get_container_client(f"{prefix}-{container_name}")
    # Probe with a lightweight read to confirm the container exists
    container.read()
except CosmosResourceNotFoundError:
    # Fallback to old per-scenario DB for pre-migration data
    old_db = client.get_database_client(f"{prefix}-telemetry")
    container = old_db.get_container_client(container_name)
```

> **⚠️ Note:** The fallback uses `CosmosResourceNotFoundError` (not a bare `except:`)
> to avoid swallowing unrelated exceptions like `ServiceRequestError`,
> `CosmosHttpResponseError`, `KeyboardInterrupt`, etc. The `container.read()` probe
> is needed because `get_container_client()` is lazy and doesn't hit the network.

> **⚠️ Caveat on DB name derivation:** The fallback above assumes old databases
> follow the `{prefix}-telemetry` pattern. However, `router_ingest.py` has two
> derivation paths: when `scenario_name` is passed as a query param, the DB is
> `f"{sc_name}-telemetry"` (hardcoded suffix). When omitted, it reads from
> `scenario.yaml`'s `cosmos.nosql.database` field (defaulting to `"telemetry"`).
> If any `scenario.yaml` overrides this field (e.g., `database: "metrics"`), the
> fallback would miss `{name}-metrics` databases. **Assumption:** All existing
> scenarios use the default `telemetry` suffix. Verify this before relying on the
> fallback — or add a second fallback attempt using the manifest-derived name.

This fallback can be removed after all scenarios are re-uploaded.

### API Surface Compatibility

All API endpoints remain the same. Changes are internal to the data layer.
Frontend is unaffected except for the `SavedScenario.resources` type update
(additive — new optional fields marked with `?` for back-compat with existing docs).