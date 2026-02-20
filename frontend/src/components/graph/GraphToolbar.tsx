import { useState, useRef } from 'react';
import { useNodeColor } from '../../hooks/useNodeColor';
import { ColorWheelPopover } from './ColorWheelPopover';

interface GraphToolbarProps {
  availableLabels: string[];
  activeLabels: string[];
  onToggleLabel: (label: string) => void;
  visibleNodeCount: number;
  totalNodeCount: number;
  nodeColorOverride: Record<string, string>;
  onSetColor?: (label: string, color: string) => void;
  /** Node label font-style controls */
  nodeLabelFontSize?: number | null;
  onNodeLabelFontSizeChange?: (size: number | null) => void;
  nodeLabelColor?: string | null;
  onNodeLabelColorChange?: (color: string | null) => void;
}

export function GraphToolbar({
  availableLabels, activeLabels, onToggleLabel,
  visibleNodeCount, totalNodeCount,
  nodeColorOverride, onSetColor,
  nodeLabelFontSize, onNodeLabelFontSizeChange,
  nodeLabelColor, onNodeLabelColorChange,
}: GraphToolbarProps) {
  const getColor = useNodeColor(nodeColorOverride);
  const [colorPickerLabel, setColorPickerLabel] = useState<string | null>(null);
  const [colorPickerAnchor, setColorPickerAnchor] = useState<DOMRect | null>(null);
  const [showTextPopover, setShowTextPopover] = useState(false);
  const [textColorAnchor, setTextColorAnchor] = useState<DOMRect | null>(null);
  const [showTextColorPicker, setShowTextColorPicker] = useState(false);
  const dotRefs = useRef<Record<string, HTMLSpanElement | null>>({});
  const textBtnRef = useRef<HTMLButtonElement>(null);

  const openColorPicker = (label: string) => {
    const el = dotRefs.current[label];
    if (!el) return;
    setColorPickerAnchor(el.getBoundingClientRect());
    setColorPickerLabel(label);
  };

  return (
    <div className="flex items-center gap-2 px-3 py-1.5 border-b border-border shrink-0">
      {/* Section label */}
      <span className="text-[10px] font-medium text-text-muted whitespace-nowrap">● Nodes</span>

      {/* Label filter chips */}
      <div className="flex items-center gap-1 ml-1 overflow-x-auto">
        {availableLabels.map((label) => {
          const active = activeLabels.length === 0 || activeLabels.includes(label);
          return (
            <span
              key={label}
              className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px]
                         border transition-colors
                         ${active
                           ? 'border-border-strong text-text-secondary'
                           : 'border-transparent text-text-muted opacity-40'}`}
            >
              {/* Color dot — click opens color wheel */}
              <span
                ref={(el) => { dotRefs.current[label] = el; }}
                className="h-2.5 w-2.5 rounded-full shrink-0 cursor-pointer
                           hover:scale-150 transition-transform ring-1 ring-transparent
                           hover:ring-brand/40"
                style={{ backgroundColor: getColor(label) }}
                onClick={(e) => { e.stopPropagation(); openColorPicker(label); }}
                title={`Change color for ${label}`}
              />
              {/* Label text — click toggles filter */}
              <button
                className="hover:text-text-primary transition-colors"
                onClick={() => onToggleLabel(label)}
              >
                {label}
              </button>
            </span>
          );
        })}
      </div>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Counts */}
      <span className="text-[10px] text-text-muted whitespace-nowrap">
        {visibleNodeCount}/{totalNodeCount}N
      </span>

      {/* Node text style button */}
      {onNodeLabelFontSizeChange && (
        <button
          ref={textBtnRef}
          onClick={() => {
            if (textBtnRef.current) setTextColorAnchor(textBtnRef.current.getBoundingClientRect());
            setShowTextPopover((v) => !v);
            setShowTextColorPicker(false);
          }}
          className={`text-xs px-1 transition-colors ${
            showTextPopover ? 'text-brand' : 'text-text-muted hover:text-text-primary'
          }`}
          title="Node label style"
        >Aa</button>
      )}

      {/* Node text style popover */}
      {showTextPopover && textColorAnchor && onNodeLabelFontSizeChange && onNodeLabelColorChange && (
        <div
          className="fixed z-50 bg-neutral-bg3 border border-border rounded-lg p-3 shadow-xl space-y-2"
          style={{ top: textColorAnchor.bottom + 4, left: textColorAnchor.left - 100 }}
        >
          <div className="text-[10px] text-text-muted uppercase tracking-wider font-medium">Node Label Style</div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-text-secondary w-10">Size</span>
            <input
              type="range"
              min={0}
              max={30}
              step={0.5}
              value={nodeLabelFontSize ?? 10}
              onChange={(e) => {
                const v = parseFloat(e.target.value);
                onNodeLabelFontSizeChange(v === 10 ? null : v);
              }}
              className="w-24 accent-brand"
            />
            <span className="text-[10px] text-text-muted w-6">{nodeLabelFontSize ?? 'auto'}</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-text-secondary w-10">Color</span>
            <button
              className="h-4 w-4 rounded-full border border-border cursor-pointer hover:scale-125 transition-transform"
              style={{ backgroundColor: nodeLabelColor ?? '#ccc' }}
              onClick={() => setShowTextColorPicker((v) => !v)}
              title="Change node label color"
            />
            {nodeLabelColor && (
              <button
                className="text-[10px] text-text-muted hover:text-text-primary"
                onClick={() => onNodeLabelColorChange(null)}
              >reset</button>
            )}
          </div>
          {showTextColorPicker && (
            <ColorWheelPopover
              currentColor={nodeLabelColor ?? '#ccc'}
              anchorRect={textColorAnchor}
              onSelect={(c) => { onNodeLabelColorChange(c); setShowTextColorPicker(false); }}
              onClose={() => setShowTextColorPicker(false)}
            />
          )}
          <button
            className="text-[10px] text-text-muted hover:text-text-primary mt-1"
            onClick={() => setShowTextPopover(false)}
          >Close</button>
        </div>
      )}

      {/* Color wheel popover */}
      {colorPickerLabel && colorPickerAnchor && onSetColor && (
        <ColorWheelPopover
          currentColor={getColor(colorPickerLabel)}
          anchorRect={colorPickerAnchor}
          onSelect={(color) => onSetColor(colorPickerLabel, color)}
          onClose={() => { setColorPickerLabel(null); setColorPickerAnchor(null); }}
        />
      )}
    </div>
  );
}
