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
      {/* Title */}
      <span className="text-xs font-semibold text-text-primary whitespace-nowrap">◆ Network Topology</span>

      {/* Label filter chips */}
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
              <span
                className="h-2 w-2 rounded-full shrink-0"
                style={{ backgroundColor: NODE_COLORS[label] ?? '#6B7280' }}
              />
              {label}
            </button>
          );
        })}
      </div>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Search */}
      <input
        type="text"
        value={searchQuery}
        onChange={(e) => onSearchChange(e.target.value)}
        placeholder="Search nodes..."
        className="bg-white/5 border border-white/10 rounded px-2 py-0.5
                   text-[11px] text-text-secondary placeholder:text-text-muted
                   w-32 focus:w-44 transition-all focus:outline-none focus:border-white/25"
      />

      {/* Counts */}
      {meta && (
        <span className="text-[10px] text-text-muted whitespace-nowrap">
          {meta.node_count}N · {meta.edge_count}E
        </span>
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
