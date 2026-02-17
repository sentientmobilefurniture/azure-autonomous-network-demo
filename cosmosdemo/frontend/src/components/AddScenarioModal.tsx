import { useState, useCallback, useRef, useEffect } from 'react';
import type { SlotKey, ScenarioUploadSlot } from '../types';
import { useScenarioUpload, SLOT_DEFS } from '../hooks/useScenarioUpload';

// ---------------------------------------------------------------------------
// Helpers (UI / form validation — not upload-related)
// ---------------------------------------------------------------------------

const KNOWN_SUFFIXES: SlotKey[] = ['graph', 'telemetry', 'runbooks', 'tickets', 'prompts'];

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

interface Props {
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
  existingNames: string[];
  saveScenarioMeta: (meta: {
    name: string;
    display_name?: string;
    description?: string;
    use_cases?: string[];
    example_questions?: string[];
    graph_styles?: Record<string, unknown>;
    domain?: string;
    graph_connector?: string;
    upload_results: Record<string, unknown>;
  }) => Promise<unknown>;
}

export function AddScenarioModal({ open, onClose, onSaved, existingNames, saveScenarioMeta }: Props) {
  const [name, setName] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [description, setDescription] = useState('');
  const [showAdvanced, setShowAdvanced] = useState(false);
  const selectedBackend = 'cosmosdb-gremlin' as const;
  const dropZoneRef = useRef<HTMLDivElement>(null);

  const {
    modalState,
    globalError,
    slots,
    showOverrideConfirm,
    setShowOverrideConfirm,
    handleSlotFile,
    startUpload,
    updateSlot,
  } = useScenarioUpload({
    name,
    displayName,
    description,
    existingNames,
    selectedBackend,
    saveScenarioMeta,
    onSaved,
    onClose,
    open,
  });

  // Reset local form fields when modal opens
  useEffect(() => {
    if (open) {
      setName('');
      setDisplayName('');
      setDescription('');
      setShowAdvanced(false);
    }
  }, [open]);

  // Close on Escape (when not uploading)
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (modalState === 'uploading') return; // don't close while submitting
        onClose();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [open, modalState, onClose]);

  // Handle multi-file drop
  const handleDrop = useCallback((files: FileList | File[]) => {
    const fileArr = Array.from(files);
    const detectedNames: string[] = [];

    for (const file of fileArr) {
      const detected = detectSlot(file.name);
      if (detected) {
        handleSlotFile(detected.slot, file);
        detectedNames.push(detected.scenarioName);
      } else {
        // Can't reliably auto-assign without filename detection
        console.warn(`Could not auto-detect slot for ${file.name}`);
      }
    }

    // Auto-derive scenario name from detected filenames (always takes priority)
    if (detectedNames.length > 0) {
      // Use most common name
      const counts: Record<string, number> = {};
      for (const n of detectedNames) counts[n] = (counts[n] || 0) + 1;
      const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]);
      setName(sorted[0][0]);
    }
  }, [handleSlotFile]);

  const nameError = name ? validateName(name) : null;

  const allFilled = SLOT_DEFS.every(d => slots[d.key].file);
  const canSave = !!name && !nameError && allFilled && modalState === 'idle';

  // Handle Save button click
  const handleSave = useCallback(async () => {
    if (!canSave) return;
    startUpload();
  }, [canSave, startUpload]);

  const handleCancel = useCallback(() => {
    onClose();
  }, [onClose]);

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
            New Scenario
          </h2>
          <button
            onClick={handleCancel}
            className="text-text-muted hover:text-text-primary transition-colors text-xl leading-none"
            disabled={modalState === 'uploading'}
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
            <div className="relative">
              <input
                type="text"
                value={name}
                readOnly
                disabled={modalState !== 'idle'}
                placeholder="Detected from uploaded files"
                className="w-full bg-neutral-bg1 border border-white/10 rounded px-3 py-2 text-sm text-text-primary
                  placeholder:text-text-muted/50 focus:outline-none cursor-not-allowed opacity-75 disabled:opacity-50"
              />
              {name && (
                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted text-sm" title="Name read from scenario.yaml">
                  🔒
                </span>
              )}
            </div>
            {nameError && <p className="text-xs text-status-error mt-1">{nameError}</p>}
            {name && (
              <p className="text-xs text-text-muted mt-1 italic">
                Name detected from uploaded files — cannot be overridden
              </p>
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
                  onFile={(file) => handleSlotFile(def.key, file)}
                  onClear={() => updateSlot(def.key, { file: null, status: 'empty', progress: '', pct: 0, result: null, error: null })}
                  onRetry={slot.status === 'error' ? () => updateSlot(def.key, { status: 'staged', error: null }) : undefined}
                />
              );
            })}
          </div>

          {/* Submitting indicator */}
          {modalState === 'uploading' && (
            <div className="flex items-center gap-2 text-xs text-text-muted">
              <span className="animate-spin">⏳</span>
              <span>Submitting upload job…</span>
            </div>
          )}

          {/* Global error */}
          {globalError && (
            <div className="bg-status-error/10 border border-status-error/30 rounded-lg p-3 max-h-32 overflow-y-auto">
              <p className="text-xs text-status-error whitespace-pre-wrap">{globalError}</p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-white/10 flex justify-between">
          <button
            onClick={handleCancel}
            className="px-4 py-1.5 text-sm text-text-primary bg-white/10 hover:bg-white/15 rounded-md transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={!canSave}
            className={`px-5 py-1.5 text-sm rounded-md transition-colors ${
              canSave
                ? 'bg-brand text-white hover:bg-brand/90'
                : 'bg-white/5 text-text-muted cursor-not-allowed'
            }`}
          >
            {modalState === 'uploading' ? 'Submitting…' : 'Save Scenario'}
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
          {slot.category && (
            <p className="text-[10px] font-medium text-brand truncate">{slot.category}</p>
          )}
          <div className="h-1 bg-white/10 rounded-full overflow-hidden">
            <div className="h-full bg-brand rounded-full transition-all" style={{ width: `${Math.max(slot.pct, 5)}%` }} />
          </div>
          <p className="text-[10px] text-text-muted truncate">{slot.progress}</p>
        </div>
      )}

      {slot.status === 'done' && (
        <p className="text-[10px] text-status-success">Loaded successfully</p>
      )}

      {slot.status === 'error' && (
        <div>
          <div className="max-h-16 overflow-y-auto">
            <p className="text-[10px] text-status-error whitespace-pre-wrap">{slot.error}</p>
          </div>
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
