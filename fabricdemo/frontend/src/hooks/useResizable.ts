import { useState, useRef, useCallback } from 'react';

interface UseResizableOptions {
  initial: number;
  min: number;
  max: number;
  storageKey: string;
  /** When true, moving the pointer in the negative direction grows the panel
   *  (used for sidebar left-edge and terminal top-edge). */
  invert?: boolean;
}

export function useResizable(axis: 'x' | 'y', opts: UseResizableOptions) {
  const { min, max, storageKey, invert = false } = opts;

  const [size, setSize] = useState(() => {
    const saved = localStorage.getItem(storageKey);
    return saved ? Math.max(min, Math.min(max, Number(saved))) : opts.initial;
  });

  const dragging = useRef(false);
  const startPos = useRef(0);
  const startSize = useRef(0);

  const onPointerDown = useCallback((e: React.PointerEvent) => {
    dragging.current = true;
    startPos.current = axis === 'x' ? e.clientX : e.clientY;
    startSize.current = size;
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  }, [axis, size]);

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    if (!dragging.current) return;
    const pos = axis === 'x' ? e.clientX : e.clientY;
    const delta = invert
      ? startPos.current - pos
      : pos - startPos.current;
    setSize(Math.max(min, Math.min(max, startSize.current + delta)));
  }, [axis, invert, min, max]);

  const onPointerUp = useCallback(() => {
    if (!dragging.current) return;
    dragging.current = false;
    localStorage.setItem(storageKey, String(size));
  }, [storageKey, size]);

  return {
    size,
    handleProps: { onPointerDown, onPointerMove, onPointerUp },
  };
}
