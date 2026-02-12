# Architecture

## Demo built with assistance from Claude Opus 4.6 using the following [skills](https://github.com/microsoft/skills):
* azure-ai-projects-py — `~/references/skills/.github/skills/azure-ai-projects-py`
* hosted-agents-v2-py — `~/references/skills/.github/skills/hosted-agents-v2-py`
* mcp-builder — `~/references/skills/.github/skills/mcp-builder`
* azure-appconfiguration-py — `~/references/skills/.github/skills/azure-appconfiguration-py`
* azure-containerregistry-py — `~/references/skills/.github/skills/azure-containerregistry-py`
* fastapi-router-py (training data, no local reference)
* frontend-ui-dark-ts (training data, no local reference)

---

## System Overview

Multi-agent NOC diagnosis system. An alert enters via the frontend, flows through
a FastAPI backend that streams SSE progress, and reaches an orchestrator agent in
Azure AI Foundry. The orchestrator delegates to four specialist agents, each backed
by a distinct data source in Microsoft Fabric or Azure AI Search.

Three deployable services:
- **API** (port 8000) — FastAPI backend, orchestrator bridge, SSE streaming
- **fabric-query-api** (port 8100) — Graph & telemetry microservice with backend-agnostic graph abstraction
- **Frontend** (port 5173) — React/Vite NOC dashboard

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
                       │ OpenApiTool       │ OpenApiTool     │ AI Search         │ AI Search
                       ▼                    ▼                ▼                   ▼
              ┌──────────────────┐   ┌──────────────────┐  ┌──────────────┐  ┌──────────────────┐
              │ fabric-query-api │   │ fabric-query-api │  │ runbooks-    │  │ tickets-         │
              │ POST /query/     │   │ POST /query/     │  │ index        │  │ index            │
              │ graph            │   │ telemetry (KQL)  │  │ (hybrid)     │  │ (hybrid)         │
              └────────┬─────────┘   └────────┬─────────┘  └──────────────┘  └──────────────────┘
                       │ dispatches           │
                       ▼ via GRAPH_BACKEND    ▼
              ┌──────────────────┐   ┌───────────────┐
              │  Backend layer   │   │ Fabric        │
              │  ┌─ fabric.py   │   │ Eventhouse    │
              │  ├─ cosmosdb.py │   │ (KQL/Kusto)   │
              │  └─ mock.py     │   └───────────────┘
              └──────────────────┘
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
│       ├── container-apps-environment.bicep  # Log Analytics + ACR + Managed Environment
│       ├── container-app.bicep              # Generic Container App (managed identity)
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
│   ├── prompts/                # Agent system prompts — see "Agent Prompt Architecture"
│   │   ├── foundry_orchestrator_agent.md
│   │   ├── foundry_telemetry_agent_v2.md
│   │   ├── foundry_runbook_kb_agent.md
│   │   ├── foundry_historical_ticket_agent.md
│   │   ├── alert_storm.md
│   │   ├── graph_explorer/     # Decomposed GraphExplorer prompt (backend-agnostic)
│   │   │   ├── core_instructions.md   # Role, rules, scope boundaries
│   │   │   ├── core_schema.md         # Entity/relationship schema (all backends)
│   │   │   ├── language_gql.md        # GQL syntax, examples (Fabric)
│   │   │   ├── language_gremlin.md    # Gremlin syntax, examples (Cosmos DB)
│   │   │   ├── language_mock.md       # Natural language (offline demos)
│   │   │   └── description.md         # Agent description one-liner
│   │   └── deprecated/         # Previous monolithic prompts
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
│   ├── assign_fabric_role.py   # Grant Container App identity Fabric workspace access
│   ├── agent_ids.json          # Output: provisioned agent IDs
│   └── testing_scripts/        # CLI test & debug utilities
│       ├── test_orchestrator.py    # Stream orchestrator run with metadata
│       ├── test_fabric_agent.py    # Query a single Fabric Data Agent
│       ├── test_gql_query.py       # GQL queries against Fabric GraphModel API
│       ├── test_kql_query.py       # KQL queries against Fabric Eventhouse
│       ├── test_fabric_query_api.py # Deployment smoke test for fabric-query-api
│       ├── test_function_tool.py   # PoC — Foundry agent with FunctionTool (archived)
│       └── check_status.py         # Inspect Fabric workspace items and job status
│
├── api/                        # FastAPI backend (NOC API)
│   ├── pyproject.toml          # Python deps (fastapi, sse-starlette, mcp, azure SDKs)
│   └── app/
│       ├── main.py             # App factory, CORS, router mounts, /health
│       ├── orchestrator.py     # Foundry agent bridge — sync SDK → async SSE with retry
│       ├── routers/
│       │   ├── alert.py        # POST /api/alert → SSE stream of orchestrator steps
│       │   ├── agents.py       # GET /api/agents → list of agent metadata
│       │   └── logs.py         # GET /api/logs + /api/fabric-logs → SSE log streams
│       └── mcp/
│           └── server.py       # FastMCP tool stubs (query_eventhouse, search_tickets, …)
│
├── fabric-query-api/           # Graph & telemetry microservice — V4 architecture
│   ├── main.py                 # Slim app factory: middleware, health, log SSE, router mounts
│   ├── config.py               # GRAPH_BACKEND enum, env var loading, credential
│   ├── models.py               # Pydantic request/response models (shared across backends)
│   ├── router_graph.py         # POST /query/graph — dispatches to backend via Protocol
│   ├── router_telemetry.py     # POST /query/telemetry — KQL via Kusto SDK
│   ├── backends/               # Backend abstraction layer (V4)
│   │   ├── __init__.py         # GraphBackend Protocol + get_backend() factory
│   │   ├── fabric.py           # Fabric GraphModel GQL via REST API (production)
│   │   ├── cosmosdb.py         # Cosmos DB Gremlin placeholder (raises NotImplementedError)
│   │   └── mock.py             # Static topology responses (offline demos)
│   ├── openapi/                # Per-backend OpenAPI specs for Foundry OpenApiTool
│   │   ├── fabric.yaml         # GQL description, workspace_id/graph_model_id params
│   │   ├── cosmosdb.yaml       # Gremlin description, no Fabric-specific params
│   │   └── mock.yaml           # Generic description
│   ├── pyproject.toml          # Python deps (fastapi, uvicorn, azure-identity, azure-kusto-data)
│   └── Dockerfile              # python:3.11-slim, uv for deps, port 8100
│
├── frontend/                   # React SPA — NOC Dashboard
│   ├── package.json
│   ├── vite.config.ts          # Dev server :5173, proxies /api + SSE routes → :8000
│   ├── tailwind.config.js      # Full colour system (brand, neutral, status)
│   ├── index.html
│   └── src/
│       ├── main.tsx            # React 18 entry
│       ├── App.tsx             # Layout shell — three-zone resizable dashboard
│       ├── types/index.ts      # StepEvent, ThinkingState, RunMeta
│       ├── hooks/
│       │   └── useInvestigation.ts   # SSE connection + all investigation state
│       ├── components/
│       │   ├── Header.tsx            # Branding + HealthDot + "5 Agents" indicator
│       │   ├── MetricsBar.tsx        # PanelGroup with 7 resizable panels
│       │   ├── MetricCard.tsx        # KPI display (hardcoded for demo)
│       │   ├── AlertChart.tsx        # Static anomaly detection chart image
│       │   ├── LogStream.tsx         # Generic SSE log viewer (url + title props)
│       │   ├── InvestigationPanel.tsx # Left panel: alert input + agent timeline
│       │   ├── AlertInput.tsx        # Textarea + submit button
│       │   ├── AgentTimeline.tsx     # Step list + thinking dots + run-complete footer
│       │   ├── StepCard.tsx          # Collapsible step with query/response expand
│       │   ├── ThinkingDots.tsx      # Bouncing dots indicator
│       │   ├── ErrorBanner.tsx       # Contextual error messages + retry
│       │   ├── DiagnosisPanel.tsx    # Right panel: empty → loading → markdown
│       │   └── HealthDot.tsx         # API health check indicator
│       └── styles/
│           └── globals.css           # CSS custom properties, glass utilities, dark theme
│
├── documentation/              # Architecture docs, design specs, scenario description
│   ├── ARCHITECTURE.md         # This file
│   ├── SCENARIO.md             # Demo scenario description
│   ├── V4GRAPH.md              # V4 graph model design spec
│   ├── VUNKAGENTRETHINK.md     # Agent architecture rethink notes
│   └── previous_dev_phases/    # Archived design docs (V2, V3)
│
└── .github/
    └── copilot-instructions.md # Copilot context for this project
```

---

## fabric-query-api — V4 Backend-Agnostic Architecture

The most architecturally significant service. A FastAPI microservice that provides
two endpoints — `/query/graph` and `/query/telemetry` — consumed by Foundry agents
via `OpenApiTool`. Runs as a Container App in production, authenticated via
system-assigned managed identity.

### Design Principle

Agents don't know or care which graph database backs `/query/graph`. They send a
query string and get back `{columns, data}`. The **query language** changes per
backend (GQL, Gremlin, natural language), but the **API contract** is identical.
A single environment variable controls the backend:

```bash
GRAPH_BACKEND=fabric          # Options: "fabric" | "cosmosdb" | "mock"
```

### Module Breakdown

#### `config.py` — Centralised Configuration

- `GraphBackendType` enum: `FABRIC`, `COSMOSDB`, `MOCK`
- Reads all env vars once: Fabric API URLs, workspace/model IDs, Eventhouse URIs,
  Cosmos DB connection strings
- Exports shared `credential = DefaultAzureCredential()`
- `BACKEND_REQUIRED_VARS` dict validates that each backend has its required env vars

#### `models.py` — Shared Request/Response Models

| Model | Fields | Notes |
|-------|--------|-------|
| `GraphQueryRequest` | `query`, optional `workspace_id`, `graph_model_id` | Fabric params optional — defaults from env |
| `GraphQueryResponse` | `columns=[]`, `data=[]`, `error: str \| None` | Error field enables LLM self-repair |
| `TelemetryQueryRequest` | `query`, optional `eventhouse_query_uri`, `kql_db_name` | |
| `TelemetryQueryResponse` | `columns=[]`, `rows=[]`, `error: str \| None` | Same error pattern |

The `error` field is key to error resilience — see [Error Resilience](#error-resilience).

#### `router_graph.py` — Graph Query Dispatch

- `POST /query/graph` — dispatches to the active `GraphBackend`
- Lazy-initialised backend singleton via `get_graph_backend()`
- All exceptions (`HTTPException`, `NotImplementedError`, generic) are caught and
  returned as **HTTP 200 with `error` in the response body**
- Backend is closed on app shutdown via `close_graph_backend()`

#### `router_telemetry.py` — KQL Queries

- `POST /query/telemetry` — KQL queries against Fabric Eventhouse
- Thread-safe cached `KustoClient` (recreated if URI changes)
- Sync KQL execution wrapped in `asyncio.to_thread()` 
- `KustoServiceError` caught → 200 + error payload (not HTTP 400)
- Auto-serialises `datetime` values via `.isoformat()`

#### `backends/` — Protocol + Implementations

```python
class GraphBackend(Protocol):
    async def execute_query(self, query: str, **kwargs) -> dict: ...
    def close(self) -> None: ...
```

`get_backend()` factory returns the correct implementation based on `GRAPH_BACKEND`:

| Backend | Implementation | Query Language | Status |
|---------|---------------|----------------|--------|
| `fabric` | `FabricGraphBackend` | GQL | Production — Fabric GraphModel REST API |
| `cosmosdb` | `CosmosDBGremlinBackend` | Gremlin | Placeholder — raises `NotImplementedError` |
| `mock` | `MockGraphBackend` | Natural language | Working — static topology data |

**`backends/fabric.py`** is the most complex:
- `_execute_gql()` — async `httpx` POST to `/workspaces/{ws}/GraphModels/{gm}/executeQuery`
- **429 retry** — up to 3 attempts, parses `Retry-After` header or Fabric's JSON body
  timestamp, minimum delay 10s × attempt number (exponential backoff)
- Detects Fabric's "HTTP 200 but GQL logical error" pattern (raises `HTTPException`)
- Bearer auth via `credential.get_token(FABRIC_SCOPE)`

**`backends/mock.py`** — Pattern-matches query strings for entity types ("corerouter",
"transportlink", etc.) and returns canned topology data. Useful for offline demos
without Fabric connectivity.

#### `main.py` — Slim App Factory

~211 lines. Responsibilities:
- FastAPI app with lifespan handler (validates env vars at startup)
- CORS middleware for localhost dev
- HTTP request logging middleware with timing
- SSE log broadcasting (asyncio.Queue subscribers + deque buffer, max 100 lines)
- Mounts `router_graph` and `router_telemetry`
- `GET /health` with backend type and version
- `GET /api/logs` SSE stream

#### Per-Backend OpenAPI Specs

Three standalone OpenAPI 3.0.3 specs in `openapi/`, each consumed by Foundry's
`OpenApiTool` when provisioning agents:

| Spec | `/query/graph` description | Fabric-specific params |
|------|---------------------------|----------------------|
| `fabric.yaml` | GQL query language, GQL examples | `workspace_id`, `graph_model_id` |
| `cosmosdb.yaml` | Gremlin query language, Gremlin examples | None (server-side config) |
| `mock.yaml` | Generic "send any query string" | None |

All specs share the same `/query/telemetry` definition (KQL, unchanged across backends).
Each 200 response schema includes an `error` field (nullable string) with a description
instructing the LLM to read the error and retry with corrected syntax.

`provision_agents.py` selects the correct spec at provisioning time based on
`GRAPH_BACKEND`.

---

## API Service — Orchestrator Bridge

The API (`api/`) bridges the synchronous Azure AI Agents SDK to the async SSE-based
frontend. It does **not** query Fabric or any data source directly — all data access
flows through the Foundry agents.

### `orchestrator.py` — Foundry → SSE Bridge

The most complex module in the API. Architecture:

```
submitAlert() ─────────┐
                        ▼
              ┌─────────────────────────┐
              │  Background thread      │
              │  ├─ Create thread       │
              │  ├─ Create run          │◀── Retry loop (MAX_RUN_ATTEMPTS=2)
              │  ├─ Stream events       │
              │  │  ├─ on_thread_run    │──→ tracks run_failed status
              │  │  ├─ on_run_step      │──→ emits step_start/step_complete
              │  │  └─ on_message_done  │──→ emits final message
              │  └─ On failure: post    │
              │     recovery message    │
              │     and retry           │
              └──────────┬──────────────┘
                         │ asyncio.Queue
                         ▼
              ┌─────────────────────────┐
              │  Async SSE generator    │
              │  yields EventSourceResponse
              └─────────────────────────┘
```

Key design patterns:

1. **Thread bridging**: Foundry's `AgentEventHandler` is synchronous (callbacks).
   The orchestrator runs it in a daemon thread and pushes SSE event dicts to an
   `asyncio.Queue`. The async generator yields from the queue for Starlette's
   `EventSourceResponse`.

2. **Run retry with recovery** (`MAX_RUN_ATTEMPTS = 2`): If a run fails (e.g.,
   sub-agent tool error), the handler sets `run_failed = True` instead of
   immediately emitting an SSE error. The retry loop posts a recovery message to
   the thread ("The previous investigation attempt failed with: {detail}. Please
   retry...") and creates a new run on the same thread. Only emits an SSE error
   on the final failed attempt.

3. **Fabric log emission**: Synthesises fabric-query-api log events for Graph and
   Telemetry agent tool calls. The frontend displays these in the "Fabric Logs"
   LogStream panel even though fabric-query-api runs remotely.

4. **Configuration check**: `is_configured()` validates that `agent_ids.json`
   exists and required env vars (`PROJECT_ENDPOINT`, `AI_FOUNDRY_PROJECT_NAME`)
   are set. If not configured, the alert endpoint falls back to a stub generator
   with synthetic 4-agent walkthrough events.

### Router Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/alert` | POST | Accept alert text, return SSE stream of investigation |
| `/api/agents` | GET | Return list of provisioned agents from `agent_ids.json` |
| `/api/logs` | GET | SSE stream of API process logs (app.*, azure.*, uvicorn) |
| `/api/fabric-logs` | GET | SSE stream of synthetic fabric-query-api logs |
| `/health` | GET | Health check |

---

## Agent Architecture

### Connected Agents Pattern

Five Foundry agents, each scoped to one responsibility:

| Agent | Role | Data Source | Tool Type |
|-------|------|-------------|-----------|
| **Orchestrator** | Supervisor — coordinates investigation, synthesises diagnosis | — | `ConnectedAgentTool` → 4 sub-agents |
| **GraphExplorerAgent** | Topology & dependency analysis (forward/reverse trace) | Fabric GraphModel (GQL) | `OpenApiTool` → `/query/graph` |
| **TelemetryAgent** | Raw telemetry & alert retrieval | Fabric Eventhouse (KQL) | `OpenApiTool` → `/query/telemetry` |
| **RunbookKBAgent** | Procedure lookup (SOPs, diagnostics, escalation) | AI Search `runbooks-index` | `AzureAISearchTool` |
| **HistoricalTicketAgent** | Precedent search (past incidents, resolution patterns) | AI Search `tickets-index` | `AzureAISearchTool` |

The orchestrator never accesses data directly. It delegates to sub-agents via
`ConnectedAgentTool`, which creates a child thread + run on the sub-agent. Each
sub-agent has its own system prompt, tool configuration, and data scope.

### Agent Prompt Architecture

The GraphExplorerAgent prompt is **decomposed into composable parts** and assembled
at provisioning time based on `GRAPH_BACKEND`:

```
data/prompts/graph_explorer/
├── core_instructions.md    ← Role, rules, scope (backend-agnostic)
├── core_schema.md          ← 8 entity types, 7 relationship types, instances
├── language_gql.md         ← GQL syntax, MATCH patterns, examples (Fabric)
├── language_gremlin.md     ← Gremlin traversals, g.V() patterns (Cosmos DB)
├── language_mock.md        ← Natural language instructions (offline)
└── description.md          ← Agent description one-liner
```

`provision_agents.py` composes the full prompt:

```python
LANGUAGE_FILE_MAP = {
    "fabric": "language_gql.md",
    "cosmosdb": "language_gremlin.md",
    "mock": "language_mock.md",
}

def load_graph_explorer_prompt() -> str:
    parts = [core_instructions, core_schema, language_file]
    return "\n\n---\n\n".join(parts)
```

All other agent prompts remain monolithic (single `.md` file) as they are
backend-agnostic.

### Backend-Aware Provisioning

`provision_agents.py` adjusts three things based on `GRAPH_BACKEND`:

1. **OpenAPI spec** — selects `openapi/{backend}.yaml`
2. **GraphExplorer prompt** — assembles from `graph_explorer/` parts with the
   correct language file
3. **Tool description** — backend-specific one-liner ("Execute a GQL query..." /
   "Execute a Gremlin query..." / "Query the topology graph...")

### Investigation Flows

The orchestrator prompt defines two investigation strategies:

- **Flow A** (known infrastructure trigger) — forward trace from cause to impact:
  infrastructure failure → affected paths → affected services → SLA exposure
- **Flow B** (alert storm / service symptoms) — backward trace from symptoms to
  root cause: service alerts → dependency chains → common infrastructure ancestor

The orchestrator autonomously selects the appropriate flow based on the alert content.

---

## Error Resilience

A three-layer defence against sub-agent tool failures, designed to prevent a single
failed tool call from terminating the entire investigation.

### The Problem

Foundry's `OpenApiTool` treats HTTP 4xx/5xx responses as fatal:

```
HTTP 400 from fabric-query-api
  → Foundry: tool_server_error (sub-agent run step fails)
  → Sub-agent run status = "failed"
  → ConnectedAgentTool returns failure to orchestrator
  → Orchestrator run status = "failed"
  → Entire investigation terminates
```

The orchestrator LLM **never sees** the error message. It cannot retry or adapt.

### Layer 1: Errors as 200 + Error Payload (Most Impactful)

Both `router_graph.py` and `router_telemetry.py` now catch **all** exceptions and
return HTTP 200 with the error message in the response body:

```json
{
  "columns": [],
  "data": [],
  "error": "KQL query error: Column 'nonexistent' not found. Please check column names and retry."
}
```

The sub-agent LLM sees the error in the tool response, reads it, and can self-correct.
The TelemetryAgent prompt already has a rule: "If a query returns an error, read the
error message and fix the query. Retry with corrected syntax."

The OpenAPI specs include the `error` field in their 200 response schemas with a
description that instructs the LLM: "If this field is present, the query failed.
Read the error, fix your query, and try again."

### Layer 2: Orchestrator Run Retry (Safety Net)

If a run still fails despite Layer 1 (e.g., transient Foundry platform error),
`orchestrator.py` retries:

- `MAX_RUN_ATTEMPTS = 2`
- On failure: posts a recovery message to the existing thread with error details
  and instructions to retry
- Creates a new run on the same thread (preserving conversation context)
- Only emits SSE error event to the frontend on the final failed attempt

### Layer 3: Graceful Degradation (Orchestrator Prompt)

Rule #8 in the orchestrator system prompt:

> **Handle sub-agent failures gracefully.** If a sub-agent call fails or returns
> an error response, do NOT terminate the investigation. Instead: note which data
> source was unavailable, continue with remaining agents, produce a situation
> report even if incomplete.

This ensures even if one data source is entirely down, the investigation continues
with the remaining agents and produces a partial but useful report.

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

### Single `azure_config.env` for All Config

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

### Connected Agents over Direct Tool Calls

The orchestrator doesn't call external APIs directly. It delegates to four
sub-agents via Foundry's `ConnectedAgentTool`. Each sub-agent is scoped to one
data source and has its own system prompt. This keeps each agent focused and
testable independently.

### OpenApiTool + fabric-query-api over FabricTool

GraphExplorerAgent and TelemetryAgent access Microsoft Fabric through a dedicated
Container App micro-service (`fabric-query-api`) rather than the Fabric Data Agent
(`FabricTool`). This change was driven by a key constraint: `ConnectedAgentTool`
sub-agents run server-side on Foundry and cannot execute client-side `FunctionTool`
callbacks. `OpenApiTool` makes server-side REST calls, so it works natively.

**Why not FabricTool?** FabricTool requires a Fabric Data Agent connected as a
"Connected Resource" in AI Foundry — a manual portal step that cannot be automated.
It also only supports delegated user identities, not managed identities. The
OpenApiTool approach eliminates both limitations and provides full control over
query construction (GQL/KQL) and error handling (429 retry, errors-as-200, etc.).

### Backend-Agnostic Graph Abstraction (V4)

The graph endpoint (`/query/graph`) is decoupled from any specific graph database
via a `GraphBackend` Protocol. Switching backends requires only changing
`GRAPH_BACKEND` env var and re-provisioning agents. No code changes to the agent
layer, API, or frontend. See `documentation/V4GRAPH.md` for the full design spec.

### Fabric Identity and Role Assignment

The `fabric-query-api` Container App authenticates to the Fabric REST API using
its system-assigned managed identity (via `DefaultAzureCredential`). For this to
work, the identity must be a member of the Fabric workspace.

`scripts/assign_fabric_role.py` automates this:
1. Reads `FABRIC_WORKSPACE_ID` and `FABRIC_QUERY_API_PRINCIPAL_ID` from `azure_config.env`
2. Calls `GET /v1/workspaces/{id}/roleAssignments` to check if the principal already has a role
3. If not, calls `POST /v1/workspaces/{id}/roleAssignments` to add it as **Contributor**

The script is idempotent — re-running it skips if the assignment already exists.
It must run after both `azd up` (which creates the Container App identity) and
`provision_lakehouse.py` (which creates the Fabric workspace).

---

## SSE Event Protocol

The API streams structured SSE events to the frontend. Event types:

| Event | Payload | Purpose |
|-------|---------|---------|
| `run_start` | `{run_id, alert, timestamp}` | Signals diagnosis began |
| `step_thinking` | `{agent, status}` | Agent is working (shows thinking dots) |
| `step_start` | `{step, agent}` | Agent invocation starting |
| `step_complete` | `{step, agent, duration, query, response, error?}` | Agent returned; includes I/O. `error: true` on failure |
| `message` | `{text}` | Final diagnosis (markdown) |
| `error` | `{message}` | Run-level error (agent failure, timeout, etc.) |
| `run_complete` | `{steps, tokens, time}` | Run finished; summary stats |

---

## Frontend Architecture — V4 NOC Dashboard

Dark theme component-based three-zone dashboard with vertically and horizontally
resizable panels. Built with React 18, Vite, Tailwind CSS, and Framer Motion.

### Design System

- CSS custom properties for all colours (`--brand`, `--bg-*`, `--text-*`, `--status-*`)
- Glass morphism utilities: `glass-card`, `glass-panel`, `glass-input`, `glass-overlay`
- Framer Motion for all transitions: `AnimatePresence`, stagger containers, spring-physics buttons
- `clsx` for conditional class composition
- `focus-visible` ring styles for keyboard accessibility

### Layout Structure

(`h-screen flex flex-col`, no page scroll):

```
┌──────────────────────────────────────────────────────────────────────┐
│  Header          (h-12, fixed)                              Zone 1  │
├──────────────────────────────────────────────────────────────────────┤
│  MetricsBar      (resizable height, default 30%)            Zone 2  │
│  [KPI] [KPI] [KPI] [KPI] [AlertChart] [API Logs] [Fabric Logs]     │
│  ←──── resizable panels (react-resizable-panels) ────→              │
├═══════════════════════════ vertical drag handle ═════════════════════┤
│                  (resizable height, default 70%)            Zone 3  │
│  ┌────────────────────────┬─────────────────────────────────┐       │
│  │  InvestigationPanel    │  DiagnosisPanel                 │       │
│  │  (w-1/2, scroll-y)    │  (w-1/2, scroll-y)              │       │
│  │  AlertInput            │  Empty → Loading → Markdown     │       │
│  │  AgentTimeline         │                                 │       │
│  │  ErrorBanner           │                                 │       │
│  └────────────────────────┴─────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────────────┘
```

Zone 2 and Zone 3 are vertically resizable via a `PanelGroup` with
`orientation="vertical"`. Users can drag the handle between them to
allocate more space to metrics or investigation.

### State Management

All SSE state lives in `useInvestigation()` custom hook. The hook returns
`{ alert, setAlert, steps, thinking, finalMessage, errorMessage, running,
runStarted, runMeta, submitAlert }`. `App.tsx` calls the hook and passes
props down. Both panels read from the same hook instance. The hook uses
`@microsoft/fetch-event-source` to issue POST-based SSE requests (standard
`EventSource` is GET-only).

### Live Log Streaming

Two `LogStream` components in the metrics bar display real-time backend logs via SSE:
- **API logs** (`/api/logs`) — captures `app.*`, `azure.*`, and `uvicorn` log
  output from the FastAPI process
- **Fabric logs** (`/api/fabric-logs`) — synthetic logs emitted by the orchestrator
  showing queries and responses that flow through fabric-query-api

Each LogStream supports auto-scroll, manual scroll-pause, and connection status.

### Hardcoded vs Live Data

Metrics values (12 alerts, 3 services, $115k SLA, 231 anomalies) and the alert
chart image are hardcoded for demo reliability. The investigation panel (SSE steps),
diagnosis panel (final markdown), and log streams are connected to the live backend.

---

## Infrastructure as Code

Subscription-scoped Bicep deployment via `azd up`. The parameter file reads from
environment variables (synced from `azure_config.env` by `preprovision.sh`).
Resources use a deterministic `resourceToken` derived from subscription + env name +
location, so names are globally unique and reproducible.

### Bicep Modules

| Module | Resources |
|--------|-----------|
| `ai-foundry.bicep` | AI Foundry account + project + GPT-4.1 deployment |
| `search.bicep` | Azure AI Search service |
| `storage.bicep` | Storage account + blob containers (runbooks, tickets) |
| `fabric.bicep` | Fabric capacity (F-SKU, configurable F2–F2048) |
| `container-apps-environment.bicep` | Log Analytics workspace + ACR + Managed Environment |
| `container-app.bicep` | Generic Container App template (managed identity) |
| `roles.bicep` | RBAC assignments (user + service principals) |

### Deployment: `azd up` and `azd deploy`

`azd up` runs the full infrastructure + service deployment cycle:
1. `preprovision.sh` syncs `azure_config.env` → azd environment variables
2. Bicep provisions all Azure resources (Container Apps Environment + ACR, etc.)
3. `azd deploy` builds and deploys `fabric-query-api` (Docker image built in ACR via `remoteBuild`)
4. `postprovision.sh` uploads data to blob, writes deployment outputs to `azure_config.env`

For code-only changes to `fabric-query-api`, use `azd deploy fabric-query-api`
without re-running the full `azd up`. This rebuilds the container image and
creates a new Container App revision (~60 seconds).

---

## Configuration Signpost

All runtime configuration lives in `azure_config.env`. The template
(`azure_config.env.template`) documents every variable, its purpose, and whether
it's user-set or auto-populated.

### Variable Groups

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
| **Model Deployments** | | |
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
| **Graph Backend** | | |
| `GRAPH_BACKEND` | user | fabric-query-api (config.py), provision_agents.py |
| **Fabric API** | | |
| `FABRIC_API_URL` | user (default ok) | scripts/_config.py → all scripts |
| `FABRIC_SCOPE` | user (default ok) | scripts/_config.py → all scripts |
| **Fabric Resource Names** | | |
| `FABRIC_WORKSPACE_NAME` | user | scripts (provision_lakehouse, populate_fabric_config) |
| `FABRIC_LAKEHOUSE_NAME` | user | scripts/_config.py → provision_lakehouse |
| `FABRIC_EVENTHOUSE_NAME` | user | scripts/_config.py → provision_eventhouse |
| `FABRIC_KQL_DB_DEFAULT` | user | scripts (provision_eventhouse) |
| `FABRIC_ONTOLOGY_NAME` | user | scripts/_config.py → provision_ontology |
| **Fabric IDs** (auto-populated) | | |
| `FABRIC_CAPACITY_ID` | populate_fabric_config | scripts |
| `FABRIC_WORKSPACE_ID` | populate_fabric_config | scripts, fabric-query-api |
| `FABRIC_LAKEHOUSE_ID` | populate_fabric_config | scripts (provision_ontology) |
| `FABRIC_GRAPH_MODEL_ID` | provision_ontology | fabric-query-api |
| `EVENTHOUSE_QUERY_URI` | populate_fabric_config | fabric-query-api, scripts |
| `FABRIC_KQL_DB_NAME` | populate_fabric_config | fabric-query-api |
| **fabric-query-api** | | |
| `FABRIC_QUERY_API_URI` | postprovision (azd output) | scripts (provision_agents) |
| `FABRIC_QUERY_API_PRINCIPAL_ID` | postprovision (azd output) | scripts (assign_fabric_role) |
| **Cosmos DB** (optional, when `GRAPH_BACKEND=cosmosdb`) | | |
| `COSMOS_GREMLIN_ENDPOINT` | user | fabric-query-api |
| `COSMOS_GREMLIN_PRIMARY_KEY` | user | fabric-query-api |
| `COSMOS_GREMLIN_DATABASE` | user | fabric-query-api |
| `COSMOS_GREMLIN_GRAPH` | user | fabric-query-api |
| **App / CORS** | | |
| `CORS_ORIGINS` | user | API (main.py CORS middleware) |

### Config Files Beyond azure_config.env

| File | Purpose | Consumed by |
|------|---------|-------------|
| `azure.yaml` | azd project definition: hook paths, service targets | azd CLI |
| `pyproject.toml` (root) | Python deps for scripts/ | uv (scripts) |
| `api/pyproject.toml` | Python deps for API | uv (api) |
| `fabric-query-api/pyproject.toml` | Python deps for fabric-query-api | uv (fabric-query-api) |
| `frontend/package.json` | Node deps for frontend | npm |
| `frontend/vite.config.ts` | Dev server port, `/api` proxy target | Vite |
| `frontend/tailwind.config.js` | Colour system, fonts | Tailwind CSS |
| `infra/main.bicepparam` | Bicep parameter values (reads env vars) | azd/Bicep |
| `scripts/agent_ids.json` | Provisioned Foundry agent IDs | scripts, API (orchestrator) |
| `data/prompts/*.md` | System prompts for each agent | scripts (provision_agents) |

---

## Data Flow

### Provisioning Pipeline (One-Time Setup)

```
azure_config.env → preprovision.sh → azd up (Bicep) → postprovision.sh → azure_config.env
                                       │                ├─ uploads runbooks/ → blob → create_runbook_indexer.py → AI Search
                                       │                └─ uploads tickets/  → blob → create_tickets_indexer.py → AI Search
                                       │
                                       ├─ Container Apps Environment (ACR + Log Analytics)
                                       └─ fabric-query-api Container App (deployed by azd deploy)

provision_lakehouse.py ─── CSV topology data ──────────▶ Fabric Lakehouse
provision_eventhouse.py ── CSV telemetry data ─────────▶ Fabric Eventhouse (KQL)
provision_ontology.py ──── ontology definition ────────▶ Fabric Ontology (graph index)
populate_fabric_config.py ── discovers IDs ────────────▶ azure_config.env
assign_fabric_role.py ──── grants managed identity ────▶ Fabric workspace Contributor
provision_agents.py ──── creates 5 Foundry agents ─────▶ agent_ids.json
  ├─ GraphExplorerAgent   (OpenApiTool → fabric-query-api /query/graph)
  │   └─ prompt assembled from graph_explorer/{core_instructions + core_schema + language_X}.md
  │   └─ OpenAPI spec from openapi/{GRAPH_BACKEND}.yaml
  ├─ TelemetryAgent       (OpenApiTool → fabric-query-api /query/telemetry)
  ├─ RunbookKBAgent       (AzureAISearchTool → runbooks-index)
  ├─ HistoricalTicketAgent(AzureAISearchTool → tickets-index)
  └─ Orchestrator         (ConnectedAgentTool → all 4 above)
```

### Runtime Flow (Per Alert)

```
User types alert in frontend
  → POST /api/alert {text: "..."}
  → API creates orchestrator thread + run (azure-ai-agents SDK)
  → Background thread streams AgentEvents via SSEEventHandler callbacks
  → Orchestrator delegates to sub-agents via ConnectedAgentTool:
      ├─ GraphExplorerAgent → OpenApiTool → fabric-query-api /query/graph
      │   → dispatches to backends/{GRAPH_BACKEND}.py → Fabric/Cosmos/Mock
      ├─ TelemetryAgent → OpenApiTool → fabric-query-api /query/telemetry
      │   → KustoClient → Fabric Eventhouse
      ├─ RunbookKBAgent → AzureAISearchTool → runbooks-index
      └─ HistoricalTicketAgent → AzureAISearchTool → tickets-index
  → Each sub-agent call yields SSE events (step_start, step_thinking, step_complete)
  → Orchestrator synthesises situation report → SSE message event
  → Frontend renders timeline + diagnosis markdown
```

### Error Recovery Flow

```
Sub-agent tool call returns error (e.g., bad KQL syntax)
  → fabric-query-api catches exception, returns 200 + {error: "..."}
  → Sub-agent LLM reads error message
  → Sub-agent retries with corrected query (prompt instructs self-repair)
  → If sub-agent run still fails:
      → Orchestrator run fails
      → orchestrator.py retry loop posts recovery message
      → New run created on same thread
      → If final attempt fails: SSE error event to frontend
```

---

## Deployment Targets

| Component | Local | Production |
|-----------|-------|------------|
| API | `uvicorn :8000` | Azure Container Apps |
| fabric-query-api | `uvicorn :8100` | Azure Container Apps (via `azd deploy`) |
| Frontend | Vite dev server `:5173` | Azure Static Web Apps |
| Infra | n/a | `azd up` → Azure |

Production deployment uses `azd up` for infrastructure and `azd deploy` for
services. The `fabric-query-api` service is configured with `remoteBuild: true`
in `azure.yaml` so Docker images are built in ACR (cross-platform safe).
CORS_ORIGINS must be updated to the production frontend URL before deploying.

---

## SDK Versions

| Package | Version | Notes |
|---------|---------|-------|
| `azure-ai-projects` | `>=1.0.0,<2.0.0` | v2 has breaking API changes |
| `azure-ai-agents` | `1.2.0b6` | `OpenApiTool`, `ConnectedAgentTool`, `AzureAISearchTool` |
| `azure-kusto-data` | `>=4.6.0` | KQL queries against Eventhouse |
| `fastapi` | `>=0.115` | ASGI framework |
| `sse-starlette` | `>=2.0` | SSE responses |
| `mcp[cli]` | `>=1.9.0` | FastMCP server framework |
| `react` | `18.x` | UI library |
| `framer-motion` | `11.x` | Animation |
| `@microsoft/fetch-event-source` | `^2.0.1` | POST-capable SSE client |
| `react-markdown` | `^10.1.0` | Markdown rendering in diagnosis + step cards |
| `react-resizable-panels` | `^4.6.2` | Resizable panel layout (metrics bar + vertical split) |
| `tailwindcss` | `3.x` | Utility-first CSS |

---

## Extension Guidance

### Add a New Graph Backend

1. Create `fabric-query-api/backends/{name}.py` implementing `GraphBackend` Protocol
2. Add the backend to `config.py` `GraphBackendType` enum and `BACKEND_REQUIRED_VARS`
3. Register in `backends/__init__.py` `get_backend()` factory
4. Create `fabric-query-api/openapi/{name}.yaml` with query language description
5. Create `data/prompts/graph_explorer/language_{name}.md` with syntax + examples
6. Add to `LANGUAGE_FILE_MAP`, `OPENAPI_SPEC_MAP`, `GRAPH_TOOL_DESCRIPTIONS` in
   `provision_agents.py`
7. Re-provision agents: `source azure_config.env && GRAPH_BACKEND={name} uv run python scripts/provision_agents.py`

### Add a New Sub-Agent

1. Create system prompt in `data/prompts/foundry_{name}_agent.md`
2. Add tool creation function in `provision_agents.py` (OpenApiTool, AzureAISearchTool, etc.)
3. Add agent creation in `provision_agents.py` `main()`
4. Add as `ConnectedAgentTool` to the orchestrator agent
5. Update orchestrator prompt to describe the new agent's capabilities
6. Re-provision agents

### Frontend Customisation

- **Add metric card:** Add entry to `metrics` array in `MetricsBar.tsx`, add `<Panel>`
- **Make metrics live:** Replace hardcoded values with hook polling `/api/metrics`
- **Adjust zone split:** Change `defaultSize` props in `App.tsx` (currently 30/70)
- **State migration:** Replace `useInvestigation` with Zustand store if prop-drilling grows
