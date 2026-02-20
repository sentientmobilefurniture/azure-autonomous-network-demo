# SOTA Implementation Plan v2 — Microsoft Agent Framework Migration

> **Date**: 2026-02-21  
> **Framework**: `agent-framework` (`1.0.0rc1`)  
> **Principle**: Replace ALL custom orchestration code with the official Microsoft Agent Framework  
> **Source code**: `/home/hanchoong/microsoft_skills/agent-framework/python/`

---

## Executive Summary

v1 of the SOTA plan proposed `ImageBasedHostedAgentDefinition` + custom containers. This v2 takes a fundamentally different approach: **adopt `microsoft/agent-framework` as the runtime layer** and eliminate ALL custom orchestration plumbing.

The agent-framework already provides:
- `AzureAIAgentsProvider` → wraps our Foundry agents as `Agent` instances
- `HandoffOrchestrator` / `GroupChatOrchestrator` → replaces our custom `ConnectedAgentTool` orchestration loop
- `AgentFunctionApp` → one-line Azure Functions hosting (or `from_agent_framework` for Hosted Agents)
- `AG-UI` protocol → replaces our custom SSE bridge
- `AgentSession` + `InMemoryHistoryProvider` → replaces our `session_manager.py`
- `FunctionTool` → replaces our manual `FunctionToolDefinition` + `enable_auto_function_calls` wiring
- `MCPTool` → native MCP support
- Streaming via `agent.run(stream=True)` → replaces our 771-line `orchestrator.py`

**Net result**: ~2,100 lines of backend Python eliminated, replaced by ~300 lines of framework integration.

---

## Architecture: Before vs After

### BEFORE (Current — 2,483 lines of custom code)

```
Container App
├── api/ (FastAPI)
│   ├── orchestrator.py (771 lines)
│   │   ├── SSEEventHandler (custom AgentEventHandler subclass)
│   │   ├── asyncio.Queue bridge (thread → async)
│   │   ├── _parse_structured_output() (response parsing)
│   │   ├── _run_in_thread() (background thread lifecycle)
│   │   └── run_orchestrator_session() (async generator)
│   ├── session_manager.py (367 lines)
│   │   ├── Session lifecycle management
│   │   ├── Multi-turn thread reuse
│   │   └── Cosmos DB persistence
│   ├── sessions.py (156 lines)
│   │   ├── Session dataclass
│   │   └── Subscriber fan-out (asyncio.Queue per SSE client)
│   ├── agent_ids.py (235 lines)
│   │   ├── TTL-cached agent discovery
│   │   └── Foundry API polling
│   ├── dispatch.py (139 lines)
│   │   └── dispatch_field_engineer FunctionTool
│   └── routers/sessions.py (219 lines)
│       └── REST/SSE endpoints
│
├── scripts/
│   ├── agent_provisioner.py (416 lines)
│   │   ├── OpenAPI tool loading
│   │   ├── 5× create_agent() calls
│   │   └── ConnectedAgentTool wiring
│   └── provision_agents.py (183 lines)
│       └── CLI wrapper
│
└── graph-query-api/ (separate FastAPI)
    ├── router_graph.py (76 lines) — OpenAPI proxy for GQL
    └── router_telemetry.py (74 lines) — OpenAPI proxy for KQL
```

### AFTER (Agent Framework — ~300 lines of integration)

```
Container App
├── api/ (FastAPI)
│   ├── agents.py (~80 lines) — NEW
│   │   ├── AzureAIAgentsProvider setup
│   │   ├── Agent creation (5 agents)
│   │   └── HandoffOrchestrator wiring
│   ├── endpoints.py (~40 lines) — NEW
│   │   ├── AG-UI endpoint OR
│   │   └── SSE proxy via agent.run(stream=True)
│   ├── sessions.py (~80 lines) — SIMPLIFIED
│   │   ├── AgentSession integration
│   │   └── Cosmos persistence (kept)
│   ├── dispatch.py (139 lines) — KEPT (moved to FunctionTool)
│   └── routers/sessions.py (~100 lines) — SIMPLIFIED
│
│   DELETED:
│   ├── orchestrator.py (771 lines → 0)
│   ├── agent_ids.py (235 lines → 0)
│
├── scripts/
│   └── provision_agents.py (~120 lines) — SIMPLIFIED
│       ├── AzureAIAgentsProvider.create_agent()
│       └── No more OpenAPI loading, ConnectedAgentTool wiring
│
└── graph-query-api/ (REDUCED)
    ├── router_graph.py — DELETED (FabricTool)
    └── router_telemetry.py — DELETED (FabricTool)
```

---

## Phase 1: Install agent-framework & upgrade SDK (Day 1)

### Step 1.1 — Update dependencies

**File**: `api/pyproject.toml`

```toml
# BEFORE
dependencies = [
    "azure-ai-projects>=1.0.0,<2.0.0",
    "azure-ai-agents==1.2.0b6",
    ...
]

# AFTER
dependencies = [
    "agent-framework-azure-ai>=1.0.0rc1",  # Pulls in agent-framework-core + azure-ai-agents
    "agent-framework-orchestrations>=1.0.0rc1",  # Handoff/GroupChat
    ...
]
```

**Cross-ref**: `agent-framework/python/packages/azure-ai/pyproject.toml`:
```toml
dependencies = [
    "agent-framework-core>=1.0.0rc1",
    "azure-ai-agents == 1.2.0b5",
]
```

**Note**: The framework pins `azure-ai-agents==1.2.0b5`. Our code currently uses `1.2.0b6`. This must be reconciled — either use the framework's pin or override.

**File**: `pyproject.toml` (root)

Same changes — replace direct `azure-ai-projects` / `azure-ai-agents` with `agent-framework-azure-ai`.

### Step 1.2 — Verify installation

```bash
cd api && uv sync && .venv/bin/python3 -c "
from agent_framework import Agent
from agent_framework_azure_ai import AzureAIAgentsProvider
from agent_framework_orchestrations import HandoffOrchestrator
print('All imports OK')
"
```

---

## Phase 2: Create Agent Provider (Day 1-2)

### Step 2.1 — Create `api/app/agents.py`

This single file replaces `agent_ids.py` (235 lines) + the agent creation parts of `orchestrator.py`.

```python
"""
Agent definitions using Microsoft Agent Framework.

Replaces: orchestrator.py (config/agent wiring), agent_ids.py (discovery)
"""

import os
import logging
from typing import Any

from agent_framework import Agent, FunctionTool
from agent_framework_azure_ai import AzureAIAgentsProvider
from azure.identity.aio import DefaultAzureCredential

from app.dispatch import dispatch_field_engineer

logger = logging.getLogger(__name__)

# Singleton provider
_provider: AzureAIAgentsProvider | None = None
_credential: DefaultAzureCredential | None = None


async def get_provider() -> AzureAIAgentsProvider:
    """Get or create the AzureAIAgentsProvider singleton."""
    global _provider, _credential
    if _provider is None:
        _credential = DefaultAzureCredential()
        _provider = AzureAIAgentsProvider(
            project_endpoint=os.environ.get("PROJECT_ENDPOINT"),
            credential=_credential,
        )
    return _provider


async def get_orchestrator_agent() -> Agent:
    """Get the Orchestrator agent, providing the dispatch function tool.

    The framework's AzureAIAgentsProvider handles:
    - Agent discovery by ID (no more TTL-cached polling)
    - Tool validation (ensures dispatch_field_engineer is provided)
    - Streaming via agent.run(stream=True)
    - Function auto-execution via FunctionTool
    """
    provider = await get_provider()
    orchestrator_id = os.environ.get("ORCHESTRATOR_AGENT_ID", "")

    if not orchestrator_id:
        raise RuntimeError("ORCHESTRATOR_AGENT_ID not set")

    # The FunctionTool wraps dispatch_field_engineer with auto-execution
    dispatch_tool = FunctionTool.from_function(dispatch_field_engineer)

    return await provider.get_agent(
        id=orchestrator_id,
        tools=[dispatch_tool],
    )


async def cleanup():
    """Close provider and credential on shutdown."""
    global _provider, _credential
    if _provider:
        await _provider.close()
        _provider = None
    if _credential:
        await _credential.close()
        _credential = None
```

**Cross-ref**: `agent-framework/python/packages/azure-ai/agent_framework_azure_ai/_agent_provider.py`:
- `get_agent(id, tools=[...])` fetches by ID and validates function tools ✅
- Provider manages `AgentsClient` lifecycle ✅
- `_validate_function_tools` ensures dispatch_field_engineer is provided ✅

**What this eliminates**:
- `agent_ids.py` (235 lines) — `get_agent()` replaces `_discover_agents()` + TTL cache
- `orchestrator.py` lines 30-85 — config helpers (`_get_credential`, `_get_project_client`, `is_configured`, `_load_orchestrator_id`, `_load_agent_names`)

### Step 2.2 — Create `api/app/streaming.py`

This replaces the ENTIRE 771-line `orchestrator.py` — the SSEEventHandler, asyncio.Queue bridge, thread lifecycle, retry logic.

```python
"""
Streaming bridge — agent.run(stream=True) → SSE events.

Replaces: orchestrator.py (771 lines)
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

from agent_framework import AgentResponseUpdate

logger = logging.getLogger(__name__)


async def stream_agent_to_sse(
    agent,
    alert_text: str,
    *,
    conversation_id: str | None = None,
) -> AsyncGenerator[dict, None]:
    """Run the agent with streaming and yield SSE-shaped events.

    The Agent Framework handles ALL of:
    - Thread creation/reuse (via conversation_id option)
    - Tool call execution (FunctionTool auto-dispatches)
    - Connected agent delegation
    - Retry on failure
    - Streaming response chunks

    We just translate framework events → our SSE schema.
    """
    msg_id = str(uuid.uuid4())

    yield {
        "event": "run.start",
        "data": json.dumps({
            "run_id": "",
            "alert": alert_text,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }),
    }

    try:
        step_counter = 0
        options = {}
        if conversation_id:
            options["conversation_id"] = conversation_id

        async with agent.run(
            alert_text,
            stream=True,
            **options,
        ) as stream:
            async for update in stream:
                sse_events = _translate_update(update, msg_id, step_counter)
                for event in sse_events:
                    if event.get("_step_increment"):
                        step_counter += 1
                    yield event

        # Final response
        response = await stream.get_response()
        if response.text:
            yield {
                "event": "message.complete",
                "data": json.dumps({"id": msg_id, "text": response.text}),
            }
        yield {
            "event": "run.complete",
            "data": json.dumps({
                "steps": step_counter,
                "time": "",
            }),
        }

    except Exception as e:
        logger.exception("Agent stream failed")
        yield {
            "event": "error",
            "data": json.dumps({"message": str(e)}),
        }


def _translate_update(
    update: AgentResponseUpdate,
    msg_id: str,
    step: int,
) -> list[dict]:
    """Translate a framework AgentResponseUpdate → SSE events.

    The framework emits structured updates for:
    - Tool calls (start/complete)
    - Message text deltas
    - Function call results
    """
    events = []

    # Text content delta
    if update.text:
        events.append({
            "event": "message.delta",
            "data": json.dumps({"id": msg_id, "text": update.text}),
        })

    # Tool call events (the framework tracks these on RunStep callbacks)
    if update.tool_calls:
        for tc in update.tool_calls:
            if tc.get("status") == "in_progress":
                events.append({
                    "event": "tool_call.start",
                    "data": json.dumps({
                        "id": tc.get("id", str(uuid.uuid4())),
                        "step": step + 1,
                        "agent": tc.get("agent", ""),
                        "query": tc.get("query", ""),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }),
                    "_step_increment": True,
                })
            elif tc.get("status") == "completed":
                events.append({
                    "event": "tool_call.complete",
                    "data": json.dumps({
                        "id": tc.get("id", ""),
                        "step": step,
                        "agent": tc.get("agent", ""),
                        "duration": tc.get("duration", ""),
                        "response": tc.get("response", ""),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }),
                })

    return events
```

**What this eliminates entirely**:
- `SSEEventHandler` class (~200 lines)
- `_run_in_thread()` function (~150 lines)
- `run_orchestrator_session()` async generator (~80 lines)
- `_parse_structured_output()` (~100 lines)
- `_resolve_agent_name()` / `_extract_arguments()` (~80 lines)
- `asyncio.Queue` bridge pattern
- Thread-safe `_put()` helper
- `MAX_RUN_ATTEMPTS` retry loop
- Cancel event handling
- Message ID generation for SSE

The framework's `AzureAIAgentClient._chat_client.py` (1,476 lines) handles ALL of this internally via `AsyncAgentEventHandler`, including:
- Run step tracking
- Message delta streaming
- Function tool auto-execution
- MCP tool approval
- Thread management

**Cross-ref**: `agent-framework/python/packages/azure-ai/agent_framework_azure_ai/_chat_client.py` — the framework's own 1,476-line streaming handler does everything our 771-line `orchestrator.py` does, plus more (MCP approval, code interpreter, file search annotations, structured outputs).

---

## Phase 3: Provisioning Rewrite (Day 2)

### Step 3.1 — Rewrite `scripts/agent_provisioner.py`

**Current**: 416 lines — OpenAPI spec loading, ConnectedAgentTool wiring, FunctionToolDefinition schema, delete-and-recreate.

**New**: ~120 lines — use `AzureAIAgentsProvider.create_agent()`.

```python
"""
Agent provisioning using Microsoft Agent Framework.

Replaces the manual create_agent + ConnectedAgentTool + FunctionToolDefinition
pattern with the framework's AzureAIAgentsProvider.
"""

import asyncio
import os
import logging

from agent_framework import FunctionTool
from agent_framework_azure_ai import AzureAIAgentsProvider
from azure.identity.aio import DefaultAzureCredential

from dispatch import dispatch_field_engineer  # local import

logger = logging.getLogger("agent-provisioner")


async def provision_all(
    project_endpoint: str,
    model: str,
    prompts: dict[str, str],
    search_connection_id: str,
    runbooks_index: str,
    tickets_index: str,
) -> dict:
    """Provision all 5 agents using the Agent Framework provider."""

    async with (
        DefaultAzureCredential() as credential,
        AzureAIAgentsProvider(
            project_endpoint=project_endpoint,
            credential=credential,
        ) as provider,
    ):
        # --- Sub-agents ---

        ge = await provider.create_agent(
            name="GraphExplorerAgent",
            model=model,
            instructions=prompts["graph_explorer"],
            tools=[],  # FabricTool added via Foundry portal or future SDK support
        )
        logger.info("Created GraphExplorerAgent: %s", ge.id)

        tel = await provider.create_agent(
            name="TelemetryAgent",
            model=model,
            instructions=prompts["telemetry"],
            tools=[],
        )
        logger.info("Created TelemetryAgent: %s", tel.id)

        # AI Search tools — use low-level SDK tool objects passed as dicts
        from azure.ai.agents.models import AzureAISearchTool, AzureAISearchQueryType

        rb_search = AzureAISearchTool(
            index_connection_id=search_connection_id,
            index_name=runbooks_index,
            query_type=AzureAISearchQueryType.SEMANTIC,
            top_k=5,
        )
        rb = await provider.create_agent(
            name="RunbookKBAgent",
            model=model,
            instructions=prompts["runbook"],
            tools=rb_search.definitions,
        )
        logger.info("Created RunbookKBAgent: %s", rb.id)

        tk_search = AzureAISearchTool(
            index_connection_id=search_connection_id,
            index_name=tickets_index,
            query_type=AzureAISearchQueryType.SEMANTIC,
            top_k=5,
        )
        tk = await provider.create_agent(
            name="HistoricalTicketAgent",
            model=model,
            instructions=prompts["ticket"],
            tools=tk_search.definitions,
        )
        logger.info("Created HistoricalTicketAgent: %s", tk.id)

        # --- Orchestrator with ConnectedAgentTool + FunctionTool ---

        from azure.ai.agents.models import ConnectedAgentTool

        connected_tools = []
        for agent_ref in [
            (ge, "Graph topology explorer"),
            (tel, "Telemetry and alert analyst"),
            (rb, "Operational runbook searcher"),
            (tk, "Historical incident searcher"),
        ]:
            ct = ConnectedAgentTool(
                id=agent_ref[0].id,
                name=agent_ref[0].name,
                description=agent_ref[1],
            )
            connected_tools.extend(ct.definitions)

        dispatch_tool = FunctionTool.from_function(dispatch_field_engineer)

        orch = await provider.create_agent(
            name="Orchestrator",
            model=model,
            instructions=prompts["orchestrator"],
            tools=[*connected_tools, dispatch_tool],
        )
        logger.info("Created Orchestrator: %s", orch.id)

        return {
            "orchestrator_id": orch.id,
            "sub_agents": {
                "GraphExplorerAgent": ge.id,
                "TelemetryAgent": tel.id,
                "RunbookKBAgent": rb.id,
                "HistoricalTicketAgent": tk.id,
            },
        }
```

**What this eliminates**:
- `_load_openapi_spec()` (40 lines)
- `CONNECTOR_OPENAPI_VARS` dict (25 lines)
- `GRAPH_TOOL_DESCRIPTIONS` dict (5 lines)
- `_build_connection_id()` (15 lines)
- `cleanup_existing()` (20 lines)
- Manual `FunctionToolDefinition` + `FunctionDefinition` schema (60 lines)
- The `AgentProvisioner` class wrapper (50 lines)

**Cross-ref**: `agent-framework/python/packages/azure-ai/agent_framework_azure_ai/_agent_provider.py` line 160:
- `create_agent(name, model, instructions, tools)` — creates on Foundry AND returns wrapped `Agent` ✅
- Tools are automatically converted via `to_azure_ai_agent_tools()` ✅
- `FunctionTool.from_function(dispatch_field_engineer)` auto-generates the JSON schema from the Python docstring ✅

---

## Phase 4: Session Management Simplification (Day 2-3)

### Step 4.1 — Simplify `api/app/session_manager.py`

The framework provides `AgentSession` with built-in history management. Our `SessionManager` simplifies to just Cosmos persistence + SSE subscriber management.

**Current session_manager.py responsibilities**:
1. Session creation → **KEEP** (Cosmos tracking)
2. Launch orchestrator task → **REPLACE** with `agent.run(stream=True)`
3. Event tracking (tool_call.complete → session.steps) → **SIMPLIFY**
4. Multi-turn thread reuse → **FRAMEWORK HANDLES** (via `conversation_id`)
5. Cancel support → **FRAMEWORK HANDLES** (via AbortController-style)
6. Cosmos persistence → **KEEP**
7. Idle timeout → **KEEP**

**Key change**: The `start()` and `continue_session()` methods no longer call `run_orchestrator_session()`. Instead they call `stream_agent_to_sse()` from the new `streaming.py`.

```python
# BEFORE (session_manager.py → start())
from app.orchestrator import run_orchestrator_session

async for event in run_orchestrator_session(
    session.alert_text, session._cancel_event
):
    session.push_event(event)
    # ... track events

# AFTER
from app.streaming import stream_agent_to_sse
from app.agents import get_orchestrator_agent

agent = await get_orchestrator_agent()
async for event in stream_agent_to_sse(
    agent, session.alert_text,
    conversation_id=session.thread_id,
):
    session.push_event(event)
    # ... track events (same logic, different source)
```

---

## Phase 5: Alternative — AG-UI Protocol Endpoint (Day 3)

### Option A: Keep Custom SSE (minimal frontend change)

Keep the existing SSE event schema (`tool_call.start`, `message.delta`, etc.) and use `streaming.py` to translate framework events. **Frontend unchanged.**

### Option B: AG-UI Protocol (radical frontend simplification)

Use the framework's `add_agent_framework_fastapi_endpoint` to expose the agent directly via the AG-UI streaming protocol. **Frontend switches to AG-UI client.**

```python
# api/app/main.py
from agent_framework.ag_ui import add_agent_framework_fastapi_endpoint
from app.agents import get_orchestrator_agent

agent = await get_orchestrator_agent()
add_agent_framework_fastapi_endpoint(app, agent, "/api/agent")
```

**Cross-ref**: `agent-framework/python/packages/ag-ui/agent_framework_ag_ui/__init__.py`:
```python
from ._endpoint import add_agent_framework_fastapi_endpoint
```

**Frontend would use**:
```typescript
// Replace useConversation.ts SSE parser with AG-UI client
import { AGUIClient } from '@ag-ui/client';  // or direct fetch

const client = new AGUIClient({ endpoint: '/api/agent' });
const stream = client.run(alertText);
for await (const event of stream) {
  // AG-UI protocol events are standardized
}
```

**Recommendation**: Start with **Option A** (zero frontend changes), evaluate Option B as a future enhancement.

---

## Phase 6: Orchestration Upgrade — Handoff Pattern (Day 3-4)

### Current vs Framework Orchestration

**Current**: The Orchestrator agent has `ConnectedAgentTool` references to sub-agents. Foundry's server-side agent loop decides when to call which sub-agent. Our code has no control over orchestration order — it's all in the LLM's prompt.

**Framework alternative**: Use `HandoffOrchestrator` for explicit agent-to-agent routing with state management.

```python
from agent_framework_orchestrations import HandoffOrchestrator, HandoffConfiguration

orchestrator = HandoffOrchestrator.build(
    agents=[graph_agent, telemetry_agent, runbook_agent, ticket_agent],
    handoffs={
        graph_agent: [
            HandoffConfiguration(target=telemetry_agent, description="Hand off to telemetry for alert data"),
            HandoffConfiguration(target=runbook_agent, description="Hand off to runbook for procedures"),
        ],
        telemetry_agent: [
            HandoffConfiguration(target=graph_agent, description="Hand off to graph for topology"),
            HandoffConfiguration(target=ticket_agent, description="Hand off to tickets for history"),
        ],
        # ... each agent can hand off to any other
    },
)
```

**Cross-ref**: `agent-framework/python/packages/orchestrations/agent_framework_orchestrations/_handoff.py`:
- `HandoffConfiguration(target=..., description=...)` — defines routing ✅
- `_AutoHandoffMiddleware` — intercepts handoff tool calls ✅
- Agents decide routing via tool calls (same as `ConnectedAgentTool`) ✅

**Assessment**: This is architecturally elegant but **does not add value for our demo** because:
1. Our orchestration is already handled server-side by Foundry's `ConnectedAgentTool`
2. The Handoff pattern runs the orchestration **client-side** (in our Container App), which means MORE network round-trips
3. Our agents are server-side Foundry agents, not local

**Decision**: **Skip Handoff orchestration for now.** Keep ConnectedAgentTool server-side orchestration. The framework's `get_agent()` + `agent.run(stream=True)` pattern is sufficient. The Handoff pattern would only make sense if we moved to local agent execution.

---

## Phase 7: Hosting Options (Day 4-5)

### Option A: Container App + agent.run() (RECOMMENDED)

Keep the existing Container App. Replace the orchestrator bridge with `agent.run(stream=True)`. Minimal infrastructure change.

### Option B: Azure Functions with AgentFunctionApp

```python
from agent_framework.azure import AgentFunctionApp

app = AgentFunctionApp(agents=[orchestrator_agent], enable_health_check=True)
```

**Cross-ref**: `agent-framework/python/samples/04-hosting/azure_functions/01_single_agent/function_app.py`:
```python
app = AgentFunctionApp(agents=[_create_agent()], enable_health_check=True, max_poll_retries=50)
```

**Assessment**: Would require rewriting the entire API surface from FastAPI to Azure Functions triggers. **Not recommended** — too much churn for no real benefit. Our Container App already handles scaling.

### Option C: Hosted Agents with from_agent_framework

```python
from azure.ai.agentserver.agentframework import from_agent_framework

agent = AzureOpenAIChatClient(credential=DefaultAzureCredential()).as_agent(...)
from_agent_framework(agent).run()
```

**Cross-ref**: `agent-framework/python/samples/05-end-to-end/hosted_agents/agent_with_hosted_mcp/main.py`:
```python
from azure.ai.agentserver.agentframework import from_agent_framework
from_agent_framework(agent).run()
```

**Assessment**: This is the v1 SOTA plan's `ImageBasedHostedAgentDefinition` approach, but via the framework. Same trade-offs (beta, ACR, container image). **Not recommended for now.**

**Decision**: **Option A — Container App + agent.run().**

---

## File Change Manifest

### Files DELETED

| File | Lines | Reason |
|------|-------|--------|
| `api/app/orchestrator.py` | 772 | Framework handles streaming, tool execution, thread management |
| `api/app/agent_ids.py` | 236 | `AzureAIAgentsProvider.get_agent()` replaces discovery |
| `graph-query-api/router_graph.py` | 76 | FabricTool replaces OpenAPI proxy (future) |
| `graph-query-api/router_telemetry.py` | 74 | FabricTool replaces OpenAPI proxy (future) |
| `graph-query-api/openapi/templates/graph.yaml` | 61 | No more OpenAPI specs |
| `graph-query-api/openapi/templates/telemetry.yaml` | 61 | No more OpenAPI specs |
| **Total deleted** | **1,280** | |

### Files CREATED

| File | Lines | Purpose |
|------|-------|---------|
| `api/app/agents.py` | ~80 | AzureAIAgentsProvider singleton, get_orchestrator_agent() |
| `api/app/streaming.py` | ~120 | agent.run(stream=True) → SSE event translation |
| **Total created** | **~200** | |

### Files MODIFIED

| File | Before | After | Delta |
|------|--------|-------|-------|
| `api/pyproject.toml` | 18 | 18 | Dependencies change |
| `pyproject.toml` | 27 | 27 | Dependencies change |
| `api/app/session_manager.py` | 367 | ~250 | -117 (no thread bridge) |
| `scripts/agent_provisioner.py` | 416 | ~120 | -296 (framework does the heavy lifting) |
| `scripts/provision_agents.py` | 183 | ~100 | -83 (simplified) |
| `api/app/routers/sessions.py` | 219 | ~150 | -69 (simplified) |
| `graph-query-api/main.py` | 193 | ~160 | -33 (remove graph/telemetry routers) |

### Net Code Change

| Category | Lines |
|----------|-------|
| Deleted | −1,280 |
| Simplified | −598 |
| Created | +200 |
| **Net** | **−1,678** |

---

## SDK / Package Dependencies

### Current

```toml
"azure-ai-projects>=1.0.0,<2.0.0"   # GA
"azure-ai-agents==1.2.0b6"           # beta
```

### After

```toml
"agent-framework-azure-ai>=1.0.0rc1"          # RC — pulls in azure-ai-agents==1.2.0b5
"agent-framework-orchestrations>=1.0.0rc1"     # RC — handoff/group-chat (optional)
```

### Version Note

The `agent-framework-azure-ai` package pins `azure-ai-agents==1.2.0b5`. Our code uses `1.2.0b6`. We need to:
1. Use the framework's pin (`1.2.0b5`) — safest
2. OR override with `1.2.0b6` in our `pyproject.toml` — test compatibility

---

## Infrastructure Changes

### Bicep — No changes required

The framework operates against the same Foundry project endpoint, same agents, same tools. No new Azure resources needed.

### Environment Variables — One addition

```
ORCHESTRATOR_AGENT_ID=<id>   # Set by provision_agents.py after creation
```

This replaces the dynamic agent discovery in `agent_ids.py`. After provisioning writes the ID, the Container App reads it at startup.

---

## Frontend Impact

### Option A: Zero frontend changes

The `streaming.py` module translates framework events → the same SSE schema (`tool_call.start`, `message.delta`, etc.) that the frontend already consumes. **No frontend changes.**

### Option B: AG-UI protocol (future)

Replace `useConversation.ts` SSE parser with AG-UI client library. The AG-UI protocol is a standardized streaming format that the framework emits natively. This would eliminate the custom SSE line parser.

---

## Migration Sequence

| Day | Phase | What Changes | Risk |
|-----|-------|-------------|------|
| 1 | 1-2 | Install framework, create agents.py, verify provider works | Low |
| 2 | 3 | Rewrite provisioner, provision agents | Low |
| 2-3 | 4 | Create streaming.py, update session_manager to use it | Medium |
| 3 | 5 | Delete orchestrator.py + agent_ids.py, test end-to-end | High |
| 4 | 6 (skip) | Evaluate Handoff orchestration — likely skip | N/A |
| 5 | 7 | Delete graph/telemetry OpenAPI proxies (if FabricTool works) | Medium |

### Total: 5 working days

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `agent-framework` is RC (not GA) | **Medium** | **High** | It's `1.0.0rc1` — very close to GA. Pin version. |
| `azure-ai-agents` version conflict (1.2.0b5 vs b6) | **Medium** | **Low** | Test with b5 first; override if needed |
| `agent.run(stream=True)` event format differs from our SSE schema | **High** | **Medium** | `streaming.py` translation layer absorbs the difference |
| Framework async patterns conflict with our sync/thread bridge | **Low** | **Medium** | Framework is fully async — we drop the thread bridge entirely |
| `AzureAIAgentClient` doesn't expose ConnectedAgentTool step details | **Medium** | **Medium** | Test streaming output format; may need to parse RunStep events |
| Performance regression (framework overhead) | **Low** | **Low** | Framework uses same SDK under the hood |

---

## Comparison: v1 (Hosted Agents) vs v2 (Agent Framework)

| Aspect | v1 (SOTA_DESIGN_IMPLEMENTATION_PLAN.md) | v2 (This document) |
|--------|----------------------------------------|---------------------|
| **Approach** | ImageBasedHostedAgentDefinition + custom container | Agent Framework as runtime layer |
| **SDK** | `azure-ai-projects>=2.0.0b4` (beta) | `agent-framework>=1.0.0rc1` (RC) |
| **Stability** | Early beta, undocumented RESPONSES protocol | RC → GA soon, active development, Microsoft official |
| **ACR required** | Yes (new infrastructure) | No |
| **Container image** | Must build, push, version | No |
| **CI/CD changes** | New image build pipeline | None |
| **Bicep changes** | ACR, enablePublicHostingEnvironment, Fabric connection | None |
| **Lines eliminated** | ~1,169 net | ~1,678 net |
| **New code** | ~320 lines (container + scripts) | ~200 lines (agents.py + streaming.py) |
| **Frontend changes** | SSE event mapping (container emits different format) | None (or AG-UI protocol future) |
| **Time estimate** | ~18 working days (7 phases) | ~5 working days |
| **Fallback** | Restore orchestrator.py | Restore orchestrator.py |
| **Community** | No framework community | Microsoft-backed open-source framework |

---

## Appendix: Key Import Patterns

```python
# Core framework
from agent_framework import Agent, FunctionTool, AgentSession, Message
from agent_framework import AgentResponse, AgentResponseUpdate

# Azure AI provider
from agent_framework_azure_ai import AzureAIAgentsProvider
from agent_framework_azure_ai._chat_client import AzureAIAgentClient, AzureAIAgentOptions

# Orchestrations (if needed)
from agent_framework_orchestrations import (
    HandoffOrchestrator, HandoffConfiguration,
    GroupChatOrchestrator, GroupChatSelectionFunction,
    ConcurrentBuilder, SequentialBuilder,
)

# AG-UI protocol (if needed)
from agent_framework.ag_ui import add_agent_framework_fastapi_endpoint

# Azure credentials (async)
from azure.identity.aio import DefaultAzureCredential

# Low-level SDK tools (still needed for ConnectedAgentTool, AzureAISearchTool)
from azure.ai.agents.models import (
    ConnectedAgentTool,
    AzureAISearchTool,
    AzureAISearchQueryType,
)
```
