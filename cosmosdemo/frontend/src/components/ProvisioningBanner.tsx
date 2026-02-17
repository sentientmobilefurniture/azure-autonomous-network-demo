import { useEffect, useState, useCallback } from 'react';
import { useScenarioContext, ProvisioningStatus } from '../context/ScenarioContext';
import { triggerProvisioning } from '../utils/triggerProvisioning';

/**
 * Non-blocking slim banner below header during agent provisioning.
 * Shows current step from SSE stream, auto-dismisses on success,
 * stays on error until dismissed.
 * Also shows a "needs provisioning" prompt with a one-click Provision button.
 */
export function ProvisioningBanner() {
  const { provisioningStatus, setProvisioningStatus, activeScenario } = useScenarioContext();
  const [visible, setVisible] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  // Show banner when provisioning starts, errors, or agents need provisioning
  useEffect(() => {
    if (provisioningStatus.state === 'provisioning' || provisioningStatus.state === 'needs-provisioning') {
      setVisible(true);
      setDismissed(false);
    } else if (provisioningStatus.state === 'done') {
      setVisible(true);
      const timer = setTimeout(() => {
        setVisible(false);
      }, 3000);
      return () => clearTimeout(timer);
    } else if (provisioningStatus.state === 'error') {
      setVisible(true);
    } else if (provisioningStatus.state === 'idle') {
      setVisible(false);
    }
  }, [provisioningStatus]);

  // Check if agents need provisioning when scenario changes
  useEffect(() => {
    if (!activeScenario) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch('/api/agents');
        if (!res.ok) return;
        const data = await res.json();
        const agents: unknown[] = data.agents ?? [];
        if (!cancelled && agents.length === 0) {
          setProvisioningStatus({ state: 'needs-provisioning', scenarioName: activeScenario });
        }
      } catch {
        // Silent — don't show banner on network error
      }
    })();
    return () => { cancelled = true; };
  }, [activeScenario, setProvisioningStatus]);

  const handleProvisionNow = useCallback(async () => {
    if (!activeScenario) return;
    await triggerProvisioning(
      { prompt_scenario: activeScenario },
      activeScenario,
      setProvisioningStatus,
    );
  }, [activeScenario, setProvisioningStatus]);

  if (!visible || dismissed) return null;

  const bgClass = getBgClass(provisioningStatus);
  const textClass = getTextClass(provisioningStatus);
  const icon = getIcon(provisioningStatus);
  const message = getMessage(provisioningStatus);

  return (
    <div className={`h-7 flex-shrink-0 flex items-center justify-between px-4 text-xs ${bgClass} ${textClass} transition-colors`}>
      <div className="flex items-center gap-2 min-w-0">
        <span>{icon}</span>
        <span className="truncate">{message}</span>
      </div>

      <div className="flex items-center gap-2 flex-shrink-0 ml-2">
        {provisioningStatus.state === 'needs-provisioning' && (
          <button
            onClick={handleProvisionNow}
            className="px-2 py-0.5 text-[10px] font-medium bg-brand/20 hover:bg-brand/30 text-brand rounded transition-colors"
          >
            Provision Now
          </button>
        )}
        {(provisioningStatus.state === 'error' || provisioningStatus.state === 'needs-provisioning') && (
          <button
            onClick={() => {
              setDismissed(true);
              setProvisioningStatus({ state: 'idle' });
            }}
            className="hover:opacity-80 transition-opacity"
            title="Dismiss"
          >
            ✕
          </button>
        )}
      </div>
    </div>
  );
}

function getBgClass(status: ProvisioningStatus): string {
  switch (status.state) {
    case 'needs-provisioning': return 'bg-amber-500/10 border-b border-amber-500/20';
    case 'provisioning': return 'bg-brand/10 border-b border-brand/20';
    case 'done': return 'bg-status-success/10 border-b border-status-success/20';
    case 'error': return 'bg-red-500/10 border-b border-red-500/20';
    default: return '';
  }
}

function getTextClass(status: ProvisioningStatus): string {
  switch (status.state) {
    case 'needs-provisioning': return 'text-amber-400';
    case 'provisioning': return 'text-brand';
    case 'done': return 'text-status-success';
    case 'error': return 'text-red-400';
    default: return '';
  }
}

function getIcon(status: ProvisioningStatus): string {
  switch (status.state) {
    case 'needs-provisioning': return '⚠';
    case 'provisioning': return '⟳';
    case 'done': return '✓';
    case 'error': return '✗';
    default: return '';
  }
}

function getMessage(status: ProvisioningStatus): string {
  switch (status.state) {
    case 'needs-provisioning':
      return `Agents not provisioned for "${status.scenarioName}" — click Provision Now to set up.`;
    case 'provisioning':
      return `Provisioning agents for "${status.scenarioName}"... ${status.step}`;
    case 'done':
      return `Agents provisioned for "${status.scenarioName}" ✓`;
    case 'error':
      return `Provisioning failed for "${status.scenarioName}": ${status.error}`;
    default:
      return '';
  }
}
