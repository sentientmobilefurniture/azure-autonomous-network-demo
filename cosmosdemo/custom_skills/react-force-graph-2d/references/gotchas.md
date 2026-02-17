# Gotchas & Pitfalls

Hard-won lessons from integrating `react-force-graph-2d` into a production TypeScript + React application. Every item here cost real debugging time.

---

## 1. TypeScript Generic Wiring

### The Problem

`react-force-graph-2d` exposes three core generics that must be threaded correctly:

```typescript
import ForceGraph2D, { ForceGraphMethods, NodeObject, LinkObject } from 'react-force-graph-2d';
```

If you define your domain types as `TopologyNode` and `TopologyEdge`, the correct generic wiring is:

```typescript
// ✅ Correct
type GNode = NodeObject<TopologyNode>;
type GLink = LinkObject<TopologyNode, TopologyEdge>;

const fgRef = useRef<ForceGraphMethods<GNode, GLink> | undefined>(undefined);
```

### Common Mistakes

```typescript
// ❌ Wrong — ForceGraphMethods ref initialized with null
const fgRef = useRef<ForceGraphMethods<GNode, GLink>>(null);
// The library expects `| undefined` — using null causes type errors

// ❌ Wrong — Missing domain type parameter
type GNode = NodeObject;  // Loses your custom fields
type GLink = LinkObject;  // source/target typed as raw NodeObject

// ❌ Wrong — Swapping generic order in LinkObject
type GLink = LinkObject<TopologyEdge, TopologyNode>;  // Args are <NodeType, LinkType>
```

---

## 2. source/target Mutation

### The Problem

This is the single most confusing behavior. When you pass edge data to `ForceGraph2D`:

```typescript
// What you pass in:
{ source: "router-1", target: "switch-1", label: "CONNECTS_TO" }

// What the library MUTATES it to (after first render):
{ source: { id: "router-1", x: 100, y: 200, ... }, target: { id: "switch-1", x: 50, y: 80, ... }, label: "CONNECTS_TO" }
```

The library **replaces** the `source` and `target` string fields with references to the full node objects. This is d3-force behavior, not a bug.

### Defensive Access

```typescript
// ✅ Always use defensive access
const srcId = typeof edge.source === 'string' ? edge.source : edge.source.id;
const tgtId = typeof edge.target === 'string' ? edge.target : edge.target.id;
```

This is critical in:
- `linkCanvasObject` (source/target will be objects)
- Filtering logic (source/target may be strings on first pass, objects on subsequent)
- Tooltip rendering for edges

---

## 3. Hover Callback Signature — No MouseEvent

### The Problem

```typescript
// ❌ This is NOT the callback signature
onNodeHover={(node: GNode, event: MouseEvent) => { ... }}

// ✅ This IS the callback signature
onNodeHover={(node: GNode | null, prevNode: GNode | null) => { ... }}
```

The `onNodeHover` and `onLinkHover` callbacks receive `(currentObj, previousObj)` — **no mouse event**. You cannot get cursor position from these callbacks.

### Workaround

Track mouse position globally with a `mousemove` listener:

```typescript
const mousePos = useRef({ x: 0, y: 0 });

useEffect(() => {
  const handler = (e: MouseEvent) => {
    mousePos.current = { x: e.clientX, y: e.clientY };
  };
  window.addEventListener('mousemove', handler);
  return () => window.removeEventListener('mousemove', handler);
}, []);

// In hover handler:
const handleNodeHover = (node: TopologyNode | null) => {
  setTooltip(node
    ? { x: mousePos.current.x, y: mousePos.current.y, node }
    : null
  );
};
```

> **Note**: `onNodeRightClick` _does_ receive a `MouseEvent` as the second argument. Only hover callbacks lack it.

---

## 4. nodeCanvasObjectMode: 'replace' vs 'after'

| Mode | Behavior | Use When |
|------|----------|----------|
| `'replace'` | Your canvas draw replaces the library's default circle | Custom node shapes, colored fills, labels below nodes |
| `'after'` | Your draw runs on top of the library's default | Adding text labels on top of default circles |
| `'before'` | Your draw runs behind the library's default | Background highlights |

For nodes, **always use `'replace'`** — the default circle is unstyled (solid color, no label).

For links, **use `'after'`** — let the library draw the line + arrow, then add your label text on top:

```typescript
// Node: full custom
nodeCanvasObjectMode={() => 'replace'}

// Link: label on top of library-drawn line
linkCanvasObjectMode={() => 'after'}
```

---

## 5. No Native Double-Click

### The Problem

`react-force-graph-2d` has `onNodeClick` but **no `onNodeDoubleClick`** event. Every click fires `onNodeClick`.

### Options

1. **Use single-click for navigation** (recommended — this is what the demo does):
   ```typescript
   onNodeClick={(node) => {
     fgRef.current?.centerAt(node.x, node.y, 600);
     fgRef.current?.zoom(4, 600);
   }}
   ```

2. **Implement double-click detection manually**:
   ```typescript
   const lastClick = useRef<{ id: string; time: number } | null>(null);

   const handleClick = (node: GNode) => {
     const now = Date.now();
     if (lastClick.current?.id === node.id && now - lastClick.current.time < 300) {
       // Double click
       handleDoubleClick(node);
       lastClick.current = null;
     } else {
       lastClick.current = { id: String(node.id), time: now };
     }
   };
   ```

---

## 6. Edge Filtering When Nodes Are Hidden

When filtering nodes by label or search query, you **must** also filter edges whose source or target is no longer visible:

```typescript
const filteredNodes = data.nodes.filter(n => activeLabels.includes(n.label));
const nodeIdSet = new Set(filteredNodes.map(n => n.id));

// ✅ Filter edges too — account for source/target mutation
const filteredEdges = data.edges.filter(e => {
  const srcId = typeof e.source === 'string' ? e.source : e.source.id;
  const tgtId = typeof e.target === 'string' ? e.target : e.target.id;
  return nodeIdSet.has(srcId) && nodeIdSet.has(tgtId);
});
```

If you forget this, the graph will throw errors or draw edges to invisible nodes at `(0, 0)`.

---

## 7. Canvas Rendering & globalScale

### Font Sizing

`globalScale` in `nodeCanvasObject` reflects the current zoom level. Use it to keep labels readable at all zoom levels:

```typescript
const fontSize = Math.max(10 / globalScale, 3);
ctx.font = `${fontSize}px 'Segoe UI', system-ui, sans-serif`;
```

Without `Math.max(..., 3)`, labels become unreadably small when zoomed out. Without dividing by `globalScale`, labels appear enormous when zoomed in.

### Node Size

Node radius should generally be in **world coordinates** (not screen pixels). A node drawn with `ctx.arc(x, y, 6, ...)` will appear to grow when you zoom in — this is usually the desired behavior for graph topology views.

---

## 8. localStorage Persistence Safety

Always wrap `JSON.parse` in a try-catch when reading persisted state:

```typescript
// ✅ Safe
const [nodeColorOverride, setNodeColorOverride] = useState<Record<string, string>>(() => {
  try {
    const stored = localStorage.getItem('graph-colors');
    return stored ? JSON.parse(stored) : {};
  } catch {
    return {};
  }
});
```

If the stored JSON is corrupted (partial write, quota exceeded), `JSON.parse` will throw and break your component's initial render.

---

## 9. ResizeObserver Cleanup

When using `ResizeObserver` to track container dimensions for the graph's `width`/`height` props:

```typescript
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
  return () => observer.disconnect();  // ← Don't forget this
}, []);
```

Missing `observer.disconnect()` causes memory leaks in SPAs where panels mount/unmount.

---

## 10. Performance Limits

| Node Count | Behavior |
|-----------|----------|
| < 200 | Smooth at 60fps |
| 200–500 | Acceptable, force simulation noticeable |
| 500–1000 | Degraded, consider disabling labels at low zoom |
| > 1000 | Use `nodeCanvasObjectMode` to simplify rendering or switch to WebGL (`react-force-graph-3d`) |

Tips for scaling:
- Set `d3AlphaDecay={0.02}` and `d3VelocityDecay={0.3}` to settle the simulation faster
- Use `cooldownTime={3000}` to stop simulation after 3 seconds
- Skip edge labels when `globalScale < 1`:
  ```typescript
  const linkCanvasObject = (link, ctx, globalScale) => {
    if (globalScale < 1) return; // Skip labels when zoomed out
    // ... draw label
  };
  ```

---

## 11. HTML Overlays vs Canvas

Components like tooltips and context menus **must be rendered as separate HTML elements** positioned with `position: fixed`. You **cannot** render React components inside the `<canvas>` element.

Architecture:
```
<div className="relative">
  <GraphCanvas />          ← canvas element
  <GraphTooltip />         ← position: fixed HTML overlay
  <GraphContextMenu />     ← position: fixed HTML overlay
</div>
```

This means tooltip/menu state must live in the **parent** component, not in `GraphCanvas`.

---

## 12. AbortController for Fetch

If the user triggers rapid refetches (e.g., toggling label filters), previous in-flight requests should be aborted:

```typescript
const abortRef = useRef<AbortController | null>(null);

const fetchTopology = async () => {
  abortRef.current?.abort();
  const ctrl = new AbortController();
  abortRef.current = ctrl;

  try {
    const res = await fetch('/query/topology', { signal: ctrl.signal, ... });
    // ...
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') return; // Ignore
    setError(err.message);
  }
};
```

Without this, stale responses can overwrite fresher data.
