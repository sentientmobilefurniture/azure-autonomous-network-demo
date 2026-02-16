import { useState, useEffect, useCallback } from 'react';
import { ModalShell } from './ModalShell';
import { ProgressBar } from './ProgressBar';
import { useFabricDiscovery } from '../hooks/useFabricDiscovery';

interface Props {
  open: boolean;
  onClose: () => void;
  onCreateScenario?: () => void;
}

type WizardStep = 1 | 2 | 3;

const STEP_LABELS = ['Connect', 'Provision', 'Create Scenario'] as const;

/**
 * 3-step stepper modal for Fabric workspace setup.
 *
 * Step 1: Connect — shows workspace connection status (env var or runtime)
 * Step 2: Provision — discover/create Fabric resources with SSE progress
 * Step 3: Create Scenario — summary + CTA to open AddScenarioModal
 */
export function FabricSetupWizard({ open, onClose, onCreateScenario }: Props) {
  const fabric = useFabricDiscovery();
  const [step, setStep] = useState<WizardStep>(1);

  // Determine initial step based on health state
  useEffect(() => {
    if (!open) return;
    fabric.checkHealth();
    fabric.fetchAll();
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (fabric.workspaceConnected === null) return; // still loading
    if (fabric.queryReady) {
      setStep(3);
    } else if (fabric.workspaceConnected) {
      setStep(2);
    } else {
      setStep(1);
    }
  }, [fabric.workspaceConnected, fabric.queryReady]);

  const handleProvision = useCallback(() => {
    fabric.runProvisionPipeline({ scenario_name: 'telco-noc-fabric' });
  }, [fabric]);

  const handleCreateScenario = useCallback(() => {
    onClose();
    onCreateScenario?.();
  }, [onClose, onCreateScenario]);

  if (!open) return null;

  const footer = (
    <div className="flex justify-between w-full">
      <div>
        {step > 1 && (
          <button
            onClick={() => setStep((step - 1) as WizardStep)}
            className="px-4 py-1.5 text-sm text-text-muted hover:text-text-primary transition-colors"
          >
            ← Back
          </button>
        )}
      </div>
      <div className="flex gap-2">
        <button
          onClick={onClose}
          className="px-4 py-1.5 text-sm text-text-primary bg-white/10 hover:bg-white/15 rounded-md transition-colors"
        >
          Close
        </button>
        {step === 1 && fabric.workspaceConnected && (
          <button
            onClick={() => setStep(2)}
            className="px-4 py-1.5 text-sm bg-brand text-white hover:bg-brand/90 rounded-md transition-colors"
          >
            Continue →
          </button>
        )}
        {step === 2 && fabric.provisionState === 'done' && (
          <button
            onClick={() => setStep(3)}
            className="px-4 py-1.5 text-sm bg-brand text-white hover:bg-brand/90 rounded-md transition-colors"
          >
            Continue →
          </button>
        )}
        {step === 3 && (
          <button
            onClick={handleCreateScenario}
            className="px-5 py-1.5 text-sm bg-brand text-white hover:bg-brand/90 rounded-md transition-colors font-medium"
          >
            Create Fabric Scenario →
          </button>
        )}
      </div>
    </div>
  );

  return (
    <ModalShell title="Set Up Microsoft Fabric" onClose={onClose} footer={footer} className="!max-w-3xl">
      {/* Stepper header */}
      <div className="flex items-center justify-center gap-8 pb-4 border-b border-white/10 -mt-2">
        {STEP_LABELS.map((label, i) => {
          const stepNum = (i + 1) as WizardStep;
          const isActive = step === stepNum;
          const isDone = step > stepNum;
          return (
            <button
              key={label}
              onClick={() => isDone && setStep(stepNum)}
              className={`flex items-center gap-2 text-sm transition-colors ${
                isActive ? 'text-brand font-medium' :
                isDone ? 'text-status-success cursor-pointer hover:text-status-success/80' :
                'text-text-muted'
              }`}
            >
              <span className={`h-6 w-6 rounded-full flex items-center justify-center text-xs border ${
                isActive ? 'border-brand bg-brand/20 text-brand' :
                isDone ? 'border-status-success bg-status-success/20 text-status-success' :
                'border-white/20 bg-white/5 text-text-muted'
              }`}>
                {isDone ? '✓' : stepNum}
              </span>
              {label}
            </button>
          );
        })}
      </div>

      {/* Step content */}
      <div className="min-h-[280px]">
        {step === 1 && <Step1Connect fabric={fabric} />}
        {step === 2 && <Step2Provision fabric={fabric} onProvision={handleProvision} />}
        {step === 3 && <Step3Create />}
      </div>
    </ModalShell>
  );
}


// ---------------------------------------------------------------------------
// Step 1: Connect
// ---------------------------------------------------------------------------

function Step1Connect({ fabric }: { fabric: ReturnType<typeof useFabricDiscovery> }) {
  if (fabric.checking) {
    return (
      <div className="flex items-center justify-center py-12">
        <span className="inline-block h-6 w-6 animate-spin rounded-full border-2 border-brand border-t-transparent" />
        <span className="ml-3 text-sm text-text-muted">Checking connection…</span>
      </div>
    );
  }

  if (fabric.workspaceConnected) {
    return (
      <div className="space-y-4">
        <div className="bg-status-success/10 border border-status-success/30 rounded-lg p-4">
          <div className="flex items-center gap-2">
            <span className="text-status-success text-lg">✓</span>
            <span className="text-sm font-medium text-status-success">Connected via environment config</span>
          </div>
          <p className="text-xs text-text-muted mt-1">
            Workspace ID is set in azure_config.env. Fabric workspace is reachable.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-4 space-y-2">
        <p className="text-sm font-medium text-amber-400">Fabric workspace not connected</p>
        <p className="text-xs text-text-secondary">
          Set <code className="bg-white/5 px-1 rounded">FABRIC_WORKSPACE_ID</code> in{' '}
          <code className="bg-white/5 px-1 rounded">azure_config.env</code> and redeploy.
        </p>
      </div>
      <div className="bg-neutral-bg1 rounded-lg border border-white/5 p-4 space-y-3">
        <label className="text-xs text-text-muted block">Workspace ID</label>
        <input
          type="text"
          disabled
          placeholder="Set via env var (runtime config coming in Phase F)"
          className="w-full bg-neutral-bg2 border border-white/10 rounded px-3 py-2 text-sm text-text-muted
            placeholder:text-text-muted/50 cursor-not-allowed opacity-60"
        />
        <p className="text-[10px] text-text-muted">
          Find this in your Fabric portal → Workspace settings
        </p>
      </div>
    </div>
  );
}


// ---------------------------------------------------------------------------
// Step 2: Provision
// ---------------------------------------------------------------------------

function Step2Provision({
  fabric,
  onProvision,
}: {
  fabric: ReturnType<typeof useFabricDiscovery>;
  onProvision: () => void;
}) {
  const ResourceRow = ({ label, items, loading }: {
    label: string; items: { id: string }[]; loading: boolean;
  }) => (
    <div className="flex items-center justify-between py-1.5">
      <span className="text-sm text-text-primary">{label}</span>
      <span className="text-xs">
        {loading ? (
          <span className="text-text-muted animate-pulse">Checking…</span>
        ) : items.length > 0 ? (
          <span className="text-status-success">✓ Found ({items.length})</span>
        ) : (
          <span className="text-text-muted">○ Will be created</span>
        )}
      </span>
    </div>
  );

  const isLoading = fabric.loadingSection !== null;

  return (
    <div className="space-y-4">
      {/* Resource discovery list */}
      <div className="bg-neutral-bg1 rounded-lg border border-white/5 p-4 space-y-1">
        <ResourceRow label="Lakehouse" items={fabric.lakehouses} loading={isLoading} />
        <ResourceRow label="Ontology" items={fabric.ontologies} loading={isLoading} />
        <ResourceRow label="Graph Model" items={fabric.graphModels} loading={isLoading} />
        <ResourceRow label="Eventhouse" items={fabric.eventhouses} loading={isLoading} />
        <ResourceRow label="KQL Databases" items={fabric.kqlDatabases} loading={isLoading} />
      </div>

      {/* Provision CTA */}
      {fabric.provisionState === 'idle' && (
        <button
          onClick={onProvision}
          disabled={!fabric.workspaceConnected}
          className={`w-full py-2.5 text-sm rounded-lg transition-colors font-medium ${
            fabric.workspaceConnected
              ? 'bg-brand text-white hover:bg-brand/90'
              : 'bg-white/5 text-text-muted cursor-not-allowed'
          }`}
        >
          Set Up Resources
        </button>
      )}

      {/* Progress */}
      {fabric.provisionState === 'running' && (
        <div className="space-y-2">
          <ProgressBar pct={fabric.provisionPct} />
          <div className="flex items-center justify-between text-xs text-text-muted">
            <span>{fabric.provisionStep}</span>
            <span>{fabric.provisionPct}%</span>
          </div>
        </div>
      )}

      {/* Done */}
      {fabric.provisionState === 'done' && (
        <div className="bg-status-success/10 border border-status-success/30 rounded-lg p-3 text-center">
          <p className="text-sm text-status-success">All resources ready ✓</p>
        </div>
      )}

      {/* Error with retry */}
      {fabric.provisionState === 'error' && (
        <div className="bg-status-error/10 border border-status-error/30 rounded-lg p-3 space-y-2">
          <p className="text-xs text-status-error">{fabric.provisionError}</p>
          {fabric.provisionCompleted.length > 0 && (
            <p className="text-[10px] text-text-muted">
              Completed: {fabric.provisionCompleted.join(', ')}
            </p>
          )}
          <button
            onClick={onProvision}
            className="px-3 py-1 text-xs bg-brand/20 text-brand hover:bg-brand/30 rounded transition-colors"
          >
            Retry
          </button>
        </div>
      )}

      {/* Refresh button */}
      <button
        onClick={() => fabric.fetchAll()}
        disabled={fabric.checking}
        className="text-xs text-text-muted hover:text-text-secondary transition-colors"
      >
        {fabric.checking ? 'Checking…' : '↻ Refresh'}
      </button>
    </div>
  );
}


// ---------------------------------------------------------------------------
// Step 3: Create Scenario
// ---------------------------------------------------------------------------

function Step3Create() {
  return (
    <div className="space-y-6 py-4">
      <div className="space-y-3">
        <div className="flex items-center gap-2 text-sm text-status-success">
          <span>✓</span> Workspace connected
        </div>
        <div className="flex items-center gap-2 text-sm text-status-success">
          <span>✓</span> Lakehouse provisioned with graph data
        </div>
        <div className="flex items-center gap-2 text-sm text-status-success">
          <span>✓</span> Ontology defined and indexed
        </div>
        <div className="flex items-center gap-2 text-sm text-status-success">
          <span>✓</span> Graph Model discovered
        </div>
      </div>
      <div className="text-center space-y-2">
        <p className="text-sm text-text-secondary">
          Everything is ready. Create a scenario to start investigating with AI agents.
        </p>
      </div>
    </div>
  );
}
