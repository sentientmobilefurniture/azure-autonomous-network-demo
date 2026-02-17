import { useState, useEffect, useCallback, useRef } from 'react';
import { useClickOutside } from '../hooks/useClickOutside';

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

const STATUS_ICON: Record<string, string> = {
  connected: '●',
  partial: '⚠',
  error: '✗',
  not_configured: '○',
};

const STATUS_COLOR: Record<string, string> = {
  connected: 'text-status-success',
  partial: 'text-amber-400',
  error: 'text-status-error',
  not_configured: 'text-text-muted',
};

/**
 * Compact popover showing service health status.
 * Anchored below the ServiceHealthSummary button.
 */
export function ServiceHealthPopover({
  open,
  onClose,
  onFabricSetup,
}: {
  open: boolean;
  onClose: () => void;
  onFabricSetup: () => void;
}) {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [lastChecked, setLastChecked] = useState<Date | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  useClickOutside(ref, onClose, open);

  const fetchHealth = useCallback(async () => {
    try {
      const res = await fetch('/api/services/health');
      if (res.ok) {
        setHealth(await res.json());
        setLastChecked(new Date());
      }
    } catch {
      // fail silently
    }
  }, []);

  useEffect(() => {
    if (open) fetchHealth();
  }, [open, fetchHealth]);

  if (!open) return null;

  return (
    <div
      ref={ref}
      className="absolute top-full right-0 mt-1 w-72 bg-neutral-bg2 border border-white/10 rounded-lg shadow-xl z-50 p-4 space-y-3"
    >
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-text-primary">Services</span>
        <button
          onClick={fetchHealth}
          className="text-xs text-text-muted hover:text-text-secondary transition-colors"
        >
          ↻
        </button>
      </div>

      {health ? (
        <div className="space-y-1.5">
          {health.services.map((svc) => (
            <div key={svc.name} className="space-y-0.5">
              <div className="flex items-center justify-between">
                <span className="text-xs text-text-primary">{svc.name}</span>
                <span className={`text-xs ${STATUS_COLOR[svc.status]}`}>
                  {STATUS_ICON[svc.status]} {svc.status === 'connected' ? '✓' : svc.status}
                </span>
              </div>
              {svc.details && (
                <p className="text-[10px] text-text-muted pl-2">{svc.details}</p>
              )}
              {svc.name === 'Microsoft Fabric' && svc.status === 'partial' && (
                <button
                  onClick={() => { onClose(); onFabricSetup(); }}
                  className="text-[10px] text-brand hover:text-brand/80 pl-2"
                >
                  → Set up Fabric
                </button>
              )}
            </div>
          ))}
        </div>
      ) : (
        <p className="text-xs text-text-muted text-center py-4">Loading…</p>
      )}

      {lastChecked && (
        <p className="text-[10px] text-text-muted text-center">
          Last checked: {Math.round((Date.now() - lastChecked.getTime()) / 1000)}s ago
        </p>
      )}
    </div>
  );
}
