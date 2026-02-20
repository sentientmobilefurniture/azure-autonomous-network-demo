# Story 1 — Step-Level Visualization Buttons

> **Audit Status: REVIEWED** — Audited against live codebase on 2026-02-19.
> Plan is architecturally sound and will fulfil requirements. Critical corrections applied:
> 1. **Prompt file paths fixed** — were generic `prompts/`, now point to actual scenario-specific paths under `data/scenarios/telecom-playground/data/prompts/`
> 2. **GraphExplorer prompt composition documented** — prompt is assembled from 3 files at provisioning time; Response Format must go into `core_instructions.md`
> 3. **RunbookKB/HistoricalTicket prompt paths added** — explicit file paths for developer clarity
> 4. **Modified files table expanded** — now lists all 4 prompt files to edit
> 5. **BUGs 11-13 added** — `AzureAISearch` dead code path, replay error handling gap, empty query for AI Search steps
> 6. **BUG 12 (replay error handling)** — `useVisualization` replay path doesn't handle graph-query-api's error-in-200 pattern; would cause silent failures

## Vision

Each conversation step in the Investigation Panel gets a **visualization button** (bottom-right corner of the StepCard). Clicking it opens a **modal overlay** showing rich, type-aware visualization of that step's data, then closes cleanly when dismissed.

| Agent type | Visual treatment |
|---|---|
| `GraphExplorerAgent` | Force-directed graph of returned nodes & edges |
| `TelemetryAgent` | Tabular data grid (columns + rows) |
| `RunbookKBAgent` | Formatted document / knowledge-panel list |
| `HistoricalTicketAgent` | Formatted document / knowledge-panel list |
| `AzureAISearch` (generic) | Formatted document / knowledge-panel list |

![conceptual](assets/story1-concept.png) *(to be added)*

---

## Current State Analysis

### What we have today

| Component | Purpose |
|---|---|
| `StepCard.tsx` | Renders one `StepEvent` — collapsed preview + expandable query/response |
| `AgentTimeline.tsx` | Maps `StepEvent[]` → `<StepCard>` list |
| `GraphTopologyViewer.tsx` + `graph/*` | Force-directed network topology viewer (uses `react-force-graph-2d`) |
| `ResourceVisualizer.tsx` + `resource/*` | Force-directed agent-architecture viewer |

### Key constraint — no structured data on the frontend today

`StepEvent` only carries:
```ts
{ step, agent, duration?, query?, response?, error? }
```
`query` and `response` are **plain strings** (truncated at 500 / 2000 chars in the orchestrator). The structured query results (`{ columns, data }` for GQL and `{ columns, rows }` for KQL) exist only between the graph-query-api microservice and the Azure AI Foundry tool — they never reach the frontend.

This means we need a **data pipeline change** to surface structured results.

---

## Architecture Plan

### Phase 1 — Backend: Surface Structured Data

#### 1A. Extend `StepEvent` with optional structured payload

Add a new optional field to the SSE `step_complete` event:

```python
# orchestrator.py — step_complete payload
{
    "event": "step_complete",
    "data": {
        "step": 3,
        "agent": "GraphExplorerAgent",
        "duration": "11.2s",
        "query": "MATCH (l:TransportLink)...",
        "response": "The link LINK-SYD-MEL-FIBRE-01 ...",
        "visualization": {                       # ← NEW
            "type": "graph",                     # "graph" | "table" | "documents"
            "data": { ... }                      # type-specific structured payload
        }
    }
}
```

**Visualization payload shapes:**

```jsonc
// type: "graph"
// NOTE: graph-query-api returns `data` (not `rows`) for GQL results — see BUG 3
{
    "type": "graph",
    "data": {
        "columns": [{"name": "r.RouterId", "type": "String"}, ...],
        "data": [{"r.RouterId": "RTR-01", ...}, ...],
        "query": "MATCH (r:CoreRouter) RETURN r.RouterId, r.Hostname"
    }
}

// type: "table"
{
    "type": "table",
    "data": {
        "columns": [{"name": "AlertId", "type": "String"}, {"name": "Timestamp", "type": "DateTime"}, ...],
        "rows": [{"AlertId": "A1", "Timestamp": "...", ...}, ...],
        "query": "AlertStream | where SourceNodeId == 'LINK-SYD-MEL-FIBRE-01' | top 20"
    }
}

// type: "documents"
{
    "type": "documents",
    "data": {
        "content": "...agent's response text...",
        "agent": "RunbookKBAgent"
    }
}
```

#### 1B. Strategy for obtaining structured data — corrected analysis

> **⚠ Critical finding: `step.query` is NOT the actual GQL/KQL query.**

The `_extract_arguments()` method in `orchestrator.py` (line 171) extracts `connected_agent.arguments`, which is the **orchestrator's natural language delegation instruction** to the sub-agent (e.g., *"Search for transport links related to LINK-SYD-MEL-FIBRE-01"*). The actual GQL/KQL query is formulated **inside** the sub-agent by its LLM and sent to the OpenAPI tool (graph-query-api). The orchestrator never sees this query.

Similarly, `connected_agent.output` (line 254) is the sub-agent's **LLM-generated text summary** — not the raw JSON response from `/query/graph` or `/query/telemetry`. The structured `{columns, data/rows}` response exists only within the sub-agent's thread context and is consumed by the sub-agent's LLM to produce its summary.

| What we assumed | Reality |
|-----------------|---------|
| `step.query` = actual GQL/KQL | `step.query` = orchestrator's NL instruction to sub-agent |
| `step.response` = raw query results | `step.response` = sub-agent's LLM-generated text summary |
| Can replay by re-executing `step.query` | Cannot — `step.query` is not an executable database query |

**For AI Search agents (RunbookKBAgent, HistoricalTicketAgent):** The `AzureAISearchTool` is a **Foundry built-in tool**. The actual search query is generated inside the sub-agent's LLM and executed by Foundry's runtime. Neither the search query nor the raw search hits (document titles, content chunks, relevance scores) are exposed to the orchestrator. Only the sub-agent's synthesized summary surfaces as `connected_agent.output`.

---

**Three options (revised analysis):**

**Option A — Replay (❌ BROKEN as originally designed)**

As originally described, this fails because `step.query` isn't the actual GQL/KQL. Could be salvaged by:
1. Parsing the actual query from the sub-agent's response text (fragile — relies on the LLM echoing the query)
2. Modifying sub-agent prompts to include queries in a parseable format (see Option C)

Even if fixed, replay is **impossible** for AI Search agents and provides **no guarantee of consistent results** for graph/telemetry (underlying data may change between investigation and view time).

For **restored interactions**, this approach works only if the actual query was persisted — which it currently is not. The persisted `step.query` contains the NL instruction.

**Option B — Piggyback on SSE stream (❌ NOT FEASIBLE as described)**

The original proposal suggested intercepting `RequiresAction` tool outputs. However:
- The `RequiresAction` event in `on_run_step` fires for the **orchestrator's** tool calls (connected_agent type), not the sub-agent's internal tool calls (OpenAPI calls to graph-query-api)
- `connected_agent.output` is the sub-agent's text summary, not raw tool responses
- The Foundry Agents SDK provides no callback hook to intercept tool calls inside a connected agent's thread
- Accessing the sub-agent's thread steps would require the sub-thread ID, which is not exposed by `AgentEventHandler`

**Option C — Sub-agent prompt instrumentation + orchestrator parsing (✅ RECOMMENDED)**

Modify the sub-agent prompts to **return structured data in a machine-parseable format** within their response. Then have the orchestrator parse `connected_agent.output` and separate it into:
- `response` — the NL summary text (same as today, for display in StepCard)
- `visualization` — the structured payload (actual query + raw results)

This works because:
1. Sub-agents have full access to their tool call results (the raw `{columns, data}` JSON from graph-query-api)
2. We control the sub-agent prompts (we provision them via `agent_provisioner.py`)
3. The orchestrator already reads `connected_agent.output` — we just parse more from it
4. No Foundry SDK changes or new infrastructure required
5. Captured at investigation time → available for **immediate persistence** → works in restored interactions

**See Phase 1D for detailed implementation.**

**Recommendation:** Use **Option C** for all agents. This is the only approach that:
1. Captures the **actual query** AND **structured results** (not NL paraphrasing)
2. Works at investigation time (no extra API calls, no latency spike on viz button click)
3. Can be **persisted** with the interaction for restored-interaction visualization
4. Handles all agent types (including AI Search via citation extraction — see 1D)

#### 1C. Replay endpoint (fallback only — for pre-migration interactions)

The replay endpoint is now a **fallback mechanism** for interactions saved before the prompt instrumentation was deployed. It requires the actual GQL/KQL query, which is only available for interactions saved AFTER Phase 1D is deployed.

```
POST /query/replay
Content-Type: application/json

{
    "agent": "GraphExplorerAgent",
    "query": "MATCH (l:TransportLink) WHERE l.LinkId = 'LINK-SYD-MEL-FIBRE-01' RETURN l"
}

Response 200:
{
    "type": "graph",
    "columns": [...],
    "data": [...]
}
```

**Routing logic:**

| `agent` value | Backend target | Response shape |
|---------------|---------------|----------------|
| `GraphExplorerAgent` | `POST /query/graph` → graph-query-api | `{ type: "graph", columns: [...], data: [...] }` |
| `TelemetryAgent` | `POST /query/telemetry` → graph-query-api | `{ type: "table", columns: [...], rows: [...] }` |
| `RunbookKBAgent` / `HistoricalTicketAgent` | No backend call | N/A — render `step.response` directly |

> **⚠ Gotcha — replay endpoint must call graph-query-api directly:**
> The replay endpoint routes to our own graph-query-api service (`/query/graph`, `/query/telemetry`), NOT through the Foundry agent tool system. This is correct and intentional.

> **⚠ Gotcha — pre-migration interactions cannot be replayed:**
> If the interaction was saved before Phase 1D was deployed, `step.query` contains the NL instruction (not the actual GQL/KQL query), and there is no `visualization` payload. In this case the viz button should show a graceful degradation message:
> *"Structured data was not captured for this investigation. Re-run the investigation to see visualization results."*
> Do NOT attempt to pass the NL instruction to the replay endpoint — it will fail with a syntax error from the graph/telemetry backend.

> **⚠ Gotcha — 500-char truncation breaks replay:**
> `step.query` is currently truncated to 500 chars in the orchestrator (line 263). If the actual query exceeds 500 chars, the truncated version cannot be replayed. After Phase 1D, the actual query is stored in `visualization.data.query` (untruncated), so this is only a concern for the replay fallback path.

**Files to modify:**
- `graph-query-api/router_replay.py` — add replay router (must be on graph-query-api, NOT main API — see BUG 8)
- `graph-query-api/main.py` — register the replay router
- `graph-query-api/` — no changes needed to existing `/query/graph` and `/query/telemetry` endpoints (reused)

#### 1D. Sub-agent prompt instrumentation (data capture)

Modify sub-agent prompts so their responses include structured data in a parseable format. Then modify the orchestrator to parse this data from `connected_agent.output`.

##### 1D-i. Prompt changes for GraphExplorerAgent and TelemetryAgent

Append the following instruction block to `data/scenarios/telecom-playground/data/prompts/graph_explorer/core_instructions.md` and `data/scenarios/telecom-playground/data/prompts/foundry_telemetry_agent_v2.md`:

> **⚠ CRITICAL — GraphExplorer prompt is composed from MULTIPLE files:**
> The GraphExplorer prompt is assembled at provisioning time from three files:
> 1. `graph_explorer/core_instructions.md` — role, rules, behavior
> 2. `graph_explorer/core_schema.md` — entity/relationship ontology
> 3. `graph_explorer/language_gql.md` (or `language_mock.md`) — query syntax
>
> The Response Format section must be appended to `core_instructions.md` (the behavioral instructions file),
> NOT to the schema or language files. See `scripts/provision_agents.py` → `_load_graph_explorer_prompt()`
> for the composition logic.
>
> **Prompt file path resolution:** All prompt files live under `PROMPTS_DIR`, which is resolved at runtime
> by `scenario_loader.py` from `scenario.yaml`. The default scenario resolves to:
> `data/scenarios/telecom-playground/data/prompts/`

```markdown
## Response Format

Always structure your response with these sections, separated by the exact delimiters shown:

---QUERY---
<the exact GQL/KQL query you sent to the tool, as-is>
---RESULTS---
<the complete JSON response from the query tool, pasted verbatim>
---ANALYSIS---
<your analysis and summary for the orchestrator>
```

**Example sub-agent output after instrumentation:**

```
---QUERY---
MATCH (l:TransportLink) WHERE l.LinkId = 'LINK-SYD-MEL-FIBRE-01' RETURN l
---RESULTS---
{"columns": [{"name": "l.LinkId", "type": "String"}, {"name": "l.Status", "type": "String"}], "data": [{"l.LinkId": "LINK-SYD-MEL-FIBRE-01", "l.Status": "DEGRADED"}]}
---ANALYSIS---
The link LINK-SYD-MEL-FIBRE-01 is currently in DEGRADED status...
```

> **⚠ Gotcha — LLM may not echo tool results verbatim:**
> Even with explicit instructions, the LLM may:
> - Truncate large result sets (especially if >50 rows)
> - Reformulate the JSON (add whitespace, reorder keys)
> - Omit the delimiters if the prompt isn't strong enough
>
> Mitigations:
> 1. Use very explicit prompt language: *"Paste the COMPLETE JSON response between the RESULTS delimiters. Do NOT summarize, truncate, or omit any fields."*
> 2. Test with real-world queries that return 20+ rows to verify the LLM complies
> 3. If the LLM truncates results (e.g., >100 rows), accept partial data and show a `"Results may be incomplete — showing what was captured"` notice in the modal
> 4. In the orchestrator parser, handle malformed/missing delimiters gracefully (fall back to documents-type visualization using the full response text)

> **⚠ Gotcha — increased token usage:**
> Requiring sub-agents to echo raw tool results in their response will increase output token consumption. For a typical GraphExplorer step returning 20 rows × 5 columns, this adds ~500-2000 output tokens per step. For a 5-step investigation, total increase is ~2500-10000 tokens. This is acceptable but should be monitored.
>
> If token cost becomes a concern, consider:
> - Limiting echoed results to first 100 rows with a `"(truncated N remaining rows)"` notice
> - Making the echo opt-in via a prompt variable (echo only when the orchestrator's instruction includes a flag)

##### 1D-ii. Prompt changes for RunbookKBAgent and HistoricalTicketAgent

**Prompt files to modify:**
- RunbookKBAgent: `data/scenarios/telecom-playground/data/prompts/foundry_runbook_kb_agent.md`
- HistoricalTicketAgent: `data/scenarios/telecom-playground/data/prompts/foundry_historical_ticket_agent.md`

AI Search agents can't expose the raw search hits or the actual search query (handled by Foundry's built-in `AzureAISearchTool`). However, we can instruct them to include **citations** in a structured format:

```markdown
## Response Format

Always structure your response with these sections, separated by the exact delimiters shown:

---CITATIONS---
<list each source document you referenced, one per line, in the format:>
- [document_title] relevance: high|medium|low
---ANALYSIS---
<your analysis incorporating the search results>
```

This gives us at least document-level metadata for the visualization panel. The actual content remains the LLM summary, which is the best we can get without building a custom search tool (which would be a Story 3+ effort).

> **⚠ Gotcha — `AzureAISearchTool` results are invisible:**
> Unlike OpenAPI tools where the sub-agent sees `{columns, data}` JSON, the `AzureAISearchTool` returns document chunks directly into the sub-agent's context. The sub-agent never sees a parseable "results JSON" — only the injected document text. So we cannot instruct it to "echo the tool response verbatim" — there is no discrete response to echo.
>
> This means AI Search visualization will always be `type: "documents"` — the sub-agent's text summary + optional citation metadata. This is an acceptable limitation.

##### 1D-iii. Orchestrator parser changes

Modify the `on_run_step` handler in `orchestrator.py` to parse structured data from `connected_agent.output` before emitting `step_complete`.

```python
# orchestrator.py — new helper method on SSEEventHandler

import re

def _parse_structured_output(self, agent_name: str, raw_output: str) -> tuple[str, dict | None]:
    """Parse sub-agent output into (summary_text, visualization_payload).
    
    Returns:
        (response_text, visualization_dict_or_None)
    """
    if not raw_output:
        return "", None
    
    # Try to extract delimited sections
    query_match = re.search(r'---QUERY---\s*(.+?)\s*---(?:RESULTS|ANALYSIS)---', raw_output, re.DOTALL)
    results_match = re.search(r'---RESULTS---\s*(.+?)\s*---ANALYSIS---', raw_output, re.DOTALL)
    analysis_match = re.search(r'---ANALYSIS---\s*(.+)', raw_output, re.DOTALL)
    citations_match = re.search(r'---CITATIONS---\s*(.+?)\s*---ANALYSIS---', raw_output, re.DOTALL)
    
    # Determine viz type from agent name
    viz_type = {
        "GraphExplorerAgent": "graph",
        "TelemetryAgent": "table",
    }.get(agent_name, "documents")
    
    # For graph/table agents with delimited output
    if query_match and results_match:
        actual_query = query_match.group(1).strip()
        raw_results = results_match.group(1).strip()
        summary = analysis_match.group(1).strip() if analysis_match else raw_output
        
        # Parse the raw results JSON
        try:
            results_json = json.loads(raw_results)
        except json.JSONDecodeError:
            # LLM mangled the JSON — fall back to documents view
            logger.warning("Failed to parse structured results JSON for %s", agent_name)
            return raw_output, {
                "type": "documents",
                "data": {"content": raw_output, "agent": agent_name}
            }
        
        viz_data = {
            "type": viz_type,
            "data": {
                **results_json,   # columns + data/rows
                "query": actual_query,
            }
        }
        return summary, viz_data
    
    # For AI Search agents with citations
    if citations_match and analysis_match:
        citations = citations_match.group(1).strip()
        summary = analysis_match.group(1).strip()
        return summary, {
            "type": "documents",
            "data": {
                "content": summary,
                "citations": citations,
                "agent": agent_name,
            }
        }
    
    # No delimiters found — graceful fallback
    # This happens for pre-instrumentation agents or when LLM ignores format
    if agent_name in ("RunbookKBAgent", "HistoricalTicketAgent", "AzureAISearch"):
        return raw_output, {
            "type": "documents",
            "data": {"content": raw_output, "agent": agent_name}
        }
    
    # Graph/Telemetry agent didn't follow format — fall back to documents
    logger.warning("Agent %s did not emit structured delimiters — falling back to documents view", agent_name)
    return raw_output, {
        "type": "documents",
        "data": {"content": raw_output, "agent": agent_name}
    }
```

**Integration into `on_run_step` (completed tool_calls branch, line 242+):**

```python
# Replace the current response extraction block:
#   response = ""  
#   if tc_type == "connected_agent":
#       ...
#       if out: response = str(out)

# With:
response = ""
visualization = None
if tc_type == "connected_agent":
    ca = (
        tc.connected_agent
        if hasattr(tc, "connected_agent")
        else tc.get("connected_agent", {})
    )
    out = getattr(ca, "output", None) or ca.get("output", None)
    if out:
        response, visualization = self._parse_structured_output(agent_name, str(out))
        if not response:
            response = str(out)  # Fallback: use full output as response

# Then in the step_complete event:
event_data = {
    "step": self.ui_step,
    "agent": agent_name,
    "duration": duration,
    "query": query[:500] + "…" if len(query) > 500 else query,
    "response": response[:2000] + "…" if len(response) > 2000 else response,
}
if visualization:
    event_data["visualization"] = visualization

_put("step_start", {"step": self.ui_step, "agent": agent_name})
_put("step_complete", event_data)
```

> **⚠ Gotcha — `visualization.data` may be large (SSE payload size):**
> A GQL query returning 100 rows × 10 columns = ~50KB of JSON. The SSE spec has no payload size limit, and `EventSourceResponse` handles chunked transfer, so this is technically fine. However:
> - `fetchEventSource` on the frontend buffers the full message before calling `onmessage` — a 200KB payload won't cause errors but may briefly spike memory
> - The `JSON.parse()` call in `onmessage` handles large strings fine
> - Consider capping results at 200 rows in the parser (add note to viz data: `truncated: true`)

> **⚠ Gotcha — response truncation now operates on the ANALYSIS section:**
> The 2000-char truncation on `response` now applies to the summary/analysis text only (not the full raw output including structured data). This is correct — the `visualization` field carries the structured data separately and is NOT truncated. Verify that the truncated `response` still makes sense as standalone text.

> **⚠ Gotcha — thread-safety of `_parse_structured_output`:**
> This method runs in the background thread (daemon thread spawned for the agent run). It uses only function-local state and the module-level `json` / `re` imports, which are thread-safe. No issues expected, but avoid using `self.*` for temporary parsing state.

---

### Phase 2 — Frontend: Types & Data Layer

#### 2A. Extend `StepEvent` type

```ts
// types/index.ts
export type VisualizationType = 'graph' | 'table' | 'documents';

export interface VisualizationColumn {
    name: string;
    type: string;
}

export interface GraphVisualizationData {
    type: 'graph';
    columns: VisualizationColumn[];
    data: Record<string, unknown>[];   // NOTE: graph-query-api uses `data`, not `rows` (see BUG 3)
    query: string;
}

export interface TableVisualizationData {
    type: 'table';
    columns: VisualizationColumn[];
    rows: Record<string, unknown>[];
    query: string;
}

export interface DocumentVisualizationData {
    type: 'documents';
    content: string;
    agent: string;
}

export type VisualizationData =
    | GraphVisualizationData
    | TableVisualizationData
    | DocumentVisualizationData;

// Add visualization field to existing StepEvent
export interface StepEvent {
    step: number;
    agent: string;
    duration?: string;
    query?: string;
    response?: string;
    error?: boolean;
    visualization?: VisualizationData;  // ← NEW: populated by orchestrator parser
}

// Extend Interaction type — same field flows through save/restore
export interface Interaction {
    id: string;
    scenario: string;
    query: string;
    steps: StepEvent[];        // steps now carry visualization data
    diagnosis: string;
    run_meta: RunMeta | null;
    created_at: string;
}
```

> **⚠ Gotcha — backward compatibility with existing saved interactions:**
> The `visualization` field is optional (`?`). Interactions saved before this change have steps without `visualization`. All frontend code must null-check: `step.visualization?.type` — never assume it exists. TypeScript will enforce this if the type is correct, but watch out for `as` casts or `!` assertions that bypass the check.

> **⚠ Gotcha — `StepEvent` is used in TWO contexts:**
> 1. **Live SSE stream** — parsed from `step_complete` JSON in `useInvestigation.ts` (line 73: `data as StepEvent`)
> 2. **Restored interactions** — deserialized from Cosmos DB via `useInteractions.ts` → `Interaction.steps[]`
>
> Both paths must pass `visualization` through. For the SSE path, `JSON.parse(ev.data)` will naturally include the `visualization` field if present. For the restore path, the Cosmos DB document must include it (see Phase 5).

#### 2B. Visualization data hook (replaces `useQueryReplay`)

Renamed from `useQueryReplay` to `useVisualization` because the primary path is now **reading persisted data**, not replaying queries.

```ts
// hooks/useVisualization.ts
import { useState, useCallback } from 'react';
import type { StepEvent, VisualizationData } from '../types';

export function useVisualization() {
    const [loading, setLoading] = useState(false);
    const [data, setData] = useState<VisualizationData | null>(null);
    const [error, setError] = useState<string | null>(null);

    const getVisualization = useCallback(async (step: StepEvent): Promise<VisualizationData | null> => {
        // 1. Primary path: use persisted visualization data
        if (step.visualization) {
            setData(step.visualization);
            return step.visualization;
        }

        // 2. Fallback for AI Search agents: construct from response text
        if (['RunbookKBAgent', 'HistoricalTicketAgent', 'AzureAISearch'].includes(step.agent)) {
            const docViz: VisualizationData = {
                type: 'documents',
                content: step.response ?? '(no response captured)',
                agent: step.agent,
            };
            setData(docViz);
            return docViz;
        }

        // 3. Fallback for graph/telemetry: try replay if we have a plausible query
        //    This only works for post-Phase-1D interactions where visualization.data.query
        //    was captured. For pre-migration interactions, step.query is the NL instruction
        //    and replay will fail.
        //
        //    ⚠ Do NOT attempt replay if step.query looks like NL text —
        //    check for GQL/KQL syntax markers before calling.
        const query = step.visualization?.data?.query ?? step.query;
        if (!query || !looksLikeQuery(query)) {
            setError('Visualization data was not captured for this step. '
                   + 'Re-run the investigation to see structured results.');
            return null;
        }

        setLoading(true);
        setError(null);
        try {
            const res = await fetch('/query/replay', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ agent: step.agent, query }),
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const result = await res.json();
            setData(result);
            return result;
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load visualization');
            return null;
        } finally {
            setLoading(false);
        }
    }, []);

    const reset = useCallback(() => {
        setData(null);
        setError(null);
        setLoading(false);
    }, []);

    return { getVisualization, data, loading, error, reset };
}

// Heuristic: does this string look like GQL or KQL, not natural language?
function looksLikeQuery(s: string): boolean {
    // GQL markers
    if (/^\s*(MATCH|RETURN|WHERE|CREATE|MERGE|WITH)\b/i.test(s)) return true;
    // KQL markers
    if (/\|\s*(where|project|top|summarize|extend|join)\b/i.test(s)) return true;
    // Has pipe operators (KQL) or arrow patterns (GQL)
    if (/\|\s*\w+/.test(s) || /\(\w+\)-\[/.test(s)) return true;
    return false;
}
```

> **⚠ Gotcha — `looksLikeQuery()` is a heuristic, not a guarantee:**
> An NL instruction like *"Search for MATCH patterns in transport links"* would false-positive on the `MATCH` check. In practice, the orchestrator's delegation instructions don't start with GQL/KQL keywords, so this is unlikely. But add logging of replay attempts to catch false positives in production.

> **⚠ Gotcha — stale closure in modal:**
> The `getVisualization` callback captures `step` at render time. If the step data changes (unlikely but possible during live investigation), the modal could show stale data. Use a ref or re-fire on step change.

#### 2C. Agent-type resolver utility

```ts
// utils/agentType.ts
export function getVisualizationType(agent: string): VisualizationType {
    switch (agent) {
        case 'GraphExplorerAgent':
            return 'graph';
        case 'TelemetryAgent':
            return 'table';
        case 'RunbookKBAgent':
        case 'HistoricalTicketAgent':
        case 'AzureAISearch':
            return 'documents';
        default:
            return 'documents';
    }
}
```

---

### Phase 3 — Frontend: UI Components

#### 3A. Visualization button on StepCard

Add a small icon button to the **bottom-right** of each `StepCard`:

```
┌─────────────────────────────────────────────────────────┐
│ ● GraphExplorerAgent                           11.2s    │
│ ▸ Query: MATCH (l:TransportLink)...                     │
│ ▸ Response: MPLS-PATH-SYD-MEL-PRIMARY trav...           │
│                                                         │
│                                      [ ⬡ View Graph ]   │  ← visualization button
└─────────────────────────────────────────────────────────┘
```

**Button design — use a real `<button>`, not a div:**

```tsx
<button
  onClick={(e) => { e.stopPropagation(); openModal(); }}
  className="flex items-center gap-1.5 text-[10px] font-medium px-2.5 py-1
             rounded-md border border-brand/30 bg-brand/8
             text-brand hover:bg-brand/15 hover:border-brand/50
             focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-1
             transition-all group/viz"
  aria-label={`View ${vizLabel} for step ${step.step}`}
  title={tooltip}
>
  <span className="text-xs group-hover/viz:scale-110 transition-transform">{icon}</span>
  <span>{label}</span>
</button>
```

**Button labeling (not just icons — text + icon for clarity):**

| Agent | Icon | Label | Tooltip |
|-------|------|-------|---------|
| `GraphExplorerAgent` | `⬡` | View Graph | View graph query results |
| `TelemetryAgent` | `▤` | View Data | View telemetry data table |
| `RunbookKBAgent` | `▧` | View Docs | View runbook search results |
| `HistoricalTicketAgent` | `▧` | View Docs | View historical ticket results |

> **UX rationale:** Emoji icons (📊, 🔗, 📄) render inconsistently across OS/browsers and are not accessible. Use geometric Unicode symbols that render reliably in monospace/system fonts, paired with text labels so the button is self-explanatory without hovering.

**Button behavior:**
- `e.stopPropagation()` — prevents click from toggling StepCard expand/collapse
- Button is always visible in collapsed state (not gated behind expand)
- Uses `border-brand/30` + `bg-brand/8` to match the teal brand color system (no hard-coded colors)
- `focus-visible:ring-2 ring-brand` — keyboard-accessible focus ring matching global pattern
- Subtle `scale-110` on icon hover for micro-interaction feedback

**Accessibility:**
- Proper `<button>` element (not a div with onClick)
- `aria-label` includes agent type and step number for screen readers
- `title` for sighted tooltip on hover
- Keyboard navigable — Tab to reach, Enter/Space to activate

**Files to modify:**
- `components/StepCard.tsx` — add button in the card footer

#### 3B. Visualization Modal (`StepVisualizationModal.tsx`)

A **centered overlay modal** (not full-screen — leaves visual context of the investigation behind it):

```
┌──────────────────────────────────────────────────────────────┐
│  ⬡  GraphExplorerAgent — Query Results               [ ✕ ]  │
│─────────────────────────────────────────────────────────────│
│                                                             │
│              (type-specific content area)                    │
│                                                             │
│              - Graph canvas                                 │
│              - Data table                                   │
│              - Document list                                │
│                                                             │
│─────────────────────────────────────────────────────────────│
│  ▾ Query                                           [ Copy ] │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ MATCH (l:TransportLink) WHERE l.LinkId = '...'      │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│                                               [ Close ]     │
└──────────────────────────────────────────────────────────────┘
```

**Modal structure (3 zones):**

| Zone | Content | Styling |
|------|---------|--------|
| **Header bar** | Agent icon + name + title + close button | `glass-card-header` pattern — `bg-neutral-bg2 border-b border-border px-4 py-3` |
| **Content area** | Type-specific visualization (scrollable) | `flex-1 overflow-auto p-4`, min-height `300px` |
| **Footer** | Collapsible query preview + Copy + Close button | `border-t border-border-subtle px-4 py-3` |

**Modal behavior — matching existing `ServicesPanel` overlay pattern:**

```tsx
// Render as React Portal (createPortal to document.body)
<AnimatePresence>
  {isOpen && (
    <>
      {/* Backdrop — reuse existing glass-overlay class */}
      <motion.div
        className="glass-overlay fixed inset-0 z-40"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
        aria-hidden="true"
      />
      {/* Modal panel */}
      <motion.div
        className="fixed inset-0 z-50 flex items-center justify-center p-6"
        role="dialog"
        aria-modal="true"
        aria-label={`${agentName} query results`}
        initial={{ opacity: 0, scale: 0.95, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 10 }}
        transition={{ duration: 0.2, ease: 'easeOut' }}
      >
        <div className="glass-card w-full max-w-4xl max-h-[85vh] flex flex-col
                        shadow-2xl overflow-hidden">
          {/* header / content / footer */}
        </div>
      </motion.div>
    </>
  )}
</AnimatePresence>
```

**Interaction & accessibility (major improvement over existing ServicesPanel pattern):**

| Feature | Implementation |
|---------|---------------|
| **Escape to close** | `useEffect` with `keydown` listener for `Escape` |
| **Backdrop click** | `onClick` on backdrop overlay (separate from modal panel) |
| **Focus trap** | On open: focus moves to close button. Tab cycles within modal. On close: focus returns to the viz button that opened it. |
| **ARIA** | `role="dialog"`, `aria-modal="true"`, `aria-label` with agent name |
| **Close button** | `<button aria-label="Close">` — not just `✕` text |
| **Body scroll lock** | `document.body.style.overflow = 'hidden'` while modal is open |
| **Reduced motion** | Respect `prefers-reduced-motion` — skip scale/slide animation, use opacity-only |

**Loading state (GQL/KQL replay):**

```
┌──────────────────────────────────────────────────┐
│  ▤  TelemetryAgent — Query Results        [ ✕ ]  │
│──────────────────────────────────────────────────│
│                                                  │
│              ● ● ●                               │
│         Loading telemetry data...                │
│                                                  │
│──────────────────────────────────────────────────│
│  Query: AlertStream | where ...                  │
└──────────────────────────────────────────────────┘
```

- Reuse `ThinkingDots` component with a label ("Loading graph data..." / "Loading telemetry data...")
- Matches existing loading pattern from `DiagnosisPanel`

**Error state:**

```
┌──────────────────────────────────────────────────┐
│  ▤  TelemetryAgent — Query Results        [ ✕ ]  │
│──────────────────────────────────────────────────│
│                                                  │
│         ⚠ Could not load query results           │
│         Connection timed out                     │
│                                                  │
│                  [ Retry ]                        │
│                                                  │
└──────────────────────────────────────────────────┘
```

- Warning icon + error message + Retry button
- Retry button: `bg-neutral-bg3 border border-border hover:bg-neutral-bg4 text-xs rounded-md px-3 py-1.5`

**Files to create:**
- `components/visualization/StepVisualizationModal.tsx` — the modal wrapper
- `components/visualization/GraphResultView.tsx` — graph visualization content
- `components/visualization/TableResultView.tsx` — table content
- `components/visualization/DocumentResultView.tsx` — document list content

#### 3C. `GraphResultView` — Graph Visualization

Render GQL query results as an interactive force-directed graph.

**Approach:** Reuse the existing `react-force-graph-2d` pattern from `GraphCanvas`:

1. Parse the `columns` + `rows` response to extract nodes and edges.
   - Heuristic: rows with `source`/`target` fields → edges; otherwise → nodes.
   - Or: send the same query to `/query/topology` which returns pre-structured `{nodes, edges}`.
2. Render with a lightweight version of `ForceGraph2D` (same library already installed).
3. Node colors use the same palette from `graphConstants.ts`.
4. Tooltip on hover showing node properties.
5. No toolbar needed (simpler than the main topology viewer).

**Alternative (simpler):** If the GQL results are tabular (e.g., `RETURN r.RouterId, r.Hostname`), show them as a table with a "View as graph" toggle that calls `/query/topology` filtered to those entities.

#### 3D. `TableResultView` — Tabular Data

Render KQL query results as a clean, scannable data table.

**Visual design:**

```
┌──────────────────────────────────────────────────────────────────┐
│  Showing 20 of 20 results                          [ Export? ] │
├──────────┬───────────┬──────────────┬────────┬─────────────────┤
│ AlertId  │ Severity  │ Timestamp    │ Type   │ OpticalPower    │
│ ▾ sort   │           │ ▾ sort       │        │                 │
├──────────┼───────────┼──────────────┼────────┼─────────────────┤
│ A-0042   │ CRITICAL  │ 14:31:14     │ FIBRE… │ -40.0 dBm       │
│ A-0041   │ MAJOR     │ 14:30:00     │ OPTIC… │ -22.5 dBm       │
│ A-0040   │ WARNING   │ 14:28:45     │ HIGH_… │ -15.3 dBm       │
│ ...      │           │              │        │                 │
└──────────┴───────────┴──────────────┴────────┴─────────────────┘
```

**Implementation — pure HTML table with Tailwind (no extra dependencies):**

```tsx
<div className="overflow-x-auto rounded-lg border border-border">
  <table className="w-full text-xs text-left">
    <thead>
      <tr className="bg-neutral-bg2 border-b border-border">
        {columns.map(col => (
          <th key={col.name}
              className="px-3 py-2 text-[10px] font-medium uppercase tracking-wider
                         text-text-muted cursor-pointer hover:text-text-primary
                         select-none whitespace-nowrap"
              onClick={() => toggleSort(col.name)}
              aria-sort={sortState}>
            {col.name}
            {sortCol === col.name && <span className="ml-1">{sortDir === 'asc' ? '▴' : '▾'}</span>}
          </th>
        ))}
      </tr>
    </thead>
    <tbody>
      {rows.map((row, i) => (
        <tr key={i} className="border-b border-border-subtle last:border-0
                               hover:bg-brand/5 transition-colors">
          {columns.map(col => (
            <td key={col.name}
                className={`px-3 py-2 whitespace-nowrap ${isNumeric(col.type) ? 'font-mono tabular-nums' : ''}`}>
              {formatCell(row[col.name], col.type)}
            </td>
          ))}
        </tr>
      ))}
    </tbody>
  </table>
</div>
```

**UX details:**
- **Column headers:** `text-[10px] uppercase tracking-wider` — matches the label pattern used everywhere in the app
- **Sortable columns:** Click header to sort. `aria-sort` attribute for accessibility. Visual indicator (▴/▾).
- **Row hover:** `hover:bg-brand/5` — subtle teal highlight, consistent with brand color system
- **No zebra stripes** — the app uses a dark theme with subtle borders; zebra stripes add visual noise. Use `hover:bg-brand/5` instead for active row identification.
- **Monospace for numbers:** `font-mono tabular-nums` on numeric/timestamp columns so digits align vertically
- **Cell formatting:** Timestamps formatted as `HH:MM:SS`, numbers with appropriate precision, long strings truncated with `title` for full value on hover
- **Row count header:** `"Showing N of M results"` — if >100 rows, show first 100 with a `"Load more"` button
- **Horizontal scroll:** `overflow-x-auto` wrapper with rounded border — scrollbar styled via existing `::-webkit-scrollbar` globals
- **Empty state:** `"No data returned"` centered message if rows is empty

**Severity highlighting (optional but impactful for NOC context):**

| Severity | Cell treatment |
|----------|---------------|
| `CRITICAL` | `text-status-error font-medium` |
| `MAJOR` | `text-status-warning` |
| `WARNING` | `text-yellow-400` |
| `MINOR` | `text-text-secondary` |

This uses the existing `status-*` design tokens, not hard-coded colors.

#### 3E. `DocumentResultView` — Document List

Render AI Search results (RunbookKB / HistoricalTicket) as a formatted knowledge panel.

**Visual design:**

```
┌──────────────────────────────────────────────────────────────┐
│  ┌──────────────────────────────────────────────────────┐    │
│  │ ▧ RunbookKBAgent                                    │    │
│  │   Operational Runbook Results                       │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                             │
│  The fibre cut recovery procedure involves the following    │
│  steps:                                                     │
│                                                             │
│  1. **Verify the outage scope** — Confirm which links       │
│     are affected using the topology graph...                │
│                                                             │
│  2. **Initiate traffic reroute** — Activate backup MPLS     │
│     paths if available...                                   │
│                                                             │
│  > **Escalation:** If no backup path exists, escalate       │
│  > to Tier-3 within 15 minutes per SLA policy.              │
│                                                             │
└──────────────────────────────────────────────────────────────┘
```

**Implementation:**
- Render `step.response` as rich Markdown via `ReactMarkdown` — reuse the existing `prose prose-sm` setup from `StepCard`
- Agent badge at top: icon + agent name + descriptive subtitle
- `max-w-prose` (65ch) container for comfortable reading width within the modal
- Markdown rendered at `text-sm` (14px) — **larger than StepCard's `text-xs`** since the modal has more space and the content deserves more comfortable reading

**Agent-specific treatment:**

| Agent | Badge subtitle | Badge color |
|-------|---------------|-------------|
| `RunbookKBAgent` | Operational Runbook Results | `border-blue-500/20 bg-blue-500/5 text-blue-300` |
| `HistoricalTicketAgent` | Historical Incident Records | `border-amber-500/20 bg-amber-500/5 text-amber-300` |

> **UX note:** These badge colors (blue/amber) complement the existing palette without conflicting with brand teal, status green/red, or the purple used for Orchestrator Thoughts (Story 2). They serve as semantic hints: blue = reference material, amber = historical.

This is the simplest visualization — essentially the expanded StepCard response content displayed at comfortable reading scale in a larger container.

---

### Phase 4 — Styling & Polish

#### 4A. Design tokens — use ONLY theme tokens, no hard-coded colors

The existing codebase has some hard-coded colors (e.g., `purple-800`, `bg-red-500/5` in StepCard). New components must use **only** the established design token system:

| Element | Token | Rationale |
|---------|-------|-----------|
| Modal backdrop | `glass-overlay` (existing utility) | Already defined as `bg-black/40 backdrop-blur-sm` |
| Modal panel | `glass-card` (existing utility) | `bg-neutral-bg1 border border-border rounded-xl shadow-sm` |
| Modal header | `bg-neutral-bg2 border-b border-border` | Matches Header and tab-bar patterns |
| Button primary accent | `border-brand/30 bg-brand/8 text-brand` | Brand teal at low opacity |
| Table borders | `border-border` / `border-border-subtle` | Existing tokens |
| Table header bg | `bg-neutral-bg2` | Consistent with header surfaces |
| Table row hover | `hover:bg-brand/5` | Extremely subtle brand tint |
| Text hierarchy | `text-text-primary` / `text-text-secondary` / `text-text-muted` | Existing 3-tier text system |
| Focus rings | `focus-visible:ring-2 ring-brand ring-offset-2` | Matches global `*:focus-visible` rule |
| Error states | `text-status-error` / `bg-status-error/10` | Existing status tokens |
| Agent badge colors | Defined per-agent (see 3E) | Complementary to palette |

#### 4B. Responsive behavior

| Viewport | Modal sizing | Content adaptation |
|----------|--------------|-----------|
| Desktop (≥1024px) | `max-w-4xl` (896px) × `max-h-[85vh]` | Full table/graph |
| Tablet (768–1023px) | `max-w-2xl` × `max-h-[85vh]` | Table scrolls horizontally |
| Narrow (<768px) | `max-w-full mx-4` × `max-h-[90vh]` | Graph zooms to fit, table stacks columns |

- Close button always visible (top-right of header, not absolute-positioned over content)
- Graph canvas uses `ResizeObserver` to fill available space (same pattern as `GraphTopologyViewer`)
- Table uses `overflow-x-auto` with visible scrollbar (styled via existing scrollbar globals)

#### 4C. Animation — respect user preferences

```tsx
const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

// Modal transitions
const modalVariants = prefersReducedMotion
  ? { initial: { opacity: 0 }, animate: { opacity: 1 }, exit: { opacity: 0 } }
  : { initial: { opacity: 0, scale: 0.95, y: 10 },
      animate: { opacity: 1, scale: 1, y: 0 },
      exit: { opacity: 0, scale: 0.95, y: 10 } };
```

| Element | Default | Reduced motion |
|---------|---------|----------------|
| Modal enter | `opacity + scale(0.95→1) + y(10→0)`, 200ms | `opacity` only, 150ms |
| Modal exit | reverse of enter | `opacity` only |
| Viz button hover | `scale(1.05)` on icon | no transform |
| Table sort | instant (no animation) | — |

#### 4D. Keyboard navigation

| Key | Context | Action |
|-----|---------|--------|
| `Tab` | StepCard | Reaches viz button (natural tab order) |
| `Enter` / `Space` | Viz button focused | Opens modal |
| `Escape` | Modal open | Closes modal |
| `Tab` | Inside modal | Cycles through: close button → content → query copy → close footer button |
| `Shift+Tab` | Inside modal | Reverse cycle |
| `Arrow ↑/↓` | Table focused | Navigate rows (optional, stretch goal) |

**Focus management:**
1. On open: focus moves to modal close button
2. Focus is trapped within modal (Tab wraps around)
3. On close: focus returns to the viz button that triggered the modal

Use a lightweight focus-trap (or implement manually with `querySelectorAll('[tabindex], button, a')`).

#### 4E. Light theme compatibility

The app supports light/dark themes via `.dark` class toggle. All proposed styling uses CSS custom properties that automatically adapt. Verify:
- `glass-overlay` backdrop is visible on light backgrounds
- Table header `bg-neutral-bg2` has sufficient contrast in light mode
- Brand-tinted hover (`bg-brand/5`) is visible on white backgrounds
- Focus rings have correct `ring-offset` color (uses `--color-bg-1`)

---

### Phase 5 — Interaction Persistence (Save & Restore Visualization Data)

This phase ensures that visualization data captured during a live investigation is **persisted** alongside the interaction in Cosmos DB, and can be **restored and redisplayed** when loading a past interaction from the sidebar.

#### 5A. Backend: Extend InteractionStep model

Add the optional `visualization` field to the Pydantic model in `graph-query-api/models.py`:

```python
from typing import Any

class InteractionStep(BaseModel):
    step: int
    agent: str
    duration: str | None = None
    query: str | None = None
    response: str | None = None
    error: bool = False
    visualization: dict[str, Any] | None = None   # ← NEW
```

> **Design choice — `dict[str, Any]` not a typed model:**
> Using a loose `dict` type instead of a strict Pydantic model for `visualization` is intentional:
> 1. The visualization payload shape varies by type (`graph` vs `table` vs `documents`)
> 2. It avoids tight coupling between the API layer and the orchestrator's output format
> 3. Cosmos DB stores it as a nested JSON object — no schema needed
> 4. Frontend TypeScript types provide the real contract

#### 5B. Cosmos DB document size considerations

**Cosmos DB limit: 2 MB per document.** (Technically 2,097,152 bytes after UTF-8 encoding including system properties.)

An interaction document today is roughly:
- `query` (alert text): ~200 bytes
- `steps` (5 steps × ~3KB): ~15 KB
- `diagnosis`: ~2-5 KB
- `run_meta` + metadata: ~500 bytes
- **Total today: ~20 KB**

With visualization data:
- Graph results (50 rows × 8 cols): ~20 KB
- Telemetry results (100 rows × 6 cols): ~30 KB
- Documents (response text): ~2-5 KB
- **Per step: 2-30 KB** → 5 steps: ~10-150 KB
- **Total with viz: ~30-170 KB**

This is well within the 2 MB limit. However, edge cases to watch:

| Scenario | Estimated doc size | Risk |
|----------|-------------------|------|
| Normal (5 steps, moderate results) | ~50-80 KB | ✅ Safe |
| Heavy (8 steps, 200+ rows per step) | ~300-500 KB | ✅ Safe but large |
| Extreme (10 steps, 1000+ rows each) | ~1-2 MB | ⚠ Approaching limit |

> **⚠ Gotcha — cap visualization data before persistence:**
> Add a safety check in the `save_interaction` endpoint: if the total serialized document exceeds 1.5 MB, truncate `visualization.data.rows`/`visualization.data.data` to the first 200 rows per step and set `visualization.data.truncated = true`. Log a warning.

> **⚠ Gotcha — Cosmos DB indexing on large nested objects:**
> By default, Cosmos DB indexes all paths in a document. Large `visualization.data` arrays will increase RU consumption on writes. Consider excluding `/steps/*/visualization/*` from the indexing policy:
> ```json
> {
>   "indexingPolicy": {
>     "excludedPaths": [
>       { "path": "/steps/*/visualization/*" }
>     ]
>   }
> }
> ```
> This is a Cosmos DB container-level setting. Update it via the Azure portal or Bicep/infra code.

#### 5C. Backend: Save endpoint changes

The existing `POST /query/interactions` endpoint (`router_interactions.py` line 78) already serializes steps via `s.model_dump()`. Since `model_dump()` includes all fields (including optional ones that are `None`), this works automatically — no code change needed for the save path.

However, verify:

```python
# router_interactions.py — save_interaction
doc = {
    "id": str(uuid.uuid4()),
    "scenario": req.scenario,
    "query": req.query,
    "steps": [s.model_dump() for s in req.steps],  # ← visualization included if present
    "diagnosis": req.diagnosis,
    "run_meta": req.run_meta.model_dump() if req.run_meta else None,
    "created_at": datetime.now(timezone.utc).isoformat(),
}
```

`model_dump()` on an `InteractionStep` with `visualization={"type": "graph", "data": {...}}` will produce:
```json
{
    "step": 1,
    "agent": "GraphExplorerAgent",
    "duration": "11.2s",
    "query": "(NL instruction, truncated)",
    "response": "The link LINK-SYD-MEL...",
    "error": false,
    "visualization": {
        "type": "graph",
        "data": {
            "columns": [...],
            "data": [...],
            "query": "MATCH (l:TransportLink)..."
        }
    }
}
```

This is correct. The `None` case (pre-migration steps) will produce `"visualization": null`.

> **⚠ Gotcha — `model_dump()` includes `None` fields by default:**
> In Pydantic v2, `model_dump()` includes fields with `None` values. This means pre-migration steps get `"visualization": null` in the JSON. This is fine — Cosmos DB handles null values, and the frontend's `step.visualization?.type` check handles it. But if you want to exclude nulls to save space, use `model_dump(exclude_none=True)`. Be careful: this would also exclude other `None` fields like `query` and `duration`, which may break frontend expectations.
>
> **Recommendation:** Keep `model_dump()` as-is (include nulls). The space cost is negligible.

#### 5D. Backend: Fetch endpoint changes

The `GET /query/interactions` endpoint returns items directly from Cosmos DB via `store.list()`. Since Cosmos DB stores the full document including nested `visualization` objects, no change is needed — the visualization data flows through automatically.

#### 5E. Frontend: Save path changes

The frontend's `saveInteraction` in `useInteractions.ts` (line 26) sends `steps: StepEvent[]` directly to the backend. Since `StepEvent` now includes `visualization?`, this field will be serialized into the POST body automatically — **no code change needed**.

Verify the data flow:
1. SSE `step_complete` event includes `visualization` → parsed as `StepEvent` in `useInvestigation.ts`
2. `steps` state accumulates `StepEvent[]` (with `visualization`) → passed to `saveInteraction()`
3. `saveInteraction()` JSON-serializes and POSTs → backend receives `InteractionStep` with `visualization`
4. Backend stores to Cosmos DB → visualization data persisted

> **⚠ Gotcha — `steps` state reference in auto-save:**
> The auto-save in `App.tsx` (line 80) uses `latestValuesRef.current.steps` to capture the step data. This ref is updated on every render via:
> ```tsx
> useEffect(() => {
>     latestValuesRef.current = { alert, steps, runMeta };
> });
> ```
> Since `steps` is an array of `StepEvent` objects (which include `visualization`), the ref captures the live data correctly. No change needed.

> **⚠ Gotcha — serialization of visualization data:**
> `JSON.stringify()` (called by `fetch` in `saveInteraction`) will serialize the nested `visualization` object correctly. However, if any `visualization.data` values contain:
> - `undefined` (stripped by JSON.stringify — fine)
> - `BigInt` (throws TypeError — unlikely but watch for KQL integer values)
> - Circular references (throws TypeError — shouldn't happen with our data shapes)
> - `Date` objects (serialized as strings — fine)
>
> Test with real investigation data to verify clean serialization.

#### 5F. Frontend: Restore path changes

When a user clicks a past interaction in `InteractionSidebar`, `setViewingInteraction(i)` sets the interaction. Then `App.tsx` (line 94) does:

```tsx
const displaySteps = viewingInteraction?.steps ?? steps;
```

Since `viewingInteraction.steps` now includes `visualization` data (loaded from Cosmos DB), the `StepCard` components receive `StepEvent` objects with visualization. The viz button reads `step.visualization` — **this works automatically, no change needed**.

Verify the full restore chain:
1. Sidebar click → `setViewingInteraction(interaction)` where `interaction.steps[].visualization` exists
2. `displaySteps` = `viewingInteraction.steps` → passed to `InvestigationPanel` → `AgentTimeline` → `StepCard`
3. `StepCard` renders viz button → user clicks → `useVisualization().getVisualization(step)` → reads `step.visualization` directly
4. No API call needed — data is already in memory

> **⚠ Gotcha — interaction sidebar list items don't load full data:**
> Verify that `GET /query/interactions?scenario=...&limit=50` returns the full `steps[].visualization` data. If the Cosmos DB query uses `SELECT *`, it does. But if there's a projection (`SELECT c.id, c.query, ...`), visualization data would be missing.
>
> Current code: `"SELECT * FROM c"` in `router_interactions.py` line 62 → full documents returned → ✅ safe.
>
> **However**, loading 50 interactions with full visualization data could be 50 × 50KB = 2.5 MB of JSON. This may cause:
> - Slow initial load on poor connections
> - Memory pressure on mobile devices
>
> **Mitigation options (implement if measured performance is poor):**
> 1. **Lazy load visualization**: `GET /query/interactions` returns steps without visualization. When user clicks an interaction, fire `GET /query/interactions/{id}?scenario=...` which returns the full document including visualization. (This endpoint already exists in `router_interactions.py` line 96.)
> 2. **Cosmos DB projection**: Use `SELECT c.id, c.scenario, c.query, c.diagnosis, c.run_meta, c.created_at` for the list endpoint, omitting `c.steps` entirely. Load steps+visualization only on detail fetch.
>
> **Recommendation for v1:** Ship with full `SELECT *` (current behavior). Optimize later if users report slow sidebar loads with many interactions.

#### 5G. Migration strategy for existing interactions

Existing interactions in Cosmos DB have `steps[].visualization = undefined` (field absent). After deploying Phase 1D + Phase 5:

- **New investigations**: Automatically get `visualization` data via the orchestrator parser
- **Existing interactions**: Steps have no `visualization` field. The viz button should handle this gracefully:

```tsx
// In StepCard or viz button logic:
const hasVisualization = !!step.visualization;
const canReplay = ['GraphExplorerAgent', 'TelemetryAgent'].includes(step.agent)
    && step.visualization?.data?.query;  // Only true for post-migration steps
const isDocAgent = ['RunbookKBAgent', 'HistoricalTicketAgent', 'AzureAISearch'].includes(step.agent);

// Show viz button only if we have data to show
const showVizButton = hasVisualization || isDocAgent;

// For doc agents, we can always show the response text
// For graph/telemetry without viz data, don't show the button (no data to display)
```

> **⚠ Gotcha — don't show viz button with no data behind it:**
> If the button opens a modal that says "no data available", it's a bad UX. Better to hide the button entirely for pre-migration graph/telemetry steps. For doc agents, the response text is always available (even truncated at 2000 chars), so the button can always show.
>
> **Exception:** If the response text was also empty or very short (error case), hide the button for ALL agent types.

---

## Implementation Order

```
Phase 1D  →  Phase 1A  →  Phase 2A  →  Phase 5A      (data capture + types + model — foundation)
                                ↓
                         Phase 5B-5G                    (persistence — must work before UI)
                                ↓
                         Phase 3B  →  Phase 3E          (documents — simplest end-to-end viz)
                                ↓
          Phase 1C  →  Phase 2B  →  Phase 3D            (tables — medium complexity)
                                       ↓
                                  Phase 3C              (graph — most complex)
                                       ↓
                                  Phase 3A              (button on StepCard — wire it all together)
                                       ↓
                                  Phase 4               (polish)
```

**Key change from original:** Phase 1D (sub-agent instrumentation) and Phase 5 (persistence) must come FIRST — before any frontend visualization work. Without data capture and persistence, the viz components would have nothing to display for restored interactions.

**Suggested sprint breakdown:**

| Sprint | Scope | Effort |
|--------|-------|--------|
| **S0** | Sub-agent prompt changes (1D-i, 1D-ii) + orchestrator parser (1D-iii) + test with real investigation | ~3 hrs |
| **S1** | Backend model changes (5A) + frontend types (2A) + verify save/restore roundtrip (5C-5F) | ~2 hrs |
| **S2** | Types + DocumentResultView + Modal shell + StepCard button (documents only) | ~3 hrs |
| **S3** | `/query/replay` fallback endpoint (1C) + `useVisualization` hook (2B) + TableResultView | ~3 hrs |
| **S4** | GraphResultView (reuse `react-force-graph-2d`) | ~3 hrs |
| **S5** | Polish: animations, responsive, error states, migration graceful degradation (5G) | ~2 hrs |

**Total estimated effort: ~16 hours** (was ~11 hrs before persistence scope)

---

## Files Changed / Created

### New files

| File | Purpose |
|------|---------|
| `frontend/src/components/visualization/StepVisualizationModal.tsx` | Modal overlay wrapper |
| `frontend/src/components/visualization/GraphResultView.tsx` | Graph visualization panel |
| `frontend/src/components/visualization/TableResultView.tsx` | Tabular data panel |
| `frontend/src/components/visualization/DocumentResultView.tsx` | Document list panel |
| `frontend/src/hooks/useVisualization.ts` | Visualization data hook (reads persisted data, falls back to replay) |
| `frontend/src/utils/agentType.ts` | Agent name → visualization type resolver |
| `graph-query-api/router_replay.py` | Query replay endpoint (on graph-query-api, NOT main API — see BUG 8) |

### Modified files

| File | Change |
|------|--------|
| `frontend/src/types/index.ts` | Add `VisualizationData` types |
| `frontend/src/components/StepCard.tsx` | Add visualization button (bottom-right) |
| `graph-query-api/main.py` | Register replay router |
| `graph-query-api/models.py` | Add `ReplayRequest` model; add `visualization` field to `InteractionStep`; add `reasoning` field (for Story 2 compatibility) |
| `api/app/orchestrator.py` | Add `_parse_structured_output()` method (Phase 1D-iii); fix `_extract_arguments()` to unwrap JSON dict (BUG 1) |
| `data/scenarios/telecom-playground/data/prompts/graph_explorer/core_instructions.md` | Append `## Response Format` section with `---QUERY---`/`---RESULTS---`/`---ANALYSIS---` delimiters |
| `data/scenarios/telecom-playground/data/prompts/foundry_telemetry_agent_v2.md` | Append `## Response Format` section with `---QUERY---`/`---RESULTS---`/`---ANALYSIS---` delimiters |
| `data/scenarios/telecom-playground/data/prompts/foundry_runbook_kb_agent.md` | Append `## Response Format` section with `---CITATIONS---`/`---ANALYSIS---` delimiters |
| `data/scenarios/telecom-playground/data/prompts/foundry_historical_ticket_agent.md` | Append `## Response Format` section with `---CITATIONS---`/`---ANALYSIS---` delimiters |

---

## Risks & Mitigations

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| **LLM doesn't follow structured output format** | High | Sub-agent may ignore `---QUERY---`/`---RESULTS---` delimiters or truncate raw JSON. Parser falls back to `type: "documents"` (shows response as markdown). Add strict prompting + test with varied queries. Monitor fallback rate in logs. |
| **Sub-agent truncates large result sets in output** | Medium | LLMs may compress/omit rows when output exceeds context window. Cap visualization at 200 rows and set `truncated: true`. Show `"Showing 200 of N results"` in modal. |
| **Increased token consumption** | Medium | Echoing raw tool results adds ~500-2000 output tokens per sub-agent step. For 5-step investigations: +2500-10000 tokens. Monitor costs; add prompt flag to make echo opt-in if needed. |
| **Cosmos DB document size approaching 2 MB** | Low | Truncate `visualization.data` rows to 200 per step before saving. Log warning if doc exceeds 1.5 MB. Extreme case (10 steps × 1000 rows) is unlikely in practice. |
| **Cosmos DB write RU spike from large nested objects** | Low | Exclude `/steps/*/visualization/*` from indexing policy to avoid RU increase on writes. |
| **Sidebar loads 50 interactions with full viz data (>2.5 MB)** | Medium | v1: accept it. v2: lazy-load viz data via `GET /query/interactions/{id}` on click. Or use Cosmos DB projection to exclude `steps` from list endpoint. |
| **Pre-migration interactions show broken viz button** | Medium | Hide viz button for graph/telemetry steps without `visualization` data. Show it only for doc agents (can always render `step.response`). |
| **Query replay (fallback) returns different results** | Low | Show disclaimer `"Results may differ from original investigation"` in modal footer. Only used for pre-migration interactions or parser failures. |
| **`step.query` NL instruction accidentally sent to replay endpoint** | High | `looksLikeQuery()` heuristic in `useVisualization` guards against this. Never replay unless string matches GQL/KQL syntax patterns. Log replay attempts for monitoring. |
| GQL results are not graph-shaped (e.g., aggregations) | Medium | Fall back to table view when results don't contain identifiable nodes/edges. Show a `"Displaying as table — results are not graph-shaped"` info banner. |
| AI Search agents don't have structured results | None | Handled — render `step.response` as markdown. Citation metadata is best-effort (LLM may not list all sources). |
| `react-force-graph-2d` bundle size increase | Low | Already bundled in the app for `GraphTopologyViewer`. |
| Modal opens on mobile / narrow viewport | Low | Modal goes near-full-width with `mx-4` margin; content adapts (table scrolls, graph zooms to fit). |
| User clicks viz button during live investigation | Low | Button works fine — visualization data is already in the `StepEvent` object. No API call needed for post-1D steps. |
| Color-blind users can't distinguish row highlights | Low | Severity text labels accompany colors; hover highlight is structural (no color-only meaning). |
| **`model_dump()` serializes `None` as `null` in JSON** | Low | Acceptable. Cosmos DB handles null. Frontend null-checks via `?.` operator. Don't use `exclude_none=True` (breaks other optional fields). |

---

## Implementation Bugs & Gotchas (Audit)

These are verified issues found by reading the actual source code. Each MUST be addressed during implementation.

### BUG 1: `step.query` is JSON-wrapped, not a raw query string

**Where:** `orchestrator.py` → `_extract_arguments()` (line ~170)

`_extract_arguments()` parses `connected_agent.arguments` as JSON and returns it as a string. If the sub-agent receives arguments like `{"query": "Search for transport links..."}`, the function returns the full JSON dict as a string — not just the value. This means `step.query` in the SSE event is something like `'{"query": "Search for transport links related to LINK-SYD-MEL-FIBRE-01"}'` instead of `'Search for transport links related to LINK-SYD-MEL-FIBRE-01'`.

**Impact:**
- The StepCard preview shows the JSON wrapper — ugly.
- The replay endpoint receives JSON, not a bare query — must parse.
- The modal footer shows the full JSON wrapper.

**Fix options:**
1. **(Recommended)** Change `_extract_arguments()` to unwrap: if the parsed dict has a single `"query"` or `"input"` key, return that value instead of the full JSON.
2. Parse on the frontend when displaying / replaying.
3. Parse in the replay endpoint only (handled in 1C above).

**Note:** Changing `_extract_arguments()` also changes what gets saved in persisted `Interaction.steps[].query`. Old interactions would have the JSON-wrapped version. Handle gracefully.

### BUG 2: `InteractionStep` Pydantic model drops extra fields

**Where:** `graph-query-api/models.py` → `InteractionStep`

The current model:
```python
class InteractionStep(BaseModel):
    step: int; agent: str; duration: str | None = None; query: str | None = None
    response: str | None = None; error: bool = False
```

Pydantic v2 default `extra` is `"ignore"` — extra fields are **silently dropped**. If Story 2 adds `reasoning` to `StepEvent` on the frontend, and the user finishes an investigation, the `reasoning` field will be lost when saved via `POST /query/interactions`. When loading that interaction from the sidebar, `step.reasoning` will be `undefined`.

**Fix:** Add `reasoning: str | None = None` to `InteractionStep`.

### BUG 3: Graph query response uses `data`, not `rows`

**Where:** `graph-query-api/models.py` → `GraphQueryResponse`

```python
class GraphQueryResponse(BaseModel):
    columns: list[dict] = []
    data: list[dict] = []          # ← "data", not "rows"

class TelemetryQueryResponse(BaseModel):
    columns: list[dict] = []
    rows: list[dict] = []          # ← "rows", not "data"
```

The Story 1 types now define `GraphVisualizationData.data` to match the API (fixed in this audit). `TableVisualizationData` uses `rows` which matches `TelemetryQueryResponse.rows`. The frontend must handle both field names defensively.

**Fix:** ~~Either:~~
1. ~~Normalize in the replay endpoint / hook: map `response.data` → `rows` for graph results.~~
2. ~~Or use `data` in the `GraphVisualizationData` type to match the API.~~

**RESOLVED:** Option 2 applied — `GraphVisualizationData` now uses `data` to match the API. The Section 1A payload shape and Phase 2A TypeScript types have been updated. Frontend graph visualization components must access `vizData.data` (not `vizData.rows`) for graph results.

### BUG 4: `columns` type is `list[dict]`, not `VisualizationColumn[]`

**Where:** `graph-query-api/models.py`

The API declares `columns: list[dict]` — untyped dicts. The frontend type `VisualizationColumn` expects `{ name: string, type: string }`. The actual shape depends on the Fabric GQL / KQL backend.

**Fix:** Verify the actual column dict shape by running a test query, then either:
1. Validate/transform in the replay endpoint.
2. Make the frontend defensive: `col.name ?? col.column_name ?? 'Unknown'`.

### BUG 5: No error HTTP status codes from graph-query-api

**Where:** `router_graph.py`, `router_telemetry.py`

Both endpoints catch all exceptions and return **HTTP 200** with an `error` string field. The frontend `useVisualization` hook must NOT check `response.ok` alone — it must also check `result.error`.

```ts
// Wrong:
if (!response.ok) { setError('Failed'); return; }

// Correct:
const result = await response.json();
if (result.error) { setError(result.error); return; }
```

### BUG 6: No pagination on graph/telemetry query results

**Where:** `router_graph.py`, `router_telemetry.py`

Neither endpoint has pagination or max-row limits. A KQL query like `AlertStream | where SourceNodeId == 'X'` could return thousands of rows. The frontend table would try to render all of them.

**Fix:** Slice client-side: `rows.slice(0, 100)` with a "Showing 100 of N results" header. Or add a `limit` parameter to the replay endpoint.

### BUG 7: `createPortal` not currently imported anywhere

**Where:** Frontend — the modal plan uses `createPortal` but it's never been used in the codebase.

**Fix:** Add `import { createPortal } from 'react-dom'` in `StepVisualizationModal.tsx`. This is a minor import, not a missing dependency — `react-dom` is already in `package.json`.

### BUG 8: Replay endpoint must live on graph-query-api, not main API

**Where:** Architecture

The plan says to add `api/app/routers/replay.py` on the main API (port 8000). But the graph/telemetry backends are only accessible from the graph-query-api (port 8100). Nginx routes `/query/*` → 8100 and `/api/*` → 8000. If replay is on the main API, it would need to make an HTTP call to `http://127.0.0.1:8100/query/graph`, adding latency.

**Fix:** Add `router_replay.py` to `graph-query-api/` instead. Route: `POST /query/replay`. Nginx handles routing automatically.

### BUG 9: `step.query` truncated to 500 chars may break replay

**Where:** `orchestrator.py` line ~243 (in the `completed` tool_calls branch)

```python
if len(query) > 500:
    query = query[:500] + "…"
```

If a GQL/KQL query is >500 chars, it gets truncated with `…`. The replay endpoint receives a broken query that will fail.

**Fix:** Either:
1. **(Recommended)** Store the full query in a separate field (`full_query`) and only truncate for display (`query`).
2. Increase the limit to 2000+ chars.
3. Don't truncate at all — the frontend already uses `truncate` CSS.

Option 1 is safest because it doesn't change the existing SSE payload size for non-visualization use.

### BUG 10: Retry loop emits duplicate step numbers

**Where:** `orchestrator.py` retry logic

Each retry creates a new `SSEEventHandler()` with `ui_step = 0`. If attempt 1 emits steps 1-3 and then fails, attempt 2 starts at step 1 again. The frontend `steps.map(s => <StepCard key={s.step}>)` uses `s.step` as React key — duplicate keys cause rendering bugs.

**Impact on Story 1:** The viz button uses `step.step` in its `aria-label`. Duplicate step numbers would confuse screen readers.

**Fix:** Pass the running step counter across retries, or use a globally unique key (UUID or running counter outside the handler).

### BUG 11: `"AzureAISearch"` agent name won't appear in practice

**Where:** `orchestrator.py` → `_resolve_agent_name()`, frontend agent-type checks

`_resolve_agent_name()` has a branch for `tc_type == "azure_ai_search"` that returns `"AzureAISearch"`. However, the orchestrator is provisioned exclusively with `ConnectedAgentTool` for all 4 sub-agents (see `agent_provisioner.py` → `provision_all()`). It does NOT have an `AzureAISearchTool` attached directly. Therefore, tool calls from the orchestrator's perspective are always type `connected_agent`, and the agent name comes from `ca.name` (e.g., `"RunbookKBAgent"`, `"HistoricalTicketAgent"`).

The `"AzureAISearch"` branch is defensive code for a scenario that doesn't occur in the current architecture.

**Impact on Story 1:** The plan's `getVisualizationType()`, `useVisualization()`, and migration logic (`5G`) all check for `"AzureAISearch"` as a possible agent name. These checks are harmless but dead code — they will never match. Including them is fine for forward-compatibility, but developers should not expect this path to be exercised.

**Fix:** No breaking change needed. Add a code comment noting this is defensive/forward-looking. Don't rely on it for testing.

### BUG 12: `useVisualization` replay doesn't handle graph-query-api's error-in-200 pattern

**Where:** `hooks/useVisualization.ts` → replay fallback path

The `useVisualization` hook's replay path (Phase 2B) checks `if (!res.ok) throw new Error(...)`. But as noted in BUG 5, graph-query-api returns **HTTP 200 with an `error` field** in the response body, not HTTP error codes. The hook would treat a failed query as success and try to display the error string as visualization data.

**Fix:** After `const result = await res.json()`, check `if (result.error) { setError(result.error); return null; }` before setting data. This is noted in BUG 5's description but the `useVisualization` code in Phase 2B doesn't implement it.

### BUG 13: `_extract_arguments()` only extracts for `connected_agent` — no query displayed for `azure_ai_search` steps

**Where:** `orchestrator.py` → `_extract_arguments()` (line ~175)

The method returns `""` for any `tc_type != "connected_agent"`. If the `"AzureAISearch"` code path in `_resolve_agent_name` is ever triggered (BUG 11), the corresponding `step.query` would be empty. The StepCard would show no query preview and the viz button's modal footer would have nothing to display.

**Impact:** Low (defensive scenario). No fix needed unless the architecture changes.

---

## Open Questions

1. **Should the graph visualization for GQL use `/query/topology` (nodes/edges structure) or `/query/graph` (tabular results)?**
   - `/query/topology` gives us pre-structured nodes/edges — better for graph viz but requires a second call that may return a different scope.
   - `/query/graph` returns the exact query results but in tabular form — we'd need to parse/infer the graph structure.
   - **Recommendation:** Use `/query/graph` and render as table by default; add a "View as topology" toggle that calls `/query/topology` with a scope filter.

2. ~~**Should we increase the `step.query` truncation limit?**~~
   - **RESOLVED:** No. `step.query` contains the orchestrator's NL instruction, not the actual GQL/KQL query. The actual query is captured in `visualization.data.query` (untruncated) via Phase 1D. The 500-char truncation is acceptable for StepCard preview only. See Phase 1D-iii for details.

3. ~~**Should past interactions (loaded from sidebar) support visualization?**~~
   - **RESOLVED: Yes.** Phase 5 addresses this completely. Visualization data is persisted in Cosmos DB and restored when loading past interactions. Pre-migration interactions degrade gracefully (viz button hidden for graph/telemetry, doc agents render `step.response`). See Phases 5A-5G.

4. **Modal vs. side panel vs. inline expansion?**
   - Modal recommended for maximum visualization space without disrupting the investigation flow.
   - Could later add a "pop out to side panel" option.

5. **Should the sub-agent prompt instrumentation be optional/togglable?**
   - The structured output format adds token overhead. If cost becomes a concern, we could make it opt-in via a prompt variable (e.g., include the format instructions only when the orchestrator's delegation message contains `[CAPTURE_RESULTS]`).
   - For v1, always-on is simpler and ensures consistent data capture.
   - **Recommendation:** Always-on for v1. Re-evaluate after measuring token cost increase over ~50 investigations.

6. **How to handle sub-agent retries within the orchestrator?**
   - If the orchestrator retries after a failed run (uses `MAX_RUN_ATTEMPTS = 2`), the second attempt's sub-agents will produce new structured output. The `ui_step` counter is NOT reset between attempts (`total_steps += handler.ui_step`), so steps from both attempts accumulate.
   - **Risk:** Steps from the failed attempt may have `visualization` data for a query that ultimately failed. The modal would show outdated/wrong data.
   - **Mitigation:** Mark steps from failed attempts with `error: true` (already done). Don't show viz button on error steps.

7. **What if a sub-agent makes multiple tool calls in one run?**
   - A sub-agent (e.g., GraphExplorerAgent) might call `/query/graph` multiple times before producing its final response. The structured output will contain only the LAST query/results (the one immediately preceding the `---ANALYSIS---` section).
   - **Risk:** Intermediate queries are lost. The visualization shows only the final query's results.
   - **Mitigation:** This is acceptable for v1. Multi-query steps are rare (the orchestrator's instructions typically ask for one specific piece of data). If this becomes an issue, extend the format to support multiple `---QUERY---`/`---RESULTS---` blocks.
