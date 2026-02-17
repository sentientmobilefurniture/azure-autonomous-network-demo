---
name: react-force-graph-2d
description: Build interactive force-directed graph visualizations in React using react-force-graph-2d with canvas rendering, custom node/edge drawing, tooltips, context menus, and resizable panel integration. Use when creating network topology viewers, knowledge graphs, or any node-edge visualization in a dark-themed dashboard.
---

# react-force-graph-2d — Interactive Graph Visualization (TypeScript)

A production-tested pattern for embedding **interactive force-directed graphs** in React applications using **react-force-graph-2d**. Canvas-based, performant for small-to-medium graphs (~50–500 nodes), with custom node rendering, hover tooltips, right-click context menus, and full dark-theme integration.

## Stack

| Package | Version | Purpose |
|---------|---------|---------|
| `react-force-graph-2d` | ^1.29.x | Canvas-based force-directed graph renderer |
| `react` | ^18.x | UI framework |
| `framer-motion` | ^11.x | Tooltip/menu animations |
| `react-resizable-panels` | ^4.x | Panel layout with dynamic graph sizing |
| `tailwindcss` | ^3.x | Styling (dark theme) |
| `typescript` | ^5.x | Type safety |

## Quick Start

```bash
npm install react-force-graph-2d
```

No additional type packages needed — `react-force-graph-2d` ships its own TypeScript declarations via `force-graph` (its underlying engine). The key generic types are `NodeObject<N>` and `LinkObject<N, L>` for extending the base node/link data with your domain types.

## Component Architecture

```
GraphTopologyViewer.tsx          ← Orchestrator (state, filtering, localStorage)
├── useTopology.ts               ← Data fetching hook (POST → backend)
├── GraphCanvas.tsx              ← react-force-graph-2d wrapper (forwardRef)
├── GraphToolbar.tsx             ← Search, label chips, zoom/refresh controls
├── GraphTooltip.tsx             ← Hover tooltip (Framer Motion overlay)
├── GraphContextMenu.tsx         ← Right-click node customization menu
└── graphConstants.ts            ← Node colors, sizes per label type
```

### State Ownership

State lives in the **orchestrating parent** (`GraphTopologyViewer`), not in the canvas wrapper. This is critical because:

1. **Tooltip and context menu** render as HTML overlays *above* the `<canvas>` element — they cannot be rendered inside the canvas component.
2. **User customizations** (display fields, color overrides) need to flow down as props and persist to `localStorage`.
3. **Filtering** (by label, by search query) happens on the data before passing to the canvas.

```
GraphTopologyViewer (state owner)
  │
  ├─ tooltip state ──────────────→ GraphTooltip (rendered above canvas)
  ├─ contextMenu state ──────────→ GraphContextMenu (rendered above canvas)
  ├─ nodeDisplayField state ─────→ GraphCanvas (props)
  ├─ nodeColorOverride state ────→ GraphCanvas (props)
  ├─ filteredNodes / filteredEdges → GraphCanvas (props)
  └─ canvasRef (imperative) ←────── GraphCanvas (forwardRef)
```

## Data Shape

### Types

```typescript
export interface TopologyNode {
  id: string;
  label: string;                    // vertex type ("CoreRouter", "Host", etc.)
  properties: Record<string, unknown>;
  // Force-graph mutates these — must be included:
  x?: number;
  y?: number;
  fx?: number;                      // pinned x (set when user drags)
  fy?: number;                      // pinned y
}

export interface TopologyEdge {
  id: string;
  source: string | TopologyNode;    // string before graph processes; object after
  target: string | TopologyNode;
  label: string;                    // edge type ("connects_to", "depends_on")
  properties: Record<string, unknown>;
}

export interface TopologyMeta {
  node_count: number;
  edge_count: number;
  query_time_ms: number;
  labels: string[];                 // sorted unique node labels
}
```

### API Response

```json
{
  "nodes": [{ "id": "...", "label": "...", "properties": {...} }],
  "edges": [{ "id": "...", "source": "...", "target": "...", "label": "...", "properties": {...} }],
  "meta": { "node_count": 50, "edge_count": 77, "query_time_ms": 340, "labels": ["CoreRouter", "Service"] },
  "error": null
}
```

## Core Rendering

### The `<ForceGraph2D>` Component

```tsx
<ForceGraph2D
  ref={fgRef}
  width={width}
  height={height}
  graphData={{ nodes: nodes as GNode[], links: edges as GLink[] }}
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
  linkCanvasObjectMode={() => 'after'}
  linkCanvasObject={linkCanvasObject}
  // Interaction
  onNodeHover={handleNodeHover}
  onLinkHover={handleLinkHover}
  onNodeRightClick={onNodeRightClick}
  onNodeClick={handleNodeDoubleClick}
  onBackgroundClick={onBackgroundClick}
  // Physics
  d3AlphaDecay={0.02}
  d3VelocityDecay={0.3}
  cooldownTime={3000}
  enableNodeDrag={true}
  enableZoomInteraction={true}
  enablePanInteraction={true}
/>
```

### Custom Node Rendering (Canvas API)

Nodes are drawn as colored circles with text labels below. The `nodeCanvasObjectMode: 'replace'` tells the library to skip its default rendering entirely.

```typescript
const nodeCanvasObject = useCallback(
  (node: GNode, ctx: CanvasRenderingContext2D, globalScale: number) => {
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

    // Label below node
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
```

### Custom Edge Label Rendering

Edge labels are drawn at the midpoint of each link. Use `linkCanvasObjectMode: 'after'` so the line is drawn first by the library, then we add the label on top.

```typescript
const linkCanvasObject = useCallback(
  (link: GLink, ctx: CanvasRenderingContext2D, globalScale: number) => {
    const src = link.source as GNode;
    const tgt = link.target as GNode;
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
```

## Imperative API (ForceGraphMethods)

Access the graph instance via a ref for programmatic control:

```typescript
const fgRef = useRef<ForceGraphMethods<GNode, GLink> | undefined>(undefined);

// Zoom to fit all visible nodes
fgRef.current?.zoomToFit(400, 40);  // (duration_ms, padding_px)

// Center on a specific node
fgRef.current?.centerAt(node.x, node.y, 600);

// Set zoom level
fgRef.current?.zoom(4, 600);  // (level, duration_ms)
```

Expose via `forwardRef` + `useImperativeHandle` so parent components can trigger zoom-to-fit from toolbar buttons:

```typescript
export const GraphCanvas = forwardRef<GraphCanvasHandle, GraphCanvasProps>(
  function GraphCanvas(props, ref) {
    const fgRef = useRef<ForceGraphMethods<GNode, GLink> | undefined>(undefined);

    useImperativeHandle(ref, () => ({
      zoomToFit: () => fgRef.current?.zoomToFit(400, 40),
    }), []);

    // ...
  }
);
```

## Node Color + Size Constants

Define per-label styling as `Record<string, string | number>` maps. Unknown labels fall back to grey (#6B7280) and size 6.

```typescript
export const NODE_COLORS: Record<string, string> = {
  CoreRouter:     '#38BDF8',  // sky-400
  AggSwitch:      '#FB923C',  // orange-400
  BaseStation:    '#A78BFA',  // violet-400
  TransportLink:  '#3B82F6',  // blue-500
  MPLSPath:       '#C084FC',  // purple-400
  Service:        '#CA8A04',  // yellow-600
  SLAPolicy:      '#FB7185',  // rose-400
  BGPSession:     '#F472B6',  // pink-400
};

export const NODE_SIZES: Record<string, number> = {
  CoreRouter:     10,   // largest — central hub
  AggSwitch:      7,
  BaseStation:    5,
  TransportLink:  7,
  MPLSPath:       6,
  Service:        8,    // important business context
  SLAPolicy:      6,
  BGPSession:     5,
};
```

For server-driven styling (multi-scenario), replace these constants with values fetched from an API endpoint and stored in React context or a store.

## Resizable Panel Integration

The graph must resize dynamically when the user drags a panel divider. Use `ResizeObserver` on the panel container to track dimensions:

```typescript
const graphPanelRef = useRef<HTMLDivElement>(null);
const [graphSize, setGraphSize] = useState({ width: 800, height: 300 });

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

// Pass to canvas:
<GraphCanvas width={graphSize.width} height={graphSize.height} ... />
```

## Interaction Summary

| Action | Behavior |
|--------|----------|
| **Hover node** | Show tooltip with all node properties |
| **Hover edge** | Show tooltip with edge label + endpoints + properties |
| **Drag node** | Pin node to new position (sets `fx`/`fy`) |
| **Click background** | Dismiss context menu |
| **Right-click node** | Open context menu (display field, color picker) |
| **Scroll wheel** | Zoom in/out |
| **Drag background** | Pan viewport |
| **Click node** | Center + zoom to node |

## Client-Side Filtering

Filter nodes by label type and search query *before* passing to the canvas. Edges whose endpoints are filtered out are also removed:

```typescript
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
```

## Related Files

- [Core Patterns](./references/core-patterns.md) — Full component implementations, type wiring, hover/tooltip patterns
- [Backend Integration](./references/backend-integration.md) — FastAPI topology endpoint, Pydantic models, Gremlin queries, mock backend
- [Gotchas & Considerations](./references/gotchas.md) — TypeScript generics, source/target mutation, performance, canvas vs DOM
- [Acceptance Criteria](./references/acceptance-criteria.md) — Correct/incorrect patterns for validation
