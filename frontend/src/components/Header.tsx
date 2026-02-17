import { useState } from 'react';
import { ScenarioChip } from './ScenarioChip';
import { AgentBar } from './AgentBar';
import { DataSourceBar } from './DataSourceBar';
import { ProvisioningBanner } from './ProvisioningBanner';
import { ServiceHealthSummary } from './ServiceHealthSummary';
import { ServiceHealthPopover } from './ServiceHealthPopover';
import { ScenarioStatusPanel, UploadStatusBadge } from './ScenarioStatusPanel';

export function Header() {
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
          <UploadStatusBadge onClick={() => setStatusOpen(!statusOpen)} />
          <ServiceHealthSummary onClick={() => setHealthOpen(!healthOpen)} />
          <ServiceHealthPopover
            open={healthOpen}
            onClose={() => setHealthOpen(false)}
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
    </>
  );
}
