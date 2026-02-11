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

1. GraphExplorerAgent in Foundry connects to Fabric ontology via fabric data agent (NetworkQueryAgent) and uses it to navigate network topology.
2. RunbookKBAgent in Foundry looks at historical runbooks for guidance on what to do in certain scenarios. (connected to runbooks-index)
3. HistoricalTicketAgent looks at old tickets to find similar scenarios (connected to tickets-index)
4. TelemetryAgent connects to telemetry stored in Fabric EventHouse via fabric data agent (TelemetryQueryAgent) and uses it to retrieve metrics and observational evidence. 
5. Orchestrator agent receives alert storm prompt (/data/prompts/alert_storm.md), runs diagnosis flow in (/home/hanchoong/projects/autonomous-network-demo/data/prompts/orchestrator_agent.md). Is connected to GraphExplorerAgent, RunbookKBAgent, HistoricalTicketAgent, TelemetryAgent

## Current Implementation State 

1. azd up to deploy azure services works okay 
2. provision fabric and create indexer scripts work okay
3. fabric data agent works fine 
4. foundry agent can call fabric data agent
5. Foundry agent can call other agents 

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

This deploys AI Foundry, AI Search, Storage, and Fabric Capacity via Bicep.

### 3. Provision data stores

```bash
uv run python scripts/create_runbook_indexer.py
uv run python scripts/create_tickets_indexer.py
uv run python scripts/provision_lakehouse.py
uv run python scripts/provision_eventhouse.py
uv run python scripts/provision_ontology.py   # ~30 min for graph indexing
```

### 4. Create Fabric Data Agents (manual)

1. Create anomaly detectors in Fabric
2. Create two Fabric Data Agents using prompts in `data/prompts/`:
   - `fabric_network_data_agent_instructions.md` → Graph/Ontology Data Agent (Lakehouse)
   - `fabric_telemetry_data_agent_instructions.md` → Telemetry Data Agent (Eventhouse)
3. Register them:
   ```bash
   uv run python scripts/collect_fabric_agents.py
   ```

### 5. Create Fabric connections in Foundry

Manually create **two** Fabric connections in Foundry UI (Management Center → Connected Resources).
`provision_agents.py` will prompt for connection names if not pre-filled in `azure_config.env`.

### 6. Provision Foundry agents

```bash
uv run python scripts/provision_agents.py
```

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

## TODO

### Automation
- [x] Bug fix provision_ontology.py
- [x] Auto fill eventhouse tables
- [ ] Auto create fabric data agents (pending API support)
- [ ] Auto create anomaly detectors (pending API support)
- [x] Multi-agent workflow provisioning
- [x] Test multi-agent flow programmatically
- [x] Stream agent events with input/output metadata

### Frontend & API
- [x] FastAPI backend with SSE streaming
- [x] React/Vite dark theme UI scaffold
- [ ] Wire real orchestrator into SSE endpoint
- [ ] Deploy API to Azure Container Apps
- [ ] Deploy frontend to Azure Static Web Apps

### Future
- [ ] MCP server tools (query_eventhouse, search_tickets, create_incident)
- [ ] CosmosDB for tickets
- [ ] Corrective action API
- [ ] Live visualization of the graph directly in the UI
- [ ] Click on a node, select a particular type of error or scenario, trigger it! - Needs reset button. Hot damn! 
- [ ] Expand data complexity and size to more closely affect real world? 