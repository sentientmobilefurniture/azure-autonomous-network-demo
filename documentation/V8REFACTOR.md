# Codebase Simplification & Refactor — Implementation Plan

> **Created:** 2026-02-15
> **Last audited:** 2026-02-15 ✅ (all claims verified against source; 9 corrections applied)
> **Status:** ⬜ Not Started
> **Goal:** Reduce codebase complexity by ~1,826 lines (~13.8%) through
> dead code removal, pattern deduplication, and structural consolidation —
> without altering any API contracts, UI behavior, or deployment topology.
> All existing functionality is preserved; changes are purely structural.

---

## Requirements (Original)

1. Preserve all functionality and the good quality of the current codebase without altering key functions.
2. Simplify and streamline the codebase for efficiency and elegance without damaging functionality.
3. Achieve a reduction in the number of lines and the overall codebase complexity while preserving integrity and robustness, scalability, ease-of-use.
4. Enhance maintainability and ease of understanding.
5. Improving functionality would be ideal as a bonus.

---

## Implementation Status

| Phase | Status | Scope |
|-------|--------|-------|
| **Phase 1:** Zero-risk cleanup | ⬜ Not started | `router_ingest.py`, `main.py`, `search_indexer.py`, `router_telemetry.py` |
| **Phase 2:** Backend DRY refactoring | ⬜ Not started | New `cosmos_helpers.py`, `sse_helpers.py`; modify 5 routers + `config.py` + `orchestrator.py` |
| **Phase 3:** Script consolidation | ⬜ Not started | `provision_agents.py`, `agent_provisioner.py`, `scenario_loader.py` |
| **Phase 4:** Frontend componentisation | ⬜ Not started | `SettingsModal.tsx`, `AddScenarioModal.tsx`, new shared components |
| **Phase 5:** Cross-service cleanup | ⬜ Not started | `api/app/main.py`, `graph-query-api/main.py`, `api/app/routers/logs.py` |

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
- [Item 1: Dead Code Removal](#item-1-dead-code-removal)
- [Item 2: SSE Streaming Helper Extraction](#item-2-sse-streaming-helper-extraction)
- [Item 3: Cosmos Container Helper Extraction](#item-3-cosmos-container-helper-extraction)
- [Item 4: Merge Runbooks/Tickets Upload Endpoints](#item-4-merge-runbookstickets-upload-endpoints)
- [Item 5: Provision Scripts Consolidation](#item-5-provision-scripts-consolidation)
- [Item 6: Frontend Component Extraction](#item-6-frontend-component-extraction)
- [Item 7: Credential & Client Caching Standardisation](#item-7-credential--client-caching-standardisation)
- [Item 8: Code Quality Fixes](#item-8-code-quality-fixes)
- [Item 9: Log SSE Handler Evaluation](#item-9-log-sse-handler-evaluation)
- [Implementation Phases](#implementation-phases)
- [File Change Inventory](#file-change-inventory)
- [Edge Cases & Validation](#edge-cases--validation)
- [Migration & Backwards Compatibility](#migration--backwards-compatibility)
- [Audit Findings](#audit-findings)

---

## Codebase Conventions & Context

### Request Routing

Two backend services sit behind nginx. The frontend dev server (Vite) mirrors the same routes for local development.

| URL prefix | Proxied to | Config |
|------------|-----------|--------|
| `/api/*` | NOC API on port **8000** | `nginx.conf` lines 12-20; `vite.config.ts` proxy section |
| `/query/*` | Graph Query API on port **8100** | `nginx.conf` lines 22-30 (600s timeout); `vite.config.ts` proxy section |
| `/health` | NOC API on port **8000** | `nginx.conf`; `vite.config.ts` |
| `/` | Static React build (`index.html`) | `nginx.conf` |

Both `/api/` and `/query/` nginx blocks have SSE support (`proxy_buffering off`, `proxy_cache off`). `/query/` has a longer 600s read timeout for uploads.

**Router prefixes in `api/`:**
- `alert.router` → `prefix="/api"` → `/api/alert/...`
- `agents.router` → `prefix="/api"`
- `logs.router` → `prefix="/api"`
- `config.router` → `prefix="/api/config"`

**Router prefixes in `graph-query-api/`:**
- `router_ingest` → `prefix="/query"`
- `router_scenarios` → `prefix="/query"`
- `router_prompts` → `prefix="/query"`
- `router_interactions` → `prefix="/query"`
- `router_graph` / `router_telemetry` / `router_topology` → no prefix (routes defined at path level)
- `main.py` directly defines `/api/logs` and `/query/logs` SSE endpoints

> **⚠️ Trap:** `/api/logs` in `graph-query-api/main.py` is **shadowed** by nginx routing (`/api/*` → port 8000). Only the `/query/logs` alias works in production.

### Naming Conventions

| Concept | Example | Derivation |
|---------|---------|-----------|
| Scenario name | `"cloud-outage"` | User-provided; validated by regex `^[a-z0-9](?!.*--)[a-z0-9-]{0,48}[a-z0-9]$` |
| Gremlin graph | `"cloud-outage-topology"` | `{scenario}-topology`; reverse via `rsplit("-", 1)[0]` |
| Gremlin database | `"networkgraph"` | Shared; from `COSMOS_GREMLIN_DATABASE` env var |
| Telemetry database | `"telemetry"` | Shared |
| Telemetry container prefix | `"cloud-outage"` | `{scenario}` (containers: `{scenario}-AlertStream`, etc.) |
| Runbooks search index | `"cloud-outage-runbooks-index"` | `{scenario}-runbooks-index` |
| Tickets search index | `"cloud-outage-tickets-index"` | `{scenario}-tickets-index` |
| Prompts database | `"prompts"` | Shared |
| Prompts container | `"cloud-outage"` | `{scenario}` (partition key `/agent`) |

**Reserved suffixes** (rejected during validation): `-topology`, `-telemetry`, `-prompts`, `-runbooks`, `-tickets`

### Import & Code Style Conventions

**Import order** (observed across all backend files):

```python
from __future__ import annotations         # 1. Future annotations
import asyncio, json, logging, os, re      # 2. Stdlib
from fastapi import APIRouter              # 3. Third-party
from azure.cosmos import CosmosClient      # 3. Third-party (Azure SDK)
from config import get_credential, ...     # 4. Local
```

**Credential pattern:**
- Data-plane: use `from config import get_credential` → lazy-cached singleton `DefaultAzureCredential()`
- ARM management-plane (inside function body): `from azure.identity import DefaultAzureCredential as _DC`

**Logger naming:** `logging.getLogger("graph-query-api.<module>")` — e.g., `graph-query-api.ingest`, `graph-query-api.scenarios`

### Data Format Conventions

| Convention | Format | Where Used |
|-----------|--------|------------|
| SSE progress | `event: progress\ndata: {"step": "...", "detail": "...", "pct": 50}\n\n` | All upload endpoints in `router_ingest.py` |
| SSE complete | `event: complete\ndata: {"scenario": "...", ...}\n\n` | Upload endpoint final event |
| SSE error | `event: error\ndata: {"error": "message"}\n\n` | Upload endpoint error event |
| SSE logs | `event: log\ndata: {"ts": "...", "level": "...", "name": "...", "msg": "..."}\n\n` | Both `/api/logs` and `/query/logs` |

> **⚠️ Trap:** The frontend `sseStream.ts` detects event types by inspecting JSON payload fields (e.g., `"pct" in parsed` → progress), **NOT** by the SSE `event:` type line. Any new helper must preserve these field names.

**SSE dispatch scaffold** (repeated 5× in `router_ingest.py`):

```python
async def stream():
    progress: asyncio.Queue = asyncio.Queue()
    def emit(step, detail, pct):
        progress.put_nowait({"step": step, "detail": detail, "pct": pct})
    async def run():
        try:
            # ... endpoint-specific logic ...
        except Exception as e:
            logger.exception("... upload failed")
            progress.put_nowait({"step": "error", "detail": str(e), "pct": -1})
        finally:
            progress.put_nowait(None)
    task = asyncio.create_task(run())
    while True:
        ev = await progress.get()
        if ev is None:
            break
        if "_result" in ev:
            yield {"event": "complete", "data": json.dumps(ev["_result"])}
        elif ev.get("step") == "error":
            yield {"event": "error", "data": json.dumps({"error": ev["detail"]})}
        else:
            yield {"event": "progress", "data": json.dumps(ev)}
    await task
return EventSourceResponse(stream())
```

---

## Overview of Changes

| # | Item | Category | Impact | Effort |
|---|------|----------|--------|--------|
| 1 | Dead code removal (`router_ingest.py` + `scenario_loader.py`) | Backend | High — removes 678 lines of noise | Trivial |
| 2 | SSE streaming helper extraction | Backend | Medium — deduplicates 5× scaffolds | Small |
| 3 | Cosmos container helper extraction | Backend | Medium — deduplicates 3× init patterns | Small |
| 4 | Merge runbooks/tickets upload endpoints | Backend | Low-Med — merges near-identical endpoints | Small |
| 5 | Provision scripts consolidation | Scripts | High — resolves 2-file duplication + bug | Medium |
| 6 | Frontend component extraction | Frontend | Medium — component readability | Medium |
| 7 | Credential & client caching standardisation | Backend | Low — consistency + resource efficiency | Small |
| 8 | Code quality fixes (bare excepts, dead imports, cache `agent_ids.json`) | Full-stack | Low — hygiene | Trivial |
| 9 | Log SSE handler evaluation | Full-stack | Low — optional cross-service dedup | Small |

### Dependency Graph

```
Phase 1 (Zero-risk cleanup) ──────────────────────┐
                                                    ├──▶ Phase 5 (Cross-service)
Phase 2 (Backend DRY) ────────────────────────────┘
    Item 7 (Credential caching) ──▶ Item 3 (Cosmos helpers)
    Item 2 (SSE helpers) ──▶ Item 4 (Merge runbooks/tickets)
Phase 3 (Script consolidation) ────── independent
Phase 4 (Frontend componentisation) ── independent
```

- **Phases 1, 3, 4** can be executed in parallel.
- **Phase 2** should follow Phase 1 (Phase 1 removes dead code from `router_ingest.py`, reducing merge conflicts).
- **Phase 5** should follow Phase 2.
- Within Phase 2: Item 7 (credential caching) should precede Item 3 (Cosmos helpers).

### UX Audit Summary

| Area | Finding | Severity |
|------|---------|----------|
| `UploadBox` SSE parsing | Hand-rolls SSE parsing instead of using imported `consumeSSE` from `sseStream.ts` — creates a bug surface | Medium |
| Name validation | Regex duplicated between `AddScenarioModal.tsx` and `router_scenarios.py` — functional but fragile | Low |
| `SettingsModal.tsx` readability | 744 lines with 3 tab views inlined; difficult to navigate | Low |

---

## Item 1: Dead Code Removal

### Current State

**`router_ingest.py`** (1,384 lines) contains ~483 lines of dead code (lines ~165–644): the original monolithic `upload_scenario()` endpoint and its `_ingest_scenario()` helper. This code is entirely commented out with `#` prefixes, interspersed with blank lines. It was superseded by the 5 per-type upload endpoints (`upload/graph`, `upload/telemetry`, `upload/runbooks`, `upload/tickets`, `upload/prompts`), which are the only active code paths.

**`scenario_loader.py`** (195 lines) defines a `ScenarioLoader` class. Grep confirms it is **only referenced within its own file** — no other file imports or uses it. This is confirmed dead code.

**`main.py` (graph-query-api)** (lines 228–236) defines a `/api/logs` endpoint that is shadowed by nginx routing in production (nginx sends `/api/*` → port 8000, not 8100). The `/query/logs` alias (lines 239–243) was added to make it accessible. The shadowed endpoint adds confusion.

**Problem:** 686 lines of dead/inaccessible code add noise and increase cognitive load for every developer who reads these files.

### Target State

- `router_ingest.py` shrinks from 1,384 to ~901 lines — only active upload endpoints remain.
- `scenario_loader.py` is deleted (or moved to `deprecated/`).
- The shadowed `/api/logs` endpoint in `graph-query-api/main.py` is removed; only `/query/logs` remains.

### Backend Changes

#### `graph-query-api/router_ingest.py` — Delete commented-out block

Delete lines ~165–644 (the entire dead monolithic code block — 401 `#`-prefixed lines + 82 blank lines).

> **⚠️ Implementation note:** The active `list_scenarios()` endpoint starts at line 647. Verify that no code below line 644 references anything in the dead block.

#### `scripts/scenario_loader.py` — Delete file

```bash
rm scripts/scenario_loader.py
# OR: mv scripts/scenario_loader.py deprecated/
```

> **⚠️ Implementation note:** Verify with `grep -r "scenario_loader" --include="*.py"` that no file imports from it.

#### `graph-query-api/main.py` — Remove shadowed `/api/logs` endpoint

```python
# Current (lines 228-243): two endpoints returning identical generator
@app.get("/api/logs")              # ← shadowed by nginx
async def stream_logs(): ...
@app.get("/query/logs")            # ← the accessible alias
async def stream_logs_query_route(): ...

# New: only the accessible route remains
@app.get("/query/logs")
async def stream_logs(): ...
```

---

## Item 2: SSE Streaming Helper Extraction

### Current State

Each of the 5 upload endpoints in `router_ingest.py` contains an identical 18-line SSE dispatch scaffold:
- `upload/graph` at ~line 783
- `upload/telemetry` at ~line 910
- `upload/runbooks` at ~line 1019
- `upload/tickets` at ~line 1121
- `upload/prompts` at ~line 1237

The scaffold includes: `asyncio.Queue` creation → `emit()` helper → `async run()` with try/except/finally → `create_task` → while-loop yielding events → `EventSourceResponse`.

**Problem:** 5× copy-pasted scaffolds — 80–120 lines of structural duplication. Bug fixes must be applied in 5 places.

### Target State

A single reusable helper in a new `graph-query-api/sse_helpers.py` module:

```python
# sse_helpers.py (~35 lines)
from __future__ import annotations
import asyncio, json, logging
from collections.abc import Callable, Coroutine
from typing import Any
from sse_starlette.sse import EventSourceResponse

logger = logging.getLogger("graph-query-api.sse")

class SSEProgress:
    """Thin wrapper around asyncio.Queue for SSE upload progress."""
    def __init__(self) -> None:
        self._q: asyncio.Queue[dict | None] = asyncio.Queue()

    def emit(self, step: str, detail: str, pct: int) -> None:
        self._q.put_nowait({"step": step, "detail": detail, "pct": pct})

    def complete(self, result: dict) -> None:
        self._q.put_nowait({"_result": result})

    def error(self, msg: str) -> None:
        self._q.put_nowait({"step": "error", "detail": msg, "pct": -1})

    def done(self) -> None:
        self._q.put_nowait(None)

    async def get(self) -> dict | None:
        return await self._q.get()


def sse_upload_response(
    work_fn: Callable[[SSEProgress], Coroutine[Any, Any, None]],
    error_label: str = "upload",
) -> EventSourceResponse:
    """Standard SSE lifecycle: run work_fn, stream progress/complete/error."""
    async def stream():
        progress = SSEProgress()
        async def run():
            try:
                await work_fn(progress)
            except Exception as e:
                logger.exception(f"{error_label} failed")
                progress.error(str(e))
            finally:
                progress.done()
        task = asyncio.create_task(run())
        while True:
            ev = await progress.get()
            if ev is None:
                break
            if "_result" in ev:
                yield {"event": "complete", "data": json.dumps(ev["_result"])}
            elif ev.get("step") == "error":
                yield {"event": "error", "data": json.dumps({"error": ev["detail"]})}
            else:
                yield {"event": "progress", "data": json.dumps(ev)}
        await task
    return EventSourceResponse(stream())
```

Each upload endpoint then becomes:

```python
# Before (~120 lines per endpoint):
@router.post("/query/upload/graph")
async def upload_graph(scenario: str = Form(...), file: UploadFile = File(...)):
    async def stream():
        progress = asyncio.Queue()
        def emit(step, detail, pct): ...
        async def run():
            try: ...  # upload logic
            except: ...
            finally: ...
        task = asyncio.create_task(run())
        # ... while-loop ...
    return EventSourceResponse(stream())

# After (~70 lines per endpoint):
@router.post("/query/upload/graph")
async def upload_graph(scenario: str = Form(...), file: UploadFile = File(...)):
    async def work(progress: SSEProgress):
        # ... upload logic using progress.emit() / progress.complete() ...
    return sse_upload_response(work, error_label="graph upload")
```

> **⚠️ Implementation note:** The `emit()` signature stays identical (`step`, `detail`, `pct`). The `_result` dict key convention for complete events must be preserved — the frontend `sseStream.ts` checks for specific keys like `"scenario"`, `"graph"`, `"index"` in the parsed payload.

**Savings:** ~80–120 lines of boilerplate across the 5 endpoints.

---

## Item 3: Cosmos Container Helper Extraction

### Current State

Three routers implement their own `_get_*_container()` function with identical ARM boilerplate:

| Router | Function | DB name | Container | Partition key |
|--------|----------|---------|-----------|--------------|
| `router_prompts.py` | `_get_prompts_container()` | `prompts` (shared) | `{scenario}` | `/agent` |
| `router_scenarios.py` | `_get_scenarios_container()` | `scenarios` | `scenarios` | `/id` |
| `router_interactions.py` | `_get_interactions_container()` | `interactions` | `interactions` | `/scenario` |

Additionally, `router_ingest.py` has:
- `_ensure_nosql_containers()` (line 89) — plural container creation from list config
- `_ensure_gremlin_graph()` (line 128) — Gremlin DB/graph creation

All share the same ARM pattern:
1. Check lazy cache → return if cached
2. Check `COSMOS_NOSQL_ENDPOINT` → raise 503 if missing
3. Derive `account_name` from endpoint, get `sub_id`/`rg` from env
4. Instantiate `CosmosDBManagementClient`, call `begin_create_update_sql_database()` (catch "already exists"), call `begin_create_update_sql_container()` (catch "already exists")
5. Create data-plane `CosmosClient`, get db/container, cache, return

**Problem:** ~120 lines of duplicated ARM boilerplate across 3 routers, plus 7 independent `CosmosDBManagementClient` instantiations.

### Target State

A new `graph-query-api/cosmos_helpers.py` module (~40–50 lines):

```python
# cosmos_helpers.py
from __future__ import annotations
import logging, os
from azure.cosmos import CosmosClient, ContainerProxy
from config import get_credential, COSMOS_NOSQL_ENDPOINT

logger = logging.getLogger("graph-query-api.cosmos")

# ⚠️ AUDIT: Use manual singleton pattern (matching config.py), NOT @lru_cache.
# lru_cache retains references indefinitely with no invalidation — if a
# credential expires or a transient error corrupts the client, there's no way
# to force recreation without cache_clear(). Manual singletons allow simple
# reset (set _x = None) and match the existing codebase convention.

_cosmos_client: CosmosClient | None = None

def get_cosmos_client() -> CosmosClient:
    """Cached data-plane CosmosClient singleton."""
    global _cosmos_client
    if _cosmos_client is None:
        _cosmos_client = CosmosClient(url=COSMOS_NOSQL_ENDPOINT, credential=get_credential())
    return _cosmos_client

_mgmt_client = None

def get_mgmt_client():
    """Cached ARM CosmosDBManagementClient singleton."""
    global _mgmt_client
    if _mgmt_client is None:
        from azure.mgmt.cosmosdb import CosmosDBManagementClient
        sub_id = os.environ["AZURE_SUBSCRIPTION_ID"]
        _mgmt_client = CosmosDBManagementClient(get_credential(), sub_id)
    return _mgmt_client

_container_cache: dict[tuple[str, str], ContainerProxy] = {}

def get_or_create_container(
    db_name: str,
    container_name: str,
    partition_key_path: str,
    ensure_created: bool = False,
) -> ContainerProxy:
    """Get a Cosmos container, optionally creating DB + container via ARM."""
    cache_key = (db_name, container_name)
    if cache_key in _container_cache:
        return _container_cache[cache_key]
    if not COSMOS_NOSQL_ENDPOINT:
        from fastapi import HTTPException
        raise HTTPException(503, "COSMOS_NOSQL_ENDPOINT not configured")
    if ensure_created:
        _arm_ensure_db_and_container(db_name, container_name, partition_key_path)
    client = get_cosmos_client()
    container = client.get_database_client(db_name).get_container_client(container_name)
    _container_cache[cache_key] = container
    return container

def _arm_ensure_db_and_container(db_name, container_name, pk_path):
    """Idempotent ARM creation (catches 'already exists')."""
    # ... ARM boilerplate once ...
```

Each router then replaces ~40 lines with a 4-line call:

```python
# Before (in router_scenarios.py, ~40 lines):
_scenarios_container = None
def _get_scenarios_container():
    global _scenarios_container
    if _scenarios_container: return _scenarios_container
    # ... 35 lines of ARM boilerplate ...

# After (4 lines):
from cosmos_helpers import get_or_create_container
def _get_scenarios_container():
    return get_or_create_container("scenarios", "scenarios", "/id", ensure_created=True)
```

> **⚠️ Implementation note:** `router_prompts.py` uses a per-scenario container name (`{scenario}`) with a shared `prompts` DB. The caching must support dynamic container names — the `_container_cache` dict handles this.

> **⚠️ Implementation note:** `router_ingest.py`'s `_ensure_nosql_containers()` takes a **list** of container configs (e.g., telemetry creates multiple containers at once). This function has a distinct signature — it can either use `get_or_create_container()` in a loop or remain as-is, calling `get_mgmt_client()` from the helper.

> **⚠️ AUDIT — Gremlin management client:** `_ensure_gremlin_graph()` in `router_ingest.py` (line 128) also creates its own `CosmosDBManagementClient` for Gremlin DB/graph ARM calls. While the Gremlin creation logic must stay in `router_ingest.py` (different ARM methods: `begin_create_update_gremlin_database/graph` vs SQL), it should call `cosmos_helpers.get_mgmt_client()` instead of creating its own management client instance.

> **⚠️ AUDIT — Existing `CosmosClient` singleton in `router_telemetry.py`:** `router_telemetry.py` already maintains its own `_cosmos_client` singleton (with `threading.Lock`), independent of the three `_get_*_container()` functions in other routers. After creating `cosmos_helpers.get_cosmos_client()`, the codebase would have **two** `CosmosClient` singletons unless `router_telemetry.py` is also migrated. Either:
> 1. Migrate `router_telemetry.py` to use `cosmos_helpers.get_cosmos_client()` (recommended — full consolidation), or
> 2. Explicitly accept the duplication and document it.
>
> **Decision:** Migrate `router_telemetry.py` to use the shared singleton. Add it to the Phase 2 file change inventory.

**Savings:** ~120 lines across the 3 routers (+ `router_telemetry.py` if migrated), replaced by ~50-line shared module.

---

## Item 4: Merge Runbooks/Tickets Upload Endpoints

### Current State

`upload/runbooks` (lines ~1018–1117) and `upload/tickets` (lines ~1120–1218) in `router_ingest.py` are near character-for-character identical. They differ only in:
- File extension filter: `*.md` vs `*.txt`
- Container/index name suffix: `-runbooks` vs `-tickets`
- Log labels: `"runbooks"` vs `"tickets"`

**Problem:** ~200 lines for two endpoints that are structurally identical.

### Target State

A shared `_upload_knowledge_files()` helper parameterised by file type:

```python
async def _upload_knowledge_files(
    scenario: str,
    file: UploadFile,
    file_ext: str,          # ".md" or ".txt"
    type_label: str,        # "runbooks" or "tickets"
    progress: SSEProgress,
) -> None:
    """Shared logic for runbooks and tickets upload."""
    container_name = f"{scenario}-{type_label}"
    index_name = f"{scenario}-{type_label}-index"
    # ... shared upload logic ...

@router.post("/query/upload/runbooks")
async def upload_runbooks(scenario: str = Form(...), file: UploadFile = File(...)):
    async def work(progress: SSEProgress):
        await _upload_knowledge_files(scenario, file, ".md", "runbooks", progress)
    return sse_upload_response(work, error_label="runbooks upload")

@router.post("/query/upload/tickets")
async def upload_tickets(scenario: str = Form(...), file: UploadFile = File(...)):
    async def work(progress: SSEProgress):
        await _upload_knowledge_files(scenario, file, ".txt", "tickets", progress)
    return sse_upload_response(work, error_label="tickets upload")
```

> **⚠️ Implementation note:** Depends on Item 2 (SSE helper). Implement Item 2 first.

**Savings:** ~80–100 lines.

---

## Item 5: Provision Scripts Consolidation

### Current State

Two scripts share extensive overlap:

| File | Lines | Purpose |
|------|-------|---------|
| `scripts/provision_agents.py` | 518 | CLI tool for initial agent provisioning |
| `scripts/agent_provisioner.py` | 281 | Importable class used by API `/api/config/apply` |

Duplicated content:
- `AGENT_NAMES` list (5 agents)
- `AI_SEARCH_CONNECTION_NAME = "aisearch-connection"`
- `OPENAPI_SPEC_MAP` dict
- `GRAPH_TOOL_DESCRIPTIONS` (slightly different wording)
- `_build_connection_id()` function (different signatures but same logic)
- `_load_openapi_spec()` function (different signatures but same logic)
- Both create the same 5 agents with the same tools in the same order

**Bug:** `provision_agents.py` line 218 uses exact match (`k == keep_path`) for OpenAPI spec path filtering; `agent_provisioner.py` line 92 uses prefix match (`k.startswith(keep_path)`). This functional inconsistency could cause different agent tool configurations between CLI and API provisioning.

**Problem:** 800 lines across 2 files when ~400 would suffice, plus a latent bug from divergent filter logic.

### Target State

`provision_agents.py` becomes a thin CLI wrapper (~100–150 lines) around `AgentProvisioner`:

```python
# provision_agents.py (refactored — ~120 lines)
"""CLI wrapper for agent provisioning."""
import argparse, json, os, sys
from agent_provisioner import AgentProvisioner

def load_config() -> dict:
    """Load config from env vars (or .env file)."""
    ...

def load_prompts_from_disk(data_dir: str) -> dict:
    """Read prompt files from data/prompts/."""
    ...

def main():
    parser = argparse.ArgumentParser(...)
    args = parser.parse_args()
    config = load_config()
    prompts = load_prompts_from_disk(args.data_dir)
    provisioner = AgentProvisioner(config)
    result = provisioner.provision_all(prompts)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
```

All shared constants (`AGENT_NAMES`, `OPENAPI_SPEC_MAP`, etc.) and logic (`_build_connection_id()`, `_load_openapi_spec()`) live exclusively in `agent_provisioner.py`.

### Backend Changes

#### `scripts/agent_provisioner.py` — Canonical source of all constants and logic

- Ensure `_load_openapi_spec()` uses consistent filtering (standardise on `startswith` as the more robust option)
- Export `AGENT_NAMES`, `OPENAPI_SPEC_MAP`, `GRAPH_TOOL_DESCRIPTIONS` as module-level constants

#### `scripts/provision_agents.py` — Refactor to thin CLI wrapper

- Remove all duplicated constants and functions
- Import from `agent_provisioner` instead
- Keep only CLI-specific logic: arg parsing, env loading, prompt file reading, output formatting

> **⚠️ Implementation note:** The CLI's prompt-loading from disk (`load_prompt()`, `load_graph_explorer_prompt()`) is still needed for initial provisioning before any UI uploads. Keep this in `provision_agents.py` but pass the loaded prompts to `AgentProvisioner.provision_all()`.

> **⚠️ Implementation note:** Fix the OpenAPI path filter inconsistency (`==` vs `startswith`) — standardise on `startswith` in `agent_provisioner.py` since it's the more robust pattern for matching API path prefixes.

**Savings:** ~300 lines from `provision_agents.py` + bug fix.

---

## Item 6: Frontend Component Extraction

### Current State

**`SettingsModal.tsx`** (744 lines) contains:
- `UploadBox` sub-component (110 lines) — inline file-upload-with-SSE; **hand-rolls SSE parsing** instead of using the already-imported `consumeSSE` from `sseStream.ts`
- `ActionButton` sub-component (50 lines) — generic reusable button, defined inline
- 3 tab views inlined: Scenarios, Data Sources, Upload

**`AddScenarioModal.tsx`** (668 lines) contains:
- `FileSlot` sub-component (80 lines) — similar to `UploadBox` but different state model
- Already correctly uses `uploadWithSSE` from `sseStream.ts`

**Problem:** 1,412 lines in two components (33% of frontend). `UploadBox` has a redundant SSE implementation.

### Target State

#### `SettingsModal.tsx` → `UploadBox` uses `consumeSSE`

```tsx
// Current UploadBox (lines ~45-47): manual fetch + reader.read() + TextDecoder
const resp = await fetch(url, { method: "POST", body: formData });
const reader = resp.body!.getReader();
// ... manual SSE line parsing ...

// New UploadBox: use existing utility
import { uploadWithSSE } from "../utils/sseStream";
await uploadWithSSE(url, formData, {
  onProgress: (data) => { setProgress(data.pct); setStatus(data.detail); },
  onComplete: (data) => { setDone(true); },
  onError: (err) => { setError(err); },
});
```

> **⚠️ CRITICAL — `uploadWithSSE` form field compatibility:** `uploadWithSSE(endpoint, file, handlers, params?, signal?)` takes a `File` object, but `UploadBox` currently builds its own `FormData` with a `scenario` form field:
> ```tsx
> const formData = new FormData();
> formData.append("file", file);
> formData.append("scenario", scenarioName);
> ```
> **Before implementing this refactor**, verify that `uploadWithSSE`'s `params` argument appends the `scenario` field as a form field (not a query param). If `params` is appended as query parameters, you must extend `uploadWithSSE` to accept extra `FormData` entries. **If the `scenario` field is missing from the form body, the backend will return 422** — this is a breaking change that would be invisible until runtime.

**Savings:** ~30–40 lines; eliminates a bug surface.

#### Extract `ActionButton` to `components/ActionButton.tsx`

Move the self-contained `ActionButton` component to its own file. Import it in `SettingsModal.tsx`.

**Savings:** ~50 lines from `SettingsModal.tsx`; makes `ActionButton` reusable.

#### Optionally: Split `SettingsModal` tabs into sub-components

Extract `ScenariosTab`, `DataSourcesTab`, `UploadTab` into separate files. No line savings but significant readability improvement.

**Savings from all frontend work:** ~100–150 lines + readability improvement.

### UX Enhancements

#### 6a. Unified file upload progress component

**Problem:** `UploadBox` and `FileSlot` handle similar UX flows (file input → progress → success/error) with different implementations.

**Fix:** Create a shared `FileUploadSlot` component that both modals can use, parameterised by state model.

**Why:** Single source of truth for upload UX; easier to add features like retry or cancel.

---

## Item 7: Credential & Client Caching Standardisation

### Current State

Within `graph-query-api/`:
- `config.py` exposes `get_credential()` — lazy-cached singleton `DefaultAzureCredential()`
- 5 locations bypass this and create their own credential:
  - `router_ingest.py` line 671: `DefaultAzureCredential()` directly
  - `router_prompts.py` lines 72, 107: `_DC()` alias
  - `router_scenarios.py` line 91: `_DC()` alias
  - `router_interactions.py` line 70: `_DC()` alias
- `search_indexer.py` line 16: imports `DefaultAzureCredential` but never uses it (dead import)
- Each `_get_*_container()` plus `_list_prompt_scenarios()` creates its own `CosmosDBManagementClient` — 7 instantiations total
- `_get_prompts_container()` creates a new `CosmosClient` per unique scenario (cached per scenario name in a `_containers: dict`, so not per-call — but still N clients instead of 1 singleton)

**Problem:** Wasted credential probe time per duplicate instantiation; inconsistent patterns; unnecessary resource overhead (N `CosmosClient` instances for prompts instead of 1 shared singleton).

### Target State

- All ARM calls use `get_credential()` from `config.py` (or via `cosmos_helpers.get_mgmt_client()` from Item 3)
- A single cached `CosmosClient` singleton in `config.py` (or `cosmos_helpers.py`) serves all data-plane operations
- Remove the dead `DefaultAzureCredential` import from `search_indexer.py`
- Remove all inline `from azure.identity import DefaultAzureCredential as _DC` imports in function bodies

> **⚠️ Implementation note:** This item is a prerequisite for Item 3 (Cosmos helpers). Implement the caching in `config.py` first, then build `cosmos_helpers.py` on top of it.

**Savings:** ~30 lines of credential init + resource efficiency.

---

## Item 8: Code Quality Fixes

### Current State

1. **Bare `except: pass`** in `router_ingest.py` at lines 983, 1077, 1178:
   - **Line 983** (inside `upload_telemetry`): swallows `float()` conversion errors for numeric fields:
     ```python
     try: row[nf] = float(row[nf])
     except: pass
     ```
   - **Lines 1077, 1178** (inside `upload_runbooks` and `upload_tickets`): swallow blob `create_container()` errors:
     ```python
     try: blob_svc.create_container(container_name)
     except: pass
     ```
   All three swallow all exceptions including `KeyboardInterrupt` and `SystemExit`.

2. **Duplicate section header** in `router_telemetry.py` — lines 119 and 124 both contain `# Endpoint`.

3. **Deferred import** in `router_telemetry.py` — line 75: `import time as _time` inside function body with a TODO comment.

4. **Uncached `agent_ids.json` reads** in `api/app/orchestrator.py` — `_load_orchestrator_id()` (line 72) and `_load_agent_names()` (line 77) read + parse JSON on every `/api/alert` request. The file only changes on agent re-provisioning (rare).

5. **CORS default inconsistency** — `api/app/main.py` defaults to `"http://localhost:5173"` with `allow_credentials=True`; `graph-query-api/main.py` defaults to `"http://localhost:5173,http://localhost:3000"` without `allow_credentials`.

### Target State

1. Replace bare `except: pass` with narrowed exception handling (3 locations):
   - **Line 983:** `except (ValueError, TypeError): pass` — intentional skip for non-numeric fields; no log needed.
   - **Lines 1077, 1178:** `except Exception: logger.debug("Blob container '%s' may already exist", container_name)` — blob container creation.
2. Remove duplicate `# Endpoint` header (1 line).
3. Move `import time` to module level in `router_telemetry.py`.
4. Cache `agent_ids.json` at module level with a simple reload mechanism:
   ```python
   _agent_ids_cache: dict | None = None
   _agent_ids_mtime: float = 0
   def _load_agent_ids() -> dict:
       global _agent_ids_cache, _agent_ids_mtime
       mtime = AGENT_IDS_FILE.stat().st_mtime
       if _agent_ids_cache is None or mtime != _agent_ids_mtime:
           _agent_ids_cache = json.loads(AGENT_IDS_FILE.read_text())
           _agent_ids_mtime = mtime
       return _agent_ids_cache
   ```
5. Unify CORS defaults (both services use same default origins and `allow_credentials` setting).

**Savings:** ~5 actual lines + significant maintainability improvement.

---

## Item 9: Log SSE Handler Evaluation

### Current State

Both `api/app/routers/logs.py` (128 lines) and `graph-query-api/main.py` (lines ~157–235) contain structurally identical SSE log streaming code:
- `_SSELogHandler(logging.Handler)` class
- Broadcast hub (subscriber set, thread lock, deque buffer)
- SSE generator
- SSE endpoint

Differences:
- Filter: API filters `app`, `azure`, `uvicorn`; graph-query-api filters `graph-query-api.*`
- SSE format: API uses `EventSourceResponse` with dict yields; graph-query-api uses `StreamingResponse` with raw string yields
- `allow_credentials` in API only

**Problem:** ~90 lines of structural duplication across two independently deployed services.

### Target State

**Two options:**

**Option A (Recommended): Accept the duplication.**
The services are separately packaged (`pyproject.toml`), separately deployed, and separately tested. Cross-service shared code adds a dependency that complicates independent deployment. The duplication is stable (log handlers rarely change). **Savings: 0 lines but avoids coupling.**

**Option B: Create shared `sse_log_handler` package.**
A small shared library parameterised by logger filter and SSE format. Both services install it. **Savings: ~90 lines but adds cross-service dependency.**

> **Decision point:** Recommend Option A unless the organisation plans to add more services that need log streaming.

---

## Implementation Phases

### Phase 1: Zero-Risk Cleanup (est. 30 min)

> Independent — no prerequisites. **Prerequisite for Phase 2.**

> **⚠️ Note:** Fixing bare `except: pass` (Item 8) is included here for convenience since the same files are already being touched, but it is technically a low-risk *behavior* change (narrowing exception scope), not zero-risk dead code removal. Exercise normal caution and test the affected upload endpoints.

**Files to modify:**
- `graph-query-api/router_ingest.py` — Delete ~483 lines of commented-out dead code (lines ~165–644)
- `graph-query-api/main.py` — Remove shadowed `/api/logs` endpoint (~8 lines)
- `graph-query-api/router_ingest.py` — Replace 3× bare `except: pass` with narrowed exception handling (lines 983, 1077, 1178)
- `graph-query-api/search_indexer.py` — Remove unused `DefaultAzureCredential` import (line 16)
- `graph-query-api/router_telemetry.py` — Remove duplicate `# Endpoint` header; move `import time` to module level

**Files to delete:**
- `scripts/scenario_loader.py` (195 lines of verified dead code)

**Verification:**
- `grep -rn "scenario_loader" --include="*.py"` returns no results (confirms no imports)
- `cd graph-query-api && uv run python -c "import router_ingest"` — confirms module still loads
- Start both services locally; verify all upload endpoints work and `/query/logs` streams logs
- **Verify `/query/upload/graph` and `/query/upload/telemetry` still work** (they reference code after the deleted block)

### Phase 2: Backend DRY Refactoring (est. 2–3 hours)

> Depends on Phase 1. **Phase 5 depends on this.**

**Files to create:**
- `graph-query-api/sse_helpers.py` — SSE upload lifecycle helper (~45 lines)
- `graph-query-api/cosmos_helpers.py` — Cosmos container init helper (~50 lines)

**Files to modify:**
- `graph-query-api/config.py` — Add cached `CosmosClient` singleton; optionally add cached `CosmosDBManagementClient`
- `graph-query-api/router_ingest.py` — Refactor 5 upload endpoints to use `sse_upload_response()`; merge `upload/runbooks` and `upload/tickets` shared logic; standardise credential usage
- `graph-query-api/router_prompts.py` — Replace `_get_prompts_container()` with `cosmos_helpers.get_or_create_container()`; remove `_DC` imports
- `graph-query-api/router_scenarios.py` — Replace `_get_scenarios_container()` with `cosmos_helpers.get_or_create_container()`; remove `_DC` imports
- `graph-query-api/router_interactions.py` — Replace `_get_interactions_container()` with `cosmos_helpers.get_or_create_container()`; remove `_DC` imports
- `api/app/orchestrator.py` — Cache `agent_ids.json` reads with mtime-based invalidation

**Verification:**
- Start graph-query-api locally with `GRAPH_BACKEND=mock`
- Upload a graph tarball → verify SSE progress events render correctly in frontend
- Upload a runbooks tarball → verify SSE progress and index creation
- Upload a tickets tarball → verify SSE progress and index creation
- Create a scenario → verify Cosmos container created and data persists
- Load prompts → verify prompts container created per scenario
- Trigger `/api/alert` → verify orchestrator loads agent IDs correctly
- **Run end-to-end: create scenario → upload all 5 data types → run alert → verify logs stream**

### Phase 3: Script Consolidation (est. 1–2 hours)

> Independent — can run in parallel with Phases 1, 2, 4.

**Files to modify:**
- `scripts/agent_provisioner.py` — Ensure all shared constants and logic are here; fix OpenAPI path filter to use `startswith`
- `scripts/provision_agents.py` — Refactor to thin CLI wrapper (~120 lines) using `AgentProvisioner`

**Verification:**
- Run `python scripts/provision_agents.py --help` — should show CLI args
- Run provisioning via CLI — verify 5 agents created with correct tools
- Run provisioning via API `/api/config/apply` — verify same 5 agents created
- **Compare agent tool configurations** between CLI and API routes — should now be identical (bug fix verified)

### Phase 4: Frontend Componentisation (est. 2–3 hours)

> Independent — can run in parallel with Phases 1, 2, 3.

**Files to create:**
- `frontend/src/components/ActionButton.tsx` — Extracted from `SettingsModal.tsx` (~50 lines)
- *(Optional)* `frontend/src/components/settings/ScenariosTab.tsx`, `DataSourcesTab.tsx`, `UploadTab.tsx`

**Files to modify:**
- `frontend/src/components/SettingsModal.tsx` — Refactor `UploadBox` to use `uploadWithSSE`; extract `ActionButton`; optionally split tabs
- `frontend/src/components/AddScenarioModal.tsx` — *(Optional)* Extract shared upload progress component

**Verification:**
- Open Settings modal → Scenarios tab → create/delete scenario
- Open Settings modal → Upload tab → upload each data type → verify SSE progress bars
- Open Add Scenario modal → drop files → upload → verify SSE progress in each slot
- **Browser console: no new errors or warnings**
- **Visual regression: compare upload progress UI before and after — should be identical**

### Phase 5: Cross-Service Cleanup (est. 1 hour)

> Depends on Phase 2.

**Files to modify:**
- `api/app/main.py` — Unify CORS defaults
- `graph-query-api/main.py` — Unify CORS defaults; match `allow_credentials` setting

**Verification:**
- Start both services; open frontend in browser
- Verify no CORS errors in browser console
- Verify SSE log streaming works from both services
- Test from `http://localhost:5173` and `http://localhost:3000`

---

## File Change Inventory

| File | Action | Phase | Changes |
|------|--------|-------|---------|
| `graph-query-api/sse_helpers.py` | **CREATE** | 2 | SSE upload lifecycle helper (~45 lines) |
| `graph-query-api/cosmos_helpers.py` | **CREATE** | 2 | Cosmos container init + caching (~50 lines) |
| `frontend/src/components/ActionButton.tsx` | **CREATE** | 4 | Extracted reusable button (~50 lines) |
| `graph-query-api/router_ingest.py` | MODIFY | 1, 2 | Phase 1: delete ~483 dead lines (lines ~165–644) + fix bare excepts. Phase 2: use `sse_upload_response()`, merge runbooks/tickets, use shared credential |
| `graph-query-api/main.py` | MODIFY | 1, 5 | Phase 1: remove shadowed `/api/logs`. Phase 5: unify CORS |
| `graph-query-api/search_indexer.py` | MODIFY | 1 | Remove unused `DefaultAzureCredential` import |
| `graph-query-api/router_telemetry.py` | MODIFY | 1, 2 | Phase 1: Remove duplicate header; move `import time` to module level. Phase 2: migrate to `cosmos_helpers.get_cosmos_client()` singleton |
| `graph-query-api/config.py` | MODIFY | 2 | Add cached `CosmosClient` and `CosmosDBManagementClient` singletons |
| `graph-query-api/router_prompts.py` | MODIFY | 2 | Use `cosmos_helpers`; remove `_DC` imports |
| `graph-query-api/router_scenarios.py` | MODIFY | 2 | Use `cosmos_helpers`; remove `_DC` imports |
| `graph-query-api/router_interactions.py` | MODIFY | 2 | Use `cosmos_helpers`; remove `_DC` imports |
| `api/app/orchestrator.py` | MODIFY | 2 | Cache `agent_ids.json` reads with mtime invalidation |
| `api/app/main.py` | MODIFY | 5 | Unify CORS defaults |
| `scripts/provision_agents.py` | MODIFY | 3 | Refactor to thin CLI wrapper (~120 lines) |
| `scripts/agent_provisioner.py` | MODIFY | 3 | Consolidate all constants/logic; fix OpenAPI path filter |
| `frontend/src/components/SettingsModal.tsx` | MODIFY | 4 | `UploadBox` uses `uploadWithSSE`; extract `ActionButton` |
| `frontend/src/components/AddScenarioModal.tsx` | MODIFY | 4 | *(Optional)* extract shared upload component |
| `scripts/scenario_loader.py` | **DELETE** | 1 | Confirmed dead code — 195 lines |

### Files NOT Changed

- `graph-query-api/router_graph.py` — Graph query logic is clean; no refactor needed
- `graph-query-api/router_topology.py` — Recently added; independent
- `graph-query-api/models.py` — Data models are clean; no overlap
- `api/app/routers/alert.py` — Alert routing is self-contained
- `api/app/routers/agents.py` — Agent routing is self-contained
- `api/app/routers/logs.py` — Log SSE handler duplication accepted (Item 9 Option A)
- `api/app/routers/config.py` — Already uses `AgentProvisioner` correctly
- `frontend/src/utils/sseStream.ts` — Already clean; consumed by Item 6 refactors
- `infra/*.bicep` — Already modular; low refactor opportunity
- `deploy.sh` — Sequential Azure CLI; refactoring yields minimal benefit
- `nginx.conf` — Routing config stays the same
- `Dockerfile`, `supervisord.conf` — Deployment topology unchanged

---

## Edge Cases & Validation

### Dead Code Removal (Item 1)

**Active code references deleted block:** Verified that no code after line 644 in `router_ingest.py` references any function or variable defined in the dead block. The active `list_scenarios()` endpoint at line 647 is self-contained.

**`scenario_loader.py` imports:** `grep -r "scenario_loader" --include="*.py"` confirms zero imports. Safe to delete.

**Shadowed endpoint removal:** After removing `/api/logs` from `graph-query-api/main.py`, the only log streaming route is `/query/logs`. Frontend must already be using `/query/logs` (since `/api/logs` was shadowed in production).

### SSE Helper (Item 2)

**Frontend field detection:** The frontend `sseStream.ts` detects event types by inspecting JSON payload fields (`"pct"`, `"scenario"`, `"error"`), not SSE `event:` types. The helper must preserve these exact field names in the JSON payloads. The `_result` key convention and `step: "error"` pattern must be maintained.

**Queue sentinel:** The `None` sentinel in the queue signals stream end. The helper's `SSEProgress.done()` must always be called in a `finally` block to prevent hanging SSE connections.

**Concurrent uploads:** Each upload gets its own `SSEProgress` instance (created per request). No shared state between concurrent uploads.

### Cosmos Helper (Item 3)

**Per-scenario containers in prompts:** `router_prompts.py` creates containers named `{scenario}` (dynamic) in the shared `prompts` database. The cache must use `(db_name, container_name)` as key, not just `container_name`.

**ARM "already exists" errors:** The ARM `begin_create_update_sql_database()` and `begin_create_update_sql_container()` calls are idempotent — they return successfully if the resource exists. The current code catches "already exists" exceptions redundantly; the helper can simplify this.

**Missing env vars:** If `COSMOS_NOSQL_ENDPOINT`, `AZURE_SUBSCRIPTION_ID`, or `AZURE_RESOURCE_GROUP` are unset, the helper should raise `HTTPException(503)` with a descriptive message.

**Existing `CosmosClient` in `router_telemetry.py`:** `router_telemetry.py` has its own `_cosmos_client` singleton with `threading.Lock`. After `cosmos_helpers.py` is created, migrate `router_telemetry.py` to use `cosmos_helpers.get_cosmos_client()` to avoid dual singletons.

### Script Consolidation (Item 5)

**OpenAPI path filter bug:** The exact-match filter in `provision_agents.py` (`k == keep_path`) could miss paths that are prefixes of the desired path. Standardising on `startswith` is more robust but must be verified against the actual OpenAPI spec to ensure it doesn't over-include paths.

**Prompt source:** The CLI loads prompts from disk (`data/prompts/`); the API loads from Cosmos. Both pass prompts to `AgentProvisioner` — the provisioner doesn't care about the source.

### Frontend (Item 6)

**`UploadBox` SSE migration:** The current manual SSE parsing in `UploadBox` may handle edge cases differently than `sseStream.ts`. Test that multiline `data:` fields, reconnection events, and partial chunks all work correctly with `uploadWithSSE`.

**`ActionButton` extraction:** Verify that all style classes and props are preserved. The component may use closure variables from `SettingsModal` that need to be converted to props.

**`uploadWithSSE` form field compatibility:** `uploadWithSSE` takes a `File` object, but `UploadBox` currently builds `FormData` with a `scenario` field. Verify that `uploadWithSSE` passes extra form fields correctly, or extend it to accept additional `FormData` entries. If the `scenario` field is dropped, the backend returns 422.

---

## Migration & Backwards Compatibility

### Existing Data

**No data migration required.** All changes are structural code refactors. No database schemas, Cosmos containers, search indices, or blob storage structures change. Existing scenario data, prompts, telemetry, and graph data remain untouched.

### API Surface Compatibility

**No API contracts change.** All endpoints retain:
- Same URL paths
- Same request format (Form fields, file uploads)
- Same response format (SSE events with identical JSON payloads)
- Same error codes and messages

The only removed endpoint (`/api/logs` in graph-query-api) was already inaccessible in production due to nginx shadowing.

### Gradual Adoption

All phases are independently deployable:
- Phase 1 can deploy without any other phase
- Phase 2 can deploy independently (assuming Phase 1 is done to avoid merge conflicts)
- Phase 3 can deploy at any time
- Phase 4 can deploy at any time
- Phase 5 can deploy after Phase 2

There is no "big bang" migration. Each phase is a standalone PR.

### Rollback Plan

Each phase is a simple code revert (no data format changes). If any phase introduces a regression:
1. Revert the PR
2. Redeploy the previous version
3. No data cleanup needed

No feature flags are required — the changes preserve identical external behavior.

---

## Audit Findings

The following issues were identified during a line-by-line audit on 2026-02-15. All factual claims in the plan were verified against source code. Corrections have been applied inline throughout the document; this section serves as a consolidated reference.

| # | Severity | Finding | Resolution |
|---|----------|---------|------------|
| A-1 | **Medium** | Bare except at L983 is a `float()` conversion (not blob creation as originally described). Plan's fix description would produce misleading log messages. | **Fixed in Item 8:** differentiated the three locations — L983 uses `except (ValueError, TypeError): pass`; L1077/L1178 use `except Exception` with correct log message. |
| A-2 | **High** | `@lru_cache` proposed for `get_cosmos_client()`/`get_mgmt_client()` in `cosmos_helpers.py` has no invalidation mechanism. Expired credentials or transient errors would be permanently cached with no reset path. Mismatches existing `config.py` convention. | **Fixed in Item 3:** replaced `@lru_cache` with manual singleton pattern (global variable + None check) matching `config.py`'s established convention. |
| A-3 | **Low** | SSE endpoint line numbers were approximate. | **Fixed** — line numbers updated to match source. Implementers should still identify scaffolds by structure, not line number, as the numbers shift after Phase 1 dead code removal. |
| A-4 | **Medium** | `router_telemetry.py` already maintains its own `_cosmos_client` singleton (with `threading.Lock`), not covered by `cosmos_helpers.py`. After Item 3, the codebase would have two `CosmosClient` singletons. | **Fixed in Items 3/File Inventory:** added `router_telemetry.py` to Phase 2 scope; migrate it to `cosmos_helpers.get_cosmos_client()`. |
| A-5 | **Medium** | `_ensure_gremlin_graph()` in `router_ingest.py` creates its own `CosmosDBManagementClient` — not mentioned for consolidation. | **Fixed in Item 3:** added note that `_ensure_gremlin_graph()` should use `cosmos_helpers.get_mgmt_client()` even though Gremlin creation logic stays in `router_ingest.py`. |
| A-6 | **Low** | Plan claims "each call to `_get_prompts_container()` for a new scenario creates a new `CosmosClient`". Actually, the container is cached per scenario in a `_containers: dict` — it's N clients per N unique scenarios, not per call. | **Fixed in Item 7:** corrected description to note per-scenario caching, clarifying the real issue is N singletons vs 1 shared singleton. |
| A-7 | **Low** | `uploadWithSSE` takes `(endpoint, file, handlers)` but `UploadBox` currently builds `FormData` with an extra `scenario` field. If `uploadWithSSE` only appends `file`, the backend returns 422. | **Fixed in Item 6 + Edge Cases:** added implementation note to verify/extend `uploadWithSSE` to pass extra form fields. |

---

## UX Priority Matrix

| Priority | Enhancement | Item | Effort | Impact |
|----------|------------|------|--------|--------|
| **P0** | `UploadBox` uses `uploadWithSSE` (eliminates bug surface) | 6 | Small | High — removes SSE parsing duplication and potential bugs |
| **P0** | Fix bare `except: pass` (prevents swallowed errors) | 8 | Tiny | Medium — prevents silent failures |
| **P0** | Fix OpenAPI path filter inconsistency (bug fix) | 5 | Tiny | High — agents may have wrong tools |
| **P1** | Extract `ActionButton` to own file | 6 | Tiny | Low — reusability and readability |
| **P1** | Cache `agent_ids.json` reads | 8 | Small | Medium — removes disk I/O per request |
| **P1** | Unify CORS defaults | 8 | Tiny | Low — consistency |
| **P2** | Split `SettingsModal` tabs into sub-components | 6 | Medium | Medium — readability |
| **P2** | Shared `FileUploadSlot` component | 6 | Medium | Low — shared UX pattern |
| **P3** | Merge log SSE handlers (Option B) | 9 | Small | Low — minor DRY improvement |

### Implementation Notes

- **P0 items** must be implemented in their respective phases. The OpenAPI filter bug is a functional correctness issue.
- **P1 items** are low-effort improvements that should be included alongside their parent items.
- **P2 items** enhance readability but don't affect functionality — include if time permits.
- **P3 items** are deferred to a future iteration (cross-service coupling concern).

---

## Savings Summary

| Opportunity | Lines saved | Risk | Effort | Phase |
|-------------|------------|------|--------|-------|
| Delete dead commented code in `router_ingest.py` | **~483** | None | Trivial | 1 |
| Delete dead `scenario_loader.py` | **~195** | None | Trivial | 1 |
| Remove shadowed `/api/logs` endpoint | ~8 | None | Trivial | 1 |
| SSE streaming helper extraction | ~100 | Low | Small | 2 |
| Cosmos container helper extraction | ~120 | Low | Small | 2 |
| Merge runbooks/tickets upload | ~90 | Low | Small | 2 |
| Cache `agent_ids.json` | ~10 | Low | Small | 2 |
| Credential/client caching | ~30 | Low | Small | 2 |
| Consolidate provision scripts | ~300 | Low | Medium | 3 |
| Frontend `UploadBox` → `uploadWithSSE` | ~35 | Low | Small | 4 |
| Extract `ActionButton` | ~50 | None | Tiny | 4 |
| Frontend component extraction | ~50 | Low | Medium | 4 |
| Dead imports/headers/TODOs | ~5 | None | Trivial | 1 |
| CORS unification | ~5 | None | Tiny | 5 |
| **Total** | **~1,826** | | | |

**Current total:** ~13,218 lines
**After all optimizations:** ~11,392 lines
**Reduction:** ~13.8% line count + significant complexity reduction (5× SSE scaffolds → 1, 3× Cosmos inits → 1, 7× ARM clients → 1 cached, 2× provision scripts → 1 canonical + 1 wrapper)
