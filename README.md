# Sydney Fiber Cut Demo 

> **CONFIRMATION NEEDED **Tip: Ontology is a preview feature and may exhibit unexpected behaviors. Sweden Central may be faster due to less regional contention, but this is anecdotal and needs more observation. Expect 20-90 minutes for the graph to finish indexing and become available to query. This wait is normal for now. If you are anxious, scheduling a graph refresh may help as one is triggered whenever the ontology is updated.**

## Prerequisites

Before you begin, install the following tools and authenticate:

### Tools

| Tool | Install | Verify |
|------|---------|--------|
| **Python 3.11+** | [python.org](https://www.python.org/downloads/) or `sudo apt install python3` | `python3 --version` |
| **uv** (package manager) | `curl -LsSf https://astral.sh/uv/install.sh \| sh` | `uv --version` |
| **Azure CLI (`az`)** | [Install Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli-linux) | `az --version` |
| **Azure Developer CLI (`azd`)** | `curl -fsSL https://aka.ms/install-azd.sh \| bash` | `azd version` |

### Authentication

```bash
# Log in to Azure CLI
az login

# Log in to Azure Developer CLI (uses the same browser flow)
azd auth login
```

Both CLIs must be authenticated before running any provisioning or deployment commands. `azd up` uses your Azure CLI credentials under the hood.

### Python Dependencies

All Python dependencies are managed via `pyproject.toml` and installed automatically by `uv run`. No manual `pip install` needed — just prefix commands with `uv run`.

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

## Currently working setup steps
0. Create azure_config.env from the azure_config.env.template file, fill in desired params, leave auto-marked params blank.
02. Run data creation scripts:
```bash
uv run python3 generate_alert_stream.py
uv run python3 generate_routing_data.py
uv run python3 generate_tickets.py
uv run python3 generate_topology_data.py
```
1. Run deployment scripts: 
```bash
azd up -e myenvname (This will name both the env and the resource group)
uv run python3 create_runbook_indexer.py
uv run python3 create_tickets_indexer.py
uv run python3 provision_lakehouse.py
uv run python3 provision_eventhouse.py
uv run python3 provision_ontology.py # To Swedencentral - Requires 30 mins to become available for query
```
2. Manually create anomaly detectors
3. Manually create fabric data agents using the prompts in /data/prompts:
   - `fabric_network_data_agent_instructions.md` → Graph/Ontology Data Agent (Lakehouse)
   - `fabric_telemetry_data_agent_instructions.md` → Telemetry Data Agent (Eventhouse)
4. Run this script and select the appropriate agents:
```bash
uv run python3 collect_fabric_agents.py
```
5. Manually create **two** fabric connections in Foundry UI (one per Data Agent) (Management Center -> Connected Resources). Refer to azure_config.env for workspace and artifact IDs
   `provision_agents.py` will prompt for the connection names if not pre-filled in `azure_config.env`.
6. Run this script to create the multi-agent system:
```bash 
uv run python3 provision_agents.py
```
7. Run this script to test the multi-agent flow:
```bash
uv run python3 test_orchestrator.py
```

## TO DO - Automation Tasks 
1. ~~Bug fix provision_ontology.py - Why doesn't graph materialize?~~
2. ~~Auto fill eventhouse tables~~
3. (HOLD) Auto create fabric data agents for telemetry and graph (Not sure if supported)
4. (HOLD) Auto create anomaly detectors (Not sure if supported)
5. ~~Automatically define multi-agent workflow (using yaml rather than pure python SDK)~~
6. ~~Test multi-agent workflow programmatically ~~
7. Stream agent events and thread logs for eventual display on a UI

## TO DO - Demo Completion - Frontend time
1. Create simulator environment - See about using Azure Websites
2. At push of a button, trigger alert storm, see results 
3. Agent should trigger some corrective action (Dummy API request)

## TO DO - Demo Structuring  
1. Deploy MCP server 
2. Switch tickets to CosmosDB, connect to cosmosdb 
3. 

## TO DO - Extra Credit
1. Dummy API response does something to a simulated network infra (Seems unnecessary lol)
2. Linking time series data to an entity does something 

---

## Architecture Map

### Infrastructure (Bicep via `azd up`)

| Module | Azure Resource | Purpose |
|--------|---------------|---------|
| `ai-foundry.bicep` | AI Foundry Hub + Project | Agent hosting, model deployments |
| `search.bicep` | AI Search | Hybrid (vector + keyword) search over runbooks & tickets |
| `storage.bicep` | Storage Account | Blob containers for runbook/ticket source docs |
| `fabric.bicep` | Fabric Capacity | Compute for Lakehouse, Eventhouse, Ontology, Data Agent |
| `roles.bicep` | Role Assignments | RBAC for user, search, and foundry identities |

### Data Stores & What Goes In

| Store | Item | Data Loaded |
|-------|------|-------------|
| **Blob Storage** | `runbooks` container | 5 markdown runbooks (fibre cut, BGP loss, alert triage, reroute, comms template) |
| | `tickets` container | 10 historical incident `.txt` files |
| **AI Search** | `runbooks-index` | Chunked + embedded runbook docs (hybrid search) |
| | `tickets-index` | Chunked + embedded ticket docs (hybrid search) |
| **Fabric Lakehouse** (`NetworkTopologyLH`) | Dim tables | `DimCoreRouter`, `DimTransportLink`, `DimAggSwitch`, `DimBaseStation`, `DimBGPSession`, `DimMPLSPath`, `DimService`, `DimSLAPolicy` |
| | Fact tables | `FactMPLSPathHops`, `FactServiceDependency` |
| **Fabric Eventhouse** (`NetworkTelemetryEH`) | KQL DB (`NetworkDB`) | `AlertStream` (alerts with severity, optical power, BER, CPU, packet loss) · `LinkTelemetry` (utilization, latency, optical power, BER per link) |
| **Fabric Ontology** | `NetworkTopologyOntology` | 8 entity types + 7 relationship types binding Lakehouse dims + Eventhouse time-series |

### MCP Server (Azure Functions)

Hosted function app exposing 3 tools to Foundry agents via MCP protocol:

| Tool | Backend | Action |
|------|---------|--------|
| `query_eventhouse` | Fabric Eventhouse (KQL) | Run arbitrary KQL against `NetworkDB` |
| `search_tickets` | AI Search (`tickets-index`) | Hybrid search over historical incidents |
| `create_incident` | In-memory (stub) | Generate a structured incident ticket |

### Foundry Agents

| Agent | Role | Data Source |
|-------|------|-------------|
| **Orchestrator** | Top-level supervisor; routes to sub-agents | Connects to all agents below |
| **GraphExplorerAgent** | Discover blast radius via network topology | Fabric Data Agent (Ontology → Lakehouse/Eventhouse) |
| **TelemetryAgent** | Query real-time link/alert telemetry | MCP `query_eventhouse` |
| **RunbookKBAgent** | Find relevant operational procedures | AI Search `runbooks-index` |
| **HistoricalTicketAgent** | Find similar past incidents | MCP `search_tickets` / AI Search `tickets-index` |

### Data Flow (Demo)

```
Anomaly detected (latency spike)
  → Orchestrator
    → GraphExplorerAgent   → Fabric Ontology/Lakehouse → blast radius
    → TelemetryAgent       → Eventhouse KQL            → live metrics
    → HistoricalTicketAgent→ AI Search tickets-index    → precedent
    → RunbookKBAgent       → AI Search runbooks-index   → remediation
  → Orchestrator synthesizes diagnosis + recommended action
  → create_incident tool   → structured ticket output
```