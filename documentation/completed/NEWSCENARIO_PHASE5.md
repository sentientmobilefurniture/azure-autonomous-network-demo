# Phase 5 — Frontend: Action Card with "View Action" Button

> **Scope:** Frontend TypeScript/React only. No backend changes.
> **Depends on:** Phase 3 (SSE emits `action_executed` event and `step_complete` with `is_action: true`).
> **Outcome:** When the orchestrator calls `dispatch_field_engineer`, a distinctive **Action Card** appears in the chat scroll showing the dispatch was executed, with a "View Action" button that opens a modal displaying the full dispatch email.
>
> **AUDIT STATUS:** Corrected. The original plan referenced `OrchestratorBubble.tsx` and `StepGroup.tsx` which do NOT exist in this codebase. The actual component is `ChatPanel.tsx` which renders steps inline (flat, no wrapper box, no collapsible group). All changes target `ChatPanel.tsx`.

---

## 1. Why

The requirements state:
- "Make sure there is a unique block that appears during the thread that simulates an action done by the orchestrator"
- "The email should be viewable by clicking a (View action) button on the right side of the action card as it appears in the scrolling chat window"

Currently, all tool calls render as `StepCard` components rendered flat in `ChatPanel.tsx`. An **action** is fundamentally different from an **investigation step** — it's the orchestrator *doing* something, not *learning* something. It needs distinct visual treatment.

---

## 2. Type Updates

File: `frontend/src/types/index.ts`

### 2.1 Add action-related types

```typescript
// Action types (dispatched by FunctionTool)
export interface ActionData {
  status: string;           // "dispatched"
  dispatch_id: string;
  dispatch_time: string;
  engineer: {
    name: string;
    email: string;
    phone: string;
  };
  destination: {
    description: string;
    latitude: number;
    longitude: number;
    maps_link: string;
  };
  urgency: string;          // "CRITICAL" | "HIGH" | "STANDARD"
  sensor_ids: string[];
  email_subject: string;
  email_body: string;
}
```

### 2.2 Extend StepEvent

```typescript
export interface StepEvent {
  step: number;
  agent: string;
  duration?: string;
  query?: string;
  response?: string;
  error?: boolean;
  visualization?: VisualizationData;
  reasoning?: string;
  // NEW — action support
  is_action?: boolean;       // true when this step is a FunctionTool call
  action?: ActionData;       // parsed output of the function
}
```

---

## 3. New Component: `ActionCard.tsx`

File: `frontend/src/components/ActionCard.tsx`

This component renders a distinctive card for action executions — visually different from `StepCard` to make it immediately obvious that the orchestrator **did something**.

### Design

- **Accent colour:** Orange/amber (`#F97316`) — distinct from the blue brand colour used by investigation steps
- **Icon:** ⚡ (lightning bolt) — conveys action/execution
- **Header:** "⚡ ACTION — dispatch_field_engineer" with a green "DISPATCHED" badge
- **Summary:** "Dispatched {engineer_name} to {destination_description}" (always visible, not collapsible)
- **"View Action" button:** Right-aligned, opens a modal with the full email body
- **Appears inline** in the step sequence at its chronological position (not grouped separately)

### Implementation

```tsx
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
            <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${urgencyColor}`}>
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
```

---

## 4. New Component: `ActionEmailModal.tsx`

File: `frontend/src/components/ActionEmailModal.tsx`

A modal that displays the full dispatch email, styled to look like an email preview. This is what appears when the user clicks "View Action".

### Implementation

```tsx
import { motion, AnimatePresence } from 'framer-motion';
import type { ActionData } from '../types';

interface ActionEmailModalProps {
  isOpen: boolean;
  onClose: () => void;
  action: ActionData;
}

export function ActionEmailModal({ isOpen, onClose, action }: ActionEmailModalProps) {
  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            className="fixed inset-0 bg-black/60 z-50"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
          />

          {/* Modal */}
          <motion.div
            className="fixed inset-0 flex items-center justify-center z-50 p-4"
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
          >
            <div className="glass-card w-full max-w-2xl max-h-[80vh] overflow-hidden
                            flex flex-col border border-amber-500/30">
              {/* Header — email style */}
              <div className="p-4 border-b border-border-subtle">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <span className="text-amber-400">📧</span>
                    <span className="text-sm font-semibold text-text-primary">
                      Dispatch Email Preview
                    </span>
                  </div>
                  <button
                    onClick={onClose}
                    className="text-text-muted hover:text-text-primary text-lg
                               transition-colors"
                  >
                    ✕
                  </button>
                </div>

                {/* Email metadata */}
                <div className="space-y-1 text-xs text-text-secondary">
                  <div>
                    <span className="text-text-muted w-12 inline-block">To:</span>
                    <span className="font-medium">{action.engineer.name}</span>
                    <span className="text-text-muted"> &lt;{action.engineer.email}&gt;</span>
                  </div>
                  <div>
                    <span className="text-text-muted w-12 inline-block">Subject:</span>
                    <span className="font-medium">{action.email_subject}</span>
                  </div>
                  <div>
                    <span className="text-text-muted w-12 inline-block">Sent:</span>
                    <span>{new Date(action.dispatch_time).toLocaleString()}</span>
                  </div>
                </div>
              </div>

              {/* Email body — monospace to preserve formatting */}
              <div className="p-4 overflow-y-auto flex-1">
                <pre className="text-xs text-text-primary whitespace-pre-wrap
                               font-mono leading-relaxed">
                  {action.email_body}
                </pre>
              </div>

              {/* Footer with map link */}
              <div className="p-3 border-t border-border-subtle flex items-center
                             justify-between">
                <a
                  href={action.destination.maps_link}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-brand hover:text-brand/80 underline
                             transition-colors"
                >
                  📍 Open in Google Maps
                </a>
                <button
                  onClick={() => navigator.clipboard.writeText(action.email_body)}
                  className="text-xs text-text-muted hover:text-text-primary
                             transition-colors"
                >
                  Copy email
                </button>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
```

---

## 5. Update `ChatPanel.tsx`

> **AUDIT NOTE:** The original plan referenced `OrchestratorBubble.tsx` and `StepGroup.tsx` — neither exists. Steps are rendered flat in `ChatPanel.tsx`. The conditional must be a **ternary inside the existing wrapper `<div key={s.step}>`**, NOT an early return from `.map()`. An early return would lose the `key` prop and skip `OrchestratorThoughts` rendering for action steps.

File: `frontend/src/components/ChatPanel.tsx`

### Change:

In the `steps.map()` loop (currently lines 61–79), replace the unconditional `<StepCard>` with a ternary:

```tsx
import { ActionCard } from './ActionCard';  // NEW import

// Inside the steps.map() callback — the key/wrapper div stays the same:
{steps.map((s) => (
  <div key={s.step}>
    {s.reasoning && (
      <>
        <OrchestratorThoughts
          reasoning={s.reasoning}
          expanded={expandedThoughts[`${msg.id}-t-${s.step}`] ?? false}
          onToggle={() => toggleThought(msg.id, s.step)}
        />
        <div className="ml-4 h-1.5 border-l-2 border-brand/20" aria-hidden="true" />
      </>
    )}
    {/* NEW: Branch on is_action — ternary, not early return */}
    {s.is_action
      ? <ActionCard step={s} />
      : <StepCard
          step={s}
          expanded={expandedSteps[`${msg.id}-${s.step}`] ?? false}
          onToggle={() => toggleStep(msg.id, s.step)}
        />
    }
  </div>
))}
```

**Why ternary, not early return:**
- The wrapper `<div key={s.step}>` provides React's reconciliation key — removing it would cause re-mount issues.
- `OrchestratorThoughts` renders the reasoning annotation above each step. Action steps may also have reasoning (the orchestrator explains why it's dispatching). Skipping this would lose important context.
- When `s.is_action` is `undefined` (all existing steps, all pre-upgrade sessions), the ternary evaluates the falsy branch → existing `StepCard` renders unchanged. **Zero regression risk.**

---

## 6. Update `useSession.ts` — Handle `action_executed` SSE Event

File: `frontend/src/hooks/useSession.ts`

### 6.1 `updateOrchestratorMessage` — add `action_executed` handler

> **AUDIT NOTE:** `action_executed` must be handled in **three** locations in useSession.ts:
> 1. The `updateOrchestratorMessage` switch statement
> 2. The `connectToStream` ThinkingState logic
> 3. The `loadSessionMessages` event_log reconstruction
>
> The primary data carrier is `step_complete` with `is_action: true`. The `action_executed` event is supplementary.

```typescript
case 'action_executed':
  // action_executed is informational — the actual step data comes
  // via step_complete with is_action:true. No additional state update needed.
  // However, we could use this to trigger a toast notification or sound.
  break;
```

### 6.2 `connectToStream` — add `action_executed` to thinking state handler

```typescript
} else if (ev.event === 'action_executed') {
  setThinking(null);  // Clear thinking state — action executed
}
```

### 6.3 `loadSessionMessages` — handle `action_executed` in event_log reconstruction

```typescript
else if (evType === 'action_executed') {
  // action_executed is supplementary — step_complete already carries the data
  // No additional processing needed for replay
}
```

**Note:** The `step_complete` event with `is_action: true` and `action` data is the primary carrier. The `action_executed` event is a separate signal for UX purposes (e.g., toast notifications, sound effects). The session replay works entirely through `step_complete` events.

---

## 7. Update `agentType.ts` — Add Dispatch Action Meta

File: `frontend/src/utils/agentType.ts`

Add a case for the dispatch function:

```typescript
export function getVizButtonMeta(agent: string) {
  switch (agent) {
    // ... existing cases ...
    case 'dispatch_field_engineer':
      return { icon: '⚡', label: 'View Action', tooltip: 'View field dispatch details' };
    default:
      return { icon: '▧', label: 'View Docs', tooltip: 'View results' };
  }
}
```

---

## 8. Files to Create / Modify — Summary

| Action | File | Description |
|---|---|---|
| **CREATE** | `frontend/src/components/ActionCard.tsx` | Action card component with dispatch summary and "View Action" button |
| **CREATE** | `frontend/src/components/ActionEmailModal.tsx` | Modal displaying full dispatch email preview |
| **MODIFY** | `frontend/src/types/index.ts` | Add `ActionData` interface, extend `StepEvent` with `is_action` and `action` |
| **MODIFY** | `frontend/src/components/ChatPanel.tsx` | Render `ActionCard` for steps with `is_action: true`, `StepCard` for others |
| **MODIFY** | `frontend/src/hooks/useSession.ts` | Handle `action_executed` SSE event in 3 locations |
| **MODIFY** | `frontend/src/utils/agentType.ts` | Add dispatch function viz meta |

---

## 9. Visual Hierarchy in the Chat Stream

After all phases are implemented, `ChatPanel.tsx` renders orchestrator steps in this order:

```
┌─────────────────────────────────────────────────┐
│ Orchestrator turn (all steps rendered flat)       │
│                                                 │
│ 💭 [ORCHESTRATOR_THINKING] reasoning... (step 1)  │
│ ┌─ StepCard: GraphExplorerAgent  [View Graph] ─┐  │
│ └─────────────────────────────────────────┘  │
│ 💭 [ORCHESTRATOR_THINKING] reasoning... (step 2)  │
│ ┌─ StepCard: TelemetryAgent     [View Data]  ─┐  │
│ └─────────────────────────────────────────┘  │
│ ...more StepCards...                             │
│                                                 │
│ ⚡ ACTION — dispatch_field_engineer    HIGH       │
│   Dispatched Dave Mitchell to Goulburn           │
│   📞 +61-412-555-401  📍 -34.7546, 149.7186     │
│   🔗 DISPATCH-20260206-143215                    │
│   [SENS-SYD-MEL-F1-OPT-002] [AMP-GOULBURN...]   │
│                                  [📧 View Action] │
│                                                 │
│ ▾ Diagnosis                                      │
│   ### 1. Incident Summary                        │
│   Fibre cut on LINK-SYD-MEL-FIBRE-01...          │
│   ### 7. Field Dispatch                          │
│   Dave Mitchell dispatched to Goulburn...        │
│                                                 │
│ 6 steps · 38.2s                        [Copy]    │
└─────────────────────────────────────────────────┘
```

---

## 10. Validation Checklist

- [ ] `ActionCard` renders with amber/orange styling, visually distinct from blue `StepCard`
- [ ] "View Action" button opens modal with full email body
- [ ] Email body is readable in monospace format with correct line breaks
- [ ] Google Maps link opens in new tab with correct coordinates
- [ ] "Copy email" button copies the full email body to clipboard
- [ ] Action steps do NOT render as `StepCard` — they render as `ActionCard`
- [ ] Action steps appear inline in the step sequence at their chronological position
- [ ] Session replay (`loadSessionMessages`) correctly reconstructs action steps with `is_action: true`
- [ ] `action_executed` handled in all 3 locations in useSession.ts (switch, SSE, replay)
- [ ] TypeScript types compile without errors (`ActionData`, extended `StepEvent`)
- [ ] Animation on ActionCard entry is smooth (framer-motion)
- [ ] Modal backdrop click and ✕ button both close the modal
- [ ] Component works with zero action steps (no unnecessary elements rendered)
- [ ] Component works with multiple action steps (e.g., dispatching to two locations)
