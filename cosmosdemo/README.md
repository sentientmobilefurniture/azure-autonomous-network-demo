# AI Incident Investigator — Multi-Scenario Demo

An AI-powered incident investigation platform that diagnoses operational issues
using multi-agent orchestration on Azure. Five specialist agents collaborate to
perform root-cause analysis, assess blast radius, retrieve operating procedures,
and produce actionable situation reports — without human intervention.

The platform is **scenario-agnostic** — it supports multiple investigation domains.
New scenarios are added as self-contained data packs; no code changes required.

### Available Scenarios

| Scenario | Domain | Incident |
|----------|--------|----------|
| **telco-noc** | Telecommunications | Fibre cut triggers cascading alert storm across routers, switches, and services |
| **cloud-outage** | Cloud Infrastructure | Cooling failure causes thermal shutdown cascade across hosts, VMs, and services |
| **customer-recommendation** | E-Commerce | Recommendation model bias spikes return rates across customer segments |

> **See also:** [ARCHITECTURE.md](documentation/ARCHITECTURE.md) for detailed
> architecture, data flow diagrams, and design decisions.

---

## How It Works

An alert storm enters the system (simulated or real). An **Orchestrator** agent in
Azure AI Foundry delegates to four specialists:

| Agent | Data Source | Tool |
|-------|-----------|------|
| **GraphExplorer** | Topology/dependency graph | `OpenApiTool` → `graph-query-api /query/graph` |
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
chmod +x deploy.sh
./deploy.sh
```

`deploy.sh` provisions Azure infrastructure and deploys the container. Data loading
and agent configuration happen via the UI after deployment.

```bash
# Skip infrastructure (reuse existing Azure resources)
./deploy.sh --skip-infra

# Target a specific azd environment and location
./deploy.sh --env myenv --location eastus2

# Non-interactive (skip all prompts)
./deploy.sh --yes

# Skip starting local dev servers
./deploy.sh --skip-local
```

| Flag | Effect |
|------|--------|
| `--skip-infra` | Skip `azd up` (reuse existing Azure resources) |
| `--skip-local` | Skip starting local API + frontend |
| `--env NAME` | azd environment name |
| `--location LOC` | Azure location (default: swedencentral) |
| `--yes` | Skip all confirmation prompts |

### Option B: Step-by-step

#### 1. Configure

```bash
cp azure_config.env.template azure_config.env
```

#### 2. Deploy infrastructure

```bash
./deploy.sh
# or: azd up -e <env-name>
```

This provisions all Azure resources and deploys the unified container.

#### 3. Upload scenario data

Generate tarballs from the included scenarios:

```bash
./data/generate_all.sh
```

This creates:
- `data/scenarios/telco-noc.tar.gz`
- `data/scenarios/cloud-outage.tar.gz`
- `data/scenarios/customer-recommendation.tar.gz`

Open the app, click ⚙ Settings → Upload tab, and upload a `.tar.gz` file.
The Container App loads graph data into Cosmos DB, telemetry into NoSQL,
runbooks/tickets into AI Search — all inside the VNet, no firewall issues.

#### 4. Configure agents

In Settings → Data Sources tab, select which graph and search indexes
each agent should use, then click Apply Changes. This provisions 5 AI
Foundry agents with the correct data bindings.

#### 5. Run an investigation

Paste an alert into the input panel and watch the agents investigate.

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
├── azure.yaml                  # azd service definitions & hooks
├── azure_config.env            # Runtime config (gitignored, auto-populated)
├── azure_config.env.template   # Config template
├── deploy.sh                   # Automated deployment (infra + container)
├── Dockerfile                  # Unified container: nginx + API + graph-query-api
├── nginx.conf                  # Reverse proxy (localhost routing)
├── supervisord.conf            # Process manager for unified container
│
├── api/                        # FastAPI backend (port 8000)
│   └── app/
│       ├── main.py             # App factory, CORS, router mounting
│       ├── orchestrator.py     # Foundry agent bridge (sync SDK → async SSE)
│       └── routers/
│           ├── alert.py        # POST /api/alert → SSE investigation stream
│           ├── agents.py       # GET /api/agents
│           ├── config.py       # POST /api/config/apply → re-provision agents
│           └── logs.py         # GET /api/logs → SSE log stream
│
├── graph-query-api/            # Graph, telemetry & data management (port 8100)
│   ├── config.py               # ScenarioContext, env vars, X-Graph header routing
│   ├── router_graph.py         # POST /query/graph (per-scenario Gremlin dispatch)
│   ├── router_telemetry.py     # POST /query/telemetry (scenario-aware SQL)
│   ├── router_topology.py      # POST /query/topology (graph visualization)
│   ├── router_ingest.py        # POST /query/scenario/upload (data ingestion)
│   ├── router_prompts.py       # CRUD /query/prompts (Cosmos-backed prompts)
│   ├── search_indexer.py       # AI Search indexer pipeline (blob → vectorize)
│   └── backends/               # Per-graph client cache
│       ├── cosmosdb.py         # Cosmos DB Gremlin (parameterised)
│       └── mock.py             # Static responses (offline demos)
│
├── frontend/                   # React/Vite dashboard
│   └── src/
│       ├── context/ScenarioContext.tsx  # Active graph/index state
│       ├── hooks/
│       │   ├── useInvestigation.ts     # SSE alert investigation
│       │   ├── useTopology.ts          # Graph topology data
│       │   └── useScenarios.ts         # Scenario upload + listing
│       └── components/
│           ├── Header.tsx              # Branding + ⚙ Settings button
│           ├── SettingsModal.tsx        # Data Sources + Upload tabs
│           └── graph/                  # Force-directed graph viewer
│
├── data/
│   ├── generate_all.sh         # Generate + tarball all scenarios
│   └── scenarios/
│       ├── telco-noc/          # Telco — fibre cut
│       ├── cloud-outage/       # Cloud DC — cooling cascade
│       └── customer-recommendation/  # E-commerce — model bias
│
├── scripts/
│   ├── scenario_loader.py      # ScenarioLoader — resolves paths/config
│   ├── agent_provisioner.py    # AgentProvisioner class (importable)
│   ├── provision_agents.py     # CLI agent provisioning (fallback)
│   └── testing_scripts/        # Smoke tests & CLI tools
│
├── infra/                      # Bicep IaC (azd up)
│   ├── main.bicep              # Subscription-scoped orchestrator
│   └── modules/                # AI Foundry, Search, Storage, Cosmos, VNet, Roles
│
├── deprecated/                 # Superseded scripts (kept for reference)
│
└── documentation/
    ├── ARCHITECTURE.md         # Full architecture reference
    └── v8datamanagementplane.md # V8 data management design
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

### Generating scenario data

```bash
./data/generate_all.sh                    # All scenarios
./data/generate_all.sh cloud-outage       # Single scenario
```

Tarballs are created at `data/scenarios/<name>.tar.gz` ready for upload.

### Redeploying the app

```bash
azd deploy app    # Rebuilds container, creates new revision (~60s)
```

### CLI agent provisioning (fallback)

```bash
source azure_config.env && uv run python scripts/provision_agents.py --force
```

### CLI testing (no UI)

```bash
uv run python scripts/testing_scripts/test_orchestrator.py
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

Configuration is managed in `azure_config.env`, populated by `deploy.sh` and
`postprovision.sh`. Hooks, scripts, and local dev commands all read this file.

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
