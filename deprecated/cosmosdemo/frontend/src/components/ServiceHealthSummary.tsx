import { useState, useEffect, useCallback } from 'react';

interface ServiceStatus {
  name: string;
  group: string;
  status: 'connected' | 'partial' | 'error' | 'not_configured';
  details?: string;
}

interface HealthData {
  services: ServiceStatus[];
  summary: { total: number; connected: number; partial: number; error: number };
}

/**
 * Shows "N/N Services" in the Header. Polls health every 30s.
 * Click opens ServiceHealthPopover.
 */
export function ServiceHealthSummary({ onClick }: { onClick: () => void }) {
  const [health, setHealth] = useState<HealthData | null>(null);

  const fetchHealth = useCallback(async () => {
    try {
      const res = await fetch('/api/services/health');
      if (res.ok) {
        setHealth(await res.json());
      }
    } catch {
      // Endpoint may not exist yet — fail silently
    }
  }, []);

  useEffect(() => {
    fetchHealth();
    const interval = setInterval(fetchHealth, 30_000);
    return () => clearInterval(interval);
  }, [fetchHealth]);

  if (!health) return null;

  const { connected, total, error } = health.summary;
  const color = error > 0 ? 'text-status-error' : connected === total ? 'text-status-success' : 'text-amber-400';

  return (
    <button
      onClick={onClick}
      className={`text-[10px] px-2 py-0.5 rounded border border-white/10 hover:bg-white/5 transition-colors ${color}`}
      title="Service health"
    >
      {connected}/{total} Services
    </button>
  );
}
