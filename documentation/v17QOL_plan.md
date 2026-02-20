# v17 QOL — Implementation Plan

> Generated from [v17QOL_requirements.md](v17QOL_requirements.md) after full codebase audit.

---

## Requirement Summary

| # | Requirement | Priority |
|---|------------|----------|
| 1 | Graph visualizer: stop recentering when toggling nodes | High |
| 2 | Edge display control bar (similar style to node bar) | High |
| 3 | Font size & color controls for node and edge labels | Medium |
| 4 | Conversation-card graphs: frozen by default | Medium |
| 6 | Remove min/max limits on all resizable panels | Medium |
| 7 | Resource tab: static architecture diagram from file | High |
| 8 | Zero regressions — additive only | Critical |
| 9 | Anti-contradiction / full audit | Critical |

---

## Req 1 — Prevent Graph Recentering on Node Toggle

### Root Cause

[GraphCanvas.tsx](../frontend/src/components/graph/GraphCanvas.tsx) lines 53-56:

```ts
useEffect(() => {
  if (fgRef.current && nodes.length > 0) {
    setTimeout(() => fgRef.current?.zoomToFit(400, 40), 500);
  }
}, [nodes.length]);
```

This fires whenever `nodes.length` changes — which happens every time a node-type filter chip is toggled in the toolbar. The graph re-fits to view, resetting the user's viewport.

### Plan

1. **Add a `suppressAutoFit` prop** to `GraphCanvas` (default `false`).
2. **In `GraphTopologyViewer`**: track whether the data change came from an initial load/refresh vs. a user filter toggle.
   - Introduce a `filterChangeRef = useRef(false)` flag. Set it `true` inside the `onToggleLabel` / `onSearchChange` handlers. Pass `suppressAutoFit={filterChangeRef.current}` to `GraphCanvas`, then reset the ref after render.
   - Alternatively (simpler): Replace the `nodes.length` dependency with a **data identity key** — compare `data.nodes.length` from `useTopology()` instead of `filteredNodes.length`. Since `data.nodes` only changes on fetch/refresh, filtering won't trigger the effect.
3. **Chosen approach**: Change the auto-fit `useEffect` in `GraphCanvas` to depend on a **stable data key** prop (e.g., `dataVersion: number`) that `GraphTopologyViewer` only bumps on initial load and refresh — never on filter toggles.

### Files to Modify

| File | Change |
|------|--------|
| `frontend/src/components/graph/GraphCanvas.tsx` | Add `dataVersion` prop; change `useEffect` dependency from `nodes.length` → `dataVersion`. |
| `frontend/src/components/GraphTopologyViewer.tsx` | Pass `dataVersion` derived from `useTopology()` fetch count (not from filtered node count). Add a `dataVersion` state that increments only on `refetch()` completion. |

### Regression Risks

- **ResourceCanvas.tsx** also has an auto-fit on `nodes.length`. Req 7 will replace the resource tab entirely, so no change needed there now. If we keep ResourceCanvas, apply same fix.
- **GraphResultView.tsx** (conversation cards) also auto-fits on `nodes.length` — but those don't have filter toggles, so unaffected.
- Node double-click still calls `centerAt + zoom`, which is intentional and separate from this fix.

---

## Req 2 — Edge Display Control Bar

### Current State

- Edges have a `label` field (e.g., `connects_to`, `aggregates_to`, `backhauls_via`, `routes_via`, `depends_on`, `governed_by`, `peers_with`).
- `TopologyMeta.labels` only returns **vertex** labels, not edge labels.
- Edges are currently filtered implicitly: an edge is shown iff both endpoints are visible.
- No explicit edge type toggle exists anywhere in the UI.

### Plan

1. **Derive edge labels** from `data.edges` in `GraphTopologyViewer`:
   ```ts
   const availableEdgeLabels = useMemo(
     () => [...new Set(data.edges.map(e => e.label))].sort(),
     [data.edges]
   );
   ```

2. **Add `activeEdgeLabels` state** (same toggling semantics as `activeLabels` — empty = all shown).

3. **Create `GraphEdgeToolbar` component** — sits directly below `GraphToolbar`:
   - Same visual style: `flex items-center gap-2 px-3 py-1.5 border-b border-border shrink-0`
   - Title: `"━ Edge Types"`
   - Edge label chips with color dots + toggle buttons
   - Edge colors: auto-assign from `COLOR_PALETTE` (or a dedicated edge palette)
   - Optional: color picker popover (reuse `ColorWheelPopover`)
   - Display counts: visible edges / total edges

4. **Update edge filtering** in `GraphTopologyViewer`:
   ```ts
   const filteredEdges = data.edges.filter((e) => {
     // Existing: both endpoints visible
     const srcId = typeof e.source === 'string' ? e.source : e.source.id;
     const tgtId = typeof e.target === 'string' ? e.target : e.target.id;
     if (!nodeIdSet.has(srcId) || !nodeIdSet.has(tgtId)) return false;
     // NEW: edge label filter
     if (activeEdgeLabels.length > 0 && !activeEdgeLabels.includes(e.label)) return false;
     return true;
   });
   ```

5. **Adjust `TOOLBAR_HEIGHT`** → now accounts for two bars. Change to `TOOLBAR_HEIGHT = 36 * 2` (or measure dynamically).

### Files to Create

| File | Purpose |
|------|---------|
| `frontend/src/components/graph/GraphEdgeToolbar.tsx` | New edge filter bar component |

### Files to Modify

| File | Change |
|------|--------|
| `frontend/src/components/GraphTopologyViewer.tsx` | Add `activeEdgeLabels` state, derive `availableEdgeLabels`, update edge filter logic, render `GraphEdgeToolbar`, adjust toolbar height. |
| `frontend/src/components/graph/graphConstants.ts` | Add `EDGE_COLOR_PALETTE` (or reuse existing `COLOR_PALETTE`). |

### Regression Risks

- Edge filtering is currently implicit only. Adding an explicit filter is purely additive — the existing node-based filter still applies as the first gate.
- The edge bar adds height, so `TOOLBAR_HEIGHT` must be updated to avoid the canvas thinking it has more space than it does.

---

## Req 3 — Font Size & Color Controls for Display Text

### Current State

- Node labels are rendered in `GraphCanvas.tsx` via `ctx.fillText()` with hardcoded:
  - `fontSize = Math.max(3.5, getNodeSize(label) * 0.55)` (scaled from node size)
  - `fillStyle = themeColors.textPrimary`
- Edge labels are rendered at midpoint with hardcoded:
  - `fontSize = 3` (fixed)
  - `fillStyle = themeColors.textMuted`

### Plan

1. **Add settings to `GraphToolbar` (node bar)**:
   - **Node label font size**: Small slider or +/- stepper (range 0–20, default from current formula). The value acts as a multiplier or absolute override.
   - **Node label color**: A single color picker (or per-label override). Keep it simple: one global node-label color setting, with a color dot that opens `ColorWheelPopover`.
   
2. **Add settings to `GraphEdgeToolbar` (edge bar)**:
   - **Edge label font size**: Same slider/stepper (range 0–12, default 3).
   - **Edge label color**: Single color picker.

3. **Implementation**:
   - Add state in `GraphTopologyViewer`:
     ```ts
     const [nodeLabelFontSize, setNodeLabelFontSize] = useState<number | null>(null); // null = auto
     const [nodeLabelColor, setNodeLabelColor] = useState<string | null>(null);       // null = theme default
     const [edgeLabelFontSize, setEdgeLabelFontSize] = useState<number>(3);
     const [edgeLabelColor, setEdgeLabelColor] = useState<string | null>(null);
     ```
   - Persist all four to localStorage under `graph-label-style:{scenario}`.
   - Pass these as props to `GraphCanvas`, which uses them in `nodeCanvasObject` and `linkCanvasObjectMode`/`linkCanvasObject`.

4. **UI placement**: Add a small `Aa` icon/button at the right end of each bar that opens a compact popover with the size slider + color picker. Keeps the bars clean.

### Files to Modify

| File | Change |
|------|--------|
| `frontend/src/components/GraphTopologyViewer.tsx` | Add label style state, persist to localStorage, pass to canvas + toolbars. |
| `frontend/src/components/graph/GraphCanvas.tsx` | Accept `nodeLabelFontSize`, `nodeLabelColor`, `edgeLabelFontSize`, `edgeLabelColor` props. Apply in `nodeCanvasObject` and edge label rendering. |
| `frontend/src/components/graph/GraphToolbar.tsx` | Add `Aa` button + popover for node label style controls. |
| `frontend/src/components/graph/GraphEdgeToolbar.tsx` | Add `Aa` button + popover for edge label style controls. |

### Regression Risks

- `null` / default values must exactly reproduce current rendering behavior — no visual change unless user explicitly adjusts.
- Font size of `0` should hide text entirely (not cause errors). Guard `ctx.fillText()` calls with `if (fontSize > 0)`.

---

## Req 4 — Freeze Conversation-Card Graphs by Default

### Current State

`GraphResultView.tsx` uses `ForceGraph2D` with:
```ts
cooldownTicks={80}
```
This lets the simulation run 80 ticks before stopping. The graph is **interactive** (drag/zoom/pan) but not explicitly frozen — it stabilizes over ~2 seconds.

### Plan

1. **Set `cooldownTicks={0}`** — graph renders with initial layout positions, then immediately freezes. No simulation movement.
2. **Alternative (preferred)**: Use `cooldownTicks={1}` to allow one tick for initial positioning, then freeze. This avoids all-nodes-stacked-at-origin if no initial positions exist.
3. **Keep zoom/pan/drag enabled** — "frozen" means the simulation doesn't run, not that the user can't interact.
4. **Optional**: Add a small play/pause button to the card graph if the user wants to unfreeze. Low priority — defer unless requested.

### Files to Modify

| File | Change |
|------|---------|
| `frontend/src/components/visualization/GraphResultView.tsx` | Change `cooldownTicks={80}` → `cooldownTicks={1}`. Optionally add a ref and `warmupTicks={1}` to ensure initial layout before freeze. |

### Regression Risks

- If graph data has no pre-computed positions, `cooldownTicks={0}` may render all nodes on top of each other. Using `cooldownTicks={1}` with a `setTimeout(() => zoomToFit(), 100)` mitigates this.
- The existing `zoomToFit` after 500ms should still work fine — just fits a now-static layout.
- Test with both small (2-5 node) and large (50+ node) graph results to verify layout quality.

---

## Req 6 — Remove Min/Max Resize Limits

### Current State

| Component | Min | Max | Storage Key |
|-----------|-----|-----|-------------|
| `ResizableGraph` | 100 | 600 | `graph-h` |
| `ResizableSidebar` | 200 | 500 | `sidebar-w` |
| `ResizableTerminal` | 100 | 500 | `terminal-h` |

These constraints are hardcoded in each component and enforced in `useResizable.ts` via `Math.max(min, Math.min(max, ...))`.

### Plan

1. **Change limits to effectively unbounded**:
   - `min: 0` (allows collapsing to invisible)
   - `max: Infinity` (allows expanding to fill screen)

2. **Update `useResizable.ts`**: When `max === Infinity`, skip the `Math.min` clamp. When `min === 0`, skip the `Math.max` clamp. (Actually `Math.max(0, Math.min(Infinity, x)) === x` for any positive x, so no logic changes needed — just change the constants.)

3. **Update all three components**:
   ```ts
   // ResizableGraph.tsx
   const { size, handleProps } = useResizable('y', { initial: 280, min: 0, max: 99999, storageKey: 'graph-h' });
   
   // ResizableSidebar.tsx
   const { size, handleProps } = useResizable('x', { initial: 288, min: 0, max: 99999, storageKey: 'sidebar-w', invert: true });
   
   // ResizableTerminal.tsx
   const { size, handleProps } = useResizable('y', { initial: 200, min: 0, max: 99999, storageKey: 'terminal-h', invert: true });
   ```

4. **Use `99999` instead of `Infinity`** to avoid JSON serialization issues with localStorage.

5. **Ensure localStorage restore still clamps correctly**: On restore, `Math.max(0, Math.min(99999, saved))` — effectively no-op for any reasonable value.

### Files to Modify

| File | Change |
|------|--------|
| `frontend/src/components/ResizableGraph.tsx` | `min: 0`, `max: 99999` |
| `frontend/src/components/ResizableSidebar.tsx` | `min: 0`, `max: 99999` |
| `frontend/src/components/ResizableTerminal.tsx` | `min: 0`, `max: 99999` |

### Regression Risks

- At `height: 0` or `width: 0`, child components must not crash. Check that `GraphCanvas` / `ForceGraph2D` handles 0-dimension gracefully (it should — canvas just renders nothing).
- At full-screen size, no overflow issues should arise since the elements use `overflow-hidden`.
- If a user accidentally resizes to 0, they can drag the handle back. The handle must remain grabbable even at size 0. Verify the drag handle `h-2.5` / `w-2.5` is still visible/interactive at collapsed sizes. May need to add `min-h-[10px]` to the drag handle's parent or ensure the handle renders outside the collapsed area.

### Edge Case: Handle Visibility at Size 0

The drag handle is rendered **inside** the resizable div. If height/width = 0 with `overflow-hidden`, the handle itself becomes invisible and unreachable.

**Fix**: Render the drag handle **outside** the sized container, adjacent to it. Refactor each Resizable component to:
```tsx
<div className="flex flex-col shrink-0">
  <div style={{ height: size }} className="overflow-hidden">
    {children}
  </div>
  <div {...handleProps} className="h-2.5 cursor-row-resize ..." />
</div>
```

This ensures the handle is always accessible regardless of `size`. Apply same pattern to sidebar (horizontal) and terminal (inverted vertical).

---

## Req 7 — Resource Tab: Full Architecture Diagram from File

### Current State

- `ResourceVisualizer.tsx` renders a force-directed graph of agents/tools/datasources/infrastructure.
- Data comes from `GET /api/config/resources` → `_build_resource_graph()` in `api/app/routers/config.py`.
- The graph is **dynamically generated** from `scenario.yaml` — it only shows what's declared in the scenario config.
- Missing: container apps, API services, the graph database itself, the frontend, background workers, or any other infrastructure not modeled in scenario.yaml.

### Plan

#### A. Create a static architecture graph data file

1. **Create** `data/architecture_graph.json` — a comprehensive JSON file defining every element:
   ```json
   {
     "nodes": [
       { "id": "frontend", "label": "Frontend", "type": "container-app", "description": "React/Vite SPA", "tech": "TypeScript, React, Tailwind" },
       { "id": "api-server", "label": "API Server", "type": "container-app", "description": "FastAPI application server", "tech": "Python, FastAPI" },
       { "id": "graph-query-api", "label": "Graph Query API", "type": "container-app", "description": "Gremlin query proxy", "tech": "Python, FastAPI" },
       { "id": "orchestrator-agent", "label": "Orchestrator Agent", "type": "orchestrator", "description": "Azure AI Foundry orchestrator" },
       { "id": "graph-explorer-agent", "label": "Graph Explorer", "type": "agent", "description": "Graph traversal agent" },
       { "id": "telemetry-agent", "label": "Telemetry Agent", "type": "agent", "description": "Time-series analysis" },
       { "id": "runbook-kb-agent", "label": "Runbook KB Agent", "type": "agent", "description": "Knowledge base search" },
       { "id": "historical-ticket-agent", "label": "Historical Ticket Agent", "type": "agent", "description": "Past incident search" },
       ...tools, data sources, search indexes, blob containers, Fabric graph, AI Search, AI Foundry, etc.
     ],
     "edges": [
       { "source": "frontend", "target": "api-server", "label": "HTTP/WebSocket", "type": "connects_to" },
       { "source": "api-server", "target": "orchestrator-agent", "label": "Foundry SDK", "type": "delegates_to" },
       ...
     ],
     "metadata": {
       "title": "Service Architecture",
       "description": "Complete deployment architecture — regenerate if architecture changes or new tools are added.",
       "lastUpdated": "2026-02-20"
     }
   }
   ```

2. **Populate the file** by auditing the full codebase:
   - From `scenario.yaml`: all agents and their tools
   - From `deploy.sh` / `infra/`: container apps, Azure AI Search, storage accounts, Fabric workspace
   - From `api/app/main.py` + `graph-query-api/main.py`: API services
   - From `frontend/`: the SPA itself
   - From `custom_skills/`: any custom tool implementations
   - Edge relationships derived from actual code dependencies

#### B. Serve the file from the API

3. **Add a new endpoint** or modify existing:
   - Option A: `GET /api/config/architecture` → reads and returns `data/architecture_graph.json`
   - Option B: Modify `GET /api/config/resources` to read from the file instead of building dynamically
   - **Chosen**: Option A (new endpoint) — preserves the existing dynamic endpoint for backward compatibility (Req 8).

4. **Backend implementation** in `api/app/routers/config.py`:
   ```python
   @router.get("/architecture")
   async def get_architecture():
       path = PROJECT_ROOT / "data" / "architecture_graph.json"
       if not path.exists():
           raise HTTPException(404, "architecture_graph.json not found")
       return json.loads(path.read_text())
   ```

#### C. Update the frontend

5. **Create `useArchitectureGraph` hook** (new file `frontend/src/hooks/useArchitectureGraph.ts`):
   ```ts
   // Fetches from GET /api/config/architecture instead of /api/config/resources
   ```

6. **Update `ResourceVisualizer.tsx`**:
   - Switch data source from `useResourceGraph()` → `useArchitectureGraph()`
   - Keep all existing rendering, filtering, toolbar functionality
   - The node/edge types and rendering in `ResourceCanvas.tsx` should continue to work — the static file uses the same type taxonomy

7. **Add tooltip to Resources tab** in `TabBar.tsx`:
   ```tsx
   <span title="Regenerate architecture_graph.json if architecture changes or new tools are added">
     Resources
   </span>
   ```

#### D. Full node coverage for the architecture file

The file must include these categories (audit against codebase):

| Category | Nodes |
|----------|-------|
| **Containers/Apps** | Frontend SPA, API Server, Graph Query API, Nginx reverse proxy |
| **AI Agents** | Orchestrator, Graph Explorer, Telemetry, Runbook KB, Historical Ticket |
| **Agent Tools** | Graph query tool (OpenAPI), Telemetry tool, Runbook search (AI Search), Ticket search (AI Search) |
| **Data Sources** | Network topology graph (Fabric), Telemetry CSVs, Runbook documents, Historical tickets |
| **Search Indexes** | Runbooks index, Tickets index |
| **Storage** | Blob containers (runbooks, tickets, telemetry) |
| **Infrastructure** | Azure AI Foundry, Azure AI Search, Azure Blob Storage, Microsoft Fabric (Graph DB), Azure Container Apps, Container Registry |
| **Config/Deployment** | scenario.yaml, deploy.sh, Docker images |

### Files to Create

| File | Purpose |
|------|---------|
| `data/architecture_graph.json` | Static comprehensive architecture graph data |
| `frontend/src/hooks/useArchitectureGraph.ts` | Hook to fetch architecture graph from API |

### Files to Modify

| File | Change |
|------|--------|
| `api/app/routers/config.py` | Add `GET /api/config/architecture` endpoint |
| `frontend/src/components/ResourceVisualizer.tsx` | Switch to `useArchitectureGraph` hook |
| `frontend/src/components/TabBar.tsx` | Add tooltip to Resources tab |

### Files NOT to Delete

| File | Reason |
|------|--------|
| `frontend/src/hooks/useResourceGraph.ts` | Preserved — still valid, just not used by Resources tab (Req 8) |
| `api/app/routers/config.py` `_build_resource_graph()` | Preserved — the endpoint remains available |

### Regression Risks

- `ResourceCanvas.tsx` renders nodes by `type` field using shape logic. The architecture JSON must use the same `type` values (`orchestrator`, `agent`, `tool`, `datasource`, `search-index`, `blob-container`, `foundry`, `storage`, `search-service`, `container-app`). New node types may need new shapes added to `ResourceCanvas`.
- The Y-force layering in `ResourceCanvas` assigns Y positions by type. New types need positions defined or they'll float.
- `ResourceToolbar` iterates `RESOURCE_TYPE_LABELS` for filter chips. New types need entries in `resourceConstants.ts`.

---

## Req 8 & 9 — Zero Regressions & Anti-Contradiction Audit

### Pre-Implementation Checklist

- [ ] **Snapshot current behavior**: Record screenshots/screen captures of all affected views before changes
- [ ] **Identify all consumers**: For every modified prop/interface/component, grep for all import sites

### Specific Risks Identified

| Risk | Mitigation |
|------|-----------|
| Changing `GraphCanvas` props breaks `ResourceCanvas` | `ResourceCanvas` is a separate component with its own `ForceGraph2D` — not affected by `GraphCanvas` prop changes |
| Edge toolbar height pushes graph canvas offscreen | Dynamic height measurement: sum toolbar + edge toolbar heights, subtract from container |
| Removing resize limits breaks saved localStorage values | `Math.max(0, Math.min(99999, saved))` handles all saved values gracefully |
| Architecture graph JSON has wrong node types | Validate against `ResourceNodeType` enum in `types/index.ts` at build time |
| Multiple components import from `useTopology` | Only `GraphTopologyViewer` uses it for the main graph — safe to modify the flow |
| `GraphResultView` freeze breaks graph layouts | Use `cooldownTicks={1}` not `0` — allows initial positioning; test with synthetic data |
| Drag handle invisible at size 0 | Refactor handle to render outside the sized container |

### Testing Plan

| Test | Verify |
|------|--------|
| Toggle node types on/off | Graph stays at current viewport position and zoom level |
| Toggle edge types on/off | Edges appear/disappear without recentering |
| Adjust node/edge label size | Text scales smoothly, no crashes at size 0 |
| Resize graph panel to 0 | Panel collapses, drag handle remains visible and functional |
| Resize graph panel to full screen | Panel fills available space, no overflow |
| Open conversation card with graph | Graph renders frozen, no jittering |
| Switch to Resources tab | Static architecture diagram loads from file |
| All existing chat/investigation flows | No changes to behavior |
| Refresh topology | Graph re-fetches and auto-fits (this is the only case where auto-fit should trigger) |

---

## Implementation Order

| Phase | Requirements | Rationale |
|-------|-------------|-----------|
| **Phase 1** | Req 1 (no recenter) | Foundation — fixes core UX annoyance, low risk |
| **Phase 2** | Req 6 (resize limits) | Small, isolated change to three files + hook edge case |
| **Phase 3** | Req 4 (freeze card graphs) | One-line change, isolated component |
| **Phase 4** | Req 2 (edge bar) | New component + filter logic — builds on Req 1's pattern |
| **Phase 5** | Req 3 (font controls) | Adds to toolbars from Phase 4; touches canvas rendering |
| **Phase 6** | Req 7 (resource tab) | Largest change — new file, new endpoint, component swap |
| **Phase 7** | Req 8-9 (regression audit) | Final verification pass across all changes |

---

## File Change Summary

### New Files (4)

| File | Purpose |
|------|---------|
| `frontend/src/components/graph/GraphEdgeToolbar.tsx` | Edge type filter bar |
| `frontend/src/hooks/useArchitectureGraph.ts` | Fetch static architecture graph |
| `data/architecture_graph.json` | Static architecture graph data |
| *(this file)* `documentation/v17QOL_plan.md` | Implementation plan |

### Modified Files (11)

| File | Requirements |
|------|-------------|
| `frontend/src/components/graph/GraphCanvas.tsx` | Req 1 (dataVersion prop), Req 3 (label style props) |
| `frontend/src/components/GraphTopologyViewer.tsx` | Req 1 (dataVersion), Req 2 (edge state+filtering), Req 3 (label style state) |
| `frontend/src/components/graph/GraphToolbar.tsx` | Req 3 (font size/color controls) |
| `frontend/src/components/graph/graphConstants.ts` | Req 2 (edge color palette) |
| `frontend/src/components/visualization/GraphResultView.tsx` | Req 4 (cooldownTicks) |
| `frontend/src/components/ResizableGraph.tsx` | Req 6 (remove limits) |
| `frontend/src/components/ResizableSidebar.tsx` | Req 6 (remove limits) |
| `frontend/src/components/ResizableTerminal.tsx` | Req 6 (remove limits) |
| `frontend/src/components/ResourceVisualizer.tsx` | Req 7 (switch data source) |
| `frontend/src/components/TabBar.tsx` | Req 7 (tooltip) |
| `api/app/routers/config.py` | Req 7 (architecture endpoint) |

### Potentially Modified (edge cases)

| File | If Needed |
|------|-----------|
| `frontend/src/components/resource/resourceConstants.ts` | Req 7 — if new node types are introduced in the architecture graph |
| `frontend/src/components/resource/ResourceCanvas.tsx` | Req 7 — if new node type shapes are needed |
| `frontend/src/types/index.ts` | Req 7 — if `ResourceNodeType` needs new values |
| `frontend/src/hooks/useResizable.ts` | Req 6 — if drag handle visibility at size 0 needs structural fix |

### Files NOT Modified (preserved)

| File | Reason |
|------|--------|
| `frontend/src/hooks/useResourceGraph.ts` | Kept for backward compatibility |
| `frontend/src/hooks/useTopology.ts` | No changes needed — fetch logic unchanged |
| `frontend/src/components/resource/ResourceToolbar.tsx` | No changes — works with any data source |
| All prompt files | No changes |
| All scenario data files | No changes |
| All agent/session/orchestration code | No changes |
