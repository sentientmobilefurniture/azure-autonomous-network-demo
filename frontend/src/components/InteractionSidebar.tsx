import type { Interaction } from '../types';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatTimeAgo(isoString: string): string {
  const seconds = Math.floor((Date.now() - new Date(isoString).getTime()) / 1000);
  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

// ---------------------------------------------------------------------------
// InteractionCard
// ---------------------------------------------------------------------------

interface InteractionCardProps {
  interaction: Interaction;
  onClick: () => void;
  onDelete: () => void;
  isActive: boolean;
}

function InteractionCard({ interaction, onClick, onDelete, isActive }: InteractionCardProps) {
  const timeAgo = formatTimeAgo(interaction.created_at);

  return (
    <div
      onClick={onClick}
      className={`group cursor-pointer rounded-lg border p-2.5 transition-colors ${
        isActive
          ? 'border-brand/40 bg-brand/10'
          : 'border-white/5 bg-neutral-bg3 hover:border-white/15 hover:bg-neutral-bg4'
      }`}
    >
      {/* Header: timestamp + delete */}
      <div className="flex items-center justify-between mb-1">
        <span className="text-[10px] text-text-muted">{timeAgo}</span>
        <button
          onClick={(e) => { e.stopPropagation(); onDelete(); }}
          className="opacity-0 group-hover:opacity-100 text-text-muted hover:text-red-400
                     transition-opacity text-xs p-0.5"
          title="Delete"
        >
          ✕
        </button>
      </div>

      {/* Scenario badge */}
      <span className="inline-block text-[10px] font-medium px-1.5 py-0.5 rounded
                       bg-accent/15 text-accent mb-1">
        {interaction.scenario}
      </span>

      {/* Query preview */}
      <p className="text-xs text-text-secondary line-clamp-2 leading-relaxed">
        {interaction.query}
      </p>

      {/* Meta: step count + elapsed */}
      {interaction.run_meta && (
        <div className="mt-1.5 text-[10px] text-text-muted flex gap-2">
          <span>{interaction.run_meta.steps} steps</span>
          <span>{interaction.run_meta.time}</span>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// InteractionSidebar
// ---------------------------------------------------------------------------

interface InteractionSidebarProps {
  interactions: Interaction[];
  loading: boolean;
  onSelect: (interaction: Interaction) => void;
  onDelete: (id: string, scenario: string) => void;
  activeInteractionId: string | null;
  collapsed: boolean;
  onToggleCollapse: () => void;
}

export function InteractionSidebar({
  interactions, loading, onSelect, onDelete,
  activeInteractionId, collapsed, onToggleCollapse,
}: InteractionSidebarProps) {
  return (
    <div className={`
      border-l border-white/10 bg-neutral-bg2 flex flex-col
      transition-[width] duration-200 ease-out
      ${collapsed ? 'w-10' : 'w-72'}
    `}>
      {/* Header with collapse toggle */}
      <div className="h-10 flex items-center justify-between px-3 border-b border-white/10 shrink-0">
        {!collapsed && (
          <span className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
            History
          </span>
        )}
        <button
          onClick={onToggleCollapse}
          className="text-text-muted hover:text-text-primary text-xs transition-colors"
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? '◀' : '▶'}
        </button>
      </div>

      {/* Interaction list */}
      {!collapsed && (
        <div className="flex-1 overflow-y-auto p-2 space-y-2">
          {/* Loading skeleton */}
          {loading && interactions.length === 0 && (
            <div className="space-y-2 p-2">
              {[1, 2, 3].map(i => (
                <div key={i} className="h-20 rounded-lg bg-white/5 animate-pulse" />
              ))}
            </div>
          )}

          {/* Empty state */}
          {!loading && interactions.length === 0 && (
            <div className="flex flex-col items-center justify-center text-center py-8 px-3">
              <span className="text-2xl opacity-40 mb-2">◇</span>
              <p className="text-xs text-text-muted leading-relaxed">
                History appears here.<br />
                Submit an alert to start an investigation.<br />
                Results are auto-saved.
              </p>
            </div>
          )}

          {/* Interaction cards */}
          {interactions.map(interaction => (
            <InteractionCard
              key={interaction.id}
              interaction={interaction}
              onClick={() => onSelect(interaction)}
              onDelete={() => onDelete(interaction.id, interaction.scenario)}
              isActive={activeInteractionId === interaction.id}
            />
          ))}
        </div>
      )}
    </div>
  );
}
