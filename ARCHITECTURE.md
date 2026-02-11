# Architecture

## System Overview

Multi-agent NOC diagnosis system. An alert enters via the frontend, flows through
a FastAPI backend that streams SSE progress, and reaches an orchestrator agent in
Azure AI Foundry. The orchestrator delegates to four specialist agents, each backed
by a distinct data source in Microsoft Fabric or Azure AI Search.

```
┌──────────────┐      POST /api/alert       ┌──────────────────┐
│   Frontend   │  ───────────────────────▶   │   FastAPI API    │
│  React/Vite  │  ◀─────── SSE stream ────  │   (uvicorn)      │
│  :5173       │                             │   :8000          │
└──────────────┘                             └────────┬─────────┘
                                                      │ azure-ai-agents SDK
                                                      ▼
                                          ┌───────────────────────┐
                                          │   Orchestrator Agent  │
                                          │   (Azure AI Foundry)  │
                                          └───┬───┬───┬───┬───────┘
                        ┌─────────────────────┘   │   │   └──────────────────────┐
                        ▼                         ▼   ▼                          ▼
              ┌─────────────────┐   ┌──────────────┐ ┌──────────────┐  ┌─────────────────┐
              │ GraphExplorer   │   │ Telemetry    │ │ RunbookKB    │  │ HistoricalTicket│
              │ Agent           │   │ Agent        │ │ Agent        │  │ Agent           │
              └────────┬────────┘   └──────┬───────┘ └──────┬───────┘  └────────┬────────┘
                       │ FabricTool         │ FabricTool     │ AI Search         │ AI Search
                       ▼                    ▼                ▼                   ▼
              ┌──────────────┐   ┌───────────────┐  ┌──────────────┐  ┌──────────────────┐
              │ Fabric       │   │ Fabric        │  │ runbooks-    │  │ tickets-         │
              │ Ontology +   │   │ Eventhouse    │  │ index        │  │ index            │
              │ Lakehouse    │   │ (KQL/AlertDB) │  │ (hybrid)     │  │ (hybrid)         │
              └──────────────┘   └───────────────┘  └──────────────┘  └──────────────────┘
```

---

## Project Structure

```
.
├── azure.yaml                  # azd project definition (hooks, service targets)
├── azure_config.env            # Runtime config — single source of truth (gitignored)
├── azure_config.env.template   # Checked-in template for azure_config.env
├── pyproject.toml              # Python deps for scripts/ (uv-managed)
│
├── infra/                      # Bicep IaC (deployed by `azd up`)
│   ├── main.bicep              # Subscription-scoped orchestrator
│   ├── main.bicepparam         # Reads env vars via readEnvironmentVariable()
│   └── modules/
│       ├── ai-foundry.bicep    # AI Foundry account + project + GPT deployment
│       ├── search.bicep        # Azure AI Search
│       ├── storage.bicep       # Storage account + blob containers
│       ├── fabric.bicep        # Fabric capacity (F-SKU)
│       └── roles.bicep         # RBAC assignments
│
├── hooks/                      # azd lifecycle hooks
│   ├── preprovision.sh         # Syncs azure_config.env → azd env vars for Bicep
│   └── postprovision.sh        # Uploads data to blob, writes outputs → azure_config.env
│
├── data/                       # Source data (checked in)
│   ├── runbooks/               # Markdown runbook files → uploaded to blob → AI Search
│   ├── tickets/                # JSON ticket files → uploaded to blob → AI Search
│   ├── lakehouse/              # CSV topology data → loaded into Fabric Lakehouse
│   ├── eventhouse/             # CSV telemetry data → ingested into Fabric Eventhouse
│   ├── prompts/                # Agent system prompts (Foundry + Fabric Data Agents)
│   └── scripts/                # Synthetic data generators (run once)
│
├── scripts/                    # Provisioning & operational scripts
│   ├── _config.py              # Shared config module (FABRIC_API, paths, helpers)
│   ├── provision_lakehouse.py  # Create Fabric workspace + lakehouse + load CSVs
│   ├── provision_eventhouse.py # Create Eventhouse + KQL tables + ingest CSVs
│   ├── provision_ontology.py   # Create Ontology item on Lakehouse data
│   ├── create_runbook_indexer.py   # Build AI Search index from blob runbooks
│   ├── create_tickets_indexer.py   # Build AI Search index from blob tickets
│   ├── populate_fabric_config.py   # Discover Fabric IDs → write to azure_config.env
│   ├── collect_fabric_agents.py    # Discover Fabric Data Agent IDs → azure_config.env
│   ├── provision_agents.py     # Create all 5 Foundry agents (orchestrator + 4 sub-agents)
│   ├── test_orchestrator.py    # CLI test — stream orchestrator run with metadata
│   ├── test_fabric_agent.py    # CLI test — query a single Fabric Data Agent
│   ├── check_status.py         # Inspect Fabric workspace items and job status
│   └── agent_ids.json          # Output: provisioned agent IDs
│
├── api/                        # FastAPI backend
│   ├── pyproject.toml          # Python deps (fastapi, sse-starlette, mcp, azure SDKs)
│   └── app/
│       ├── main.py             # App factory, CORS, router mounts
│       ├── routers/
│       │   ├── alert.py        # POST /api/alert → SSE stream of orchestrator steps
│       │   └── agents.py       # GET /api/agents → list of agent metadata
│       └── mcp/
│           └── server.py       # FastMCP tool stubs (query_eventhouse, search_tickets, …)
│
├── frontend/                   # React SPA
│   ├── package.json
│   ├── vite.config.ts          # Dev server :5173, proxies /api → :8000
│   ├── tailwind.config.js      # Full colour system (brand, neutral, status)
│   ├── index.html
│   └── src/
│       ├── main.tsx            # React 18 entry
│       ├── App.tsx             # Alert input → SSE consumer → step timeline → diagnosis
│       └── styles/globals.css  # CSS custom properties, glass utilities, dark theme
│
└── deprecated/                 # Archived code (not used)
```

---

## Architectural Decisions

### FastAPI over Azure Functions

| Concern | Azure Functions | FastAPI |
|---------|-----------------|---------|
| SSE streaming | Not native; requires Durable Functions workarounds | `StreamingResponse` / `sse-starlette` native |
| Orchestrator timeout | 230 s max (Consumption), needs Durable for longer | No limit (process stays alive) |
| MCP server hosting | Separate deployment or complex setup | FastMCP mounts directly on the ASGI app |
| Cold start | Yes (Consumption plan) | Container Apps: scales to zero, minimal cold start |
| Single codebase | Separate Function App project | REST + MCP + SSE all in one process |

**Decision:** FastAPI on Azure Container Apps. Single Python process serves the REST
API, SSE streaming, and MCP tools. No cold-start penalty with min-replicas=1.

### Single `azure_config.env` for all config

A single dotenv file is the source of truth for every part of the system:
infrastructure, scripts, API, and (via proxy) frontend. Avoids config drift between
layers. The `preprovision.sh` hook syncs selected values into `azd env` so Bicep
can read them via `readEnvironmentVariable()`. The `postprovision.sh` hook writes
deployment outputs back into the same file.

### Shared `scripts/_config.py`

All provisioning scripts import from a single module rather than each defining
`FABRIC_API`, `FABRIC_SCOPE`, credential helpers, and path constants locally.
Changes to API URLs, OAuth scopes, or default resource names propagate everywhere
from one file.

### Agent architecture: Connected Agents pattern

The orchestrator doesn't call external APIs directly. It delegates to four
sub-agents via Foundry's `ConnectedAgentTool`. Each sub-agent is scoped to one
data source and has its own system prompt. This keeps each agent focused and
testable independently.

Fabric data access uses `FabricTool` — the agent SDK's native mechanism for
querying Fabric Data Agents (Lakehouse ontology, Eventhouse KQL).

### SSE event protocol

The API streams structured SSE events to the frontend. Event types:

| Event | Payload | Purpose |
|-------|---------|---------|
| `run_start` | `{run_id, alert, timestamp}` | Signals diagnosis began |
| `step_start` | `{step, agent}` | Agent invocation starting |
| `step_complete` | `{step, agent, duration, query, response}` | Agent returned; includes I/O |
| `message` | `{text}` | Final diagnosis (markdown) |
| `run_complete` | `{steps, tokens, time}` | Run finished; summary stats |

### Frontend design system

Dark theme following the `frontend-ui-dark-ts` skill specification:
- CSS custom properties for all colours (`--brand`, `--bg-*`, `--text-*`, `--status-*`)
- Glass morphism utilities: `glass-card`, `glass-panel`, `glass-input`, `glass-overlay`
- Framer Motion for all transitions: `AnimatePresence`, stagger containers, spring-physics buttons
- `clsx` for conditional class composition
- `focus-visible` ring styles for keyboard accessibility

### Infrastructure as Code

Subscription-scoped Bicep deployment via `azd up`. The parameter file reads from
environment variables (synced from `azure_config.env` by `preprovision.sh`).
Resources use a deterministic `resourceToken` derived from subscription + env name +
location, so names are globally unique and reproducible.

Modules: `ai-foundry` (Foundry account + project + GPT deployment), `search`,
`storage` (account + containers), `fabric` (capacity), `roles` (RBAC for user +
service principals).

---

## Configuration Signpost

All runtime configuration lives in `azure_config.env`. The template
(`azure_config.env.template`) documents every variable, its purpose, and whether
it's user-set or auto-populated.

### Variable groups and which system layers consume them

| Variable | Set by | Consumed by |
|----------|--------|-------------|
| **Core Azure** | | |
| `AZURE_SUBSCRIPTION_ID` | postprovision | scripts |
| `AZURE_RESOURCE_GROUP` | postprovision | scripts |
| `AZURE_LOCATION` | user | preprovision → Bicep |
| **AI Foundry** | | |
| `AI_FOUNDRY_NAME` | postprovision | scripts |
| `AI_FOUNDRY_ENDPOINT` | postprovision | scripts |
| `AI_FOUNDRY_PROJECT_NAME` | postprovision | scripts |
| `PROJECT_ENDPOINT` | postprovision | scripts (provision_agents, test_orchestrator) |
| **Model deployments** | | |
| `MODEL_DEPLOYMENT_NAME` | user | scripts (provision_agents), Bicep |
| `EMBEDDING_MODEL` | user | scripts (create_*_indexer) |
| `EMBEDDING_DIMENSIONS` | user | scripts (create_*_indexer) |
| `GPT_CAPACITY_1K_TPM` | user | preprovision → Bicep |
| **AI Search** | | |
| `AI_SEARCH_NAME` | postprovision | scripts (create_*_indexer) |
| `RUNBOOKS_INDEX_NAME` | user | scripts (create_runbook_indexer), API (MCP) |
| `TICKETS_INDEX_NAME` | user | scripts (create_tickets_indexer), API (MCP) |
| **Storage** | | |
| `STORAGE_ACCOUNT_NAME` | postprovision | scripts |
| `RUNBOOKS_CONTAINER_NAME` | user | scripts, must match Bicep container name |
| `TICKETS_CONTAINER_NAME` | user | scripts, must match Bicep container name |
| **Fabric API** | | |
| `FABRIC_API_URL` | user (default ok) | scripts/_config.py → all scripts |
| `FABRIC_SCOPE` | user (default ok) | scripts/_config.py → all scripts |
| **App / CORS** | | |
| `CORS_ORIGINS` | user | API (main.py CORS middleware) |
| **Fabric deployment** | | |
| `FABRIC_SKU` | user | preprovision → Bicep |
| `AZURE_FABRIC_ADMIN` | user | preprovision → Bicep |
| **Fabric resource names** | | |
| `FABRIC_WORKSPACE_NAME` | user | scripts (provision_lakehouse, populate_fabric_config) |
| `FABRIC_LAKEHOUSE_NAME` | user | scripts/_config.py → provision_lakehouse |
| `FABRIC_EVENTHOUSE_NAME` | user | scripts/_config.py → provision_eventhouse |
| `FABRIC_KQL_DB_DEFAULT` | user | scripts (provision_eventhouse) |
| `FABRIC_ONTOLOGY_NAME` | user | scripts/_config.py → provision_ontology |
| **Fabric IDs** | | |
| `FABRIC_CAPACITY_ID` | populate_fabric_config | scripts (provision_lakehouse, provision_eventhouse) |
| `FABRIC_WORKSPACE_ID` | populate_fabric_config | scripts/_config.py → all Fabric scripts |
| `FABRIC_LAKEHOUSE_ID` | populate_fabric_config | scripts (provision_ontology) |
| `FABRIC_EVENTHOUSE_ID` | populate_fabric_config | scripts (provision_eventhouse) |
| `FABRIC_KQL_DB_ID` | populate_fabric_config | scripts |
| `FABRIC_KQL_DB_NAME` | populate_fabric_config | scripts/_config.py |
| `EVENTHOUSE_QUERY_URI` | populate_fabric_config | scripts (provision_eventhouse — Kusto ingestion) |
| **Fabric Data Agents** | | |
| `GRAPH_DATA_AGENT_ID` | collect_fabric_agents | scripts (provision_agents) |
| `TELEMETRY_DATA_AGENT_ID` | collect_fabric_agents | scripts (provision_agents) |
| `FABRIC_DATA_AGENT_API_VERSION` | user (default ok) | scripts (test_fabric_agent) |
| **Fabric connections** | | |
| `GRAPH_FABRIC_CONNECTION_NAME` | user (manual) | scripts (provision_agents) |
| `TELEMETRY_FABRIC_CONNECTION_NAME` | user (manual) | scripts (provision_agents) |

### Config files beyond azure_config.env

| File | Purpose | Consumed by |
|------|---------|-------------|
| `azure.yaml` | azd project definition: hook paths, service targets | azd CLI |
| `pyproject.toml` (root) | Python deps for scripts/ | uv (scripts) |
| `api/pyproject.toml` | Python deps for API | uv (api) |
| `frontend/package.json` | Node deps for frontend | npm |
| `frontend/vite.config.ts` | Dev server port, `/api` proxy target | Vite |
| `frontend/tailwind.config.js` | Colour system, fonts | Tailwind CSS |
| `infra/main.bicepparam` | Bicep parameter values (reads env vars) | azd/Bicep |
| `scripts/agent_ids.json` | Provisioned Foundry agent IDs | scripts (test_orchestrator) |
| `data/prompts/*.md` | System prompts for each agent | scripts (provision_agents) |

---

## Data Flow

### Provisioning pipeline (one-time setup)

```
azure_config.env → preprovision.sh → azd up (Bicep) → postprovision.sh → azure_config.env
                                                        ├─ uploads runbooks/ → blob → create_runbook_indexer.py → AI Search
                                                        └─ uploads tickets/  → blob → create_tickets_indexer.py → AI Search
provision_lakehouse.py ─── CSV topology data ──────────▶ Fabric Lakehouse
provision_eventhouse.py ── CSV telemetry data ─────────▶ Fabric Eventhouse (KQL)
provision_ontology.py ──── ontology definition ────────▶ Fabric Ontology (graph index)
populate_fabric_config.py ── discovers IDs ────────────▶ azure_config.env
collect_fabric_agents.py ── discovers agent IDs ───────▶ azure_config.env
provision_agents.py ──── creates 5 Foundry agents ─────▶ agent_ids.json
```

### Runtime flow (per alert)

```
User types alert → Frontend POST /api/alert
  → FastAPI receives AlertRequest
  → Creates orchestrator thread + run (azure-ai-agents SDK)
  → OrchestratorEventHandler streams AgentEvents
  → Each sub-agent invocation yields SSE events
  → Frontend parses SSE, renders step timeline
  → Final diagnosis rendered as markdown
```

---

## Deployment Targets

| Component | Local | Production |
|-----------|-------|------------|
| API | `uvicorn :8000` | Azure Container Apps |
| Frontend | Vite dev server `:5173` | Azure Static Web Apps |
| Infra | n/a | `azd up` → Azure |

Production deployment config is stubbed in `azure.yaml` (commented-out `services` block).
CORS_ORIGINS must be updated to the production frontend URL before deploying.

---

## SDK Versions

| Package | Version | Notes |
|---------|---------|-------|
| `azure-ai-projects` | `>=1.0.0,<2.0.0` | v2 has breaking API changes |
| `azure-ai-agents` | `1.2.0b6` | Required for `FabricTool`, `ConnectedAgentTool` |
| `fastapi` | `>=0.115` | ASGI framework |
| `sse-starlette` | `>=2.0` | SSE responses |
| `mcp[cli]` | `>=1.9.0` | FastMCP server framework |
| `react` | `18.x` | UI library |
| `framer-motion` | `11.x` | Animation |
| `tailwindcss` | `3.x` | Utility-first CSS |
