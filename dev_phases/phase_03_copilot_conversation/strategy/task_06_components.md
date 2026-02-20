# Task 06: Frontend Components

> **Phase**: B (Rebuild)
> **Prerequisite**: Task 05 (streaming hook)
> **Output**: `execution/task_06_components_execution_log.md`

## Goal

Build the new conversation UI components: `ConversationPanel`, `AssistantMessage`, `ToolCallCard`, `StreamingText`, `ThinkingIndicator`.

## Files to Create

### 1. `frontend/src/components/ConversationPanel.tsx`

Replaces `ChatPanel.tsx`. Maps `Message[]` to render components.

```
Props:
  messages: Message[]
  onSave?: () => void

Renders:
  - Empty state (if no messages)
  - For each message:
    - kind === 'user' → <UserMessage>
    - kind === 'assistant' → <AssistantMessage>
```

Simpler than old `ChatPanel` — no inline step rendering, no thinking state prop (it's on the message).

### 2. `frontend/src/components/AssistantMessage.tsx`

New component. Renders a single assistant turn with all its tool calls and response.

```
Props:
  message: AssistantMessage
  onSave?: () => void

Renders:
  <div className="space-y-2">
    {/* Tool calls — progressive disclosure */}
    {message.toolCalls.map(tc =>
      tc.isAction
        ? <ActionCard key={tc.id} toolCall={tc} />
        : <ToolCallCard key={tc.id} toolCall={tc} />
    )}

    {/* Thinking indicator — when pending with no tool calls yet */}
    {message.status === 'pending' && message.toolCalls.length === 0 && (
      <ThinkingIndicator />
    )}

    {/* Streaming text — token-by-token with cursor */}
    {message.streamingContent && !message.content && (
      <StreamingText text={message.streamingContent} />
    )}

    {/* Final diagnosis */}
    {message.content && (
      <DiagnosisBlock text={message.content} />
    )}

    {/* Error */}
    {message.errorMessage && (
      <div className="glass-card p-3 border-status-error/30 bg-status-error/5">
        <span className="text-xs text-status-error">⚠ {message.errorMessage}</span>
      </div>
    )}

    {/* Status */}
    {message.statusMessage && (
      <div className="glass-card p-2 border-brand/20 bg-brand/5">
        <span className="text-xs text-brand">ℹ {message.statusMessage}</span>
      </div>
    )}

    {/* Run meta footer */}
    {message.runMeta && (
      <div className="flex items-center justify-between text-[10px] text-text-muted px-1">
        <span>{message.runMeta.steps} step{message.runMeta.steps !== 1 ? 's' : ''} · {message.runMeta.time}</span>
        <div className="flex gap-2">
          {onSave && <button onClick={onSave} className="hover:text-text-primary transition-colors">Save</button>}
          <button onClick={() => navigator.clipboard.writeText(message.content)} className="hover:text-text-primary transition-colors">Copy</button>
        </div>
      </div>
    )}
  </div>
```

### 3. `frontend/src/components/ToolCallCard.tsx`

Replaces `StepCard.tsx`. Progressive disclosure with status transitions.

```
Props:
  toolCall: ToolCall

States:
  pending   → pulsing dot + agent name + "Querying..."
  running   → pulsing dot + agent name + truncated query + "Running..."
  complete  → green dot + agent name + duration + expandable response
  error     → red dot + agent name + friendly error message

Features:
  - Click to expand/collapse response body
  - Reasoning shown above (via OrchestratorThoughts component)
  - Sub-steps shown below response (via SubStepList component)
  - Viz button (reuse useVisualization + StepVisualizationModal)
  - Framer Motion animations (same as old StepCard)
```

Port the error parsing logic from old `StepCard.tsx` (`parseErrorMessage` function).

### 4. `frontend/src/components/StreamingText.tsx`

New component. Renders partial markdown with a blinking cursor.

```
Props:
  text: string

Renders:
  <div className="glass-card overflow-hidden">
    <div className="px-3 py-2 text-xs font-medium text-text-muted">Diagnosis</div>
    <div className="prose prose-sm max-w-none px-3 pb-3">
      <ReactMarkdown>{text}</ReactMarkdown>
      <span className="inline-block w-2 h-4 bg-brand animate-pulse ml-0.5" />
    </div>
  </div>
```

### 5. `frontend/src/components/ThinkingIndicator.tsx`

Replaces `ThinkingDots.tsx`. Simpler — just shows the assistant is working.

```
Props:
  (none — or optional agent/status strings)

Renders:
  <div className="flex items-center gap-3 px-3 py-2">
    <div className="flex gap-1">
      <div className="animate-bounce h-1.5 w-1.5 rounded-full bg-brand" style={{animationDelay: '0ms'}} />
      <div className="animate-bounce h-1.5 w-1.5 rounded-full bg-brand" style={{animationDelay: '150ms'}} />
      <div className="animate-bounce h-1.5 w-1.5 rounded-full bg-brand" style={{animationDelay: '300ms'}} />
    </div>
    <span className="text-xs text-text-secondary">Thinking...</span>
  </div>
```

Wrapped in `motion.div` with enter/exit animations.

## Files to Keep (already updated in Task 02)

- `UserMessage.tsx` — using new `UserMessage` type
- `SubStepList.tsx` — using new `SubStep` type
- `ActionCard.tsx` — using new `ToolCall` type
- `OrchestratorThoughts.tsx` — unchanged (receives `reasoning: string`)
- `DiagnosisBlock.tsx` — unchanged (receives `text: string`)
- `ActionEmailModal.tsx` — unchanged

## Completion Criteria

- [ ] `ConversationPanel.tsx` created — renders full message thread
- [ ] `AssistantMessage.tsx` created — renders tool calls + streaming + diagnosis
- [ ] `ToolCallCard.tsx` created — progressive disclosure (pending → running → complete)
- [ ] `StreamingText.tsx` created — markdown with blinking cursor
- [ ] `ThinkingIndicator.tsx` created — bouncing dots
- [ ] Existing design system preserved (glass-card, dark theme, brand colors)
- [ ] Visualization system integrated (useVisualization + StepVisualizationModal)
- [ ] Framer Motion animations on ToolCallCard
- [ ] Error parsing ported from old StepCard
- [ ] `npx tsc --noEmit` — errors only in App.tsx (not yet wired)
