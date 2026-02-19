import { useResizable } from '../hooks/useResizable';

interface ResizableTerminalProps {
  children: React.ReactNode;
  visible: boolean;
}

export function ResizableTerminal({ children, visible }: ResizableTerminalProps) {
  const { size: height, handleProps } = useResizable('y', {
    initial: 200, min: 100, max: 500, storageKey: 'terminal-h', invert: true,
  });

  if (!visible) return null;

  return (
    <div
      style={{ height }}
      className="shrink-0 bg-neutral-bg2 border-t border-border relative"
    >
      {/* Drag handle — top edge */}
      <div
        className="absolute top-0 left-0 right-0 h-2.5 cursor-row-resize
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
      <div className="h-full pt-1.5 overflow-hidden">
        {children}
      </div>
    </div>
  );
}
