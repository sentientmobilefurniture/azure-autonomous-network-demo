# Sydney Fiber Cut Demo 

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

1. GraphExplorerAgent in Foundry connects to Fabric ontology via fabric data agent and uses it to navigate network topology.
2. RunbookKBAgent in Foundry looks at historical runbooks for guidance on what to do in certain scenarios. (connected to runbooks-index)
3. HistoricalTicketAgent looks at old tickets to find similar scenarios (connected to tickets-index)
4. TelemetryAgent looks at telemetry stored in Fabric EventHouse and uses it to retrieve metrics and observational evidence. 
5. Orchestrator agent receives alert storm prompt (/data/prompts/alert_storm.md), runs diagnosis flow in (/home/hanchoong/projects/autonomous-network-demo/data/prompts/orchestrator_agent.md) 

## Current Implementation State 

1. azd up to deploy azure services works okay 
2. provision fabric and create indexer scripts work okay
3. fabric data agent works fine 
4. foundry agent can call fabric data agent
5. Foundry agent can call other agents 

## Currently working setup steps
0. Create azure_config.env from the azure_config.env.template file, fill in desired params, leave auto-marked params blank.
1. azd up -e myenvname (This will name both the env and the resource group)
2. uv run python3 create_runbook_indexer.py
3. uv run python3 create_tickets_indexer.py
4. uv run python3 provision_fabric.py
5. uv run python3 provision_ontology.py (to test if working)
5. Manually create ontology in Microsoft Fabric UI, manually create fabric data agents
6. Manually create anomaly detectors
7. Manually create agents using the prompts in /data/prompts

## Items yet to be done
1. Haven't wired up anomaly detector
2. Haven't wired up multi-agent flow 

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