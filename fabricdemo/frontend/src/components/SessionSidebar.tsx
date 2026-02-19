import { useState } from 'react';
import type { SessionSummary } from '../types';
import { formatTimeAgo } from '../utils/formatTime';

// ---------------------------------------------------------------------------
// SessionCard
// ---------------------------------------------------------------------------

interface SessionCardProps {
  session: SessionSummary;
  onClick: () => void;
  isActive: boolean;
}

function StatusBadge({ status }: { status: string }) {
  const config: Record<string, { icon: string; color: string; label: string }> = {
    pending: { icon: '○', color: 'text-text-muted', label: 'Pending' },
    in_progress: { icon: '●', color: 'text-brand animate-pulse', label: 'In Progress' },
    completed: { icon: '✓', color: 'text-green-400', label: 'Completed' },
    failed: { icon: '✗', color: 'text-status-error', label: 'Failed' },
    cancelled: { icon: '⏹', color: 'text-yellow-400', label: 'Cancelled' },
  };
  const { icon, color, label } = config[status] ?? config.pending;
  return (
    <span className={`text-[10px] font-medium ${color}`} title={label}>
      {icon} {label}
    </span>
  );
}

function SessionCard({ session, onClick, isActive }: SessionCardProps) {
  const timeAgo = formatTimeAgo(session.created_at);

  return (
    <div
      onClick={onClick}
      className={`group cursor-pointer rounded-lg border p-2.5 transition-colors ${
        isActive
          ? 'border-brand/40 bg-brand/10'
          : 'border-border-subtle bg-neutral-bg3 hover:border-border-strong hover:bg-neutral-bg4'
      }`}
    >
      {/* Header: status badge + time */}
      <div className="flex items-center justify-between mb-1">
        <StatusBadge status={session.status} />
        <span className="text-[10px] text-text-muted">{timeAgo}</span>
      </div>

      {/* Alert preview */}
      <p className="text-xs text-text-secondary line-clamp-2 leading-relaxed">
        {session.alert_text}
      </p>

      {/* Meta: step count */}
      {session.step_count > 0 && (
        <div className="mt-1.5 text-[10px] text-text-muted">
          {session.step_count} step{session.step_count !== 1 ? 's' : ''}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// SessionSidebar
// ---------------------------------------------------------------------------

interface SessionSidebarProps {
  sessions: SessionSummary[];
  loading: boolean;
  onSelect: (sessionId: string) => void;
  activeSessionId: string | null;
  collapsed: boolean;
  onToggleCollapse: () => void;
}

export function SessionSidebar({
  sessions, loading, onSelect,
  activeSessionId, collapsed, onToggleCollapse,
}: SessionSidebarProps) {
  const [filter, setFilter] = useState('');

  const filtered = filter.trim()
    ? sessions.filter(s =>
        s.alert_text.toLowerCase().includes(filter.toLowerCase())
      )
    : sessions;

  return (
    <div className="h-full border-l border-border bg-neutral-bg2 flex flex-col">
      {/* Header with collapse toggle */}
      <div className="h-10 flex items-center justify-between px-3 border-b border-border shrink-0">
        {!collapsed && (
          <span className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
            Sessions
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

      {/* Search filter */}
      {!collapsed && (
        <div className="px-2 pt-2 shrink-0">
          <input
            type="text"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Search sessions…"
            className="w-full text-[11px] px-2 py-1 rounded border border-border bg-neutral-bg3
                       text-text-secondary placeholder-text-muted focus:outline-none focus:border-brand/40"
          />
        </div>
      )}

      {/* Session list */}
      {!collapsed && (
        <div className="flex-1 overflow-y-auto p-2 space-y-2">
          {/* Loading skeleton */}
          {loading && sessions.length === 0 && (
            <div className="space-y-2 p-2">
              {[1, 2, 3].map(i => (
                <div key={i} className="h-20 rounded-lg bg-neutral-bg3 animate-pulse" />
              ))}
            </div>
          )}

          {/* Empty state */}
          {!loading && sessions.length === 0 && (
            <div className="flex flex-col items-center justify-center text-center py-8 px-3">
              <span className="text-2xl opacity-40 mb-2">◇</span>
              <p className="text-xs text-text-muted leading-relaxed">
                No sessions yet.<br />
                Submit an alert to start an investigation.
              </p>
            </div>
          )}

          {/* No results for filter */}
          {!loading && sessions.length > 0 && filtered.length === 0 && (
            <div className="text-center py-4">
              <p className="text-xs text-text-muted">No matches for &quot;{filter}&quot;</p>
            </div>
          )}

          {/* Session cards */}
          {filtered.map(session => (
            <SessionCard
              key={session.id}
              session={session}
              onClick={() => onSelect(session.id)}
              isActive={activeSessionId === session.id}
            />
          ))}
        </div>
      )}
    </div>
  );
}
