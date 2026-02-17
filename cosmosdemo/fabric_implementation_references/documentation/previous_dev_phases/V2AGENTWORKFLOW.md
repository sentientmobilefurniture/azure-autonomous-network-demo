# V2 Agent Workflow — Direct GQL Queries, No Fabric Data Agent

## TL;DR

Replace `FabricTool` (which proxies through Fabric Data Agents) with direct
REST calls to the Fabric GraphModel `executeQuery` API and Eventhouse KQL
API. Expose these as `FunctionTool` callables on the Foundry agents.
**Stay on Foundry** — there is no good reason to leave it. The
`ConnectedAgentTool` orchestration pattern, `AzureAISearchTool`, SSE
streaming, and `ToolSet` auto-execution all work today and would need to be
rebuilt from scratch in any alternative framework.

---

## Why move off Fabric Data Agent

| Problem | Detail |
|---------|--------|
| **Black box** | FabricTool sends natural-language questions to the Data Agent, which translates them to GQL/KQL. We cannot control query formulation, cannot retry specific queries, and cannot inspect what was actually executed. |
| **Preview instability** | Fabric Data Agent is in private preview. The graph engine auto-suspends on F4 capacity, connections break silently, and the Data Agent occasionally returns empty results for valid questions. |
| **Manual connection setup** | Each Data Agent requires a manual portal step: create a Connected Resource in AI Foundry, then paste the connection name back into config. This cannot be automated via any public API. |
| **Auth limitation** | Data Agents require delegated user identity (no service principal), same as the direct GQL API, so there is no auth advantage. |
| **Query control** | With direct GQL, agents can construct precise graph queries (entity types, filters, hops) instead of hoping the Data Agent's NL→GQL translation captures the intent. |

## What stays the same

- **Foundry as the agent runtime.** `AIProjectClient`, `create_agent`, threads, runs, streaming — all unchanged.
- **ConnectedAgentTool orchestration.** Orchestrator → 4 sub-agents pattern, unchanged.
- **AzureAISearchTool for RunbookKB and HistoricalTickets.** These agents are already working well and are unaffected.
- **FastAPI + SSE backend.** The API layer does not change.
- **Frontend.** The React SPA consumes the same SSE protocol regardless of how agents get their data.

---

## Architecture Comparison

### V1 (current)

```
Orchestrator (ConnectedAgentTool)
├── GraphExplorerAgent  ──▶  FabricTool  ──▶  Fabric Data Agent  ──▶  Ontology Graph
├── TelemetryAgent      ──▶  FabricTool  ──▶  Fabric Data Agent  ──▶  Eventhouse KQL
├── RunbookKBAgent      ──▶  AzureAISearchTool  ──▶  AI Search
└── HistoricalTicketAgent ──▶  AzureAISearchTool  ──▶  AI Search
```

### V2 (proposed)

```
Orchestrator (ConnectedAgentTool)
├── GraphExplorerAgent  ──▶  FunctionTool(query_graph)  ──▶  Fabric REST API (executeQuery)
├── TelemetryAgent      ──▶  FunctionTool(query_kql)    ──▶  Eventhouse KQL (azure-kusto-data)
├── RunbookKBAgent      ──▶  AzureAISearchTool  ──▶  AI Search  (unchanged)
└── HistoricalTicketAgent ──▶  AzureAISearchTool  ──▶  AI Search  (unchanged)
```

The Data Agent layer is removed entirely. Agents call Python functions that
hit the Fabric REST APIs directly.

---

## Implementation Options Evaluated

### Option A: `FunctionTool` with `ToolSet` auto-execution (RECOMMENDED)

Define Python functions (`query_graph`, `query_kql`) and register them as
`FunctionTool` on the agent. Use `ToolSet` + `enable_auto_function_calls`
so the SDK automatically executes tool calls and feeds results back to the
agent — no manual tool-call loop needed.

**Pros:**
- Simplest code change — just swap tool definitions in `provision_agents.py`
- Functions run in the same Python process as the API server
- Full control over auth, retry logic, query formulation
- No extra infrastructure to deploy or manage
- Works with the existing SDK version (`azure-ai-agents==1.2.0b6`)

**Cons:**
- Functions must be registered at runtime, not at agent creation time
  (FunctionTool definitions are serialised as JSON schema, but execution
  happens in the client process that calls `create_and_process`)
- If the API process restarts, tool functions are re-registered from code
  (no persistence concern — they are stateless)

```python
# Example: GraphExplorerAgent with FunctionTool
from azure.ai.agents.models import FunctionTool, ToolSet

def query_graph(gql_query: str) -> str:
    """Execute a GQL query against the Fabric Graph Model.

    Args:
        gql_query: A GQL (Graph Query Language) query string.
                   Example: MATCH (r:CoreRouter) RETURN r.RouterId, r.City

    Returns:
        JSON string with query results (columns and data rows),
        or an error message if the query fails.
    """
    result = execute_gql(WORKSPACE_ID, GRAPH_MODEL_ID, gql_query)
    return json.dumps(result, ensure_ascii=False)

functions = FunctionTool(functions=[query_graph])
toolset = ToolSet()
toolset.add(functions)
project_client.agents.enable_auto_function_calls(toolset)
```

### Option B: MCP Server (`McpTool`)

Wrap the GQL and KQL functions in a FastMCP server (the stub already exists
at `api/app/mcp/server.py`). Register the MCP server URL as an `McpTool`
on the Foundry agent.

**Pros:**
- Tools are reusable by any MCP client (Copilot, Claude Desktop, etc.)
- Decoupled deployment — MCP server can evolve independently
- Aligns with Microsoft's MCP-first direction

**Cons:**
- Requires the MCP server to be deployed and reachable (extra infra)
- `McpTool` on Foundry agents is newer (added in `azure-ai-agents` 1.2.x)
  and less battle-tested than `FunctionTool`
- Adds network hop + latency for every tool call
- Auth flow is more complex — MCP server needs its own credential to call
  Fabric APIs, and may need to accept forwarded tokens

**Verdict:** Good future direction but adds unnecessary complexity for V2.
Consider migrating to MCP in V3 when the MCP server is production-ready.

### Option C: Hosted Agent (`ImageBasedHostedAgentDefinition`)

Package the agent + tool logic into a container image and deploy as a
Hosted Agent on Foundry. The container runs the full Python process with
direct access to Fabric APIs.

**Pros:**
- Agent logic and tools are co-located in a container
- Foundry manages scaling and lifecycle
- Good for production isolation

**Cons:**
- Requires `azure-ai-projects>=2.0.0b3` (breaking change from current v1.x)
- Need ACR, capability host setup, container build pipeline
- Overkill for a demo — adds Docker/ACR complexity without clear benefit
- Still in beta (`ImageBasedHostedAgentDefinition` is v2 SDK only)

**Verdict:** Production path for a real deployment, but wrong for this
phase. Consider for V3/production.

### Option D: Leave Foundry entirely (AutoGen / Semantic Kernel / custom)

Replace the entire Foundry agent runtime with an open-source framework.

**Pros:**
- Full control over every aspect of agent lifecycle
- No dependency on preview SDKs

**Cons:**
- Must reimplement: agent creation, thread management, tool execution,
  streaming, connected-agent orchestration, SSE event translation, cleanup
- Lose access to AzureAISearchTool (must build custom search integration)
- Lose Foundry portal visibility, monitoring, and agent versioning
- 10x more code for equivalent functionality
- Misaligned with the demo's thesis ("Azure-native, no third-party frameworks")

**Verdict:** Not recommended. The Foundry SDK works well for orchestration.
The only problem was FabricTool/Data Agent, which Option A fixes directly.

---

## Recommended Approach: Option A — `FunctionTool` on Foundry

### What changes

| Component | V1 | V2 | Change size |
|-----------|----|----|-------------|
| `scripts/provision_agents.py` | `FabricTool(connection_id=...)` | `FunctionTool(functions=[...])` tool definitions (schema only) | Medium — rewrite tool setup for 2 agents |
| `api/app/orchestrator.py` | `runs.stream()` with bare handler | `runs.stream()` with `ToolSet` + auto function calls | Medium — add ToolSet registration and function definitions |
| `scripts/_config.py` | Exports Fabric connection helpers | Add `query_graph()` and `query_kql()` functions | Small — extract from test_gql_query.py |
| Agent system prompts | "ask the Data Agent in natural language" | "construct a GQL/KQL query and call the tool" | Medium — rewrite query instructions |
| `azure_config.env` | `GRAPH_FABRIC_CONNECTION_NAME`, `TELEMETRY_FABRIC_CONNECTION_NAME` | `FABRIC_GRAPH_MODEL_ID` (already added) | Minimal — drop connection name vars |
| `provision_agents.py` | Manual connection prompt flow | Removed (no more Connected Resources needed) | Deletion — remove ~60 lines |
| `collect_fabric_agents.py` | Discovers Data Agent IDs | No longer needed | Delete script |

### What doesn't change

- `provision_ontology.py`, `provision_lakehouse.py`, `provision_eventhouse.py` — data provisioning is unchanged
- `create_runbook_indexer.py`, `create_tickets_indexer.py` — search index creation unchanged
- RunbookKBAgent, HistoricalTicketAgent — AzureAISearchTool unchanged
- Frontend, SSE protocol — completely unchanged
- `infra/` Bicep — no infra changes needed

---

## Detailed Implementation Plan

### Phase 1: Extract tool functions (Day 1)

#### 1.1 Create `scripts/fabric_tools.py`

Extract reusable functions from `test_gql_query.py` and `_config.py`:

```python
"""
Fabric data-access functions for use as FunctionTool callables.

These functions are called by Foundry agents via FunctionTool/ToolSet
to query the Fabric Graph (GQL) and Eventhouse (KQL) directly,
bypassing the Fabric Data Agent.
"""

import json
import os
import time
from datetime import datetime, timezone

import requests
from azure.identity import DefaultAzureCredential
from azure.kusto.data import KustoClient, KustoConnectionStringBuilder

# -- GQL --

def query_graph(gql_query: str) -> str:
    """Execute a GQL query against the Fabric Graph Model (network topology).

    Args:
        gql_query: A GQL query string. Use MATCH/RETURN syntax.
            Entity types: CoreRouter, TransportLink, AggSwitch, BaseStation,
            BGPSession, MPLSPath, Service, SLAPolicy.
            Example: MATCH (r:CoreRouter) RETURN r.RouterId, r.City

    Returns:
        JSON with 'status' and 'result' (columns + data rows),
        or JSON with 'error' key if the query fails.
    """
    ...  # Implementation from test_gql_query.py execute_gql()

# -- KQL --

def query_kql(kql_query: str) -> str:
    """Execute a KQL query against the Eventhouse (network telemetry).

    Args:
        kql_query: A KQL query string.
            Tables: AlertStream, LinkTelemetry.
            Example: AlertStream | where Severity == 'CRITICAL' | take 10

    Returns:
        JSON array of result rows, or an error message.
    """
    ...  # Implementation using azure-kusto-data
```

#### 1.2 Copy into `api/app/tools/fabric_tools.py`

The API process needs its own copy (or shared module) because `FunctionTool`
auto-execution runs in the API process, not in the scripts process.

Alternatively, structure as a shared package importable from both `scripts/`
and `api/app/`.

### Phase 2: Update agent provisioning (Day 1-2)

#### 2.1 Modify `provision_agents.py`

**Remove:**
- `FabricTool` import
- `prompt_fabric_connections()` — no more manual connection setup
- `get_fabric_connection_id()` — no longer needed
- `_make_fabric_tool()` — replaced by FunctionTool schema
- Step [2/6] "Checking Fabric connections" — entire step removed

**Add:**
- `FunctionTool` schema definitions for `query_graph` and `query_kql`
- These are JSON-schema-only at provisioning time (the actual callables
  are registered at runtime in the API process)

```python
def create_graph_explorer_agent(agents_client, model: str) -> dict:
    """Create the GraphExplorerAgent with FunctionTool (query_graph)."""
    instructions, description = load_prompt("foundry_graph_explorer_agent.md")

    # Define the tool schema (execution happens at runtime via ToolSet)
    tools = [
        {
            "type": "function",
            "function": {
                "name": "query_graph",
                "description": "Execute a GQL query against the network topology graph.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "gql_query": {
                            "type": "string",
                            "description": "GQL query. Use MATCH (n:EntityType) RETURN ... syntax."
                        }
                    },
                    "required": ["gql_query"]
                }
            }
        }
    ]

    agent = agents_client.create_agent(
        model=model,
        name="GraphExplorerAgent",
        instructions=instructions,
        tools=tools,
    )
    return {"id": agent.id, "name": agent.name, "description": description}
```

#### 2.2 Update `create_telemetry_agent` similarly

Replace `FabricTool` with `query_kql` function tool definition.

### Phase 3: Update runtime orchestrator (Day 2)

#### 3.1 Modify `api/app/orchestrator.py`

The key change: when running agent threads, register a `ToolSet` with
the actual Python callables so `create_and_process` (or streaming equivalent)
can auto-execute tool calls.

```python
from azure.ai.agents.models import FunctionTool, ToolSet
from app.tools.fabric_tools import query_graph, query_kql

def _build_toolset() -> ToolSet:
    """Build ToolSet with all FunctionTool callables for auto-execution."""
    functions = FunctionTool(functions=[query_graph, query_kql])
    toolset = ToolSet()
    toolset.add(functions)
    return toolset

# In the run loop:
toolset = _build_toolset()
project_client.agents.enable_auto_function_calls(toolset)

run = project_client.agents.runs.create_and_process(
    thread_id=thread.id,
    agent_id=orchestrator_id,
    toolset=toolset,
)
```

**Important:** `enable_auto_function_calls` must be called before
`create_and_process`. The SDK intercepts `requires_action` events and
automatically calls the registered Python functions, submitting results
back to the agent without manual intervention.

**For streaming** (the current SSE pattern), the `ToolSet` is passed to
the streaming run as well. The `AgentEventHandler` callbacks still fire
for each step, so the SSE event protocol is unchanged.

### Phase 4: Update agent prompts (Day 2)

#### 4.1 Rewrite `foundry_graph_explorer_agent.md`

**Key change:** Instead of "ask the Data Agent a natural-language question",
instruct the agent to construct GQL queries and call `query_graph`.

```markdown
## How you work

You have access to the `query_graph` function tool, which executes GQL
queries directly against the Fabric Graph Model containing the network
topology ontology.

When asked a question about network topology, you:
1. Determine which entity types and relationships are relevant
2. Construct a GQL query using MATCH/RETURN syntax
3. Call `query_graph(gql_query="...")` with your query
4. Interpret the results and answer the question

## GQL query patterns

### Find entities by type
MATCH (r:CoreRouter) RETURN r.RouterId, r.City, r.Region

### Traverse relationships (forward)
MATCH (l:TransportLink)-[:connects_to]->(r:CoreRouter)
WHERE r.RouterId = 'CORE-SYD-01'
RETURN l.LinkId, l.LinkType

### Multi-hop: link → path → service → SLA
MATCH (l:TransportLink)<-[:routes_via]-(p:MPLSPath)<-[:depends_on]-(s:Service)<-[:governed_by]-(sla:SLAPolicy)
WHERE l.LinkId = 'LINK-SYD-MEL-FIBRE-01'
RETURN p.PathId, s.ServiceId, s.ServiceType, sla.SLAPolicyId, sla.AvailabilityTarget

### Reverse: service → what it depends on
MATCH (s:Service)-[:depends_on]->(dep)
WHERE s.ServiceId = 'VPN-ACME-CORP'
RETURN LABELS(dep) AS type, dep

### Count entities by type
MATCH (n) RETURN LABELS(n) AS type, count(n) AS cnt GROUP BY type ORDER BY cnt DESC
```

#### 4.2 Rewrite `foundry_telemetry_agent.md`

**Key change:** Instead of natural-language Data Agent queries, instruct
the agent to construct KQL queries and call `query_kql`.

```markdown
## How you work

You have access to the `query_kql` function tool, which executes KQL
queries directly against the Eventhouse containing alert and telemetry data.

When asked for telemetry data, you:
1. Determine which table and columns are relevant
2. Construct a KQL query
3. Call `query_kql(kql_query="...")` with your query
4. Return the raw results without interpretation

## KQL query patterns

### Recent alerts for an entity
AlertStream
| where SourceNodeId == 'LINK-SYD-MEL-FIBRE-01'
| order by Timestamp desc
| take 20

### All recent critical/major alerts
AlertStream
| where Severity in ('CRITICAL', 'MAJOR')
| order by Timestamp desc
| take 50

### Link telemetry for a specific link
LinkTelemetry
| where LinkId == 'LINK-SYD-MEL-FIBRE-01'
| order by Timestamp desc
| take 10
```

### Phase 5: Cleanup and testing (Day 3)

#### 5.1 Remove deprecated components
- Delete or archive `collect_fabric_agents.py` (no longer needed)
- Remove `GRAPH_FABRIC_CONNECTION_NAME` and `TELEMETRY_FABRIC_CONNECTION_NAME`
  from `azure_config.env.template` (and mark as deprecated in existing env)
- Remove `GRAPH_DATA_AGENT_ID` and `TELEMETRY_DATA_AGENT_ID` from template
- Remove `FABRIC_DATA_AGENT_API_VERSION` from template

#### 5.2 Test script
- Update `test_orchestrator.py` to use `ToolSet` with function tools
- Verify the full investigation flow works end-to-end
- Confirm SSE events still stream correctly to the frontend

#### 5.3 Update documentation
- Update `ARCHITECTURE.md` to reflect V2 tool chain
- Update `SCENARIO.md` data-flow table
- Update `README.md` provisioning instructions (remove Data Agent step)

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| GQL query formulation by agent is unreliable | Medium | High | Provide comprehensive GQL examples in system prompt; start with known-good query templates; add fallback to simpler queries |
| KQL query formulation by agent is unreliable | Low | Medium | Telemetry queries are simpler (filter + sort + take); provide KQL examples in prompt |
| `FunctionTool` auto-execution with streaming | Low | Medium | Test `ToolSet` + streaming handler interaction; fallback to manual tool-call loop if needed |
| 429 rate limiting on GQL during demo | Medium | High | Keep retry logic from test_gql_query.py; scale up capacity to F8+ for demo; warm up graph before demo |
| Token auth expiry during long investigations | Low | Medium | DefaultAzureCredential auto-refreshes tokens; add explicit refresh in tool functions |

---

## Should We Leave Foundry?

**No.** The analysis strongly favours staying on Foundry:

1. **Foundry gives us for free**: Agent lifecycle management, thread/run
   persistence, `ConnectedAgentTool` multi-agent orchestration,
   `AzureAISearchTool` (no code needed for search), model hosting,
   streaming callbacks, and portal visibility for debugging.

2. **The only problem was FabricTool/Data Agent**, which is one tool type
   on two agents. Replacing it with `FunctionTool` is a surgical fix that
   preserves everything else.

3. **Moving off Foundry** would require reimplementing: agent state
   management, tool-call dispatch loops, search integration, streaming
   protocol, connected-agent delegation, and cleanup lifecycle. That's
   weeks of work for zero functional gain.

4. **Future optionality**: When Foundry's `MCPTool` matures, we can expose
   the GQL/KQL tools via an MCP server and upgrade to container-hosted
   agents. The FunctionTool approach is a clean stepping stone.

---

## Migration Checklist

- [ ] Create `api/app/tools/__init__.py` and `api/app/tools/fabric_tools.py`
- [ ] Implement `query_graph()` — extract from `test_gql_query.py`
- [ ] Implement `query_kql()` — using `azure-kusto-data` KustoClient
- [ ] Update `provision_agents.py` — remove FabricTool, add FunctionTool schemas
- [ ] Remove `prompt_fabric_connections()` and related connection code
- [ ] Update `api/app/orchestrator.py` — add ToolSet with auto-execution
- [ ] Rewrite `foundry_graph_explorer_agent.md` — GQL query instructions
- [ ] Rewrite `foundry_telemetry_agent.md` — KQL query instructions
- [ ] Update `foundry_orchestrator_agent.md` — reference new tool capabilities
- [ ] Remove or archive `collect_fabric_agents.py`
- [ ] Clean up `azure_config.env.template` — remove Data Agent vars
- [ ] Test end-to-end: alert → orchestrator → sub-agents → situation report
- [ ] Update `ARCHITECTURE.md`, `SCENARIO.md`, `README.md`
- [ ] Verify SSE streaming works with FunctionTool auto-execution
- [ ] Scale Fabric capacity for demo (F8+ recommended)

---

## Future Directions (V3)

| Direction | Description | When |
|-----------|-------------|------|
| **MCP Server** | Wrap `query_graph` and `query_kql` in a FastMCP server. Register as `McpTool` on agents. Enables reuse by Copilot, Claude Desktop, etc. The stub at `api/app/mcp/server.py` already exists. | When `McpTool` on Foundry is GA |
| **Hosted Agents** | Package agent + tools into container images. Deploy as `ImageBasedHostedAgentDefinition`. Requires `azure-ai-projects>=2.0.0b3`. | When v2 SDK is stable |
| **Agent-executed actions** | Add `execute_mpls_failover`, `create_incident_ticket`, `send_customer_notification` tools. With human-approval gates (L4 autonomy). | After V2 is validated |
| **A2A Protocol** | Use `A2APreviewTool` for inter-agent communication once it stabilises. Could replace `ConnectedAgentTool`. | When A2A is GA |
