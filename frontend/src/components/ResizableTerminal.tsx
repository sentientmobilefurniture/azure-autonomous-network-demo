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
    <div className="shrink-0 bg-neutral-bg2 flex flex-col">
      {/* Drag handle — blends with surroundings, demarcated by borders */}
      <div
        className="h-5 cursor-row-resize shrink-0 border-y border-border
                   hover:bg-neutral-bg3 active:bg-brand/10
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
      <div style={{ height }} className="overflow-hidden">
        {children}
      </div>
    </div>
  );
}
