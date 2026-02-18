import { useState } from 'react';

export interface DataSourceHealth {
  source_type: string;
  connector: string;
  resource_name: string;
  ok: boolean;
  query: string;
  detail: string;
  latency_ms: number;
}

function connectorLabel(connector: string): string {
  const labels: Record<string, string> = {
    'fabric-gql': 'Fabric Ontology',
    'fabric-kql': 'Fabric Eventhouse',
    'azure-ai-search': 'AI Search',
    'mock': 'Mock',
  };
  return labels[connector] || connector;
}

export function DataSourceCard({ source }: { source: DataSourceHealth }) {
  const [showTooltip, setShowTooltip] = useState(false);

  return (
    <div
      className="relative"
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
    >
      <div className="flex items-center gap-1.5 px-2 py-1 rounded bg-neutral-bg3 text-[10px] cursor-default">
        <span className={source.ok ? 'text-status-success' : 'text-status-error'}>●</span>
        <span className="text-text-secondary">{connectorLabel(source.connector)}</span>
        <span className="text-text-muted"> — {source.resource_name}</span>
      </div>

      {showTooltip && (
        <div className="absolute left-0 top-full mt-1 z-50 min-w-[260px]
                        bg-neutral-bg3 border border-border rounded-lg
                        shadow-xl p-3 text-xs text-text-secondary">
          <p className="font-medium">
            {connectorLabel(source.connector)}: {source.resource_name}
          </p>
          <p className={`mt-1 ${source.ok ? 'text-status-success' : 'text-status-error'}`}>
            Status: {source.ok ? '🟢 Reachable' : '🔴 Unreachable'}
          </p>
          {source.latency_ms > 0 && (
            <p className="text-text-muted">Latency: {source.latency_ms}ms</p>
          )}
          <p className="mt-2 text-text-muted text-[10px] uppercase tracking-wider">
            Query sent:
          </p>
          <pre className="mt-1 p-2 bg-neutral-bg1 rounded text-[10px] font-mono whitespace-pre-wrap">
            {source.query}
          </pre>
          {!source.ok && source.detail && (
            <p className="mt-2 text-status-error/80 text-[10px]">Error: {source.detail}</p>
          )}
        </div>
      )}
    </div>
  );
}
