# Acceptance Criteria

Correct and incorrect patterns for validating `react-force-graph-2d` implementations. Use this as a checklist when reviewing or generating code.

---

## Imports

### ✅ Correct

```typescript
import ForceGraph2D, {
  ForceGraphMethods,
  NodeObject,
  LinkObject,
} from 'react-force-graph-2d';
```

### ❌ Incorrect

```typescript
// Wrong package — this is the 3D WebGL variant
import ForceGraph3D from 'react-force-graph-3d';

// Wrong — importing from the underlying engine directly
import { ForceGraphMethods } from 'force-graph';

// Wrong — destructured default export
import { ForceGraph2D } from 'react-force-graph-2d';
// ForceGraph2D is the DEFAULT export, not a named export
```

---

## Type Generics

### ✅ Correct

```typescript
type GNode = NodeObject<TopologyNode>;
type GLink = LinkObject<TopologyNode, TopologyEdge>;

const fgRef = useRef<ForceGraphMethods<GNode, GLink> | undefined>(undefined);
```

### ❌ Incorrect

```typescript
// Missing domain type — loses custom fields
type GNode = NodeObject;

// Wrong generic order — LinkObject is <NodeType, LinkType>
type GLink = LinkObject<TopologyEdge, TopologyNode>;

// null instead of undefined — library expects undefined
const fgRef = useRef<ForceGraphMethods<GNode, GLink>>(null);

// Missing library wrapper types — can't access x, y, vx, vy
type GNode = TopologyNode;
```

---

## Component Architecture

### ✅ Correct

```
GraphTopologyViewer (state owner)
├── GraphToolbar (stateless)
├── GraphCanvas (forwardRef, stateless)
├── GraphTooltip (stateless, position: fixed)
└── GraphContextMenu (stateless, position: fixed)
```

- Tooltip/context menu state lives in the parent
- `GraphCanvas` receives only props and exposes `zoomToFit()` via `useImperativeHandle`
- HTML overlays are siblings of canvas, not children

### ❌ Incorrect

```
// Wrong — tooltip state inside canvas wrapper
GraphCanvas
├── ForceGraph2D
└── GraphTooltip  // Can't render HTML inside <canvas>!

// Wrong — toolbar owns filtering state
GraphToolbar (owns activeLabels state)
└── passes filtered data up via callback  // Prop drilling in wrong direction
```

---

## Canvas Rendering

### ✅ Correct — Node

```typescript
nodeCanvasObjectMode={() => 'replace'}
nodeCanvasObject={(node: GNode, ctx: CanvasRenderingContext2D, globalScale: number) => {
  const size = 6;
  ctx.beginPath();
  ctx.arc(node.x!, node.y!, size, 0, 2 * Math.PI);
  ctx.fillStyle = '#38BDF8';
  ctx.fill();

  const fontSize = Math.max(10 / globalScale, 3);
  ctx.font = `${fontSize}px 'Segoe UI', sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  ctx.fillStyle = '#E4E4E7';
  ctx.fillText(node.id, node.x!, node.y! + size + 2);
}}
```

### ❌ Incorrect — Node

```typescript
// Wrong mode — 'after' draws ON TOP of the default circle
nodeCanvasObjectMode={() => 'after'}

// Wrong — using React JSX in canvas callback
nodeCanvasObject={(node) => (
  <div className="node-label">{node.id}</div>  // This is Canvas2D, not DOM!
)}

// Wrong — not using globalScale for font sizing
ctx.font = '12px sans-serif';  // Huge when zoomed in, tiny when zoomed out

// Wrong — forgetting non-null assertion on coordinates
ctx.arc(node.x, node.y, size, 0, 2 * Math.PI);
// Should be node.x! and node.y! — coordinates are optional in the type
```

### ✅ Correct — Link

```typescript
linkCanvasObjectMode={() => 'after'}
linkCanvasObject={(link: GLink, ctx, globalScale) => {
  const src = link.source as GNode;  // source is mutated to object
  const tgt = link.target as GNode;
  if (!src.x || !tgt.x) return;

  const midX = (src.x + tgt.x) / 2;
  const midY = (src.y! + tgt.y!) / 2;
  ctx.fillText(link.label, midX, midY);
}}
```

### ❌ Incorrect — Link

```typescript
// Wrong — accessing source as string after graph processes data
linkCanvasObject={(link) => {
  const srcId = link.source;  // This is now an OBJECT, not a string!
  const src = nodes.find(n => n.id === srcId);  // Fails — srcId is an object
}}

// Wrong — 'replace' mode removes the library-drawn line
linkCanvasObjectMode={() => 'replace'}
```

---

## Hover & Tooltip

### ✅ Correct

```typescript
// Track mouse position separately
const mousePos = useRef({ x: 0, y: 0 });
useEffect(() => {
  const handler = (e: MouseEvent) => {
    mousePos.current = { x: e.clientX, y: e.clientY };
  };
  window.addEventListener('mousemove', handler);
  return () => window.removeEventListener('mousemove', handler);
}, []);

// Hover callback — no mouse event available
onNodeHover={(node: GNode | null) => {
  setTooltip(node
    ? { x: mousePos.current.x, y: mousePos.current.y, node }
    : null
  );
}}
```

### ❌ Incorrect

```typescript
// Wrong — onNodeHover doesn't receive MouseEvent
onNodeHover={(node, event: MouseEvent) => {
  setTooltip({ x: event.clientX, y: event.clientY, node });
}}

// Wrong — trying to get position from the node's canvas coordinates
onNodeHover={(node) => {
  setTooltip({ x: node.x, y: node.y, node });
  // node.x/y are WORLD coordinates, not screen pixels!
}}
```

---

## Edge Filtering

### ✅ Correct

```typescript
const filteredNodes = data.nodes.filter(n => activeLabels.includes(n.label));
const nodeIdSet = new Set(filteredNodes.map(n => n.id));
const filteredEdges = data.edges.filter(e => {
  const srcId = typeof e.source === 'string' ? e.source : e.source.id;
  const tgtId = typeof e.target === 'string' ? e.target : e.target.id;
  return nodeIdSet.has(srcId) && nodeIdSet.has(tgtId);
});
```

### ❌ Incorrect

```typescript
// Wrong — not filtering edges when filtering nodes
graphData={{ nodes: filteredNodes, links: data.edges }}
// Edges to hidden nodes cause errors or lines to (0,0)

// Wrong — not handling source/target mutation
const filteredEdges = data.edges.filter(e =>
  nodeIdSet.has(e.source) && nodeIdSet.has(e.target)
);
// e.source may be an object after first render, not a string
```

---

## Data Passing

### ✅ Correct

```typescript
<ForceGraph2D
  graphData={{ nodes: filteredNodes as GNode[], links: filteredEdges as GLink[] }}
  nodeId="id"
  linkSource="source"
  linkTarget="target"
/>
```

### ❌ Incorrect

```typescript
// Wrong — missing nodeId/linkSource/linkTarget when using custom field names
<ForceGraph2D
  graphData={{ nodes, links: edges }}
  // Library defaults to 'id', 'source', 'target' — but be explicit

// Wrong — nodes and links as separate props
<ForceGraph2D
  nodes={nodes}    // No such prop
  links={edges}    // No such prop — must use graphData
/>
```

---

## Resizing

### ✅ Correct

```typescript
// ResizeObserver to track container dimensions
useEffect(() => {
  const el = ref.current;
  if (!el) return;
  const observer = new ResizeObserver(([entry]) => {
    setSize({
      width: entry.contentRect.width,
      height: entry.contentRect.height,
    });
  });
  observer.observe(el);
  return () => observer.disconnect();
}, []);

<ForceGraph2D width={size.width} height={size.height} />
```

### ❌ Incorrect

```typescript
// Wrong — no width/height props, graph uses window dimensions
<ForceGraph2D graphData={data} />
// This makes the graph take up the full window, ignoring panel layout

// Wrong — hardcoded dimensions
<ForceGraph2D width={800} height={600} />
// Doesn't respond to panel resizing

// Wrong — CSS dimensions on a wrapper without passing to ForceGraph2D
<div style={{ width: 800, height: 600 }}>
  <ForceGraph2D graphData={data} />  // Still uses window dimensions
</div>
```

---

## Imperative API

### ✅ Correct

```typescript
// Expose via forwardRef + useImperativeHandle
export const GraphCanvas = forwardRef<GraphCanvasHandle, Props>((props, ref) => {
  const fgRef = useRef<ForceGraphMethods<GNode, GLink> | undefined>(undefined);

  useImperativeHandle(ref, () => ({
    zoomToFit: () => fgRef.current?.zoomToFit(400, 40),
  }), []);

  return <ForceGraph2D ref={fgRef} ... />;
});
```

### ❌ Incorrect

```typescript
// Wrong — passing fgRef up via props instead of forwardRef
<GraphCanvas onRefReady={(ref) => setFgRef(ref)} />

// Wrong — calling imperative methods during render
function GraphCanvas() {
  const fgRef = useRef(...);
  fgRef.current?.zoomToFit(400);  // Called on every render!
  return <ForceGraph2D ref={fgRef} />;
}
```

---

## Dependencies Checklist

```json
{
  "react-force-graph-2d": "^1.29.1",
  "framer-motion": "^11.x",
  "react-resizable-panels": "^2.x"
}
```

- `react-force-graph-2d` requires `react` ≥ 16.8 (hooks)
- Types ship via the package itself (no separate `@types/` needed)
- The underlying `force-graph` engine is bundled — do not install it separately
