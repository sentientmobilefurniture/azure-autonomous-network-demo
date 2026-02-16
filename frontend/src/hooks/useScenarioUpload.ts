import { useState, useCallback, useRef, useEffect } from 'react';
import type { SlotKey, ScenarioUploadSlot } from '../types';
import { uploadWithSSE } from '../utils/sseStream';

// ---------------------------------------------------------------------------
// Slot configuration
// ---------------------------------------------------------------------------

export const SLOT_DEFS: { key: SlotKey; label: string; icon: string; endpoint: string }[] = [
  { key: 'graph', label: 'Graph Data', icon: '🔗', endpoint: '/query/upload/graph' },
  { key: 'telemetry', label: 'Telemetry', icon: '📊', endpoint: '/query/upload/telemetry' },
  { key: 'runbooks', label: 'Runbooks', icon: '📋', endpoint: '/query/upload/runbooks' },
  { key: 'tickets', label: 'Tickets', icon: '🎫', endpoint: '/query/upload/tickets' },
  { key: 'prompts', label: 'Prompts', icon: '📝', endpoint: '/query/upload/prompts' },
];

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ModalState = 'idle' | 'uploading' | 'saving' | 'done' | 'error';

export interface UseScenarioUploadProps {
  name: string;
  displayName: string;
  description: string;
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
  const { name, displayName, description, existingNames, saveScenarioMeta, onSaved, onClose, open } = props;

  const [modalState, setModalState] = useState<ModalState>('idle');
  const [overallPct, setOverallPct] = useState(0);
  const [currentUploadStep, setCurrentUploadStep] = useState('');
  const [globalError, setGlobalError] = useState('');
  const [slots, setSlots] = useState<Record<SlotKey, ScenarioUploadSlot>>(() => makeEmptySlots());
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [showOverrideConfirm, setShowOverrideConfirm] = useState(false);
  const [detectedConnector, setDetectedConnector] = useState<string | null>(null);

  const scenarioMetadataRef = useRef<Record<string, unknown> | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const uploadStartRef = useRef<number>(0);
  const timerIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ------- timer helpers -------

  function stopTimer() {
    if (timerIntervalRef.current) {
      clearInterval(timerIntervalRef.current);
      timerIntervalRef.current = null;
    }
  }

  // ------- reset -------

  const reset = useCallback(() => {
    setSlots(makeEmptySlots());
    setModalState('idle');
    setOverallPct(0);
    setCurrentUploadStep('');
    setGlobalError('');
    setShowOverrideConfirm(false);
    setDetectedConnector(null);
    scenarioMetadataRef.current = null;
    setElapsedSeconds(0);
    stopTimer();
  }, []);

  // Auto-reset when modal opens
  useEffect(() => {
    if (open) reset();
  }, [open, reset]);

  // Cleanup timer on unmount
  useEffect(() => {
    return () => stopTimer();
  }, []);

  // ------- slot helpers -------

  const updateSlot = useCallback((key: SlotKey, updates: Partial<ScenarioUploadSlot>) => {
    setSlots(prev => ({ ...prev, [key]: { ...prev[key], ...updates } }));
  }, []);

  const handleSlotFile = useCallback((key: SlotKey, file: File) => {
    updateSlot(key, { file, status: 'staged', progress: '', pct: 0, result: null, error: null });
  }, [updateSlot]);

  // ------- derived state -------

  const allDone = SLOT_DEFS.every(d => slots[d.key].status === 'done');

  // ------- upload -------

  const startUpload = useCallback(async () => {
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
              updateSlot(def.key, { progress: data.detail, pct: data.pct, category: data.category });
              setCurrentUploadStep(data.category ? `${def.label}: ${data.category}` : `Uploading ${def.label}...`);
              const overallBase = (i / SLOT_DEFS.length) * 100;
              const slotContribution = (data.pct / 100) * (100 / SLOT_DEFS.length);
              setOverallPct(Math.round(overallBase + slotContribution));
            },
            onComplete: (data) => {
              updateSlot(def.key, { status: 'done', result: data, progress: 'Complete', pct: 100 });
              uploadResults[def.key] = data;
              // Capture metadata from graph upload for save call
              if (def.key === 'graph' && data.scenario_metadata) {
                scenarioMetadataRef.current = data.scenario_metadata as Record<string, unknown>;
                // Detect connector type from uploaded manifest
                const meta = data.scenario_metadata as Record<string, unknown>;
                const ds = meta?.data_sources as Record<string, unknown> | undefined;
                const graphDs = ds?.graph as Record<string, unknown> | undefined;
                const connector = (meta?.graph_connector as string)
                  || (graphDs?.connector as string)
                  || null;
                if (connector) setDetectedConnector(connector);
              }
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
      const meta = scenarioMetadataRef.current;
      await saveScenarioMeta({
        name,
        display_name: (meta?.display_name as string) || displayName || undefined,
        description: (meta?.description as string) || description || undefined,
        use_cases: meta?.use_cases as string[] | undefined,
        example_questions: meta?.example_questions as string[] | undefined,
        graph_styles: meta?.graph_styles as Record<string, unknown> | undefined,
        domain: meta?.domain as string | undefined,
        graph_connector: detectedConnector || undefined,
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
  }, [existingNames, name, showOverrideConfirm, slots, updateSlot, saveScenarioMeta, displayName, description, detectedConnector, onSaved, onClose]);

  // ------- cancel -------

  const cancelUpload = useCallback(() => {
    if (modalState === 'uploading') {
      abortRef.current?.abort();
      stopTimer();
      setModalState('idle');
    }
  }, [modalState]);

  return {
    modalState,
    overallPct,
    currentUploadStep,
    globalError,
    slots,
    elapsedSeconds,
    showOverrideConfirm,
    setShowOverrideConfirm,
    handleSlotFile,
    startUpload,
    reset,
    scenarioMetadataRef,
    detectedConnector,
    updateSlot,
    cancelUpload,
    allDone,
  };
}
