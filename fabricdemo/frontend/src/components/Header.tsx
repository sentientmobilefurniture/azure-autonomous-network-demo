import { useState } from 'react';
import { AgentBar } from './AgentBar';
import { HealthButtonBar } from './HealthButtonBar';
import { ServiceHealthPopover } from './ServiceHealthPopover';
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

export function Header() {
  const SCENARIO = useScenario();
  const { theme, toggleTheme } = useTheme();
  const [healthOpen, setHealthOpen] = useState(false);
  const [showAgents, setShowAgents] = useState(true);
  const [showHealth, setShowHealth] = useState(true);

  return (
    <>
      <header className="h-12 flex-shrink-0 bg-neutral-bg2 border-b border-border flex items-center px-6 justify-between">
        <div className="flex items-center gap-3">
          <span className="text-brand text-lg leading-none">◆</span>
          <h1 className="text-lg font-semibold text-text-primary leading-none">
            AI Incident Investigator
          </h1>
          <span className="text-xs text-text-muted ml-1 hidden sm:inline">
            Multi-agent diagnosis
          </span>
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-brand/10 text-brand border border-brand/20 font-medium">
            {SCENARIO.displayName}
          </span>
        </div>
        <div className="flex items-center gap-1.5 relative">
          <ToggleBtn
            label="Agents"
            active={showAgents}
            onClick={() => setShowAgents((v) => !v)}
            icon={showAgents ? '👁' : '👁‍🗨'}
            tooltip={showAgents ? HEADER_TOOLTIPS['agents-hide'] : HEADER_TOOLTIPS['agents-show']}
          />
          <ToggleBtn
            label="Health"
            active={showHealth}
            onClick={() => setShowHealth((v) => !v)}
            icon={showHealth ? '👁' : '👁‍🗨'}
            tooltip={showHealth ? HEADER_TOOLTIPS['health-hide'] : HEADER_TOOLTIPS['health-show']}
          />
          <button
            onClick={() => setHealthOpen(!healthOpen)}
            className="text-[10px] px-2 py-0.5 rounded border border-border hover:bg-neutral-bg3 transition-colors text-text-muted"
            title={HEADER_TOOLTIPS['services']}
          >
            ⚙ Services
          </button>
          <button
            onClick={toggleTheme}
            className="text-[10px] px-2 py-0.5 rounded border border-border hover:bg-neutral-bg3 transition-colors text-text-muted"
            title={theme === 'light' ? HEADER_TOOLTIPS['dark-mode'] : HEADER_TOOLTIPS['light-mode']}
          >
            {theme === 'light' ? '🌙 Dark' : '☀️ Light'}
          </button>
          <ServiceHealthPopover
            open={healthOpen}
            onClose={() => setHealthOpen(false)}
          />
        </div>
      </header>
      {showAgents && <AgentBar />}
      {showHealth && <HealthButtonBar />}
    </>
  );
}
