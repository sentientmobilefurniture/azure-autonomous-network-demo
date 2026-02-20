# Task 01: Feasibility Validation — Conversation Revamp

> **Phase**: [README.md](../README.md) — Azure Autonomous Network Demo: Conversation Revamp  
> **Output**: `planning/task_01_validation_plan.md`

## Goal

Produce a comprehensive feasibility validation that determines whether each
requirement in the phase README is achievable given the **current codebase
state**, identifies blockers, quantifies effort, and proposes concrete
implementation paths for each requirement.

## Prerequisites

- Full read access to the codebase at `/home/hanchoong/azure-autonomous-network-demo/`
- Read the phase [README.md](../README.md) for the complete objective and success criteria

## Scope

Validate **every** requirement from the README against the current code. The
six requirements to validate are:

1. **Hierarchical streaming** — orchestrator reasoning → sub-agent call → sub-agent internal API calls, streamed live to UI in a collapsible tree
2. **Sub-agent internal call visibility** — sub-agent's own API queries and responses rendered indented under the sub-agent bubble
3. **Async session management** — new scenario launches without blocking current, prior session appears in sidebar
4. **Manual save with chunked Cosmos persistence** — explicit user-triggered save, session split into chunks, async persist, chunk-based retrieval
5. **Graceful degradation** — partial sessions render without crash
6. **Real-time streaming of all steps** — continuous visual feedback, no waiting for full response

## Steps

### Step 1: Map the Current Architecture

Read and document the following. Quote key code (function signatures, event
schemas, data models). Do not paraphrase from memory.

| Area | Files to Read | What to Extract |
|------|--------------|-----------------|
| **Orchestrator** | `api/app/orchestrator.py` | Entry points, event types emitted, `SSEEventHandler` callbacks, how sub-agents are invoked, thread model |
| **Sub-agent provisioning** | `scripts/agent_provisioner.py`, `api/app/agent_ids.py` | Agent definitions, tool types (ConnectedAgentTool, OpenApiTool, AzureAISearchTool, FunctionTool), how orchestrator connects to sub-agents |
| **Session model** | `api/app/sessions.py` | `Session` dataclass fields, `push_event`, `subscribe`, `to_dict`, `MAX_EVENT_LOG_SIZE` |
| **Session manager** | `api/app/session_manager.py` | `create`, `start`, `continue_session`, `_finalize_turn`, `_persist_to_cosmos`, `recover_from_cosmos`, `_move_to_recent` |
| **SSE router** | `api/app/routers/sessions.py` | `stream_session` generator, SSE lifecycle, event replay + live tail |
| **Frontend SSE** | `frontend/src/hooks/useSession.ts` | `connectToStream`, `updateOrchestratorMessage` switch, `loadSessionMessages` reconstruction |
| **Frontend types** | `frontend/src/types/index.ts` | `ChatMessage`, `StepEvent`, `SessionDetail`, `SessionSummary` |
| **Frontend rendering** | `frontend/src/components/ChatPanel.tsx`, `StepCard.tsx`, `OrchestratorThoughts.tsx`, `DiagnosisBlock.tsx`, `ActionCard.tsx` | How messages and steps render, any existing nesting/hierarchy |
| **Cosmos persistence** | `graph-query-api/router_sessions.py`, `graph-query-api/stores/cosmos_nosql.py`, `graph-query-api/stores/__init__.py` | `DocumentStore` protocol, how sessions are persisted/retrieved, document size constraints |
| **App setup** | `api/app/main.py`, `supervisord.conf` | FastAPI config, lifespan hooks, process model |

### Step 2: Validate Each Requirement

For each of the six requirements, produce a structured assessment:

```markdown
### Requirement N: <title>

**Current State**: What exists today that serves this requirement (cite files, functions, line numbers).

**Gap Analysis**: What is missing or insufficient. Be specific — cite exact code that would need to change.

**SDK / External Constraints**: Any Azure AI Agents SDK limitations, Cosmos DB limits, or library constraints that affect feasibility. For SDK constraints, check whether the installed SDK version supports features like sub-agent event streaming — run `pip show azure-ai-projects azure-ai-agents` if possible or check imports in the codebase.

**Feasibility Verdict**: One of:
- ✅ **Achievable** — can be done with the current architecture
- ⚠️ **Achievable with significant changes** — requires architectural rework but no external blockers
- ❌ **Blocked** — requires external capability that does not exist (SDK feature, service feature)

**Proposed Implementation Path**: Concrete approach if achievable. List files to modify, new files to create, key design decisions. If blocked, describe the workaround (if any) and its trade-offs.

**Effort Estimate**: S / M / L / XL with justification.

**Risks**: What could go wrong, regression risks, user-facing impacts.
```

### Step 3: Identify the Critical Path

Determine:
- Which requirements are **already met** and need no work
- Which requirements are **independently implementable**
- Which requirements have **dependencies** on other requirements
- Which requirement is the **highest-risk / highest-effort** item
- Recommended implementation order

### Step 4: SDK Investigation

The single most important question: **Can the Azure AI Agents SDK stream
events from sub-agent runs executed via ConnectedAgentTool?**

To answer this:
1. Read the orchestrator's `SSEEventHandler` — does `on_run_step` fire for
   sub-agent internal steps or only orchestrator-level steps?
2. Check `scripts/agent_provisioner.py` — how are ConnectedAgentTools
   configured? Is there a streaming option?
3. Check the installed SDK version and compare against Azure AI Agents SDK
   documentation (look for `azure-ai-agents` in `api/pyproject.toml` or
   `requirements.txt`)
4. If ConnectedAgentTool is opaque, evaluate the **manual sub-agent
   orchestration** alternative: run each sub-agent explicitly with its own
   `AgentEventHandler`, collect events, merge into the session event stream.
   Assess the complexity of this refactor.

### Step 5: Chunked Persistence Design

Evaluate the chunked Cosmos persistence requirement:
1. Current max document size (2MB Cosmos limit) vs. typical session sizes
2. How would chunking work? (e.g., chunk `event_log` into N documents,
   store a manifest, reconstruct on read)
3. Impact on `router_sessions.py` endpoints
4. Impact on `loadSessionMessages` in the frontend
5. Trade-offs vs. simply increasing `MAX_EVENT_LOG_SIZE` or compressing events

### Step 6: Write the Validation Report

Produce the output document `planning/task_01_validation_plan.md` covering:

1. **Architecture Summary** (brief — focus on what matters for the revamp)
2. **Per-Requirement Validation** (Step 2 output for all six requirements)
3. **Critical Path & Dependency Graph** (Step 3 output)
4. **SDK Feasibility Deep-Dive** (Step 4 output)
5. **Chunked Persistence Design Notes** (Step 5 output)
6. **Overall Feasibility Verdict** — can the revamp be done? What is the recommended scope reduction if any requirement is blocked?
7. **Recommended Task Breakdown** — proposed list of implementation tasks for the phase, in dependency order

## Completion Criteria

- [ ] Every file listed in Step 1 has been read and key details extracted
- [ ] All six requirements have structured assessments with verdicts
- [ ] SDK limitation around sub-agent event streaming is conclusively answered
- [ ] Chunked persistence approach is designed or rejected with rationale
- [ ] Output document exists at `planning/task_01_validation_plan.md`
- [ ] Recommended task breakdown is actionable (each task is a standalone unit of work)
