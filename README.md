# Autonomous Network NOC Demo

An AI-powered autonomous Network Operations Centre that diagnoses fibre cuts and
network incidents using multi-agent orchestration on Azure. Five specialist agents
collaborate to perform root-cause analysis, assess blast radius, retrieve operating
procedures, and produce actionable situation reports — without human intervention.

> **See also:** [ARCHITECTURE.md](documentation/ARCHITECTURE.md) for detailed
> architecture, data flow diagrams, and design decisions.

---

## How It Works

A simulated alert storm enters the system. An **Orchestrator** agent in Azure AI
Foundry delegates to four specialists:

| Agent | Data Source | Tool |
|-------|-----------|------|
| **GraphExplorer** | Network topology graph | `OpenApiTool` → `graph-query-api /query/graph` |
| **Telemetry** | Metrics & alerts in Cosmos DB NoSQL | `OpenApiTool` → `graph-query-api /query/telemetry` |
| **RunbookKB** | Operational procedures | `AzureAISearchTool` → `runbooks-index` |
| **HistoricalTicket** | Past incident records | `AzureAISearchTool` → `tickets-index` |

The orchestrator correlates all findings into a structured diagnosis with
recommended remediation actions.

```
Frontend :5173  ──POST /api/alert──▶  API :8000  ──SDK──▶  Orchestrator (Foundry)
                ◀──── SSE stream ────                        │
                                                  ┌──────────┴──────────┐
                                                  ▼         ▼          ▼
                                            GraphExplorer  Telemetry  RunbookKB ...
                                                  │         │
                                                  ▼         ▼
                                            graph-query-api :8100
                                            (Cosmos Gremlin / Mock)
```

---

## Graph Backend Modes

The `graph-query-api` microservice supports two backends, controlled by the
`GRAPH_BACKEND` environment variable:

| Value | Graph Engine | Deployment | Use Case |
|-------|-------------|-----------|----------|
| `cosmosdb` | Azure Cosmos DB (Gremlin API) | `azd up` provisions automatically | **Default.** Fully automated setup. |
| `mock` | Static JSON responses | No external dependencies | Local development & testing. |

Setup guide: **[Cosmos DB Setup](documentation/SETUP_COSMOSDB.md)**

---

## Prerequisites

| Tool | Install | Verify |
|------|---------|--------|
| **Python 3.11+** | [python.org](https://www.python.org/downloads/) | `python3 --version` |
| **uv** | `curl -LsSf https://astral.sh/uv/install.sh \| sh` | `uv --version` |
| **Node.js 20+** | [nodesource](https://deb.nodesource.com/setup_20.x) or `nvm install 20` | `node --version` |
| **Azure CLI** | [Install guide](https://learn.microsoft.com/cli/azure/install-azure-cli-linux) | `az --version` |
| **Azure Developer CLI** | `curl -fsSL https://aka.ms/install-azd.sh \| bash` | `azd version` |

```bash
az login
azd auth login
```

---

## Quick Start

### 1. Configure

```bash
cp azure_config.env.template azure_config.env
# Edit azure_config.env — set GRAPH_BACKEND, etc.
```

### 2. Deploy infrastructure

```bash
azd up -e <env-name>
```

`azd up` provisions all Azure resources, builds and deploys the `graph-query-api`
container, uploads data to blob storage, and populates `azure_config.env` with
deployment outputs.

Resources deployed:
- AI Foundry (account + project + GPT-4.1 deployment)
- Azure AI Search
- Storage Account + blob containers (runbooks, tickets)
- Container Apps Environment (ACR + Log Analytics)
- `graph-query-api` Container App (system-assigned managed identity)
- Cosmos DB Gremlin account + database + graph

### 3. Set up your graph backend

Follow the backend-specific guide:

- **Cosmos DB** → [documentation/SETUP_COSMOSDB.md](documentation/SETUP_COSMOSDB.md)

### 4. Create search indices

```bash
uv run python scripts/create_runbook_indexer.py
uv run python scripts/create_tickets_indexer.py
```

### 5. Provision AI agents

```bash
uv run python scripts/provision_agents.py
```

Creates 5 Foundry agents: Orchestrator + GraphExplorer + Telemetry + RunbookKB +
HistoricalTicket.

### 6. Run the demo

```bash
# Terminal 1 — Backend API
cd api && source ../azure_config.env && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2 — Frontend
cd frontend && npm install && npm run dev
```

Open http://localhost:5173

---

## Project Structure

```
.
├── azure.yaml                  # azd service definitions & hooks
├── azure_config.env            # Runtime config (single source of truth, gitignored)
├── azure_config.env.template   # Template for azure_config.env
├── pyproject.toml              # Python deps for scripts/ (uv-managed)
│
├── api/                        # FastAPI backend (port 8000)
│   └── app/
│       ├── main.py             # App factory, CORS, router mounting
│       ├── orchestrator.py     # Agent orchestrator bridge
│       ├── routers/            # REST endpoints (alert, agents, logs)
│       └── mcp/                # MCP server (stub)
│
├── graph-query-api/            # Graph & telemetry microservice (port 8100)
│   ├── main.py                 # FastAPI app with lifespan management
│   ├── config.py               # Env var loading, backend selector enum
│   ├── router_graph.py         # POST /query/graph
│   ├── router_telemetry.py     # POST /query/telemetry (SQL)
│   ├── backends/
│   │   ├── cosmosdb.py         # Cosmos DB Gremlin (gremlinpython)
│   │   └── mock.py             # Static JSON responses
│   ├── openapi/                # Backend-specific OpenAPI specs
│   └── Dockerfile
│
├── frontend/                   # React/Vite NOC dashboard (port 5173)
│   └── src/
│       ├── App.tsx             # Main app component
│       ├── components/         # AlertPanel, AgentTimeline, etc.
│       └── hooks/              # SSE streaming hook
│
├── infra/                      # Bicep IaC (azd up)
│   ├── main.bicep              # Orchestrator (subscription-scoped)
│   ├── main.bicepparam         # Parameter file (reads env vars)
│   └── modules/                # AI Foundry, Search, Storage, Cosmos, Container Apps
│
├── data/
│   ├── graph_schema.yaml       # Declarative graph schema manifest
│   ├── network/                # CSV topology data (vertices & edges)
│   ├── runbooks/               # Markdown operating procedures
│   ├── tickets/                # Historical incident tickets
│   ├── prompts/                # Agent system prompts
│   └── scripts/                # Data generation scripts
│
├── scripts/
│   ├── provision_agents.py     # Create/update Foundry agents
│   ├── create_runbook_indexer.py
│   ├── create_tickets_indexer.py
│   ├── cosmos/                 # Cosmos DB-specific scripts
│   │   └── provision_cosmos_gremlin.py   # YAML-manifest-driven graph loader
│   └── testing_scripts/        # Smoke tests & CLI orchestrator
│
├── hooks/
│   ├── preprovision.sh         # Resolves principal ID, syncs env → Bicep
│   └── postprovision.sh        # Uploads blobs, writes azure_config.env, fetches Cosmos key
│
└── documentation/
    ├── ARCHITECTURE.md         # Full architecture reference
    ├── SCENARIO.md             # Demo scenario narrative
    ├── SETUP_COSMOSDB.md       # Cosmos DB backend setup guide
    ├── V5MULTISCENARIODEMO.md  # V5 multi-scenario demo spec
    ├── VUNKAGENTRETHINK.md     # Agent architecture rethink notes
    ├── assets/                 # Screenshots & diagrams
    ├── ui_states/              # UI state screenshots
    └── previous_dev_phases/    # Archived design docs
```

---

## Operations

### Running locally

```bash
# Terminal 1 — Backend API
cd api && source ../azure_config.env && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2 — Frontend (HMR enabled)
cd frontend && npm run dev

# Terminal 3 (optional) — graph-query-api locally
cd graph-query-api && source ../azure_config.env && uv run uvicorn main:app --host 0.0.0.0 --port 8100 --reload
```

> **Note:** The backend API talks to the **deployed** `graph-query-api` in Azure
> (via agents' `OpenApiTool`). Running it locally is for direct testing only.

### Redeploying graph-query-api

```bash
azd deploy graph-query-api    # Rebuilds Docker image in ACR, updates Container App
```

### Reprovisioning agents

```bash
uv run python scripts/provision_agents.py    # Deletes old agents, creates fresh ones
```

### CLI testing (no UI)

```bash
# Default alert scenario
uv run python scripts/testing_scripts/test_orchestrator.py

# Custom alert
uv run python scripts/testing_scripts/test_orchestrator.py "08:15:00 MAJOR ROUTER-SYD-01 BGP_FLAP BGP session down"
```

### Container App management

```bash
source azure_config.env
CA_NAME=ca-graphquery-<suffix>    # Check Azure portal for exact name
RG=$AZURE_RESOURCE_GROUP

# View logs
az containerapp logs show --name $CA_NAME --resource-group $RG --type console --tail 50

# Stream logs
az containerapp logs show --name $CA_NAME --resource-group $RG --type console --follow

# Check status
az containerapp show --name $CA_NAME --resource-group $RG \
  --query "{fqdn:properties.configuration.ingress.fqdn, revision:properties.latestRevisionName}" -o table
```

---

## Teardown

### Full teardown

```bash
bash infra/nuclear_teardown.sh
```

Deletes all Azure resources + purges soft-deleted accounts.

### Azure resources only

```bash
azd down --force --purge
```

---

## Troubleshooting

### Container App logs

```bash
az containerapp logs show --name $CA_NAME --resource-group $RG --type console --tail 50
```

### Agent health

```bash
curl -s http://localhost:8000/api/agents | python3 -m json.tool
curl -s http://localhost:8000/health
```

---

## Configuration Reference

All configuration lives in `azure_config.env` (single source of truth). Key sections:

| Section | Examples | Set by |
|---------|----------|--------|
| Core Azure | `AZURE_SUBSCRIPTION_ID`, `AZURE_RESOURCE_GROUP` | `postprovision.sh` |
| AI Foundry | `AI_FOUNDRY_ENDPOINT`, `PROJECT_ENDPOINT` | `postprovision.sh` |
| Model | `MODEL_DEPLOYMENT_NAME`, `EMBEDDING_MODEL` | User |
| AI Search | `AI_SEARCH_NAME`, `RUNBOOKS_INDEX_NAME` | Mixed |
| Graph Backend | `GRAPH_BACKEND` (`cosmosdb`/`mock`) | User (before `azd up`) |
| Cosmos DB | `COSMOS_GREMLIN_ENDPOINT`, `COSMOS_GREMLIN_PRIMARY_KEY` | `postprovision.sh` |
| Telemetry | `COSMOS_NOSQL_ENDPOINT`, `COSMOS_NOSQL_DATABASE` | `postprovision.sh` |

See `azure_config.env.template` for the complete list with inline documentation.
