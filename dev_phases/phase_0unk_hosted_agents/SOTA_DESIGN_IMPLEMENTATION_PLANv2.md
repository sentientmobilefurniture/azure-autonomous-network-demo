# SOTA Implementation Plan v2.1 — Declarative Local Agents + Web App

> **Date**: 2026-02-21 (v2.1 — declarative YAML rewrite)  
> **Framework**: `agent-framework` (`1.0.0rc1`) — verified on PyPI  
> **Pattern**: Declarative YAML agents with typed Python tool functions  
> **Hosting**: Azure Web App (replacing Container Apps)  
> **Live endpoint tested**: `https://foundrydev1.services.ai.azure.com/api/projects/devproj1`  
> **Source code**: `/home/hanchoong/microsoft_skills/agent-framework/python/`

---

## Executive Summary

Replace the entire Foundry persistent agent + custom orchestrator architecture with **local declarative agents** defined in YAML, loaded by `AgentFactory` at startup, with tools as typed Python functions organized in modules.

### Key architectural shift

| Aspect | Current | v2.1 (Declarative Local) |
|--------|---------|-------------------------|
| Agent definition | Python `create_agent()` calls to Foundry API | **YAML files** loaded by `AgentFactory` |
| Agent lifecycle | Persistent in Foundry cloud | **In-process** — created at app startup |
| Orchestration | Foundry ConnectedAgentTool (server-side) | **Single agent with all tools** — LLM routes directly |
| Tool definitions | Manual `FunctionToolDefinition` + JSON schema | **Typed Python functions** — framework auto-generates schema |
| Tool execution | `enable_auto_function_calls` in custom thread | **Framework handles internally** in `agent.run()` |
| Streaming | Custom `SSEEventHandler` + `asyncio.Queue` bridge | **`agent.run(stream=True)`** → translate to SSE |
| Provisioning | `provision_agents.py` (416 lines) → Foundry API | **Zero provisioning** — agents load from YAML |
| Agent discovery | `agent_ids.py` TTL-cached polling (236 lines) | **None needed** — agents are local |
| Prompts | Markdown files in `data/scenarios/*/prompts/` | **Inline in YAML** or `=File(path)` references |
| Sessions | Custom `Session` dataclass + Cosmos persistence | **`AgentSession`** + Cosmos persistence |

### The single-agent insight

The 4 sub-agents (GraphExplorer, Telemetry, RunbookKB, HistoricalTicket) existed as separate Foundry agents because `ConnectedAgentTool` required it. In the local model, **one agent can have all tools directly**. The LLM decides which tool to call based on the query — no orchestrator-to-sub-agent delegation overhead.

The frontend still sees progressive tool call disclosure (each tool call shows agent name, query, response) because the framework emits `Content(type='function_call')` events for each tool invocation. We name the tools descriptively (`graph_topology_query`, `telemetry_kql_query`, `search_runbooks`, `search_tickets`, `dispatch_field_engineer`) so the UI can display them as "steps".

### Files eliminated

| File | Lines | Reason |
|------|-------|--------|
| `api/app/orchestrator.py` | 772 | Framework handles everything |
| `api/app/agent_ids.py` | 236 | No Foundry agents to discover |
| `api/app/dispatch.py` | 139 | Moved to `api/app/tools/dispatch.py` |
| `scripts/agent_provisioner.py` | 416 | YAML replaces provisioning |
| `scripts/provision_agents.py` | 183 | No provisioning step |
| `graph-query-api/` (entire) | 1,975 | Merged into api/ |
| `Dockerfile` | 75 | Web App |
| `nginx.conf`, `supervisord.conf` | 95 | Single process |
| **Total eliminated** | **~3,891** | |

### Files created

| File | Lines | Purpose |
|------|-------|---------|
| `api/agents/orchestrator.yaml` | ~40 | Declarative agent definition |
| `api/app/agent_loader.py` | ~30 | `AgentFactory` + tool binding |
| `api/app/streaming.py` | ~150 | `agent.run(stream=True)` → SSE |
| `api/app/tools/__init__.py` | ~20 | Tool bindings export |
| `api/app/tools/graph.py` | ~60 | `graph_topology_query()` |
| `api/app/tools/telemetry.py` | ~60 | `telemetry_kql_query()` |
| `api/app/tools/search.py` | ~80 | `search_runbooks()`, `search_tickets()` |
| `api/app/tools/dispatch.py` | ~140 | `dispatch_field_engineer()` (moved) |
| `infra/modules/web-app.bicep` | ~60 | App Service Plan + Web App |
| **Total created** | **~640** | |

### Net: −3,251 lines

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

### AFTER (Web App — declarative agent, typed tools, single process)

```
Azure Web App (single process, gunicorn + FastAPI)
├── app/ (unified FastAPI)
│   ├── main.py — single entry point, all routes
│   │
│   │ ── Agent layer (declarative YAML) ──
│   ├── agents/
│   │   └── orchestrator.yaml           # THE agent — instructions + tool refs
│   ├── agent_loader.py (~30 lines)     # AgentFactory + load_agent()
│   ├── streaming.py (~150 lines)       # agent.run(stream=True) → SSE events
│   │
│   │ ── Tools (typed Python functions, auto-schema) ──
│   ├── tools/
│   │   ├── __init__.py                 # TOOL_BINDINGS export
│   │   ├── graph.py                    # graph_topology_query(query: str) → str
│   │   ├── telemetry.py               # telemetry_kql_query(query: str) → str
│   │   ├── search.py                  # search_runbooks(query: str) → str
│   │   │                              # search_tickets(query: str) → str
│   │   └── dispatch.py                # dispatch_field_engineer(...) → str
│   │
│   │ ── Session layer ──
│   ├── session_manager.py (~200 lines) # AgentSession + Cosmos persistence
│   ├── sessions.py (156 lines)         # Session dataclass (kept)
│   │
│   │ ── Data layer (merged from graph-query-api) ──
│   ├── routers/
│   │   ├── sessions.py                 # REST/SSE endpoints
│   │   ├── topology.py                 # Fabric topology → graph viewer
│   │   ├── search.py                   # AI Search → frontend viz
│   │   ├── health.py                   # health checks
│   │   ├── interactions.py             # frontend interactions
│   │   └── replay.py                   # session replay
│   ├── cosmos_helpers.py               # Cosmos DB (moved)
│   ├── fabric_discovery.py             # Fabric workspace (moved)
│   └── data_models.py                  # data models (moved)
│
├── static/                              # React build (served by FastAPI)
└── startup.sh                           # gunicorn command

NO MORE:
├── orchestrator.py (772 lines)         → agent.run() handles everything
├── agent_ids.py (236 lines)            → agents are local, no discovery
├── scripts/agent_provisioner.py (416)  → YAML replaces provisioning
├── scripts/provision_agents.py (183)   → no provisioning step
├── graph-query-api/ (entire dir)       → merged into app/
├── Dockerfile, nginx.conf, supervisord → Web App deployment
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

### Step 1.1 — Update api/pyproject.toml

```toml
# BEFORE
dependencies = [
    "azure-ai-projects>=1.0.0,<2.0.0",
    "azure-ai-agents==1.2.0b6",
    "pyyaml>=6.0",
]

# AFTER
dependencies = [
    "agent-framework-azure-ai>=1.0.0rc1",    # Pulls in core + azure-ai-agents
    "agent-framework-declarative>=1.0.0rc1",  # YAML agent loader (AgentFactory)
]
```

### Step 1.2 — Verify

```bash
cd api && uv sync && .venv/bin/python3 -c "
from agent_framework import Agent
from agent_framework_declarative import AgentFactory
print('OK')
"
```

---

## Phase 2: Create Typed Tool Modules (Day 1-2)

### Step 2.1 — Create api/app/tools/ directory

**File**: `api/app/tools/__init__.py`

```python
"""Tool bindings for the declarative agent."""
from .graph import graph_topology_query
from .telemetry import telemetry_kql_query
from .search import search_runbooks, search_tickets
from .dispatch import dispatch_field_engineer

TOOL_BINDINGS = {
    "graph_topology_query": graph_topology_query,
    "telemetry_kql_query": telemetry_kql_query,
    "search_runbooks": search_runbooks,
    "search_tickets": search_tickets,
    "dispatch_field_engineer": dispatch_field_engineer,
}
```

**File**: `api/app/tools/graph.py` — Typed function, schema auto-generated from `Annotated[str, Field(...)]`.

```python
from typing import Annotated
import httpx
from pydantic import Field

async def graph_topology_query(
    query: Annotated[str, Field(description=(
        "GQL query. Uses MATCH/RETURN syntax. "
        "Example: MATCH (r:CoreRouter) RETURN r.RouterId, r.Hostname. "
        "Relationships: MATCH (a)-[r:connects_to]->(b)."
    ))],
) -> str:
    """Execute a GQL graph query against the network topology."""
    from app.config import GRAPH_QUERY_BASE
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(f"{GRAPH_QUERY_BASE}/query/graph", json={"query": query})
        resp.raise_for_status()
        return resp.text
```

**File**: `api/app/tools/telemetry.py`

```python
from typing import Annotated
import httpx
from pydantic import Field

async def telemetry_kql_query(
    query: Annotated[str, Field(description=(
        "KQL query. Start with table name + pipe operators. "
        "Tables: AlertStream, LinkTelemetry."
    ))],
) -> str:
    """Execute a KQL query against network telemetry and alert data."""
    from app.config import GRAPH_QUERY_BASE
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(f"{GRAPH_QUERY_BASE}/query/telemetry", json={"query": query})
        resp.raise_for_status()
        return resp.text
```

**File**: `api/app/tools/search.py`

```python
from typing import Annotated
import httpx
from pydantic import Field

async def search_runbooks(
    query: Annotated[str, Field(description="Search query for operational runbooks and procedures")],
) -> str:
    """Search the runbook knowledge base for procedures and troubleshooting steps."""
    from app.config import GRAPH_QUERY_BASE
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(f"{GRAPH_QUERY_BASE}/query/search",
            json={"agent": "RunbookKBAgent", "query": query, "top": 5})
        resp.raise_for_status()
        return resp.text

async def search_tickets(
    query: Annotated[str, Field(description="Search query for historical incident tickets")],
) -> str:
    """Search historical incident tickets for past resolutions and patterns."""
    from app.config import GRAPH_QUERY_BASE
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(f"{GRAPH_QUERY_BASE}/query/search",
            json={"agent": "HistoricalTicketAgent", "query": query, "top": 5})
        resp.raise_for_status()
        return resp.text
```

**File**: `api/app/tools/dispatch.py` — Move from `api/app/dispatch.py`, unchanged. Already has `Annotated` parameter types and full docstring.

### Step 2.2 — Create YAML agent definition

**File**: `api/agents/orchestrator.yaml`

```yaml
kind: Prompt
name: NetworkInvestigator
description: Autonomous NOC investigator agent
instructions: |
  You are an autonomous Network Operations Center (NOC) AI investigator.
  
  When you receive a network alert, systematically investigate it:
  1. Graph topology — Use graph_topology_query to explore the network.
  2. Telemetry & alerts — Use telemetry_kql_query for evidence.
  3. Runbooks — Use search_runbooks for procedures.
  4. Historical tickets — Use search_tickets for past incidents.
  5. Diagnosis — Synthesize findings.
  6. Action — If needed, use dispatch_field_engineer.
  
  Always explain your reasoning at each step.

model:
  id: =Env.MODEL_DEPLOYMENT_NAME
  connection:
    kind: Remote
    endpoint: =Env.AZURE_AI_PROJECT_ENDPOINT

tools:
  - kind: function
    name: graph_topology_query
    bindings: { graph_topology_query: graph_topology_query }
  - kind: function
    name: telemetry_kql_query
    bindings: { telemetry_kql_query: telemetry_kql_query }
  - kind: function
    name: search_runbooks
    bindings: { search_runbooks: search_runbooks }
  - kind: function
    name: search_tickets
    bindings: { search_tickets: search_tickets }
  - kind: function
    name: dispatch_field_engineer
    bindings: { dispatch_field_engineer: dispatch_field_engineer }
```

### Step 2.3 — Create agent loader

**File**: `api/app/agent_loader.py`

```python
"""Load the declarative agent from YAML at startup."""
import os
from pathlib import Path
from agent_framework_declarative import AgentFactory
from app.tools import TOOL_BINDINGS

_agent = None
AGENTS_DIR = Path(__file__).parent.parent / "agents"

def load_agent():
    global _agent
    # Map our env vars to what the framework expects
    os.environ.setdefault("AZURE_AI_PROJECT_ENDPOINT",
        os.environ.get("PROJECT_ENDPOINT", ""))
    os.environ.setdefault("AZURE_AI_MODEL_DEPLOYMENT_NAME",
        os.environ.get("MODEL_DEPLOYMENT_NAME", ""))
    factory = AgentFactory(bindings=TOOL_BINDINGS)
    _agent = factory.create_agent_from_yaml_path(
        str(AGENTS_DIR / "orchestrator.yaml"))
    return _agent

def get_agent():
    if _agent is None:
        raise RuntimeError("Agent not loaded. Call load_agent() at startup.")
    return _agent
```

---

## Phase 3: Create Streaming Translator (Day 2)

**File**: `api/app/streaming.py`

Translates `agent.run(stream=True)` → our existing SSE schema so the frontend is unchanged.

```python
"""Stream agent.run() events → SSE events matching the frontend schema."""
import json, uuid
from datetime import datetime, timezone
from typing import AsyncGenerator
from agent_framework import AgentSession

async def stream_agent_to_sse(
    agent, alert_text: str, session: AgentSession | None = None,
) -> AsyncGenerator[dict, None]:
    msg_id = str(uuid.uuid4())
    step_counter = 0
    accumulated_text = ""
    message_started = False

    yield {"event": "run.start", "data": json.dumps({
        "run_id": "", "alert": alert_text,
        "timestamp": datetime.now(timezone.utc).isoformat()})}

    try:
        stream = agent.run(alert_text, stream=True, session=session)
        async for update in stream:
            for content in (update.contents or []):
                if content.type == "text" and content.text:
                    if not message_started:
                        message_started = True
                        yield {"event": "message.start",
                               "data": json.dumps({"id": msg_id})}
                    accumulated_text += content.text
                    yield {"event": "message.delta",
                           "data": json.dumps({"id": msg_id, "text": content.text})}

                elif content.type == "function_call":
                    step_counter += 1
                    yield {"event": "tool_call.start", "data": json.dumps({
                        "id": getattr(content, 'id', '') or str(uuid.uuid4()),
                        "step": step_counter,
                        "agent": getattr(content, 'name', ''),
                        "query": (getattr(content, 'arguments', '') or '')[:500],
                        "timestamp": datetime.now(timezone.utc).isoformat()})}

                elif content.type == "function_result":
                    yield {"event": "tool_call.complete", "data": json.dumps({
                        "id": getattr(content, 'call_id', ''),
                        "step": step_counter,
                        "agent": getattr(content, 'name', ''),
                        "duration": "", "query": "",
                        "response": (getattr(content, 'text', '') or '')[:2000],
                        "timestamp": datetime.now(timezone.utc).isoformat()})}

        if accumulated_text:
            yield {"event": "message.complete",
                   "data": json.dumps({"id": msg_id, "text": accumulated_text})}
        yield {"event": "run.complete",
               "data": json.dumps({"steps": step_counter, "time": ""})}

    except Exception as e:
        yield {"event": "error",
               "data": json.dumps({"message": str(e)})}
```

---

## Phase 4: Wire Agent Into Session Manager (Day 2-3)

### Step 4.1 — Update session_manager.py

Replace `run_orchestrator_session()` calls with `stream_agent_to_sse()`:

```python
# BEFORE
from app.orchestrator import run_orchestrator_session
async for event in run_orchestrator_session(
    session.alert_text, session._cancel_event):
    session.push_event(event)

# AFTER
from app.agent_loader import get_agent
from app.streaming import stream_agent_to_sse
agent = get_agent()
async for event in stream_agent_to_sse(agent, session.alert_text):
    session.push_event(event)
```

### Step 4.2 — Update main.py lifespan

```python
from contextlib import asynccontextmanager
from app.agent_loader import load_agent

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_agent()
    yield

app = FastAPI(lifespan=lifespan)
```

### Step 4.3 — Delete replaced files

```bash
rm api/app/orchestrator.py       # 772 lines → framework handles it
rm api/app/agent_ids.py          # 236 lines → no Foundry agents
rm api/app/dispatch.py           # moved to api/app/tools/dispatch.py
rm scripts/agent_provisioner.py  # 416 lines → YAML
rm scripts/provision_agents.py   # 183 lines → no provisioning
```

---

## Phase 5: Verify agent flow end-to-end (Day 3)

```bash
# 1. Compile check
cd api && python3 -m py_compile app/agent_loader.py
cd api && python3 -m py_compile app/streaming.py
cd api && python3 -m py_compile app/tools/__init__.py

# 2. Start locally
cd api && source ../azure_config.env && uv run uvicorn app.main:app --port 8000

# 3. Test SSE stream
curl -s -N http://localhost:8000/api/sessions/{id}/stream
```

Frontend should show tool calls streaming in real-time — same visual as before.

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
| `api/app/orchestrator.py` | 772 | `agent.run()` handles streaming + tool execution |
| `api/app/agent_ids.py` | 236 | Agents are local (YAML), no Foundry discovery |
| `api/app/dispatch.py` | 139 | Moved to `api/app/tools/dispatch.py` |
| `scripts/agent_provisioner.py` | 416 | YAML replaces provisioning |
| `scripts/provision_agents.py` | 183 | No provisioning step |
| `graph-query-api/router_graph.py` | 76 | Tools call graph-query-api directly |
| `graph-query-api/router_telemetry.py` | 74 | Tools call graph-query-api directly |
| `graph-query-api/openapi/templates/*.yaml` | 122 | No more OpenAPI specs |
| `graph-query-api/main.py` | 193 | Merged into api/app/main.py |
| `graph-query-api/config.py` | 172 | Merged into api/app/paths.py |
| `supervisord.conf` | 40 | Single process |
| `nginx.conf` | 55 | FastAPI serves static files |
| `Dockerfile` | 75 | Web App deployment |
| `infra/modules/container-app.bicep` | 127 | Replaced by web-app.bicep |
| **Total deleted** | **~2,680** | |

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
| `api/agents/orchestrator.yaml` | ~40 | Declarative agent definition (instructions + tool refs) |
| `api/app/agent_loader.py` | ~30 | `AgentFactory(bindings=TOOL_BINDINGS)` + `load_agent()` |
| `api/app/streaming.py` | ~150 | `agent.run(stream=True)` → SSE event translation |
| `api/app/tools/__init__.py` | ~20 | `TOOL_BINDINGS` export |
| `api/app/tools/graph.py` | ~25 | `graph_topology_query()` typed function |
| `api/app/tools/telemetry.py` | ~25 | `telemetry_kql_query()` typed function |
| `api/app/tools/search.py` | ~40 | `search_runbooks()` + `search_tickets()` |
| `api/app/tools/dispatch.py` | ~140 | `dispatch_field_engineer()` (moved, unchanged) |
| `infra/modules/web-app.bicep` | ~60 | App Service Plan + Web App |
| `startup.sh` | ~5 | gunicorn command |
| **Total created** | **~535** | |

### Files MODIFIED

| File | Before | After | Delta |
|------|--------|-------|-------|
| `api/pyproject.toml` | 18 | ~25 | SDK change + graph-query-api deps merged |
| `api/app/main.py` | ~50 | ~100 | Mount merged routers + static files + lifespan |
| `api/app/session_manager.py` | 367 | ~200 | −167 (stream_agent_to_sse replaces thread bridge) |
| `api/app/routers/sessions.py` | 219 | ~150 | −69 |
| `infra/main.bicep` | ~300 | ~280 | Swap container-app for web-app module |
| `deploy.sh` | ~1120 | ~1000 | Remove container + agent provisioning steps |
| `azure.yaml` | ~20 | ~15 | Change host to `appservice` |

### Net Code Change

| Category | Lines |
|----------|-------|
| Deleted (files removed) | −2,680 |
| Simplified (modifications) | −236 |
| Created (new files) | +535 |
| Moved (neutral) | 0 |
| **Net** | **−2,381** |

---

## SDK / Package Dependencies

### Current

```toml
"azure-ai-projects>=1.0.0,<2.0.0"   # GA
"azure-ai-agents==1.2.0b6"           # beta
"pyyaml>=6.0"                       # OpenAPI spec parsing
```

### After

```toml
"agent-framework-azure-ai>=1.0.0rc1"          # RC — pulls in core + azure-ai-agents
"agent-framework-declarative>=1.0.0rc1"       # RC — YAML agent loader (AgentFactory)
```

`pyyaml` removed (declarative package handles YAML). `azure-ai-projects` and `azure-ai-agents` are transitive deps — no direct pin needed.

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
| 1 | 1 | Install agent-framework + declarative package | Low |
| 1-2 | 2 | Create `api/app/tools/` module + `agents/orchestrator.yaml` + `agent_loader.py` | Low |
| 2 | 3 | Create `streaming.py` (agent.run → SSE translator) | Medium |
| 2-3 | 4 | Wire into session_manager, delete orchestrator.py + agent_ids.py + provisioners | High |
| 3 | 5 | End-to-end test: alert → tool calls streaming → diagnosis | High |
| 3-4 | 6 | Merge graph-query-api into api/ | Medium |
| 4-5 | 7 | Web App Bicep + deploy.sh rewrite | Medium |

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
# Declarative agent loading
from agent_framework_declarative import AgentFactory

# Core types
from agent_framework import Agent, AgentSession, AgentResponse, AgentResponseUpdate
from agent_framework import tool  # @tool decorator (if needed)

# Typed tool parameters
from typing import Annotated
from pydantic import Field

# Tool binding pattern
from app.tools import TOOL_BINDINGS
factory = AgentFactory(bindings=TOOL_BINDINGS)
agent = factory.create_agent_from_yaml_path("agents/orchestrator.yaml")

# Streaming
result = await agent.run("alert text")           # non-streaming
stream = agent.run("alert text", stream=True)     # streaming
async for update in stream:
    for content in update.contents:
        content.type  # 'text', 'function_call', 'function_result', 'usage'
        content.text  # text delta (if type=='text')

# Sessions (multi-turn)
session = agent.create_session()
r1 = await agent.run("initial alert", session=session)
r2 = await agent.run("follow up", session=session)
data = session.to_dict()  # serialize to Cosmos
session = AgentSession.from_dict(data)  # restore
```
