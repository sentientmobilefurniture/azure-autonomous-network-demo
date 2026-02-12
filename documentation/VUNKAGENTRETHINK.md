# V3 UI Enhancement: Sub-Agent Streaming & Telemetry

## Summary

This document captures research into real-time sub-agent streaming, what's
possible and what isn't with the current Azure AI Agents SDK (`1.2.0b6`),
and the plan for enriching the investigation UI with sub-agent execution
detail.

---

## The Question

Can we stream sub-agent logs (internal tool calls, queries, intermediate
reasoning) to the UI in real time as the orchestrator runs?

### Quick Answer

**No — not in real time.** But we CAN enrich the UI with sub-agent detail
**post-hoc** using data the SDK already exposes.

---

## SDK Architecture: Why Real-Time Sub-Agent Streaming Is Impossible

### How ConnectedAgentTool Works

When the orchestrator calls a sub-agent via `ConnectedAgentTool`, the following
happens server-side:

```
Orchestrator run (parent thread)
  └─ tool_call: connected_agent
       └─ Azure AI service creates a NEW thread + run for the sub-agent
            └─ Sub-agent executes (may call OpenApiTool, AzureAISearchTool, etc.)
            └─ Sub-agent completes → output returned to parent as tool_call result
       └─ Parent run resumes with sub-agent output
```

The sub-agent run is **entirely server-side**. The parent's event stream
(`AgentEventHandler`) receives exactly **one** event for the sub-agent: the
completed `tool_calls` step containing the `RunStepConnectedAgent` object.

### What Events the Parent Stream Receives

| Event | Agent | Timing | Data |
|-------|-------|--------|------|
| `on_thread_run` | Parent | Start/end | Run status, usage |
| `on_run_step` (in_progress) | Parent | When tool call starts | Step ID, type |
| `on_run_step_delta` | Parent | Progressive | Field-by-field population |
| `on_run_step` (completed) | Parent | When tool call finishes | Full `RunStepConnectedAgent` |
| `on_message_delta` | Parent | Final answer streaming | Text chunks |

**Crucially missing**: There are no events from the sub-agent's internal execution.
No `on_run_step` for the sub-agent's tool calls, no `on_message_delta` for the
sub-agent's reasoning. The parent stream is blind to what happens inside a
connected agent call.

### RunStepConnectedAgent Fields

When a connected agent tool call completes, the `RunStepConnectedAgent` object
contains:

```python
class RunStepConnectedAgent:
    name: str           # Sub-agent name (e.g., "GraphExplorerAgent")
    arguments: str      # JSON string of input sent to sub-agent
    output: str         # Sub-agent's final response text
    run_id: str         # The sub-agent's own run ID
    thread_id: str      # The sub-agent's own thread ID
    agent_id: str       # The sub-agent's agent ID
```

The `run_id` and `thread_id` are the key to post-hoc enrichment.

### What on_run_step_delta Gives Us (Early Signals)

The `on_run_step_delta` callback fires as individual fields of the step are
populated. For connected agent calls, this means:

1. **Early**: `name` field populated → we know which sub-agent is being called
2. **Early-mid**: `arguments` populated → we know what input was sent
3. **Late**: `output` populated → sub-agent has finished

This gives us enough to show "Calling GraphExplorerAgent..." and
"Sent: {query text}" in the UI before the sub-agent finishes, even though we
can't see the sub-agent's internal progress.

### Current Implementation

The current `SSEEventHandler` in `api/app/orchestrator.py` already extracts
connected agent data from completed steps:

```python
# In on_run_step (status == "completed", step_type == "tool_calls")
if tc_type == "connected_agent":
    ca = tc.connected_agent
    agent_name = ca.name
    query = json.loads(ca.arguments)
    response = ca.output
    # Emits step_start + step_complete SSE events
```

This works but only fires on completion. The `on_run_step_delta` handler is
**not yet implemented** and would provide early signals.

---

## Post-Hoc Enrichment: The Viable Path

### Concept

After a sub-agent completes, we have its `thread_id` and `run_id`. We can use
the Agents SDK to fetch the sub-agent's own execution trace:

```python
# After connected agent tool call completes
sub_thread_id = ca.thread_id
sub_run_id = ca.run_id

# Fetch the sub-agent's own run steps
sub_steps = agents_client.run_steps.list(
    thread_id=sub_thread_id,
    run_id=sub_run_id,
)

# Fetch the sub-agent's messages (including tool call results)
sub_messages = agents_client.messages.list(
    thread_id=sub_thread_id,
)
```

### What Sub-Agent Run Steps Reveal

Each sub-agent's run steps contain:

| Step Type | Content |
|-----------|---------|
| `tool_calls` | The actual tool calls the sub-agent made (e.g., `OpenApiTool` call to `/query/graph` with a graph query) |
| `message_creation` | The sub-agent's reasoning and response composition |

For a GraphExplorerAgent call, you'd see:
1. **Step 1** (tool_calls): `OpenApiTool` → `POST /query/graph` with `{"query": "MATCH (r:CoreRouter)-[:CONNECTS_TO]->(l:TransportLink) WHERE l.LinkId = 'LINK-SYD-MEL-FIBRE-01' RETURN r.RouterId, r.City"}`
2. **Step 2** (message_creation): Agent synthesizes the raw data into a natural language response

For a TelemetryAgent call:
1. **Step 1** (tool_calls): `OpenApiTool` → `POST /query/telemetry` with `{"query": "AlertStream | where EntityId == 'LINK-SYD-MEL-FIBRE-01' | top 10 by Timestamp desc"}`
2. **Step 2** (message_creation): Agent returns the raw data

### What This Enables in the UI

Each `step_complete` SSE event currently contains:
```json
{
  "step": 1,
  "agent": "GraphExplorerAgent",
  "duration": "4.2s",
  "query": "<input arguments>",
  "response": "<final response text>"
}
```

With post-hoc enrichment, we can add:
```json
{
  "step": 1,
  "agent": "GraphExplorerAgent",
  "duration": "4.2s",
  "query": "<input arguments>",
  "response": "<final response text>",
  "tool_calls": [
    {
      "tool": "query_graph",
      "input": "MATCH (r:CoreRouter)-[:CONNECTS_TO]->(l:TransportLink) WHERE l.LinkId = 'LINK-SYD-MEL-FIBRE-01' RETURN r.RouterId, r.City",
      "output": "{\"columns\": [...], \"data\": [...]}"
    }
  ],
  "retries": 0
}
```

This gives the operator visibility into the exact queries agents ran, whether
they retried on errors, and the raw data they received.

### Implementation Cost

**Backend** (orchestrator.py changes):
- Add enrichment logic after each connected agent step completes
- ~30 lines of code: list run_steps, extract tool calls, append to SSE payload
- Adds ~200-500ms latency per sub-agent (one API call to list run steps)

**Frontend** (expandable step cards):
- Each step card gets a "Details" toggle
- Expanding shows: exact query text (with syntax highlighting), raw response,
  any retry errors
- ~50-100 lines of additional React code

### Latency Concern

Fetching sub-agent run steps adds a sequential API call per sub-agent. For 4
sub-agents, that's potentially 800ms-2s of additional latency before
`step_complete` events are emitted. Options:

1. **Fire step_complete immediately, enrich later**: Emit `step_complete` without
   tool_calls, then emit a separate `step_enriched` event once the fetch returns.
   The UI updates the card asynchronously.

2. **Accept the latency**: 200-500ms per sub-agent is acceptable if the total
   investigation takes 30-60s anyway.

3. **Make it optional**: Only fetch sub-agent details if the UI requests it
   (e.g., a "Load details" button on each step card triggers a backend API call).

**Recommendation**: Option 1 (fire-then-enrich). It gives the fastest perceived
performance while still populating details automatically. The SSE event stream
would look like:

```
event: step_start     {"step": 1, "agent": "GraphExplorerAgent"}
event: step_complete  {"step": 1, "agent": "GraphExplorerAgent", "duration": "4.2s", ...}
event: step_enriched  {"step": 1, "tool_calls": [...]}  ← new event, arrives ~300ms later
```

---

## The Nuclear Option: FunctionTool Manual Orchestration

If true real-time sub-agent streaming is required, the only path is to **replace
ConnectedAgentTool with explicit FunctionTool orchestration**:

```python
# Instead of ConnectedAgentTool, register a FunctionTool on the orchestrator
@function_tool
def call_graph_explorer(query: str) -> str:
    """Manually create a thread, run the GraphExplorerAgent, stream events."""
    thread = agents_client.threads.create()
    agents_client.messages.create(thread_id=thread.id, role="user", content=query)

    # Stream the sub-agent's events and forward them to the SSE queue
    with agents_client.runs.stream(
        thread_id=thread.id,
        agent_id=graph_explorer_id,
        event_handler=SubAgentEventHandler(queue, "GraphExplorerAgent"),
    ) as stream:
        stream.until_done()

    # Return the sub-agent's response to the parent orchestrator
    messages = agents_client.messages.list(thread_id=thread.id)
    return extract_response(messages)
```

### Pros
- Full real-time streaming of sub-agent events
- Each sub-agent's tool calls visible as they happen
- Maximum transparency

### Cons
- **Massive complexity**: You're reimplementing ConnectedAgentTool from scratch
- **Lost automatic handoff**: ConnectedAgentTool handles thread creation,
  context passing, and output extraction automatically
- **Orchestrator prompt changes**: The orchestrator now calls `call_graph_explorer()`
  instead of naturally routing to a connected agent. The prompt engineering
  changes significantly. The model may route less intelligently.
- **Thread management**: You own thread cleanup, error handling, timeouts
- **Maintenance burden**: Every SDK update to ConnectedAgentTool semantics must
  be manually replicated

### Verdict

**Not recommended** for this demo. The post-hoc enrichment path provides 90% of
the value at 10% of the cost. The nuclear option exists as documentation for
future reference if real-time sub-agent observability becomes a hard requirement.

---

## UI Design: Sub-Agent Detail Display

### Current Step Cards

```
┌─────────────────────────────────────────────┐
│ ● Step 1 — GraphExplorerAgent     [4.2s]    │
│   Query: {"question": "What links connect…" │
│   Response: "The following links..."         │
└─────────────────────────────────────────────┘
```

### Enhanced Step Cards (with enrichment)

```
┌─────────────────────────────────────────────────────────────┐
│ ● Step 1 — GraphExplorerAgent                     [4.2s]    │
│   Input: "What transport links connect Sydney to Melbourne?" │
│                                                             │
│   ▼ Tool Calls (1)                                          │
│   ┌─────────────────────────────────────────────────────┐   │
│   │ query_graph                                         │   │
│   │ ┌─────────────────────────────────────────────┐     │   │
│   │ │ MATCH (t:TransportLink)                     │     │   │
│   │ │ WHERE t.SourceRouterId = 'CORE-SYD-01'     │     │   │
│   │ │   AND t.TargetRouterId = 'CORE-MEL-01'     │     │   │
│   │ │ RETURN t.LinkId, t.LinkType, t.CapacityGbps│     │   │
│   │ └─────────────────────────────────────────────┘     │   │
│   │ ▼ Raw Response (2 rows)                             │   │
│   │ LINK-SYD-MEL-FIBRE-01 | DWDM_100G | 100            │   │
│   │ LINK-SYD-MEL-FIBRE-02 | DWDM_100G | 100            │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                             │
│   ● Response:                                               │
│   "There are two transport links between Sydney and         │
│    Melbourne: LINK-SYD-MEL-FIBRE-01 and LINK-SYD-MEL-..."  │
└─────────────────────────────────────────────────────────────┘
```

### UI Components Needed

| Component | Purpose | Skill Reference |
|-----------|---------|-----------------|
| `StepCard` | Expandable card for each sub-agent call | `frontend-ui-dark-ts` (glassmorphism panels) |
| `ToolCallDetail` | Nested panel showing tool invocation | `frontend-ui-dark-ts` |
| `QueryHighlighter` | Syntax-highlighted query display | Could use `react-syntax-highlighter` or `prism-react-renderer` |
| `CollapsibleSection` | Expand/collapse for tool calls and raw responses | Framer Motion for smooth animation |

### State Management

Using Zustand (per `zustand-store-ts` skill):

```typescript
interface InvestigationStore {
  steps: StepData[];
  addStep: (step: StepData) => void;
  enrichStep: (stepNum: number, toolCalls: ToolCallData[]) => void;
  // ...
}

interface StepData {
  step: number;
  agent: string;
  duration: string;
  query: string;
  response: string;
  toolCalls?: ToolCallData[];  // populated by step_enriched event
}

interface ToolCallData {
  tool: string;
  input: string;
  output: string;
}
```

The SSE consumer would handle the new `step_enriched` event:

```typescript
case 'step_enriched':
  useInvestigationStore.getState().enrichStep(
    data.step,
    data.tool_calls
  );
  break;
```

---

## Implementation Plan

### Phase 1: Post-Hoc Enrichment (Backend)

**File**: `api/app/orchestrator.py`

1. After each connected agent step completes, extract `ca.thread_id` and
   `ca.run_id`
2. Call `agents_client.run_steps.list(thread_id, run_id)` to get sub-agent steps
3. Extract tool call details (tool name, input, output) from each step
4. Emit a new `step_enriched` SSE event with the tool call data
5. Handle errors gracefully (enrichment failure should not break the main stream)

**Estimated effort**: ~30-50 lines of code, 0.5 day

### Phase 2: Enhanced Step Cards (Frontend)

**Files**: New components in `frontend/src/`

1. Add `ToolCallDetail` component (collapsible panel with query + response)
2. Update existing step display to support `toolCalls` in step data
3. Handle `step_enriched` SSE events in the consumer
4. Add query syntax highlighting (Gremlin/Cypher keywords)
5. Add Framer Motion expand/collapse animation

**Estimated effort**: ~100-150 lines of new React code, 1 day

### Phase 3: on_run_step_delta for Early Signals

**File**: `api/app/orchestrator.py`

1. Implement `on_run_step_delta` callback in `SSEEventHandler`
2. When `name` field is populated → emit `step_thinking` event with agent name
3. When `arguments` field is populated → emit `step_input` event with query text
4. Frontend shows "Calling GraphExplorerAgent with: ..." before step completes

**Estimated effort**: ~20 lines of code, 0.5 day

---

## Skills References

### Directly Applicable

| Skill | Path | Usage |
|-------|------|-------|
| `react-flow-node-ts` | `.github/skills/react-flow-node-ts/` | Custom node components for graph viz (shared with V3GRAPH) |
| `zustand-store-ts` | `.github/skills/zustand-store-ts/` | Store design: `subscribeWithSelector`, individual selectors, `useShallow` |
| `frontend-ui-dark-ts` | `.github/skills/frontend-ui-dark-ts/` | Dark theme, glassmorphism, brand purple `#8251EE`, Framer Motion |
| `fastapi-router-py` | `.github/skills/fastapi-router-py/` | APIRouter for enrichment endpoint if on-demand |
| `pydantic-models-py` | `.github/skills/pydantic-models-py/` | Response models for enriched step data |

### Key Patterns from Skills

**Zustand store** (`zustand-store-ts`):
- Use `subscribeWithSelector` for efficient step-card re-rendering
- Individual selectors: `useInvestigationStore(s => s.steps)` not `useStore()`
- `useShallow` for array selectors to prevent unnecessary re-renders

**Frontend dark theme** (`frontend-ui-dark-ts`):
- Glassmorphism for step cards: `bg-white/5 backdrop-blur-xl border border-white/10`
- Framer Motion `AnimatePresence` for expand/collapse transitions
- Brand purple accent: `#8251EE` for active states and highlights

**FastAPI router** (`fastapi-router-py`):
- If implementing on-demand enrichment: `APIRouter(prefix="/enrichment")`
- Response models: `class EnrichedStep(BaseModel): ...`

---

## SSE Event Stream: Complete Specification

### Current Events

| Event | When | Payload |
|-------|------|---------|
| `run_start` | Investigation begins | `{run_id, alert, timestamp}` |
| `step_thinking` | Sub-agent call starts | `{agent, status}` |
| `step_start` | Step registered | `{step, agent}` |
| `step_complete` | Sub-agent returns | `{step, agent, duration, query, response}` |
| `message` | Final answer ready | `{text}` |
| `run_complete` | Investigation finished | `{steps, tokens, time}` |
| `error` | Failure | `{message}` |

### New Events (V3)

| Event | When | Payload |
|-------|------|---------|
| `step_input` | Sub-agent arguments known (delta) | `{step, agent, arguments}` |
| `step_enriched` | Sub-agent details fetched | `{step, tool_calls: [{tool, input, output}]}` |

### Event Timeline Example

```
00.0s  run_start       {alert: "LINK-SYD-MEL-FIBRE-01 down"}
00.5s  step_thinking   {agent: "Orchestrator", status: "calling sub-agent..."}
01.0s  step_input      {step: 1, agent: "GraphExplorerAgent", arguments: "..."}
04.5s  step_start      {step: 1, agent: "GraphExplorerAgent"}
04.5s  step_complete   {step: 1, agent: "GraphExplorerAgent", duration: "4.0s", ...}
04.8s  step_enriched   {step: 1, tool_calls: [{tool: "query_graph", input: "MATCH...", output: "..."}]}
05.0s  step_thinking   {agent: "Orchestrator", status: "calling sub-agent..."}
05.5s  step_input      {step: 2, agent: "TelemetryAgent", arguments: "..."}
09.0s  step_start      {step: 2, agent: "TelemetryAgent"}
09.0s  step_complete   {step: 2, agent: "TelemetryAgent", duration: "3.5s", ...}
09.3s  step_enriched   {step: 2, tool_calls: [{tool: "query_telemetry", ...}]}
...
35.0s  message         {text: "## Situation Report\n\n### Incident Summary\n..."}
35.5s  run_complete    {steps: 6, tokens: 4200, time: "35.5s"}
```

---

## Learnings

### SDK Internals

1. **ConnectedAgentTool is opaque by design**: The SDK authors intentionally
   encapsulate sub-agent execution. This is good for simplicity but prevents
   real-time observability of sub-agents.

2. **RunStepConnectedAgent exposes enough for post-hoc**: The `thread_id` and
   `run_id` fields were likely added precisely for this use case — fetching
   sub-agent traces after the fact.

3. **on_run_step_delta is underused**: Most examples only implement
   `on_message_delta` for text streaming. The step delta callback gives early
   signals about what the model is doing (calling tools, selecting agents).

4. **Thread isolation**: Each connected agent call creates a fresh thread.
   Sub-agent threads are NOT visible through the parent thread's API. You must
   use the sub-agent's own `thread_id` to access its history.

5. **Token usage is parent-only**: `run.usage.total_tokens` on the parent run
   includes tokens consumed by sub-agents, but there's no breakdown per
   sub-agent in the parent run. To get per-agent token usage, you'd need to
   fetch each sub-agent's run via `runs.get(thread_id, run_id)`.

### Architecture Implications

1. **Post-hoc enrichment is async-safe**: Fetching sub-agent details happens
   after the step completes. Even if the fetch fails, the main investigation
   stream is unaffected.

2. **SSE is sufficient**: No need for WebSocket upgrade just for enrichment
   events. The unidirectional SSE stream can carry `step_enriched` events fine.

3. **State management matters**: With asynchronous enrichment, the frontend
   must handle steps appearing before their details. Zustand's
   `subscribeWithSelector` makes this clean — individual step cards re-render
   only when their tool_calls change.

---

## Open Questions

1. **Token usage per sub-agent**: Should we fetch per-sub-agent token usage
   via `runs.get(thread_id, run_id).usage`? Useful for cost visibility but
   adds another API call per sub-agent.

2. **Query syntax highlighting**: Which library? `prism-react-renderer` is
   lightweight, `react-syntax-highlighter` is heavier but supports more
   languages. Need Gremlin/Cypher highlighting.

3. **Enrichment caching**: If the user re-expands a step card, should we re-fetch
   from the API or cache the enrichment data? Caching is simpler and the data
   doesn't change after completion.

4. **Sub-agent retries**: If a sub-agent retried a query (e.g., graph query syntax error
   → fixed → retried), the run_steps will show multiple tool calls. Should the
   UI display all attempts or only the final successful one? Showing all
   attempts is more educational for the NOC operator.
