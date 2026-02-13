# V5 Graph Query Refactor — Implementation Plan

## Status: PLANNED
## Date: 2026-02-13

---

## 1. Problem Statement

The current architecture uses **OpenApiTool** on Foundry sub-agents (GraphExplorer, Telemetry) to call a separate **graph-query-api** Container App. This creates a network security problem:

1. **Foundry → Container App**: Foundry's OpenApiTool makes HTTP calls from Microsoft-managed IPs that we don't control. The Container App must expose external ingress with anonymous auth (`OpenApiAnonymousAuthDetails`) — an unauthenticated public endpoint.
2. **Container App → Cosmos DB**: The Container App connects to Cosmos DB Gremlin via WSS. Cosmos DB IP firewall rules block any IP not in the allow list, causing **HTTP 403 Forbidden** errors when the Container App's outbound IP or local dev IP isn't whitelisted.
3. **Key-based auth**: Gremlin wire protocol does not support `DefaultAzureCredential`. The primary key is passed as a Container App secret, but the overall chain (anonymous HTTP → key-based WSS) is fragile.

**Root cause**: Two-hop data access (Foundry → Container App → Cosmos DB) doubles the network/auth surface area. Each hop needs independent security configuration, and Foundry's server-side execution model means we can't use VNet-internal ingress.

---

## 2. Solution: Hybrid FunctionTool Architecture

### Architecture Decision

**Eliminate the graph-query-api as a separate service.** Move graph and telemetry query functions into the **API process** and register them as `FunctionTool` on the **Orchestrator agent directly**.

This is possible because:
- `FunctionTool` with `enable_auto_function_calls()` executes **in-process** (client-side) during `runs.create_and_process()`
- The API process runs inside the Container Apps VNet → can reach Cosmos DB via private endpoint
- Graph and telemetry queries become simple function calls, not HTTP hops

### Critical Constraint: ConnectedAgentTool vs FunctionTool

The current architecture uses `ConnectedAgentTool` sub-agents for all 4 specialists. Sub-agents run **server-side in Foundry** where `FunctionTool` callbacks cannot be reached.

**Solution**: Restructure the agent hierarchy:

| Before (V4) | After (V5) |
|---|---|
| Orchestrator → ConnectedAgentTool × 4 | Orchestrator → FunctionTool (graph, telemetry) + ConnectedAgentTool × 2 |
| GraphExplorer sub-agent + OpenApiTool | *Removed* — logic folded into Orchestrator FunctionTool |
| Telemetry sub-agent + OpenApiTool | *Removed* — logic folded into Orchestrator FunctionTool |
| RunbookKB sub-agent + AzureAISearchTool | RunbookKB sub-agent + AzureAISearchTool *(unchanged)* |
| HistoricalTicket sub-agent + AzureAISearchTool | HistoricalTicket sub-agent + AzureAISearchTool *(unchanged)* |

### Target Architecture

```
┌──────────────┐      POST /api/alert       ┌──────────────────────────────────┐
│   Frontend   │  ───────────────────────▶   │   FastAPI API + Query Engine     │
│  React/Vite  │  ◀─────── SSE stream ────  │   (Container App, VNet, MI)      │
│  :5173       │                             │   :8000                          │
└──────────────┘                             └────────┬────────────────┬────────┘
                                                      │                │
                                         azure-ai-agents SDK     FunctionTool
                                          (streaming + manual     auto-executes
                                           function handling)     in-process
                                                      │                │
                                                      ▼                │
                                          ┌───────────────────────┐    │
                                          │   Orchestrator Agent  │    │
                                          │   (Azure AI Foundry)  │    │
                                          │                       │    │
                                          │  Tools:               │    │
                                          │   • query_graph ──────┼────┤► Cosmos Gremlin
                                          │   • query_telemetry ──┼────┤► Cosmos NoSQL
                                          │   • ConnectedAgent ───┼──┐ │
                                          │   • ConnectedAgent ───┼┐ │ │
                                          └───────────────────────┘│ │ │
                                                                   │ │ │
                                          ┌────────────────────────┘ │ │
                                          ▼                          ▼ │
                                 ┌──────────────┐  ┌─────────────────┐ │
                                 │ RunbookKB    │  │ HistoricalTicket│ │
                                 │ Agent        │  │ Agent           │ │
                                 │ (AI Search)  │  │ (AI Search)     │ │
                                 └──────────────┘  └─────────────────┘ │
                                                                       │
                                          ┌────────────────────────────┘
                                          ▼ (via private endpoint)
                                 ┌────────────────────────────────────┐
                                 │          Cosmos DB                 │
                                 │  ┌─ Gremlin (networkgraph)        │
                                 │  └─ NoSQL   (telemetrydb)         │
                                 │  publicNetworkAccess: Disabled     │
                                 └────────────────────────────────────┘
```

### What This Eliminates

- graph-query-api Container App (no separate service to deploy, scale, or secure)
- External ingress with anonymous auth (attack surface removed)
- OpenAPI spec maintenance (cosmosdb.yaml, mock.yaml)
- ACR image for graph-query-api
- Cosmos DB IP firewall gymnastics (private endpoint only)
- `GRAPH_QUERY_API_URI` configuration

### What This Preserves

- Backend abstraction (`GraphBackend` Protocol — cosmosdb, mock)
- graph-query-api code remains as a **library**, not a service
- RunbookKB and HistoricalTicket agents unchanged
- SSE streaming to frontend
- Retry with exponential backoff on Gremlin errors
- Error tolerance (errors-as-data pattern)

---

## 3. Streaming + FunctionTool: The Technical Challenge

The current orchestrator uses `runs.stream()` with `AgentEventHandler` for SSE streaming. `FunctionTool` with `enable_auto_function_calls()` uses `runs.create_and_process()` which is **synchronous and blocking** — incompatible with the streaming architecture.

### Solution: Manual Function Call Handling in the Stream Handler

Instead of `enable_auto_function_calls()`, handle `requires_action` events manually in `SSEEventHandler`:

```python
# In the streaming loop:
with agents_client.runs.stream(
    thread_id=thread.id,
    agent_id=orchestrator_id,
    event_handler=handler,
) as stream:
    stream.until_done()

# If the run requires function calls, handle them and re-stream
while handler.pending_tool_calls:
    tool_outputs = []
    for tc in handler.pending_tool_calls:
        result = execute_function(tc.function.name, tc.function.arguments)
        tool_outputs.append({"tool_call_id": tc.id, "output": result})

    # Submit tool outputs and continue streaming
    handler.pending_tool_calls = []
    with agents_client.runs.submit_tool_outputs_and_stream(
        thread_id=thread.id,
        run_id=handler.current_run_id,
        tool_outputs=tool_outputs,
        event_handler=handler,
    ) as stream:
        stream.until_done()
```

The handler captures `requires_action` status in `on_thread_run()` and exposes the pending tool calls for the outer loop to process.

---

## 4. Implementation Phases

### Phase 1: Extract Query Functions as a Library (api-side)

**Goal**: Make graph-query-api query logic importable from the API process without running a separate server.

#### 1.1 Create `api/app/graph_queries.py`

A thin module that wraps the existing backend code:

```python
"""
In-process graph and telemetry query functions for FunctionTool.

Reuses the graph-query-api backend layer (CosmosDBGremlinBackend, mock)
and telemetry query logic, but runs in-process instead of via HTTP.
"""

import asyncio
import json
import logging
import os
import threading

from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential

logger = logging.getLogger(__name__)

# ── Graph query ─────────────────────────────────────────────────────

def query_graph(query: str) -> str:
    """Execute a Gremlin query against the network topology graph.

    Args:
        query: A Gremlin traversal query string.

    Returns:
        JSON string with {columns, data} or {error} on failure.
    """
    # Implementation: reuse CosmosDBGremlinBackend._submit_query + _normalise_results
    ...

# ── Telemetry query ─────────────────────────────────────────────────

def query_telemetry(query: str, container_name: str = "AlertStream") -> str:
    """Execute a Cosmos SQL query against telemetry data.

    Args:
        query: A Cosmos DB SQL query string.
        container_name: Target container — "AlertStream" or "LinkTelemetry".

    Returns:
        JSON string with {columns, rows} or {error} on failure.
    """
    ...
```

**Key decisions**:
- Functions return `str` (JSON) because FunctionTool requires string return values
- Error handling: catch all exceptions, return `{"error": "..."}` — never raise
- Reuse `_submit_query()` and `_normalise_results()` from backends/cosmosdb.py
- Thread-safe singleton clients (same pattern as current graph-query-api)

#### 1.2 Add data-access dependencies to `api/pyproject.toml`

```toml
dependencies = [
    # ... existing ...
    "azure-cosmos>=4.9.0",
    "gremlinpython>=3.7.0",
]
```

#### 1.3 Port and adapt backend code

- Copy `_submit_query()`, `_normalise_results()`, `_flatten_valuemap()` from `graph-query-api/backends/cosmosdb.py` into `api/app/graph_queries.py`
- Copy telemetry query logic from `graph-query-api/router_telemetry.py`
- Remove FastAPI/HTTP concerns (no Request/Response objects)
- Keep retry logic, dead-client detection, and thread-safe singletons intact

**Files created/modified**:
- `api/app/graph_queries.py` — NEW
- `api/pyproject.toml` — MODIFIED (add cosmos + gremlin deps)

---

### Phase 2: Refactor Orchestrator for Manual FunctionTool Handling

**Goal**: Modify the streaming orchestrator to handle `requires_action` events for FunctionTool calls while maintaining SSE streaming to the frontend.

#### 2.1 Modify `SSEEventHandler` in `api/app/orchestrator.py`

Add detection of `requires_action` status:

```python
class SSEEventHandler(AgentEventHandler):
    def __init__(self):
        super().__init__()
        # ... existing fields ...
        self.pending_tool_calls = []
        self.current_run_id = None

    def on_thread_run(self, run):
        self.current_run_id = run.id
        status = run.status.value if hasattr(run.status, "value") else str(run.status)

        if status == "requires_action":
            # Extract function tool calls
            if hasattr(run, "required_action") and run.required_action:
                submit = run.required_action.submit_tool_outputs
                if submit and submit.tool_calls:
                    self.pending_tool_calls = list(submit.tool_calls)
        # ... rest of existing on_thread_run ...
```

#### 2.2 Modify the streaming loop in `_thread_target()`

Replace the simple `stream.until_done()` with a loop that handles function calls:

```python
def _run_with_function_calls(agents_client, thread_id, agent_id, handler):
    """Stream a run, handling FunctionTool calls inline."""
    MAX_FUNCTION_ROUNDS = 10  # safety limit

    with agents_client.runs.stream(
        thread_id=thread_id,
        agent_id=agent_id,
        event_handler=handler,
    ) as stream:
        stream.until_done()

    for _ in range(MAX_FUNCTION_ROUNDS):
        if not handler.pending_tool_calls:
            break

        # Execute each function call in-process
        tool_outputs = []
        for tc in handler.pending_tool_calls:
            fn_name = tc.function.name
            fn_args = tc.function.arguments
            _put("step_start", {
                "step": handler.ui_step + 1,
                "agent": f"FunctionTool:{fn_name}",
            })
            t0 = time.time()

            result = _execute_function(fn_name, fn_args)

            duration = f"{time.time() - t0:.1f}s"
            handler.ui_step += 1
            _put("step_complete", {
                "step": handler.ui_step,
                "agent": fn_name,
                "duration": duration,
                "query": fn_args[:500],
                "response": result[:2000],
            })

            tool_outputs.append({
                "tool_call_id": tc.id,
                "output": result,
            })

        handler.pending_tool_calls = []

        # Submit results and continue streaming
        with agents_client.runs.submit_tool_outputs_and_stream(
            thread_id=thread_id,
            run_id=handler.current_run_id,
            tool_outputs=tool_outputs,
            event_handler=handler,
        ) as stream:
            stream.until_done()
```

#### 2.3 Create function dispatcher

```python
from app.graph_queries import query_graph, query_telemetry

FUNCTION_REGISTRY = {
    "query_graph": query_graph,
    "query_telemetry": query_telemetry,
}

def _execute_function(name: str, arguments: str) -> str:
    """Execute a registered function by name. Returns JSON string."""
    fn = FUNCTION_REGISTRY.get(name)
    if not fn:
        return json.dumps({"error": f"Unknown function: {name}"})
    try:
        kwargs = json.loads(arguments) if isinstance(arguments, str) else arguments
        return fn(**kwargs)
    except Exception as e:
        logger.exception("FunctionTool %s failed", name)
        return json.dumps({"error": f"{type(e).__name__}: {str(e)}"})
```

**Files modified**:
- `api/app/orchestrator.py` — MODIFIED (add function call handling loop)

---

### Phase 3: Refactor Agent Provisioning

**Goal**: Restructure the agent hierarchy — remove GraphExplorer and Telemetry sub-agents, add FunctionTool to the Orchestrator.

#### 3.1 Modify `scripts/provision_agents.py`

**Remove**:
- `create_graph_explorer_agent()` function
- `create_telemetry_agent()` function
- `_make_graph_openapi_tool()` and `_make_telemetry_openapi_tool()`
- `_load_openapi_spec()` helper
- OpenApiTool imports

**Add**:
- `FunctionTool` import from `azure.ai.agents.models`
- Function definitions for `query_graph` and `query_telemetry` registered on the Orchestrator

**Modify** `create_orchestrator()`:

```python
from azure.ai.agents.models import ConnectedAgentTool, FunctionTool

def create_orchestrator(agents_client, model: str, sub_agents: list[dict]) -> dict:
    """Create the Orchestrator with FunctionTool (data) + ConnectedAgentTool (search)."""
    instructions, description = load_orchestrator_prompt()  # updated prompt

    # FunctionTool for graph + telemetry queries (executed client-side)
    function_tool = FunctionTool(functions=[query_graph, query_telemetry])

    # ConnectedAgentTool for search-based sub-agents (executed server-side)
    connected_tools = []
    for sa in sub_agents:
        ct = ConnectedAgentTool(id=sa["id"], name=sa["name"], description=sa["description"])
        connected_tools.extend(ct.definitions)

    all_tools = function_tool.definitions + connected_tools

    agent = agents_client.create_agent(
        model=model,
        name="Orchestrator",
        instructions=instructions,
        tools=all_tools,
    )
    return {"id": agent.id, "name": agent.name, "description": description}
```

#### 3.2 Update Orchestrator prompt

Merge the GraphExplorer and Telemetry agent prompts into the Orchestrator's instructions:
- Append graph schema (from `data/prompts/graph_explorer/core_schema.md`)
- Append Gremlin language reference (from `data/prompts/graph_explorer/language_gremlin.md`)
- Append telemetry query guidance (from `data/prompts/foundry_telemetry_agent_v2.md`)
- Add tool-usage instructions: "Use `query_graph` for topology, `query_telemetry` for time-series data"

#### 3.3 Update `agent_ids.json` schema

The sub_agents map shrinks from 4 to 2:

```json
{
  "orchestrator": { "id": "...", "name": "Orchestrator" },
  "sub_agents": {
    "RunbookKBAgent": { "id": "...", "name": "RunbookKBAgent" },
    "HistoricalTicketAgent": { "id": "...", "name": "HistoricalTicketAgent" }
  }
}
```

**Files modified**:
- `scripts/provision_agents.py` — MODIFIED (major refactor)
- `data/prompts/foundry_orchestrator_agent.md` — MODIFIED (merged prompts)

---

### Phase 4: Infrastructure Changes

**Goal**: Remove graph-query-api Container App, lock down Cosmos DB, update RBAC.

#### 4.1 Remove graph-query-api Container App from Bicep

In `infra/main.bicep`:
- Remove the `graphQueryApi` Container App module invocation
- Remove `GRAPH_QUERY_API_URI` output
- Remove `GRAPH_QUERY_API_PRINCIPAL_ID` output
- Keep the API Container App and add data-access env vars to it

#### 4.2 Add Cosmos DB env vars to the API Container App

```bicep
// In the API Container App env block:
{ name: 'COSMOS_GREMLIN_ENDPOINT', value: cosmosGremlin.outputs.gremlinEndpoint }
{ name: 'COSMOS_GREMLIN_DATABASE', value: 'networkgraph' }
{ name: 'COSMOS_GREMLIN_GRAPH', value: 'topology' }
{ name: 'COSMOS_GREMLIN_PRIMARY_KEY', secretRef: 'cosmos-gremlin-key' }
{ name: 'COSMOS_NOSQL_ENDPOINT', value: cosmosGremlin.outputs.noSqlEndpoint }
{ name: 'COSMOS_NOSQL_DATABASE', value: 'telemetrydb' }
```

#### 4.3 Lock down Cosmos DB

In `infra/modules/cosmos-gremlin.bicep`:

```bicep
resource cosmosAccount '...' = {
  properties: {
    publicNetworkAccess: 'Disabled'  // was 'Enabled'
    // ... rest unchanged
  }
}
```

All access goes through private endpoints. No more IP firewall rules.

#### 4.4 Update RBAC

In `infra/modules/roles.bicep`:
- Assign **Cosmos DB Built-in Data Contributor** to the **API Container App's** managed identity (for NoSQL telemetry queries)
- Remove the graph-query-api principal ID role assignments

**Note**: Gremlin still uses key-based auth (wire protocol limitation). The key is stored as a Container App secret — same security posture as before, just on the API Container App instead of graph-query-api.

#### 4.5 Remove graph-query-api from `azure.yaml`

```yaml
# Remove:
# graphQueryApi:
#   host: containerapp
#   ...
```

**Files modified**:
- `infra/main.bicep` — MODIFIED
- `infra/modules/cosmos-gremlin.bicep` — MODIFIED
- `infra/modules/roles.bicep` — MODIFIED
- `azure.yaml` — MODIFIED

---

### Phase 5: Local Development & Testing

#### 5.1 Update `azure_config.env.template`

- Remove `GRAPH_QUERY_API_URI`
- Remove `GRAPH_QUERY_API_PRINCIPAL_ID`
- Keep all `COSMOS_*` variables (now consumed by the API directly)

#### 5.2 Add mock/offline mode

Keep the `GRAPH_BACKEND=mock` path working for local dev without Cosmos DB:

```python
# In api/app/graph_queries.py:
GRAPH_BACKEND = os.environ.get("GRAPH_BACKEND", "cosmosdb")

def query_graph(query: str) -> str:
    if GRAPH_BACKEND == "mock":
        return _mock_graph_query(query)
    return _cosmos_graph_query(query)
```

#### 5.3 Test plan

| Test | Command | Validates |
|------|---------|-----------|
| Unit: graph query functions | `uv run pytest api/tests/test_graph_queries.py` | FunctionTool functions return valid JSON, handle errors |
| Unit: function dispatcher | `uv run pytest api/tests/test_orchestrator.py` | `_execute_function()` routes correctly, handles unknown functions |
| Integration: mock backend | `GRAPH_BACKEND=mock uv run uvicorn app.main:app` | Full SSE flow with mock data, no Cosmos DB required |
| Integration: Cosmos DB | `source azure_config.env && uv run uvicorn app.main:app` | Real Gremlin + NoSQL queries via private endpoint |
| E2E: agent provisioning | `uv run python provision_agents.py --force` | Orchestrator created with FunctionTool + ConnectedAgentTool |
| E2E: alert flow | `curl -X POST /api/alert -d '{"text":"..."}' ` | Full SSE stream with function call steps visible in UI |

#### 5.4 Local dev: Cosmos DB access

For local development (outside VNet), temporarily allow your IP:
```bash
MY_IP=$(curl -s ifconfig.me)
az cosmosdb update -n <account> -g <rg> --ip-range-filter "$MY_IP"
```

Or use `GRAPH_BACKEND=mock` for fully offline development.

---

### Phase 6: Cleanup

#### 6.1 Deprecate graph-query-api as a service

- Keep `graph-query-api/` directory as reference / library code
- Remove its `Dockerfile`
- Remove its ACR build step from `azure.yaml` / `deploy.sh`
- Update `documentation/ARCHITECTURE.md` with the new diagram

#### 6.2 Frontend updates

The SSE event stream format changes slightly:
- `step_complete` events for graph/telemetry queries will show `agent: "query_graph"` or `agent: "query_telemetry"` instead of `agent: "GraphExplorerAgent"`
- Update the agent name mapping in the frontend `AgentStep` component to display friendly names

#### 6.3 Update documentation

- `ARCHITECTURE.md` — new diagram, remove graph-query-api service
- `TASKS.md` — mark completed
- `README.md` — update quickstart / deployment instructions
- Remove `GRAPH_QUERY_API_URI` from all config references

---

## 5. Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Orchestrator prompt too large (merged instructions) | Token limit, degraded reasoning | Keep graph/telemetry instructions concise; test token count < 8K |
| `requires_action` not captured in streaming | Function calls never execute | Unit test the handler with mock runs; validate in integration |
| Gremlin client blocks the event loop | API becomes unresponsive | Already using `asyncio.to_thread()` — keep this pattern |
| Loss of independent scaling | Graph queries can't scale separately | Monitor CPU/memory; API Container App can scale 1→10 replicas |
| Rollback needed | Service downtime | Keep graph-query-api code intact; can re-provision old agents in minutes |

---

## 6. Migration Path

### Zero-downtime migration sequence

1. **Deploy Phase 1-2**: API gets query functions + function call handling, but old agents still work (graph-query-api still running)
2. **Test Phase 3**: Re-provision agents with `--force` → new Orchestrator has FunctionTool, old sub-agents deleted
3. **Validate**: Run E2E tests against the new architecture
4. **Deploy Phase 4**: Remove graph-query-api Container App, lock down Cosmos DB
5. **Cleanup Phase 6**: Documentation, frontend labels

At any point, rollback = `provision_agents.py --force` with the old code + redeploy graph-query-api.

---

## 7. File Change Summary

| File | Action | Description |
|------|--------|-------------|
| `api/app/graph_queries.py` | CREATE | In-process graph + telemetry query functions |
| `api/pyproject.toml` | MODIFY | Add azure-cosmos, gremlinpython deps |
| `api/app/orchestrator.py` | MODIFY | Add manual FunctionTool handling in stream loop |
| `scripts/provision_agents.py` | MODIFY | Remove OpenApiTool agents, add FunctionTool to Orchestrator |
| `data/prompts/foundry_orchestrator_agent.md` | MODIFY | Merge graph + telemetry instructions |
| `infra/main.bicep` | MODIFY | Remove graph-query-api CA, add Cosmos env to API CA |
| `infra/modules/cosmos-gremlin.bicep` | MODIFY | `publicNetworkAccess: 'Disabled'` |
| `infra/modules/roles.bicep` | MODIFY | Reassign RBAC to API CA identity |
| `azure.yaml` | MODIFY | Remove graph-query-api service |
| `azure_config.env.template` | MODIFY | Remove GRAPH_QUERY_API_URI |
| `documentation/ARCHITECTURE.md` | MODIFY | New architecture diagram |
| `graph-query-api/Dockerfile` | DELETE | No longer a separate service |
| Frontend agent name mapping | MODIFY | Update step labels for FunctionTool names |

---

## 8. Security Posture Comparison

| Aspect | Before (V4) | After (V5) |
|--------|-------------|-------------|
| Public endpoints | graph-query-api (anonymous, external ingress) | None (API behind SWA proxy or internal) |
| Cosmos DB network | Public + IP firewall (fragile) | Private endpoint only (`publicNetworkAccess: Disabled`) |
| Cosmos NoSQL auth | Managed Identity (RBAC) | Managed Identity (RBAC) — unchanged |
| Cosmos Gremlin auth | Primary key (Container App secret) | Primary key (Container App secret) — unchanged* |
| Attack surface | 2 Container Apps, 1 public endpoint | 1 Container App, 0 public data endpoints |
| Credential exposure | Key in graph-query-api env | Key in API env (same posture, fewer services) |

*Gremlin wire protocol limitation — key-based auth is currently the only option. If/when Microsoft adds Entra ID support for the Gremlin endpoint, the migration is isolated to `graph_queries.py`.

---

## 9. Estimated Effort

| Phase | Effort | Dependencies |
|-------|--------|-------------|
| Phase 1: Extract query functions | 2-3 hours | None |
| Phase 2: Orchestrator refactor | 3-4 hours | Phase 1 |
| Phase 3: Agent provisioning | 2-3 hours | Phase 1 |
| Phase 4: Infrastructure | 1-2 hours | Phases 1-3 validated |
| Phase 5: Testing | 2-3 hours | Phases 1-3 |
| Phase 6: Cleanup | 1-2 hours | All phases |
| **Total** | **~12-16 hours** | |
