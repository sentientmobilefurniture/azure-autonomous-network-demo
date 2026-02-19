import { useResizable } from '../hooks/useResizable';

export function ResizableSidebar({ children }: { children: React.ReactNode }) {
  const { size: width, handleProps } = useResizable('x', {
    initial: 288, min: 200, max: 500, storageKey: 'sidebar-w', invert: true,
  });

  return (
    <aside
      style={{ width }}
      className="shrink-0 h-full overflow-y-auto relative"
    >
      {/* Drag handle — left edge */}
      <div
        className="absolute top-0 left-0 bottom-0 w-2.5 cursor-col-resize
                   hover:bg-brand/10 active:bg-brand/20 transition-colors z-10
                   flex items-center justify-center group/handle"
        {...handleProps}
      >
        <div className="h-8 w-1 rounded-full bg-border group-hover/handle:bg-brand/40
                        transition-colors flex flex-col items-center justify-center gap-0.5">
          <span className="block w-0.5 h-0.5 rounded-full bg-text-muted/40 group-hover/handle:bg-brand/60" />
          <span className="block w-0.5 h-0.5 rounded-full bg-text-muted/40 group-hover/handle:bg-brand/60" />
          <span className="block w-0.5 h-0.5 rounded-full bg-text-muted/40 group-hover/handle:bg-brand/60" />
        </div>
      </div>
      <div className="pl-1.5 h-full">{children}</div>
    </aside>
  );
}
