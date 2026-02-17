# Old Ways Setup Guide

Step-by-step instructions to deploy the AI Incident Investigator demo from scratch.

---

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.11+ | `brew install python@3.12` or system package manager |
| uv | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Node.js | 20+ | `nvm install 20` |
| Azure CLI | latest | `curl -sL https://aka.ms/InstallAzureCLIDeb \| sudo bash` |
| Azure Developer CLI (azd) | latest | `curl -fsSL https://aka.ms/install-azd.sh \| bash` |

You also need:
- An Azure subscription with sufficient quota
- A Microsoft Fabric workspace (you'll need the workspace ID)
- Owner or Contributor access on the subscription

---

## Step 1: Deploy Azure Infrastructure

```bash
cd fabricdemo
chmod +x deploy.sh
./deploy.sh
```

This runs `azd up` which provisions:
- Resource Group
- AI Foundry (account + project + GPT-4.1 deployment)
- Azure AI Search
- Storage Account
- Cosmos DB NoSQL (interactions store)
- Fabric Capacity (F8, if `fabricAdminEmail` param is set)
- Container Apps Environment (ACR + Log Analytics)
- Unified Container App (nginx + API + graph-query-api)

The script will:
1. Check/install prerequisites
2. Let you create or select an azd environment
3. Write `azure_config.env` with `GRAPH_BACKEND=fabric-gql`
4. Run `azd up` (~10-15 minutes)
5. Verify the deployed app is healthy

After completion, `azure_config.env` is populated with all resource names and endpoints.

### Flags

| Flag | Purpose |
|------|---------|
| `--skip-infra` | Skip `azd up`, reuse existing Azure resources |
| `--skip-local` | Don't start local dev servers after deploy |
| `--env NAME` | Use a specific azd environment name |
| `--location LOC` | Azure location (default: `swedencentral`) |
| `--yes` / `-y` | Skip all confirmation prompts |

---

## Step 2: Set Up Microsoft Fabric

### 2a. Set `FABRIC_WORKSPACE_ID`

If you already have a Fabric workspace, open `azure_config.env` and set:

```env
FABRIC_WORKSPACE_ID=<your-workspace-guid>
```

### 2b. Grant Container App access to Fabric

The Container App's managed identity needs Contributor access on the Fabric workspace. `deploy.sh` attempts this automatically in Step 4, but if it fails, do it manually:

```bash
source azure_config.env
uv run python scripts/fabric/assign_fabric_role.py
```

Or grant access in the Fabric portal:
> Fabric Portal → Workspace → Manage access → Add `APP_PRINCIPAL_ID` as **Contributor**

### 2c. Provision Fabric resources

```bash
./deploy.sh --skip-infra --provision-fabric
```

This runs four scripts in sequence:
1. **provision_lakehouse.py** — Creates the `NetworkTopologyLH` lakehouse
2. **provision_eventhouse.py** — Creates the `NetworkTelemetryEH` eventhouse + KQL database
3. **provision_ontology.py** — Creates the `NetworkTopologyOntology` ontology + graph model with all 7 relationship types
4. **populate_fabric_config.py** — Discovers created resource IDs and writes them to `azure_config.env`

After this step, `azure_config.env` will have `FABRIC_WORKSPACE_ID`, `FABRIC_GRAPH_MODEL_ID`, `FABRIC_EVENTHOUSE_ID`, `FABRIC_KQL_DB_NAME`, and `EVENTHOUSE_QUERY_URI` populated.

---

## Step 3: Load Data

```bash
./deploy.sh --skip-infra --provision-data
```

This runs:
1. **provision_cosmos.py** — Loads alert stream and link telemetry into Cosmos DB NoSQL
2. **provision_search_index.py --upload-files** — Uploads runbooks + tickets to blob storage, creates AI Search indexes (with HNSW vectorization), and runs indexers

Data sources:
- `data/scenarios/telco-noc/data/telemetry/` → Cosmos DB
- `data/scenarios/telco-noc/data/knowledge/runbooks/` → Blob → AI Search `runbooks-index`
- `data/scenarios/telco-noc/data/knowledge/tickets/` → Blob → AI Search `tickets-index`

> **Note:** `postprovision.sh` (run automatically by `azd up`) also uploads runbooks and tickets to blob storage. The `--provision-data` step creates the search indexes on top of that.

---

## Step 4: Provision AI Agents

```bash
./deploy.sh --skip-infra --provision-agents
```

This creates 5 AI Foundry agents:
1. **Orchestrator** — Routes alerts to specialist agents
2. **GraphExplorer** — Queries network topology via Fabric GQL (OpenApiTool)
3. **Telemetry** — Queries telemetry via Fabric KQL (OpenApiTool)
4. **RunbookKB** — Searches runbook knowledge base (Azure AI Search tool)
5. **HistoricalTicket** — Searches historical tickets (Azure AI Search tool)

Agent IDs are saved to `scripts/agent_ids.json`, which the API reads at runtime.

To re-provision agents (e.g., after changing prompts):
```bash
source azure_config.env && uv run python scripts/provision_agents.py --force
```

After this step, redeploy the app so it picks up the new `agent_ids.json`:
```bash
azd deploy app
```

---

## Step 5: Verify

Open the app URL (printed at the end of deploy, or check `APP_URI` in `azure_config.env`):

```bash
source azure_config.env && echo $APP_URI
```

### Smoke test

Paste an alert into the investigation panel:

```
14:31:14.259 CRITICAL VPN-ACME-CORP SERVICE_DEGRADATION VPN tunnel unreachable
```

You should see:
- The orchestrator route to specialist agents
- Graph topology queries returning network nodes/links
- Telemetry data showing recent metrics
- Runbook recommendations
- Similar historical tickets
- A final synthesized analysis

### Health check

```bash
curl $APP_URI/health
```

---

## All-In-One (Steps 2c–4)

If Fabric workspace is already set up and `FABRIC_WORKSPACE_ID` is in `azure_config.env`:

```bash
./deploy.sh --skip-infra --provision-all
```

This runs Fabric provisioning + data loading + agent provisioning in one go.

---

## Quick Reference

### Redeploy after code changes
```bash
azd deploy app
```

### Tear down everything
```bash
azd down --force --purge
```

### Run locally (instead of Azure)
```bash
# Terminal 1 — API
cd api && source ../azure_config.env && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2 — Graph Query API
cd graph-query-api && source ../azure_config.env && uv run uvicorn main:app --host 0.0.0.0 --port 8100 --reload

# Terminal 3 — Frontend
cd frontend && npm install && npm run dev
```

Open http://localhost:5173

### Key files

| File | Purpose |
|------|---------|
| `azure_config.env` | Single source of truth for all configuration |
| `azure_config.env.template` | Template with all vars and comments |
| `deploy.sh` | End-to-end deployment orchestrator |
| `hooks/preprovision.sh` | Syncs config → azd env before Bicep |
| `hooks/postprovision.sh` | Uploads blobs + populates config after Bicep |
| `scripts/agent_ids.json` | Agent IDs (created by provision_agents.py) |
| `scripts/fabric/` | Fabric provisioning scripts |
| `scripts/provision_cosmos.py` | Cosmos DB data loader |
| `scripts/provision_search_index.py` | AI Search index pipeline |
| `scripts/provision_agents.py` | AI Foundry agent provisioner |

---

## Troubleshooting

### `azd up` fails with quota exceeded
Try a different location: `./deploy.sh --location eastus2`

### `azd up` fails with name conflict
Soft-deleted resources may block names. Purge and retry:
```bash
azd down --force --purge
./deploy.sh
```

### App not responding after deploy
Container may still be starting. Check logs:
```bash
az containerapp logs show --name <ca-name> --resource-group <rg-name> --type console --tail 50
```

### Agents return errors
Ensure `GRAPH_QUERY_API_URI` in `azure_config.env` points to the app URL (should be same as `APP_URI`). Re-provision agents with `--force` so they pick up the correct OpenAPI endpoint.

### Fabric provisioning fails
Ensure you're logged into the Fabric tenant:
```bash
az login --tenant <your-tenant-id>
```
Check that `FABRIC_WORKSPACE_ID` is correct and your user has admin access to the workspace.
