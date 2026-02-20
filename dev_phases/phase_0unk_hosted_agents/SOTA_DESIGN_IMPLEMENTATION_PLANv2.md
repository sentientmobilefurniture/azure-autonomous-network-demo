# SOTA Implementation Plan v2 — Microsoft Agent Framework Migration

> **Date**: 2026-02-21 (updated)  
> **Framework**: `agent-framework` (`1.0.0rc1`)  
> **Hosting**: Azure Web App (replacing Container Apps)  
> **Principle**: Replace ALL custom orchestration code with the official Microsoft Agent Framework  
> **Source code**: `/home/hanchoong/microsoft_skills/agent-framework/python/`

---

## Executive Summary

v1 of the SOTA plan proposed `ImageBasedHostedAgentDefinition` + custom containers. This v2 takes a fundamentally different approach: **adopt `microsoft/agent-framework` as the runtime layer**, **merge graph-query-api into a single FastAPI process**, and **deploy on Azure Web App** instead of Container Apps.

The agent-framework already provides:
- `AzureAIAgentsProvider` → wraps our Foundry agents as `Agent` instances
- `HandoffOrchestrator` / `GroupChatOrchestrator` → replaces our custom `ConnectedAgentTool` orchestration loop
- `FunctionTool` → replaces our manual `FunctionToolDefinition` + `enable_auto_function_calls` wiring
- Streaming via `agent.run(stream=True)` → replaces our 771-line `orchestrator.py`

The infrastructure simplification:
- **Merge** `graph-query-api/` into `api/` → single FastAPI process
- **Delete** nginx, supervisord, multi-process Dockerfile
- **Replace** Container App with Azure Web App → simpler deployment, no container registry
- **Delete** OpenAPI proxy routers → FabricTool handles graph/telemetry queries natively

**Net result**: ~2,400 lines of backend Python eliminated, ~200 lines of infra config eliminated, replaced by ~300 lines of framework integration. Single-process Web App deployment.

---

## Architecture: Before vs After

### BEFORE (Current — Container App, 2 processes, nginx, supervisord)

```
Container App (single container, supervisord + nginx)
├── nginx (:80) — reverse proxy + SPA static files
├── api/ (:8000 — FastAPI process #1)
│   ├── orchestrator.py (771 lines) — SSE bridge
│   ├── session_manager.py (367 lines) — session lifecycle
│   ├── sessions.py (156 lines) — session dataclass
│   ├── agent_ids.py (235 lines) — agent discovery
│   ├── dispatch.py (139 lines) — FunctionTool
│   └── routers/sessions.py (219 lines) — REST/SSE endpoints
│
├── graph-query-api/ (:8100 — FastAPI process #2)
│   ├── router_graph.py (76) — GQL proxy for agents
│   ├── router_telemetry.py (74) — KQL proxy for agents
│   ├── router_sessions.py (190) — Cosmos session CRUD
│   ├── router_search.py (168) — AI Search for frontend viz
│   ├── router_topology.py (174) — Fabric topology for graph viewer
│   ├── router_health.py (216) — health + rediscovery
│   ├── router_interactions.py (119) — frontend interactions
│   ├── router_replay.py (89) — session replay
│   ├── cosmos_helpers.py (143) — Cosmos DB helpers
│   ├── fabric_discovery.py (301) — Fabric workspace discovery
│   ├── config.py (172) — configuration
│   ├── models.py (114) — data models
│   └── log_broadcaster.py (96) — log streaming
│
├── supervisord.conf — multi-process orchestration
├── nginx.conf — reverse proxy config
└── Dockerfile — multi-stage (node build + python + nginx + supervisord)
```

### AFTER (Web App — single FastAPI process, zero infra plumbing)

```
Azure Web App (single process, `gunicorn app.main:app`)
├── app/ (unified FastAPI)
│   ├── main.py — single FastAPI app, all routes
│   │
│   │ ── Agent layer (agent-framework) ──
│   ├── agents.py (~80 lines) — AzureAIAgentsProvider, get_orchestrator_agent()
│   ├── streaming.py (~120 lines) — agent.run(stream=True) → SSE translation
│   ├── dispatch.py (139 lines) — dispatch_field_engineer (kept)
│   │
│   │ ── Session layer ──
│   ├── session_manager.py (~250 lines) — simplified, calls agent.run()
│   ├── sessions.py (156 lines) — session dataclass (kept)
│   │
│   │ ── Data layer (merged from graph-query-api) ──
│   ├── routers/
│   │   ├── sessions.py (~150 lines) — REST/SSE endpoints
│   │   ├── topology.py — Fabric topology for graph viewer (moved)
│   │   ├── search.py — AI Search for frontend viz (moved)
│   │   ├── health.py — health checks (moved)
│   │   ├── interactions.py — frontend interactions (moved)
│   │   └── replay.py — session replay (moved)
│   ├── cosmos_helpers.py — Cosmos DB helpers (moved)
│   ├── fabric_discovery.py — Fabric workspace discovery (moved)
│   └── models.py — data models (moved)
│
├── static/ — React build output (served by FastAPI StaticFiles)
└── startup.sh — `gunicorn app.main:app -w 2 -k uvicorn.workers.UvicornWorker`

DELETED:
├── graph-query-api/ (entire directory — merged into app/)
├── supervisord.conf
├── nginx.conf
├── Dockerfile (replaced by Web App deployment)
├── orchestrator.py (771 lines → 0)
├── agent_ids.py (235 lines → 0)
├── router_graph.py (76 lines → 0, FabricTool)
├── router_telemetry.py (74 lines → 0, FabricTool)
```
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
(See diagram above — unified Web App)
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

> **Skipped** — see assessment below.

---

## Phase 6: Merge graph-query-api into api/ (Day 3-4)

### Rationale

With FabricTool handling graph/telemetry queries natively, the graph-query-api's agent-facing routers are deleted. The remaining routers serve the **frontend** only (topology viewer, search results, session CRUD, health). These belong in the main `api/` process.

Merging eliminates:
- `supervisord.conf` — no more multi-process orchestration
- `nginx.conf` — no more reverse proxy (FastAPI serves static files + API)
- Two separate `pyproject.toml` / `uv.lock` dependency sets
- Port 8100 internal routing

### Step 6.1 — Move routers into api/app/routers/

| Source (graph-query-api/) | Destination (api/app/routers/) | Lines |
|--------------------------|-------------------------------|-------|
| `router_sessions.py` | `routers/data_sessions.py` | 190 |
| `router_search.py` | `routers/search.py` | 168 |
| `router_topology.py` | `routers/topology.py` | 174 |
| `router_health.py` | `routers/health.py` | 216 |
| `router_interactions.py` | `routers/interactions.py` | 119 |
| `router_replay.py` | `routers/replay.py` | 89 |

Rename `router_sessions.py` → `data_sessions.py` to avoid collision with the existing `routers/sessions.py` (agent session SSE endpoints).

### Step 6.2 — Move shared modules into api/app/

| Source (graph-query-api/) | Destination (api/app/) | Lines |
|--------------------------|------------------------|-------|
| `cosmos_helpers.py` | `app/cosmos_helpers.py` | 143 |
| `fabric_discovery.py` | `app/fabric_discovery.py` | 301 |
| `models.py` | `app/data_models.py` | 114 |
| `log_broadcaster.py` | `app/log_broadcaster.py` | 96 |
| `config.py` | Merge into `app/paths.py` | 172 |

### Step 6.3 — Update imports and route prefixes

All moved routers currently mount at `/query/*`. After merge, re-mount them under the same prefix to avoid frontend changes:

```python
# api/app/main.py
from app.routers import topology, search, data_sessions, health, interactions, replay

app.include_router(topology.router, prefix="/query")
app.include_router(search.router, prefix="/query")
app.include_router(data_sessions.router, prefix="/query")
app.include_router(health.router, prefix="/query")
app.include_router(interactions.router, prefix="/query")
app.include_router(replay.router, prefix="/query")
```

**Frontend impact**: Zero — routes stay at `/query/*`.

### Step 6.4 — Update session_manager.py internal URL

```python
# BEFORE — talks to graph-query-api on localhost:8100
_GQ_BASE = os.getenv("GRAPH_QUERY_API_URI", "http://localhost:8100")

# AFTER — no network hop, import directly
from app.cosmos_helpers import cosmos_upsert_session, cosmos_list_sessions
```

This eliminates the `httpx` internal HTTP calls between the two processes. Direct function calls instead.

### Step 6.5 — Merge dependencies

Merge `graph-query-api/pyproject.toml` dependencies into `api/pyproject.toml`. The graph-query-api has:
- `azure-cosmos` — for Cosmos DB
- `azure-kusto-data` — for Fabric KQL queries (topology/search)
- `fabric-client` or REST calls — for Fabric API

### Step 6.6 — Add static file serving to FastAPI

```python
# api/app/main.py
from fastapi.staticfiles import StaticFiles

# Serve React build at root
app.mount("/", StaticFiles(directory="static", html=True), name="static")
```

The React build output goes to `api/static/` instead of nginx's `/usr/share/nginx/html`.

### Step 6.7 — Delete graph-query-api directory

```bash
rm -rf graph-query-api/
rm supervisord.conf
rm nginx.conf
```

### Step 6.8 — Delete OpenAPI proxy files (already dead after FabricTool)

```bash
rm graph-query-api/router_graph.py
rm graph-query-api/router_telemetry.py
rm graph-query-api/openapi/
```

---

## Phase 7: Migrate to Azure Web App (Day 4-5)

### Step 7.1 — Create new Bicep module: web-app.bicep

```bicep
@description('Name of the Web App')
param webAppName string

@description('Azure region')
param location string

@description('Resource tags')
param tags object = {}

@description('App Service Plan SKU')
param skuName string = 'B1'

// App Service Plan
resource plan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: '${webAppName}-plan'
  location: location
  tags: tags
  kind: 'linux'
  sku: {
    name: skuName
  }
  properties: {
    reserved: true  // Linux
  }
}

// Web App
resource webApp 'Microsoft.Web/sites@2024-04-01' = {
  name: webAppName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: plan.id
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.12'
      appCommandLine: 'gunicorn app.main:app -w 2 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000'
      alwaysOn: true
      ftpsState: 'Disabled'
      appSettings: [
        // All env vars from azure_config.env injected here
        { name: 'PROJECT_ENDPOINT', value: projectEndpoint }
        { name: 'MODEL_DEPLOYMENT_NAME', value: 'gpt-4.1' }
        { name: 'COSMOS_NOSQL_ENDPOINT', value: cosmosEndpoint }
        // ... etc
      ]
    }
    httpsOnly: true
  }
}

output webAppName string = webApp.name
output webAppUrl string = 'https://${webApp.properties.defaultHostName}'
output webAppPrincipalId string = webApp.identity.principalId
```

### Step 7.2 — Delete Container App Bicep module

```bash
rm infra/modules/container-app.bicep
```

Update `infra/main.bicep` to reference `web-app.bicep` instead.

### Step 7.3 — Replace Dockerfile with Web App deployment

**Delete**:
- `Dockerfile` (multi-stage, nginx, supervisord)
- `supervisord.conf`
- `nginx.conf`

**Create**: `startup.sh`
```bash
#!/bin/bash
# Build frontend at deploy time (or pre-build in CI)
cd /home/site/wwwroot
gunicorn app.main:app -w 2 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### Step 7.4 — Update deploy.sh

Replace the `az containerapp up` / `az acr build` deployment with:

```bash
# Build frontend
cd frontend && npm ci && npm run build && cd ..
# Copy build to static/
cp -r frontend/dist api/static/
# Deploy to Web App
cd api && az webapp up --name "$WEB_APP_NAME" --resource-group "$AZURE_RESOURCE_GROUP" --runtime "PYTHON:3.12"
```

Or use `azd` with the new Web App target in `azure.yaml`.

### Step 7.5 — Update azure.yaml for azd

```yaml
name: autonomous-network-demo
services:
  api:
    host: appservice
    project: ./api
    language: python
    hooks:
      prepackage:
        shell: bash
        run: cd ../frontend && npm ci && npm run build && cp -r dist ../api/static/
```

### Step 7.6 — Update role assignments

The Web App's system-assigned managed identity needs the same roles the Container App had:
- Cosmos DB: `Cosmos DB Built-in Data Contributor`
- AI Foundry: `Cognitive Services User`
- AI Search: `Search Index Data Reader`
- Storage: `Storage Blob Data Reader`

The Bicep `roleAssignments` resource references change from `containerApp.outputs.principalId` to `webApp.outputs.webAppPrincipalId`.

---

## Phase 8: Hosting Options Assessment (DECIDED)

> Container App vs Web App vs Azure Functions — **Web App selected.**

| Aspect | Container App (current) | Web App (selected) | Azure Functions |
|--------|------------------------|-------------------|-----------------|
| Process model | Multi-process (supervisord) | Single process (gunicorn) | Per-function |
| Static files | nginx proxy | FastAPI `StaticFiles` | Not applicable |
| Config complexity | Dockerfile + nginx + supervisord | `startup.sh` | host.json + bindings |
| Deployment | `az acr build` + `az containerapp up` | `az webapp up` or `azd deploy` | `func azure functionapp publish` |
| SSE streaming | ✅ | ✅ | ⚠️ (limited) |
| Scale to zero | ✅ (free) | ❌ (B1 ~$13/mo min) | ✅ (Consumption) |
| Cold start | ~5-10s | ~3-5s (always-on) | ~10-30s |
| Bicep complexity | 127 lines (ingress, secrets, env) | ~60 lines (plan + site) | ~40 lines |
| CI/CD | Container build pipeline | `az webapp up` (no registry) | `func deploy` |

**Decision**: Web App. Simpler deployment, no container registry, no multi-process orchestration, familiar `az webapp up` workflow. The ~$13/mo cost is negligible for a demo.

---

## File Change Manifest

### Files DELETED

| File | Lines | Reason |
|------|-------|--------|
| `api/app/orchestrator.py` | 772 | Framework handles streaming, tool execution, thread management |
| `api/app/agent_ids.py` | 236 | `AzureAIAgentsProvider.get_agent()` replaces discovery |
| `graph-query-api/router_graph.py` | 76 | FabricTool replaces OpenAPI proxy |
| `graph-query-api/router_telemetry.py` | 74 | FabricTool replaces OpenAPI proxy |
| `graph-query-api/openapi/templates/*.yaml` | 122 | No more OpenAPI specs |
| `graph-query-api/main.py` | 193 | Merged into api/app/main.py |
| `graph-query-api/config.py` | 172 | Merged into api/app/paths.py |
| `supervisord.conf` | 40 | Single process — no multi-process orchestration |
| `nginx.conf` | 55 | FastAPI serves static files directly |
| `Dockerfile` | 75 | Web App deployment — no container build |
| `infra/modules/container-app.bicep` | 127 | Replaced by web-app.bicep |
| **Total deleted** | **~1,942** | |

### Files MOVED (graph-query-api → api/app/)

| Source | Destination | Lines |
|--------|------------|-------|
| `graph-query-api/router_sessions.py` | `api/app/routers/data_sessions.py` | 190 |
| `graph-query-api/router_search.py` | `api/app/routers/search.py` | 168 |
| `graph-query-api/router_topology.py` | `api/app/routers/topology.py` | 174 |
| `graph-query-api/router_health.py` | `api/app/routers/health.py` | 216 |
| `graph-query-api/router_interactions.py` | `api/app/routers/interactions.py` | 119 |
| `graph-query-api/router_replay.py` | `api/app/routers/replay.py` | 89 |
| `graph-query-api/cosmos_helpers.py` | `api/app/cosmos_helpers.py` | 143 |
| `graph-query-api/fabric_discovery.py` | `api/app/fabric_discovery.py` | 301 |
| `graph-query-api/models.py` | `api/app/data_models.py` | 114 |
| `graph-query-api/log_broadcaster.py` | `api/app/log_broadcaster.py` | 96 |
| **Total moved** | | **1,610** |

### Files CREATED

| File | Lines | Purpose |
|------|-------|---------|
| `api/app/agents.py` | ~80 | AzureAIAgentsProvider singleton, get_orchestrator_agent() |
| `api/app/streaming.py` | ~120 | agent.run(stream=True) → SSE event translation |
| `infra/modules/web-app.bicep` | ~60 | App Service Plan + Web App |
| `startup.sh` | ~5 | gunicorn command |
| **Total created** | **~265** | |

### Files MODIFIED

| File | Before | After | Delta |
|------|--------|-------|-------|
| `api/pyproject.toml` | 18 | ~25 | Deps change + graph-query-api deps merged |
| `api/app/main.py` | ~50 | ~100 | Mount merged routers + static files |
| `api/app/session_manager.py` | 367 | ~250 | −117 (no thread bridge, direct cosmos calls) |
| `scripts/agent_provisioner.py` | 416 | ~120 | −296 (framework does the heavy lifting) |
| `scripts/provision_agents.py` | 183 | ~100 | −83 (simplified) |
| `api/app/routers/sessions.py` | 219 | ~150 | −69 (simplified) |
| `infra/main.bicep` | ~300 | ~280 | Swap container-app for web-app module |
| `deploy.sh` | ~900 | ~850 | Remove container build, add `az webapp up` |
| `azure.yaml` | ~20 | ~15 | Change host to `appservice` |

### Net Code Change

| Category | Lines |
|----------|-------|
| Deleted (files removed) | −1,942 |
| Simplified (modifications) | −565 |
| Created (new files) | +265 |
| Moved (neutral — same code, new location) | 0 |
| **Net** | **−2,242** |

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

### Bicep — Container App → Web App

| Change | Detail |
|--------|--------|
| **Delete** `infra/modules/container-app.bicep` (127 lines) | No more Container App |
| **Create** `infra/modules/web-app.bicep` (~60 lines) | App Service Plan (B1 Linux) + Web App (Python 3.12) |
| **Update** `infra/main.bicep` | Swap module reference, update role assignment principal ID |
| **Delete** Container App Environment Bicep (if separate) | No longer needed |
| Role assignments | Change `containerApp.outputs.principalId` → `webApp.outputs.webAppPrincipalId` |

No changes to: AI Foundry, Cosmos DB, AI Search, Storage — all stay the same.

### Environment Variables — One addition

```
ORCHESTRATOR_AGENT_ID=<id>   # Set by provision_agents.py after creation
```

This replaces the dynamic agent discovery in `agent_ids.py`. After provisioning writes the ID, the Web App reads it at startup.

---

## Frontend Impact

### Zero frontend changes

The `streaming.py` module translates framework events → the same SSE schema (`tool_call.start`, `message.delta`, etc.) that the frontend already consumes. Routes stay at `/api/*` and `/query/*`. **No frontend changes.**

---

## Migration Sequence

| Day | Phase | What Changes | Risk |
|-----|-------|-------------|------|
| 1 | 1-2 | Install framework, create agents.py, verify provider works | Low |
| 2 | 3 | Rewrite provisioner, provision agents | Low |
| 2-3 | 4 | Create streaming.py, update session_manager to use it | Medium |
| 3 | 5 | Delete orchestrator.py + agent_ids.py, test end-to-end | High |
| 3-4 | 6 | Merge graph-query-api into api/, delete OpenAPI proxies | Medium |
| 4-5 | 7 | Create web-app.bicep, delete container-app.bicep, deploy | Medium |

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
| Web App SSE timeout at 230s | **Low** | **Medium** | Set `WEBSITE_RUN_FROM_PACKAGE` and `FUNCTIONS_REQUEST_TIMEOUT` |
| graph-query-api merge breaks import paths | **Low** | **Low** | All routes re-mounted at same `/query/*` prefix |
| Web App cold start latency | **Low** | **Low** | `alwaysOn: true` on B1 plan |

---

## Comparison: v1 (Hosted Agents) vs v2 (Agent Framework + Web App)

| Aspect | v1 (SOTA_DESIGN_IMPLEMENTATION_PLAN.md) | v2 (This document) |
|--------|----------------------------------------|---------------------|
| **Approach** | ImageBasedHostedAgentDefinition + custom container | Agent Framework + Azure Web App |
| **SDK** | `azure-ai-projects>=2.0.0b4` (beta) | `agent-framework>=1.0.0rc1` (RC) |
| **Hosting** | Container Apps (kept) | **Azure Web App** (simplified) |
| **Process model** | 2 processes + nginx + supervisord | **Single process** (gunicorn + FastAPI) |
| **Stability** | Early beta, undocumented RESPONSES protocol | RC → GA soon, active development |
| **ACR required** | Yes (new infrastructure) | **No** |
| **Container image** | Must build, push, version | **No** (`az webapp up`) |
| **CI/CD changes** | New image build pipeline | **Simplified** (zip deploy) |
| **Bicep complexity** | 127 lines (container-app) + ACR | **~60 lines** (web-app) |
| **Lines eliminated** | ~1,169 net | **~2,242 net** |
| **New code** | ~320 lines | **~265 lines** |
| **Frontend changes** | SSE event mapping | **None** |
| **Time estimate** | ~18 working days (7 phases) | **~5 working days** |
| **Infrastructure files removed** | 0 | **3** (Dockerfile, nginx.conf, supervisord.conf) |
| **Fallback** | Restore orchestrator.py | Restore orchestrator.py + re-deploy Container App |

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
