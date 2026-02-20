import type { TopologyMeta } from '../../hooks/useTopology';

interface GraphHeaderBarProps {
  meta: TopologyMeta | null;
  loading: boolean;
  isPaused?: boolean;
  onTogglePause?: () => void;
  onZoomToFit: () => void;
  onRefresh: () => void;
  showNodeBar: boolean;
  onToggleNodeBar: () => void;
  showEdgeBar: boolean;
  onToggleEdgeBar: () => void;
}

export function GraphHeaderBar({
  meta, loading,
  isPaused, onTogglePause,
  onZoomToFit, onRefresh,
  showNodeBar, onToggleNodeBar,
  showEdgeBar, onToggleEdgeBar,
}: GraphHeaderBarProps) {
  return (
    <div className="flex items-center gap-2 px-3 py-1.5 border-b border-border shrink-0">
      {/* Title */}
      <span className="text-xs font-semibold text-text-primary whitespace-nowrap">◆ Network Topology</span>

      {/* Counts */}
      {meta && (
        <span className="text-[10px] text-text-muted whitespace-nowrap ml-1">
          {meta.node_count}N · {meta.edge_count}E
        </span>
      )}

      {/* Spacer */}
      <div className="flex-1" />

      {/* Toggle node bar */}
      <button
        onClick={onToggleNodeBar}
        className={`text-[10px] px-1.5 py-0.5 rounded border transition-colors inline-flex items-center gap-1 ${
          showNodeBar
            ? 'border-brand/30 text-brand bg-brand/5 hover:bg-brand/10'
            : 'border-border text-text-muted hover:bg-neutral-bg3'
        }`}
        title={showNodeBar ? 'Hide node filter bar' : 'Show node filter bar'}
      >
        <span className="text-[9px]">●</span> Nodes
      </button>

      {/* Toggle edge bar */}
      <button
        onClick={onToggleEdgeBar}
        className={`text-[10px] px-1.5 py-0.5 rounded border transition-colors inline-flex items-center gap-1 ${
          showEdgeBar
            ? 'border-brand/30 text-brand bg-brand/5 hover:bg-brand/10'
            : 'border-border text-text-muted hover:bg-neutral-bg3'
        }`}
        title={showEdgeBar ? 'Hide edge filter bar' : 'Show edge filter bar'}
      >
        <span className="text-[9px]">━</span> Edges
      </button>

      <div className="w-px h-4 bg-border mx-0.5" />

      {/* Pause/Play toggle */}
      {onTogglePause && (
        <button
          onClick={onTogglePause}
          className={`text-xs px-1 transition-colors ${
            isPaused ? 'text-brand hover:text-brand/80' : 'text-text-muted hover:text-text-primary'
          }`}
          title={isPaused ? 'Resume simulation' : 'Pause simulation'}
        >{isPaused ? '▶' : '⏸'}</button>
      )}

      {/* Zoom-to-fit */}
      <button
        onClick={onZoomToFit}
        className="text-text-muted hover:text-text-primary text-xs px-1"
        title="Fit to view"
      >⤢</button>

      {/* Refresh */}
      <button
        onClick={onRefresh}
        className={`text-text-muted hover:text-text-primary text-xs px-1
                   ${loading ? 'animate-spin' : ''}`}
        title="Refresh"
      >⟳</button>
    </div>
  );
}
