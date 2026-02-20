import { useResizable } from '../hooks/useResizable';

interface ResizableTerminalProps {
  children: React.ReactNode;
  visible: boolean;
}

export function ResizableTerminal({ children, visible }: ResizableTerminalProps) {
  const { size: height, handleProps } = useResizable('y', {
    initial: 200, min: 0, max: 99999, storageKey: 'terminal-h', invert: true,
  });

  if (!visible) return null;

  return (
    <div className="shrink-0 bg-neutral-bg2 border-t border-border flex flex-col">
      {/* Drag handle — top edge (outside sized container so always accessible) */}
      <div
        className="h-4 cursor-row-resize shrink-0
                   hover:bg-brand/10 active:bg-brand/20 transition-colors z-10
                   flex items-center justify-center group/handle"
        {...handleProps}
      >
        <svg width="16" height="14" viewBox="0 0 16 14" className="text-text-muted/40 group-hover/handle:text-brand/60 transition-colors">
          {/* Up chevron */}
          <polyline points="4,5 8,1.5 12,5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          {/* Center bar */}
          <rect x="2" y="6" width="12" height="2" rx="1" fill="currentColor" />
          {/* Down chevron */}
          <polyline points="4,9 8,12.5 12,9" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
      <div style={{ height }} className="overflow-hidden">
        {children}
      </div>
    </div>
  );
}
