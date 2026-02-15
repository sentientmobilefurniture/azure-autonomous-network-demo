# V6 Interactive Graph Topology Viewer — Implementation Plan

## Summary

Replace the 5 leftmost panels in the MetricsBar (4 hardcoded MetricCards + AlertChart image) with an **interactive network topology graph viewer**. The viewer displays the live Cosmos DB Gremlin graph state, supports pan/zoom/drag navigation, hover tooltips on nodes and edges, right-click context menus for display customization, and resizes within the existing `react-resizable-panels` layout. The LogStream panel remains unchanged.

---

## 1. Current State → Target State

### Current MetricsBar Layout (Zone 2)

```
┌────────────┬───────────────┬──────────┬──────────────┬──────────────────┬───────────────────────────┐
│ Active     │ Services      │ SLA At   │ Anomalies    │ AlertChart       │ >_ API LogStream (SSE)    │
│ Alerts: 12 │ Impacted: 3   │ Risk:    │ (24h): 231   │ (static PNG)     │    (live scrolling logs)  │
│ ▲4 vs 1h   │               │ $115k/hr │ ▲87 vs avg   │                  │                           │
└────────────┴───────────────┴──────────┴──────────────┴──────────────────┴───────────────────────────┘
  MetricCard    MetricCard    MetricCard   MetricCard      AlertChart          LogStream
  (8%)          (8%)          (8%)         (8%)            (14%)              (36%)    ← panel sizes
```

**All 5 boxes left of LogStream are hardcoded/static.** They add visual polish but provide no interactive value.

### Target MetricsBar Layout (Zone 2)

```
┌──────────────────────────────────────────────────────────────────┬───────────────────────────┐
│ ◆ Network Topology              [🔍 search...]  [⟳] [⤢ fit]    │ >_ API LogStream (SSE)    │
│                                                                  │    (live scrolling logs)  │
│          ┌─CoreRouter─┐                                          │                           │
│          │  SYD-01     │──connects_to──▸ TransportLink            │                           │
│          └─────────────┘       │                                  │                           │
│               ▲                ▼                                  │                           │
│          AggSwitch        MPLSPath ──depends_on──▸ Service        │                           │
│               │                                      │           │                           │
│          BaseStation        SLAPolicy ◂──governed_by──┘           │                           │
│                                                                  │                           │
│  [hover: tooltip with all node properties]                       │                           │
│  [right-click: context menu for color/label customization]       │                           │
└──────────────────────────────────────────────────────────────────┴───────────────────────────┘
  GraphTopologyViewer (resizable, ~64%)                               LogStream (resizable, ~36%)
```

---

## 2. Library Selection

### Decision: **react-force-graph-2d** (Primary Choice)

After evaluating 6 libraries, **react-force-graph-2d** is the best fit:

| Library | Recommendation | Why |
|---------|---------------|-----|
| **react-force-graph-2d** | **✅ PRIMARY** | 150K weekly downloads, actively maintained (days ago), rich API, canvas-based (lightweight), excellent React integration, `width`/`height` props for resizable panels |
| Reagraph | Runner-up | Built-in context menu + dark theme, but smaller community (27K/wk) and WebGL (three.js) is heavier than needed for ~50 nodes |
| Cytoscape.js | Eliminated | React wrapper unmaintained (3 years old) |
| vis-network | Eliminated | No React wrapper, 83MB bundle |
| @react-sigma/core | Eliminated | Sparse docs, overkill WebGL for small graphs |
| D3-force | Eliminated | Far too much custom code needed |

### Why react-force-graph-2d over Reagraph

- **3× larger community** (150K vs 27K weekly downloads) — more Stack Overflow answers, battle-tested
- **Canvas-based** — lighter than Reagraph's WebGL/three.js for our ~50-node graph
- **`width`/`height` props** — integrates cleanly with `react-resizable-panels` resize events
- **`nodeCanvasObject`** — full custom rendering control for our dark theme
- **`nodeLabel` accepts HTML** — rich tooltips without external dependency
- **`onNodeRightClick` / `onLinkRightClick`** — context menu events built in
- We build our own tooltip and context menu components (trivial with our existing Tailwind + Framer Motion stack, and gives us full control over styling)

### Installation

```bash
cd frontend && npm install react-force-graph-2d
```

No additional type packages needed — `react-force-graph-2d` ships its own TypeScript declarations. Verify after install that the `ForceGraphMethods` ref type is exported (some versions export it as `ForceGraphMethods`, others require accessing it differently — check the installed `.d.ts` if `import { ForceGraphMethods }` fails).

---

## 3. Backend: New `/query/topology` Endpoint

The existing `/query/graph` endpoint accepts arbitrary Gremlin queries and returns `{columns, data}` — a tabular format designed for agent consumption. For the graph viewer, we need a **topology-shaped response** with separate nodes and edges arrays.

### 3.1 New Endpoint Design

**File:** `graph-query-api/router_topology.py` (new)

```
POST /query/topology
```

**Request:**

```json
{
  "query": "g.V().hasLabel('CoreRouter','AggSwitch').bothE().otherV().path()",
  "vertex_labels": ["CoreRouter", "AggSwitch", "TransportLink"]
}
```

All fields optional. If empty, returns the full graph (all vertices + edges).

**Precedence rules:**
1. If `query` is provided, it is executed as raw Gremlin and the result is shaped into the topology format. `vertex_labels` is ignored.
2. If only `vertex_labels` is provided (no `query`), the backend generates a scoped Gremlin query that fetches only the listed vertex types and their inter-connecting edges (see §3.3).
3. If neither `query` nor `vertex_labels` is provided, the backend serves the full topology (see §3.2).

**Response:**

```json
{
  "nodes": [
    {
      "id": "CORE-SYD-01",
      "label": "CoreRouter",
      "properties": {
        "RouterId": "CORE-SYD-01",
        "City": "Sydney",
        "Region": "NSW",
        "Vendor": "Cisco",
        "Model": "ASR-9922"
      }
    }
  ],
  "edges": [
    {
      "id": "e-LINK-SYD-MEL-01-to-CORE-SYD-01",
      "source": "LINK-SYD-MEL-FIBRE-01",
      "target": "CORE-SYD-01",
      "label": "connects_to",
      "properties": {
        "direction": "source"
      }
    }
  ],
  "meta": {
    "node_count": 45,
    "edge_count": 72,
    "query_time_ms": 340,
    "labels": ["CoreRouter", "AggSwitch", "BaseStation", "TransportLink", "MPLSPath", "Service", "SLAPolicy", "BGPSession"]
  },
  "error": null
}
```

### 3.2 Default "Full Topology" Gremlin Query

When no `query` or `vertex_labels` are provided, execute two queries:

```gremlin
-- All vertices with full properties
g.V().project('id','label','properties').by(id).by(label).by(valueMap())

-- All edges with endpoints
g.E().project('id','label','source','target','properties').by(id).by(label).by(outV().id()).by(inV().id()).by(valueMap())
```

For the demo dataset this returns ~45 vertices + ~72 edges — trivially fast.

### 3.3 Filtered Query (via `vertex_labels`)

When `vertex_labels` is provided, fetch only those vertex types plus their incident edges:

```gremlin
g.V().hasLabel('CoreRouter','AggSwitch','TransportLink')
  .project('id','label','properties').by(id).by(label).by(valueMap())

g.V().hasLabel('CoreRouter','AggSwitch','TransportLink')
  .bothE()
  .where(otherV().hasLabel('CoreRouter','AggSwitch','TransportLink'))
  .project('id','label','source','target','properties')
  .by(id).by(label).by(outV().id()).by(inV().id()).by(valueMap())
```

### 3.4 Router Implementation

**File:** `graph-query-api/router_topology.py` (new)

The router handler calls the backend's `get_topology()` method, measures query time, and returns a `TopologyResponse`:

```python
import time
from fastapi import APIRouter
from models import TopologyRequest, TopologyResponse, TopologyMeta
from router_graph import get_graph_backend  # reuse the lazy-init singleton

router = APIRouter()

@router.post("/query/topology", response_model=TopologyResponse)
async def topology(req: TopologyRequest) -> TopologyResponse:
    backend = get_graph_backend()  # NOT get_backend() — avoids creating a new client per request
    t0 = time.perf_counter()
    try:
        result = await backend.get_topology(
            query=req.query,
            vertex_labels=req.vertex_labels,
        )
        elapsed = (time.perf_counter() - t0) * 1000
        labels = sorted({n["label"] for n in result["nodes"]})
        return TopologyResponse(
            nodes=result["nodes"],
            edges=result["edges"],
            meta=TopologyMeta(
                node_count=len(result["nodes"]),
                edge_count=len(result["edges"]),
                query_time_ms=round(elapsed, 1),
                labels=labels,
            ),
        )
    except Exception as exc:
        return TopologyResponse(error=str(exc))
```

**Mounting** (in `main.py`, same pattern as existing routers):
```python
from router_topology import router as topology_router
app.include_router(topology_router)
```

### 3.5 Mock Backend Support

Add a `get_topology()` method to `MockGraphBackend` that returns the same structure using static data — no Gremlin queries needed. This lets the graph viewer work offline with `GRAPH_BACKEND=mock`.

### 3.6 Pydantic Models

**File:** `graph-query-api/models.py` (additions)

The existing file imports `BaseModel` and `Field` from pydantic but does **not** import `Any` from `typing`. Add it:

```python
from __future__ import annotations
from typing import Any          # ← ADD THIS
from pydantic import BaseModel, Field

# ... existing models ...

class TopologyNode(BaseModel):
    id: str
    label: str  # vertex label (CoreRouter, AggSwitch, etc.)
    properties: dict[str, Any] = {}

class TopologyEdge(BaseModel):
    id: str
    source: str  # source vertex id
    target: str  # target vertex id
    label: str   # edge label (connects_to, aggregates_to, etc.)
    properties: dict[str, Any] = {}

class TopologyMeta(BaseModel):
    node_count: int
    edge_count: int
    query_time_ms: float
    labels: list[str] = []

class TopologyRequest(BaseModel):
    query: str | None = None
    vertex_labels: list[str] | None = None

class TopologyResponse(BaseModel):
    nodes: list[TopologyNode] = []
    edges: list[TopologyEdge] = []
    meta: TopologyMeta | None = None
    error: str | None = None
```

### 3.7 `GraphBackend` Protocol Extension

**File:** `graph-query-api/backends/__init__.py`

The existing `GraphBackend` protocol defines `execute_query()` and `close()`. Add `get_topology()`:

```python
@runtime_checkable
class GraphBackend(Protocol):
    async def execute_query(self, query: str, **kwargs) -> dict: ...
    async def get_topology(
        self,
        query: str | None = None,
        vertex_labels: list[str] | None = None,
    ) -> dict:
        """Return {nodes: [...], edges: [...]} in TopologyResponse shape."""
        ...
    def close(self) -> None: ...
```

> **Implementation note:** Because the protocol is `@runtime_checkable`, adding
> `get_topology()` means any backend that has not yet implemented it will fail
> `isinstance` checks. To allow phased rollout (mock first, cosmosdb later),
> add a **concrete default** to the protocol method body that raises
> `NotImplementedError("get_topology() not implemented for this backend")` —
> or, alternatively, don't add `get_topology()` to the Protocol at all and
> instead call it via `getattr(backend, 'get_topology')` in the router with
> a clear error message. The simplest approach: implement `get_topology()` on
> both `MockGraphBackend` and `CosmosDBGremlinBackend` in the same phase.

### 3.8 Cosmos DB `get_topology()` Implementation Notes

**File:** `graph-query-api/backends/cosmosdb.py`

The existing `_normalise_results()` method flattens Gremlin `valueMap()` output — where property values are wrapped in single-element lists — into flat dicts. The new `get_topology()` method reuses this normalization but must additionally:

1. Run two Gremlin queries (§3.2 or §3.3) inside `asyncio.to_thread` (same pattern as `execute_query`).
2. Flatten `valueMap()` list-wrapped values: `{"City": ["Sydney"]}` → `{"City": "Sydney"}`.
3. Handle the `query` vs `vertex_labels` precedence (§3.1). When a raw `query` is given, execute it and reshape the traversal result into `{nodes, edges}` — this requires path-decomposition logic and should be deferred post-MVP (return an error for raw queries initially).

---

## 4. Frontend: `GraphTopologyViewer` Component

### 4.1 Component Architecture

```
MetricsBar.tsx (modified)
├── GraphTopologyViewer.tsx  (new — replaces 4 MetricCards + AlertChart)
│   ├── useTopology.ts       (new — data fetching hook)
│   ├── GraphCanvas.tsx      (new — react-force-graph-2d wrapper)
│   ├── GraphToolbar.tsx     (new — search bar + controls)
│   ├── GraphTooltip.tsx     (new — hover tooltip overlay)
│   └── GraphContextMenu.tsx (new — right-click context menu)
└── LogStream.tsx            (unchanged)
```

### 4.2 `useTopology` Hook

**File:** `frontend/src/hooks/useTopology.ts`

```typescript
import { useState, useEffect, useCallback, useRef } from 'react';

// ── Types ──────────────────────────────────────────────────────

export interface TopologyNode {
  id: string;
  label: string;     // vertex label (CoreRouter, AggSwitch, etc.)
  properties: Record<string, unknown>;
  // Force-graph internal fields (added by the library)
  x?: number;
  y?: number;
  fx?: number | null;
  fy?: number | null;
}

export interface TopologyEdge {
  id: string;
  source: string | TopologyNode;
  target: string | TopologyNode;
  label: string;     // edge label (connects_to, etc.)
  properties: Record<string, unknown>;
}

export interface TopologyMeta {
  node_count: number;
  edge_count: number;
  query_time_ms: number;
  labels: string[];
}

interface TopologyData {
  nodes: TopologyNode[];
  edges: TopologyEdge[];
  meta: TopologyMeta | null;
}

// ── Hook ───────────────────────────────────────────────────────

export function useTopology() {
  const [data, setData] = useState<TopologyData>({ nodes: [], edges: [], meta: null });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const fetchTopology = useCallback(async (vertexLabels?: string[]) => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    setLoading(true);
    setError(null);

    try {
      const res = await fetch('/query/topology', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ vertex_labels: vertexLabels }),
        signal: ctrl.signal,
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      if (json.error) throw new Error(json.error);
      setData({ nodes: json.nodes, edges: json.edges, meta: json.meta });
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch full topology on mount
  useEffect(() => {
    fetchTopology();
  }, [fetchTopology]);

  return { data, loading, error, refetch: fetchTopology };
}
```

### 4.3 Node Color Mapping

Each vertex label gets a distinct color from our design system. These match the attached reference image's aesthetic:

```typescript
export const NODE_COLORS: Record<string, string> = {
  CoreRouter:     '#38BDF8', // sky-400 (cyan circle in reference)
  AggSwitch:      '#FB923C', // orange-400 (orange circle)
  BaseStation:    '#A78BFA', // violet-400 (purple circle)
  TransportLink:  '#3B82F6', // blue-500 (blue circle)
  MPLSPath:       '#C084FC', // purple-400 (lavender circle)
  Service:        '#CA8A04', // yellow-600 (dark gold circle)
  SLAPolicy:      '#FB7185', // rose-400 (pink circle)
  BGPSession:     '#F472B6', // pink-400 (pink circle)
};

export const NODE_SIZES: Record<string, number> = {
  CoreRouter:     10,  // largest — central hub
  AggSwitch:      7,
  BaseStation:    5,
  TransportLink:  7,
  MPLSPath:       6,
  Service:        8,   // important business context
  SLAPolicy:      6,
  BGPSession:     5,
};
```

### 4.4 `GraphCanvas` Component

**File:** `frontend/src/components/graph/GraphCanvas.tsx`

This is the core rendering component wrapping `react-force-graph-2d`.

**State ownership note:** Tooltip, context menu state, and user-customization callbacks all live in the parent `GraphTopologyViewer` and are passed down as props. `GraphCanvas` is a pure rendering wrapper — it forwards DOM events upward.

The component also exposes an imperative `zoomToFit()` method via `React.forwardRef` + `useImperativeHandle` so the toolbar's "Fit" button can call it from `GraphTopologyViewer`.

```typescript
import { useRef, useCallback, useEffect, forwardRef, useImperativeHandle } from 'react';
import ForceGraph2D, { ForceGraphMethods } from 'react-force-graph-2d';
import type { TopologyNode, TopologyEdge } from '../../hooks/useTopology';
import { NODE_COLORS, NODE_SIZES } from './graphConstants';

export interface GraphCanvasHandle {
  zoomToFit: () => void;
}

interface GraphCanvasProps {
  nodes: TopologyNode[];
  edges: TopologyEdge[];
  width: number;
  height: number;
  nodeDisplayField: Record<string, string>;  // { 'CoreRouter': 'City', 'Service': 'CustomerName' }
  nodeColorOverride: Record<string, string>; // user-customized colors
  onNodeHover: (node: TopologyNode | null, event?: MouseEvent) => void;
  onLinkHover: (edge: TopologyEdge | null, event?: MouseEvent) => void;
  onNodeRightClick: (node: TopologyNode, event: MouseEvent) => void;
  onBackgroundClick: () => void;
}

export const GraphCanvas = forwardRef<GraphCanvasHandle, GraphCanvasProps>(
  function GraphCanvas(
    { nodes, edges, width, height,
      nodeDisplayField, nodeColorOverride,
      onNodeHover, onLinkHover, onNodeRightClick, onBackgroundClick },
    ref,
  ) {
    const fgRef = useRef<ForceGraphMethods>(null);

    // Expose zoomToFit to parent via imperative handle
    useImperativeHandle(ref, () => ({
      zoomToFit: () => fgRef.current?.zoomToFit(400, 40),
    }), []);

    // Fit graph to view on data change
    useEffect(() => {
      if (fgRef.current && nodes.length > 0) {
        setTimeout(() => fgRef.current?.zoomToFit(400, 40), 500);
      }
    }, [nodes.length]);

  // Color resolver
  const getNodeColor = useCallback(
    (node: TopologyNode) =>
      nodeColorOverride[node.label] ?? NODE_COLORS[node.label] ?? '#6B7280',
    [nodeColorOverride],
  );

  // Custom node rendering (colored circle + label)
  const nodeCanvasObject = useCallback(
    (node: TopologyNode, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const size = NODE_SIZES[node.label] ?? 6;
      const color = getNodeColor(node);

      // Circle
      ctx.beginPath();
      ctx.arc(node.x!, node.y!, size, 0, 2 * Math.PI);
      ctx.fillStyle = color;
      ctx.fill();
      ctx.strokeStyle = 'rgba(255,255,255,0.15)';
      ctx.lineWidth = 0.5;
      ctx.stroke();

      // Label (show custom field or id)
      const displayField = nodeDisplayField[node.label] ?? 'id';
      const label = displayField === 'id'
        ? node.id
        : String(node.properties[displayField] ?? node.id);

      const fontSize = Math.max(10 / globalScale, 3);
      ctx.font = `${fontSize}px 'Segoe UI', system-ui, sans-serif`;
      ctx.fillStyle = '#E4E4E7';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      ctx.fillText(label, node.x!, node.y! + size + 2);
    },
    [getNodeColor, nodeDisplayField],
  );

  // Edge label rendering
  const linkCanvasObjectMode = () => 'after' as const;
  const linkCanvasObject = useCallback(
    (link: TopologyEdge, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const src = link.source as TopologyNode;
      const tgt = link.target as TopologyNode;
      if (!src.x || !tgt.x) return;

      const midX = (src.x + tgt.x) / 2;
      const midY = (src.y! + tgt.y!) / 2;
      const fontSize = Math.max(8 / globalScale, 2.5);

      ctx.font = `${fontSize}px 'Segoe UI', system-ui, sans-serif`;
      ctx.fillStyle = '#71717A';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(link.label, midX, midY);
    },
    [],
  );

  // Double-click handler: center + zoom to specific node
  const handleNodeDoubleClick = useCallback((node: TopologyNode) => {
    fgRef.current?.centerAt(node.x, node.y, 600);
    fgRef.current?.zoom(4, 600);
  }, []);

  return (
    <ForceGraph2D
      ref={fgRef}
      width={width}
      height={height}
      graphData={{ nodes, links: edges }}
      backgroundColor="transparent"
      // Node rendering
      nodeCanvasObject={nodeCanvasObject}
      nodeCanvasObjectMode={() => 'replace'}
      nodeId="id"
      // Edge rendering
      linkSource="source"
      linkTarget="target"
      linkColor={() => 'rgba(255,255,255,0.12)'}
      linkWidth={1.5}
      linkDirectionalArrowLength={4}
      linkDirectionalArrowRelPos={0.9}
      linkDirectionalArrowColor={() => 'rgba(255,255,255,0.2)'}
      linkCanvasObjectMode={linkCanvasObjectMode}
      linkCanvasObject={linkCanvasObject}
      // Interaction
      onNodeHover={onNodeHover}
      onLinkHover={onLinkHover}
      onNodeRightClick={onNodeRightClick}
      onNodeClick={handleNodeDoubleClick}  // react-force-graph fires onClick for double-click
      onBackgroundClick={onBackgroundClick}
      // Physics
      d3AlphaDecay={0.02}
      d3VelocityDecay={0.3}
      cooldownTime={3000}
      enableNodeDrag={true}
      enableZoomInteraction={true}
      enablePanInteraction={true}
    />
  );
  },
);
```

> **Note:** `react-force-graph-2d` does not distinguish single-click from double-click natively. The `onNodeClick` handler above fires on every click. To implement true double-click, wrap with a debounced timer that distinguishes single from double clicks.

### 4.5 `GraphTooltip` Component

**File:** `frontend/src/components/graph/GraphTooltip.tsx`

A floating tooltip that appears on hover, showing all node/edge metadata:

```typescript
import { motion, AnimatePresence } from 'framer-motion';
import type { TopologyNode, TopologyEdge } from '../../hooks/useTopology';
import { NODE_COLORS } from './graphConstants';

interface GraphTooltipProps {
  tooltip: {
    x: number;
    y: number;
    node?: TopologyNode;
    edge?: TopologyEdge;
  } | null;
}

export function GraphTooltip({ tooltip }: GraphTooltipProps) {
  return (
    <AnimatePresence>
      {tooltip && (
        <motion.div
          className="fixed z-50 bg-neutral-bg3 border border-white/15 rounded-lg shadow-xl
                     px-3 py-2 pointer-events-none max-w-xs"
          style={{ left: tooltip.x + 12, top: tooltip.y - 8 }}
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.95 }}
          transition={{ duration: 0.1 }}
        >
          {tooltip.node && <NodeTooltipContent node={tooltip.node} />}
          {tooltip.edge && <EdgeTooltipContent edge={tooltip.edge} />}
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function NodeTooltipContent({ node }: { node: TopologyNode }) {
  return (
    <>
      <div className="flex items-center gap-2 mb-1.5">
        <span className="h-2 w-2 rounded-full" style={{ backgroundColor: NODE_COLORS[node.label] }} />
        <span className="text-xs font-semibold text-text-primary">{node.id}</span>
      </div>
      <span className="text-[10px] uppercase tracking-wider text-text-muted block mb-1">
        {node.label}
      </span>
      <div className="space-y-0.5">
        {Object.entries(node.properties).map(([key, val]) => (
          <div key={key} className="text-[11px]">
            <span className="text-text-muted">{key}:</span>{' '}
            <span className="text-text-secondary">{String(val)}</span>
          </div>
        ))}
      </div>
    </>
  );
}

function EdgeTooltipContent({ edge }: { edge: TopologyEdge }) {
  const srcId = typeof edge.source === 'string' ? edge.source : edge.source.id;
  const tgtId = typeof edge.target === 'string' ? edge.target : edge.target.id;
  return (
    <>
      <div className="text-xs font-semibold text-text-primary mb-1">{edge.label}</div>
      <div className="text-[11px] text-text-muted mb-1">
        {srcId} → {tgtId}
      </div>
      {Object.keys(edge.properties).length > 0 && (
        <div className="space-y-0.5">
          {Object.entries(edge.properties).map(([key, val]) => (
            <div key={key} className="text-[11px]">
              <span className="text-text-muted">{key}:</span>{' '}
              <span className="text-text-secondary">{String(val)}</span>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
```

### 4.6 `GraphContextMenu` Component

**File:** `frontend/src/components/graph/GraphContextMenu.tsx`

Right-click on a node opens a styled context menu that lets the user:
1. Choose which property field to display as the node label
2. Change the color for that node type

```typescript
import { motion, AnimatePresence } from 'framer-motion';
import type { TopologyNode } from '../../hooks/useTopology';
import { NODE_COLORS } from './graphConstants';

const COLOR_PALETTE = [
  '#38BDF8', '#FB923C', '#A78BFA', '#3B82F6',
  '#C084FC', '#CA8A04', '#FB7185', '#F472B6',
  '#10B981', '#EF4444', '#6366F1', '#FBBF24',
];

interface GraphContextMenuProps {
  menu: { x: number; y: number; node: TopologyNode } | null;
  onClose: () => void;
  onSetDisplayField: (label: string, field: string) => void;
  onSetColor: (label: string, color: string) => void;
}

export function GraphContextMenu({ menu, onClose, onSetDisplayField, onSetColor }: GraphContextMenuProps) {
  if (!menu) return null;

  const propertyKeys = ['id', ...Object.keys(menu.node.properties)];

  return (
    <>
      {/* Backdrop to catch clicks */}
      <div className="fixed inset-0 z-40" onClick={onClose} onContextMenu={(e) => {e.preventDefault(); onClose();}} />

      <motion.div
        className="fixed z-50 bg-neutral-bg3 border border-white/15 rounded-lg shadow-xl
                   py-1 min-w-[180px]"
        style={{ left: menu.x, top: menu.y }}
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.12 }}
      >
        {/* Header */}
        <div className="px-3 py-1.5 border-b border-white/10">
          <span className="text-xs font-semibold text-text-primary">{menu.node.id}</span>
          <span className="text-[10px] text-text-muted ml-2">{menu.node.label}</span>
        </div>

        {/* Display field selector */}
        <div className="px-3 py-1.5">
          <span className="text-[10px] uppercase tracking-wider text-text-muted">Display Field</span>
          <div className="mt-1 space-y-0.5">
            {propertyKeys.map((key) => (
              <button
                key={key}
                className="block w-full text-left text-xs px-2 py-1 rounded
                           hover:bg-white/10 text-text-secondary hover:text-text-primary"
                onClick={() => { onSetDisplayField(menu.node.label, key); onClose(); }}
              >
                {key}
              </button>
            ))}
          </div>
        </div>

        {/* Color picker */}
        <div className="px-3 py-1.5 border-t border-white/10">
          <span className="text-[10px] uppercase tracking-wider text-text-muted">
            Color ({menu.node.label})
          </span>
          <div className="flex flex-wrap gap-1.5 mt-1.5">
            {COLOR_PALETTE.map((color) => (
              <button
                key={color}
                className="h-4 w-4 rounded-full border border-white/20 hover:scale-125 transition-transform"
                style={{ backgroundColor: color }}
                onClick={() => { onSetColor(menu.node.label, color); onClose(); }}
              />
            ))}
          </div>
        </div>
      </motion.div>
    </>
  );
}
```

### 4.7 `GraphToolbar` Component

**File:** `frontend/src/components/graph/GraphToolbar.tsx`

A compact toolbar above the graph with:
- Search/filter input (type to fuzzy-match node IDs)
- Vertex label filter chips (colored dots matching `NODE_COLORS`)
- Zoom-to-fit button
- Refresh button
- Node count + edge count

```typescript
import { NODE_COLORS } from './graphConstants';
import type { TopologyMeta } from '../../hooks/useTopology';

interface GraphToolbarProps {
  meta: TopologyMeta | null;
  loading: boolean;
  availableLabels: string[];
  activeLabels: string[];
  onToggleLabel: (label: string) => void;
  searchQuery: string;
  onSearchChange: (q: string) => void;
  onRefresh: () => void;
  onZoomToFit: () => void;
}

export function GraphToolbar({
  meta, loading, availableLabels, activeLabels,
  onToggleLabel, searchQuery, onSearchChange, onRefresh, onZoomToFit,
}: GraphToolbarProps) {
  return (
    <div className="flex items-center gap-2 px-3 py-1.5 border-b border-white/10 shrink-0">
      {/* Title */}
      <span className="text-xs font-semibold text-text-primary whitespace-nowrap">◆ Network Topology</span>

      {/* Label filter chips */}
      <div className="flex items-center gap-1 ml-2 overflow-x-auto">
        {availableLabels.map((label) => {
          const active = activeLabels.length === 0 || activeLabels.includes(label);
          return (
            <button
              key={label}
              onClick={() => onToggleLabel(label)}
              className={`flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px]
                         border transition-colors
                         ${active
                           ? 'border-white/20 text-text-secondary'
                           : 'border-transparent text-text-muted opacity-40'}`}
            >
              <span
                className="h-2 w-2 rounded-full shrink-0"
                style={{ backgroundColor: NODE_COLORS[label] ?? '#6B7280' }}
              />
              {label}
            </button>
          );
        })}
      </div>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Search */}
      <input
        type="text"
        value={searchQuery}
        onChange={(e) => onSearchChange(e.target.value)}
        placeholder="Search nodes..."
        className="bg-white/5 border border-white/10 rounded px-2 py-0.5
                   text-[11px] text-text-secondary placeholder:text-text-muted
                   w-32 focus:w-44 transition-all focus:outline-none focus:border-white/25"
      />

      {/* Counts */}
      {meta && (
        <span className="text-[10px] text-text-muted whitespace-nowrap">
          {meta.node_count}N · {meta.edge_count}E
        </span>
      )}

      {/* Zoom-to-fit */}
      <button
        onClick={onZoomToFit}
        className="text-text-muted hover:text-text-primary text-xs px-1"
        title="Fit to view"
      >⤢</button>

      {/* Refresh */}
      <button
        onClick={onRefresh}
        className={`text-text-muted hover:text-text-primary text-xs px-1
                   ${loading ? 'animate-spin' : ''}`}
        title="Refresh"
      >⟳</button>
    </div>
  );
}
```

### 4.8 `GraphTopologyViewer` — Orchestrating Component

**File:** `frontend/src/components/GraphTopologyViewer.tsx`

Composes the hook, toolbar, canvas, tooltip, and context menu. Manages user customization state (display fields, colors) in local state (persisted to `localStorage` for cross-session survival).

```typescript
import { useState, useCallback, useRef, useEffect } from 'react';
import { useTopology, TopologyNode, TopologyEdge } from '../hooks/useTopology';
import { GraphCanvas, GraphCanvasHandle } from './graph/GraphCanvas';
import { GraphToolbar } from './graph/GraphToolbar';
import { GraphTooltip } from './graph/GraphTooltip';
import { GraphContextMenu } from './graph/GraphContextMenu';

interface GraphTopologyViewerProps {
  width: number;
  height: number;
}

export function GraphTopologyViewer({ width, height }: GraphTopologyViewerProps) {
  const { data, loading, error, refetch } = useTopology();
  const canvasRef = useRef<GraphCanvasHandle>(null);

  // ── Tooltip + context menu state (owned here, not in GraphCanvas) ──

  const [tooltip, setTooltip] = useState<{
    x: number; y: number;
    node?: TopologyNode; edge?: TopologyEdge;
  } | null>(null);
  const [contextMenu, setContextMenu] = useState<{
    x: number; y: number; node: TopologyNode;
  } | null>(null);

  const handleNodeHover = useCallback((node: TopologyNode | null, event?: MouseEvent) => {
    if (node && event) {
      setTooltip({ x: event.clientX, y: event.clientY, node, edge: undefined });
    } else {
      setTooltip(null);
    }
  }, []);

  const handleLinkHover = useCallback((edge: TopologyEdge | null, event?: MouseEvent) => {
    if (edge && event) {
      setTooltip({ x: event.clientX, y: event.clientY, edge, node: undefined });
    } else {
      setTooltip(null);
    }
  }, []);

  const handleNodeRightClick = useCallback((node: TopologyNode, event: MouseEvent) => {
    event.preventDefault();
    setContextMenu({ x: event.clientX, y: event.clientY, node });
  }, []);

  // ── User customization (persisted to localStorage) ──

  const [nodeDisplayField, setNodeDisplayField] = useState<Record<string, string>>(() => {
    const stored = localStorage.getItem('graph-display-fields');
    return stored ? JSON.parse(stored) : {};
  });
  const [nodeColorOverride, setNodeColorOverride] = useState<Record<string, string>>(() => {
    const stored = localStorage.getItem('graph-colors');
    return stored ? JSON.parse(stored) : {};
  });

  // Label filtering
  const [activeLabels, setActiveLabels] = useState<string[]>([]);
  const [searchQuery, setSearchQuery] = useState('');

  // Persist customization
  useEffect(() => {
    localStorage.setItem('graph-display-fields', JSON.stringify(nodeDisplayField));
  }, [nodeDisplayField]);
  useEffect(() => {
    localStorage.setItem('graph-colors', JSON.stringify(nodeColorOverride));
  }, [nodeColorOverride]);

  // ── Node/edge filtering ──

  const filteredNodes = data.nodes.filter((n) => {
    if (activeLabels.length > 0 && !activeLabels.includes(n.label)) return false;
    if (searchQuery && !n.id.toLowerCase().includes(searchQuery.toLowerCase())) return false;
    return true;
  });
  const nodeIdSet = new Set(filteredNodes.map((n) => n.id));
  const filteredEdges = data.edges.filter((e) => {
    const srcId = typeof e.source === 'string' ? e.source : e.source.id;
    const tgtId = typeof e.target === 'string' ? e.target : e.target.id;
    return nodeIdSet.has(srcId) && nodeIdSet.has(tgtId);
  });

  // Reserve toolbar height
  const TOOLBAR_HEIGHT = 36;

  return (
    <div className="glass-card h-full flex flex-col overflow-hidden">
      <GraphToolbar
        meta={data.meta}
        loading={loading}
        availableLabels={data.meta?.labels ?? []}
        activeLabels={activeLabels}
        onToggleLabel={(l) =>
          setActiveLabels((prev) =>
            prev.includes(l) ? prev.filter((x) => x !== l) : [...prev, l]
          )
        }
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        onRefresh={() => refetch()}
        onZoomToFit={() => canvasRef.current?.zoomToFit()}
      />

      {error && (
        <div className="text-xs text-status-error px-3 py-1">{error}</div>
      )}

      {loading && data.nodes.length === 0 && (
        <div className="flex-1 flex items-center justify-center">
          <span className="text-xs text-text-muted animate-pulse">Loading topology…</span>
        </div>
      )}

      <div className="flex-1 min-h-0 relative">
        <GraphCanvas
          ref={canvasRef}
          nodes={filteredNodes}
          edges={filteredEdges}
          width={width}
          height={height - TOOLBAR_HEIGHT}
          nodeDisplayField={nodeDisplayField}
          nodeColorOverride={nodeColorOverride}
          onNodeHover={handleNodeHover}
          onLinkHover={handleLinkHover}
          onNodeRightClick={handleNodeRightClick}
          onBackgroundClick={() => setContextMenu(null)}
        />
      </div>

      {/* Overlays rendered outside GraphCanvas so they appear above the <canvas> */}
      <GraphTooltip tooltip={tooltip} />
      <GraphContextMenu
        menu={contextMenu}
        onClose={() => setContextMenu(null)}
        onSetDisplayField={(label, field) =>
          setNodeDisplayField((prev) => ({ ...prev, [label]: field }))
        }
        onSetColor={(label, color) =>
          setNodeColorOverride((prev) => ({ ...prev, [label]: color }))
        }
      />
    </div>
  );
}
```

### 4.9 Modified `MetricsBar.tsx`

Replace the 4 MetricCards + AlertChart with a single `GraphTopologyViewer` panel:

```typescript
// BEFORE (6 panels: 4 metrics + 1 chart + 1 log)
// AFTER  (2 panels: 1 graph viewer + 1 log)

import { useRef, useState, useEffect } from 'react';
import { Group as PanelGroup, Panel, Separator as PanelResizeHandle } from 'react-resizable-panels';
import { GraphTopologyViewer } from './GraphTopologyViewer';
import { LogStream } from './LogStream';

export function MetricsBar() {
  const graphPanelRef = useRef<HTMLDivElement>(null);
  const [graphSize, setGraphSize] = useState({ width: 800, height: 300 });

  // Track panel resize via ResizeObserver
  useEffect(() => {
    const el = graphPanelRef.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => {
      setGraphSize({
        width: entry.contentRect.width,
        height: entry.contentRect.height,
      });
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <div className="h-full px-6 py-3">
      <PanelGroup className="h-full">
        {/* Graph topology viewer */}
        <Panel defaultSize={64} minSize={30}>
          <div ref={graphPanelRef} className="h-full px-1">
            <GraphTopologyViewer width={graphSize.width} height={graphSize.height} />
          </div>
        </Panel>

        <PanelResizeHandle className="metrics-resize-handle" />

        {/* API logs (unchanged) */}
        <Panel defaultSize={36} minSize={12}>
          <div className="h-full px-1">
            <LogStream url="/api/logs" title="API" />
          </div>
        </Panel>
      </PanelGroup>
    </div>
  );
}
```

---

## 5. Interaction Reference

### Mouse Controls

| Action | Behavior |
|--------|----------|
| **Hover node** | Show tooltip with all vertex properties (id, label, City, Region, Vendor, etc.) |
| **Hover edge** | Show tooltip with edge label + source/target + edge properties |
| **Left-click + drag node** | Pin node to new position (sets `fx`/`fy`) |
| **Left-click background** | Dismiss any open context menu |
| **Right-click node** | Open context menu: choose display field, change node type color |
| **Scroll wheel** | Zoom in/out |
| **Left-click + drag background** | Pan the viewport |
| **Double-click node** | Center + zoom to node (see §4.4 caveat — `react-force-graph-2d` fires `onNodeClick` for all clicks; true double-click requires a debounce wrapper) |

### Toolbar Controls

| Control | Behavior |
|---------|----------|
| **Search** | Filter nodes by ID substring — non-matching nodes and their orphaned edges are hidden |
| **Label chips** | Toggle vertex types on/off (e.g., hide all BaseStation nodes) |
| **⟳ Refresh** | Re-fetch topology from API |
| **⤢ Fit** | `zoomToFit()` — fit all visible nodes in viewport |

---

## 6. Dataset Size Analysis

The demo graph is intentionally small — perfect for real-time interactive visualization:

| Vertex Type | Count | Properties |
|------------|-------|------------|
| CoreRouter | 3 | RouterId, City, Region, Vendor, Model |
| AggSwitch | 6 | SwitchId, City, UplinkRouterId |
| BaseStation | 8 | StationId, StationType, AggSwitchId, City |
| TransportLink | 10 | LinkId, LinkType, CapacityGbps, SourceRouterId, TargetRouterId |
| MPLSPath | 5 | PathId, PathType |
| Service | 10 | ServiceId, ServiceType, CustomerName, CustomerCount, ActiveUsers |
| SLAPolicy | 5 | SLAPolicyId, ServiceId, AvailabilityPct, MaxLatencyMs, PenaltyPerHourUSD, Tier |
| BGPSession | 3 | SessionId, PeerARouterId, PeerBRouterId, ASNumberA, ASNumberB |
| **Total vertices** | **~50** | |

| Edge Type | Estimated Count |
|-----------|----------------|
| connects_to (TransportLink→CoreRouter, ×2 per link) | ~20 |
| aggregates_to (AggSwitch→CoreRouter) | ~6 |
| backhauls_via (BaseStation→AggSwitch) | ~8 |
| routes_via (MPLSPath→TransportLink hops) | ~17 |
| depends_on (Service→MPLSPath/AggSwitch/BaseStation) | ~15 |
| governed_by (SLAPolicy→Service) | ~5 |
| peers_over (BGPSession→CoreRouter, ×2 per session) | ~6 |
| **Total edges** | **~77** |

At **~50 nodes / ~77 edges**, `react-force-graph-2d` renders in <1ms per frame at 60fps. No performance concerns.

---

## 7. File Manifest

### New Files

| File | Purpose |
|------|---------|
| `graph-query-api/router_topology.py` | New POST /query/topology endpoint (§3.4) |
| `frontend/src/hooks/useTopology.ts` | Data fetching hook |
| `frontend/src/components/GraphTopologyViewer.tsx` | Orchestrating container component |
| `frontend/src/components/graph/GraphCanvas.tsx` | react-force-graph-2d wrapper (with `forwardRef` imperative handle) |
| `frontend/src/components/graph/GraphToolbar.tsx` | Search + label chips + zoom/refresh controls |
| `frontend/src/components/graph/GraphTooltip.tsx` | Hover tooltip overlay |
| `frontend/src/components/graph/GraphContextMenu.tsx` | Right-click display-field + color picker menu |
| `frontend/src/components/graph/graphConstants.ts` | `NODE_COLORS`, `NODE_SIZES`, shared config |

### Modified Files

| File | Change |
|------|--------|
| `frontend/src/components/MetricsBar.tsx` | Replace 5 panels with `GraphTopologyViewer` + `LogStream` |
| `graph-query-api/main.py` | Mount `topology_router` via `include_router()` |
| `graph-query-api/models.py` | Add `TopologyNode`, `TopologyEdge`, `TopologyMeta`, `TopologyRequest`, `TopologyResponse`; add `from typing import Any` |
| `graph-query-api/backends/cosmosdb.py` | Add `get_topology()` method (§3.8) |
| `graph-query-api/backends/mock.py` | Add `get_topology()` returning static topology data |
| `graph-query-api/backends/__init__.py` | Add `get_topology()` to `GraphBackend` protocol (§3.7) |
| `frontend/package.json` | Add `react-force-graph-2d` dependency |
| `frontend/vite.config.ts` | Add `/query` proxy entry pointing to `localhost:8100` (§9) |

> **OpenAPI specs (`openapi/cosmosdb.yaml`, `openapi/mock.yaml`) — NO CHANGE.**
> These specs are consumed by Foundry agents via `OpenApiTool`. The `/query/topology`
> endpoint is for the frontend graph viewer only — exposing it in the agent-facing
> OpenAPI specs would cause agents to call it during investigations, which is not
> intended. Keep the specs unchanged.

> **`frontend/nginx.conf.template` — optional fix (legacy artifact).**
> This template is missing the `/query/` location block that the root `nginx.conf`
> has. However, it is only used by the per-service `frontend/Dockerfile` which is
> marked as "Legacy — unused in unified deploy" in ARCHITECTURE.md. The production
> unified container uses the root `nginx.conf` (which already has `/query/`). Fix
> for consistency if desired, but it is not required for V6 to work.

### Deleted Files (or deprecated)

| File | Reason |
|------|--------|
| `frontend/src/components/MetricCard.tsx` | No longer used (can keep for future re-use) |
| `frontend/src/components/AlertChart.tsx` | Replaced by live graph |

---

## 8. Implementation Order

| Phase | Tasks | Estimate |
|-------|-------|----------|
| **Phase 1** | Backend: Add Pydantic models (§3.6), `GraphBackend` protocol extension (§3.7), `router_topology.py` (§3.4), mock backend `get_topology()` (§3.5), **cosmosdb `get_topology()` (§3.8)** — both backends must implement the protocol method in the same phase to avoid breaking `@runtime_checkable` checks | 1.5 hours |
| **Phase 2** | Frontend: `npm install react-force-graph-2d`, create `graphConstants.ts`, `useTopology.ts`, `GraphCanvas.tsx` (basic rendering) | 1.5 hours |
| **Phase 3** | Frontend: `GraphTooltip.tsx`, `GraphContextMenu.tsx`, `GraphToolbar.tsx` | 1.5 hours |
| **Phase 4** | Frontend: `GraphTopologyViewer.tsx` + modify `MetricsBar.tsx` — integrate all pieces + Vite proxy (§9) | 1 hour |
| **Phase 5** | Testing: verify with mock backend locally, then with live Cosmos DB | 0.5 hours |
| **Total** | | **~6 hours** |

### Phase 1 can be tested independently

After Phase 1, the new endpoint works with `GRAPH_BACKEND=mock`:

```bash
curl -s -X POST http://localhost:8100/query/topology | python3 -m json.tool | head -20
```

### Phase 2–4 can be tested with mock data

The frontend hook fetches from `/query/topology` which proxies to the graph-query-api (or the deployed container). The mock backend returns static topology, so the full graph viewer works without Azure credentials.

---

## 9. API Proxy Configuration

### Vite Dev Server (local development)

The existing `vite.config.ts` proxies 4 paths to port 8000 (`/api/alert`, `/api/logs`, `/api`, `/health`). Add a `/query` entry proxying to the graph-query-api on port 8100:

**File:** `frontend/vite.config.ts` (modify the `server.proxy` block)

```typescript
server: {
  proxy: {
    '/api/alert': { target: 'http://localhost:8000', /* existing SSE config */ },
    '/api/logs':  { target: 'http://localhost:8000', /* existing SSE config */ },
    '/api':       'http://localhost:8000',
    '/health':    'http://localhost:8000',
    '/query':     'http://localhost:8100',  // ← ADD THIS (graph-query-api)
  },
},
```

> **Order matters:** `/api/alert` and `/api/logs` must appear before the catch-all `/api` entry. Place `/query` at the end.

### Production nginx (Container App)

The root `nginx.conf` already routes `/query/` → port 8100 — no change needed.

`frontend/nginx.conf.template` is **out of sync** — it is missing the `/query/` location block that the root `nginx.conf` has. However, this is a **legacy artifact**: the template is used by `frontend/Dockerfile` (per-service deploy), which ARCHITECTURE.md marks as "Legacy — per-service, unused in unified deploy." The production unified container uses the root `nginx.conf`, which already routes `/query/` correctly. Fixing the template for consistency is optional — the graph viewer works in both local dev (Vite proxy) and production (root `nginx.conf`) without it.

---

## 10. Future Enhancements (Out of Scope for V6)

- **Live telemetry overlay**: Color nodes by health status (green/yellow/red) based on real-time LinkTelemetry data
- **Blast radius highlighting**: When an investigation runs, highlight affected nodes/edges on the graph
- **Path visualization**: Click two nodes → highlight shortest path between them
- **Subgraph expansion**: Click a collapsed cluster to expand/reveal connected nodes
- **Graph editing**: Add/remove nodes and edges via the UI (demo scenario builder)
- **3D mode**: Switch to `react-force-graph-3d` for a more immersive view
- **Layout presets**: Save/load named graph layouts (force-directed, hierarchical, radial)
