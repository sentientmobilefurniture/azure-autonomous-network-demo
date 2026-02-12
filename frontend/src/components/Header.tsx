import { HealthDot } from './HealthDot';

export function Header() {
  return (
    <header className="h-12 flex-shrink-0 bg-neutral-bg2 border-b border-white/10 flex items-center justify-between px-6">
      {/* Left: branding */}
      <div className="flex items-center gap-3">
        <span className="text-brand text-lg leading-none">◆</span>
        <h1 className="text-lg font-semibold text-text-primary leading-none">
          Autonomous Network NOC
        </h1>
        <span className="text-xs text-text-muted ml-1 hidden sm:inline">
          Multi-agent diagnosis
        </span>
      </div>

      {/* Right: status indicators */}
      <div className="flex items-center gap-4">
        <HealthDot label="API" />
        <span className="inline-flex items-center gap-1.5 text-xs">
          <span className="h-1.5 w-1.5 rounded-full bg-status-success" />
          <span className="text-status-success">5 Agents</span>
        </span>
      </div>
    </header>
  );
}
