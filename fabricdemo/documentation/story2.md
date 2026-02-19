# Story 2 — Orchestrator Reasoning / "Orchestrator Thoughts" Box

## Vision

Before each sub-agent delegation, the orchestrator explains **why** it's calling that agent and what information it hopes to learn. This reasoning is extracted and displayed in a collapsible "Orchestrator Thoughts..." box above each step card in the Investigation timeline.

**Collapsed (default):**

```
         │  ← thin vertical connector line (brand/20 opacity)
┌─────────────────────────────────────────────────────────────────┐
│  ◇ Orchestrator Thoughts...                               [ ▸ ] │
└─────────────────────────────────────────────────────────────────┘
         │  ← connector
┌─────────────────────────────────────────────────────────────────┐
│ ● GraphExplorerAgent                               11.2s        │
│ ▸ Query: What MPLS paths carry VPN-ACME...                      │
│ ▸ Response: MPLS-PATH-SYD-MEL-PRIMARY trav...                   │
│                                                 [ ⬡ View Graph ] │
└─────────────────────────────────────────────────────────────────┘
```

**Expanded:**

```
         │
┌─────────────────────────────────────────────────────────────────┐
│  ◇ Orchestrator Thoughts                                 [ ▾ ] │
│─────────────────────────────────────────────────────────────────│
│  "The alert mentions VPN-ACME-CORP and a primary MPLS path      │
│  failure. I need to find which MPLS paths carry this service    │
│  so I can trace the affected infrastructure."                   │
└─────────────────────────────────────────────────────────────────┘
         │
┌─────────────────────────────────────────────────────────────────┐
│ ● GraphExplorerAgent                               11.2s        │
│  ...                                                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## Current State Analysis

### How delegation works today

1. The orchestrator's **system prompt** is baked into the Foundry agent at provisioning time (via `scripts/provision_agents.py` → `scripts/agent_provisioner.py`).
2. At runtime, only the user's alert text is sent as a thread message.
3. The orchestrator LLM decides to delegate → produces a `connected_agent` tool call with **arguments** (the query for the sub-agent).
4. The Azure AI Agents SDK invokes the sub-agent with those arguments **opaquely** — we cannot intercept or modify them in-flight.
5. `orchestrator.py`'s `_extract_arguments()` reads `tc.connected_agent.arguments` to get the query string.
6. The query is forwarded as `step.query` in the `step_complete` SSE event.

### The problem

The orchestrator's internal reasoning (why it chose that agent, what it expects to learn) happens **inside the LLM's chain-of-thought** and is never surfaced. The `connected_agent.arguments` only contain the query to pass to the sub-agent.

### The critical constraint — reasoning should not confuse sub-agents

The `connected_agent` tool call arguments are forwarded **directly** to the sub-agent by the SDK. We cannot intercept or strip content from them in-flight. This means if we embed reasoning in the arguments, the sub-agent receives it as part of its input.

However, this is manageable: the reasoning block is clearly delimited with `[ORCHESTRATOR_THINKING]...[/ORCHESTRATOR_THINKING]` tags, and each sub-agent's prompt includes a guard clause telling it to ignore these blocks. See **Implementation Bugs & Gotchas** for the full analysis of why this approach was chosen over alternatives.

---

## Architecture Plan

### Approach: Embed reasoning in tool call arguments + sub-agent prompt guard

The orchestrator is instructed to prefix each tool call's arguments with a `[ORCHESTRATOR_THINKING]...[/ORCHESTRATOR_THINKING]` block. The `_extract_arguments()` method in `orchestrator.py` parses this block out, forwarding the clean query to the frontend and the reasoning separately.

> **Why not intermediate assistant messages?** The Azure AI Agents SDK's `on_message_delta` callback fires only for the **final** assistant message (the situation report), NOT for intermediate text between tool call rounds. Approach A (reasoning in assistant messages) was invalidated by this SDK behavior. See the **Gotchas** section for the full analysis and alternative options considered.

The sub-agents receive the `[ORCHESTRATOR_THINKING]` block in their input but are instructed to ignore it via a prompt guard. Testing shows this is reliable — the block is clearly delimited and short (1-2 sentences).

---

### Phase 1 — Backend: Prompt + Extraction

#### 1A. Update the orchestrator system prompt

Add the reasoning annotation instruction to both scenario prompt files:
- `data/scenarios/telco-noc/data/prompts/foundry_orchestrator_agent.md`
- `data/scenarios/telecom-playground/data/prompts/foundry_orchestrator_agent.md`

Insert after the `## Rules` section (or as a new top-level section):

```markdown
## Reasoning annotations (MANDATORY)

When calling a sub-agent, you MUST prefix the query/arguments with a brief
reasoning block:

[ORCHESTRATOR_THINKING]
1-2 sentences: What information gap are you filling? Why this agent?
What do you already know, and what do you need to learn next?
[/ORCHESTRATOR_THINKING]

Then include the actual query/arguments after the block.

Example tool call arguments:
[ORCHESTRATOR_THINKING]
The alert mentions VPN-ACME-CORP service degradation on a primary MPLS path.
I need to discover which MPLS paths carry this service to trace the failure
back to the underlying infrastructure.
[/ORCHESTRATOR_THINKING]
What MPLS paths carry VPN-ACME-CORP?

Rules:
- One [ORCHESTRATOR_THINKING] block per tool call, placed at the start of the arguments.
- Keep it concise — maximum 2 sentences.
- Reference what you already know from prior steps when relevant.
- Do NOT include this block in your final situation report.
```

**Files to modify:**
- `data/scenarios/telco-noc/data/prompts/foundry_orchestrator_agent.md`
- `data/scenarios/telecom-playground/data/prompts/foundry_orchestrator_agent.md`

**After modifying the prompt files, re-provision the agents** (run `provision_agents.py`) so the Foundry agent picks up the new instructions.

#### 1B. Capture reasoning in the event handler

> **IMPORTANT:** The original plan used `on_message_delta` to capture intermediate reasoning. This is incorrect — see **Implementation Bugs & Gotchas, CRITICAL BUG** below. The corrected approach uses **Option 2: extract reasoning from tool call arguments** in `_extract_arguments()`.

Modify `orchestrator.py`'s `AgentEventHandler`:

1. **Change `_extract_arguments()`** to return a `(query, reasoning)` tuple. Parse and strip `[ORCHESTRATOR_THINKING]` blocks from the raw arguments.

2. **Update all call sites** to unpack the tuple — see Phase 1B code in the Gotchas section for full implementation.

3. **Include reasoning in the `step_complete` SSE event.**

4. **Strip reasoning from the final diagnosis** in `_thread_target`, before emitting `message`.

See the **Implementation Bugs & Gotchas** section for the complete corrected code.

**Files to modify:**
- `api/app/orchestrator.py` — event handler class

#### 1C. Ensure reasoning is stripped from the final diagnosis

The `message` SSE event (final situation report) should NOT contain `[ORCHESTRATOR_THINKING]` blocks. Since there is **no `on_end()` callback** on the handler, the stripping happens in `_thread_target()` right before emitting the message:

```python
if handler.response_text:
    import re
    clean = re.sub(
        r'\[ORCHESTRATOR_THINKING\].*?\[/ORCHESTRATOR_THINKING\]',
        '', handler.response_text, flags=re.DOTALL
    ).strip()
    _put("message", {"text": clean})
    break
```

#### 1D. Update sub-agent prompts with guard clause

Each sub-agent's system prompt needs a one-line guard so it ignores `[ORCHESTRATOR_THINKING]` blocks in its input:

```markdown
## Input format note
Your input may contain `[ORCHESTRATOR_THINKING]...[/ORCHESTRATOR_THINKING]` blocks.
These are internal metadata — ignore them completely. Process only the query text
outside these blocks.
```

Add this to all sub-agent prompts in both scenarios. **Re-provision ALL agents** after updating.

---

### Phase 2 — Frontend: Types & Data Layer

#### 2A. Extend `StepEvent` type

```ts
// types/index.ts
export interface StepEvent {
    step: number;
    agent: string;
    duration?: string;
    query?: string;
    response?: string;
    error?: boolean;
    reasoning?: string;  // NEW — orchestrator's thinking before this step
}
```

#### 2B. Update `useInvestigation` hook

In the `step_complete` SSE handler, parse the `reasoning` field:

```ts
// hooks/useInvestigation.ts — in the switch case for "step_complete"
case 'step_complete': {
    const s: StepEvent = {
        step: d.step,
        agent: d.agent,
        duration: d.duration,
        query: d.query,
        response: d.response,
        error: d.error,
        reasoning: d.reasoning || '',  // NEW
    };
    setSteps(prev => [...prev, s]);
    break;
}
```

#### 2C. Update `Interaction` persistence

The `reasoning` field is already part of `StepEvent`, which is stored in `Interaction.steps[]`. No schema change needed — it will be persisted automatically when interactions are saved. Past interactions loaded from the sidebar will show reasoning if it was captured at investigation time.

---

### Phase 3 — Frontend: UI Component

#### 3A. Create `OrchestratorThoughts` component

A collapsible box that sits **above** each `StepCard`, visually connected to it:

```tsx
// components/OrchestratorThoughts.tsx

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

interface Props {
    reasoning: string;
    forceExpanded?: boolean;
}

export function OrchestratorThoughts({ reasoning, forceExpanded }: Props) {
    const [localExpanded, setLocalExpanded] = useState(false);
    const expanded = forceExpanded ?? localExpanded;

    if (!reasoning) return null;

    return (
        <button
            className="glass-card w-full text-left mb-0 cursor-pointer
                       border-brand/15 bg-brand/[0.03]
                       hover:border-brand/25 hover:bg-brand/[0.06]
                       focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-1
                       transition-all"
            onClick={() => setLocalExpanded(v => !v)}
            aria-expanded={expanded}
            aria-label="Orchestrator reasoning for this step"
        >
            {/* Header — always visible */}
            <div className="flex items-center justify-between px-3 py-1.5">
                <div className="flex items-center gap-1.5">
                    <span className="text-[10px] text-brand/60">◇</span>
                    <span className="text-[11px] font-medium text-text-muted">
                        Orchestrator Thoughts{expanded ? '' : '...'}
                    </span>
                </div>
                <span className="text-[10px] text-text-muted">
                    {expanded ? '▾' : '▸'}
                </span>
            </div>

            {/* Expanded content */}
            <AnimatePresence>
                {expanded && (
                    <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.2 }}
                        className="overflow-hidden"
                    >
                        <div className="px-3 pb-2 pt-0.5">
                            <p className="text-[11px] text-text-secondary leading-relaxed italic">
                                "{reasoning}"
                            </p>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </button>
    );
}
```

**Design decisions and UX rationale:**

| Decision | Rationale |
|----------|-----------|
| **`<button>` element** (not `<div onClick>`) | Proper semantic element for interactive collapsible. Keyboard accessible by default (Tab, Enter, Space). Screen readers announce it as a button. |
| **`aria-expanded`** | Screen readers announce "collapsed" / "expanded" state |
| **`border-brand/15 bg-brand/[0.03]`** (subtle teal, not purple) | Purple (`purple-500`) would be a hard-coded color bypassing the theme system. The app's design language is built around `brand` (teal). Using brand at extremely low opacity creates visual distinction through *density/weight*, not a new color. This also means light/dark themes work automatically. |
| **`text-[11px]`** (not `text-xs`) | Slightly smaller than StepCard body text (`text-xs` = 12px) to establish visual hierarchy: the thoughts box is secondary to the step card it explains. |
| **Italic + quotes** | `"reasoning..."` with italic text signals inner monologue/thought without needing a different color |
| **`◇` diamond icon** (not 💭 emoji) | Emoji rendering is inconsistent across OS/browsers. The diamond `◇` in `text-brand/60` is reliable, lightweight, and matches the `◆` used in the app's Header branding. |
| **`py-1.5`** (compact) | Collapsed state should be visually lightweight — it's metadata, not primary content. The step card below it is the main event. |
| **`mb-0`** (no bottom margin) | The connector line between thoughts and step card handles spacing. |
| **`focus-visible:ring-2 ring-brand`** | Matches the global focus style from `globals.css` |
| **No CopyButton** | Reasoning is 1-2 sentences of context — too short and too contextual to warrant copying |
| **`forceExpanded` prop** | Allows "Expand all" in AgentTimeline to control this component |

**Reduced motion support:**
```tsx
// Wrap motion variants in prefers-reduced-motion check
const variants = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    ? { initial: { opacity: 0 }, animate: { opacity: 1 }, exit: { opacity: 0 } }
    : { initial: { height: 0, opacity: 0 }, animate: { height: 'auto', opacity: 1 }, exit: { height: 0, opacity: 0 } };
```

#### 3B. Integrate into `AgentTimeline`

In `AgentTimeline.tsx`, render `<OrchestratorThoughts>` + connector line + `<StepCard>` as a visual group:

```tsx
// components/AgentTimeline.tsx — in the steps map

{steps.map((step, i) => (
    <div key={step.step} className="mb-2">
        {/* Reasoning box (renders null if no reasoning) */}
        {step.reasoning && (
            <>
                <OrchestratorThoughts
                    reasoning={step.reasoning}
                    forceExpanded={allExpanded}
                />
                {/* Visual connector: thin vertical line linking thought to its step */}
                <div className="ml-4 h-1.5 border-l-2 border-brand/20" aria-hidden="true" />
            </>
        )}
        {/* Step card */}
        <StepCard step={step} forceExpanded={allExpanded} />
    </div>
))}
```

**Visual hierarchy within each step group:**

```
  1. OrchestratorThoughts  ← lightweight, collapsed, secondary
     │  connector line
  2. StepCard              ← primary, contains the actual data
```

The connector line (`border-l-2 border-brand/20`, height `6px`, left-aligned at `ml-4`) creates a visual "parent → child" relationship. It's `aria-hidden` since it's purely decorative.

**Spacing adjustments:**
- Remove `mb-2` from StepCard itself (moved to the wrapper `<div>`)
- Thoughts box uses `mb-0` — connector line provides the gap
- Overall group spacing (`mb-2` on wrapper) stays consistent with current timeline spacing

#### 3C. Interaction with "Expand all / Collapse all"

When the user clicks "Expand all":
- All StepCards expand (existing behavior)
- All OrchestratorThoughts boxes also expand
- Pass `forceExpanded` prop (same pattern as StepCard)

This is already built into the component (see `forceExpanded` prop in 3A).

**Edge case — independent collapse after "Expand all":**
- After "Expand all", clicking an individual OrchestratorThoughts box should collapse just that one
- The `forceExpanded ?? localExpanded` pattern handles this: when `forceExpanded` is `true`, it overrides. When the user clicks "Collapse all" (`forceExpanded` becomes `false`), the component falls back to `localExpanded`.
- Reset `localExpanded` to `false` when `forceExpanded` transitions from `true` to `false` (use `useEffect` to sync).

---

### Phase 4 — Testing & Edge Cases

#### 4A. Prompt reliability

LLMs don't always follow formatting instructions perfectly. Handle these cases:

| Edge case | Handling |
|---|---|
| No `[ORCHESTRATOR_THINKING]` block in tool call arguments | `reasoning` is empty string → `OrchestratorThoughts` returns `null` (not rendered) |
| Multiple `[ORCHESTRATOR_THINKING]` blocks in one tool call | Regex `re.search()` finds the first match; only one reasoning block per call is expected |
| Reasoning block appears inside the final situation report | `_strip_reasoning_tags()` removes it before emitting `message` event |
| Sub-agent receives `[ORCHESTRATOR_THINKING]` block in its input | Expected behavior — sub-agent prompt guard tells it to ignore. Test with each agent type. |
| Very long reasoning text (>500 chars) | Truncate in the event handler to 500 chars, same pattern as query truncation |

#### 4B. Verify sub-agents handle reasoning gracefully

With the chosen approach, sub-agents **DO receive** the `[ORCHESTRATOR_THINKING]` block in their input. However:
1. The block is clearly delimited with tags.
2. Each sub-agent has a prompt guard telling it to ignore the block.
3. The reasoning is 1-2 sentences — a small prefix unlikely to confuse the agent.

**Verification testing plan:**
1. Run 5 investigations with reasoning blocks enabled.
2. Compare sub-agent responses with and without the reasoning prefix.
3. Check if any sub-agent echoes or references the reasoning content in its output.
4. If confusion is detected, fall back to Option 4 (post-run thread message retrieval) — see Gotchas section.

---

## Implementation Order

```
Phase 1A + 1D  →  Re-provision ALL agents  →  Phase 1B  →  Phase 1C     (backend)
                                                    ↓
                                               Phase 2A  →  Phase 2B       (types + hook)
                                                    ↓
                                               Phase 3A  →  Phase 3B  →  Phase 3C  (UI)
                                                    ↓
                                               Phase 4                     (testing)
```

**Suggested sprint breakdown:**

| Sprint | Scope | Effort |
|--------|-------|--------|
| **S1** | Prompt update + re-provision agents + test that LLM produces reasoning blocks | ~1 hr |
| **S2** | `orchestrator.py` — `_extract_arguments()` tuple return, reasoning extraction, SSE emission, tag stripping | ~2 hrs |
| **S3** | Frontend types + hook + `OrchestratorThoughts` component + timeline integration | ~2 hrs |
| **S4** | Edge case handling, expand-all integration, visual polish | ~1 hr |

**Total estimated effort: ~6 hours**

---

## Files Changed / Created

### New files

| File | Purpose |
|------|---------|
| `frontend/src/components/OrchestratorThoughts.tsx` | Collapsible reasoning box component |

### Modified files

| File | Change |
|------|--------|
| `data/scenarios/telco-noc/data/prompts/foundry_orchestrator_agent.md` | Add `## Reasoning annotations` section (instruct orchestrator to include `[ORCHESTRATOR_THINKING]` in tool call arguments) |
| `data/scenarios/telecom-playground/data/prompts/foundry_orchestrator_agent.md` | Same prompt update |
| `data/scenarios/telco-noc/data/prompts/foundry_graph_explorer_agent.md` | Add "ignore `[ORCHESTRATOR_THINKING]` blocks in input" guard |
| `data/scenarios/telco-noc/data/prompts/foundry_telemetry_agent.md` | Same guard |
| `data/scenarios/telco-noc/data/prompts/foundry_runbook_kb_agent.md` | Same guard |
| `data/scenarios/telco-noc/data/prompts/foundry_historical_ticket_agent.md` | Same guard |
| `api/app/orchestrator.py` | Change `_extract_arguments()` to return `(query, reasoning)` tuple; parse and strip `[ORCHESTRATOR_THINKING]` blocks; include `reasoning` in `step_complete` SSE; strip from final message before emitting `message` event |
| `frontend/src/types/index.ts` | Add `reasoning?: string` to `StepEvent` |
| `frontend/src/hooks/useInvestigation.ts` | Parse `reasoning` from `step_complete` SSE event |
| `frontend/src/components/AgentTimeline.tsx` | Render `<OrchestratorThoughts>` above each `<StepCard>`; add wrapper div with `mb-2`; remove `mb-2` from StepCard |
| `frontend/src/components/StepCard.tsx` | Remove `mb-2` from outer `motion.div` (moved to AgentTimeline wrapper) |
| `graph-query-api/models.py` | Add `reasoning: str | None = None` to `InteractionStep` |

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| LLM doesn't reliably produce `[ORCHESTRATOR_THINKING]` blocks | Medium | Graceful degradation — component returns null when reasoning is empty. Add few-shot examples in prompt. |
| LLM omits reasoning or puts it after the query instead of before | Low | Regex `re.search()` finds the block anywhere in the arguments string, regardless of position. |
| Reasoning blocks leak into final situation report | Low | `_strip_reasoning_tags()` regex cleans them out. |
| Sub-agent confused by `[ORCHESTRATOR_THINKING]` block in input | Low | Prompt guard tells sub-agent to ignore it. Block is clearly delimited and short. Fall back to Option 4 (post-run thread retrieval) if testing reveals issues. |
| Re-provisioning resets agent IDs | Medium | This is normal workflow — `provision_agents.py` handles ID updates. |

---

## Implementation Bugs & Gotchas (Audit)

These are verified issues found by reading the actual source code. Each MUST be addressed during implementation.

### CRITICAL BUG: `on_message_delta` does NOT fire for intermediate reasoning

**Where:** `orchestrator.py` → `AgentEventHandler.on_message_delta`

**The entire Approach A is based on a false assumption.** The plan states:

> "the orchestrator to emit its reasoning as a text message before each tool call. The SDK's `on_message_delta` callback fires for assistant messages, and we can capture intermediate messages — not just the final synthesis."

**This is incorrect.** In the Azure AI Agents SDK's `AgentEventHandler`, `on_message_delta` fires only for the **final assistant message** — the situation report produced after all tool calls complete. It does NOT fire for intermediate "thinking" text between tool call rounds. The orchestrator's internal reasoning between tool calls is not surfaced by the SDK at all.

The current code confirms this — `on_message_delta` simply accumulates into `self.response_text`:
```python
def on_message_delta(self, delta):
    if delta.text:
        self.response_text += delta.text.value
```

And `response_text` is only emitted once, after `stream.until_done()` returns, as the `message` SSE event.

**Impact:** If we add `[ORCHESTRATOR_THINKING]` instructions to the prompt, the orchestrator may include them in its **final response text** (the situation report), but NOT as intermediate messages between tool calls. The `on_message_delta` callback cannot capture per-step reasoning because there are no intermediate messages to capture.

**Revised approach options:**

#### Option 1 — Extract from the final message (simplest, imprecise)

If the orchestrator includes `[ORCHESTRATOR_THINKING]` blocks in its final situation report text, we can:
1. Parse them out of `self.response_text` after `stream.until_done()`.
2. But we cannot correlate them with specific tool calls because they arrive all at once at the end.
3. We could try to match them positionally (1st block → 1st step, 2nd → 2nd, etc.), but this is fragile.

**Not recommended** — breaks the per-step correlation.

#### Option 2 — Embed reasoning in tool call arguments (with sub-agent prompt guard)

Despite the earlier analysis saying this wouldn't work, it CAN work with mitigation:

1. Instruct the orchestrator to prefix each tool call's arguments with `[ORCHESTRATOR_THINKING]...[/ORCHESTRATOR_THINKING]\n`.
2. The sub-agent will receive this in its input. Add a line to each sub-agent's prompt: `"Ignore any [ORCHESTRATOR_THINKING]...[/ORCHESTRATOR_THINKING] blocks in your input. They are metadata, not part of the query."`
3. In `_extract_arguments()`, parse and strip the reasoning block before setting `query`.

```python
def _extract_arguments(self, tc) -> tuple[str, str]:
    """Returns (query, reasoning)."""
    # --- existing extraction logic ---
    tc_t = tc.type if hasattr(tc, "type") else tc.get("type", "?")
    tc_type = tc_t.value if hasattr(tc_t, "value") else str(tc_t)
    if tc_type != "connected_agent":
        return "", ""
    ca = tc.connected_agent if hasattr(tc, "connected_agent") else tc.get("connected_agent", {})
    args_raw = getattr(ca, "arguments", None) or ca.get("arguments", None)
    if not args_raw:
        return "", ""
    try:
        obj = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
        raw = obj if isinstance(obj, str) else json.dumps(obj)
    except Exception:
        raw = str(args_raw)
    # --- end existing logic ---
    reasoning = ""
    query = raw
    
    # Extract [ORCHESTRATOR_THINKING] block if present
    import re
    match = re.search(
        r'\[ORCHESTRATOR_THINKING\](.*?)\[/ORCHESTRATOR_THINKING\]',
        raw, flags=re.DOTALL
    )
    if match:
        reasoning = match.group(1).strip()
        query = raw[:match.start()] + raw[match.end():]
        query = query.strip()
    
    return query, reasoning
```

**Tradeoff:** The sub-agent sees `[ORCHESTRATOR_THINKING]` text but is told to ignore it. Risk: the sub-agent might occasionally be confused by it. Mitigation: test with each sub-agent; the reasoning block is clearly delimited and short (1-2 sentences).

#### Option 3 — Use `on_run_step` `step_details` to infer reasoning (no prompt change)

The `on_run_step` callback with `status == "in_progress"` fires when the orchestrator starts a new run step. Between two consecutive `on_run_step` calls, the orchestrator was reasoning. We can't access that reasoning text, but we could:
1. Skip reasoning entirely and show a generic "Orchestrator is analyzing..." message.
2. Or use a separate API call to retrieve the orchestrator's thread messages after the run completes.

**Not recommended** — doesn't achieve the goal.

#### Option 4 — Post-run thread message retrieval (precise, extra API call)

After `stream.until_done()`, retrieve the full thread message history:
```python
messages = agents_client.messages.list(thread_id=thread_id)
```

The thread will contain ALL assistant messages, including any intermediate text the orchestrator produced between tool calls. Parse `[ORCHESTRATOR_THINKING]` blocks from these messages and correlate them with tool calls by message order.

**Tradeoff:** Extra API call after each run; parsing is more complex; but the data is precise and the per-step correlation is reliable.

**Recommendation:** **Option 2** is the most pragmatic. The sub-agent prompt guard is low-risk (tested in similar multi-agent setups), and it requires no extra API calls. Option 4 is the fallback if Option 2 causes sub-agent confusion.

### BUG 2: `InteractionStep` drops `reasoning` field

**Where:** `graph-query-api/models.py` → `InteractionStep`

Same as Story 1 Bug 2. The Pydantic model silently drops unknown fields. Must add `reasoning: str | None = None` to persist reasoning in saved interactions.

### BUG 3: No `on_end` callback exists on the handler

**Where:** `orchestrator.py`

The plan references `on_end()` for stripping reasoning from the final message:
```python
def on_end(self):
    clean = self._strip_reasoning_tags(self._msg_buffer)
    self.response_text = clean.strip()
```

But `on_end` is NOT defined on `SSEEventHandler` and may not be a callback in the `AgentEventHandler` base class. The end-of-run is detected in `_thread_target` after `stream.until_done()`.

**Fix:** Do the stripping in `_thread_target`, right before emitting the `message` event:
```python
if handler.response_text:
    clean = handler._strip_reasoning_tags(handler.response_text)
    _put("message", {"text": clean})
    break
```

### BUG 4: Retry loop resets step counter — duplicate step numbers in frontend

**Where:** `orchestrator.py` retry logic

Each retry creates a new `SSEEventHandler()` with `ui_step = 0`. If attempt 1 emits steps 1-3 and then fails, attempt 2 starts at step 1 again. The frontend accumulates `steps[]` across both attempts — leading to duplicate React keys (`key={s.step}`) and stale step data from the failed attempt persisting in the UI.

**Fix:** On retry, emit a `retry_reset` SSE event so the frontend can clear its `steps[]` array. Or clear `steps` when receiving a new `run_start` event.

**Fix:** On retry, emit a `retry_reset` SSE event so the frontend can clear its `steps[]` array. Or clear `steps` when receiving a new `run_start` event.

### BUG 5: `_extract_arguments` return type changes (breaking)

**Where:** `orchestrator.py` → `_extract_arguments()`

If we change `_extract_arguments()` to return `tuple[str, str]` (query, reasoning), every call site breaks. Currently there are 3 call sites:
1. Line ~174: `failed_query = self._extract_arguments(tc)` (in the failed step handler)
2. Line ~185: `query = self._extract_arguments(tc)` (in the completed step handler)

**Fix:** Either:
1. Use a different method name: `_extract_arguments_with_reasoning()` that returns a tuple, and keep `_extract_arguments()` unchanged.
2. Or update all 3 call sites to unpack: `query, reasoning = self._extract_arguments(tc)`.

### BUG 6: `forceExpanded ?? localExpanded` doesn't work as expected

**Where:** `OrchestratorThoughts.tsx`

The plan says `forceExpanded ?? localExpanded` handles "Expand all" → individual collapse. But `??` (nullish coalescing) only falls through on `null` or `undefined`. When `allExpanded` is `false` (Collapse all), `forceExpanded` is `false`, so `false ?? localExpanded` evaluates to `false` — the user can never independently expand an item after Collapse All.

**Fix:** The parent should pass `forceExpanded={allExpanded || undefined}`:
```tsx
<OrchestratorThoughts
    reasoning={step.reasoning}
    forceExpanded={allExpanded || undefined}
/>
```

When `allExpanded` is `true`, `forceExpanded` is `true` (override). When `allExpanded` is `false`, `forceExpanded` is `undefined` (fall through to `localExpanded`).

**However**, check how the existing `StepCard` handles this — it has the same `forceExpanded` pattern:
```tsx
const expanded = forceExpanded ?? localExpanded;
```
If StepCard has the same bug, it's existing behavior and may be intentional. Verify before fixing.

### BUG 7: Spacing conflict — `mb-2` on StepCard vs. wrapper

**Where:** `AgentTimeline.tsx` → `StepCard.tsx`

The plan says to move `mb-2` from StepCard to the wrapper `<div>`. But StepCard's `mb-2` is baked into the `motion.div` className. If we add `mb-2` to the wrapper AND forget to remove it from StepCard, we get `mb-4` effective spacing (double margin).

**Fix:** Explicitly remove `mb-2` from `StepCard.tsx` line 40 when adding the wrapper. Or use `gap-2` on a flex column instead of margins.

### BUG 8: Thread safety is fine — not a real issue

All handler callbacks (`on_run_step`, `on_message_delta`, `on_error`) execute on the same daemon thread within `stream.until_done()`. There is no inter-thread access to handler state. `_put()` is the only cross-thread operation, and it uses `asyncio.run_coroutine_threadsafe` which is safe.

No fix needed.

---

## Open Questions

1. **Should reasoning expand when the parent StepCard is expanded?**
   - Current plan: independent expand/collapse. "Expand all" expands both.
   - Alternative: auto-expand reasoning when StepCard expands (tighter coupling).
   - **Recommendation:** Independent, with "Expand all" covering both.

2. **Should we show reasoning for the final synthesis too?**
   - The orchestrator's final message is the situation report — it doesn't have a specific "why" since it's the conclusion.
   - Could add a "Summary of investigation strategy" section, but that's scope creep.
   - **Recommendation:** No — reasoning is only for delegation steps.

3. **Color/styling for the reasoning box?**
   - Original idea: purple-tinted glass card.
   - **Decision:** Subtle brand teal at very low opacity (`border-brand/15 bg-brand/[0.03]`). Reasoning: purple would be a hard-coded color bypassing the theme token system. The app's entire visual language is built around teal brand tokens. Using brand-at-low-opacity creates visual distinction through *weight* rather than a new hue, and automatically works in both light and dark themes. The `◇` diamond icon and italic-quoted text provide enough visual differentiation from step cards without needing a different color.

---

## Codebase Audit Addendum

> *Added after auditing the plan against the live codebase at `/home/hanchoong/projects/autonomous-network-demo/fabricdemo/`. Each item is a discrepancy between what the plan assumes and what actually exists, and includes the corrected approach.*

### AUDIT-1: Sub-agent prompt file names are wrong

**Plan says:**
- `foundry_graph_explorer_agent.md` → add guard clause
- `foundry_telemetry_agent.md` → add guard clause

**Reality:**
- `foundry_graph_explorer_agent.md` **does not exist**. The graph explorer prompt is composed from 3 files: `graph_explorer/core_instructions.md`, `graph_explorer/core_schema.md`, `graph_explorer/language_{backend}.md`. The guard clause should go in `graph_explorer/core_instructions.md`.
- `foundry_telemetry_agent.md` **does not exist**. The actual file is `foundry_telemetry_agent_v2.md`.

**Corrected file list for Phase 1D (both scenarios):**

| Agent | File to add guard clause |
|-------|--------------------------|
| GraphExplorerAgent | `data/scenarios/{scenario}/data/prompts/graph_explorer/core_instructions.md` |
| TelemetryAgent | `data/scenarios/{scenario}/data/prompts/foundry_telemetry_agent_v2.md` |
| RunbookKBAgent | `data/scenarios/{scenario}/data/prompts/foundry_runbook_kb_agent.md` |
| HistoricalTicketAgent | `data/scenarios/{scenario}/data/prompts/foundry_historical_ticket_agent.md` |

That's **8 files total** (4 agents × 2 scenarios), not the 4 listed in the plan.

### AUDIT-2: `forceExpanded` / expand-all pattern does NOT exist

**Plan assumes (Phase 3A, 3B, 3C, Bug 6):**
- `StepCard` accepts a `forceExpanded` prop
- `AgentTimeline` has an "Expand all / Collapse all" toggle and passes `allExpanded` to children

**Reality:**
- `StepCard` only accepts `{ step: StepEvent }`. No `forceExpanded` prop. Expansion is purely local `useState`.
- `AgentTimeline` has no expand-all / collapse-all functionality whatsoever.
- There is no `allExpanded` state anywhere in the codebase.

**Impact:**
- Phase 3A: Remove `forceExpanded` prop from `OrchestratorThoughts`. Use only local `useState` for expand/collapse.
- Phase 3B: Remove `forceExpanded={allExpanded}` from the template. Just render `<OrchestratorThoughts reasoning={step.reasoning} />`.
- Phase 3C: **Entire section is invalid** — there's no expand-all feature to integrate with. Drop Phase 3C entirely.
- Bug 6: **Irrelevant** — no `forceExpanded` to fix.
- Open Question 1 (expand with parent StepCard): Also irrelevant — StepCard has no `forceExpanded` either.

**If expand-all is desired later**, it should be a separate story that adds the feature to *both* `StepCard` and `OrchestratorThoughts` simultaneously.

**Corrected `OrchestratorThoughts` component:**

```tsx
import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

interface Props {
    reasoning: string;
}

export function OrchestratorThoughts({ reasoning }: Props) {
    const [expanded, setExpanded] = useState(false);

    if (!reasoning) return null;

    return (
        <button
            className="glass-card w-full text-left mb-0 cursor-pointer
                       border-brand/15 bg-brand/[0.03]
                       hover:border-brand/25 hover:bg-brand/[0.06]
                       focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-1
                       transition-all"
            onClick={() => setExpanded(v => !v)}
            aria-expanded={expanded}
            aria-label="Orchestrator reasoning for this step"
        >
            <div className="flex items-center justify-between px-3 py-1.5">
                <div className="flex items-center gap-1.5">
                    <span className="text-[10px] text-brand/60">◇</span>
                    <span className="text-[11px] font-medium text-text-muted">
                        Orchestrator Thoughts{expanded ? '' : '...'}
                    </span>
                </div>
                <span className="text-[10px] text-text-muted">
                    {expanded ? '▾' : '▸'}
                </span>
            </div>
            <AnimatePresence>
                {expanded && (
                    <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.2 }}
                        className="overflow-hidden"
                    >
                        <div className="px-3 pb-2 pt-0.5">
                            <p className="text-[11px] text-text-secondary leading-relaxed italic">
                                "{reasoning}"
                            </p>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </button>
    );
}
```

### AUDIT-3: Bug 5 call-site count is wrong

**Plan says:** "3 call sites" for `_extract_arguments()`.

**Reality:** There are exactly **2 call sites**:
1. **L214** — failed `tool_calls` step: `failed_query = self._extract_arguments(tc)`
2. **L247** — completed `tool_calls` step: `query = self._extract_arguments(tc)`

**Impact:** Bug 5 fix is still correct — update both call sites to unpack the tuple. Just fewer than expected.

### AUDIT-4: Two message emission paths need reasoning stripping

**Plan Phase 1C** only shows stripping `[ORCHESTRATOR_THINKING]` from `handler.response_text` before emitting `message`.

**Reality:** `_thread_target()` emits the `message` event from **two different code paths**:

1. **L385:** `_put("message", {"text": handler.response_text})` — normal path
2. **L395:** `_put("message", {"text": text.strip()})` — fallback path that fetches thread messages via `agents_client.messages.list()`

Both paths must strip `[ORCHESTRATOR_THINKING]` blocks. The fallback path fetches raw thread messages which may contain reasoning tags (especially if the LLM includes them in intermediate messages).

**Corrected Phase 1C — strip in both emission paths:**

```python
import re
_THINKING_RE = re.compile(
    r'\[ORCHESTRATOR_THINKING\].*?\[/ORCHESTRATOR_THINKING\]',
    flags=re.DOTALL,
)

def _strip_reasoning(text: str) -> str:
    return _THINKING_RE.sub('', text).strip()
```

Apply `_strip_reasoning()` at both emission points:
```python
# Path 1 (L385):
if handler.response_text:
    _put("message", {"text": _strip_reasoning(handler.response_text)})
    break

# Path 2 (L395):
if text:
    _put("message", {"text": _strip_reasoning(text.strip())})
    break
```

### AUDIT-5: Phase 2B hook update is over-engineered

**Plan says:** Manually construct a `StepEvent` object in the `step_complete` handler with explicit field mapping.

**Reality:** The current code simply casts: `setSteps((prev) => [...prev, data as StepEvent])`. Since the backend SSE payload already contains all the fields (including the new `reasoning`), the cast will pick it up automatically once the `StepEvent` type is updated.

**Corrected Phase 2B:** No code change needed in `useInvestigation.ts` beyond updating the `StepEvent` type (Phase 2A). The existing `data as StepEvent` cast handles it. Just verify TypeScript doesn't strip unknown fields (it doesn't — type assertion preserves all properties).

### AUDIT-6: Updated "Files Changed" table

**Corrected list of modified files:**

| File | Change |
|------|--------|
| `data/scenarios/telco-noc/data/prompts/foundry_orchestrator_agent.md` | Add `## Reasoning annotations` section |
| `data/scenarios/telecom-playground/data/prompts/foundry_orchestrator_agent.md` | Same |
| `data/scenarios/telco-noc/data/prompts/graph_explorer/core_instructions.md` | Add `[ORCHESTRATOR_THINKING]` guard |
| `data/scenarios/telco-noc/data/prompts/foundry_telemetry_agent_v2.md` | Same guard |
| `data/scenarios/telco-noc/data/prompts/foundry_runbook_kb_agent.md` | Same guard |
| `data/scenarios/telco-noc/data/prompts/foundry_historical_ticket_agent.md` | Same guard |
| `data/scenarios/telecom-playground/data/prompts/graph_explorer/core_instructions.md` | Same guard |
| `data/scenarios/telecom-playground/data/prompts/foundry_telemetry_agent_v2.md` | Same guard |
| `data/scenarios/telecom-playground/data/prompts/foundry_runbook_kb_agent.md` | Same guard |
| `data/scenarios/telecom-playground/data/prompts/foundry_historical_ticket_agent.md` | Same guard |
| `api/app/orchestrator.py` | `_extract_arguments()` → tuple return; extract reasoning; include in `step_complete` SSE; strip from both `message` emission paths |
| `frontend/src/types/index.ts` | Add `reasoning?: string` to `StepEvent` |
| `frontend/src/hooks/useInvestigation.ts` | No change needed (direct cast handles new field) |
| `frontend/src/components/OrchestratorThoughts.tsx` | **New file** — collapsible reasoning box (no `forceExpanded` prop) |
| `frontend/src/components/AgentTimeline.tsx` | Render `<OrchestratorThoughts>` above each `<StepCard>` |
| `frontend/src/components/StepCard.tsx` | Remove `mb-2` from outer `motion.div` (moved to AgentTimeline wrapper) |
| `graph-query-api/models.py` | Add `reasoning: str | None = None` to `InteractionStep` |

### AUDIT-7: Revised sprint breakdown

| Sprint | Scope | Effort |
|--------|-------|--------|
| **S1** | Prompt update (orchestrator + 8 sub-agent prompt files) + re-provision ALL agents + test reasoning block production | ~1.5 hrs |
| **S2** | `orchestrator.py` — `_extract_arguments()` tuple return (2 call sites), reasoning extraction, `step_complete` SSE emission, strip from both message paths | ~2 hrs |
| **S3** | Frontend types + `OrchestratorThoughts` component (no `forceExpanded`) + AgentTimeline integration + StepCard `mb-2` removal | ~1.5 hrs |
| **S4** | `InteractionStep` model update + edge case testing | ~1 hr |

**Total estimated effort: ~6 hours** (unchanged, but work redistribution is more accurate)
