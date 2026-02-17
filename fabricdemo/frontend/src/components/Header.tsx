import { useState } from 'react';
import { ScenarioChip } from './ScenarioChip';
import { AgentBar } from './AgentBar';
import { DataSourceBar } from './DataSourceBar';
import { ProvisioningBanner } from './ProvisioningBanner';
import { FabricConnectionPanel } from './FabricConnectionPanel';
import { ServiceHealthSummary } from './ServiceHealthSummary';
import { ServiceHealthPopover } from './ServiceHealthPopover';
import { ScenarioStatusPanel, UploadStatusBadge } from './ScenarioStatusPanel';

export function Header() {
  const [fabricOpen, setFabricOpen] = useState(false);
  const [healthOpen, setHealthOpen] = useState(false);
  const [statusOpen, setStatusOpen] = useState(false);

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
          <button
            onClick={() => setFabricOpen(true)}
            className="text-xs px-2 py-0.5 rounded border border-white/10 hover:bg-white/5 transition-colors text-cyan-400/70 hover:text-cyan-400"
            title="Fabric Workspaces"
          >
            🔌 Fabric
          </button>
          <UploadStatusBadge onClick={() => setStatusOpen(!statusOpen)} />
          <ServiceHealthSummary onClick={() => setHealthOpen(!healthOpen)} />
          <ServiceHealthPopover
            open={healthOpen}
            onClose={() => setHealthOpen(false)}
            onFabricSetup={() => setFabricOpen(true)}
          />
          <ScenarioStatusPanel
            open={statusOpen}
            onClose={() => setStatusOpen(false)}
          />
        </div>
      </header>
      <AgentBar />
      <DataSourceBar />
      <ProvisioningBanner />
      <FabricConnectionPanel
        open={fabricOpen}
        onClose={() => setFabricOpen(false)}
      />
    </>
  );
}
