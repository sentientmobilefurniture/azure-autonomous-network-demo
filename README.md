# AI Incident Investigator — Autonomous Network NOC

### Wear and tear alert scenario!

An AI-powered incident investigation platform that diagnoses operational issues
using a declarative agent on Azure AI Foundry. A single YAML-defined agent with
multiple typed tools performs root-cause analysis, assesses blast radius, retrieves
operating procedures, and produces actionable situation reports — without human
intervention.

The platform is **scenario-agnostic** — new investigation domains are added as
self-contained data packs under `data/scenarios/`; no code changes required.

---

## Architecture

```
                         ┌─────────────────────────────────────────────┐
                         │      Azure Web App (single process)          │
                         │      gunicorn + uvicorn (FastAPI)             │
                         │                                              │
Browser ──POST /api/──▶  │  FastAPI :8000                                │
         ◀──SSE stream── │   ├─ /         → React SPA (static)          │
                         │   ├─ /api/*    → Session + Agent endpoints    │
                         │   ├─ /query/*  → Topology, Search, Health     │
                         │   └─ /health   → Health check                │
                         └─────────────────┬───────────────────────────┘
                                          │ agent-framework (declarative YAML)
                              ┌───────────┴──────────┐
                              │  NetworkInvestigator   │
                              │  (orchestrator.yaml)   │
                              └──┬───┬───┬───┬───┬──┘
                                │   │   │   │   │
                           graph kql search search dispatch
                                │   │   │   │
                                ▼   ▼   ▼   ▼
                         Fabric Fabric AI Search AI Search
                          GQL    KQL   (runbooks) (tickets)
```

### Agent Tools

| Tool | Data Source | Function |
|------|-----------|----------|
| `graph_topology_query` | Topology graph (Fabric GQL) | Typed async Python function |
| `telemetry_kql_query` | Metrics & alerts (Fabric KQL) | Typed async Python function |
| `search_runbooks` | Operational procedures | Typed async Python function |
| `search_tickets` | Past incident records | Typed async Python function |
| `dispatch_field_engineer` | Action tool | Typed async Python function |

### Azure Resources (provisioned by `azd up`)

| Resource | Purpose |
|----------|---------|
| AI Foundry (account + project) | Hosts GPT-4.1 deployment + agent runtime |
| Azure AI Search | Vector search indexes (runbooks, tickets) |
| Storage Account | Blob storage for search indexer data source |
| Cosmos DB NoSQL | Interaction/session store |
| App Service Plan + Web App | Single-process Python app (gunicorn + FastAPI) |
| VNet + Private Endpoints | Network isolation for Cosmos DB |
| Microsoft Fabric Capacity | F8 capacity for graph + telemetry (conditional) |
| RBAC Role Assignments | Managed identity access across all services |

### Microsoft Fabric Resources (provisioned by `--provision-fabric`)

| Resource | Purpose |
|----------|---------|
| Workspace | Container for all Fabric items |
| Lakehouse | Delta tables for graph entity data (nodes + edges) |
| Eventhouse + KQL Database | Time-series telemetry (alerts, link metrics) |
| IQ Ontology + Graph Model | GQL-queryable graph over lakehouse tables |

---

## Prerequisites

| Tool | Install | Verify |
|------|---------|--------|
| **Python 3.11+** | [python.org](https://www.python.org/downloads/) | `python3 --version` |
| **uv** | `curl -LsSf https://astral.sh/uv/install.sh \| sh` | `uv --version` |
| **Node.js 20+** | `nvm install 20` or [nodesource](https://deb.nodesource.com/setup_20.x) | `node --version` |
| **Azure CLI** | [Install guide](https://learn.microsoft.com/cli/azure/install-azure-cli-linux) | `az --version` |
| **Azure Developer CLI** | `curl -fsSL https://aka.ms/install-azd.sh \| bash` | `azd version` |

> **Note:** `deploy.sh` auto-detects missing tools and offers to install them.

### Azure Accounts Required

1. **Azure subscription** with permission to create resources
2. **Microsoft 365 tenant** with Fabric capacity (F8 or higher) — or set `AZURE_FABRIC_ADMIN` to provision one via Bicep
3. **Fabric admin email** — the user who owns/administers the Fabric workspace

```bash
az login
azd auth login
```

---

## Quick Start (Full Deployment)

```bash
chmod +x deploy.sh

# Full end-to-end: infrastructure + Fabric + data
./deploy.sh --provision-all --yes

# Or step-by-step with prompts:
./deploy.sh                         # Step 1: Infrastructure only
./deploy.sh --skip-infra --provision-fabric   # Step 2: Fabric resources
./deploy.sh --skip-infra --provision-data     # Step 3: AI Search indexes
```

### What happens during `./deploy.sh --provision-all`:

| Step | What it does | Duration |
|------|-------------|----------|
| **0** | Check/install prerequisites (Python, uv, Node, az, azd) | ~10s |
| **1** | Select or create azd environment | interactive |
| **2** | Configure graph backend (Fabric GQL) | ~5s |
| **2b** | Generate static `topology.json` from scenario CSVs | ~5s |
| **3** | `azd up` — provision all Azure resources | **10–15 min** |
| **3b** | Auto-discover resources, write `azure_config.env` | ~30s |
| **4a** | Find-or-create Fabric workspace (hard gate — exits on failure) | ~30s |
| **4b** | Grant Container App managed identity Contributor on workspace | ~5s |
| **4c** | Provision Lakehouse + upload entity CSVs + load delta tables | ~3 min |
| **4d** | Provision Eventhouse + create KQL tables + ingest telemetry CSVs | ~3 min |
| **4e** | Provision IQ Ontology + Graph Model from `graph_schema.yaml` | ~2 min |
| **4f** | Re-populate `azure_config.env` with discovered Fabric IDs | ~10s |
| **5** | Create AI Search indexes (runbooks + tickets) from blob storage | ~2 min |
| **6** | *(Removed — agents load from YAML at startup)* | — |
| **7** | Build frontend + deploy Web App via `azd deploy api` | ~2 min |
| **8** | Health check (poll `/health` up to 5× with 15s intervals) | ~15s |

---

## deploy.sh Reference

### Flags

| Flag | Effect |
|------|--------|
| `--provision-fabric` | Run Fabric provisioning (Steps 4a–4f) |
| `--provision-data` | Run data provisioning (Step 5 — AI Search indexes) |
| `--provision-all` | All of the above |
| `--skip-infra` | Skip `azd up` (reuse existing Azure resources) |
| `--skip-local` | Skip starting local dev servers |
| `--env NAME` | Use a specific azd environment name |
| `--location LOC` | Azure location (default: `swedencentral`) |
| `--scenario NAME` | Scenario to deploy (auto-detected if only one exists) |
| `--yes` / `-y` | Skip all confirmation prompts |

### Common Workflows

```bash
# First-time full deploy
./deploy.sh --provision-all --yes

# Redeploy app after code changes
azd deploy api

# Re-provision Fabric resources only
./deploy.sh --skip-infra --provision-fabric --yes

# Re-provision everything except Azure infra
./deploy.sh --skip-infra --provision-all --yes

# Deploy to a specific environment and location
./deploy.sh --env myenv --location eastus2
```

---

## Configuration

### `azure_config.env`

Single source of truth for all runtime configuration. Generated automatically by
`deploy.sh` (Step 3b) and enriched by Fabric provisioning (Step 4f). Both the API
and graph-query-api load this file at startup via `python-dotenv`.

**You should never need to edit this file manually** — `deploy.sh` handles everything.

| Section | Key Variables | Populated By |
|---------|---------------|-------------|
| **Core Azure** | `AZURE_SUBSCRIPTION_ID`, `AZURE_RESOURCE_GROUP`, `AZURE_LOCATION` | Step 3b auto-discovery |
| **AI Foundry** | `AI_FOUNDRY_NAME`, `PROJECT_ENDPOINT` | Step 3b auto-discovery |
| **Model** | `MODEL_DEPLOYMENT_NAME` (default: `gpt-4.1`) | User (template default) |
| **AI Search** | `AI_SEARCH_NAME`, `RUNBOOKS_INDEX_NAME`, `TICKETS_INDEX_NAME` | Step 3b + scenario.yaml |
| **Storage** | `STORAGE_ACCOUNT_NAME` | Step 3b auto-discovery |
| **App** | `APP_URI`, `APP_PRINCIPAL_ID`, `GRAPH_QUERY_API_URI` | Step 3b auto-discovery |
| **Cosmos DB** | `COSMOS_NOSQL_ENDPOINT` | Step 3b auto-discovery |
| **Fabric Admin** | `AZURE_FABRIC_ADMIN`, `FABRIC_CAPACITY_SKU` | User / preprovision hook |
| **Fabric Resources** | `FABRIC_WORKSPACE_ID`, `FABRIC_LAKEHOUSE_ID`, `FABRIC_EVENTHOUSE_ID`, `FABRIC_KQL_DB_ID`, `FABRIC_KQL_DB_NAME`, `EVENTHOUSE_QUERY_URI` | Step 4f populate script |

### How config reaches the Web App

`azure_config.env` values are injected as **App Settings** via Bicep. The Web App
reads them as environment variables at startup — no baked config file.

- **API** (`api/app/paths.py`): `load_dotenv(PROJECT_ROOT / "azure_config.env")` for local dev
- **Web App**: reads env vars directly from App Service configuration

**To update config in production:** update App Settings in Azure Portal or via
`az webapp config appsettings set`, or run `azd up` to re-apply from Bicep.

### Runtime Discovery

The Web App only needs `FABRIC_WORKSPACE_ID` to bootstrap. Everything else
(Graph Model ID, Eventhouse Query URI, KQL DB name) is **discovered at runtime**
by `app/fabric_discovery.py` using the managed identity. This module:

- Queries the Fabric REST API for items in the workspace
- Matches resources by convention name (`NetworkTopologyOntology`, `NetworkTelemetryEH`)
- Caches results for 10 minutes (configurable via `FABRIC_DISCOVERY_TTL`)
- Honors env var overrides if set explicitly

---

## Project Structure

```
.
├── azure.yaml                  # azd service definitions & hooks
├── azure_config.env            # Runtime config (gitignored, auto-generated)
├── azure_config.env.template   # Config template (reference)
├── deploy.sh                   # End-to-end deployment orchestrator
│
├── api/                        # Unified FastAPI backend
│   ├── agents/
│   │   └── orchestrator.yaml   # Declarative agent definition (YAML)
│   ├── startup.sh              # gunicorn command for Web App
│   └── app/
│       ├── main.py             # App factory, all routes mounted
│       ├── paths.py            # PROJECT_ROOT, CONFIG_FILE, load_dotenv
│       ├── agent_loader.py     # AgentFactory + load_agent() singleton
│       ├── streaming.py        # agent.run(stream=True) → SSE events
│       ├── session_manager.py  # Session lifecycle + Cosmos persistence
│       ├── sessions.py         # Session dataclass
│       ├── tools/              # Typed async tool functions
│       │   ├── __init__.py     # TOOL_BINDINGS export
│       │   ├── graph.py        # graph_topology_query()
│       │   ├── telemetry.py    # telemetry_kql_query()
│       │   ├── search.py       # search_runbooks(), search_tickets()
│       │   └── dispatch.py     # dispatch_field_engineer()
│       ├── routers/            # REST/SSE endpoints
│       │   ├── sessions.py     # Session CRUD + SSE streaming
│       │   ├── config.py       # /api/config/* resource graph
│       │   ├── logs.py         # /api/logs SSE stream
│       │   ├── topology.py     # /query/topology (graph visualization)
│       │   ├── search.py       # /query/search (AI Search direct)
│       │   ├── health.py       # /query/health (data source probes)
│       │   ├── data_sessions.py # /query/sessions (Cosmos CRUD)
│       │   ├── interactions.py # /query/interactions
│       │   ├── replay.py       # /query/replay
│       │   ├── graph_backend.py    # /query/graph (GQL dispatch)
│       │   └── telemetry_backend.py # /query/telemetry (KQL dispatch)
│       ├── gq_config.py        # Graph-query configuration
│       ├── cosmos_helpers.py    # Cosmos DB client + container creation
│       ├── fabric_discovery.py  # Runtime Fabric resource discovery
│       ├── data_models.py      # Pydantic request/response models
│       ├── log_broadcaster.py  # SSE log fan-out
│       ├── adapters/           # Fabric GQL + KQL config
│       ├── backends/           # Graph backend implementations
│       │   └── fixtures/       # Static topology.json
│       └── stores/             # Document store (Cosmos NoSQL)
│
├── frontend/                   # React/Vite dashboard (TypeScript)
│   └── src/
│       ├── hooks/              # useInvestigation, useTopology, useScenarios
│       └── components/         # Header, SettingsModal, graph viewer
│
├── data/
│   └── scenarios/
│       └── telecom-playground/ # Extended telco scenario (default)
│           ├── scenario.yaml   # Scenario manifest
│           ├── graph_schema.yaml # Graph entity/edge definitions
│           └── data/           # entities/, telemetry/, knowledge/
│
├── scripts/
│   ├── provision_search_index.py # AI Search index creation
│   ├── generate_topology_json.py # Static topology JSON generator
│   └── fabric/
│       ├── provision_workspace.py
│       ├── provision_lakehouse.py
│       ├── provision_eventhouse.py
│       ├── provision_ontology.py
│       └── populate_fabric_config.py
│
├── infra/                      # Bicep IaC
│   ├── main.bicep              # Subscription-scoped orchestrator
│   └── modules/
│       ├── ai-foundry.bicep    # AI Foundry account + project + model
│       ├── web-app.bicep       # App Service Plan + Web App
│       ├── cosmos-nosql.bicep  # Cosmos DB NoSQL
│       ├── search.bicep        # AI Search
│       ├── storage.bicep       # Storage Account
│       ├── vnet.bicep          # VNet + subnets
│       ├── roles.bicep         # RBAC role assignments
│       └── fabric.bicep        # Fabric capacity (conditional)
│
├── hooks/
│   ├── preprovision.sh     # Sync config → azd env before Bicep
│   └── postprovision.sh    # Populate config from Bicep outputs
│
└── graph-query-api/            # (Legacy — merged into api/app/)
```

---

## Scenario Data Format

Each scenario is a self-contained directory under `data/scenarios/<name>/`:

```
telecom-playground/
├── scenario.yaml           # Manifest: agents, data sources, use cases
├── graph_schema.yaml       # Vertex/edge definitions + CSV file mappings
├── data/
│   ├── entities/           # CSVs for graph nodes + edges (→ Lakehouse)
│   │   ├── CoreRouter.csv
│   │   ├── AggSwitch.csv
│   │   ├── TransportLink.csv
│   │   └── ...
│   ├── telemetry/          # CSVs for time-series data (→ Eventhouse)
│   │   ├── AlertStream.csv
│   │   └── LinkTelemetry.csv
│   └── knowledge/          # Markdown docs (→ AI Search)
│       ├── runbooks/
│       └── tickets/
└── scripts/                # Scenario-specific generators (optional)
```

The provisioning pipeline is **fully data-driven** — adding a new entity type
only requires editing `graph_schema.yaml` and adding the corresponding CSV.
No code changes needed.

---

## Running Locally

```bash
# Terminal 1 — Backend API (single process — all routes)
cd api && source ../azure_config.env && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2 — Frontend (HMR enabled)
cd frontend && npm install && npm run dev
```

Open http://localhost:5173

---

## Operations

### Redeploy after code changes

```bash
azd deploy api    # Builds frontend, deploys Web App (~2 min)
```

### Update config in production

```bash
# Update App Settings directly
az webapp config appsettings set --name <webapp-name> -g <rg> \
  --settings KEY=value

# Or update via Bicep
azd up
```

### View Web App logs

```bash
# Get webapp name
WA_NAME=$(az webapp list -g rg-<env-name> --query "[0].name" -o tsv)

# Stream logs
az webapp log tail --name $WA_NAME -g rg-<env-name>
```

### Check data source connectivity

```bash
# From deployed app
curl -s https://<app-uri>/query/health/sources?scenario=telecom-playground | python3 -m json.tool

# Locally
curl -s http://localhost:8100/query/health/sources?scenario=telecom-playground | python3 -m json.tool
```

Expected healthy output:
```json
{
  "sources": [
    { "source_type": "graph",    "ok": true, "detail": "1 row(s)" },
    { "source_type": "telemetry","ok": true, "detail": "tables accessible" },
    { "source_type": "search_indexes.runbooks", "ok": true },
    { "source_type": "search_indexes.tickets",  "ok": true }
  ]
}
```

### CLI agent test

```bash
source azure_config.env && uv run python scripts/testing_scripts/test_orchestrator.py
```

---

## Teardown

### Full teardown (recommended)

```bash
bash infra/nuclear_teardown.sh
```

Runs `azd down --force --purge`, purges soft-deleted Cognitive Services accounts,
force-deletes the resource group, and clears azd environment state.

### Azure resources only

```bash
azd down --force --purge
```

### Delete just the Fabric workspace

This is done manually in the [Fabric portal](https://app.fabric.microsoft.com/) →
Workspace settings → Remove this workspace.

---

## Troubleshooting

### Common Issues

#### `FABRIC_WORKSPACE_ID not set — cannot discover Fabric resources`

The Web App doesn't have `FABRIC_WORKSPACE_ID` in its App Settings.

**Fix:**
```bash
# 1. Ensure it's populated locally
grep FABRIC_WORKSPACE_ID azure_config.env

# 2. If empty, run the populate script:
source azure_config.env && uv run python scripts/fabric/populate_fabric_config.py

# 3. Set it on the Web App:
az webapp config appsettings set --name <webapp-name> -g <rg> \
  --settings FABRIC_WORKSPACE_ID=$(grep FABRIC_WORKSPACE_ID azure_config.env | cut -d= -f2)
```

#### Agent provisioning fails with "Project not found"

**Cause:** The AI Foundry project endpoint may be wrong, or the project hasn't
finished provisioning.

**Fix:**
```bash
# Verify the project exists
az cognitiveservices account list -g rg-<env-name> --query "[?contains(name,'proj')]" -o table

# Test the endpoint
TOKEN=$(az account get-access-token --resource "https://cognitiveservices.azure.com" --query accessToken -o tsv)
curl -s -w "\nHTTP: %{http_code}" \
  "https://<aif-name>.services.ai.azure.com/api/projects/<proj-name>" \
  -H "Authorization: Bearer $TOKEN"
```

#### Fabric RBAC — Web App can't access workspace

The Web App's managed identity needs Contributor access on the Fabric workspace.

**Check:**
```bash
# Get the Web App's principal ID
source azure_config.env && echo $APP_PRINCIPAL_ID
```

**Fix (manual grant via Fabric API):**
```bash
FABRIC_TOKEN=$(az account get-access-token --resource https://api.fabric.microsoft.com --query accessToken -o tsv)
curl -X POST "https://api.fabric.microsoft.com/v1/workspaces/<workspace-id>/roleAssignments" \
  -H "Authorization: Bearer $FABRIC_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"principal":{"id":"<APP_PRINCIPAL_ID>","type":"ServicePrincipal"},"role":"Contributor"}'
```

Or grant via Fabric portal → Workspace → Manage access → Add the service principal as Contributor.

#### `azd up` fails — soft-deleted resources

```bash
# Purge soft-deleted Cognitive Services accounts
az cognitiveservices account list-deleted -o table
az cognitiveservices account purge --name <name> --resource-group <rg> --location <loc>

# Then retry
azd up
```

#### `azd up` fails — name conflict

Use a different environment name:
```bash
azd env delete <old-name> --yes
azd env new <new-name>
./deploy.sh --env <new-name>
```

#### Web App not starting / unhealthy

```bash
# View logs
az webapp log tail --name <webapp-name> -g <rg>

# Check provisioning state
az webapp show -n <webapp-name> -g <rg> --query "state"

# Restart
az webapp restart -n <webapp-name> -g <rg>
```

#### Graph queries return empty results

1. Check if Lakehouse has data:
   - Fabric portal → Workspace → Lakehouse → Tables tab
   - Each entity type from `graph_schema.yaml` should have a corresponding table

2. Check if the Ontology/Graph Model was created:
   - Fabric portal → Workspace → look for an item of type "GraphModel"

3. Check discovery:
   ```bash
   curl -s https://<app-uri>/query/health/sources?scenario=telecom-playground | python3 -m json.tool
   ```

#### KQL/Telemetry queries fail

1. Check if the Eventhouse exists and has tables:
   - Fabric portal → Workspace → Eventhouse → KQL Database

2. Verify the query URI:
   ```bash
   grep EVENTHOUSE_QUERY_URI azure_config.env
   ```

### Environment Variables Not Updating

Config flow:

```
azure_config.env (local file for development)
    ↓ azd up / az webapp config appsettings set
  App Settings on Azure Web App
    ↓ environment variables
  Available to FastAPI at runtime
```

For local dev, `paths.py` loads `azure_config.env` via `python-dotenv`.
For production, App Settings are injected by Azure.

### Useful Debug Commands

```bash
# List all resources in the resource group
az resource list -g rg-<env-name> -o table

# Check azd environment values
azd env get-values

# Check Web App env vars
az webapp config appsettings list -n <webapp-name> -g <rg> -o table

# Test Fabric API access with current credentials
TOKEN=$(az account get-access-token --resource https://api.fabric.microsoft.com --query accessToken -o tsv)
curl -s "https://api.fabric.microsoft.com/v1/workspaces/<workspace-id>/items" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool | head -30

# Re-run Fabric config discovery
source azure_config.env && uv run python scripts/fabric/populate_fabric_config.py
```

---

## Adding a New Scenario

1. Create `data/scenarios/<name>/scenario.yaml` (copy from `telecom-playground`)
2. Create `data/scenarios/<name>/graph_schema.yaml` defining vertex + edge types
3. Add entity CSVs to `data/scenarios/<name>/data/entities/`
4. Add telemetry CSVs to `data/scenarios/<name>/data/telemetry/`
5. Add runbook/ticket markdown files to `data/scenarios/<name>/data/knowledge/`
6. Deploy:
   ```bash
   ./deploy.sh --skip-infra --provision-all --scenario <name> --yes
   ```

The provisioning pipeline reads everything from `graph_schema.yaml` and
`scenario.yaml` — no hardcoded schema anywhere in the codebase.
