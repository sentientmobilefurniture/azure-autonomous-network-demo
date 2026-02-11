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

---

## Operations

### Starting the UI locally

```bash
# Terminal 1 — Backend API
cd api && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2 — Frontend
cd frontend && npm run dev
```

Open http://localhost:5173. The Vite dev server proxies `/api/*` and `/health` to the backend.

### Restarting the frontend

The frontend picks up `.tsx` changes via HMR automatically. For config changes
(`vite.config.ts`, `package.json`, `tailwind.config.js`), you must restart:

```bash
# Kill and restart
lsof -ti:5173 | xargs -r kill -9
cd frontend && npm run dev
```

### Restarting the backend

The backend runs with `--reload`, so Python file changes are picked up
automatically. To fully restart:

```bash
lsof -ti:8000 | xargs -r kill -9
cd api && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Killing everything

```bash
# Kill frontend + backend + fabric-query-api (local)
lsof -ti:8000,5173,5174,8100 | xargs -r kill -9
```

### Container App management

The `fabric-query-api` runs as an Azure Container App. Common operations:

```bash
# Set these or source azure_config.env
CA_NAME=ca-fabricquery-<suffix>
RG=rg-<your-resource-group>

# View recent logs (last 50 lines)
az containerapp logs show --name $CA_NAME --resource-group $RG --type console --tail 50

# Stream logs in real-time
az containerapp logs show --name $CA_NAME --resource-group $RG --type console --follow

# Check current revision & status
az containerapp show --name $CA_NAME --resource-group $RG --query "{fqdn:properties.configuration.ingress.fqdn, replicas:properties.template.scale.minReplicas, revision:properties.latestRevisionName}" -o table

# View env vars on the container
az containerapp show --name $CA_NAME --resource-group $RG --query "properties.template.containers[0].env" -o table

# Restart (creates new revision with same config)
az containerapp revision restart --name $CA_NAME --resource-group $RG --revision <REVISION_NAME>

# Redeploy after code changes
azd deploy fabric-query-api
```

### Reprovisioning agents

After changing prompts, OpenAPI specs, or agent configuration:

```bash
uv run python scripts/provision_agents.py
```

This deletes old agents and creates fresh ones. The backend reads `agent_ids.json`
at request time, so no backend restart is needed.

### Checking agent health

```bash
# List agents and their IDs
curl -s http://localhost:8000/api/agents | python3 -m json.tool

# Quick health check
curl -s http://localhost:8000/health
```

### Running the orchestrator from CLI

For debugging without the UI:

```bash
# Default alert
uv run python scripts/test_orchestrator.py

# Custom alert
uv run python scripts/test_orchestrator.py "08:15:00 MAJOR ROUTER-SYD-01 BGP_FLAP BGP session down"

# Quiet mode (final response only)
uv run python scripts/test_orchestrator.py --quiet
```

---

## Troubleshooting

### Viewing Container App logs

When agents return `HTTP 400` or other errors, check the `fabric-query-api`
container logs for the raw request body and Fabric error:

```bash
# Recent logs (last 50 lines)
az containerapp logs show \
  --name <CONTAINER_APP_NAME> \
  --resource-group <RESOURCE_GROUP> \
  --type console \
  --tail 50

# Follow logs in real-time
az containerapp logs show \
  --name <CONTAINER_APP_NAME> \
  --resource-group <RESOURCE_GROUP> \
  --type console \
  --follow
```

The logging middleware logs every incoming POST body and flags 4xx+ responses.
Look for lines like:

```
INFO  Incoming POST /query/graph — body=b'{"query": "MATCH ..."}'
WARNING  Response 400 for POST /query/graph
```

Common GQL 400 causes:
- **Property not found** — the GQL property name doesn't match the ontology
  property name (see "Ontology naming rules" below).
- **Relationship direction wrong** — GQL edge traversal `->` vs `<-` doesn't
  match the ontology relationship source/target definition.
- **Entity type not found** — typing mistake in the node label (e.g., `SlaPolicy`
  instead of `SLAPolicy`).

### Ontology property naming rules

**GQL queries must use ontology property names, NOT Lakehouse column names.**

The Fabric graph model exposes properties by the names defined in
`provision_ontology.py` via `prop(id, "PropertyName")`. These names may differ
from the underlying Lakehouse CSV column names. The binding maps CSV columns to
property IDs (integers), and the property ID maps to a property name.

Example:

```
# Lakehouse CSV column     →  Ontology property name  →  GQL usage
# "ServiceId"              →  "ServiceId"              →  sla.ServiceId
# "Tier"                   →  "Tier"                   →  sla.Tier
```

When adding new entity types or properties:
1. **Match property names to CSV column names** wherever possible to avoid
   confusion. Only rename when there's a genuine ambiguity (e.g., both
   `Service.ServiceId` and `SLAPolicy.ServiceId` — but in GQL, properties are
   entity-scoped so this isn't actually ambiguous).
2. **Update the agent prompt** in `data/prompts/foundry_graph_explorer_agent_v2.md`
   with the exact property names from the ontology definition.
3. **Test the GQL query** directly against `/query/graph` before provisioning
   agents — a 400 from Fabric will include the available property names in the
   error message.

### Debug endpoint

Set `DEBUG_ENDPOINTS=1` as an env var on the Container App to enable `/debug/raw-gql`,
which returns the raw Fabric API response without normalization. Useful for
diagnosing GQL issues. Disabled by default in production.

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
- [x] Fix unreliable behavior - Ontology/Data file mismatch + confusing prompt spec - Fixed
- [x] Verify that v2 architecture works with current UI
- [x] Fix event streaming not working
- [ ] Final test before merging v2architecture
- [ ] Deploy main API to Azure Container Apps
- [ ] Deploy frontend to Azure Static Web Apps

### Future
- [x] Format query and response text with markdown
- [x] Query Fabric graph directly (GQL via REST API)
- [x] Create and test graph query tool — FunctionTool PoC → OpenApiTool production
- [ ] **Neo4j graph backend** — Replace Fabric GraphModel with Neo4j for demo. Enables real-time graph mutations from the UI (add/remove nodes, trigger faults, visualize topology live). Cypher ≈ GQL. Fabric remains the production-scale story; Neo4j is the interactive demo story.
- [ ] Real-time graph visualization in UI (D3-force / Neovis.js over Bolt websockets)
- [ ] Click on a node, select a particular type of error or scenario, trigger it!
- [ ] Cache common GQL queries (Redis / embedding cache)
- [ ] Link telemetry from all agents rather than just the orchestrator
- [ ] MCP server tools
- [ ] CosmosDB for tickets
- [ ] Corrective action API
- [ ] Expand data complexity and size to more closely model real world
- [ ] Play by play commentary on each step of the demo
- [ ] Better and more readable formatting of demo output
- [ ] Logs and Application Insights to trace server-side errors
- [ ] Display final response somewhere — wireframe needed
