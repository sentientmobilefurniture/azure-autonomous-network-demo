# Hosted Agents Migration — Design Document

> **Status**: Investigation / Design  
> **Date**: 2026-02-21  
> **Scope**: Full architectural assessment of migrating from Prompt Agents to Hosted Agents / Versioned Agents  
> **Source of truth**: `/home/hanchoong/microsoft_skills/skills/.github/plugins/azure-sdk-python/skills/`

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current Architecture](#2-current-architecture)
3. [Agent Definition Types Available](#3-agent-definition-types-available)
4. [Migration Option A: Versioned Prompt Agents](#4-migration-option-a-versioned-prompt-agents)
5. [Migration Option B: ImageBased Hosted Agents](#5-migration-option-b-imagebased-hosted-agents)
6. [Migration Option C: ContainerApp Agents](#6-migration-option-c-containerapp-agents)
7. [Hybrid Approach (Recommended)](#7-hybrid-approach-recommended)
8. [SDK & API Version Requirements](#8-sdk--api-version-requirements)
9. [Infrastructure Changes (Bicep)](#9-infrastructure-changes-bicep)
10. [Codebase Impact Analysis](#10-codebase-impact-analysis)
11. [New Tool Types Available](#11-new-tool-types-available)
12. [Risk Assessment](#12-risk-assessment)
13. [Migration Phases](#13-migration-phases)
14. [Decision Matrix](#14-decision-matrix)

---

## 1. Executive Summary

The Azure AI Foundry Agent Service now supports **five agent definition types**, up from one. Our demo currently uses the original `create_agent()` pattern (unversioned prompt agents). Three migration paths exist, each with different tradeoffs:

| Option | SDK | Effort | Key Win | Risk |
|--------|-----|--------|---------|------|
| **A: Versioned Prompt Agents** | GA (`1.0.0`) | Low (~1 day) | Named versioning, no delete-recreate | Minimal |
| **B: ImageBased Hosted Agents** | Beta (`2.0.0b3`) | High (~2 weeks) | Custom code inside Foundry, protocol-based | High (beta SDK, ACR, new protocol) |
| **C: ContainerApp Agents** | Beta (`2.0.0b3`) | Medium (~1 week) | Reuse existing Container App as an agent | Medium (beta SDK, ARM resource ID wiring) |

**Recommendation**: Start with **Option A** (immediate, zero-risk upgrade) then evaluate **Option C** as a stretch goal since it maps directly to our existing Container App.

---

## 2. Current Architecture

### System Topology

```
┌─────────────────────────────────────────────────┐
│  Azure Container App (ca-app-*)                 │
│  ┌───────────────────┐  ┌────────────────────┐  │
│  │  api/ (FastAPI)   │  │  graph-query-api/  │  │
│  │  port 5000        │  │  port 8100         │  │
│  │                   │  │                    │  │
│  │  orchestrator.py  │──│  /query/graph      │  │
│  │  session_mgr.py   │  │  /query/telemetry  │  │
│  │  dispatch.py      │  │  /query/search     │  │
│  │  agent_ids.py     │  │  /query/sessions   │  │
│  └───────────────────┘  └────────────────────┘  │
│           │                       │              │
│           ▼                       ▼              │
│  ┌─────────────┐       ┌────────────────────┐   │
│  │  Foundry    │       │  Cosmos DB / Fabric │   │
│  │  Agent API  │       │  (data layer)       │   │
│  └─────────────┘       └────────────────────┘   │
└─────────────────────────────────────────────────┘
```

### Agent Creation Pattern (Current)

```python
# Ephemeral, ID-based — no name versioning
agent = agents_client.create_agent(
    model="gpt-4.1",
    name="GraphExplorerAgent",
    instructions="...",
    tools=[...],
)
# Returns: agent.id (opaque UUID)
# Delete-and-recreate on every deploy
```

### Orchestration Bridge (Current)

The `orchestrator.py` (771 lines) runs the agent in a background thread with a custom `SSEEventHandler` subclass, bridging the synchronous `AgentEventHandler` callbacks to an async SSE generator via `asyncio.Queue`:

```python
class SSEEventHandler(AgentEventHandler):
    def on_run_step(self, step):    # → tool_call.start / tool_call.complete
    def on_message_delta(self, delta): # → message.start / message.delta
    def on_thread_run(self, run):   # → run status tracking
    def on_error(self, data):       # → error event

def _run_in_thread():
    # FunctionTool auto-execution (dispatch_field_engineer)
    # Retry logic (MAX_RUN_ATTEMPTS=2)
    # Cancel support
    # Thread creation/reuse for multi-turn

async def run_orchestrator_session():
    # asyncio.Queue bridge between thread and async generator
    # Yields SSE event dicts
```

### File Inventory (Agent-Related Backend)

| File | Lines | Purpose |
|------|-------|---------|
| `api/app/orchestrator.py` | 771 | SSE bridge, AgentEventHandler, thread lifecycle |
| `api/app/session_manager.py` | 367 | Session creation, multi-turn, Cosmos persistence |
| `api/app/sessions.py` | 156 | Session dataclass, subscriber fan-out |
| `api/app/dispatch.py` | 139 | `dispatch_field_engineer` FunctionTool callable |
| `api/app/agent_ids.py` | 235 | Runtime agent discovery via Foundry API |
| `api/app/routers/sessions.py` | 219 | REST/SSE endpoints for sessions |
| `scripts/agent_provisioner.py` | 415 | Agent creation (all 5 agents + tools) |
| `scripts/provision_agents.py` | 182 | CLI wrapper for provisioning |
| **Total** | **2,483** | |

---

## 3. Agent Definition Types Available

Source: `azure-ai-projects` SDK, `microsoft_skills` reference docs.

```
AgentDefinition (base)
├── PromptAgentDefinition         # AgentKind.PROMPT
│   └── Standard LLM agent with instructions + tools
│       Created via: create_version(agent_name=..., definition=PromptAgentDefinition(...))
│       SDK: azure-ai-projects >= 1.0.0 (GA)
│
├── HostedAgentDefinition         # AgentKind.HOSTED
│   └── Pre-built hosted agent with protocol version
│       SDK: azure-ai-projects >= 2.0.0b3 (beta)
│
├── ImageBasedHostedAgentDefinition  # AgentKind.IMAGE_BASED_HOSTED
│   └── Custom container running your code inside Foundry
│       Needs: ACR, container image, AgentProtocol.RESPONSES
│       SDK: azure-ai-projects >= 2.0.0b3 (beta)
│
├── ContainerAppAgentDefinition   # AgentKind.CONTAINER_APP
│   └── Points to an existing Azure Container App
│       Needs: Container App resource ID
│       SDK: azure-ai-projects >= 2.0.0b3 (beta)
│
└── WorkflowAgentDefinition       # AgentKind.WORKFLOW
    └── CSDL-based workflow definition
        SDK: azure-ai-projects >= 2.0.0b3 (beta)
```

---

## 4. Migration Option A: Versioned Prompt Agents

### What Changes

Replace `create_agent()` with `create_version()` + `PromptAgentDefinition`. Agents get persistent names and version histories instead of ephemeral UUIDs.

### Code Diff (agent_provisioner.py)

```python
# BEFORE (current)
ge = agents_client.create_agent(
    model=model,
    name="GraphExplorerAgent",
    instructions=prompts["graph_explorer"],
    tools=ge_tools,
)

# AFTER (Option A)
from azure.ai.projects.models import PromptAgentDefinition

ge = client.agents.create_version(
    agent_name="GraphExplorerAgent",
    definition=PromptAgentDefinition(
        model=model,
        instructions=prompts["graph_explorer"],
        tools=ge_tools,
    ),
    version_label="v1.0",
    description="Graph topology explorer",
)
```

### Impact

| Area | Change |
|------|--------|
| `agent_provisioner.py` | ~30 lines: `create_agent()` → `create_version()` for all 5 agents |
| `provision_agents.py` | Minimal: pass version label |
| `agent_ids.py` | Update discovery to use `list_versions()` instead of `list_agents()` |
| `orchestrator.py` | **None** — still uses `agents_client.runs.stream()` the same way |
| `session_manager.py` | **None** |
| Bicep | **None** |
| SDK | **None** — `create_version` is available in GA `1.0.0` |

### Advantages

- Zero risk — GA SDK, same runtime behavior
- Named agents persist across deploys
- Version history enables rollback
- No delete-and-recreate — `create_version` creates a new version, old one stays
- No infrastructure changes

### Disadvantages

- Does not simplify orchestrator.py
- Does not change the SSE bridge architecture
- No custom code execution inside Foundry

---

## 5. Migration Option B: ImageBased Hosted Agents

### What Changes

Package the Orchestrator logic (or the entire API) as a container image, deploy it to ACR, and register it as an `ImageBasedHostedAgentDefinition`. Foundry runs your container, manages scaling, and exposes the agent via the Responses protocol.

### Architecture (After)

```
┌────────────────────────────────────────────┐
│  Foundry Platform                          │
│                                            │
│  ┌──────────────────────────────────────┐  │
│  │  Orchestrator (ImageBasedHosted)     │  │
│  │  Image: acr.azurecr.io/noc-orch:v1  │  │
│  │  CPU: 2, Memory: 4Gi                │  │
│  │                                      │  │
│  │  Your code runs here:                │  │
│  │  - dispatch_field_engineer           │  │
│  │  - Custom SSE event formatting       │  │
│  │  - Retry logic                       │  │
│  │  - AgentProtocol.RESPONSES handler   │  │
│  └──────────┬───────────────────────────┘  │
│             │ ConnectedAgentTool            │
│  ┌──────────▼───────────────────────────┐  │
│  │  Sub-agents (PromptAgentDefinition)  │  │
│  │  GraphExplorer, Telemetry,           │  │
│  │  RunbookKB, HistoricalTicket         │  │
│  └──────────────────────────────────────┘  │
│                                            │
└────────────────────────────────────────────┘
         │
         ▼  Responses API (streaming)
┌────────────────────────────────┐
│  Container App (thin proxy)    │
│  api/ → just proxies SSE      │
│  graph-query-api/ (unchanged)  │
└────────────────────────────────┘
```

### Requirements

1. **Azure Container Registry (ACR)**
   - New Bicep resource: `Microsoft.ContainerRegistry/registries`
   - Managed identity: Foundry principal needs `AcrPull` role

2. **Container Image**
   - Dockerfile for the orchestrator agent
   - Must implement `AgentProtocol.RESPONSES` wire protocol
   - Environment variables for config (endpoint, model, etc.)

3. **Capability Host Update**
   - Account-level capability host needs `enablePublicHostingEnvironment: true`

4. **SDK Upgrade**
   - `azure-ai-projects >= 2.0.0b3` (currently beta, not GA)
   - New imports: `ImageBasedHostedAgentDefinition`, `ProtocolVersionRecord`, `AgentProtocol`

5. **CI/CD Pipeline**
   - Build & push container image to ACR on every deploy
   - Tag management (version labels)

### Agent Provisioning Code

```python
from azure.ai.projects.models import (
    ImageBasedHostedAgentDefinition,
    PromptAgentDefinition,
    ProtocolVersionRecord,
    AgentProtocol,
)

# Sub-agents remain PromptAgentDefinition
ge = client.agents.create_version(
    agent_name="GraphExplorerAgent",
    definition=PromptAgentDefinition(
        model=model,
        instructions=prompts["graph_explorer"],
        tools=ge_tools,
    ),
)

# Orchestrator becomes ImageBasedHostedAgent
orch = client.agents.create_version(
    agent_name="Orchestrator",
    definition=ImageBasedHostedAgentDefinition(
        container_protocol_versions=[
            ProtocolVersionRecord(
                protocol=AgentProtocol.RESPONSES,
                version="v1"
            )
        ],
        image=f"{acr_name}.azurecr.io/noc-orchestrator:v{version}",
        cpu="2",
        memory="4Gi",
        tools=[
            *connected_tools,  # ConnectedAgentTool for sub-agents
            dispatch_tool_def,  # FunctionTool for dispatch
        ],
        environment_variables={
            "AZURE_AI_PROJECT_ENDPOINT": project_endpoint,
            "MODEL_NAME": model,
            "GRAPH_QUERY_API_URI": graph_query_api_uri,
        },
    ),
)
```

### orchestrator.py Changes

The entire `orchestrator.py` would be **replaced** by a Responses protocol handler inside the container image. The current SSE bridge (`AgentEventHandler` → `asyncio.Queue` → async generator) would be eliminated:

```python
# BEFORE: 771 lines of SSE bridging
class SSEEventHandler(AgentEventHandler):
    def on_run_step(self, step): ...
    def on_message_delta(self, delta): ...

def _run_in_thread(): ...
async def run_orchestrator_session(): ...

# AFTER: ~50 lines — just call the Responses API
async def run_orchestrator_session(alert_text, cancel_event, existing_thread_id):
    response = await client.agents.responses.create(
        agent_name="Orchestrator",
        input=alert_text,
        stream=True,
    )
    async for event in response:
        yield {"event": event.type, "data": json.dumps(event.data)}
```

**Caveat**: The exact Responses API streaming interface is not fully documented yet. The `AgentProtocol.RESPONSES` protocol spec is still evolving.

### Impact

| Area | Change |
|------|--------|
| `agent_provisioner.py` | Major rewrite: `ImageBasedHostedAgentDefinition` for orchestrator |
| `orchestrator.py` | **Delete entirely** — replaced by container image + thin Responses proxy |
| `dispatch.py` | Moves into container image |
| `session_manager.py` | Simplify — no more thread bridging |
| `agent_ids.py` | Simplify — use named agents instead of UUID discovery |
| Bicep | Add ACR, update capability host, add AcrPull role |
| SDK | **Breaking**: upgrade to `2.0.0b3` (beta) |
| CI/CD | **New**: container build + push pipeline |
| Dockerfile | **New**: agent container Dockerfile |

### Advantages

- Orchestrator logic runs inside Foundry (managed scaling, no Container App needed for agent)
- Responses API streaming eliminates SSE bridge plumbing
- FunctionTool execution happens natively inside the container
- Agent versioning with container image tags
- Foundry manages agent lifecycle (start, stop, scale)

### Disadvantages

- **Beta SDK** (`2.0.0b3`) — breaking changes expected
- **AgentProtocol.RESPONSES** wire protocol not fully documented
- **ACR dependency** — new infrastructure to manage
- **Debugging harder** — logs inside Foundry-managed containers
- **Cold start** — container pull + startup latency
- **Resource limits** — max 4 CPU, 8Gi RAM per agent
- **No direct access** to the running container (no SSH, no port forwarding)
- **Significant effort** (~2 weeks for container, protocol, CI/CD)

---

## 6. Migration Option C: ContainerApp Agents

### What Changes

Register your **existing Container App** as an agent using `ContainerAppAgentDefinition`. The Container App you already deploy becomes a Foundry-managed agent endpoint.

### Architecture (After)

```
┌────────────────────────────────────────────┐
│  Foundry Platform                          │
│                                            │
│  ┌──────────────────────────────────────┐  │
│  │  Orchestrator (ContainerAppAgent)    │  │
│  │  container_app_id: /subscriptions/   │  │
│  │    .../containerApps/ca-app-*        │  │
│  │                                      │  │
│  │  → Routes to your Container App      │  │
│  │  → Your code handles everything      │  │
│  └──────────┬───────────────────────────┘  │
│             │ ConnectedAgentTool            │
│  ┌──────────▼───────────────────────────┐  │
│  │  Sub-agents (PromptAgentDefinition)  │  │
│  └──────────────────────────────────────┘  │
└────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────┐
│  Container App (YOUR code)     │
│  api/ → orchestrator.py        │
│  graph-query-api/ (unchanged)  │
│                                │
│  You still own the runtime,    │
│  but Foundry can invoke your   │
│  app as an agent.              │
└────────────────────────────────┘
```

### Code

```python
from azure.ai.projects.models import ContainerAppAgentDefinition

orch = client.agents.create_version(
    agent_name="Orchestrator",
    definition=ContainerAppAgentDefinition(
        container_app_id=(
            f"/subscriptions/{subscription_id}"
            f"/resourceGroups/{resource_group}"
            f"/providers/Microsoft.App/containerApps/{container_app_name}"
        ),
    ),
)
```

### Impact

| Area | Change |
|------|--------|
| `agent_provisioner.py` | Moderate: `ContainerAppAgentDefinition` for orchestrator |
| `orchestrator.py` | May need to implement a protocol endpoint (TBD) |
| Bicep | Add role assignment for Foundry → Container App invocation |
| SDK | **Breaking**: upgrade to `2.0.0b3` (beta) |

### Advantages

- Reuses your existing Container App — no ACR, no new images
- You keep full control over the runtime
- Debugging is easy (it's your Container App, you have logs)
- No cold start issues (Container App is already running)

### Disadvantages

- **Beta SDK** required
- **Sparse documentation** — `ContainerAppAgentDefinition` has minimal docs
- **Unknown protocol requirements** — unclear what endpoints the Container App must implement
- **Potential breaking changes** — most minimal docs of all options

---

## 7. Hybrid Approach (Recommended)

### Phase 1: Versioned Prompt Agents (Immediate — 1 day)

Switch from `create_agent()` to `create_version()` + `PromptAgentDefinition`. No SDK upgrade needed. Gets you:

- Named agents that persist across deploys
- Version history with rollback capability
- No delete-and-recreate provisioning

### Phase 2: FabricTool Integration (Short-term — 3 days)

Replace the custom OpenAPI tools for graph queries with the native `MicrosoftFabricPreviewTool` / `FabricTool`. This is available in the current SDK and could eliminate the `graph-query-api` graph/telemetry endpoints.

```python
from azure.ai.agents.models import FabricTool

fabric = FabricTool(connection_id=fabric_connection_id)

ge = client.agents.create_version(
    agent_name="GraphExplorerAgent",
    definition=PromptAgentDefinition(
        model=model,
        instructions=prompts["graph_explorer"],
        tools=[fabric],
    ),
)
```

### Phase 3: Hosted/ContainerApp Agents (When GA — TBD)

Wait for `azure-ai-projects >= 2.0.0` GA release, then evaluate:

- If **ContainerAppAgentDefinition** matures with good docs → use Option C (lowest effort)
- If **ImageBasedHostedAgentDefinition** proves stable → consider Option B for the orchestrator (biggest reward but biggest effort)
- Either way, sub-agents should remain `PromptAgentDefinition` — they don't need custom code

---

## 8. SDK & API Version Requirements

### Current Versions

| Package | Installed | Latest Stable | Latest Beta |
|---------|-----------|---------------|-------------|
| `azure-ai-projects` | 1.0.0 | 1.0.0 (Jul 2025) | 2.0.0b4 |
| `azure-ai-agents` | 1.2.0b6 | 1.1.0 (Aug 2025) | — |
| `azure-identity` | 1.25.2 | Current | — |

### What Each Option Requires

| Feature | SDK Required | API Version |
|---------|-------------|-------------|
| `create_agent()` (current) | `azure-ai-agents >= 1.0.0` | v1 |
| `create_version()` + `PromptAgentDefinition` | `azure-ai-projects >= 1.0.0` | v1 |
| `ImageBasedHostedAgentDefinition` | `azure-ai-projects >= 2.0.0b3` | v1 |
| `ContainerAppAgentDefinition` | `azure-ai-projects >= 2.0.0b3` | v1 |
| `FabricTool` | `azure-ai-agents >= 1.0.0` | v1 |
| `McpTool` | `azure-ai-agents >= 1.0.0` | v1 |
| `A2APreviewTool` | `azure-ai-agents >= 1.0.0` | v1 |

### Bicep API Versions

| Resource | Current | Latest Stable |
|----------|---------|---------------|
| `accounts` | `2025-06-01` | `2025-09-01` |
| `accounts/projects` | `2025-06-01` | `2025-09-01` |
| `accounts/capabilityHosts` | `2025-06-01` | `2025-09-01` |
| `accounts/deployments` | `2025-09-01` | `2025-09-01` |
| `accounts/connections` | `2025-06-01` | `2025-09-01` |
| `accounts/projects/capabilityHosts` | `2025-06-01` | `2025-09-01` |

---

## 9. Infrastructure Changes (Bicep)

### Option A: Versioned Prompt Agents

**No Bicep changes required.**

### Option B: ImageBased Hosted Agents

New resources:

```bicep
// 1. Azure Container Registry
resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  sku: { name: 'Basic' }
  properties: { adminUserEnabled: false }
}

// 2. AcrPull role for Foundry managed identity
resource acrPullRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: acr
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '7f951dda-4ed3-4680-a7ca-43fe172d538d'  // AcrPull
    )
    principalId: foundry.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// 3. Update account capability host
resource accountCapabilityHost '...' = {
  properties: {
    capabilityHostKind: 'Agents'
    enablePublicHostingEnvironment: true  // NEW — required for hosted agents
    storageConnections: [...]
    vectorStoreConnections: [...]
    threadStorageConnections: [...]
  }
}
```

### Option C: ContainerApp Agents

Minimal changes:

```bicep
// Role assignment: Foundry → Container App invocation
// (exact role TBD — docs are sparse)
```

---

## 10. Codebase Impact Analysis

### Files Changed Per Option

| File | Option A | Option B | Option C |
|------|----------|----------|----------|
| `scripts/agent_provisioner.py` | ~30 lines | Major rewrite | Moderate |
| `scripts/provision_agents.py` | ~5 lines | ~20 lines | ~10 lines |
| `api/app/orchestrator.py` | **None** | **Delete/rewrite entirely** | Protocol endpoint |
| `api/app/session_manager.py` | **None** | Simplify significantly | Minor changes |
| `api/app/sessions.py` | **None** | **None** | **None** |
| `api/app/dispatch.py` | **None** | Move into container image | **None** |
| `api/app/agent_ids.py` | Update to versioned lookup | Simplify (named agents) | Simplify |
| `api/app/routers/sessions.py` | **None** | SSE proxy simplification | **None** |
| `infra/modules/ai-foundry.bicep` | **None** | ACR + role + caphost update | Role assignment |
| `Dockerfile` | **None** | **New** agent Dockerfile | **None** |
| `pyproject.toml` | **None** | SDK upgrade | SDK upgrade |
| CI/CD | **None** | **New** container build pipeline | **None** |

### Estimated Effort

| Option | Development | Testing | Total |
|--------|-------------|---------|-------|
| A | 4 hours | 2 hours | **~1 day** |
| B | 8 days | 4 days | **~2 weeks** |
| C | 3 days | 2 days | **~1 week** |

---

## 11. New Tool Types Available

The latest SDK exposes several tools we aren't using that could enhance the demo:

### Immediately Useful (GA SDK)

| Tool | Current Alternative | Potential Use |
|------|-------------------|---------------|
| `FabricTool` | Custom OpenAPI tools | Direct Fabric graph/KQL queries — could eliminate `graph-query-api` graph/telemetry endpoints |
| `McpTool` | None | Expose `graph-query-api` as an MCP server |
| `ConnectedAgentTool` | Already using | No change needed |

### Future Potential (Beta SDK)

| Tool | Description | Potential Use |
|------|-------------|---------------|
| `MicrosoftFabricPreviewTool` | Native Fabric integration | Graph + telemetry queries without OpenAPI proxy |
| `A2APreviewTool` | Agent-to-Agent protocol | Cross-project agent orchestration |
| `BrowserAutomationPreviewTool` | Browser automation | Live network dashboard screenshots |
| `MemorySearchPreviewTool` | Agent memory | Cross-session investigation context |
| `CaptureStructuredOutputsTool` | Structured output extraction | Typed investigation results |

### FabricTool Deep Dive

This is the most relevant new tool. It could replace our custom `graph-query-api` OpenAPI endpoints:

```python
from azure.ai.agents.models import FabricTool

# Instead of OpenApiTool + custom API
fabric = FabricTool(connection_id=fabric_connection_id)

# Agent can query Fabric directly:
# - KQL queries against Eventhouse
# - Graph queries against Graph Model
# - Lakehouse table reads
```

**Trade-off**: `FabricTool` gives the agent direct access to Fabric, but you lose the structured response parsing (`_parse_structured_output`) that currently extracts visualizations, sub-steps, and analysis sections from agent responses. You'd need to move that parsing to the frontend or to the agent's instructions.

---

## 12. Risk Assessment

### Option A: Versioned Prompt Agents

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `create_version` API behavior differs from `create_agent` | Low | Low | Test with one agent first |
| Agent name collisions | Low | Low | Version labels prevent collisions |
| **Overall risk**: **Low** | | | |

### Option B: ImageBased Hosted Agents

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Beta SDK breaking changes | **High** | **High** | Pin version, test on every SDK update |
| AgentProtocol.RESPONSES underdocumented | **High** | **High** | Build incrementally, have fallback |
| Container cold start latency | Medium | Medium | Pre-warm, use keep-alive |
| ACR/IAM permission issues | Medium | Medium | Test role assignments early |
| Resource limits (4 CPU / 8Gi) | Low | Medium | Current Container App uses ~1 CPU |
| Debugging difficulty | Medium | Medium | Structured logging, App Insights |
| **Overall risk**: **High** | | | |

### Option C: ContainerApp Agents

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Beta SDK breaking changes | **High** | **High** | Same as Option B |
| Sparse documentation | **High** | Medium | Experiment early, read SDK source |
| Unknown protocol requirements | **High** | **High** | Test with minimal implementation |
| **Overall risk**: **Medium-High** | | | |

---

## 13. Migration Phases

### Phase 1: Versioned Prompt Agents (Option A)

**Scope**: Replace `create_agent` → `create_version` + `PromptAgentDefinition`

| Step | File | Change |
|------|------|--------|
| 1 | `scripts/agent_provisioner.py` | Use `create_version()` + `PromptAgentDefinition` for all 5 agents |
| 2 | `scripts/agent_provisioner.py` | Remove `cleanup_existing()` delete-and-recreate logic |
| 3 | `scripts/provision_agents.py` | Add `--version-label` CLI argument |
| 4 | `api/app/agent_ids.py` | Update discovery to use `list_versions()` / named lookup |
| 5 | Test | Verify provisioning, runtime discovery, streaming |

**Duration**: 1 day  
**Risk**: Minimal  
**SDK**: No upgrade needed (GA `1.0.0` supports `create_version`)

### Phase 2: FabricTool Evaluation

**Scope**: Evaluate replacing OpenAPI tools with native `FabricTool`

| Step | Action |
|------|--------|
| 1 | Create a Fabric connection in accouns/connections |
| 2 | Create a test agent with `FabricTool` |
| 3 | Evaluate: can it run GQL queries? KQL queries? |
| 4 | Compare output format with current `_parse_structured_output` |
| 5 | Decision: replace OpenAPI tools or keep them |

**Duration**: 2–3 days  
**Risk**: Low (evaluation only, no production changes)

### Phase 3: Hosted Agents Prototype (When SDK Goes GA)

**Scope**: Prototype either ContainerApp or ImageBased hosted agent for the Orchestrator

| Step | Action |
|------|--------|
| 1 | Upgrade SDK to `azure-ai-projects >= 2.0.0` (when GA) |
| 2 | Prototype `ContainerAppAgentDefinition` with existing Container App |
| 3 | If ContainerApp doesn't work, prototype `ImageBasedHostedAgentDefinition` |
| 4 | Build Responses protocol handler |
| 5 | Test streaming, multi-turn, cancel |
| 6 | If successful, migrate orchestrator.py |

**Duration**: 1–2 weeks  
**Risk**: Medium-High  
**Gate**: SDK must be GA

---

## 14. Decision Matrix

| Criteria | Weight | Option A (Versioned Prompt) | Option B (ImageBased Hosted) | Option C (ContainerApp) |
|----------|--------|---------------------------|--------------------------|----------------------|
| Effort | 25% | ⭐⭐⭐⭐⭐ (minimal) | ⭐⭐ (high) | ⭐⭐⭐ (moderate) |
| Risk | 25% | ⭐⭐⭐⭐⭐ (GA SDK) | ⭐⭐ (beta SDK) | ⭐⭐⭐ (beta SDK) |
| Code reduction | 15% | ⭐⭐ (none) | ⭐⭐⭐⭐⭐ (delete orchestrator.py) | ⭐⭐⭐ (simplify) |
| Versioning | 15% | ⭐⭐⭐⭐⭐ (full) | ⭐⭐⭐⭐⭐ (full + image tags) | ⭐⭐⭐⭐⭐ (full) |
| Debugability | 10% | ⭐⭐⭐⭐⭐ (same as today) | ⭐⭐ (Foundry logs) | ⭐⭐⭐⭐⭐ (your Container App) |
| Demo value | 10% | ⭐⭐⭐ (incremental) | ⭐⭐⭐⭐⭐ (cutting edge) | ⭐⭐⭐⭐ (modern pattern) |
| **Weighted** | | **4.2** | **3.1** | **3.5** |

### Recommendation

1. **Do Option A now** — immediate win, zero risk, 1 day of work
2. **Evaluate FabricTool** — could simplify tool architecture significantly
3. **Wait for `2.0.0` GA** before attempting Option B or C
4. **When GA arrives**, try Option C first (lowest delta from current architecture)

---

## Appendix A: Key SDK Import Patterns

Source: `microsoft_skills/skills/.github/plugins/azure-sdk-python/skills/azure-ai-projects-py/references/acceptance-criteria.md`

```python
# GA (current) — create_version with PromptAgentDefinition
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition, AgentKind
from azure.ai.agents.models import (
    ConnectedAgentTool, OpenApiTool, AzureAISearchTool,
    FunctionTool, ToolSet, FabricTool, McpTool,
)

# Beta (2.0.0b3+) — hosted agents
from azure.ai.projects.models import (
    ImageBasedHostedAgentDefinition,
    ContainerAppAgentDefinition,
    ProtocolVersionRecord,
    AgentProtocol,
)
```

## Appendix B: Reference Material Locations

| Topic | Path |
|-------|------|
| Agent operations | `microsoft_skills/skills/.github/plugins/azure-sdk-python/skills/azure-ai-projects-py/references/agents.md` |
| Full API reference | `microsoft_skills/skills/.github/plugins/azure-sdk-python/skills/azure-ai-projects-py/references/api-reference.md` |
| Tool reference | `microsoft_skills/skills/.github/plugins/azure-sdk-python/skills/azure-ai-projects-py/references/tools.md` |
| Acceptance criteria | `microsoft_skills/skills/.github/plugins/azure-sdk-python/skills/azure-ai-projects-py/references/acceptance-criteria.md` |
| Hosted agents (v2) | `microsoft_skills/skills/.github/plugins/azure-sdk-python/skills/agents-v2-py/SKILL.md` |
| Hosted agents (detail) | `microsoft_skills/skills/.github/plugins/azure-sdk-python/skills/hosted-agents-v2-py/SKILL.md` |
| Bicep types (CognitiveServices) | `microsoft_skills/bicep-types-az/generated/cognitiveservices/microsoft.cognitiveservices/` |
| REST API specs | `microsoft_skills/azure-rest-api-specs/specification/cognitiveservices/` |
