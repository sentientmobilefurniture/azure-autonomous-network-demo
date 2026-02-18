import { useState, useCallback } from 'react';
import { useScenario } from '../ScenarioContext';

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

type CheckStatus = 'idle' | 'checking' | 'ok' | 'error';

interface ButtonDef {
  key: string;
  label: string;
  /** HTTP method */
  method: 'GET' | 'POST';
  /** URL to call */
  url: string | ((scenario: string) => string);
  /** Max retries the *backend* might do (shown as attempt counter) */
  maxAttempts?: number;
}

const BUTTONS: ButtonDef[] = [
  {
    key: 'fabric-sources',
    label: 'Fabric Sources',
    method: 'GET',
    url: (s) => `/query/health/sources?scenario=${encodeURIComponent(s)}`,
  },
  {
    key: 'fabric-discovery',
    label: 'Fabric Discovery',
    method: 'POST',
    url: '/query/health/rediscover',
  },
  {
    key: 'agent-health',
    label: 'Agent Health',
    method: 'GET',
    url: '/api/services/health',
  },
  {
    key: 'agent-discovery',
    label: 'Agent Discovery',
    method: 'POST',
    url: '/api/agents/rediscover',
  },
];

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function statusDot(s: CheckStatus): string {
  switch (s) {
    case 'idle':     return 'bg-text-muted';
    case 'checking': return 'bg-status-warning animate-pulse';
    case 'ok':       return 'bg-status-success';
    case 'error':    return 'bg-status-error';
  }
}

function statusRing(s: CheckStatus): string {
  switch (s) {
    case 'idle':     return 'border-border hover:border-text-muted';
    case 'checking': return 'border-status-warning';
    case 'ok':       return 'border-status-success/40';
    case 'error':    return 'border-status-error/40';
  }
}

/* ------------------------------------------------------------------ */
/*  Single button                                                      */
/* ------------------------------------------------------------------ */

function HealthButton({ def, scenario }: { def: ButtonDef; scenario: string }) {
  const [status, setStatus] = useState<CheckStatus>('idle');
  const [detail, setDetail] = useState<string>('');
  const [elapsed, setElapsed] = useState<number>(0);

  const run = useCallback(async () => {
    setStatus('checking');
    setDetail('');
    const t0 = Date.now();

    // Update elapsed every 500ms while checking
    const timer = setInterval(() => {
      setElapsed(Math.round((Date.now() - t0) / 1000));
    }, 500);

    try {
      const url = typeof def.url === 'function' ? def.url(scenario) : def.url;
      const resp = await fetch(url, {
        method: def.method,
        headers: def.method === 'POST' ? { 'Content-Type': 'application/json' } : {},
      });

      clearInterval(timer);
      setElapsed(Math.round((Date.now() - t0) / 1000));

      if (resp.ok) {
        const data = await resp.json();
        setStatus('ok');
        // Build a concise detail string
        if (def.key === 'fabric-sources') {
          const sources = data.sources ?? [];
          const okCount = sources.filter((s: { ok: boolean }) => s.ok).length;
          setDetail(`${okCount}/${sources.length} sources reachable`);
        } else if (def.key === 'fabric-discovery') {
          setDetail(
            data.fabric_ready && data.kql_ready
              ? 'All Fabric items found'
              : data.fabric_ready
                ? 'Graph ready, KQL missing'
                : 'Discovery incomplete'
          );
        } else if (def.key === 'agent-health') {
          const s = data.summary;
          if (s) setDetail(`${s.connected}/${s.total} connected`);
        } else if (def.key === 'agent-discovery') {
          setDetail(`${data.count ?? 0} agents found`);
        }
      } else {
        setStatus('error');
        setDetail(`HTTP ${resp.status}`);
      }
    } catch (err) {
      clearInterval(timer);
      setElapsed(Math.round((Date.now() - t0) / 1000));
      setStatus('error');
      setDetail(err instanceof Error ? err.message : 'Network error');
    }
  }, [def, scenario]);

  return (
    <button
      onClick={run}
      disabled={status === 'checking'}
      className={`
        inline-flex items-center gap-1.5 px-2.5 py-1 rounded
        border text-[11px] transition-all select-none
        ${statusRing(status)}
        ${status === 'checking'
          ? 'bg-status-warning/5 cursor-wait'
          : 'bg-neutral-bg3 hover:bg-neutral-bg4 cursor-pointer'}
      `}
      title={detail || def.label}
    >
      <span className={`h-1.5 w-1.5 rounded-full flex-shrink-0 ${statusDot(status)}`} />
      <span className="text-text-secondary">{def.label}</span>
      {status === 'checking' && (
        <span className="text-status-warning font-mono text-[10px]">{elapsed}s</span>
      )}
      {status !== 'idle' && status !== 'checking' && detail && (
        <span className={`text-[10px] ${status === 'ok' ? 'text-status-success' : 'text-status-error'}`}>
          — {detail}
        </span>
      )}
    </button>
  );
}

/* ------------------------------------------------------------------ */
/*  Bar                                                                */
/* ------------------------------------------------------------------ */

export function HealthButtonBar() {
  const scenario = useScenario();

  return (
    <div className="h-8 flex-shrink-0 bg-neutral-bg2 border-b border-border
                    flex items-center gap-2 px-6 overflow-x-auto">
      <span className="text-[10px] text-text-muted uppercase tracking-wider mr-1">
        Health
      </span>
      {BUTTONS.map((b) => (
        <HealthButton key={b.key} def={b} scenario={scenario.name} />
      ))}
    </div>
  );
}
