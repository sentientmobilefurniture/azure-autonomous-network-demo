import { useState, useRef } from 'react';
import { ModalShell } from './ModalShell';
import { useScenarioContext } from '../context/ScenarioContext';
import { useScenarios } from '../hooks/useScenarios';
import { triggerProvisioning } from '../utils/triggerProvisioning';
import { useClickOutside } from '../hooks/useClickOutside';

interface Props {
  open: boolean;
  onClose: () => void;
  onNewScenario: () => void;
  onFabricSetup: () => void;
}

/**
 * Scenario list + management modal.
 * Opened from ScenarioChip's "⊞ Manage scenarios…" menu item.
 */
export function ScenarioManagerModal({ open, onClose, onNewScenario, onFabricSetup }: Props) {
  const { setProvisioningStatus } = useScenarioContext();
  const { savedScenarios, selectScenario, deleteSavedScenario } = useScenarios();
  const [menuOpen, setMenuOpen] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useClickOutside(menuRef, () => setMenuOpen(null), !!menuOpen);

  if (!open) return null;

  const handleSwitch = (id: string) => {
    selectScenario(id);
    onClose();
  };

  const handleReprovisionAgents = async (id: string) => {
    setMenuOpen(null);
    await triggerProvisioning(
      { prompt_scenario: id },
      id,
      setProvisioningStatus,
    );
  };

  const handleDelete = async (id: string) => {
    setMenuOpen(null);
    if (confirm(`Delete scenario "${id}"? This cannot be undone.`)) {
      await deleteSavedScenario(id);
    }
  };

  const handleFabricReprovision = () => {
    setMenuOpen(null);
    onClose();
    onFabricSetup();
  };

  const backendBadge = (connector?: string) => {
    if (connector === 'fabric-gql') return { label: 'Fabric', color: 'text-cyan-400 bg-cyan-400/10 border-cyan-400/30' };
    if (connector === 'mock') return { label: 'Mock', color: 'text-yellow-400 bg-yellow-400/10 border-yellow-400/30' };
    return { label: 'Backend', color: 'text-emerald-400 bg-emerald-400/10 border-emerald-400/30' };
  };

  const footer = (
    <div className="flex justify-between w-full">
      <button
        onClick={onClose}
        className="px-4 py-1.5 text-sm text-text-primary bg-white/10 hover:bg-white/15 rounded-md transition-colors"
      >
        Close
      </button>
      <button
        onClick={() => { onClose(); onNewScenario(); }}
        className="px-4 py-1.5 text-sm bg-brand text-white hover:bg-brand/90 rounded-md transition-colors"
      >
        + New Scenario
      </button>
    </div>
  );

  return (
    <ModalShell title="Manage Scenarios" onClose={onClose} footer={footer}>
      {savedScenarios.length === 0 ? (
        <div className="text-center py-8 text-sm text-text-muted">
          No saved scenarios. Upload one to get started.
        </div>
      ) : (
        <div className="space-y-1">
          {savedScenarios.map((s) => {
            const badge = backendBadge(s.graph_connector);
            const isFabric = s.graph_connector === 'fabric-gql';
            return (
              <div
                key={s.id}
                className="flex items-center justify-between px-3 py-2 rounded-lg hover:bg-white/5 transition-colors group"
              >
                <button
                  onClick={() => handleSwitch(s.id)}
                  className="flex-1 text-left flex items-center gap-2 min-w-0"
                >
                  <span className="text-sm text-text-primary truncate">{s.display_name || s.id}</span>
                  <span className={`text-[9px] px-1 py-0.5 rounded border font-medium flex-shrink-0 ${badge.color}`}>
                    {badge.label}
                  </span>
                </button>

                {/* Per-row ⋮ menu */}
                <div className="relative" ref={menuOpen === s.id ? menuRef : undefined}>
                  <button
                    onClick={() => setMenuOpen(menuOpen === s.id ? null : s.id)}
                    className="px-1.5 py-0.5 text-text-muted hover:text-text-primary transition-colors opacity-0 group-hover:opacity-100"
                  >
                    ⋮
                  </button>
                  {menuOpen === s.id && (
                    <div className="absolute right-0 top-full mt-1 w-52 bg-neutral-bg2 border border-white/10 rounded-lg shadow-xl z-50 overflow-hidden">
                      <button onClick={() => handleSwitch(s.id)}
                        className="w-full text-left px-3 py-2 text-xs text-text-primary hover:bg-white/5">
                        Switch to this scenario
                      </button>
                      <button onClick={() => handleReprovisionAgents(s.id)}
                        className="w-full text-left px-3 py-2 text-xs text-text-primary hover:bg-white/5">
                        Re-provision agents
                      </button>
                      {isFabric && (
                        <button onClick={handleFabricReprovision}
                          className="w-full text-left px-3 py-2 text-xs text-cyan-400 hover:bg-cyan-400/10">
                          Re-provision Fabric resources
                        </button>
                      )}
                      <div className="border-t border-white/10" />
                      <button onClick={() => handleDelete(s.id)}
                        className="w-full text-left px-3 py-2 text-xs text-status-error hover:bg-status-error/10">
                        Delete scenario
                      </button>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </ModalShell>
  );
}
