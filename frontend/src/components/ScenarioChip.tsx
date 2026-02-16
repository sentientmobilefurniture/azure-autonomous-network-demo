import { useState, useRef } from 'react';
import { useScenarioContext } from '../context/ScenarioContext';
import { useScenarios } from '../hooks/useScenarios';
import { AddScenarioModal } from './AddScenarioModal';
import { useClickOutside } from '../hooks/useClickOutside';

/**
 * Header bar scenario selector chip with flyout dropdown.
 * Shows active scenario name and allows one-click switching.
 */
export function ScenarioChip() {
  const {
    activeScenario,
    provisioningStatus,
    setActiveScenario,
    refreshScenarios,
  } = useScenarioContext();

  const {
    savedScenarios,
    selectScenario,
    saveScenario,
  } = useScenarios();

  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [addModalOpen, setAddModalOpen] = useState(false);
  const chipRef = useRef<HTMLDivElement>(null);

  useClickOutside(chipRef, () => setDropdownOpen(false), dropdownOpen);

  const isProvisioning = provisioningStatus.state === 'provisioning';

  // Resolve backend badge for a scenario
  const backendBadge = (connector?: string) => {
    if (connector === 'fabric-gql') return { label: 'Fabric', color: 'text-cyan-400 bg-cyan-400/10 border-cyan-400/30' };
    if (connector === 'mock') return { label: 'Mock', color: 'text-yellow-400 bg-yellow-400/10 border-yellow-400/30' };
    return { label: 'Cosmos', color: 'text-emerald-400 bg-emerald-400/10 border-emerald-400/30' };
  };

  const activeRecord = savedScenarios.find(s => s.id === activeScenario);
  const activeBadge = activeRecord ? backendBadge(activeRecord.graph_connector) : null;

  return (
    <>
      <div ref={chipRef} className="relative">
        {/* Chip button */}
        <button
          onClick={() => setDropdownOpen(!dropdownOpen)}
          className={`
            inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium
            border transition-colors cursor-pointer
            ${activeScenario
              ? 'border-brand/40 bg-brand/10 text-brand hover:bg-brand/20'
              : 'border-white/20 bg-white/5 text-text-muted hover:bg-white/10'
            }
          `}
          title={activeScenario ? `Active scenario: ${activeScenario}` : 'No scenario selected'}
        >
          {isProvisioning && (
            <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-brand border-t-transparent" />
          )}
          <span className="max-w-[280px] truncate">
            {activeScenario ? activeScenario : '(No scenario)'}
          </span>
          {activeBadge && (
            <span className={`text-[9px] px-1 py-0.5 rounded border font-medium ${activeBadge.color}`}>
              {activeBadge.label}
            </span>
          )}
          <svg className="h-3 w-3 opacity-60" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        </button>

        {/* Flyout dropdown */}
        {dropdownOpen && (
          <div className="absolute top-full left-0 mt-1 w-80 bg-neutral-bg2 border border-white/10 rounded-lg shadow-xl z-50 overflow-hidden">
            {/* Saved scenarios */}
            <div className="max-h-48 overflow-y-auto">
              {savedScenarios.length === 0 ? (
                <div className="px-3 py-4 text-xs text-text-muted text-center">
                  No saved scenarios
                </div>
              ) : (
                savedScenarios.map((s) => (
                  <button
                    key={s.id}
                    onClick={() => {
                      selectScenario(s.id);
                      setDropdownOpen(false);
                    }}
                    className={`
                      w-full text-left px-3 py-2 text-sm transition-colors flex items-center gap-2
                      ${s.id === activeScenario
                        ? 'bg-brand/15 text-brand'
                        : 'text-text-primary hover:bg-white/5'
                      }
                    `}
                  >
                    {s.id === activeScenario && (
                      <span className="h-1.5 w-1.5 rounded-full bg-brand flex-shrink-0" />
                    )}
                    <span className="flex-1 truncate">{s.display_name || s.id}</span>
                    {(() => {
                      const badge = backendBadge(s.graph_connector);
                      return (
                        <span className={`text-[9px] px-1 py-0.5 rounded border font-medium flex-shrink-0 ${badge.color}`}>
                          {badge.label}
                        </span>
                      );
                    })()}
                  </button>
                ))
              )}
            </div>

            <div className="border-t border-white/10">
              {/* Custom mode option */}
              {activeScenario && (
                <button
                  onClick={() => {
                    setActiveScenario(null);
                    setDropdownOpen(false);
                  }}
                  className="w-full text-left px-3 py-2 text-sm text-text-muted hover:bg-white/5 transition-colors"
                >
                  ✦ Custom mode
                </button>
              )}

              {/* New scenario */}
              <button
                onClick={() => {
                  setDropdownOpen(false);
                  setAddModalOpen(true);
                }}
                className="w-full text-left px-3 py-2 text-sm text-brand hover:bg-brand/10 transition-colors"
              >
                + New Scenario
              </button>
            </div>
          </div>
        )}
      </div>

      <AddScenarioModal
        open={addModalOpen}
        onClose={() => setAddModalOpen(false)}
        onSaved={() => {
          refreshScenarios();
        }}
        existingNames={savedScenarios.map(s => s.id)}
        saveScenarioMeta={saveScenario}
      />
    </>
  );
}
