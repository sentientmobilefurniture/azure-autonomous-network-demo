import { useState } from 'react';
import { ServicesPanel } from './ServicesPanel';
import { useScenario } from '../ScenarioContext';
import { useTheme } from '../ThemeContext';
import { HEADER_TOOLTIPS } from '../config/tooltips';

/* ── tiny reusable toggle button ────────────────────────────────── */

function ToggleBtn({
  label,
  active,
  onClick,
  icon,
  tooltip,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
  icon: string;
  tooltip?: string;
}) {
  const [showTip, setShowTip] = useState(false);

  return (
    <div
      className="relative"
      onMouseEnter={() => setShowTip(true)}
      onMouseLeave={() => setShowTip(false)}
    >
      <button
        onClick={onClick}
        className={`
          text-[10px] px-2 py-0.5 rounded border transition-colors select-none
          inline-flex items-center gap-1
          ${active
            ? 'border-brand/30 text-brand bg-brand/5 hover:bg-brand/10'
            : 'border-border text-text-muted hover:bg-neutral-bg3'}
        `}
      >
        <span className="text-[11px]">{icon}</span>
        <span>{label}</span>
      </button>
      {showTip && tooltip && (
        <div className="absolute right-0 top-full mt-1.5 z-50 w-52
                        bg-neutral-bg3 border border-border rounded-lg
                        shadow-xl px-3 py-2 text-[11px] text-text-secondary
                        leading-relaxed pointer-events-none whitespace-normal">
          {tooltip}
        </div>
      )}
    </div>
  );
}

interface HeaderProps {
  showTabs: boolean;
  onToggleTabs: () => void;
  terminalVisible: boolean;
  onToggleTerminal: () => void;
}

export function Header({ showTabs, onToggleTabs, terminalVisible, onToggleTerminal }: HeaderProps) {
  const SCENARIO = useScenario();
  const { theme, toggleTheme } = useTheme();
  const [healthOpen, setHealthOpen] = useState(false);

  return (
    <>
      <header className="h-12 flex-shrink-0 bg-neutral-bg2 border-b border-border flex items-center px-6 justify-between">
        <div className="flex items-center gap-3">
          <span className="text-brand text-lg leading-none">◆</span>
          <h1 className="text-sm font-semibold text-text-primary leading-none">
            3IQ Demo — Fabric Graphs + Foundry Agents
          </h1>
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-brand/10 text-brand border border-brand/20 font-medium">
            {SCENARIO.displayName}
          </span>
        </div>
        <div className="flex items-center gap-1.5 relative">
          {/* Portal quick-launch buttons */}
          <a
            href="https://ai.azure.com/"
            target="_blank"
            rel="noopener noreferrer"
            className="text-[10px] px-2 py-0.5 rounded border border-purple-800/30
                       bg-purple-800/10 text-purple-300 hover:bg-purple-800/20
                       transition-colors select-none inline-flex items-center gap-1"
            title={HEADER_TOOLTIPS['open-foundry']}
          >
            Open Foundry
          </a>
          <a
            href="https://app.fabric.microsoft.com/home?experience=fabric-developer"
            target="_blank"
            rel="noopener noreferrer"
            className="text-[10px] px-2 py-0.5 rounded border border-emerald-800/30
                       bg-emerald-800/10 text-emerald-300 hover:bg-emerald-800/20
                       transition-colors select-none inline-flex items-center gap-1"
            title={HEADER_TOOLTIPS['open-fabric']}
          >
            Open Fabric
          </a>

          {/* Services button — prominent with aggregate status */}
          <button
            onClick={() => setHealthOpen(!healthOpen)}
            className="text-[10px] px-2.5 py-0.5 rounded border border-border
                       hover:bg-neutral-bg3 transition-colors text-text-secondary
                       font-medium inline-flex items-center gap-1.5"
            title={HEADER_TOOLTIPS['services']}
          >
            ⚙ Services
          </button>

          <ToggleBtn
            label="Tabs"
            active={showTabs}
            onClick={onToggleTabs}
            icon={showTabs ? '👁' : '👁‍🗨'}
            tooltip={showTabs ? HEADER_TOOLTIPS['tabs-hide'] : HEADER_TOOLTIPS['tabs-show']}
          />
          <ToggleBtn
            label="Console"
            active={terminalVisible}
            onClick={onToggleTerminal}
            icon={terminalVisible ? '▣' : '□'}
            tooltip={terminalVisible ? 'Hide the API terminal / log console' : 'Show the API terminal / log console'}
          />
          <button
            onClick={toggleTheme}
            className="text-[10px] px-2 py-0.5 rounded border border-border hover:bg-neutral-bg3 transition-colors text-text-muted"
            title={theme === 'light' ? HEADER_TOOLTIPS['dark-mode'] : HEADER_TOOLTIPS['light-mode']}
          >
            {theme === 'light' ? '🌙 Dark' : '☀️ Light'}
          </button>
          <ServicesPanel
            open={healthOpen}
            onClose={() => setHealthOpen(false)}
          />
        </div>
      </header>
    </>
  );
}
