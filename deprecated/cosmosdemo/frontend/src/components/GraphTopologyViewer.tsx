import { useState, useCallback, useRef, useEffect } from 'react';
import { useTopology, TopologyNode, TopologyEdge } from '../hooks/useTopology';
import { GraphCanvas, GraphCanvasHandle } from './graph/GraphCanvas';
import { GraphToolbar } from './graph/GraphToolbar';
import { GraphTooltip } from './graph/GraphTooltip';
import { GraphContextMenu } from './graph/GraphContextMenu';
import { usePausableSimulation } from '../hooks/usePausableSimulation';
import { useTooltipTracking } from '../hooks/useTooltipTracking';
import { useScenarioContext } from '../context/ScenarioContext';

interface GraphTopologyViewerProps {
  width: number;
  height: number;
}

export function GraphTopologyViewer({ width, height }: GraphTopologyViewerProps) {
  const { data, loading, error, refetch } = useTopology();
  const { activeScenario } = useScenarioContext();
  const canvasRef = useRef<GraphCanvasHandle>(null);
  const storagePrefix = activeScenario ?? '__custom__';

  // ── Graph pause/freeze state ──

  const { isPaused, handleMouseEnter, handleMouseLeave, handleTogglePause, resetPause } =
    usePausableSimulation(canvasRef);

  // ── Tooltip + context menu state (owned here, not in GraphCanvas) ──

  const { tooltip, handleNodeHover, handleLinkHover } =
    useTooltipTracking<TopologyNode, TopologyEdge>();
  const [contextMenu, setContextMenu] = useState<{
    x: number; y: number; node: TopologyNode;
  } | null>(null);

  const handleNodeRightClick = useCallback((node: TopologyNode, event: MouseEvent) => {
    event.preventDefault();
    setContextMenu({ x: event.clientX, y: event.clientY, node });
  }, []);

  // ── User customization (persisted to localStorage) ──

  const [nodeDisplayField, setNodeDisplayField] = useState<Record<string, string>>(() => {
    try {
      const stored = localStorage.getItem(`graph-display-fields:${storagePrefix}`);
      return stored ? JSON.parse(stored) : {};
    } catch { return {}; }
  });
  const [nodeColorOverride, setNodeColorOverride] = useState<Record<string, string>>(() => {
    try {
      const stored = localStorage.getItem(`graph-colors:${storagePrefix}`);
      return stored ? JSON.parse(stored) : {};
    } catch { return {}; }
  });

  // Label filtering
  const [activeLabels, setActiveLabels] = useState<string[]>([]);
  const [searchQuery, setSearchQuery] = useState('');

  // Persist customization
  useEffect(() => {
    localStorage.setItem(`graph-display-fields:${storagePrefix}`, JSON.stringify(nodeDisplayField));
  }, [nodeDisplayField, storagePrefix]);
  useEffect(() => {
    localStorage.setItem(`graph-colors:${storagePrefix}`, JSON.stringify(nodeColorOverride));
  }, [nodeColorOverride, storagePrefix]);

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
        onRefresh={() => { refetch(); resetPause(); }}
        onZoomToFit={() => canvasRef.current?.zoomToFit()}
        isPaused={isPaused}
        onTogglePause={handleTogglePause}
        nodeColorOverride={nodeColorOverride}
        onSetColor={(label, color) =>
          setNodeColorOverride((prev) => ({ ...prev, [label]: color }))
        }
      />

      {error && (
        <div className="text-xs text-status-error px-3 py-1">{error}</div>
      )}

      {loading && data.nodes.length === 0 && (
        <div className="flex-1 flex items-center justify-center">
          <span className="text-xs text-text-muted animate-pulse">Loading topology…</span>
        </div>
      )}

      {!loading && !error && data.nodes.length === 0 && (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center space-y-2">
            <p className="text-sm text-text-muted">No graph data available</p>
            <p className="text-xs text-text-muted/60">
              Upload scenario data or check the active scenario configuration.
            </p>
          </div>
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
      />
    </div>
  );
}
