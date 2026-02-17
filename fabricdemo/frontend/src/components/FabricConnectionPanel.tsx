import { useState, useEffect, useCallback } from 'react';
import { ModalShell } from './ModalShell';

interface Connection {
  id: string;
  workspace_id: string;
  workspace_name: string;
  created_at: string;
  last_used: string;
  active: boolean;
}

interface Props {
  open: boolean;
  onClose: () => void;
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

export function FabricConnectionPanel({ open, onClose }: Props) {
  const [connections, setConnections] = useState<Connection[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Add form
  const [newId, setNewId] = useState('');
  const [newName, setNewName] = useState('');
  const [addError, setAddError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  const fetchConnections = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch('/query/fabric/connections');
      if (res.ok) {
        const data = await res.json();
        const conns: Connection[] = data.connections || [];
        setConnections(conns.filter(c => c.id !== '__active_fabric_config__'));
        // Pre-select active
        const active = conns.find(c => c.active);
        if (active) setSelectedId(active.id);
      }
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) {
      fetchConnections();
      setNewId('');
      setNewName('');
      setAddError(null);
      setError(null);
    }
  }, [open, fetchConnections]);

  const handleAdd = async () => {
    if (!newId.trim() || !newName.trim()) return;
    setAdding(true);
    setAddError(null);
    try {
      const res = await fetch('/query/fabric/connections', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ workspace_id: newId.trim(), workspace_name: newName.trim() }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setAddError(data.detail || `Error ${res.status}`);
        return;
      }
      const conn = await res.json();
      setConnections(prev => {
        const filtered = prev.filter(c => c.id !== conn.id);
        return [conn, ...filtered];
      });
      setSelectedId(conn.id);
      setNewId('');
      setNewName('');
    } catch (e) {
      setAddError(String(e));
    } finally {
      setAdding(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await fetch(`/query/fabric/connections/${id}`, { method: 'DELETE' });
      setConnections(prev => prev.filter(c => c.id !== id));
      if (selectedId === id) setSelectedId(null);
    } catch {
      // silent
    }
  };

  const handleSave = async () => {
    if (!selectedId) return;
    setSaving(true);
    setError(null);
    try {
      const res = await fetch(`/query/fabric/connections/${selectedId}/select`, {
        method: 'POST',
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setError(data.detail || `Error ${res.status}`);
        return;
      }
      onClose();
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  };

  if (!open) return null;

  const footer = (
    <div className="flex justify-between w-full">
      <button
        onClick={onClose}
        className="px-4 py-1.5 text-sm text-text-primary bg-white/10 hover:bg-white/15 rounded-md transition-colors"
      >
        Close
      </button>
      <button
        onClick={handleSave}
        disabled={!selectedId || saving}
        className={`px-5 py-1.5 text-sm rounded-md transition-colors font-medium ${
          selectedId && !saving
            ? 'bg-brand text-white hover:bg-brand/90'
            : 'bg-white/5 text-text-muted cursor-not-allowed'
        }`}
      >
        {saving ? 'Saving…' : 'Save'}
      </button>
    </div>
  );

  return (
    <ModalShell title="Fabric Workspaces" onClose={onClose} footer={footer}>
      {/* Add Connection Form */}
      <div className="bg-neutral-bg1 rounded-lg border border-white/10 p-4 space-y-3">
        <p className="text-xs text-text-muted font-medium uppercase tracking-wider">Add Connection</p>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-[10px] text-text-muted block mb-1">Workspace ID</label>
            <input
              type="text"
              value={newId}
              onChange={(e) => setNewId(e.target.value)}
              placeholder="e.g. 4a4ff69c-18dd-..."
              className="w-full bg-neutral-bg2 border border-white/10 rounded px-3 py-1.5 text-sm text-text-primary
                placeholder:text-text-muted/40 focus:outline-none focus:border-brand/50"
            />
          </div>
          <div>
            <label className="text-[10px] text-text-muted block mb-1">Workspace Name</label>
            <input
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="e.g. cosmosfab1"
              className="w-full bg-neutral-bg2 border border-white/10 rounded px-3 py-1.5 text-sm text-text-primary
                placeholder:text-text-muted/40 focus:outline-none focus:border-brand/50"
            />
          </div>
        </div>
        {addError && <p className="text-xs text-status-error">{addError}</p>}
        <div className="flex justify-end">
          <button
            onClick={handleAdd}
            disabled={!newId.trim() || !newName.trim() || adding}
            className={`px-3 py-1 text-xs rounded transition-colors ${
              newId.trim() && newName.trim() && !adding
                ? 'bg-brand/20 text-brand hover:bg-brand/30'
                : 'bg-white/5 text-text-muted cursor-not-allowed'
            }`}
          >
            {adding ? 'Adding…' : '+ Add Connection'}
          </button>
        </div>
      </div>

      {/* Saved Connections */}
      <div className="space-y-2">
        <p className="text-xs text-text-muted font-medium uppercase tracking-wider">Saved Connections</p>

        {loading ? (
          <div className="text-center py-6">
            <span className="text-xs text-text-muted animate-pulse">Loading…</span>
          </div>
        ) : connections.length === 0 ? (
          <div className="text-center py-6 text-xs text-text-muted">
            No connections saved. Add one above.
          </div>
        ) : (
          <div className="space-y-2">
            {connections.map(conn => {
              const isSelected = selectedId === conn.id;
              return (
                <button
                  key={conn.id}
                  onClick={() => setSelectedId(conn.id)}
                  className={`w-full text-left px-4 py-3 rounded-lg border transition-colors group ${
                    isSelected
                      ? 'border-brand/50 bg-brand/10'
                      : 'border-white/10 bg-neutral-bg1 hover:bg-white/5'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className={`h-3 w-3 rounded-full border-2 flex-shrink-0 ${
                        isSelected ? 'border-brand bg-brand' : 'border-white/30'
                      }`} />
                      <span className="text-sm font-medium text-text-primary truncate">
                        {conn.workspace_name}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <span className="text-[10px] text-text-muted">{timeAgo(conn.last_used)}</span>
                      <span
                        onClick={(e) => { e.stopPropagation(); handleDelete(conn.id); }}
                        className="text-text-muted hover:text-status-error opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer text-xs"
                      >
                        ✕
                      </span>
                    </div>
                  </div>
                  <p className="text-[10px] text-text-muted mt-1 ml-5 font-mono">{conn.workspace_id}</p>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {error && (
        <p className="text-xs text-status-error">{error}</p>
      )}

      <p className="text-[10px] text-text-muted text-center">
        Select a connection, then click Save to set it as the active workspace.
      </p>
    </ModalShell>
  );
}
