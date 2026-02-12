# Autonomous Network NOC Demo — Copilot Instructions

## Agent! First, read these materials to gain a thorough understanding of the project.
ocumentation/ARCHITECTURE.md
documentation/SCENARIO.md
README.md

## Demo built with Claude Opus 4.6 using [skills](https://github.com/microsoft/skills)

Skills used during development (read the relevant skill before modifying its area):

| Skill | Local path | When to read |
|-------|------------|--------------|
| azure-ai-projects-py | `~/references/skills/.github/skills/azure-ai-projects-py` | Agent/tool code, SDK patterns, imports |
| hosted-agents-v2-py | `~/references/skills/.github/skills/hosted-agents-v2-py` | Hosted agent deployment patterns |
| mcp-builder | `~/references/skills/.github/skills/mcp-builder` | MCP server code (`api/app/mcp/`) |
| fastapi-router-py | (training data) | FastAPI routers, SSE streaming |
| frontend-ui-dark-ts | (training data) | Dark theme, glass morphism, CSS variables |
| azure-appconfiguration-py | `~/references/skills/.github/skills/azure-appconfiguration-py` | App Configuration integration |
| azure-containerregistry-py | `~/references/skills/.github/skills/azure-containerregistry-py` | ACR / Container App deployment |

### Key reference files to read before writing agent code

```
~/references/skills/.github/skills/azure-ai-projects-py/references/tools.md        — OpenApiTool, AzureAISearchTool, ConnectedAgentTool, FabricTool
~/references/skills/.github/skills/azure-ai-projects-py/references/agents.md       — create_agent, threads, runs, streaming
~/references/skills/.github/skills/azure-ai-projects-py/references/connections.md  — connection listing, connection ID formats
~/references/skills/.github/skills/azure-ai-projects-py/references/api-reference.md — AIProjectClient setup, endpoint formats
~/references/skills/.github/skills/azure-ai-projects-py/references/acceptance-criteria.md — complete import lists, SDK version requirements
```

---

## Project Overview

Multi-agent NOC (Network Operations Center) diagnosis demo. An alert enters via
a React frontend, flows through a FastAPI backend that streams SSE progress, and
reaches an orchestrator agent in Azure AI Foundry. The orchestrator delegates to
four specialist agents, each backed by a distinct data source.

Full architecture documentation: `documentation/ARCHITECTURE.md`

---

## Architecture — Agent Pattern (V2: OpenApiTool)

5 Foundry Agents in a Connected Agents orchestrator pattern:

| Agent | Tool | Data Source |
|-------|------|-------------|
| GraphExplorerAgent | `OpenApiTool` | graph-query-api → Fabric GraphModel (GQL) |
| TelemetryAgent | `OpenApiTool` | graph-query-api → Fabric Eventhouse (KQL) |
| RunbookKBAgent | `AzureAISearchTool` | runbooks-index (hybrid search) |
| HistoricalTicketAgent | `AzureAISearchTool` | tickets-index (hybrid search) |
| Orchestrator | `ConnectedAgentTool` | Wired to all 4 above |

**Why OpenApiTool instead of FabricTool for Graph/Telemetry:** `ConnectedAgentTool`
sub-agents run server-side on Foundry and cannot execute client-side `FunctionTool`
callbacks. `OpenApiTool` makes server-side REST calls natively. The `graph-query-api`
Container App proxies queries to Fabric (GQL and KQL). See `documentation/ARCHITECTURE.md`
for the full rationale.

---

## SDK Versions — Critical Constraints

| Package | Pinned version | Why |
|---------|---------------|-----|
| `azure-ai-projects` | `>=1.0.0,<2.0.0` | **v2 has breaking API changes** — different client setup, different method names |
| `azure-ai-agents` | `==1.2.0b6` | Specific beta with `OpenApiTool`, `ConnectedAgentTool`, `AzureAISearchTool` |
| `azure-kusto-data` | `>=4.6.0` | KQL queries against Eventhouse |

### SDK patterns that MUST be followed

- Use `AIProjectClient` with **project-scoped endpoint**:
  ```python
  endpoint = f"{base_endpoint}/api/projects/{project_name}"
  client = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())
  ```
- Access agents via `client.agents` (returns `AgentsClient`)
- Connection IDs must be **project-scoped**: `…/accounts/{acct}/projects/{proj}/connections/{name}`
- `AgentEventHandler` is synchronous — bridge to async via `threading.Thread` + `asyncio.Queue`
  (see `api/app/orchestrator.py` for the canonical implementation)
- Streaming uses `agents_client.runs.stream(thread_id, agent_id, event_handler=handler)`

### Common mistakes to avoid

- **Do NOT use azure-ai-projects v2** — the import paths, client construction, and method
  signatures are completely different. Always check the pinned version.
- **Do NOT use `EventSource` for POST requests** — browser `EventSource` is GET-only.
  The frontend uses `@microsoft/fetch-event-source` for POST-based SSE.
- **Do NOT try to use `FunctionTool` inside `ConnectedAgentTool` sub-agents** — they run
  server-side and cannot execute local callbacks.

---

## Project Structure (3 independent Python environments)

Each has its own `pyproject.toml` and `uv.lock`. Run `uv` commands from each directory:

| Directory | Purpose | Run locally |
|-----------|---------|-------------|
| `./` (root) | Provisioning scripts (`scripts/`) | `cd scripts && uv run python provision_agents.py` |
| `api/` | FastAPI backend (REST + SSE + MCP) | `cd api && uv run uvicorn app.main:app --reload --port 8000` |
| `graph-query-api/` | Fabric proxy micro-service | `cd graph-query-api && source ../azure_config.env && uv run uvicorn main:app --port 8100` |
| `frontend/` | React SPA (npm, not uv) | `cd frontend && npm run dev` |

---

## Configuration — Single Source of Truth

**`azure_config.env`** (gitignored) holds ALL runtime config. Template: `azure_config.env.template`.

- **User-set values:** `AZURE_LOCATION`, `MODEL_DEPLOYMENT_NAME`, `FABRIC_SKU`, index names, etc.
- **Auto-populated by `postprovision.sh`:** resource names, endpoints, IDs from `azd` outputs
- **Auto-populated by scripts:** Fabric IDs (`populate_fabric_config.py`), agent IDs (`provision_agents.py`)
- **`preprovision.sh`** syncs selected env vars into `azd env` so Bicep can read them

Scripts use `from _config import …` (shared module) or `load_config()` for config access.

---

## File Conventions

| Pattern | Convention |
|---------|-----------|
| Agent prompts | `data/prompts/foundry_*.md` — each has `## Foundry Agent Description` section |
| Provisioning scripts | `scripts/*.py` — import from `scripts/_config.py` for shared constants |
| Test scripts | `scripts/testing_scripts/*.py` — CLI test/debug utilities |
| Infrastructure | `infra/modules/*.bicep` — individual resource modules |
| Agent IDs | `scripts/agent_ids.json` — output of `provision_agents.py`, input to API |

---

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/alert` | Submit alert → SSE stream of orchestrator steps |
| GET | `/api/agents` | List provisioned agents (from `agent_ids.json` or stubs) |
| GET | `/api/logs` | SSE stream of backend log output |
| GET | `/api/fabric-logs` | SSE stream of synthetic graph-query-api logs |
| GET | `/health` | Health check |

---

## SSE Event Protocol

Events streamed on `POST /api/alert`:

| Event | Payload | Purpose |
|-------|---------|---------|
| `run_start` | `{run_id, alert, timestamp}` | Diagnosis started |
| `step_thinking` | `{agent, status}` | Agent working (shows thinking indicator) |
| `step_start` | `{step, agent}` | Agent step starting |
| `step_complete` | `{step, agent, duration, query, response, error?}` | Agent returned; `error: true` on failure |
| `message` | `{text}` | Final diagnosis (markdown) |
| `error` | `{message}` | Run-level error |
| `run_complete` | `{steps, tokens, time}` | Run finished with summary |

---

## Frontend Architecture (V4)

React 18 + TypeScript + Vite + Tailwind CSS dark theme.

**Three-zone layout:** Header (fixed) → MetricsBar (resizable height) → Investigation + Diagnosis (resizable height, side-by-side).

Zone 2 and Zone 3 use a vertical `PanelGroup` (react-resizable-panels). MetricsBar has 7 horizontally resizable panels: 4 KPI cards + alert chart + API log stream + Fabric log stream.

**Key state hook:** `useInvestigation()` in `hooks/useInvestigation.ts` — owns all SSE state. Uses `@microsoft/fetch-event-source` for POST-based SSE.

**Component file list:** `components/Header.tsx`, `MetricsBar.tsx`, `MetricCard.tsx`, `AlertChart.tsx`, `LogStream.tsx`, `InvestigationPanel.tsx`, `AlertInput.tsx`, `AgentTimeline.tsx`, `StepCard.tsx`, `ThinkingDots.tsx`, `ErrorBanner.tsx`, `DiagnosisPanel.tsx`, `HealthDot.tsx`.

---

## Deployment

| Component | Local | Production |
|-----------|-------|------------|
| API | `uvicorn :8000` | Azure Container Apps |
| graph-query-api | `uvicorn :8100` | Azure Container Apps (`azd deploy graph-query-api`) |
| Frontend | Vite `:5173` | Azure Static Web Apps |
| Infrastructure | — | `azd up` (Bicep) |

`graph-query-api` uses `remoteBuild: true` in `azure.yaml` — Docker images built in ACR.

---

## Provisioning Order (one-time setup)

```
1. azd up                         → Azure resources + graph-query-api deployed
2. provision_lakehouse.py          → Fabric workspace + lakehouse + CSV data
3. provision_eventhouse.py         → Eventhouse + KQL tables + CSV data
4. provision_ontology.py           → Ontology (graph index) on lakehouse data
5. populate_fabric_config.py       → Discover Fabric IDs → azure_config.env
6. assign_fabric_role.py           → Grant Container App identity Fabric workspace access
7. create_runbook_indexer.py       → AI Search index from blob runbooks
8. create_tickets_indexer.py       → AI Search index from blob tickets
9. provision_agents.py             → Create 5 Foundry agents → agent_ids.json
```
