# V11 Fabric Prep-B — Low-Stakes Immediately Actionable Tasks

> **Created:** 2026-02-16
> **Audited:** 2026-02-16 (against actual codebase + post-v11d state)
> **Status:** 🔲 Not started
> **Source:** v11fabricv3.md (Sections 4, 7, 8)
> **Depends on:** v11fabricprepa.md (✅ complete), v11d.md (✅ complete)
> **Purpose:** Extract every task from the consolidated plan that is low-risk,
> independently testable, and can be implemented right now — no complex logic,
> no multi-system coordination, no new file creation, no breaking changes.
> **Estimated total effort:** ~2 hours

---

## v11d Compatibility

v11d (Agent Bar & Resizable Panels) was implemented. Key changes affecting this plan:

| v11d change | File | Impact on prep-b |
|---|---|---|
| HealthDot removed from header | `Header.tsx` | **P6 ("gear is a junk drawer") is half-resolved** — gear button was already removed by v11d. `Header.tsx` is now 43 lines: title + ScenarioChip + Fabric button + AgentBar + ProvisioningBanner. PREPB-4 (ScenarioChip menu item) unaffected — ScenarioChip itself was NOT touched by v11d. |
| AgentBar replaces health dots | `Header.tsx`, `AgentBar.tsx` (new) | No conflict with any prep-b task. The future ConnectionsDrawer / ServiceHealthSummary (v11fabricv3.md Change 2) will need to account for AgentBar's position in the visual stack: Header → AgentBar → ProvisioningBanner → TabBar → content. |
| Resizable panels + PanelGroups | `App.tsx` | No conflict with any prep-b task. |
| `agent_ids.py` nested iteration fixed | `agent_ids.py` | No overlap. |
| `InteractionSidebar.tsx` sizing simplified | `InteractionSidebar.tsx` | No overlap. |

**Zero conflicts.** All 5 prep-b tasks target files untouched by v11d.

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

**File:** `graph-query-api/router_fabric_discovery.py` (L215–220)
**Effort:** ~15 min
**Risk:** None — additive fields only

**Current state:** The `/query/fabric/health` endpoint (L215–220) returns only 2 fields:
```python
return {
    "configured": FABRIC_CONFIGURED,
    "workspace_id": FABRIC_WORKSPACE_ID,
}
```

**Change:** Expand the response to include lifecycle state fields that the
ConnectionsDrawer (Phase C) will need. The frontend currently checks
`data.configured === true` — this field is preserved as-is, so no breakage.

```python
return {
    "configured": FABRIC_CONFIGURED,
    "workspace_connected": FABRIC_WORKSPACE_CONNECTED,
    "query_ready": FABRIC_QUERY_READY,
    "workspace_id": FABRIC_WORKSPACE_ID or None,
    "graph_model_id": FABRIC_GRAPH_MODEL_ID or None,
}
```

All values come from constants already defined and imported in `fabric_config.py`:
- `FABRIC_WORKSPACE_CONNECTED` — already imported (L28), currently used only in `_fabric_get()` guard (L74)
- `FABRIC_QUERY_READY` — already imported (L29), currently **unused** in this file (⚠ audit finding — this task wires it in)
- `FABRIC_GRAPH_MODEL_ID` — needs to be **added to the import** (L23–29)

**⚠ Gotcha: missing import.** `FABRIC_GRAPH_MODEL_ID` is defined in
`fabric_config.py` (L24) but NOT imported by `router_fabric_discovery.py`.
The import block at L22–29 must be updated:
```python
from adapters.fabric_config import (
    FABRIC_API_URL,
    FABRIC_SCOPE,
    FABRIC_WORKSPACE_ID,
    FABRIC_GRAPH_MODEL_ID,        # ← ADD
    FABRIC_CONFIGURED,
    FABRIC_WORKSPACE_CONNECTED,
    FABRIC_QUERY_READY,
)
```

**Note:** The original prepb spec included `"ontology_id": null` in the response.
This is **not available** — `fabric_config.py` has no `FABRIC_ONTOLOGY_ID` constant
(only the _name_ `FABRIC_ONTOLOGY_NAME`). Drop `ontology_id` from the response.
The ontology ID is only known after provisioning and is not persisted anywhere
currently. It can be added when BE-7 (dynamic config) is implemented.

**Three UI states derive from this (for future ConnectionsDrawer):**
| State | Condition | Display |
|---|---|---|
| Not configured | `workspace_connected === false` | ○ "Not configured" |
| Partially ready | `workspace_connected && !query_ready` | ⚠ "Workspace connected" |
| Connected | `workspace_connected && query_ready` | ● "Connected ✓" |

**Verification:** `GET /query/fabric/health` returns all 5 fields. Existing
frontend health check (`data.configured === true`) still works. `FABRIC_QUERY_READY`
import is no longer unused.

---

### PREPB-2: Add `fetchLakehouses()` to useFabricDiscovery hook (FE-5)

**File:** `frontend/src/hooks/useFabricDiscovery.ts`
**Effort:** ~10 min
**Risk:** None — new state + function, nothing changed

**Current state (verified):** The hook (206 lines) has state for `ontologies`,
`graphModels`, `eventhouses` (L46–48) and fetch functions: `checkHealth` (L60),
`fetchOntologies` (L78), `fetchGraphModels` (L93), `fetchEventhouses` (L108).
The backend endpoint `/query/fabric/lakehouses` exists in
`router_fabric_discovery.py` (L202–207) but the frontend has no corresponding
function.

**Change:** Add `lakehouses` state and `fetchLakehouses()` function, following
the exact same pattern as the existing `fetchEventhouses()` (L108–120):
- `const [lakehouses, setLakehouses] = useState<FabricItem[]>([]);` — after L48
- `fetchLakehouses()` — `GET /query/fabric/lakehouses`, parse with `Array.isArray(data) ? data : []`, set state
- Wire into `fetchAll()` at L169: add to `Promise.all`
- Add `lakehouses` and `fetchLakehouses` to the hook's return object

**⚠ Gotcha: `loadingSection` contention.** All existing fetch functions set
`loadingSection` to track which section is loading (`'ontologies'`, `'eventhouses'`,
etc.). When `fetchAll()` runs them in parallel via `Promise.all`, only the last
one to start "wins" the `loadingSection` state — the others overwrite it. This
is a pre-existing bug (not introduced by this task), but adding more parallel
fetches makes it more visible. **Mitigation:** Don't set `loadingSection` from
`fetchAll()` context. Or accept the cosmetic issue for now — `loadingSection`
is not used in any visible UI currently.

**Verification:** `fetchLakehouses()` callable, populates `lakehouses` state.
`fetchAll()` includes lakehouses in its parallel fetch.

---

### PREPB-3: Add `fetchKqlDatabases()` to useFabricDiscovery hook (FE-6)

**File:** `frontend/src/hooks/useFabricDiscovery.ts`
**Effort:** ~10 min
**Risk:** None — same pattern as PREPB-2

**Change:** Add `kqlDatabases` state and `fetchKqlDatabases()` function:
- `const [kqlDatabases, setKqlDatabases] = useState<FabricItem[]>([]);` — after lakehouses state
- `fetchKqlDatabases()` — `GET /query/fabric/kql-databases`, same parsing pattern
- Wire into `fetchAll()` at L169: add to `Promise.all`
- Add `kqlDatabases` and `fetchKqlDatabases` to the hook's return object

**Same `loadingSection` contention note as PREPB-2.**

**⚠ Gotcha: `fetchAll` dependency array.** The current `fetchAll` at L169 has:
```typescript
const fetchAll = useCallback(async () => {
    await checkHealth();
    await Promise.all([fetchOntologies(), fetchEventhouses()]);
  }, [checkHealth, fetchOntologies, fetchEventhouses]);
```
After PREPB-2 and PREPB-3, this must become:
```typescript
const fetchAll = useCallback(async () => {
    await checkHealth();
    await Promise.all([
      fetchOntologies(),
      fetchEventhouses(),
      fetchLakehouses(),
      fetchKqlDatabases(),
    ]);
  }, [checkHealth, fetchOntologies, fetchEventhouses, fetchLakehouses, fetchKqlDatabases]);
```
Missing any function from the dependency array will cause a React exhaustive-deps
lint warning (or worse, stale closure). Implement PREPB-2 and PREPB-3 together
to update `fetchAll` once.

**Verification:** `fetchKqlDatabases()` callable, populates `kqlDatabases` state.
`fetchAll()` includes KQL databases in its parallel fetch.

---

### PREPB-4: Add "⊞ Manage scenarios…" to ScenarioChip dropdown (C7 partial)

**File:** `frontend/src/components/ScenarioChip.tsx` (after L143)
**Effort:** ~15 min
**Risk:** None — adds a menu item to existing dropdown, no behavior change

**Current state (verified, post-v11d):** ScenarioChip dropdown has: scenario
list (with backend badges — Cosmos/Fabric/Mock), "✦ Custom mode" (L127–134),
"+ New Scenario" (L137–143). v11d did NOT touch this file.

**Change:** Add a divider (`<div className="border-t border-white/10" />`) and
"⊞ Manage scenarios…" menu item after the "+ New Scenario" button (after L143,
before the closing `</div>` of the dropdown container). For now, clicking it
can log to console — the `ScenarioManagerModal` it will open doesn't exist yet
(v11fabricv3.md Phase D). The point is to get the dropdown structure in place
so Phase D just wires the handler.

```tsx
{/* Manage scenarios */}
<div className="border-t border-white/10" />
<button
  onClick={() => {
    setDropdownOpen(false);
    console.log('[ScenarioChip] Manage scenarios — handler not wired yet');
  }}
  className="w-full text-left px-3 py-2 text-sm text-text-secondary hover:bg-white/5 transition-colors"
>
  ⊞ Manage scenarios…
</button>
```

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

**File:** `api/app/routers/fabric_provision.py` (L370–387)
**Effort:** ~10 min
**Risk:** None — adds guard before provisioning, prevents concurrent conflicts

**Current state (verified):** No concurrency protection anywhere in the file
(587 lines). `asyncio` is already imported (L18). The agent provisioning in
`config.py` already has `_provisioning_lock = asyncio.Lock()` (refactor #48)
as the pattern to follow.

**Change:** Add a module-level lock and acquire it in the provision endpoint.
If already locked, return 409 Conflict immediately (not wait — the SSE stream
is long-running and two concurrent streams would create duplicate resources).

Place the lock after the imports, before the helper functions:
```python
# Near top of file, after imports (~line 35)
_fabric_provision_lock = asyncio.Lock()
```

Wrap the provision endpoint handler (L370):
```python
@router.post("/provision")
async def provision_fabric_resources(req: FabricProvisionRequest):
    if _fabric_provision_lock.locked():
        raise HTTPException(
            status_code=409,
            detail="Fabric provisioning already in progress",
        )
    async with _fabric_provision_lock:
        # ... existing body (indented one level deeper)
```

**⚠ Gotcha: SSE StreamingResponse and lock scope.** The current endpoint
returns `StreamingResponse(stream(), ...)`. The `stream()` async generator
runs lazily — the actual provisioning happens when the client reads the
response, NOT when `provision_fabric_resources()` returns. If the lock wraps
only the outer function, it will be released as soon as the StreamingResponse
is returned (before provisioning starts), defeating the purpose.

**Fix:** The lock must be acquired INSIDE the `stream()` generator, not
around it:
```python
@router.post("/provision")
async def provision_fabric_resources(req: FabricProvisionRequest):
    if _fabric_provision_lock.locked():
        raise HTTPException(
            status_code=409,
            detail="Fabric provisioning already in progress",
        )

    workspace_name = req.workspace_name or FABRIC_WORKSPACE_NAME
    # ... other req field reads (unchanged) ...

    async def stream():
        async with _fabric_provision_lock:
            client = AsyncFabricClient()
            try:
                # ... existing provisioning steps (unchanged) ...
            ...

    return StreamingResponse(stream(), media_type="text/event-stream")
```

This way the lock is held for the entire duration of the SSE stream. The
outer `_fabric_provision_lock.locked()` check provides a fast-reject before
even starting the response.

**⚠ Gotcha: race between `.locked()` check and `async with`.** There's a
tiny window where two requests could pass the `.locked()` check before
either enters `async with`. In an asyncio single-threaded event loop, this
can only happen if there's an `await` between the check and the `async with`
— and there isn't (only synchronous assignments). So this is safe. If paranoid,
use `try: _fabric_provision_lock.acquire_nowait()` / `except RuntimeError`
pattern instead, but it's not necessary here.

**Verification:** Sending two concurrent provision requests → second gets 409.
Single request works as before. Lock is held for the full SSE stream duration.

---

## What Is NOT In This Prep (and Why)

| Task | Why deferred | v11d impact |
|---|---|---|
| **C1: Non-blocking startup** (remove overlay) | Touches startup flow + context init. Medium risk — needs careful handling of race where persisted scenario was deleted. | v11d did NOT remove the overlay. App.tsx still has the full-screen `z-[100]` blocker (L96–113), though it's now inside a more complex PanelGroup tree structure. |
| **C6: Update Header** (remove gear, add health + connections) | **Half done by v11d.** Gear and HealthDot already removed. Header is now 43 lines with AgentBar. Future ConnectionsDrawer button (🔌) would go into Header.tsx alongside ScenarioChip. Must coexist with AgentBar's position below the header. |
| **D2: Backend chooser in AddScenarioModal** | Medium complexity — new UI state, integration with `useScenarioUpload` hook, conditional slot disabling. | No v11d impact. |
| **C4: ConnectionsDrawer** | New component (~320 lines), new slide-over panel pattern, depends on BE-3 + BE-5. | No v11d impact, but must account for AgentBar in the visual stack (drawer slides over content, not over AgentBar). |
| **C3: Aggregate services health endpoint (BE-5)** | New route that polls multiple Azure services. Medium complexity, needs health check functions for each service. | No v11d impact. |
| **F1: Dynamic Fabric config (BE-7)** | Config store integration, TTL cache, fallback chain. Medium complexity. | No v11d impact. |
| **B1-B5: Provision pipeline completion** | Large task (~800 lines), porting reference scripts, async adaptation. The biggest single change. | No v11d impact. |
| **D1: ScenarioManagerModal** | New component (~400 lines), composed from existing tab pieces. | No v11d impact. |
| **E3: Delete SettingsModal** | Blocked by ScenarioManagerModal (D1) — can't delete until replacement exists. | No v11d impact. |

---

## Audit Findings

| # | Severity | Task | Finding | Resolution |
|---|----------|------|---------|------------|
| B1 | BUG | PREPB-1 | `FABRIC_GRAPH_MODEL_ID` not imported by `router_fabric_discovery.py` — adding it to the health response without importing it would crash | Add to import block at L22–29 |
| B2 | BUG | PREPB-1 | Original spec included `ontology_id` in response but `FABRIC_ONTOLOGY_ID` doesn't exist in `fabric_config.py` (only `FABRIC_ONTOLOGY_NAME`) | Drop `ontology_id` from response |
| B3 | BUG | PREPB-5 | Lock around `provision_fabric_resources()` outer function would release before SSE stream runs (StreamingResponse is lazy) — no actual concurrency protection | Move lock inside `stream()` generator |
| B4 | NOTE | PREPB-2/3 | `loadingSection` state contention — parallel fetches in `fetchAll()` overwrite each other's loading indicator | Pre-existing cosmetic bug, not introduced by this task, no current UI consumers |
| B5 | NOTE | PREPB-2/3 | `fetchAll` dependency array must include new functions or React will use stale closures | Implement PREPB-2 + PREPB-3 together, update `fetchAll` once |
| B6 | NOTE | PREPB-1 | `FABRIC_QUERY_READY` is imported but unused in `router_fabric_discovery.py` | This task wires it into the response, fixing the unused import |

---

## Implementation Order

All 5 tasks are independent of each other. Any order works.
Suggested: PREPB-1 → PREPB-5 → PREPB-2+3 (together) → PREPB-4
(backend first, then frontend hook, then UI)

PREPB-2 and PREPB-3 should be implemented together to update `fetchAll()`
and its dependency array in one pass.
