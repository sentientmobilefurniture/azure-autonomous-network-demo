import { useState } from 'react';

interface AgentSpec {
  id: string;
  name: string;
  role: string;
  model: string;
  status: string;
  is_orchestrator?: boolean;
  tools?: { type: string; spec_template?: string; index_key?: string }[];
  connected_agents?: string[];
}

export function AgentCard({ agent }: { agent: AgentSpec }) {
  const [showTooltip, setShowTooltip] = useState(false);

  const dotColor = agent.status === 'provisioned'
    ? 'bg-status-success'
    : agent.status === 'provisioning'
      ? 'bg-amber-400 animate-pulse'
      : agent.status === 'error'
        ? 'bg-status-error'
        : 'bg-text-muted';

  return (
    <div
      className="relative inline-flex items-center gap-1.5 px-2 py-1
                 rounded bg-white/5 hover:bg-white/10 transition-colors
                 cursor-default select-none"
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
    >
      <span className={`h-1.5 w-1.5 rounded-full flex-shrink-0 ${dotColor}`} />
      <span className="text-xs text-text-secondary truncate max-w-[140px]">
        {agent.is_orchestrator && (
          <span className="text-brand mr-1" title="Orchestrator">⬡</span>
        )}
        {agent.name}
      </span>

      {showTooltip && (
        <div className="absolute left-0 top-full mt-1 z-50 min-w-[220px]
                        bg-neutral-bg3 border border-white/10 rounded-lg
                        shadow-xl p-3 text-xs text-text-secondary">
          <div className="font-medium text-text-primary mb-2">{agent.name}</div>
          <div className="space-y-1">
            <Row label="Role" value={agent.role} />
            <Row label="Model" value={agent.model} />
            {agent.tools && agent.tools.length > 0 && (
              <div>
                <span className="text-text-muted">Tools:</span>
                <ul className="ml-3 mt-0.5 space-y-0.5">
                  {agent.tools.map((t, i) => (
                    <li key={i} className="text-text-secondary">
                      • {formatTool(t)}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {agent.connected_agents && agent.connected_agents.length > 0 && (
              <Row label="Delegates to" value={agent.connected_agents.join(', ')} />
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="text-text-muted">{label}:</span>{' '}
      <span className="text-text-primary">{value}</span>
    </div>
  );
}

function formatTool(tool: { type: string; spec_template?: string; index_key?: string }): string {
  if (tool.type === 'openapi') return `OpenAPI: ${tool.spec_template ?? 'unknown'}`;
  if (tool.type === 'azure_ai_search') return `AI Search: ${tool.index_key ?? 'unknown'}`;
  return tool.type;
}
