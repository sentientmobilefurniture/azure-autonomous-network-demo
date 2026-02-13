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
                         ┌──────────────────────────────────────────┐
                         │       Unified Container App (:80)        │
                         │                                          │
Browser ──POST /api/──▶  │  nginx :80                               │
         ◀──SSE stream── │   ├─ /        → React SPA (static)      │
                         │   ├─ /api/*   → uvicorn :8000 (API)     │
                         │   ├─ /health  → uvicorn :8000            │
                         │   └─ /query/* → uvicorn :8100 (graph)   │
                         │                                          │
                         │  supervisord manages all 3 processes     │
                         └────────────────┬─────────────────────────┘
                                          │ azure-ai-agents SDK
                              ┌───────────┴──────────┐
                              ▼         ▼            ▼
                        GraphExplorer  Telemetry  RunbookKB ...
                              │         │
                              ▼         ▼
                        graph-query-api (same container)
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

Setup guide: **[Cosmos DB Setup](documentation/deprecated/SETUP_COSMOSDB.md)** (archived — `deploy.sh` now automates this)

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

### Option A: Automated (recommended)

```bash
chmod +x deploy_app.sh
./deploy_app.sh --env myenv --location eastus2
```

`deploy_app.sh` is the **environment-isolated** deployment script. Each azd
environment gets its own config file under `envs/{name}.env` — no risk of
cross-environment contamination when switching between deployments.

**How it works:**
1. Creates `envs/{name}.env` from `azure_config.env.template` (if new)
2. Symlinks `azure_config.env → envs/{name}.env` (hooks & scripts work unchanged)
3. Runs the full pipeline: infra → data → indexes → agents → local services
4. Switching environments just moves the symlink

```bash
# Fresh deployment
./deploy_app.sh --env cosmosprod5 --location eastus2

# Reuse existing infra, just re-index
./deploy_app.sh --env cosmosprod5 --skip-infra

# Use a specific env file
./deploy_app.sh --env-file envs/cosmosgraphstable3.env

# Interactive — lists existing environments and lets you choose
./deploy_app.sh
```

| Flag | Effect |
|------|--------|
| `--env NAME` | azd environment name (creates `envs/{NAME}.env` if needed) |
| `--env-file PATH` | Use an existing env file directly |
| `--location LOC` | Azure location (default: swedencentral) |
| `--skip-infra` | Skip `azd up` (reuse existing Azure resources) |
| `--skip-index` | Skip AI Search index creation (keeps existing indexes) |
| `--skip-data` | Skip Cosmos DB graph + telemetry loading |
| `--skip-agents` | Skip AI Foundry agent provisioning |
| `--skip-local` | Skip starting local API + frontend |
| `--yes` | Skip all confirmation prompts |

> **Note:** `deploy.sh` (legacy) still works but uses a single shared
> `azure_config.env` file, which can cause cross-environment contamination
> when switching between deployments. Prefer `deploy_app.sh`.

### Option B: Step-by-step

#### 1. Configure

```bash
cp azure_config.env.template azure_config.env
# Edit azure_config.env — set GRAPH_BACKEND, etc.
```

#### 2. Deploy infrastructure

```bash
azd up -e <env-name>
```

`azd up` provisions all Azure resources, builds and deploys the **unified
container** (nginx + API + graph-query-api), uploads data to blob storage,
and populates `azure_config.env` with deployment outputs.

Resources deployed:
- VNet (Container Apps + Private Endpoints subnets)
- AI Foundry (account + project + GPT-4.1 deployment)
- Azure AI Search
- Storage Account + blob containers (runbooks, tickets)
- Container Apps Environment (ACR + Log Analytics)
- **Unified Container App** (nginx + API + graph-query-api, system-assigned managed identity)
- Cosmos DB Gremlin account + database + graph
- Cosmos DB NoSQL account (telemetry)
- Cosmos DB Private Endpoints
- RBAC role assignments (5 roles for container app identity)

#### 3. Load Cosmos DB data

```bash
source azure_config.env
uv run python scripts/cosmos/provision_cosmos_gremlin.py
uv run python scripts/cosmos/provision_cosmos_telemetry.py
```

#### 4. Create search indices

```bash
uv run python scripts/create_runbook_indexer.py
uv run python scripts/create_tickets_indexer.py
```

#### 5. Provision AI agents

```bash
uv run python scripts/provision_agents.py
```

Creates 5 Foundry agents: Orchestrator + GraphExplorer + Telemetry + RunbookKB +
HistoricalTicket.

#### 6. Run the demo

**Production (Azure):** After `deploy.sh` or `azd up` completes, the app is live at
the Container App URL (printed as `APP_URI` in `azure_config.env`). No local
services needed.

**Local development:**

```bash
# Terminal 1 — Backend API
cd api && source ../azure_config.env && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2 — Frontend (dev server with HMR)
cd frontend && npm install && npm run dev
```

Open http://localhost:5173

---

## Project Structure

```
.
├── azure.yaml                  # azd service definitions & hooks (1 unified service)
├── azure_config.env            # Symlink → envs/{active-env}.env (gitignored)
├── azure_config.env.template   # Template for per-environment config files
├── deploy_app.sh               # Environment-isolated deployment script (recommended)
├── deploy.sh                   # Legacy deployment script (single shared config)
├── envs/                       # Per-environment config files (gitignored)
│   ├── cosmosprod5.env         #   Created by deploy_app.sh
│   └── cosmosgraphstable3.env  #   One file per azd environment
├── Dockerfile                  # Unified container: nginx + API + graph-query-api
├── nginx.conf                  # Reverse proxy config (hardcoded localhost)
├── supervisord.conf            # Process manager for unified container
├── .dockerignore               # Build context exclusions
├── pyproject.toml              # Python deps for scripts/ (uv-managed)
│
├── api/                        # FastAPI backend (port 8000)
│   └── app/
│       ├── main.py             # App factory, CORS, router mounting
│       ├── orchestrator.py     # Agent orchestrator bridge
│       └── routers/            # REST endpoints (alert, agents, logs)
│
├── graph-query-api/            # Graph & telemetry microservice (port 8100)
│   ├── main.py                 # FastAPI app with lifespan management
│   ├── config.py               # Env var loading, backend selector enum
│   ├── router_graph.py         # POST /query/graph
│   ├── router_telemetry.py     # POST /query/telemetry (SQL)
│   ├── backends/
│   │   ├── cosmosdb.py         # Cosmos DB Gremlin (gremlinpython)
│   │   └── mock.py             # Static JSON responses
│   └── openapi/                # Backend-specific OpenAPI specs
│
├── frontend/                   # React/Vite NOC dashboard
│   └── src/
│       ├── App.tsx             # Main app component
│       ├── components/         # AlertPanel, AgentTimeline, etc.
│       └── hooks/              # SSE streaming hook
│
├── infra/                      # Bicep IaC (azd up)
│   ├── main.bicep              # Orchestrator (subscription-scoped, 1 Container App)
│   ├── main.bicepparam         # Parameter file (reads env vars)
│   └── modules/                # AI Foundry, Search, Storage, Cosmos, VNet, Roles
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
│   │   ├── provision_cosmos_gremlin.py   # YAML-manifest-driven graph loader
│   │   └── provision_cosmos_telemetry.py # CSV telemetry data → Cosmos NoSQL
│   └── testing_scripts/        # Smoke tests & CLI orchestrator
│
├── hooks/
│   ├── preprovision.sh         # Resolves principal ID, syncs env → Bicep
│   └── postprovision.sh        # Uploads blobs, writes azure_config.env, fetches Cosmos key
│
└── documentation/
    ├── ARCHITECTURE.md         # Full architecture reference
    ├── SCENARIO.md             # Demo scenario narrative
    └── ...
```

---

## Operations

### Running locally (development)

```bash
# Terminal 1 — Backend API
cd api && source ../azure_config.env && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2 — Frontend (HMR enabled)
cd frontend && npm run dev

# Terminal 3 (optional) — graph-query-api locally
cd graph-query-api && source ../azure_config.env && uv run uvicorn main:app --host 0.0.0.0 --port 8100 --reload
```

> **Note:** When running locally, the API talks to **remote** Azure resources
> (Foundry agents, Cosmos DB). The agents' `OpenApiTool` calls go to the
> **deployed** Container App URL (set in `GRAPH_QUERY_API_URI`).
> Running graph-query-api locally is for direct endpoint testing only.

### Redeploying the app

```bash
azd deploy app    # Rebuilds unified container in ACR, creates new Container App revision
```

### Reprovisioning agents

```bash
uv run python scripts/provision_agents.py    # Deletes old agents, creates fresh ones
azd deploy app                                # Rebake container with new agent_ids.json
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
# Container App name format: ca-app-<resourceToken>
CA_NAME=$(az containerapp list --resource-group $AZURE_RESOURCE_GROUP --query "[?contains(name,'ca-app')].name" -o tsv)

# View logs
az containerapp logs show --name $CA_NAME --resource-group $AZURE_RESOURCE_GROUP --type console --tail 50

# Stream logs
az containerapp logs show --name $CA_NAME --resource-group $AZURE_RESOURCE_GROUP --type console --follow

# Check status
az containerapp show --name $CA_NAME --resource-group $AZURE_RESOURCE_GROUP \
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

Configuration is managed per-environment in `envs/{name}.env` files, created by
`deploy_app.sh`. A symlink at `azure_config.env` points to the active environment's
file so that hooks, scripts, and local dev commands all read the correct config.

Key sections:

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
