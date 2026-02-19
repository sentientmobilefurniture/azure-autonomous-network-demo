import { useState, useRef, useCallback } from 'react';
import { fetchEventSource } from '@microsoft/fetch-event-source';
import type { StepEvent, ThinkingState, RunMeta } from '../types';

const DEFAULT_ALERT =
  '14:31:14.259 CRITICAL VPN-ACME-CORP SERVICE_DEGRADATION VPN tunnel unreachable — primary MPLS path down';

export function useInvestigation() {
  const [alert, setAlert] = useState(DEFAULT_ALERT);
  const [steps, setSteps] = useState<StepEvent[]>([]);
  const [thinking, setThinking] = useState<ThinkingState | null>(null);
  const [finalMessage, setFinalMessage] = useState('');
  const [errorMessage, setErrorMessage] = useState('');
  const [running, setRunning] = useState(false);
  const [runStarted, setRunStarted] = useState(false);
  const [runMeta, setRunMeta] = useState<RunMeta | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const startTimeRef = useRef<number>(0);
  const stepCountRef = useRef<number>(0);
  const alertRef = useRef(alert);
  alertRef.current = alert;

  const submitAlert = useCallback(async () => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    setSteps([]);
    setThinking(null);
    setFinalMessage('');
    setErrorMessage('');
    setRunning(true);
    setRunStarted(false);
    setRunMeta(null);
    startTimeRef.current = Date.now();
    stepCountRef.current = 0;

    // Auto-abort after 5 minutes to prevent indefinite "processing..." hangs
    const timeoutId = setTimeout(() => {
      setErrorMessage('Investigation timed out after 5 minutes.');
      ctrl.abort();
    }, 300_000);

    try {
      await fetchEventSource('/api/alert', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: alertRef.current }),
        signal: ctrl.signal,

        onopen: async (res) => {
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
        },

        onmessage: (ev) => {
          if (!ev.event || !ev.data) return;
          try {
            const data = JSON.parse(ev.data);
            switch (ev.event) {
              case 'run_start':
                setRunStarted(true);
                break;
              case 'step_thinking':
                setThinking(data as ThinkingState);
                break;
              case 'step_start':
                setThinking({ agent: data.agent, status: 'processing...' });
                break;
              case 'step_complete':
                setThinking(null);
                stepCountRef.current += 1;
                setSteps((prev) => [...prev, data as StepEvent]);
                break;
              case 'message':
                setThinking(null);
                setFinalMessage(data.text);
                break;
              case 'run_complete': {
                setThinking(null);
                const elapsed = ((Date.now() - startTimeRef.current) / 1000).toFixed(0);
                setRunMeta({
                  steps: stepCountRef.current,
                  time: `${elapsed}s`,
                });
                break;
              }
              case 'error':
                setThinking(null);
                setErrorMessage(data.message);
                break;
            }
          } catch (parseErr) {
            console.warn('Failed to parse SSE data:', ev.data, parseErr);
          }
        },

        onerror: (err) => {
          console.error('SSE error:', err);
          throw err;
        },

        openWhenHidden: true,
      });
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      console.error('SSE stream error:', err);
      setErrorMessage((prev) => prev || 'Connection to server lost — the investigation may still be running. Try again.');
    } finally {
      clearTimeout(timeoutId);
      setThinking(null);
      setRunning(false);
      // Ensure runMeta is set with correct step count from ref
      setRunMeta((m) => ({
        steps: stepCountRef.current,
        time: m?.time ?? `${((Date.now() - startTimeRef.current) / 1000).toFixed(0)}s`,
      }));
    }
  }, []);

  const resetInvestigation = useCallback(() => {
    abortRef.current?.abort();
    setSteps([]);
    setThinking(null);
    setFinalMessage('');
    setErrorMessage('');
    setRunning(false);
    setRunStarted(false);
    setRunMeta(null);
  }, []);

  const cancelInvestigation = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return {
    alert,
    setAlert,
    steps,
    thinking,
    finalMessage,
    errorMessage,
    running,
    runStarted,
    runMeta,
    submitAlert,
    resetInvestigation,
    cancelInvestigation,
  };
}
