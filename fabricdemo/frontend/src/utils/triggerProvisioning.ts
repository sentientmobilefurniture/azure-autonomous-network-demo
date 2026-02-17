import { consumeSSE } from './sseStream';
import type { ProvisioningStatus } from '../context/ScenarioContext';

/**
 * Shared provisioning trigger — calls POST /api/config/apply with SSE progress tracking.
 * Used by ProvisioningBanner, useScenarios.selectScenario, and SettingsModal.
 */
export async function triggerProvisioning(
  body: Record<string, unknown>,
  scenarioName: string,
  setProvisioningStatus: (status: ProvisioningStatus) => void,
): Promise<void> {
  setProvisioningStatus({ state: 'provisioning', step: 'Starting...', scenarioName });

  try {
    const res = await fetch('/api/config/apply', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    await consumeSSE(res, {
      onProgress: (data) => {
        setProvisioningStatus({
          state: 'provisioning',
          step: data.detail || data.step,
          scenarioName,
        });
      },
      onComplete: () => {
        setProvisioningStatus({ state: 'done', scenarioName });
      },
      onError: (data) => {
        setProvisioningStatus({ state: 'error', error: data.error, scenarioName });
      },
    });

    // Auto-clear "done" state after 3 seconds
    setTimeout(() => {
      setProvisioningStatus({ state: 'idle' });
    }, 3000);
  } catch (e) {
    setProvisioningStatus({
      state: 'error',
      error: String(e),
      scenarioName,
    });
  }
}
