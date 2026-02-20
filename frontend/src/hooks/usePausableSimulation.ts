import { useState, useCallback, useRef, useEffect, type RefObject } from 'react';

interface PausableSimulationResult {
  isPaused: boolean;
  manualPause: boolean;
  handleMouseEnter: () => void;
  handleMouseLeave: () => void;
  handleTogglePause: () => void;
  resetPause: () => void;
}

interface Freezable {
  setFrozen: (frozen: boolean) => void;
}

/**
 * Hook to manage pause/freeze state for force-graph simulations.
 * Shared between GraphTopologyViewer and ResourceVisualizer.
 */
export function usePausableSimulation(
  canvasRef: RefObject<Freezable | null>,
): PausableSimulationResult {
  const [isPaused, setIsPaused] = useState(false);
  const [manualPause, setManualPause] = useState(false);
  const resumeTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleMouseEnter = useCallback(() => {
    if (resumeTimeoutRef.current) {
      clearTimeout(resumeTimeoutRef.current);
      resumeTimeoutRef.current = null;
    }
    canvasRef.current?.setFrozen(true);
    setIsPaused(true);
  }, [canvasRef]);

  const handleMouseLeave = useCallback(() => {
    if (manualPause) return;
    resumeTimeoutRef.current = setTimeout(() => {
      canvasRef.current?.setFrozen(false);
      setIsPaused(false);
      resumeTimeoutRef.current = null;
    }, 300);
  }, [manualPause, canvasRef]);

  const handleTogglePause = useCallback(() => {
    if (manualPause) {
      setManualPause(false);
      canvasRef.current?.setFrozen(false);
      setIsPaused(false);
    } else {
      setManualPause(true);
      canvasRef.current?.setFrozen(true);
      setIsPaused(true);
    }
  }, [manualPause, canvasRef]);

  const resetPause = useCallback(() => {
    setManualPause(false);
    canvasRef.current?.setFrozen(false);
    setIsPaused(false);
  }, [canvasRef]);

  // Cleanup debounce timeout
  useEffect(() => {
    return () => {
      if (resumeTimeoutRef.current) clearTimeout(resumeTimeoutRef.current);
    };
  }, []);

  return { isPaused, manualPause, handleMouseEnter, handleMouseLeave, handleTogglePause, resetPause };
}
