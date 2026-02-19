# AI Incident Investigator — Autonomous Network NOC

### Wear and tear alert scenario!

An AI-powered incident investigation platform that diagnoses operational issues
using multi-agent orchestration on Azure. Five specialist agents collaborate to
perform root-cause analysis, assess blast radius, retrieve operating procedures,
and produce actionable situation reports — without human intervention.

The platform is **scenario-agnostic** — new investigation domains are added as
self-contained data packs under `data/scenarios/`; no code changes required.

---

## Architecture

```
                         ┌─────────────────────────────────────────────┐
                         │       Unified Container App (:80)           │
                         │       supervisord × 3 processes             │
                         │                                             │
Browser ──POST /api/──▶  │  nginx :80                                  │
         ◀──SSE stream── │   ├─ /        → React SPA (static)         │
                         │   ├─ /api/*   → uvicorn :8000 (API)        │
                         │   ├─ /health  → uvicorn :8000              │
                         │   └─ /query/* → uvicorn :8100 (graph-api)  │
                         └────────────────┬────────────────────────────┘
                                          │ azure-ai-agents SDK
                              ┌───────────┴──────────┐
                              ▼         ▼            ▼
                        GraphExplorer  Telemetry  RunbookKB ...
                              │         │            │
                              ▼         ▼            ▼
                     Fabric GQL    Fabric KQL    AI Search
                    (graph model)  (eventhouse)  (vector indexes)
```

### AI Agents

| Agent | Data Source | Tool |
|-------|-----------|------|
| **GraphExplorer** | Topology graph (Fabric GQL) | `OpenApiTool` → `/query/graph` |
| **Telemetry** | Metrics & alerts (Fabric KQL Eventhouse) | `OpenApiTool` → `/query/telemetry` |
| **RunbookKB** | Operational procedures | `AzureAISearchTool` → runbooks index |
| **HistoricalTicket** | Past incident records | `AzureAISearchTool` → tickets index |
| **Orchestrator** | Delegates to above 4 agents | `ConnectedAgentTool` |

### Azure Resources (provisioned by `azd up`)

| Resource | Purpose |
|----------|---------|
| AI Foundry (account + project) | Hosts GPT-4.1 deployment + agent definitions |
| Azure AI Search | Vector search indexes (runbooks, tickets) |
| Storage Account | Blob storage for search indexer data source |
| Cosmos DB NoSQL | Interaction/session store |
| Container Apps Environment | ACR + Log Analytics + Container App hosting |
| Unified Container App | nginx + API + graph-query-api (1 CPU, 2Gi, 1–3 replicas) |
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

# Full end-to-end: infrastructure + Fabric + data + agents
./deploy.sh --provision-all --yes

# Or step-by-step with prompts:
./deploy.sh                         # Step 1: Infrastructure only
./deploy.sh --skip-infra --provision-fabric   # Step 2: Fabric resources
./deploy.sh --skip-infra --provision-data     # Step 3: AI Search indexes
./deploy.sh --skip-infra --provision-agents   # Step 4: AI agents
```

### What happens during `./deploy.sh --provision-all`:

| Step | What it does | Duration |
|------|-------------|----------|
| **0** | Check/install prerequisites (Python, uv, Node, az, azd) | ~10s |
| **1** | Select or create azd environment | interactive |
| **2** | Configure graph backend (Fabric GQL) | ~5s |
| **2b** | Generate static `topology.json` from scenario CSVs | ~5s |
| **3** | `azd up` — provision all Azure resources + build/deploy container | **10–15 min** |
| **3b** | Auto-discover resources, write `azure_config.env` | ~30s |
| **4a** | Find-or-create Fabric workspace (hard gate — exits on failure) | ~30s |
| **4b** | Grant Container App managed identity Contributor on workspace | ~5s |
| **4c** | Provision Lakehouse + upload entity CSVs + load delta tables | ~3 min |
| **4d** | Provision Eventhouse + create KQL tables + ingest telemetry CSVs | ~3 min |
| **4e** | Provision IQ Ontology + Graph Model from `graph_schema.yaml` | ~2 min |
| **4f** | Re-populate `azure_config.env` with discovered Fabric IDs | ~10s |
| **5** | Create AI Search indexes (runbooks + tickets) from blob storage | ~2 min |
| **6** | Provision 5 AI Foundry agents | ~1 min |
| **6b** | Sync `FABRIC_WORKSPACE_ID` → azd env → Container App env vars | ~2 min |
| **7** | Health check (poll `/health` up to 5× with 15s intervals) | ~15s |

---

## deploy.sh Reference

### Flags

| Flag | Effect |
|------|--------|
| `--provision-fabric` | Run Fabric provisioning (Steps 4a–4f) |
| `--provision-data` | Run data provisioning (Step 5 — AI Search indexes) |
| `--provision-agents` | Run agent provisioning (Step 6) |
| `--provision-all` | All three above |
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

# Redeploy app container only (after code changes)
azd deploy app

# Re-provision Fabric resources only
./deploy.sh --skip-infra --provision-fabric --yes

# Re-provision agents only
./deploy.sh --skip-infra --provision-agents --yes

# Re-provision everything except Azure infra
./deploy.sh --skip-infra --provision-all --yes

# Deploy to a specific environment and location
./deploy.sh --env myenv --location eastus2

# CLI agent provisioning (outside deploy.sh)
source azure_config.env && uv run python scripts/provision_agents.py --force
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

### How config reaches the Container App

`azure_config.env` is **baked into the Docker image** (copied to `/app/azure_config.env`).
Both Python services load it at startup:

- **API** (`api/app/paths.py`): `load_dotenv(PROJECT_ROOT / "azure_config.env")`
- **graph-query-api** (`main.py`): `load_dotenv("/app/azure_config.env", override=True)`

The `override=True` is critical — without it, empty env vars injected by Bicep
(e.g., `FABRIC_WORKSPACE_ID=""`) would shadow the values in the file.

**To update config in production:** edit `azure_config.env` locally, then run
`azd deploy app` to rebuild the image with the updated file.

### Runtime Discovery

The Container App only needs `FABRIC_WORKSPACE_ID` to bootstrap. Everything else
(Graph Model ID, Eventhouse Query URI, KQL DB name) is **discovered at runtime**
by `graph-query-api/fabric_discovery.py` using the managed identity. This module:

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
├── Dockerfile                  # Unified container: nginx + API + graph-query-api
├── nginx.conf                  # Reverse proxy config
├── supervisord.conf            # Process manager (3 services)
│
├── api/                        # FastAPI backend (port 8000)
│   └── app/
│       ├── main.py             # App factory, CORS, router mounting
│       ├── paths.py            # PROJECT_ROOT, CONFIG_FILE, load_dotenv
│       ├── orchestrator.py     # Foundry agent bridge (sync SDK → async SSE)
│       └── routers/
│           ├── alert.py        # POST /api/alert → SSE investigation stream
│           ├── agents.py       # GET /api/agents — list provisioned agents
│           ├── config.py       # POST /api/config/apply → re-provision agents
│           └── logs.py         # GET /api/logs → SSE log stream
│
├── graph-query-api/            # Graph & telemetry queries (port 8100)
│   ├── main.py                 # App factory, load_dotenv, lifespan
│   ├── config.py               # ScenarioContext, backend selection
│   ├── fabric_discovery.py     # Runtime Fabric resource discovery
│   ├── router_graph.py         # POST /query/graph (GQL dispatch)
│   ├── router_telemetry.py     # POST /query/telemetry (KQL dispatch)
│   ├── router_topology.py      # POST /query/topology (graph visualization)
│   ├── router_interactions.py  # Interaction/session CRUD (Cosmos NoSQL)
│   ├── router_health.py        # GET /query/health/sources (connectivity check)
│   ├── search_indexer.py       # AI Search indexer pipeline
│   ├── adapters/               # Fabric GQL + KQL adapters
│   ├── backends/               # Backend implementations
│   │   └── fixtures/           # Static topology.json (pre-built)
│   ├── services/               # Blob uploader, data helpers
│   └── stores/                 # Cosmos interaction store
│
├── frontend/                   # React/Vite dashboard (TypeScript)
│   └── src/
│       ├── hooks/              # useInvestigation, useTopology, useScenarios
│       └── components/         # Header, SettingsModal, graph viewer
│
├── data/
│   └── scenarios/
│       ├── telecom-playground/ # Extended telco scenario (default)
│       │   ├── scenario.yaml   # Scenario manifest
│       │   ├── graph_schema.yaml # Graph entity/edge definitions
│       │   └── data/           # entities/, telemetry/, knowledge/
│       └── telco-noc/          # Compact telco scenario
│
├── scripts/
│   ├── agent_provisioner.py    # AgentProvisioner (importable module)
│   ├── provision_agents.py     # CLI agent provisioning
│   ├── provision_search_index.py # AI Search index creation
│   ├── generate_topology_json.py # Static topology JSON generator
│   └── fabric/
│       ├── _config.py          # Shared Fabric config (API URL, workspace name)
│       ├── provision_workspace.py  # Find-or-create Fabric workspace
│       ├── provision_lakehouse.py  # Lakehouse + CSV upload + table load
│       ├── provision_eventhouse.py # Eventhouse + KQL tables + telemetry ingest
│       ├── provision_ontology.py   # IQ Ontology + Graph Model
│       └── populate_fabric_config.py # Discover Fabric IDs → azure_config.env
│
├── infra/                      # Bicep IaC
│   ├── main.bicep              # Subscription-scoped orchestrator
│   ├── main.parameters.json    # Parameter file (reads from azd env)
│   ├── modules/
│   │   ├── ai-foundry.bicep    # AI Foundry account + project + GPT deployment
│   │   ├── container-app.bicep # Unified Container App
│   │   ├── container-apps-environment.bicep # CAE + ACR + Log Analytics
│   │   ├── cosmos-nosql.bicep  # Cosmos DB NoSQL
│   │   ├── cosmos-private-endpoints.bicep
│   │   ├── fabric.bicep        # Fabric capacity (conditional)
│   │   ├── roles.bicep         # RBAC role assignments
│   │   ├── search.bicep        # AI Search
│   │   ├── storage.bicep       # Storage Account
│   │   └── vnet.bicep          # VNet + subnets
│   └── nuclear_teardown.sh     # Full teardown + purge
│
├── hooks/
│   ├── preprovision.sh         # Sync config → azd env before Bicep
│   └── postprovision.sh        # Populate config from Bicep outputs
│
└── documentation/              # Architecture docs, plans, changelogs
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
# Terminal 1 — Backend API
cd api && source ../azure_config.env && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2 — Graph Query API
cd graph-query-api && source ../azure_config.env && uv run uvicorn main:app --host 0.0.0.0 --port 8100 --reload

# Terminal 3 — Frontend (HMR enabled)
cd frontend && npm install && npm run dev
```

Open http://localhost:5173

---

## Operations

### Redeploy after code changes

```bash
azd deploy app    # Rebuilds the container image remotely and creates a new revision (~2 min)
```

### Update config in production

```bash
# 1. Edit azure_config.env locally
# 2. Redeploy to bake updated config into the image
azd deploy app
```

### View Container App logs

```bash
# Get container app name
CA_NAME=$(az containerapp list -g rg-<env-name> --query "[0].name" -o tsv)

# Stream console logs
az containerapp logs show --name $CA_NAME -g rg-<env-name> --type console --tail 100 --follow

# System logs (container restarts, scaling events)
az containerapp logs show --name $CA_NAME -g rg-<env-name> --type system --tail 50
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

The graph-query-api container doesn't have `FABRIC_WORKSPACE_ID` in its environment.

**Cause:** `azure_config.env` doesn't contain the value, or the container image
was built before the Fabric provisioning step populated it.

**Fix:**
```bash
# 1. Ensure it's populated locally
grep FABRIC_WORKSPACE_ID azure_config.env
# Should show: FABRIC_WORKSPACE_ID=<guid>

# 2. If empty, run the populate script:
source azure_config.env && uv run python scripts/fabric/populate_fabric_config.py

# 3. Redeploy to bake into the image:
azd deploy app
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

#### Fabric RBAC — Container App can't access workspace

The Container App's managed identity needs Contributor access on the Fabric workspace.

**Check:**
```bash
# Get the Container App's principal ID
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

#### Container App not starting / unhealthy

```bash
# Check revision status
az containerapp revision list -n <ca-name> -g <rg> -o table

# Check provisioning state
az containerapp show -n <ca-name> -g <rg> --query "properties.provisioningState"

# View startup logs
az containerapp logs show -n <ca-name> -g <rg> --type console --tail 100
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

Remember the config flow:

```
azure_config.env (local file)
    ↓ azd deploy app
  COPY into Docker image → /app/azure_config.env
    ↓ load_dotenv (override=True)
  Available to graph-query-api + API at runtime
```

If you change `azure_config.env`, you **must** run `azd deploy app` to push
the changes into the container.

### Useful Debug Commands

```bash
# List all resources in the resource group
az resource list -g rg-<env-name> -o table

# Check azd environment values
azd env get-values

# Check Container App env vars
az containerapp show -n <ca-name> -g <rg> --query "properties.template.containers[0].env" -o table

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
