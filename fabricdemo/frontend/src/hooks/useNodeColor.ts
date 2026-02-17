import { useCallback } from 'react';
import { SCENARIO } from '../config';
import { COLOR_PALETTE } from '../components/graph/graphConstants';

const scenarioNodeColors = SCENARIO.graphStyles.nodeColors;

function autoColor(label: string): string {
  let hash = 0;
  for (const ch of label) hash = ((hash << 5) - hash + ch.charCodeAt(0)) | 0;
  return COLOR_PALETTE[Math.abs(hash) % COLOR_PALETTE.length];
}

/**
 * Centralized color resolution hook.
 *
 * Resolution order:
 *   userOverride[label] → scenarioNodeColors[label] → autoColor(label)
 *
 * Accepts nodeColorOverride as a parameter (managed as React state in
 * GraphTopologyViewer, synced to localStorage) rather than reading localStorage
 * directly, to avoid stale state after context menu color changes.
 */
export function useNodeColor(nodeColorOverride: Record<string, string>) {
  return useCallback(
    (label: string) =>
      nodeColorOverride[label]
      ?? scenarioNodeColors[label]
      ?? autoColor(label),
    [nodeColorOverride],
  );
}
