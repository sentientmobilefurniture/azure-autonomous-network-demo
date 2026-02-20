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
                   transition-colors z-10 flex items-center justify-center group/handle"
        {...handleProps}
      >
        <div className="h-10 w-1.5 rounded-full bg-text-muted/20
                        group-hover/handle:bg-brand/40 transition-colors" />
      </div>
      <div style={{ width }} className="overflow-y-auto overflow-x-hidden h-full">{children}</div>
    </aside>
  );
}
