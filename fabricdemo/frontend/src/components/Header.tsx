import { useState } from 'react';
import { AgentBar } from './AgentBar';
import { DataSourceBar } from './DataSourceBar';
import { ServiceHealthSummary } from './ServiceHealthSummary';
import { ServiceHealthPopover } from './ServiceHealthPopover';
import { useScenario } from '../ScenarioContext';

export function Header() {
  const SCENARIO = useScenario();
  const [healthOpen, setHealthOpen] = useState(false);

  return (
    <>
      <header className="h-12 flex-shrink-0 bg-neutral-bg2 border-b border-border flex items-center px-6 justify-between">
        <div className="flex items-center gap-3">
          <span className="text-brand text-lg leading-none">◆</span>
          <h1 className="text-lg font-semibold text-text-primary leading-none">
            AI Incident Investigator
          </h1>
          <span className="text-xs text-text-muted ml-1 hidden sm:inline">
            Multi-agent diagnosis
          </span>
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-brand/10 text-brand border border-brand/20 font-medium">
            {SCENARIO.displayName}
          </span>
        </div>
        <div className="flex items-center gap-2 relative">
          <ServiceHealthSummary onClick={() => setHealthOpen(!healthOpen)} />
          <ServiceHealthPopover
            open={healthOpen}
            onClose={() => setHealthOpen(false)}
          />
        </div>
      </header>
      <AgentBar />
      <DataSourceBar />
    </>
  );
}
