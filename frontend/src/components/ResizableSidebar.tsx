import { useResizable } from '../hooks/useResizable';

export function ResizableSidebar({ children }: { children: React.ReactNode }) {
  const { size: width, handleProps } = useResizable('x', {
    initial: 288, min: 0, max: 99999, storageKey: 'sidebar-w', invert: true,
  });

  return (
    <aside className="shrink-0 h-full flex flex-row">
      {/* Drag handle — blends with surroundings, demarcated by borders */}
      <div
        className="w-5 cursor-col-resize shrink-0 border-x border-border
                   hover:bg-neutral-bg3 active:bg-brand/10
                   transition-colors z-10 flex flex-col items-center justify-center gap-1 group/handle"
        {...handleProps}
      >
        <div className="h-1 w-1 rounded-full bg-text-muted/30
                        group-hover/handle:bg-brand/50 transition-colors" />
        <div className="h-8 w-1 rounded-full bg-text-muted/30
                        group-hover/handle:bg-brand/50 transition-colors" />
        <div className="h-1 w-1 rounded-full bg-text-muted/30
                        group-hover/handle:bg-brand/50 transition-colors" />
      </div>
      <div style={{ width }} className="overflow-y-auto overflow-x-hidden h-full">{children}</div>
    </aside>
  );
}
