# SOTA Hosted Agents — Implementation Plan

> **Source design**: `SOTA_DESIGN.md` in this directory  
> **SDK reference**: `microsoft_skills/skills/.github/plugins/azure-sdk-python/skills/`  
> **Bicep types**: `microsoft_skills/bicep-types-az/generated/cognitiveservices/microsoft.cognitiveservices/2025-09-01/`  
> **Date**: 2026-02-21

---

## Table of Contents

- [Phase 1: SDK Upgrade & Versioned Prompt Agents](#phase-1-sdk-upgrade--versioned-prompt-agents)
- [Phase 2: FabricTool Migration](#phase-2-fabrictool-migration)
- [Phase 3: Search Tool Upgrade](#phase-3-search-tool-upgrade)
- [Phase 4: Hosted Orchestrator Container](#phase-4-hosted-orchestrator-container)
- [Phase 5: Memory Integration](#phase-5-memory-integration)
- [Phase 6: Evaluation & Insights](#phase-6-evaluation--insights)
- [Phase 7: Structured Outputs & Frontend](#phase-7-structured-outputs--frontend)

---

## Phase 1: SDK Upgrade & Versioned Prompt Agents

**Duration**: 1–2 days  
**Risk**: Medium (beta SDK)  
**Gate**: All 5 agents provisionable and runnable with the new SDK

### Step 1.1 — Upgrade SDK dependencies

**Files**:
- `api/pyproject.toml` (18 lines)
- `pyproject.toml` (27 lines)

**Current** (both files):
```toml
"azure-ai-projects>=1.0.0,<2.0.0",
"azure-ai-agents==1.2.0b6",
```

**New** (both files):
```toml
"azure-ai-projects>=2.0.0b4",
"azure-ai-agents>=1.1.0",
```

**Cross-ref**: `hosted-agents-v2-py/SKILL.md` line 18: `pip install azure-ai-projects>=2.0.0b3`  
**Cross-ref**: `hosted-agents-v2-py/references/acceptance-criteria.md`: `Minimum Version: >=2.0.0b3`

**Verification**:
```bash
cd api && uv sync && .venv/bin/python3 -c "import azure.ai.projects; print(azure.ai.projects.__version__)"
# Expected: 2.0.0b4
```

### Step 1.2 — Rewrite agent_provisioner.py imports

**File**: `scripts/agent_provisioner.py` (416 lines)

**Current imports** (lines 19–30):
```python
from azure.ai.projects import AIProjectClient
from azure.ai.agents.models import (
    AzureAISearchTool,
    AzureAISearchQueryType,
    ConnectedAgentTool,
    OpenApiTool,
    OpenApiAnonymousAuthDetails,
    FunctionToolDefinition,
    FunctionDefinition,
)
```

**New imports**:
```python
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    PromptAgentDefinition,
    AzureAISearchAgentTool,
    AzureAISearchToolResource,
    AISearchIndexResource,
    AzureAISearchQueryType,
)
from azure.ai.agents.models import (
    ConnectedAgentTool,
    OpenApiTool,
    OpenApiAnonymousAuthDetails,
    FunctionToolDefinition,
    FunctionDefinition,
)
```

**Cross-ref**: `azure-ai-projects-py/references/acceptance-criteria.md` §1.3:
- `PromptAgentDefinition` → from `azure.ai.projects.models` ✅
- `AzureAISearchAgentTool` → from `azure.ai.projects.models` ✅

**Cross-ref**: `azure-ai-projects-py/references/acceptance-criteria.md` §1.4:
- `ConnectedAgentTool`, `OpenApiTool` → from `azure.ai.agents.models` ✅

**Cross-ref**: `azure-ai-projects-py/references/acceptance-criteria.md` §1.6 (anti-patterns):
- ❌ `from azure.ai.projects.models import ConnectedAgentTool` → WRONG, it's in `azure.ai.agents.models`
- ❌ `from azure.ai.agents.models import PromptAgentDefinition` → WRONG, it's in `azure.ai.projects.models`

### Step 1.3 — Switch create_agent → create_version for sub-agents

**File**: `scripts/agent_provisioner.py`, method `provision_all()` (lines 176–416)

Each sub-agent changes from:
```python
ge = agents_client.create_agent(
    model=model,
    name="GraphExplorerAgent",
    instructions=prompts.get("graph_explorer", "..."),
    tools=ge_tools,
)
```

To:
```python
ge = client.agents.create_version(
    agent_name="GraphExplorerAgent",
    definition=PromptAgentDefinition(
        model=model,
        instructions=prompts.get("graph_explorer", "..."),
        tools=ge_tools,
    ),
    version_label=version_label,
    description="Graph topology explorer",
)
```

**Cross-ref**: `azure-ai-projects-py/references/agents.md` lines 32–48:
```python
agent = project_client.agents.create_version(
    agent_name="customer-support-agent",
    definition=PromptAgentDefinition(
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        instructions="You are a customer support specialist.",
        tools=[],
    ),
    version_label="v1.0",
    description="Initial version",
)
```

**Apply to all 5 agents**:

| Agent | Current line | `create_agent` → `create_version` |
|-------|-------------|-----------------------------------|
| GraphExplorerAgent | L245 | `agents_client.create_agent(model, name, instructions, tools)` → `client.agents.create_version(agent_name, definition=PromptAgentDefinition(...), version_label)` |
| TelemetryAgent | L260 | Same pattern |
| RunbookKBAgent | L275 | Same pattern + `tool_resources` stays |
| HistoricalTicketAgent | L295 | Same pattern with ticket search tool |
| Orchestrator | L380 | Same pattern with connected_tools + dispatch_tool |

**Note on tools with `tool_resources`**: `PromptAgentDefinition` accepts `tools` and `tool_resources` parameters.

**Cross-ref**: `azure-ai-projects-py/references/api-reference.md` lines 84–100:
```python
definition = PromptAgentDefinition(
    model="gpt-4o-mini",
    instructions="...",
    tools=[CodeInterpreterTool()],
    tool_resources={...},
)
```

### Step 1.4 — Add version_label parameter

**File**: `scripts/provision_agents.py`, `_load_config()` (line 74) and `main()` (line 153)

**Add to config**:
```python
return {
    ...
    "version_label": os.environ.get("AGENT_VERSION_LABEL", "v1.0"),
}
```

**Pass to provisioner**:
```python
result = provisioner.provision_all(
    ...
    version_label=config["version_label"],  # NEW
)
```

**File**: `scripts/agent_provisioner.py`, `provision_all()` signature

**Add parameter**:
```python
def provision_all(
    self,
    model: str,
    prompts: dict[str, str],
    graph_query_api_uri: str,
    graph_backend: str,
    runbooks_index: str,
    tickets_index: str,
    search_connection_id: str,
    on_progress: callable | None = None,
    version_label: str = "v1.0",  # NEW
) -> dict:
```

### Step 1.5 — Remove cleanup_existing() delete-and-recreate

**File**: `scripts/agent_provisioner.py`, `cleanup_existing()` (lines 166–183)

**Action**: Keep the method but make it version-aware. With `create_version`, you don't need to delete old agents — new versions are additive. The cleanup shifts from "delete agent by ID" to "delete old versions if desired".

**Cross-ref**: `hosted-agents-v2-py/references/acceptance-criteria.md` §8:
- ✅ `list_versions`, `delete_version`
- ❌ `delete_agent` (WRONG for versioned agents — use `delete_version`)

**New cleanup**:
```python
def cleanup_old_versions(self, agent_name: str, keep_latest: int = 3) -> int:
    """Delete old versions of a named agent, keeping the N most recent."""
    client = self._get_client()
    versions = list(client.agents.list_versions(agent_name=agent_name))
    if len(versions) <= keep_latest:
        return 0
    # Sort by version (newest first), delete the rest
    to_delete = versions[keep_latest:]
    deleted = 0
    for v in to_delete:
        try:
            client.agents.delete_version(agent_name=agent_name, version=v.version)
            deleted += 1
        except Exception as exc:
            logger.warning("Could not delete version %s of %s: %s", v.version, agent_name, exc)
    return deleted
```

### Step 1.6 — Update agent_ids.py for named agents

**File**: `api/app/agent_ids.py` (236 lines)

**Current**: `_discover_agents()` uses `client.agents.list_agents(limit=100)` and filters by name from an unordered list of ephemeral agents.

**New**: Use `client.agents.list_versions(agent_name=...)` for each known agent name. This returns versions of specifically-named agents — no more filtering through 100 ephemeral UUIDs.

**Replace** `_discover_agents()` body (lines 80–140):
```python
def _discover_agents() -> dict:
    client = _get_project_client()
    if client is None:
        return {}

    sub_agents = {}
    orchestrator = None

    for name in ("GraphExplorerAgent", "TelemetryAgent", "RunbookKBAgent", "HistoricalTicketAgent"):
        try:
            versions = list(client.agents.list_versions(agent_name=name))
            if versions:
                latest = versions[0]  # Most recent version
                sub_agents[name] = {
                    "id": latest.id,
                    "name": latest.name,
                    "model": getattr(latest, 'model', ''),
                    "is_orchestrator": False,
                    "tools": [],
                    "connected_agents": [],
                }
        except Exception as e:
            logger.warning("Could not discover agent %s: %s", name, e)

    try:
        versions = list(client.agents.list_versions(agent_name="Orchestrator"))
        if versions:
            latest = versions[0]
            orchestrator = {
                "id": latest.id,
                "name": latest.name,
                "model": getattr(latest, 'model', ''),
                "is_orchestrator": True,
                "tools": [],
                "connected_agents": list(sub_agents.keys()),
            }
    except Exception as e:
        logger.warning("Could not discover Orchestrator: %s", e)

    result = {}
    if orchestrator:
        result["orchestrator"] = orchestrator
    result["sub_agents"] = sub_agents
    return result
```

**Cross-ref**: `azure-ai-projects-py/references/agents.md` — `list_versions` returns versions sorted newest-first.

### Step 1.7 — Update orchestrator.py imports

**File**: `api/app/orchestrator.py` (772 lines)

**Current** (line 28):
```python
from app.agent_ids import load_agent_ids, get_agent_names
```

**No change needed** — `load_agent_ids` and `get_agent_names` signatures stay the same. Internal implementation changes in Step 1.6 are transparent.

### Step 1.8 — Verification

```bash
# SDK version check
cd api && .venv/bin/python3 -c "
import azure.ai.projects; print(f'projects: {azure.ai.projects.__version__}')
import azure.ai.agents; print(f'agents: {azure.ai.agents.__version__}')
"
# Expected: projects: 2.0.0b4, agents: 1.1.0

# Agent provisioning
cd scripts && uv run python provision_agents.py
# Expected: 5 agents created via create_version, no errors

# Runtime discovery
cd api && PYTHONPATH=. .venv/bin/python3 -c "
from app.agent_ids import load_agent_ids
data = load_agent_ids()
print(f'Orchestrator: {data.get(\"orchestrator\", {}).get(\"id\", \"MISSING\")}')
print(f'Sub-agents: {list(data.get(\"sub_agents\", {}).keys())}')
"

# Full backend compile
for f in api/app/*.py api/app/routers/*.py; do python3 -m py_compile "$f" && echo "OK: $f"; done
```

### Step 1.9 — Fallback

If `create_version` fails or the SDK is incompatible:
1. Revert `pyproject.toml` to `azure-ai-projects>=1.0.0,<2.0.0`
2. Revert `agent_provisioner.py` to `create_agent` pattern
3. All other files unchanged

---

## Phase 2: FabricTool Migration

**Duration**: 2–3 days  
**Risk**: High (FabricTool is preview, may not support GQL)  
**Gate**: GraphExplorerAgent and TelemetryAgent can query Fabric natively  
**Prerequisite**: Phase 1 complete, Fabric connection created in Foundry

### Step 2.1 — Create Fabric connection in Bicep

**File**: `infra/modules/ai-foundry.bicep` (281 lines)

**Add new parameter** (after line 36):
```bicep
@description('Resource ID of the Fabric workspace')
param fabricWorkspaceId string = ''
```

**Add new resource** (after `cosmosConnection`, before `project`):
```bicep
// ---------------------------------------------------------------------------
// Connection — Microsoft Fabric (for FabricTool — graph + telemetry queries)
// ---------------------------------------------------------------------------

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
```

**Cross-ref**: `bicep-types-az/2025-09-01/types.md` — `ConnectionPropertiesV2.category` includes `MicrosoftFabric` as a valid value (line 469 area).

**Also add output**:
```bicep
output fabricConnectionName string = fabricConnection.name
```

### Step 2.2 — Add FABRIC_CONNECTION_NAME to azure_config.env

**File**: `azure_config.env` and `azure_config.env.template`

**Add**:
```
FABRIC_CONNECTION_NAME=fabric-connection
```

### Step 2.3 — Switch GraphExplorerAgent to FabricTool

**File**: `scripts/agent_provisioner.py`, `provision_all()` — GraphExplorer section (lines 230–250)

**Current**:
```python
ge_tools = []
if graph_query_api_uri:
    spec = _load_openapi_spec(graph_query_api_uri, graph_backend, "/query/graph", spec_template="graph")
    tool = OpenApiTool(
        name="query_graph",
        spec=spec,
        description=GRAPH_TOOL_DESCRIPTIONS.get(graph_backend, ...),
        auth=OpenApiAnonymousAuthDetails(),
    )
    ge_tools = tool.definitions

ge = agents_client.create_agent(
    model=model,
    name="GraphExplorerAgent",
    instructions=prompts.get("graph_explorer", "..."),
    tools=ge_tools,
)
```

**New**:
```python
from azure.ai.agents.models import FabricTool

fabric_connection_id = _build_connection_id(
    subscription_id, resource_group, foundry_name, project_name, "fabric-connection"
)
fabric_tool = FabricTool(connection_id=fabric_connection_id)

ge = client.agents.create_version(
    agent_name="GraphExplorerAgent",
    definition=PromptAgentDefinition(
        model=model,
        instructions=prompts["graph_explorer"],
        tools=fabric_tool.definitions,
    ),
    version_label=version_label,
    description="Graph topology explorer — queries Fabric graph model",
)
```

**Cross-ref**: `azure-ai-projects-py/references/tools.md` — FabricTool section:
```python
from azure.ai.agents.models import FabricTool
```

**Cross-ref**: `azure-ai-projects-py/references/acceptance-criteria.md` §1.4:
- `FabricTool` is in `azure.ai.agents.models` ✅

### Step 2.4 — Switch TelemetryAgent to FabricTool

**File**: `scripts/agent_provisioner.py`, TelemetryAgent section (lines 252–268)

Same pattern as Step 2.3 — replace `OpenApiTool` with `FabricTool`.

```python
tel = client.agents.create_version(
    agent_name="TelemetryAgent",
    definition=PromptAgentDefinition(
        model=model,
        instructions=prompts["telemetry"],
        tools=fabric_tool.definitions,  # Same FabricTool instance
    ),
    version_label=version_label,
    description="Telemetry and alert analyst — queries Fabric eventhouse",
)
```

### Step 2.5 — Remove OpenAPI loading code

**File**: `scripts/agent_provisioner.py`

**Delete** (lines 42–68): `CONNECTOR_OPENAPI_VARS` dict  
**Delete** (lines 70–73): `GRAPH_TOOL_DESCRIPTIONS` dict  
**Delete** (lines 98–133): `_load_openapi_spec()` function  
**Remove** imports: `OpenApiTool`, `OpenApiAnonymousAuthDetails`, `yaml`

### Step 2.6 — Delete OpenAPI template files

**Files to delete**:
- `graph-query-api/openapi/templates/graph.yaml` (61 lines)
- `graph-query-api/openapi/templates/telemetry.yaml` (61 lines)
- `graph-query-api/openapi/templates/` directory (if empty)
- `graph-query-api/openapi/` directory (if empty)

### Step 2.7 — Remove graph-query-api graph/telemetry routers

**Files to delete**:
- `graph-query-api/router_graph.py` (76 lines)
- `graph-query-api/router_telemetry.py` (74 lines)

**File to update**: `graph-query-api/main.py` (193 lines)

Remove the router imports and `include_router` calls for graph and telemetry.

### Step 2.8 — Update GraphExplorer and Telemetry agent prompts

**Files**:
- `data/scenarios/*/prompts/graph_explorer/core_instructions.md`
- `data/scenarios/*/prompts/foundry_telemetry_agent_v2.md`

**Changes**: Remove references to OpenAPI tool usage patterns and update to FabricTool patterns. The agent now queries Fabric directly — instructions should reference GQL / KQL query syntax but not the OpenAPI endpoint format.

### Step 2.9 — Update orchestrator.py _parse_structured_output

**File**: `api/app/orchestrator.py`, `_parse_structured_output()` method (approx. lines 255–340)

**Assessment**: This method parses the `---QUERY--- / ---RESULTS--- / ---ANALYSIS---` delimited format that sub-agents currently emit. With FabricTool, the agents may return results in a different format. **This method may need to be updated or replaced depending on how FabricTool structures its responses.**

**Action**: Test first, then adapt. If FabricTool returns structured data natively, simplify the parser. If it returns raw text, keep the parser but update the delimiters.

### Step 2.10 — Verification

```bash
# Provision with FabricTool
cd scripts && uv run python provision_agents.py

# Test GraphExplorer query (manual)
cd api && PYTHONPATH=. .venv/bin/python3 -c "
from app.orchestrator import _get_project_client
client = _get_project_client()
# Create thread, send graph query, check response format
thread = client.agents.threads.create()
client.agents.messages.create(thread_id=thread.id, role='user', content='Show me all CoreRouters')
# ... run and check
"
```

### Step 2.11 — Fallback

If FabricTool doesn't support GQL or returns unusable results:
1. Keep `router_graph.py` and `router_telemetry.py`
2. Revert to OpenAPI tools
3. Feature-flag: `USE_FABRIC_TOOL=true/false` in azure_config.env

---

## Phase 3: Search Tool Upgrade

**Duration**: 0.5 days  
**Risk**: Low  
**Gate**: RunbookKB and HistoricalTicket agents query via project-level typed tools

### Step 3.1 — Switch AzureAISearchTool → AzureAISearchAgentTool

**File**: `scripts/agent_provisioner.py`, RunbookKB section (lines 270–285)

**Current**:
```python
from azure.ai.agents.models import AzureAISearchTool, AzureAISearchQueryType

search_tool = AzureAISearchTool(
    index_connection_id=search_connection_id,
    index_name=runbooks_index,
    query_type=AzureAISearchQueryType.SEMANTIC,
    top_k=5,
)
rb = agents_client.create_agent(
    model=model,
    name="RunbookKBAgent",
    instructions=prompts.get("runbook", "..."),
    tools=search_tool.definitions,
    tool_resources=search_tool.resources,
)
```

**New**:
```python
from azure.ai.projects.models import (
    AzureAISearchAgentTool,
    AzureAISearchToolResource,
    AISearchIndexResource,
    AzureAISearchQueryType,
)

# Resolve connection dynamically at runtime
search_conn = client.connections.get("aisearch-connection")

runbook_search = AzureAISearchAgentTool(
    azure_ai_search=AzureAISearchToolResource(
        indexes=[
            AISearchIndexResource(
                project_connection_id=search_conn.id,
                index_name=runbooks_index,
                query_type=AzureAISearchQueryType.VECTOR_SEMANTIC_HYBRID,
            ),
        ]
    )
)

rb = client.agents.create_version(
    agent_name="RunbookKBAgent",
    definition=PromptAgentDefinition(
        model=model,
        instructions=prompts.get("runbook", "..."),
        tools=[runbook_search],
    ),
    version_label=version_label,
    description="Operational runbook searcher",
)
```

**Cross-ref**: `azure-ai-projects-py/references/tools.md` — AzureAISearchAgentTool section:
```python
search_connection = project_client.connections.get(os.environ["AI_SEARCH_PROJECT_CONNECTION_NAME"])
tool = AzureAISearchAgentTool(
    azure_ai_search=AzureAISearchToolResource(
        indexes=[
            AISearchIndexResource(
                project_connection_id=search_connection.id,
                index_name=os.environ["AI_SEARCH_INDEX_NAME"],
                query_type=AzureAISearchQueryType.SIMPLE,
            ),
        ]
    )
)
```

**Cross-ref**: `azure-ai-projects-py/references/tools.md` — Query Types:
```python
AzureAISearchQueryType.SIMPLE
AzureAISearchQueryType.SEMANTIC
AzureAISearchQueryType.VECTOR
AzureAISearchQueryType.VECTOR_SIMPLE_HYBRID
AzureAISearchQueryType.VECTOR_SEMANTIC_HYBRID  # ← upgrade from SEMANTIC
```

### Step 3.2 — Same for HistoricalTicketAgent

Same pattern as Step 3.1, using `tickets_index`.

### Step 3.3 — Remove _build_connection_id helper

**File**: `scripts/agent_provisioner.py`, function `_build_connection_id()` (lines 82–95)

**Action**: This function manually constructs ARM resource paths for connection IDs. With project-level tools, connections are resolved via `client.connections.get(name)` — no more manual ARM path construction.

**Delete the function** and update `provision_agents.py` to remove its usage (line 155–161).

### Step 3.4 — Verification

```bash
# Provision and test
cd scripts && uv run python provision_agents.py
# Test: submit an alert that triggers RunbookKB search
```

---

## Phase 4: Hosted Orchestrator Container

**Duration**: 5 days  
**Risk**: High (protocol underdocumented, beta SDK)  
**Gate**: Orchestrator runs inside Foundry-managed container, SSE streaming works

### Step 4.1 — Create ACR in Bicep

**File**: `infra/main.bicep` — add new module reference

**New file**: `infra/modules/container-registry.bicep`

```bicep
@description('Name of the Azure Container Registry')
param acrName string

@description('Azure region')
param location string

@description('Resource tags')
param tags object = {}

@description('Principal ID that needs AcrPull access')
param pullPrincipalId string

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  tags: tags
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
  }
}

resource acrPullRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: acr
  name: guid(acr.id, pullPrincipalId, 'AcrPull')
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '7f951dda-4ed3-4680-a7ca-43fe172d538d'
    )
    principalId: pullPrincipalId
    principalType: 'ServicePrincipal'
  }
}

output acrName string = acr.name
output acrLoginServer string = acr.properties.loginServer
```

**File**: `infra/main.bicep` — wire the module:
```bicep
module acr 'modules/container-registry.bicep' = {
  name: 'acr'
  params: {
    acrName: 'acr${uniqueSuffix}'
    location: location
    tags: tags
    pullPrincipalId: aiFoundry.outputs.foundryPrincipalId
  }
}
```

### Step 4.2 — Enable hosted agent hosting on capability host

**File**: `infra/modules/ai-foundry.bicep`, `accountCapabilityHost` resource

**Current** `CapabilityHostProperties` on the bicep-types-az `2025-09-01` does NOT include `enablePublicHostingEnvironment` as a Bicep property. Per the `hosted-agents-v2-py/SKILL.md` prerequisites, this must be set via REST API or portal.

**Cross-ref**: `hosted-agents-v2-py/SKILL.md` line 35:
> 3. **Capability Host** — Account-level capability host with `enablePublicHostingEnvironment=true`

**Cross-ref**: `bicep-types-az/2025-09-01/types.md` — `CapabilityHostProperties`: No `enablePublicHostingEnvironment` property exists.

**Action**: Add a post-provisioning script step to `deploy.sh`:
```bash
# Enable hosted agent hosting environment
az rest --method PATCH \
  --url "https://management.azure.com/subscriptions/${AZURE_SUBSCRIPTION_ID}/resourceGroups/${AZURE_RESOURCE_GROUP}/providers/Microsoft.CognitiveServices/accounts/${AI_FOUNDRY_NAME}/capabilityHosts/${AI_FOUNDRY_NAME}-caphost?api-version=2025-09-01" \
  --body '{"properties":{"enablePublicHostingEnvironment":true}}'
```

### Step 4.3 — Create agent container directory

**New directory**: `agent-container/`

```
agent-container/
├── Dockerfile
├── pyproject.toml
├── app/
│   ├── __init__.py
│   ├── main.py              # AgentProtocol.RESPONSES handler
│   └── dispatch.py           # Moved from api/app/dispatch.py
```

**New file**: `agent-container/Dockerfile`
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .
COPY app/ app/
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

**New file**: `agent-container/pyproject.toml`
```toml
[project]
name = "noc-orchestrator-agent"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn>=0.30.0",
]
```

**New file**: `agent-container/app/__init__.py`
```python
```

**New file**: `agent-container/app/main.py`
```python
"""
AgentProtocol.RESPONSES handler for the NOC Orchestrator hosted agent.
Foundry routes agent invocations to this endpoint.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import json
import logging
from app.dispatch import dispatch_field_engineer

logger = logging.getLogger(__name__)
app = FastAPI()

@app.post("/responses")
async def handle_response(request: Request):
    body = await request.json()

    if body.get("type") == "function_call":
        name = body.get("name", "")
        args = body.get("arguments", "{}")

        if name == "dispatch_field_engineer":
            try:
                parsed_args = json.loads(args) if isinstance(args, str) else args
                result = dispatch_field_engineer(**parsed_args)
                return JSONResponse({"type": "function_call_output", "output": result})
            except Exception as e:
                logger.exception("dispatch_field_engineer failed")
                return JSONResponse({"type": "function_call_output", "output": json.dumps({"error": str(e)})})

    return JSONResponse({"type": "ack"})

@app.get("/health")
async def health():
    return {"status": "ok"}
```

**Move file**: `api/app/dispatch.py` → `agent-container/app/dispatch.py` (copy, then delete original in a later step)

### Step 4.4 — Build and push container image

**New file**: `.github/workflows/build-agent-image.yml` (or script in `scripts/`)

```bash
#!/bin/bash
# scripts/build_agent_image.sh
set -euo pipefail
source azure_config.env

ACR_NAME="${ACR_NAME:-acr${UNIQUE_SUFFIX}}"
VERSION=$(git rev-parse --short HEAD)
IMAGE="${ACR_NAME}.azurecr.io/noc-orchestrator:${VERSION}"

echo "Building: ${IMAGE}"
az acr build --registry "$ACR_NAME" --image "noc-orchestrator:${VERSION}" agent-container/
echo "Pushed: ${IMAGE}"
echo "ACR_IMAGE=${IMAGE}" >> "$GITHUB_ENV" 2>/dev/null || true
```

### Step 4.5 — Register Orchestrator as ImageBasedHostedAgentDefinition

**File**: `scripts/agent_provisioner.py`, Orchestrator section (lines 305–400)

**Current**:
```python
orch = agents_client.create_agent(
    model=model,
    name="Orchestrator",
    instructions=prompts.get("orchestrator", "..."),
    tools=all_tools,
)
```

**New**:
```python
from azure.ai.projects.models import (
    ImageBasedHostedAgentDefinition,
    ProtocolVersionRecord,
    AgentProtocol,
)

orch = client.agents.create_version(
    agent_name="Orchestrator",
    definition=ImageBasedHostedAgentDefinition(
        container_protocol_versions=[
            ProtocolVersionRecord(
                protocol=AgentProtocol.RESPONSES,
                version="v1",
            )
        ],
        image=f"{acr_login_server}/noc-orchestrator:{image_version}",
        cpu="2",
        memory="4Gi",
        tools=[
            *connected_tools,
            dispatch_tool_def,
        ],
        environment_variables={
            "AZURE_AI_PROJECT_ENDPOINT": project_endpoint,
            "MODEL_NAME": model,
        },
    ),
    version_label=version_label,
    description="NOC Orchestrator — hosted container agent",
)
```

**Cross-ref**: `hosted-agents-v2-py/SKILL.md` — complete example (lines 215–265):
- `client.agents.create_version` ✅ (NOT `create_agent`)
- `container_protocol_versions` required ✅
- `image` required ✅
- `cpu` and `memory` are strings ✅
- `tools` is list of dicts or tool objects ✅

**Cross-ref**: `hosted-agents-v2-py/references/acceptance-criteria.md` §3:
- ❌ Using `create_agent` → WRONG, must use `create_version`
- ❌ Missing `container_protocol_versions` → required
- ❌ Passing `model=` parameter → NOT applicable for hosted agents

**Cross-ref**: `hosted-agents-v2-py/references/acceptance-criteria.md` §5:
- ✅ `cpu="2"` (string, not int)
- ✅ `memory="4Gi"` (string with unit)

**New parameters needed in provisioner**:
```python
def provision_all(
    self,
    ...
    acr_login_server: str = "",    # NEW
    image_version: str = "latest", # NEW
    project_endpoint: str = "",    # NEW (for env vars)
) -> dict:
```

### Step 4.6 — Replace orchestrator.py with thin proxy

**File**: `api/app/orchestrator.py` (772 lines)

**Replace entire file** with thin Responses API proxy (~80 lines):

```python
"""
Orchestrator proxy — thin bridge to the Foundry Responses API.

The Orchestrator runs as a hosted agent inside Foundry. This module
proxies the Responses API stream to the frontend SSE format.
"""

import asyncio
import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

import app.paths  # noqa: F401

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    """Check whether the Foundry orchestrator is ready to use."""
    return bool(os.environ.get("PROJECT_ENDPOINT"))


def _get_project_client():
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    endpoint = os.environ.get("PROJECT_ENDPOINT", "").rstrip("/")
    project_name = os.environ.get("AI_FOUNDRY_PROJECT_NAME", "")
    if not endpoint or not project_name:
        raise RuntimeError("PROJECT_ENDPOINT and AI_FOUNDRY_PROJECT_NAME must be set")
    if "/api/projects/" not in endpoint:
        endpoint = endpoint.replace("cognitiveservices.azure.com", "services.ai.azure.com")
        endpoint = f"{endpoint}/api/projects/{project_name}"
    return AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())


async def run_orchestrator_session(
    alert_text: str,
    cancel_event: threading.Event = None,
    existing_thread_id: str = None,
) -> AsyncGenerator[dict, None]:
    """Stream investigation results from the hosted Orchestrator agent.

    Calls the Responses API and translates events into the SSE schema
    expected by the frontend (tool_call.start, message.delta, etc.).
    """
    client = _get_project_client()

    try:
        # Use Responses API — the hosted container handles everything
        response = client.agents.responses.create(
            agent_name="Orchestrator",
            input=alert_text,
            stream=True,
            thread_id=existing_thread_id,
        )

        session_id = ""
        for event in response:
            # Translate Responses API events → our SSE schema
            sse_event = _translate_event(event)
            if sse_event:
                yield sse_event

    except Exception as e:
        logger.exception("Orchestrator session failed")
        yield {
            "event": "error",
            "data": json.dumps({"message": str(e)}),
        }


def _translate_event(event) -> dict | None:
    """Translate a Responses API event to our SSE schema."""
    # Event mapping TBD — depends on actual Responses API event types
    # Placeholder mapping:
    event_type = getattr(event, 'type', '')
    event_data = getattr(event, 'data', {})

    mapping = {
        'response.output_item.added': 'tool_call.start',
        'response.output_item.done': 'tool_call.complete',
        'response.output_text.delta': 'message.delta',
        'response.output_text.done': 'message.complete',
        'response.completed': 'run.complete',
        'response.failed': 'error',
    }

    sse_type = mapping.get(event_type)
    if sse_type:
        return {
            "event": sse_type,
            "data": json.dumps(event_data if isinstance(event_data, dict) else {"raw": str(event_data)}),
        }
    return None
```

**Note**: The `_translate_event` function is a **placeholder**. The exact Responses API event types and data structures are not fully documented. This must be validated experimentally once the hosted agent is running.

### Step 4.7 — Delete api/app/dispatch.py

After the container image includes dispatch.py:
```bash
rm api/app/dispatch.py
```

Update `api/app/orchestrator.py` — no more `from app.dispatch import dispatch_field_engineer` (it's in the container now).

### Step 4.8 — Delete api/app/agent_ids.py

With named agents and the thin proxy, agent discovery is no longer needed at runtime:
```bash
rm api/app/agent_ids.py
```

Remove imports from `orchestrator.py` (already replaced in Step 4.6).

### Step 4.9 — Add ACR_NAME and image version to azure_config.env

**Files**: `azure_config.env`, `azure_config.env.template`

```
ACR_NAME=
AGENT_IMAGE_VERSION=latest
```

### Step 4.10 — Verification

```bash
# Build and push image
./scripts/build_agent_image.sh

# Provision hosted orchestrator
cd scripts && uv run python provision_agents.py

# Test via curl
SID=$(curl -s http://localhost:5000/api/sessions -X POST \
  -H 'Content-Type: application/json' \
  -d '{"scenario":"test","alert_text":"test alert"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['session_id'])")
curl -s -N "http://localhost:5000/api/sessions/$SID/stream"
```

---

## Phase 5: Memory Integration

**Duration**: 1–2 days  
**Risk**: Medium (preview API)  
**Gate**: Agents can recall context from previous investigations

### Step 5.1 — Create memory store provisioning script

**New file**: `scripts/provision_memory.py`

```python
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    MemoryStoreDefaultDefinition,
    MemoryStoreDefaultOptions,
)
from azure.identity import DefaultAzureCredential

client = AIProjectClient(
    endpoint=os.environ["PROJECT_ENDPOINT"],
    credential=DefaultAzureCredential(),
)

store = client.memory_stores.create(
    name="noc-investigation-memory",
    definition=MemoryStoreDefaultDefinition(
        options=MemoryStoreDefaultOptions(),
    ),
)
print(f"Created memory store: {store.name}")
```

**Cross-ref**: `azure-ai-projects-py/references/api-reference.md` §8 — Memory Classes:
```python
from azure.ai.projects.models import (
    MemoryStoreDefinition,
    MemoryStoreDefaultDefinition,
    MemoryStoreDefaultOptions,
)
```

### Step 5.2 — Add MemorySearchPreviewTool to all agents

**File**: `scripts/agent_provisioner.py`

**Add import**:
```python
from azure.ai.projects.models import MemorySearchPreviewTool
```

**Add to each agent's tools list**:
```python
tools=[
    ...,  # existing tools
    MemorySearchPreviewTool(),
]
```

**Cross-ref**: `azure-ai-projects-py/references/tools.md` — Tools Quick Reference:
| Tool | Class | Connection Required | Use Case |
|------|-------|---------------------|----------|
| Memory Search | `MemorySearchPreviewTool` | No | Agent memory |

**Cross-ref**: `azure-ai-projects-py/references/api-reference.md` line 185: `MemorySearchPreviewTool` is in the tool type hierarchy.

### Step 5.3 — Verification

```bash
# Provision memory store
cd scripts && uv run python provision_memory.py

# Re-provision agents with memory tool
cd scripts && uv run python provision_agents.py

# Test: run two investigations, check if second one remembers first
```

---

## Phase 6: Evaluation & Insights

**Duration**: 1–2 days  
**Risk**: Low (non-blocking, additive)  
**Gate**: Scheduled evaluations running, insights visible in Foundry portal

### Step 6.1 — Create evaluation provisioning script

**New file**: `scripts/provision_evaluations.py`

```python
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    Evaluator,
    EvaluatorType,
    Schedule,
    CronTrigger,
    EvaluationScheduleTask,
)
from azure.identity import DefaultAzureCredential

client = AIProjectClient(
    endpoint=os.environ["PROJECT_ENDPOINT"],
    credential=DefaultAzureCredential(),
)

# Groundedness evaluation
groundedness_eval = client.evaluations.create(
    evaluator=Evaluator(type=EvaluatorType.GROUNDEDNESS),
)
print(f"Created groundedness evaluator: {groundedness_eval.id}")

# Schedule daily
schedule = client.schedules.create(
    name="daily-investigation-quality",
    trigger=CronTrigger(
        expression="0 6 * * *",
        time_zone="Australia/Sydney",
    ),
    task=EvaluationScheduleTask(evaluation_id=groundedness_eval.id),
)
print(f"Created schedule: {schedule.name}")
```

**Cross-ref**: `azure-ai-projects-py/references/api-reference.md` §7 — Evaluation Classes  
**Cross-ref**: `azure-ai-projects-py/references/api-reference.md` §9 — Schedule & Trigger Classes

### Step 6.2 — Create insights script

**New file**: `scripts/run_insights.py`

```python
from azure.ai.projects.models import (
    AgentClusterInsightsRequest,
    InsightModelConfiguration,
)

insights = client.insights.create(
    request=AgentClusterInsightsRequest(
        agent_name="Orchestrator",
        model_configuration=InsightModelConfiguration(model="gpt-4.1"),
    ),
)
for cluster in insights.clusters:
    print(f"Cluster: {cluster.summary} ({cluster.count} investigations)")
```

**Cross-ref**: `azure-ai-projects-py/references/api-reference.md` §13 — Insight Classes

---

## Phase 7: Structured Outputs & Frontend

**Duration**: 2 days  
**Risk**: Medium  
**Gate**: Frontend renders typed investigation results

### Step 7.1 — Add CaptureStructuredOutputsTool to Orchestrator

**File**: `scripts/agent_provisioner.py`, Orchestrator tools

```python
from azure.ai.projects.models import CaptureStructuredOutputsTool

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

# Add to orchestrator tools:
tools=[
    *connected_tools,
    dispatch_tool_def,
    MemorySearchPreviewTool(),
    structured_output,  # NEW
]
```

**Cross-ref**: `azure-ai-projects-py/references/api-reference.md` line 183: `CaptureStructuredOutputsTool` in tool hierarchy.

### Step 7.2 — Add InvestigationResult type to frontend

**File**: `frontend/src/types/conversation.ts`

```typescript
export interface InvestigationResult {
  root_cause: string;
  affected_nodes: string[];
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
  recommended_action: string;
  dispatch_required: boolean;
}
```

### Step 7.3 — Update AssistantMessage to render structured results

**File**: `frontend/src/components/AssistantMessage.tsx`

Add a new `InvestigationResultCard` component that renders typed fields instead of raw markdown when structured output is available.

### Step 7.4 — Verification

```bash
# Full end-to-end test
# Submit alert → verify structured JSON in run.complete event → verify frontend renders typed card
```

---

## Summary: File Change Manifest

### Files Created (New)

| File | Phase | Lines | Purpose |
|------|-------|-------|---------|
| `agent-container/Dockerfile` | 4 | ~10 | Hosted agent container |
| `agent-container/pyproject.toml` | 4 | ~10 | Container dependencies |
| `agent-container/app/__init__.py` | 4 | 1 | Package marker |
| `agent-container/app/main.py` | 4 | ~40 | Responses protocol handler |
| `agent-container/app/dispatch.py` | 4 | 139 | Moved from api/app/ |
| `infra/modules/container-registry.bicep` | 4 | ~35 | ACR resource |
| `scripts/build_agent_image.sh` | 4 | ~15 | Image build script |
| `scripts/provision_memory.py` | 5 | ~25 | Memory store provisioning |
| `scripts/provision_evaluations.py` | 6 | ~30 | Evaluation setup |
| `scripts/run_insights.py` | 6 | ~15 | Investigation clustering |

### Files Modified

| File | Phase | What Changes |
|------|-------|-------------|
| `api/pyproject.toml` | 1 | SDK version bump |
| `pyproject.toml` | 1 | SDK version bump |
| `scripts/agent_provisioner.py` | 1,2,3,4,5,7 | Major rewrite: versioned agents, FabricTool, AzureAISearchAgentTool, hosted orchestrator, memory, structured outputs |
| `scripts/provision_agents.py` | 1 | Add version_label, remove _build_connection_id |
| `api/app/agent_ids.py` | 1 (then delete in 4) | Switch to list_versions |
| `api/app/orchestrator.py` | 4 | Replace entirely with thin proxy |
| `api/app/session_manager.py` | 4 | Simplify (no thread bridge) |
| `infra/modules/ai-foundry.bicep` | 2 | Add Fabric connection |
| `infra/main.bicep` | 4 | Add ACR module |
| `graph-query-api/main.py` | 2 | Remove graph/telemetry router imports |
| `azure_config.env.template` | 2,4 | Add FABRIC_CONNECTION_NAME, ACR_NAME |
| `deploy.sh` | 4 | Add enablePublicHostingEnvironment REST call |
| `frontend/src/types/conversation.ts` | 7 | Add InvestigationResult type |
| `frontend/src/components/AssistantMessage.tsx` | 7 | Add structured result rendering |

### Files Deleted

| File | Phase | Lines | Reason |
|------|-------|-------|--------|
| `api/app/dispatch.py` | 4 | 139 | Moved to agent-container/ |
| `api/app/agent_ids.py` | 4 | 236 | Named agents — no discovery needed |
| `graph-query-api/router_graph.py` | 2 | 76 | FabricTool replaces OpenAPI proxy |
| `graph-query-api/router_telemetry.py` | 2 | 74 | FabricTool replaces OpenAPI proxy |
| `graph-query-api/openapi/templates/graph.yaml` | 2 | 61 | No more OpenAPI specs |
| `graph-query-api/openapi/templates/telemetry.yaml` | 2 | 61 | No more OpenAPI specs |
| **Total deleted** | | **647** | |

### Net Line Count Change

| Category | Lines |
|----------|-------|
| Lines deleted (files removed) | −647 |
| Lines deleted (orchestrator.py rewrite: 772 → ~80) | −692 |
| Lines deleted (agent_provisioner.py cleanup) | −150 |
| Lines created (new files) | +320 |
| **Net** | **~−1,169** |

---

## Cross-Reference Index

Every code pattern in this plan was validated against these reference files:

| Reference | Path | Used In |
|-----------|------|---------|
| Agent creation patterns | `skills/azure-ai-projects-py/references/agents.md` | Steps 1.3, 1.5 |
| Tool import patterns | `skills/azure-ai-projects-py/references/tools.md` | Steps 2.3, 3.1, 5.2, 7.1 |
| API reference (all classes) | `skills/azure-ai-projects-py/references/api-reference.md` | Steps 1.2, 3.1, 5.1, 6.1 |
| Import acceptance criteria | `skills/azure-ai-projects-py/references/acceptance-criteria.md` | Steps 1.2 (anti-patterns) |
| Hosted agent SKILL | `skills/hosted-agents-v2-py/SKILL.md` | Steps 4.2, 4.5 |
| Hosted agent acceptance | `skills/hosted-agents-v2-py/references/acceptance-criteria.md` | Step 4.5 (validation rules) |
| Connection patterns | `skills/azure-ai-projects-py/references/connections.md` | Step 3.1 |
| Bicep types (2025-09-01) | `bicep-types-az/.../2025-09-01/types.md` | Steps 2.1, 4.2 |
