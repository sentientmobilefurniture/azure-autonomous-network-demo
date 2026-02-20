import { useState, useEffect, useCallback, useRef } from 'react';
import { useClickOutside } from '../hooks/useClickOutside';

interface JobStep {
  name: string;
  status: 'pending' | 'running' | 'done' | 'error';
  detail?: string;
  pct?: number;
}

interface Job {
  id: string;
  scenario_name: string;
  status: 'pending' | 'running' | 'done' | 'error';
  overall_pct: number;
  created_at: string;
  steps: JobStep[];
  error?: string | null;
}

const STATUS_ICON: Record<string, string> = {
  pending: '○',
  running: '⟳',
  done: '✓',
  error: '✗',
};

const STATUS_COLOR: Record<string, string> = {
  pending: 'text-text-muted',
  running: 'text-brand',
  done: 'text-status-success',
  error: 'text-status-error',
};

interface Props {
  open: boolean;
  onClose: () => void;
}

export function ScenarioStatusPanel({ open, onClose }: Props) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const ref = useRef<HTMLDivElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useClickOutside(ref, onClose, open);

  const fetchJobs = useCallback(async () => {
    try {
      const res = await fetch('/api/upload-jobs');
      if (res.ok) {
        const data = await res.json();
        setJobs(data.jobs || []);
      }
    } catch {
      // silent
    }
  }, []);

  useEffect(() => {
    if (open) {
      fetchJobs();
      // Poll while open
      pollRef.current = setInterval(fetchJobs, 5000);
    }
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [open, fetchJobs]);

  // Stop polling when no running jobs
  useEffect(() => {
    const hasRunning = jobs.some(j => j.status === 'running' || j.status === 'pending');
    if (!hasRunning && pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, [jobs]);

  if (!open) return null;

  return (
    <div
      ref={ref}
      className="absolute top-full right-0 mt-1 w-96 bg-neutral-bg2 border border-white/10 rounded-lg shadow-xl z-50 max-h-[70vh] overflow-y-auto"
    >
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
        <span className="text-sm font-medium text-text-primary">Uploads</span>
        <button onClick={onClose} className="text-text-muted hover:text-text-primary text-xs">✕</button>
      </div>

      {jobs.length === 0 ? (
        <div className="px-4 py-8 text-center text-xs text-text-muted">
          No uploads yet.
        </div>
      ) : (
        <div className="p-3 space-y-3">
          {jobs.map(job => (
            <div key={job.id} className="bg-neutral-bg1 rounded-lg border border-white/10 p-3 space-y-2">
              {/* Header */}
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-text-primary truncate">
                  {job.scenario_name}
                </span>
                <span className={`text-xs ${STATUS_COLOR[job.status]}`}>
                  {STATUS_ICON[job.status]} {job.status === 'running' ? `${job.overall_pct}%` : job.status}
                </span>
              </div>

              {/* Progress bar for running jobs */}
              {job.status === 'running' && (
                <div className="bg-neutral-bg2 rounded-full h-1">
                  <div
                    className="bg-brand h-1 rounded-full transition-all"
                    style={{ width: `${Math.max(job.overall_pct, 3)}%` }}
                  />
                </div>
              )}

              {/* Steps tree */}
              <div className="space-y-0.5 ml-1">
                {job.steps.map((step, i) => (
                  <div key={step.name} className="flex items-start gap-1.5">
                    <span className="text-[10px] text-text-muted mt-0.5">
                      {i < job.steps.length - 1 ? '├─' : '└─'}
                    </span>
                    <span className={`text-[10px] ${STATUS_COLOR[step.status]}`}>
                      {STATUS_ICON[step.status]}
                    </span>
                    <span className="text-[10px] text-text-primary capitalize">{step.name}</span>
                    {step.detail && (
                      <span className="text-[10px] text-text-muted ml-auto truncate max-w-[140px]">
                        {step.detail}
                      </span>
                    )}
                  </div>
                ))}
              </div>

              {/* Error */}
              {job.error && (
                <p className="text-[10px] text-status-error truncate">{job.error}</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * Badge component for Header — shows count of running upload jobs.
 */
export function UploadStatusBadge({ onClick }: { onClick: () => void }) {
  const [runningCount, setRunningCount] = useState(0);

  useEffect(() => {
    const check = async () => {
      try {
        const res = await fetch('/api/upload-jobs');
        if (res.ok) {
          const data = await res.json();
          const running = (data.jobs || []).filter(
            (j: Job) => j.status === 'running' || j.status === 'pending'
          ).length;
          setRunningCount(running);
        }
      } catch {
        // silent
      }
    };
    check();
    const interval = setInterval(check, 10000);
    return () => clearInterval(interval);
  }, []);

  return (
    <button
      onClick={onClick}
      className="text-[10px] px-2 py-0.5 rounded border border-white/10 hover:bg-white/5 transition-colors text-text-muted relative"
      title="Upload status"
    >
      📤 Uploads
      {runningCount > 0 && (
        <span className="absolute -top-1 -right-1 h-3.5 w-3.5 bg-brand rounded-full flex items-center justify-center text-[8px] text-white font-bold">
          {runningCount}
        </span>
      )}
    </button>
  );
}
