import { Group as PanelGroup, Panel, Separator as PanelResizeHandle } from 'react-resizable-panels';
import { MetricCard } from './MetricCard';
import { AlertChart } from './AlertChart';
import { LogStream } from './LogStream';

const metrics: { label: string; value: string; colorClass: string; delta?: string; deltaColor?: string }[] = [
  {
    label: 'Active Alerts',
    value: '12',
    colorClass: 'text-status-error',
    delta: '▲ 4 vs 1h',
    deltaColor: 'text-status-error',
  },
  {
    label: 'Services Impacted',
    value: '3',
    colorClass: 'text-status-warning',
  },
  {
    label: 'SLA At Risk',
    value: '$115k/hr',
    colorClass: 'text-status-error',
  },
  {
    label: 'Anomalies (24h)',
    value: '231',
    colorClass: 'text-brand',
    delta: '▲ 87 vs avg',
    deltaColor: 'text-status-error',
  },
];

function ResizeHandle() {
  return <PanelResizeHandle className="metrics-resize-handle" />;
}

export function MetricsBar() {
  return (
    <div className="h-full px-6 py-3">
      <PanelGroup className="h-full">
        {/* 4 metric cards */}
        {metrics.map((m, i) => (
          <>
            {i > 0 && <ResizeHandle key={`h-${i}`} />}
            <Panel key={m.label} defaultSize={8} minSize={5}>
              <div className="h-full px-1">
                <MetricCard
                  label={m.label}
                  value={m.value}
                  colorClass={m.colorClass}
                  delta={m.delta}
                  deltaColor={m.deltaColor}
                />
              </div>
            </Panel>
          </>
        ))}

        {/* 5 — Anomaly chart */}
        <ResizeHandle />
        <Panel defaultSize={14} minSize={8}>
          <div className="h-full px-1">
            <AlertChart />
          </div>
        </Panel>

        {/* 6 — API logs */}
        <ResizeHandle />
        <Panel defaultSize={28} minSize={12}>
          <div className="h-full px-1">
            <LogStream url="/api/logs" title="API" />
          </div>
        </Panel>

        {/* 7 — Fabric query API logs */}
        <ResizeHandle />
        <Panel defaultSize={28} minSize={12}>
          <div className="h-full px-1">
            <LogStream url="/api/fabric-logs" title="Fabric" />
          </div>
        </Panel>
      </PanelGroup>
    </div>
  );
}
