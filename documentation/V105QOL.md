# V10.5 QOL Improvements — Implementation Plan

> **Created:** 2026-02-16
> **Last audited:** 2026-02-16
> **Status:** ⬜ Not Started
> **Goal:** Five targeted quality-of-life fixes: repair resource visualizer
> edges, enforce scenario.yaml naming, reorganise tarball output, widen
> scenario dropdown, and add an always-accessible example questions dropdown
> next to the investigation chatbox.

---

## Requirements (Original)

4. Resource visualizer kind of sucks — It's not showing relationships between tools and their datasources and then the data and the underlying infrastructure etc. The nodes are there but the relationships are not.
5. No custom scenario naming allowed anymore. Only names specified in scenario.yamls are allowed. Some UI changes are needed.
6. Move tarballs into the folders they belong to — need to change tarball generation script.
7. Scenario dropdown needs to be wider so the text of the scenario name doesn't get cut off.
8. Example questions should not just be in scenario info. Should also be in a dropdown menu next to the 'submit alert' chatbox.

---

## Implementation Status

| Phase | Status | Scope |
|-------|--------|-------|
| **Phase 1:** Resource visualizer edge fixes | ⬜ Not started | `api/app/routers/config.py`, `ResourceVisualizer.tsx`, `useResourceGraph.ts` |
| **Phase 2:** Enforce scenario.yaml naming | ⬜ Not started | `AddScenarioModal.tsx`, `router_ingest.py` |
| **Phase 3:** Tarball output reorganisation | ⬜ Not started | `data/generate_all.sh` |
| **Phase 4:** Scenario dropdown width | ⬜ Not started | `ScenarioChip.tsx` |
| **Phase 5:** Example questions dropdown | ⬜ Not started | `AlertInput.tsx`, `InvestigationPanel.tsx` |

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
- [Item 4: Resource Visualizer Edge Fixes](#item-4-resource-visualizer-edge-fixes)
- [Item 5: Enforce Scenario YAML Naming](#item-5-enforce-scenario-yaml-naming)
- [Item 6: Tarball Output Reorganisation](#item-6-tarball-output-reorganisation)
- [Item 7: Scenario Dropdown Width](#item-7-scenario-dropdown-width)
- [Item 8: Example Questions Dropdown](#item-8-example-questions-dropdown)
- [Implementation Phases](#implementation-phases)
- [File Change Inventory](#file-change-inventory)
- [Edge Cases & Validation](#edge-cases--validation)
- [Migration & Backwards Compatibility](#migration--backwards-compatibility)

---

## Codebase Conventions & Context

### Request Routing

| URL prefix | Proxied to | Config |
|------------|-----------|--------|
| `/api/*` | API service on port 8000 | `nginx.conf` |
| `/query/*` | graph-query-api on port 8100 | `nginx.conf` |

The resource visualizer endpoint lives in the **API service** at `/api/config/resources`.
It internally calls the graph-query-api at `http://127.0.0.1:8100/query/scenario/config?scenario=<name>` to fetch the stored scenario config, then builds the node/edge graph via `_build_resource_graph()`.

### Naming Conventions

| Concept | Example | Derivation |
|---------|---------|-----------|
| Scenario name | `"telco-noc"` | From `scenario.yaml` `name:` field |
| Graph name | `"telco-noc-topology"` | `{scenario}-topology` (from `data_sources.graph.config.graph`) |
| Telemetry prefix | `"telco-noc"` | `data_sources.telemetry.config.container_prefix` |
| Search indexes | `"telco-noc-runbooks-index"` | `data_sources.search_indexes.runbooks.index_name` |
| Tarball naming | `telco-noc-graph.tar.gz` | `{scenario}-{type}.tar.gz` |

### Frontend Conventions

- Tailwind CSS with design tokens from `tailwind.config.js`
- Dark theme: backgrounds use `bg-neutral-bg*` / `bg-surface-*`, text uses `text-text-*`
- Dropdowns/flyouts use `absolute` positioning with `z-50`, `bg-neutral-bg2` (e.g., `ScenarioChip.tsx`), `rounded-lg`, `border border-white/10`
- Motion via `framer-motion` (`AnimatePresence`, `motion.div`)
- Props pass data down; context (`ScenarioContext`) for cross-cutting state

### Data Format Conventions

| Convention | Format | Where Used |
|-----------|--------|------------|
| Resource graph API response | `{ nodes: ResourceNode[], edges: ResourceEdge[], scenario: string }` | `/api/config/resources` → `useResourceGraph.ts` |
| `ResourceNode` | `{ id, label, type, meta }` | `resourceConstants.ts` defines types |
| `ResourceEdge` | `{ source, target, type, label }` | Source/target must match node `id` fields exactly |

---

## Overview of Changes

| # | Item | Category | Impact | Effort |
|---|------|----------|--------|--------|
| 4 | Resource visualizer edge fixes | Full-stack | **High** — core feature is broken | Medium |
| 5 | Enforce scenario.yaml naming | Full-stack | **Medium** — prevents naming confusion | Medium |
| 6 | Tarball output reorganisation | Script | **Low** — developer convenience | Small |
| 7 | Scenario dropdown width | Frontend | **Medium** — text truncation hurts usability | Small |
| 8 | Example questions dropdown | Frontend | **Medium** — discoverability improvement | Medium |

### Dependency Graph

```
Phase 1 (Resource viz)     ← Independent
Phase 2 (YAML naming)     ← Independent
Phase 3 (Tarballs)         ← Independent
Phase 4 (Dropdown width)   ← Independent
Phase 5 (Example Qs)       ← Independent
```

All phases are independent and can be parallelised.

---

## Item 4: Resource Visualizer Edge Fixes

### Current State

The resource visualizer (`Resources` tab) renders a force-directed graph using `react-force-graph-2d`. Data comes from:

1. **Frontend:** `useResourceGraph.ts` fetches `GET /api/config/resources`
2. **Backend:** `api/app/routers/config.py` → `_build_resource_graph(config, scenario_name)`
3. **Rendering:** `ResourceCanvas.tsx` renders nodes and edges

The backend function `_build_resource_graph()` constructs edges in 6 categories:

| Edge type | From → To | Mechanism |
|-----------|-----------|-----------|
| `delegates_to` | orchestrator → sub-agent | Loops `ag.connected_agents[]` |
| `uses_tool` | agent → tool | Loops `ag.tools[]` |
| `queries` | tool → datasource | `tool.data_source` matched against `data_sources` dict |
| `runs_on` | agent → infra-foundry | Every agent → `infra-foundry` |
| `contains` | datasource → infra (Gremlin, NoSQL, Blob) | Type-based mapping |
| `hosted_on` | datasource → infra (AI Search) | Type-based mapping |

> **Note:** The frontend `resourceConstants.ts` also defines `stores_in` and
> `indexes_from` edge types, but the backend never generates these. They are
> currently dead constants.

**Problem:** Nodes render but edges/relationships do not. Multiple potential root causes:

#### Root Cause 1: Scenario config fetch fails silently

At the `/api/config/resources` endpoint, the backend:
1. Derives `scenario_name` from the current graph name: `graph.rsplit("-", 1)[0]`
2. Calls `GET http://127.0.0.1:8100/query/scenario/config?scenario={scenario_name}`
3. If this call **fails** (timeout, 404, no config in Cosmos), it catches the exception, logs at `logger.debug` level (invisible in production), and returns `{"nodes": [], "edges": []}` — effectively silent.

If the graph-query-api has no stored config for the scenario, the entire resource graph is empty.

#### Root Cause 2: Scenario name derivation is wrong

```python
graph = cfg.get("graph", "topology")
scenario_name = graph.rsplit("-", 1)[0] if "-" in graph else graph
```

If `graph` is `"topology"` (the default when no scenario override was set), then `scenario_name = "topology"` — which likely doesn't match any stored scenario config. Config fetch fails → empty graph.

#### Root Cause 3: Node ID mismatches cause silent edge drops

`react-force-graph-2d` **silently drops edges whose source or target don't match any node ID**. If:
- `connected_agents` references don't exactly match agent `name` fields → `delegates_to` edges silently vanish
- `tool.data_source` doesn't match a key in `data_sources` → `queries` edges never created

#### Root Cause 4: Frontend filtering hides edges

In `ResourceVisualizer.tsx`, edges are filtered to only include those whose **both** source and target are in `filteredNodeIds`. If a type filter is active (e.g., showing only "agent"), all edges to tools/datasources/infra vanish because those nodes are filtered out.

#### Root Cause 5: Edge colours invisible on dark backgrounds

If an edge `type` is not in `RESOURCE_EDGE_COLORS`, fallback is `'rgba(255,255,255,0.12)'` — nearly invisible on dark backgrounds.

### Target State

All relationship edges render visibly between nodes:
- Orchestrator → sub-agents (blue solid lines)
- Agents → tools (amber dashed lines)
- Tools → datasources (green dashed lines)
- Datasources → infrastructure (subtle connecting lines)
- Agents → AI Foundry (orange connecting lines)

```
┌──────────────────────────────────────────────────────────────┐
│  Resources Tab                                               │
│                                                              │
│  [orchestrator] ──delegates──▶ [agent1]                     │
│       │                          │                           │
│       │ uses_tool                │ uses_tool                 │
│       ▼                          ▼                           │
│  [tool: OpenAPI] ──queries──▶ [ds: graph]──contains──▶[Cosmos]│
│                                                              │
│  All agents ──runs_on──▶ [AI Foundry]                       │
└──────────────────────────────────────────────────────────────┘
```

### Backend Changes

#### `api/app/routers/config.py` — Fix scenario name resolution + error visibility

**Fix 1: Use `activeScenario` directly instead of deriving from graph name**

The `/api/config/resources` endpoint should accept the scenario name directly (e.g., via query param or header) rather than deriving it from the graph name, which is error-prone.

```python
# Current (fragile) — in get_resource_graph() (L434/L443):
graph = cfg.get("graph", "topology")
scenario_name = graph.rsplit("-", 1)[0] if "-" in graph else graph

# New: Add Request parameter to accept scenario name from header:
@router.get("/resources", summary="Get resource graph for visualization")
async def get_resource_graph(request: Request):
    # Try X-Scenario header first, fall back to graph-name derivation
    cfg = _load_current_config()
    graph = cfg.get("graph", "topology")
    scenario_name = (
        request.headers.get("X-Scenario")
        or (graph.rsplit("-", 1)[0] if "-" in graph else graph)
    )
```

> **⚠️ Note:** The current function is `async def get_resource_graph()` with no
> parameters. Adding `request: Request` requires importing `Request` from
> `starlette.requests` (or `fastapi`). The route decorator is
> `@router.get("/resources")` (not `/config/resources` — the `/api/config`
> prefix comes from `router = APIRouter(prefix="/config")` at the top of the file).

**Fix 2: Log errors instead of silently returning empty graph**

```python
# Current (logs at debug level only — invisible in production):
except Exception as e:
    logger.debug("Could not fetch scenario config for resources: %s", e)
    return {"nodes": [], "edges": [], "scenario": scenario_name}

# New (log at warning level, return partial graph with infra nodes at minimum):
except Exception as e:
    logger.warning(f"Failed to fetch scenario config for '{scenario_name}': {e}")
    # Return at least infra nodes so the user sees something
    return {"nodes": _infra_nodes_only(), "edges": [], "error": str(e)}
```

**Fix 3: Validate node ID references before emitting edges**

```python
# Add validation after building all nodes:
node_ids = {n["id"] for n in nodes}
edges = [e for e in edges if e["source"] in node_ids and e["target"] in node_ids]
```

> **⚠️ Implementation note:** The `connected_agents` list in `scenario.yaml` uses
> agent **names** (e.g., `"graph-analyst"`), and the node ID format is `"agent-{name}"`.
> The current code correctly prefixes with `agent-`, but if `connected_agents`
> contains the prefixed form, edge targets would become `"agent-agent-graph-analyst"`.
> Verify the format in each scenario.yaml.

### Frontend Changes

#### `useResourceGraph.ts` — Pass scenario name header

```tsx
// Current:
const res = await fetch('/api/config/resources');

// New: Send X-Scenario header so backend doesn't have to derive it:
const res = await fetch('/api/config/resources', {
  headers: { 'X-Scenario': activeScenario || '' },
});
```

#### `ResourceVisualizer.tsx` — Improve edge filtering + show error state

When type filters are active, include edges that connect two **visible** nodes AND edges that connect a visible node to a hidden node **if the hidden node's type is "infrastructure"** (so structural relationships remain visible even with filters).

Also: show an error/warning banner when the API returns an error field.

#### `resourceConstants.ts` — Increase edge visibility

Increase alpha values for edge colours to make them more visible:

```tsx
// Current:
delegates_to: 'rgba(96,165,250,0.5)',   // blue-400
uses_tool:    'rgba(245,158,11,0.4)',   // amber
queries:      'rgba(34,197,94,0.4)',    // green
stores_in:    'rgba(6,182,212,0.4)',    // cyan
hosted_on:    'rgba(249,115,22,0.3)',   // orange
indexes_from: 'rgba(139,92,246,0.4)',   // violet
runs_on:      'rgba(249,115,22,0.3)',   // orange
contains:     'rgba(255,255,255,0.15)', // subtle

// New (increase alpha for better visibility):
delegates_to: 'rgba(96,165,250,0.7)',
uses_tool:    'rgba(245,158,11,0.6)',
queries:      'rgba(34,197,94,0.6)',
stores_in:    'rgba(6,182,212,0.6)',    // cyan — up from 0.4
hosted_on:    'rgba(249,115,22,0.5)',   // orange — up from 0.3
indexes_from: 'rgba(139,92,246,0.6)',   // violet — up from 0.4
runs_on:      'rgba(249,115,22,0.5)',   // orange — up from 0.3
contains:     'rgba(255,255,255,0.3)',  // up from 0.15
```

> **⚠️ Note:** `stores_in` and `indexes_from` are defined in the frontend
> constants but the backend `_build_resource_graph()` never emits these edge
> types. They may be intended for future use, or they represent a frontend/
> backend mismatch that should be investigated.

### UX Enhancements

#### 4a. Loading state for resource graph — ALREADY EXISTS

**Problem:** No feedback while the resource graph is loading.

**Current state:** `ResourceVisualizer.tsx` (lines 181–188) already renders a spinner overlay with "Loading resource graph…" text when `loading` is true. **No new work needed** unless we want to improve the visual treatment.

#### 4b. Empty state with diagnostic info — PARTIALLY EXISTS

**Problem:** When the graph returns empty, user sees a blank canvas with no explanation.

**Current state:** `ResourceVisualizer.tsx` (lines 199–205) already shows "No resources to display" with a hint to upload a scenario. **What's missing:** the empty state doesn't distinguish between "no scenario active" vs. "scenario has no config data" and has no Retry button. Enhance to include an `error` field check from the API response and a Retry button.

#### 4c. Edge labels on hover — ALREADY EXISTS

**Problem:** Edge type is not visible — users don't know what a line means.

**Current state:** `ResourceCanvas.tsx` (line ~234–246) already renders `link.label` text at the midpoint of each edge on the canvas. `ResourceTooltip.tsx` `EdgeContent` component (line ~60–67) already shows `edge.label`, source→target, and `edge.type` on hover. **No new work needed** — edge labels are already implemented in both the canvas and tooltip.

---

## Item 5: Enforce Scenario YAML Naming

### Current State

The `AddScenarioModal` has a freely editable text input for the scenario name (`name` state). It auto-detects the name from tarball filenames via `detectSlot()` but allows the user to override it. The backend in `router_ingest.py` supports overrides via `_rewrite_manifest_prefix()`.

**Problem:** Custom naming leads to confusion and potential resource naming mismatches. The user wants to enforce that scenario names must come from the `scenario.yaml` inside the uploaded tarballs — no user overrides.

### Target State

1. The scenario name field in `AddScenarioModal` becomes **read-only**, auto-populated from the `name:` field inside the first uploaded tarball's `scenario.yaml`.
2. Before any tarball is uploaded, the name field is empty and shows a placeholder: `"Detected from scenario.yaml"`.
3. After the first tarball containing a `scenario.yaml` is parsed, the name auto-fills and becomes locked.
4. The backend ignores the `scenario_name` override parameter — always uses the manifest's embedded name.
5. The `_rewrite_manifest_prefix()` function is removed or made dead code (it only exists to support overrides).
6. The mismatch warning (yellow hint) is removed since mismatches are now impossible.

```
┌── Add Scenario ──────────────────────────────┐
│                                               │
│  Scenario Name                                │
│  ┌─────────────────────────────────────────┐  │
│  │ telco-noc                          🔒   │  │
│  └─────────────────────────────────────────┘  │
│  ℹ Name read from scenario.yaml (read-only)  │
│                                               │
│  Drop files here...                           │
│  ┌─────────────────────────────────────────┐  │
│  │  📦 Graph     telco-noc-graph.tar.gz ✓  │  │
│  │  📊 Telemetry telco-noc-tele...tar.gz ✓ │  │
│  │  📚 Runbooks  (empty)                    │  │
│  │  🎫 Tickets   (empty)                    │  │
│  │  💬 Prompts   (empty)                    │  │
│  └─────────────────────────────────────────┘  │
│                                               │
│                              [Cancel] [Save]  │
└───────────────────────────────────────────────┘
```

### Backend Changes

#### `graph-query-api/router_ingest.py` — Remove override support

```python
# Current (graph upload endpoint):
sc_name = scenario_name or manifest["name"]
if scenario_name and scenario_name != manifest.get("name"):
    manifest = _rewrite_manifest_prefix(manifest, scenario_name)

# New: Always use manifest name, ignore scenario_name param:
sc_name = manifest["name"]
# _rewrite_manifest_prefix call removed
```

The `scenario_name` query parameter can be kept for backwards compatibility but is ignored. Document it as deprecated.

> **⚠️ Implementation note:** Only **graph** and **telemetry** endpoints call
> `_rewrite_manifest_prefix()` directly (graph at L477, telemetry at L581).
> The other 3 endpoints (**runbooks**, **tickets**, **prompts**) use a different
> function: `_resolve_scenario_name(tmppath, override, fallback)` (defined at
> L362), which prioritises `override > scenario.yaml > fallback`. For these 3,
> the fix is to change `_resolve_scenario_name()` to ignore the `override`
> parameter (or remove it) so it always returns the `scenario.yaml` name.
>
> Summary of changes per endpoint:
> - **graph** (L462–477): Remove `_rewrite_manifest_prefix` call; use `manifest["name"]` directly
> - **telemetry** (L577–581): Remove `_rewrite_manifest_prefix` call; use `manifest["name"]` directly
> - **runbooks** (L673): Change `_resolve_scenario_name` to not accept/use override
> - **tickets** (via `_upload_knowledge_files` L673): Same as runbooks
> - **prompts** (L883): Change `_resolve_scenario_name` to not accept/use override

### Frontend Changes

#### `AddScenarioModal.tsx` — Lock name to YAML-derived value

1. **Extract `name` from `scenario.yaml` inside the tarball.** Currently, `detectSlot()` only parses the tarball **filename** (e.g., `telco-noc-graph.tar.gz` → `telco-noc`). It needs to also read the `scenario.yaml` file inside the tarball to extract the `name:` field.

   Since tarballs are parsed client-side, this requires reading the tar contents in the browser. The existing upload flow already reads the file — extend `detectSlot()` or add a `parseScenarioYamlFromTar()` utility that:
   - Reads the tarball as an `ArrayBuffer`
   - Decompresses with `DecompressionStream('gzip')` (Web Streams API)
   - Parses the tar headers to find `scenario.yaml`
   - Extracts and YAML-parses the `name:` field

   **Alternative (simpler):** Continue using filename-based detection from `detectSlot()` but make the name field **read-only** after auto-detection. This is simpler and the tarball filename already matches the YAML name in all generated tarballs (since `generate_all.sh` uses the directory name, which matches `scenario.yaml`'s `name`).

2. **Make the name input `readOnly`:**

```tsx
<input
  type="text"
  value={name}
  readOnly                          // ← Always read-only
  className="... cursor-not-allowed opacity-75"
  placeholder="Detected from uploaded files"
/>
```

3. **Remove the `onChange` handler** and the `nameAutoDetected` state.

4. **Update hint text:**

```tsx
{name && (
  <p className="text-xs text-text-muted mt-1 italic">
    Name read from scenario.yaml — cannot be overridden
  </p>
)}
```

5. **Remove the mismatch warning** (yellow hint for name vs filename mismatch).

### UX Enhancements

#### 5a. Visual lock indicator

**Problem:** A read-only field might confuse users about whether it's editable.

**Fix:** Add a small lock icon (🔒) inside the input, right-aligned.

#### 5b. Clear error when no YAML name detected

**Problem:** If the user uploads a tarball that has no `scenario.yaml` (or it's malformed), the name stays empty and the user can't proceed.

**Fix:** Show a red error: "Could not detect scenario name — ensure your tarball contains a valid scenario.yaml with a `name:` field."

---

## Item 6: Tarball Output Reorganisation

### Current State

`data/generate_all.sh` outputs all tarballs into the flat `data/scenarios/` directory:

```
data/scenarios/
├── telco-noc/                      ← scenario source folder
├── telco-backbone/                 ← scenario source folder
├── telco-noc-graph.tar.gz          ← tarball sits beside its source folder
├── telco-noc-telemetry.tar.gz
├── telco-noc-runbooks.tar.gz
├── telco-noc-tickets.tar.gz
├── telco-noc-prompts.tar.gz
├── telco-backbone-graph.tar.gz
├── telco-backbone-telemetry.tar.gz
└── ...
```

**Problem:** Tarballs clutter the `scenarios/` directory. They should live inside their respective scenario folders.

### Target State

```
data/scenarios/
├── telco-noc/
│   ├── scenario.yaml
│   ├── data/
│   ├── telco-noc-graph.tar.gz      ← tarball inside its scenario folder
│   ├── telco-noc-telemetry.tar.gz
│   ├── telco-noc-runbooks.tar.gz
│   ├── telco-noc-tickets.tar.gz
│   └── telco-noc-prompts.tar.gz
├── telco-backbone/
│   ├── scenario.yaml
│   ├── data/
│   ├── telco-backbone-graph.tar.gz
│   └── ...
└── hello-world/
    └── scenario.yaml               ← No tarballs until generation runs
```

### Script Changes

#### `data/generate_all.sh` — Change output paths

Every `tar czf` command's output path changes from `$SCENARIOS_DIR/$SCENARIO-{type}.tar.gz` to `$SCENARIOS_DIR/$SCENARIO/$SCENARIO-{type}.tar.gz`:

```bash
# Current:
tar czf "$SCENARIOS_DIR/$SCENARIO-graph.tar.gz" -C "$SCENARIOS_DIR" \
  "$SCENARIO/scenario.yaml" "$SCENARIO/graph_schema.yaml" "$SCENARIO/data/entities" 2>/dev/null

# New:
tar czf "$SCENARIOS_DIR/$SCENARIO/$SCENARIO-graph.tar.gz" -C "$SCENARIOS_DIR" \
  "$SCENARIO/scenario.yaml" "$SCENARIO/graph_schema.yaml" "$SCENARIO/data/entities" 2>/dev/null
```

Same change for all 5 tarball types: `graph`, `telemetry`, `runbooks`, `tickets`, `prompts`.

The `du -h` and listing sections at the bottom also need updated paths:

```bash
# Current:
echo -e "  ${GREEN}✓${NC} $SCENARIO-graph.tar.gz ($(du -h "$SCENARIOS_DIR/$SCENARIO-graph.tar.gz" | cut -f1))"

# New:
echo -e "  ${GREEN}✓${NC} $SCENARIO-graph.tar.gz ($(du -h "$SCENARIOS_DIR/$SCENARIO/$SCENARIO-graph.tar.gz" | cut -f1))"
```

And the final listing:

```bash
# Current:
T="$SCENARIOS_DIR/$SCENARIO-$TYPE.tar.gz"

# New:
T="$SCENARIOS_DIR/$SCENARIO/$SCENARIO-$TYPE.tar.gz"
```

### UX Enhancements

#### 6a. Clean up old tarballs

**Problem:** After changing the script, old tarballs in `data/scenarios/*.tar.gz` remain.

**Fix:** Add a one-time cleanup step at the top of the script or a separate `clean` flag:

```bash
# Optional: remove old flat tarballs
if [ "$1" = "--clean" ]; then
  rm -f "$SCENARIOS_DIR"/*.tar.gz
  echo "Cleaned old flat tarballs"
fi
```

Or: just manually `rm data/scenarios/*.tar.gz` after the change and add `*.tar.gz` to `.gitignore` in `data/scenarios/`.

#### 6b. Add .gitignore for tarballs

**Fix:** Add `/data/scenarios/*/*.tar.gz` to the repo's `.gitignore` so generated tarballs aren't committed.

---

## Item 7: Scenario Dropdown Width

### Current State

In `ScenarioChip.tsx`:

1. **Chip label** (line 76): `<span className="max-w-[140px] truncate">` — hard-caps the scenario name display at 140px, truncating with ellipsis.
2. **Flyout dropdown** (line 84): `<div className="... w-56 ...">` — fixed width of 224px (14rem). Each dropdown item also has `truncate`.

**Problem:** Scenario names like `"telco-backbone-extended"` or `"customer-recommendation"` get cut off in both the chip and the dropdown.

### Target State

```
┌─────────────────────────────────────────┐
│ 🟢 customer-recommendation        ▾    │  ← Chip: wider, full name visible
├─────────────────────────────────────────┤
│  telco-noc                              │  ← Dropdown: wider, no truncation
│  telco-backbone                         │
│  customer-recommendation                │
│  cloud-infrastructure-outage            │
│  ──────────────────────────────────────  │
│  + New Scenario                         │
└─────────────────────────────────────────┘
```

### Frontend Changes

#### `ScenarioChip.tsx` — Widen chip + dropdown

```tsx
// Line 76 — Chip label width:
// Current:
<span className="max-w-[140px] truncate">

// New:
<span className="max-w-[280px] truncate">


// Line 84 — Flyout dropdown width:
// Current:
<div className="... w-56 ...">

// New:
<div className="... w-80 ...">
```

`w-80` = 320px (20rem), which accommodates names up to ~35 characters at 14px font size.

Optionally also remove `truncate` from dropdown items (line 103) so the full name always shows, and let the dropdown grow to fit:

```tsx
// Current:
<span className="truncate">{s.display_name || s.id}</span>

// New:
<span>{s.display_name || s.id}</span>
```

> **⚠️ Implementation note:** The Header is a `flex` row. Widening the chip
> may push other elements (HealthDot, agent status, SettingsModal) rightward.
> Verify the header doesn't overflow on narrow viewports. If it does, consider
> `max-w-[280px]` + `truncate` (chip still truncates but at a larger width).

---

## Item 8: Example Questions Dropdown

### Current State

Example questions flow through the system at three points:

1. **`ScenarioInfoPanel`** — Displays example questions as clickable cards. Clicking one fills the alert textarea and switches to the Investigate tab. Only visible on the "Scenario Info" tab.

2. **`InvestigationPanel`** — Fetches the active scenario, extracts `example_questions`, and passes them to `AlertInput` as a prop.

3. **`AlertInput`** — Accepts `exampleQuestions?: string[]` and renders **chip-based suggestions** below the textarea, but **only when the textarea is empty** (`!alert.trim()`). Chips disappear once the user types.

**Problem:** Example questions are only visible in two places that require specific conditions: (a) the Scenario Info tab (requires switching tabs), or (b) chip suggestions that vanish when text is entered. There is no **persistent, always-accessible** way to browse and select example questions while on the Investigate tab.

### Target State

A dropdown button next to the "Investigate" submit button that shows all example questions in a popover menu. Always accessible regardless of textarea content.

```
┌─────────────────────────────────────────────────────┐
│  Describe the alert or incident...                  │
│                                                     │
│                                                     │
│                                                     │
├─────────────────────────────────────────────────────┤
│                                                     │
│  [💡▾ Examples]   [▶ Investigate               ]   │
│                                                     │
└─────────────────────────────────────────────────────┘
       │
       ▼ (dropdown open)
┌──────────────────────────────────────────┐
│  Example Questions                        │
│  ─────────────────────────────────────── │
│  Multiple cell sites are reporting...     │
│  BGP session between router-core-01...    │
│  Transport link utilisation on the...     │
│  SLA breach detected on the premium...    │
└──────────────────────────────────────────┘
```

### Frontend Changes

#### `AlertInput.tsx` — Add example questions dropdown button

Add a new dropdown button component inline with the submit button:

```tsx
// New state:
const [examplesOpen, setExamplesOpen] = useState(false);

// New JSX — button row below textarea:
<div className="mt-3 flex gap-2">
  {/* Example questions dropdown */}
  {exampleQuestions && exampleQuestions.length > 0 && (
    <div className="relative">
      <button
        type="button"
        onClick={() => setExamplesOpen(!examplesOpen)}
        className="flex items-center gap-1.5 px-3 py-2 text-sm
                   bg-white/5 hover:bg-white/10 border border-white/10
                   rounded-lg text-text-muted hover:text-text-primary
                   transition-colors"
      >
        <span>💡</span>
        <span>Examples</span>
        <span className="text-xs">▾</span>
      </button>

      {examplesOpen && (
        <div className="absolute bottom-full mb-1 left-0 w-80
                        bg-neutral-bg2 border border-white/10
                        rounded-lg shadow-xl z-50 max-h-64 overflow-y-auto">
          <div className="p-2">
            <p className="text-xs text-text-muted px-2 py-1 uppercase tracking-wide">
              Example Questions
            </p>
            {exampleQuestions.map((q, i) => (
              <button
                key={i}
                className="w-full text-left px-3 py-2 text-sm rounded-lg
                           hover:bg-white/10 text-text-secondary
                           hover:text-text-primary transition-colors"
                onClick={() => {
                  onAlertChange(q);
                  setExamplesOpen(false);
                }}
              >
                {q.length > 80 ? q.slice(0, 80) + '…' : q}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )}

  {/* Existing Investigate button — migrated from standalone w-full to flex-1 */}
  <motion.button className="flex-1 ..." ...>
    ▶ Investigate
  </motion.button>
</div>
```

> **⚠️ Layout gotcha:** The existing Investigate `<motion.button>` currently has
> `mt-3 w-full` applied directly (line 53). When wrapping it in the flex row:
> 1. Move `mt-3` to the wrapper `<div className="mt-3 flex gap-2">`
> 2. Change the button from `w-full` to `flex-1` so it shares the row
> 3. Keep all other classes (`py-2.5`, `rounded-lg`, `bg-brand`, etc.) unchanged
>
> Without these changes, the button will either have double top-margin or
> fight the flex layout with `w-full`.

The existing chip suggestions below the textarea can remain for the empty-textarea case — they provide a different (scan-friendly) UX for first-time users.

#### Close-on-outside-click

Add a `useEffect` with a document click listener that closes the dropdown when clicking outside, following the same pattern as `ScenarioChip.tsx`'s flyout:

```tsx
const dropdownRef = useRef<HTMLDivElement>(null);

useEffect(() => {
  if (!examplesOpen) return;
  const handler = (e: MouseEvent) => {
    if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
      setExamplesOpen(false);
    }
  };
  document.addEventListener('mousedown', handler);
  return () => document.removeEventListener('mousedown', handler);
}, [examplesOpen]);
```

### UX Enhancements

#### 8a. Dropdown opens upward

**Problem:** The button is at the bottom of the investigation panel. A downward dropdown would be clipped by the panel edge.

**Fix:** Use `bottom-full mb-1` positioning (shown in the code above) so the dropdown opens **upward** from the button.

#### 8b. Question preview with full text on hover

**Problem:** Long example questions are truncated in the dropdown.

**Fix:** Truncate display text to ~80 chars with `…`, but show the full text in a `title` tooltip on hover:

```tsx
<button title={q} ...>
  {q.length > 80 ? q.slice(0, 80) + '…' : q}
</button>
```

#### 8c. Keyboard navigation

**Fix:** Add `onKeyDown` handler for arrow keys + Enter to navigate the dropdown items. Low priority — can be a follow-up.

---

## Implementation Phases

### Phase 1: Resource Visualizer Edge Fixes

> Independent — no prerequisites.

**Files to modify:**
- `api/app/routers/config.py` — Fix scenario name resolution; add error logging; validate node ID refs
- `frontend/src/hooks/useResourceGraph.ts` — Send `X-Scenario` header
- `frontend/src/components/ResourceVisualizer.tsx` — Improve edge filtering; add error/empty states
- `frontend/src/components/resource/resourceConstants.ts` — Increase edge alpha values

**Verification:**
1. Navigate to Resources tab with an active, provisioned scenario
2. **Verify edges render** between: orchestrator → agents, agents → tools, tools → datasources, datasources → infra
3. Check browser devtools Network tab: `GET /api/config/resources` should return non-empty `edges[]`
4. Toggle type filters on/off — edges should update correctly
5. **With no active scenario**: should show empty state with helpful message, not blank canvas

### Phase 2: Enforce Scenario YAML Naming

> Independent — no prerequisites.

**Files to modify:**
- `frontend/src/components/AddScenarioModal.tsx` — Make name field read-only, remove override logic
- `graph-query-api/router_ingest.py` — Remove `_rewrite_manifest_prefix()` calls; always use manifest name

**Verification:**
1. Open Add Scenario modal → name field shows placeholder "Detected from uploaded files"
2. Drop a tarball → name auto-fills from filename → field is **not editable**
3. Try typing in the name field → cursor should not enter, field should appear locked
4. Upload completes → scenario saved with the auto-detected name
5. Backend: upload with `?scenario_name=override` → verify the override is **ignored** and manifest name is used

### Phase 3: Tarball Output Reorganisation

> Independent — no prerequisites.

**Files to modify:**
- `data/generate_all.sh` — Change all output paths from `$SCENARIOS_DIR/` to `$SCENARIOS_DIR/$SCENARIO/`

**Verification:**
1. Run `./data/generate_all.sh telco-noc`
2. Verify tarballs appear in `data/scenarios/telco-noc/telco-noc-*.tar.gz`
3. Verify NO tarballs appear in `data/scenarios/telco-noc-*.tar.gz` (flat level)
4. Remove old flat tarballs: `rm data/scenarios/*.tar.gz`

### Phase 4: Scenario Dropdown Width

> Independent — no prerequisites.

**Files to modify:**
- `frontend/src/components/ScenarioChip.tsx` — Widen chip label max-w and dropdown width

**Verification:**
1. Create/switch to a scenario with a long name (20+ chars)
2. Verify full name is visible in the Header chip (no truncation for reasonable names)
3. Open dropdown → verify all scenario names are fully readable
4. **Narrow viewport test**: resize browser to ~1024px width → verify header doesn't overflow

### Phase 5: Example Questions Dropdown

> Independent — no prerequisites.

**Files to modify:**
- `frontend/src/components/AlertInput.tsx` — Add dropdown button + flyout menu

**Verification:**
1. Switch to a scenario that has `example_questions` defined
2. Verify 💡 Examples button appears next to "Investigate" button
3. Click → dropdown opens **upward** showing all example questions
4. Click a question → textarea fills with that question, dropdown closes
5. Click outside dropdown → dropdown closes
6. **No example questions**: verify button is hidden when `exampleQuestions` is empty/undefined
7. Existing chip suggestions should still work when textarea is empty

---

## File Change Inventory

| File | Action | Phase | Changes |
|------|--------|-------|---------|
| `api/app/routers/config.py` | MODIFY | 1 | Fix scenario name resolution; add error logging; validate edge refs |
| `frontend/src/hooks/useResourceGraph.ts` | MODIFY | 1 | Send `X-Scenario` header with fetch |
| `frontend/src/components/ResourceVisualizer.tsx` | MODIFY | 1 | Improve edge filtering; add error/empty state (~20 lines) |
| `frontend/src/components/resource/resourceConstants.ts` | MODIFY | 1 | Increase edge colour alpha values |
| `frontend/src/components/AddScenarioModal.tsx` | MODIFY | 2 | Make name field readOnly; remove override logic (~15 lines changed) |
| `graph-query-api/router_ingest.py` | MODIFY | 2 | Remove `_rewrite_manifest_prefix()` usage in all 5 upload endpoints |
| `data/generate_all.sh` | MODIFY | 3 | Change tarball output paths (~12 lines changed) |
| `frontend/src/components/ScenarioChip.tsx` | MODIFY | 4 | Widen `max-w-[140px]` → `max-w-[280px]`; widen `w-56` → `w-80` |
| `frontend/src/components/AlertInput.tsx` | MODIFY | 5 | Add example questions dropdown button + flyout (~60 lines added) |

### Files NOT Changed

- `frontend/src/components/InvestigationPanel.tsx` — Already passes `exampleQuestions` to `AlertInput`; no change needed
- `frontend/src/components/ScenarioInfoPanel.tsx` — Example questions remain here as-is; the new dropdown is additive
- `frontend/src/components/resource/ResourceCanvas.tsx` — Edge rendering logic is correct (includes edge label drawing at midpoint); the issue is data not arriving
- `frontend/src/components/resource/ResourceTooltip.tsx` — Already shows edge label, source→target, and edge type on hover (EdgeContent component). No changes needed.
- `data/validate_scenario.py` — Unrelated to tarball output paths
- `frontend/src/components/Header.tsx` — No changes; ScenarioChip handles its own width

---

## Edge Cases & Validation

### Resource Visualizer (Item 4)

**No scenario active:** `useResourceGraph` should skip the fetch (already does — checks `activeScenario`). Empty state shown.

**Scenario config not in Cosmos yet:** Backend returns error field. Frontend shows error state with retry.

**Agent references non-existent connected_agent:** Edge validation (`source in node_ids && target in node_ids`) silently drops the invalid edge. No crash.

**All node types filtered out:** No edges shown (correct behaviour — nothing to connect).

### Scenario YAML Naming (Item 5)

**Tarball has no scenario.yaml inside:** `detectSlot()` falls back to filename-based name extraction. Name field auto-fills from filename. If filename parsing also fails, the name stays empty and Save is disabled (existing validation: `!name` → Save button disabled).

**Two tarballs with different scenario names:** The auto-detection uses majority voting (`counts` map, sorted by frequency). Whichever name appears most wins. Since all tarballs for a scenario should have the same name, this handles the mismatch gracefully.

**Backend receives no scenario_name param:** Falls back to `manifest["name"]` — correct behaviour, unchanged.

### Tarball Reorganisation (Item 6)

**Scenario folder doesn't exist:** `tar czf` into a non-existent path will fail. But this can't happen because we loop over existing `$SCENARIOS_DIR/*/` directories.

**Old tarballs remain at flat level:** Not cleaned up automatically. Must manually `rm data/scenarios/*.tar.gz`. Document this in the PR description.

### Scenario Dropdown Width (Item 7)

**Extremely long scenario names (50+ chars):** `max-w-[280px]` + `truncate` still clips at 280px. This handles all reasonable names; pathological names still truncate gracefully.

**Narrow viewport:** Header uses `flex` with `gap-3`. At 1024px widths, the header should not overflow with a 280px chip. Below ~900px, consider responsive adjustments (out of scope for this fix).

### Example Questions Dropdown (Item 8)

**No example questions for the scenario:** The dropdown button is conditionally rendered — hidden when `exampleQuestions` is empty/undefined. No visual noise.

**Very long question text:** Truncated to 80 chars in the dropdown with `title` attribute for full text on hover.

**Many example questions (10+):** Dropdown has `max-h-64 overflow-y-auto` — scrollable at 256px height. Each item is ~36px, so ~7 visible at once.

**Clicking outside dropdown:** Close handler via `mousedown` event listener on document. Same pattern as `ScenarioChip.tsx`.

---

## Migration & Backwards Compatibility

### Existing Data

- **Item 4 (Resource viz):** No data migration. Fix is in how the endpoint resolves and serves data.
- **Item 5 (YAML naming):** Existing scenarios with overridden names remain in Cosmos as-is. The change only affects **new** uploads going forward. No migration needed.
- **Item 6 (Tarballs):** Old tarballs at `data/scenarios/*.tar.gz` should be manually removed after the script change. Git-tracked tarballs (if any) need a commit removing them.

### API Surface Compatibility

- **Item 4:** `/api/config/resources` gains an optional `X-Scenario` header. Fully backwards-compatible — the endpoint falls back to the old graph-name derivation if the header is missing.
- **Item 5:** The `scenario_name` query parameter on upload endpoints is preserved but ignored. No breaking change for API callers, but behaviour changes (override silently unused).

### Rollback Plan

All changes are independently revertible:
- Phase 1–2: Revert frontend + backend commits separately
- Phase 3: Old tarballs can be regenerated with the old script (or just move them back manually)
- Phase 4–5: Pure frontend changes, trivially revertible

No feature flags needed — all changes are small, isolated, and low-risk.

---

## UX Priority Matrix

| Priority | Enhancement | Item | Effort | Impact |
|----------|------------|------|--------|--------|
| **P0** | Fix edge rendering (backend scenario name resolution) | 4 | Medium | High |
| **P0** | Make name field read-only | 5 | Small | Medium |
| **P0** | Move tarball output paths | 6 | Tiny | Low |
| **P0** | Widen chip + dropdown | 7 | Tiny | Medium |
| **P0** | Add example questions dropdown button | 8 | Small | Medium |
| **P1** | Improve empty state with error field + retry | 4a/4b | Small | Medium |
| **P1** | Visual lock indicator on name field | 5a | Tiny | Low |
| **P1** | Dropdown opens upward + question truncation | 8a/8b | Tiny | Medium |
| ~~P2~~ | ~~Edge labels on hover~~ | ~~4c~~ | — | — |
| **P2** | Error for missing scenario.yaml | 5b | Small | Low |
| **P2** | Gitignore for tarballs | 6b | Tiny | Low |
| **P3** | Keyboard navigation for examples dropdown | 8c | Medium | Low |

### Implementation Notes

- **P0 items** are the core of each requirement — implement in the same phase.
- **P1 items** are small polish that should be included if time permits.
- **P2–P3 items** are follow-ups that can be deferred without impact.
- ~~**4c (edge labels on hover)**~~ — already fully implemented in `ResourceCanvas.tsx` (midpoint text) and `ResourceTooltip.tsx` (`EdgeContent`). Remove from scope.
- **4a/4b** — loading spinner and empty state already exist in `ResourceVisualizer.tsx` L181–205. Scope is limited to *improving* the empty state with API error field support and a retry button.
