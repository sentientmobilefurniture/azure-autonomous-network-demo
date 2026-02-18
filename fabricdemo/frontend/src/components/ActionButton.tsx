import { useState, useCallback } from 'react';

export type ActionStatus = 'idle' | 'working' | 'done' | 'error';

interface ActionButtonProps {
  label: string;
  icon: string;
  description: string;
  onClick: () => Promise<string>;
}

export function ActionButton({ label, icon, description, onClick }: ActionButtonProps) {
  const [status, setStatus] = useState<ActionStatus>('idle');
  const [result, setResult] = useState('');

  const handleClick = useCallback(async () => {
    setStatus('working');
    setResult('');
    try {
      const msg = await onClick();
      setResult(msg);
      setStatus('done');
    } catch (e) {
      setResult(String(e));
      setStatus('error');
    }
  }, [onClick]);

  return (
    <button
      onClick={handleClick}
      disabled={status === 'working'}
      className={`flex-1 p-3 rounded-lg border text-left transition-colors ${
        status === 'done' ? 'border-status-success/30 bg-status-success/5' :
        status === 'error' ? 'border-status-error/30 bg-status-error/5' :
        status === 'working' ? 'border-brand/30 bg-brand/5 animate-pulse' :
        'border-border bg-neutral-bg1 hover:border-border-strong'
      }`}
    >
      <div className="flex items-center gap-2 mb-1">
        <span>{icon}</span>
        <span className="text-sm font-medium text-text-primary">{label}</span>
        {status === 'done' && <span className="text-xs text-status-success ml-auto">✓</span>}
        {status === 'error' && <span className="text-xs text-status-error ml-auto">✗</span>}
        {status === 'working' && <span className="text-xs text-text-muted ml-auto">...</span>}
      </div>
      <p className="text-xs text-text-muted">
        {status === 'done' ? result : status === 'error' ? result.substring(0, 80) : description}
      </p>
    </button>
  );
}
