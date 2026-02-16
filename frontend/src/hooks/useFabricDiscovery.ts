/**
 * Hook for Fabric workspace resource discovery (V11).
 *
 * Calls /query/fabric/* discovery endpoints to list ontologies,
 * graph models, eventhouses, and other Fabric workspace items.
 * Also calls /api/fabric/* for provisioning operations.
 */

import { useState, useCallback } from 'react';
import type { FabricItem } from '../types';
import { consumeSSE } from '../utils/sseStream';

export interface FabricDiscoveryState {
  /** Fabric workspace connectivity status */
  healthy: boolean | null;
  /** Whether a health check is in progress */
  checking: boolean;

  /** Ontologies in the workspace */
  ontologies: FabricItem[];
  /** Graph models for a selected ontology */
  graphModels: FabricItem[];
  /** Eventhouses in the workspace */
  eventhouses: FabricItem[];

  /** Currently loading section */
  loadingSection: string | null;
  /** Last error message */
  error: string | null;

  /** Provision pipeline progress (0-100) */
  provisionPct: number;
  /** Provision pipeline step description */
  provisionStep: string;
  /** Provision pipeline state */
  provisionState: 'idle' | 'running' | 'done' | 'error';
  /** Provision error message */
  provisionError: string | null;
}

export function useFabricDiscovery() {
  const [healthy, setHealthy] = useState<boolean | null>(null);
  const [checking, setChecking] = useState(false);

  const [ontologies, setOntologies] = useState<FabricItem[]>([]);
  const [graphModels, setGraphModels] = useState<FabricItem[]>([]);
  const [eventhouses, setEventhouses] = useState<FabricItem[]>([]);

  const [loadingSection, setLoadingSection] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [provisionPct, setProvisionPct] = useState(0);
  const [provisionStep, setProvisionStep] = useState('');
  const [provisionState, setProvisionState] = useState<'idle' | 'running' | 'done' | 'error'>('idle');
  const [provisionError, setProvisionError] = useState<string | null>(null);

  // -- Health check --
  const checkHealth = useCallback(async () => {
    setChecking(true);
    setError(null);
    try {
      const res = await fetch('/query/fabric/health');
      const data = await res.json();
      setHealthy(data.configured === true);
      if (!data.configured) {
        setError('Fabric not fully configured');
      }
    } catch (e) {
      setHealthy(false);
      setError(`Health check failed: ${e}`);
    } finally {
      setChecking(false);
    }
  }, []);

  // -- Fetch ontologies --
  const fetchOntologies = useCallback(async () => {
    setLoadingSection('ontologies');
    setError(null);
    try {
      const res = await fetch('/query/fabric/ontologies');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setOntologies(Array.isArray(data) ? data : []);
    } catch (e) {
      setError(`Failed to fetch ontologies: ${e}`);
    } finally {
      setLoadingSection(null);
    }
  }, []);

  // -- Fetch graph models for an ontology --
  const fetchGraphModels = useCallback(async (ontologyId: string) => {
    setLoadingSection('graphModels');
    setError(null);
    try {
      const res = await fetch(`/query/fabric/ontologies/${encodeURIComponent(ontologyId)}/models`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setGraphModels(Array.isArray(data) ? data : []);
    } catch (e) {
      setError(`Failed to fetch graph models: ${e}`);
    } finally {
      setLoadingSection(null);
    }
  }, []);

  // -- Fetch eventhouses --
  const fetchEventhouses = useCallback(async () => {
    setLoadingSection('eventhouses');
    setError(null);
    try {
      const res = await fetch('/query/fabric/eventhouses');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setEventhouses(Array.isArray(data) ? data : []);
    } catch (e) {
      setError(`Failed to fetch eventhouses: ${e}`);
    } finally {
      setLoadingSection(null);
    }
  }, []);

  // -- Run full provision pipeline (SSE) --
  const runProvisionPipeline = useCallback(async (opts?: {
    workspace_name?: string;
    lakehouse_name?: string;
    eventhouse_name?: string;
    ontology_name?: string;
    scenario_name?: string;
  }) => {
    setProvisionState('running');
    setProvisionPct(0);
    setProvisionStep('Starting...');
    setProvisionError(null);

    try {
      const res = await fetch('/api/fabric/provision', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(opts || {}),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      let receivedTerminalEvent = false;

      await consumeSSE(res, {
        onProgress: (data) => {
          setProvisionPct(data.pct);
          setProvisionStep(data.detail || data.step);
        },
        onComplete: () => {
          receivedTerminalEvent = true;
          setProvisionState('done');
          setProvisionPct(100);
          setProvisionStep('Complete');
        },
        onError: (data) => {
          receivedTerminalEvent = true;
          setProvisionState('error');
          setProvisionError(data.error);
        },
      });

      // If no complete/error event was received but stream ended OK
      if (!receivedTerminalEvent) {
        setProvisionState('done');
        setProvisionPct(100);
      }
    } catch (e) {
      setProvisionState('error');
      setProvisionError(String(e));
    }
  }, []);

  // -- Fetch all discovery data at once --
  const fetchAll = useCallback(async () => {
    await checkHealth();
    await Promise.all([fetchOntologies(), fetchEventhouses()]);
  }, [checkHealth, fetchOntologies, fetchEventhouses]);

  return {
    // State
    healthy,
    checking,
    ontologies,
    graphModels,
    eventhouses,
    loadingSection,
    error,
    provisionPct,
    provisionStep,
    provisionState,
    provisionError,

    // Actions
    checkHealth,
    fetchOntologies,
    fetchGraphModels,
    fetchEventhouses,
    runProvisionPipeline,
    fetchAll,
  };
}
