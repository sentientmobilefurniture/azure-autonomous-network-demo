import { useEffect, type RefObject } from 'react';

/**
 * Hook that fires a callback when a click occurs outside the referenced element.
 * Shared between AlertInput, ScenarioChip, and ColorWheelPopover.
 */
export function useClickOutside(
  ref: RefObject<HTMLElement | null>,
  onClose: () => void,
  enabled: boolean = true,
): void {
  useEffect(() => {
    if (!enabled) return;
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        onClose();
      }
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [ref, onClose, enabled]);
}
