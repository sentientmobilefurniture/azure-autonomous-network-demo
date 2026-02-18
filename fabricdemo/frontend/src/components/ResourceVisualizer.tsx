import { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import { useResourceGraph } from '../hooks/useResourceGraph';
import { ResourceCanvas, ResourceCanvasHandle } from './resource/ResourceCanvas';
import { ResourceToolbar } from './resource/ResourceToolbar';
import { ResourceTooltip } from './resource/ResourceTooltip';
import type { ResourceNode, ResourceEdge, ResourceNodeType } from '../types';
import { usePausableSimulation } from '../hooks/usePausableSimulation';
import { useTooltipTracking } from '../hooks/useTooltipTracking';

/**
 * ResourceVisualizer — full-page tab component showing the agent & data-source
 * flow graph for the active scenario.
 *
 * Mirrors the layout/interaction patterns of GraphTopologyViewer but with
 * resource-specific node types, shapes, and a layered force layout.
 */
const INFRA_TYPES = new Set<ResourceNodeType>(['foundry', 'storage', 'search-service', 'container-app']);

export function ResourceVisualizer() {
  const { nodes, edges, loading, error } = useResourceGraph();
  const canvasRef = useRef<ResourceCanvasHandle>(null);

  // ── Container sizing (fill available space) ───────────────────────────

  const containerRef = useRef<HTMLDivElement>(null);
  const [dims, setDims] = useState({ width: 800, height: 600 });

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      setDims({ width, height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // ── Pause / freeze ───────────────────────────────────────────────────

  const { isPaused, handleMouseEnter, handleMouseLeave, handleTogglePause } =
    usePausableSimulation(canvasRef);

  // ── Tooltip ───────────────────────────────────────────────────────────

  const { tooltip, handleNodeHover, handleLinkHover, clearTooltip } =
    useTooltipTracking<ResourceNode, ResourceEdge>();

  // ── Filtering ─────────────────────────────────────────────────────────

  const [activeTypes, setActiveTypes] = useState<ResourceNodeType[]>([]);
  const [searchQuery, setSearchQuery] = useState('');

  const handleToggleType = useCallback((type: ResourceNodeType) => {
    setActiveTypes((prev) =>
      prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type],
    );
  }, []);

  const filteredNodes = useMemo(() => {
    return nodes.filter((n) => {
      if (activeTypes.length > 0 && !activeTypes.includes(n.type)) return false;
      if (searchQuery && !n.label.toLowerCase().includes(searchQuery.toLowerCase())) return false;
      return true;
    });
  }, [nodes, activeTypes, searchQuery]);

  const filteredNodeIds = useMemo(() => new Set(filteredNodes.map((n) => n.id)), [filteredNodes]);

  // Build a map from node id → type so we can keep infra-connected edges visible
  const nodeTypeMap = useMemo(() => {
    const m = new Map<string, ResourceNodeType>();
    for (const n of nodes) m.set(n.id, n.type);
    return m;
  }, [nodes]);

  const filteredEdges = useMemo(() => {
    return edges.filter((e) => {
      const srcId = typeof e.source === 'string' ? e.source : (e.source as ResourceNode).id;
      const tgtId = typeof e.target === 'string' ? e.target : (e.target as ResourceNode).id;
      // Always include if both endpoints are visible
      if (filteredNodeIds.has(srcId) && filteredNodeIds.has(tgtId)) return true;
      // When type filters are active, also include edges to infrastructure nodes
      // so structural relationships stay visible even with filters
      if (activeTypes.length > 0) {
        const srcVisible = filteredNodeIds.has(srcId);
        const tgtVisible = filteredNodeIds.has(tgtId);
        if (srcVisible && INFRA_TYPES.has(nodeTypeMap.get(tgtId)!)) return true;
        if (tgtVisible && INFRA_TYPES.has(nodeTypeMap.get(srcId)!)) return true;
      }
      return false;
    });
  }, [edges, filteredNodeIds, activeTypes, nodeTypeMap]);

  // ── Toolbar height reservation ────────────────────────────────────────

  const TOOLBAR_HEIGHT = 36;

  return (
    <div className="h-full w-full flex flex-col bg-neutral-bg1">
      <div className="glass-card h-full flex flex-col overflow-hidden m-2 rounded-lg">
        <ResourceToolbar
          nodeCount={filteredNodes.length}
          edgeCount={filteredEdges.length}
          activeTypes={activeTypes}
          onToggleType={handleToggleType}
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          onZoomToFit={() => canvasRef.current?.zoomToFit()}
          isPaused={isPaused}
          onTogglePause={handleTogglePause}
        />

        <div ref={containerRef} className="flex-1 min-h-0 relative">
          <ResourceCanvas
            ref={canvasRef}
            nodes={filteredNodes}
            edges={filteredEdges}
            width={dims.width}
            height={Math.max(dims.height - TOOLBAR_HEIGHT, 100)}
            onNodeHover={handleNodeHover}
            onLinkHover={handleLinkHover}
            onBackgroundClick={clearTooltip}
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

          {/* Loading / error / empty overlays */}
          {loading && (
            <div className="absolute inset-0 flex items-center justify-center bg-black/10">
              <div className="flex flex-col items-center gap-2 text-text-secondary">
                <span className="inline-block h-6 w-6 animate-spin rounded-full border-2 border-brand border-t-transparent" />
                <span className="text-xs">Loading resource graph…</span>
              </div>
            </div>
          )}
          {!loading && error && nodes.length === 0 && (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="text-center space-y-2 text-text-muted">
                <p className="text-sm">Could not load resource graph</p>
                <p className="text-xs text-status-error max-w-sm">{error}</p>
              </div>
            </div>
          )}
          {!loading && error && nodes.length > 0 && (
            <div className="absolute top-2 left-2 right-2 z-10">
              <div className="bg-status-warning/10 border border-status-warning/30 rounded-lg px-3 py-2 text-xs text-status-warning">
                ⚠ {error}
              </div>
            </div>
          )}
          {!loading && !error && nodes.length === 0 && (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="text-center space-y-2 text-text-muted">
                <p className="text-sm">No resources to display</p>
                <p className="text-xs">Upload and configure a scenario to see the resource graph.</p>
              </div>
            </div>
          )}
        </div>

        <ResourceTooltip tooltip={tooltip} />
      </div>
    </div>
  );
}
