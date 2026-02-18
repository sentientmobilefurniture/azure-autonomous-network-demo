import { useState, useEffect } from 'react';

export function HealthDot({ label }: { label?: string }) {
  const [ok, setOk] = useState<boolean | null>(null);

  useEffect(() => {
    // Single check on mount — no polling (health buttons handle ongoing checks)
    fetch('/health')
      .then((r) => setOk(r.ok))
      .catch(() => setOk(false));
  }, []);

  return (
    <span className="inline-flex items-center gap-1.5 text-xs">
      <span
        className={
          ok === null
            ? 'h-1.5 w-1.5 rounded-full bg-text-muted'
            : ok
              ? 'h-1.5 w-1.5 rounded-full bg-status-success'
              : 'h-1.5 w-1.5 rounded-full bg-status-error'
        }
      />
      <span
        className={
          ok === null
            ? 'text-text-muted'
            : ok
              ? 'text-status-success'
              : 'text-status-error'
        }
      >
        {label ?? (ok === null ? '...' : ok ? 'Connected' : 'Disconnected')}
      </span>
    </span>
  );
}
