import { useState } from 'react';
import { motion } from 'framer-motion';
import type { StepEvent } from '../types';
import { ActionEmailModal } from './ActionEmailModal';

interface ActionCardProps {
  step: StepEvent;
}

export function ActionCard({ step }: ActionCardProps) {
  const [modalOpen, setModalOpen] = useState(false);
  const action = step.action;

  if (!action) return null;

  const urgencyColor = {
    CRITICAL: 'text-red-400 bg-red-500/10 border-red-500/30',
    HIGH: 'text-amber-400 bg-amber-500/10 border-amber-500/30',
    STANDARD: 'text-blue-400 bg-blue-500/10 border-blue-500/30',
  }[action.urgency] || 'text-amber-400 bg-amber-500/10 border-amber-500/30';

  return (
    <>
      <motion.div
        className="border border-amber-500/40 bg-amber-500/5 rounded-lg p-3 my-2"
        initial={{ opacity: 0, y: 10, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.3, ease: 'easeOut' }}
      >
        {/* Header row */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-amber-400 text-sm">⚡</span>
            <span className="text-xs font-semibold text-amber-300 uppercase tracking-wide">
              Action — {step.agent}
            </span>
            <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded border ${urgencyColor}`}>
              {action.urgency}
            </span>
            <span className="text-[10px] font-medium px-1.5 py-0.5 rounded
                           text-emerald-400 bg-emerald-500/10 border border-emerald-500/30">
              DISPATCHED ✓
            </span>
          </div>
          {step.duration && (
            <span className="text-xs text-text-muted">{step.duration}</span>
          )}
        </div>

        {/* Summary — always visible */}
        <div className="mt-2 text-sm text-text-primary">
          Dispatched <span className="font-semibold text-amber-300">{action.engineer.name}</span>
          {' '}to{' '}
          <span className="text-text-secondary">{action.destination.description}</span>
        </div>

        {/* Key details */}
        <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-[11px] text-text-muted">
          <div>📞 {action.engineer.phone}</div>
          <div>📍 {action.destination.latitude.toFixed(4)}, {action.destination.longitude.toFixed(4)}</div>
          <div>🔗 Dispatch ID: {action.dispatch_id}</div>
          <div>🕐 {new Date(action.dispatch_time).toLocaleTimeString()}</div>
        </div>

        {/* Sensor IDs */}
        {action.sensor_ids.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {action.sensor_ids.map((sid) => (
              <span key={sid} className="text-[10px] px-1.5 py-0.5 rounded
                     bg-neutral-bg3 text-text-secondary font-mono">
                {sid}
              </span>
            ))}
          </div>
        )}

        {/* View Action button — right-aligned */}
        <div className="flex justify-end mt-3">
          <button
            onClick={() => setModalOpen(true)}
            className="flex items-center gap-1.5 text-[10px] font-medium px-3 py-1.5
                       rounded-md border border-amber-500/40 bg-amber-500/10
                       text-amber-300 hover:bg-amber-500/20 hover:border-amber-500/60
                       focus-visible:ring-2 focus-visible:ring-amber-400
                       transition-all"
          >
            <span>📧</span>
            <span>View Action</span>
          </button>
        </div>
      </motion.div>

      {/* Email preview modal */}
      <ActionEmailModal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        action={action}
      />
    </>
  );
}
