import { useState } from 'react';
import { ScenarioChip } from './ScenarioChip';
import { AgentBar } from './AgentBar';
import { ProvisioningBanner } from './ProvisioningBanner';
import { FabricSetupModal } from './FabricSetupModal';
import { useScenarioContext } from '../context/ScenarioContext';

export function Header() {
  const { activeScenarioRecord } = useScenarioContext();
  const [fabricOpen, setFabricOpen] = useState(false);

  const isFabricScenario = activeScenarioRecord?.graph_connector === 'fabric-gql';

  return (
    <>
      <header className="h-12 flex-shrink-0 bg-neutral-bg2 border-b border-white/10 flex items-center px-6">
        <div className="flex items-center gap-3">
          <span className="text-brand text-lg leading-none">◆</span>
          <h1 className="text-lg font-semibold text-text-primary leading-none">
            AI Incident Investigator
          </h1>
          <span className="text-xs text-text-muted ml-1 hidden sm:inline">
            Multi-agent diagnosis
          </span>
          <ScenarioChip />
          {isFabricScenario && (
            <button
              onClick={() => setFabricOpen(true)}
              className="text-xs text-cyan-400 hover:text-cyan-300 bg-cyan-400/10 hover:bg-cyan-400/20 border border-cyan-400/30 px-2 py-0.5 rounded transition-colors"
              title="Fabric Setup"
            >
              ⬡ Fabric
            </button>
          )}
        </div>
      </header>
      <AgentBar />
      <ProvisioningBanner />
      <FabricSetupModal open={fabricOpen} onClose={() => setFabricOpen(false)} />
    </>
  );
}
