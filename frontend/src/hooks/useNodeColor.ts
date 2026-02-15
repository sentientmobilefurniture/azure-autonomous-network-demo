import { useCallback } from 'react';
import { useScenarioContext } from '../context/ScenarioContext';
import { NODE_COLORS } from '../components/graph/graphConstants';

/**
 * Deterministic auto-assign palette for unknown node labels.
 * Uses a stable string hash so the same label always gets the same color.
 */
const AUTO_PALETTE = [
  '#38BDF8', '#FB923C', '#A78BFA', '#3B82F6',
  '#C084FC', '#CA8A04', '#FB7185', '#F472B6',
  '#10B981', '#EF4444', '#6366F1', '#FBBF24',
];

function autoColor(label: string): string {
  let hash = 0;
  for (const ch of label) hash = ((hash << 5) - hash + ch.charCodeAt(0)) | 0;
  return AUTO_PALETTE[Math.abs(hash) % AUTO_PALETTE.length];
}

/**
 * Centralized color resolution hook.
 *
 * Resolution order:
 *   userOverride[label] → scenarioNodeColors[label] → NODE_COLORS[label] → autoColor(label)
 *
 * Accepts nodeColorOverride as a parameter (managed as React state in
 * GraphTopologyViewer, synced to localStorage) rather than reading localStorage
 * directly, to avoid stale state after context menu color changes.
 */
export function useNodeColor(nodeColorOverride: Record<string, string>) {
  const { scenarioNodeColors } = useScenarioContext();

  return useCallback(
    (label: string) =>
      nodeColorOverride[label]
      ?? scenarioNodeColors[label]
      ?? NODE_COLORS[label]
      ?? autoColor(label),
    [nodeColorOverride, scenarioNodeColors],
  );
}
