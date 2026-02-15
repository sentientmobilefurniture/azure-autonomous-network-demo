# QOL Improvements — Implementation Plan

> **Created:** 2026-02-15
> **Last audited:** 2026-02-15
> **Status:** ⬜ Not Started
> **Goal:** Six quality-of-life improvements to speed up loading, improve observability,
> enhance graph interaction, track investigation history, and eliminate runtime ARM
> delays by pre-creating core databases at infrastructure provisioning time.

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
| **Phase 1:** Pre-create Core DBs in Bicep | ⬜ Not started | `cosmos-gremlin.bicep`, `router_scenarios.py`, `router_prompts.py`, `router_ingest.py` |
| **Phase 2:** Per-Scenario Containers (Shared DBs) | ⬜ Not started | `router_ingest.py`, `router_prompts.py`, `router_scenarios.py`, `config.py`, `types/index.ts` |
| **Phase 3:** Upload Timer | ⬜ Not started | `AddScenarioModal.tsx` |
| **Phase 4:** Graph API Log Stream in MetricsBar | ⬜ Not started | `MetricsBar.tsx`, `main.py` (graph-query-api) |
| **Phase 5:** Graph Pause/Unpause on Mouseover | ⬜ Not started | `GraphCanvas.tsx`, `GraphTopologyViewer.tsx` |
| **Phase 6:** Interaction History Sidebar | ⬜ Not started | New router, new hook, new components, `App.tsx`, `types/index.ts`, `cosmos-gremlin.bicep` |

---

## Table of Contents

- [Overview of Changes](#overview-of-changes)
- [Item 1: Per-Scenario Containers in Shared DBs](#item-1-per-scenario-containers-in-shared-dbs)
- [Item 2: Upload Timer](#item-2-upload-timer)
- [Item 3: Graph API Log Stream in MetricsBar](#item-3-graph-api-log-stream-in-metricsbar)
- [Item 4: Graph Pause/Unpause on Mouseover](#item-4-graph-pauseunpause-on-mouseover)
- [Item 5: Interaction History Sidebar](#item-5-interaction-history-sidebar)
- [Item 6: Pre-Create Core DBs in Bicep](#item-6-pre-create-core-dbs-in-bicep)
- [Implementation Phases](#implementation-phases)
- [File Change Inventory](#file-change-inventory)
- [Edge Cases & Validation](#edge-cases--validation)
- [Migration & Backwards Compatibility](#migration--backwards-compatibility)

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
    prefix = graph_name.rsplit("-", 1)[0] if "-" in graph_name else ""

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

Update the `resources` field in `SavedScenario` to reflect shared DBs:

```typescript
resources: {
  graph: string;                    // "cloud-outage-topology" (unchanged)
  telemetry_database: string;       // "telemetry" (was "cloud-outage-telemetry")
  telemetry_container_prefix: string; // "cloud-outage" (NEW)
  runbooks_index: string;           // unchanged
  tickets_index: string;            // unchanged
  prompts_database: string;         // "prompts" (was "cloud-outage-prompts")
  prompts_container: string;        // "cloud-outage" (NEW)
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

`AddScenarioModal.tsx` (621 lines) tracks upload progress via `overallPct` (0-100)
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

2. **Start timer when upload begins** (in the `handleSave` function, before the first upload):
```typescript
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

---

## Item 4: Graph Pause/Unpause on Mouseover

### Current State

`GraphCanvas.tsx` renders `<ForceGraph2D>` with physics configured via:
- `d3AlphaDecay={0.02}`, `d3VelocityDecay={0.3}`, `cooldownTime={3000}`
- `enableNodeDrag={true}`

There is **no pause/resume logic**. The graph simulation runs continuously after data
loads, then cools down after 3 seconds. Node dragging temporarily "pins" the dragged
node but doesn't pause the overall simulation.

From the `react-force-graph-2d` SKILL reference (`custom_skills/react-force-graph-2d/SKILL.md`),
the `ForceGraphMethods` ref exposes imperative methods including:
- `pauseAnimation()` — freezes the canvas rendering loop
- `resumeAnimation()` — resumes the canvas rendering loop

### Target State

When the user's mouse enters the graph canvas area, the simulation pauses (nodes
stop moving). When the mouse leaves, the simulation resumes. This makes it easier
for users to hover over specific nodes to read labels and inspect tooltips without
the graph layout shifting under their cursor.

### Implementation

#### `GraphCanvas.tsx` — Add Pause/Resume

1. **Expose `pauseAnimation` and `resumeAnimation` via the imperative handle:**

```typescript
export interface GraphCanvasHandle {
  zoomToFit: () => void;
  pauseAnimation: () => void;   // NEW
  resumeAnimation: () => void;  // NEW
}

useImperativeHandle(ref, () => ({
  zoomToFit: () => fgRef.current?.zoomToFit(400, 40),
  pauseAnimation: () => fgRef.current?.pauseAnimation(),
  resumeAnimation: () => fgRef.current?.resumeAnimation(),
}), []);
```

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

#### `GraphTopologyViewer.tsx` — Wire Up Pause/Resume

```typescript
const canvasRef = useRef<GraphCanvasHandle>(null);
const [isPaused, setIsPaused] = useState(false);

const handleMouseEnter = useCallback(() => {
  canvasRef.current?.pauseAnimation();
  setIsPaused(true);
}, []);

const handleMouseLeave = useCallback(() => {
  canvasRef.current?.resumeAnimation();
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

- **Node dragging:** When a user starts dragging a node, the graph is already paused
  (mouse is over the canvas). Node drag still works because `pauseAnimation()` only
  stops the animation frame loop; `enableNodeDrag` operates via mouse events independently.
  However, we should **not** call `resumeAnimation` on mouse-up during a drag — only
  on mouseLeave. This is already correct with the current approach since we only resume
  on `onMouseLeave`.
- **Cooldown period:** If the graph hasn't finished its initial cooldown (3s after data
  load), pausing freezes the layout mid-settling. This is acceptable — the user
  intentionally moused over to inspect nodes.
- **Touch devices:** `onMouseEnter`/`onMouseLeave` won't fire on touch. The graph
  behaves as before on touch devices — no regression.

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
| Throughput | Autoscale max 400 RU/s |

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

```python
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
    Uses cross-partition query when no scenario filter.
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
        return list(container.query_items(
            query=query,
            parameters=params,
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
        return container.read_item(item=interaction_id, partition_key=scenario)
    item = await asyncio.to_thread(_get)
    return item


@router.delete("/interactions/{interaction_id}", summary="Delete an interaction")
async def delete_interaction(interaction_id: str, scenario: str = Query(...)):
    """Delete a specific interaction."""
    container = _get_interactions_container(ensure_created=False)
    def _delete():
        container.delete_item(item=interaction_id, partition_key=scenario)
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
    const url = scenario
      ? `/query/interactions?scenario=${encodeURIComponent(scenario)}&limit=50`
      : '/query/interactions?limit=50';
    const res = await fetch(url);
    const data = await res.json();
    setInteractions(data.interactions ?? []);
    setLoading(false);
  }, []);

  const saveInteraction = useCallback(async (interaction: {
    scenario: string;
    query: string;
    steps: StepEvent[];
    diagnosis: string;
    run_meta: RunMeta | null;
  }) => {
    const res = await fetch('/query/interactions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(interaction),
    });
    const saved = await res.json();
    setInteractions(prev => [saved, ...prev]);
    return saved;
  }, []);

  const deleteInteraction = useCallback(async (id: string, scenario: string) => {
    await fetch(`/query/interactions/${id}?scenario=${encodeURIComponent(scenario)}`, {
      method: 'DELETE',
    });
    setInteractions(prev => prev.filter(i => i.id !== id));
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

**`InteractionCard` sub-component** renders: relative timestamp, scenario badge,
truncated query text (line-clamp-2), step count + elapsed time, and a delete button
visible on hover.

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

  // Auto-save interaction when investigation completes
  const prevRunningRef = useRef(running);
  useEffect(() => {
    if (prevRunningRef.current && !running && finalMessage && activeScenario) {
      saveInteraction({
        scenario: activeScenario,
        query: alert,
        steps,
        diagnosis: finalMessage,
        run_meta: runMeta,
      });
    }
    prevRunningRef.current = running;
  }, [running, finalMessage]);

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
    options: { autoscaleSettings: { maxThroughput: 400 } }
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
    }
    options: { autoscaleSettings: { maxThroughput: 400 } }
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
- `frontend/src/components/graph/GraphCanvas.tsx` — add `pauseAnimation`/`resumeAnimation` to handle; add mouse event props; wrap in `<div>`
- `frontend/src/components/GraphTopologyViewer.tsx` — wire mouse enter/leave callbacks

**Verification:**
- Load graph topology → confirm nodes animate
- Mouse over graph → confirm animation pauses
- Mouse out → confirm animation resumes
- Confirm node drag + hover tooltips still work while paused

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
| `frontend/src/components/MetricsBar.tsx` | MODIFY | 4 | Add third `<Panel>` with Graph API `<LogStream>` |
| `frontend/src/components/graph/GraphCanvas.tsx` | MODIFY | 5 | Add pause/resume to handle; mouse event props; wrapper div |
| `frontend/src/components/GraphTopologyViewer.tsx` | MODIFY | 5 | Wire mouse enter/leave |
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

**Rapid mouse enter/leave:** `pauseAnimation()`/`resumeAnimation()` are idempotent.

**Initial layout:** Pausing during cooldown freezes mid-settle. Acceptable — mouse
removal resumes.

**Touch devices:** No regression — `onMouseEnter`/`onMouseLeave` don't fire on touch.

### Interaction Sidebar (Item 5)

**Large history:** `limit=50` default prevents overloading. Older records remain
in Cosmos.

**Auto-save race condition:** Use `ref` for `runMeta` to capture correct value.

**Viewing vs. running:** Starting a new investigation clears `viewingInteraction`.

**Partition key:** Cross-scenario queries use `enable_cross_partition_query=True`.
Acceptable for < 1000 interactions.

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
try:
    # Try shared DB with prefixed container
    container = db.get_container_client(f"{prefix}-{container_name}")
except:
    # Fallback to old per-scenario DB
    old_db = client.get_database_client(f"{prefix}-telemetry")
    container = old_db.get_container_client(container_name)
```

This fallback can be removed after all scenarios are re-uploaded.

### API Surface Compatibility

All API endpoints remain the same. Changes are internal to the data layer.
Frontend is unaffected except for the `SavedScenario.resources` type update
(additive — new fields).