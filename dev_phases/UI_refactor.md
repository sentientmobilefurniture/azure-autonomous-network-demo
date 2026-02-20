# UI Refactor Plan — Conversational Chat with Rich Tool Visualization

## Problem

The current frontend has an excellent investigation UI with rich tool-call
visualization (graph topology, KQL tables, search documents, action dispatch
cards) but the conversation model is tightly coupled to a single-shot
"alert → investigation → diagnosis" flow. It uses a custom `useReducer` +
SSE parser pattern that is harder to extend for true multi-turn chat.

The `github_copilot_ui` has a clean Zustand-based chat architecture with
proper streaming state machine, optimistic updates, abort support, and
session management — but no domain-specific visualization.

**Goal**: Merge the best of both — `github_copilot_ui`'s chat architecture
with `graph_main`'s rich visualization components.

## What to Keep (graph_main)

These components are excellent and must be preserved unchanged:

| Component | Purpose | Keep as-is? |
|-----------|---------|-------------|
| `ToolCallCard.tsx` (341 lines) | Progressive tool call disclosure with expand/collapse, error parsing, viz buttons | ✅ Yes |
| `ActionCard.tsx` | Field engineer dispatch card with email body | ✅ Yes |
| `visualization/GraphResultView.tsx` | Interactive force-graph rendering of GQL results | ✅ Yes |
| `visualization/TableResultView.tsx` | KQL telemetry results in sortable table | ✅ Yes |
| `visualization/DocumentResultView.tsx` | Search hits rendered as document cards | ✅ Yes |
| `visualization/StepVisualizationModal.tsx` | Full-screen modal for visualizations | ✅ Yes |
| `DiagnosisBlock.tsx` | Markdown-rendered final diagnosis | ✅ Yes |
| `StreamingText.tsx` | Token-by-token text with cursor animation | ✅ Yes |
| `OrchestratorThoughts.tsx` | Reasoning annotation display | ✅ Yes |
| `SubStepList.tsx` | Sub-step drill-down within a tool call | ✅ Yes |
| `ThinkingIndicator.tsx` | "Thinking..." dots animation | ✅ Yes |
| `GraphTopologyViewer.tsx` | Main network topology graph | ✅ Yes |
| `ResizableGraph.tsx` | Resizable graph panel | ✅ Yes |
| `ResizableTerminal.tsx` | Resizable terminal panel | ✅ Yes |
| `ResizableSidebar.tsx` | Resizable session sidebar | ✅ Yes |
| `Header.tsx` / `TabBar.tsx` | Navigation header with tabs | ✅ Yes |
| `ScenarioPanel.tsx` / `OntologyPanel.tsx` | Scenario and ontology views | ✅ Yes |
| `ResourceVisualizer.tsx` | Resource graph visualization | ✅ Yes |
| `TerminalPanel.tsx` / `TabbedLogStream.tsx` | API + Graph log streaming | ✅ Yes |
| `ServicesPanel.tsx` | Service health dashboard | ✅ Yes |

## What to Adopt (from github_copilot_ui)

| Pattern | Source | Why |
|---------|--------|-----|
| **Zustand stores** | `chatStore.ts`, `sessionStore.ts` | Cleaner state management than useReducer — single source of truth, no prop drilling |
| **Streaming state machine** | `chatStore.ts` | `idle → streaming → done/error` with abort support |
| **Optimistic user message** | `chatStore.ts` | User message appears immediately, before API responds |
| **Tool call accumulation in store** | `chatStore.ts` | `Map<string, ToolCall>` updated via callbacks |
| **Message bubble pattern** | `MessageBubble.tsx` | User/assistant messages as bubbles with avatars |
| **Session CRUD** | `sessionStore.ts` | Create, select, delete, rename with immediate UI feedback |
| **Abort streaming** | `chatStore.abort()` | Cancel mid-generation with `AbortController` |

## What NOT to Adopt

| Pattern | Why skip |
|---------|----------|
| `github_copilot_ui`'s `ToolCallDisplay.tsx` | Too simple — raw JSON args/result. graph_main's `ToolCallCard` with rich visualization is far better |
| `github_copilot_ui`'s SSE event names | Different event schema — graph_main uses `tool_call.start`/`tool_call.complete`/`message.delta`, copilot_ui uses `tool_call_start`/`tool_result`/`token` |
| `github_copilot_ui`'s API client | Different backend API contract — graph_main has REST sessions + SSE streams |
| `CitationList.tsx` / `ThinkingSteps.tsx` | Not applicable to NOC agent |

## Architecture Diff

```
BEFORE (graph_main):                       AFTER (merged):
┌────────────────────────┐                ┌────────────────────────┐
│ useConversation()      │                │ chatStore (Zustand)    │
│   useReducer + dispatch│                │   messages, status,    │
│   SSE parser inline    │                │   streamingToolCalls   │
│   session mgmt inline  │                │   sendMessage()/abort()│
├────────────────────────┤                ├────────────────────────┤
│ useSessions()          │                │ sessionStore (Zustand) │
│   fetch-only hook      │                │   CRUD + active session│
├────────────────────────┤                ├────────────────────────┤
│ ConversationPanel      │                │ ConversationPanel      │
│   → UserMessage        │                │   → UserMessage        │
│   → AssistantMessage   │                │   → AssistantMessage   │
│     → ToolCallCard ✨  │                │     → ToolCallCard ✨  │
│     → DiagnosisBlock   │                │     → DiagnosisBlock   │
│     → ActionCard       │                │     → ActionCard       │
│     → StreamingText    │                │     → StreamingText    │
└────────────────────────┘                └────────────────────────┘
```

## Implementation Plan

### Phase 1: Zustand Store Layer (no UI changes)

**Files to create:**

1. `frontend/src/stores/chatStore.ts` — Adapted from copilot_ui but using graph_main's SSE event schema
2. `frontend/src/stores/sessionStore.ts` — Session CRUD with graph_main's `/api/sessions` API

**Key adaptations from copilot_ui → graph_main:**

The SSE event mapping:

| graph_main SSE event | chatStore callback | Notes |
|---------------------|-------------------|-------|
| `run.start` | (initialize run) | Start streaming state |
| `session.created` | (store thread_id) | For multi-turn |
| `tool_call.start` | `onToolCallStart(id, step, agent, query)` | Richer than copilot_ui — includes step number + agent name |
| `tool_call.complete` | `onToolCallEnd(id, agent, response, visualizations)` | Has visualization data that copilot_ui lacks |
| `message.delta` | `onToken(text)` | Same concept |
| `message.complete` | (finalize text) | copilot_ui doesn't have this — it just accumulates |
| `run.complete` | `onDone(runMeta)` | Includes step count + duration |
| `error` | `onError(message)` | Same concept |
| `done` | (close stream) | SSE connection close signal |

**chatStore state shape** (graph_main–specific additions in **bold**):

```typescript
interface ChatState {
  messages: Message[];             // from graph_main types
  status: 'idle' | 'streaming' | 'error';
  streamingContent: string;
  streamingToolCalls: Map<string, ToolCall>;  // graph_main's rich ToolCall type
  lastRunMeta: RunMeta | null;
  error: string | null;
  _abortController: AbortController | null;

  // Actions
  sendMessage: (sessionId: string, text: string) => Promise<void>;
  sendFollowUp: (sessionId: string, text: string) => Promise<void>;
  abort: (sessionId: string) => void;
  setMessages: (messages: Message[]) => void;
  clearChat: () => void;
}
```

**sessionStore** — nearly identical to copilot_ui but using graph_main's API:

```typescript
interface SessionState {
  sessions: SessionSummary[];
  activeSessionId: string | null;
  loading: boolean;

  fetchSessions: () => Promise<void>;
  createSession: (scenario: string, alertText: string) => Promise<string>;
  selectSession: (id: string) => Promise<void>;
  deleteSession: (id: string) => Promise<void>;
}
```

### Phase 2: SSE Stream Parser

**File to create:** `frontend/src/stores/sseParser.ts`

Extract the SSE parsing logic from `useConversation.ts` (lines 1-50) into
a reusable module. This parser handles:
- Chunked data + partial line buffering
- Event/data field extraction
- JSON payload parsing

The parser feeds events into the chatStore callbacks.

### Phase 3: Wire Stores into Existing Components

**Files to modify (minimal changes):**

1. `App.tsx` — Replace `useConversation()` with `useChatStore` + `useSessionStore`
   - Remove `useConversation` import
   - Destructure from stores instead: `const messages = useChatStore(s => s.messages)`
   - Keep all existing JSX layout unchanged

2. `ConversationPanel.tsx` — No changes needed (already receives `messages` as prop)

3. `AssistantMessage.tsx` — No changes needed (already renders `ToolCallCard`, `DiagnosisBlock`, etc.)

4. `ChatInput.tsx` — Wire `onSubmit` to `chatStore.sendMessage()`, `onCancel` to `chatStore.abort()`

5. `SessionSidebar.tsx` — Wire to `sessionStore` instead of prop drilling

### Phase 4: Session Replay

**File to keep:** The `replayEventLog()` function in `useConversation.ts` that
reconstructs `Message[]` from a persisted `event_log`. Move it to a utility:

`frontend/src/utils/sessionReplay.ts`

This function is critical for viewing historical sessions — it reconstructs
the full conversation from the event log stored in Cosmos.

### Phase 5: Abort Support

Add abort functionality that graph_main currently lacks:

1. `chatStore.abort()` — calls `AbortController.abort()` + `POST /api/sessions/{id}/cancel`
2. `ChatInput.tsx` — show "Stop" button during streaming (already has `onCancel` prop)
3. `AssistantMessage.tsx` — show "aborted" status indicator

### Phase 6: Clean Up

**Files to delete:**

| File | Replacement |
|------|-------------|
| `hooks/useConversation.ts` (511 lines) | `stores/chatStore.ts` (~200 lines) + `stores/sseParser.ts` (~50 lines) |
| `reducers/conversationReducer.ts` | Zustand store handles state directly |

**Files moved:**

| From | To |
|------|-----|
| `hooks/useSessions.ts` | `stores/sessionStore.ts` (enhanced) |
| SSE parser from `useConversation.ts` | `stores/sseParser.ts` |
| `replayEventLog()` from `useConversation.ts` | `utils/sessionReplay.ts` |

## File Change Summary

| Category | Files | Delta |
|----------|-------|-------|
| Created | `stores/chatStore.ts`, `stores/sessionStore.ts`, `stores/sseParser.ts`, `utils/sessionReplay.ts` | +~350 lines |
| Modified | `App.tsx`, `ChatInput.tsx`, `SessionSidebar.tsx` | ~50 lines changed |
| Deleted | `hooks/useConversation.ts`, `reducers/conversationReducer.ts` | −~700 lines |
| Unchanged | **All 20+ visualization/display components** | 0 |
| **Net** | | **−~300 lines** |

## What Does NOT Change

- **Backend API** — zero backend changes. Same SSE event schema, same REST endpoints.
- **Graph topology viewer** — same GraphTopologyViewer component
- **Tool call visualization** — same ToolCallCard with graph/table/document views
- **Action cards** — same dispatch card with email modal
- **Terminal panel** — same log streaming
- **Scenario/Resources/Ontology tabs** — unchanged
- **CSS/Tailwind** — same theme, same styles
- **Types** — same `types/conversation.ts` and `types/index.ts`

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| SSE event mapping mismatch | Medium | Reuse existing parseSSELines + dispatchSSEEvent logic verbatim |
| Session replay breaks | Low | Extract `replayEventLog()` as-is, no logic changes |
| Store-component wiring misses edge case | Low | Phase 3 is mechanical prop→store substitution |
| Zustand adds dependency | Low | Already used by copilot_ui; ~5KB gzipped |

## Dependencies to Add

```json
{
  "zustand": "^5.0.0"
}
```

No other new dependencies. All existing deps stay.

## Estimated Effort

| Phase | Effort |
|-------|--------|
| Phase 1: Zustand stores | 2-3 hours |
| Phase 2: SSE parser extraction | 30 min |
| Phase 3: Wire stores into UI | 1-2 hours |
| Phase 4: Session replay utility | 30 min |
| Phase 5: Abort support | 1 hour |
| Phase 6: Clean up | 30 min |
| **Total** | **~6-8 hours** |
