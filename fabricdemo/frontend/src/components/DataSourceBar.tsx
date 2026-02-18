import { useState, useEffect } from 'react';
import { DataSourceCard } from './DataSourceCard';
import type { DataSourceHealth } from './DataSourceCard';
import { useScenario } from '../ScenarioContext';

const QUERY_API = '/query';

export function DataSourceBar() {
  const SCENARIO = useScenario();
  const [sources, setSources] = useState<DataSourceHealth[]>([]);

  useEffect(() => {
    const check = () =>
      fetch(`${QUERY_API}/health/sources?scenario=${encodeURIComponent(SCENARIO.name)}`)
        .then((r) => r.json())
        .then((d) => setSources(d.sources || []))
        .catch(() => {});

    check();
    const iv = setInterval(check, 30_000);
    return () => clearInterval(iv);
  }, [SCENARIO.name]);

  if (sources.length === 0) return null;

  return (
    <div className="h-8 flex-shrink-0 bg-neutral-bg2 border-b border-white/10
                    flex items-center gap-2 px-6 overflow-x-auto">
      <span className="text-[10px] text-text-muted uppercase tracking-wider mr-2">
        Sources
      </span>
      {sources.map((s) => (
        <DataSourceCard key={s.source_type} source={s} />
      ))}
    </div>
  );
}
