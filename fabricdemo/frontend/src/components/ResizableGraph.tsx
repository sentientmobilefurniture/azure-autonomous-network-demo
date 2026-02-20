import { useResizable } from '../hooks/useResizable';

export function ResizableGraph({ children }: { children: React.ReactNode }) {
  const { size: height, handleProps } = useResizable('y', {
    initial: 280, min: 0, max: 99999, storageKey: 'graph-h',
  });

  return (
    <div className="border-b border-border relative shrink-0 flex flex-col">
      <div style={{ height }} className="overflow-hidden">
        {children}
      </div>
      {/* Drag handle — bottom edge (outside sized container so always accessible) */}
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
    </div>
  );
}
