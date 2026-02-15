import { useState, useCallback, useRef, useEffect } from 'react';
import type { SlotKey, ScenarioUploadSlot } from '../types';
import { uploadWithSSE } from '../utils/sseStream';

// ---------------------------------------------------------------------------
// Slot configuration
// ---------------------------------------------------------------------------

const SLOT_DEFS: { key: SlotKey; label: string; icon: string; endpoint: string }[] = [
  { key: 'graph', label: 'Graph Data', icon: '🔗', endpoint: '/query/upload/graph' },
  { key: 'telemetry', label: 'Telemetry', icon: '📊', endpoint: '/query/upload/telemetry' },
  { key: 'runbooks', label: 'Runbooks', icon: '📋', endpoint: '/query/upload/runbooks' },
  { key: 'tickets', label: 'Tickets', icon: '🎫', endpoint: '/query/upload/tickets' },
  { key: 'prompts', label: 'Prompts', icon: '📝', endpoint: '/query/upload/prompts' },
];

const KNOWN_SUFFIXES: SlotKey[] = ['graph', 'telemetry', 'runbooks', 'tickets', 'prompts'];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function detectSlot(filename: string): { slot: SlotKey; scenarioName: string } | null {
  const base = filename.replace(/\.(tar\.gz|tgz)$/i, '');
  const lastDash = base.lastIndexOf('-');
  if (lastDash < 1) return null;
  const suffix = base.substring(lastDash + 1).toLowerCase() as SlotKey;
  const name = base.substring(0, lastDash);
  if (KNOWN_SUFFIXES.includes(suffix)) {
    return { slot: suffix, scenarioName: name };
  }
  return null;
}

const NAME_RE = /^[a-z0-9](?!.*--)[a-z0-9-]{0,48}[a-z0-9]$/;
const RESERVED_SUFFIXES = ['-topology', '-telemetry', '-prompts', '-runbooks', '-tickets'];

function validateName(name: string): string | null {
  if (!name) return 'Name is required';
  if (!NAME_RE.test(name)) return 'Lowercase letters, numbers, and hyphens. 2-50 chars. No consecutive hyphens.';
  for (const s of RESERVED_SUFFIXES) {
    if (name.endsWith(s)) return `Must not end with "${s}"`;
  }
  return null;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

type ModalState = 'idle' | 'uploading' | 'saving' | 'done' | 'error';

interface Props {
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
  existingNames: string[];
  saveScenarioMeta: (meta: {
    name: string;
    display_name?: string;
    description?: string;
    upload_results: Record<string, unknown>;
  }) => Promise<unknown>;
}

export function AddScenarioModal({ open, onClose, onSaved, existingNames, saveScenarioMeta }: Props) {
  const [name, setName] = useState('');
  const [nameAutoDetected, setNameAutoDetected] = useState(false);
  const [displayName, setDisplayName] = useState('');
  const [description, setDescription] = useState('');
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [slots, setSlots] = useState<Record<SlotKey, ScenarioUploadSlot>>(() => makeEmptySlots());
  const [modalState, setModalState] = useState<ModalState>('idle');
  const [overallPct, setOverallPct] = useState(0);
  const [currentUploadStep, setCurrentUploadStep] = useState('');
  const [globalError, setGlobalError] = useState('');
  const [showOverrideConfirm, setShowOverrideConfirm] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const dropZoneRef = useRef<HTMLDivElement>(null);

  // Upload timer
  const uploadStartRef = useRef<number>(0);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const timerIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  function formatElapsed(seconds: number): string {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return m > 0 ? `${m}m ${s.toString().padStart(2, '0')}s` : `${s}s`;
  }

  function stopTimer() {
    if (timerIntervalRef.current) {
      clearInterval(timerIntervalRef.current);
      timerIntervalRef.current = null;
    }
  }

  function makeEmptySlots(): Record<SlotKey, ScenarioUploadSlot> {
    const result: Partial<Record<SlotKey, ScenarioUploadSlot>> = {};
    for (const def of SLOT_DEFS) {
      result[def.key] = {
        key: def.key,
        label: def.label,
        icon: def.icon,
        file: null,
        status: 'empty',
        progress: '',
        pct: 0,
        result: null,
        error: null,
      };
    }
    return result as Record<SlotKey, ScenarioUploadSlot>;
  }

  // Reset state when modal opens
  useEffect(() => {
    if (open) {
      setName('');
      setNameAutoDetected(false);
      setDisplayName('');
      setDescription('');
      setShowAdvanced(false);
      setSlots(makeEmptySlots());
      setModalState('idle');
      setOverallPct(0);
      setCurrentUploadStep('');
      setGlobalError('');
      setShowOverrideConfirm(false);
      setElapsedSeconds(0);
      stopTimer();
    }
  }, [open]);

  // Cleanup timer on unmount
  useEffect(() => {
    return () => stopTimer();
  }, []);

  // Close on Escape (when not uploading)
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (modalState === 'uploading') return; // don't close during upload
        onClose();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [open, modalState, onClose]);

  const updateSlot = useCallback((key: SlotKey, updates: Partial<ScenarioUploadSlot>) => {
    setSlots(prev => ({ ...prev, [key]: { ...prev[key], ...updates } }));
  }, []);

  // Assign a file to a slot
  const assignFile = useCallback((key: SlotKey, file: File) => {
    updateSlot(key, { file, status: 'staged', progress: '', pct: 0, result: null, error: null });
  }, [updateSlot]);

  // Handle multi-file drop
  const handleDrop = useCallback((files: FileList | File[]) => {
    const fileArr = Array.from(files);
    const detectedNames: string[] = [];

    for (const file of fileArr) {
      const detected = detectSlot(file.name);
      if (detected) {
        assignFile(detected.slot, file);
        detectedNames.push(detected.scenarioName);
      } else {
        // Can't reliably auto-assign without filename detection
        console.warn(`Could not auto-detect slot for ${file.name}`);
      }
    }

    // Auto-derive scenario name if name field is empty
    if (!name && detectedNames.length > 0) {
      // Use most common name
      const counts: Record<string, number> = {};
      for (const n of detectedNames) counts[n] = (counts[n] || 0) + 1;
      const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]);
      setName(sorted[0][0]);
      setNameAutoDetected(true);
    }
  }, [assignFile, name]);

  const nameError = name ? validateName(name) : null;

  // Compute mismatch hint
  const detectedNamesFromSlots = Object.values(slots)
    .filter(s => s.file)
    .map(s => detectSlot(s.file!.name)?.scenarioName)
    .filter(Boolean) as string[];
  const mismatchHint = name && detectedNamesFromSlots.length > 0 &&
    detectedNamesFromSlots.some(n => n !== name)
    ? `File names suggest "${detectedNamesFromSlots[0]}" but resources will be created as "${name}".`
    : null;

  const allFilled = SLOT_DEFS.every(d => slots[d.key].file);
  const canSave = !!name && !nameError && allFilled && modalState === 'idle';

  // Check if all previously completed slots are done (for retry scenario)
  const allDone = SLOT_DEFS.every(d => slots[d.key].status === 'done');

  // Handle Save button click
  const handleSave = useCallback(async () => {
    if (!canSave && !allDone) return;

    // Check if scenario already exists — show confirmation
    if (existingNames.includes(name) && !showOverrideConfirm) {
      setShowOverrideConfirm(true);
      return;
    }
    setShowOverrideConfirm(false);

    setModalState('uploading');
    setGlobalError('');
    abortRef.current = new AbortController();

    // Start upload timer
    uploadStartRef.current = Date.now();
    setElapsedSeconds(0);
    timerIntervalRef.current = setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - uploadStartRef.current) / 1000));
    }, 1000);

    const uploadResults: Record<string, unknown> = {};

    // Upload sequentially: graph → telemetry → runbooks → tickets → prompts
    for (let i = 0; i < SLOT_DEFS.length; i++) {
      const def = SLOT_DEFS[i];
      const slot = slots[def.key];

      // Skip already-done slots (for retry)
      if (slot.status === 'done') {
        uploadResults[def.key] = slot.result;
        continue;
      }

      if (!slot.file) continue;

      updateSlot(def.key, { status: 'uploading', progress: 'Starting...', pct: 0 });
      setCurrentUploadStep(`Uploading ${def.label}...`);

      try {
        const result = await uploadWithSSE(
          def.endpoint,
          slot.file,
          {
            onProgress: (data) => {
              updateSlot(def.key, { progress: data.detail, pct: data.pct });
              const overallBase = (i / SLOT_DEFS.length) * 100;
              const slotContribution = (data.pct / 100) * (100 / SLOT_DEFS.length);
              setOverallPct(Math.round(overallBase + slotContribution));
            },
            onComplete: (data) => {
              updateSlot(def.key, { status: 'done', result: data, progress: 'Complete', pct: 100 });
              uploadResults[def.key] = data;
            },
            onError: (data) => {
              updateSlot(def.key, { status: 'error', error: data.error });
            },
          },
          { scenario_name: name },
          abortRef.current!.signal,
        );

        // If no complete event was received but no error either, mark as done
        if (slot.status !== 'error' && result) {
          uploadResults[def.key] = result;
        }

        // Check if the slot errored (set by onError handler)
        if (slots[def.key]?.status === 'error') {
          setModalState('idle');
          return;
        }
      } catch (e) {
        if (e instanceof DOMException && e.name === 'AbortError') {
          setModalState('idle');
          return;
        }
        updateSlot(def.key, { status: 'error', error: String(e) });
        setModalState('idle');
        return;
      }
    }

    // All uploads done, save metadata
    setModalState('saving');
    setCurrentUploadStep('Saving scenario metadata...');
    setOverallPct(95);

    try {
      await saveScenarioMeta({
        name,
        display_name: displayName || undefined,
        description: description || undefined,
        upload_results: uploadResults,
      });
      setModalState('done');
      setOverallPct(100);
      stopTimer();
      // Auto-close after brief delay
      setTimeout(() => {
        onSaved();
        onClose();
      }, 1500);
    } catch (e) {
      setGlobalError(String(e));
      setModalState('error');
      stopTimer();
    }
  }, [canSave, allDone, existingNames, name, showOverrideConfirm, slots, updateSlot, saveScenarioMeta, displayName, description, onSaved, onClose]);

  const handleCancel = useCallback(() => {
    if (modalState === 'uploading') {
      abortRef.current?.abort();
      stopTimer();
      setModalState('idle');
    } else {
      onClose();
    }
  }, [modalState, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === e.currentTarget && modalState !== 'uploading') onClose();
      }}
    >
      <div
        className="bg-neutral-bg2 border border-white/10 rounded-xl w-full max-w-xl max-h-[90vh] flex flex-col shadow-2xl"
        role="dialog"
        aria-modal="true"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 pt-5 pb-3 border-b border-white/10">
          <h2 className="text-lg font-semibold text-text-primary">
            {modalState === 'done' ? '✓ Scenario Saved' : 'New Scenario'}
          </h2>
          <button
            onClick={handleCancel}
            className="text-text-muted hover:text-text-primary transition-colors text-xl leading-none"
            disabled={modalState === 'saving'}
          >
            ✕
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          {/* Override Confirmation */}
          {showOverrideConfirm && (
            <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-4 space-y-3">
              <p className="text-sm text-yellow-400 font-medium">⚠ Scenario Already Exists</p>
              <p className="text-xs text-text-secondary">
                "{name}" already exists. Saving will overwrite all data.
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => setShowOverrideConfirm(false)}
                  className="px-3 py-1 text-xs bg-white/10 rounded hover:bg-white/15 text-text-primary"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSave}
                  className="px-3 py-1 text-xs bg-yellow-600 rounded hover:bg-yellow-700 text-white"
                >
                  Overwrite & Continue
                </button>
              </div>
            </div>
          )}

          {/* Scenario Name */}
          <div>
            <label className="text-xs text-text-muted block mb-1">Scenario Name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => {
                setName(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ''));
                setNameAutoDetected(false);
              }}
              disabled={modalState !== 'idle'}
              placeholder="cloud-outage"
              className="w-full bg-neutral-bg1 border border-white/10 rounded px-3 py-2 text-sm text-text-primary
                placeholder:text-text-muted/50 focus:outline-none focus:border-brand/50 disabled:opacity-50"
            />
            {nameError && <p className="text-xs text-status-error mt-1">{nameError}</p>}
            {nameAutoDetected && !nameError && (
              <p className="text-xs text-text-muted mt-1 italic">Auto-detected from filename — edit freely</p>
            )}
            {mismatchHint && !nameError && (
              <p className="text-xs text-yellow-400/80 mt-1">ⓘ {mismatchHint}</p>
            )}
          </div>

          {/* Advanced (collapsed) */}
          <button
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="text-xs text-text-muted hover:text-text-secondary flex items-center gap-1"
          >
            <span>{showAdvanced ? '▾' : '▸'}</span>
            Display Name & Description (optional)
          </button>
          {showAdvanced && (
            <div className="space-y-3 pl-3 border-l border-white/5">
              <div>
                <label className="text-xs text-text-muted block mb-1">Display Name</label>
                <input
                  type="text"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  disabled={modalState !== 'idle'}
                  placeholder={name ? name.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) : ''}
                  className="w-full bg-neutral-bg1 border border-white/10 rounded px-3 py-1.5 text-sm text-text-primary
                    placeholder:text-text-muted/50 focus:outline-none focus:border-brand/50 disabled:opacity-50"
                />
              </div>
              <div>
                <label className="text-xs text-text-muted block mb-1">Description</label>
                <input
                  type="text"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  disabled={modalState !== 'idle'}
                  placeholder="Brief scenario description"
                  className="w-full bg-neutral-bg1 border border-white/10 rounded px-3 py-1.5 text-sm text-text-primary
                    placeholder:text-text-muted/50 focus:outline-none focus:border-brand/50 disabled:opacity-50"
                />
              </div>
            </div>
          )}

          {/* Multi-drop zone */}
          <div className="text-xs text-text-muted font-medium uppercase tracking-wider">Upload Data Files</div>
          <div
            ref={dropZoneRef}
            className={`border-2 border-dashed rounded-lg p-4 text-center transition-colors cursor-pointer
              ${modalState !== 'idle' ? 'opacity-50 pointer-events-none' : 'border-white/15 hover:border-white/30'}`}
            onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); }}
            onDrop={(e) => {
              e.preventDefault();
              e.stopPropagation();
              if (modalState !== 'idle') return;
              handleDrop(e.dataTransfer.files);
            }}
            onClick={() => {
              if (modalState !== 'idle') return;
              const input = document.createElement('input');
              input.type = 'file';
              input.multiple = true;
              input.accept = '.tar.gz,.tgz';
              input.onchange = () => {
                if (input.files) handleDrop(input.files);
              };
              input.click();
            }}
          >
            <p className="text-sm text-text-muted">📂 Drop all 5 tarballs here, or click to browse</p>
          </div>

          {/* Individual file slots */}
          <div className="grid grid-cols-2 gap-3">
            {SLOT_DEFS.map((def) => {
              const slot = slots[def.key];
              return (
                <FileSlot
                  key={def.key}
                  def={def}
                  slot={slot}
                  disabled={modalState !== 'idle'}
                  onFile={(file) => assignFile(def.key, file)}
                  onClear={() => updateSlot(def.key, { file: null, status: 'empty', progress: '', pct: 0, result: null, error: null })}
                  onRetry={slot.status === 'error' ? () => updateSlot(def.key, { status: 'staged', error: null }) : undefined}
                />
              );
            })}
          </div>

          {/* Upload Progress */}
          {(modalState === 'uploading' || modalState === 'saving') && (
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs text-text-muted">
                <span>{currentUploadStep}</span>
                <span>{overallPct}%</span>
              </div>
              <div className="w-full bg-neutral-bg1 rounded-full h-1.5">
                <div
                  className="bg-brand h-1.5 rounded-full transition-all duration-300"
                  style={{ width: `${Math.max(overallPct, 3)}%` }}
                />
              </div>
              <div className="flex items-center justify-between mt-1">
                <span className="text-xs text-text-secondary">
                  Overall: {SLOT_DEFS.filter(d => slots[d.key].status === 'done').length} of {SLOT_DEFS.length}
                </span>
                <span className={`text-xs font-mono tabular-nums ${
                  elapsedSeconds > 30 ? 'text-text-secondary' : 'text-text-muted'
                }`}>
                  ⏱ {formatElapsed(elapsedSeconds)}
                </span>
              </div>
            </div>
          )}

          {/* Done message */}
          {modalState === 'done' && (
            <div className="bg-status-success/10 border border-status-success/30 rounded-lg p-3 text-center">
              <p className="text-sm text-status-success">Scenario "{name}" saved successfully</p>
              <p className="text-xs text-status-success/70 mt-1 font-mono tabular-nums">
                Total: {formatElapsed(elapsedSeconds)}
              </p>
            </div>
          )}

          {/* Global error */}
          {globalError && (
            <div className="bg-status-error/10 border border-status-error/30 rounded-lg p-3">
              <p className="text-xs text-status-error">{globalError}</p>
            </div>
          )}

          {/* First-time warning */}
          {modalState === 'uploading' && (
            <p className="text-xs text-text-muted">
              ⓘ First-time setup may take 3-5 minutes while Azure resources are created.
              Subsequent uploads will be faster.
            </p>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-white/10 flex justify-between">
          <button
            onClick={handleCancel}
            className="px-4 py-1.5 text-sm text-text-primary bg-white/10 hover:bg-white/15 rounded-md transition-colors"
          >
            {modalState === 'uploading' ? 'Cancel Upload' : 'Cancel'}
          </button>
          <button
            onClick={handleSave}
            disabled={!canSave && !allDone}
            className={`px-5 py-1.5 text-sm rounded-md transition-colors ${
              canSave || allDone
                ? 'bg-brand text-white hover:bg-brand/90'
                : 'bg-white/5 text-text-muted cursor-not-allowed'
            }`}
          >
            {modalState === 'saving' ? 'Saving...' :
             modalState === 'done' ? '✓ Saved' :
             modalState === 'uploading' ? 'Uploading...' :
             'Save Scenario'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// File Slot sub-component
// ---------------------------------------------------------------------------

function FileSlot({ def, slot, disabled, onFile, onClear, onRetry }: {
  def: { key: SlotKey; label: string; icon: string };
  slot: ScenarioUploadSlot;
  disabled: boolean;
  onFile: (file: File) => void;
  onClear: () => void;
  onRetry?: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);

  const borderClass =
    slot.status === 'done' ? 'border-status-success/40' :
    slot.status === 'error' ? 'border-status-error/40' :
    slot.status === 'uploading' ? 'border-brand/40 animate-pulse' :
    slot.status === 'staged' ? 'border-white/20' :
    'border-dashed border-white/10';

  return (
    <div className={`bg-neutral-bg1 rounded-lg border ${borderClass} p-3 space-y-1.5 relative`}>
      <div className="flex items-center gap-2">
        <span className="text-base">{def.icon}</span>
        <span className="text-xs font-medium text-text-primary">{def.label}</span>
        {slot.status === 'done' && <span className="text-xs text-status-success ml-auto">✓</span>}
        {slot.status === 'error' && <span className="text-xs text-status-error ml-auto">✗</span>}
      </div>

      {slot.status === 'empty' && (
        <div
          className={`text-center py-2 cursor-pointer ${disabled ? 'opacity-50 pointer-events-none' : ''}`}
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); }}
          onDrop={(e) => {
            e.preventDefault();
            e.stopPropagation();
            const f = e.dataTransfer.files[0];
            if (f) onFile(f);
          }}
        >
          <p className="text-[10px] text-text-muted">— not selected —</p>
          <input
            ref={inputRef}
            type="file"
            accept=".tar.gz,.tgz"
            className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f); }}
          />
        </div>
      )}

      {slot.status === 'staged' && slot.file && (
        <div className="flex items-center justify-between">
          <div className="min-w-0">
            <p className="text-[10px] text-text-secondary truncate">{slot.file.name}</p>
            <p className="text-[10px] text-text-muted">{formatBytes(slot.file.size)}</p>
          </div>
          {!disabled && (
            <button onClick={onClear} className="text-text-muted hover:text-text-primary text-xs ml-2 flex-shrink-0">
              ✕
            </button>
          )}
        </div>
      )}

      {slot.status === 'uploading' && (
        <div className="space-y-1">
          <div className="w-full bg-neutral-bg2 rounded-full h-1">
            <div className="bg-brand h-1 rounded-full transition-all" style={{ width: `${Math.max(slot.pct, 5)}%` }} />
          </div>
          <p className="text-[10px] text-text-muted truncate">{slot.progress}</p>
        </div>
      )}

      {slot.status === 'done' && (
        <p className="text-[10px] text-status-success">Loaded successfully</p>
      )}

      {slot.status === 'error' && (
        <div>
          <p className="text-[10px] text-status-error truncate">{slot.error}</p>
          {onRetry && (
            <button onClick={onRetry} className="text-[10px] text-brand hover:text-brand/80 mt-1">
              Retry
            </button>
          )}
        </div>
      )}
    </div>
  );
}
