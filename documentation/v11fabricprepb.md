# V11 Fabric Prep-B — Low-Stakes Immediately Actionable Tasks

> **Created:** 2026-02-16
> **Status:** 🔲 Not started
> **Source:** v11fabricv3.md (Sections 4, 7, 8)
> **Depends on:** v11fabricprepa.md (✅ complete)
> **Purpose:** Extract every task from the consolidated plan that is low-risk,
> independently testable, and can be implemented right now — no complex logic,
> no multi-system coordination, no new file creation, no breaking changes.
> **Estimated total effort:** ~2 hours

---

## Why These Are Low Risk

Every task below meets ALL of these criteria:
- **Purely additive** — adds new fields, functions, or UI items alongside existing ones
- **No existing behavior changes** — current functionality is untouched
- **No new files created** — all edits are to existing files
- **No new dependencies** — uses already-installed packages and existing patterns
- **Backend endpoints already exist** (for frontend tasks) — no plumbing needed
- **Independently testable** — each task can be verified in isolation
- **Fail-safe** — if any task is wrong, the app continues working exactly as before

---

## Tasks

### PREPB-1: Richer Fabric health endpoint (BE-3 / Phase A4)

**File:** `graph-query-api/router_fabric_discovery.py`
**Effort:** ~15 min
**Risk:** None — additive fields only

**Current state:** The `/query/fabric/health` endpoint returns only 2 fields:
```json
{"configured": true, "workspace_id": "abc-123"}
```

**Change:** Expand the response to include lifecycle state fields that the
ConnectionsDrawer (Phase C) will need. The frontend currently checks
`data.configured === true` — this field is preserved as-is, so no breakage.

```json
{
  "configured": true,
  "workspace_connected": true,
  "query_ready": false,
  "workspace_id": "abc-123",
  "graph_model_id": null,
  "ontology_id": null
}
```

All values come from constants already defined in `fabric_config.py`:
- `workspace_connected` → `FABRIC_WORKSPACE_CONNECTED`
- `query_ready` → `FABRIC_QUERY_READY`
- `graph_model_id` → `FABRIC_GRAPH_MODEL_ID or None`

**Three UI states derive from this (for future ConnectionsDrawer):**
| State | Condition | Display |
|---|---|---|
| Not configured | `workspace_connected === false` | ○ "Not configured" |
| Partially ready | `workspace_connected && !query_ready` | ⚠ "Workspace connected" |
| Connected | `workspace_connected && query_ready` | ● "Connected ✓" |

**Verification:** `GET /query/fabric/health` returns all 5 fields. Existing
frontend health check (`data.configured === true`) still works.

---

### PREPB-2: Add `fetchLakehouses()` to useFabricDiscovery hook (FE-5)

**File:** `frontend/src/hooks/useFabricDiscovery.ts`
**Effort:** ~10 min
**Risk:** None — new state + function, nothing changed

**Current state:** The hook has fetch functions for ontologies, graph models,
and eventhouses. The backend endpoints for lakehouses and KQL databases already
exist in `router_fabric_discovery.py` (`/query/fabric/lakehouses`,
`/query/fabric/kql-databases`), but the frontend has no corresponding functions.

**Change:** Add `lakehouses` state and `fetchLakehouses()` function, following
the exact same pattern as the existing `fetchEventhouses()`:
- `lakehouses` state (initially `[]`)
- `fetchLakehouses()` — `GET /query/fabric/lakehouses`, result → state
- Wire into `fetchAll()` alongside existing calls

**Verification:** `fetchLakehouses()` callable, populates `lakehouses` state.
`fetchAll()` includes lakehouses in its parallel fetch.

---

### PREPB-3: Add `fetchKqlDatabases()` to useFabricDiscovery hook (FE-6)

**File:** `frontend/src/hooks/useFabricDiscovery.ts`
**Effort:** ~10 min
**Risk:** None — same pattern as PREPB-2

**Change:** Add `kqlDatabases` state and `fetchKqlDatabases()` function:
- `kqlDatabases` state (initially `[]`)
- `fetchKqlDatabases()` — `GET /query/fabric/kql-databases`, result → state
- Wire into `fetchAll()` alongside existing calls

**Verification:** `fetchKqlDatabases()` callable, populates `kqlDatabases` state.
`fetchAll()` includes KQL databases in its parallel fetch.

---

### PREPB-4: Add "⊞ Manage scenarios…" to ScenarioChip dropdown (C7 partial)

**File:** `frontend/src/components/ScenarioChip.tsx`
**Effort:** ~15 min
**Risk:** None — adds a menu item to existing dropdown, no behavior change

**Current state:** ScenarioChip dropdown has: scenario list, "✦ Custom mode",
"+ New Scenario". Backend badge (Cosmos/Fabric/Mock) already exists.

**Change:** Add a bottom separator and "⊞ Manage scenarios…" menu item after
"+ New Scenario". For now, clicking it can be a no-op or log to console — the
`ScenarioManagerModal` it will open doesn't exist yet (Phase D). The point is
to get the dropdown structure in place so Phase D just wires the handler.

```
┌───────────────────────────────────────┐
│  ● telecom-v3        Cosmos   42v    │
│  ○ fabric-demo       Fabric   18v    │
│ ─────────────────────────────────────│
│  ✦ Custom mode                       │
│  + New Scenario                      │
│ ─────────────────────────────────────│
│  ⊞ Manage scenarios…                 │  ← NEW
└───────────────────────────────────────┘
```

**Verification:** Dropdown renders the new item. Clicking it does not crash.
Existing dropdown items behave identically.

---

### PREPB-5: Add provisioning concurrency lock (B7)

**File:** `api/app/routers/fabric_provision.py`
**Effort:** ~10 min
**Risk:** None — adds guard before provisioning, prevents concurrent conflicts

**Current state:** No concurrency protection. Two simultaneous `POST /api/fabric/provision`
requests could create duplicate resources. The agent provisioning in `config.py`
already has `_provisioning_lock = asyncio.Lock()` (refactor #48) as the pattern.

**Change:** Add a module-level `asyncio.Lock` and acquire it in the main provision
endpoint handler. If already locked, return 409 Conflict immediately.

```python
import asyncio

_fabric_provision_lock = asyncio.Lock()

# In the provision endpoint:
if _fabric_provision_lock.locked():
    raise HTTPException(409, "Fabric provisioning already in progress")
async with _fabric_provision_lock:
    # existing provision logic
    ...
```

**Verification:** Sending two concurrent provision requests → second gets 409.
Single request works as before.

---

## What Is NOT In This Prep (and Why)

| Task | Why deferred |
|---|---|
| **C1: Non-blocking startup** (remove overlay) | Touches startup flow + context init. Medium risk — needs careful handling of race where persisted scenario was deleted. |
| **D2: Backend chooser in AddScenarioModal** | Medium complexity — new UI state, integration with `useScenarioUpload` hook, conditional slot disabling. |
| **C4: ConnectionsDrawer** | New component (~320 lines), new slide-over panel pattern, depends on BE-3 + BE-5. |
| **C3: Aggregate services health endpoint (BE-5)** | New route that polls multiple Azure services. Medium complexity, needs health check functions for each service. |
| **F1: Dynamic Fabric config (BE-7)** | Config store integration, TTL cache, fallback chain. Medium complexity. |
| **B1-B5: Provision pipeline completion** | Large task (~800 lines), porting reference scripts, async adaptation. The biggest single change. |
| **D1: ScenarioManagerModal** | New component (~400 lines), composed from existing tab pieces. |
| **E3: Delete SettingsModal** | Blocked by ScenarioManagerModal (D1) — can't delete until replacement exists. |

---

## Implementation Order

All 5 tasks are independent of each other. Any order works.
Suggested: PREPB-1 → PREPB-5 → PREPB-2 → PREPB-3 → PREPB-4
(backend first, then frontend hook, then UI)
