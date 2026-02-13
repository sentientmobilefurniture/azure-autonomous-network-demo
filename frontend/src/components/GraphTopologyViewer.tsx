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

  // Track mouse position for tooltip positioning (library hover callbacks don't include events)
  const mousePos = useRef({ x: 0, y: 0 });
  useEffect(() => {
    const handler = (e: MouseEvent) => { mousePos.current = { x: e.clientX, y: e.clientY }; };
    window.addEventListener('mousemove', handler);
    return () => window.removeEventListener('mousemove', handler);
  }, []);

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
