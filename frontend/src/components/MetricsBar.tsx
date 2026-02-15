import { useRef, useState, useEffect } from 'react';
import { Group as PanelGroup, Panel, Separator as PanelResizeHandle } from 'react-resizable-panels';
import { GraphTopologyViewer } from './GraphTopologyViewer';
import { TabbedLogStream } from './TabbedLogStream';

const LOG_STREAMS = [
  { url: '/api/logs', title: 'API' },
  { url: '/query/logs', title: 'Graph API' },
];

export function MetricsBar() {
  const graphPanelRef = useRef<HTMLDivElement>(null);
  const [graphSize, setGraphSize] = useState({ width: 800, height: 300 });

  // Track panel resize via ResizeObserver
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
    <div className="h-full px-6 py-3">
      <PanelGroup className="h-full">
        {/* Graph topology viewer */}
        <Panel defaultSize={64} minSize={30}>
          <div ref={graphPanelRef} className="h-full px-1">
            <GraphTopologyViewer width={graphSize.width} height={graphSize.height} />
          </div>
        </Panel>

        <PanelResizeHandle className="metrics-resize-handle" />

        {/* API + Graph API logs (tabbed) */}
        <Panel defaultSize={36} minSize={12}>
          <div className="h-full px-1">
            <TabbedLogStream streams={LOG_STREAMS} />
          </div>
        </Panel>
      </PanelGroup>
    </div>
  );
}
