# V11 Fabric Prep-A — Zero-Risk Foundational Tasks

> **Created:** 2026-02-16
> **Status:** ⬜ Not started
> **Source:** v11fabricv3.md
> **Purpose:** Extract every task from the consolidated plan that is zero-risk,
> foundational, and can be implemented quickly — no behavioral changes to working
> features, no complex logic, no new UI. These unblock everything else.
> **Estimated total effort:** ~3–4 hours

---

## Why These Are Zero Risk

Every task below meets ALL of these criteria:
- **No existing behavior changes** — adds new constants, fixes dead-on-arrival bugs, or adds commented-out template values
- **No UI changes** — backend config / constants / template files only (except two trivial frontend bug fixes)
- **No new dependencies required** (except one pyproject.toml addition that adds no code)
- **Independently testable** — each task can be verified in isolation
- **Fail-safe** — if any task is wrong, the app continues working exactly as before

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

---

### PREP-5: Fix provision URL bug in `useFabricDiscovery.ts` _(from FE-2 / Bug B2)_

**File:** `frontend/src/hooks/useFabricDiscovery.ts` (or equivalent path)
**Effort:** 10 min
**Risk:** Zero — fixes a route that currently 404s every time. Can only improve things.

```typescript
// BEFORE (broken — always 404):
const url = '/api/fabric/provision/pipeline';

// AFTER (correct):
const url = '/api/fabric/provision';
```

---

### PREP-6: Fix discovery response parsing in `useFabricDiscovery.ts` _(from FE-4 / Bug B4)_

**File:** `frontend/src/hooks/useFabricDiscovery.ts` (or equivalent path)
**Effort:** 10 min
**Risk:** Zero — fixes parsing that currently returns empty arrays every time

```typescript
// BEFORE (broken — backend returns flat list, not {items: [...]}):
const items = data.items || [];

// AFTER:
const items = Array.isArray(data) ? data : [];
```

---

### PREP-7: Upload guard for Fabric scenarios _(from A5 / BE-4)_

**File:** `graph-query-api/ingest/graph_ingest.py`
**Effort:** 30 min
**Risk:** Zero — adds a guard for a code path that currently crashes with a 500 error
(`FabricGQLBackend.ingest()` raises `NotImplementedError`). Replaces a 500 with a
clear 400 error message.

When `POST /query/upload/graph` is called for a scenario with
`graph_connector: "fabric-gql"`, return HTTP 400:

> "This scenario uses Fabric for graph data. Graph topology is managed via the
> Fabric provisioning pipeline. Upload telemetry, runbooks, and tickets normally."

This prevents a confusing unhandled exception and gives users a clear explanation.

---

### PREP-8: Add Fabric provision dependencies to `pyproject.toml` _(from B6)_

**File:** `api/pyproject.toml`
**Effort:** 15 min
**Risk:** Zero — adds pip packages. No code uses them until Phase B is implemented.

```toml
"azure-storage-file-datalake>=12.14.0"   # OneLake CSV upload (Lakehouse provisioning)
"azure-kusto-ingest>=4.3.0"              # Eventhouse KQL ingestion
```

Having these installed early means Phase B can focus on logic, not environment setup.

---

## Dependency Graph

```
PREP-1 (env template)         — independent, do anytime
PREP-2 (split CONFIGURED)     — independent, do first (unblocks PREP-4)
PREP-3 (re-add env vars)      — independent, do anytime
PREP-4 (discovery gate)       — depends on PREP-2
PREP-5 (fix provision URL)    — independent, do anytime
PREP-6 (fix discovery parse)  — independent, do anytime
PREP-7 (upload guard)         — independent, do anytime
PREP-8 (add pip deps)         — independent, do anytime
```

Recommended order: PREP-2 → PREP-3 → PREP-4 → PREP-1 → PREP-5 → PREP-6 → PREP-7 → PREP-8

All 8 tasks are independent of each other except PREP-4 depends on PREP-2.
Five of the eight can be done in parallel.

---

## What This Unblocks

After completing all 8 tasks:

| Capability | Before | After |
|---|---|---|
| Fabric discovery (list lakehouses, ontologies, etc.) | Blocked until Graph Model ID set | Works with workspace ID only |
| Provision button | 404s every time | Hits correct endpoint |
| Discovery response parsing | Always returns empty arrays | Returns real resource lists |
| Graph upload to Fabric scenario | 500 unhandled error | Clear 400 with explanation |
| Env template | No Fabric vars documented | Full reference for deployers |
| Config constants for provisioning | Deleted by refactor | Available for Phase B |
| Provision pipeline dependencies | Not installed | Ready for Phase B code |

**This prep work makes Phase A (bug fixes + config) from v11fabricv3.md ~80% complete
and removes all blockers for Phase B (provision pipeline completion).**
