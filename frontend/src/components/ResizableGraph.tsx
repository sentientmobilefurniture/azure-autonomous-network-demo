import { useResizable } from '../hooks/useResizable';

export function ResizableGraph({ children }: { children: React.ReactNode }) {
  const { size: height, handleProps } = useResizable('y', {
    initial: 280, min: 0, max: 99999, storageKey: 'graph-h',
  });

  return (
    <div className="relative shrink-0 flex flex-col">
      <div style={{ height }} className="overflow-hidden">
        {children}
      </div>
      {/* Drag handle — styled like the header bar */}
      <div
        className="h-5 cursor-row-resize shrink-0 border-y border-border
                   bg-neutral-bg2 hover:bg-neutral-bg3 active:bg-brand/10
                   transition-colors z-10 flex items-center justify-center gap-1 group/handle"
        {...handleProps}
      >
        <div className="w-1 h-1 rounded-full bg-text-muted/30
                        group-hover/handle:bg-brand/50 transition-colors" />
        <div className="w-8 h-1 rounded-full bg-text-muted/30
                        group-hover/handle:bg-brand/50 transition-colors" />
        <div className="w-1 h-1 rounded-full bg-text-muted/30
                        group-hover/handle:bg-brand/50 transition-colors" />
      </div>
    </div>
  );
}
