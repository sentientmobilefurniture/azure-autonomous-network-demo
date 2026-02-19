import type { ResourceNodeType } from '../../types';
import { RESOURCE_NODE_COLORS, RESOURCE_TYPE_LABELS } from './resourceConstants';

/** All node types in display order — grouped: agents → tools → data → infrastructure */
const ALL_TYPES: ResourceNodeType[] = [
  'orchestrator', 'agent', 'tool',
  'datasource', 'search-index', 'blob-container',
  'foundry', 'storage', 'search-service', 'container-app',
];

interface ResourceToolbarProps {
  nodeCount: number;
  edgeCount: number;
  activeTypes: ResourceNodeType[];
  onToggleType: (type: ResourceNodeType) => void;
  searchQuery: string;
  onSearchChange: (q: string) => void;
  onZoomToFit: () => void;
  isPaused: boolean;
  onTogglePause: () => void;
}

export function ResourceToolbar({
  nodeCount, edgeCount, activeTypes,
  onToggleType, searchQuery, onSearchChange,
  onZoomToFit, isPaused, onTogglePause,
}: ResourceToolbarProps) {
  return (
    <div className="flex items-center gap-2 px-3 py-1.5 border-b border-border shrink-0">
      {/* Title */}
      <span className="text-xs font-semibold text-text-primary whitespace-nowrap">
        ◇ Agent &amp; Resource Flow
      </span>

      {/* Type filter chips */}
      <div className="flex items-center gap-1 ml-2 overflow-x-auto">
        {ALL_TYPES.map((type) => {
          const active = activeTypes.length === 0 || activeTypes.includes(type);
          return (
            <button
              key={type}
              onClick={() => onToggleType(type)}
              className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px]
                         border transition-colors
                         ${active
                           ? 'border-border-strong text-text-secondary'
                           : 'border-transparent text-text-muted opacity-40'}`}
            >
              <span
                className="h-2.5 w-2.5 rounded-full shrink-0"
                style={{ backgroundColor: RESOURCE_NODE_COLORS[type] }}
              />
              {RESOURCE_TYPE_LABELS[type]}
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
        placeholder="Search resources..."
        className="bg-neutral-bg3 border border-border rounded px-2 py-0.5
                   text-[11px] text-text-secondary placeholder:text-text-muted
                   w-32 focus:w-44 transition-all focus:outline-none focus:border-brand"
      />

      {/* Counts */}
      <span className="text-[10px] text-text-muted whitespace-nowrap">
        {nodeCount}N · {edgeCount}E
      </span>

      {/* Pause/Play */}
      <button
        onClick={onTogglePause}
        className={`text-xs px-1 transition-colors ${
          isPaused ? 'text-brand hover:text-brand/80' : 'text-text-muted hover:text-text-primary'
        }`}
        title={isPaused ? 'Resume simulation' : 'Pause simulation'}
      >{isPaused ? '▶' : '⏸'}</button>

      {/* Zoom-to-fit */}
      <button
        onClick={onZoomToFit}
        className="text-text-muted hover:text-text-primary text-xs px-1"
        title="Fit to view"
      >⤢</button>
    </div>
  );
}
