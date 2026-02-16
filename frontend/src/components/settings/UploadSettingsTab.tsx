import { useRef, useState, useCallback } from 'react';
import type { ScenarioInfo } from '../../hooks/useScenarios';
import { ProgressBar } from '../ProgressBar';
import { uploadWithSSE } from '../../utils/sseStream';

// ---------------------------------------------------------------------------
// UploadBox — self-contained file-upload widget with SSE progress
// ---------------------------------------------------------------------------

interface UploadBoxProps {
  label: string;
  icon: string;
  hint: string;
  endpoint: string;
  accept: string;
  onComplete?: () => void;
}

function UploadBox({ label, icon, hint, endpoint, accept, onComplete }: UploadBoxProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [status, setStatus] = useState<'idle' | 'uploading' | 'done' | 'error'>('idle');
  const [progress, setProgress] = useState('');
  const [pct, setPct] = useState(0);
  const [result, setResult] = useState('');

  const handleFile = useCallback(async (file: File) => {
    setStatus('uploading');
    setProgress('Uploading...');
    setPct(0);
    setResult('');

    try {
      await uploadWithSSE(endpoint, file, {
        onProgress: (d) => { setProgress(d.detail || d.step); setPct(d.pct); },
        onError: (d) => { setStatus('error'); setResult(d.error); },
        onComplete: (d) => {
          setStatus('done');
          setResult(JSON.stringify(d));
          onComplete?.();
        },
      });
      // If no complete event was received but stream ended OK
      if (status !== 'done' && status !== 'error') setStatus('done');
    } catch (e) {
      setStatus('error');
      setResult(String(e));
    }
  }, [endpoint, onComplete, status]);

  return (
    <div className="bg-neutral-bg1 rounded-lg border border-white/5 p-3 space-y-2">
      <div className="flex items-center gap-2">
        <span className="text-lg">{icon}</span>
        <span className="text-sm font-medium text-text-primary">{label}</span>
        {status === 'done' && <span className="text-xs text-status-success ml-auto">✓</span>}
        {status === 'error' && <span className="text-xs text-status-error ml-auto">✗</span>}
      </div>

      {status === 'idle' && (
        <div
          className="border border-dashed border-white/20 hover:border-white/40 rounded p-3 text-center cursor-pointer transition-colors"
          onClick={() => inputRef.current?.click()}
        >
          <p className="text-xs text-text-muted">{hint}</p>
          <input ref={inputRef} type="file" accept={accept} className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); }} />
        </div>
      )}

      {status === 'uploading' && (
        <div className="space-y-1">
          <ProgressBar pct={Math.max(pct, 5)} />
          <p className="text-xs text-text-muted truncate">{progress}</p>
        </div>
      )}

      {status === 'done' && (
        <div className="text-xs text-status-success">
          Loaded successfully
          <button onClick={() => setStatus('idle')} className="ml-2 text-brand hover:text-brand/80">
            Upload again
          </button>
        </div>
      )}

      {status === 'error' && (
        <div className="text-xs text-status-error">
          {result.substring(0, 120)}
          <button onClick={() => setStatus('idle')} className="ml-2 text-brand hover:text-brand/80">
            Retry
          </button>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// UploadSettingsTab
// ---------------------------------------------------------------------------

interface UploadSettingsTabProps {
  scenarios: ScenarioInfo[];
  loading: boolean;
  fetchScenarios: () => void;
  fetchIndexes: () => void;
}

export function UploadSettingsTab({
  scenarios,
  loading,
  fetchScenarios,
  fetchIndexes,
}: UploadSettingsTabProps) {
  return (
    <>
      {/* Loaded scenarios list */}
      <div>
        <h3 className="text-sm font-semibold text-text-secondary uppercase tracking-wider mb-3">
          Loaded Data
        </h3>
        {loading ? (
          <p className="text-text-muted text-sm">Loading...</p>
        ) : scenarios.length === 0 ? (
          <p className="text-text-muted text-sm">No graphs loaded yet.</p>
        ) : (
          <div className="space-y-2">
            {scenarios.filter(s => s.has_data).map((s) => (
              <div
                key={s.graph_name}
                className="flex items-center justify-between px-4 py-2 bg-neutral-bg1 rounded-lg border border-white/5"
              >
                <div className="flex items-center gap-3">
                  <span className="h-2 w-2 rounded-full bg-status-success" />
                  <span className="text-sm text-text-primary font-medium">{s.graph_name}</span>
                </div>
                <span className="text-xs text-text-muted">{s.vertex_count} vertices</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 4 independent upload areas */}
      <div className="grid grid-cols-2 gap-3">
        <UploadBox
          label="Graph Data"
          icon="🔗"
          hint="scenario.yaml + graph_schema.yaml + data/entities/*.csv"
          endpoint="/query/upload/graph"
          accept=".tar.gz,.tgz"
          onComplete={() => fetchScenarios()}
        />
        <UploadBox
          label="Telemetry"
          icon="📊"
          hint="scenario.yaml + data/telemetry/*.csv"
          endpoint="/query/upload/telemetry"
          accept=".tar.gz,.tgz"
        />
        <UploadBox
          label="Runbooks"
          icon="📋"
          hint=".md runbook files → AI Search"
          endpoint="/query/upload/runbooks"
          accept=".tar.gz,.tgz"
          onComplete={() => fetchIndexes()}
        />
        <UploadBox
          label="Tickets"
          icon="🎫"
          hint=".txt ticket files → AI Search"
          endpoint="/query/upload/tickets"
          accept=".tar.gz,.tgz"
          onComplete={() => fetchIndexes()}
        />
        <UploadBox
          label="Prompts"
          icon="📝"
          hint=".md prompt files → Cosmos DB"
          endpoint="/query/upload/prompts"
          accept=".tar.gz,.tgz"
        />
      </div>

      <p className="text-xs text-text-muted">
        Generate tarballs: <code>./data/generate_all.sh</code>
      </p>
    </>
  );
}
