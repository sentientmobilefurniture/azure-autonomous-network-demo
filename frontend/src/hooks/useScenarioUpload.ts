import { useState, useCallback, useEffect } from 'react';
import type { SlotKey, ScenarioUploadSlot } from '../types';

// ---------------------------------------------------------------------------
// Slot configuration
// ---------------------------------------------------------------------------

export const SLOT_DEFS: { key: SlotKey; label: string; icon: string }[] = [
  { key: 'graph', label: 'Graph Data', icon: '🔗' },
  { key: 'telemetry', label: 'Telemetry', icon: '📊' },
  { key: 'runbooks', label: 'Runbooks', icon: '📋' },
  { key: 'tickets', label: 'Tickets', icon: '🎫' },
  { key: 'prompts', label: 'Prompts', icon: '📝' },
];

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Post-refactor: uploading is the brief POST; 'saving'/'done' are gone. */
export type ModalState = 'idle' | 'uploading' | 'error';

export interface UseScenarioUploadProps {
  name: string;
  displayName: string;
  description: string;
  existingNames: string[];
  selectedBackend: 'cosmosdb-gremlin' | 'fabric-gql';
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
  onSaved: () => void;
  onClose: () => void;
  open: boolean;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

export function makeEmptySlots(): Record<SlotKey, ScenarioUploadSlot> {
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

export function formatElapsed(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return m > 0 ? `${m}m ${s.toString().padStart(2, '0')}s` : `${s}s`;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useScenarioUpload(props: UseScenarioUploadProps) {
  const { name, displayName, description, existingNames, selectedBackend, saveScenarioMeta, onSaved, onClose, open } = props;

  const [modalState, setModalState] = useState<ModalState>('idle');
  const [globalError, setGlobalError] = useState('');
  const [slots, setSlots] = useState<Record<SlotKey, ScenarioUploadSlot>>(() => makeEmptySlots());
  const [showOverrideConfirm, setShowOverrideConfirm] = useState(false);

  // ------- reset -------

  const reset = useCallback(() => {
    setSlots(makeEmptySlots());
    setModalState('idle');
    setGlobalError('');
    setShowOverrideConfirm(false);
  }, []);

  // Auto-reset when modal opens
  useEffect(() => {
    if (open) reset();
  }, [open, reset]);

  // ------- slot helpers -------

  const updateSlot = useCallback((key: SlotKey, updates: Partial<ScenarioUploadSlot>) => {
    setSlots(prev => ({ ...prev, [key]: { ...prev[key], ...updates } }));
  }, []);

  const handleSlotFile = useCallback((key: SlotKey, file: File) => {
    updateSlot(key, { file, status: 'staged', progress: '', pct: 0, result: null, error: null });
  }, [updateSlot]);

  // ------- upload: single POST to background job API -------

  const startUpload = useCallback(async () => {
    // Check if scenario already exists — show confirmation dialog
    if (existingNames.includes(name) && !showOverrideConfirm) {
      setShowOverrideConfirm(true);
      return;
    }
    setShowOverrideConfirm(false);

    setModalState('uploading');
    setGlobalError('');

    try {
      // Build multipart form with all staged files
      const formData = new FormData();
      formData.append('scenario_name', name);
      formData.append('backend', selectedBackend);

      // Derive telemetry backend from graph backend selection
      const telemetryBackend = selectedBackend === 'fabric-gql' ? 'fabric-kql' : 'cosmosdb-nosql';
      formData.append('telemetry_backend', telemetryBackend);

      // For Fabric uploads, resolve active workspace from connection panel
      if (selectedBackend === 'fabric-gql') {
        try {
          const connResp = await fetch('/query/fabric/connections');
          if (connResp.ok) {
            const connData = await connResp.json();
            const active = (connData.connections || []).find((c: { active: boolean }) => c.active);
            if (active) {
              formData.append('workspace_id', active.workspace_id || '');
              formData.append('workspace_name', active.workspace_name || '');
            }
          }
        } catch {
          // Best-effort — job will proceed without workspace info
        }
      }

      // Append each staged file
      for (const def of SLOT_DEFS) {
        const slot = slots[def.key];
        if (slot.file) {
          formData.append(def.key, slot.file);
        }
      }

      // Submit to background job API
      const resp = await fetch('/api/upload-jobs', { method: 'POST', body: formData });
      if (!resp.ok) {
        const text = await resp.text();
        throw new Error(`Upload submission failed (${resp.status}): ${text}`);
      }

      // Save scenario metadata (basic — job will enrich later)
      try {
        await saveScenarioMeta({
          name,
          display_name: displayName || undefined,
          description: description || undefined,
          graph_connector: selectedBackend === 'fabric-gql' ? 'fabric-gql' : undefined,
          upload_results: {},
        });
      } catch (e: unknown) {
        // Check for 409 backend conflict
        const errMsg = e instanceof Error ? e.message : String(e);
        if (errMsg.includes('409')) {
          // Try to parse structured detail from the error text
          try {
            const jsonMatch = errMsg.match(/\{[\s\S]*\}/);
            if (jsonMatch) {
              const body = JSON.parse(jsonMatch[0]);
              const detail = body?.detail || body;
              setGlobalError(
                `Backend conflict: ${detail?.message || 'Scenario exists with a different backend.'} ${detail?.suggestion || 'Use a different name.'}`
              );
            } else {
              setGlobalError('Backend conflict: This scenario already exists with a different graph backend. Use a different name (e.g. add "-fabric" suffix).');
            }
          } catch {
            setGlobalError('Backend conflict: This scenario already exists with a different graph backend. Use a different name (e.g. add "-fabric" suffix).');
          }
          setModalState('error');
          return;
        }
        console.warn('Failed to save scenario metadata:', e);
      }

      // Job submitted — close modal immediately
      onSaved();
      onClose();
    } catch (e) {
      setGlobalError(String(e));
      setModalState('error');
    }
  }, [existingNames, name, showOverrideConfirm, selectedBackend, slots, saveScenarioMeta, displayName, description, onSaved, onClose]);

  return {
    modalState,
    globalError,
    slots,
    showOverrideConfirm,
    setShowOverrideConfirm,
    handleSlotFile,
    startUpload,
    reset,
    updateSlot,
  };
}
