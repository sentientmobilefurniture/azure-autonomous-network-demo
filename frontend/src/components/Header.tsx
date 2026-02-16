import { useState, useEffect } from 'react';
import { ScenarioChip } from './ScenarioChip';
import { AgentBar } from './AgentBar';
import { ProvisioningBanner } from './ProvisioningBanner';
import { FabricSetupWizard } from './FabricSetupWizard';
import { ServiceHealthSummary } from './ServiceHealthSummary';
import { ServiceHealthPopover } from './ServiceHealthPopover';
import { useFabricDiscovery } from '../hooks/useFabricDiscovery';

export function Header() {
  const [wizardOpen, setWizardOpen] = useState(false);
  const [healthOpen, setHealthOpen] = useState(false);
  const fabric = useFabricDiscovery();

  // Check health once on mount to determine button state
  useEffect(() => { fabric.checkHealth(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const showFabricButton = fabric.healthy !== null;
  const fabricReady = fabric.queryReady === true;

  return (
    <>
      <header className="h-12 flex-shrink-0 bg-neutral-bg2 border-b border-white/10 flex items-center px-6 justify-between">
        <div className="flex items-center gap-3">
          <span className="text-brand text-lg leading-none">◆</span>
          <h1 className="text-lg font-semibold text-text-primary leading-none">
            AI Incident Investigator
          </h1>
          <span className="text-xs text-text-muted ml-1 hidden sm:inline">
            Multi-agent diagnosis
          </span>
          <ScenarioChip />
        </div>
        <div className="flex items-center gap-2 relative">
          {showFabricButton && (
            <button
              onClick={() => setWizardOpen(true)}
              className={`text-xs px-2 py-0.5 rounded border transition-colors ${
                fabricReady
                  ? 'text-cyan-400/60 hover:text-cyan-400 border-white/10 hover:bg-cyan-400/10'
                  : 'text-amber-400 bg-amber-400/10 border-amber-400/30 hover:bg-amber-400/20'
              }`}
              title="Fabric Setup"
            >
              🔌 {fabricReady ? 'Fabric' : 'Set Up Fabric'}
            </button>
          )}
          <ServiceHealthSummary onClick={() => setHealthOpen(!healthOpen)} />
          <ServiceHealthPopover
            open={healthOpen}
            onClose={() => setHealthOpen(false)}
            onFabricSetup={() => setWizardOpen(true)}
          />
        </div>
      </header>
      <AgentBar />
      <ProvisioningBanner />
      <FabricSetupWizard
        open={wizardOpen}
        onClose={() => setWizardOpen(false)}
      />
    </>
  );
}
