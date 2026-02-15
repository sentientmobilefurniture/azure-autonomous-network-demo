import { useEffect, useState } from 'react';
import { useScenarioContext, ProvisioningStatus } from '../context/ScenarioContext';

/**
 * Non-blocking slim banner below header during agent provisioning.
 * Shows current step from SSE stream, auto-dismisses on success,
 * stays on error until dismissed.
 */
export function ProvisioningBanner() {
  const { provisioningStatus, setProvisioningStatus } = useScenarioContext();
  const [visible, setVisible] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  // Show banner when provisioning starts or errors
  useEffect(() => {
    if (provisioningStatus.state === 'provisioning') {
      setVisible(true);
      setDismissed(false);
    } else if (provisioningStatus.state === 'done') {
      setVisible(true);
      // Auto-dismiss after 3 seconds
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

      {provisioningStatus.state === 'error' && (
        <button
          onClick={() => {
            setDismissed(true);
            setProvisioningStatus({ state: 'idle' });
          }}
          className="flex-shrink-0 ml-2 hover:opacity-80 transition-opacity"
          title="Dismiss"
        >
          ✕
        </button>
      )}
    </div>
  );
}

function getBgClass(status: ProvisioningStatus): string {
  switch (status.state) {
    case 'provisioning': return 'bg-brand/10 border-b border-brand/20';
    case 'done': return 'bg-status-success/10 border-b border-status-success/20';
    case 'error': return 'bg-red-500/10 border-b border-red-500/20';
    default: return '';
  }
}

function getTextClass(status: ProvisioningStatus): string {
  switch (status.state) {
    case 'provisioning': return 'text-brand';
    case 'done': return 'text-status-success';
    case 'error': return 'text-red-400';
    default: return '';
  }
}

function getIcon(status: ProvisioningStatus): string {
  switch (status.state) {
    case 'provisioning': return '⟳';
    case 'done': return '✓';
    case 'error': return '✗';
    default: return '';
  }
}

function getMessage(status: ProvisioningStatus): string {
  switch (status.state) {
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
