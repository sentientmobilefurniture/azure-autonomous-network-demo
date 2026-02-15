# Config-Driven Multi-Agent Orchestration — Implementation Plan

> **Created:** 2026-02-16
> **Last audited:** 2026-02-16
> **Status:** ⬜ Not Started
> **Goal:** Transform the platform from a hardcoded 5-agent telco-NOC demo into a
> config-driven orchestration engine where a single YAML file defines all agents,
> data sources, storage backends, query languages, prompts, and inter-agent
> connections. The current telco-noc scenario becomes one config file; new
> scenarios require zero code changes.

---

## Requirements (Original)

1. I want to be able to specify data formats and agent structures, perhaps by YAML or some other config file. That means genericizing data ingestion and storage, as well as agent provisioning.
2. A single config file fully describes a deployment — agents, data sources, storage backends, query languages, prompts, inter-agent connections, UI bindings.
3. The current telco-noc scenario should keep working throughout the refactor and become the first config-driven scenario.
4. New scenarios = new config file + data, zero code changes.
5. Genericize data ingestion so new backends (Fabric, Neo4j, etc.) can slot in as adapters without touching core code.
6. Build a Resource & Agent Flow Visualizer UI tab showing agents, tools, data sources, and their connections as an interactive graph.
7. The genericization should come before adding Fabric or any other new backend.

---

## Implementation Status

| Phase | Status | Scope |
|-------|--------|-------|
| **Phase 0:** Infrastructure Genericization (Bicep + Deploy) | ⬜ Not started | `infra/`, `deploy.sh`, `hooks/`, `azure_config.env.template` |
| **Phase 1:** DocumentStore Protocol + CosmosDocumentStore | ⬜ Not started | `graph-query-api/stores/` (new) |
| **Phase 2:** Extract Cosmos Config into Adapter Module | ⬜ Not started | `graph-query-api/adapters/`, `config.py` |
| **Phase 3:** Rename ScenarioContext Fields to Generic Names | ⬜ Not started | `config.py`, 4-5 consumer files |
| **Phase 4:** Migrate NoSQL Routers to DocumentStore | ⬜ Not started | `router_interactions.py`, `router_scenarios.py`, `router_telemetry.py`, `router_prompts.py` |
| **Phase 5:** Extract Blob + AI Search into Service Modules | ⬜ Not started | `router_ingest.py`, `services/` (new) |
| **Phase 6:** Add `ingest()` to GraphBackend Protocol | ⬜ Not started | `backends/__init__.py`, `backends/cosmosdb.py`, `router_ingest.py` |
| **Phase 7:** Backend Registry (Replace Enum Dispatch) | ⬜ Not started | `backends/__init__.py`, `config.py` |
| **Phase 8:** Config-Driven Agent Provisioner | ⬜ Not started | `agent_provisioner.py`, `api/app/routers/config.py` |
| **Phase 9:** OpenAPI Spec Templating | ⬜ Not started | `openapi/`, `agent_provisioner.py` |
| **Phase 10:** Config-Driven Prompt System | ⬜ Not started | `router_ingest.py`, `router_prompts.py`, `api/app/routers/config.py` |
| **Phase 11:** Frontend Genericization | ⬜ Not started | `ScenarioContext.tsx`, `graphConstants.ts`, `SettingsModal.tsx`, `TabBar.tsx`, `App.tsx`, empty-state + ARIA + provisioning CTA |
| **Phase 12:** Resource Visualizer — Backend Endpoint | ⬜ Not started | `api/app/routers/config.py` |
| **Phase 13:** Migrate telco-noc to Config | ⬜ Not started | `data/scenarios/telco-noc/scenario.yaml` |

> **Phase ↔ Item mapping:** Phase 0 = Item 14, Phases 1–13 = Items 1–13.
> Phase 0 is listed first because it should run before all others.

### Resource Visualizer (Frontend) — Pre-built

| Component | Status |
|-----------|--------|
| Tab system (`App.tsx`, `TabBar.tsx`) | ✅ Complete |
| `ResourceVisualizer.tsx` | ✅ Complete (mock data) |
| `ResourceCanvas.tsx` | ✅ Complete |
| `ResourceToolbar.tsx` | ✅ Complete |
| `ResourceTooltip.tsx` | ✅ Complete |
| `useResourceGraph.ts` | ✅ Complete (mock) — swap for real API in Phase 12 |

### Deviations From Plan

| # | Plan Said | What Was Done | Rationale |
|---|-----------|---------------|-----------|
| D-1 | — | — | — |

### Extra Work Not In Plan

- {None yet}

---

## Table of Contents

- [Requirements (Original)](#requirements-original)
- [Implementation Status](#implementation-status)
- [Codebase Conventions & Context](#codebase-conventions--context)
- [Overview of Changes](#overview-of-changes)
- [Item 1: DocumentStore Protocol](#item-1-documentstore-protocol)
- [Item 2: Extract Cosmos Config](#item-2-extract-cosmos-config)
- [Item 3: Generic ScenarioContext Fields](#item-3-generic-scenariocontext-fields)
- [Item 4: Migrate NoSQL Routers to DocumentStore](#item-4-migrate-nosql-routers-to-documentstore)
- [Item 5: Extract Blob + AI Search Services](#item-5-extract-blob--ai-search-services)
- [Item 6: Add Ingest to GraphBackend Protocol](#item-6-add-ingest-to-graphbackend-protocol)
- [Item 7: Backend Registry](#item-7-backend-registry)
- [Item 8: Config-Driven Agent Provisioner](#item-8-config-driven-agent-provisioner)
- [Item 9: OpenAPI Spec Templating](#item-9-openapi-spec-templating)
- [Item 10: Config-Driven Prompt System](#item-10-config-driven-prompt-system)
- [Item 11: Frontend Genericization](#item-11-frontend-genericization)
  - [11a. ScenarioContext — Config-Specified Resources](#11a-scenariocontext--config-specified-resources)
  - [11b. graphConstants.ts — Remove Telco-Specific Defaults](#11b-graphconstantsts--remove-telco-specific-defaults)
  - [11c. SettingsModal — Config-Aware Data Sources](#11c-settingsmodal--config-aware-data-sources)
  - [11d. Stub Agents — Config-Driven Names](#11d-stub-agents--config-driven-names)
  - [11e. First-Run Empty State](#11e-first-run-empty-state)
  - [11f. ARIA Tab Semantics](#11f-aria-tab-semantics)
  - [11g. Provisioning Discoverability](#11g-provisioning-discoverability)
  - [11h. Upload Progress Visibility](#11h-upload-progress-visibility)
- [Item 12: Resource Visualizer Backend](#item-12-resource-visualizer-backend)
- [Item 13: Migrate telco-noc to Config](#item-13-migrate-telco-noc-to-config)
- [Item 14: Infrastructure Genericization](#item-14-infrastructure-genericization-bicep--deploy-scripts)
- [Implementation Phases](#implementation-phases)
- [File Change Inventory](#file-change-inventory)
- [Edge Cases & Validation](#edge-cases--validation)
- [Migration & Backwards Compatibility](#migration--backwards-compatibility)
- [Codebase Audit Reference](#codebase-audit-reference)
- [Resource Visualizer Reference](#resource-visualizer-reference)

---

## Codebase Conventions & Context

> **Read this section first** before implementing any phase. These conventions
> are load-bearing — ignoring them causes import errors, routing failures, or
> mismatched data.

### Request Routing

| URL prefix | Proxied to | Config |
|------------|-----------|--------|
| `/api/*` | API service on port **8000** | `vite.config.ts` L21-31 (dev), `nginx.conf` L17-18 (prod) |
| `/query/*` | graph-query-api on port **8100** | `vite.config.ts` L44-53 (dev), `nginx.conf` L40-41 (prod) |

Both proxy configs include SSE-compatible settings (`proxy_buffering off`,
`proxy_cache off`). New routes under either prefix automatically inherit
routing — **no nginx changes needed**.

### Scenario Naming & Derivation

| Concept | Example | Derivation |
|---------|---------|-----------|
| Base scenario name | `"telco-noc"` | User-provided at upload time, stored in `ScenarioContext.activeScenario` |
| Graph name | `"telco-noc-topology"` | `${name}-topology` — sent as `X-Graph` header |
| Prefix extraction | `"telco-noc"` | Backend: `graph_name.rsplit("-", 1)[0]` in `config.py` L109 |
| Telemetry containers | `"telco-noc-AlertStream"` | `${prefix}-${container_name}` in `router_telemetry.py` |
| Prompts container | `"telco-noc"` | Container name = scenario name, in shared `prompts` DB |
| Runbooks index | `"telco-noc-runbooks-index"` | `${name}-runbooks-index` |
| Tickets index | `"telco-noc-tickets-index"` | `${name}-tickets-index` |

> **⚠️ Implementation trap:** The `X-Graph` header is used for read-time query
> routing. Upload endpoints receive scenario names via the `scenario_name`
> query parameter — **not** from `X-Graph`.

### Import & Code Style Conventions

**Backend (Python):**
- All graph-query-api files import from `config` (not `graph-query-api.config`) — the service runs standalone with its own working directory.
- `cosmos_helpers` is imported directly (e.g., `from cosmos_helpers import get_cosmos_client`), not via relative import.
- FastAPI dependency injection via `Depends(get_scenario_context)` for per-request context.

**Frontend (TypeScript):**
- Panel imports are aliased:
  ```tsx
  import { Group as PanelGroup, Panel, Separator as PanelResizeHandle }
    from 'react-resizable-panels';
  ```
- CSS classes follow the existing `glass-card`, `bg-neutral-bg1`, `text-text-primary` convention.
- State management via React Context (`ScenarioContext`), not Redux.

### Data Format Conventions

| Convention | Format | Where Used |
|-----------|--------|------------|
| SSE events | `event: log\ndata: ...\n\n` | Log streams in both APIs, `TabbedLogStream.tsx` |
| SSE listener | `addEventListener('log', ...)` — NOT `onmessage` | All SSE consumers |
| Graph response | `{nodes: [{id, label, properties}], edges: [{id, source, target, label, properties}]}` | `GraphBackend.get_topology()`, `useTopology.ts` |
| Telemetry response | `{columns: [{name, type}], rows: [dict]}` | `router_telemetry.py`, `_execute_cosmos_sql()` |
| Per-request routing | `X-Graph` header → `ScenarioContext` | All `/query/*` endpoints |

### Shared Databases (Pre-created by Bicep)

| Database | Type | Purpose | Containers |
|----------|------|---------|------------|
| `networkgraph` | Cosmos Gremlin | Graph topologies | Per-scenario graphs (e.g., `telco-noc-topology`) |
| `telemetry` | Cosmos NoSQL | Telemetry time-series | Per-scenario prefixed (e.g., `telco-noc-AlertStream`) |
| `prompts` | Cosmos NoSQL | Agent prompts | Per-scenario (e.g., `telco-noc`) |
| `scenarios` | Cosmos NoSQL | Scenario metadata | `scenarios` (shared) |
| `interactions` | Cosmos NoSQL | Investigation history | `interactions` (shared) |

> **⚠️ Architectural constraint:** ARM calls create **containers/graphs** within
> these shared databases — never new databases. Adapters for new backends must
> respect this pattern or provide their own resource provisioning.

---

## Overview of Changes

| # | Item | Category | Impact | Effort |
|---|------|----------|--------|--------|
| 1 | DocumentStore Protocol | Backend (abstraction) | High — enables all NoSQL migrations | Small |
| 2 | Extract Cosmos Config | Backend (cleanup) | Low — import restructure | Small |
| 3 | Generic ScenarioContext Fields | Backend (naming) | Medium — touches 5 files | Small |
| 4 | Migrate NoSQL Routers | Backend (refactor) | High — 4 routers become backend-agnostic | Medium |
| 5 | Extract Blob + Search Services | Backend (refactor) | Medium — untangles router_ingest | Medium |
| 6 | Add ingest() to GraphBackend | Backend (protocol) | High — graph loading becomes pluggable | Medium-Hard |
| 7 | Backend Registry | Backend (architecture) | Medium — enables new backends | Small |
| 8 | Config-Driven Provisioner | Backend (architecture) | High — N agents from config | Large |
| 9 | OpenAPI Spec Templating | Backend (plumbing) | Medium — per-connector specs | Medium |
| 10 | Config-Driven Prompts | Backend (plumbing) | Medium — breaks hardcoded mappings | Medium |
| 11 | Frontend Genericization | Frontend | Medium — config-aware rendering | Medium |
| 12 | Resource Visualizer Backend | Backend + Frontend | Medium — connects mock UI to real data | Small |
| 13 | Migrate telco-noc | Full-stack (validation) | High — proves the whole system | Medium |

### Dependency Graph

```
Phase 1 (DocumentStore) ──┐
Phase 2 (Cosmos Config)   ├──▶ Phase 4 (Migrate NoSQL Routers) ──┐
Phase 3 (Generic Fields)──┘                                      │
                                                                  │
Phase 5 (Blob/Search Services)───────────────────────────────────┤
Phase 6 (Ingest Protocol)────────────────────────────────────────┤
Phase 7 (Backend Registry)───┐                                   │
Phase 10 (Config Prompts)────┤                                   │
                              │                                   │
Phase 9 (OpenAPI Templates) ─┼─▶ Phase 8 (Config Provisioner) ──┤
                                                                  │
Phase 11 (Frontend Generic) ──────────────────────────────────────┤
Phase 12 (Viz Backend) ───────────────────────────────────────────┤
                                                                  │
                                                 Phase 13 (Migrate telco-noc)
```

**Parallelizable:** Phases 1, 2, 3 can run in parallel. Phases 11 and 12 can
run in parallel.

**Sequential gates:** Phase 4 requires Phases 1+3 (Phase 2 is shown in the
diagram but is NOT a hard prerequisite — Phase 4 replaces Cosmos imports with
DocumentStore imports, so the old import paths still work if Phase 2 hasn't run).
Phase 8 requires Phase 7 (registry provides `str`-based backend types used by
the connector-aware provisioner) and Phase 9 (`_build_tools()` uses
`spec_template` references defined in Phase 9). Phase 13 requires all prior phases.

> **⚠️ Practical parallelism caveat:** Phases 5, 6, 8, and 10 all modify
> `router_ingest.py`. While they touch different sections, running them
> simultaneously creates merge conflicts. **Recommended execution order for
> those phases:** 5 → 6 → 10 → 8 (each builds on the previous cleanup).
> Only Phases 7 and 9 are truly safe to run in parallel with this sequence.

---

## Item 1: DocumentStore Protocol

### Current State

Four routers directly import `cosmos_helpers` and call Cosmos SDK methods:

| Router | Lines | Cosmos SDK Calls |
|--------|-------|-----------------|
| `router_interactions.py` | 146 | `query_items`, `upsert_item`, `read_item`, `delete_item` |
| `router_scenarios.py` | 220 | `query_items`, `upsert_item`, `read_item`, `delete_item` |
| `router_telemetry.py` | 144 | `query_items` (SQL) |
| `router_prompts.py` | 288 | `query_items`, `read_item`, `upsert_item`, ARM `list_sql_containers` |

> **Note:** Line counts above are exact as of the current codebase. Some later
> sections referenced slightly different counts (off-by-one) — the values in
> this table are authoritative.

Each router gets a container via `get_or_create_container(db_name, container_name, pk_path)`
from `cosmos_helpers.py`, then calls Cosmos SDK methods directly. There is no
abstraction between the router logic and the storage backend.

**Problem:** Any new storage backend (Fabric, PostgreSQL, in-memory mock) requires
modifying all 4 routers. The Cosmos SDK is spread across 800+ lines of router code.

### Target State

A `DocumentStore` Protocol sits between routers and storage. Routers call
`store.query()`, `store.upsert()`, etc. The Cosmos implementation lives behind
the protocol. New backends implement the same protocol.

```python
# graph-query-api/stores/__init__.py

from typing import Protocol, runtime_checkable, Any

@runtime_checkable
class DocumentStore(Protocol):
    """Backend-agnostic document CRUD + query interface."""

    async def list(
        self,
        *,
        query: str | None = None,
        parameters: list[dict[str, Any]] | None = None,
        partition_key: str | None = None,
    ) -> list[dict[str, Any]]:
        """List/query documents. If query is None, return all.

        Args:
            query: Cosmos SQL query string (e.g. "SELECT * FROM c WHERE c.x = @x")
            parameters: Parameterized query values (e.g. [{"name": "@x", "value": 1}]).
                        Always use parameters instead of f-string interpolation.
            partition_key: Scope query to a single partition (avoids cross-partition cost).
        """
        ...

    async def get(
        self,
        item_id: str,
        partition_key: str,
    ) -> dict[str, Any]:
        """Get a single document by ID + partition key."""
        ...

    async def upsert(
        self,
        item: dict[str, Any],
    ) -> dict[str, Any]:
        """Insert or update a document."""
        ...

    async def delete(
        self,
        item_id: str,
        partition_key: str,
    ) -> None:
        """Delete a document by ID + partition key."""
        ...


_document_store_registry: dict[str, type] = {}

def register_document_store(name: str, cls: type) -> None:
    _document_store_registry[name] = cls

def get_document_store(
    db_name: str,
    container_name: str,
    partition_key_path: str,
    *,
    backend_type: str | None = None,
    ensure_created: bool = False,
) -> DocumentStore:
    """Factory that returns the appropriate DocumentStore implementation.

    Args:
        backend_type: Override store type. Defaults to 'cosmosdb-nosql'.
                      Must match a registered store name.
    """
    bt = backend_type or "cosmosdb-nosql"
    if bt not in _document_store_registry:
        raise ValueError(f"Unknown document store: {bt}. "
                         f"Available: {list(_document_store_registry)}")
    return _document_store_registry[bt](
        db_name, container_name, partition_key_path,
        ensure_created=ensure_created,
    )

# Auto-register at module load:
from .cosmos_nosql import CosmosDocumentStore
register_document_store("cosmosdb-nosql", CosmosDocumentStore)
```

```python
# graph-query-api/stores/cosmos_nosql.py

import asyncio
from typing import Any
from cosmos_helpers import get_or_create_container

class CosmosDocumentStore:
    """Cosmos NoSQL implementation of DocumentStore."""

    def __init__(self, db_name: str, container_name: str, pk_path: str,
                 *, ensure_created: bool = False):
        self._container = get_or_create_container(
            db_name, container_name, pk_path, ensure_created=ensure_created
        )

    async def list(self, *, query: str | None = None,
                   parameters: list[dict[str, Any]] | None = None,
                   partition_key: str | None = None) -> list[dict[str, Any]]:
        q = query or "SELECT * FROM c"
        kwargs: dict = {"query": q}
        if parameters:
            kwargs["parameters"] = parameters
        if partition_key:
            kwargs["partition_key"] = partition_key
            kwargs["enable_cross_partition_query"] = False
        else:
            kwargs["enable_cross_partition_query"] = True
        return await asyncio.to_thread(
            lambda: list(self._container.query_items(**kwargs))
        )

    async def get(self, item_id: str, partition_key: str) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._container.read_item, item_id, partition_key=partition_key
        )

    async def upsert(self, item: dict[str, Any]) -> dict[str, Any]:
        return await asyncio.to_thread(self._container.upsert_item, item)

    async def delete(self, item_id: str, partition_key: str) -> None:
        await asyncio.to_thread(
            self._container.delete_item, item_id, partition_key=partition_key
        )
```

> **⚠️ Implementation note:** The existing `cosmos_helpers.get_or_create_container()`
> is synchronous and uses a cache keyed by `(db_name, container_name)`. The
> `CosmosDocumentStore.__init__` must NOT be called in async context without
> wrapping — but since the container is cached after first creation, this is
> safe for subsequent calls. First-call ARM creation (5-10s) happens synchronously.

### Mock Implementation (Optional but Recommended)

```python
# graph-query-api/stores/mock_store.py

from typing import Any

class MockDocumentStore:
    """In-memory document store for testing."""

    def __init__(self, db_name: str = "", container_name: str = "",
                 pk_path: str = "", *, ensure_created: bool = False):
        # Accept and ignore factory args so it satisfies the same
        # constructor signature as CosmosDocumentStore.
        self._items: dict[str, dict[str, Any]] = {}

    async def list(self, *, query=None, parameters=None, partition_key=None):
        items = list(self._items.values())
        if partition_key:
            items = [i for i in items if i.get("_pk") == partition_key]
        return items

    async def get(self, item_id: str, partition_key: str):
        return self._items[item_id]

    async def upsert(self, item: dict[str, Any]):
        self._items[item["id"]] = item
        return item

    async def delete(self, item_id: str, partition_key: str):
        self._items.pop(item_id, None)
```

### What Does NOT Change

- `cosmos_helpers.py` — stays as-is. `CosmosDocumentStore` wraps it.
- All 4 routers — unchanged in this phase. They are migrated in Phase 4.
- `GraphBackend` Protocol — separate concern, not affected.

---

## Item 2: Extract Cosmos Config

### Current State

`config.py` (136 lines) mixes generic platform config with Cosmos-specific
connection strings:

```python
# Generic (should stay):
GRAPH_BACKEND = GraphBackendType(os.getenv("GRAPH_BACKEND", "cosmosdb"))
AI_SEARCH_NAME = os.getenv("AI_SEARCH_NAME", "")

# Cosmos-specific (should move):
COSMOS_NOSQL_ENDPOINT = os.getenv("COSMOS_NOSQL_ENDPOINT", "")
COSMOS_GREMLIN_ENDPOINT = os.getenv("COSMOS_GREMLIN_ENDPOINT", "")
COSMOS_GREMLIN_PRIMARY_KEY = os.getenv("COSMOS_GREMLIN_PRIMARY_KEY", "")
COSMOS_GREMLIN_DATABASE = os.getenv("COSMOS_GREMLIN_DATABASE", "networkgraph")
COSMOS_GREMLIN_GRAPH = os.getenv("COSMOS_GREMLIN_GRAPH", "topology")
COSMOS_NOSQL_DATABASE = os.getenv("COSMOS_NOSQL_DATABASE", "telemetry")
```

**Problem:** Anyone reading `config.py` to understand the app's config model
sees 50% Cosmos internals that are irrelevant for non-Cosmos backends.

### Target State

```python
# graph-query-api/adapters/__init__.py
# (empty — just marks it as a package)

# graph-query-api/adapters/cosmos_config.py
import os
from config import get_credential  # re-use shared credential

COSMOS_NOSQL_ENDPOINT = os.getenv("COSMOS_NOSQL_ENDPOINT", "")
COSMOS_NOSQL_DATABASE = os.getenv("COSMOS_NOSQL_DATABASE", "telemetry")
COSMOS_GREMLIN_ENDPOINT = os.getenv("COSMOS_GREMLIN_ENDPOINT", "")
COSMOS_GREMLIN_PRIMARY_KEY = os.getenv("COSMOS_GREMLIN_PRIMARY_KEY", "")
COSMOS_GREMLIN_DATABASE = os.getenv("COSMOS_GREMLIN_DATABASE", "networkgraph")
COSMOS_GREMLIN_GRAPH = os.getenv("COSMOS_GREMLIN_GRAPH", "topology")

TELEMETRY_REQUIRED_VARS = ["COSMOS_NOSQL_ENDPOINT"]
COSMOS_REQUIRED_VARS = ["COSMOS_GREMLIN_ENDPOINT", "COSMOS_GREMLIN_PRIMARY_KEY"]
```

### Files Modified

| File | Change |
|------|--------|
| `config.py` | Remove Cosmos constants (~6 lines), keep `get_credential()`, `GraphBackendType`, `ScenarioContext`, `AI_SEARCH_NAME` |
| `cosmos_helpers.py` | `from adapters.cosmos_config import COSMOS_NOSQL_ENDPOINT` (was: `from config import ...`) |
| `backends/cosmosdb.py` | `from adapters.cosmos_config import COSMOS_GREMLIN_ENDPOINT, COSMOS_GREMLIN_PRIMARY_KEY, COSMOS_GREMLIN_DATABASE, COSMOS_GREMLIN_GRAPH` (was: `from config import ...`) |
| `router_ingest.py` | `from adapters.cosmos_config import COSMOS_GREMLIN_ENDPOINT, COSMOS_GREMLIN_PRIMARY_KEY, COSMOS_GREMLIN_DATABASE, COSMOS_GREMLIN_GRAPH, COSMOS_NOSQL_ENDPOINT` (was: `from config import ...`) |

> **⚠️ Implementation trap:** `router_telemetry.py` imports `COSMOS_NOSQL_ENDPOINT`
> and `COSMOS_NOSQL_DATABASE` from `config`. These must move to importing from
> `adapters.cosmos_config`. Miss this and you get `ImportError` at startup.

---

## Item 3: Generic ScenarioContext Fields

### Current State

```python
@dataclass
class ScenarioContext:
    graph_name: str                  # "telco-noc-topology"
    gremlin_database: str            # "networkgraph"
    telemetry_database: str          # "telemetry"
    telemetry_container_prefix: str  # "telco-noc"
    prompts_database: str            # "prompts"
    prompts_container: str           # "telco-noc"
    backend_type: GraphBackendType
```

**Problem:** `gremlin_database` leaks implementation details. A Fabric backend
would have a `kusto_cluster` field, not a Gremlin database.

### Target State

```python
@dataclass
class ScenarioContext:
    graph_name: str                  # "telco-noc-topology"
    graph_database: str              # "networkgraph" (was gremlin_database)
    telemetry_database: str          # "telemetry" (unchanged)
    telemetry_container_prefix: str  # "telco-noc" (unchanged)
    prompts_database: str            # "prompts" (unchanged)
    prompts_container: str           # "telco-noc" (unchanged)
    backend_type: GraphBackendType   # will become str in Phase 7
```

### All References to Update

| File | Current Reference | New Reference |
|------|------------------|---------------|
| `config.py` ~L108 | `gremlin_database=COSMOS_GREMLIN_DATABASE` (inside `get_scenario_context()`) | `graph_database=COSMOS_GREMLIN_DATABASE` |
| `config.py` ~L78 | `gremlin_database: str` (field definition inside `ScenarioContext` dataclass) | `graph_database: str` |

> **Note:** Line numbers are approximate.
> The `@dataclass` decorator is at L78, the `gremlin_database` field is at L89,
> and `get_scenario_context()` starts at L97 (assignment ~L115).
> Always verify with `grep -n gremlin_database config.py`.

> **Note:** `backends/cosmosdb.py` uses `COSMOS_GREMLIN_DATABASE` (the constant)
> directly, not `ctx.gremlin_database`. Only `config.py` references the field.

> **⚠️ Safety note:** Use project-wide grep for `gremlin_database` before
> committing. An `AttributeError` from a missed reference will crash at
> runtime, not at import time.

**Verification:** `grep -rn "gremlin_database" graph-query-api/` should return
zero results after the rename. All endpoints that use `ScenarioContext` must be
tested: `POST /query/graph`, `POST /query/topology`, `POST /query/telemetry`.

---

## Item 4: Migrate NoSQL Routers to DocumentStore

### Migration Order

Migrate in order of increasing complexity:

| Order | Router | Lines | Complexity | Why This Order |
|-------|--------|-------|------------|----------------|
| 4a | `router_interactions.py` | 146 | Pure CRUD | Simplest — validates the Protocol works |
| 4b | `router_scenarios.py` | 220 | CRUD + validation | Slightly more logic (name validation, upsert-with-preserve) |
| 4c | `router_telemetry.py` | 144 | Query-only | Different pattern — SQL queries, not CRUD. Tests the `list()` method |
| 4d | `router_prompts.py` | 288 | CRUD + versioning + ARM | Most complex — auto-versioning, soft-delete, ARM container listing |

### 4a. Migrate `router_interactions.py`

#### Current Code Pattern

```python
# router_interactions.py — current
from cosmos_helpers import get_or_create_container

INTERACTIONS_DATABASE = "interactions"
INTERACTIONS_CONTAINER = "interactions"

def _get_interactions_container(*, ensure_created=True):
    return get_or_create_container(
        INTERACTIONS_DATABASE, INTERACTIONS_CONTAINER,
        "/scenario", ensure_created=ensure_created
    )

async def list_interactions(scenario=None, limit=50):
    container = _get_interactions_container(ensure_created=False)
    def _list():
        query = "SELECT * FROM c"
        params: list[dict] = []
        if scenario:
            query += " WHERE c.scenario = @scenario"
            params.append({"name": "@scenario", "value": scenario})
        query += " ORDER BY c.created_at DESC OFFSET 0 LIMIT @limit"
        params.append({"name": "@limit", "value": limit})
        if scenario:
            return list(container.query_items(
                query=query, parameters=params, partition_key=scenario))
        else:
            return list(container.query_items(
                query=query, parameters=params, enable_cross_partition_query=True))
    return await asyncio.to_thread(_list)
```

> **Note:** The current code already uses parameterized queries (`@scenario`,
> `@limit`) and partition-key-scoped reads when a scenario filter is provided.
> The migration must preserve this pattern — the new `DocumentStore.list()`
> must support parameterized queries and partition-key-scoped reads.

#### New Code Pattern

```python
# router_interactions.py — new
from stores import get_document_store, DocumentStore

INTERACTIONS_DATABASE = "interactions"
INTERACTIONS_CONTAINER = "interactions"

def _get_store() -> DocumentStore:
    return get_document_store(
        INTERACTIONS_DATABASE, INTERACTIONS_CONTAINER,
        "/scenario", ensure_created=True
    )

async def list_interactions(scenario=None, limit=50):
    store = _get_store()
    query = "SELECT * FROM c"
    params: list[dict] = []
    if scenario:
        query += " WHERE c.scenario = @scenario"
        params.append({"name": "@scenario", "value": scenario})
    query += " ORDER BY c.created_at DESC OFFSET 0 LIMIT @limit"
    params.append({"name": "@limit", "value": limit})
    items = await store.list(
        query=query,
        parameters=params,
        partition_key=scenario,  # scoped when filtering, None → cross-partition
    )
    return items
```

> **⚠️ Key change:** Router methods become `async` callers of the store.
> The store handles the `asyncio.to_thread()` wrapping. Existing Cosmos
> SDK calls are synchronous — the store wraps them in `to_thread()` to
> avoid blocking the event loop. **Always use parameterized queries** (`@param`)
> instead of f-string interpolation to prevent SQL injection.

#### All 4 Endpoints to Update

- `GET /query/interactions` → replace `container.query_items()` with `store.list()`
- `POST /query/interactions` → replace `container.upsert_item()` with `store.upsert()`
- `GET /query/interactions/{id}` → replace `container.read_item()` with `store.get()`
- `DELETE /query/interactions/{id}` → replace `container.delete_item()` with `store.delete()`

### 4b. Migrate `router_scenarios.py`

Same CRUD pattern as 4a, but note:

- `save_scenario()` does `read_item()` first to preserve `created_at`, then `upsert_item()`.
  This becomes `store.get()` + `store.upsert()`.
- `_get_scenarios_container()` uses `ensure_created=True`. Map to
  `get_document_store(..., ensure_created=True)`.

#### ⚠️ Critical: Genericize Resource Bindings in `save_scenario()`

`save_scenario()` (L148-158) currently hardcodes resource name derivation:

```python
# Current (hardcoded telco convention):
"resources": {
    "graph": f"{name}-topology",
    "telemetry_database": "telemetry",
    "telemetry_container_prefix": name,
    "runbooks_index": f"{name}-runbooks-index",
    "tickets_index": f"{name}-tickets-index",
    "prompts_database": "prompts",
    "prompts_container": name,
},
```

This must be changed to read from the scenario config when available:

```python
# New (config-driven with convention fallback):
def _derive_resources(name: str, config: dict | None = None) -> dict:
    """Build resource bindings from config, falling back to conventions."""
    ds = (config or {}).get("data_sources", {})
    graph_cfg = ds.get("graph", {}).get("config", {})
    search_cfg = ds.get("search_indexes", {})
    return {
        "graph": graph_cfg.get("graph", f"{name}-topology"),
        "telemetry_database": ds.get("telemetry", {}).get("config", {}).get("database", "telemetry"),
        "telemetry_container_prefix": name,
        "runbooks_index": search_cfg.get("runbooks", {}).get("index_name", f"{name}-runbooks-index"),
        "tickets_index": search_cfg.get("tickets", {}).get("index_name", f"{name}-tickets-index"),
        "prompts_database": "prompts",
        "prompts_container": name,
    }
```

> **Why this is critical:** The frontend reads `SavedScenario.resources` to set
> `X-Graph` headers and search index names. If these are derived incorrectly,
> all query-time routing fails. A Fabric scenario with a different graph naming
> convention would get the wrong `resources.graph` value persisted.

### 4c. Migrate `router_telemetry.py`

Different pattern — this router doesn't use `get_or_create_container()`.
Instead it directly creates `CosmosClient` and calls `query_items()`:

```python
# Current:
client = get_cosmos_client()
database = client.get_database_client(db_name)
container = database.get_container_client(container_name)
items = list(container.query_items(query=query, enable_cross_partition_query=True))
```

Migration: Replace with `DocumentStore.list(query=...)`. The container name
includes the scenario prefix: `f"{ctx.telemetry_container_prefix}-{req.container_name}"`.

> **⚠️ Implementation trap:** `_execute_cosmos_sql()` in `router_telemetry.py`
> has custom column-type inference logic (detecting numeric, boolean, null types)
> and excludes Cosmos system keys (`_rid`, `_self`, `_etag`, `_attachments`, `_ts`).
> This post-processing must be preserved in the router, not moved into the store.
> The store returns raw documents; the router transforms them.

> **⚠️ Container name abstraction:** The container name derivation
> `f"{ctx.telemetry_container_prefix}-{req.container_name}"` is Cosmos-specific.
> With a non-Cosmos telemetry backend, "container" may map to a KQL table or
> SQL schema.table. Abstract this by passing the logical collection name
> (`req.container_name`) to the `DocumentStore` and letting the store
> implementation handle any prefix/mapping internally. The router should NOT
> do the prefixing — move it into `CosmosDocumentStore.__init__` or add a
> `collection_prefix` constructor parameter.

### 4d. Migrate `router_prompts.py`

Most complex migration:

- `_get_prompts_container(scenario)` creates per-scenario containers. The store
  factory must accept dynamic container names.
- `_list_prompt_scenarios()` calls ARM `mgmt.sql_resources.list_sql_containers`
  to enumerate scenario containers. This is **not** a DocumentStore operation —
  it's infrastructure introspection. Options:
  (a) Keep the ARM call alongside the store (pragmatic, recommended)
  (b) Add a `list_containers()` method to DocumentStore (leaks infra concerns)
- Auto-versioning in `create_prompt()` uses `query_items()` to find max version,
  then deactivates old versions via `upsert_item()`. Map to `store.list()` + `store.upsert()`.
- Soft-delete sets `deleted=True` via `upsert_item()`. Map to `store.upsert()`.

---

## Item 5: Extract Blob + AI Search Services

### Current State

`router_ingest.py` (872 lines) mixes 4 concerns in one file:

1. Graph loading (Gremlin-specific)
2. Telemetry loading (Cosmos NoSQL-specific)
3. Knowledge file upload (Blob Storage — backend-agnostic)
4. Search index creation (AI Search — backend-agnostic)

Concerns 3 and 4 stay the same regardless of graph/telemetry backend.

### Target State

```python
# graph-query-api/services/__init__.py
# (empty)

# graph-query-api/services/blob_uploader.py (~80 lines)
async def upload_files_to_blob(
    container_name: str,
    files: dict[str, bytes],    # filename → content
    *,
    on_progress: Callable[[str], None] | None = None,
) -> str:
    """Upload files to Azure Blob Storage. Returns blob container URL."""
    ...

# graph-query-api/services/search_service.py
# (move search_indexer.py here, or re-export from it)
```

#### Extraction from `router_ingest.py`

The `_upload_knowledge_files()` function (currently nested inside upload handlers)
contains the blob upload logic. Extract it to `services/blob_uploader.py`:

```python
# Current (inside router_ingest.py, nested in run() coroutine):
blob_service = BlobServiceClient(
    account_url=f"https://{storage_account}.blob.core.windows.net",
    credential=get_credential()
)
blob_container = blob_service.get_container_client(container_name)
if not blob_container.exists():
    blob_container.create_container()
for file_path in files:
    blob_client = blob_container.get_blob_client(file_path.name)
    with open(file_path, "rb") as f:
        blob_client.upload_blob(f, overwrite=True)
```

> **⚠️ Implementation note:** The blob upload logic lives in a standalone async
> function `_upload_knowledge_files()` (~L571), which contains a nested sync
> helper `_upload_and_index()`. It is **not** a nested closure inside `run()`.
> Extract `_upload_knowledge_files()` directly; the nested sync helper can be
> inlined or moved alongside it. Pass `emit` (SSE progress callback) as an
> explicit parameter.

After extraction, `router_ingest.py` calls:
```python
from services.blob_uploader import upload_files_to_blob
await upload_files_to_blob(container_name, files, on_progress=emit)
```

`search_indexer.py` (226 lines) is already a separate module. It can stay where
it is or be moved to `services/search_indexer.py` — no functional change either way.

---

## Item 6: Add Ingest to GraphBackend Protocol

### Current State

`router_ingest.py` creates its **own** Gremlin client via `_gremlin_client()` and
`_gremlin_submit()` — duplicating the client management that `backends/cosmosdb.py`
already does. Graph loading bypasses the `GraphBackend` Protocol entirely.

### Target State

```python
# backends/__init__.py — extended Protocol
class GraphBackend(Protocol):
    async def execute_query(self, query: str, **kwargs) -> dict: ...
    async def get_topology(self, ...) -> dict: ...
    def close(self) -> None: ...

    # NEW:
    async def ingest(
        self,
        vertices: list[dict],
        edges: list[dict],
        *,
        graph_name: str,
        graph_database: str,
        on_progress: Callable[[str, int, int], None] | None = None,
    ) -> dict:
        """Load vertices and edges into the graph backend.

        Args:
            vertices: List of {label, properties} dicts
            edges: List of {label, source_id, target_id, properties} dicts
            graph_name: Target graph name
            graph_database: Target database name
            on_progress: Callback(message, current, total) for progress reporting

        Returns:
            {vertices_loaded: int, edges_loaded: int, errors: list[str]}
        """
        ...
```

#### `CosmosDBGremlinBackend.ingest()` Implementation

Move the following from `router_ingest.py` into `backends/cosmosdb.py`:
- `_gremlin_client()` (~15 lines) — Gremlin WebSocket client creation
- `_gremlin_submit()` (~20 lines) — batch submission with retry
- `_ensure_gremlin_graph()` (~30 lines) — ARM call to create graph resource
- Vertex/edge loading loop (~80 lines) — iterates schema, builds Gremlin queries, submits

**Total moved:** ~145 lines from `router_ingest.py` to `backends/cosmosdb.py`.

#### Schema-to-Dict Transformation Helpers

The `GraphBackend.ingest()` method takes flat `vertices: list[dict]` and
`edges: list[dict]`, but the current loading code works from `graph_schema.yaml`
definitions + CSV files. The router needs transformation helpers to bridge this:

```python
# In router_ingest.py — transformation layer (stays in router, not in backend)
def _prepare_vertices_from_schema(schema: dict, data_dir: Path) -> list[dict]:
    """Convert graph_schema.yaml vertex definitions + CSV data → flat dicts."""
    vertices = []
    for vdef in schema.get("vertices", []):
        csv_path = data_dir / vdef["csv_file"]
        rows = _read_csv(csv_path)
        for row in rows:
            vertices.append({
                "label": vdef["label"],
                "id": row[vdef["id_column"]],
                "partition_key": row.get(vdef.get("partition_key_column",
                                                  vdef["id_column"])),
                "properties": {
                    p["name"]: row.get(p["column"], "")
                    for p in vdef["properties"]
                },
            })
    return vertices

def _prepare_edges_from_schema(schema: dict, data_dir: Path) -> list[dict]:
    """Convert graph_schema.yaml edge definitions + CSV data → flat dicts."""
    edges = []
    for edef in schema.get("edges", []):
        csv_path = data_dir / edef["csv_file"]
        rows = _read_csv(csv_path)
        for row in rows:
            edges.append({
                "label": edef["label"],
                "source_id": row[edef["source_column"]],
                "target_id": row[edef["target_column"]],
                "properties": {
                    p["name"]: row.get(p["column"], "")
                    for p in edef.get("properties", [])
                },
            })
    return edges
```

> These helpers live in `router_ingest.py` (not in the backend) because they
> deal with scenario-specific file formats. The backend only sees generic dicts.

#### `MockGraphBackend.ingest()` — Stub

```python
async def ingest(self, vertices, edges, **kwargs):
    return {"vertices_loaded": len(vertices), "edges_loaded": len(edges), "errors": []}
```

> **⚠️ Implementation trap:** The current Gremlin ingest code uses SSE progress
> events extensively (`emit(f"Loading vertex {i}/{total}")`. The `on_progress`
> callback must be threaded through from the router to the backend's `ingest()`
> method. Design the callback signature carefully — the backend shouldn't know
> about SSE, just call the callback with progress info.

#### Progress Callback Adapter

The current `SSEProgress.emit()` signature is `(category: str, message: str,
percent: int)`, which differs from the `on_progress(message, current, total)`
signature on `GraphBackend.ingest()`. Bridge them in `router_ingest.py`:

```python
# In router_ingest.py, when calling backend.ingest():
def progress_adapter(message: str, current: int, total: int):
    pct = int(current / max(total, 1) * 100)
    progress.emit("graph", message, pct)

await backend.ingest(vertices, edges, graph_name=graph_name,
                     graph_database=graph_database,
                     on_progress=progress_adapter)
```

> `SSEProgress.emit()` is already thread-safe — it uses `asyncio.Queue` with
> `call_soon_threadsafe()`. The `ingest()` method runs in `asyncio.to_thread()`,
> so the callback is called from a background thread. This is safe.

---

## Item 7: Backend Registry

### Current State

```python
# backends/__init__.py — current dispatch
def get_backend_for_graph(graph_name, backend_type=None):
    bt = backend_type or GRAPH_BACKEND
    cache_key = f"{bt.value}:{graph_name}"
    with _backend_lock:
        if cache_key not in _backend_cache:
            if bt == GraphBackendType.COSMOSDB:
                from .cosmosdb import CosmosDBGremlinBackend
                _backend_cache[cache_key] = CosmosDBGremlinBackend(graph_name=graph_name)
            elif bt == GraphBackendType.MOCK:
                from .mock import MockGraphBackend
                _backend_cache[cache_key] = MockGraphBackend()
            else:
                raise ValueError(...)
```

**Problem:** Adding a new backend requires modifying `if/elif` dispatch code.

### Target State

```python
# backends/__init__.py — registry pattern
_backend_registry: dict[str, type[GraphBackend]] = {}

def register_backend(name: str, cls: type[GraphBackend]) -> None:
    _backend_registry[name] = cls

def get_backend_for_graph(graph_name: str, backend_type: str | None = None) -> GraphBackend:
    bt = backend_type or GRAPH_BACKEND
    cache_key = f"{bt}:{graph_name}"
    with _backend_lock:
        if cache_key not in _backend_cache:
            if bt not in _backend_registry:
                raise ValueError(f"Unknown backend: {bt}. Available: {list(_backend_registry)}")
            _backend_cache[cache_key] = _backend_registry[bt](graph_name=graph_name)
    return _backend_cache[cache_key]

# Auto-registration at module load:
from .cosmosdb import CosmosDBGremlinBackend
from .mock import MockGraphBackend
register_backend("cosmosdb", CosmosDBGremlinBackend)
register_backend("mock", MockGraphBackend)
```

#### `GraphBackendType` Enum → String

In `config.py`, change:
```python
# Old:
class GraphBackendType(str, Enum):
    COSMOSDB = "cosmosdb"
    MOCK = "mock"
GRAPH_BACKEND = GraphBackendType(os.getenv("GRAPH_BACKEND", "cosmosdb"))

# New:
GRAPH_BACKEND: str = os.getenv("GRAPH_BACKEND", "cosmosdb")
```

All references to `GraphBackendType.COSMOSDB` become `"cosmosdb"` string
comparisons. `ScenarioContext.backend_type` changes from `GraphBackendType` to `str`.

> **⚠️ Migration checklist — `.value` removal:** After removing the enum,
> all `.value` calls on backend_type become `AttributeError` on `str`. **Six
> call sites must be updated:**
>
> | File | Line | Change |
> |------|------|--------|
> | `main.py` | L67 | `GRAPH_BACKEND.value` → `GRAPH_BACKEND` (warning log) |
> | `main.py` | L76 | `GRAPH_BACKEND.value` → `GRAPH_BACKEND` (startup log) |
> | `main.py` | L85 | `GRAPH_BACKEND.value` → `GRAPH_BACKEND` (FastAPI description) |
> | `main.py` | L233 | `GRAPH_BACKEND.value` → `GRAPH_BACKEND` (health endpoint) |
> | `router_graph.py` | L51 | `ctx.backend_type.value` → `ctx.backend_type` (query log) |
> | `backends/__init__.py` | L97 | `bt.value` → `bt` (cache key) |
>
> **Verify:** `grep -rn "\.value" graph-query-api/ | grep -i "backend"` should return zero results after the change.

---

## Item 8: Config-Driven Agent Provisioner

### Current State

`agent_provisioner.py` (282 lines) hardcodes exactly 5 agents:

```python
AGENT_NAMES = [
    "GraphExplorerAgent", "TelemetryAgent", "RunbookKBAgent",
    "HistoricalTicketAgent", "Orchestrator",
]
```

`provision_all()` creates them in a hardcoded sequence with hardcoded tool
bindings:
- GraphExplorer → `OpenApiTool` (graph query)
- Telemetry → `OpenApiTool` (telemetry query)
- RunbookKB → `AzureAISearchTool` (runbooks index)
- HistoricalTicket → `AzureAISearchTool` (tickets index)
- Orchestrator → `ConnectedAgentTool` to all 4

### Target State

The provisioner reads agent definitions from the scenario config YAML:

```yaml
# scenario.yaml — agents section
agents:
  - name: "GraphExplorerAgent"
    display_name: "Network Graph Explorer"  # human-readable label for UI (optional, defaults to name)
    role: "graph_explorer"
    model: "gpt-4.1"
    instructions_file: "prompts/graph_explorer/"  # composable fragments
    compose_with_connector: true  # auto-selects language_gremlin.md etc.
    tools:
      - type: "openapi"
        spec_template: "graph"    # maps to openapi/ template
        keep_path: "/query/graph"

  - name: "TelemetryAgent"
    display_name: "Telemetry Analyst"
    role: "telemetry"
    model: "gpt-4.1"
    instructions_file: "prompts/foundry_telemetry_agent_v2.md"
    tools:
      - type: "openapi"
        spec_template: "telemetry"
        keep_path: "/query/telemetry"

  - name: "RunbookKBAgent"
    display_name: "Runbook Knowledge Base"
    role: "runbook"
    model: "gpt-4.1"
    instructions_file: "prompts/foundry_runbook_kb_agent.md"
    tools:
      - type: "azure_ai_search"
        index_key: "runbooks"  # references data_sources[].search_indexes[]

  - name: "HistoricalTicketAgent"
    display_name: "Historical Ticket Search"
    role: "ticket"
    model: "gpt-4.1"
    instructions_file: "prompts/foundry_historical_ticket_agent.md"
    tools:
      - type: "azure_ai_search"
        index_key: "tickets"

  - name: "Orchestrator"
    display_name: "Investigation Orchestrator"
    role: "orchestrator"
    model: "gpt-4.1"
    instructions_file: "prompts/foundry_orchestrator_agent.md"
    is_orchestrator: true
    connected_agents: ["GraphExplorerAgent", "TelemetryAgent", "RunbookKBAgent", "HistoricalTicketAgent"]
```

> **`display_name` field:** Optional human-readable label for UI display. If
> omitted, defaults to `name`. Surfaced in `AgentTimeline` step cards,
> `ResourceVisualizer` node labels, and `StepCard` headings. The technical
> `name` is shown in tooltips or as a subtitle. This keeps config identifiers
> developer-friendly while the UI stays readable for operators.

#### New `provision_from_config()` Method

```python
def provision_from_config(
    self,
    config: dict,               # parsed scenario.yaml
    graph_query_api_uri: str,
    search_connection_id: str,
    graph_name: str,
    *,
    force: bool = True,
    on_progress: Callable | None = None,
) -> dict:
    """Provision N agents from scenario config."""
    agent_defs = config["agents"]
    created_agents = {}

    # Phase 1: Create sub-agents (non-orchestrators)
    for agent_def in agent_defs:
        if agent_def.get("is_orchestrator"):
            continue
        tools, tool_resources = self._build_tools(agent_def, config,
                                                   graph_query_api_uri,
                                                   search_connection_id, graph_name)
        prompt = self._load_prompt(agent_def, config)
        create_kwargs = dict(
            model=agent_def["model"],
            name=agent_def["name"],
            instructions=prompt,
            tools=tools,
        )
        if tool_resources:
            create_kwargs["tool_resources"] = tool_resources
        agent = self._client.agents.create_agent(**create_kwargs)
        created_agents[agent_def["name"]] = agent.id

    # Phase 2: Create orchestrators with ConnectedAgentTool
    for agent_def in agent_defs:
        if not agent_def.get("is_orchestrator"):
            continue
        connected_tools = []
        for name in agent_def.get("connected_agents", []):
            ct = ConnectedAgentTool(
                id=created_agents[name],
                name=name,
                description=f"Delegate to {name}",
            )
            connected_tools.extend(ct.definitions)  # .definitions returns dicts
        prompt = self._load_prompt(agent_def, config)
        agent = self._client.agents.create_agent(
            model=agent_def["model"],
            name=agent_def["name"],
            instructions=prompt,
            tools=connected_tools,
        )
        created_agents[agent_def["name"]] = agent.id

    return created_agents
```

#### `_load_prompt()` — Prompt Resolver

```python
def _load_prompt(self, agent_def: dict, config: dict) -> str:
    """Load and compose the agent's instruction prompt.

    Handles two patterns declared in scenario YAML:
    1. Single file: instructions_file points to a .md file
    2. Composed directory: instructions_file points to a directory,
       compose_with_connector=true triggers language fragment selection.

    Args:
        agent_def: Single agent entry from config["agents"]
        config: Full parsed scenario config (for connector lookup)

    Returns:
        Composed prompt string with placeholders NOT yet expanded
        (expansion happens in the caller after all agents are created).
    """
    path = agent_def["instructions_file"]

    if not agent_def.get("compose_with_connector", False):
        # Single file — read from prompts Cosmos container or Blob
        return self._read_prompt_file(path)

    # Composed directory — read all .md files, auto-select language fragment
    connector = _resolve_connector_for_agent(agent_def, config)
    # connector is e.g. "cosmosdb-gremlin" → language file is "language_gremlin.md"
    # Mapping: strip prefix, take last segment after hyphen
    language_suffix = connector.split("-")[-1]  # "gremlin", "nosql", "kusto"
    language_file = f"language_{language_suffix}.md"

    fragments = []
    prompt_files = self._list_prompt_files(path)  # returns sorted list of .md filenames
    for fname in prompt_files:
        # Skip non-matching language files (e.g., skip language_kusto.md
        # when connector is cosmosdb-gremlin)
        if fname.startswith("language_") and fname != language_file:
            continue
        fragments.append(self._read_prompt_file(f"{path}{fname}"))

    return "\n\n---\n\n".join(fragments)


def _resolve_connector_for_agent(agent_def: dict, config: dict) -> str:
    """Determine which data source connector an agent uses.

    Looks at the agent's tools to find the first tool that references a
    data source, then returns that data source's connector type.

    Fallback: 'cosmosdb-gremlin' (the only connector today).
    """
    ds = config.get("data_sources", {})
    for tool_def in agent_def.get("tools", []):
        if tool_def["type"] == "openapi":
            template = tool_def.get("spec_template", "")
            if template == "graph" and "graph" in ds:
                return ds["graph"].get("connector", "cosmosdb-gremlin")
            if template == "telemetry" and "telemetry" in ds:
                return ds["telemetry"].get("connector", "cosmosdb-nosql")
    return "cosmosdb-gremlin"
```

> **Implementation note:** `_read_prompt_file()` and `_list_prompt_files()` read
> from the prompts Cosmos container (where prompts are stored after upload via
> `POST /query/scenario/upload`). The container has documents with `filename` and
> `content` fields, partitioned by scenario name. `_list_prompt_files(path)` queries
> for all documents whose `filename` starts with the directory prefix.

#### `_build_tools()` — Tool Factory

```python
def _build_tools(self, agent_def, config, api_uri, search_conn_id, graph_name):
    """Build tool definitions and resources for an agent.

    Returns:
        (tool_definitions, tool_resources): tool_definitions is a list of dicts
        from .definitions; tool_resources is the AzureAISearchTool.resources
        object (or None if no search tools).
    """
    tool_definitions = []
    tool_resources = None
    for tool_def in agent_def.get("tools", []):
        if tool_def["type"] == "openapi":
            spec = _load_openapi_spec(api_uri, tool_def["spec_template"],
                                       graph_name=graph_name,
                                       keep_path=tool_def.get("keep_path"))
            tool = OpenApiTool(
                name=f"{tool_def['spec_template']}_query",
                spec=spec,
                description=tool_def.get("description", ""),
                auth=OpenApiAnonymousAuthDetails(),
            )
            tool_definitions.extend(tool.definitions)  # .definitions → list[dict]
        elif tool_def["type"] == "azure_ai_search":
            index_cfg = config["data_sources"]["search_indexes"][tool_def["index_key"]]
            index_name = index_cfg["index_name"]  # e.g. "telco-noc-runbooks-index"
            search_tool = AzureAISearchTool(
                index_connection_id=search_conn_id,
                index_name=index_name,
            )
            tool_definitions.extend(search_tool.definitions)  # .definitions → list[dict]
            tool_resources = search_tool.resources              # capture for create_agent()
    return tool_definitions, tool_resources
```

> **⚠️ Search connection ID:** `search_conn_id` is currently hardcoded as
> `"aisearch-connection"` in `agent_provisioner.py`. For full genericization,
> this should be configurable — either as an env var (`AI_SEARCH_CONNECTION_ID`)
> or a field in `scenario.yaml` (`search_connection_id: "aisearch-connection"`).
> Default to the current hardcoded value for backward compatibility.

### `api/app/routers/config.py` Changes

`POST /api/config/apply` currently hardcodes 5 agents. Change to:

```python
# Current:
defaults = {
    "orchestrator": "You are an investigation orchestrator.",
    "graph_explorer": "You are a graph explorer agent.",
    ...
}
provisioner.provision_all(model=..., prompts=defaults, ...)

# New:
scenario_config = await fetch_scenario_config(req.prompt_scenario)
provisioner.provision_from_config(config=scenario_config, ...)
```

#### ⚠️ Critical: `fetch_scenario_config()` Definition

This function is the linchpin of config-driven provisioning. Without it,
Phases 8, 10, 12, and 13 cannot be implemented.

**Config persistence model:** The full scenario YAML is stored in two places:
1. **Upload time:** `POST /query/scenario/upload` parses the tarball's
   `scenario.yaml` and stores it as a JSON document in the `scenarios/configs`
   Cosmos container (partition key: scenario name).
2. **Runtime:** `fetch_scenario_config()` reads from this container.

```python
# graph-query-api/config_store.py  (new file — created in Phase 8)

_config_store = get_document_store(
    "scenarios", "configs", "/scenario_name", ensure_created=True
)

async def fetch_scenario_config(scenario_name: str) -> dict:
    """Fetch the full scenario configuration from Cosmos.

    Returns the parsed scenario.yaml content stored during upload.
    Raises ValueError if no config exists for the scenario.

    This is an async function — DocumentStore.get() is async.
    Callers must `await fetch_scenario_config(...)` accordingly.
    """
    try:
        doc = await _config_store.get(scenario_name, partition_key=scenario_name)
        return doc.get("config", {})
    except Exception:
        raise ValueError(
            f"No scenario config found for '{scenario_name}'. "
            f"Upload the scenario with a scenario.yaml that includes "
            f"an 'agents' section."
        )


async def save_scenario_config(scenario_name: str, config: dict) -> None:
    """Persist the full scenario YAML as a Cosmos document.

    Called during POST /query/scenario/upload after parsing the tarball.

    Uses datetime.now(timezone.utc) instead of deprecated utcnow().
    """
    await _config_store.upsert({
        "id": scenario_name,
        "scenario_name": scenario_name,
        "config": config,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
```

**Ingest integration:** In `router_ingest.py`, the graph/telemetry/search upload
flow already parses `scenario.yaml` (via `manifest = yaml.safe_load(...)`). After
parsing, add:

```python
# In router_ingest.py, after parsing scenario.yaml:
if "agents" in manifest:
    await save_scenario_config(scenario_name, manifest)
```

This ensures the config is available for `fetch_scenario_config()` at provisioning
time without requiring a separate upload step.

> **Backward compatibility:** If `fetch_scenario_config()` raises (no config stored),
> `apply_config()` falls back to the old `provision_all()` path. This makes the
> migration gradual — scenarios uploaded before this change still work.

> **⚠️ Implementation note:** `provision_all()` should be KEPT alongside
> `provision_from_config()` for backward compatibility during migration. It becomes 
> a wrapper that constructs the equivalent config dict and calls `provision_from_config()`.

---

## Item 9: OpenAPI Spec Templating

### Current State

Two static YAML files:
- `openapi/cosmosdb.yaml` — Gremlin-specific descriptions
- `openapi/mock.yaml` — mock-specific descriptions

Placeholders `{base_url}` and `{graph_name}` are replaced via string substitution.
Query language descriptions are **baked into** the YAML (e.g., "Execute a Gremlin query...").

### Target State

OpenAPI specs become connector-aware templates. The config-driven approach:

**Option A (Recommended): Connector-specific templates with config injection**

Each connector provides its own OpenAPI template with appropriate query language
descriptions. The variables expand at provisioning time.

```yaml
# openapi/templates/graph.yaml.j2
paths:
  /query/graph:
    post:
      parameters:
        - name: X-Graph
          in: header
          schema:
            enum: ["{{ graph_name }}"]
      requestBody:
        schema:
          properties:
            query:
              type: string
              description: |
                {{ query_language_description }}
```

Variable sources:
```python
# Per connector:
CONNECTOR_OPENAPI_VARS = {
    "cosmosdb": {
        "query_language_description": "A Gremlin traversal query string. Use g.V()...",
    },
    "mock": {
        "query_language_description": "Query the topology graph (offline mock mode).",
    },
    "fabric": {
        "query_language_description": "A KQL query against Kusto...",
    },
}
```

> **⚠️ Decision point:** Jinja2 is not currently a dependency. Options:
> (a) Add `jinja2` to `pyproject.toml` — cleanest, 1 extra dependency
> (b) Use Python's `str.format_map()` — zero dependencies but **fragile** —
>     any literal `{...}` in OpenAPI YAML (e.g., JSON Schema examples in
>     description fields) causes `KeyError`
> (c) Keep current `.replace()` approach with more placeholders — safest

**Recommendation:** Keep using `.replace()` per-placeholder. OpenAPI YAML specs
contain literal `{braces}` in JSON Schema examples (`{"type": "string"}`),
which break `format_map()`. The `.replace()` approach is strictly safer:

```python
# Using .replace() per-placeholder instead of str.format_map() because
# OpenAPI YAML files may contain literal {braces} in JSON Schema examples.
raw = raw.replace("{base_url}", api_uri.rstrip("/"))
raw = raw.replace("{graph_name}", graph_name)
raw = raw.replace("{query_language_description}",
                  connector_vars.get("query_language_description", ""))
```

---

## Item 10: Config-Driven Prompt System

### Current State

Prompt-to-agent mapping is hardcoded:

```python
PROMPT_AGENT_MAP = {
    "foundry_orchestrator_agent.md": "orchestrator",
    "orchestrator.md": "orchestrator",
    "foundry_telemetry_agent_v2.md": "telemetry",
    ...
}
```

GraphExplorer prompts are composed from 3 hardcoded files:
```
graph_explorer/core_instructions.md + core_schema.md + language_gremlin.md
```

### Target State

Prompt configuration moves into the scenario YAML:

```yaml
# In scenario.yaml agents section:
agents:
  - name: "GraphExplorerAgent"
    instructions_file: "prompts/graph_explorer/"
    compose_with_connector: true
    # When compose_with_connector is true, the system:
    # 1. Reads all .md files in the directory
    # 2. Auto-selects language_{connector}.md based on the agent's data source connector
    # 3. Joins them with \n\n---\n\n

  - name: "TelemetryAgent"
    instructions_file: "prompts/foundry_telemetry_agent_v2.md"
    # Single file — no composition
```

The prompt ingest endpoint (`POST /query/scenario/upload` for prompts) reads
the agent definitions from scenario config to map files to agents, instead of
using `PROMPT_AGENT_MAP`.

### Placeholder Expansion

Currently only `{graph_name}` and `{scenario_prefix}` are expanded. The full
set of supported placeholders:

| Placeholder | Value Source | Expansion Time |
|-------------|-------------|----------------|
| `{graph_name}` | `ScenarioContext.graph_name` | Provisioning |
| `{scenario_prefix}` | Scenario name | Provisioning |
| `{query_language}` | Connector metadata | Provisioning |
| `{graph_database}` | `ScenarioContext.graph_database` | Provisioning |
| `{telemetry_container_prefix}` | `ScenarioContext.telemetry_container_prefix` | Provisioning |

Expansion happens in `api/app/routers/config.py` at provisioning time (same
as current behavior, just with more placeholders).

---

## Item 11: Frontend Genericization

### 11a. ScenarioContext — Config-Specified Resources

#### Current State

```typescript
// ScenarioContext.tsx — hardcoded derivation
const deriveGraph = (name: string | null) => name ? `${name}-topology` : 'topology';
const deriveRunbooks = (name: string | null) => name ? `${name}-runbooks-index` : 'runbooks-index';
const deriveTickets = (name: string | null) => name ? `${name}-tickets-index` : 'tickets-index';
```

#### Target State

```typescript
// Use exact names from SavedScenario.resources when available
const setActiveScenario = useCallback((name: string | null, scenario?: SavedScenario) => {
  setScenarioName(name);
  if (scenario?.resources) {
    // Use exact resource names from saved scenario
    setActiveGraph(scenario.resources.graph);
    setActiveRunbooksIndex(scenario.resources.runbooks_index);
    setActiveTicketsIndex(scenario.resources.tickets_index);
    setActivePromptSet(scenario.resources.prompts_container ?? name ?? '');
  } else if (name) {
    // Fallback: derive from conventions (backward compatibility)
    setActiveGraph(`${name}-topology`);
    setActiveRunbooksIndex(`${name}-runbooks-index`);
    setActiveTicketsIndex(`${name}-tickets-index`);
    setActivePromptSet(name);
  }
}, []);
```

> **⚠️ Backward compatibility:** The `SavedScenario.resources` field already
> exists in the type definition. Scenarios saved before this change have
> convention-based names that match the derivation fallback. No migration needed.

### 11b. graphConstants.ts — Remove Telco-Specific Defaults

#### Current State

```typescript
export const NODE_COLORS: Record<string, string> = {
  CoreRouter: '#38BDF8', AggSwitch: '#FB923C', BaseStation: '#A78BFA',
  TransportLink: '#3B82F6', MPLSPath: '#C084FC', Service: '#CA8A04',
  SLAPolicy: '#FB7185', BGPSession: '#F472B6',
};
```

#### Target State

```typescript
// Empty maps — all colors come from scenario graph_styles or auto-hash
export const NODE_COLORS: Record<string, string> = {};
export const NODE_SIZES: Record<string, number> = {};
```

The color resolution chain in `useNodeColor.ts` already handles this:
user override → `scenarioNodeColors` → `NODE_COLORS` → auto-hash.
Emptying `NODE_COLORS` just removes the telco-specific fallback; the
auto-hash ensures every label always gets a color.

> **⚠️ Telco-noc compatibility:** Add the telco-noc colors to the
> telco-noc `scenario.yaml` `graph_styles` section so they're loaded
> via `scenarioNodeColors` instead of hardcoded constants.

### 11c. SettingsModal — Config-Aware Data Sources

The current `SettingsModal` assumes 3 data source types (graph, runbooks, tickets).
With config-driven scenarios, it should dynamically render data source bindings
based on what the scenario config declares.

This is a **lower-priority** change — the modal already works for the current
structure. The main change is making the data source section read-only when a
saved scenario is active (bindings come from config, not manual selection).

### 11d. Stub Agents — Config-Driven Names

#### Current State

```python
# api/app/routers/alert.py
agents = ["TelemetryAgent", "GraphExplorerAgent", "RunbookKBAgent", "HistoricalTicketAgent"]
```

```python
# api/app/routers/agents.py — _STUB_AGENTS hardcodes 5 telco-specific names
_STUB_AGENTS = [
    {"name": "Orchestrator", "id": "stub-orchestrator", "status": "stub"},
    {"name": "GraphExplorerAgent", "id": "stub-graph", "status": "stub"},
    {"name": "TelemetryAgent", "id": "stub-telemetry", "status": "stub"},
    {"name": "RunbookKBAgent", "id": "stub-runbook", "status": "stub"},
    {"name": "HistoricalTicketAgent", "id": "stub-ticket", "status": "stub"},
]
```

#### Target State

Both files read agent names dynamically:

```python
# Shared helper (e.g., in api/app/agent_helpers.py):
import json
from pathlib import Path

AGENT_IDS_FILE = Path(__file__).parent.parent / "agent_ids.json"

def _load_agent_names() -> list[str]:
    """Load provisioned agent names from agent_ids.json.
    Returns empty list if not provisioned yet."""
    if AGENT_IDS_FILE.exists():
        with open(AGENT_IDS_FILE) as f:
            ids = json.load(f)
            return list(ids.keys())
    return []

def _load_stub_agents() -> list[dict]:
    """Build stub agent list from agent_ids.json.
    Returns empty list if not provisioned yet.

    ⚠️ Must include 'status' key — existing frontend/consumers
    expect {name, id, status} per the current _STUB_AGENTS shape.
    """
    if AGENT_IDS_FILE.exists():
        with open(AGENT_IDS_FILE) as f:
            ids = json.load(f)
            return [{"name": name, "id": aid, "status": "provisioned"}
                    for name, aid in ids.items()]
    return []
```

```python
# api/app/routers/alert.py — updated:
agents = _load_agent_names()  # reads agent_ids.json, returns [] if not found

# api/app/routers/agents.py — updated:
@router.get("/agents")
async def list_agents():
    return _load_stub_agents()  # dynamic, not hardcoded
```

> **⚠️ Note:** `agent_ids.json` is written by `agent_provisioner.py` after
> successful provisioning. If no scenario has been provisioned, both endpoints
> return empty lists instead of hardcoded telco names.

### 11e. First-Run Empty State

Phase 0 removes all pre-created scenario-specific resources. A fresh deployment
has zero scenarios — they must be uploaded. Without an onboarding flow, a user
hitting the app after `azd up` sees an empty Investigate tab with no guidance.

**Implementation:**
- Add a **first-run empty state** to the Investigate tab: a centered card with
  "No scenario loaded" heading, brief explanation, and a primary CTA button
  ("Upload Scenario") that opens the Settings modal on the Upload tab.
- Show this state when `activeScenario` is `null` and the saved scenarios list
  is empty.
- Show a subtle **guided steps** indicator: "1. Upload data → 2. Select
  scenario → 3. Provision agents → 4. Investigate" — displayed inline until
  the user completes provisioning for the first time.

### 11f. ARIA Tab Semantics

The 3-tab navigation (`TabBar.tsx`) uses `<button>` elements without
`role="tablist"`, `role="tab"`, or `aria-selected` attributes. This is a WCAG
2.1 Level A failure (4.1.2 Name, Role, Value). Fix during Phase 11:

```tsx
// TabBar.tsx — wrap buttons in tablist container
<div role="tablist" aria-label="Main navigation">
  {tabs.map(tab => (
    <button
      key={tab.id}
      role="tab"
      aria-selected={activeTab === tab.id}
      aria-controls={`tabpanel-${tab.id}`}
      onClick={() => onTabChange(tab.id)}
    >
      {tab.label}
    </button>
  ))}
</div>

// Tab content panel:
<div role="tabpanel" id={`tabpanel-${activeTab}`} aria-labelledby={activeTab}>
  {children}
</div>
```

This is ~10 lines of changes with no visual impact.

### 11g. Provisioning Discoverability

Agent provisioning is critical — without it, investigations don't work — but
it's buried in Settings → Data Sources tab → scroll → button. New users may
not discover it.

**Implementation:**
- When a scenario is active but agents are not provisioned (or are stale),
  show a **persistent banner** in the Investigate tab: "Agents need
  provisioning for this scenario" with a primary "Provision Now" button that
  triggers provisioning directly.
- After switching scenarios, auto-check if agents match the scenario config.
  If not, show the banner automatically.
- The existing `ProvisioningBanner` component can be extended to also serve
  as a prompt when provisioning is *needed*, not just during provisioning.

### 11h. Upload Progress Visibility

The ingest pipeline is multi-stage (parse YAML → validate config → create
Cosmos containers → load data → create search indexes). The current UI shows
a single progress bar per upload card with generic error messages.

**Implementation:**
- Surface the SSE `category` field as a **stage label** above the progress
  bar (e.g., "Validating config…", "Creating graph resource…", "Loading
  vertices 42/300…", "Indexing documents…").
- On validation failure (Phase 8's `ConfigValidationError`), display the
  specific error messages from `validate_scenario_config()` in a scrollable
  error panel within the upload card — not just generic "Error".
- The backend already emits granular SSE events with `category` and `message`;
  the frontend just needs to render them.

---

## Item 12: Resource Visualizer Backend

### Current State

The Resource Visualizer frontend is **already implemented** with mock data
showing a **full architecture diagram** — agents, tools, data sources,
blob containers, Cosmos databases, and Azure infrastructure services
(Foundry, Storage, Cosmos accounts, AI Search, Container App).

**Mock data:** 28 nodes, 37 edges across 6 layers in `hooks/useResourceGraph.ts`.
**Node types:** 12 types — `orchestrator`, `agent`, `tool`, `datasource`,
`search-index`, `foundry`, `storage`, `cosmos-account`, `search-service`,
`container-app`, `blob-container`, `cosmos-database`.
**Edge types:** 8 types — `delegates_to`, `uses_tool`, `queries`,
`stores_in`, `hosted_on`, `indexes_from`, `runs_on`, `contains`.

The graph visualizes:
1. **Agent layer** — orchestrator → sub-agents (delegation flow)
2. **Tool layer** — agents → tools (OpenAPI, AzureAISearch)
3. **Data source layer** — tools → data sources (graph, telemetry, search indexes)
4. **Upload/ingest layer** — blob containers → data sources (indexing + ingestion pipeline)
5. **Database layer** — Cosmos databases, blob containers → infrastructure
6. **Infrastructure layer** — Azure services (Foundry, Cosmos accounts, Storage, AI Search, Container App)

**Excluded:** VPNs, private endpoints, NSGs, DNS zones — these are networking
concerns that don't appear in the scenario YAML.

**Problem:** The frontend has no real data source. It needs a backend endpoint
that derives the graph from scenario config + Azure resource metadata.

### Target State

#### Backend: `GET /api/config/resources`

Returns the scenario's full resource graph including infrastructure:

```python
# api/app/routers/config.py — new endpoint

@router.get("/config/resources")
async def get_resource_graph(scenario: str | None = None):
    """Return the full architecture graph for the resource visualizer.

    Combines:
    1. Agent/tool/data-source graph from scenario config YAML
    2. Infrastructure nodes from env vars (Cosmos accounts, Storage, etc.)
    3. Data-flow edges showing upload → ingest → query pipeline
    """
    config = _load_scenario_config(scenario)
    return _build_resource_graph(config)

def _build_resource_graph(config: dict) -> dict:
    nodes = []
    edges = []

    # ── Agent nodes ──────────────────────────────────────────────────────
    for agent in config.get("agents", []):
        node_type = "orchestrator" if agent.get("is_orchestrator") else "agent"
        agent_id = agent["name"].lower().replace(" ", "-")
        nodes.append({
            "id": agent_id,
            "label": agent.get("display_name", agent["name"]),
            "type": node_type,
            "meta": {
                "model": agent.get("model", ""),
                "role": agent.get("role", ""),
                "name": agent["name"],  # technical name for tooltips
                "prompt_preview": "",   # populated from prompts store
                "provisioned": False,    # populated from agent_ids.json
            },
        })

        # Agent tools → tool nodes + uses_tool edges
        for tool in agent.get("tools", []):
            tool_id = _tool_node_id(tool)
            nodes.append({"id": tool_id, "label": _tool_label(tool), "type": "tool", "meta": tool})
            edges.append({"source": agent_id, "target": tool_id, "type": "uses_tool", "label": "uses"})

        # ConnectedAgentTool → delegates_to edges
        for sub in agent.get("connected_agents", []):
            edges.append({"source": agent_id, "target": sub.lower().replace(" ", "-"),
                          "type": "delegates_to", "label": "delegates"})

    # ── Data source + infrastructure nodes ───────────────────────────────
    ds = config.get("data_sources", {})
    _add_data_source_nodes(ds, nodes, edges)
    _add_infrastructure_nodes(nodes, edges)

    # Deduplicate nodes by id
    seen = set()
    unique = []
    for n in nodes:
        if n["id"] not in seen:
            seen.add(n["id"])
            unique.append(n)

    return {"nodes": unique, "edges": edges}
```

#### Frontend: Swap Mock for Real API

```typescript
// hooks/useResourceGraph.ts — updated
type ResourceState = 'loading' | 'ready' | 'error' | 'empty';

export function useResourceGraph() {
  const { activeScenario } = useScenarioContext();
  const [data, setData] = useState({ nodes: [], edges: [] });
  const [state, setState] = useState<ResourceState>('empty');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!activeScenario) {
      setData({ nodes: [], edges: [] });
      setState('empty');
      return;
    }
    setState('loading');
    fetch(`/api/config/resources?scenario=${activeScenario}`)
      .then(r => {
        if (!r.ok) throw new Error(`API returned ${r.status}`);
        return r.json();
      })
      .then(d => { setData(d); setState('ready'); setErrorMsg(null); })
      .catch(err => {
        setData({ nodes: [], edges: [] });
        setState('error');
        setErrorMsg(err.message);
      });
  }, [activeScenario]);

  return { ...data, state, errorMsg };
}
```

**State-driven rendering in `ResourceVisualizer.tsx`:**
- **`loading`** — Show a skeleton/spinner overlay while fetching.
- **`error`** — Show an error message with a "Retry" button. Do NOT fall
  back to mock data in production — silent mock fallback hides real failures.
- **`empty`** — Show "Select a scenario to view its resource graph" when
  `activeScenario` is null.
- **`ready`** — Render the force graph as normal.

Mock data fallback is only used when `GRAPH_BACKEND=mock` or in development
builds (e.g., `import.meta.env.DEV`).

> **`meta` field design note:** The `meta` object on each node should contain
> enough data to power a future detail panel (slide-in sidebar on node click)
> without extra API calls. Agent nodes include `model`, `role`, `name`,
> `prompt_preview`, `provisioned`. Data source nodes include `connector`,
> `database`, `container`. Tool nodes include `type`, `spec_template`,
> `endpoint`. This schema should be established now even if the detail panel
> is built later.

---

## Item 13: Migrate telco-noc to Config

### Current State

The telco-noc scenario uses hardcoded agent definitions, prompt mappings, and
tool bindings scattered across `agent_provisioner.py`, `api/app/routers/config.py`,
and `router_ingest.py`. The current `scenario.yaml` (v1.0) uses the old `cosmos:`
and `search_indexes:` schema, has no `agents:` section, and does not explicitly
declare which Azure resources to create.

Additionally, the Bicep infrastructure pre-creates scenario-specific resources
(Gremlin graph `topology`, blob containers `runbooks`/`tickets`) that should
instead be created at runtime from the scenario YAML.

### Target State

The telco-noc `scenario.yaml` becomes the single source of truth for the entire
scenario. The full target YAML is documented below in the
"Telco-NOC Scenario Pack" section, including complete directory structure,
v2.0 schema YAML, agents, data sources, and infrastructure declarations.

### ⚠️ Critical: YAML Schema Migration Path

The current `scenario.yaml` has `cosmos:` and `search_indexes:` sections with
a specific structure. The new `data_sources:` section proposed above replaces
them. This migration must be handled carefully.

#### Current → New Mapping

| Current YAML | New YAML | Notes |
|-------------|----------|-------|
| `cosmos.gremlin.database` | `data_sources.graph.config.database` | Same value |
| `cosmos.gremlin.graph` | `data_sources.graph.config.graph` | Same value |
| `cosmos.nosql.database` | `data_sources.telemetry.config.database` | Same value |
| `cosmos.nosql.containers[]` | `data_sources.telemetry.config.containers[]` | Same structure |
| `search_indexes[].name` | `data_sources.search_indexes.<key>` | List → dict; key derived from container name |
| `search_indexes[].container` | (dropped) | Blob container = search index key |
| `search_indexes[].source` | `data_sources.search_indexes.<key>.source` | **MUST preserve** — needed for upload |

**Key change:** `search_indexes` goes from a list-of-objects to a nested dict:

```yaml
# Current (list-of-objects):
search_indexes:
  - name: runbooks-index
    container: runbooks
    source: data/knowledge/runbooks
  - name: tickets-index
    container: tickets
    source: data/knowledge/tickets

# New (nested dict with source paths preserved):
data_sources:
  search_indexes:
    runbooks:
      index_name: "telco-noc-runbooks-index"
      source: "data/knowledge/runbooks"      # retained for blob upload
      blob_container: "runbooks"             # retained for blob container naming
    tickets:
      index_name: "telco-noc-tickets-index"
      source: "data/knowledge/tickets"
      blob_container: "tickets"
```

#### Backward Compatibility Strategy

The ingest code (`router_ingest.py` L357, L500) reads `manifest.get("cosmos", {})`.
Removing the `cosmos:` section without updating this code breaks ingest.

**Strategy: Support both formats during migration.**

```python
# In router_ingest.py — config normalization:
def _normalize_manifest(manifest: dict) -> dict:
    """Normalize old-format manifest to new data_sources format.

    Supports both old (cosmos: / search_indexes:) and new (data_sources:)
    formats. If both exist, data_sources takes precedence.
    """
    if "data_sources" in manifest:
        return manifest  # already new format

    ds = {}
    cosmos = manifest.get("cosmos", {})
    if cosmos.get("gremlin"):
        ds["graph"] = {
            "connector": "cosmosdb-gremlin",
            "config": cosmos["gremlin"],
        }
    if cosmos.get("nosql"):
        ds["telemetry"] = {
            "connector": "cosmosdb-nosql",
            "config": cosmos["nosql"],
        }

    old_indexes = manifest.get("search_indexes", [])
    if old_indexes:
        si = {}
        for idx in old_indexes:
            key = idx["container"]  # "runbooks", "tickets"
            si[key] = {
                "index_name": idx["name"],
                "source": idx.get("source", ""),
                "blob_container": idx["container"],
            }
        ds["search_indexes"] = si

    manifest["data_sources"] = ds
    return manifest
```

All ingest code paths call `_normalize_manifest()` first, then read from
`manifest["data_sources"]` exclusively. This lets old-format YAML files
work without modification while new scenarios use the new format.

#### Migration Checklist

- [ ] Add `_normalize_manifest()` to `router_ingest.py`
- [ ] Update all `manifest.get("cosmos", {})` calls to use normalized format
- [ ] Update all `manifest.get("search_indexes", [])` calls
- [ ] Update telco-noc `scenario.yaml` to new format
- [ ] Verify old-format YAML still works (regression test)
- [ ] Verify new-format YAML works end-to-end

### Telco-NOC Scenario Pack — Complete File Structure

The migrated telco-noc scenario pack must be fully self-describing. The YAML
defines **everything** needed to recreate the scenario from scratch on a fresh
deployment — which Cosmos databases, containers, and graphs to create; which
blob containers and search indexes to provision; which agents to deploy.

#### Target Directory Structure

```
data/scenarios/telco-noc/
├── scenario.yaml                          # Complete scenario manifest (see below)
├── graph_schema.yaml                      # Gremlin vertex/edge definitions (unchanged)
├── data/
│   ├── entities/                          # Graph CSVs (unchanged)
│   │   ├── DimAggSwitch.csv
│   │   ├── DimBGPSession.csv
│   │   ├── DimBaseStation.csv
│   │   ├── DimCoreRouter.csv
│   │   ├── DimMPLSPath.csv
│   │   ├── DimSLAPolicy.csv
│   │   ├── DimService.csv
│   │   ├── DimTransportLink.csv
│   │   ├── FactMPLSPathHops.csv
│   │   └── FactServiceDependency.csv
│   ├── knowledge/
│   │   ├── runbooks/                      # .md files → Blob → AI Search
│   │   └── tickets/                       # .txt files → Blob → AI Search
│   ├── prompts/                           # Agent prompt fragments
│   │   ├── alert_storm.md                 # Default demo input
│   │   ├── foundry_historical_ticket_agent.md
│   │   ├── foundry_orchestrator_agent.md
│   │   ├── foundry_runbook_kb_agent.md
│   │   ├── foundry_telemetry_agent_v2.md
│   │   └── graph_explorer/
│   │       ├── core_instructions.md
│   │       ├── core_schema.md
│   │       ├── description.md
│   │       ├── language_gremlin.md
│   │       └── language_mock.md
│   └── telemetry/                         # CSVs → Cosmos NoSQL
│       ├── AlertStream.csv
│       └── LinkTelemetry.csv
└── scripts/                               # Data generation (dev only)
    ├── generate_all.sh
    ├── generate_routing.py
    ├── generate_telemetry.py
    ├── generate_tickets.py
    └── generate_topology.py
```

#### Target `scenario.yaml` — Complete

This is the **final, production-ready** format. It replaces the old `cosmos:`
and `search_indexes:` sections with `data_sources:`, adds `agents:`, and
retains `graph_styles:`, `telemetry_baselines:`, `use_cases:`, `example_questions:`,
and `paths:`. Every resource that needs to exist for this scenario is declared here.

```yaml
# ============================================================================
# Scenario Manifest — Telco NOC (Fibre Cut)
# ============================================================================

name: telco-noc
display_name: "Australian Telco NOC — Fibre Cut Incident"
description: >
  A fibre cut on the Sydney-Melbourne corridor triggers a cascading alert
  storm affecting enterprise VPNs, broadband, and mobile services.
version: "2.0"          # bumped from 1.0 — schema change
domain: telecommunications

# ---------------------------------------------------------------------------
# Use cases & example questions (surfaced in Scenario Info tab)
# ---------------------------------------------------------------------------

use_cases:
  - "Fibre cut incident investigation and root cause correlation"
  - "MPLS path failover analysis and traffic rerouting assessment"
  - "Enterprise service impact mapping across BGP sessions"
  - "Alert storm triage and deduplication across transport links"
  - "SLA breach risk assessment for affected customers"

example_questions:
  - "What caused the alert storm on the Sydney-Melbourne corridor?"
  - "Which enterprise services are affected by the fibre cut?"
  - "How are MPLS paths rerouting around the failed transport link?"
  - "What BGP sessions are down and what's their blast radius?"
  - "Which SLA policies are at risk of being breached?"

# ---------------------------------------------------------------------------
# Data layout — paths relative to this file's parent directory
# ---------------------------------------------------------------------------

paths:
  entities: data/entities
  graph_schema: graph_schema.yaml
  telemetry: data/telemetry
  runbooks: data/knowledge/runbooks
  tickets: data/knowledge/tickets
  prompts: data/prompts
  default_alert: data/prompts/alert_storm.md

# ---------------------------------------------------------------------------
# Data sources — REPLACES old cosmos: and search_indexes: sections
# The ingest runtime uses this to create all necessary Azure resources
# (databases, containers, graphs, blob containers, search indexes).
# ---------------------------------------------------------------------------

data_sources:
  graph:
    connector: "cosmosdb-gremlin"
    config:
      database: "networkgraph"        # shared Gremlin DB
      graph: "telco-noc-topology"     # scenario-prefixed graph
      partition_key: "/partitionKey"
    schema_file: "graph_schema.yaml"

  telemetry:
    connector: "cosmosdb-nosql"
    config:
      database: "telemetry"           # shared NoSQL DB
      container_prefix: "telco-noc"   # containers: telco-noc-AlertStream, etc.
      containers:
        - name: AlertStream
          partition_key: /SourceNodeType
          csv_file: AlertStream.csv
          id_field: AlertId
          numeric_fields: [OpticalPowerDbm, BitErrorRate, CPUUtilPct, PacketLossPct]
        - name: LinkTelemetry
          partition_key: /LinkId
          csv_file: LinkTelemetry.csv
          id_field: null              # composite: LinkId + Timestamp
          numeric_fields: [UtilizationPct, OpticalPowerDbm, BitErrorRate, LatencyMs]

  search_indexes:
    runbooks:
      index_name: "telco-noc-runbooks-index"
      source: "data/knowledge/runbooks"   # path to .md files
      blob_container: "runbooks"          # Blob Storage container
    tickets:
      index_name: "telco-noc-tickets-index"
      source: "data/knowledge/tickets"
      blob_container: "tickets"

# ---------------------------------------------------------------------------
# Agents — defines the complete agent topology for this scenario
# ---------------------------------------------------------------------------

agents:
  - name: "GraphExplorerAgent"
    role: "graph_explorer"
    model: "gpt-4.1"
    instructions_file: "prompts/graph_explorer/"
    compose_with_connector: true
    tools:
      - type: "openapi"
        spec_template: "graph"
        keep_path: "/query/graph"

  - name: "TelemetryAgent"
    role: "telemetry"
    model: "gpt-4.1"
    instructions_file: "prompts/foundry_telemetry_agent_v2.md"
    tools:
      - type: "openapi"
        spec_template: "telemetry"
        keep_path: "/query/telemetry"

  - name: "RunbookKBAgent"
    role: "runbook"
    model: "gpt-4.1"
    instructions_file: "prompts/foundry_runbook_kb_agent.md"
    tools:
      - type: "azure_ai_search"
        index_key: "runbooks"

  - name: "HistoricalTicketAgent"
    role: "ticket"
    model: "gpt-4.1"
    instructions_file: "prompts/foundry_historical_ticket_agent.md"
    tools:
      - type: "azure_ai_search"
        index_key: "tickets"

  - name: "Orchestrator"
    role: "orchestrator"
    model: "gpt-4.1"
    instructions_file: "prompts/foundry_orchestrator_agent.md"
    is_orchestrator: true
    connected_agents:
      - "GraphExplorerAgent"
      - "TelemetryAgent"
      - "RunbookKBAgent"
      - "HistoricalTicketAgent"

# ---------------------------------------------------------------------------
# Graph visualisation hints (frontend node styling)
# ---------------------------------------------------------------------------

graph_styles:
  node_types:
    # Colors match the existing graphConstants.ts NODE_COLORS
    # so the migration from hardcoded → config preserves the visual appearance.
    CoreRouter:    { color: "#38BDF8", size: 28, icon: "router" }
    AggSwitch:     { color: "#FB923C", size: 22, icon: "switch" }
    BaseStation:   { color: "#A78BFA", size: 18, icon: "antenna" }
    TransportLink: { color: "#3B82F6", size: 16, icon: "link" }
    MPLSPath:      { color: "#C084FC", size: 14, icon: "path" }
    Service:       { color: "#CA8A04", size: 20, icon: "service" }
    SLAPolicy:     { color: "#FB7185", size: 12, icon: "policy" }
    BGPSession:    { color: "#F472B6", size: 14, icon: "session" }

# ---------------------------------------------------------------------------
# Telemetry baselines (used to generate prompt sections)
# ---------------------------------------------------------------------------

telemetry_baselines:
  link_telemetry:
    - metric: LatencyMs
      normal: "2–15 ms"
      degraded: "> 50 ms"
      down: "9999 ms"
    - metric: OpticalPowerDbm
      normal: "-8 to -12 dBm"
      degraded: "< -20 dBm"
      down: "< -30 dBm"
    - metric: BitErrorRate
      normal: "< 1e-9"
      degraded: "> 1e-6"
      down: "≈ 1"
    - metric: UtilizationPct
      normal: "20–70%"
      degraded: "> 80%"
      down: "0% (with other down indicators)"
  alert_stream:
    - metric: PacketLossPct
      normal: "< 1%"
      anomalous: "> 2%"
    - metric: CPUUtilPct
      normal: "< 70%"
      anomalous: "> 85%"
```

> **Key differences from v1.0 scenario.yaml:**
> - `cosmos:` replaced by `data_sources.graph` + `data_sources.telemetry`
> - `search_indexes:` (list) replaced by `data_sources.search_indexes` (dict)
> - New `agents:` section (5 agents with tool bindings)
> - Graph name now includes scenario prefix: `"telco-noc-topology"` (was `"topology"`)
> - Container prefix explicit: `"telco-noc"` (no more runtime string concatenation)
> - `version: "2.0"` marks the schema change
>
> **Note on `display_name`:** The `display_name` field (defined in Item 8) is
> omitted here because it's optional — it defaults to `name`. Add it if you
> want human-readable labels in the UI (e.g., `display_name: "Network Graph Explorer"`).

### Verification

1. Delete all hardcoded agent definitions from `agent_provisioner.py`
2. Upload telco-noc scenario with the new config YAML
3. Provision agents via `POST /api/config/apply`
4. Verify all 5 agents are created with correct tools
5. Run an investigation — verify orchestrator delegates correctly
6. Verify resource visualizer shows the correct graph
7. Verify topology, telemetry, and prompt queries work

---

## Item 14: Infrastructure Genericization (Bicep + Deploy Scripts)

### Problem Statement

The Bicep infrastructure and deployment scripts currently pre-create
scenario-specific resources at deploy time:

| Resource | File | Scenario-Specific? |
|----------|------|--------------------|
| Gremlin graph `topology` | `cosmos-gremlin.bicep` L12 | **YES** — should be per-scenario |
| NoSQL database `telemetry` | `cosmos-gremlin.bicep` L96 | **YES** — telemetry containers are per-scenario |
| Blob container `runbooks` | `storage.bicep` L14 | **YES** — knowledge files per scenario |
| Blob container `tickets` | `storage.bicep` L55 | **YES** — knowledge files per scenario |
| Env vars `RUNBOOKS_INDEX_NAME`, `TICKETS_INDEX_NAME` | `deploy.sh`, `azure_config.env.template` | **YES** — index names per scenario |
| Env vars `COSMOS_GREMLIN_GRAPH`, `COSMOS_NOSQL_DATABASE` | `deploy.sh`, `azure_config.env.template` | **YES** — per-scenario values |
| Default `topology` graph param | `main.bicep` L103 | **YES** — single default graph |

In the config-driven architecture, every scenario's YAML defines its own
resources. The **infrastructure** should only create the shared scaffolding;
scenario-specific resources are created at runtime during scenario upload.

### What Stays in Bicep (Shared Infrastructure)

These are genuinely shared across all scenarios and should remain:

| Resource | Module | Why Shared |
|----------|--------|------------|
| Cosmos Gremlin **account** | `cosmos-gremlin.bicep` | Shared service endpoint |
| Cosmos NoSQL **account** | `cosmos-gremlin.bicep` | Shared service endpoint |
| Gremlin database `networkgraph` | `cosmos-gremlin.bicep` | Shared DB; per-scenario graphs live inside it |
| NoSQL database `scenarios` + container `scenarios` | `cosmos-gremlin.bicep` | Shared scenario metadata store |
| NoSQL database `prompts` | `cosmos-gremlin.bicep` | Shared; per-scenario containers created at runtime |
| NoSQL database `interactions` + container `interactions` | `cosmos-gremlin.bicep` | Shared; partitioned by `/scenario` |
| Storage **account** | `storage.bicep` | Shared service endpoint |
| AI Search **service** | `search.bicep` | Shared service (indexes are per-scenario) |
| AI Foundry + model deployments | `ai-foundry.bicep` | Shared |
| VNet, Private Endpoints | `vnet.bicep`, `cosmos-private-endpoints.bicep` | Shared networking |
| Container App + ACR | `container-apps-environment.bicep`, `container-app.bicep` | Shared compute |
| RBAC role assignments | `roles.bicep` | Shared identity |
| Blob containers `telemetry-data`, `network-data` | `storage.bicep` | Shared utility containers |

### What Must Be Removed from Bicep (Scenario-Specific)

These are created at runtime by the ingest API based on the scenario YAML:

| Resource | Current Location | Runtime Owner |
|----------|-----------------|---------------|
| Gremlin graph `topology` | `cosmos-gremlin.bicep` L12, `main.bicep` L103 | `router_ingest.py` → `_ensure_gremlin_graph()` |
| NoSQL database `telemetry` | `cosmos-gremlin.bicep` L96 | `router_ingest.py` → `cosmos_helpers.get_or_create_container()` |
| Blob container `runbooks` | `storage.bicep` L14 | `router_ingest.py` → blob upload creates container |
| Blob container `tickets` | `storage.bicep` L55 | `router_ingest.py` → blob upload creates container |

> **⚠️ Important:** The `telemetry` database is shared (all scenarios store containers
> inside it, e.g., `telco-noc-AlertStream`). But it was being created by Bicep. After
> removal, the **first scenario upload** must create it. `cosmos_helpers.get_or_create_container()`
> already handles this — it calls the ARM API to create the database if it doesn't exist.
> However, this adds ~5-10s to the first upload. **Decision:** Keep `telemetry` database
> in Bicep as a shared resource. Only remove the scenario-specific resources.

#### Revised Decision: What to Actually Remove

After analysis, only **3 resources** need to be removed from Bicep:

1. **Gremlin graph `topology`** — scenario YAML defines graph names; runtime creates them
2. **Blob container `runbooks`** — scenario YAML defines blob containers; runtime creates them
3. **Blob container `tickets`** — same as above

The `telemetry` NoSQL database stays in Bicep as a shared container; scenario-specific
containers (e.g., `telco-noc-AlertStream`) are already created at runtime.

### Bicep Changes

#### `infra/modules/cosmos-gremlin.bicep`

```bicep
// REMOVE: Gremlin graph resource (lines ~L65-L85)
// The graph was declared as:
//   resource gremlinGraph 'Microsoft.DocumentDB/databaseAccounts/gremlinDatabases/graphs@2024-05-15'
//   name: graphName   (default: 'topology')
// This entire resource block is removed.
// Graphs are created at runtime by router_ingest.py → _ensure_gremlin_graph()

// KEEP: The Gremlin database 'networkgraph' (shared)
// KEEP: All NoSQL databases and containers (scenarios, prompts, interactions)
// KEEP: The 'telemetry' NoSQL database (shared)
```

Also remove the `graphName` and `partitionKeyPath` parameters from the module
since they're no longer used. Update `main.bicep` to stop passing them.

#### `infra/modules/storage.bicep`

```bicep
// REMOVE: Blob containers 'runbooks' and 'tickets' (lines ~L14-L60)
// These are scenario-specific. The ingest API creates blob containers
// on-demand when uploading knowledge files.

// KEEP: 'telemetry-data' and 'network-data' (shared utility containers)
```

Remove the `runbooksContainerName` parameter. Keep only shared containers.

#### `infra/main.bicep`

```bicep
// REMOVE: graphName and partitionKeyPath params passed to cosmos-gremlin module
// REMOVE: COSMOS_GREMLIN_GRAPH env var from container app (no longer a deploy-time value)
// KEEP: COSMOS_GREMLIN_DATABASE env var (still 'networkgraph' — shared)
```

### Deploy Script Changes

#### `deploy.sh`

```bash
# REMOVE these defaults — they're scenario-specific, not deploy-time:
# RUNBOOKS_INDEX_NAME="runbooks-index"
# TICKETS_INDEX_NAME="tickets-index"
# RUNBOOKS_CONTAINER_NAME="runbooks"
# TICKETS_CONTAINER_NAME="tickets"
# COSMOS_GREMLIN_GRAPH="topology"

# KEEP these — they're shared infrastructure:
# COSMOS_GREMLIN_DATABASE="networkgraph"
# COSMOS_NOSQL_DATABASE="telemetry"   (still needed as shared DB name)
```

#### `azure_config.env.template`

```bash
# REMOVE scenario-specific env vars:
# RUNBOOKS_INDEX_NAME=runbooks-index
# TICKETS_INDEX_NAME=tickets-index
# RUNBOOKS_CONTAINER_NAME=runbooks
# TICKETS_CONTAINER_NAME=tickets
# COSMOS_GREMLIN_GRAPH=topology

# KEEP shared env vars:
# COSMOS_GREMLIN_DATABASE=networkgraph
# COSMOS_NOSQL_DATABASE=telemetry

# ADD new env var:
# COSMOS_NOSQL_DATABASE=telemetry     (renamed from COSMOS_NOSQL_DATABASE — same)
```

#### `hooks/postprovision.sh`

Remove lines that write scenario-specific defaults:
- Remove `RUNBOOKS_INDEX_NAME`, `TICKETS_INDEX_NAME` defaults
- Remove `RUNBOOKS_CONTAINER_NAME`, `TICKETS_CONTAINER_NAME` defaults
- Remove `COSMOS_GREMLIN_GRAPH` default

### Runtime Resource Creation

When a scenario is uploaded (`POST /query/scenario/upload`), the ingest
API reads `data_sources` from the scenario YAML and creates:

1. **Gremlin graph:** `_ensure_gremlin_graph(db, graph_name)` — ARM API call
   - Already implemented in `router_ingest.py`
   - Graph name comes from `data_sources.graph.config.graph`

2. **NoSQL containers:** `cosmos_helpers.get_or_create_container(db, container_name)`
   - Already implemented — creates container if not exists
   - Container names come from `data_sources.telemetry.config.containers[].name`
   (prefixed with `container_prefix`)

3. **Blob containers:** `BlobServiceClient.get_container_client(name).create_container()`
   - Already implemented in the blob upload flow
   - Container names come from `data_sources.search_indexes.<key>.blob_container`

4. **Search indexes:** `search_indexer.create_or_update_index(name)`
   - Already implemented — creates index, data source, indexer
   - Index names come from `data_sources.search_indexes.<key>.index_name`

> **All 4 creation paths already exist in the codebase.** The only changes
> are: (a) reading names from YAML instead of env vars / hardcoded values,
> and (b) removing the Bicep pre-creation so there's no duplication.

### New Cosmos Container for Config Storage

The `fetch_scenario_config()` function (defined in Item 8) stores scenario
configs in a Cosmos container. Add this to the shared Bicep infrastructure:

```bicep
// In cosmos-gremlin.bicep — add to scenarios database:
resource configsContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: scenariosDatabase
  name: 'configs'
  properties: {
    resource: {
      id: 'configs'
      partitionKey: {
        paths: ['/scenario_name']
        kind: 'Hash'
      }
    }
  }
}
```

This container stores the full parsed `scenario.yaml` for each scenario,
used by `fetch_scenario_config()` at provisioning time.

> **Note:** The `config_store.py` code also specifies `ensure_created=True`,
> which creates this container at runtime if it doesn't exist. Declaring it
> in Bicep is not strictly necessary but avoids a ~5-10s ARM delay on the
> first scenario upload. Both approaches are idempotent — having both is safe.

### Env Var Cleanup Summary

| Env Var | Action | Reason |
|---------|--------|--------|
| `COSMOS_GREMLIN_GRAPH` | **REMOVE** | Graph name comes from scenario YAML |
| `RUNBOOKS_INDEX_NAME` | **REMOVE** | Index name comes from scenario YAML |
| `TICKETS_INDEX_NAME` | **REMOVE** | Index name comes from scenario YAML |
| `RUNBOOKS_CONTAINER_NAME` | **REMOVE** | Blob container comes from scenario YAML |
| `TICKETS_CONTAINER_NAME` | **REMOVE** | Blob container comes from scenario YAML |
| `COSMOS_GREMLIN_DATABASE` | KEEP | Shared DB name (`networkgraph`) |
| `COSMOS_NOSQL_DATABASE` | KEEP | Shared DB name (`telemetry`) |
| `COSMOS_GREMLIN_ENDPOINT` | KEEP | Account-level endpoint |
| `COSMOS_NOSQL_ENDPOINT` | KEEP | Account-level endpoint |
| `AI_SEARCH_NAME` | KEEP | Service-level name |
| `STORAGE_ACCOUNT_NAME` | KEEP | Account-level name |

> **Impact on existing code:** Any code that reads `COSMOS_GREMLIN_GRAPH`,
> `RUNBOOKS_INDEX_NAME`, etc. from env vars must be changed to read from
> the scenario config instead. This aligns with Phases 4-10.

---

## Implementation Phases

### Phase 0: Infrastructure Genericization

> Independent — should be done FIRST to establish the shared-only infra pattern

**Files to modify:**
- `infra/modules/cosmos-gremlin.bicep` — remove Gremlin graph resource, remove `graphName`/`partitionKeyPath` params
- `infra/modules/storage.bicep` — remove `runbooks` and `tickets` blob containers, remove `runbooksContainerName` param
- `infra/main.bicep` — stop passing graph params to cosmos module, remove `COSMOS_GREMLIN_GRAPH` env var from container app
- `infra/modules/cosmos-gremlin.bicep` — add `configs` container to `scenarios` database
- `deploy.sh` — remove scenario-specific env var defaults
- `azure_config.env.template` — remove scenario-specific env vars
- `hooks/postprovision.sh` — remove scenario-specific defaults
- `hooks/preprovision.sh` — remove any references to removed env vars

**Verification:**
- `azd up` succeeds — infra deploys without the removed resources
- Cosmos `networkgraph` database exists (shared), but NO default graph inside it
- Cosmos `scenarios` database has both `scenarios` and `configs` containers
- Cosmos `telemetry`, `prompts`, `interactions` databases exist (shared)
- Storage account has `telemetry-data` and `network-data` containers ONLY (no `runbooks`/`tickets`)
- `grep -rn 'RUNBOOKS_INDEX_NAME\|TICKETS_INDEX_NAME\|RUNBOOKS_CONTAINER_NAME\|TICKETS_CONTAINER_NAME\|COSMOS_GREMLIN_GRAPH' deploy.sh azure_config.env.template hooks/` returns **zero** results
- Upload telco-noc scenario via UI — all resources created at runtime (graph, containers, indexes)

> **⚠️ Risk:** If `azd up` is run on an existing deployment that already has
> these resources, Bicep will NOT delete them (Bicep is additive by default).
> The removal only affects new deployments. Existing resources remain and
> continue to work.

### Phase 1: DocumentStore Protocol + CosmosDocumentStore

> Independent — no prerequisites

**Files to create:**
- `graph-query-api/stores/__init__.py` — Protocol + factory (~70 lines)
- `graph-query-api/stores/cosmos_nosql.py` — Cosmos implementation (~80 lines)
- `graph-query-api/stores/mock_store.py` — In-memory mock (~50 lines)

**Files to modify:**
- None — purely additive

**Verification:**
- Import `CosmosDocumentStore` and verify it satisfies `isinstance(store, DocumentStore)`
- Run existing endpoints — they must still work (nothing changed)
- **Write a quick test:** Create a `CosmosDocumentStore` for `interactions/interactions`,
  call `store.list()` — verify it returns the same data as the existing endpoint

### Phase 2: Extract Cosmos Config

> Independent — can run in parallel with Phase 1

**Files to create:**
- `graph-query-api/adapters/__init__.py` — empty package marker
- `graph-query-api/adapters/cosmos_config.py` — Cosmos env vars (~30 lines)

**Files to modify:**
- `graph-query-api/config.py` — remove Cosmos constants (~-6 lines)
- `graph-query-api/cosmos_helpers.py` — update imports
- `graph-query-api/backends/cosmosdb.py` — update imports
- `graph-query-api/router_ingest.py` — update imports
- `graph-query-api/router_telemetry.py` — update imports

**Verification:**
- `python -c "from config import ScenarioContext; print('ok')"` — must not fail
- `python -c "from adapters.cosmos_config import COSMOS_NOSQL_ENDPOINT; print('ok')"` — must work
- **Start graph-query-api** (`uvicorn main:app`) — must boot without ImportError
- Test `POST /query/telemetry` — must still work

### Phase 3: Rename ScenarioContext Fields

> Independent — can run in parallel with Phases 1 and 2

**Files to modify:**
- `graph-query-api/config.py` — rename field in dataclass
- All files referencing `gremlin_database` (grep to find exact list)

**Verification:**
- `grep -rn "gremlin_database" graph-query-api/` returns **zero** results
- `POST /query/graph` with `X-Graph: telco-noc-topology` — works
- `POST /query/topology` — works
- graph-query-api boots without exception

### Phase 4: Migrate NoSQL Routers to DocumentStore

> Requires Phase 1 (DocumentStore) and Phase 3 (generic field names)

**Sub-phases (each independently shippable):**

**4a: router_interactions.py**
- Modify `router_interactions.py` — replace `cosmos_helpers` imports with `stores`
- Verification: `GET /query/interactions`, `POST /query/interactions`, `GET/DELETE /query/interactions/{id}`

**4b: router_scenarios.py**
- Modify `router_scenarios.py` — replace direct Cosmos calls
- Verification: `GET /query/scenarios/saved`, `POST /query/scenarios/save`, `DELETE /query/scenarios/saved/{name}`

**4c: router_telemetry.py**
- Modify `router_telemetry.py` — replace `_execute_cosmos_sql()` internals
- Verification: `POST /query/telemetry` with various container names and queries

**4d: router_prompts.py**
- Modify `router_prompts.py` — replace Cosmos calls (keep ARM listing for now)
- Verification: All `/query/prompts/*` endpoints, especially prompt versioning

### Phase 5: Extract Blob + AI Search Services

> Independent

**Files to create:**
- `graph-query-api/services/__init__.py` — empty
- `graph-query-api/services/blob_uploader.py` (~80 lines)

**Files to modify:**
- `graph-query-api/router_ingest.py` — replace inline blob logic with service calls

**Verification:**
- Upload runbooks tarball — blobs appear in storage, search index created
- Upload tickets tarball — same verification

### Phase 6: Add ingest() to GraphBackend Protocol

> Independent (but benefits from Phase 5 having untangled router_ingest)

**Files to modify:**
- `graph-query-api/backends/__init__.py` — add `ingest()` to Protocol
- `graph-query-api/backends/cosmosdb.py` — implement `ingest()` (~145 lines moved from router_ingest)
- `graph-query-api/backends/mock.py` — stub `ingest()`
- `graph-query-api/router_ingest.py` — replace `_gremlin_client()/_gremlin_submit()` with `backend.ingest()`

**Verification:**
- Upload graph tarball — vertices and edges loaded correctly
- `POST /query/topology` returns the uploaded graph
- `POST /query/graph` can query the uploaded data

### Phase 7: Backend Registry

> Independent

**Files to modify:**
- `graph-query-api/backends/__init__.py` — replace `if/elif` with registry
- `graph-query-api/config.py` — remove `GraphBackendType` enum, use `str`
- All files referencing `GraphBackendType` — update to `str`

**Verification:**
- Boot with `GRAPH_BACKEND=cosmosdb` — works
- Boot with `GRAPH_BACKEND=mock` — works
- Boot with `GRAPH_BACKEND=invalid` — raises `ValueError` with available backends

### Phase 8: Config-Driven Agent Provisioner

> Requires Phases 7 (registry, for connector-aware specs) and 9 (OpenAPI templates)

**Files to modify:**
- `scripts/agent_provisioner.py` — add `provision_from_config()`, `_load_prompt()`, `_build_tools()`, keep `provision_all()` as wrapper
- `api/app/routers/config.py` — update `apply_config()` to use scenario config
- `graph-query-api/config_store.py` — add `fetch_scenario_config()` and `save_scenario_config()`
- `graph-query-api/router_ingest.py` — call `save_scenario_config()` after parsing

**Files to create:**
- `graph-query-api/config_validator.py` — YAML schema validation (~60 lines)

#### ⚠️ Scenario Config Validation

The `agents` section in scenario YAML has complex nesting. Invalid or missing
fields cause cryptic errors deep in provisioning (e.g., `KeyError` on a missing
`model` field inside `provision_from_config()`). Add validation at upload time.

```python
# graph-query-api/config_validator.py

from typing import Any

REQUIRED_AGENT_FIELDS = {"name", "role", "model", "instructions_file"}
VALID_TOOL_TYPES = {"openapi", "azure_ai_search", "fabric", "code_interpreter"}

class ConfigValidationError(ValueError):
    """Raised when scenario config fails validation."""
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(f"Config validation failed: {'; '.join(errors)}")


def validate_scenario_config(config: dict) -> list[str]:
    """Validate a scenario config dict. Returns list of error strings (empty = valid).

    Called during:
    - POST /query/scenario/upload (after parsing scenario.yaml)
    - POST /api/config/apply (before provisioning)
    """
    errors: list[str] = []

    # Top-level required fields
    if "agents" not in config:
        errors.append("Missing required 'agents' section")
        return errors  # can't validate further

    agents = config["agents"]
    if not isinstance(agents, list) or len(agents) == 0:
        errors.append("'agents' must be a non-empty list")
        return errors

    # Per-agent validation
    agent_names: set[str] = set()
    orchestrator_count = 0

    for i, agent in enumerate(agents):
        prefix = f"agents[{i}]"
        if not isinstance(agent, dict):
            errors.append(f"{prefix}: must be a dict")
            continue

        # Required fields
        for field in REQUIRED_AGENT_FIELDS:
            if field not in agent:
                errors.append(f"{prefix}: missing required field '{field}'")

        # Unique names
        name = agent.get("name", "")
        if name in agent_names:
            errors.append(f"{prefix}: duplicate agent name '{name}'")
        agent_names.add(name)

        # Orchestrator validation
        if agent.get("is_orchestrator"):
            orchestrator_count += 1
            connected = agent.get("connected_agents", [])
            for ref in connected:
                if ref not in {a.get("name") for a in agents}:
                    errors.append(
                        f"{prefix}: connected_agent '{ref}' not found in agents list"
                    )

        # Tool validation
        for j, tool in enumerate(agent.get("tools", [])):
            tprefix = f"{prefix}.tools[{j}]"
            if "type" not in tool:
                errors.append(f"{tprefix}: missing 'type'")
            elif tool["type"] not in VALID_TOOL_TYPES:
                errors.append(f"{tprefix}: unknown type '{tool['type']}'")

    if orchestrator_count == 0:
        errors.append("No orchestrator agent defined (set is_orchestrator: true)")

    return errors
```

**Integration points:**
- `router_ingest.py`: After parsing `scenario.yaml`, call `validate_scenario_config()`.
  If errors, return 422 with the error list. Do NOT proceed with ingest.
- `config.py` (`POST /api/config/apply`): Before calling `provision_from_config()`,
  validate. Fail fast with a clear error message.

**Verification:**
- `POST /api/config/apply` with telco-noc scenario — creates 5 agents
- `GET /api/agents` — returns all 5 with correct names
- Run investigation — orchestrator delegates correctly
- Upload scenario with missing `model` field → 422 error with clear message
- Upload scenario with duplicate agent names → 422 error

### Phase 9: OpenAPI Spec Templating

> Independent

**Files to create:**
- `graph-query-api/openapi/templates/graph.yaml` — generic graph query spec with placeholders
- `graph-query-api/openapi/templates/telemetry.yaml` — generic telemetry spec with placeholders

**Files to modify:**
- `scripts/agent_provisioner.py` — update `_load_openapi_spec()` to use templates

**Verification:**
- Load OpenAPI spec for cosmosdb — contains Gremlin descriptions
- Load OpenAPI spec for mock — contains mock descriptions
- Specs parse as valid OpenAPI 3.0

### Phase 10: Config-Driven Prompt System

> Logically independent, but modifies `router_ingest.py` which is also
> touched by Phases 5, 6, and 8. See the parallelism caveat in the
> Dependency Graph section — **run after Phases 5 and 6** to avoid
> merge conflicts.

**Files to modify:**
- `graph-query-api/router_ingest.py` — remove `PROMPT_AGENT_MAP`, read from config
- `graph-query-api/router_prompts.py` — support config-driven prompt composition
- `api/app/routers/config.py` — expand prompt placeholders from config

**Verification:**
- Upload prompts tarball — prompts stored with correct agent mappings
- Provision agents — each gets correct prompt content
- GraphExplorer gets composed prompt (core + schema + language)

### Phase 11: Frontend Genericization

> Independent (can run in parallel with backend phases)

**Files to modify:**
- `frontend/src/context/ScenarioContext.tsx` — config-specified resources
- `frontend/src/components/graph/graphConstants.ts` — empty hardcoded maps
- `frontend/src/components/SettingsModal.tsx` — read-only when scenario active (optional)
- `api/app/routers/alert.py` — remove hardcoded stub agent names

**Verification:**
- Load telco-noc scenario — colors match (now from `graph_styles`)
- Load a non-telco scenario — auto-hash colors assigned
- Settings modal shows correct bindings from saved scenario

### Phase 12: Resource Visualizer Backend

> Requires Phase 8 (config-driven provisioner, so config contains agent definitions)

**Files to create:**
- `GET /api/config/resources` endpoint in `api/app/routers/config.py` (~60 lines)

**Files to modify:**
- `frontend/src/hooks/useResourceGraph.ts` — swap mock for real API call

**Verification:**
- Navigate to Resources tab — graph shows real agents/tools/data sources
- Hover nodes — tooltip shows real metadata (model, role, etc.)
- Filter by type — works correctly

### Phase 13: Migrate telco-noc to Config

> Requires all prior phases + Phase 0 (infrastructure genericization)

This phase rewrites the telco-noc scenario pack to use the v2.0 YAML schema.
The scenario.yaml becomes the single source of truth: it tells the system
exactly which databases, containers, graphs, blob containers, search indexes,
and agents to create.

**Files to modify:**
- `data/scenarios/telco-noc/scenario.yaml` — full rewrite to v2.0 schema (see Item 13 target YAML)

**Files to regenerate:**
- Pre-built tarballs in `data/scenarios/` — regenerate from source data:
  - `telco-noc-graph.tar.gz` — must include updated `scenario.yaml` + `graph_schema.yaml` + CSVs
  - `telco-noc-prompts.tar.gz` — prompts unchanged
  - `telco-noc-runbooks.tar.gz` — runbooks unchanged
  - `telco-noc-telemetry.tar.gz` — must include updated `scenario.yaml` + CSVs
  - `telco-noc-tickets.tar.gz` — tickets unchanged

**Files to audit:**
- `data/scenarios/telco-noc/scripts/generate_all.sh` — ensure it doesn't read old `cosmos:` keys
- `data/scenarios/telco-noc/scripts/generate_*.py` — ensure YAML parsing uses new schema

**Verification:**
- Full end-to-end test on a **fresh deployment** (no pre-existing scenario resources):
  1. `azd up` — deploys shared infra only (no scenario-specific resources)
  2. Upload telco-noc scenario via UI
  3. Verify runtime resource creation:
     - Cosmos Gremlin: `telco-noc-topology` graph created in `networkgraph` DB
     - Cosmos NoSQL: `telco-noc-AlertStream` + `telco-noc-LinkTelemetry` containers in `telemetry` DB
     - Blob: `runbooks` and `tickets` containers created in storage account
     - AI Search: `telco-noc-runbooks-index` and `telco-noc-tickets-index` created
  4. Select scenario → agents auto-provision (5 agents from YAML)
  5. Run investigation → orchestrator delegates correctly
  6. Resources tab shows correct graph
  7. Telemetry queries work
  8. Prompt editing works
- Backward compatibility test: upload a v1.0 scenario YAML → `_normalize_manifest()` handles it

---

## File Change Inventory

| File | Action | Phase | Changes |
|------|--------|-------|---------|
| `graph-query-api/stores/__init__.py` | **CREATE** | 1 | DocumentStore Protocol + registry + factory (~80 lines) |
| `graph-query-api/stores/cosmos_nosql.py` | **CREATE** | 1 | CosmosDocumentStore implementation (~80 lines) |
| `graph-query-api/stores/mock_store.py` | **CREATE** | 1 | MockDocumentStore (~50 lines) |
| `graph-query-api/adapters/__init__.py` | **CREATE** | 2 | Empty package marker |
| `graph-query-api/adapters/cosmos_config.py` | **CREATE** | 2 | Cosmos env vars (~30 lines) |
| `graph-query-api/services/__init__.py` | **CREATE** | 5 | Empty package marker |
| `graph-query-api/services/blob_uploader.py` | **CREATE** | 5 | Blob upload service (~80 lines) |
| `graph-query-api/config_validator.py` | **CREATE** | 8 | Scenario config YAML validation (~60 lines) |
| `graph-query-api/config_store.py` | **CREATE** | 8 | `fetch_scenario_config()` + `save_scenario_config()` (~40 lines) |
| `api/app/agent_helpers.py` | **CREATE** | 11 | Shared `_load_agent_names()`, `_load_stub_agents()` (~30 lines) |
| `graph-query-api/openapi/templates/graph.yaml` | **CREATE** | 9 | Generic graph OpenAPI template |
| `graph-query-api/openapi/templates/telemetry.yaml` | **CREATE** | 9 | Generic telemetry OpenAPI template |
| `graph-query-api/config.py` | MODIFY | 2, 3, 7 | Remove Cosmos vars, rename fields, remove enum |
| `graph-query-api/cosmos_helpers.py` | MODIFY | 2 | Update imports |
| `graph-query-api/backends/__init__.py` | MODIFY | 6, 7 | Add `ingest()`, add registry |
| `graph-query-api/backends/cosmosdb.py` | MODIFY | 2, 6 | Update imports, implement `ingest()` |
| `graph-query-api/backends/mock.py` | MODIFY | 6 | Stub `ingest()` |
| `graph-query-api/router_interactions.py` | MODIFY | 4a | Migrate to DocumentStore |
| `graph-query-api/router_scenarios.py` | MODIFY | 4b | Migrate to DocumentStore + genericize resource bindings |
| `graph-query-api/router_telemetry.py` | MODIFY | 2, 4c | Update imports, migrate to DocumentStore |
| `graph-query-api/router_prompts.py` | MODIFY | 4d, 10 | Migrate to DocumentStore, config prompts |
| `graph-query-api/router_ingest.py` | MODIFY | 2, 5, 6, 8, 10, 13 | Update imports, extract services, use `backend.ingest()`, add `_normalize_manifest()`, save config, config prompts |
| `scripts/agent_provisioner.py` | MODIFY | 8, 9 | Add `provision_from_config()`, `_load_prompt()`, `_build_tools()`, template specs |
| `api/app/routers/config.py` | MODIFY | 8, 10, 12 | Config-driven provisioning, prompt expansion, resource endpoint |
| `api/app/routers/alert.py` | MODIFY | 11 | Use `_load_agent_names()` from agent_helpers |
| `api/app/routers/agents.py` | MODIFY | 11 | Use `_load_stub_agents()` from agent_helpers |
| `frontend/src/context/ScenarioContext.tsx` | MODIFY | 11 | Config-specified resources |
| `frontend/src/components/graph/graphConstants.ts` | MODIFY | 11 | Empty hardcoded maps |
| `frontend/src/hooks/useResourceGraph.ts` | MODIFY | 12 | Swap mock for real API |
| `data/scenarios/telco-noc/scenario.yaml` | MODIFY | 13 | Full rewrite to v2.0 schema — data_sources + agents |
| `infra/modules/cosmos-gremlin.bicep` | MODIFY | 0 | Remove Gremlin graph resource, add `configs` container |
| `infra/modules/storage.bicep` | MODIFY | 0 | Remove `runbooks` + `tickets` blob containers |
| `infra/main.bicep` | MODIFY | 0 | Remove graph params, remove `COSMOS_GREMLIN_GRAPH` env var |
| `deploy.sh` | MODIFY | 0 | Remove scenario-specific env var defaults |
| `azure_config.env.template` | MODIFY | 0 | Remove scenario-specific env vars |
| `hooks/postprovision.sh` | MODIFY | 0 | Remove scenario-specific defaults |

### Files NOT Changed

- `graph-query-api/main.py` — FastAPI app wiring is already generic (mounts routers by reference)
- `graph-query-api/models.py` — Pure Pydantic models, no backend coupling
- `graph-query-api/sse_helpers.py` — Pure asyncio/SSE utilities
- `graph-query-api/router_graph.py` — Already uses `GraphBackend` Protocol exclusively
- `graph-query-api/router_topology.py` — Already uses `GraphBackend` Protocol exclusively
- `graph-query-api/search_indexer.py` — Backend-agnostic (Blob → AI Search); stays as-is or moves to `services/` for organizational clarity
- `api/app/main.py` — Just mounts routers
- `api/app/orchestrator.py` — Already scenario-agnostic (runs any agent by ID)
- `frontend/src/components/ResourceVisualizer.tsx` — Already implemented, no changes needed
- `frontend/src/components/resource/*` — Already implemented
- `Dockerfile`, `supervisord.conf`, `nginx.conf` — No changes needed

---

## Edge Cases & Validation

### DocumentStore Protocol (Item 1)

**Partition key mismatch:** Cosmos requires exact partition key for `read_item()` and
`delete_item()`. The `DocumentStore.get()` and `delete()` signatures include
`partition_key` explicitly. Callers must always provide it.

**Empty database on first call:** `get_or_create_container()` with `ensure_created=True`
handles ARM container creation (~5-10s on first call). Subsequent calls are cached.
The `DocumentStore` factory's `ensure_created` parameter controls this.

**Query cross-partition performance:** `enable_cross_partition_query=True` is always
set in `CosmosDocumentStore.list()`. This works for all current usage patterns but may
be slow for large datasets. Cross-partition is acceptable for scenario/interaction
data (< 1000 documents per container).

### ScenarioContext Field Rename (Item 3)

**Runtime crash from missed reference:** The field rename from `gremlin_database` to
`graph_database` changes a dataclass field name. Any code accessing `ctx.gremlin_database`
will raise `AttributeError` at runtime, not at import time. **Mitigation:** Run
`grep -rn "gremlin_database" graph-query-api/ api/` and verify zero matches post-rename.

### Backend Registry (Item 7)

**Unknown backend string:** If `GRAPH_BACKEND` env var is set to an unregistered name,
the registry raises `ValueError` with the list of available backends. This is a clear
error message, better than the current `ValueError` from `GraphBackendType()` enum.

**Import order:** Backend modules register themselves at import time. If `backends/__init__.py`
fails to import a module (e.g., missing `gremlin_python` package), registration fails
silently. **Mitigation:** Wrap imports in try/except, log a warning, exclude the backend.

### Config-Driven Provisioner (Item 8)

**Agent name collisions:** If two agents in config have the same name, the second
creation will fail or overwrite. **Mitigation:** Validate unique names when parsing config.

**Missing connected agent:** If an orchestrator references a `connected_agent` that
doesn't exist in the config, `provision_from_config()` will KeyError when looking up
the agent ID. **Mitigation:** Validate `connected_agents` references at parse time.

**Partial provisioning failure:** If agent 3 of 5 fails to create, agents 1-2 exist
but 4-5 don't. **Mitigation:** `cleanup_existing()` before provisioning (already done 
with `force=True`). On failure, clean up partially created agents.

### OpenAPI Spec Templating (Item 9)

**Placeholder in YAML value:** If a placeholder like `{graph_name}` appears in a YAML
value field, `str.format_map()` will replace it correctly. But if the placeholder
appears in a YAML key, it could produce invalid YAML. **Mitigation:** Placeholders
only in string values, never in keys.

### Frontend Genericization (Item 11)

**Scenario without graph_styles:** If a scenario's `graph_styles` is empty, the
auto-hash in `useNodeColor.ts` assigns deterministic colors based on label string hash.
This already works — tested with non-telco scenarios.

**Resource visualizer with no scenario:** If no scenario is active, the resource
visualizer shows the mock data badge. After Phase 12, it shows an empty state message:
"Select a scenario to view its resource graph."

### Scenario Switching (Item 11)

**Stale investigation state on switch:** If a user switches scenarios mid-investigation,
the investigation panel shows steps from the previous scenario. **Mitigation:** Clear
(or archive) the current investigation state on scenario switch. Show a confirmation
dialog if an investigation is in progress: "Switch scenario? Current investigation
progress will be cleared."

**Interaction sidebar filtering:** The sidebar shows all interaction history across
scenarios. As multiple scenarios accumulate history, this gets confusing.
**Mitigation (V10+):** Add a scenario filter chip to the `InteractionSidebar`.

**Scenario readiness after switch:** After selecting a scenario, there's no validation
that backend resources actually exist. A partially-uploaded scenario (graph loaded
but prompts missing) causes silent failures during investigation.
**Mitigation:** After scenario selection, perform a lightweight health check via
`GET /query/scenarios/saved/{name}` or a dedicated status endpoint. Show a readiness
indicator in the header's `ScenarioChip` — green for fully ready, amber for partial,
red for missing critical resources.

### Resource Visualizer Scaling (Item 12)

**Large node counts:** The 6-layer y-force layout works for the current 28-node mock.
A custom scenario with 10+ agents and 2–3 tools each produces 50+ nodes, where
force-directed layouts degrade (overlap, label collisions). **Mitigation (V10+):**
Add a layout toggle between force-directed and hierarchical (dagre/ELK), or add
collapse/expand on agent nodes to reduce visual clutter.

### First-Run Experience (Item 11)

**Empty app after fresh deploy:** Phase 0 removes pre-created resources. A fresh
`azd up` produces an empty Investigate tab with no onboarding guidance.
**Mitigation:** First-run empty state added in Phase 11e.

---

## Migration & Backwards Compatibility

### Existing Data

**Cosmos databases:** All shared databases (`networkgraph`, `telemetry`, `prompts`,
`scenarios`, `interactions`) are pre-created by Bicep and remain unchanged.

**Scenario metadata:** Existing `scenarios/scenarios` documents in Cosmos have
resource fields that match the convention-based derivation. No migration needed —
the frontend fallback logic produces identical values.

**Prompts:** Existing prompt documents in per-scenario containers continue to work.
The `DocumentStore` wraps the same `get_or_create_container()` calls.

**Interactions:** Existing interaction history is untouched. The `DocumentStore`
wraps the same container access.

### Data Generation Scripts

`data/generate_all.sh` and per-scenario generation scripts (e.g., Python scripts
that generate CSV data) are NOT modified by this plan. However, if the scenario
YAML schema changes (e.g., `cosmos:` → `data_sources:`), any generation scripts
that read `scenario.yaml` must be updated to match the new structure. The
`_normalize_manifest()` function only helps the ingest runtime, not offline scripts.

**Action:** After completing Phase 13, audit `data/generate_all.sh` and any
`data/scenarios/*/generate_*.py` scripts to ensure they don't read old-format
YAML keys directly.

### Dependency Management

`pyproject.toml` currently installs all Cosmos dependencies unconditionally
(`azure-cosmos`, `gremlinpython`, etc.), even when running with `GRAPH_BACKEND=mock`.

**Current state:** This is acceptable — Docker image sizes are not a concern for
Container Apps, and conditional dependencies add build complexity.

**Future consideration:** If a Fabric connector is added that doesn't need Cosmos
packages, consider using optional dependency groups:

```toml
[project.optional-dependencies]
cosmosdb = ["azure-cosmos>=4.7", "gremlinpython>=3.7"]
fabric = ["azure-kusto-data>=4.0"]
```

This is **out of scope** for V9 but documented here so it's not forgotten.

### API Surface Compatibility

**All existing endpoints preserved.** Changes are internal (how the endpoint
implementation accesses storage), not external (request/response shapes).

| Endpoint | Change | Compat |
|----------|--------|--------|
| All `/query/*` endpoints | Internal refactor (DocumentStore) | Request/response shapes unchanged |
| `POST /api/config/apply` | Accepts config from YAML | Old `ConfigApplyRequest` still works (backward compat) |
| `GET /api/config/resources` | **NEW** | Additive — doesn't break existing clients |

### Gradual Adoption

Each phase is independently deployable:
- Phase 1 (DocumentStore) — purely additive, zero risk
- Phases 2-3 — import restructure, easy rollback
- Phase 4 — one router at a time, testable in isolation
- Phases 5-7 — backend internals, transparent to frontend
- Phases 8-10 — provisioner changes, but `provision_all()` remains as wrapper
- Phase 11 — frontend changes, with derivation fallback for old scenarios
- Phase 13 — migration of one scenario, validates everything

### Rollback Plan

**Phases 1-3:** Revert the commits. No data format changes.

**Phase 4:** Each router migration is a single commit. Revert individual
router migrations without affecting others.

**Phases 8, 10:** `provision_all()` is kept as a wrapper around
`provision_from_config()`. If config-driven provisioning fails, the old
method still works by constructing the equivalent config internally.

**Phase 13:** If the new config format doesn't work, the old `scenario.yaml`
(without `agents` section) is still valid. The provisioner falls back to
hardcoded behavior when no `agents` section is found.

---

## Codebase Audit Reference

### Layer-by-Layer Summary

| Layer | Generic (lines) | Needs Work (lines) | Key Blocker |
|-------|----------------|-------------------|-------------|
| graph-query-api | 896 (27%) | 2,330 (69%) | NoSQL routers coupled to Cosmos SDK |
| API backend | ~400 (75%) | ~130 (25%) | `config.py` hardcodes 5 agents |
| Agent provisioner | 0 (0%) | 281 (100%) | Everything hardcoded |
| Data layer | ~80% generic | ~20% hardcoded | `scenario.yaml` Cosmos-specific sections |
| Frontend | ~85% generic | ~15% hardcoded | `graphConstants.ts`, `ScenarioContext` derivation |
| Deployment | ~95% generic | ~5% hardcoded | `.env.template` defaults |

### What's Already Good (Minimal or No Change Needed)

- `GraphBackend` Protocol + factory — clean interface, CosmosDB and Mock implement it
- `ScenarioContext` per-request routing via `X-Graph` header
- `scenario.yaml` / `graph_schema.yaml` structure — already declarative
- Force-graph topology rendering — renders any node/edge topology
- `useNodeColor` fallback chain — auto-hash handles unknown labels
- Orchestrator SSE bridge — runs any agent by ID
- nginx / Dockerfile / supervisord architecture — scenario-agnostic

### Graph-Query-API File Classification

**Already generic (896 lines / 27%):**

| File | Lines |
|------|-------|
| `backends/__init__.py` | 120 |
| `backends/mock.py` | 204 |
| `router_graph.py` | 73 |
| `router_topology.py` | 69 |
| `models.py` | 107 |
| `sse_helpers.py` | 86 |
| `main.py` | 237 |

**Cosmos-specific (2,330 lines / 69%):**

| File | Lines | Cosmos Usage |
|------|-------|-------------|
| `backends/cosmosdb.py` | 303 | Gremlin adapter (already behind Protocol) |
| `cosmos_helpers.py` | 132 | NoSQL client + ARM |
| `router_telemetry.py` | 145 | Cosmos SQL queries |
| `router_interactions.py` | 147 | Cosmos CRUD |
| `router_scenarios.py` | 221 | Cosmos CRUD + validation |
| `router_prompts.py` | 289 | Cosmos CRUD + versioning |
| `router_ingest.py` | 871 | Gremlin + NoSQL + Blob + Search |
| `search_indexer.py` | 225 | AI Search pipelines |

### Environment Variables

| Variable | Used By | Default | Phase 0 Action |
|----------|---------|---------|----------------|
| `GRAPH_BACKEND` | config.py | `"cosmosdb"` | KEEP |
| `COSMOS_GREMLIN_ENDPOINT` | config.py, router_ingest.py | `""` | KEEP (account-level) |
| `COSMOS_GREMLIN_PRIMARY_KEY` | config.py, router_ingest.py | `""` | KEEP (account-level) |
| `COSMOS_GREMLIN_DATABASE` | config.py, router_ingest.py | `"networkgraph"` | KEEP (shared DB) |
| ~~`COSMOS_GREMLIN_GRAPH`~~ | ~~config.py~~ | ~~`"topology"`~~ | **REMOVE** — graph name from scenario YAML |
| `COSMOS_NOSQL_ENDPOINT` | config.py, router_telemetry.py, router_prompts.py | `""` | KEEP (account-level) |
| `COSMOS_NOSQL_DATABASE` | config.py | `"telemetry"` | KEEP (shared DB) |
| `AI_SEARCH_NAME` | config.py, router_ingest.py | `""` | KEEP (service-level) |
| `AI_SEARCH_CONNECTION_ID` | agent_provisioner.py | `"aisearch-connection"` | KEEP |
| `STORAGE_ACCOUNT_NAME` | router_ingest.py | `""` | KEEP (account-level) |
| `PROJECT_ENDPOINT` | api config.py | `""` | KEEP |
| `AI_FOUNDRY_ENDPOINT` | api config.py | `""` | KEEP |
| `AI_FOUNDRY_PROJECT_NAME` | api config.py | `""` | KEEP |
| `AI_FOUNDRY_NAME` | api config.py, search_indexer.py | `""` | KEEP |
| `MODEL_DEPLOYMENT_NAME` | api config.py | `"gpt-4.1"` | KEEP |
| `EMBEDDING_MODEL` | search_indexer.py | `"text-embedding-3-large"` | KEEP |
| `EMBEDDING_DIMENSIONS` | search_indexer.py | `"1536"` | KEEP |
| `GRAPH_QUERY_API_URI` | api config.py | `""` | KEEP |
| `CONTAINER_APP_HOSTNAME` | api config.py | `""` | KEEP |
| `AZURE_SUBSCRIPTION_ID` | router_ingest.py, api config.py | `""` | KEEP |
| `AZURE_RESOURCE_GROUP` | router_ingest.py, api config.py | `""` | KEEP |
| `AZURE_LOCATION` | infra, deploy.sh | `"swedencentral"` | KEEP |
| `DEFAULT_SCENARIO` | azure_config.env.template | `"telco-noc"` | KEEP |
| `LOADED_SCENARIOS` | api config.py | `""` | KEEP |
| ~~`RUNBOOKS_INDEX_NAME`~~ | ~~deploy.sh, env template~~ | ~~`"runbooks-index"`~~ | **REMOVE** — index name from scenario YAML |
| ~~`TICKETS_INDEX_NAME`~~ | ~~deploy.sh, env template~~ | ~~`"tickets-index"`~~ | **REMOVE** — index name from scenario YAML |
| ~~`RUNBOOKS_CONTAINER_NAME`~~ | ~~deploy.sh, env template~~ | ~~`"runbooks"`~~ | **REMOVE** — blob container from scenario YAML |
| ~~`TICKETS_CONTAINER_NAME`~~ | ~~deploy.sh, env template~~ | ~~`"tickets"`~~ | **REMOVE** — blob container from scenario YAML |

> **⚠️ `GRAPH_QUERY_API_URI`:** In Container Apps, this must be set to the
> external Container App FQDN (e.g., `https://<app-name>.<region>.azurecontainerapps.io`),
> NOT `http://localhost:8100`. The API backend calls graph-query-api via the
> OpenAPI tool, which resolves through the external URL. Using localhost would
> fail because the agent service runs in Azure AI Foundry, not inside the container.

> **⚠️ `AI_SEARCH_CONNECTION_ID`:** Currently hardcoded as `"aisearch-connection"`
> in `agent_provisioner.py`. Add as env var so different AI Foundry projects with
> different connection names can work without code changes.

---

## Resource Visualizer Reference

### Implementation Status (Frontend — Complete)

The Resource Visualizer frontend was built with Option C (mock data now, real
API later). TypeScript compiles clean, zero errors.

#### Files Created

| File | Lines | Purpose |
|------|-------|---------|
| `frontend/src/types/index.ts` | +36 | `ResourceNode`, `ResourceEdge`, 12 node types, 8 edge types |
| `frontend/src/hooks/useResourceGraph.ts` | ~140 | Mock hook returning 28-node, 37-edge full architecture graph |
| `frontend/src/components/resource/resourceConstants.ts` | ~80 | Node colours/sizes per type, edge colours/dash patterns (12+8 entries) |
| `frontend/src/components/resource/ResourceTooltip.tsx` | 72 | Hover tooltip with node/edge metadata |
| `frontend/src/components/resource/ResourceToolbar.tsx` | ~100 | Filter chips (10 types), search, pause/play, zoom-to-fit |
| `frontend/src/components/resource/ResourceCanvas.tsx` | ~290 | ForceGraph2D with 4 shapes (circle, diamond, round-rect, hexagon), 6-layer y-force |
| `frontend/src/components/ResourceVisualizer.tsx` | 164 | ResizeObserver sizing, pause/freeze, tooltip, filtering |

#### Files Modified

| File | Change |
|------|--------|
| `frontend/src/App.tsx` | Added `'resources'` to `AppTab`, imported `ResourceVisualizer` |
| `frontend/src/components/TabBar.tsx` | Extended type, added `◇ Resources` button |

#### Node Types & Visual Language

| Type | Shape | Colour | Layer |
|------|-------|--------|-------|
| `orchestrator` | Circle (double border) | blue `#3b82f6` | Agent |
| `agent` | Circle | blue `#60a5fa` | Agent |
| `tool` | Diamond | amber `#f59e0b` | Tool |
| `datasource` | Rounded rectangle | green `#22c55e` | Data source |
| `search-index` | Rounded rectangle | purple `#a855f7` | Data source |
| `blob-container` | Rounded rectangle | cyan `#67e8f9` | Upload/DB |
| `cosmos-database` | Rounded rectangle | emerald `#34d399` | Upload/DB |
| `foundry` | Hexagon | pink `#ec4899` | Infrastructure |
| `cosmos-account` | Hexagon | emerald `#10b981` | Infrastructure |
| `storage` | Hexagon | cyan `#06b6d4` | Infrastructure |
| `search-service` | Hexagon | violet `#8b5cf6` | Infrastructure |
| `container-app` | Hexagon | orange `#f97316` | Infrastructure |

#### Edge Types

| Type | Style | Colour | Example |
|------|-------|--------|--------|
| `delegates_to` | Solid | blue | Orchestrator → Agent |
| `uses_tool` | Dash `[4,2]` | amber | Agent → Tool |
| `queries` | Dot `[2,2]` | green | Tool → Data source |
| `stores_in` | Dash `[6,3]` | cyan | Data source → Database |
| `hosted_on` | Dash `[3,3]` | orange | Search index → Search service |
| `indexes_from` | Dash `[4,2]` | violet | Blob container → Search index |
| `runs_on` | Dash `[3,3]` | orange | Agent → Foundry |
| `contains` | Dot `[1,2]` | subtle | Database → Cosmos account |

#### Excluded from Visualizer

Networking infrastructure is excluded because it's not scenario-specific and
doesn't appear in the YAML config:
- Virtual network, subnets, NSGs
- Private endpoints, private DNS zones, NICs
- Event Grid system topics
- Log Analytics workspaces
- Container registry (deployment concern, not data flow)
- Container Apps Environment (deployment concern)

#### Remaining Work (Phase 12)

Swap `useResourceGraph.ts` mock constants for `fetch('/api/config/resources')`
call. Backend must build the full graph from scenario YAML `agents:` +
`data_sources:` sections plus infrastructure env vars.

---

## Resolved Design Decisions

> These decisions were resolved during planning. They are documented here for
> context on *why* the plan is shaped this way. **Do not re-deliberate** — the
> plan body already implements these choices.

### Q1: Where does the V9 config live at runtime?

**Options:**
1. Embedded in `scenario.yaml` within each data pack
2. In the `scenarios/scenarios` Cosmos container (alongside scenario metadata)
3. As a separate YAML in Blob Storage

**Recommendation (adopted):** Option 1 — extend `scenario.yaml`. It already has `cosmos`,
`graph_styles`, `use_cases`, `example_questions`. Adding `agents` and
`data_sources` sections is natural. The config is uploaded with the scenario
data and persisted in the `scenarios` database when the scenario is saved.

### Q2: Adapter registration mechanism?

**Options:**
1. pip-installable plugins
2. Module discovery via `connectors/` directory
3. Explicit registration in `backends/__init__.py`

**Recommendation (adopted):** Option 3 for now. Explicit imports at the bottom of
`backends/__init__.py`. Move to plugin-based discovery only when there are
enough backends to justify it.

### Q3: Separate telemetry and graph adapters, or unified?

**Options:**
1. One "cosmosdb" adapter handling both Gremlin and NoSQL
2. Separate `cosmosdb-gremlin` (graph) + `cosmosdb-nosql` (telemetry) adapters

**Recommendation (adopted):** Separate. They use different SDKs, different query languages,
different databases. The `GraphBackend` Protocol handles graph queries; the
`DocumentStore` Protocol handles NoSQL operations. A Fabric adapter would be a
single adapter handling both via KQL.

### Q4: OpenAPI spec generation vs templating?

**Recommendation (adopted):** Template with per-placeholder `.replace()` calls — zero
new dependencies, already the pattern used today. **Do NOT use
`str.format_map()`** — OpenAPI YAML files contain literal `{braces}` in JSON
Schema examples (e.g., `{"type": "string"}`), which cause `KeyError`. See
Item 9 for the safe `.replace()` pattern. Switch to Jinja2 only if conditional
logic is needed (e.g., showing different examples per connector).

### Q5: Should all agents support prompt composition from fragments?

**Recommendation (adopted):** Support both patterns:
- Single file: `instructions_file: "prompts/telemetry.md"`
- Composed: `instructions_file: "prompts/graph_explorer/"` + `compose_with_connector: true`

The config declares which pattern each agent uses. No need to force all agents
into composition.

### Q6: Prompt placeholder expansion timing?

**Recommendation (adopted):** Expansion at provisioning time (same as current behavior).
The `api/app/routers/config.py` endpoint substitutes placeholders when calling
`provision_from_config()`. Expansion at upload time is too early — values may
change between scenarios.
