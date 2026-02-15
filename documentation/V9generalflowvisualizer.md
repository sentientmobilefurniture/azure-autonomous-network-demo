# V9 — Resource & Agent Flow Visualizer (UI Considerations)

> Companion to `V9generalflow.md`. Focuses on the UI tab that visualises
> the multi-agent flow, data sources, and their connections.

---

## 1. The Idea

A new **"Resources"** tab (alongside "Investigate" and "Scenario Info") that
renders a live, interactive graph showing:

- **Agents** — each Foundry agent as a node (orchestrator, sub-agents)
- **Data sources** — Cosmos Gremlin graph, Cosmos NoSQL containers, AI Search
  indexes, blob containers
- **Tools** — OpenAPI specs, AzureAISearchTool, ConnectedAgentTool
- **Connections** — edges showing which agent uses which tool, which tool talks
  to which data source, which agent delegates to which sub-agent

Think of it as a **dependency graph of the scenario's runtime architecture**,
not the network topology the scenario *analyses*.

---

## 2. Does the UI Actually Need to Change?

**Yes, but not as much as you'd think.** The current UI is already structured
to make this easy:

### What already exists

| Asset | Status | Notes |
|-------|--------|-------|
| Tab system | ✅ trivial to extend | `AppTab` union type + `TabBar.tsx` (31 lines). Add `'resources'` literal, one button, one content branch. |
| `react-force-graph-2d` | ✅ already installed | Same lib used for network topology. We know how to render custom nodes, edges, tooltips, context menus. |
| `GraphCanvas.tsx` | ✅ reusable patterns | 184 lines. Custom `nodeCanvasObject` + `linkCanvasObject` — we can copy the pattern for a different node shape vocabulary. |
| `GraphToolbar.tsx` | ✅ adaptable | Filter chips by node type, search, pause/play, zoom-to-fit — all reusable. |
| `GraphTooltip.tsx` | ✅ reusable | Mouse-tracked tooltip showing node/edge properties. |
| `framer-motion` | ✅ installed | Entry/exit animations for the tab content. |
| `react-resizable-panels` | ✅ installed | If we want a split view (graph + detail panel). |
| `ScenarioContext` | ✅ has scenario metadata | `activeScenario` gives us scenario name, which we can use to fetch the full config. |
| `GET /api/agents` | ✅ exists | Returns orchestrator + sub-agent IDs and names from `agent_ids.json`. |

### What's missing

| Gap | Effort | Notes |
|-----|--------|-------|
| Backend endpoint for full resource graph | Medium | Need `GET /api/config/resources` or similar that returns the scenario's full wiring: agents + tools + data sources + edges. Currently `GET /api/agents` only returns agent names/IDs, not their tool bindings or data source connections. |
| Resource graph data model | Low | Define the node/edge types for the resource graph (different from topology graph). |
| `ResourceVisualizer.tsx` | Medium | New component wrapping `ForceGraph2D` with resource-specific rendering. ~200-300 lines, mostly adapted from `GraphTopologyViewer.tsx`. |
| Resource detail panel | Low | Click a node → see its properties (agent instructions, data source config, tool spec). Could reuse the tooltip pattern or add a sidebar. |
| Config YAML as data source | Depends | In the genericized world, the scenario YAML *is* the source of truth. Until then, we'd need to assemble the graph from `agent_ids.json` + `scenario.yaml` + hardcoded knowledge of tool bindings. |

---

## 3. Feasibility Assessment: Easy or Fucking Whack?

**Verdict: Solidly in "easy" territory**, with one caveat.

### Why it's easy

1. **We already have `react-force-graph-2d`** — the hardest part of any graph
   viz (layout, interaction, rendering) is solved. We're not bringing in a new
   library or building from scratch.

2. **The tab system is trivial** — literally 3 lines to add a tab:
   ```ts
   // App.tsx
   type AppTab = 'investigate' | 'info' | 'resources'  // +1 literal
   // TabBar.tsx — +1 <button>
   // App.tsx render — +1 branch
   ```

3. **The resource graph is small** — a typical scenario has 5 agents + 4-5 data
   sources + 5-6 tools = ~15 nodes and ~20 edges. This is *tiny* compared to
   the topology graph (100+ nodes). Force layout will converge instantly and
   look good without tuning.

4. **Existing component patterns are directly reusable** — `GraphCanvas.tsx`'s
   custom canvas rendering, `GraphToolbar.tsx`'s filter chips, `GraphTooltip.tsx`'s
   hover info — all can be adapted with different node shapes/colors for agent
   vs data source vs tool.

5. **No new dependencies needed** — everything required is already in
   `package.json`.

### The one caveat (what could make it whack)

**The backend data assembly.** Right now, the relationship between agents, tools,
and data sources is **implicit** — it's encoded in the provisioning logic
(`agent_provisioner.py`), not exposed as queryable metadata. To render the
resource graph, the frontend needs a single endpoint that returns something like:

```json
{
  "nodes": [
    { "id": "orchestrator", "type": "agent", "label": "Orchestrator", "model": "gpt-4.1" },
    { "id": "graph-explorer", "type": "agent", "label": "GraphExplorerAgent", "model": "gpt-4.1" },
    { "id": "telemetry-agent", "type": "agent", "label": "TelemetryAgent", "model": "gpt-4.1" },
    { "id": "runbook-agent", "type": "agent", "label": "RunbookKBAgent", "model": "gpt-4.1" },
    { "id": "ticket-agent", "type": "agent", "label": "HistoricalTicketAgent", "model": "gpt-4.1" },
    { "id": "cosmos-gremlin", "type": "datasource", "label": "Cosmos Gremlin", "backend": "cosmosdb" },
    { "id": "cosmos-nosql", "type": "datasource", "label": "Cosmos NoSQL (Telemetry)", "backend": "cosmosdb" },
    { "id": "search-runbooks", "type": "datasource", "label": "AI Search: runbooks-index" },
    { "id": "search-tickets", "type": "datasource", "label": "AI Search: tickets-index" },
    { "id": "tool-graph-query", "type": "tool", "label": "OpenAPI: query_graph" },
    { "id": "tool-telemetry-query", "type": "tool", "label": "OpenAPI: query_telemetry" },
    { "id": "tool-search-runbooks", "type": "tool", "label": "AzureAISearchTool" },
    { "id": "tool-search-tickets", "type": "tool", "label": "AzureAISearchTool" }
  ],
  "edges": [
    { "source": "orchestrator", "target": "graph-explorer", "type": "delegates_to" },
    { "source": "orchestrator", "target": "telemetry-agent", "type": "delegates_to" },
    { "source": "orchestrator", "target": "runbook-agent", "type": "delegates_to" },
    { "source": "orchestrator", "target": "ticket-agent", "type": "delegates_to" },
    { "source": "graph-explorer", "target": "tool-graph-query", "type": "uses_tool" },
    { "source": "telemetry-agent", "target": "tool-telemetry-query", "type": "uses_tool" },
    { "source": "runbook-agent", "target": "tool-search-runbooks", "type": "uses_tool" },
    { "source": "ticket-agent", "target": "tool-search-tickets", "type": "uses_tool" },
    { "source": "tool-graph-query", "target": "cosmos-gremlin", "type": "queries" },
    { "source": "tool-telemetry-query", "target": "cosmos-nosql", "type": "queries" },
    { "source": "tool-search-runbooks", "target": "search-runbooks", "type": "queries" },
    { "source": "tool-search-tickets", "target": "search-tickets", "type": "queries" }
  ]
}
```

**Before genericization**: this endpoint would need to be hardcoded or assembled
from `agent_ids.json` + `scenario.yaml`. Doable but somewhat brittle.

**After genericization**: the scenario config YAML *already contains* all this
information (agents, data_sources, tools, connections). The endpoint becomes a
trivial YAML-to-graph transformation. **This is one of the payoffs of
genericization.**

---

## 4. Proposed Architecture

### 4.1 Node Types & Visual Language

| Node Type | Shape | Color Family | Icon/Symbol | Example |
|-----------|-------|-------------|-------------|---------|
| **Agent (orchestrator)** | Large circle with double border | Blue `#3b82f6` | Crown / star | Orchestrator |
| **Agent (sub-agent)** | Circle | Blue `#60a5fa` | Bot / brain | GraphExplorerAgent |
| **Data Source** | Rounded rectangle | Green `#22c55e` | Database / cylinder | Cosmos Gremlin |
| **Tool** | Diamond / hexagon | Orange `#f59e0b` | Wrench / gear | OpenAPI: query_graph |
| **Search Index** | Rounded rectangle | Purple `#a855f7` | Magnifying glass | runbooks-index |

### 4.2 Edge Types

| Edge Type | Style | Label |
|-----------|-------|-------|
| `delegates_to` | Solid, directional arrow | "delegates" |
| `uses_tool` | Dashed, directional arrow | "uses" |
| `queries` | Dotted, directional arrow | "queries" |

### 4.3 Layout

The resource graph is small enough that **force-directed layout** (what we
already use) will produce a clean result. The orchestrator naturally
gravitates to center, sub-agents form a ring, tools and data sources
radiate outward. No special layout algorithm needed.

For a more structured view, we could use a **layered/hierarchical layout**:
```
Layer 0:  [Orchestrator]
Layer 1:  [GraphExplorer] [Telemetry] [Runbook] [Ticket]
Layer 2:  [query_graph]   [query_tel] [search]  [search]
Layer 3:  [Cosmos Gremlin] [Cosmos NoSQL] [AI Search idx] [AI Search idx]
```
This could be done by fixing `node.fy` (vertical position) based on node type
and letting `node.fx` be free. `react-force-graph-2d` supports this via the
`d3Force` callback — we'd configure `d3.forceY()` with per-type target
positions. Not hard.

### 4.4 Interaction

- **Hover**: Tooltip with node details (agent: model, instructions preview;
  data source: backend type, database/container; tool: spec file)
- **Click**: Expand a detail panel (slide-in from right, or bottom split)
  showing full config for that resource
- **Filter**: Toolbar chips to show/hide by node type (same pattern as topology
  graph)
- **Highlight path**: Click an agent → highlight its full chain down to data
  sources. Dim everything else. This is straightforward with the force-graph
  library's `linkDirectionalArrowLength` + node/link `color` callbacks.

---

## 5. Component Plan

### New files

| File | Est. Lines | Purpose |
|------|-----------|---------|
| `components/ResourceVisualizer.tsx` | ~250 | Main orchestrator component (like `GraphTopologyViewer.tsx` is for topology) |
| `components/resource/ResourceCanvas.tsx` | ~200 | `ForceGraph2D` wrapper with resource-specific node/edge rendering |
| `components/resource/ResourceToolbar.tsx` | ~100 | Filter chips for agent/datasource/tool, search, layout toggle |
| `components/resource/ResourceTooltip.tsx` | ~60 | Hover tooltip adapted for resource nodes |
| `components/resource/resourceConstants.ts` | ~30 | Node type colors, sizes, shapes |
| `hooks/useResourceGraph.ts` | ~50 | Fetch resource graph from API, transform for force-graph |

**Total estimate: ~690 lines of new frontend code.**

For context, the existing topology graph system is ~782 lines across 6 files.
So we're building roughly the same thing again but simpler (fewer nodes, fewer
interaction modes, no telemetry overlay).

### Modified files

| File | Change | Lines |
|------|--------|-------|
| `App.tsx` | Add `'resources'` to `AppTab`, add content branch | +10 |
| `TabBar.tsx` | Add third tab button | +5 |
| `types/index.ts` | Add `ResourceNode`, `ResourceEdge` types | +20 |

### New backend

| File | Change | Lines |
|------|--------|-------|
| `api/app/routers/config.py` | Add `GET /api/config/resources` endpoint | +60 |

---

## 6. Sequencing — When to Build This

### Option A: Build now (pre-genericization)

- Hardcode the resource graph assembly from `agent_ids.json` + `scenario.yaml`
- Works, but the backend endpoint is ugly — it knows about the 5-agent structure
- Gets replaced when genericization lands

### Option B: Build after genericization (recommended)

- The config YAML already declares agents + data_sources + tools + connections
- Backend endpoint is a trivial YAML→graph transform
- Frontend is identical either way
- **No throwaway work**

### Option C: Build frontend now, backend later

- Create the frontend components with mock data
- Hook up to real backend once genericization provides the clean data model
- Gets the UI patterns established without coupling to current hardcoded structure
- **Best of both worlds** — we validate the UX without writing throwaway backend code

**Recommendation: Option C.** Build the frontend with a mock `useResourceGraph`
hook that returns hardcoded data matching the schema above. Once the config
YAML genericization lands, swap the mock for a real API call. Total throwaway
code: ~20 lines of mock data.

---

## 7. Open Questions

1. **Should the visualizer also show runtime state?** e.g., during an
   investigation, light up the agents as they're invoked (SSE events already
   include agent names in `step` events). This would be cool but adds
   complexity — probably a V10 enhancement.

2. **Should clicking an agent let you edit its prompt?** The SettingsModal
   already has prompt editing. Could link to it from the resource graph, or
   embed inline editing. Nice-to-have, not essential for V9.

3. **Topology graph vs resource graph — same component?** They're conceptually
   similar (both are force-directed node-edge graphs) but different enough in
   data shape, rendering, and interaction that **separate components sharing
   utility functions** is cleaner than one uber-component with mode switches.

4. **Tab naming**: "Resources"? "Architecture"? "Agent Flow"? "System Map"?
   Needs to be immediately understandable to someone who hasn't read this doc.

5. **Mobile/narrow viewport**: The existing topology graph already handles
   this (canvas resizes). Resource graph will be even simpler since it has
   fewer nodes. No special work needed.

---

## 8. Summary

| Question | Answer |
|----------|--------|
| Does the UI need to change? | Yes — one new tab + one new component tree |
| Is it easy? | **Yes.** All required libraries installed, tab system trivial to extend, force-graph patterns fully established. |
| Is it fucking whack? | **No.** ~690 lines of new frontend, ~60 lines of new backend. No new dependencies. |
| What's the hardest part? | Backend data assembly (where does the resource graph come from?). Solved cleanly by genericization. |
| When to build? | Frontend with mock data now (Option C), real backend after genericization. |
