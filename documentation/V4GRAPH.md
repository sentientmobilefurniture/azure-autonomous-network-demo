# V4 Graph Architecture: Backend-Agnostic Graph Abstraction

## Context & Motivation

The demo currently works end-to-end with **Fabric GraphModel** (GQL via `fabric-query-api`).
The previous V3 plan proposed swapping Fabric for Neo4j, but the strategic direction has
shifted — we now want a **backend-agnostic architecture** that can swap graph backends
via a single environment variable, with no code changes to the agent layer.

### Why backend-agnostic?

1. **Fabric still works** — we don't want to break the current demo
2. **Cosmos DB Gremlin is the next target** — Microsoft-native, sales motion, Fabric migration path
3. **Future-proof** — any graph backend (Fabric, Cosmos DB, Neo4j, in-memory mock) should slot in
4. **Demo flexibility** — `GRAPH_BACKEND=fabric` for customer Fabric demos, `GRAPH_BACKEND=cosmosdb`
   for graph-manipulation demos, `GRAPH_BACKEND=mock` for offline/disconnected demos

### The key insight (unchanged from V3)

> The agents don't know or care whether `/query/graph` talks to Fabric, Cosmos DB, or anything else.
> They send a query string and get back `{columns, data}`. The API contract stays the same.

What *does* change per backend:
- **Query language** in the agent's system prompt (GQL vs Gremlin vs Cypher)
- **Backend implementation** in `fabric-query-api/main.py` (which SDK to call)
- **Data loading** (how topology CSVs get into the graph)
- **OpenAPI spec description** (which query language examples to show)
- **Infrastructure** (Bicep modules for provisioning)

---

## Current State (V2 — Fabric Only)

### Files that are Fabric-specific today

| File | What's Fabric-specific | What's generic |
|------|----------------------|----------------|
| `fabric-query-api/main.py` | `_execute_gql()` function, Fabric REST API call, `_fabric_headers()` | KQL endpoint, FastAPI app, request/response models, error handling |
| `fabric-query-api/openapi.yaml` | GQL description, `workspace_id`/`graph_model_id` params | Endpoint paths, response schema |
| `data/prompts/foundry_graph_explorer_agent_v2.md` | GQL syntax examples, "GQL" references throughout | Entity schema, relationship schema, query patterns (logic), scope boundaries |
| `data/prompts/foundry_orchestrator_agent.md` | None (already generic) | Everything |
| `scripts/provision_agents.py` | `_make_graph_openapi_tool()` description says "GQL" | Everything else |
| `azure_config.env.template` | `FABRIC_GRAPH_MODEL_ID`, `FABRIC_ONTOLOGY_ID` | All other vars |

### Current request flow (Fabric)

```
Agent → OpenApiTool → POST /query/graph {query: "MATCH (r:CoreRouter)..."}
  → fabric-query-api → _execute_gql() → Fabric GraphModel REST API
  → {columns, data} → Agent
```

---

## Target Architecture (V4 — Backend-Agnostic)

### Control via `GRAPH_BACKEND` env var

```bash
# azure_config.env
GRAPH_BACKEND=fabric          # Options: "fabric" | "cosmosdb" | "mock"
```

- `fabric` → current behaviour, no changes
- `cosmosdb` → Cosmos DB for Apache Gremlin (future implementation)
- `mock` → in-memory static responses for offline demos (stretch)

### Request flow (all backends)

```
Agent → OpenApiTool → POST /query/graph {query: "..."}
  → fabric-query-api/main.py
  → reads GRAPH_BACKEND env
  → dispatches to backend:
      fabric   → backends/fabric.py   → Fabric GraphModel REST API (GQL)
      cosmosdb → backends/cosmosdb.py → Cosmos DB Gremlin (gremlinpython)
      mock     → backends/mock.py     → static JSON responses
  → normalises to {columns, data}
  → returns to agent
```

### What changes, what stays

| Component | Changes? | Detail |
|-----------|----------|--------|
| **Orchestrator agent** | No | Already generic |
| **TelemetryAgent** | No | KQL path is unaffected |
| **RunbookKBAgent** | No | AI Search, unrelated |
| **HistoricalTicketAgent** | No | AI Search, unrelated |
| **GraphExplorerAgent prompt** | Yes | Split into core schema + backend-specific query language |
| **fabric-query-api/main.py** | Yes | Extract backend dispatch, move Fabric code to backends/ |
| **fabric-query-api/openapi.yaml** | Yes | Make description backend-aware (template per backend) |
| **scripts/provision_agents.py** | Yes | Compose prompt from parts, select correct OpenAPI spec |
| **azure_config.env.template** | Yes | Add `GRAPH_BACKEND`, add Cosmos DB vars (commented) |
| **Frontend** | No | Receives same SSE events regardless |
| **API (main FastAPI app)** | No | Doesn't touch graph at all |

---

## Implementation Plan

### Phase 0: File Reorganisation (No Behaviour Change)

**Goal**: Move Fabric-specific code into clearly labelled locations. The demo
continues to work exactly as before — this is purely structural.

#### 0.1 Restructure `fabric-query-api/` internals

Current flat structure:
```
fabric-query-api/
├── main.py          ← 458 lines, GQL + KQL + SSE logs all mixed
├── openapi.yaml
├── Dockerfile
└── pyproject.toml
```

Target structure:
```
fabric-query-api/
├── main.py              ← slim: app factory, middleware, health, log streaming
├── config.py            ← GRAPH_BACKEND enum, env var loading
├── models.py            ← Pydantic request/response models (shared across backends)
├── router_graph.py      ← POST /query/graph endpoint (dispatches to backend)
├── router_telemetry.py  ← POST /query/telemetry endpoint (KQL, unchanged)
├── backends/
│   ├── __init__.py      ← GraphBackend protocol + get_backend() factory
│   ├── fabric.py        ← _execute_gql() moved here (current Fabric logic)
│   ├── cosmosdb.py      ← placeholder: raises NotImplementedError
│   └── mock.py          ← placeholder: returns static topology data
├── openapi/
│   ├── fabric.yaml      ← /query/graph + /query/telemetry spec with GQL description
│   ├── cosmosdb.yaml    ← /query/graph + /query/telemetry spec with Gremlin description
│   └── mock.yaml        ← /query/graph + /query/telemetry spec with generic description
├── Dockerfile
└── pyproject.toml
```

#### 0.2 Restructure agent prompts

Current:
```
data/prompts/
├── foundry_graph_explorer_agent_v2.md    ← 345 lines, GQL baked in everywhere
├── foundry_telemetry_agent_v2.md
├── foundry_orchestrator_agent.md
├── foundry_historical_ticket_agent.md
├── foundry_runbook_kb_agent.md
└── alert_storm.md
```

Target:
```
data/prompts/
├── graph_explorer/
│   ├── core_schema.md           ← Entity types, relationships, instances (backend-agnostic)
│   ├── core_instructions.md     ← Role, critical rules, scope boundaries (backend-agnostic)
│   ├── language_gql.md          ← GQL syntax, GQL examples, GQL-specific rules
│   ├── language_gremlin.md      ← Gremlin syntax, Gremlin examples, Gremlin-specific rules
│   ├── language_mock.md         ← Generic "send natural language" instructions
│   └── description.md           ← Foundry agent description (one-liner, backend-agnostic)
├── foundry_telemetry_agent_v2.md        ← unchanged
├── foundry_orchestrator_agent.md        ← unchanged
├── foundry_historical_ticket_agent.md   ← unchanged
├── foundry_runbook_kb_agent.md          ← unchanged
└── alert_storm.md                       ← unchanged
```

The full GraphExplorerAgent prompt is **assembled at provisioning time** by
`provision_agents.py`:

```python
GRAPH_BACKEND = os.getenv("GRAPH_BACKEND", "fabric")

LANGUAGE_FILE_MAP = {
    "fabric": "language_gql.md",
    "cosmosdb": "language_gremlin.md",
    "mock": "language_mock.md",
}

def load_graph_explorer_prompt() -> str:
    """Compose the GraphExplorer prompt from parts based on GRAPH_BACKEND."""
    base = PROMPTS_DIR / "graph_explorer"
    parts = [
        (base / "core_instructions.md").read_text(),
        (base / "core_schema.md").read_text(),
        (base / LANGUAGE_FILE_MAP[GRAPH_BACKEND]).read_text(),
    ]
    return "\n\n---\n\n".join(parts)
```

#### 0.3 `provision_agents.py` changes

```python
# Current:
OPENAPI_SPEC_FILE = PROJECT_ROOT / "fabric-query-api" / "openapi.yaml"

# New:
GRAPH_BACKEND = os.getenv("GRAPH_BACKEND", "fabric")
OPENAPI_DIR = PROJECT_ROOT / "fabric-query-api" / "openapi"

def _get_openapi_spec_file() -> Path:
    """Return the backend-specific OpenAPI spec for graph queries."""
    return OPENAPI_DIR / f"{GRAPH_BACKEND}.yaml"
```

The `_make_graph_openapi_tool()` function loads the backend-specific spec and
adjusts the description:

```python
TOOL_DESCRIPTIONS = {
    "fabric": "Execute a GQL query against the Fabric GraphModel to explore network topology.",
    "cosmosdb": "Execute a Gremlin query against Azure Cosmos DB to explore network topology.",
    "mock": "Query the network topology graph (offline mock mode).",
}

def _make_graph_openapi_tool(config: dict) -> OpenApiTool:
    spec = _load_openapi_spec(config, keep_path="/query/graph")
    return OpenApiTool(
        name="query_graph",
        spec=spec,
        description=TOOL_DESCRIPTIONS[GRAPH_BACKEND],
        auth=OpenApiAnonymousAuthDetails(),
    )
```

#### 0.4 `azure_config.env.template` additions

```bash
# --- Graph Backend (USER: set before provisioning agents) ---
# Controls which graph database backend is used by fabric-query-api
# and which query language the GraphExplorer agent uses.
# Options: "fabric" (default, GQL → Fabric GraphModel)
#          "cosmosdb" (Gremlin → Azure Cosmos DB)
#          "mock" (static responses, no external dependency)
GRAPH_BACKEND=fabric

# --- Cosmos DB Gremlin (required when GRAPH_BACKEND=cosmosdb) ---
# COSMOS_GREMLIN_ENDPOINT=
# COSMOS_GREMLIN_PRIMARY_KEY=
# COSMOS_GREMLIN_DATABASE=networkgraph
# COSMOS_GREMLIN_GRAPH=topology
```

---

### Phase 1: Backend Abstraction Layer

**Goal**: Define the `GraphBackend` protocol and implement the dispatch layer.
After this phase, `GRAPH_BACKEND=fabric` works identically to today.

#### 1.1 `fabric-query-api/backends/__init__.py` — Protocol + Factory

```python
"""Graph backend abstraction layer."""
from __future__ import annotations

import os
from typing import Protocol


class GraphBackend(Protocol):
    """Interface that all graph backends must implement."""

    async def execute_query(
        self,
        query: str,
        **kwargs,
    ) -> dict:
        """Execute a graph query and return {columns: [...], data: [...]}.

        The query language depends on the backend:
        - fabric: GQL
        - cosmosdb: Gremlin (string-based)
        - mock: natural language or predefined keys

        Returns:
            dict with "columns" (list of {name, type}) and "data" (list of dicts)
        """
        ...

    def close(self) -> None:
        """Clean up resources (connections, clients)."""
        ...


def get_backend() -> GraphBackend:
    """Factory: return the correct backend based on GRAPH_BACKEND env var."""
    backend_type = os.getenv("GRAPH_BACKEND", "fabric").lower()

    if backend_type == "fabric":
        from .fabric import FabricGraphBackend
        return FabricGraphBackend()
    elif backend_type == "cosmosdb":
        from .cosmosdb import CosmosDBGremlinBackend
        return CosmosDBGremlinBackend()
    elif backend_type == "mock":
        from .mock import MockGraphBackend
        return MockGraphBackend()
    else:
        raise ValueError(
            f"Unknown GRAPH_BACKEND: {backend_type!r}. "
            f"Valid options: fabric, cosmosdb, mock"
        )
```

#### 1.2 `fabric-query-api/backends/fabric.py` — Extract from current main.py

Move the existing `_execute_gql()`, `_fabric_headers()`, and related logic into
a class that implements `GraphBackend`:

```python
class FabricGraphBackend:
    """Graph backend using Fabric GraphModel REST API (GQL)."""

    async def execute_query(self, query: str, **kwargs) -> dict:
        workspace_id = kwargs.get("workspace_id", WORKSPACE_ID)
        graph_model_id = kwargs.get("graph_model_id", GRAPH_MODEL_ID)
        raw = await _execute_gql(query, workspace_id, graph_model_id)
        result = raw.get("result", raw)
        return {
            "columns": result.get("columns", []),
            "data": result.get("data", []),
        }

    def close(self) -> None:
        pass  # httpx client is per-request
```

**The `_execute_gql()` function itself is moved here verbatim.** No logic changes.

#### 1.3 `fabric-query-api/backends/cosmosdb.py` — Placeholder

```python
class CosmosDBGremlinBackend:
    """Graph backend using Azure Cosmos DB for Apache Gremlin."""

    async def execute_query(self, query: str, **kwargs) -> dict:
        raise NotImplementedError(
            "Cosmos DB Gremlin backend not yet implemented. "
            "Set GRAPH_BACKEND=fabric to use Fabric GraphModel."
        )

    def close(self) -> None:
        pass
```

#### 1.4 `fabric-query-api/backends/mock.py` — Static responses

```python
class MockGraphBackend:
    """Graph backend returning static topology data for offline demos."""

    async def execute_query(self, query: str, **kwargs) -> dict:
        # Return a minimal static response for any query
        return {
            "columns": [{"name": "info", "type": "string"}],
            "data": [{"info": f"Mock backend received query: {query[:100]}"}],
        }

    def close(self) -> None:
        pass
```

#### 1.5 `fabric-query-api/router_graph.py` — New graph router

```python
from fastapi import APIRouter, HTTPException
from .backends import get_backend, GraphBackend
from .models import GraphQueryRequest, GraphQueryResponse

router = APIRouter()
_backend: GraphBackend | None = None


def get_graph_backend() -> GraphBackend:
    global _backend
    if _backend is None:
        _backend = get_backend()
    return _backend


@router.post("/query/graph", response_model=GraphQueryResponse)
async def query_graph(req: GraphQueryRequest):
    backend = get_graph_backend()
    try:
        result = await backend.execute_query(
            req.query,
            workspace_id=getattr(req, "workspace_id", ""),
            graph_model_id=getattr(req, "graph_model_id", ""),
        )
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Graph query error: {e}")
    return GraphQueryResponse(
        columns=result.get("columns", []),
        data=result.get("data", []),
    )
```

#### 1.6 `fabric-query-api/main.py` — Slimmed down

After extraction, `main.py` becomes ~100 lines:
- App factory + lifespan (creates/closes backend)
- CORS middleware
- Request logging middleware
- Mount `router_graph` and `router_telemetry`
- SSE log streaming
- Health endpoint

The `query_graph` and `query_telemetry` endpoints move to their respective routers.

---

### Phase 2: Prompt Decomposition

**Goal**: Split the GraphExplorer prompt into composable parts. After this phase,
`provision_agents.py` assembles the prompt dynamically based on `GRAPH_BACKEND`.

#### 2.1 Create `data/prompts/graph_explorer/core_instructions.md`

Extracted from `foundry_graph_explorer_agent_v2.md`:
- Role section (generic: "You are a network topology analysis agent")
- How you work section (generic: "You have access to a `query_graph` tool")
- Critical rules (made generic: "use exact entity IDs", "retry on error", etc.)
- "What you can answer" / "What you cannot answer" sections
- Foundry Agent Description

**Remove**: All GQL-specific language ("GQL", "MATCH", query syntax examples)

#### 2.2 Create `data/prompts/graph_explorer/core_schema.md`

Extracted from `foundry_graph_explorer_agent_v2.md`:
- All 8 entity type tables (CoreRouter, TransportLink, AggSwitch, BaseStation, etc.)
- All instance data tables
- All relationship definitions (connects_to, aggregates_to, etc.)
- Relationship examples (kept generic — just show the relationship semantics,
  no query syntax)

**Remove**: Query examples (those go in language files)

#### 2.3 Create `data/prompts/graph_explorer/language_gql.md`

GQL-specific content extracted from `foundry_graph_explorer_agent_v2.md`:
- "You construct GQL queries" instruction
- GQL syntax rules and gotchas (e.g. "never use LOWER()")
- All GQL query examples (single-hop, multi-hop, blast radius)
- `MATCH ... WHERE ... RETURN` patterns

#### 2.4 Create `data/prompts/graph_explorer/language_gremlin.md`

New file for Cosmos DB Gremlin:
- "You construct Gremlin queries" instruction
- Gremlin syntax rules (string-based, pass as plain text to the tool)
- Cosmos DB-specific notes (no lambdas, no bytecode, partition key matters)
- Equivalent query examples translated from GQL to Gremlin

Example translations:

| Pattern | GQL | Gremlin |
|---------|-----|---------|
| Find router | `MATCH (r:CoreRouter) WHERE r.RouterId = "CORE-SYD-01" RETURN r` | `g.V().hasLabel('CoreRouter').has('RouterId','CORE-SYD-01').valueMap(true)` |
| Link → paths | `MATCH (mp:MPLSPath)-[:routes_via]->(tl:TransportLink) WHERE tl.LinkId = "..." RETURN mp` | `g.V().hasLabel('TransportLink').has('LinkId','...').in('routes_via').hasLabel('MPLSPath').valueMap(true)` |
| Blast radius (2-hop) | `MATCH (mp:MPLSPath)-[:routes_via]->(tl:TransportLink), (svc:Service)-[:depends_on]->(mp) WHERE tl.LinkId = "..." RETURN ...` | `g.V().hasLabel('TransportLink').has('LinkId','...').in('routes_via').hasLabel('MPLSPath').as('mp').in('depends_on').hasLabel('Service').as('svc').select('mp','svc').by(valueMap(true))` |
| Blast radius (3-hop with SLA) | 3-hop MATCH | chained `.in()/.out()` traversals with `.as()/.select()` |
| Count by label | `MATCH (n) RETURN labels(n), count(*)` | `g.V().groupCount().by(label)` |
| All routers | `MATCH (r:CoreRouter) RETURN r.RouterId, r.City` | `g.V().hasLabel('CoreRouter').valueMap(true)` |

#### 2.5 Create `data/prompts/graph_explorer/language_mock.md`

Minimal file:
```markdown
## Query Language: Natural Language (Mock Mode)

Send a natural language description of what you want to find.
The mock backend returns static topology data for demonstration purposes.
Example: "find all core routers" or "what services depend on LINK-SYD-MEL-FIBRE-01"
```

#### 2.6 Create `data/prompts/graph_explorer/description.md`

One-liner for Foundry agent description (backend-agnostic):
```
> Queries the network topology graph to answer questions about routers, links,
> switches, base stations, MPLS paths, services, SLA policies, and BGP sessions.
> Use this agent to discover infrastructure relationships, trace connectivity
> paths, determine blast radius of failures, and assess SLA exposure. Does not
> have access to real-time telemetry, operational runbooks, or historical
> incident records.
```

---

### Phase 3: OpenAPI Spec Splitting

**Goal**: Create per-backend OpenAPI specs for the `/query/graph` endpoint.
Each spec is a **complete, standalone file** — no inheritance or composition.

#### 3.1 Create `fabric-query-api/openapi/fabric.yaml`

Complete spec including:
- `info` section (title: "Fabric Query API", version)
- `servers` section (with `{base_url}` placeholder)
- `/query/graph` with GQL description, `workspace_id`/`graph_model_id` params, GQL examples
- `/query/telemetry` (unchanged, identical across all specs)
- Shared response schemas

This is essentially the current `openapi.yaml` renamed and moved.

#### 3.2 Create `fabric-query-api/openapi/cosmosdb.yaml`

Complete spec including:
- Same structure as `fabric.yaml`
- `/query/graph` with Gremlin description, Gremlin examples
- **No** `workspace_id`/`graph_model_id` params (Cosmos DB config is server-side env vars)
- `/query/telemetry` (unchanged)

#### 3.3 Create `fabric-query-api/openapi/mock.yaml`

Complete spec including:
- Same structure
- `/query/graph` with generic description ("send any query string")
- `/query/telemetry` (unchanged)

#### 3.4 Update `provision_agents.py` to select correct spec

```python
OPENAPI_SPEC_MAP = {
    "fabric": OPENAPI_DIR / "fabric.yaml",
    "cosmosdb": OPENAPI_DIR / "cosmosdb.yaml",
    "mock": OPENAPI_DIR / "mock.yaml",
}

OPENAPI_SPEC_FILE = OPENAPI_SPEC_MAP[GRAPH_BACKEND]
```

---

### Phase 4: Wire It All Together

**Goal**: Everything connected. `GRAPH_BACKEND=fabric` works exactly like today.
Changing to `cosmosdb` or `mock` routes correctly (cosmosdb returns 501, mock
returns static data).

#### 4.1 Update `provision_agents.py` to compose prompts

Modify `load_prompt()` to handle the new graph_explorer directory structure:

```python
def load_graph_explorer_prompt() -> tuple[str, str]:
    """Compose GraphExplorer prompt from parts based on GRAPH_BACKEND."""
    base = PROMPTS_DIR / "graph_explorer"
    language_file = LANGUAGE_FILE_MAP[GRAPH_BACKEND]

    instructions = "\n\n---\n\n".join([
        (base / "core_instructions.md").read_text(encoding="utf-8"),
        (base / "core_schema.md").read_text(encoding="utf-8"),
        (base / language_file).read_text(encoding="utf-8"),
    ])

    description = (base / "description.md").read_text(encoding="utf-8").strip()
    # Extract > quoted lines
    desc_lines = [
        line.lstrip("> ").strip()
        for line in description.splitlines()
        if line.strip().startswith(">")
    ]
    description = " ".join(desc_lines) if desc_lines else description

    return instructions, description
```

#### 4.2 Update `Dockerfile` for new file structure

The Dockerfile currently copies `main.py` and `openapi.yaml`. Update to copy the
new directory structure:

```dockerfile
COPY main.py config.py models.py router_graph.py router_telemetry.py ./
COPY backends/ ./backends/
COPY openapi/ ./openapi/
```

#### 4.3 Update `azure.yaml` if needed

The service target for `fabric-query-api` should continue to work with the same
Docker build context. No changes expected unless the build context path changes.

#### 4.4 Smoke test checklist

```bash
# Test 1: GRAPH_BACKEND=fabric (default) — must behave identically to current
source azure_config.env
cd fabric-query-api && uv run uvicorn main:app --port 8100

curl -s http://localhost:8100/health
curl -s -X POST http://localhost:8100/query/graph \
  -H 'Content-Type: application/json' \
  -d '{"query": "MATCH (r:CoreRouter) RETURN r.RouterId, r.City"}'
# Expected: same response as today

# Test 2: GRAPH_BACKEND=mock
GRAPH_BACKEND=mock uv run uvicorn main:app --port 8100
curl -s -X POST http://localhost:8100/query/graph \
  -H 'Content-Type: application/json' \
  -d '{"query": "find all routers"}'
# Expected: mock response with static data

# Test 3: GRAPH_BACKEND=cosmosdb
GRAPH_BACKEND=cosmosdb uv run uvicorn main:app --port 8100
curl -s -X POST http://localhost:8100/query/graph \
  -H 'Content-Type: application/json' \
  -d '{"query": "g.V().hasLabel(\"CoreRouter\").valueMap(true)"}'
# Expected: 501 Not Implemented

# Test 4: Full agent flow
# Set GRAPH_BACKEND=fabric, reprovision agents, run test_orchestrator.py
# Verify identical behaviour to current
```

---

## Execution Order (Task Sequence)

```
Phase 0 — File Reorganisation
  ├─ 0.1  Create fabric-query-api/{config,models,router_graph,router_telemetry}.py
  │       Extract from main.py, main.py becomes slim app factory
  ├─ 0.2  Create fabric-query-api/backends/{__init__,fabric,cosmosdb,mock}.py
  │       Move _execute_gql() into backends/fabric.py
  ├─ 0.3  Split foundry_graph_explorer_agent_v2.md into graph_explorer/ parts
  │       {core_instructions,core_schema,language_gql,language_gremlin,language_mock,description}.md
  ├─ 0.4  Create openapi/{fabric,cosmosdb,mock}.yaml
  └─ 0.5  Add GRAPH_BACKEND + Cosmos DB vars to azure_config.env.template

Phase 1 — Backend Abstraction
  ├─ 1.1  Implement GraphBackend protocol in backends/__init__.py
  ├─ 1.2  Implement FabricGraphBackend in backends/fabric.py
  ├─ 1.3  Implement placeholders (CosmosDBGremlinBackend, MockGraphBackend)
  └─ 1.4  Wire router_graph.py to use get_backend()

Phase 2 — Prompt Composition
  ├─ 2.1  Update provision_agents.py with load_graph_explorer_prompt()
  ├─ 2.2  Update provision_agents.py with backend-specific OpenAPI spec selection
  └─ 2.3  Verify: re-provision agents with GRAPH_BACKEND=fabric, run test_orchestrator.py

Phase 3 — Integration Test
  ├─ 3.1  Smoke test: GRAPH_BACKEND=fabric (must be identical to current behaviour)
  ├─ 3.2  Smoke test: GRAPH_BACKEND=mock (returns static data)
  ├─ 3.3  Smoke test: GRAPH_BACKEND=cosmosdb (returns 501)
  └─ 3.4  Full flow test: submit alert, verify agent uses correct query language

Phase 4 — Cleanup
  ├─ 4.1  Update Dockerfile for new file structure
  ├─ 4.2  Update ARCHITECTURE.md to document new structure
  ├─ 4.3  Move foundry_graph_explorer_agent_v2.md to data/prompts/deprecated/
  └─ 4.4  Move fabric-query-api/openapi.yaml to deprecated/
```

---

## File Change Summary

### New files to create

| File | Purpose |
|------|---------|
| `fabric-query-api/config.py` | `GRAPH_BACKEND` enum, env var loading |
| `fabric-query-api/models.py` | Shared Pydantic models |
| `fabric-query-api/router_graph.py` | `/query/graph` endpoint + backend dispatch |
| `fabric-query-api/router_telemetry.py` | `/query/telemetry` endpoint (KQL, extracted) |
| `fabric-query-api/backends/__init__.py` | `GraphBackend` protocol + `get_backend()` factory |
| `fabric-query-api/backends/fabric.py` | Fabric GraphModel backend (moved from main.py) |
| `fabric-query-api/backends/cosmosdb.py` | Cosmos DB Gremlin placeholder |
| `fabric-query-api/backends/mock.py` | Static response placeholder |
| `fabric-query-api/openapi/fabric.yaml` | GQL OpenAPI spec (current openapi.yaml) |
| `fabric-query-api/openapi/cosmosdb.yaml` | Gremlin OpenAPI spec |
| `fabric-query-api/openapi/mock.yaml` | Generic OpenAPI spec |
| `data/prompts/graph_explorer/core_instructions.md` | Role, rules, scope (backend-agnostic) |
| `data/prompts/graph_explorer/core_schema.md` | Entity & relationship schema (backend-agnostic) |
| `data/prompts/graph_explorer/language_gql.md` | GQL syntax + examples |
| `data/prompts/graph_explorer/language_gremlin.md` | Gremlin syntax + examples |
| `data/prompts/graph_explorer/language_mock.md` | Mock mode instructions |
| `data/prompts/graph_explorer/description.md` | Agent description one-liner |

### Files to modify

| File | Change |
|------|--------|
| `fabric-query-api/main.py` | Slim down to app factory + middleware + router mounts |
| `fabric-query-api/Dockerfile` | Update COPY commands for new structure |
| `scripts/provision_agents.py` | Compose prompt from parts, select backend-specific OpenAPI spec |
| `azure_config.env.template` | Add `GRAPH_BACKEND` + Cosmos DB vars |

### Files to deprecate (move to deprecated/)

| File | Reason |
|------|--------|
| `data/prompts/foundry_graph_explorer_agent_v2.md` | Replaced by `graph_explorer/` directory |
| `fabric-query-api/openapi.yaml` | Replaced by `openapi/{fabric,cosmosdb,mock}.yaml` |

### Files that DO NOT change

| File | Reason |
|------|--------|
| `data/prompts/foundry_orchestrator_agent.md` | Already backend-agnostic |
| `data/prompts/foundry_telemetry_agent_v2.md` | KQL, unrelated to graph backend |
| `data/prompts/foundry_runbook_kb_agent.md` | AI Search, unrelated |
| `data/prompts/foundry_historical_ticket_agent.md` | AI Search, unrelated |
| `api/` (entire directory) | Doesn't touch graph — calls fabric-query-api via agents |
| `frontend/` (entire directory) | Receives same SSE events regardless of backend |
| `infra/` | No Bicep changes in Phase 0-4 (Cosmos DB Bicep comes in a future phase) |
| All `scripts/` except `provision_agents.py` | Fabric provisioning scripts are unaffected |

---

## Request/Response Contract (Unchanged)

The API contract between agents and fabric-query-api does **not change**:

### Request (POST /query/graph)
```json
{
  "query": "<query string in backend-appropriate language>",
  "workspace_id": "<optional, Fabric only>",
  "graph_model_id": "<optional, Fabric only>"
}
```

### Response
```json
{
  "columns": [{"name": "RouterId", "type": "string"}, ...],
  "data": [{"RouterId": "CORE-SYD-01", "City": "Sydney"}, ...]
}
```

For Cosmos DB Gremlin, the backend normalises `valueMap(true)` output into the
same `{columns, data}` shape. This normalisation happens in `backends/cosmosdb.py`,
not in the agent or router.

---

## Risk & Mitigation

| Risk | Mitigation |
|------|------------|
| Breaking current Fabric flow during refactor | Phase 0 is pure file moves, test after each step |
| Agent prompt quality regression | Keep the current `_v2.md` as fallback until validated |
| OpenAPI spec divergence | Each backend spec is a complete standalone file, no inheritance complexity |
| Cosmos DB response shape differs from Fabric | Normalisation in backend layer, not in agent/router |
| Prompt too long after composition | Monitor token count — schema is ~200 lines, language ~100 lines |

---

## Future Phases (Out of Scope for This Plan)

These come after the abstraction layer is in place:

- **Phase 5**: Implement `backends/cosmosdb.py` with gremlinpython SDK
  (see `custom_skills/azure-cosmosdb-gremlin-py/`)
- **Phase 6**: Cosmos DB Bicep module (`infra/modules/cosmos-gremlin.bicep`)
  (see `custom_skills/azure-cosmosdb-gremlin-py/references/bicep-provisioning.md`)
- **Phase 7**: Data loading script (`scripts/provision_cosmos_gremlin.py`)
  (see `custom_skills/azure-cosmosdb-gremlin-py/references/data-loading.md`)
- **Phase 8**: Graph visualisation in frontend (React Flow / D3)
- **Phase 9**: Live graph mutation endpoints (`POST /graph/mutate`)
