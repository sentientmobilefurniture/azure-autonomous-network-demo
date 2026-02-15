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

  // ── Graph pause/freeze state ──

  const [isPaused, setIsPaused] = useState(false);
  const [manualPause, setManualPause] = useState(false);
  const resumeTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleMouseEnter = useCallback(() => {
    if (resumeTimeoutRef.current) {
      clearTimeout(resumeTimeoutRef.current);
      resumeTimeoutRef.current = null;
    }
    canvasRef.current?.setFrozen(true);
    setIsPaused(true);
  }, []);

  const handleMouseLeave = useCallback(() => {
    // Don't auto-resume if manually paused
    if (manualPause) return;
    resumeTimeoutRef.current = setTimeout(() => {
      canvasRef.current?.setFrozen(false);
      setIsPaused(false);
      resumeTimeoutRef.current = null;
    }, 300);
  }, [manualPause]);

  const handleTogglePause = useCallback(() => {
    if (manualPause) {
      // Unpause
      setManualPause(false);
      canvasRef.current?.setFrozen(false);
      setIsPaused(false);
    } else {
      // Manual pause
      setManualPause(true);
      canvasRef.current?.setFrozen(true);
      setIsPaused(true);
    }
  }, [manualPause]);

  // Cleanup debounce timeout
  useEffect(() => {
    return () => {
      if (resumeTimeoutRef.current) clearTimeout(resumeTimeoutRef.current);
    };
  }, []);

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
        onRefresh={() => { refetch(); setManualPause(false); }}
        onZoomToFit={() => canvasRef.current?.zoomToFit()}
        isPaused={isPaused}
        onTogglePause={handleTogglePause}
        nodeColorOverride={nodeColorOverride}
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
          onMouseEnter={handleMouseEnter}
          onMouseLeave={handleMouseLeave}
        />

        {/* Paused indicator */}
        {isPaused && (
          <div className="absolute bottom-2 right-2 px-2 py-0.5 rounded-full
                         bg-white/10 backdrop-blur-sm text-text-muted text-[10px]
                         transition-opacity duration-100">
            ⏸ Paused
          </div>
        )}
      </div>

      {/* Overlays rendered outside GraphCanvas so they appear above the <canvas> */}
      <GraphTooltip tooltip={tooltip} nodeColorOverride={nodeColorOverride} />
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
