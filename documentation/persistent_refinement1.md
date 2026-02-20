# Persistent Plan — Refinement 1

> Addendum to [persistent.md](persistent.md). Covers three refinements:
> 1. **Resizable peripheral panels** (graph, sidebar, terminal)
> 2. **"New Session" button** in the sidebar for concurrent conversations
> 3. **Fix: Restore interleaved step timeline** (orchestrator thoughts + steps streamed individually)

---

## R1. Resizable Peripheral Panels

### R1.1 Summary

Three panels get lightweight drag-to-resize handles. None of them touch the
chat thread's document flow, so page scroll is unaffected.

| Panel | Resize Edge | Direction | Default | Range |
|---|---|---|---|---|
| Graph topology | Bottom | Vertical | 280px | 100–600px |
| Session sidebar | Left | Horizontal | 288px (18rem) | 200–500px |
| Terminal drawer | Top | Vertical | 200px | 100–500px |

### R1.2 Shared Hook: `useResizable`

All three panels share the same pointer-drag pattern via a reusable hook:

```tsx
// hooks/useResizable.ts

import { useState, useRef, useCallback } from 'react';

interface UseResizableOptions {
  initial: number;
  min: number;
  max: number;
  storageKey: string;
  /** When true, moving the pointer in the negative direction grows the panel
   *  (used for sidebar left-edge and terminal top-edge). */
  invert?: boolean;
}

export function useResizable(axis: 'x' | 'y', opts: UseResizableOptions) {
  const { min, max, storageKey, invert = false } = opts;

  const [size, setSize] = useState(() => {
    const saved = localStorage.getItem(storageKey);
    return saved ? Math.max(min, Math.min(max, Number(saved))) : opts.initial;
  });

  const dragging = useRef(false);
  const startPos = useRef(0);
  const startSize = useRef(0);

  const onPointerDown = useCallback((e: React.PointerEvent) => {
    dragging.current = true;
    startPos.current = axis === 'x' ? e.clientX : e.clientY;
    startSize.current = size;
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  }, [axis, size]);

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    if (!dragging.current) return;
    const pos = axis === 'x' ? e.clientX : e.clientY;
    const delta = invert
      ? startPos.current - pos    // sidebar (left), terminal (top)
      : pos - startPos.current;   // graph (bottom)
    setSize(Math.max(min, Math.min(max, startSize.current + delta)));
  }, [axis, invert, min, max]);

  const onPointerUp = useCallback(() => {
    dragging.current = false;
    localStorage.setItem(storageKey, String(size));
  }, [storageKey, size]);

  return {
    size,
    handleProps: { onPointerDown, onPointerMove, onPointerUp },
  };
}
```

### R1.3 Graph Topology — Bottom-Edge Resize

```tsx
// components/ResizableGraph.tsx

import { useResizable } from '../hooks/useResizable';

export function ResizableGraph({ children }: { children: React.ReactNode }) {
  const { size: height, handleProps } = useResizable('y', {
    initial: 280, min: 100, max: 600, storageKey: 'graph-h',
  });

  return (
    <div style={{ height }} className="border-b border-border relative shrink-0">
      {children}
      {/* Drag handle — bottom edge */}
      <div
        className="absolute bottom-0 left-0 right-0 h-1.5 cursor-row-resize
                   hover:bg-brand/20 active:bg-brand/40 transition-colors z-10"
        {...handleProps}
      />
    </div>
  );
}
```

**Why scroll-safe:** The chat content flows *after* the graph div. Changing
graph height just shifts where chat bubbles start — the page still scrolls
normally.

### R1.4 Session Sidebar — Left-Edge Resize

```tsx
// components/ResizableSidebar.tsx

import { useResizable } from '../hooks/useResizable';

export function ResizableSidebar({ children }: { children: React.ReactNode }) {
  const { size: width, handleProps } = useResizable('x', {
    initial: 288, min: 200, max: 500, storageKey: 'sidebar-w', invert: true,
  });

  return (
    <aside
      style={{ width }}
      className="shrink-0 border-l border-border sticky top-12
                 h-[calc(100vh-3rem)] overflow-y-auto relative"
    >
      {/* Drag handle — left edge */}
      <div
        className="absolute top-0 left-0 bottom-0 w-1.5 cursor-col-resize
                   hover:bg-brand/20 active:bg-brand/40 transition-colors z-10"
        {...handleProps}
      />
      <div className="pl-2">{children}</div>
    </aside>
  );
}
```

**Why scroll-safe:** The sidebar is `sticky` with its own `overflow-y-auto`.
It doesn't contribute to document height. Changing its width just adjusts
how much horizontal space the `flex-1` chat area gets.

### R1.5 Terminal Panel — Top-Edge Resize

```tsx
// components/ResizableTerminal.tsx

import { useResizable } from '../hooks/useResizable';

export function ResizableTerminal({ children, visible }: {
  children: React.ReactNode;
  visible: boolean;
}) {
  const { size: height, handleProps } = useResizable('y', {
    initial: 200, min: 100, max: 500, storageKey: 'terminal-h', invert: true,
  });

  if (!visible) return null;

  return (
    <div
      style={{ height }}
      className="fixed bottom-0 left-0 right-0 z-30
                 bg-neutral-bg2 border-t border-border shadow-lg"
    >
      {/* Drag handle — top edge */}
      <div
        className="absolute top-0 left-0 right-0 h-1.5 cursor-row-resize
                   hover:bg-brand/20 active:bg-brand/40 transition-colors"
        {...handleProps}
      />
      <div className="h-full pt-1.5 overflow-hidden">
        {children}
      </div>
    </div>
  );
}
```

**Chat Input interaction:** When the terminal is open, the sticky Chat Input
shifts up to sit above it:

```tsx
<div
  className="sticky z-40 border-t border-border p-3 bg-neutral-bg2"
  style={{ bottom: terminalVisible ? terminalHeight : 0 }}
>
  <ChatInput ... />
</div>
```

**Why scroll-safe:** The terminal is `position: fixed` — completely outside
document flow. Resizing it has zero effect on page scroll.

### R1.6 Updated App.tsx Layout

```tsx
{activeTab === 'investigate' && (
  <div className="flex-1 flex">
    <main className="flex-1 min-w-0 flex flex-col">
      <ResizableGraph>
        <MetricsBar />
      </ResizableGraph>

      <ChatPanel
        messages={messages}
        currentThinking={thinking}
        running={running}
        onSubmit={handleSubmit}
        onCancel={cancelSession}
        exampleQuestions={SCENARIO.exampleQuestions}
      />
    </main>

    <ResizableSidebar>
      <SessionSidebar
        sessions={sessions}
        activeSessionId={activeSessionId}
        onSelect={viewSession}
        onNewSession={handleNewSession}
      />
    </ResizableSidebar>
  </div>
)}

<ResizableTerminal visible={terminalVisible}>
  <TerminalPanel />
</ResizableTerminal>
```

---

## R2. "New Session" Button — Concurrent Conversations

### R2.1 Problem

With the persistent session model, users can start an investigation and then
want to ask a **different** question while the first one is still running. Today
you'd have to wait for the current run to finish or cancel it. There's no way
to "park" one conversation and start another.

### R2.2 Solution

A **"New Session"** button at the top of the session sidebar. Clicking it:

1. **Parks** the current conversation — the backend session keeps running
2. **Clears** the chat thread for a fresh start
3. The parked session remains visible in the sidebar with its live ⏳ status
4. You can click back to it at any time to reconnect

This is exactly how GitHub Copilot's "New Session" button works.

### R2.3 Sidebar Layout

```
┌─────────────────────────┐
│  SESSIONS               │
│  ┌───────────────────┐  │
│  │  ＋ New Session    │  │  ← always visible, top of sidebar
│  └───────────────────┘  │
│                         │
│  Search sessions…       │
│                         │
│  ┌───────────────────┐  │
│  │ ⏳ IN PROGRESS    │  │  ← the one you just parked
│  │ VPN-ACME-CORP     │  │
│  │ 4 steps · 45s     │  │
│  └───────────────────┘  │
│  ┌───────────────────┐  │
│  │ ⏳ IN PROGRESS    │  │  ← the new one you started
│  │ BGP flap PE-03    │  │
│  │ 2 steps · 12s     │  │  ← active (highlighted)
│  └───────────────────┘  │
│  ┌───────────────────┐  │
│  │ ✓ COMPLETED       │  │
│  │ Fibre cut SYD-MEL │  │
│  │ 9 steps · 139s    │  │
│  └───────────────────┘  │
└─────────────────────────┘
```

Multiple sessions can be `IN_PROGRESS` simultaneously — each has its own
Foundry thread, its own orchestrator background task, and its own event log.
The sidebar shows them all. Clicking any session loads its chat messages.

### R2.4 Frontend: `handleNewSession`

```typescript
// In useSession hook or App.tsx

const handleNewSession = () => {
  // 1. Disconnect SSE from current session (but don't cancel it)
  abortRef.current?.abort();

  // 2. Clear chat thread — show empty/welcome state
  setMessages([]);
  setActiveSessionId(null);
  setRunning(false);

  // Note: the previous session's orchestrator keeps running server-side.
  // It stays in SessionManager._active and appears in the sidebar.
  // The user can click it to reconnect at any time.
};
```

Key point: `handleNewSession` does **not** call `/cancel`. It simply
disconnects the frontend SSE and clears local state. The backend session
continues running and its events accumulate in `Session.event_log[]`.

### R2.5 Frontend: SessionSidebar Update

```tsx
// components/SessionSidebar.tsx — updated header

interface SessionSidebarProps {
  sessions: SessionSummary[];
  activeSessionId: string | null;
  onSelect: (sessionId: string) => void;
  onNewSession: () => void;
  loading: boolean;
}

export function SessionSidebar({
  sessions, activeSessionId, onSelect, onNewSession, loading,
}: SessionSidebarProps) {
  const [filter, setFilter] = useState('');

  // ... existing filter logic ...

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="px-3 pt-3 pb-2 shrink-0">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
            Sessions
          </span>
        </div>

        {/* New Session button — always visible */}
        <button
          onClick={onNewSession}
          className="w-full flex items-center justify-center gap-1.5 py-2 px-3
                     text-xs font-medium rounded-lg border border-border
                     bg-neutral-bg3 hover:bg-neutral-bg4 hover:border-brand/30
                     text-text-secondary hover:text-text-primary
                     transition-colors"
        >
          <span className="text-sm">＋</span>
          New Session
        </button>
      </div>

      {/* Search filter */}
      <div className="px-3 pb-2 shrink-0">
        <input
          type="text"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Search sessions…"
          className="w-full text-[11px] px-2 py-1 rounded border border-border
                     bg-neutral-bg3 text-text-secondary placeholder-text-muted
                     focus:outline-none focus:border-brand/40"
        />
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto px-2 pb-2 space-y-2">
        {sessions.map(session => (
          <SessionCard
            key={session.id}
            session={session}
            isActive={activeSessionId === session.id}
            onClick={() => onSelect(session.id)}
          />
        ))}
      </div>
    </div>
  );
}
```

### R2.6 SessionCard with Live Status

```tsx
function SessionCard({ session, isActive, onClick }: {
  session: SessionSummary;
  isActive: boolean;
  onClick: () => void;
}) {
  const statusMeta = {
    pending:     { icon: '○', color: 'text-text-muted',    label: 'Pending' },
    in_progress: { icon: '●', color: 'text-brand',         label: 'In Progress', pulse: true },
    completed:   { icon: '✓', color: 'text-status-success', label: 'Completed' },
    failed:      { icon: '✗', color: 'text-status-error',   label: 'Failed' },
    cancelled:   { icon: '⊘', color: 'text-text-muted',    label: 'Cancelled' },
  }[session.status];

  return (
    <div
      onClick={onClick}
      className={`group cursor-pointer rounded-lg border p-2.5 transition-colors ${
        isActive
          ? 'border-brand/40 bg-brand/10'
          : 'border-border-subtle bg-neutral-bg3 hover:border-border-strong hover:bg-neutral-bg4'
      }`}
    >
      {/* Status badge */}
      <div className="flex items-center gap-1.5 mb-1">
        <span className={`text-xs ${statusMeta.color} ${statusMeta.pulse ? 'animate-pulse' : ''}`}>
          {statusMeta.icon}
        </span>
        <span className="text-[10px] font-medium text-text-muted uppercase">
          {statusMeta.label}
        </span>
        <span className="text-[10px] text-text-muted ml-auto">
          {formatTimeAgo(session.created_at)}
        </span>
      </div>

      {/* Alert preview */}
      <p className="text-xs text-text-secondary line-clamp-2 leading-relaxed">
        {session.alert_text}
      </p>

      {/* Step count */}
      {session.step_count > 0 && (
        <div className="mt-1.5 text-[10px] text-text-muted">
          {session.step_count} steps
        </div>
      )}
    </div>
  );
}
```

### R2.7 Backend: No Changes Needed

The backend already supports this. `SessionManager` allows multiple
concurrent active sessions (up to `MAX_ACTIVE_SESSIONS = 20`). Each session
has its own:

- Foundry thread
- Orchestrator background task
- Event log
- Subscriber list

The frontend just needs to manage which session is currently *displayed*.
Creating a new session while another is running is already a valid
`POST /api/sessions` call — the existing session keeps running.

### R2.8 Reconnecting to a Parked Session

When the user clicks a running session in the sidebar:

```typescript
const viewSession = async (sessionId: string) => {
  const res = await fetch(`/api/sessions/${sessionId}`);
  const session: SessionDetail = await res.json();

  setActiveSessionId(sessionId);
  setMessages(loadSessionMessages(session));

  // If still running, connect to live SSE stream
  if (session.status === 'in_progress') {
    const lastOrch = messages.findLast(m => m.role === 'orchestrator');
    if (lastOrch) connectToStream(sessionId, lastOrch.id);
  }
};
```

The SSE `/stream` endpoint replays all buffered events then tails live ones,
so even if the session has been running for 2 minutes with no subscriber, the
user sees the full history catch up instantly.

### R2.9 UX Flow

1. User submits alert "VPN-ACME-CORP SERVICE_DEGRADATION..."
2. Investigation starts — steps appear in chat thread
3. User notices something else while waiting — clicks **＋ New Session**
4. Chat clears to welcome state. Sidebar shows:
   - ⏳ VPN-ACME-CORP (4 steps, running...)
5. User submits new alert "BGP flap on PE-03..."
6. Second investigation runs in parallel. Sidebar shows:
   - ⏳ BGP flap PE-03 (2 steps, running...) ← active
   - ⏳ VPN-ACME-CORP (7 steps, running...)
7. User clicks VPN-ACME-CORP in sidebar
8. Chat thread loads with all 7+ steps that ran while they were away
9. Live SSE reconnects — new steps continue streaming in

---

## R3. Changes to [persistent.md](persistent.md)

These refinements are **additive** — they don't contradict existing sections:

| persistent.md Section | Impact |
|---|---|
| §3.2 `SessionManager` | Already supports concurrent sessions. No change. |
| §3.3 API Routes | Already supports multiple `POST /api/sessions`. No change. |
| §3.5 / §14 `useSession` hook | Add `handleNewSession` function. Add `onNewSession` prop threading. |
| §12.1 `ChatPanel` | No change (clear messages → empty state renders). |
| §20 Layout diagram | Updated in persistent.md to show resize handles. |
| §21.2 App.tsx layout | Updated in persistent.md to use `Resizable*` wrappers. |
| §21.4 Resize handles | Added to persistent.md (§21.4.1–21.4.4). |
| §23 "What This Eliminates" | Updated in persistent.md (3 localStorage keys, pointer handles). |
| §24 Implementation table | Updated in persistent.md (Resizable wrappers + useResizable listed). |

### New items for §17 Phase Table

| Phase | Addition |
|---|---|
| **Phase 3** | Add `ResizableGraph`, `ResizableSidebar`, `ResizableTerminal` wrappers. |
| **Phase 4** | Add `useResizable` hook. Add `handleNewSession` to `useSession`. |
| **Phase 5** | Add `＋ New Session` button to `SessionSidebar`. Add `SessionCard` with status badges. |

### Estimated Additional Effort

| Item | Estimate |
|---|---|
| `useResizable` hook | ~55 lines |
| `ResizableGraph` | ~20 lines |
| `ResizableSidebar` | ~25 lines |
| `ResizableTerminal` | ~25 lines |
| `handleNewSession` + wiring | ~15 lines |
| `SessionSidebar` (new session button) | ~40 lines |
| `SessionCard` (status badges) | ~50 lines |
| **Total** | **~230 lines** |

---

## R3. Fix: Restore Interleaved Step Timeline

### R3.1 Problem (Two Bugs)

The plan's `OrchestratorBubble` (§12.3) broke the investigation timeline in
two ways:

**Bug 1: Orchestrator Thoughts are detached from their steps.**

The plan introduced a `thinking: string[]` array on `ChatMessage` and rendered
all thinking blocks as a flat list at the *top* of the bubble:

```tsx
// BROKEN — all thoughts dumped at the top, detached from their steps
{message.thinking?.map((t, i) => (
  <OrchestratorThoughts key={i} reasoning={t} />
))}
```

But in the real backend, reasoning is **per-step** — each `StepEvent` already
has a `reasoning?: string` field (populated from `[ORCHESTRATOR_THINKING]` tags
in the orchestrator's connected-agent call arguments). The `step_thinking` SSE
event is just a transient "calling sub-agent…" status indicator, not the actual
reasoning text. Dumping those status strings into a `thinking[]` array produces
9 identical "calling sub-agent…" blocks with no useful content.

**Bug 2: Steps are collapsed into a single group.**

The `StepGroup` component (§12.4) hides all steps behind a summary line:

```
▸ Investigated with 8 agents    GraphExplorerAgent, TelemetryAgent, ...
```

This kills the streaming UX. In the current (working) UI, each step appears
*as it arrives* — you watch the investigation unfold in real time. With
`StepGroup`, you see nothing until all steps are done, then expand a collapsed
block to see them.

### R3.2 Root Cause

The plan tried to mimic Copilot's "Used 5 references" pattern, but that pattern
only works for *references* (passive context). Investigation steps are *actions*
— the user needs to watch them happen. Collapsing active work into a summary
defeats the purpose of the streaming UI.

The current `AgentTimeline` component does this correctly:

```tsx
// CORRECT — from AgentTimeline.tsx (the working code)
{steps.map((s) => (
  <div key={s.step} className="mb-2">
    {s.reasoning && (
      <>
        <OrchestratorThoughts reasoning={s.reasoning} ... />
        <div className="ml-4 h-1.5 border-l-2 border-brand/20" />
      </>
    )}
    <StepCard step={s} ... />
  </div>
))}
```

Each step renders individually. Reasoning is **above its own step**, connected
by a visual line. Steps appear one-by-one as `step_complete` events arrive.

### R3.3 Fix: Flatten the Chat Thread — No Wrapper Boxes

The key realization: wrapping everything in an "OrchestratorBubble" box creates
an ugly nested container that fights the existing component style. The
`OrchestratorThoughts` and `StepCard` components already look great on their
own — they have their own borders, backgrounds, and expand/collapse behavior.
Putting them inside another box just adds visual noise.

**The fix:** Render each chat turn as a **sequence of top-level elements** in
the thread — not wrapped in a container. The chat thread becomes a flat list
of items that happen to be grouped by turn.

#### Updated ChatMessage Type

```typescript
export interface ChatMessage {
  id: string;
  role: ChatRole;
  timestamp: string;

  // User messages
  text?: string;

  // Orchestrator messages
  steps?: StepEvent[];           // reasoning lives on each step.reasoning
  diagnosis?: string;
  runMeta?: RunMeta;
  status?: 'thinking' | 'investigating' | 'complete' | 'error';
  errorMessage?: string;
}
```

`thinking: string[]` is removed. The `step_thinking` SSE event is transient
UI state (drives `ThinkingDots`), not a stored field.

#### Updated UserMessage Component (Full-Width, Collapsible)

The user prompt should match the style of other elements — full-width, with a
glass-card style, and collapsible since alert text can be very long:

```tsx
function UserMessage({ message }: { message: ChatMessage }) {
  const [expanded, setExpanded] = useState(false);
  const text = message.text ?? '';
  const isLong = text.length > 200;

  return (
    <div
      className="glass-card p-3 cursor-pointer transition-colors
                 hover:border-brand/20"
      onClick={() => isLong && setExpanded(v => !v)}
    >
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[10px] uppercase font-medium text-text-muted">You</span>
        <span className="text-[10px] text-text-muted">
          {formatTime(message.timestamp)}
        </span>
      </div>
      <p className={`text-sm text-text-primary whitespace-pre-wrap ${
        !expanded && isLong ? 'line-clamp-3' : ''
      }`}>
        {text}
      </p>
      {isLong && (
        <button className="text-[10px] text-text-muted hover:text-brand mt-1">
          {expanded ? '▴ Collapse' : '▾ Show full alert'}
        </button>
      )}
    </div>
  );
}
```

Key differences from the broken `UserBubble`:
- **Full width** (no `max-w-[85%]`, no `justify-end`)
- **`glass-card`** style matches `StepCard` and `OrchestratorThoughts`
- **Collapsible** for long alert text (NOC alerts can be 20+ lines)
- No separate "bubble" aesthetic — it's just another card in the flow

#### Updated ChatPanel — Flat Rendering

The `OrchestratorBubble` wrapper is **deleted**. Instead, each orchestrator
turn's elements render directly into the chat thread. The chat thread is just
a flat sequence of `UserMessage`, `OrchestratorThoughts`, `StepCard`,
`ThinkingDots`, `DiagnosisBlock`, etc.

```tsx
export function ChatPanel({
  messages, currentThinking, running, onSubmit, onCancel, exampleQuestions,
}: ChatPanelProps) {

  // Per-step expand/collapse state, shared across the whole thread
  const [expandedSteps, setExpandedSteps] = useState<Record<string, boolean>>({});
  const [expandedThoughts, setExpandedThoughts] = useState<Record<string, boolean>>({});

  const toggleStep = (msgId: string, stepNum: number) => {
    const key = `${msgId}-${stepNum}`;
    setExpandedSteps(prev => ({ ...prev, [key]: !prev[key] }));
  };
  const toggleThought = (msgId: string, stepNum: number) => {
    const key = `${msgId}-t-${stepNum}`;
    setExpandedThoughts(prev => ({ ...prev, [key]: !prev[key] }));
  };

  return (
    <div className="flex flex-col">
      <div className="p-4 space-y-2">
        {messages.length === 0 && (
          <EmptyState exampleQuestions={exampleQuestions} onSelect={onSubmit} />
        )}

        {messages.map((msg) => {
          if (msg.role === 'user') {
            return <UserMessage key={msg.id} message={msg} />;
          }

          // Orchestrator turn — render elements FLAT, no wrapper box
          const steps = msg.steps ?? [];
          const isLive = msg.status === 'thinking' || msg.status === 'investigating';

          return (
            <div key={msg.id} className="space-y-2">
              {/* Each step renders at the top level with its reasoning */}
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
                  <StepCard
                    step={s}
                    expanded={expandedSteps[`${msg.id}-${s.step}`] ?? false}
                    onToggle={() => toggleStep(msg.id, s.step)}
                  />
                </div>
              ))}

              {/* Live thinking indicator between steps */}
              {isLive && !msg.diagnosis && (
                <ThinkingDots agent="Orchestrator" status="processing..." />
              )}

              {/* Error */}
              {msg.errorMessage && (
                <div className="glass-card p-3 border-status-error/30 bg-status-error/5">
                  <span className="text-xs text-status-error">⚠ {msg.errorMessage}</span>
                </div>
              )}

              {/* Diagnosis — same glass-card style, collapsible */}
              {msg.diagnosis && (
                <DiagnosisBlock text={msg.diagnosis} />
              )}

              {/* Run meta footer */}
              {msg.runMeta && (
                <div className="flex items-center justify-between text-[10px] text-text-muted px-1">
                  <span>
                    {msg.runMeta.steps} step{msg.runMeta.steps !== 1 ? 's' : ''} · {msg.runMeta.time}
                  </span>
                  <button
                    onClick={() => navigator.clipboard.writeText(msg.diagnosis ?? '')}
                    className="hover:text-text-primary transition-colors"
                  >
                    Copy
                  </button>
                </div>
              )}
            </div>
          );
        })}

        {/* Global thinking indicator for new turns */}
        {currentThinking && (
          <ThinkingDots agent={currentThinking.agent} status={currentThinking.status} />
        )}
      </div>

      {/* Bottom-pinned input */}
      <ChatInput onSubmit={onSubmit} onCancel={onCancel} running={running} />
    </div>
  );
}
```

#### DiagnosisBlock — Also a Top-Level Card

The diagnosis block renders as its own glass-card, not nested inside a bubble:

```tsx
function DiagnosisBlock({ text }: { text: string }) {
  const [expanded, setExpanded] = useState(true); // auto-expand

  return (
    <div className="glass-card overflow-hidden">
      <button
        onClick={() => setExpanded(v => !v)}
        className="w-full flex items-center gap-2 px-3 py-2 text-xs font-medium
                   text-text-muted hover:text-text-primary transition-colors"
      >
        <span>{expanded ? '▾' : '▸'}</span>
        <span>Diagnosis</span>
      </button>
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div className="prose prose-sm max-w-none px-3 pb-3">
              <ReactMarkdown>{text}</ReactMarkdown>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
```

#### What changed vs the plan

| Aspect | Plan (§12) | Fixed |
|---|---|---|
| User prompt | Right-aligned bubble, `max-w-[85%]`, not collapsible | Full-width `glass-card`, collapsible for long alerts |
| Orchestrator wrapper | Giant `OrchestratorBubble` box around everything | **No wrapper** — elements render flat in the thread |
| Steps | Nested inside OrchestratorBubble | Top-level `StepCard` components (same as current) |
| Orchestrator Thoughts | `thinking[]` array at top of bubble | Per-step `step.reasoning`, above each `StepCard` |
| Diagnosis | Nested inside OrchestratorBubble | Top-level `DiagnosisBlock` card |
| Visual style | New "bubble" aesthetic | **Same `glass-card` style** as existing components |

#### Updated Component Hierarchy

```
ChatPanel
├── ChatThread (flat list, no nesting)
│   │
│   ├── UserMessage              ← full-width glass-card, collapsible
│   │
│   ├── OrchestratorThoughts     ← step 1 reasoning (top level)
│   │   └── connector line
│   ├── StepCard                 ← step 1 (top level, streamed)
│   │
│   ├── OrchestratorThoughts     ← step 2 reasoning
│   │   └── connector line
│   ├── StepCard                 ← step 2
│   │
│   ├── ... (each step appears as it arrives)
│   │
│   ├── ThinkingDots             ← between steps while investigating
│   │
│   ├── DiagnosisBlock           ← glass-card, auto-expanded
│   ├── RunMetaFooter            ← "8 steps · 150s  Copy"
│   │
│   ├── UserMessage              ← follow-up question
│   │
│   ├── OrchestratorThoughts     ← turn 2, step 1
│   │   └── connector line
│   ├── StepCard                 ← turn 2, step 1
│   ├── ...
│   │
│   └── DiagnosisBlock           ← turn 2 diagnosis
│
└── ChatInput (sticky bottom)
```

`StepGroup` and `OrchestratorBubble` are both **deleted** from the plan.

#### Updated Event Mapping (§10.2 correction)

(Unchanged from previous R3 — `step_thinking` is transient, `step_complete`
appends to `steps[]`, reasoning lives on `step.reasoning`.)

### R3.4 Visual Comparison

**Before fix (plan §12 — broken):**
```
  ┌─ YOU ──────────────────────────────────────────┐
  │ (right-aligned bubble, small, not collapsible) │
  └────────────────────────────────────────────────┘

┌─ ORCHESTRATOR ──────────────────────────────────────┐
│  ◇ Orchestrator Thoughts  "calling sub-agent…"      │ ← useless
│  ◇ Orchestrator Thoughts  "calling sub-agent…"      │ ← 9 of these
│  ...                                                 │
│  ▸ Investigated with 8 agents [collapsed blob]       │ ← can't see steps
│  ▾ Diagnosis                                         │
│  ┌──────────────────────────────────────────────┐    │
│  │ # Incident Summary ...                       │    │
│  └──────────────────────────────────────────────┘    │
│  Everything crammed inside one giant bordered box    │
└──────────────────────────────────────────────────────┘
```

**After fix (flat thread — same style as current):**
```
┌ YOU ─────────────────────────────────────────────────┐
│ [AUTOMATED TRIGGER — Fabric Eventhouse...]           │
│ 14:31:14.077 WARNING MOB-5G-MEL-3011 SERVICE_DEG... │
│ 14:31:14.133 CRITICAL VPN-ACME-CORP SERVICE_DEG...  │ ← full-width,
│ ...                                                  │   collapsible
│                                        ▾ Show full   │
└──────────────────────────────────────────────────────┘

◇ Orchestrator Thoughts                           [▸]   ← top-level card
  "To diagnose the service degradation..."
│ (connector line)
● GraphExplorerAgent                           191.5s    ← top-level card
  ▸ Query: For the following services...
  ▸ Response: For the EnterpriseVPN...
                                          [View Graph]

◇ Orchestrator Thoughts                           [▸]
  "Now I need telemetry data..."
│
● TelemetryAgent                                12.7s
  ▸ Query: Get all alerts for LINK-SYD-MEL...
  ▸ Response: Recent alerts include...
                                           [View Data]
... (each step streams in one by one)

◇ Orchestrator Thoughts                           [▸]
  "Based on all findings, I can now write..."
│
▾ Diagnosis                                              ← top-level card
┌──────────────────────────────────────────────────────┐
│ # Incident Summary                                   │
│ At 14:31:14, a burst of 20 correlated alerts was ... │
│ ...                                                  │
└──────────────────────────────────────────────────────┘
8 steps · 150s                                     Copy
```

Every element uses the same `glass-card` style. No wrapper box. Identical
to the current working `AgentTimeline` — just with user messages interspersed
between orchestrator turns.

### R3.5 Changes to [persistent.md](persistent.md)

| Section | Change Required |
|---|---|
| §10.1 `ChatMessage` type | Remove `thinking?: string[]` field |
| §10.2 Event mapping table | `step_thinking` is transient indicator, not stored |
| §11 Component hierarchy | Flat list — delete `OrchestratorBubble`, `StepGroup`, `UserBubble`. Replace with `UserMessage` + top-level `OrchestratorThoughts`/`StepCard`/`DiagnosisBlock` |
| §12.1 `ChatPanel` | Replace with flat rendering version (R3.3 in this document) |
| §12.2 `UserBubble` | **Delete** — replaced by `UserMessage` (full-width, collapsible glass-card) |
| §12.3 `OrchestratorBubble` | **Delete entirely** — no wrapper box |
| §12.4 `StepGroup` | **Delete entirely** |
| §12.5 `DiagnosisBlock` | Keep but simplify — standalone glass-card, no `onToggle` prop needed (internal state) |
| §14 `updateOrchestratorMessage` | Remove `thinking` accumulation; `step_thinking` drives UI indicator only |
| §14 `loadSessionMessages` | Remove `thinking` reconstruction |

### R3.6 Estimated Fix Effort

Mostly *removing* code:

| Item | Change |
|---|---|
| Delete `OrchestratorBubble` component | -60 lines |
| Delete `StepGroup` component | -50 lines |
| Delete `UserBubble` component | -15 lines |
| New `UserMessage` component | +25 lines |
| New `DiagnosisBlock` (standalone) | +25 lines |
| Update `ChatPanel` (flat rendering) | ~0 net (simpler than before) |
| Remove `thinking[]` from types & hook | -15 lines |
| **Net** | **~-90 lines** (significant simplification) |