# State-of-the-Art Hosted Agents Design — Full Migration

> **Status**: Aspirational design — uses every cutting-edge feature regardless of stability  
> **Date**: 2026-02-21  
> **SDK**: `azure-ai-projects >= 2.0.0b4` (beta)  
> **Principle**: Maximum use of platform capabilities, minimum custom code  
> **Source**: `microsoft_skills/skills/.github/plugins/azure-sdk-python/skills/`

---

## 1. Vision

Eliminate all custom orchestration plumbing. Every piece of logic that the platform can handle natively — tool execution, streaming, memory, evaluation, scheduling — moves into the platform. The Container App becomes a thin SSE proxy and data API. The Foundry platform runs, manages, scales, versions, and evaluates all agents.

```
┌───────────────────────────────────────────────────────────────────┐
│                    Azure AI Foundry Platform                      │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  Orchestrator (ImageBasedHostedAgentDefinition)             │  │
│  │  Image: acr.azurecr.io/noc-orchestrator:v2.1               │  │
│  │  Protocol: AgentProtocol.RESPONSES v1                      │  │
│  │  CPU: 2, RAM: 4Gi                                          │  │
│  │                                                             │  │
│  │  Tools:                                                     │  │
│  │  ├── ConnectedAgentTool → GraphExplorer                    │  │
│  │  ├── ConnectedAgentTool → TelemetryAgent                   │  │
│  │  ├── ConnectedAgentTool → RunbookKBAgent                   │  │
│  │  ├── ConnectedAgentTool → HistoricalTicketAgent            │  │
│  │  ├── FunctionTool → dispatch_field_engineer (in-container) │  │
│  │  └── MemorySearchPreviewTool → cross-session context       │  │
│  │                                                             │  │
│  │  Custom code inside container:                              │  │
│  │  ├── dispatch_field_engineer() implementation               │  │
│  │  ├── SSE event formatter (tool_call.start/complete schema)  │  │
│  │  └── AgentProtocol.RESPONSES handler                        │  │
│  └────────────┬────────────────────────────────────────────────┘  │
│               │                                                   │
│  ┌────────────▼────────────────────────────────────────────────┐  │
│  │  Sub-Agents (all PromptAgentDefinition + create_version)   │  │
│  │                                                             │  │
│  │  GraphExplorerAgent                                         │  │
│  │  ├── MicrosoftFabricPreviewTool (graph queries — native)   │  │
│  │  └── No more OpenAPI proxy for graph queries                │  │
│  │                                                             │  │
│  │  TelemetryAgent                                             │  │
│  │  ├── MicrosoftFabricPreviewTool (KQL queries — native)     │  │
│  │  └── No more OpenAPI proxy for telemetry queries            │  │
│  │                                                             │  │
│  │  RunbookKBAgent                                             │  │
│  │  ├── AzureAISearchAgentTool (project-level, typed)         │  │
│  │  └── MemorySearchPreviewTool (remember past searches)      │  │
│  │                                                             │  │
│  │  HistoricalTicketAgent                                      │  │
│  │  ├── AzureAISearchAgentTool (project-level, typed)         │  │
│  │  └── MemorySearchPreviewTool (incident pattern memory)     │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  Platform Services                                          │  │
│  │                                                             │  │
│  │  Memory Store (MemoryStoreDefaultDefinition)                │  │
│  │  ├── ChatSummaryMemoryItem per session                     │  │
│  │  └── UserProfileMemoryItem (operator patterns)             │  │
│  │                                                             │  │
│  │  Evaluation (scheduled)                                     │  │
│  │  ├── Groundedness evaluator on agent responses              │  │
│  │  ├── Relevance evaluator on tool call selection             │  │
│  │  └── Custom evaluator: investigation completeness           │  │
│  │                                                             │  │
│  │  Insights (ClusterInsightResult)                            │  │
│  │  └── Cluster similar investigations for pattern detection   │  │
│  └─────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────┘
                            │
                            ▼  Responses API (streaming)
┌───────────────────────────────────────────────────────────────────┐
│  Container App (THIN — ~200 lines of proxy code)                 │
│                                                                   │
│  api/                                                             │
│  ├── thin_proxy.py       (~50 lines — Responses API → SSE)      │
│  ├── session_manager.py  (simplified — Cosmos persist only)      │
│  └── routers/sessions.py (unchanged REST endpoints)              │
│                                                                   │
│  graph-query-api/        (REDUCED — only session CRUD remains)   │
│  ├── router_sessions.py  (Cosmos session persistence)            │
│  ├── router_search.py    (AI Search proxy for frontend viz)      │
│  └── router_health.py    (health checks)                         │
│                                                                   │
│  DELETED:                                                         │
│  ├── orchestrator.py     (771 lines → 0 — platform handles it)  │
│  ├── agent_ids.py        (235 lines → 0 — named agents)         │
│  ├── dispatch.py         (139 lines → 0 — in hosted container)  │
│  ├── router_graph.py     (FabricTool replaces OpenAPI proxy)     │
│  └── router_telemetry.py (FabricTool replaces OpenAPI proxy)     │
└───────────────────────────────────────────────────────────────────┘
```

---

## 2. Agent Definitions

### 2.1 Sub-Agents (PromptAgentDefinition + create_version)

All sub-agents use the GA versioned prompt agent pattern. No container needed — they're pure LLM + tools.

#### GraphExplorerAgent

```python
from azure.ai.projects.models import (
    PromptAgentDefinition,
    MicrosoftFabricPreviewTool,
    MemorySearchPreviewTool,
)

ge = client.agents.create_version(
    agent_name="GraphExplorerAgent",
    definition=PromptAgentDefinition(
        model="gpt-4.1",
        instructions=graph_explorer_prompt,
        tools=[
            # Native Fabric graph queries — no more OpenAPI proxy
            MicrosoftFabricPreviewTool(
                connection_id=fabric_connection_id,
            ),
            # Remember graph patterns across sessions
            MemorySearchPreviewTool(),
        ],
    ),
    version_label=f"v{deploy_version}",
    description="Queries Fabric graph model for network topology",
)
```

#### TelemetryAgent

```python
tel = client.agents.create_version(
    agent_name="TelemetryAgent",
    definition=PromptAgentDefinition(
        model="gpt-4.1",
        instructions=telemetry_prompt,
        tools=[
            # Native Fabric KQL queries — no more OpenAPI proxy
            MicrosoftFabricPreviewTool(
                connection_id=fabric_connection_id,
            ),
            MemorySearchPreviewTool(),
        ],
    ),
    version_label=f"v{deploy_version}",
    description="Queries Fabric eventhouse for telemetry/alerts",
)
```

#### RunbookKBAgent

```python
from azure.ai.projects.models import (
    AzureAISearchAgentTool,
    AzureAISearchToolResource,
    AISearchIndexResource,
    AzureAISearchQueryType,
)

rb = client.agents.create_version(
    agent_name="RunbookKBAgent",
    definition=PromptAgentDefinition(
        model="gpt-4.1",
        instructions=runbook_prompt,
        tools=[
            # Project-level typed AI Search (not low-level)
            AzureAISearchAgentTool(
                azure_ai_search=AzureAISearchToolResource(
                    indexes=[
                        AISearchIndexResource(
                            project_connection_id=search_connection.id,
                            index_name=runbooks_index,
                            query_type=AzureAISearchQueryType.VECTOR_SEMANTIC_HYBRID,
                        ),
                    ]
                )
            ),
            MemorySearchPreviewTool(),
        ],
    ),
    version_label=f"v{deploy_version}",
)
```

#### HistoricalTicketAgent

```python
tk = client.agents.create_version(
    agent_name="HistoricalTicketAgent",
    definition=PromptAgentDefinition(
        model="gpt-4.1",
        instructions=ticket_prompt,
        tools=[
            AzureAISearchAgentTool(
                azure_ai_search=AzureAISearchToolResource(
                    indexes=[
                        AISearchIndexResource(
                            project_connection_id=search_connection.id,
                            index_name=tickets_index,
                            query_type=AzureAISearchQueryType.VECTOR_SEMANTIC_HYBRID,
                        ),
                    ]
                )
            ),
            MemorySearchPreviewTool(),
        ],
    ),
    version_label=f"v{deploy_version}",
)
```

### 2.2 Orchestrator (ImageBasedHostedAgentDefinition)

The orchestrator runs as a hosted container inside Foundry. Your custom code (dispatch_field_engineer, response formatting) runs natively.

```python
from azure.ai.projects.models import (
    ImageBasedHostedAgentDefinition,
    ProtocolVersionRecord,
    AgentProtocol,
)
from azure.ai.agents.models import ConnectedAgentTool

orch = client.agents.create_version(
    agent_name="Orchestrator",
    definition=ImageBasedHostedAgentDefinition(
        container_protocol_versions=[
            ProtocolVersionRecord(
                protocol=AgentProtocol.RESPONSES,
                version="v1",
            )
        ],
        image=f"{acr_name}.azurecr.io/noc-orchestrator:{deploy_version}",
        cpu="2",
        memory="4Gi",
        tools=[
            # Sub-agent delegation
            ConnectedAgentTool(
                id=ge.id, name="GraphExplorerAgent",
                description="Query Fabric graph for topology",
            ),
            ConnectedAgentTool(
                id=tel.id, name="TelemetryAgent",
                description="Query Fabric eventhouse for alerts/telemetry",
            ),
            ConnectedAgentTool(
                id=rb.id, name="RunbookKBAgent",
                description="Search operational runbooks",
            ),
            ConnectedAgentTool(
                id=tk.id, name="HistoricalTicketAgent",
                description="Search historical incident tickets",
            ),
            # Dispatch (implemented inside the container)
            dispatch_tool_def,
            # Cross-session investigation memory
            MemorySearchPreviewTool(),
        ],
        environment_variables={
            "AZURE_AI_PROJECT_ENDPOINT": project_endpoint,
            "MODEL_NAME": "gpt-4.1",
        },
    ),
    version_label=f"v{deploy_version}",
    description="NOC Orchestrator — hosted agent with dispatch capability",
)
```

---

## 3. Memory System

### 3.1 Memory Store

```python
from azure.ai.projects.models import (
    MemoryStoreDefinition,
    MemoryStoreDefaultDefinition,
    MemoryStoreDefaultOptions,
)

# Create a memory store for the project
memory_store = client.memory_stores.create(
    name="noc-investigation-memory",
    definition=MemoryStoreDefaultDefinition(
        options=MemoryStoreDefaultOptions(),
    ),
)
```

### 3.2 Memory Types

| Memory Type | Use Case | Written By | Read By |
|-------------|----------|------------|---------|
| `ChatSummaryMemoryItem` | Summarize completed investigations | Orchestrator (auto) | All agents |
| `UserProfileMemoryItem` | NOC operator patterns & preferences | System | Orchestrator |

### 3.3 How Memory Changes the Demo

**Current**: Every investigation starts from zero. No cross-session context.

**SOTA**: The `MemorySearchPreviewTool` lets agents remember:
- "Last week we investigated a similar fiber cut on the Sydney-Melbourne corridor"
- "This operator usually wants detailed KQL telemetry evidence"
- "The Goulburn amplifier site has had 3 incidents in 6 months — escalate to maintenance review"

Agents query memory automatically when the tool is attached — no explicit code needed.

---

## 4. Evaluation System

### 4.1 Scheduled Evaluations

```python
from azure.ai.projects.models import (
    Schedule,
    CronTrigger,
    EvaluationScheduleTask,
    Evaluator,
    EvaluatorType,
    CodeBasedEvaluatorDefinition,
)

# Groundedness — does the diagnosis match the evidence?
groundedness_eval = client.evaluations.create(
    evaluator=Evaluator(type=EvaluatorType.GROUNDEDNESS),
    data_source=DataSourceConfigCustom(
        # Pull from completed session event logs
        dataset_name="completed-investigations",
    ),
)

# Relevance — did the orchestrator pick the right sub-agents?
relevance_eval = client.evaluations.create(
    evaluator=Evaluator(type=EvaluatorType.RELEVANCE),
)

# Custom — investigation completeness
completeness_eval = client.evaluations.create(
    evaluator=Evaluator(
        type=EvaluatorType.CUSTOM,
        definition=CodeBasedEvaluatorDefinition(
            code="""
def evaluate(investigation):
    score = 0
    if investigation.graph_queries > 0: score += 25
    if investigation.telemetry_queries > 0: score += 25
    if investigation.runbook_consulted: score += 25
    if investigation.dispatch_executed or investigation.no_dispatch_needed: score += 25
    return {"completeness": score}
""",
        ),
    ),
)

# Schedule daily evaluation
schedule = client.schedules.create(
    name="daily-investigation-quality",
    trigger=CronTrigger(
        expression="0 6 * * *",  # 6 AM daily
        time_zone="Australia/Sydney",
    ),
    task=EvaluationScheduleTask(evaluation_id=groundedness_eval.id),
)
```

### 4.2 Safety Evaluations

```python
# Ensure agent responses don't contain harmful content
for eval_type in [
    EvaluatorType.HATE_UNFAIRNESS,
    EvaluatorType.VIOLENCE,
    EvaluatorType.SELF_HARM,
    EvaluatorType.PROTECTED_MATERIAL_TEXT,
]:
    client.evaluations.create(
        evaluator=Evaluator(type=eval_type),
    )
```

---

## 5. Insights System

### 5.1 Investigation Clustering

```python
from azure.ai.projects.models import (
    AgentClusterInsightsRequest,
    InsightModelConfiguration,
)

# Cluster similar investigations to find recurring patterns
insights = client.insights.create(
    request=AgentClusterInsightsRequest(
        agent_name="Orchestrator",
        model_configuration=InsightModelConfiguration(
            model="gpt-4.1",
        ),
    ),
)

# Result: groups of similar investigations
# e.g., "Fiber degradation incidents (15 cases, avg 4.2 steps)"
# e.g., "BGP flap investigations (8 cases, avg 3.1 steps)"
for cluster in insights.clusters:
    print(f"Cluster: {cluster.summary}")
    print(f"  Count: {cluster.count}")
    print(f"  Samples: {[s.id for s in cluster.samples]}")
```

---

## 6. Tool Upgrades

### 6.1 MicrosoftFabricPreviewTool (Replaces OpenAPI Tools)

**Current**: 2 custom OpenAPI specs + 2 graph-query-api endpoints + `_parse_structured_output()` in orchestrator.py  
**SOTA**: One `MicrosoftFabricPreviewTool` per agent — queries Fabric directly

```python
from azure.ai.projects.models import MicrosoftFabricPreviewTool

fabric_tool = MicrosoftFabricPreviewTool(
    connection_id=fabric_connection_id,
)
```

**What this eliminates**:
- `graph-query-api/router_graph.py` (~200 lines)
- `graph-query-api/router_telemetry.py` (~150 lines)
- `graph-query-api/openapi/templates/graph.yaml`
- `graph-query-api/openapi/templates/telemetry.yaml`
- `orchestrator.py._parse_structured_output()` (~100 lines)
- `agent_provisioner._load_openapi_spec()` (~40 lines)

**Trade-off**: You lose fine-grained control over query formatting and response parsing. The agent talks to Fabric directly — results come back in Fabric's native format, not your `---QUERY--- / ---RESULTS--- / ---ANALYSIS---` delimited format. Visualization extraction would need to move into the frontend or agent instructions.

### 6.2 AzureAISearchAgentTool (Project-Level, Replaces Low-Level)

**Current**: `AzureAISearchTool` from `azure.ai.agents.models` with raw connection ID string  
**SOTA**: `AzureAISearchAgentTool` from `azure.ai.projects.models` with typed resources

```python
# CURRENT (low-level)
from azure.ai.agents.models import AzureAISearchTool, AzureAISearchQueryType
tool = AzureAISearchTool(
    index_connection_id=raw_arm_connection_id,
    index_name="runbooks-index",
    query_type=AzureAISearchQueryType.SEMANTIC,
    top_k=5,
)

# SOTA (project-level, typed)
from azure.ai.projects.models import (
    AzureAISearchAgentTool,
    AzureAISearchToolResource,
    AISearchIndexResource,
    AzureAISearchQueryType,
)
search_connection = client.connections.get("aisearch-connection")
tool = AzureAISearchAgentTool(
    azure_ai_search=AzureAISearchToolResource(
        indexes=[
            AISearchIndexResource(
                project_connection_id=search_connection.id,
                index_name="runbooks-index",
                query_type=AzureAISearchQueryType.VECTOR_SEMANTIC_HYBRID,
            ),
        ]
    )
)
```

**Win**: Uses `project_connection_id` (resolved via `connections.get()` at runtime) instead of hardcoded ARM resource path. Also upgrades to `VECTOR_SEMANTIC_HYBRID` from `SEMANTIC`.

### 6.3 MemorySearchPreviewTool (NEW — Cross-Session Context)

```python
from azure.ai.projects.models import MemorySearchPreviewTool

# Attach to any agent — it automatically searches memory
tool = MemorySearchPreviewTool()
```

### 6.4 CaptureStructuredOutputsTool (NEW — Typed Results)

```python
from azure.ai.projects.models import CaptureStructuredOutputsTool

# Force the orchestrator's final response into a typed schema
structured_output = CaptureStructuredOutputsTool(
    schema={
        "type": "object",
        "properties": {
            "root_cause": {"type": "string"},
            "affected_nodes": {"type": "array", "items": {"type": "string"}},
            "severity": {"type": "string", "enum": ["CRITICAL", "HIGH", "MEDIUM", "LOW"]},
            "recommended_action": {"type": "string"},
            "dispatch_required": {"type": "boolean"},
        },
        "required": ["root_cause", "severity", "recommended_action"],
    },
)
```

**Win**: Frontend gets structured investigation results instead of parsing free-text markdown. Enables typed action cards, severity badges, affected node highlights.

### 6.5 McpTool (NEW — MCP Server Integration)

Expose the graph-query-api as an MCP server that agents can call:

```python
from azure.ai.agents.models import McpTool

mcp = McpTool(
    server_label="graph-query-api",
    server_url=f"{graph_query_api_uri}/mcp",
    allowed_tools=["search_sessions", "get_topology_stats"],
)
```

**Note**: This requires adding an MCP endpoint to graph-query-api. Potential replacement for REST endpoints.

---

## 7. Infrastructure (Bicep)

### New Resources

```bicep
// ── Azure Container Registry ──
resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  sku: { name: 'Basic' }
  properties: {
    adminUserEnabled: false
  }
}

// ── AcrPull role for Foundry identity ──
resource acrPullRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: acr
  name: guid(acr.id, foundry.id, 'AcrPull')
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '7f951dda-4ed3-4680-a7ca-43fe172d538d'
    )
    principalId: foundry.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// ── Fabric connection on Foundry account ──
resource fabricConnection 'Microsoft.CognitiveServices/accounts/connections@2025-09-01' = {
  parent: foundry
  name: 'fabric-connection'
  properties: {
    authType: 'AAD'
    category: 'MicrosoftFabric'
    target: 'https://api.fabric.microsoft.com'
    isSharedToAll: true
    metadata: {
      WorkspaceId: fabricWorkspaceId
    }
  }
}

// ── Update account capability host ──
resource accountCapabilityHost 'Microsoft.CognitiveServices/accounts/capabilityHosts@2025-09-01' = {
  name: '${foundryName}-caphost'
  parent: foundry
  properties: {
    capabilityHostKind: 'Agents'
    enablePublicHostingEnvironment: true  // Required for hosted agents
    storageConnections: [ storageAccountConnection.name ]
    vectorStoreConnections: [ cosmosConnection.name ]
    threadStorageConnections: [ cosmosConnection.name ]
  }
  dependsOn: [ project ]
}

// ── Project capability host ──
resource projectCapabilityHost 'Microsoft.CognitiveServices/accounts/projects/capabilityHosts@2025-09-01' = {
  name: '${projectName}-caphost'
  parent: project
  properties: {
    aiServicesConnections: []
    storageConnections: [ storageAccountConnection.name ]
    vectorStoreConnections: [ cosmosConnection.name ]
    threadStorageConnections: [ cosmosConnection.name ]
  }
  dependsOn: [ accountCapabilityHost ]
}
```

### CI/CD Pipeline (New)

```yaml
# .github/workflows/deploy-agent-image.yml
name: Build & Push Agent Image
on:
  push:
    paths: ['agent-container/**']
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: azure/docker-login@v2
        with:
          login-server: ${{ vars.ACR_NAME }}.azurecr.io
          username: ${{ secrets.ACR_CLIENT_ID }}
          password: ${{ secrets.ACR_CLIENT_SECRET }}
      - run: |
          VERSION=$(git rev-parse --short HEAD)
          docker build -t ${{ vars.ACR_NAME }}.azurecr.io/noc-orchestrator:${VERSION} agent-container/
          docker push ${{ vars.ACR_NAME }}.azurecr.io/noc-orchestrator:${VERSION}
```

---

## 8. Container Image (Orchestrator)

### Directory Structure

```
agent-container/
├── Dockerfile
├── pyproject.toml
├── app/
│   ├── __init__.py
│   ├── main.py              # AgentProtocol.RESPONSES handler
│   ├── dispatch.py           # dispatch_field_engineer (moved from api/app/)
│   └── response_formatter.py # Format tool results for the demo UI
```

### Dockerfile

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .
COPY app/ app/
# AgentProtocol.RESPONSES handler listens on port 8080
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

### Protocol Handler (main.py)

```python
"""
AgentProtocol.RESPONSES handler for the NOC Orchestrator.

This runs INSIDE the Foundry-managed container. Foundry routes
agent invocations to this endpoint.
"""

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
import json
from app.dispatch import dispatch_field_engineer

app = FastAPI()

@app.post("/responses")
async def handle_response(request: Request):
    """Handle incoming agent response protocol requests."""
    body = await request.json()
    
    # The Responses protocol sends tool calls here for execution
    if body.get("type") == "function_call":
        name = body["name"]
        args = body["arguments"]
        
        if name == "dispatch_field_engineer":
            result = dispatch_field_engineer(**json.loads(args))
            return {"type": "function_call_output", "output": result}
    
    # For other requests, return acknowledgment
    return {"type": "ack"}

@app.get("/health")
async def health():
    return {"status": "ok"}
```

---

## 9. Simplified Container App (Thin Proxy)

### What orchestrator.py Becomes (~50 lines)

```python
"""
Thin SSE proxy — calls the Responses API and streams to the frontend.

The hosted Orchestrator agent handles all tool execution, retries,
and streaming internally. We just proxy the stream.
"""

import asyncio
import json
from typing import AsyncGenerator

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

_client = None

def _get_client() -> AIProjectClient:
    global _client
    if _client is None:
        _client = AIProjectClient(
            endpoint=os.environ["PROJECT_ENDPOINT"],
            credential=DefaultAzureCredential(),
        )
    return _client

async def run_orchestrator_session(
    alert_text: str,
    cancel_event=None,
    existing_thread_id=None,
) -> AsyncGenerator[dict, None]:
    """Stream investigation results from the hosted Orchestrator agent."""
    client = _get_client()
    
    # The Responses API handles everything:
    # - Thread creation/reuse
    # - Tool call execution (inside the hosted container)
    # - Streaming results
    # - Retry on failure
    response = client.agents.responses.create(
        agent_name="Orchestrator",
        input=alert_text,
        stream=True,
        thread_id=existing_thread_id,
    )
    
    for event in response:
        yield {
            "event": event.type,
            "data": json.dumps(event.data),
        }
```

**Lines eliminated**: 771 → ~50 (orchestrator.py)  
**Complexity eliminated**: AgentEventHandler, asyncio.Queue, threading bridge, retry logic, FunctionTool auto-execution wrapper

### What agent_ids.py Becomes (~20 lines)

```python
"""Named agent lookup — no more UUID discovery."""

def get_agent_names() -> dict[str, str]:
    """Static mapping — agents are named and versioned."""
    return {
        "GraphExplorerAgent": "GraphExplorerAgent",
        "TelemetryAgent": "TelemetryAgent",
        "RunbookKBAgent": "RunbookKBAgent",
        "HistoricalTicketAgent": "HistoricalTicketAgent",
        "Orchestrator": "Orchestrator",
    }

def is_configured() -> bool:
    return bool(os.environ.get("PROJECT_ENDPOINT"))
```

---

## 10. Code Deletion Manifest

### Files Deleted Entirely

| File | Lines | Reason |
|------|-------|--------|
| `api/app/orchestrator.py` | 771 | Replaced by Responses API proxy (~50 lines) |
| `api/app/agent_ids.py` | 235 | Named agents — no UUID discovery needed |
| `api/app/dispatch.py` | 139 | Moved into hosted container image |
| `graph-query-api/router_graph.py` | ~200 | `MicrosoftFabricPreviewTool` handles graph queries |
| `graph-query-api/router_telemetry.py` | ~150 | `MicrosoftFabricPreviewTool` handles KQL queries |
| `graph-query-api/openapi/templates/graph.yaml` | ~80 | No more OpenAPI tool specs |
| `graph-query-api/openapi/templates/telemetry.yaml` | ~80 | No more OpenAPI tool specs |
| **Total deleted** | **~1,655** | |

### Files Simplified

| File | Before | After | Delta |
|------|--------|-------|-------|
| `scripts/agent_provisioner.py` | 415 | ~200 | -215 (no OpenAPI loading, typed tools) |
| `api/app/session_manager.py` | 367 | ~200 | -167 (no thread bridge management) |

### Files Created

| File | Lines | Purpose |
|------|-------|---------|
| `agent-container/Dockerfile` | ~10 | Hosted agent container |
| `agent-container/app/main.py` | ~40 | Responses protocol handler |
| `agent-container/app/dispatch.py` | 139 | Moved from api/app/ |
| `.github/workflows/deploy-agent-image.yml` | ~25 | CI/CD for container image |

### Net Code Change

```
Deleted:  ~1,655 lines + 382 lines simplified = ~2,037 lines removed
Created:  ~215 lines
Net:      ~1,822 lines eliminated
```

---

## 11. SDK Requirements

```toml
# pyproject.toml (api/)
[project]
dependencies = [
    "azure-ai-projects>=2.0.0b4",       # Hosted agents, memory, evaluation
    "azure-ai-agents>=1.1.0",           # ConnectedAgentTool, FabricTool
    "azure-identity>=1.25.0",
    "fastapi>=0.115.0",
    "sse-starlette>=2.0.0",
    "httpx>=0.27.0",
]

# pyproject.toml (agent-container/)
[project]
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn>=0.30.0",
]
```

---

## 12. Frontend Impact

### Visualization Changes

With `MicrosoftFabricPreviewTool` replacing custom OpenAPI tools, the agent responses won't have the `---QUERY--- / ---RESULTS--- / ---ANALYSIS---` delimited format. Options:

1. **Move parsing to agent instructions** — tell agents to format output with delimiters (fragile)
2. **Use `CaptureStructuredOutputsTool`** — force typed output schema (recommended)
3. **Frontend parses Fabric-native format** — adapt visualization components

Recommended: Use `CaptureStructuredOutputsTool` on the Orchestrator to emit:

```json
{
  "root_cause": "Fiber degradation on SYD-MEL-F1 at Goulburn splice point",
  "affected_nodes": ["CR-SYDNEY-01", "CR-MELBOURNE-01"],
  "severity": "CRITICAL",
  "evidence": {
    "graph_queries": [...],
    "telemetry_data": [...],
    "runbook_matches": [...]
  },
  "recommended_action": "Dispatch field engineer to Goulburn",
  "dispatch_required": true
}
```

Frontend `AssistantMessage.tsx` component renders from typed fields instead of parsing markdown.

### SSE Event Format

The Responses API stream events may differ from the current `tool_call.start` / `tool_call.complete` schema. The thin proxy would need to map:

| Responses API Event | Current SSE Event |
|---------------------|-------------------|
| `response.output_item.added` | `tool_call.start` |
| `response.output_item.done` | `tool_call.complete` |
| `response.output_text.delta` | `message.delta` |
| `response.output_text.done` | `message.complete` |
| `response.completed` | `run.complete` |
| `response.failed` | `error` |

The `thin_proxy.py` would translate between these formats, keeping the frontend unchanged.

---

## 13. Migration Sequence

### Phase 1: Foundation (3 days)

1. Upgrade SDK to `azure-ai-projects >= 2.0.0b4`
2. Switch all agents to `create_version` + `PromptAgentDefinition`
3. Add Fabric connection to Bicep
4. Create ACR in Bicep
5. Verify named agents work with existing orchestrator.py

### Phase 2: FabricTool Migration (3 days)

1. Replace OpenAPI graph tool with `MicrosoftFabricPreviewTool`
2. Replace OpenAPI telemetry tool with `MicrosoftFabricPreviewTool`
3. Remove `router_graph.py` and `router_telemetry.py` from graph-query-api
4. Update agent instructions to handle Fabric-native query format
5. Test graph and telemetry queries end-to-end

### Phase 3: Search Tool Upgrade (1 day)

1. Replace `AzureAISearchTool` with `AzureAISearchAgentTool` (project-level)
2. Upgrade query type to `VECTOR_SEMANTIC_HYBRID`
3. Use `connections.get()` for dynamic connection resolution

### Phase 4: Hosted Orchestrator (5 days)

1. Create `agent-container/` with Responses protocol handler
2. Move `dispatch.py` into container
3. Build and push container image to ACR
4. Register Orchestrator as `ImageBasedHostedAgentDefinition`
5. Replace `orchestrator.py` with thin Responses API proxy
6. Add `enablePublicHostingEnvironment: true` to capability host
7. Test streaming, multi-turn, cancel

### Phase 5: Memory Integration (2 days)

1. Create memory store
2. Add `MemorySearchPreviewTool` to all agents
3. Test cross-session context recall
4. Verify memory doesn't leak sensitive operational data

### Phase 6: Evaluation & Insights (2 days)

1. Set up scheduled groundedness evaluation
2. Create custom investigation completeness evaluator
3. Configure investigation clustering insights
4. Build dashboard for evaluation results (or use AI Foundry portal)

### Phase 7: Structured Outputs (2 days)

1. Add `CaptureStructuredOutputsTool` to Orchestrator
2. Define investigation result schema
3. Update frontend `AssistantMessage.tsx` to render typed fields
4. Remove markdown parsing from visualization pipeline

### Total: ~18 working days

---

## 14. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `azure-ai-projects 2.0.0b4` breaking changes | **High** | **Critical** | Pin version, test after every SDK update, keep Phase 1 PR separate |
| `AgentProtocol.RESPONSES` wire protocol undocumented | **High** | **High** | Build incrementally, keep old orchestrator.py as fallback |
| `MicrosoftFabricPreviewTool` doesn't support GQL | **Medium** | **High** | Keep graph-query-api OpenAPI fallback, feature-flag the switch |
| `MemorySearchPreviewTool` stores sensitive data | **Medium** | **Medium** | Review memory contents, add retention policy |
| Container cold start latency | **Medium** | **Medium** | Pre-warm, health check |
| ACR costs + management overhead | **Low** | **Low** | Basic SKU is ~$5/month |
| `CaptureStructuredOutputsTool` schema mismatch | **Low** | **Medium** | Validate schema against test investigations |
| Evaluation scoring drift | **Low** | **Low** | Baseline before migration, compare after |

---

## 15. Fallback Strategy

Every phase has a clean rollback:

| Phase | Fallback |
|-------|----------|
| 1 (Versioned agents) | Revert to `create_agent()` — zero risk |
| 2 (FabricTool) | Re-enable OpenAPI tools — files are in git history |
| 3 (Search upgrade) | Revert to low-level `AzureAISearchTool` |
| 4 (Hosted orchestrator) | Restore `orchestrator.py` — it's the most critical fallback |
| 5 (Memory) | Remove `MemorySearchPreviewTool` from agent definitions |
| 6 (Evaluation) | Delete schedules — evaluations are non-blocking |
| 7 (Structured outputs) | Remove `CaptureStructuredOutputsTool`, revert frontend |

Each phase produces a separately deployable state. If Phase 4 fails, Phases 1–3 still provide value.

---

## Appendix: Import Cheatsheet (SOTA Stack)

```python
# ── Client ──
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

# ── Agent Definitions ──
from azure.ai.projects.models import (
    PromptAgentDefinition,
    ImageBasedHostedAgentDefinition,
    ContainerAppAgentDefinition,
    ProtocolVersionRecord,
    AgentProtocol,
    AgentKind,
)

# ── Tools (project-level) ──
from azure.ai.projects.models import (
    AzureAISearchAgentTool,
    AzureAISearchToolResource,
    AISearchIndexResource,
    AzureAISearchQueryType,
    MicrosoftFabricPreviewTool,
    MemorySearchPreviewTool,
    CaptureStructuredOutputsTool,
    MCPTool,
    MCPToolFilter,
)

# ── Tools (agent-level) ──
from azure.ai.agents.models import (
    ConnectedAgentTool,
    FunctionTool,
    FunctionToolDefinition,
    FunctionDefinition,
    ToolSet,
    FabricTool,
    McpTool,
)

# ── Memory ──
from azure.ai.projects.models import (
    MemoryStoreDefinition,
    MemoryStoreDefaultDefinition,
    MemoryStoreDefaultOptions,
    MemorySearchPreviewTool,
)

# ── Evaluation ──
from azure.ai.projects.models import (
    Evaluator,
    EvaluatorType,
    CodeBasedEvaluatorDefinition,
    Schedule,
    CronTrigger,
    EvaluationScheduleTask,
)

# ── Insights ──
from azure.ai.projects.models import (
    AgentClusterInsightsRequest,
    InsightModelConfiguration,
)

# ── Connections ──
from azure.ai.projects.models import ConnectionType
```
