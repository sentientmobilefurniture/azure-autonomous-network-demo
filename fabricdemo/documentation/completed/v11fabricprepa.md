# V11 Fabric Prep-A — Zero-Risk Foundational Tasks

> **Created:** 2026-02-16
> **Audited:** 2026-02-16 (against actual codebase + post-v11b/v11c state)
> **Implemented:** 2026-02-16
> **Status:** ✅ Complete
> **Source:** v11fabricv3.md
> **Purpose:** Extract every task from the consolidated plan that is zero-risk,
> foundational, and can be implemented quickly — no behavioral changes to working
> features, no complex logic, no new UI. These unblock everything else.
> **Estimated total effort:** ~3–4 hours

---

## Why These Are Zero Risk

Every task below meets ALL of these criteria:
- **No existing behavior changes** — adds new constants, fixes dead-on-arrival bugs, or adds commented-out template values
- **No UI changes** — backend config / constants / template files only (except hook-level frontend bug fixes in `useFabricDiscovery.ts`)
- **No new dependencies required** (except one pyproject.toml addition that adds no code)
- **Independently testable** — each task can be verified in isolation
- **Fail-safe** — if any task is wrong, the app continues working exactly as before

### v11b compatibility

v11b (Terminal Visibility Overhaul) was implemented. **Zero conflicts** with this prep
plan — no overlapping files. Two synergies:
- After PREP-6 (URL fix), Fabric provisioning SSE progress will be visible in the
  always-on Data Ops terminal tab
- After PREP-8 (upload guard), the rejection log will appear in Data Ops via the
  `graph-query-api.ingest` logger

### v11c compatibility

v11c (Data Retrieval Performance Optimisation) was implemented, plus three
post-deployment fixes. **One overlapping file, zero conflicts.**

| v11c change | File | Impact on prep |
|---|---|---|
| Topology TTL cache + `invalidate_topology_cache()` | `ingest/graph_ingest.py` | PREP-8 guard (early return for Fabric) fires BEFORE the cache invalidation call — correct behavior, no data was loaded so nothing to invalidate |
| Scenario list TTL cache + `invalidate_scenarios_cache()` | `router_scenarios.py` | No overlap with any prep task |
| Deduplicate frontend fetches | `useScenarios.ts`, `ScenarioChip.tsx`, etc. | No overlap — `useFabricDiscovery.ts` was not touched |
| Gremlin connection warm-up in lifespan | `backends/cosmosdb.py`, `main.py` | No overlap |

Post-deployment fixes (all confirmed in codebase):

| Fix | File | Impact on prep |
|---|---|---|
| Partition key `/scenario_name` → `/id` | `config_store.py` | No impact — `save_scenario_config()` is called in `graph_ingest.py` BEFORE the PREP-8 guard point, and the partition key change is invisible to the guard logic |
| ARM container existence check before PUT | `cosmos_helpers.py` | No impact — eliminates 31s startup block, no prep tasks touch this file |
| `ScenarioContext` provider value wrapped in `useMemo` | `ScenarioContext.tsx` | No impact — no prep task touches this file |
| `useTopology` abort cleanup | `useTopology.ts` | No impact — no prep task touches this file |

**One gotcha corrected in PREP-8** — see the updated audit note there.

---

## Task List

### PREP-1: Add FABRIC_* vars to `azure_config.env.template` _(from A6 / BE-6)_

**File:** `azure_config.env.template`
**Effort:** 15 min
**Risk:** Zero — template file, commented-out lines, no runtime effect

Currently the template has zero `FABRIC_*` variables. Add the full set so deployments
have a reference for what can be configured:

```env
# -- Microsoft Fabric (optional) -------------------------------------------
# FABRIC_WORKSPACE_ID=                # Fabric workspace GUID
# FABRIC_GRAPH_MODEL_ID=              # Graph Model GUID (auto-set by provisioning)
# FABRIC_API_URL=https://api.fabric.microsoft.com/v1
# FABRIC_SCOPE=https://api.fabric.microsoft.com/.default
# FABRIC_WORKSPACE_NAME=AutonomousNetworkDemo
# FABRIC_CAPACITY_ID=                 # Fabric capacity GUID
# FABRIC_ONTOLOGY_ID=                 # Ontology GUID (auto-set by provisioning)
# FABRIC_ONTOLOGY_NAME=NetworkTopologyOntology
# FABRIC_LAKEHOUSE_NAME=NetworkTopologyLH
# FABRIC_EVENTHOUSE_NAME=NetworkTelemetryEH
# FABRIC_KQL_DB_ID=                   # KQL DB GUID (auto-set by provisioning)
# FABRIC_KQL_DB_NAME=                 # KQL DB name (auto-set)
# EVENTHOUSE_QUERY_URI=               # Eventhouse query endpoint
```

> **Audit note:** Added `FABRIC_API_URL` and `FABRIC_SCOPE` — these already exist in
> `fabric_config.py` with sensible defaults but were missing from the template. Including
> them lets deployers know they can override the API base URL (useful for sovereign clouds).

---

### PREP-2: Split `FABRIC_CONFIGURED` into two lifecycle stages _(from A2 / BE-1)_

**File:** `graph-query-api/adapters/fabric_config.py`
**Effort:** 30 min
**Risk:** Zero — adds two NEW constants, keeps `FABRIC_CONFIGURED` as backward-compat alias

This is the foundational config change that unblocks discovery (PREP-4) and
health (future BE-3). Currently `FABRIC_CONFIGURED = bool(WORKSPACE_ID and GRAPH_MODEL_ID)`
conflates "I can reach the workspace" with "I can execute GQL queries."

```python
FABRIC_WORKSPACE_CONNECTED = bool(os.getenv("FABRIC_WORKSPACE_ID"))
FABRIC_QUERY_READY = bool(
    os.getenv("FABRIC_WORKSPACE_ID") and os.getenv("FABRIC_GRAPH_MODEL_ID")
)
FABRIC_CONFIGURED = FABRIC_QUERY_READY  # backward compat — existing code unaffected
```

No existing code changes behavior because `FABRIC_CONFIGURED` keeps its current value.

---

### PREP-3: Re-add needed Fabric env var constants _(from B0)_

**File:** `graph-query-api/adapters/fabric_config.py`
**Effort:** 15 min
**Risk:** Zero — adds module-level constants with defaults, nothing reads them yet

Refactor #40 correctly deleted unused Fabric env vars. The provision pipeline
(Phase B) will need some of them back. Add them now so they're available:

```python
FABRIC_WORKSPACE_NAME = os.getenv("FABRIC_WORKSPACE_NAME", "AutonomousNetworkDemo")
FABRIC_LAKEHOUSE_NAME = os.getenv("FABRIC_LAKEHOUSE_NAME", "NetworkTopologyLH")
FABRIC_EVENTHOUSE_NAME = os.getenv("FABRIC_EVENTHOUSE_NAME", "NetworkTelemetryEH")
FABRIC_ONTOLOGY_NAME = os.getenv("FABRIC_ONTOLOGY_NAME", "NetworkTopologyOntology")
FABRIC_CAPACITY_ID = os.getenv("FABRIC_CAPACITY_ID", "")
```

These are read-only constants. No code path references them until Phase B is implemented.

---

### PREP-4: Discovery endpoints gate on workspace-only _(from A3 / BE-2)_

**File:** `graph-query-api/router_fabric_discovery.py`
**Effort:** 30 min
**Risk:** Zero — loosens a gate (allows more, breaks nothing). Requires PREP-2.

Change `_fabric_get()` guard from `FABRIC_CONFIGURED` to `FABRIC_WORKSPACE_CONNECTED`.
This fixes the chicken-and-egg problem (Bug B5): currently you can't discover resources
until you have a Graph Model ID, but you need discovery to provision and GET that ID.

GQL query execution (`FabricGQLBackend.execute_query()`) keeps gating on
`FABRIC_QUERY_READY` — no change to query behavior.

> **⚠️ Audit gotcha — import + error message:**
>
> 1. **Import update required.** The current import block in `router_fabric_discovery.py` is:
>    ```python
>    from adapters.fabric_config import (
>        FABRIC_API_URL,
>        FABRIC_SCOPE,
>        FABRIC_WORKSPACE_ID,
>        FABRIC_CONFIGURED,
>    )
>    ```
>    Add `FABRIC_WORKSPACE_CONNECTED` to this import. Keep `FABRIC_CONFIGURED` —
>    it's still used by the `/health` endpoint.
>
> 2. **Error message is wrong after gate change.** The current 503 detail says:
>    `"Set FABRIC_WORKSPACE_ID and FABRIC_GRAPH_MODEL_ID environment variables."`
>    After gating on workspace-only, update to:
>    `"Fabric workspace not configured. Set FABRIC_WORKSPACE_ID environment variable."`

---

### PREP-5: Fix health check bug in `useFabricDiscovery.ts` _(from FE-1 / Bug B1 — was missing from plan)_

**File:** `frontend/src/hooks/useFabricDiscovery.ts`
**Effort:** 10 min
**Risk:** Zero — currently always evaluates to `false`. Can only improve things.

> **⚠️ Audit finding: this task was omitted from the original prep plan.** The plan
> skipped B1 because v11fabricv3.md couples it with BE-3 (richer health endpoint).
> But the fix can be done independently against the current backend response format.

The backend `/query/fabric/health` returns `{configured: bool, workspace_id: str}`.
The frontend checks `data.status === 'ok'` — there is no `status` field, so `healthy`
is **always `false`**.

```typescript
// BEFORE (broken — data.status is always undefined):
setHealthy(data.status === 'ok');
if (data.status !== 'ok') {
  setError(data.error || 'Fabric not configured');
}

// AFTER (matches current backend response):
setHealthy(data.configured === true);
if (!data.configured) {
  setError('Fabric not fully configured');
}
```

When BE-3 (richer health) is implemented later, this will change again to
`data.workspace_connected`, but fixing it now unblocks accurate health display.

---

### PREP-6: Fix provision URL bug in `useFabricDiscovery.ts` _(from FE-2 / Bug B2)_

**File:** `frontend/src/hooks/useFabricDiscovery.ts`
**Effort:** 10 min
**Risk:** Zero — fixes a route that currently 404s every time. Can only improve things.

**Verified against codebase:** Line 142 has `'/api/fabric/provision/pipeline'`. The
backend route is `@router.post("/provision")` on a router with `prefix="/api/fabric"`,
making the correct URL `/api/fabric/provision`.

```typescript
// BEFORE (broken — always 404, line 142):
const res = await fetch('/api/fabric/provision/pipeline', {

// AFTER (correct — matches router prefix + route):
const res = await fetch('/api/fabric/provision', {
```

> **v11b synergy:** After this fix, Fabric provisioning SSE progress events will be
> visible in the persistent Data Ops terminal tab (v11b monitors `app.fabric-provision` logger).

---

### PREP-7: Fix discovery response parsing in `useFabricDiscovery.ts` _(from FE-4 / Bug B4)_

**File:** `frontend/src/hooks/useFabricDiscovery.ts`
**Effort:** 10 min
**Risk:** Zero — fixes parsing that currently returns empty arrays every time

> **⚠️ Audit gotcha — THREE locations, not one.** The `data.items || []` bug appears
> in all three discovery fetch functions. All three must be fixed:

```typescript
// fetchOntologies (line ~89):
// BEFORE: setOntologies(data.items || []);
setOntologies(Array.isArray(data) ? data : []);

// fetchGraphModels (line ~102):
// BEFORE: setGraphModels(data.items || []);
setGraphModels(Array.isArray(data) ? data : []);

// fetchEventhouses (line ~117):
// BEFORE: setEventhouses(data.items || []);
setEventhouses(Array.isArray(data) ? data : []);
```

**Why this is the correct fix:** All three backend endpoints declare
`response_model=list[FabricItem]` — they return a flat JSON array, not a wrapper object.

---

### PREP-8: Upload guard for Fabric scenarios _(from A5 / BE-4)_

**File:** `graph-query-api/ingest/graph_ingest.py`
**Effort:** 30 min
**Risk:** Zero — adds a guard for a code path that currently crashes with a 500 error
(`FabricGQLBackend.ingest()` raises `NotImplementedError`). Replaces a 500 with a
clear 400 error message.

> **⚠️ Audit gotcha #1 — connector detection source matters.**
>
> `graph_ingest.py` calls `get_backend_for_graph(gremlin_graph)` with NO `backend_type`
> argument — it falls back to the **global** `GRAPH_BACKEND` env var. This means:
> - If `GRAPH_BACKEND=cosmosdb` (the common case), uploading a Fabric scenario tarball
>   would try to ingest into Cosmos (wrong, but won't crash)
> - If `GRAPH_BACKEND=fabric-gql`, it crashes with `NotImplementedError`
>
> **The guard must check the uploaded tarball's manifest, NOT the global backend type.**

> **⚠️ Audit gotcha #2 — can't return JSONResponse from inside `work()`.**
>
> The original plan said to return `JSONResponse(status_code=400, ...)`. This is
> **wrong** — the guard runs inside `async def work(progress: SSEProgress):`, which
> is a callback passed to `sse_upload_response()`. The `sse_upload_response` wrapper
> catches ALL exceptions from `work()` via `progress.error(str(e))` and streams them
> as SSE error events. You cannot return an HTTP response from inside `work()`.
>
> **Two correct approaches:**
>
> **Option A (preferred): Raise inside `work()` — let SSE wrapper handle it.**
> The `sse_upload_response` wrapper catches exceptions and calls
> `progress.error(str(e))`, which streams `{"event": "error", "data": ...}` to the
> frontend. The frontend `consumeSSE` already has an `onError` handler.
>
> ```python
> # Inside work(), after manifest is parsed, BEFORE backend.ingest():
> graph_connector = manifest.get("data_sources", {}).get("graph", {}).get("connector", "")
> if graph_connector == "fabric-gql":
>     raise ValueError(
>         "This scenario uses Fabric for graph data. "
>         "Graph topology is managed via the Fabric provisioning pipeline. "
>         "Upload telemetry, runbooks, and tickets normally."
>     )
> ```
>
> **Option B: Check before `sse_upload_response()` — requires pre-reading tarball.**
> Extract `scenario.yaml` before entering the SSE stream to return a proper HTTP 400.
> More correct HTTP semantics but adds complexity. Not recommended for this prep task.

> **⚠️ Audit gotcha #3 (v11c) — file has changed since original plan.**
>
> v11c added `invalidate_topology_cache(gremlin_graph)` at the end of `work()`,
> after `backend.ingest()` completes (line ~185). The PREP-8 guard fires BEFORE
> `backend.ingest()` — if the guard raises, the topology cache invalidation is
> correctly skipped (no data was loaded, nothing to invalidate). No conflict.

> **Safety-net catch** around `backend.ingest()` for the global-override case:
> ```python
> try:
>     result = await backend.ingest(...)
> except NotImplementedError:
>     raise ValueError(
>         "This backend does not support direct graph ingest. "
>         "Use the provisioning pipeline instead."
>     )
> ```

> **v11b synergy:** The rejection will be logged by `graph-query-api.ingest` logger
> and visible in the always-on Data Ops terminal tab.

---

### PREP-9: Add Fabric provision dependencies to `pyproject.toml` _(from B6)_

**File:** `api/pyproject.toml`
**Effort:** 15 min
**Risk:** Zero — adds pip packages. No code uses them until Phase B is implemented.

```toml
"azure-storage-file-datalake>=12.14.0"   # OneLake CSV upload (Lakehouse provisioning)
"azure-kusto-ingest>=4.3.0"              # Eventhouse KQL ingestion
```

Having these installed early means Phase B can focus on logic, not environment setup.

> **⚠️ Audit gotcha — dependency chain.** `azure-kusto-ingest` pulls in
> `azure-kusto-data`, which depends on `msal` and `azure-core`. These *should* be
> compatible since `azure-identity>=1.19.0` is already a dependency, but version
> pinning conflicts are possible.
>
> **Action:** After adding, run `pip install -e . --dry-run` (or `uv pip compile`) to
> verify resolution succeeds before deploying. If conflicts arise, pin
> `azure-kusto-data>=4.3.0` explicitly to control the resolved version.

---

## Dependency Graph

```
PREP-1 (env template)         — independent, do anytime
PREP-2 (split CONFIGURED)     — independent, do first (unblocks PREP-4)
PREP-3 (re-add env vars)      — independent, do anytime
PREP-4 (discovery gate)       — depends on PREP-2
PREP-5 (fix health check)     — independent, do anytime
PREP-6 (fix provision URL)    — independent, do anytime
PREP-7 (fix discovery parse)  — independent, do anytime
PREP-8 (upload guard)         — independent, do anytime
PREP-9 (add pip deps)         — independent, do anytime
```

Recommended order: PREP-2 → PREP-3 → PREP-4 → PREP-1 → PREP-5 → PREP-6 → PREP-7 → PREP-8 → PREP-9

All 9 tasks are independent of each other except PREP-4 depends on PREP-2.
Six of the nine can be done in parallel.

---

## What This Unblocks

After completing all 9 tasks:

| Capability | Before | After |
|---|---|---|
| Fabric health check | Always shows unhealthy (checks missing `status` field) | Correctly reflects `configured` state |
| Fabric discovery (list lakehouses, ontologies, etc.) | Blocked until Graph Model ID set | Works with workspace ID only |
| Provision button | 404s every time | Hits correct endpoint |
| Discovery response parsing | Always returns empty arrays | Returns real resource lists |
| Graph upload to Fabric scenario | 500 unhandled error | Clear 400 with explanation |
| Env template | No Fabric vars documented | Full reference for deployers |
| Config constants for provisioning | Deleted by refactor | Available for Phase B |
| Provision pipeline dependencies | Not installed | Ready for Phase B code |

**This prep work makes Phase A (bug fixes + config) from v11fabricv3.md ~90% complete
and removes all blockers for Phase B (provision pipeline completion).**

---

## Audit Log

| # | Finding | Severity | Resolution |
|---|---------|----------|------------|
| 1 | Health check bug (B1) was omitted — `data.status === 'ok'` always false | **HIGH** | Added as PREP-5 |
| 2 | PREP-4: error message says "Set WORKSPACE_ID and GRAPH_MODEL_ID" but gate only requires workspace | MEDIUM | Added audit note to PREP-4 |
| 3 | PREP-4: import of `FABRIC_WORKSPACE_CONNECTED` not mentioned | MEDIUM | Added audit note to PREP-4 |
| 4 | PREP-7: `data.items \|\| []` bug appears in 3 functions, not 1 | MEDIUM | Updated PREP-7 to list all 3 locations |
| 5 | PREP-8: guard must check manifest connector, not global backend | **HIGH** | Rewrote PREP-8 with manifest check + safety-net catch |
| 6 | PREP-9: `azure-kusto-ingest` has a deep dependency chain | LOW | Added dry-run verification step |
| 7 | PREP-1: `FABRIC_API_URL` and `FABRIC_SCOPE` missing from template | LOW | Added to PREP-1 template block |
| 8 | v11b (Terminal Visibility Overhaul) — no conflicts, synergies noted | INFO | Added header note + per-task synergy notes |
| 9 | **PREP-8: can't return JSONResponse from inside `work()`** — `sse_upload_response` wraps `work()` in a task; exceptions are caught and streamed as SSE error events, not HTTP responses | **HIGH** | Rewrote PREP-8: use `raise ValueError(...)` instead of `return JSONResponse(...)`. Also changed safety-net from `HTTPException` to `ValueError` for same reason. |
| 10 | v11c added `invalidate_topology_cache()` call at end of `work()` in `graph_ingest.py` — PREP-8 guard fires before this point, no conflict | INFO | Added v11c gotcha note to PREP-8 |
| 11 | v11c — no other overlapping files (scenarios cache, frontend dedup, Gremlin warm-up all in separate files) | INFO | Added v11c compatibility section |
| 12 | v11c post-deploy: `config_store.py` partition key changed `/scenario_name` → `/id`, `cosmos_helpers.py` ARM existence check, `ScenarioContext.tsx` useMemo, `useTopology.ts` abort cleanup — zero overlap with any prep task | INFO | Updated v11c compatibility section |
