import { useState, useEffect } from 'react';
import { HealthDot } from './HealthDot';
import { ScenarioChip } from './ScenarioChip';
import { ProvisioningBanner } from './ProvisioningBanner';
import { FabricSetupModal } from './FabricSetupModal';
import { useScenarioContext } from '../context/ScenarioContext';

export function Header() {
  const { provisioningStatus, activeScenarioRecord } = useScenarioContext();
  const [agentCount, setAgentCount] = useState(0);
  const [fabricOpen, setFabricOpen] = useState(false);

  const isFabricScenario = activeScenarioRecord?.graph_connector === 'fabric-gql';

  // Fetch actual agent count when provisioning completes
  useEffect(() => {
    if (provisioningStatus.state === 'done' || provisioningStatus.state === 'idle') {
      fetch('/api/agents')
        .then(r => r.json())
        .then(d => setAgentCount(d.agents?.length ?? 0))
        .catch(() => {});
    }
  }, [provisioningStatus.state]);

  const agentLabel = (() => {
    switch (provisioningStatus.state) {
      case 'provisioning': return 'Provisioning...';
      case 'done': return `${agentCount || '?'} Agent${agentCount !== 1 ? 's' : ''} ✓`;
      case 'error': return 'Error';
      default: return agentCount > 0 ? `${agentCount} Agent${agentCount !== 1 ? 's' : ''}` : 'No Agents';
    }
  })();

  const agentColor = (() => {
    switch (provisioningStatus.state) {
      case 'provisioning': return 'text-amber-400';
      case 'error': return 'text-red-400';
      default: return 'text-status-success';
    }
  })();

  const dotColor = (() => {
    switch (provisioningStatus.state) {
      case 'provisioning': return 'bg-amber-400 animate-pulse';
      case 'error': return 'bg-red-400';
      default: return 'bg-status-success';
    }
  })();

  return (
    <>
      <header className="h-12 flex-shrink-0 bg-neutral-bg2 border-b border-white/10 flex items-center justify-between px-6">
        {/* Left: branding + scenario chip */}
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

        {/* Right: status indicators + settings */}
        <div className="flex items-center gap-4">
          <HealthDot label="API" />
          <span className="inline-flex items-center gap-1.5 text-xs">
            <span className={`h-1.5 w-1.5 rounded-full ${dotColor}`} />
            <span className={agentColor}>{agentLabel}</span>
          </span>
        </div>
      </header>
      <ProvisioningBanner />
      <FabricSetupModal open={fabricOpen} onClose={() => setFabricOpen(false)} />
    </>
  );
}
