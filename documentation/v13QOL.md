# v13 — QOL / Header & Health UI Improvements

## Overview

Streamline the header area by consolidating the agent bar, health-check bar,
and services popover into a single **Services Panel** — a hierarchical tree
of every discoverable resource, with per-item health checks and Rediscover
buttons for Fabric and Foundry Agents. Add quick-launch buttons for the
Azure AI Foundry and Fabric portals. Add a delete confirmation dialog for
saved interactions. The header shrinks from 3 rows to 1.

---

## 1. Header: "Open Foundry" & "Open Fabric" Buttons

### What
Two new buttons in the header, right-aligned alongside the existing toggles:

| Button | Colour | Link |
|--------|--------|------|
| **Open Foundry** | Dark purple (`#5B21B6` / `bg-purple-800`) | `https://ai.azure.com/` |
| **Open Fabric** | Dark green (`#065F46` / `bg-emerald-800`) | `https://app.fabric.microsoft.com/home?experience=fabric-developer` |

### Deep-link strategy
Both URLs are static — no backend endpoint needed. Hardcode them directly
as `<a target="_blank">` buttons in the header.

### Files to change

| File | Change |
|------|--------|
| `frontend/src/components/Header.tsx` | Add two `<a>` buttons with `target="_blank"` |
| `frontend/src/config/tooltips.ts` | Add tooltip text for each button |

---

## 2. Delete Confirmation on Saved Interactions

### What
When clicking the ✕ on an `InteractionCard`, show a confirmation dialog before
deleting. Currently the delete fires immediately (no confirmation).

### Approach
Add a small inline confirmation or a lightweight modal:

**Option A — Inline confirm (recommended):**  
Replace the ✕ button text with "Delete?" for 3 seconds on first click.
A second click within that window confirms; otherwise it reverts.
No new components needed.

**Option B — Modal:**  
A small centered dialog: "Delete this investigation? This cannot be undone."
with Cancel / Delete buttons.

### Files to change

| File | Change |
|------|--------|
| `frontend/src/components/InteractionSidebar.tsx` | Add confirmation state to `InteractionCard` |

---

## 3. Services Panel (Replaces Health Bar, Agent Bar, and Services Popover)

### Concept

Replace the `HealthButtonBar` (row of 4 health-check buttons), the `AgentBar`
(row of agent pills), and the `ServiceHealthPopover` with a single, prominent
**Services** button in the header. Clicking it opens a panel/popover showing a
**hierarchical tree** of every discoverable resource. Each leaf node is
individually clickable to trigger a health check, with a status indicator
(🟢 green = ok, 🔴 red = fail, 🟠 orange + timer = checking).

### Tree structure

```
Services                                          [▶ Check All]  [✕]
─────────────────────────────────────────────────────────────────
▼ Fabric                                       [🔄 Rediscover]  🟢
    ● Graph (GQL)        — noc-ontology (graph_model_id)   🟢
    ● Eventhouse (KQL)   — noc-eventhouse (kql_db_name)    🟠 3s
    ○ Lakehouse          — NetworkTopologyLH               ─
    ○ Ontology           — noc-ontology                    ─

▼ Foundry Agents                                [🔄 Rediscover]  🟢
    ● Orchestrator                                          🟢
        ↳ delegates to: GraphExplorerAgent, …
    ● GraphExplorerAgent                                    🟢
        ↳ tools: OpenAPI (graph-query-api)
    ● HistoricalTicketAgent                                 🟢
        ↳ tools: AI Search (tickets-index)
    ● RunbookKBAgent                                        🟢
        ↳ tools: AI Search (runbooks-index)
    ● TelemetryAgent                                        🟢
        ↳ tools: OpenAPI (graph-query-api)

▼ Foundry Models                                               🟢
    ● gpt-4.1            — LLM deployment                  🟢
    ● text-embedding-3-small — embedding deployment         🟢

▼ Search Indexes                                               🔴
    ● runbooks-index     — 42 docs                          🟢
    ● tickets-index      — 150 docs                         🔴

▼ Cosmos DB                                                    🟢
    ● interactions       — NoSQL database                   🟢

  ● Graph Query API      — graph-query-api:8100             🟢
  ● Main API             — api:8000                         🟢
```

**Key UI elements:**

- **🔄 Rediscover** buttons appear on **Fabric** and **Foundry Agents**
  category headers only — these are the two resource groups that require
  active discovery (Fabric workspace items via REST API; Foundry agents
  via AI Foundry). Other groups (Models, Search, Cosmos, APIs) don't
  have a discovery step — they're known from config and only need a
  health probe.
- **●** (filled dot) = item is **probeable** — clicking it triggers an
  individual health check.
- **○** (hollow dot / dash) = item is **display-only** — its status is
  derived from the 🔄 Rediscover response. No individual probe exists.
  Clicking it re-runs the parent Rediscover. See "Display-only items"
  below.
- Each **category header** (▼ Fabric, etc.) shows an aggregate dot
  reflecting worst-child status.

#### Display-only items (Lakehouse, Ontology)

The Fabric tree shows **Lakehouse** and **Ontology** as display-only rows
(○ instead of ●) because:

1. **No individual health endpoint exists.** The Fabric REST API can list
   workspace items (confirming they exist), but there's no lightweight
   ping for a Lakehouse or Ontology/GraphModel — you can only confirm
   presence.
2. **The current `rediscover` endpoint doesn't return them.** The
   `FabricConfig` dataclass only has `graph_model_id`,
   `eventhouse_query_uri`, and `kql_db_name`. It doesn't track
   `lakehouse_id` or `ontology_id`.
3. **But the underlying `_list_workspace_items()` DOES see them.** The
   Fabric API returns all workspace items including type `"Lakehouse"`
   and `"GraphModel"`.

**Backend change needed:** Enrich the `POST /query/health/rediscover`
response to include **all discovered workspace items** (not just the ones
`FabricConfig` tracks). Add a `workspace_items` array:

```json
{
  "ok": true,
  "graph_model_id": "...",
  "eventhouse_query_uri": "...",
  "kql_db_name": "...",
  "fabric_ready": true,
  "kql_ready": true,
  "workspace_items": [
    { "id": "abc-123", "type": "Lakehouse",   "displayName": "NetworkTopologyLH" },
    { "id": "def-456", "type": "GraphModel",  "displayName": "noc-ontology" },
    { "id": "ghi-789", "type": "Eventhouse",  "displayName": "noc-eventhouse" },
    { "id": "jkl-012", "type": "KQLDatabase", "displayName": "noc-kqldb" }
  ]
}
```

This is a small change: `_discover_fabric_config()` already calls
`_list_workspace_items()` — just pass the raw item list through to the
endpoint response.

The frontend uses `workspace_items` to populate the Fabric tree. Items
matching `graph_model_id` or `kql_db_name` are shown as probeable (●);
other items (Lakehouse, etc.) are shown as display-only (○) — their
status is "present" (🟢) if they appear in the list, or absent if not.
Clicking a display-only item re-runs 🔄 Rediscover for the whole
Fabric group.

### Behaviour

**Two distinct operations:** The panel supports both **discovery** (finding
what resources exist) and **health checking** (probing whether they're
accessible). These are different:

| | Discovery | Health check |
|---|---|---|
| **Purpose** | Populate the tree — what items exist? | Probe an item — is it reachable? |
| **When** | On first open; on 🔄 Rediscover click | On Check All; on individual item click |
| **Side effect** | Invalidates backend caches, re-queries Fabric/Foundry APIs | None (read-only probes) |
| **Applies to** | Fabric, Foundry Agents (have 🔄 buttons) | All items |

#### Flow on first open

1. **Discovery pass** — fire in parallel:
   - `POST /query/health/rediscover` → returns `FabricConfig` fields +
     `workspace_items[]` (enriched — see "Display-only items" above)
   - `POST /api/agents/rediscover` → returns agent list from AI Foundry
   - `GET /api/services/models` → returns model deployments
   - `GET /api/services/health` → returns Cosmos/Search/Foundry connectivity
2. **Populate tree** — items appear with their names and details. All
   dots start as grey (idle) or green/red based on the discovery response
   (the rediscover endpoints already probe items, so their results count
   as the initial health state).
3. **Check All** (auto or manual) — runs health probes for items that
   didn't get checked during discovery (Models, Search Indexes at
   individual level, Cosmos, APIs).

#### 🔄 Rediscover buttons

- **Fabric 🔄**: Calls `POST /query/health/rediscover`. Invalidates the
  Fabric discovery cache and re-queries the Fabric REST API for workspace
  items. The tree's Fabric children are rebuilt from the response. Use
  after:
  - Resuming a paused Fabric capacity
  - Provisioning new Fabric resources
  - Changing `FABRIC_WORKSPACE_ID` via env config

- **Foundry Agents 🔄**: Calls `POST /api/agents/rediscover`. Invalidates
  the agent cache and re-queries AI Foundry for provisioned agents. The
  tree's Foundry Agents children are rebuilt from the response. Use after:
  - Running the agent provisioner script
  - Deploying/deleting agents in AI Foundry
  - Changing `PROJECT_ENDPOINT` via env config

Both buttons show 🟠 with a timer while running. The response both
populates the tree (discovery) and sets initial health status (the
endpoints probe the resources they discover).

#### Check All

Runs every health check in parallel with a small stagger. Each item's
dot transitions to 🟠 (with elapsed counter) then 🟢 or 🔴. Does **not**
run discovery — uses the already-populated tree.

#### Click any item

Runs that single item's health check. The parent group's dot reflects
the worst child status (any red → parent red, any orange → parent
orange, all green → parent green).

**Exception:** Display-only items (○ Lakehouse, ○ Ontology) don't have
an individual health probe. Clicking them re-runs 🔄 Rediscover for the
parent Fabric group.

#### Auto-refresh on mount (optional, §4i)

Same auto-run logic can trigger the full discovery + Check All on first
open.

#### Close

Click ✕ or click outside the panel. State is preserved — reopening
shows cached results (no re-discovery until user clicks 🔄).

### Data sources per tree node

| Tree node | Discovery (populates tree) | Health check (probes item) | Has 🔄? |
|-----------|---------------------------|---------------------------|---------|
| **Fabric** (group header) | `POST /query/health/rediscover` — returns `FabricConfig` fields + `workspace_items[]` (new) | Aggregate of children | **Yes** |
| **Fabric → Graph (GQL)** | `workspace_items` where `type === 'GraphModel'` + `graph_model_id` | `GET /query/health/sources` → `sources[graph].ok` (actually pings the GQL backend) | — |
| **Fabric → Eventhouse (KQL)** | `workspace_items` where `type === 'KQLDatabase'` + `kql_db_name` | `GET /query/health/sources` → `sources[telemetry].ok` (actually pings KQL) | — |
| **Fabric → Lakehouse** | `workspace_items` where `type === 'Lakehouse'` | **Display-only** — shows 🟢 if item exists in workspace, ─ if absent. No individual probe. | — |
| **Fabric → Ontology** | `workspace_items` where `type === 'GraphModel'` (same as Graph) | **Display-only** — shows 🟢 if `graph_model_id` resolved, ─ if not. No individual probe. | — |
| **Foundry Agents** (group header) | `POST /api/agents/rediscover` — returns agent list from AI Foundry | Aggregate of children | **Yes** |
| **Foundry Agents → each** | Derived from rediscover response | `agent.status === 'provisioned'` | — |
| **Agent sub-items** (tools, delegates) | Derived from agent response | Display-only (no separate check) | — |
| **Foundry Models → each** | `GET /api/services/models` *(new)* | Model accessible, capacity > 0 | No |
| **Search Indexes → each** | `GET /query/health/sources` | `sources[search_indexes.*].ok` | No |
| **Cosmos DB → interactions** | `GET /api/services/health` | Cosmos ping result | No |
| **Graph Query API** | `GET /query/health` *(new — see §3a below)* | `status === 'ok'` | No |
| **Main API** | `GET /health` | `status === 'ok'` | No |

**Note:** The 🔄 Rediscover endpoints (`POST /query/health/rediscover` and
`POST /api/agents/rediscover`) both **discover + probe** in one call. Their
response is used to both populate the tree children and set the initial
health status. Subsequent individual item clicks do read-only health
probes without re-discovery.

### New backend endpoint: `GET /api/services/models`

List deployed model names from AI Foundry. Returns:

```json
{
  "models": [
    { "name": "gpt-4.1", "type": "llm", "status": "ready" },
    { "name": "text-embedding-3-small", "type": "embedding", "status": "ready" }
  ]
}
```

Implementation: uses the Azure AI Foundry client to call `list_deployments()`
(or equivalent). Falls back to env vars `MODEL_DEPLOYMENT_NAME` and
`EMBEDDING_MODEL` if the API call fails.

### Upgrading `GET /api/services/health`

The existing endpoint only checks env var presence (`"configured"`). Upgrade
it to do **real connectivity probes**:

- **AI Foundry:** call list-models or get-project
- **AI Search:** HEAD request to the search endpoint
- **Cosmos DB:** database-level ping (list databases or read metadata)
- **Graph Query API:** `GET /query/health`

Return a richer response:

```json
{
  "services": [
    { "name": "AI Foundry", "status": "connected", "details": "aif-22eeqli26cwru", "latency_ms": 120 },
    { "name": "AI Search",  "status": "connected", "details": "srch-22eeqli26cwru", "latency_ms": 85 },
    { "name": "Cosmos DB",  "status": "connected", "details": "NoSQL interactions store", "latency_ms": 40 },
    { "name": "Graph Query API", "status": "connected", "details": "Fabric GQL", "latency_ms": 15 }
  ],
  "summary": { "total": 4, "connected": 4, "error": 0 }
}
```

#### How `services/health` relates to other tree categories

The Services Panel tree has overlapping concerns with `services/health`.
To be explicit about what each endpoint provides and what part of the tree
uses it:

| `services/health` service | Tree category that uses it | What the tree also checks separately |
|---------------------------|---------------------------|--------------------------------------|
| AI Foundry → "connected" | Not a separate tree node — implicit in whether `services/models` and `agents/rediscover` succeed | **Foundry Models** use `GET /api/services/models` (lists *deployments*); **Foundry Agents** use `POST /api/agents/rediscover` |
| AI Search → "connected" | Not a separate tree node — implicit in whether `query/health/sources` succeeds | **Search Indexes** use `GET /query/health/sources` (probes each *index* individually with doc counts) |
| Cosmos DB → "connected" | **Cosmos DB → interactions** | — |
| Graph Query API → "connected" | **Graph Query API** top-level node | — |

In short:
- `services/health` answers **"can we reach this service at all?"** —
  infrastructure-level connectivity probes.
- The tree's dedicated endpoints answer **"what specific resources exist
  and are they individually healthy?"** — resource-level probes.
- The tree nodes for **Cosmos DB** and **Graph Query API** map 1:1 to
  `services/health` results (no separate resource-level detail needed).
- **Foundry** connectivity (`services/health → AI Foundry`) is consumed
  internally but not shown as a separate tree node — it's implicit in
  whether `services/models` and `agents/rediscover` succeed.
- **AI Search** connectivity (`services/health → AI Search`) is similarly
  implicit — `query/health/sources` probes individual indexes which
  reveals connectivity issues anyway.

### UI: Services button placement

The **⚙ Services** button stays in its current position in the header
(right-aligned, between toggles and theme). Restyle it to be more prominent:

- Slightly larger than other header buttons
- Shows a small aggregate dot (🟢/🟠/🔴) reflecting overall status
  (worst-of-all-children)
- Label: **"⚙ Services"**
- On click: toggles the panel open/closed

```
… Open Foundry  Open Fabric  ⚙ Services ●  👁 Tabs  ☀ Light
```

### UI: Panel component — `ServicesPanel.tsx`

- **Anchored** to the Services button (absolute positioned below it,
  right-aligned so it doesn't overflow the viewport)
- Fixed width ~400px, max-height 80vh, scrollable body
- Dark overlay behind (click-outside to close)
- Tree is rendered using nested `<div>` with indentation — no external
  tree library needed
- Each row: `[status dot] [name] [— detail text] [click to check]`
  - ● (filled) for probeable items; ○ (hollow) for display-only items
- Category headers are collapsible (▼/▶)
- **"Check All"** button at the top-right of the panel header
- **✕** close button at the top-right corner

### What gets removed

| Component | Reason |
|-----------|--------|
| `HealthButtonBar.tsx` | Replaced by Services Panel — all 4 buttons' functionality is now tree nodes |
| `HealthButton` (internal) | Same |
| `AgentBar.tsx` | Agent info now in "Foundry Agents" tree section |
| `AgentCard.tsx` | Agent details now inline in tree |
| `HealthDot.tsx` | Only imported by AgentBar |
| `ServiceHealthPopover.tsx` | Replaced by the new ServicesPanel |

The `Header.tsx` toggles for "Agents" and "Health" are both removed (no
more separate rows to toggle). The "⚙ Services" button stays but now opens
`ServicesPanel` instead of `ServiceHealthPopover`.

### Files to change

| File | Change |
|------|--------|
| **New:** `frontend/src/components/ServicesPanel.tsx` | Full tree-based services panel with per-item health checks |
| `frontend/src/components/Header.tsx` | Remove AgentBar render + toggle; remove HealthButtonBar render + toggle; restyle ⚙ Services button; open `ServicesPanel` instead of `ServiceHealthPopover` |
| `frontend/src/components/HealthButtonBar.tsx` | **Delete file** |
| `frontend/src/components/AgentBar.tsx` | **Delete file** |
| `frontend/src/components/AgentCard.tsx` | **Delete file** |
| `frontend/src/components/HealthDot.tsx` | **Delete file** |
| `frontend/src/components/ServiceHealthPopover.tsx` | **Delete file** |
| `frontend/src/config/tooltips.ts` | Remove `HEALTH_BUTTON_TOOLTIPS`, remove `agents-show`/`agents-hide`/`health-show`/`health-hide`/`services`; add tooltip for the new Services button |
| `api/app/main.py` | Upgrade `services_health` to do real probes; add `GET /api/services/models` endpoint |
| **New:** `api/app/routers/models.py` | (Optional — could live in `main.py` instead) List deployed models from AI Foundry |
| `graph-query-api/router_health.py` | **Add `GET /query/health` liveness endpoint** (see §3a below); **enrich `POST /query/health/rediscover`** to include `workspace_items[]` array (see "Display-only items" above) |
| `graph-query-api/fabric_discovery.py` | Return raw `workspace_items` list from `_discover_fabric_config()` so the endpoint can include it |

---

### 3a. New endpoint: `GET /query/health`

The Services Panel's "Graph Query API" tree node needs to health-check the
graph-query-api service. **This route does not exist.** The graph-query-api
currently has:

- `GET /health` at root (unreachable through nginx — nginx maps `/health`
  to port 8000, the main API)
- `GET /query/health/sources` (requires a `scenario` query param — too
  heavy for a simple liveness check)
- `POST /query/health/rediscover` (wrong method, has side effects)

**Fix — add a lightweight `GET /query/health` to `router_health.py`:**

```python
@router.get("/health")
async def query_health():
    """Simple liveness probe for the graph-query-api behind /query/ nginx prefix."""
    return {"status": "ok", "service": "graph-query-api"}
```

Since `router_health.py` already has `prefix="/query"`, this creates
`GET /query/health` which nginx routes to port 8100 via the existing
`location /query/` block. No nginx changes needed.

> **Also used by v14:** The Admin Panel (v14admin.md) restart overlay
> polls this same endpoint to detect when the graph-query-api is back
> online after an env var change.

---

## Summary: Final Header Layout

### Before (current)
```
┌──────────────────────────────────────────────────────────────────┐
│ ◆ 3IQ Demo — Fabric Graphs + Foundry Agents  [scenario]        │
│                          👁 Agents  👁 Health  👁 Tabs  ⚙ Services  ☀ Light │
├──────────────────────────────────────────────────────────────────┤
│ ● API │ ⬡ Orchestrator │ GraphExplorerAgent │ ...  (AgentBar)   │
├──────────────────────────────────────────────────────────────────┤
│ HEALTH  ● Fabric Sources  ● Fabric Discovery  ● Agent Health  ● Agent Discovery │
└──────────────────────────────────────────────────────────────────┘
```

### After (proposed)
```
┌──────────────────────────────────────────────────────────────────┐
│ ◆ 3IQ Demo — Fabric Graphs + Foundry Agents  [scenario]        │
│      Open Foundry  Open Fabric  ⚙ Services ●  👁 Tabs  ☀ Light │
└──────────────────────────────────────────────────────────────────┘
```

- **1 row** instead of 3 (agent bar + health bar both removed)
- All status info accessible via the Services panel popover
- Services button shows aggregate health dot
- Portal quick-launch buttons in header

---

## Implementation Order

| Step | Task | Complexity |
|------|------|------------|
| 1 | Add "Open Foundry" / "Open Fabric" buttons to `Header.tsx` | Low |
| 2 | Add `GET /query/health` liveness endpoint to `graph-query-api/router_health.py` (§3a) | Low |
| 3 | Enrich `POST /query/health/rediscover` to include `workspace_items[]` array; update `fabric_discovery.py` to surface raw items | Low |
| 4 | Upgrade `GET /api/services/health` to do real connectivity probes | Medium |
| 5 | Add `GET /api/services/models` endpoint | Medium |
| 6 | Implement `ServicesPanel.tsx` (tree, per-item checks, 🔄 Rediscover, Check All, display-only items) | High |
| 7 | Restyle ⚙ Services button; wire it to `ServicesPanel` instead of `ServiceHealthPopover` | Low |
| 8 | Remove `AgentBar`, `AgentCard`, `HealthDot`, `HealthButtonBar`, `ServiceHealthPopover`; remove Agents + Health toggles from `Header.tsx` | Low |
| 9 | Delete confirmation on interaction cards | Low |
| 10 | Update `tooltips.ts` (add new, remove stale) | Low |

---

## 4. Additional UX Improvements

### 4a. Cancel / Stop Investigation Button

**Problem:** Once an investigation starts, the user must wait up to 5 minutes
(the auto-abort timeout) with no way to cancel. The "Investigate" button just
says "Investigating..." and is disabled.

**Fix:** Show a "Stop" button (red, with ■ icon) next to or replacing the
"Investigating..." button while running. Calls `abortRef.current.abort()`.

**Important distinction:** The hook already has `resetInvestigation` which
aborts *and* clears all state (steps, diagnosis, etc.). The new
`cancelInvestigation` should **only abort** — the hook's existing `finally`
block in `submitAlert` already handles setting `running = false`,
`thinking = null`, and computing `runMeta`. Steps completed before the
cancel are preserved automatically because `setSteps([])` is NOT in the
`finally` block. So the implementation is simply:

```typescript
const cancelInvestigation = useCallback(() => {
  abortRef.current?.abort();
}, []);
```

| File | Change |
|------|--------|
| `frontend/src/components/AlertInput.tsx` | Add stop button when `running`; accept `onCancel` prop |
| `frontend/src/hooks/useInvestigation.ts` | Add `cancelInvestigation` (abort-only, unlike `resetInvestigation` which clears state); export it |

---

### 4b. Keyboard Shortcut: Enter to Submit

**Problem:** Users must click the Investigate button — there's no keyboard
shortcut. For a demo, pressing Enter (or Cmd/Ctrl+Enter) to submit is natural.

**Fix:** Add `onKeyDown` handler to the textarea: Ctrl+Enter or Cmd+Enter
submits the alert.

| File | Change |
|------|--------|
| `frontend/src/components/AlertInput.tsx` | Add keydown handler |

---

### 4c. Copy Button on Individual Step Cards

**Problem:** Users can copy the final diagnosis but not individual agent step
responses. During demos, people often want to copy a specific GQL query or
agent response.

**Fix:** Add a small copy icon button (appears on hover) in the expanded
`StepCard` for both Query and Response sections.

| File | Change |
|------|--------|
| `frontend/src/components/StepCard.tsx` | Add copy buttons to query/response blocks |

---

### 4d. Toast / Notification for Auto-Saved Interactions

**Problem:** Interactions are auto-saved silently when an investigation
completes. There's no feedback — the user doesn't know it was saved unless
they notice it in the sidebar.

**Fix:** Show a brief toast notification ("Investigation saved ✓") that
auto-dismisses after 3 seconds. Could use a lightweight toast library or
a simple animated `<div>` at the bottom of the screen.

| File | Change |
|------|--------|
| `frontend/src/App.tsx` | Add toast state, show on save |
| New: `frontend/src/components/Toast.tsx` | Simple auto-dismiss toast |

---

### 4e. Expand/Collapse All Steps

**Problem:** When reviewing a long investigation (5-9 steps), users must
click each `StepCard` individually to expand it. No way to see all details
at once.

**Fix:** Add an "Expand all / Collapse all" toggle above the step timeline.

| File | Change |
|------|--------|
| `frontend/src/components/AgentTimeline.tsx` | Add expand-all toggle, pass state to children |
| `frontend/src/components/StepCard.tsx` | Accept `forceExpanded` prop |

---

### 4f. Search / Filter History

**Problem:** As saved interactions accumulate, there's no way to search or
filter them. The sidebar just shows a chronological list.

**Fix:** Add a small search input at the top of `InteractionSidebar` that
filters by query text. Client-side only — no backend changes.

| File | Change |
|------|--------|
| `frontend/src/components/InteractionSidebar.tsx` | Add filter input + state |

---

### 4g. Log Stream: Clear button + Log level filter

**Problem:** The terminal log streams accumulate indefinitely (capped at 200
lines). No way to clear, and verbose DEBUG logs clutter the view.

**Fix:**
- Add a "Clear" button (🗑) in the log stream header
- Add a log-level filter dropdown (DEBUG / INFO / WARN / ERROR) that hides
  lines below the selected level

| File | Change |
|------|--------|
| `frontend/src/components/LogStream.tsx` | Add clear button + level filter |

---

### 4h. Responsive Error Messages with Suggestions

**Problem:** `ErrorBanner` provides canned explanations for 404/429/400 but
generic text for everything else. Users don't know what to do next.

**Fix:** Expand the error mapping with more HTTP codes and common failure
patterns. Add actionable suggestions (e.g., "Check that Fabric capacity is
resumed" for 503, "Run the Agent Discovery health check" for agent errors).

**Caveat:** `ErrorBanner` currently receives only a `message: string` prop
and matches on `message.includes('404')`, which is fragile. Two
approaches to improve this:

1. **Quick (keep string matching):** Add more `includes()` checks for
   `'503'`, `'502'`, `'timeout'`, `'ECONNREFUSED'`, etc. — good
   enough for a demo.
2. **Better (structured errors):** Pass `{ message, statusCode?, errorType? }`
   from `useInvestigation` instead of a bare string. The `error` SSE event
   already sends `data.message`; the backend could also include a `code`
   field. This is a slightly larger change but more robust.

Recommend option 1 for now, option 2 as a follow-up.

| File | Change |
|------|--------|
| `frontend/src/components/ErrorBanner.tsx` | Expand error mapping; add checks for 502, 503, timeout, ECONNREFUSED |

---

### 4i. Auto-Run Discovery + Health Checks on Panel Open

**Problem:** When the Services Panel opens, the tree is empty and all items
start as grey/idle. The user must click 🔄 Rediscover on each category
and then "Check All" manually. For a demo, you want the tree populated
with green dots immediately.

**Fix:** Auto-trigger the full discovery pass + "Check All" on first open
of the Services Panel. Only on first open — subsequent opens show cached
results and require manual re-check or 🔄.

```tsx
// In ServicesPanel:
const hasAutoRun = useRef(false);
useEffect(() => {
  if (open && !hasAutoRun.current) {
    hasAutoRun.current = true;
    runDiscoveryAndCheckAll();  // discovery first, then health checks
  }
}, [open]);
```

`runDiscoveryAndCheckAll()` fires the two 🔄 endpoints in parallel
(Fabric + Agents), populates the tree from responses, then runs
Check All for the remaining items (Models, Search, Cosmos, APIs).

| File | Change |
|------|--------|
| `frontend/src/components/ServicesPanel.tsx` | Auto-trigger discovery + Check All on first open |

---

### Summary: Additional Implementation Steps

| Step | Task | Complexity |
|------|------|------------|
| 11 | Cancel/stop investigation button | Low |
| 12 | Ctrl+Enter to submit | Low |
| 13 | Expand/collapse all steps (do before step 14 — both touch `StepCard.tsx`; this changes prop interface) | Low |
| 14 | Copy buttons on step cards | Low |
| 15 | Auto-save toast notification | Low |
| 16 | Search/filter interaction history | Low |
| 17 | Log stream clear + level filter | Medium |
| 18 | Better error messages with suggestions | Low |
| 19 | Auto-run discovery + Check All on first Services Panel open | Low |

---

> **Admin Panel** (env var editor + service restart) has been moved to
> **[v14admin.md](v14admin.md)** — it requires auth and hardening work first.
