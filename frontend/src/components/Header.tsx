import { useState } from 'react';
import { HealthDot } from './HealthDot';
import { SettingsModal } from './SettingsModal';
import { ScenarioChip } from './ScenarioChip';
import { ProvisioningBanner } from './ProvisioningBanner';
import { useScenarioContext } from '../context/ScenarioContext';

export function Header() {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const { provisioningStatus } = useScenarioContext();

  const agentLabel = (() => {
    switch (provisioningStatus.state) {
      case 'provisioning': return 'Provisioning...';
      case 'done': return '5 Agents ✓';
      case 'error': return 'Error';
      default: return '5 Agents';
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
        </div>

        {/* Right: status indicators + settings */}
        <div className="flex items-center gap-4">
          <HealthDot label="API" />
          <span className="inline-flex items-center gap-1.5 text-xs">
            <span className={`h-1.5 w-1.5 rounded-full ${dotColor}`} />
            <span className={agentColor}>{agentLabel}</span>
          </span>
          <button
            onClick={() => setSettingsOpen(true)}
            className="text-text-muted hover:text-text-primary transition-colors text-sm"
            title="Settings"
          >
            ⚙
          </button>
        </div>
      </header>
      <ProvisioningBanner />
      <SettingsModal open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </>
  );
}
