# Autonomous Network NOC Demo

> **Note:** Ontology is a preview feature and may exhibit unexpected behaviors. Sweden Central may be faster due to less regional contention. Expect 20-90 minutes for the graph to finish indexing after creation.

## Prerequisites

### Tools

| Tool | Install | Verify |
|------|---------|--------|
| **Python 3.11+** | [python.org](https://www.python.org/downloads/) or `sudo apt install python3` | `python3 --version` |
| **uv** (package manager) | `curl -LsSf https://astral.sh/uv/install.sh \| sh` | `uv --version` |
| **Node.js 20+** | [nodesource](https://deb.nodesource.com/setup_20.x) or `nvm install 20` | `node --version` |
| **Azure CLI (`az`)** | [Install Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli-linux) | `az --version` |
| **Azure Developer CLI (`azd`)** | `curl -fsSL https://aka.ms/install-azd.sh \| bash` | `azd version` |

### Authentication

```bash
az login
azd auth login
```

### Dependencies

- **Scripts** (Azure SDKs): managed by root `pyproject.toml`, installed automatically via `uv run`
- **API** (FastAPI): managed by `api/pyproject.toml`, installed via `cd api && uv sync`
- **Frontend** (React): managed by `frontend/package.json`, installed via `cd frontend && npm install`

---

## Project Structure

See [ARCHITECTURE.md](ARCHITECTURE.md) for full project structure, architectural
decisions, data flow diagrams, and the configuration signpost.

---

## Azure Services Used 

1. Microsoft Foundry 
2. AI Search 
3. Azure OpenAI (For embedding indices in AI search)
4. Microsoft Fabric

## Data used
1. Alerts and Link telemetry, stored in eventhouse in microsoft fabric workspace 
2. Runbooks in AI Search (hybrid, embeddings + words)
3. Historical Tickets in AI Search index (hybrid, embeddings + words)
4. Graph data in fabric lakehouse 


## Target Demo flow

1. **GraphExplorerAgent** queries the Fabric ontology graph via `OpenApiTool` → `fabric-query-api` `/query/graph` (GQL). Navigates network topology (routers, switches, links, base stations).
2. **RunbookKBAgent** searches historical runbooks for remediation guidance (`AzureAISearchTool` → `runbooks-index`).
3. **HistoricalTicketAgent** finds similar past incidents (`AzureAISearchTool` → `tickets-index`).
4. **TelemetryAgent** retrieves metrics and alert evidence via `OpenApiTool` → `fabric-query-api` `/query/telemetry` (KQL).
5. **Orchestrator** receives an alert storm, delegates to all four agents via `ConnectedAgentTool`, correlates findings, and produces a diagnosis with recommended actions.

## Current Implementation State

1. `azd up` deploys Azure infra (AI Foundry, AI Search, Storage, Fabric Capacity, Container Apps)
2. `azd deploy fabric-query-api` builds & deploys the Fabric query micro-service to Container Apps
3. Fabric provisioning scripts create workspace, lakehouse, eventhouse, and ontology
4. `assign_fabric_role.py` grants the Container App managed identity Fabric workspace access
5. `provision_agents.py` creates all 5 Foundry agents with OpenApiTool + AzureAISearchTool
6. Multi-agent orchestrator flow tested end-to-end

## Setup

All commands run from the **project root** unless noted otherwise.

### 0. Configure

```bash
cp azure_config.env.template azure_config.env
# Edit azure_config.env — fill in desired params, leave auto-marked params blank
```

### 1. Generate synthetic data

```bash
cd data/scripts
uv run python generate_alert_stream.py
uv run python generate_routing_data.py
uv run python generate_tickets.py
uv run python generate_topology_data.py
cd ../..
```

### 2. Deploy Azure infrastructure

```bash
azd up -e myenvname    # Names both the azd env and the resource group
```

This deploys:
- AI Foundry (account + project + GPT deployment)
- Azure AI Search
- Storage account + blob containers
- Fabric Capacity (F-SKU)
- Container Apps Environment (ACR + Log Analytics)
- fabric-query-api Container App (system-assigned managed identity)

`postprovision.sh` runs automatically — uploads runbook/ticket data to blob storage
and writes deployment outputs (including `FABRIC_QUERY_API_URI` and
`FABRIC_QUERY_API_PRINCIPAL_ID`) to `azure_config.env`.

### 3. Provision data stores

```bash
uv run python scripts/create_runbook_indexer.py
uv run python scripts/create_tickets_indexer.py
uv run python scripts/provision_lakehouse.py
uv run python scripts/provision_eventhouse.py
uv run python scripts/provision_ontology.py   # ~30 min for graph indexing
```

### 4. Grant Fabric access to the Container App

The `fabric-query-api` Container App must be a Fabric workspace member to execute
GQL/KQL queries using its managed identity:

```bash
uv run python scripts/assign_fabric_role.py
```

This reads `FABRIC_WORKSPACE_ID` and `FABRIC_QUERY_API_PRINCIPAL_ID` from
`azure_config.env` and assigns the Contributor role via the Fabric REST API.
Re-running is safe — it skips if the role already exists.

### 5. Verify the deployed API

```bash
uv run python scripts/test_fabric_query_api.py
```

This smoke-tests both `/query/graph` (GQL) and `/query/telemetry` (KQL) on the
deployed Container App.

### 6. Provision Foundry agents

```bash
uv run python scripts/provision_agents.py
```

Creates 5 agents: Orchestrator + GraphExplorer + Telemetry + RunbookKB +
HistoricalTicket. GraphExplorer and Telemetry use `OpenApiTool` pointing at
the deployed `fabric-query-api`.

### 7. Test the multi-agent flow (CLI)

```bash
uv run python scripts/test_orchestrator.py
```

### 8. Run the UI locally

```bash
# Terminal 1 — FastAPI backend
cd api && uv run uvicorn app.main:app --reload --port 8000

# Terminal 2 — React frontend
cd frontend && npm run dev
```

Open http://localhost:5173 — the Vite dev server proxies `/api/*` to the backend.

### Redeploying fabric-query-api

If you change `fabric-query-api/` code after initial `azd up`:

```bash
azd deploy fabric-query-api
```

This rebuilds the Docker image in ACR (`remoteBuild: true`) and updates the
Container App revision. No need to re-run `azd up` for code-only changes.

## TODO

### Automation
- [x] Bug fix provision_ontology.py
- [x] Auto fill eventhouse tables
- [x] Multi-agent workflow provisioning
- [x] Test multi-agent flow programmatically
- [x] Stream agent events with input/output metadata
- [x] Decouple from Fabric Data Agent → OpenApiTool + fabric-query-api
- [x] Automate Fabric role assignment (`assign_fabric_role.py`)
- [x] Deploy fabric-query-api to Container Apps (`azd deploy`)

### Frontend & API
- [x] FastAPI backend with SSE streaming
- [x] React/Vite dark theme UI scaffold
- [x] Wire real orchestrator into SSE endpoint
- [x] Deploy fabric-query-api to Azure Container Apps
- [x] Test independent graph querying
- [ ] Fix unreliable behavior
- [ ] Deploy main API to Azure Container Apps
- [ ] Deploy frontend to Azure Static Web Apps

### Future
- [x] Format query and response text with markdown
- [x] Query Fabric graph directly (GQL via REST API)
- [x] Create and test graph query tool — FunctionTool PoC → OpenApiTool production
- [ ] Cache common GQL queries (Redis / embedding cache)
- [ ] Link telemetry from all agents rather than just the orchestrator
- [ ] MCP server tools
- [ ] CosmosDB for tickets
- [ ] Corrective action API
- [ ] Live visualization of the graph directly in the UI
- [ ] Click on a node, select a particular type of error or scenario, trigger it!
- [ ] Expand data complexity and size to more closely model real world
- [ ] Play by play commentary on each step of the demo
- [ ] Better and more readable formatting of demo output
- [ ] Logs and Application Insights to trace server-side errors
- [ ] Display final response somewhere — wireframe needed
