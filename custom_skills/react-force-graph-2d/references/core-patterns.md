# Core Patterns

Full component implementations for `react-force-graph-2d` in a dark-themed React application with Tailwind CSS and Framer Motion.

---

## GraphCanvas — ForceGraph2D Wrapper

The canvas wrapper uses `forwardRef` to expose an imperative `zoomToFit()` handle. It owns no state — all callbacks and data flow down from the parent.

### Type Wiring

The library's generic types must be extended with your domain node/edge interfaces:

```typescript
import ForceGraph2D, { ForceGraphMethods, NodeObject, LinkObject } from 'react-force-graph-2d';
import type { TopologyNode, TopologyEdge } from '../../hooks/useTopology';

// Extend library generics with your domain types
type GNode = NodeObject<TopologyNode>;
type GLink = LinkObject<TopologyNode, TopologyEdge>;
```

`GNode` merges `TopologyNode` fields (`id`, `label`, `properties`) with the library's internal fields (`x`, `y`, `vx`, `vy`, `fx`, `fy`, `__indexColor`). `GLink` does the same for edges, adding the critical `source`/`target` mutation (string → object after the graph processes the data).

### Full Implementation

```tsx
import { useRef, useCallback, useEffect, forwardRef, useImperativeHandle } from 'react';
import ForceGraph2D, { ForceGraphMethods, NodeObject, LinkObject } from 'react-force-graph-2d';
import type { TopologyNode, TopologyEdge } from '../../hooks/useTopology';
import { NODE_COLORS, NODE_SIZES } from './graphConstants';

type GNode = NodeObject<TopologyNode>;
type GLink = LinkObject<TopologyNode, TopologyEdge>;

export interface GraphCanvasHandle {
  zoomToFit: () => void;
}

interface GraphCanvasProps {
  nodes: TopologyNode[];
  edges: TopologyEdge[];
  width: number;
  height: number;
  nodeDisplayField: Record<string, string>;
  nodeColorOverride: Record<string, string>;
  onNodeHover: (node: TopologyNode | null) => void;
  onLinkHover: (edge: TopologyEdge | null) => void;
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
    const fgRef = useRef<ForceGraphMethods<GNode, GLink> | undefined>(undefined);

    useImperativeHandle(ref, () => ({
      zoomToFit: () => fgRef.current?.zoomToFit(400, 40),
    }), []);

    // Auto-fit on data change
    useEffect(() => {
      if (fgRef.current && nodes.length > 0) {
        setTimeout(() => fgRef.current?.zoomToFit(400, 40), 500);
      }
    }, [nodes.length]);

    const getNodeColor = useCallback(
      (node: GNode) =>
        nodeColorOverride[node.label] ?? NODE_COLORS[node.label] ?? '#6B7280',
      [nodeColorOverride],
    );

    // Custom node rendering (colored circle + label)
    const nodeCanvasObject = useCallback(
      (node: GNode, ctx: CanvasRenderingContext2D, globalScale: number) => {
        const size = NODE_SIZES[node.label] ?? 6;
        const color = getNodeColor(node);

        ctx.beginPath();
        ctx.arc(node.x!, node.y!, size, 0, 2 * Math.PI);
        ctx.fillStyle = color;
        ctx.fill();
        ctx.strokeStyle = 'rgba(255,255,255,0.15)';
        ctx.lineWidth = 0.5;
        ctx.stroke();

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

    // Edge label at midpoint
    const linkCanvasObjectMode = () => 'after' as const;
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

    const handleNodeDoubleClick = useCallback((node: GNode) => {
      fgRef.current?.centerAt(node.x, node.y, 600);
      fgRef.current?.zoom(4, 600);
    }, []);

    // Hover wrappers — library passes (obj, prevObj), we forward only obj
    const handleNodeHoverInternal = useCallback(
      (node: GNode | null) => onNodeHover(node as TopologyNode | null),
      [onNodeHover],
    );
    const handleLinkHoverInternal = useCallback(
      (link: GLink | null) => onLinkHover(link as TopologyEdge | null),
      [onLinkHover],
    );

    return (
      <ForceGraph2D
        ref={fgRef}
        width={width}
        height={height}
        graphData={{ nodes: nodes as GNode[], links: edges as GLink[] }}
        backgroundColor="transparent"
        nodeCanvasObject={nodeCanvasObject}
        nodeCanvasObjectMode={() => 'replace'}
        nodeId="id"
        linkSource="source"
        linkTarget="target"
        linkColor={() => 'rgba(255,255,255,0.12)'}
        linkWidth={1.5}
        linkDirectionalArrowLength={4}
        linkDirectionalArrowRelPos={0.9}
        linkDirectionalArrowColor={() => 'rgba(255,255,255,0.2)'}
        linkCanvasObjectMode={linkCanvasObjectMode}
        linkCanvasObject={linkCanvasObject}
        onNodeHover={handleNodeHoverInternal}
        onLinkHover={handleLinkHoverInternal}
        onNodeRightClick={onNodeRightClick as (node: GNode, event: MouseEvent) => void}
        onNodeClick={handleNodeDoubleClick}
        onBackgroundClick={onBackgroundClick}
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

---

## GraphTooltip — Hover Overlay

A `position: fixed` overlay that tracks mouse position. Uses `AnimatePresence` for smooth entry/exit. **Must be rendered above the canvas** (in the parent, not inside `GraphCanvas`).

```tsx
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
        <span className="h-2 w-2 rounded-full"
              style={{ backgroundColor: NODE_COLORS[node.label] }} />
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
      <div className="text-[11px] text-text-muted mb-1">{srcId} → {tgtId}</div>
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

### Tooltip Mouse Tracking

The library's `onNodeHover` callback does **not** include the mouse event in its signature — it only passes `(node, prevNode)`. Track mouse position globally via a `mousemove` listener in the parent:

```typescript
const mousePos = useRef({ x: 0, y: 0 });

useEffect(() => {
  const handler = (e: MouseEvent) => {
    mousePos.current = { x: e.clientX, y: e.clientY };
  };
  window.addEventListener('mousemove', handler);
  return () => window.removeEventListener('mousemove', handler);
}, []);

const handleNodeHover = useCallback((node: TopologyNode | null) => {
  if (node) {
    setTooltip({ x: mousePos.current.x, y: mousePos.current.y, node });
  } else {
    setTooltip(null);
  }
}, []);
```

---

## GraphContextMenu — Right-Click Node Menu

A styled context menu for per-node-type customization:

1. **Display field selector** — choose which property to show as the node label
2. **Color picker** — change the color for that node type (affects all nodes of that label)

```tsx
import { motion } from 'framer-motion';
import type { TopologyNode } from '../../hooks/useTopology';

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

export function GraphContextMenu({
  menu, onClose, onSetDisplayField, onSetColor
}: GraphContextMenuProps) {
  if (!menu) return null;
  const propertyKeys = ['id', ...Object.keys(menu.node.properties)];

  return (
    <>
      {/* Invisible backdrop to dismiss on outside click */}
      <div className="fixed inset-0 z-40"
           onClick={onClose}
           onContextMenu={(e) => { e.preventDefault(); onClose(); }} />

      <motion.div
        className="fixed z-50 bg-neutral-bg3 border border-white/15 rounded-lg
                   shadow-xl py-1 min-w-[180px]"
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
          <span className="text-[10px] uppercase tracking-wider text-text-muted">
            Display Field
          </span>
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
                className="h-4 w-4 rounded-full border border-white/20
                           hover:scale-125 transition-transform"
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

---

## GraphToolbar — Controls Bar

Compact toolbar with search, label filter chips, counts, and action buttons:

```tsx
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
      <span className="text-xs font-semibold text-text-primary whitespace-nowrap">
        ◆ Network Topology
      </span>

      {/* Label filter chips — colored dots with label text */}
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
              <span className="h-2 w-2 rounded-full shrink-0"
                    style={{ backgroundColor: NODE_COLORS[label] ?? '#6B7280' }} />
              {label}
            </button>
          );
        })}
      </div>

      <div className="flex-1" />

      {/* Search input with expanding width on focus */}
      <input
        type="text"
        value={searchQuery}
        onChange={(e) => onSearchChange(e.target.value)}
        placeholder="Search nodes..."
        className="bg-white/5 border border-white/10 rounded px-2 py-0.5
                   text-[11px] text-text-secondary placeholder:text-text-muted
                   w-32 focus:w-44 transition-all focus:outline-none focus:border-white/25"
      />

      {meta && (
        <span className="text-[10px] text-text-muted whitespace-nowrap">
          {meta.node_count}N · {meta.edge_count}E
        </span>
      )}

      <button onClick={onZoomToFit}
              className="text-text-muted hover:text-text-primary text-xs px-1"
              title="Fit to view">⤢</button>

      <button onClick={onRefresh}
              className={`text-text-muted hover:text-text-primary text-xs px-1
                         ${loading ? 'animate-spin' : ''}`}
              title="Refresh">⟳</button>
    </div>
  );
}
```

---

## GraphTopologyViewer — Orchestrating Container

Composes all sub-components. Manages tooltip, context menu, filtering, and user customization state. Persists display field and color overrides to `localStorage`.

```tsx
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

  // ── Mouse tracking for tooltips ──
  const mousePos = useRef({ x: 0, y: 0 });
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      mousePos.current = { x: e.clientX, y: e.clientY };
    };
    window.addEventListener('mousemove', handler);
    return () => window.removeEventListener('mousemove', handler);
  }, []);

  // ── Tooltip state ──
  const [tooltip, setTooltip] = useState<{
    x: number; y: number;
    node?: TopologyNode; edge?: TopologyEdge;
  } | null>(null);

  const handleNodeHover = useCallback((node: TopologyNode | null) => {
    if (node) {
      setTooltip({ x: mousePos.current.x, y: mousePos.current.y, node, edge: undefined });
    } else {
      setTooltip(null);
    }
  }, []);

  const handleLinkHover = useCallback((edge: TopologyEdge | null) => {
    if (edge) {
      setTooltip({ x: mousePos.current.x, y: mousePos.current.y, edge, node: undefined });
    } else {
      setTooltip(null);
    }
  }, []);

  // ── Context menu state ──
  const [contextMenu, setContextMenu] = useState<{
    x: number; y: number; node: TopologyNode;
  } | null>(null);

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

  useEffect(() => {
    localStorage.setItem('graph-display-fields', JSON.stringify(nodeDisplayField));
  }, [nodeDisplayField]);
  useEffect(() => {
    localStorage.setItem('graph-colors', JSON.stringify(nodeColorOverride));
  }, [nodeColorOverride]);

  // ── Filtering ──
  const [activeLabels, setActiveLabels] = useState<string[]>([]);
  const [searchQuery, setSearchQuery] = useState('');

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

---

## useTopology — Data Fetching Hook

Fetches graph topology from the backend with abort controller support for cancellation:

```typescript
import { useState, useEffect, useCallback, useRef } from 'react';

export interface TopologyNode {
  id: string;
  label: string;
  properties: Record<string, unknown>;
  x?: number;
  y?: number;
  fx?: number;
  fy?: number;
}

export interface TopologyEdge {
  id: string;
  source: string | TopologyNode;
  target: string | TopologyNode;
  label: string;
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

  useEffect(() => {
    fetchTopology();
  }, [fetchTopology]);

  return { data, loading, error, refetch: fetchTopology };
}
```

---

## MetricsBar Integration with react-resizable-panels

Using `ResizeObserver` to track panel dimensions and pass them to the graph:

```tsx
import { useRef, useState, useEffect } from 'react';
import { Group as PanelGroup, Panel, Separator as PanelResizeHandle } from 'react-resizable-panels';
import { GraphTopologyViewer } from './GraphTopologyViewer';
import { LogStream } from './LogStream';

export function MetricsBar() {
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

  return (
    <div className="h-full px-6 py-3">
      <PanelGroup className="h-full">
        <Panel defaultSize={64} minSize={30}>
          <div ref={graphPanelRef} className="h-full px-1">
            <GraphTopologyViewer width={graphSize.width} height={graphSize.height} />
          </div>
        </Panel>
        <PanelResizeHandle className="metrics-resize-handle" />
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
