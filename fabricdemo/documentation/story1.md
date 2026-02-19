# Story 1 — Step-Level Visualization Buttons

## Vision

Each conversation step in the Investigation Panel gets a **visualization button** (bottom-right corner of the StepCard). Clicking it opens a **modal overlay** showing rich, type-aware visualization of that step's data, then closes cleanly when dismissed.

| Agent type | Visual treatment |
|---|---|
| `GraphExplorerAgent` | Force-directed graph of returned nodes & edges |
| `TelemetryAgent` | Tabular data grid (columns + rows) |
| `RunbookKBAgent` | Formatted document / knowledge-panel list |
| `HistoricalTicketAgent` | Formatted document / knowledge-panel list |

![conceptual](assets/story1-concept.png) *(to be added)*

---

## Current State Analysis

### What we have today

| Component | Purpose |
|---|---|
| `StepCard.tsx` | Renders one `StepEvent` — collapsed preview + expandable query/response |
| `AgentTimeline.tsx` | Maps `StepEvent[]` → `<StepCard>` list |
| `GraphTopologyViewer.tsx` + `graph/*` | Force-directed network topology viewer (uses `react-force-graph-2d`) |
| `ResourceVisualizer.tsx` + `resource/*` | Force-directed agent-architecture viewer |

### Key constraint — no structured data on the frontend today

`StepEvent` only carries:
```ts
{ step, agent, duration?, query?, response?, error? }
```
`query` and `response` are **plain strings** (truncated at 500 / 2000 chars in the orchestrator). The structured query results (`{ columns, data }` for GQL and `{ columns, rows }` for KQL) exist only between the graph-query-api microservice and the Azure AI Foundry tool — they never reach the frontend.

This means we need a **data pipeline change** to surface structured results.

---

## Architecture Plan

### Phase 1 — Backend: Surface Structured Data

#### 1A. Extend `StepEvent` with optional structured payload

Add a new optional field to the SSE `step_complete` event:

```python
# orchestrator.py — step_complete payload
{
    "event": "step_complete",
    "data": {
        "step": 3,
        "agent": "GraphExplorerAgent",
        "duration": "11.2s",
        "query": "MATCH (l:TransportLink)...",
        "response": "The link LINK-SYD-MEL-FIBRE-01 ...",
        "visualization": {                       # ← NEW
            "type": "graph",                     # "graph" | "table" | "documents"
            "data": { ... }                      # type-specific structured payload
        }
    }
}
```

**Visualization payload shapes:**

```jsonc
// type: "graph"
{
    "type": "graph",
    "data": {
        "columns": [{"name": "r.RouterId", "type": "String"}, ...],
        "rows": [{"r.RouterId": "RTR-01", ...}, ...],
        "query": "MATCH (r:CoreRouter) RETURN r.RouterId, r.Hostname"
    }
}

// type: "table"
{
    "type": "table",
    "data": {
        "columns": [{"name": "AlertId", "type": "String"}, {"name": "Timestamp", "type": "DateTime"}, ...],
        "rows": [{"AlertId": "A1", "Timestamp": "...", ...}, ...],
        "query": "AlertStream | where SourceNodeId == 'LINK-SYD-MEL-FIBRE-01' | top 20"
    }
}

// type: "documents"
{
    "type": "documents",
    "data": {
        "content": "...agent's response text...",
        "agent": "RunbookKBAgent"
    }
}
```

#### 1B. Two strategies for obtaining structured data (choose one)

**Option A — Re-execute query on demand (lazy, recommended for v1)**

- Don't change the SSE stream at all.
- Add a new frontend API endpoint: `POST /api/query/replay`
- When the user clicks the visualization button, the frontend sends `{ agent, query }` to this endpoint.
- The endpoint routes to `/query/graph` or `/query/telemetry` on the graph-query-api service and returns structured results.
- For AI Search agents, no replay is needed — just render `step.response` as a document panel.

Pros: No orchestrator changes, no increased SSE payload size, no wasted compute for steps the user never inspects.
Cons: Extra latency on button click; query may return different results if data changed.

**Option B — Piggyback on the SSE stream (eager)**

- Modify the orchestrator's `AgentEventHandler` to intercept `RequiresAction` tool outputs.
- When a tool call to the graph-query-api completes, capture the raw JSON response body.
- Embed it in the `step_complete` event as the `visualization` field.
- For AI Search tool calls, capture the search result text.

Pros: Instant visualization, no extra API calls, data is guaranteed consistent.
Cons: Larger SSE payloads, orchestrator complexity, wasted compute/bandwidth for steps never inspected.

**Recommendation:** Start with **Option A** for simplicity, migrate to **Option B** later for polish.

#### 1C. New API endpoint (Option A only)

```
POST /api/query/replay
Content-Type: application/json

{
    "agent": "GraphExplorerAgent",    // determines routing
    "query": "MATCH (l:TransportLink) WHERE l.LinkId = 'LINK-SYD-MEL-FIBRE-01' RETURN l"
}

Response 200:
{
    "type": "graph",
    "columns": [...],
    "data": [...]
}
```

For `TelemetryAgent`:
```
{
    "agent": "TelemetryAgent",
    "query": "AlertStream | where SourceNodeId == 'LINK-SYD-MEL-FIBRE-01' | top 20 by Timestamp"
}

Response 200:
{
    "type": "table",
    "columns": [...],
    "rows": [...]
}
```

For `RunbookKBAgent` / `HistoricalTicketAgent` — no endpoint needed; the visualization is just the formatted `step.response`.

**Files to modify:**
- `api/app/routers/` — add `replay.py` router
- `api/app/main.py` — register the router
- `graph-query-api/` — no changes needed (existing `/query/graph` and `/query/telemetry` endpoints are reused)

---

### Phase 2 — Frontend: Types & Data Layer

#### 2A. Extend `StepEvent` type

```ts
// types/index.ts
export type VisualizationType = 'graph' | 'table' | 'documents';

export interface VisualizationColumn {
    name: string;
    type: string;
}

export interface GraphVisualizationData {
    type: 'graph';
    columns: VisualizationColumn[];
    rows: Record<string, unknown>[];
    query: string;
}

export interface TableVisualizationData {
    type: 'table';
    columns: VisualizationColumn[];
    rows: Record<string, unknown>[];
    query: string;
}

export interface DocumentVisualizationData {
    type: 'documents';
    content: string;
    agent: string;
}

export type VisualizationData =
    | GraphVisualizationData
    | TableVisualizationData
    | DocumentVisualizationData;
```

#### 2B. Query replay hook

```ts
// hooks/useQueryReplay.ts
export function useQueryReplay() {
    const [loading, setLoading] = useState(false);
    const [data, setData] = useState<VisualizationData | null>(null);
    const [error, setError] = useState<string | null>(null);

    async function replay(agent: string, query: string) {
        // For AI Search agents, skip API call
        // For GQL/KQL agents, POST to /api/query/replay
    }

    return { replay, data, loading, error };
}
```

#### 2C. Agent-type resolver utility

```ts
// utils/agentType.ts
export function getVisualizationType(agent: string): VisualizationType {
    switch (agent) {
        case 'GraphExplorerAgent':
            return 'graph';
        case 'TelemetryAgent':
            return 'table';
        case 'RunbookKBAgent':
        case 'HistoricalTicketAgent':
        case 'AzureAISearch':
            return 'documents';
        default:
            return 'documents';
    }
}
```

---

### Phase 3 — Frontend: UI Components

#### 3A. Visualization button on StepCard

Add a small icon button to the **bottom-right** of each `StepCard`:

```
┌─────────────────────────────────────────────────────────┐
│ ● GraphExplorerAgent                           11.2s    │
│ ▸ Query: MATCH (l:TransportLink)...                     │
│ ▸ Response: MPLS-PATH-SYD-MEL-PRIMARY trav...           │
│                                                         │
│                                            [ 📊 View ]  │  ← visualization button
└─────────────────────────────────────────────────────────┘
```

**Button behavior:**
- Icon varies by type: 🔗 graph, 📊 table, 📄 documents
- Tooltip: "View graph results" / "View telemetry data" / "View search results"
- On click: opens the visualization modal
- Button is always visible (not gated behind expand)
- `glass-card` styling to match existing design

**Files to modify:**
- `components/StepCard.tsx` — add button in the card footer

#### 3B. Visualization Modal (`StepVisualizationModal.tsx`)

A **full-screen overlay modal** with:

```
┌──────────────────────────────────────────────────────────┐
│  GraphExplorerAgent — Query Results              [ ✕ ]   │
│──────────────────────────────────────────────────────────│
│                                                          │
│              (type-specific content area)                 │
│                                                          │
│              - Graph canvas                              │
│              - Data table                                │
│              - Document list                             │
│                                                          │
│                                                          │
│──────────────────────────────────────────────────────────│
│  Query: MATCH (l:TransportLink) WHERE ...      [ Copy ]  │
└──────────────────────────────────────────────────────────┘
```

**Behavior:**
- Opens as a portal (rendered outside the panel DOM) to avoid layout shifts
- Backdrop click or ✕ button closes
- Escape key closes
- `framer-motion` enter/exit animation (consistent with existing StepCard animations)
- Loading spinner while `/api/query/replay` is in-flight (GQL/KQL only)
- Error state with retry button

**Files to create:**
- `components/visualization/StepVisualizationModal.tsx` — the modal wrapper
- `components/visualization/GraphResultView.tsx` — graph visualization content
- `components/visualization/TableResultView.tsx` — table content
- `components/visualization/DocumentResultView.tsx` — document list content

#### 3C. `GraphResultView` — Graph Visualization

Render GQL query results as an interactive force-directed graph.

**Approach:** Reuse the existing `react-force-graph-2d` pattern from `GraphCanvas`:

1. Parse the `columns` + `rows` response to extract nodes and edges.
   - Heuristic: rows with `source`/`target` fields → edges; otherwise → nodes.
   - Or: send the same query to `/query/topology` which returns pre-structured `{nodes, edges}`.
2. Render with a lightweight version of `ForceGraph2D` (same library already installed).
3. Node colors use the same palette from `graphConstants.ts`.
4. Tooltip on hover showing node properties.
5. No toolbar needed (simpler than the main topology viewer).

**Alternative (simpler):** If the GQL results are tabular (e.g., `RETURN r.RouterId, r.Hostname`), show them as a table with a "View as graph" toggle that calls `/query/topology` filtered to those entities.

#### 3D. `TableResultView` — Tabular Data

Render KQL query results as a sortable, scrollable data table.

**Approach:**
- Simple HTML `<table>` with Tailwind styling (or a lightweight lib like `@tanstack/react-table` if already available).
- Column headers from `columns[].name`.
- Row data from `rows[]`.
- Optional: column sorting (click header to sort).
- Optional: row count footer.
- Zebra-striped rows for readability.
- Horizontal scroll for wide tables.
- Monospace font for numeric/timestamp columns.

No additional dependencies needed — pure HTML table with Tailwind classes.

#### 3E. `DocumentResultView` — Document List

Render AI Search results (RunbookKB / HistoricalTicket) as a formatted knowledge panel.

**Approach:**
- Take `step.response` and render as rich Markdown (same `ReactMarkdown` setup already used in StepCard).
- Add visual treatment: card-style sections, separator lines, document icons.
- Agent name badge at the top (`RunbookKBAgent` vs `HistoricalTicketAgent`).

This is the simplest visualization — it's essentially the expanded StepCard response content in a modal with better formatting.

---

### Phase 4 — Styling & Polish

#### 4A. Design tokens

Follow existing patterns:
- Modal background: `bg-surface-primary` with backdrop blur
- Glass-card styling for the modal panel
- `text-primary`, `text-secondary` for text
- `bg-brand` for the visualization button
- `border-subtle` for table borders
- Dark theme compatible (all colors via CSS custom properties)

#### 4B. Responsive behavior

- Modal should be max `90vw × 85vh`
- Table should scroll horizontally on narrow viewports
- Graph should resize to fill available modal space
- Close button always visible (fixed top-right)

#### 4C. Animation

- Modal: `framer-motion` `AnimatePresence` with `opacity` + `scale` transition
- Button: subtle hover scale + glow effect

---

## Implementation Order

```
Phase 1A  →  Phase 2A  →  Phase 3B  →  Phase 3E      (documents — simplest end-to-end)
                ↓
          Phase 1C  →  Phase 2B  →  Phase 3D          (tables — medium complexity)
                                       ↓
                                  Phase 3C             (graph — most complex)
                                       ↓
                                  Phase 3A             (button on StepCard — wire it all together)
                                       ↓
                                  Phase 4              (polish)
```

**Suggested sprint breakdown:**

| Sprint | Scope | Effort |
|--------|-------|--------|
| **S1** | Types + DocumentResultView + Modal shell + StepCard button (documents only) | ~3 hrs |
| **S2** | `/api/query/replay` endpoint + `useQueryReplay` hook + TableResultView | ~3 hrs |
| **S3** | GraphResultView (reuse `react-force-graph-2d`) | ~3 hrs |
| **S4** | Polish: animations, responsive, error states, loading states | ~2 hrs |

**Total estimated effort: ~11 hours**

---

## Files Changed / Created

### New files

| File | Purpose |
|------|---------|
| `frontend/src/components/visualization/StepVisualizationModal.tsx` | Modal overlay wrapper |
| `frontend/src/components/visualization/GraphResultView.tsx` | Graph visualization panel |
| `frontend/src/components/visualization/TableResultView.tsx` | Tabular data panel |
| `frontend/src/components/visualization/DocumentResultView.tsx` | Document list panel |
| `frontend/src/hooks/useQueryReplay.ts` | API hook for on-demand query replay |
| `frontend/src/utils/agentType.ts` | Agent name → visualization type resolver |
| `api/app/routers/replay.py` | Query replay endpoint |

### Modified files

| File | Change |
|------|--------|
| `frontend/src/types/index.ts` | Add `VisualizationData` types |
| `frontend/src/components/StepCard.tsx` | Add visualization button (bottom-right) |
| `api/app/main.py` | Register replay router |

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Query replay returns different results than original | Low | Show disclaimer "Results may differ from original investigation" |
| GQL results are not graph-shaped (e.g., aggregations) | Medium | Fall back to table view when results don't contain identifiable nodes/edges |
| Large KQL result sets (>1000 rows) | Medium | Paginate or truncate to first 100 rows with "showing 100 of N" |
| AI Search agents don't have structured results | None | Already handled — just render `step.response` as markdown |
| `react-force-graph-2d` bundle size increase | Low | Already bundled in the app for `GraphTopologyViewer` |
| Query field is truncated to 500 chars | Medium | Increase truncation limit for query field (or don't truncate for replay-eligible agents) |

---

## Open Questions

1. **Should the graph visualization for GQL use `/query/topology` (nodes/edges structure) or `/query/graph` (tabular results)?**
   - `/query/topology` gives us pre-structured nodes/edges — better for graph viz but requires a second call that may return a different scope.
   - `/query/graph` returns the exact query results but in tabular form — we'd need to parse/infer the graph structure.
   - **Recommendation:** Use `/query/graph` and render as table by default; add a "View as topology" toggle that calls `/query/topology` with a scope filter.

2. **Should we increase the `step.query` truncation limit?**
   - Currently 500 chars, which should be sufficient for most GQL/KQL queries.
   - If longer queries are common, increase to 2000 or remove the limit for replay-eligible agents.

3. **Should past interactions (loaded from sidebar) support visualization?**
   - Yes, if we store the query string in the persisted `Interaction.steps[].query`. Currently this is already the case.
   - The replay endpoint would need to be available at view time.

4. **Modal vs. side panel vs. inline expansion?**
   - Modal recommended for maximum visualization space without disrupting the investigation flow.
   - Could later add a "pop out to side panel" option.
