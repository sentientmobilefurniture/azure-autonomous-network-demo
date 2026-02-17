import { useRef, useState, useEffect } from 'react';
import { GraphTopologyViewer } from './GraphTopologyViewer';

/**
 * MetricsBar — graph topology viewer panel.
 * Log terminals have moved to the persistent TerminalPanel (always visible).
 */
export function MetricsBar() {
  const graphPanelRef = useRef<HTMLDivElement>(null);
  const [graphSize, setGraphSize] = useState({ width: 800, height: 300 });

  useEffect(() => {
    const el = graphPanelRef.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => {
      setGraphSize({
        width: entry.contentRect.width,
        height: entry.contentRect.height,
      });
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <div ref={graphPanelRef} className="h-full px-6 py-3">
      <GraphTopologyViewer width={graphSize.width} height={graphSize.height} />
    </div>
  );
}
