import { useResizable } from '../hooks/useResizable';

export function ResizableSidebar({ children }: { children: React.ReactNode }) {
  const { size: width, handleProps } = useResizable('x', {
    initial: 288, min: 0, max: 99999, storageKey: 'sidebar-w', invert: true,
  });

  return (
    <aside className="shrink-0 h-full flex flex-row">
      {/* Drag handle — left edge (outside sized container so always accessible) */}
      <div
        className="w-4 cursor-col-resize shrink-0
                   hover:bg-brand/10 active:bg-brand/20 transition-colors z-10
                   flex items-center justify-center group/handle"
        {...handleProps}
      >
        <svg width="14" height="16" viewBox="0 0 14 16" className="text-text-muted/40 group-hover/handle:text-brand/60 transition-colors">
          {/* Left chevron */}
          <polyline points="5,4 1.5,8 5,12" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          {/* Center bar */}
          <rect x="6" y="2" width="2" height="12" rx="1" fill="currentColor" />
          {/* Right chevron */}
          <polyline points="9,4 12.5,8 9,12" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
      <div style={{ width }} className="overflow-y-auto overflow-x-hidden h-full">{children}</div>
    </aside>
  );
}
