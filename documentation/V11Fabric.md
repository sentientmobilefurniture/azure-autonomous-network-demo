# Fabric Integration — Implementation Plan (Revised: Service Separation Architecture)

I am realizing something quite interesting and excellent. Because of the config-forward style of specificying data sources and agents and the overall architecture, it is possible for us to just specify fabric components in the config as well. Fabric generics are just another option to tweak in the scenario config file. There is not need for an entire new service or whatever...just a set of fabric specific backend/helper functions. And it is entirely possible to have both cosmosdb with gremlin and fabric existing in the same architecture. 


> **Created:** 2026-02-15
> **Last revised:** 2026-02-16 (major revision — V10 coordination + service separation architecture)
> **Status:** ⬜ Not Started
> **Depends on:** [V10 — Config-Driven Multi-Agent Orchestration](V10generalflow.md) (in progress)
> **Goal:** Add Microsoft Fabric as an alternative graph backend to CosmosDB,
> keeping the two backends as **completely independent services** — `cosmosdb-graph-api`
> (renamed from `graph-query-api`) and a new `fabric-graph-api` — so the UI works
> correctly even if either backend is unavailable, missing, or not instantiated.

> **⚠️ V10 Dependency:** V10 (Config-Driven Multi-Agent Orchestration) is currently
> underway and introduces foundational abstractions that V11 builds upon:
> `DocumentStore` Protocol, Backend Registry (string-based, no enum), config-driven
> agent provisioning from scenario YAML, OpenAPI spec templating, generic
> `ScenarioContext` field names (`graph_database` replacing `gremlin_database`),
> and frontend genericization. This plan assumes V10 Phases 0–9 are **complete**
> before V11 implementation begins. Where V10 changes affect V11's design,
> the specific impacts are called out inline. See the
> [V10 Coordination](#v10-coordination--impacts) section for a summary.

---

## Requirements (Original)

1. Manually provide a Fabric workspace ID
2. Read all available ontologies and provide as a list for graph explorer agent
3. Select the desired ontology
4. Read all available eventhouses and provide as a list for telemetry agent
5. Query graph to retrieve topology and display it using the graph visualizer module
6. Graph Explorer and Graph telemetry agent will be bound with Fabric data connection — So a connection to the fabric workspace must be created
7. ~~In Data sources settings menu... Have a checkbox. Add a first tab basically to choose which backend will be used. To choose whether using a cosmosDB backend or fabric backend. Clicking it will grey out the cosmosDB tabs and ungrey the fabric tab. In total there are four tabs now.~~ **Revised (UI/UX audit):** A backend dropdown at the top of Settings modal selects CosmosDB or Fabric. The tab bar **adapts contextually** — `[Scenarios] [Data Sources] [Upload]` for CosmosDB, `[Scenarios] [Fabric Setup] [Upload]` for Fabric. No greyed-out tabs (poor UX). See Decision 5 for rationale.
8. Agents will be able to query the fabric ontology freely.

### Requirements Added (UI/UX Audit)

9. **Fabric resource provisioning from UI:** The UI can provision Fabric capacity, Lakehouse, Eventhouse, and Ontology via SSE-streamed API endpoints wrapping the reference scripts in `fabric_implementation_references/scripts/fabric/`. Same progress-bar UX as CosmosDB data uploads. This replaces the requirement to run provisioning scripts manually.
10. **Adaptive "Add Scenario" modal:** When the Fabric backend is selected, the AddScenarioModal changes its upload slots from CosmosDB-specific formats (.tar.gz for graph/telemetry) to Fabric-specific formats (CSVs for Lakehouse tables, CSVs for Eventhouse tables). Shared slots (runbooks, tickets, prompts) remain the same regardless of backend.
11. **Manual Fabric data upload:** The Upload tab adapts to show Lakehouse CSV upload + Eventhouse CSV upload when Fabric is selected, mirroring the CosmosDB upload pattern with the same drag-and-drop, progress-bar UX.
12. **One-click Fabric bootstrapping:** A "Provision Fabric Resources" button on the Fabric Setup tab runs the full provisioning pipeline (capacity attach → workspace create → lakehouse create + populate → eventhouse create + ingest → ontology create) with step-by-step SSE progress, so the user can go from zero to a working Fabric backend in a single action.

### Requirements Added (Service Separation — v2 Revision)

13. **Independent backends:** The CosmosDB graph backend (`cosmosdb-graph-api`) and the Fabric graph backend (`fabric-graph-api`) are **separate services** with their own directories, dependencies, ports, and process entries. Neither imports from or depends on the other. If one is unavailable, the other continues to work.
14. **Graceful degradation:** The UI detects which backends are available (via health checks) and only presents options for running backends. If only one is available, that backend is auto-selected. If neither is available, the UI shows a clear message.
15. **Directory rename:** `graph-query-api/` is renamed to `cosmosdb-graph-api/` to make the separation explicit. All infrastructure files (Dockerfile, supervisord.conf, nginx.conf, vite.config.ts, deploy.sh, azure.yaml) are updated to reflect the rename.

---

## V10 Coordination & Impacts

V10 (Config-Driven Multi-Agent Orchestration) introduces several abstractions
that change how V11 is implemented. This section summarises each V10 change
and its effect on V11.

| V10 Change | V10 Phase | Impact on V11 |
|-----------|-----------|---------------|
| **Directory stays `graph-query-api/`** during V10 | All | V11 Phase 0 renames `graph-query-api/` → `cosmosdb-graph-api/`. All V10 paths (`graph-query-api/stores/`, `graph-query-api/adapters/`, etc.) become `cosmosdb-graph-api/stores/`, `cosmosdb-graph-api/adapters/`, etc. after the rename. |
| **DocumentStore Protocol** (`stores/__init__.py`, `stores/cosmos_nosql.py`) | V10 Ph 1 | Shared concerns (prompts, scenarios, interactions) are accessed via `DocumentStore`, not raw Cosmos SDK. V11's Gap 6 ("Cosmos still required in Fabric mode") could eventually be resolved by adding a Fabric-backed `DocumentStore` — but this is out of scope for V11. |
| **Cosmos Config extraction** (`adapters/cosmos_config.py`) | V10 Ph 2 | Cosmos env vars move from `config.py` to `adapters/cosmos_config.py`. V11's `cosmosdb-graph-api/main.py` health endpoint should import from the new location. |
| **Generic ScenarioContext fields** (`graph_database` replaces `gremlin_database`) | V10 Ph 3 | V11 frontend code and any references to `ScenarioContext` should use `graph_database`, not `gremlin_database`. |
| **NoSQL routers migrated to DocumentStore** | V10 Ph 4 | `router_interactions.py`, `router_scenarios.py`, `router_telemetry.py`, `router_prompts.py` now call `DocumentStore` methods. No direct Cosmos SDK usage in routers. V11 does not modify these files (service separation), so no conflict. |
| **Backend Registry** (string-based, `GraphBackendType` enum removed) | V10 Ph 7 | `GRAPH_BACKEND` is now a `str`, not an enum. All `.value` calls are gone. V11's health endpoint (`cosmosdb-graph-api/main.py`) should return `GRAPH_BACKEND` directly, not `GRAPH_BACKEND.value`. |
| **Config-driven agent provisioner** (`provision_from_config()`) | V10 Ph 8 | **Major impact on V11 Item 4.** The provisioner no longer uses a hardcoded `OPENAPI_SPEC_MAP` dispatch. Instead, the scenario YAML `data_sources.graph.connector` field determines which OpenAPI spec template to use. Adding Fabric means: (a) adding a `"fabric-gql"` connector entry to the provisioner's connector→spec resolution, and (b) the scenario YAML declares `connector: "fabric-gql"` for Fabric scenarios. See revised Item 4. |
| **OpenAPI Spec Templating** | V10 Ph 9 | Specs use `.replace()` per-placeholder. V11's `fabric.yaml` should follow the same template pattern with `{base_url}`, `{graph_name}`, `{query_language_description}` placeholders. |
| **Config-driven prompts** | V10 Ph 10 | Prompt-to-agent mapping comes from scenario YAML, not `PROMPT_AGENT_MAP`. Fabric scenarios define their own prompt files in YAML. |
| **Frontend genericization** (ScenarioContext, graphConstants, stub agents) | V10 Ph 11 | **Major impact on V11 Item 5.** The frontend is already config-aware after V10: `ScenarioContext` uses resource names from `SavedScenario.resources`, `graphConstants.ts` maps are empty (colors from config), agents are loaded dynamically from `agent_ids.json`. V11's frontend changes build on this foundation instead of modifying hardcoded structures. |
| **Resource Visualizer backend** (`GET /api/config/resources`) | V10 Ph 12 | Fabric resources (workspace, ontology, eventhouse) should appear as nodes in the resource visualizer graph. V11's resource graph builder should emit Fabric-specific node types. |
| **Infrastructure genericization** (Bicep removes scenario-specific resources) | V10 Ph 0 | V11's Phase 0 infrastructure changes (Dockerfile, supervisord, nginx, deploy.sh) must coordinate with V10 Phase 0's Bicep cleanup. Scenario-specific env vars (`COSMOS_GREMLIN_GRAPH`, `RUNBOOKS_INDEX_NAME`, etc.) are already removed by V10. V11 only adds Fabric env vars. |
| **Scenario YAML v2.0** (`data_sources:` replaces `cosmos:`, `agents:` section added) | V10 Ph 13 | Fabric scenarios use the v2.0 format with `data_sources.graph.connector: "fabric-gql"` and `data_sources.telemetry.connector: "fabric-kql"`. The `_normalize_manifest()` backward compatibility layer handles old-format YAML. |

### Execution Order

V10 and V11 share Phase 0 (infrastructure). The recommended execution order:

1. **V10 Phases 0–9** — Core genericization (DocumentStore, registry, config provisioner)
2. **V11 Phase 0** — Directory rename + add `fabric-graph-api` to infra
3. **V11 Phases 1–3.5** — Build `fabric-graph-api` service (independent of V10)
4. **V10 Phases 10–13** — Config-driven prompts, frontend, resource viz, telco-noc migration
5. **V11 Phase 4** — Agent provisioner Fabric entries (requires V10 Ph 8+9)
6. **V11 Phase 5** — Frontend adaptive UI (builds on V10 Ph 11)
7. **V11 Phase 6** — End-to-end testing

Phases V11.1–V11.3.5 can run in parallel with V10.10–V10.13 since `fabric-graph-api` is fully independent.

---

## Implementation Status

| Phase | Status | Scope |
|-------|--------|-------|
| **Phase 0:** Directory rename + infrastructure | ⬜ Not started | Rename `graph-query-api` → `cosmosdb-graph-api`, update Dockerfile, supervisord, nginx, vite.config, deploy.sh, azure.yaml. Coordinate with V10 Phase 0 (Bicep genericization). |
| **Phase 1:** `fabric-graph-api` service setup | ⬜ Not started | New directory, `pyproject.toml`, `config.py`, `models.py`, `main.py` |
| **Phase 2:** Fabric graph backend | ⬜ Not started | `fabric_backend.py`, `router_graph.py`, `router_topology.py` in `fabric-graph-api` |
| **Phase 3:** Fabric discovery endpoints | ⬜ Not started | `router_discovery.py` in `fabric-graph-api` |
| **Phase 3.5:** Fabric provisioning API | ⬜ Not started | `api/app/routers/fabric_provision.py` (stays in API service) |
| **Phase 4:** Agent provisioner changes | ⬜ Not started | `openapi/fabric.yaml` (in `fabric-graph-api`), connector registration in config-driven provisioner (V10 Ph 8 prerequisite) |
| **Phase 5:** Frontend — adaptive backend UI + resilience | ⬜ Not started | Backend detection, `/query/*` vs `/fabric/*` routing, graceful degradation. Builds on V10 Ph 11 frontend genericization. |
| **Phase 6:** End-to-end integration testing | ⬜ Not started | Manual verification, mock Fabric mode |

### Deviations From Plan (Original V9 → V9 Revised)

| # | Original Plan Said | What Changed | Rationale |
|---|-----------|---------------|-----------|
| D-1 | Add `FABRIC` enum to `graph-query-api/config.py` `GraphBackendType` | No changes to cosmosdb-graph-api config. Fabric config lives in `fabric-graph-api/config.py` | Service separation — Fabric code does not touch Cosmos code |
| D-2 | Add `backends/fabric.py` inside `graph-query-api/backends/` | `fabric_backend.py` lives in `fabric-graph-api/` as a top-level module | Separate service, separate directory |
| D-3 | Add `router_fabric.py` inside `graph-query-api/` | Discovery endpoints live in `fabric-graph-api/router_discovery.py` | Separate service |
| D-4 | Add Fabric fields to `graph-query-api/models.py` `GraphQueryRequest` | Fabric models are in `fabric-graph-api/models.py`, completely independent | No cross-contamination of Cosmos models |
| D-5 | Add Fabric fields to `graph-query-api/config.py` `ScenarioContext` | Fabric service has its own context model. Cosmos `ScenarioContext` is unchanged | Service isolation |
| D-6 | Modify `graph-query-api/router_graph.py` to pass workspace/model IDs | Cosmos `router_graph.py` is unchanged. Fabric has its own `router_graph.py` | No changes to working Cosmos code |
| D-7 | Modify `graph-query-api/router_telemetry.py` with 501 guard clause | Cosmos `router_telemetry.py` is unchanged. Fabric telemetry (KQL) is deferred — `fabric-graph-api` simply doesn't expose a telemetry endpoint yet | Cleaner than patching existing code with backend-aware guards |
| D-8 | Fabric endpoints at `/query/fabric/*` (same port 8100) | Fabric endpoints at `/fabric/*` on port 8200 (separate process) | True process-level isolation; if one crashes, the other is unaffected |
| D-9 | nginx.conf `/query/*` covers fabric automatically | New `/fabric/` location block added to nginx.conf proxying to port 8200 | Different service, different port |
| D-10 | Single supervisord program for graph-query-api | Two supervisord programs: `cosmosdb-graph-api` (port 8100) and `fabric-graph-api` (port 8200) | Separate processes |
| D-11 | Dockerfile builds one graph-query-api | Dockerfile builds both `cosmosdb-graph-api` and `fabric-graph-api` | Two services in the unified container |
| D-12 | No directory rename | `graph-query-api/` → `cosmosdb-graph-api/` | Explicit naming matches the Cosmos-specific nature of the service |

### Deviations Retained From Original V9

These deviations from the first V9 audit still apply:

| # | Plan Said | What Was Done | Rationale |
|---|-----------|---------------|-----------|
| D-R1 | GQL endpoint: `/graphqlapis/{id}/graphql` | Corrected to `/GraphModels/{id}/executeQuery?beta=True` | Reference `test_gql_query.py` uses this endpoint |
| D-R2 | Response format: standard GraphQL `{"data": {...}}` | Corrected to Fabric-specific: `{"status": {...}, "result": {"columns": [...], "data": [...]}}` | Reference `test_gql_query.py` parses this format |
| D-R3 | Ontology item type: `"GraphQLApi"` | Corrected to `"Ontology"` via `/workspaces/{id}/ontologies` endpoint | Reference `provision_ontology.py` uses `/ontologies` |
| D-R4 | GQL syntax: `{ routers { id } }` (GraphQL style) | Corrected to MATCH/RETURN: `MATCH (r:CoreRouter) RETURN r.RouterId` | GQL (ISO GQL) uses MATCH/RETURN syntax |
| D-R5 | `get_topology()` uses `__schema` introspection | Removed. GQL doesn't support `__schema`. Discover types via Fabric REST API | GQL is not GraphQL |
| D-R6 | No 429/rate-limit handling | Added retry loop with exponential backoff (5 retries, 15s × attempt) | Reference `test_gql_query.py` implements this |
| D-R7 | Module-level `credential = DefaultAzureCredential()` | Use lazy `get_credential()` | Prevents crash in offline/mock modes |

---

## Table of Contents

- [Requirements](#requirements-original)
- [V10 Coordination & Impacts](#v10-coordination--impacts)
- [Architecture Decision: Service Separation](#architecture-decision-service-separation)
- [Codebase Conventions & Context](#codebase-conventions--context)
- [Overview of Changes](#overview-of-changes)
- [Key Design Decisions](#key-design-decisions)
- [Item 0: Directory Rename & Infrastructure](#item-0-directory-rename--infrastructure)
- [Item 1: fabric-graph-api Service Setup](#item-1-fabric-graph-api-service-setup)
- [Item 2: Fabric Graph Backend](#item-2-fabric-graph-backend)
- [Item 3: Fabric Discovery Endpoints](#item-3-fabric-discovery-endpoints)
- [Item 3.5: Fabric Provisioning API](#item-35-fabric-provisioning-api)
- [Item 4: Agent Provisioner Changes](#item-4-agent-provisioner-changes)
- [Item 5: Frontend — Adaptive Backend UI](#item-5-frontend--adaptive-backend-ui)
- [Implementation Phases](#implementation-phases)
- [File Change Inventory](#file-change-inventory)
- [Cross-Cutting Concerns & Gaps](#cross-cutting-concerns--gaps)
- [Edge Cases & Validation](#edge-cases--validation)
- [Migration & Backwards Compatibility](#migration--backwards-compatibility)

---

## Architecture Decision: Service Separation

### Problem

The original V9 plan added Fabric as a backend option **inside** `graph-query-api`, sharing config, models, routing, and the backend abstraction layer. This entangled the two backends:

- Adding `FABRIC` to `GraphBackendType` in `config.py` meant Cosmos code loaded Fabric config paths
- Adding Fabric fields to `ScenarioContext` and `GraphQueryRequest` polluted Cosmos models
- A bug or crash in Fabric code (new, untested) could bring down Cosmos queries (stable, proven)
- Fabric dependencies (`httpx`) would be installed even when only Cosmos is needed
- Testing Fabric in isolation required mock-patching the shared backend dispatch
- The GRAPH_BACKEND env var created a global toggle — you couldn't have both active simultaneously

### Decision: Two independent services

```
┌─────────────────────────────────────────────────────────────────┐
│                    Unified Container (:80)                       │
│                                                                  │
│  ┌──────────┐  ┌─────────────────┐  ┌─────────────────────────┐ │
│  │  nginx    │  │ API service     │  │ cosmosdb-graph-api      │ │
│  │  (:80)    │  │ (:8000)         │  │ (:8100)                 │ │
│  │           │  │                 │  │                         │ │
│  │ /api/* ──►│  │ Agent orch.     │  │ Gremlin graph queries   │ │
│  │           │  │ Config/apply    │  │ Cosmos NoSQL telemetry  │ │
│  │ /query/*►─┤  │ Fabric provision│  │ Topology, ingest, etc.  │ │
│  │           │  │ (SSE endpoints) │  │ Prompts, scenarios      │ │
│  │ /fabric/*►┤  │                 │  │ Interactions, search    │ │
│  │           │  └─────────────────┘  └─────────────────────────┘ │
│  │           │                                                   │
│  │           │  ┌─────────────────────────┐                      │
│  │           │  │ fabric-graph-api        │                      │
│  │           │  │ (:8200)          NEW    │                      │
│  │           │  │                         │                      │
│  │           │  │ GQL graph queries       │                      │
│  │           │  │ Fabric topology         │                      │
│  │           │  │ Discovery (ontologies,  │                      │
│  │           │  │   eventhouses, models)  │                      │
│  │           │  └─────────────────────────┘                      │
│  └──────────┘                                                    │
└─────────────────────────────────────────────────────────────────┘
```

**Rules:**
1. `cosmosdb-graph-api` has **zero** Fabric imports, config, or code paths
2. `fabric-graph-api` has **zero** Cosmos/Gremlin imports, config, or code paths
3. Each service has its own `pyproject.toml`, dependencies, config, and models
4. Each runs as a separate supervisord process on its own port
5. nginx proxies `/query/*` → `:8100` and `/fabric/*` → `:8200`
6. The frontend detects which services are available and adapts the UI accordingly
7. If `fabric-graph-api` is not running (missing Fabric env vars, not deployed, crashed), all Cosmos functionality is unaffected — the Fabric option simply doesn't appear in the UI
8. If `cosmosdb-graph-api` is not running, Fabric graph queries still work — but prompts/scenarios/interactions (Cosmos-dependent) are unavailable

### What lives where

| Concern | Service | Port | URL prefix | Rationale |
|---------|---------|------|------------|-----------|
| Gremlin graph queries | `cosmosdb-graph-api` | 8100 | `/query/graph` | Cosmos-specific |
| Cosmos NoSQL telemetry | `cosmosdb-graph-api` | 8100 | `/query/telemetry` | Cosmos-specific |
| CosmosDB topology | `cosmosdb-graph-api` | 8100 | `/query/topology` | Uses Gremlin backend |
| Graph data ingest (`.tar.gz`) | `cosmosdb-graph-api` | 8100 | `/query/upload/*` | Cosmos-specific |
| Scenario management | `cosmosdb-graph-api` | 8100 | `/query/scenarios/*` | Cosmos + disk YAML |
| Prompts | `cosmosdb-graph-api` | 8100 | `/query/prompts/*` | Cosmos NoSQL |
| Interactions | `cosmosdb-graph-api` | 8100 | `/query/interactions/*` | Cosmos NoSQL |
| AI Search indexes | `cosmosdb-graph-api` | 8100 | `/query/indexes` | AI Search |
| GQL graph queries | `fabric-graph-api` | 8200 | `/fabric/graph` | Fabric-specific |
| Fabric topology | `fabric-graph-api` | 8200 | `/fabric/topology` | Uses GQL backend |
| Fabric discovery | `fabric-graph-api` | 8200 | `/fabric/ontologies`, etc. | Fabric REST API |
| Fabric health | `fabric-graph-api` | 8200 | `/fabric/health` | Service health |
| Agent orchestration | API service | 8000 | `/api/*` | Backend-agnostic |
| Fabric provisioning | API service | 8000 | `/api/fabric/*` | Orchestration + SSE |
| Config/apply (agents) | API service | 8000 | `/api/config/apply` | Agent provisioning |

> **Note on shared concerns:** Prompts, scenarios, and interactions are stored in Cosmos NoSQL. They remain in `cosmosdb-graph-api` because they depend on Cosmos infrastructure. In Fabric mode, the frontend still calls `/query/prompts/*` and `/query/scenarios/*` — these are not graph-backend-specific. If Cosmos is completely unavailable, prompts and scenario metadata won't work regardless of the graph backend. This is acceptable: Fabric replaces the **graph topology** and **telemetry** backends, not the entire data platform. See Gap 6 for details.

### Supervisord startup behaviour

```ini
[program:fabric-graph-api]
# autostart defaults to true — supervisord always starts this process.
# If Fabric env vars are not configured, the service starts but returns
# 503 on all endpoints (health check reports unhealthy).
# The frontend detects this via the health probe and hides the Fabric option.
autostart=true
autorestart=true
```

This is simpler than conditional startup logic. The service self-reports its readiness via `/fabric/health`. The frontend and any external health checks respect this.

---

## Codebase Conventions & Context

> **⚠️ Post-V10 state:** This section describes the codebase **after** V10
> genericization is complete. Key changes from pre-V10:
> - `GraphBackendType` enum is gone — `GRAPH_BACKEND` is now a plain `str`
> - Cosmos env vars live in `adapters/cosmos_config.py` (moved from `config.py`)
> - `ScenarioContext.gremlin_database` renamed to `.graph_database`
> - NoSQL routers use `DocumentStore` Protocol (not raw Cosmos SDK)
> - Agent provisioning is config-driven via `provision_from_config()` reading
>   scenario YAML `agents:` section
> - Frontend `ScenarioContext` uses config-specified resources from
>   `SavedScenario.resources`, with convention-based fallback
> - `graphConstants.ts` hardcoded maps are empty — colors/sizes come from
>   scenario `graph_styles` or auto-hash

### Request Routing (Updated)

| URL prefix | Proxied to | Port | Config |
|------------|-----------|------|--------|
| `/api/*` | API service | `:8000` | `vite.config.ts` (dev), `nginx.conf` (prod) |
| `/query/*` | cosmosdb-graph-api | `:8100` | `vite.config.ts` (dev), `nginx.conf` (prod) |
| `/fabric/*` | fabric-graph-api | `:8200` | `vite.config.ts` (dev), `nginx.conf` (prod) — **NEW** |
| `/health` | API service | `:8000` | `vite.config.ts` (dev), `nginx.conf` (prod) |

### Naming Conventions

| Concept | Example | Derivation |
|---------|---------|-----------|
| Graph name | `"cloud-outage-topology"` | From scenario YAML `data_sources.graph.config.graph` (V10 v2.0 schema) |
| Scenario prefix | `"cloud-outage"` | `graph_name.rsplit("-", 1)[0]` |
| Telemetry container | `"cloud-outage-AlertStream"` | From scenario YAML `data_sources.telemetry.config.container_prefix` + container name |
| Search index | `"cloud-outage-runbooks-index"` | From scenario YAML `data_sources.search_indexes.runbooks.index_name` |
| Prompts container | `"cloud-outage"` | Same as prefix |

> **V10 change:** Names are now read from scenario YAML `data_sources:` section
> (v2.0 schema) instead of being derived by convention alone. The convention
> logic remains as a fallback via `_normalize_manifest()` for old-format YAML files.

> **Fabric routing:** In Fabric mode, graph data is resolved via `workspace_id` + `graph_model_id` passed in the request body to `/fabric/graph`. The `X-Graph` header is still sent to `/query/*` endpoints for prompts/telemetry container routing (those remain in Cosmos via cosmosdb-graph-api). Fabric endpoints do not use `X-Graph` at all.

### Import & Code Style Conventions

```python
# cosmosdb-graph-api: post-V10 structure
# Generic platform config stays in config.py:
GRAPH_BACKEND: str = os.getenv("GRAPH_BACKEND", "cosmosdb")  # string, not enum (V10 Ph 7)

# Cosmos-specific env vars live in adapters/cosmos_config.py (V10 Ph 2):
from adapters.cosmos_config import COSMOS_GREMLIN_ENDPOINT

# NoSQL routers use DocumentStore protocol (V10 Ph 4):
from stores import get_document_store
store = get_document_store("interactions", "interactions", "/scenario")
await store.list(query="SELECT * FROM c", partition_key=scenario)

# fabric-graph-api: same env pattern, Fabric-specific vars:
FABRIC_WORKSPACE_ID = os.getenv("FABRIC_WORKSPACE_ID", "")
FABRIC_API = os.getenv("FABRIC_API_URL", "https://api.fabric.microsoft.com/v1")

# Both services use lazy credential init:
_credential = None
def get_credential():
    global _credential
    if _credential is None:
        _credential = DefaultAzureCredential()
    return _credential
```

### Data Format Conventions

| Convention | Format | Where Used |
|-----------|--------|------------|
| Graph query response | `{"columns": [...], "data": [...]}` | Both services' `/graph` endpoints, OpenAPI specs |
| Topology response | `{"nodes": [...], "edges": [...], "meta": {...}}` | Both services' `/topology` endpoints, frontend `useTopology.ts` |
| SSE progress events | `event: progress\ndata: {"step": "...", "detail": "..."}\n\n` | Upload and provisioning endpoints |
| Per-request graph routing (Cosmos) | `X-Graph` header → `ScenarioContext` | All `/query/*` routers |
| Per-request graph routing (Fabric) | `workspace_id` + `graph_model_id` in request body | `/fabric/graph`, `/fabric/topology` |
| Scenario config (V10) | `scenario.yaml` v2.0 with `data_sources:` + `agents:` | Upload, provisioning, resource visualizer |

---

## Overview of Changes

| # | Item | Category | Impact | Effort |
|---|------|----------|--------|--------|
| 0 | Directory rename + infrastructure | Infra | High — foundation | Medium |
| 1 | `fabric-graph-api` service setup | Backend | High — new service skeleton | Small |
| 2 | Fabric graph backend (GQL queries + topology) | Backend | High — core query path | Large |
| 3 | Fabric discovery endpoints | Backend | Medium — enables UI dropdowns | Medium |
| 3.5 | Fabric provisioning API (in API service) | Backend | High — one-click bootstrapping | Medium |
| 4 | Agent provisioner — Fabric OpenAPI spec | Backend | High — agents can query Fabric | Medium |
| 5 | Frontend — adaptive backend UI + resilience | Frontend | High — user-facing | Large |

### Dependency Graph

```
V10 Phases 0–9 (complete) ──┐
                             │
V11 Phase 0 (rename+infra)──┤
                             ├──▶ Phase 1 (fabric-graph-api setup)
                             │       │
                             │       ├──▶ Phase 2 (Fabric graph backend)
                             │       │       │
                             │       │       └──────────────────────────────┐
                             │       ├──▶ Phase 3 (discovery endpoints)    │
                             │       │                                     │
                             │       └──▶ Phase 3.5 (provisioning API)     │
                             │                                             │
V10 Phases 8+9 (prov+tmpl)──┼──────────────▶ Phase 4 (OpenAPI + provisioner)
                             │
V10 Phase 11 (FE generic) ──┼──────────────▶ Phase 5 (frontend)
                             │                   │
                             │                   └──▶ Phase 6 (E2E testing)
                             │
V10 Phase 12 (resource viz)──────────────── Phase 5 adds Fabric nodes
```

V10 Phases 0–9 are prerequisites for V11 Phase 0 (directory rename + infra).
V11 Phases 1–3.5 are independent of remaining V10 phases (fabric-graph-api is a standalone service).
V11 Phase 4 requires V10 Phases 8+9 (config-driven provisioner + OpenAPI templating).
V11 Phase 5 requires V10 Phase 11 (frontend genericization provides the config-aware scaffold).
V11 Phase 6 requires all prior V11 phases + V10 Phase 13 (telco-noc migration validates full stack).

---

## Key Design Decisions

### Decision 0: Service separation — independent processes (NEW)

**Chosen:** Two fully independent services (`cosmosdb-graph-api` on `:8100`, `fabric-graph-api` on `:8200`) with zero code sharing.

**Rationale:**
- Fabric code cannot crash or destabilize the proven Cosmos path
- Each service has only the dependencies it needs (no `httpx` in Cosmos, no `gremlinpython` in Fabric)
- The UI works if either service is unavailable — true independence
- Developers can work on Fabric without touching any Cosmos code (and vice versa)
- Simpler testing: each service is tested in isolation
- Clear ownership boundaries

**Trade-offs:**
- Some conceptual duplication (both have a `config.py`, `models.py`, `main.py`)
- Dockerfile builds two Python services instead of one (slightly larger image, ~50MB more due to separate venvs)
- Frontend must make health checks and route to different URL prefixes based on selected backend
- OpenAPI specs live in different directories (`cosmosdb-graph-api/openapi/` vs `fabric-graph-api/openapi/`)

**Why not a shared `GraphBackend` Protocol?** The original plan used a Protocol + factory pattern (`get_backend_for_context()`). This is elegant but creates coupling: both backends share models, config enums, routing code, and process space. The overhead of a second slim service is small; the isolation benefit is large.

### Decision 1: Agent tool strategy — `OpenApiTool` proxy

**Retained from original.** Same pattern for both backends:
- CosmosDB agents get `OpenApiTool(spec=cosmosdb.yaml)` → `POST /query/graph`
- Fabric agents get `OpenApiTool(spec=fabric.yaml)` → `POST /fabric/graph`

The `{base_url}` substitution in the spec handles the path prefix difference. Agents don't need to know which backend they're using — their OpenAPI spec documents the correct query syntax (Gremlin vs GQL) and endpoint.

### Decision 2: Query language — GQL for Fabric backend

**Retained.** Fabric Graph Model supports GQL natively via REST API (beta). The `fabric-graph-api` backend will:
- Accept GQL query strings (MATCH/RETURN syntax)
- Call `POST https://api.fabric.microsoft.com/v1/workspaces/{id}/GraphModels/{model_id}/executeQuery?beta=True`
- Handle the response format: `{"status": {...}, "result": {"columns": [...], "data": [...]}}`
- Implement retry with exponential backoff for HTTP 429
- Return standardized `{"columns": [...], "data": [...]}` format (same shape as Cosmos response)

### Decision 3: Telemetry backend — deferred

**Retained with modification.** When Fabric is selected, telemetry queries (KQL) are **out of scope** for this plan.

**Change from original:** Instead of adding a 501 guard clause to `cosmosdb-graph-api/router_telemetry.py` (which would be Fabric-aware code in the Cosmos service), `fabric-graph-api` simply **does not expose a telemetry endpoint**. The frontend knows this: when Fabric is selected, the telemetry panel shows "Telemetry queries not yet available for Fabric backend" instead of calling an endpoint that doesn't exist. No Cosmos code is modified.

> **⚠️ This means telemetry queries will NOT work in Fabric mode until a future `POST /fabric/telemetry` endpoint is added.** Graph topology and agent-driven graph exploration work fully.

### Decision 4: Fabric routing — request body IDs

**Retained.** `workspace_id` and `graph_model_id` are passed in the `GraphQueryRequest` body to `/fabric/graph`. They default to env vars when omitted.

The `X-Graph` header is still sent by the frontend to `/query/*` endpoints (Cosmos prompts/scenarios/telemetry routing). Fabric endpoints do not read any headers — everything is in the request body.

### Decision 5: Frontend tab structure — context-adaptive 3-tab layout

**Retained.** Backend dropdown + adaptive tabs:
- CosmosDB: `[Scenarios] [Data Sources] [Upload]`
- Fabric: `[Scenarios] [Fabric Setup] [Upload]`

**New addition for resilience:** The backend dropdown only shows backends whose health check passes:
- If `GET /query/health` responds 200 → show "CosmosDB" option
- If `GET /fabric/health` responds 200 → show "Fabric" option
- If only one passes → auto-select it, dropdown is disabled (single option)
- If neither passes → show error banner

### Decision 6: Capacity provisioning is an ARM operation

**Retained.** Fabric capacity is provisioned via `azd up` (ARM). The UI provisioning pipeline accepts `capacity_id` as input.

### Decision 7: Fabric provisioning from UI

**Retained.** Provisioning API endpoints stay in the **API service** (`api/app/routers/fabric_provision.py` at `/api/fabric/*`). This is consistent with the API service's role as the orchestration layer.

### Decision 8: URL prefix convention (NEW)

**Chosen:** `/fabric/*` for the Fabric service, `/query/*` remains for Cosmos.

| Backend | URL prefix | Port | Service |
|---------|-----------|------|---------|
| CosmosDB | `/query/*` | 8100 | cosmosdb-graph-api |
| Fabric | `/fabric/*` | 8200 | fabric-graph-api |

**Rationale:** Different prefixes make nginx routing trivial (one `location` block per service). No ambiguity, no header-based routing needed. The frontend simply switches which prefix it uses based on the selected backend.

**Considered alternative:** Both services use `/query/*` internally, nginx routes based on a custom header. Rejected — adds routing complexity, makes curl testing harder, and defeats the simplicity of the separation.

---

## Item 0: Directory Rename & Infrastructure

> **V10 Coordination:** V10 Phase 0 (Infrastructure Genericization) removes scenario-specific
> env vars from Bicep, `deploy.sh`, and `azure_config.env.template`. It also cleans up
> hardcoded scenario references in infrastructure files. **V11 Phase 0 should run after
> V10 Phase 0** so that the infrastructure files are already in their genericized state
> before V11 adds Fabric-specific variables and the directory rename.
>
> Specifically, after V10 Phase 0:
> - `deploy.sh` no longer contains scenario-specific echo blocks (just generic start instructions)
> - `azure_config.env.template` no longer lists scenario-specific env vars — V11 adds the Fabric section to this cleaned-up template
> - Bicep no longer provisions scenario-specific Cosmos databases — V11's Fabric capacity is additive
>
> Additionally, V10 Phases 1–3 create new directories inside `graph-query-api/` (`stores/`,
> `adapters/`, `services/`). The directory rename (`graph-query-api/ → cosmosdb-graph-api/`)
> must happen **after** these V10 directories exist, or they must be created in the renamed
> location. The recommended approach: complete V10 Phases 0–9, then do the V11 Phase 0 rename.

### Current State (post-V10)

- `graph-query-api/` contains all graph query logic (Cosmos Gremlin, Cosmos NoSQL telemetry, ingest, prompts, scenarios, etc.)
- **Post-V10 additions inside `graph-query-api/`:** `stores/` (DocumentStore), `adapters/` (cosmos_config), `services/` (backend registry)
- Dockerfile copies `graph-query-api/` to `/app/graph-query-api/` and runs it on port 8100
- `supervisord.conf` has a `[program:graph-query-api]` at `/app/graph-query-api`
- `nginx.conf` proxies `/query/*` to `127.0.0.1:8100`
- `vite.config.ts` proxies `/query` to `localhost:8100`
- `deploy.sh` references `graph-query-api` in local start commands (post-V10: genericized, fewer occurrences)
- `azure.yaml` comment references `graph-query-api`
- **Post-V10:** `GRAPH_BACKEND` is a plain string (not an enum), set via env var and resolved by the Backend Registry

### Target State

- `graph-query-api/` renamed to `cosmosdb-graph-api/`
- All infrastructure files updated with the new name
- New `fabric-graph-api/` directory exists (created in Item 1)
- Dockerfile builds both services
- supervisord manages both services
- nginx proxies to both services
- vite.config.ts proxies to both services

### Changes

#### Directory rename

```bash
git mv graph-query-api cosmosdb-graph-api
```

This is a simple rename. All Python code inside is unchanged — no imports reference the directory name. The only things that reference `graph-query-api` as a string are infrastructure files (Dockerfile, supervisord, nginx, deploy.sh, azure.yaml).

#### `Dockerfile` — Build both services

```dockerfile
# ============================================================================
# Unified Container — All 4 services in one container
#   - nginx (:80)                  — React SPA + reverse proxy
#   - API uvicorn (:8000)          — FastAPI orchestrator (Foundry agents)
#   - cosmosdb-graph-api uvicorn (:8100) — Gremlin/telemetry queries (Cosmos)
#   - fabric-graph-api uvicorn (:8200)   — GQL queries (Fabric)    ← NEW
#
# Build context: project root (.)
# ============================================================================

# ── Stage 1: Build React frontend ──────────────────────────────────
FROM node:20-alpine AS frontend-build

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --silent

COPY frontend/ ./
RUN npm run build

# ── Stage 2: Python runtime + nginx + supervisord ──────────────────
FROM python:3.11-slim

# Install nginx and supervisord
RUN apt-get update && \
    apt-get install -y --no-install-recommends nginx supervisor && \
    rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# ── cosmosdb-graph-api dependencies (renamed from graph-query-api) ─
WORKDIR /app/cosmosdb-graph-api
COPY cosmosdb-graph-api/pyproject.toml cosmosdb-graph-api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY cosmosdb-graph-api/*.py ./
COPY cosmosdb-graph-api/backends/ ./backends/
COPY cosmosdb-graph-api/stores/ ./stores/       # V10: DocumentStore
COPY cosmosdb-graph-api/adapters/ ./adapters/   # V10: cosmos_config
COPY cosmosdb-graph-api/services/ ./services/   # V10: backend registry
COPY cosmosdb-graph-api/openapi/ ./openapi/

# ── fabric-graph-api dependencies (NEW) ────────────────────────────
WORKDIR /app/fabric-graph-api
COPY fabric-graph-api/pyproject.toml fabric-graph-api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY fabric-graph-api/*.py ./
COPY fabric-graph-api/openapi/ ./openapi/

# ── API dependencies ──────────────────────────────────────────────
WORKDIR /app/api
COPY api/pyproject.toml api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY api/app/ ./app/

# Copy scripts needed at runtime
RUN mkdir -p /app/scripts
COPY scripts/agent_provisioner.py /app/scripts/

# Copy scenario manifests for runtime resolution
COPY data/scenarios/ /app/data/scenarios/

# ── Frontend static files ─────────────────────────────────────────
COPY --from=frontend-build /build/dist /usr/share/nginx/html

# ── Nginx config ──────────────────────────────────────────────────
RUN rm -f /etc/nginx/sites-enabled/default /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/default.conf

# ── Supervisord config ────────────────────────────────────────────
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# ── Environment ───────────────────────────────────────────────────
ENV AGENT_IDS_PATH=/app/scripts/agent_ids.json

EXPOSE 80

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
```

Key Dockerfile changes:
1. `WORKDIR /app/graph-query-api` → `WORKDIR /app/cosmosdb-graph-api` and all `COPY graph-query-api/` → `COPY cosmosdb-graph-api/`
2. New `WORKDIR /app/fabric-graph-api` block for the Fabric service
3. Comment updated to list 4 services instead of 3

#### `supervisord.conf` — Add fabric-graph-api program

```ini
[supervisord]
nodaemon=true
logfile=/dev/stdout
logfile_maxbytes=0
pidfile=/var/run/supervisord.pid

[program:nginx]
command=nginx -g "daemon off;"
autostart=true
autorestart=true
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0
priority=10

[program:api]
command=/usr/local/bin/uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
directory=/app/api
autostart=true
autorestart=true
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0
priority=20

[program:cosmosdb-graph-api]
command=/usr/local/bin/uv run uvicorn main:app --host 127.0.0.1 --port 8100
directory=/app/cosmosdb-graph-api
autostart=true
autorestart=true
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0
priority=20

[program:fabric-graph-api]
command=/usr/local/bin/uv run uvicorn main:app --host 127.0.0.1 --port 8200
directory=/app/fabric-graph-api
autostart=true
autorestart=true
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0
priority=20
```

Changes:
1. `[program:graph-query-api]` renamed to `[program:cosmosdb-graph-api]`, directory updated
2. New `[program:fabric-graph-api]` on port 8200

> **Note:** `fabric-graph-api` always starts (autostart=true). If Fabric env vars are missing, the service starts but its `/fabric/health` endpoint returns unhealthy status. The frontend detects this and hides the Fabric option. This is simpler than conditional startup logic in supervisord (which doesn't support it natively without wrapper scripts).

#### `nginx.conf` — Add `/fabric/` location block

```nginx
server {
    listen       80;
    server_name  _;

    client_max_body_size 100m;
    root   /usr/share/nginx/html;
    index  index.html;

    # SPA fallback
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API service (:8000)
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
        chunked_transfer_encoding on;
    }

    # Health check → API service
    location /health {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
    }

    # cosmosdb-graph-api (:8100) — Cosmos Gremlin/NoSQL queries
    location /query/ {
        proxy_pass http://127.0.0.1:8100;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 600s;
    }

    # fabric-graph-api (:8200) — Fabric GQL queries + discovery   ← NEW
    location /fabric/ {
        proxy_pass http://127.0.0.1:8200;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 600s;
    }

    # Security headers
    add_header X-Frame-Options SAMEORIGIN;
    add_header X-Content-Type-Options nosniff;

    # Gzip
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml;
}
```

Changes:
1. Comment updated for `cosmosdb-graph-api`
2. New `location /fabric/` block proxying to port 8200 with same settings (SSE support, 600s timeout)

#### `frontend/vite.config.ts` — Add `/fabric` proxy

```typescript
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api/alert': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on('proxyRes', (proxyRes) => {
            proxyRes.headers['cache-control'] = 'no-cache';
            proxyRes.headers['x-accel-buffering'] = 'no';
          });
        },
      },
      '/api/logs': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on('proxyRes', (proxyRes) => {
            proxyRes.headers['cache-control'] = 'no-cache';
            proxyRes.headers['x-accel-buffering'] = 'no';
          });
        },
      },
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/query': {
        target: 'http://localhost:8100',
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on('proxyRes', (proxyRes) => {
            proxyRes.headers['cache-control'] = 'no-cache';
            proxyRes.headers['x-accel-buffering'] = 'no';
          });
        },
      },
      // NEW: fabric-graph-api proxy
      '/fabric': {
        target: 'http://localhost:8200',
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on('proxyRes', (proxyRes) => {
            proxyRes.headers['cache-control'] = 'no-cache';
            proxyRes.headers['x-accel-buffering'] = 'no';
          });
        },
      },
    },
  },
});
```

Changes: New `/fabric` proxy rule targeting port 8200 with SSE support.

#### `deploy.sh` — Update references

There are **3 occurrences** of `graph-query-api` in the current `deploy.sh`:

| Line | Current text | Change to |
|------|-------------|----------|
| 10 | `#   4. Unified Container App deployment (nginx + API + graph-query-api)` | `#   4. Unified Container App deployment (nginx + API + cosmosdb-graph-api + fabric-graph-api)` |
| 470 | `echo "   • Unified Container App (nginx + API + graph-query-api)"` | `echo "   • Unified Container App (nginx + API + cosmosdb-graph-api + fabric-graph-api)"` |
| 593 | `echo "   cd graph-query-api && source ../azure_config.env && uv run uvicorn main:app --host 0.0.0.0 --port 8100 --reload"` | `echo "   cd cosmosdb-graph-api && source ../azure_config.env && uv run uvicorn main:app --host 0.0.0.0 --port 8100 --reload"` |

Additionally, add a **new** Fabric local start command after the cosmosdb-graph-api one (after current line 593 / the `# Terminal 2` block):

```bash
  echo ""
  echo "   # Terminal 3 — Fabric Graph API (optional, requires Fabric env vars)"
  echo "   cd fabric-graph-api && source ../azure_config.env && uv run uvicorn main:app --host 0.0.0.0 --port 8200 --reload"
```

And renumber the existing `# Terminal 3 — Frontend` to `# Terminal 4 — Frontend`.

The full diff for the `--skip-local` instructions block (lines ~585–600) becomes:

```bash
  echo "   To run locally instead:"
  echo "   # Terminal 1 — API"
  echo "   cd api && source ../azure_config.env && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
  echo ""
  echo "   # Terminal 2 — CosmosDB Graph API"
  echo "   cd cosmosdb-graph-api && source ../azure_config.env && uv run uvicorn main:app --host 0.0.0.0 --port 8100 --reload"
  echo ""
  echo "   # Terminal 3 — Fabric Graph API (optional, requires Fabric env vars)"
  echo "   cd fabric-graph-api && source ../azure_config.env && uv run uvicorn main:app --host 0.0.0.0 --port 8200 --reload"
  echo ""
  echo "   # Terminal 4 — Frontend"
  echo "   cd frontend && npm install && npm run dev"
```

> **⚠️ CRITICAL — This must be done in the same commit as the directory rename.** If `deploy.sh` still references `graph-query-api` after the rename, the local start instructions will point to a non-existent directory.

#### `azure.yaml` — Update comment

```yaml
# Single unified service — all 4 services (nginx + API + cosmosdb-graph-api + fabric-graph-api)
# run in one container via supervisord
```

#### `cosmosdb-graph-api/pyproject.toml` — Update project name

```toml
[project]
name = "cosmosdb-graph-api"  # was: graph-query-api
# Everything else unchanged
```

#### `cosmosdb-graph-api/Dockerfile` (standalone) — Update if it exists

The standalone Dockerfile at `graph-query-api/Dockerfile` (now `cosmosdb-graph-api/Dockerfile`) should just get the path references updated:

```dockerfile
# Same content, just the directory context changes
# WORKDIR stays /app, COPY paths stay relative
# No changes needed to the standalone Dockerfile content
```

#### `cosmosdb-graph-api/main.py` — Add `/query/health` endpoint (CRITICAL)

The frontend health detection (Phase 5) probes `GET /query/health` to determine if the CosmosDB backend is available. The current `main.py` only registers `GET /health` — but nginx proxies `/query/*` → `:8100`, so the request arrives at the service as `/query/health`, which returns 404.

**This must be added in Phase 0**, before any frontend health detection code is written, or the CosmosDB backend will appear unavailable to the UI.

Add alongside the existing `/health` endpoint:

```python
@app.get("/query/health", summary="Backend health check (via /query/* proxy)")
async def query_health():
    """Health check accessible through nginx /query/* routing.
    
    The frontend uses this to detect whether the CosmosDB backend
    is available (separate from the API service /health endpoint).
    """
    return {
        "status": "healthy",
        "backend": "cosmosdb",
        "service": "cosmosdb-graph-api",
        "version": app.version,
        "graph_backend": GRAPH_BACKEND,  # Post-V10: plain string, not .value
    }
```

> **Why both `/health` and `/query/health`?** The existing `/health` endpoint is used by supervisord and internal checks (direct port 8100 access). The new `/query/health` is used by the frontend via nginx (`/query/health` → `:8100/query/health`). Both return the same information.
>
> **Post-V10 note:** `GRAPH_BACKEND` is a plain string after V10 Phase 7 (Backend Registry replaces
> `GraphBackendType` enum). Use `GRAPH_BACKEND` directly, not `GRAPH_BACKEND.value`.

#### `scripts/agent_provisioner.py` — Fix OPENAPI_DIR path (CRITICAL)

The current `agent_provisioner.py` has:

```python
OPENAPI_DIR = PROJECT_ROOT / "graph-query-api" / "openapi"
```

After the rename, this path no longer exists and **agent provisioning via `/api/config/apply` breaks immediately**. This must be fixed in the same commit as the directory rename:

```python
OPENAPI_DIR = PROJECT_ROOT / "cosmosdb-graph-api" / "openapi"
```

> **⚠️ This fix was originally planned for Phase 4 but MUST happen in Phase 0.** The rename and the path update are atomic — deploying one without the other breaks agent provisioning. The Phase 4 changes (adding `"fabric-gql"` connector support) are still Phase 4.
>
> **Post-V10 note:** V10 Phase 8 introduces `provision_from_config()` which reads scenario YAML
> to determine connector types and resolve OpenAPI specs. After V10, `OPENAPI_DIR` is used
> by the connector→spec resolution logic (not a hardcoded `OPENAPI_SPEC_MAP`). The path fix
> here is still required — V10's `_resolve_spec_for_connector()` still needs the correct
> base directory to find spec templates.

#### `azure_config.env.template` — Add Fabric section

Add the Fabric variables section so users know what to configure. See Gap 12 for the full variable list. This is additive and does not affect existing CosmosDB deployments.

---

## Item 1: fabric-graph-api Service Setup

### Current State

No `fabric-graph-api/` directory exists.

### Target State

A minimal FastAPI service skeleton with:
- `fabric-graph-api/pyproject.toml` — dependencies
- `fabric-graph-api/config.py` — Fabric-specific env vars and credential
- `fabric-graph-api/models.py` — Request/response models
- `fabric-graph-api/main.py` — FastAPI app with health check
- `fabric-graph-api/openapi/` — directory for OpenAPI specs (Phase 4)

### New Files

#### `fabric-graph-api/pyproject.toml`

```toml
[project]
name = "fabric-graph-api"
version = "0.1.0"
description = "Micro-API for executing GQL queries against Microsoft Fabric Graph Models"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "azure-identity>=1.19.0",
    "httpx>=0.27.0",
    "pydantic>=2.0",
]

[dependency-groups]
dev = []
```

Note the minimal dependency set:
- **No** `gremlinpython` (Cosmos-specific)
- **No** `azure-cosmos` (Cosmos-specific)
- **No** `azure-storage-blob` (Cosmos ingest)
- **No** `azure-search-documents` (AI Search)
- **No** `azure-mgmt-cosmosdb` (Cosmos management)
- **Has** `httpx` for async Fabric REST API calls

#### `fabric-graph-api/config.py`

```python
"""
Configuration — Fabric-specific environment variable loading.

This service is completely independent of cosmosdb-graph-api.
It reads only Fabric-related env vars.
"""

from __future__ import annotations

import os
from azure.identity import DefaultAzureCredential


# ---------------------------------------------------------------------------
# Fabric API settings
# ---------------------------------------------------------------------------

FABRIC_API = os.getenv("FABRIC_API_URL", "https://api.fabric.microsoft.com/v1")
FABRIC_SCOPE = os.getenv("FABRIC_SCOPE", "https://api.fabric.microsoft.com/.default")

# ---------------------------------------------------------------------------
# Workspace / Graph Model / Ontology
# ---------------------------------------------------------------------------

FABRIC_WORKSPACE_ID = os.getenv("FABRIC_WORKSPACE_ID", "")
FABRIC_WORKSPACE_NAME = os.getenv("FABRIC_WORKSPACE_NAME", "")
FABRIC_ONTOLOGY_ID = os.getenv("FABRIC_ONTOLOGY_ID", "")
FABRIC_ONTOLOGY_NAME = os.getenv("FABRIC_ONTOLOGY_NAME", "")
FABRIC_GRAPH_MODEL_ID = os.getenv("FABRIC_GRAPH_MODEL_ID", "")

# ---------------------------------------------------------------------------
# Eventhouse / KQL (for future telemetry support)
# ---------------------------------------------------------------------------

FABRIC_EVENTHOUSE_ID = os.getenv("FABRIC_EVENTHOUSE_ID", "")
FABRIC_EVENTHOUSE_NAME = os.getenv("FABRIC_EVENTHOUSE_NAME", "")
FABRIC_KQL_DB_ID = os.getenv("FABRIC_KQL_DB_ID", "")
FABRIC_KQL_DB_NAME = os.getenv("FABRIC_KQL_DB_NAME", "")
EVENTHOUSE_QUERY_URI = os.getenv("EVENTHOUSE_QUERY_URI", "")

# ---------------------------------------------------------------------------
# Service readiness — are required vars configured?
# ---------------------------------------------------------------------------

REQUIRED_VARS = ("FABRIC_WORKSPACE_ID", "FABRIC_GRAPH_MODEL_ID")
CONFIGURED = all(os.getenv(v) for v in REQUIRED_VARS)

# ---------------------------------------------------------------------------
# Shared credential (lazy-initialised)
# ---------------------------------------------------------------------------

_credential = None


def get_credential() -> DefaultAzureCredential:
    global _credential
    if _credential is None:
        _credential = DefaultAzureCredential()
    return _credential
```

#### `fabric-graph-api/models.py`

```python
"""
Request/response models for fabric-graph-api.

Completely independent of cosmosdb-graph-api models.
The response shapes (columns/data, nodes/edges) are intentionally
compatible so the frontend can consume both interchangeably.
"""

from __future__ import annotations

from pydantic import BaseModel


class GraphQueryRequest(BaseModel):
    """Request body for POST /fabric/graph."""
    query: str
    workspace_id: str = ""     # Override env var per-request
    graph_model_id: str = ""   # Override env var per-request


class GraphQueryResponse(BaseModel):
    """Response body for POST /fabric/graph."""
    columns: list[dict] = []
    data: list[dict] = []
    error: str | None = None


class TopologyRequest(BaseModel):
    """Request body for POST /fabric/topology."""
    workspace_id: str = ""
    graph_model_id: str = ""
    ontology_id: str = ""       # Used to discover entity types
    vertex_labels: list[str] | None = None  # Filter to specific labels
    query: str | None = None    # Custom GQL query (overrides default)


class TopologyResponse(BaseModel):
    """Response body for POST /fabric/topology."""
    nodes: list[dict] = []
    edges: list[dict] = []
    meta: dict = {}


class FabricItem(BaseModel):
    """A Fabric workspace item (ontology, eventhouse, graph model)."""
    id: str
    display_name: str
    type: str
    description: str | None = None


class FabricListResponse(BaseModel):
    """Response for discovery list endpoints."""
    items: list[FabricItem]
    workspace_id: str
```

#### `fabric-graph-api/main.py`

```python
"""
Fabric Graph API — Micro-service for GQL queries against Microsoft Fabric.

Exposes:
  POST /fabric/graph       — Execute a GQL query against Fabric GraphModel
  POST /fabric/topology    — Get graph topology for visualization
  GET  /fabric/ontologies  — List ontologies in a workspace
  GET  /fabric/eventhouses — List eventhouses in a workspace
  GET  /fabric/graph-models — List graph models in a workspace
  GET  /fabric/health      — Service health check

This service is completely independent of cosmosdb-graph-api.
If Fabric env vars are not configured, the service starts but reports
unhealthy via /fabric/health and returns 503 on all query endpoints.

Run locally:
  cd fabric-graph-api && source ../azure_config.env && uv run uvicorn main:app --reload --port 8200
"""

from __future__ import annotations

import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import CONFIGURED, REQUIRED_VARS

logger = logging.getLogger("fabric-graph-api")
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Log config status at startup; clean up on shutdown."""
    if not CONFIGURED:
        missing = [v for v in REQUIRED_VARS if not os.getenv(v)]
        logger.warning(
            "Fabric env vars not configured — service will report unhealthy. "
            "Missing: %s", ", ".join(missing),
        )
    else:
        logger.info("Fabric backend configured. workspace=%s, graph_model=%s",
                     os.getenv("FABRIC_WORKSPACE_ID", "")[:8] + "...",
                     os.getenv("FABRIC_GRAPH_MODEL_ID", "")[:8] + "...")
    yield
    # Cleanup: close fabric backend if it was initialised
    try:
        from fabric_backend import _global_backend
        if _global_backend:
            _global_backend.close()
    except Exception:
        pass


app = FastAPI(
    title="Fabric Graph API",
    version="0.1.0",
    description="GQL queries against Microsoft Fabric GraphModel (beta).",
    lifespan=_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health check ──────────────────────────────────────────────────

@app.get("/fabric/health")
async def health():
    """Service health check.

    Returns 200 + {"status": "healthy"} if Fabric env vars are configured.
    Returns 503 + {"status": "not_configured", "missing": [...]} if not.

    The frontend uses this to decide whether to show the Fabric option.
    """
    if CONFIGURED:
        return {"status": "healthy", "backend": "fabric"}
    missing = [v for v in REQUIRED_VARS if not os.getenv(v)]
    return JSONResponse(
        status_code=503,
        content={"status": "not_configured", "missing": missing, "backend": "fabric"},
    )


# ── Guard middleware for unconfigured state ────────────────────────

@app.middleware("http")
async def guard_unconfigured(request: Request, call_next):
    """Return 503 for all non-health endpoints when Fabric is not configured."""
    if not CONFIGURED and request.url.path != "/fabric/health":
        return JSONResponse(
            status_code=503,
            content={"error": "Fabric backend not configured. Set FABRIC_WORKSPACE_ID and FABRIC_GRAPH_MODEL_ID."},
        )
    return await call_next(request)


# ── Register routers (imported after app creation) ─────────────────

from router_graph import router as graph_router       # POST /fabric/graph
from router_topology import router as topology_router # POST /fabric/topology
from router_discovery import router as discovery_router  # GET /fabric/ontologies, eventhouses, graph-models

app.include_router(graph_router)
app.include_router(topology_router)
app.include_router(discovery_router)
```

> **Key design:** The `guard_unconfigured` middleware intercepts ALL requests (except health) when Fabric vars are missing, returning a clear 503. This means the service always starts (supervisord happy) but self-reports its readiness. The frontend probes `/fabric/health` and hides the Fabric option when it gets 503.

---

## Item 2: Fabric Graph Backend

### Current State

No Fabric query execution exists. The only working GQL execution code is in `fabric_implementation_references/scripts/testing_scripts/test_gql_query.py`.

### Target State

`fabric-graph-api/fabric_backend.py` — GQL query execution via Fabric REST API.
`fabric-graph-api/router_graph.py` — `POST /fabric/graph` endpoint.
`fabric-graph-api/router_topology.py` — `POST /fabric/topology` endpoint.

### New Files

#### `fabric-graph-api/fabric_backend.py` (~200 lines)

```python
"""
Fabric Graph Backend — executes GQL queries against Microsoft Fabric
GraphModel Execute Query (beta) API.

API: POST /v1/workspaces/{workspace_id}/GraphModels/{graph_model_id}/executeQuery?beta=True
Auth: DefaultAzureCredential with scope "https://api.fabric.microsoft.com/.default"
Response: {"status": {"code": ..., "description": ...}, "result": {"columns": [...], "data": [...]}}
Rate limiting: 429 with Retry-After — retry with exponential backoff (5 retries, 15s × attempt)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import httpx

from config import (
    FABRIC_API, FABRIC_SCOPE, FABRIC_WORKSPACE_ID, FABRIC_GRAPH_MODEL_ID,
    get_credential,
)

logger = logging.getLogger("fabric-graph-api.backend")

# Module-level singleton (lazy init)
_global_backend: FabricGraphBackend | None = None


def get_backend(
    workspace_id: str | None = None,
    graph_model_id: str | None = None,
) -> "FabricGraphBackend":
    """Get or create the singleton FabricGraphBackend."""
    global _global_backend
    if _global_backend is None:
        _global_backend = FabricGraphBackend(
            workspace_id=workspace_id,
            graph_model_id=graph_model_id,
        )
    return _global_backend


class FabricGraphBackend:
    """Executes GQL queries against Microsoft Fabric GraphModel."""

    def __init__(
        self,
        workspace_id: str | None = None,
        graph_model_id: str | None = None,
    ):
        self.workspace_id = workspace_id or FABRIC_WORKSPACE_ID
        self.graph_model_id = graph_model_id or FABRIC_GRAPH_MODEL_ID
        self._client: httpx.AsyncClient | None = None

    def _get_token(self) -> str:
        cred = get_credential()
        return cred.get_token(FABRIC_SCOPE).token

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=60.0)
        return self._client

    async def execute_query(
        self,
        query: str,
        workspace_id: str | None = None,
        graph_model_id: str | None = None,
    ) -> dict:
        """Execute a GQL query.

        GQL uses MATCH/RETURN syntax (ISO GQL, not GraphQL). Example:
          MATCH (r:CoreRouter) RETURN r.RouterId, r.City LIMIT 10

        Returns: {"columns": [...], "data": [...]} or {"columns": [], "data": [], "error": "..."}
        """
        ws_id = workspace_id or self.workspace_id
        model_id = graph_model_id or self.graph_model_id

        client = await self._get_client()
        url = f"{FABRIC_API}/workspaces/{ws_id}/GraphModels/{model_id}/executeQuery"
        token = self._get_token()

        for attempt in range(1, 6):
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                params={"beta": "True"},
                json={"query": query},
            )

            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", "0"))
                if not retry_after:
                    try:
                        msg = resp.json().get("message", "")
                        if "until:" in msg:
                            ts_str = msg.split("until:")[1].strip().rstrip(")")
                            ts_str = ts_str.replace("(UTC", "").strip()
                            blocked_until = datetime.strptime(ts_str, "%m/%d/%Y %I:%M:%S %p")
                            blocked_until = blocked_until.replace(tzinfo=timezone.utc)
                            wait = (blocked_until - datetime.now(timezone.utc)).total_seconds()
                            retry_after = max(int(wait) + 1, 3)
                    except Exception:
                        pass
                retry_after = max(retry_after, 15 * attempt)
                if attempt < 5:
                    logger.warning("Rate-limited (429). Waiting %ds (attempt %d/5)", retry_after, attempt)
                    await asyncio.sleep(retry_after)
                    token = self._get_token()
                    continue
                return {"columns": [], "data": [], "error": "Rate limit exceeded after 5 retries"}

            break

        if resp.status_code != 200:
            return {"columns": [], "data": [], "error": f"Fabric API error (HTTP {resp.status_code}): {resp.text[:500]}"}

        raw = resp.json()
        status = raw.get("status", {})
        if status.get("code", "").lower() not in ("", "ok", "success"):
            return {"columns": [], "data": [], "error": status.get("description", str(status))}

        result = raw.get("result", {})
        return {
            "columns": result.get("columns", []),
            "data": result.get("data", []),
        }

    async def get_topology(
        self,
        workspace_id: str | None = None,
        graph_model_id: str | None = None,
        ontology_id: str | None = None,
        query: str | None = None,
        vertex_labels: list[str] | None = None,
    ) -> dict:
        """Query Fabric ontology for topology visualization.

        Returns {"nodes": [...], "edges": [...], "meta": {...}}.

        If custom query is provided, executes it directly.
        Otherwise discovers entity types via ontology REST API and queries each.
        """
        ws_id = workspace_id or self.workspace_id

        if query:
            result = await self.execute_query(query, workspace_id=ws_id, graph_model_id=graph_model_id)
            return {"nodes": result.get("data", []), "edges": [], "meta": {"custom_query": True}}

        # Default: discover types from ontology, query each.
        # See ⚠️ implementation note below.
        ...

    def close(self) -> None:
        if self._client and not self._client.is_closed:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._client.aclose())
            except RuntimeError:
                asyncio.run(self._client.aclose())
            self._client = None
```

> **⚠️ Implementation note:** `get_topology()` default query must:
> 1. Call `GET /v1/workspaces/{id}/ontologies/{ontology_id}` to discover entity types
> 2. Build per-type GQL queries: `MATCH (r:CoreRouter) RETURN r.RouterId AS id, r.City AS city`
> 3. Build relationship queries: `MATCH (a)-[rel]->(b) RETURN a, type(rel) AS relType, b`
> 4. Map to `{nodes: [{id, label, properties}], edges: [{id, source, target, label}]}`
>
> Start with hard-coded mapping for the Network Topology ontology, then generalize.

#### `fabric-graph-api/router_graph.py`

```python
"""
Router: POST /fabric/graph — Execute GQL query against Fabric.
"""

from __future__ import annotations

import logging
from fastapi import APIRouter

from fabric_backend import get_backend
from models import GraphQueryRequest, GraphQueryResponse

logger = logging.getLogger("fabric-graph-api")

router = APIRouter()


@router.post(
    "/fabric/graph",
    response_model=GraphQueryResponse,
    summary="Execute a GQL query against Fabric GraphModel",
    description=(
        "Dispatches a GQL MATCH/RETURN query to the Fabric GraphModel "
        "Execute Query (beta) API. Returns columns + data. "
        "workspace_id and graph_model_id can be passed in the body to "
        "override the env var defaults."
    ),
)
async def query_graph(req: GraphQueryRequest):
    backend = get_backend()
    logger.info("POST /fabric/graph  query=%.200s", req.query)
    try:
        result = await backend.execute_query(
            req.query,
            workspace_id=req.workspace_id or None,
            graph_model_id=req.graph_model_id or None,
        )
    except Exception as e:
        logger.exception("Fabric graph query error (returning 200 with error body)")
        return GraphQueryResponse(
            error=f"Fabric query error: {type(e).__name__}: {e}. Read the error, fix the query, and retry.",
        )
    return GraphQueryResponse(
        columns=result.get("columns", []),
        data=result.get("data", []),
        error=result.get("error"),
    )
```

> **Error-as-200 pattern:** Same as cosmosdb-graph-api — never return HTTP 4xx/5xx. LLM agents need to read error text to self-correct queries.

#### `fabric-graph-api/router_topology.py`

```python
"""
Router: POST /fabric/topology — Get graph topology for visualization.
"""

from __future__ import annotations

import logging
from fastapi import APIRouter

from fabric_backend import get_backend
from models import TopologyRequest, TopologyResponse

logger = logging.getLogger("fabric-graph-api")

router = APIRouter()


@router.post(
    "/fabric/topology",
    response_model=TopologyResponse,
    summary="Get Fabric graph topology for visualization",
)
async def get_topology(req: TopologyRequest):
    backend = get_backend()
    logger.info("POST /fabric/topology  workspace=%s", req.workspace_id[:8] + "..." if req.workspace_id else "env")
    try:
        result = await backend.get_topology(
            workspace_id=req.workspace_id or None,
            graph_model_id=req.graph_model_id or None,
            ontology_id=req.ontology_id or None,
            query=req.query,
            vertex_labels=req.vertex_labels,
        )
    except Exception as e:
        logger.exception("Fabric topology error")
        return TopologyResponse(meta={"error": str(e)})
    return TopologyResponse(
        nodes=result.get("nodes", []),
        edges=result.get("edges", []),
        meta=result.get("meta", {}),
    )
```

### Verification

- Unit test: Mock Fabric REST API, call `execute_query("MATCH (r:CoreRouter) RETURN r.RouterId")`, verify `{columns, data}` response
- Integration test (with real Fabric workspace): `POST /fabric/graph` with GQL → returns data
- `POST /fabric/topology` → returns `{nodes, edges, meta}`
- Health check: `GET /fabric/health` → 200 when configured, 503 when not
- Rate limit retry: Mock 429 → verify retry + backoff behaviour

---

## Item 3: Fabric Discovery Endpoints

### Current State

No endpoints exist for browsing Fabric workspace contents.

### Target State

`fabric-graph-api/router_discovery.py` with:
- `GET /fabric/ontologies?workspace_id=...` — list ontologies
- `GET /fabric/eventhouses?workspace_id=...` — list eventhouses
- `GET /fabric/graph-models?workspace_id=...` — list graph models

These live in `fabric-graph-api` because they require Fabric authentication and are only relevant when Fabric is the selected backend.

### New Files

#### `fabric-graph-api/router_discovery.py` (~130 lines)

```python
"""
Router: /fabric/* — Fabric workspace discovery endpoints.

Provides listing of ontologies, eventhouses, and graph models
for frontend dropdown population.
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException, Query

import httpx

from config import FABRIC_API, FABRIC_SCOPE, FABRIC_WORKSPACE_ID, get_credential
from models import FabricItem, FabricListResponse

logger = logging.getLogger("fabric-graph-api.discovery")

router = APIRouter(tags=["fabric-discovery"])


async def _fabric_list_items(workspace_id: str, item_type: str) -> list[dict]:
    """Call Fabric REST API to list items of a given type.

    Uses dedicated sub-resource endpoints where available:
      - "Ontology"    → GET /workspaces/{id}/ontologies
      - "Eventhouse"  → GET /workspaces/{id}/eventhouses
      - "GraphModel"  → GET /workspaces/{id}/GraphModels
      - "Lakehouse"   → GET /workspaces/{id}/lakehouses
    Falls back to GET /workspaces/{id}/items for other types.
    """
    cred = get_credential()
    token = cred.get_token(FABRIC_SCOPE)

    sub_resource_map = {
        "Ontology": "ontologies",
        "Eventhouse": "eventhouses",
        "GraphModel": "GraphModels",
        "Lakehouse": "lakehouses",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        sub_resource = sub_resource_map.get(item_type)
        if sub_resource:
            url = f"{FABRIC_API}/workspaces/{workspace_id}/{sub_resource}"
            resp = await client.get(url, headers={"Authorization": f"Bearer {token.token}"})
        else:
            url = f"{FABRIC_API}/workspaces/{workspace_id}/items"
            resp = await client.get(
                url,
                params={"type": item_type} if item_type else {},
                headers={"Authorization": f"Bearer {token.token}"},
            )
        if resp.status_code == 404:
            raise HTTPException(404, f"Workspace {workspace_id} not found")
        if resp.status_code == 403:
            raise HTTPException(403, "Access denied — check Fabric workspace permissions")
        resp.raise_for_status()
        data = resp.json()
        # Log pagination warning
        if data.get("continuationUri") or data.get("continuationToken"):
            logger.warning("Fabric API response is paginated — only first page returned. "
                          "Consider adding pagination loop for large workspaces.")
        return data.get("value", [])


@router.get("/fabric/ontologies", response_model=FabricListResponse)
async def list_ontologies(workspace_id: str = Query(default=None)):
    ws_id = workspace_id or FABRIC_WORKSPACE_ID
    if not ws_id:
        raise HTTPException(400, "workspace_id required (param or FABRIC_WORKSPACE_ID env var)")
    items = await _fabric_list_items(ws_id, "Ontology")
    return FabricListResponse(
        workspace_id=ws_id,
        items=[
            FabricItem(id=item["id"], display_name=item.get("displayName", item["id"]),
                      type="ontology", description=item.get("description"))
            for item in items
        ],
    )


@router.get("/fabric/eventhouses", response_model=FabricListResponse)
async def list_eventhouses(workspace_id: str = Query(default=None)):
    ws_id = workspace_id or FABRIC_WORKSPACE_ID
    if not ws_id:
        raise HTTPException(400, "workspace_id required (param or FABRIC_WORKSPACE_ID env var)")
    items = await _fabric_list_items(ws_id, "Eventhouse")
    return FabricListResponse(
        workspace_id=ws_id,
        items=[
            FabricItem(id=item["id"], display_name=item.get("displayName", item["id"]),
                      type="eventhouse", description=item.get("description"))
            for item in items
        ],
    )


@router.get("/fabric/graph-models", response_model=FabricListResponse)
async def list_graph_models(workspace_id: str = Query(default=None)):
    ws_id = workspace_id or FABRIC_WORKSPACE_ID
    if not ws_id:
        raise HTTPException(400, "workspace_id required")
    items = await _fabric_list_items(ws_id, "GraphModel")
    return FabricListResponse(
        workspace_id=ws_id,
        items=[
            FabricItem(id=item["id"], display_name=item.get("displayName", item["id"]),
                      type="graph-model")
            for item in items
        ],
    )
```

### Verification

- `GET /fabric/ontologies?workspace_id=<valid>` → returns list
- `GET /fabric/eventhouses?workspace_id=<valid>` → returns list
- `GET /fabric/ontologies` (no workspace, no env var) → 400
- `GET /fabric/ontologies?workspace_id=<invalid>` → 404
- Service unconfigured → 503 (middleware guard, before router runs)

---

## Item 3.5: Fabric Provisioning API

### Current State

Reference provisioning scripts exist at `fabric_implementation_references/scripts/fabric/`. They are standalone CLI tools. No UI-driven provisioning exists.

### Target State

Provisioning endpoints stay in the **API service** (`api/app/routers/fabric_provision.py` at `/api/fabric/*`). This is unchanged from the original plan — provisioning is an orchestration concern, not a graph query concern.

### Backend Changes

#### `api/app/routers/fabric_provision.py` — **NEW** (~300 lines)

Same as original plan. Wraps reference provisioning scripts as SSE-streamed endpoints:

- `POST /api/fabric/provision` — Full provisioning pipeline (SSE)
- `POST /api/fabric/upload-lakehouse` — Upload CSVs to Lakehouse delta tables (SSE)
- `POST /api/fabric/upload-eventhouse` — Upload CSVs to Eventhouse KQL tables (SSE)

```python
"""
Router: /api/fabric/* — Fabric resource provisioning and data upload.

Lives in the API service (port 8000), NOT in fabric-graph-api.
This is consistent with the API service's role as orchestration layer.

The provisioning endpoints call Fabric REST API directly (not via fabric-graph-api)
because provisioning uses different auth scopes, different endpoints
(ARM for capacity, OneLake for uploads), and doesn't need graph query capabilities.
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger("api.fabric_provision")

router = APIRouter(prefix="/api/fabric", tags=["fabric-provision"])


class ProvisionRequest(BaseModel):
    capacity_id: str
    workspace_name: str = "AutonomousNetworkDemo"
    scenario_name: str = "cloud-outage"


@router.post("/provision")
async def provision_fabric_resources(request: ProvisionRequest):
    """Full Fabric provisioning pipeline with SSE progress streaming.

    Steps:
    1. Create/find workspace (attach to capacity)
    2. Create Lakehouse
    3. Upload scenario CSVs to OneLake (from data/lakehouse/)
    4. Load CSVs as managed delta tables
    5. Create Eventhouse
    6. Create KQL tables (AlertStream, LinkTelemetry)
    7. Ingest scenario CSVs from data/eventhouse/
    8. Create Ontology with entity types + data bindings
    9. Assign Fabric role to Container App managed identity
    10. Update azure_config.env with discovered IDs
    """
    async def generate():
        ...

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/upload-lakehouse")
async def upload_lakehouse_csvs(
    files: list[UploadFile] = File(...),
    scenario_name: str = Form(default=""),
    workspace_id: str = Form(default=""),
    lakehouse_id: str = Form(default=""),
):
    """Upload CSV files to Lakehouse → OneLake → delta tables."""
    async def generate():
        ...
    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/upload-eventhouse")
async def upload_eventhouse_csvs(
    files: list[UploadFile] = File(...),
    scenario_name: str = Form(default=""),
    workspace_id: str = Form(default=""),
    eventhouse_id: str = Form(default=""),
):
    """Upload CSV files to Eventhouse KQL tables."""
    async def generate():
        ...
    return StreamingResponse(generate(), media_type="text/event-stream")
```

> **⚠️ Dependencies:** The provisioning endpoints require additional packages in `api/pyproject.toml`:
> - `azure-storage-file-datalake` (OneLake upload)
> - `azure-kusto-data` + `azure-kusto-ingest` (Eventhouse KQL ingest)
> - `requests` (if not already present)

> **⚠️ Shared provisioning module:** Extract core logic from reference scripts into `scripts/fabric/_provisioner.py`. Both the API router and standalone scripts import from it.

> **⚠️ OneLake URL:** CSVs go to `https://onelake.dfs.fabric.microsoft.com` (ADLS Gen2), NOT the Fabric REST API.

> **⚠️ Role assignment:** Include `assign_fabric_role.py` as Step 9 (Gap 10 from original). Requires `GRAPH_QUERY_API_PRINCIPAL_ID` env var.

#### `api/app/main.py` — Register provisioning router

```python
from app.routers.fabric_provision import router as fabric_provision_router
app.include_router(fabric_provision_router)
```

---

## Item 4: Agent Provisioner Changes

> **V10 Dependency: Phase 8 (Config-Driven Agent Provisioner) and Phase 9 (OpenAPI Spec Templating) must be complete before this item.**
>
> V10 Phase 8 replaces the hardcoded `provision_all()` / `OPENAPI_SPEC_MAP` approach
> with `provision_from_config()`, which reads agent definitions from scenario YAML.
> V10 Phase 9 introduces OpenAPI spec templating with `.replace()` per-placeholder and
> a `CONNECTOR_OPENAPI_VARS` dict keyed by connector string.
>
> **V11's job here is NOT to add `"fabric"` to a hardcoded map — that map no longer
> exists post-V10. Instead, V11:**
> 1. Adds `"fabric-gql"` as a recognized connector in `_resolve_connector_for_agent()`
> 2. Adds `"fabric-gql"` to `CONNECTOR_OPENAPI_VARS` with GQL-specific descriptions
> 3. Creates the `fabric-graph-api/openapi/fabric.yaml` spec (unchanged from original plan)
> 4. Adds a `"fabric-gql"` entry to the connector→spec-template resolution logic
> 5. Ensures Fabric scenario YAML uses `connector: "fabric-gql"` under `data_sources.graph`

### Current State (post-V10)

- `scripts/agent_provisioner.py` uses `provision_from_config()` to read agents from scenario YAML
- `_resolve_connector_for_agent()` maps agent tool definitions to data source connectors
- `_build_tools()` resolves OpenAPI spec templates via connector string
- `CONNECTOR_OPENAPI_VARS` provides per-connector template variables for `.replace()` expansion
- Two connectors are defined: `"cosmosdb-gremlin"` and `"cosmosdb-nosql"` (plus `"mock"`)
- OpenAPI spec templates live in `cosmosdb-graph-api/openapi/`
- `_load_openapi_spec()` uses `.replace()` to expand `{base_url}`, `{graph_name}`, `{query_language_description}`

### Target State

- New `fabric-graph-api/openapi/fabric.yaml` documenting `/fabric/graph` with GQL syntax
- `"fabric-gql"` added to `CONNECTOR_OPENAPI_VARS` with GQL-specific descriptions
- `_resolve_connector_for_agent()` recognizes `"fabric-gql"` connector
- `_load_openapi_spec()` knows to look in `fabric-graph-api/openapi/` when connector starts with `"fabric"`
- Fabric scenario YAML declares `connector: "fabric-gql"` and the provisioner auto-selects the correct spec and prompt fragments
- Agent GraphExplorer, when provisioned for a Fabric scenario, uses GQL prompt fragments and the `/fabric/graph` endpoint

### Changes

#### `fabric-graph-api/openapi/fabric.yaml` — **NEW** (~160 lines)

This file is unchanged from the original plan — it's the OpenAPI spec for the Fabric graph endpoint:

```yaml
openapi: "3.0.3"
info:
  title: Graph Query API (Fabric Backend)
  version: "0.1.0"
  description: |
    Micro-API for executing GQL queries against Microsoft Fabric Graph Model.
    Used by Foundry agents via OpenApiTool.
    GQL uses MATCH/RETURN syntax (ISO GQL), not GraphQL.
servers:
  - url: "{base_url}"
    description: Deployed Container App

paths:
  /fabric/graph:
    post:
      operationId: query_graph
      summary: Execute a GQL query against Fabric GraphModel
      description: |
        Submits a GQL (Graph Query Language) query to Microsoft Fabric.
        Returns columns and data rows from the network ontology.
        Use GQL MATCH/RETURN syntax (not Gremlin, not GraphQL). Examples:
          MATCH (r:CoreRouter) RETURN r.RouterId, r.City, r.Region LIMIT 10
          MATCH (l:TransportLink)-[:connects_to]->(r:CoreRouter) RETURN r.RouterId, l.LinkId LIMIT 10
          MATCH (n) RETURN LABELS(n) AS type, count(n) AS cnt GROUP BY type ORDER BY cnt DESC
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [query]
              properties:
                query:
                  type: string
                  description: GQL MATCH/RETURN query string
                workspace_id:
                  type: string
                  description: Fabric workspace ID (defaults to env var)
                graph_model_id:
                  type: string
                  description: Fabric graph model ID (defaults to env var)
      responses:
        "200":
          description: Query results
          content:
            application/json:
              schema:
                type: object
                properties:
                  columns:
                    type: array
                    items:
                      type: object
                      properties:
                        name: { type: string }
                        type: { type: string }
                  data:
                    type: array
                    items: { type: object }
                  error:
                    type: string
                    nullable: true
```

> **Note:** The path is `/fabric/graph` (not `/query/graph`). The `{base_url}` substitution provides the hostname. The agent's `OpenApiTool` will call `{base_url}/fabric/graph`.

#### `scripts/agent_provisioner.py` — Add Fabric connector support

**Post-V10, the changes are targeted additions to existing V10 structures, not a rewrite:**

```python
# 1. Add Fabric OpenAPI directory alongside the Cosmos one:
COSMOSDB_OPENAPI_DIR = Path(__file__).resolve().parent.parent / "cosmosdb-graph-api" / "openapi"
FABRIC_OPENAPI_DIR = Path(__file__).resolve().parent.parent / "fabric-graph-api" / "openapi"

# 2. Add "fabric-gql" to CONNECTOR_OPENAPI_VARS (V10 Phase 9 structure):
CONNECTOR_OPENAPI_VARS = {
    "cosmosdb-gremlin": {
        "query_language_description": "A Gremlin traversal query string. Use g.V()...",
    },
    "cosmosdb-nosql": {
        "query_language_description": "A KQL query against the telemetry container...",
    },
    "mock": {
        "query_language_description": "Query the topology graph (offline mock mode).",
    },
    # NEW — V11:
    "fabric-gql": {
        "query_language_description": (
            "A GQL (Graph Query Language) MATCH/RETURN query against the Fabric "
            "GraphModel. Use ISO GQL syntax (not Gremlin, not GraphQL). Examples:\n"
            "  MATCH (r:CoreRouter) RETURN r.RouterId, r.City LIMIT 10\n"
            "  MATCH (a)-[e]->(b) RETURN a, e, b LIMIT 20"
        ),
    },
}

# 3. Update _load_openapi_spec() to resolve spec files from the correct directory:
def _load_openapi_spec(api_uri, spec_template, *, graph_name, keep_path=None):
    """Load and expand an OpenAPI spec template.
    
    Post-V10: uses connector string to find the right spec file.
    V11 addition: specs starting with "fabric" resolve from FABRIC_OPENAPI_DIR.
    """
    if spec_template.startswith("fabric"):
        spec_path = FABRIC_OPENAPI_DIR / f"{spec_template}.yaml"
    else:
        spec_path = COSMOSDB_OPENAPI_DIR / f"{spec_template}.yaml"
    
    raw = spec_path.read_text()
    raw = raw.replace("{base_url}", api_uri.rstrip("/"))
    raw = raw.replace("{graph_name}", graph_name)
    
    # V10 Phase 9: expand connector-specific vars
    connector_vars = CONNECTOR_OPENAPI_VARS.get(spec_template, {})
    for key, value in connector_vars.items():
        raw = raw.replace(f"{{{key}}}", value)
    
    if keep_path:
        # Filter to only the specified path (existing V10 behavior)
        ...
    
    return raw
```

> **Key difference from pre-V10 plan:** The original V11 plan added `"fabric"` to a
> hardcoded `OPENAPI_SPEC_MAP` dict. Post-V10, there is no `OPENAPI_SPEC_MAP`.
> Instead, `_load_openapi_spec()` resolves specs by connector name, and
> `CONNECTOR_OPENAPI_VARS` provides the per-connector template variables.
> V11 just adds the `"fabric-gql"` entries to these structures.

#### `_resolve_connector_for_agent()` — Recognize Fabric connector

The V10 function already handles arbitrary connector strings via scenario YAML lookup. No code change needed — when a Fabric scenario YAML declares `connector: "fabric-gql"`, the function returns `"fabric-gql"` automatically:

```python
# V10's _resolve_connector_for_agent() already works for Fabric:
# It reads config["data_sources"]["graph"]["connector"] → "fabric-gql"
# No code change needed — the function is data-driven.
```

#### Fabric scenario YAML — `data_sources` section

A Fabric scenario declares its connector in the V10 v2.0 YAML schema:

```yaml
# data/scenarios/fabric-telecom/scenario.yaml
name: "fabric-telecom"
display_name: "Telecom Network (Fabric)"
description: "Network topology exploration via Microsoft Fabric GraphModel"

data_sources:
  graph:
    connector: "fabric-gql"          # ← V11 addition: new connector type
    # No database/container fields — Fabric uses workspace/graph model IDs
    # which are passed at runtime via env vars or request body
  # Note: no telemetry data source — Fabric telemetry is out of scope
  search_indexes:
    - name: "runbooks"
      index_name: "telco-noc-runbooks-index"
    - name: "tickets"
      index_name: "telco-noc-tickets-index"

agents:
  - name: "GraphExplorerAgent"
    display_name: "Network Graph Explorer"
    role: "graph_explorer"
    model: "gpt-4.1"
    instructions_file: "prompts/graph_explorer/"
    compose_with_connector: true      # ← V10: auto-selects language_gql.md
    tools:
      - type: "openapi"
        spec_template: "fabric"       # ← resolves to fabric-graph-api/openapi/fabric.yaml
        keep_path: "/fabric/graph"    # ← different prefix from Cosmos

  # RunbookKB and HistoricalTicket agents are identical to Cosmos scenarios
  # (they use AI Search, not graph queries)
  - name: "RunbookKBAgent"
    display_name: "Runbook Knowledge Base"
    role: "runbook"
    model: "gpt-4.1"
    instructions_file: "prompts/foundry_runbook_kb_agent.md"
    tools:
      - type: "azure_ai_search"
        index_key: "runbooks"

  - name: "HistoricalTicketAgent"
    display_name: "Historical Ticket Search"
    role: "ticket"
    model: "gpt-4.1"
    instructions_file: "prompts/foundry_historical_ticket_agent.md"
    tools:
      - type: "azure_ai_search"
        index_key: "tickets"

  # Note: No TelemetryAgent — Fabric telemetry is deferred (Decision 3)
  - name: "Orchestrator"
    display_name: "Investigation Orchestrator"
    role: "orchestrator"
    model: "gpt-4.1"
    instructions_file: "prompts/foundry_orchestrator_agent.md"
    is_orchestrator: true
    connected_agents: ["GraphExplorerAgent", "RunbookKBAgent", "HistoricalTicketAgent"]
```

> **Key points:**
> - `compose_with_connector: true` causes `_load_prompt()` to auto-select `language_gql.md` from the prompt fragments directory (V10 Phase 10). This fragment must be created with GQL syntax guidance.
> - `spec_template: "fabric"` maps to `fabric-graph-api/openapi/fabric.yaml`
> - `keep_path: "/fabric/graph"` ensures the spec only exposes the Fabric endpoint
> - No `TelemetryAgent` — the Orchestrator connects to 3 agents instead of 4
> - Search agents are unchanged — they don't depend on the graph backend

#### `prompts/graph_explorer/language_gql.md` — **NEW** prompt fragment

V10's `compose_with_connector` mechanism (Phase 10) selects language fragments based on the connector string. For `"fabric-gql"`, the suffix is `"gql"`, so the file is `language_gql.md`:

```markdown
## Query Language: GQL (Graph Query Language)

You write queries in **ISO GQL** (MATCH/RETURN syntax). This is NOT Gremlin and NOT GraphQL.

### Syntax Reference

```
MATCH (n:Label) RETURN n.property LIMIT 10
MATCH (a:Label)-[e:EdgeType]->(b:Label) RETURN a, e, b
MATCH (n) RETURN LABELS(n) AS type, count(n) AS cnt GROUP BY type ORDER BY cnt DESC
```

### Key Differences from Gremlin
- No `g.V()` — use `MATCH (n)`
- No `.has()` — use `WHERE n.property = value`
- No `.out()` — use `MATCH (a)-[e]->(b)`
- Results are tabular (columns + rows), not traversal streams
```

#### `api/app/routers/config.py` — Support Fabric in config apply (post-V10)

Post-V10, `config.py` uses `provision_from_config()` which reads the scenario YAML. The Fabric-specific fields in `ConfigApplyRequest` provide **runtime overrides** for Fabric workspace/graph model IDs:

```python
class ConfigApplyRequest(BaseModel):
    graph: str = "topology"
    runbooks_index: str = "runbooks-index"
    tickets_index: str = "tickets-index"
    prompt_scenario: str | None = None
    prompts: dict[str, str] | None = None
    # NEW (V11): Fabric-specific runtime overrides
    backend_type: str | None = None  # "cosmosdb" | "fabric" | None (use env default)
    fabric_workspace_id: str | None = None
    fabric_ontology_id: str | None = None
    fabric_graph_model_id: str | None = None
```

When `backend_type: "fabric"`:
- `provision_from_config()` reads the scenario YAML (which declares `connector: "fabric-gql"`)
- `_resolve_connector_for_agent()` returns `"fabric-gql"` for graph agents
- `_load_openapi_spec()` loads from `fabric-graph-api/openapi/`
- `_load_prompt()` selects `language_gql.md` fragment
- The GraphExplorer agent is provisioned with GQL instructions and the `/fabric/graph` tool

> **No hardcoded backend switching logic in config.py.** The backend type is declared
> in the scenario YAML's `data_sources.graph.connector` field. The `backend_type`
> parameter in `ConfigApplyRequest` is used by the frontend to pass to the agent
> provisioner, but the provisioner itself reads the connector from the YAML config.

### Verification

- Upload Fabric scenario YAML → `save_scenario_config()` stores it (V10 mechanism)
- `POST /api/config/apply { prompt_scenario: "fabric-telecom" }` → provisioner reads YAML, creates agents with Fabric spec and GQL prompts
- Agent GraphExplorer sends GQL to `/fabric/graph` → gets results
- Same provisioner flow works for Cosmos scenarios unchanged — `connector: "cosmosdb-gremlin"` → Gremlin spec and prompts

---

## Item 5: Frontend — Adaptive Backend UI with Resilience

> **V10 Dependency: Phase 11 (Frontend Genericization) should be complete before this item.**
>
> V10 Phase 11 transforms the frontend from a hardcoded telco-NOC UI into a config-aware
> scaffold. After V10:
> - `ScenarioContext` uses `SavedScenario.resources` (config-specified, not hardcoded)
> - `graphConstants.ts` maps are empty (no hardcoded labels/colors/icons)
> - Agent names come from `agent_ids.json` (config-driven, not hardcoded 5-agent list)
> - First-run empty state is supported (no scenario loaded = generic welcome)
> - `setActiveScenario()` callback reads config-specified resources
> - ARIA semantics are applied to interactive widgets
>
> **V11 builds on this genericized scaffold.** The backend type, health detection, and
> Fabric-specific state are **additive layers** on top of V10's config-aware context —
> not modifications to hardcoded telco-specific code.

### Current State (post-V10)

- Frontend is config-aware: `ScenarioContext` uses `SavedScenario.resources`, agent names from `agent_ids.json`
- `graphConstants.ts` is empty — labels, colors, icons come from config/data
- No concept of backend type (all graph calls go to `/query/*`)
- No health checks against individual backend services
- No Fabric-specific state or UI

### Target State

The frontend adds a backend type layer on top of V10's generic scaffold:
1. Probes both backend health endpoints on mount
2. Populates the backend dropdown with only available backends
3. Routes graph queries to `/query/*` or `/fabric/*` based on selection
4. Shows clear messages when a backend is unavailable
5. Cosmos-dependent features (prompts, scenarios, interactions) continue working regardless of graph backend selection

### Frontend Changes

#### `context/ScenarioContext.tsx` — Add backend type + Fabric state + health detection

V10's `ScenarioContext` already has config-driven fields (`SavedScenario.resources`,
dynamic agent names). V11 adds backend type fields as a new layer:

```tsx
interface ScenarioState {
  // ... V10 fields (resources, agents from config, etc.) ...

  /** Active backend type — V11 addition */
  activeBackendType: 'cosmosdb' | 'fabric';
  /** Which backends are available (health check passed) — V11 addition */
  availableBackends: ('cosmosdb' | 'fabric')[];
  /** Fabric workspace ID */
  fabricWorkspaceId: string;
  /** Fabric ontology ID */
  fabricOntologyId: string;
  /** Fabric graph model ID */
  fabricGraphModelId: string;
  /** Fabric eventhouse ID */
  fabricEventhouseId: string;
  /** Fabric capacity ID (for provisioning) */
  fabricCapacityId: string;
  /** Setters */
  setActiveBackendType: (type: 'cosmosdb' | 'fabric') => void;
  setFabricWorkspaceId: (id: string) => void;
  setFabricOntologyId: (id: string) => void;
  setFabricGraphModelId: (id: string) => void;
  setFabricEventhouseId: (id: string) => void;
  setFabricCapacityId: (id: string) => void;
}
```

> **V10 integration note:** V10's `setActiveScenario()` callback already reads
> `SavedScenario.resources` to populate context. V11 extends this: when a Fabric
> scenario is selected, `setActiveScenario()` also sets `activeBackendType: 'fabric'`
> based on the scenario config's `data_sources.graph.connector` field.

**Backend health detection on mount:**

```tsx
// In ScenarioProvider:
const [availableBackends, setAvailableBackends] = useState<('cosmosdb' | 'fabric')[]>([]);

useEffect(() => {
  async function detectBackends() {
    const available: ('cosmosdb' | 'fabric')[] = [];

    // Check cosmosdb-graph-api
    try {
      const res = await fetch('/query/health', { signal: AbortSignal.timeout(3000) });
      if (res.ok) available.push('cosmosdb');
    } catch { /* service unavailable */ }

    // Check fabric-graph-api
    try {
      const res = await fetch('/fabric/health', { signal: AbortSignal.timeout(3000) });
      if (res.ok) available.push('fabric');
    } catch { /* service unavailable */ }

    setAvailableBackends(available);

    // Auto-select: if saved backend is unavailable, switch to whatever is available
    const saved = localStorage.getItem('activeBackendType') as 'cosmosdb' | 'fabric';
    if (saved && available.includes(saved)) {
      setActiveBackendType(saved);
    } else if (available.length > 0) {
      setActiveBackendType(available[0]);
    }
  }
  detectBackends();
}, []);
```

> **Key resilience pattern:** The frontend never assumes either backend is available. It probes both on mount, shows only available options, and auto-selects a working backend. If the landscape changes (e.g., fabric-graph-api is deployed later), a page refresh picks up the new backend.

#### `hooks/useTopology.ts` — Backend-aware URL

```tsx
// Currently: always calls /query/topology
// New: route based on activeBackendType

const { activeBackendType, getQueryHeaders } = useScenarioContext();

const fetchTopology = useCallback(async () => {
  const url = activeBackendType === 'fabric' ? '/fabric/topology' : '/query/topology';
  const headers = activeBackendType === 'fabric'
    ? { 'Content-Type': 'application/json' }  // No X-Graph for Fabric
    : { 'Content-Type': 'application/json', ...getQueryHeaders() };

  const body = activeBackendType === 'fabric'
    ? JSON.stringify({
        workspace_id: fabricWorkspaceId,
        graph_model_id: fabricGraphModelId,
        ontology_id: fabricOntologyId,
      })
    : JSON.stringify({ vertex_labels: vertexLabels });

  const res = await fetch(url, { method: 'POST', headers, body });
  // ... rest of fetch logic (same for both backends — response shape is compatible)
}, [activeBackendType, ...]);
```

> **Compatible response shapes:** Both backends return `{nodes: [...], edges: [...], meta: {...}}` for topology. The frontend visualization code doesn't need to change — it consumes the same shape regardless of backend.

#### `hooks/useFabric.ts` — **NEW** (~120 lines)

```tsx
/**
 * Hook for Fabric workspace discovery AND provisioning.
 *
 * Calls fabric-graph-api (/fabric/*) for discovery,
 * and API service (/api/fabric/*) for provisioning.
 */
import { useState, useCallback } from 'react';

interface FabricItem {
  id: string;
  display_name: string;
  type: string;
  description?: string;
}

interface ProvisionStep {
  step: string;
  status: 'pending' | 'running' | 'done' | 'error';
  detail?: string;
}

export function useFabric() {
  const [ontologies, setOntologies] = useState<FabricItem[]>([]);
  const [eventhouses, setEventhouses] = useState<FabricItem[]>([]);
  const [graphModels, setGraphModels] = useState<FabricItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [provisionSteps, setProvisionSteps] = useState<ProvisionStep[]>([]);
  const [provisioning, setProvisioning] = useState(false);

  // Discovery calls → fabric-graph-api (/fabric/*)
  const fetchOntologies = useCallback(async (workspaceId: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/fabric/ontologies?workspace_id=${encodeURIComponent(workspaceId)}`);
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `HTTP ${res.status}`);
      const data = await res.json();
      setOntologies(data.items);
    } catch (e) { setError(String(e)); }
    finally { setLoading(false); }
  }, []);

  const fetchEventhouses = useCallback(async (workspaceId: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/fabric/eventhouses?workspace_id=${encodeURIComponent(workspaceId)}`);
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `HTTP ${res.status}`);
      setEventhouses((await res.json()).items);
    } catch (e) { setError(String(e)); }
    finally { setLoading(false); }
  }, []);

  const fetchGraphModels = useCallback(async (workspaceId: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/fabric/graph-models?workspace_id=${encodeURIComponent(workspaceId)}`);
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `HTTP ${res.status}`);
      setGraphModels((await res.json()).items);
    } catch (e) { setError(String(e)); }
    finally { setLoading(false); }
  }, []);

  // Provisioning calls → API service (/api/fabric/*)
  const provisionAll = useCallback(async (capacityId: string, workspaceName?: string) => {
    setProvisioning(true);
    setProvisionSteps([]);
    setError(null);
    try {
      const res = await fetch('/api/fabric/provision', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          capacity_id: capacityId,
          workspace_name: workspaceName || 'AutonomousNetworkDemo',
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      // Consume SSE stream...
    } catch (e) { setError(String(e)); }
    finally { setProvisioning(false); }
  }, []);

  return {
    ontologies, eventhouses, graphModels, loading, error,
    fetchOntologies, fetchEventhouses, fetchGraphModels,
    provisionSteps, provisioning, provisionAll,
  };
}
```

#### `SettingsModal.tsx` — Context-adaptive tab layout

```tsx
// Tab type adapts based on backend:
type CosmosTab = 'scenarios' | 'datasources' | 'upload';
type FabricTab = 'scenarios' | 'fabricsetup' | 'upload';
type Tab = CosmosTab | FabricTab;

const visibleTabs: { key: Tab; label: string }[] =
  activeBackendType === 'fabric'
    ? [
        { key: 'scenarios', label: 'Scenarios' },
        { key: 'fabricsetup', label: 'Fabric Setup' },
        { key: 'upload', label: 'Upload' },
      ]
    : [
        { key: 'scenarios', label: 'Scenarios' },
        { key: 'datasources', label: 'Data Sources' },
        { key: 'upload', label: 'Upload' },
      ];

// Backend dropdown — only shows available backends:
<div className="flex items-center gap-3 px-6 mt-2">
  <span className="text-xs text-text-muted">Backend:</span>
  <select
    value={activeBackendType}
    onChange={(e) => {
      const bt = e.target.value as 'cosmosdb' | 'fabric';
      setActiveBackendType(bt);
      setTab(bt === 'fabric' ? 'fabricsetup' : 'datasources');
    }}
    className="bg-neutral-bg1 border border-white/10 rounded px-2 py-1 text-sm text-text-primary"
    disabled={availableBackends.length <= 1}
  >
    {availableBackends.includes('cosmosdb') && <option value="cosmosdb">CosmosDB</option>}
    {availableBackends.includes('fabric') && <option value="fabric">Fabric</option>}
  </select>
  {availableBackends.length === 0 && (
    <span className="text-xs text-status-error">No backends available</span>
  )}
</div>
```

> **Resilience:** If only CosmosDB is available, the dropdown shows "CosmosDB" (disabled, single option). Fabric never appears. Vice versa. Both available → dropdown is active.

**Fabric Setup tab content:** Same as original plan (workspace ID input, provisioning button with SSE progress, ontology/eventhouse/graph-model dropdowns, Load Topology + Provision Agents buttons).

**Upload tab adaptation:** Same as original plan (Lakehouse/Eventhouse CSV uploads for Fabric, .tar.gz for CosmosDB).

#### `AddScenarioModal.tsx` — Backend-aware upload slots

```tsx
const { activeBackendType } = useScenarioContext();

const COSMOS_SLOTS: SlotDef[] = [
  { key: 'graph', label: 'Graph Data', endpoint: '/query/upload/graph', accept: '.tar.gz,.tgz' },
  { key: 'telemetry', label: 'Telemetry', endpoint: '/query/upload/telemetry', accept: '.tar.gz,.tgz' },
  { key: 'runbooks', label: 'Runbooks', endpoint: '/query/upload/runbooks', accept: '.tar.gz,.tgz' },
  { key: 'tickets', label: 'Tickets', endpoint: '/query/upload/tickets', accept: '.tar.gz,.tgz' },
  { key: 'prompts', label: 'Prompts', endpoint: '/query/upload/prompts', accept: '.tar.gz,.tgz' },
];

const FABRIC_SLOTS: SlotDef[] = [
  { key: 'graph', label: 'Lakehouse (Graph CSVs)', endpoint: '/api/fabric/upload-lakehouse',
    accept: '.csv', hint: 'Dim*.csv, Fact*.csv', multiFile: true },
  { key: 'telemetry', label: 'Eventhouse (Telemetry CSVs)', endpoint: '/api/fabric/upload-eventhouse',
    accept: '.csv', hint: 'AlertStream.csv, LinkTelemetry.csv', multiFile: true },
  { key: 'runbooks', label: 'Runbooks', endpoint: '/query/upload/runbooks', accept: '.tar.gz,.tgz' },
  { key: 'tickets', label: 'Tickets', endpoint: '/query/upload/tickets', accept: '.tar.gz,.tgz' },
  { key: 'prompts', label: 'Prompts', endpoint: '/query/upload/prompts', accept: '.tar.gz,.tgz' },
];

const SLOT_DEFS = activeBackendType === 'fabric' ? FABRIC_SLOTS : COSMOS_SLOTS;
```

> **Important:** Runbooks, tickets, and prompts use `/query/upload/*` (cosmosdb-graph-api) even in Fabric mode. These are backend-agnostic — they're stored in AI Search/Cosmos prompts DB regardless of graph backend. This means cosmosdb-graph-api must be available for these uploads to work, even when Fabric is the graph backend. See Gap 6.

#### `hooks/useScenarios.ts` — Pass backend_type on config/apply

```tsx
// selectScenario() calls POST /api/config/apply.
// When Fabric is selected, include backend info:

const applyBody = activeBackendType === 'fabric'
  ? {
      ...baseBody,
      backend_type: 'fabric',
      fabric_workspace_id: fabricWorkspaceId,
      fabric_ontology_id: fabricOntologyId,
      fabric_graph_model_id: fabricGraphModelId,
    }
  : baseBody;
```

#### Frontend files summary

| File | Change | Description |
|------|--------|-------------|
| `context/ScenarioContext.tsx` | MODIFY | Add `activeBackendType`, `availableBackends`, Fabric state (6 new fields + setters), `useEffect` health detection on mount |
| `hooks/useFabric.ts` | **CREATE** | Discovery (→ `/fabric/*`) + provisioning (→ `/api/fabric/*`) hook |
| `hooks/useTopology.ts` | MODIFY | Route to `/fabric/topology` or `/query/topology` based on `activeBackendType`; Fabric body uses `{workspace_id, graph_model_id, ontology_id}` instead of `{vertex_labels}` |
| `hooks/useScenarios.ts` | MODIFY | Pass `backend_type` + Fabric IDs in config/apply |
| `components/SettingsModal.tsx` | MODIFY | Backend dropdown (filtered by availability), adaptive tabs, Fabric Setup tab, adaptive Upload tab |
| `components/AddScenarioModal.tsx` | MODIFY | Refactor `SLOT_DEFS` from module-level constant to backend-reactive derived value; update `detectSlot()` helper and `KNOWN_SUFFIXES` for Fabric file types |
| `utils/sseStream.ts` | MODIFY | `uploadWithSSE()` signature changes from `file: File` to `file: File \| File[]`; when array, append each with `formData.append('file', f)` loop |

### UX Enhancements

Same as original plan:
- **5a. Auto-fetch on workspace ID entry:** Debounce 500ms after valid UUID entered
- **5b. Loading spinner during discovery:** Show spinner while Fabric REST calls are in flight
- **5c. Backend dropdown auto-tab-switch:** Switch to appropriate tab on backend change
- **5d. Post-provisioning auto-populate:** Auto-fetch ontologies/eventhouses after provisioning completes

---

## Implementation Phases

> **V10 Prerequisite:** All V11 phases assume V10 Phases 0–9 are complete.
> Specifically:
> - V10 Phase 0 (Infrastructure Genericization) → before V11 Phase 0
> - V10 Phases 1–3 (DocumentStore, Cosmos Config, ScenarioContext) → before V11 Phase 0 rename
> - V10 Phase 7 (Backend Registry) → before V11 Phase 0 health endpoint
> - V10 Phase 8 (Config-Driven Provisioner) → before V11 Phase 4
> - V10 Phase 9 (OpenAPI Templating) → before V11 Phase 4
> - V10 Phase 11 (Frontend Genericization) → before V11 Phase 5
>
> V11 Phases 1–3.5 can run in parallel with V10 Phases 10–13 (prompt system,
> frontend, visualizer, backward compat) since they operate on independent code.

### Phase 0: Directory Rename & Infrastructure

> **Prerequisite for everything.** Must be done first.
> **V10 Prerequisite:** V10 Phases 0–9 complete (infrastructure genericized, stores/adapters/services dirs exist in `graph-query-api/`, backend is string-based).

**Actions:**
1. `git mv graph-query-api cosmosdb-graph-api`
2. Update `cosmosdb-graph-api/pyproject.toml` project name
3. Update `Dockerfile` — all `graph-query-api` references → `cosmosdb-graph-api`, add `fabric-graph-api` build block
4. Update `supervisord.conf` — rename program, add `fabric-graph-api` program
5. Update `nginx.conf` — update comment, add `/fabric/` location block
6. Update `frontend/vite.config.ts` — add `/fabric` proxy
7. Update `deploy.sh` — all 3 `graph-query-api` string references → `cosmosdb-graph-api`, add Fabric local start command, renumber terminal instructions (see Item 0 `deploy.sh` section for exact line changes)
8. Update `azure.yaml` — update comment
9. Create empty `fabric-graph-api/` directory (populated in Phase 1)
10. **CRITICAL:** Update `scripts/agent_provisioner.py` — fix `OPENAPI_DIR` path from `graph-query-api/openapi` to `cosmosdb-graph-api/openapi` (without this, `/api/config/apply` breaks immediately after the rename)
11. **CRITICAL:** Add `GET /query/health` endpoint to `cosmosdb-graph-api/main.py` (required by frontend health detection in Phase 5; must exist before that phase)
12. Update `azure_config.env.template` — add Fabric variables section (Gap 12)

**Files modified:**
- `cosmosdb-graph-api/pyproject.toml` (renamed)
- `cosmosdb-graph-api/main.py` (add `/query/health` endpoint)
- `Dockerfile`
- `supervisord.conf`
- `nginx.conf`
- `frontend/vite.config.ts`
- `deploy.sh`
- `azure.yaml`
- `scripts/agent_provisioner.py` (fix `OPENAPI_DIR` path)
- `azure_config.env.template` (add Fabric section)

**Verification:**
- `docker build .` succeeds (even with empty `fabric-graph-api/`)
- Existing functionality works identically (all `/query/*` routes still work)
- `git log --follow cosmosdb-graph-api/config.py` shows full history
- `POST /api/config/apply` still provisions agents successfully (OPENAPI_DIR path is correct)
- `GET /query/health` returns `{"status": "healthy", "backend": "cosmosdb"}` via both direct access (`:8100/query/health`) and nginx proxy (`/query/health`)

### Phase 1: fabric-graph-api Service Setup

> Depends on Phase 0 (directory exists).

**Files to create:**
- `fabric-graph-api/pyproject.toml`
- `fabric-graph-api/config.py`
- `fabric-graph-api/models.py`
- `fabric-graph-api/main.py`

**Post-create step:**
- Run `cd fabric-graph-api && uv lock` to generate `uv.lock` (required by the Dockerfile's `uv sync --frozen`)

**Verification:**
- `cd fabric-graph-api && uv sync` → installs minimal deps
- `uv run uvicorn main:app --port 8200` → starts, `/fabric/health` returns 503 (missing vars)
- Set `FABRIC_WORKSPACE_ID` + `FABRIC_GRAPH_MODEL_ID` → `/fabric/health` returns 200
- All other endpoints return 503 when unconfigured
- `fabric-graph-api/uv.lock` exists and `docker build .` succeeds

### Phase 2: Fabric Graph Backend

> Depends on Phase 1. Can parallelize with Phase 3.

**Files to create:**
- `fabric-graph-api/fabric_backend.py`
- `fabric-graph-api/router_graph.py`
- `fabric-graph-api/router_topology.py`

**Verification:**
- Unit test: Mock Fabric REST API, execute GQL query, verify response
- Integration test: Real Fabric workspace → `POST /fabric/graph` with GQL → returns data
- `POST /fabric/topology` → returns `{nodes, edges, meta}`
- Rate limit retry: Mock 429 → verify backoff

### Phase 3: Fabric Discovery Endpoints

> Depends on Phase 1. Can parallelize with Phase 2.

**Files to create:**
- `fabric-graph-api/router_discovery.py`

**Verification:**
- `GET /fabric/ontologies?workspace_id=<valid>` → returns list
- `GET /fabric/eventhouses?workspace_id=<valid>` → returns list
- `GET /fabric/graph-models?workspace_id=<valid>` → returns list
- Missing workspace ID → 400

### Phase 3.5: Fabric Provisioning API

> Depends on Phase 1 (env var names). Independent of Phases 2/3.

**Files to create:**
- `api/app/routers/fabric_provision.py`
- `scripts/fabric/_provisioner.py`

**Files to modify:**
- `api/app/main.py` — register provisioning router
- `api/pyproject.toml` — add `azure-storage-file-datalake`, `azure-kusto-data`, `azure-kusto-ingest`
- `scripts/fabric/provision_lakehouse.py` — refactor to thin CLI wrapper
- `scripts/fabric/provision_eventhouse.py` — refactor to thin CLI wrapper
- `scripts/fabric/provision_ontology.py` — refactor to thin CLI wrapper

**Verification:**
- `POST /api/fabric/provision` → SSE stream completes all steps
- `POST /api/fabric/upload-lakehouse` with CSVs → tables created
- Standalone scripts still work

### Phase 4: Agent Provisioner Changes

> Depends on Phase 2 (working backend).
> **V10 Prerequisite:** V10 Phase 8 (Config-Driven Provisioner) and Phase 9 (OpenAPI Templating) must be complete.
> 
> **Note:** The `OPENAPI_DIR` path fix (`graph-query-api` → `cosmosdb-graph-api`) was already done in Phase 0 (critical rename dependency). This phase adds the `"fabric-gql"` connector to V10's config-driven provisioner structures (`CONNECTOR_OPENAPI_VARS`, `_load_openapi_spec()` directory resolution) and creates the Fabric scenario YAML + GQL prompt fragment.

**Files to create:**
- `fabric-graph-api/openapi/fabric.yaml`
- `prompts/graph_explorer/language_gql.md` (GQL prompt fragment for V10's `compose_with_connector`)
- `data/scenarios/fabric-telecom/scenario.yaml` (Fabric scenario using V10 v2.0 YAML schema)

**Files to modify:**
- `scripts/agent_provisioner.py` — add `FABRIC_OPENAPI_DIR`, add `"fabric-gql"` to `CONNECTOR_OPENAPI_VARS`, update `_load_openapi_spec()` to resolve Fabric specs from correct directory
- `api/app/routers/config.py` — add `backend_type` + Fabric fields to `ConfigApplyRequest`

**Verification:**
- Upload Fabric scenario YAML → `save_scenario_config()` stores it (V10 mechanism)
- `POST /api/config/apply { prompt_scenario: "fabric-telecom" }` → agents provisioned with Fabric spec and GQL prompts, targeting `/fabric/graph`
- `POST /api/config/apply { prompt_scenario: "telco-noc-5g" }` → agents provisioned with Cosmos spec (unchanged)
- Agent GraphExplorer sends GQL to `/fabric/graph` → gets results

### Phase 5: Frontend — Adaptive Backend UI

> Depends on Phase 0 (URL routes), Phase 3 (discovery), Phase 3.5 (provisioning).
> **V10 Prerequisite:** V10 Phase 11 (Frontend Genericization) should be complete.
> V11's frontend changes build on V10's config-aware scaffold (empty `graphConstants`,
> config-specified resources in `ScenarioContext`, dynamic agent names).

**Files to create:**
- `frontend/src/hooks/useFabric.ts`

**Files to modify:**
- `frontend/src/context/ScenarioContext.tsx` — backend type, availability, Fabric state
- `frontend/src/hooks/useTopology.ts` — backend-aware URL routing
- `frontend/src/hooks/useScenarios.ts` — pass backend_type on config/apply
- `frontend/src/components/SettingsModal.tsx` — adaptive tabs, backend dropdown, Fabric Setup
- `frontend/src/components/AddScenarioModal.tsx` — backend-aware upload slots
- `frontend/src/utils/sseStream.ts` — multi-file upload support

**Verification:**
- Page load with only cosmosdb-graph-api running → dropdown shows only "CosmosDB"
- Page load with both running → dropdown shows both
- Switch to Fabric → tabs change, topology fetches from `/fabric/topology`
- Switch back to CosmosDB → everything restored
- Close fabric-graph-api mid-session → "Fabric" option disappears on next health probe
- All existing CosmosDB functionality unchanged

### Phase 6: End-to-End Testing

> Depends on all previous phases.

**Scenarios:**
1. **Full flow (Fabric):** Toggle to Fabric → enter workspace → select ontology → load topology → provision agents → chat → agent queries Fabric → response
2. **Full flow (CosmosDB):** Standard scenario flow → all unchanged
3. **Backend switching:** Start CosmosDB → toggle Fabric → toggle back → no regressions
4. **Fabric unavailable:** Stop fabric-graph-api → CosmosDB works fully → Fabric option hidden
5. **CosmosDB unavailable:** Stop cosmosdb-graph-api → Fabric graph queries work → prompts/scenarios unavailable (expected)
6. **Mock mode:** `GRAPH_BACKEND=mock` in cosmosdb-graph-api → works as before

---

## File Change Inventory

### Phase 0 — Rename & Infrastructure

> **Post-V10 note:** The directory being renamed (`graph-query-api/`) now contains V10-created
> subdirectories (`stores/`, `adapters/`, `services/`). These are included in the rename
> automatically. The Dockerfile COPY commands must include these new directories.

| File | Action | Changes |
|------|--------|---------|
| `graph-query-api/` → `cosmosdb-graph-api/` | RENAME | `git mv` — all contents unchanged (includes V10 dirs: `stores/`, `adapters/`, `services/`) |
| `cosmosdb-graph-api/pyproject.toml` | MODIFY | `name = "cosmosdb-graph-api"` (was `graph-query-api`) |
| `Dockerfile` | MODIFY | `graph-query-api` → `cosmosdb-graph-api` in all COPY/WORKDIR; add `fabric-graph-api` build block; add COPY for V10 dirs (`stores/`, `adapters/`, `services/`) |
| `supervisord.conf` | MODIFY | Rename `[program:graph-query-api]` → `[program:cosmosdb-graph-api]`, update directory; add `[program:fabric-graph-api]` |
| `nginx.conf` | MODIFY | Update comment; add `location /fabric/` block |
| `frontend/vite.config.ts` | MODIFY | Add `/fabric` proxy to port 8200 |
| `deploy.sh` | MODIFY | `graph-query-api` string refs → `cosmosdb-graph-api` (post-V10: fewer occurrences since Phase 0 genericizes); add Fabric local start; renumber terminals |
| `azure.yaml` | MODIFY | Update comment |
| `scripts/agent_provisioner.py` | MODIFY | Fix `OPENAPI_DIR` path: `graph-query-api/openapi` → `cosmosdb-graph-api/openapi` (CRITICAL — agent provisioning breaks without this) |
| `cosmosdb-graph-api/main.py` | MODIFY | Add `GET /query/health` endpoint; use `GRAPH_BACKEND` as plain string (post-V10: no `.value`) |
| `azure_config.env.template` | MODIFY | Add Fabric variables section (post-V10: template is already genericized, Fabric section is purely additive) |

### Phase 1 — fabric-graph-api Setup

| File | Action | Changes |
|------|--------|---------|
| `fabric-graph-api/pyproject.toml` | **CREATE** | Minimal deps: fastapi, uvicorn, azure-identity, httpx, pydantic |
| `fabric-graph-api/config.py` | **CREATE** | Fabric-specific env vars, credential, `CONFIGURED` flag |
| `fabric-graph-api/models.py` | **CREATE** | GraphQueryRequest/Response, TopologyRequest/Response, FabricItem, FabricListResponse |
| `fabric-graph-api/main.py` | **CREATE** | FastAPI app, health check, guard middleware, router registration |
| `fabric-graph-api/uv.lock` | **GENERATE** | Run `cd fabric-graph-api && uv lock` after creating `pyproject.toml` (required by Dockerfile `uv sync --frozen`) |

### Phase 2 — Fabric Graph Backend

| File | Action | Changes |
|------|--------|---------|
| `fabric-graph-api/fabric_backend.py` | **CREATE** | FabricGraphBackend class (~200 lines) — execute_query(), get_topology() |
| `fabric-graph-api/router_graph.py` | **CREATE** | `POST /fabric/graph` endpoint |
| `fabric-graph-api/router_topology.py` | **CREATE** | `POST /fabric/topology` endpoint |

### Phase 3 — Discovery Endpoints

| File | Action | Changes |
|------|--------|---------|
| `fabric-graph-api/router_discovery.py` | **CREATE** | `GET /fabric/ontologies`, `/fabric/eventhouses`, `/fabric/graph-models` |

### Phase 3.5 — Provisioning API

| File | Action | Changes |
|------|--------|---------|
| `api/app/routers/fabric_provision.py` | **CREATE** | Provisioning + CSV upload endpoints (~300 lines) |
| `scripts/fabric/_provisioner.py` | **CREATE** | Shared provisioning logic |
| `api/app/main.py` | MODIFY | Register `fabric_provision_router` |
| `api/pyproject.toml` | MODIFY | Add `azure-storage-file-datalake`, `azure-kusto-data`, `azure-kusto-ingest` |
| `scripts/fabric/provision_lakehouse.py` | MODIFY | Refactor to thin CLI wrapper |
| `scripts/fabric/provision_eventhouse.py` | MODIFY | Refactor to thin CLI wrapper |
| `scripts/fabric/provision_ontology.py` | MODIFY | Refactor to thin CLI wrapper |

### Phase 4 — Agent Provisioner

> **Post-V10:** The provisioner is now config-driven (`provision_from_config()`). The changes
> here add `"fabric-gql"` connector support to V10's data-driven structures, not a hardcoded map.

| File | Action | Changes |
|------|--------|---------|
| `fabric-graph-api/openapi/fabric.yaml` | **CREATE** | GQL OpenAPI spec (~160 lines) |
| `prompts/graph_explorer/language_gql.md` | **CREATE** | GQL prompt fragment for V10's `compose_with_connector` mechanism |
| `data/scenarios/fabric-telecom/scenario.yaml` | **CREATE** | Fabric scenario YAML using V10 v2.0 schema (`connector: "fabric-gql"`) |
| `scripts/agent_provisioner.py` | MODIFY | Add `FABRIC_OPENAPI_DIR`; add `"fabric-gql"` to `CONNECTOR_OPENAPI_VARS`; update `_load_openapi_spec()` to resolve from Fabric dir when connector starts with `"fabric"` |
| `api/app/routers/config.py` | MODIFY | Add `backend_type` + Fabric fields to `ConfigApplyRequest` |

### Phase 5 — Frontend

| File | Action | Changes |
|------|--------|---------|
| `frontend/src/hooks/useFabric.ts` | **CREATE** | Fabric discovery + provisioning hook (~120 lines) |
| `frontend/src/context/ScenarioContext.tsx` | MODIFY | Add `activeBackendType`, `availableBackends`, 5 Fabric ID fields + setters, `useEffect` health detection on mount |
| `frontend/src/hooks/useTopology.ts` | MODIFY | Backend-aware URL (`/fabric/topology` vs `/query/topology`); different request bodies per backend |
| `frontend/src/hooks/useScenarios.ts` | MODIFY | Pass `backend_type` + Fabric IDs on config/apply |
| `frontend/src/components/SettingsModal.tsx` | MODIFY | Backend dropdown (availability-filtered), adaptive tabs, Fabric Setup, adaptive Upload |
| `frontend/src/components/AddScenarioModal.tsx` | MODIFY | Refactor `SLOT_DEFS` from module constant to backend-reactive; update `detectSlot()` + `KNOWN_SUFFIXES` |
| `frontend/src/utils/sseStream.ts` | MODIFY | `uploadWithSSE()` signature: `file: File` → `file: File \| File[]` (backwards-compatible) |

### Files NOT Changed

| File | Rationale |
|------|-----------|
| `cosmosdb-graph-api/config.py` | No Fabric code — service separation |
| `cosmosdb-graph-api/backends/cosmosdb.py` | Unchanged — Cosmos backend is independent |
| `cosmosdb-graph-api/backends/mock.py` | Unchanged |
| `cosmosdb-graph-api/backends/__init__.py` | No FABRIC dispatch added — that's in a separate service |
| `cosmosdb-graph-api/models.py` | No `workspace_id`/`graph_model_id` fields — those are Fabric-specific |
| `cosmosdb-graph-api/router_graph.py` | Unchanged — Cosmos graph routing is independent |
| `cosmosdb-graph-api/router_telemetry.py` | No 501 guard clause — Fabric telemetry is a separate service concern |
| `cosmosdb-graph-api/router_topology.py` | Unchanged |
| `cosmosdb-graph-api/openapi/cosmosdb.yaml` | Unchanged |
| `cosmosdb-graph-api/openapi/mock.yaml` | Unchanged |

> **The core benefit:** Every file in the "NOT Changed" list is a file that could have introduced regressions in the original plan. By separating services, we protect the stable Cosmos codebase from any Fabric-related changes.
>
> **Note:** `cosmosdb-graph-api/main.py` appears in both "Phase 0" (add `/query/health`) and "NOT Changed" (no Fabric code) — the `/query/health` addition is a Cosmos-only change that improves service discoverability, not a Fabric entanglement.

---

## Cross-Cutting Concerns & Gaps

### Gap 1: Telemetry queries in Fabric mode

**Current status:** Deferred. `fabric-graph-api` does not expose a `/fabric/telemetry` endpoint.

**Impact:** When Fabric is selected, telemetry data is unavailable. The agent's GQL-documented OpenAPI spec has no telemetry path. The frontend telemetry panel shows "Telemetry not available in Fabric mode."

**Future fix:** Add `/fabric/telemetry` endpoint using `azure-kusto-data` SDK for KQL queries against Eventhouse. This is a self-contained addition to `fabric-graph-api` — zero impact on cosmosdb-graph-api.

### Gap 2: Prompt set compatibility

**Status:** In scope (Phase 5). Prompts remain in Cosmos NoSQL regardless of graph backend. The Fabric Setup tab includes a prompt set dropdown (shared with CosmosDB) that calls `/query/prompts/scenarios`.

**Dependency:** This means cosmosdb-graph-api must be running for prompts to work, even in Fabric mode. The frontend handles this — if cosmosdb-graph-api is down, the prompt dropdown shows an error.

### Gap 3: Graph visualizer GQL response format

**Status:** Same as original — the `get_topology()` method must transform tabular GQL results to `{nodes, edges}`. Start with hard-coded mapping, then generalize.

### Gap 6: Cosmos DB still required in Fabric mode

**Impact:** Prompts, scenarios, interactions, and AI Search indexes live in Cosmos/AI Search. These are served by cosmosdb-graph-api. If cosmosdb-graph-api is unavailable, these features don't work even when Fabric is selected.

**V10 note:** V10 Phase 1 introduces the `DocumentStore` Protocol, which abstracts document
persistence behind a generic interface. Currently, the only implementation is `CosmosDocumentStore`,
but the protocol is designed for alternative backends. In the future, a `FabricDocumentStore`
(backed by Fabric Lakehouse or Eventhouse) could eliminate the Cosmos dependency for shared
concerns (prompts, scenarios, interactions). This is out of scope for V11 but the architectural
path exists thanks to V10.

**Mitigation:**
- The Fabric Setup tab shows a note: "Prompts and knowledge bases are stored in Cosmos DB / AI Search regardless of graph backend."
- The backend availability detection makes this visible: if only `fabric` is available but `cosmosdb` is not, the dropdown shows Fabric but prompts/scenarios features show "CosmosDB unavailable" inline.

### Gap 7: Ontology schema drift

**Status:** Same as original — audit `provision_ontology.py` against schema YAML before implementation.

### Gap 8: `FABRIC_KQL_DB_NAME` vs display name

**Status:** Same as original — use `properties.databaseName`, not `displayName`.

### Gap 9: Multi-file upload for Fabric CSVs

**Status:** Same as original — extend `UploadBox` with `multiple` prop or create `MultiFileUploadBox`.

**Implementation detail for `sseStream.ts`:** The current `uploadWithSSE()` signature accepts a single `File`. Fabric Lakehouse/Eventhouse uploads require multiple CSVs. Change signature to:

```typescript
export async function uploadWithSSE(
  endpoint: string,
  file: File | File[],
  handlers: SSEHandlers,
  params?: Record<string, string>,
  signal?: AbortSignal,
): Promise<Record<string, unknown> | undefined> {
  const formData = new FormData();
  if (Array.isArray(file)) {
    for (const f of file) formData.append('file', f);
  } else {
    formData.append('file', file);
  }
  // ... rest unchanged
}
```

This is backwards-compatible — existing single-`File` callers continue to work.

### Gap 10: `assign_fabric_role.py` in provisioning pipeline

**Status:** Same as original — include as Step 9 in provisioning.

### Gap 11: Graph indexing delay (20-90 min)

**Status:** Same as original — show warning banner after provisioning.

### Gap 12: `azure_config.env.template` Fabric section ~~(NEW)~~ → RESOLVED in Phase 0

**Impact:** The env template needs Fabric-specific variables so users know what to configure.

**Resolution:** Add Fabric section to `azure_config.env.template` in Phase 0 (added to Phase 0 actions list, item 12):

```bash
# --- Fabric Integration (optional — only for fabric-graph-api) ---
FABRIC_API_URL=https://api.fabric.microsoft.com/v1
FABRIC_SCOPE=https://api.fabric.microsoft.com/.default
FABRIC_SKU=F8
AZURE_FABRIC_ADMIN=
FABRIC_CAPACITY_ID=
FABRIC_WORKSPACE_ID=
FABRIC_WORKSPACE_NAME=
FABRIC_LAKEHOUSE_ID=
FABRIC_LAKEHOUSE_NAME=
FABRIC_ONTOLOGY_ID=
FABRIC_ONTOLOGY_NAME=
FABRIC_GRAPH_MODEL_ID=
FABRIC_EVENTHOUSE_ID=
FABRIC_EVENTHOUSE_NAME=
FABRIC_KQL_DB_ID=
FABRIC_KQL_DB_NAME=
FABRIC_KQL_DB_DEFAULT=NetworkDB
EVENTHOUSE_QUERY_URI=
FABRIC_CONNECTION_NAME=
GRAPH_FABRIC_CONNECTION_NAME=
TELEMETRY_FABRIC_CONNECTION_NAME=
FABRIC_DATA_AGENT_ID=
FABRIC_DATA_AGENT_API_VERSION=
GRAPH_DATA_AGENT_ID=
TELEMETRY_DATA_AGENT_ID=
```

### Gap 13: cosmosdb-graph-api health endpoint ~~(NEW)~~ → RESOLVED in Phase 0

**Impact:** The frontend probes `/query/health` to determine if the CosmosDB backend is available. Currently, `cosmosdb-graph-api` does not have a dedicated `/query/health` endpoint — the `/health` route goes to the API service (port 8000), not cosmosdb-graph-api.

**Resolution:** ~~Add a `GET /query/health` endpoint to `cosmosdb-graph-api/main.py` (Phase 0).~~ **Done — integrated into Phase 0 actions list (item 11) and Item 0 changes.** See the `cosmosdb-graph-api/main.py` section under Item 0 for the full implementation.

The frontend uses `/query/health` (→ cosmosdb-graph-api on :8100) and `/fabric/health` (→ fabric-graph-api on :8200) independently.

### Gap 14: Resource Visualizer — Fabric nodes (NEW)

**Impact:** V10 Phase 12 introduces a real backend endpoint for the Resource Visualizer
(`GET /query/resources`), replacing the current hardcoded frontend mock. The visualizer
shows a dependency graph of infrastructure resources (Cosmos account, databases, containers,
AI Search indexes, etc.).

**V11 addition:** When Fabric is the active backend, the Resource Visualizer should include
Fabric-specific nodes:
- Fabric Capacity → Workspace → Ontology → Graph Model (provisioning hierarchy)
- Fabric Workspace → Lakehouse (data storage)
- Fabric Workspace → Eventhouse → KQL Database (telemetry storage)

**Implementation approach:** The Resource Visualizer backend endpoint (V10 Phase 12) returns
a graph of resources. V11 adds a `/fabric/resources` endpoint to `fabric-graph-api` that
returns Fabric-specific resource nodes. The frontend merges both resource graphs when both
backends are available, or shows only the relevant one.

**Priority:** P2 — functional but not critical for V11 MVP. Can be added as a follow-up
after the core Fabric integration works.

### Gap 15: V10 `_normalize_manifest()` backward compatibility (NEW)

**Impact:** V10 Phase 13 introduces `_normalize_manifest()` which converts old YAML format
(`cosmos:` key) to v2.0 format (`data_sources:` key). Fabric scenarios should always use
v2.0 format natively — they should **not** use the `cosmos:` key.

**Mitigation:** Document in the Fabric scenario YAML template that `data_sources:` is
required (not `cosmos:`). `_normalize_manifest()` handles old Cosmos scenarios, not Fabric
scenarios.

---

## Edge Cases & Validation

### Service Isolation (Item 0)

**cosmosdb-graph-api crash:** If the Cosmos service crashes and supervisord restarts it, fabric-graph-api continues serving Fabric queries uninterrupted. The frontend detects the health change on next probe and may show "CosmosDB temporarily unavailable."

**fabric-graph-api crash:** Same — Cosmos service is unaffected. Fabric option disappears from the dropdown until the service recovers.

**Port conflict:** If port 8200 is already in use, supervisord logs the error and retries. Both services use `127.0.0.1` binding — no external exposure.

**Shared env vars:** Both services read the same env file (`azure_config.env`). Each reads only its own vars. No naming conflicts because Fabric vars use `FABRIC_` prefix and Cosmos vars use `COSMOS_` prefix.

### Fabric Graph Backend (Item 2)

**Rate limiting:** Same as original — 5 retries with exponential backoff, minimum 15s × attempt.

**Credential expiry:** `DefaultAzureCredential` handles token caching and refresh internally.

**GQL syntax errors:** Fabric returns error in `status.description` — returned as error body for LLM self-correction.

**Large graph responses:** Cap at ~5000 nodes for browser performance.

### Fabric Discovery (Item 3)

**No Fabric access (403):** Routes to `HTTPException(403)` with clear message.

**Empty workspace:** Returns `{"items": []}` — frontend shows empty dropdown.

**Pagination:** First page only; log warning if `continuationUri` present.

### Frontend Resilience (Item 5)

**Health probe timing:** 3-second timeout per probe. Both probes run in parallel on mount.

**Stale localStorage:** If `activeBackendType: "fabric"` is in localStorage but fabric-graph-api is now unavailable, the health probe detects this and auto-switches to the first available backend.

**Rapid backend toggling:** Last toggle wins (React state batching). Tab bar rendering is a pure function of `activeBackendType`.

**Mixed-mode uploads:** Fabric graph/telemetry uploads go to `/api/fabric/upload-*` (API service). Runbooks/tickets/prompts uploads go to `/query/upload/*` (cosmosdb-graph-api). Both must be available for a full Fabric scenario upload.

---

## Migration & Backwards Compatibility

### Directory Rename

The `git mv graph-query-api cosmosdb-graph-api` command preserves git history. All internal Python imports are relative (no `from graph_query_api import ...`), so no code changes are needed inside the directory.

### API Surface Compatibility

All changes are **additive**:
- New service on new port with new URL prefix (`/fabric/*`)
- No changes to existing `/query/*` endpoints
- New optional fields on `ConfigApplyRequest` (Pydantic defaults)
- New provisioning router at `/api/fabric/*`

### Gradual Adoption

1. **Phase 0** — rename and infra. Deploy → everything works as before. No Fabric functionality yet.
2. **Phase 1-3** — fabric-graph-api starts but returns 503 (unconfigured). No UI change. Background service.
3. **Phase 3.5** — provisioning API available via curl/API, no UI yet.
4. **Phase 5** — frontend detects fabric-graph-api as healthy → Fabric option appears in dropdown.
5. **No forced migration** — CosmosDB remains the default forever unless the user explicitly switches.

### Rollback Plan

- **Full rollback:** `git mv cosmosdb-graph-api graph-query-api`, delete `fabric-graph-api/`, revert infrastructure files. Zero data cleanup needed.
- **Partial rollback (keep rename, drop Fabric):** Delete `fabric-graph-api/`, remove `[program:fabric-graph-api]` from supervisord, remove `/fabric/` from nginx. CosmosDB works under new name.
- **Feature flag alternative:** Set `FABRIC_ENABLED=false` → fabric-graph-api still starts but health returns 503 → frontend hides Fabric option. No code removal needed.

---

## UX Priority Matrix

| Priority | Enhancement | Phase | Effort | Impact |
|----------|------------|-------|--------|--------|
| **P0** | Backend dropdown (availability-filtered) | 5 | Small | High |
| **P0** | Health probe — auto-detect available backends | 5 | Small | High |
| **P0** | Context-adaptive tab layout | 5 | Small | High |
| **P0** | Workspace ID input | 5 | Tiny | High |
| **P0** | Ontology/eventhouse/graph-model dropdowns | 5 | Small | High |
| **P0** | Adaptive AddScenarioModal (CSV slots) | 5 | Medium | High |
| **P0** | Adaptive Upload tab | 5 | Small | High |
| **P0** | One-click Fabric provisioning (SSE) | 3.5 | Medium | High |
| **P0** | Backend-aware topology fetching | 5 | Small | High |
| **P1** | Auto-fetch on workspace ID entry | 5 | Tiny | Medium |
| **P1** | Loading spinner during discovery | 5 | Tiny | Medium |
| **P1** | Post-provisioning auto-populate | 5 | Tiny | Medium |
| **P1** | Prompt set selector in Fabric Setup tab | 5 | Small | Medium |
| **P1** | "CosmosDB unavailable" inline error for prompts | 5 | Tiny | Medium |
| **P2** | Fabric connection status indicator | 5 | Small | Medium |
| **P2** | Periodic health re-probe (detect recovered service) | 5 | Small | Low |
| **P3** | KQL telemetry queries via `/fabric/telemetry` | Future | Large | Low |
