# Task 01: Current User Experience — Execution Log

> Strategy: [task_01_current_user_experience.md](../strategy/task_01_current_user_experience.md)

**Status**: complete  
**Date**: 2025-02-20

---

## 1. First Load Experience

### 1.1 Bootstrap Sequence

**File**: `frontend/src/main.tsx` L1–L16

1. React mounts `<ThemeProvider>` → `<ScenarioProvider>` → `<App>`.
2. `ThemeProvider` reads theme preference (localStorage or system `prefers-color-scheme`).
3. `ScenarioProvider` (`ScenarioContext.tsx` L7–L15) calls `getScenario()` which fires `fetch("/api/config/scenario")`. During the fetch, `SCENARIO_DEFAULTS` is used: `displayName: "Loading..."`, empty `exampleQuestions[]`, empty `graphStyles`.

### 1.2 Initial Visual State

Once `App` mounts (`App.tsx` L25–L195), the user sees a **full-height, three-zone vertical layout** with a **sidebar** on the right:

| Zone | Component | Initial State |
|------|-----------|---------------|
| **Header strip** (h-12, fixed) | `Header.tsx` | Brand diamond `◆`, title "3IQ Demo — Fabric Graphs + Foundry Agents", scenario badge showing `"Loading..."` (until `/api/config/scenario` resolves). Right side: "Open Foundry" link, "Open Fabric" link, "⚙ Services" button, "Tabs" toggle (active), "Console" toggle (active), theme toggle. |
| **Tab bar** (below header) | `TabBar.tsx` | 4 tabs: `▸ Investigate` (active, brand-colored underline), `◇ Resources`, `📋 Scenario`, `🔗 Graph Ontology`. |
| **Main content area** | Flex column | Investigate tab content (see below). |

### 1.3 Investigate Tab Layout (Default)

The Investigate tab (`App.tsx` L108–L172) is a horizontal flex with three vertical zones in the main column and a sidebar:

```
┌──────────────────────────────────────────────────────────────┬──────────┐
│  ResizableGraph (280px default, stored in localStorage)      │          │
│    └── MetricsBar → GraphTopologyViewer                      │          │
│  ════════════════ drag handle ════════════════                │  Session │
│  ChatPanel (flex-1, scrollable)                              │  Sidebar │
│    └── Empty state: ◇ diamond + "Submit an alert..."         │  (288px) │
│  ──────────────────────────────────────────────               │          │
│  ChatInput (pinned at bottom of chat section)                │          │
│  ════════════════ drag handle ════════════════                │          │
│  ResizableTerminal (200px default)                           │          │
│    └── TerminalPanel → TabbedLogStream (API | Graph API)     │          │
└──────────────────────────────────────────────────────────────┴──────────┘
```

### 1.4 Graph Panel

**Component**: `GraphTopologyViewer.tsx` L18–L263, launched via `MetricsBar.tsx`.

- On mount, `useTopology()` fires `POST /query/topology` to fetch the network topology.
- While loading: the graph area is empty (no explicit loading skeleton in `GraphTopologyViewer` — just renders nothing until data arrives).
- Once data arrives: a force-directed graph renders with colored nodes (label-based colors from `SCENARIO.graphStyles.nodeColors`), edge lines, and node labels.
- Controls visible: `GraphHeaderBar` (node count, edge count, query time), `GraphToolbar` (per-label filter chips, color customization), `GraphEdgeToolbar` (edge label chips).
- User interaction: hover shows tooltip, right-click opens context menu, drag to pan, scroll to zoom, resize handle at bottom.

### 1.5 Chat Panel — Empty State

**Component**: `ChatPanel.tsx` L35–L43

When `messages.length === 0 && !currentThinking`:
- Centered vertically and horizontally.
- Brand diamond `◇` at 3xl, 40% opacity.
- Text: "Submit an alert to begin investigation" (14px, muted).
- Subtext: "Use the examples dropdown or paste a NOC alert below." (12px, muted).

### 1.6 Chat Input — Ready State

**Component**: `ChatInput.tsx` L58–L142

- Bottom bar with `border-t`, `bg-neutral-bg2`, 12px padding.
- **Left**: 💡 button (if `exampleQuestions.length > 0` — initially false because `SCENARIO_DEFAULTS.exampleQuestions` is empty; becomes visible once scenario fetch resolves).
- **Center**: Textarea, 1 row, `placeholder="Ask a follow-up or paste a new alert..."`, enabled, auto-resizes up to 120px height.
- **Right**: `↑` send button, `bg-brand`, disabled (opacity 30%) because `text.trim()` is empty.
- Keyboard: Ctrl+Enter / Cmd+Enter triggers submit (`ChatInput.tsx` L30–L34).

### 1.7 Terminal Panel — Initial State

**Component**: `TerminalPanel.tsx` → `TabbedLogStream` → `LogStream`

- 200px height (resizable via top drag handle).
- Two tabs: **API** (active) and **Graph API**.
- Each tab opens an `EventSource` SSE connection to `/api/logs` or `/query/logs`.
- Initially shows: `">_ API"` header + green dot (connected) + level filter dropdown (`DEBUG+`) + 🗑 clear button.
- Log body: italic muted text "Waiting for log output..." until first SSE event arrives.
- Both streams are mounted simultaneously (kept alive for SSE continuity, `TabbedLogStream.tsx` L30–L38) — inactive tab is `display: hidden`.

### 1.8 Session Sidebar — Initial State

**Component**: `SessionSidebar.tsx` L100–L218

- Right edge, 288px default width (resizable via left drag handle).
- Header: "SESSIONS" label + ↻ refresh button + ▶ collapse button.
- Below: "＋ New Session" button + search filter input.
- `useSessions` hook (`useSessions.ts` L1–L36) fires `GET /api/sessions` on mount.
- While loading (`loading && sessions.length === 0`): 3 skeleton cards (h-20, rounded-lg, animate-pulse).
- After load, if empty (`!loading && sessions.length === 0`): ◇ diamond + "No sessions yet. Submit an alert to start an investigation."
- If sessions exist: `SessionCard` list, newest first, each showing `StatusBadge`, time ago, alert text preview (line-clamp-2), step count.

### 1.9 Scroll-to-Bottom FAB

**Component**: `App.tsx` L175–L183

- Hidden initially (`!isNearBottom && running` — `running` is false).
- Only appears during a live investigation when the user has scrolled away from the bottom.
- Renders as: fixed position, bottom-20 right-80, "↓ New steps", brand-colored rounded pill.

---

## 2. Starting a New Investigation

### 2.1 Selecting an Example Question

**Prerequisite**: Scenario config has loaded (💡 button visible).

1. User clicks 💡 button → `examplesOpen` toggles to `true` (`ChatInput.tsx` L70).
2. A dropdown animates in from bottom (framer-motion: opacity 0→1, y 8→0, duration 0.15s, `ChatInput.tsx` L80–L82).
3. Dropdown: `w-80`, max-h-64 with scroll, positioned `bottom-full` (above the button), dark background, border, shadow-xl.
4. Each example renders as a full-width text button prefixed with 💡 (`ChatInput.tsx` L88–L99).
5. Clicking an example: sets `text` state to the example string, closes dropdown, focuses the textarea (`ChatInput.tsx` L92–L95).
6. Outside click (anywhere else on page) closes the dropdown (`ChatInput.tsx` L46–L53).

### 2.2 Typing Manually

1. User types in textarea → `text` state updates → auto-resize effect fires (`ChatInput.tsx` L35–L39`): resets height to `auto`, then sets to `min(scrollHeight, 120)px`.
2. Send button transitions from disabled (opacity-30) to enabled (full opacity, bg-brand, hoverable).

### 2.3 Submission

User presses `↑` button or Ctrl+Enter.

**`handleSubmit`** (`ChatInput.tsx` L19–L22):
1. Guards: `text.trim()` empty or `running` true → return.
2. Calls `onSubmit(text.trim())` → `App.handleSubmit()` → `createSession(SCENARIO.name, text)` (`App.tsx` L73–L79).
3. Text state cleared to `''`.

**`createSession`** (`useSession.ts` L138–L166):

| Step | What happens | UI effect |
|------|-------------|-----------|
| 1 | Create `userMsg: ChatMessage` with `role: 'user'`, `text: alertText`, current timestamp | — |
| 2 | `setMessages([userMsg])` | **Immediate**: Chat panel replaces empty state with the `UserMessage` card. Previous messages (if any from a prior session) are **replaced**. |
| 3 | `fetch('/api/sessions', POST, {scenario, alert_text})` | **Network wait** — no loading indicator visible. The user sees their message but nothing else. |
| 4 | Response: `{session_id}` → `setActiveSessionId(session_id)` | Sidebar card for this session does not yet appear (refetch hasn't run). |
| 5 | Create `orchMsg: ChatMessage` with `role: 'orchestrator'`, `status: 'thinking'`, `steps: []`, timestamp | — |
| 6 | `setMessages(prev => [...prev, orchMsg])` | **Immediate**: An empty orchestrator message block appears. Because `status === 'thinking'` and `!msg.diagnosis`, the ChatPanel renders `ThinkingDots` inside the orchestrator message div (`ChatPanel.tsx` L95–L97). |
| 7 | `connectToStream(session_id, orchMsgId)` | SSE connection opens to `/api/sessions/{id}/stream`. `running` set to `true`. |
| 8 | `refetchSessions()` called in `App.handleSubmit()` (`App.tsx` L80) | Sidebar fetches updated session list — the new session card appears (status `in_progress`, animate-pulse dot). |

### 2.4 Visual State After Submission (Before First SSE Event)

```
┌─────────────────────────────────────────────┐
│ [UserMessage card]                          │
│   "You"                        "14:32:05"   │
│   <alert text, up to 3 lines if long>       │
│                                             │
│ [ThinkingDots]                              │
│   ● ● ● Orchestrator — processing...       │
└─────────────────────────────────────────────┘
```

- ChatInput: textarea shows `placeholder="Investigation in progress..."`, disabled (opacity-50).
- Send button replaced by ⏹ cancel button (red tint, `bg-status-error/20`).
- Sidebar: new session card with `● In Progress` (animate-pulse) badge.
- **Latency gap**: Between step 3 (POST) and step 7 (first SSE event), there is a wait of ~1-5 seconds where only ThinkingDots are visible. No progress percentage, no ETA.

---

## 3. Live Investigation Progress

### 3.1 SSE Event → UI Mapping

Events arrive from `GET /api/sessions/{id}/stream`. Each is processed in `connectToStream` (`useSession.ts` L84–L131) which:
1. Parses JSON data.
2. Updates `thinking` state (the global `ThinkingDots` indicator).
3. Calls `updateOrchestratorMessage(targetMsgId, ev.event, data)` which immutably updates the specific orchestrator `ChatMessage`.

#### Event: `run_start`

- **Handler**: Not explicitly handled in `updateOrchestratorMessage` switch — falls through with no state change.
- **Thinking state**: not set.
- **UI effect**: None visible. This event is informational (logged to event_log server-side).

#### Event: `step_thinking`

- **Handler** (`useSession.ts` L26–L28): `updated.status = 'investigating'`.
- **Thinking state**: set to `{agent: data.agent, status: data.status}` (`useSession.ts` L103).
- **UI effect**: `ThinkingDots` appears/updates at the bottom of ChatPanel (`ChatPanel.tsx` L119–L121) showing: `"● ● ● <agent> — <status>"` (e.g., "Orchestrator — calling sub-agent..."). The three dots animate with staggered bounce (0ms, 150ms, 300ms delay).

#### Event: `step_started`

- **Handler** (`useSession.ts` L29–L38): Appends a new step to `msg.steps[]` with `pending: true`. `status = 'investigating'`.
- **Thinking state**: set to `null` — clears the ThinkingDots (`useSession.ts` L107).
- **UI effect**: A new `StepCard` appears in the chat thread with:
  - **Header**: `●` pulsing dot (animate-pulse, brand color) + `"<AgentName> — Querying…"` (`StepCard.tsx` L143–L147).
  - **Collapsed body** (default): `"▸ Query: <first 80 chars>"` truncated + pulsing dot + "Querying…" (`StepCard.tsx` L165–L174).
  - Card enters with framer-motion: opacity 0→1, y 10→0, duration 0.2s, easeOut (`StepCard.tsx` L128–L131).
  - If the step has `reasoning`, an `OrchestratorThoughts` card appears **above** the StepCard with a connecting line (`ChatPanel.tsx` L71–L78`). Defaults to **collapsed** — shows "Orchestrator Thoughts..." with `▸` chevron.

#### Event: `step_response`

- **Handler** (`useSession.ts` L39–L44): Finds existing step by `step` number, merges `data` in, sets `pending: false`. `status = 'investigating'`.
- **Thinking state**: set to `null` (`useSession.ts` L109).
- **UI effect**: The pending StepCard transitions:
  - Dot changes from pulsing `animate-pulse` to solid brand color.
  - Agent name text removes "— Querying…" suffix.
  - Collapsed body: `"▸ Query: ..."` + `"▸ Response: <first 80 chars>"` replaces the pulsing indicator.
  - Duration and timestamp appear in the header right side.

#### Event: `step_complete`

- **Handler** (`useSession.ts` L45–L57): If a step with the same number exists, merges data and sets `pending: false`. If not, appends new step (backward compat for replay).  `status = 'investigating'`.
- **Thinking state**: set to `null` (`useSession.ts` L110).
- **UI effect**: Identical to `step_response` for the incremental path. For the replay/non-incremental path, a fully-formed step card appears at once.

#### Event: `message`

- **Handler** (`useSession.ts` L58–L60): Sets `msg.diagnosis = data.text`. `status = 'complete'`.
- **Thinking state**: set to `null` (`useSession.ts` L110).
- **UI effect**: 
  - ThinkingDots disappears.
  - `DiagnosisBlock` appears below all step cards (`ChatPanel.tsx` L105–L107).
  - DiagnosisBlock (`DiagnosisBlock.tsx`): glass-card container with "▾ Diagnosis" header button (auto-expanded on first render, `expanded = true`). Content rendered as markdown via `ReactMarkdown`.
  - Animates in: height 0→auto, opacity 0→1, duration from framer-motion.

#### Event: `run_complete`

- **Handler** (`useSession.ts` L61–L63): Sets `msg.runMeta = data`. `status = 'complete'`.
- **Thinking state**: set to `null`.
- **UI effect**: Run meta footer appears below DiagnosisBlock (`ChatPanel.tsx` L110–L120`):
  - Left: `"<N> steps · <time>"` (e.g., "5 steps · 12.3s").
  - Right: "Copy" button — copies `msg.diagnosis` text to clipboard.
  - Font: 10px, muted gray.

#### Event: `error`

- **Handler** (`useSession.ts` L64–L66): Sets `msg.errorMessage = data.message`. `status = 'error'`.
- **Thinking state**: set to `null`.
- **UI effect**: Error card appears below step cards (`ChatPanel.tsx` L100–L103):
  - Glass-card with error-tinted border (`border-status-error/30`) and background (`bg-status-error/5`).
  - Content: `"⚠ <error message>"` in status-error color, 12px.

#### Event: `action_executed`

- **Handler** (`useSession.ts` L67–L69): No state update (informational only — the actual step data arrives via `step_complete` with `is_action: true`).
- **Thinking state**: set to `null` (`useSession.ts` L113).
- **UI effect**: None directly. The corresponding `step_complete` event renders an `ActionCard` instead of a `StepCard` (branched in `ChatPanel.tsx` L83–L90`).

#### Event: `done`

- **Handler** (`useSession.ts` L97): `ctrl.abort()` — closes the SSE connection cleanly.
- **Thinking state**: cleared in `.finally()` block.
- **UI effect**: `running` becomes `false` in `.finally()`. ChatInput re-enables: textarea becomes active with normal placeholder, send button replaces cancel button.

### 3.2 StepCard States Summary

| State | Dot | Agent Text | Body | Duration |
|-------|-----|-----------|------|----------|
| Pending | `●` pulsing | `"<Agent> — Querying…"` | Query preview + pulsing "Querying…" | Not shown |
| Completed (collapsed) | `●` solid | `"<Agent>"` | `"▸ Query: ..."` + `"▸ Response: ..."` | Shown |
| Completed (expanded) | `●` solid | `"<Agent>"` | Full query block + full response (markdown rendered) + viz button | Shown |
| Error (collapsed) | `●` error-red | `"<Agent> — FAILED"` | Error icon + friendly summary | Shown |
| Error (expanded) | `●` error-red | `"<Agent> — FAILED"` | Error icon + summary + detail + error code badge | Shown |

### 3.3 ActionCard Rendering

**Component**: `ActionCard.tsx` L1–L118

When `step.is_action === true` and `step.action` is defined:

- Amber-bordered card (not glass-card — distinct amber theme: `border-amber-500/40 bg-amber-500/5`).
- **Header**: ⚡ icon + "ACTION — <agent_name>" in amber caps + urgency badge (CRITICAL=red, HIGH=amber, STANDARD=blue) + "DISPATCHED ✓" emerald badge.
- **Summary**: "Dispatched **<engineer name>** to <destination description>".
- **Details grid**: phone, GPS coordinates, dispatch ID, time.
- **Sensor IDs**: horizontal wrapping chips of sensor IDs in monospace.
- **View Action button**: bottom-right, amber-styled, "📧 View Action".
- Clicking "View Action" opens `ActionEmailModal` — full-screen overlay with email preview (To, Subject, Sent, monospace email body, "Open in Google Maps" link, "Copy email" button).

### 3.4 Visualization Button

**Component**: `StepCard.tsx` L258–L278

On completed, non-error steps with `response.length > 10`:
- Bottom-right of StepCard: bordered pill button showing agent-specific icon + label:
  - `GraphExplorerAgent` → `"⬡ View Graph"`
  - `TelemetryAgent` → `"▤ View Data"`
  - `RunbookKBAgent` → `"▧ View Docs"`
  - `HistoricalTicketAgent` → `"▧ View Docs"`
  - Default → `"▧ View Docs"`
- Click opens `StepVisualizationModal` and triggers `useVisualization.getVisualization(step)`.

---

## 4. Multi-Turn Follow-Up

### 4.1 Availability

Follow-up is available when:
- `activeSessionId` is set (a session exists).
- `running` is `false` (current turn is complete).
- The ChatInput placeholder reads `"Ask a follow-up or paste a new alert..."`.

### 4.2 Sending a Follow-Up

**`sendFollowUp`** (`useSession.ts` L170–L195):

| Step | What happens | UI effect |
|------|-------------|-----------|
| 1 | Create `userMsg` + `orchMsg` (status `'thinking'`, empty steps) | — |
| 2 | `setMessages(prev => [...prev, userMsg, orchMsg])` | **Prior turn's messages remain visible**. New UserMessage card appends at bottom, followed by ThinkingDots inside a new orchestrator block. Chat auto-scrolls if user is near bottom. |
| 3 | `fetch(POST /api/sessions/{id}/message, {text})` | **Network wait** — no loading indicator beyond ThinkingDots. |
| 4 | Response: `{event_offset}` — the event_log length before this turn | — |
| 5 | `connectToStream(activeSessionId, orchMsgId, event_offset)` | SSE reconnects to `/api/sessions/{id}/stream?since={event_offset}`. Only new-turn events play. `running = true`. |

### 4.3 Visual State During Follow-Up

The chat thread now shows:

```
[UserMessage — original alert]
[StepCard 1]
[StepCard 2]
...
[DiagnosisBlock — first turn diagnosis]
[RunMeta — "5 steps · 12.3s"]

[UserMessage — follow-up text]        ← NEW
[ThinkingDots — Orchestrator]         ← NEW
```

- All prior turn content is preserved and scrollable.
- New steps from the follow-up append at the bottom.
- The `since` parameter ensures SSE replay does NOT re-emit prior turn events.

### 4.4 Routing Logic

**`App.handleSubmit`** (`App.tsx` L73–L79):
- If `activeSessionId` exists AND `!running` → `sendFollowUp(text)`.
- If no `activeSessionId` AND `!running` → `createSession(SCENARIO.name, text)`.
- If `running` → neither fires (input is disabled, but the guard exists).

**Implication**: There is no way for the user to start a *new* session while viewing an existing one without first clicking "＋ New Session" in the sidebar. Typing in the input and pressing send will always send a follow-up to the active session.

---

## 5. Session Sidebar Interactions

### 5.1 Session Card

**Component**: `SessionSidebar.tsx` → `SessionCard` L36–L91

Each card displays:
- **StatusBadge** (L17–L30): icon + label + color
  - `pending`: `○ Pending` (muted)
  - `in_progress`: `● In Progress` (brand color, animate-pulse)
  - `completed`: `✓ Completed` (green-400)
  - `failed`: `✗ Failed` (status-error red)
  - `cancelled`: `⏹ Cancelled` (yellow-400)
- **Time ago** (right side): relative time via `formatTimeAgo()` — "just now", "3m ago", "2h ago", "1d ago".
- **Delete button** (right side): hidden by default, appears on card hover (`opacity-0 group-hover:opacity-100`). Shows "✕" initially.
- **Alert preview**: first 100 chars of `alert_text`, 2-line clamp.
- **Step count**: `"N steps"` if `step_count > 0`.
- **Active indicator**: if `session.id === activeSessionId`, card has brand-tinted border and background.

### 5.2 Clicking a Session Card

Calls `onSelect(session.id)` → `viewSession(sessionId)` (`useSession.ts` L303–L318):

| Step | What happens | UI effect |
|------|-------------|-----------|
| 1 | Abort current SSE if any, `running=false`, `thinking=null` | Any live stream stops. |
| 2 | `fetch(GET /api/sessions/{sessionId})` | **Network wait** — the chat area still shows previous content until response. No loading skeleton or spinner. |
| 3 | Response: `SessionDetail` JSON | — |
| 4 | `setActiveSessionId(sessionId)` | Sidebar card highlights. |
| 5 | `loadSessionMessages(session)` → reconstruct `ChatMessage[]` from `event_log` | Parses all events: `run_start` creates orchestrator message, `step_complete` adds steps, `message` adds diagnosis, `user_message` creates user messages (multi-turn). Synthesises initial user message from `alert_text` if no `user_message` events exist. |
| 6 | `setMessages(reconstructed)` | **Instant replacement**: entire chat panel re-renders with the historical session. |
| 7 | If `session.status === 'in_progress'`: find last orchestrator message, `connectToStream(sessionId, lastOrch.id)` | Live stream resumes for in-progress sessions — steps continue to animate in. |

### 5.3 Delete Flow

**Component**: `SessionCard.handleDeleteClick` (`SessionSidebar.tsx` L42–L50)

1. First click on ✕ → `confirming = true`. Button text changes to `"Delete?"` in red, becomes always-visible.
2. Auto-cancel: `setTimeout` resets `confirming` to false after 3 seconds.
3. Second click within 3s → calls `onDelete(session.id)` → `deleteSession(sessionId)` (`useSession.ts` L239–L252).
4. `deleteSession`: sends `DELETE /api/sessions/{id}`. If the deleted session is the active one, clears all UI state (messages, activeSessionId, running, thinking).

### 5.4 New Session Button

- "＋ New Session" button above the search filter.
- Calls `onNewSession()` → `handleNewSession()` (`useSession.ts` L224–L229): aborts SSE, clears messages, clears `activeSessionId`, sets `running=false`.
- **Result**: Chat panel returns to empty state. ChatInput re-enables. Sidebar de-highlights the active card.

### 5.5 Search Filter

- Text input below the New Session button.
- Filters `sessions` array by `alert_text.toLowerCase().includes(filter)` (`SessionSidebar.tsx` L118–L122).
- If no matches: `"No matches for "<filter>""`.
- Filter is local-only — does not re-fetch from the server.

### 5.6 Refresh Button

- ↻ button in sidebar header.
- Calls `onRefresh()` → `refetchSessions()` → re-fetches `GET /api/sessions`.
- Also auto-triggered when `running` transitions true→false (`App.tsx` L48–L54`).

### 5.7 Collapse/Expand

- ▶ button in sidebar header toggles `sidebarCollapsed`.
- Collapsed: sidebar narrows to `w-8` with no content except the ◀ expand button.
- Expanded: full sidebar at stored width (default 288px, resizable).

---

## 6. Cancellation Experience

### 6.1 Triggering Cancellation

**When available**: `running === true` — the ⏹ cancel button is visible in ChatInput.

**Flow**:

1. User clicks ⏹ → `onCancel()` → `cancelSession()` (`useSession.ts` L254–L259).
2. If `activeSessionId` exists: sends `POST /api/sessions/{id}/cancel`.
3. If no `activeSessionId` (legacy path): just aborts the local `AbortController`.

### 6.2 Server-Side Processing

- API receives cancel request → sets `session._cancel_event` (`routers/sessions.py` L131).
- Pushes `status_change` event: `{status: "cancelling", message: "Cancellation requested — waiting for current agent call to finish."}`.
- **The current Foundry agent call continues to completion.** Cancel is checked only between retry attempts.

### 6.3 UI During Cancellation

- The `status_change` event is **not handled** in `updateOrchestratorMessage` — it falls through the switch with no match. The event is silently ignored in the frontend.
- The user sees: ThinkingDots continue animating. No "Cancelling..." text appears.
- Eventually, the orchestrator session completes (either the current step finishes and `_cancel_event` is detected, or the run finishes normally).
- `_finalize_turn` marks session as `CANCELLED`, and the SSE `done` event fires → SSE closes → `running` becomes `false`.
- **Gap**: The user gets no visual feedback that cancellation was acknowledged. They must wait potentially 30–60 seconds for the current agent call to finish, seeing no change in the UI.

---

## 7. Error States

### 7.1 Orchestrator Failure (Non-Capacity)

- `step_complete` events with `error: true` render as error-styled StepCards (red border, red dot, "FAILED" suffix).
- `parseErrorMessage()` in `StepCard.tsx` L14–L80 provides friendly messages for known patterns:
  - `504/gateway timeout` → `"Gateway timeout — the backend query took too long"` with ⏱ icon
  - `502/bad gateway` → `"Bad gateway — upstream service unavailable"` with 🔌 icon
  - `404/not found` → `"Endpoint not found — data source may need rediscovery"` with 🔍 icon
  - `401/403/unauthorized` → `"Authentication failed"` with 🔒 icon
  - `429/rate limit` → `"Rate limited — too many requests"` with 🚦 icon
  - Fallback → `"Agent call failed"` with ⚠ icon
- The **orchestrator may retry** (MAX_RUN_ATTEMPTS=2). During retry, a `step_thinking` event fires: `"Retrying investigation (attempt 2/2)..."`.

### 7.2 Final `error` Event

- If all retries are exhausted, an `error` event arrives.
- Sets `msg.errorMessage` and `msg.status = 'error'`.
- Renders a glass-card error box: `"⚠ <message>"` in red.
- The error message includes context: `"Agent run interrupted — A backend query returned an error. N steps completed before the error. Retried 2 times. Error detail: ..."`.

### 7.3 Capacity Exhaustion

- Error message includes `"Fabric capacity exhausted"`.
- Same UI as 7.2.

### 7.4 Stuck Investigation Timeout (Legacy Path Only)

- Only fires in `run_orchestrator()` (non-session path): 120-second EVENT_TIMEOUT.
- The session path (`run_orchestrator_session`) has **no** event timeout.
- For sessions: the SSE stream can hang indefinitely. The frontend's `fetchEventSource` has no client-side timeout.
- The server-side SSE endpoint has a 120s per-event timeout that emits a `heartbeat` event (`routers/sessions.py` L89–L93`), preventing TCP close.

### 7.5 SSE Disconnect

- `onerror` in `connectToStream` (`useSession.ts` L125–L129): throws `new Error('SSE closed')` to prevent `fetchEventSource` from auto-retrying.
- `.finally()` sets `running=false`, `thinking=null`.
- **Result**: Investigation stops updating. No reconnection attempt. No error message shown to the user.
- **Recovery**: User can click the session card in the sidebar to reload via `viewSession()`, or send a follow-up.

### 7.6 Session Not Found

- `viewSession` fetches `GET /api/sessions/{id}`. If 404: the fetch doesn't throw (no `.ok` check in `useSession.ts` L305). It tries to parse the error response as `SessionDetail`, resulting in `loadSessionMessages` operating on a malformed object. Chat would show an empty or broken state.
- **Bug**: No error handling for failed session fetch.

---

## 8. Edge Cases & Micro-Interactions

### 8.1 Long Alert Text Collapse/Expand

**Component**: `UserMessage.tsx` L17–L50

- If `text.length > 200`: `isLong = true`.
- Card becomes clickable (`cursor-pointer hover:border-brand/20`).
- Text body has `line-clamp-3` (CSS limits to 3 lines with `...` truncation).
- Below text: `"▾ Show full alert"` / `"▴ Collapse"` toggle button (10px, muted, hover→brand).
- Both the card click and the button click toggle `expanded` state.
- The button uses `e.stopPropagation()` to prevent double-toggle.

### 8.2 Step Card Expand/Collapse

**Component**: `StepCard.tsx` L86–L296

- Default state: **collapsed** (controlled by `ChatPanel.expandedSteps` dict, keyed by `${msgId}-${stepNum}`).
- Clicking anywhere on the card toggles expand/collapse.
- Collapsed: shows query + response previews (first 80 chars, truncated).
- Expanded: full query block (code-style bg, whitespace-pre-wrap) + full response (markdown-rendered via ReactMarkdown) or error detail. Animates with framer-motion height 0→auto.
- Persist: expand state is in React component state (lost on page refresh or session switch).

### 8.3 Orchestrator Thoughts Toggle

**Component**: `OrchestratorThoughts.tsx`

- Renders only when `step.reasoning` exists.
- Default: **collapsed** (show "Orchestrator Thoughts..." with `▸`).
- Click expands to reveal italic reasoning text in quotes.
- Controlled by `ChatPanel.expandedThoughts` dict, keyed by `${msgId}-t-${stepNum}`.
- Connected to the StepCard below by a thin vertical line (`ChatPanel.tsx` L77`: `h-1.5 border-l-2 border-brand/20`).

### 8.4 Diagnosis Copy Button

- In run meta footer (`ChatPanel.tsx` L117`): "Copy" text button.
- Calls `navigator.clipboard.writeText(msg.diagnosis ?? '')`.
- No visual feedback on copy (no toast, no checkmark).

### 8.5 Examples Dropdown

- Described in §2.1 above.
- Positioned absolutely `bottom-full left-0` — floats above the button.
- Max height 256px with overflow scroll.
- Closing: click outside (mousedown listener), or select an example.

### 8.6 Ctrl+Enter Shortcut

- `ChatInput.tsx` L28–L33: listens for `(e.ctrlKey || e.metaKey) && e.key === 'Enter'`.
- Calls `handleSubmit()`.
- Regular Enter inserts a newline (default textarea behavior).

### 8.7 Textarea Auto-Resize

- `ChatInput.tsx` L35–L39: on every `text` change, resets height to `auto` then sets to `min(scrollHeight, 120)`.
- Grows from 1 row (40px `min-h-[2.5rem]`) up to ~120px.
- Max clamped by `max-h-[7.5rem]` CSS class (~120px).
- `resize-none` prevents manual drag-resize.

### 8.8 Auto-Scroll Behavior

**Component**: `useAutoScroll.ts`

- `scrollRef` attached to the chat scroll container (`App.tsx` L127`).
- On scroll: checks if user is within 200px of the bottom (`threshold = 200`).
- `isNearBottom` state tracks this.
- On `messages` or `currentThinking` change: if `isNearBottom`, calls `scrollToBottom()` (smooth scroll).
- If user scrolls up more than 200px from bottom: auto-scroll stops. The "↓ New steps" FAB appears (if `running`).
- FAB click: calls `scrollToBottom()` — smooth-scrolls to bottom.

### 8.9 Resizable Panels

**Hook**: `useResizable.ts`

- All three resizable zones (graph, sidebar, terminal) use the same hook.
- Initial values restored from `localStorage` (`graph-h`, `sidebar-w`, `terminal-h`).
- Drag handle uses pointer capture for smooth dragging.
- Saved to localStorage on `pointerUp`.
- `invert` flag: sidebar and terminal grow in the negative direction (drag left/up to grow).

### 8.10 Theme Toggle

- Header toggle button: `"🌙 Dark"` or `"☀️ Light"`.
- `useTheme()` from `ThemeContext.tsx` — toggles between light and dark mode.
- Persisted to localStorage.

---

## 9. Latency & Perceived Performance

### 9.1 Submission → First SSE Event

| Phase | What user sees | Duration |
|-------|---------------|----------|
| User clicks send | User message appears instantly (optimistic) | 0ms |
| POST to create session | ThinkingDots appear (after POST resolves and orchestrator message is added) | 200–1000ms (network) |
| Backend creates session + launches orchestrator | ThinkingDots animate | 0ms (immediate) |
| Orchestrator connects to Foundry, creates thread, posts message | ThinkingDots still animating — no progress detail | 1–5s |
| First `step_thinking` or `step_started` event | ThinkingDots update (or first StepCard appears) | 3–15s total from submit |

**Gap analysis**: Between clicking send and seeing the first step card, the user waits 3–15 seconds with only bouncing dots. No progress bar, no step count prediction, no "connecting to AI..." message.

### 9.2 Between Steps

- Each agent step takes 2–60 seconds depending on the agent.
- Between steps: `step_thinking` events drive ThinkingDots updates ("Orchestrator — calling sub-agent...").
- If a step takes >30s, the user sees **no intermediate progress** — just the same pulsing dots or a pending StepCard with "Querying…".

### 9.3 Final Diagnosis Delivery

- The `message` event carries the **entire** diagnosis text at once — no token streaming.
- User sees ThinkingDots → diagnosis appears atomically (can be a large block of markdown).
- DiagnosisBlock auto-expands, causing a large layout shift.

### 9.4 Session Loading

- Clicking a past session: `viewSession` fetches the full session JSON, then reconstructs messages synchronously.
- No loading skeleton/spinner during the fetch.
- For large sessions (many events), reconstruction is O(n) but fast (all in-memory JSON parsing).

### 9.5 Session List Fetch

- Initial page load: 3 skeleton cards shown during fetch.
- Refresh: no loading indicator during refetch (list updates atomically when response arrives).

---

## 10. UX Friction Points

### 10.1 No Visual Feedback on Cancellation

**Location**: `useSession.ts` L254–L259, `ChatPanel.tsx`  
**Issue**: The `status_change` event from the server (`{status: "cancelling"}`) is not handled by `updateOrchestratorMessage`. The user clicks ⏹, the button disappears (replaced by send button when `running` toggles... but `running` doesn't toggle immediately — only when the SSE closes). So the cancel button remains visible, and clicking it again sends another POST. There is **no "Cancelling..." indicator**. The user may click cancel repeatedly and see no change for 30–60 seconds.

### 10.2 No Indicator That Input Will Send a Follow-Up vs. New Session

**Location**: `App.tsx` L73–L79  
**Issue**: The ChatInput placeholder is always `"Ask a follow-up or paste a new alert..."`. There is no visual distinction between "you are about to send a follow-up to the current session" vs. "you are about to start a new session". The user must infer the mode from context. If a completed session is loaded via the sidebar, typing sends a follow-up — which may surprise the user if they intended to start a new investigation.

### 10.3 No Streaming of Final Diagnosis

**Location**: `orchestrator.py` `on_message_delta`, `useSession.ts`  
**Issue**: The orchestrator accumulates response text via `on_message_delta` but only emits it as a single `message` event after the run completes. The user sees nothing → a large markdown block appears instantly. This creates a jarring experience for long diagnoses.

### 10.4 No Error Handling for Session Fetch Failure

**Location**: `useSession.ts` L303–L308  
**Issue**: `viewSession` calls `fetch(GET /api/sessions/{id})` with no `.ok` check or try/catch. A 404 or 500 response will result in `loadSessionMessages` receiving a malformed object, likely rendering a blank or broken chat panel with no error message.

### 10.5 Session Card Missing Loading State on Click

**Location**: `SessionSidebar.tsx`, `useSession.ts` L303  
**Issue**: When clicking a session card, the full session is fetched from the server. During this fetch (which can take 1–2s for Cosmos-backed sessions), the UI shows the **previous session's messages**. There is no loading indicator, no skeleton, no highlighted-but-loading state on the clicked card. The user may click again thinking the first click didn't register.

### 10.6 Abrupt Message Replacement on New Session Creation

**Location**: `useSession.ts` L143  
**Issue**: `createSession` calls `setMessages([userMsg])` — this **replaces** the entire messages array. If the user was viewing a past session, all prior context vanishes instantly with no transition. There is no "are you sure" prompt or visual transition.

### 10.7 Copy Button Has No Feedback

**Location**: `ChatPanel.tsx` L117  
**Issue**: The "Copy" button calls `navigator.clipboard.writeText()` but provides no visual confirmation (no toast, no checkmark, no text change). The user doesn't know if copy succeeded. The `toastMessage` state exists in `App.tsx` but is never used for this purpose.

### 10.8 Diagnosis Block Can Be Collapsed and Forgotten

**Location**: `DiagnosisBlock.tsx`  
**Issue**: DiagnosisBlock defaults to `expanded = true` but can be collapsed. Once collapsed, it looks like a small "▸ Diagnosis" bar that could easily be missed, especially in a long thread. There is no indication that important content is hidden.

### 10.9 Sidebar Search Is Case-Sensitive Downstream

**Location**: `SessionSidebar.tsx` L118–L122  
**Issue**: Filter uses `toLowerCase()` comparison — this is correct. No issue here. However, the search only covers `alert_text` — there's no way to search by status, date, or step count.

### 10.10 No Reconnection on SSE Drop

**Location**: `useSession.ts` L125–L131  
**Issue**: `onerror` intentionally throws to prevent `fetchEventSource` from retrying. If the network drops temporarily, the investigation **stops updating permanently** with no error shown. The user must manually click the session card to reload, or navigate away and back.

### 10.11 Examples Dropdown Discoverable Only by Icon

**Location**: `ChatInput.tsx` L68  
**Issue**: The 💡 button has no label text — just an emoji. There is no tooltip on hover (only a `title` attribute: "Example questions"). First-time users may not know what it does.

### 10.12 Thread Context Not Visible to User

**Location**: entire frontend  
**Issue**: The user has no way to see that follow-up messages share a Foundry thread (i.e., the orchestrator has access to prior conversation context). There is no "thread ID" indicator, no "conversation context" summary, and no way to know whether follow-up answers are informed by prior turns or not.

### 10.13 Scroll-to-Bottom FAB Positioning

**Location**: `App.tsx` L177  
**Issue**: The FAB is positioned at `right-80` (320px from right). This hardcoded value may overlap with or be hidden behind the sidebar, depending on the sidebar width. The sidebar is resizable and can be anywhere from 0px to full width.

---

## Summary

The conversation UX follows a clear pattern: submit alert → optimistic user message → ThinkingDots → incremental StepCards → DiagnosisBlock → RunMeta footer. Multi-turn follow-ups append seamlessly. The primary friction points are: absence of cancellation feedback, no streaming of the final diagnosis, no visual mode indicator for follow-up vs. new session, no loading states during session switching, and silent SSE disconnect handling. The system is functionally complete but has notable polish and resilience gaps that would affect production readiness.
