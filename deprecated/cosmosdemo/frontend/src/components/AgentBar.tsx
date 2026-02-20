import { useState, useEffect } from 'react';
import { useScenarioContext } from '../context/ScenarioContext';
import { AgentCard } from './AgentCard';
import { HealthDot } from './HealthDot';

interface AgentData {
  id: string;
  name: string;
  role: string;
  model: string;
  status: string;
  is_orchestrator?: boolean;
  tools?: { type: string; spec_template?: string; index_key?: string }[];
  connected_agents?: string[];
}

export function AgentBar() {
  const { provisioningStatus, activeScenario } = useScenarioContext();
  const [agents, setAgents] = useState<AgentData[]>([]);

  useEffect(() => {
    if (!activeScenario) {
      setAgents([]);
      return;
    }
    let cancelled = false;
    fetch('/api/agents')
      .then(r => r.json())
      .then(d => {
        if (!cancelled) setAgents(d.agents ?? []);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [activeScenario, provisioningStatus.state]);

  if (agents.length === 0) return null;

  // Sort: orchestrator first, then alphabetical
  const sorted = [...agents].sort((a, b) => {
    if (a.is_orchestrator && !b.is_orchestrator) return -1;
    if (!a.is_orchestrator && b.is_orchestrator) return 1;
    return a.name.localeCompare(b.name);
  });

  return (
    <div className="h-8 flex-shrink-0 bg-neutral-bg2 border-b border-white/10
                    flex items-center gap-2 px-6 overflow-x-auto">
      <HealthDot label="API" />
      <div className="w-px h-4 bg-white/10" />
      {sorted.map(agent => (
        <AgentCard key={agent.id} agent={agent} />
      ))}
    </div>
  );
}
