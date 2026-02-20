import { useState, useRef } from 'react';
import { ColorWheelPopover } from './ColorWheelPopover';
import { COLOR_PALETTE, EDGE_COLOR_PALETTE } from './graphConstants';

interface GraphEdgeToolbarProps {
  availableEdgeLabels: string[];
  activeEdgeLabels: string[];
  onToggleEdgeLabel: (label: string) => void;
  visibleEdgeCount: number;
  totalEdgeCount: number;
  edgeColorOverride: Record<string, string>;
  onSetEdgeColor?: (label: string, color: string) => void;
  /** Font-style controls */
  edgeLabelFontSize: number | null;
  onEdgeLabelFontSizeChange: (size: number | null) => void;
  edgeLabelColor: string | null;
  onEdgeLabelColorChange: (color: string | null) => void;
}

function getEdgeColor(label: string, overrides: Record<string, string>): string {
  if (overrides[label]) return overrides[label];
  const palette = EDGE_COLOR_PALETTE.length > 0 ? EDGE_COLOR_PALETTE : COLOR_PALETTE;
  let hash = 0;
  for (let i = 0; i < label.length; i++) hash = (hash * 31 + label.charCodeAt(i)) | 0;
  return palette[Math.abs(hash) % palette.length];
}

export function GraphEdgeToolbar({
  availableEdgeLabels, activeEdgeLabels, onToggleEdgeLabel,
  visibleEdgeCount, totalEdgeCount,
  edgeColorOverride, onSetEdgeColor,
  edgeLabelFontSize, onEdgeLabelFontSizeChange,
  edgeLabelColor, onEdgeLabelColorChange,
}: GraphEdgeToolbarProps) {
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

  const openTextPopover = () => {
    if (textBtnRef.current) {
      setTextColorAnchor(textBtnRef.current.getBoundingClientRect());
    }
    setShowTextPopover((v) => !v);
    setShowTextColorPicker(false);
  };

  return (
    <div className="flex items-center gap-2 px-3 py-1.5 border-b border-border shrink-0">
      {/* Section label */}
      <span className="text-[10px] font-medium text-text-muted whitespace-nowrap">━ Edges</span>

      {/* Edge label filter chips */}
      <div className="flex items-center gap-1 ml-2 overflow-x-auto">
        {availableEdgeLabels.map((label) => {
          const active = activeEdgeLabels.length === 0 || activeEdgeLabels.includes(label);
          const color = getEdgeColor(label, edgeColorOverride);
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
                style={{ backgroundColor: color }}
                onClick={(e) => { e.stopPropagation(); openColorPicker(label); }}
                title={`Change color for ${label}`}
              />
              {/* Label text — click toggles filter */}
              <button
                className="hover:text-text-primary transition-colors"
                onClick={() => onToggleEdgeLabel(label)}
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
        {visibleEdgeCount}/{totalEdgeCount}E
      </span>

      {/* Text style button */}
      <button
        ref={textBtnRef}
        onClick={openTextPopover}
        className={`text-xs px-1 transition-colors ${
          showTextPopover ? 'text-brand' : 'text-text-muted hover:text-text-primary'
        }`}
        title="Edge label style"
      >Aa</button>

      {/* Text style popover */}
      {showTextPopover && textColorAnchor && (
        <div
          className="fixed z-50 bg-neutral-bg3 border border-border rounded-lg p-3 shadow-xl space-y-2"
          style={{ top: textColorAnchor.bottom + 4, left: textColorAnchor.left - 100 }}
        >
          <div className="text-[10px] text-text-muted uppercase tracking-wider font-medium">Edge Label Style</div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-text-secondary w-10">Size</span>
            <input
              type="range"
              min={0}
              max={20}
              step={0.5}
              value={edgeLabelFontSize ?? 8}
              onChange={(e) => {
                const v = parseFloat(e.target.value);
                onEdgeLabelFontSizeChange(v === 8 ? null : v);
              }}
              className="w-24 accent-brand"
            />
            <span className="text-[10px] text-text-muted w-6">{edgeLabelFontSize ?? 'auto'}</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-text-secondary w-10">Color</span>
            <button
              className="h-4 w-4 rounded-full border border-border cursor-pointer hover:scale-125 transition-transform"
              style={{ backgroundColor: edgeLabelColor ?? '#888' }}
              onClick={() => setShowTextColorPicker((v) => !v)}
              title="Change edge label color"
            />
            {edgeLabelColor && (
              <button
                className="text-[10px] text-text-muted hover:text-text-primary"
                onClick={() => onEdgeLabelColorChange(null)}
              >reset</button>
            )}
          </div>
          {showTextColorPicker && (
            <ColorWheelPopover
              currentColor={edgeLabelColor ?? '#888'}
              anchorRect={textColorAnchor}
              onSelect={(c) => { onEdgeLabelColorChange(c); setShowTextColorPicker(false); }}
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
      {colorPickerLabel && colorPickerAnchor && onSetEdgeColor && (
        <ColorWheelPopover
          currentColor={getEdgeColor(colorPickerLabel, edgeColorOverride)}
          anchorRect={colorPickerAnchor}
          onSelect={(color) => onSetEdgeColor(colorPickerLabel, color)}
          onClose={() => { setColorPickerLabel(null); setColorPickerAnchor(null); }}
        />
      )}
    </div>
  );
}
