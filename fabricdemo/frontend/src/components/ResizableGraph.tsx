import { useResizable } from '../hooks/useResizable';

export function ResizableGraph({ children }: { children: React.ReactNode }) {
  const { size: height, handleProps } = useResizable('y', {
    initial: 280, min: 100, max: 600, storageKey: 'graph-h',
  });

  return (
    <div style={{ height }} className="border-b border-border relative shrink-0">
      {children}
      {/* Drag handle — bottom edge */}
      <div
        className="absolute bottom-0 left-0 right-0 h-2.5 cursor-row-resize
                   hover:bg-brand/10 active:bg-brand/20 transition-colors z-10
                   flex items-center justify-center group/handle"
        {...handleProps}
      >
        <div className="w-8 h-1 rounded-full bg-border group-hover/handle:bg-brand/40
                        transition-colors flex items-center justify-center gap-0.5">
          <span className="block w-0.5 h-0.5 rounded-full bg-text-muted/40 group-hover/handle:bg-brand/60" />
          <span className="block w-0.5 h-0.5 rounded-full bg-text-muted/40 group-hover/handle:bg-brand/60" />
          <span className="block w-0.5 h-0.5 rounded-full bg-text-muted/40 group-hover/handle:bg-brand/60" />
        </div>
      </div>
    </div>
  );
}
