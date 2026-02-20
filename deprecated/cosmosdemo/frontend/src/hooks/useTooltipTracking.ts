import { useState, useCallback, useRef, useEffect } from 'react';

interface TooltipState<N, E> {
  x: number;
  y: number;
  node?: N;
  edge?: E;
}

interface TooltipTrackingResult<N, E> {
  tooltip: TooltipState<N, E> | null;
  mousePos: React.RefObject<{ x: number; y: number }>;
  handleNodeHover: (node: N | null) => void;
  handleLinkHover: (edge: E | null) => void;
  clearTooltip: () => void;
}

/**
 * Hook to track mouse position and manage tooltip state for graph viewers.
 * Shared between GraphTopologyViewer and ResourceVisualizer.
 */
export function useTooltipTracking<N, E>(): TooltipTrackingResult<N, E> {
  const [tooltip, setTooltip] = useState<TooltipState<N, E> | null>(null);

  const mousePos = useRef({ x: 0, y: 0 });
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      mousePos.current = { x: e.clientX, y: e.clientY };
    };
    window.addEventListener('mousemove', handler);
    return () => window.removeEventListener('mousemove', handler);
  }, []);

  const handleNodeHover = useCallback((node: N | null) => {
    if (node) {
      setTooltip({ x: mousePos.current.x, y: mousePos.current.y, node, edge: undefined });
    } else {
      setTooltip(null);
    }
  }, []);

  const handleLinkHover = useCallback((edge: E | null) => {
    if (edge) {
      setTooltip({ x: mousePos.current.x, y: mousePos.current.y, edge, node: undefined });
    } else {
      setTooltip(null);
    }
  }, []);

  const clearTooltip = useCallback(() => setTooltip(null), []);

  return { tooltip, mousePos, handleNodeHover, handleLinkHover, clearTooltip };
}
