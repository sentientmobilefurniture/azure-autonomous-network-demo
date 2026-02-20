import { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import { useTopology, TopologyNode, TopologyEdge } from '../hooks/useTopology';
import { GraphCanvas, GraphCanvasHandle } from './graph/GraphCanvas';
import { GraphHeaderBar } from './graph/GraphHeaderBar';
import { GraphToolbar } from './graph/GraphToolbar';
import { GraphEdgeToolbar } from './graph/GraphEdgeToolbar';
import { GraphTooltip } from './graph/GraphTooltip';
import { GraphContextMenu } from './graph/GraphContextMenu';
import { usePausableSimulation } from '../hooks/usePausableSimulation';
import { useTooltipTracking } from '../hooks/useTooltipTracking';
import { useScenario } from '../ScenarioContext';

interface GraphTopologyViewerProps {
  width: number;
  height: number;
}

export function GraphTopologyViewer({ width, height }: GraphTopologyViewerProps) {
  const SCENARIO = useScenario();
  const { data, loading, error, refetch } = useTopology();
  const storagePrefix = SCENARIO.name;
  const canvasRef = useRef<GraphCanvasHandle>(null);

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

  // ── Data version (bumped on fetch/refresh, not on filter toggles) ──

  const [dataVersion, setDataVersion] = useState(0);
  const prevNodeCountRef = useRef(data.nodes.length);
  useEffect(() => {
    // Only bump version when the raw (unfiltered) data actually changes
    if (data.nodes.length !== prevNodeCountRef.current) {
      prevNodeCountRef.current = data.nodes.length;
      setDataVersion((v) => v + 1);
    }
  }, [data.nodes.length]);

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

  // Bar visibility toggles
  const [showNodeBar, setShowNodeBar] = useState(true);
  const [showEdgeBar, setShowEdgeBar] = useState(true);

  // Edge label filtering
  const [activeEdgeLabels, setActiveEdgeLabels] = useState<string[]>([]);
  const [edgeColorOverride, setEdgeColorOverride] = useState<Record<string, string>>(() => {
    try {
      const stored = localStorage.getItem(`graph-edge-colors:${storagePrefix}`);
      return stored ? JSON.parse(stored) : {};
    } catch { return {}; }
  });

  // Text style controls (persisted to localStorage)
  const [labelStyle, setLabelStyle] = useState<{
    nodeFontSize: number | null;
    nodeColor: string | null;
    edgeFontSize: number | null;
    edgeColor: string | null;
  }>(() => {
    try {
      const stored = localStorage.getItem(`graph-label-style:${storagePrefix}`);
      return stored ? JSON.parse(stored) : { nodeFontSize: null, nodeColor: null, edgeFontSize: null, edgeColor: null };
    } catch { return { nodeFontSize: null, nodeColor: null, edgeFontSize: null, edgeColor: null }; }
  });

  // Persist customization
  useEffect(() => {
    localStorage.setItem(`graph-display-fields:${storagePrefix}`, JSON.stringify(nodeDisplayField));
  }, [nodeDisplayField, storagePrefix]);
  useEffect(() => {
    localStorage.setItem(`graph-colors:${storagePrefix}`, JSON.stringify(nodeColorOverride));
  }, [nodeColorOverride, storagePrefix]);
  useEffect(() => {
    localStorage.setItem(`graph-edge-colors:${storagePrefix}`, JSON.stringify(edgeColorOverride));
  }, [edgeColorOverride, storagePrefix]);
  useEffect(() => {
    localStorage.setItem(`graph-label-style:${storagePrefix}`, JSON.stringify(labelStyle));
  }, [labelStyle, storagePrefix]);

  // ── Derived edge labels ──

  const availableEdgeLabels = useMemo(
    () => [...new Set(data.edges.map((e) => e.label))].sort(),
    [data.edges],
  );

  // ── Node/edge filtering ──

  const filteredNodes = data.nodes.filter((n) => {
    if (activeLabels.length > 0 && !activeLabels.includes(n.label)) return false;
    return true;
  });
  const nodeIdSet = new Set(filteredNodes.map((n) => n.id));
  const filteredEdges = data.edges.filter((e) => {
    const srcId = typeof e.source === 'string' ? e.source : e.source.id;
    const tgtId = typeof e.target === 'string' ? e.target : e.target.id;
    if (!nodeIdSet.has(srcId) || !nodeIdSet.has(tgtId)) return false;
    // Edge label filter (empty = all shown)
    if (activeEdgeLabels.length > 0 && !activeEdgeLabels.includes(e.label)) return false;
    return true;
  });

  // Reserve toolbar height: header always shown + conditional node/edge bars
  const BAR_HEIGHT = 36;
  const TOOLBAR_HEIGHT = BAR_HEIGHT + (showNodeBar ? BAR_HEIGHT : 0) + (showEdgeBar ? BAR_HEIGHT : 0);

  return (
    <div className="glass-card h-full flex flex-col overflow-hidden">
      <GraphHeaderBar
        meta={data.meta}
        loading={loading}
        isPaused={isPaused}
        onTogglePause={handleTogglePause}
        onZoomToFit={() => canvasRef.current?.zoomToFit()}
        onRefresh={() => { refetch(); resetPause(); }}
        showNodeBar={showNodeBar}
        onToggleNodeBar={() => setShowNodeBar((v) => !v)}
        showEdgeBar={showEdgeBar}
        onToggleEdgeBar={() => setShowEdgeBar((v) => !v)}
      />

      {showNodeBar && (
        <GraphToolbar
          availableLabels={data.meta?.labels ?? []}
          activeLabels={activeLabels}
          onToggleLabel={(l) =>
            setActiveLabels((prev) =>
              prev.includes(l) ? prev.filter((x) => x !== l) : [...prev, l]
            )
          }
          visibleNodeCount={filteredNodes.length}
          totalNodeCount={data.nodes.length}
          nodeColorOverride={nodeColorOverride}
          onSetColor={(label, color) =>
            setNodeColorOverride((prev) => ({ ...prev, [label]: color }))
          }
          nodeLabelFontSize={labelStyle.nodeFontSize}
          onNodeLabelFontSizeChange={(s) => setLabelStyle((prev) => ({ ...prev, nodeFontSize: s }))}
          nodeLabelColor={labelStyle.nodeColor}
          onNodeLabelColorChange={(c) => setLabelStyle((prev) => ({ ...prev, nodeColor: c }))}
        />
      )}

      {showEdgeBar && (
        <GraphEdgeToolbar
          availableEdgeLabels={availableEdgeLabels}
          activeEdgeLabels={activeEdgeLabels}
          onToggleEdgeLabel={(l) =>
            setActiveEdgeLabels((prev) =>
              prev.includes(l) ? prev.filter((x) => x !== l) : [...prev, l]
            )
          }
          visibleEdgeCount={filteredEdges.length}
          totalEdgeCount={data.edges.length}
          edgeColorOverride={edgeColorOverride}
          onSetEdgeColor={(label, color) =>
            setEdgeColorOverride((prev) => ({ ...prev, [label]: color }))
          }
          edgeLabelFontSize={labelStyle.edgeFontSize}
          onEdgeLabelFontSizeChange={(s) => setLabelStyle((prev) => ({ ...prev, edgeFontSize: s }))}
          edgeLabelColor={labelStyle.edgeColor}
          onEdgeLabelColorChange={(c) => setLabelStyle((prev) => ({ ...prev, edgeColor: c }))}
        />
      )}

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
          dataVersion={dataVersion}
          nodeLabelFontSize={labelStyle.nodeFontSize}
          nodeLabelColor={labelStyle.nodeColor}
          edgeLabelFontSize={labelStyle.edgeFontSize}
          edgeLabelColor={labelStyle.edgeColor}
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
                         bg-neutral-bg4 text-text-muted text-[10px]
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
