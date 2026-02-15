import { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import { useResourceGraph } from '../hooks/useResourceGraph';
import { ResourceCanvas, ResourceCanvasHandle } from './resource/ResourceCanvas';
import { ResourceToolbar } from './resource/ResourceToolbar';
import { ResourceTooltip } from './resource/ResourceTooltip';
import type { ResourceNode, ResourceEdge, ResourceNodeType } from '../types';

/**
 * ResourceVisualizer — full-page tab component showing the agent & data-source
 * flow graph for the active scenario.
 *
 * Mirrors the layout/interaction patterns of GraphTopologyViewer but with
 * resource-specific node types, shapes, and a layered force layout.
 */
export function ResourceVisualizer() {
  const { nodes, edges } = useResourceGraph();
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
    if (manualPause) return;
    resumeTimeoutRef.current = setTimeout(() => {
      canvasRef.current?.setFrozen(false);
      setIsPaused(false);
      resumeTimeoutRef.current = null;
    }, 300);
  }, [manualPause]);

  const handleTogglePause = useCallback(() => {
    if (manualPause) {
      setManualPause(false);
      canvasRef.current?.setFrozen(false);
      setIsPaused(false);
    } else {
      setManualPause(true);
      canvasRef.current?.setFrozen(true);
      setIsPaused(true);
    }
  }, [manualPause]);

  useEffect(() => {
    return () => {
      if (resumeTimeoutRef.current) clearTimeout(resumeTimeoutRef.current);
    };
  }, []);

  // ── Tooltip ───────────────────────────────────────────────────────────

  const [tooltip, setTooltip] = useState<{
    x: number; y: number;
    node?: ResourceNode; edge?: ResourceEdge;
  } | null>(null);

  const mousePos = useRef({ x: 0, y: 0 });
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      mousePos.current = { x: e.clientX, y: e.clientY };
    };
    window.addEventListener('mousemove', handler);
    return () => window.removeEventListener('mousemove', handler);
  }, []);

  const handleNodeHover = useCallback((node: ResourceNode | null) => {
    if (node) {
      setTooltip({ x: mousePos.current.x, y: mousePos.current.y, node, edge: undefined });
    } else {
      setTooltip(null);
    }
  }, []);

  const handleLinkHover = useCallback((edge: ResourceEdge | null) => {
    if (edge) {
      setTooltip({ x: mousePos.current.x, y: mousePos.current.y, edge, node: undefined });
    } else {
      setTooltip(null);
    }
  }, []);

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

  const filteredEdges = useMemo(() => {
    return edges.filter((e) => {
      const srcId = typeof e.source === 'string' ? e.source : (e.source as ResourceNode).id;
      const tgtId = typeof e.target === 'string' ? e.target : (e.target as ResourceNode).id;
      return filteredNodeIds.has(srcId) && filteredNodeIds.has(tgtId);
    });
  }, [edges, filteredNodeIds]);

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
            onBackgroundClick={() => setTooltip(null)}
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

          {/* Mock data badge */}
          <div className="absolute top-2 right-2 px-2 py-0.5 rounded-full
                         bg-amber-500/15 text-amber-400 text-[10px] font-medium
                         border border-amber-500/20">
            Mock data — will connect to config API
          </div>
        </div>

        <ResourceTooltip tooltip={tooltip} />
      </div>
    </div>
  );
}
