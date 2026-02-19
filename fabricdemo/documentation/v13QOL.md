# v13 — QOL / Header & Health UI Improvements

## Overview

Streamline the header area by replacing the agent bar and services popover with
richer health-check buttons that show full details on hover. Add quick-launch
buttons for the Azure AI Foundry and Fabric portals. Add a delete confirmation
dialog for saved interactions.

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

## 3. Richer Health Button Tooltips

### Current problem — tooltips are invisible (CSS overflow clip)

The `HealthButtonBar` container has `overflow-x-auto` on a fixed-height
(`h-8` / 32px) wrapper. The tooltip `<div>` is positioned
`absolute left-0 top-full` — meaning it renders *below* the button, outside
the 32px-tall container. CSS spec: when either overflow axis is `auto`,
`scroll`, or `hidden`, the other axis is implicitly treated as `auto` too.
So `overflow-x-auto` forces `overflow-y: auto`, and the tooltip is clipped.

**Fix:** Remove `overflow-x-auto` from the `HealthButtonBar` wrapper (there
are only 4-5 buttons, horizontal overflow is unlikely). If horizontal
scroll is needed in the future, render tooltips via a React portal to
`document.body` instead.

### What we want (once visible)
After a health check completes, hovering the button should show:
- The **static description** (what it does)
- A **divider**
- The **last result details** — the same data that's already fetched

Examples:

**Fabric Sources tooltip after check:**
```
Ping each Fabric data source and report reachability.
────────────────────────────
Last check:
  ● Graph (GQL)     — reachable
  ● Telemetry (KQL) — reachable
  ✗ AI Search: runbooks-index — unreachable
```

**Services tooltip after check (renamed from "Agent Health" — see §6):**
```
Check backend service connectivity.
────────────────────────────
Last check:
  ● AI Foundry       — connected (aif-22eeqli26cwru)
  ● AI Search        — connected (srch-22eeqli26cwru)
  ● Cosmos DB        — connected
  ● Graph Query API  — connected (Fabric GQL)
```

**Agent Discovery tooltip after check:**
```
Re-query AI Foundry for provisioned agents.
────────────────────────────
Last check: 5 agents found
  ● Orchestrator          — provisioned
  ● GraphExplorerAgent    — provisioned
  ● HistoricalTicketAgent — provisioned
  ● RunbookKBAgent        — provisioned
  ● TelemetryAgent        — provisioned
```

### Implementation
Store the full API response in the `HealthButton` component state (already
partially done — `detail` state exists). **The `detail` state is currently
typed as `string`.** It must be changed to `unknown` (or a per-button
response type) so the tooltip renderer can access structured fields
(e.g. `data.services`, `data.agents`). A `detailSummary: string` can be
kept alongside for the inline badge text. Expand the tooltip rendering to
format the response object into a multi-line detail view.

### Backend changes needed
The existing endpoints already return structured data. We may want to enrich:

- `GET /api/services/health` — currently only checks env var presence (reports
  `"configured"` not `"connected"`). Should actually **probe** each service
  with a lightweight call (e.g. list-models for AI Foundry, list-indexes for
  AI Search, database ping for Cosmos, `/health` for Graph Query API).

> **Note:** The existing `agent-health` button already calls
> `/api/services/health`. In §6 below we **rename** this button to
> "Services" rather than adding a duplicate. The tooltip enrichment
> described here applies to that renamed button.

### Files to change

| File | Change |
|------|--------|
| `frontend/src/components/HealthButtonBar.tsx` | Change `detail` state from `string` to `unknown`; add `detailSummary` string for badge; store full response; render structured tooltip |
| `api/app/main.py` | Upgrade `services_health` to do real connectivity probes |

---

## 4. Remove Services Button & Popover

### What
The **⚙ Services** button in the header opens a `ServiceHealthPopover` that
shows the same information the **Services** health button now shows (the
`agent-health` button renamed to `services` per §6). Since we're making
the health button tooltips show full details, the popover is redundant.

### Plan
1. Remove the `⚙ Services` button from `Header.tsx`
2. Delete `ServiceHealthPopover.tsx` (no longer imported anywhere)
3. Remove the `'services'` entry from `HEADER_TOOLTIPS` in `tooltips.ts`
   (not to be confused with the new `'services'` entry in
   `HEALTH_BUTTON_TOOLTIPS`, which stays)

### Files to change

| File | Change |
|------|--------|
| `frontend/src/components/Header.tsx` | Remove Services button, remove `ServiceHealthPopover` import |
| `frontend/src/components/ServiceHealthPopover.tsx` | Delete file |
| `frontend/src/config/tooltips.ts` | Remove `services` tooltip |

---

## 5. Remove Agent Bar (Replaced by Agent Discovery Health Button)

### What
The `AgentBar` (row of agent pills below the header) duplicates information
that the **Agent Discovery** health button now provides via its tooltip.
Remove it to reclaim vertical space.

### What moves where
- Agent names + statuses → shown in the **Agent Discovery** tooltip after a
  check
- API health dot → moves into the health button bar as a new dedicated button
  (see §6)
- Agent detail tooltips (role, model, tools, delegates-to) → shown in the
  Agent Discovery tooltip per-agent

### Plan
1. Remove `{showAgents && <AgentBar />}` from `Header.tsx`
2. Remove the Agents toggle button from the header
3. `AgentBar.tsx` and `AgentCard.tsx` become unused — delete or keep for
   reference (recommend delete)
4. Remove `'agents-show'` / `'agents-hide'` tooltips

### Files to change

| File | Change |
|------|--------|
| `frontend/src/components/Header.tsx` | Remove AgentBar render + toggle; remove `import { AgentBar }` |
| `frontend/src/components/AgentBar.tsx` | Delete file |
| `frontend/src/components/AgentCard.tsx` | Delete file |
| `frontend/src/components/HealthDot.tsx` | Delete file — only imported by `AgentBar.tsx`; becomes orphaned |
| `frontend/src/config/tooltips.ts` | Remove agent toggle tooltips |

---

## 6. Rename "Agent Health" → "Services" (Not a New Button)

### Problem with the original plan

The existing `BUTTONS[]` array already has an `agent-health` entry that
calls `GET /api/services/health`. Adding a **new** `services` entry
pointing to the same endpoint would create two buttons doing the same
thing, and §3's tooltip enrichment would overlap with the new button.

### Fix: rename, don't duplicate

**Rename** the existing `agent-health` button to `services` in the
`BUTTONS[]` array. No new button needed. The enriched tooltip (from §3)
covers everything the proposed "Services" button would show.

```ts
// Before
{ key: 'agent-health', label: 'Agent Health', method: 'GET', url: '/api/services/health' }

// After
{ key: 'services', label: 'Services', method: 'GET', url: '/api/services/health' }
```

The tooltip (powered by §3's enrichment) shows:
```
Check connectivity to all backend services.
────────────────────────────
Last check:
  ● AI Foundry       — connected (aif-22eeqli26cwru)
  ● AI Search        — connected (srch-22eeqli26cwru)
  ● Cosmos DB        — connected
  ● Graph Query API  — connected
```

This replaces both the Services popover **and** the API `HealthDot`
that was in the Agent bar. The health button bar now has **4 buttons**:

| # | Button | Endpoint |
|---|--------|----------|
| 1 | Services | `GET /api/services/health` |
| 2 | Fabric Sources | `GET /query/health/sources` |
| 3 | Fabric Discovery | `POST /query/health/rediscover` |
| 4 | Agent Discovery | `POST /api/agents/rediscover` |

### Files to change

| File | Change |
|------|--------|
| `frontend/src/components/HealthButtonBar.tsx` | Rename `agent-health` → `services` in `BUTTONS[]`; update any `key === 'agent-health'` conditionals in tooltip rendering |
| `frontend/src/config/tooltips.ts` | Rename `HEALTH_BUTTON_TOOLTIPS['agent-health']` → `'services'`; update description text |
| `api/app/main.py` | Upgrade `/api/services/health` to probe services (already covered by §3) |

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
│            Open Foundry  Open Fabric  👁 Health  👁 Tabs  ☀ Light │
├──────────────────────────────────────────────────────────────────┤
│ HEALTH  ● Services  ● Fabric Sources  ● Fabric Discovery       │
│         ● Agent Discovery                                               │
└──────────────────────────────────────────────────────────────────┘
```

- **2 rows** instead of 3 (agent bar removed)
- **4 health buttons** (not 5 — "Agent Health" was renamed to "Services", not duplicated)
- Portal quick-launch buttons in header
- All status info accessible via health button tooltips
- Services popover eliminated (redundant)

---

## Implementation Order

| Step | Task | Complexity |
|------|------|------------|
| 1 | Add "Open Foundry" / "Open Fabric" buttons to `Header.tsx` | Low |
| 2 | Fix `overflow-x-auto` clipping on `HealthButtonBar` | Low |
| 3 | Upgrade `GET /api/services/health` to do real probes | Medium |
| 4 | Change `detail` state from `string` to structured type; store full response; render rich tooltips | Medium |
| 5 | Rename `agent-health` → `services` in `BUTTONS[]` and `tooltips.ts` (NOT a new button — see §6) | Low |
| 6 | Remove `⚙ Services` button + `ServiceHealthPopover` | Low |
| 7 | Remove `AgentBar` + Agents toggle from header | Low |
| 8 | Delete unused components (`AgentBar`, `AgentCard`, `HealthDot`, `ServiceHealthPopover`) | Low |
| 9 | Delete confirmation on interaction cards | Low |
| 10 | Update `tooltips.ts` (add new, remove stale) | Low |

---

## 7. Additional UX Improvements

### 7a. Cancel / Stop Investigation Button

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

### 7b. Keyboard Shortcut: Enter to Submit

**Problem:** Users must click the Investigate button — there's no keyboard
shortcut. For a demo, pressing Enter (or Cmd/Ctrl+Enter) to submit is natural.

**Fix:** Add `onKeyDown` handler to the textarea: Ctrl+Enter or Cmd+Enter
submits the alert.

| File | Change |
|------|--------|
| `frontend/src/components/AlertInput.tsx` | Add keydown handler |

---

### 7c. Copy Button on Individual Step Cards

**Problem:** Users can copy the final diagnosis but not individual agent step
responses. During demos, people often want to copy a specific GQL query or
agent response.

**Fix:** Add a small copy icon button (appears on hover) in the expanded
`StepCard` for both Query and Response sections.

| File | Change |
|------|--------|
| `frontend/src/components/StepCard.tsx` | Add copy buttons to query/response blocks |

---

### 7d. Toast / Notification for Auto-Saved Interactions

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

### 7e. Expand/Collapse All Steps

**Problem:** When reviewing a long investigation (5-9 steps), users must
click each `StepCard` individually to expand it. No way to see all details
at once.

**Fix:** Add an "Expand all / Collapse all" toggle above the step timeline.

| File | Change |
|------|--------|
| `frontend/src/components/AgentTimeline.tsx` | Add expand-all toggle, pass state to children |
| `frontend/src/components/StepCard.tsx` | Accept `forceExpanded` prop |

---

### 7f. Search / Filter History

**Problem:** As saved interactions accumulate, there's no way to search or
filter them. The sidebar just shows a chronological list.

**Fix:** Add a small search input at the top of `InteractionSidebar` that
filters by query text. Client-side only — no backend changes.

| File | Change |
|------|--------|
| `frontend/src/components/InteractionSidebar.tsx` | Add filter input + state |

---

### 7g. Log Stream: Clear button + Log level filter

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

### 7h. Responsive Error Messages with Suggestions

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

### 7i. Auto-Run Health Checks on Page Load

**Problem:** All health buttons start as grey/idle. Users must manually click
each one to see the current status. For a demo, you want green dots on load.

**Fix:** Auto-trigger all health checks once on mount (with a small stagger
to avoid request storms). Only on first load — subsequent checks remain
manual.

**Mechanism:** Each `HealthButton`'s `run()` is internal to the component;
the parent `HealthButtonBar` can't call it. Two clean approaches:

1. **`autoRun` prop (recommended):** Add an `autoRun?: boolean` prop to
   `HealthButton`. When truthy, the component calls `run()` in a
   `useEffect` on mount (with a stagger delay based on its index).
   `HealthButtonBar` passes `autoRun={true}` to each button.
2. **Imperative handle:** Use `useImperativeHandle` + `forwardRef` to
   expose `run()`, then call refs from the parent. More complex than
   needed.

```tsx
// In HealthButton:
useEffect(() => {
  if (autoRun) {
    const id = setTimeout(run, index * 300); // stagger by 300ms
    return () => clearTimeout(id);
  }
}, []); // eslint-disable-line react-hooks/exhaustive-deps
```

| File | Change |
|------|--------|
| `frontend/src/components/HealthButtonBar.tsx` | Add `useEffect` auto-run on mount |

---

### Summary: Additional Implementation Steps

| Step | Task | Complexity |
|------|------|------------|
| 11 | Cancel/stop investigation button | Low |
| 12 | Ctrl+Enter to submit | Low |
| 13 | Expand/collapse all steps (do before step 14 — both touch `StepCard.tsx`; this one changes prop interface) | Low |
| 14 | Copy buttons on step cards | Low |
| 15 | Auto-save toast notification | Low |
| 16 | Search/filter interaction history | Low |
| 17 | Log stream clear + level filter | Medium |
| 18 | Better error messages with suggestions | Low |
| 19 | Auto-run health checks on page load | Low |
| 20 | Admin Panel — env var editor + service restart | Medium |

---

## 8. Admin Control Panel (Environment Variable Editor)

### What

A **⚙ Admin Panel** button at the **extreme top-right** of the header (after
the theme toggle — rightmost element). Clicking it opens a full-screen modal
that lets the operator view and edit every environment variable from
`azure_config.env`. On save, the container's running environment is updated
and both backend services (main API on `:8000`, Graph Query API on `:8100`)
are restarted so all values — including module-level frozen constants — take
effect.

### Why this is non-trivial

Both Python services load env vars via `load_dotenv()` at startup. Some vars
are captured into **module-level constants** at import time (frozen):

| Service | Frozen vars (examples) |
|---------|------------------------|
| Main API (`api/`) | `SCENARIO_NAME`, `CORS_ORIGINS`, `SCENARIO_CONFIG`, agent YAML manifest |
| Graph Query API (`graph-query-api/`) | `GRAPH_BACKEND`, `TOPOLOGY_SOURCE`, `SCENARIO_NAME`, `DEFAULT_GRAPH`, `DATA_SOURCES` |

Other vars are read dynamically via `os.getenv()` per-request (e.g.,
`PROJECT_ENDPOINT`, `AI_SEARCH_NAME`, `FABRIC_WORKSPACE_ID`). Simply
mutating `os.environ` at runtime would update the dynamic reads but **not**
the frozen constants. Therefore a full process restart via supervisord is
required after writing changes to disk.

### Prerequisites (must be done first)

#### 1. Enable `supervisorctl` (socket + RPC config)

The current `supervisord.conf` has **no `[unix_http_server]` or
`[rpcinterface:supervisor]` section**. Without these, supervisord does not
create a control socket and `supervisorctl` exits with a connection error.
The Dockerfile runs our custom conf exclusively
(`supervisord -c /etc/supervisor/conf.d/supervisord.conf`), so the OS
defaults are not loaded.

**Add to `supervisord.conf`:**

```ini
[unix_http_server]
file=/var/run/supervisor.sock

[rpcinterface:supervisor]
supervisor.rpcinterface_factory = supervisor.rpcinterface:make_main_rpcinterface

[supervisorctl]
serverurl=unix:///var/run/supervisor.sock
```

#### 2. Fix `load_dotenv` override in main API

After supervisord restarts both services, the new processes inherit
**supervisord's environment**, which includes container-platform env vars
injected by Azure Container Apps (via Bicep `env:` blocks).

Graph Query API already uses `load_dotenv(_config, override=True)` — file
values win over inherited env vars. But the main API uses the default
`override=False` in both `paths.py` and `main.py`, meaning **inherited env
vars (even empty ones) silently take precedence** over the admin panel's
new file values.

**Fix — change both calls to `override=True`:**

```python
# api/app/paths.py
load_dotenv(CONFIG_FILE, override=True)

# api/app/main.py
load_dotenv(..., override=True)
```

This makes the env file the single source of truth for both services.

#### 3. Add `GET /query/health` endpoint to graph-query-api

The restart overlay polls `GET /query/health` to detect when the graph
query API is back online. **This route does not exist.** The graph-query-api
has:

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

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Frontend (Admin Panel modal)                               │
│                                                             │
│  1. GET /api/admin/env           → populate form            │
│  2. POST /api/admin/env {vars}   → save + restart           │
│  3. Poll GET /health & /query/health until both return 200  │
│     (treat 502 / network errors as "still restarting")      │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  Main API  (POST /api/admin/env handler)                    │
│                                                             │
│  1. Validate payload (all values must be strings)           │
│  2. Write key="value" pairs to /app/azure_config.env        │
│     (double-quote all values to handle =, #, spaces)        │
│  3. Return 200  { status: "saved", message: "Restarting…" } │
│  4. Background task — fire-and-forget detached restart:     │
│     subprocess.Popen(                                       │
│       ["sh", "-c",                                          │
│        "sleep 1 && supervisorctl restart                     │
│         graph-query-api api"],                               │
│       start_new_session=True)                                │
│     → detached shell survives the API's own death            │
│     → restarts graph-query-api first, then api               │
│     → new processes call load_dotenv(override=True)          │
└─────────────────────────────────────────────────────────────┘
```

**Why `POST` not `PUT`:** The main API's CORS middleware only allows
`["GET", "POST", "OPTIONS"]`. A `PUT` request would be blocked by the
browser's CORS preflight. Using `POST` avoids touching CORS config.

**Why `Popen` with `start_new_session=True`:**
`supervisorctl restart api graph-query-api` sends two sequential XML-RPC
calls. The first (`restart api`) kills the very process that spawned the
command. The child `supervisorctl` process dies too, and the second restart
request for `graph-query-api` is **never sent**. By using a detached shell
process (`start_new_session=True`), the shell outlives the API process.
Restarting `graph-query-api` first (while the API is still alive) ensures
both commands are delivered. The `sleep 1` is inside the shell, so the
Python handler returns instantly and the HTTP response flushes normally.

### Backend: new endpoints

#### `GET /api/admin/env`

Reads `/app/azure_config.env` **from disk** (not `os.environ`) and returns
the full list of variables with their comment-section groupings preserved.

**Response shape:**

```json
{
  "variables": [
    { "key": "DEFAULT_SCENARIO",        "value": "telecom-playground",  "group": "Scenario" },
    { "key": "AZURE_SUBSCRIPTION_ID",   "value": "67255afe-…",         "group": "Core Azure" },
    { "key": "AI_FOUNDRY_NAME",         "value": "aif-22eeqli26cwru",  "group": "AI Foundry" },
    ...
  ]
}
```

Grouping is derived from the `# --- Group Name ---` comment lines already
present in the env file. **Note:** actual headers include parenthetical
details, e.g. `# --- Core Azure settings (AUTO: populated by postprovision) ---`.
The parser regex should capture only the group name portion and strip the
parenthetical, or include it — either is fine for display. A regex like
`r'^# --- (.+?) ---'` will work for both forms.

The parser should:

1. Read the file line by line
2. Track the current group from `# --- … ---` headers
3. Skip pure-comment lines and blank lines (a line starting with `#` is
   always a comment — never parse `# GRAPH_BACKEND=fabric-gql` as a var)
4. For each `KEY=VALUE` line, split on the **first** `=` only
5. Strip surrounding quotes (`"` / `'`) from the value
6. Emit `{ key, value, group }` for each parsed line

#### `POST /api/admin/env`

**Request body:**

```json
{
  "variables": [
    { "key": "DEFAULT_SCENARIO",      "value": "telecom-playground" },
    { "key": "AZURE_SUBSCRIPTION_ID", "value": "67255afe-…" },
    ...
  ]
}
```

**Behaviour:**

1. Validate: every entry must have a non-empty `key` (string) and a `value`
   (string, may be empty).
2. Re-read the existing env file to preserve comment structure and group
   headers. For each `KEY=VALUE` line, replace the value if the key appears
   in the payload; leave comment lines and group headers intact. Append any
   new keys (not already in the file) at the end.
3. **Double-quote all values** in the written file to handle `=`, `#`,
   spaces, and other special characters safely:
   ```python
   line = f'{key}="{value}"'
   ```
   `load_dotenv` parses double-quoted values correctly (strips quotes,
   respects `#` inside quotes).
4. Write the updated file atomically (write to a temp file in the same
   directory, then `os.rename()`).
5. Return `200 { "status": "saved", "message": "Services restarting…" }`.
6. Schedule a **fire-and-forget** background task:

```python
import subprocess

def _schedule_restart():
    """Spawn a detached process that outlives the API."""
    subprocess.Popen(
        ["sh", "-c",
         "sleep 1 && supervisorctl restart graph-query-api api"],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
```

The restart order is `graph-query-api` then `api` — this ensures both
restart commands are sent before the API process is killed.

**Error handling:**

- `400` if payload is malformed
- `500` if file write fails (roll back to previous file)

#### Router file

Create `api/app/routers/admin.py` with both endpoints, mounted at prefix
`/api/admin` in `main.py`.

### Frontend: Admin Panel modal

#### Button placement

Add a **⚙ Admin Panel** button as the **last** (rightmost) element in the
header controls row — after the theme toggle:

```
… 👁 Health  👁 Tabs  ☀ Light  ⚙ Admin Panel
```

Use a cog icon (Heroicons `Cog6ToothIcon` or similar). Label text:
"Admin Panel". Style: subtle/outline, matching existing header buttons.

#### Modal component: `AdminPanel.tsx`

**Layout:**

```
┌────────────────────────────────────────────────────────────────┐
│  ⚙ Admin Panel — Environment Variables              [ ✕ ]     │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌─ Scenario ──────────────────────────────────────────────┐   │
│  │ DEFAULT_SCENARIO        [ telecom-playground         ]  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                │
│  ┌─ Core Azure ────────────────────────────────────────────┐   │
│  │ AZURE_SUBSCRIPTION_ID   [ 67255afe-8670-…            ]  │   │
│  │ AZURE_RESOURCE_GROUP    [ rg-fabricgraph              ]  │   │
│  │ AZURE_LOCATION          [ swedencentral               ]  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                │
│  ┌─ AI Foundry ────────────────────────────────────────────┐   │
│  │ AI_FOUNDRY_NAME         [ aif-22eeqli26cwru           ]  │   │
│  │ AI_FOUNDRY_ENDPOINT     [ https://aif-22eeq…          ]  │   │
│  │ …                                                       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                │
│  … (scrollable — all groups from azure_config.env) …           │
│                                                                │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              [ Cancel ]    [ 💾 Save Changes ]          │   │
│  └─────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────┘
```

- Full-screen modal with dark overlay, scrollable body
- Variables grouped by their `group` field (collapsible sections)
- Each variable: label (key name, monospace) + text input (value)
- Keys are **read-only** (cannot rename env vars from the UI)
- Values are editable
- Highlight changed values (yellow/amber border on modified fields)
- Cancel dismisses without saving
- Save triggers the confirmation flow

#### Confirmation dialog

When the user clicks **Save Changes**, show a centered confirmation modal
**on top of** the admin panel:

```
┌────────────────────────────────────────────────────┐
│  ⚠  Confirm Environment Change                    │
│                                                    │
│  You are about to update X environment variables.  │
│                                                    │
│  Warning: Changing these values will restart both  │
│  the main API and Graph Query API. Services will   │
│  be temporarily unavailable (~5–10 seconds).       │
│  Incorrect values may cause services to fail.      │
│                                                    │
│  Changed variables:                                │
│    • AI_FOUNDRY_NAME: aif-old… → aif-new…          │
│    • DEFAULT_SCENARIO: telecom… → energy…           │
│                                                    │
│         [ Cancel ]       [ ⚠ Save & Restart ]      │
└────────────────────────────────────────────────────┘
```

- Lists only the **changed** variables (diff)
- Red/warning-coloured "Save & Restart" button
- Cancel returns to the editor

#### Post-save: restart overlay

After POST returns 200, show a non-dismissible overlay:

```
┌────────────────────────────────────────┐
│                                        │
│     ⟳  Restarting services…            │
│                                        │
│     Waiting for API and Graph Query    │
│     API to come back online.           │
│                                        │
│     ● Main API        … waiting       │
│     ● Graph Query API … waiting       │
│                                        │
└────────────────────────────────────────┘
```

- Poll `GET /health` (main API) and `GET /query/health` (Graph Query API)
  every 2 seconds
- **`GET /query/health` must be created first** (see prerequisite §8.3
  above) — without it this poll returns 404 even when the service is up.
- **Treat any non-2xx response (including 502 Bad Gateway from nginx) and
  network/fetch errors as "still restarting"** — not as a fatal error.
  During the restart window nginx is up but the backends are down, so
  nginx returns 502 for proxied routes.
  ```typescript
  const isUp = async (url: string) => {
    try {
      const r = await fetch(url);
      return r.ok;   // true only for 2xx
    } catch {
      return false;  // network error, CORS error, etc.
    }
  };
  ```
- Update each line to "✓ online" when the respective endpoint returns 200
- When **both** are online, auto-dismiss the overlay and close the admin
  panel
- After 30 seconds with no response, show a warning: "Services are taking
  longer than expected. Check the container logs."
- Health button bar should also reflect the new status (auto-refresh)

### Files to change

| File | Change |
|------|--------|
| **`supervisord.conf`** | **Add `[unix_http_server]`, `[rpcinterface:supervisor]`, `[supervisorctl]` sections** — prerequisite, without this `supervisorctl` cannot communicate with supervisord |
| `api/app/paths.py` | Change `load_dotenv(CONFIG_FILE)` → `load_dotenv(CONFIG_FILE, override=True)` — ensures file values win over inherited container env vars |
| `api/app/main.py` | Change `load_dotenv(...)` → `load_dotenv(..., override=True)`; import and mount `admin` router |
| `graph-query-api/router_health.py` | **Add `GET /query/health` liveness endpoint** — prerequisite; without it the restart overlay polls a non-existent route and always sees 404 |
| **New:** `api/app/routers/admin.py` | `GET /api/admin/env`, `POST /api/admin/env` endpoints; `Popen(start_new_session=True)` for restart; double-quote all values in file writer; split on first `=` and strip quotes in reader |
| **New:** `frontend/src/components/AdminPanel.tsx` | Admin panel modal + confirmation + restart overlay; handle 502 / network errors in health polling |
| `frontend/src/components/Header.tsx` | Add ⚙ Admin Panel button (rightmost) |
| `frontend/src/config/tooltips.ts` | Add `'admin-panel'` tooltip |
| `nginx.conf` | No change needed — existing `/query/` location block already covers `/query/health`, and `/api/` covers `/api/admin/*` |

### Security note

This endpoint has **no authentication** — it trusts the caller. This is
acceptable for a demo/internal tool running in a private container. For
production, add Bearer-token auth or Azure AD validation middleware.

### Edge cases

| Scenario | Handling |
|----------|----------|
| User clears a required value (e.g., `PROJECT_ENDPOINT=""`) | Allow it — the health checks will surface the problem |
| User adds a new variable not in the original file | Append at end of file under a `# --- Custom ---` group |
| File write fails (disk full, permissions) | Return 500, do not restart services |
| Supervisord restart fails | Background task logs the error; frontend timeout triggers warning |
| User opens admin panel during an active investigation | Show a warning banner at the top of the modal: "An investigation is in progress. Restarting services will abort it." |
| Concurrent admin panel usage | Last-write-wins (no locking needed for a demo) |

### Updated header layout (final)

```
┌──────────────────────────────────────────────────────────────────────────┐
│ ◆ 3IQ Demo — Fabric Graphs + Foundry Agents  [scenario]                │
│      Open Foundry  Open Fabric  👁 Health  👁 Tabs  ☀ Light  ⚙ Admin Panel │
├──────────────────────────────────────────────────────────────────────────┤
│ HEALTH  ● Services  ● Fabric Sources  ● Fabric Discovery               │
│         ● Agent Discovery                                               │
└──────────────────────────────────────────────────────────────────────────┘
```

### Implementation steps

| # | Task | Notes |
|---|------|-------|
| 20a | Add `[unix_http_server]` + RPC sections to `supervisord.conf` | **Must be done first** — blocks everything else |
| 20b | Change `load_dotenv` to `override=True` in `api/app/paths.py` and `api/app/main.py` | Prerequisite for consistent env var behavior |
| 20c | Add `GET /query/health` liveness endpoint to `graph-query-api/router_health.py` | **Must be done before 20e** — restart overlay polls this route |
| 20d | Implement `api/app/routers/admin.py` with GET + POST endpoints | Use `Popen(start_new_session=True)`, double-quote values, parse `# ---` groups, split on first `=`, strip quotes |
| 20e | Mount admin router in `api/app/main.py` | No CORS change needed (POST is already allowed) |
| 20f | Implement `AdminPanel.tsx` (modal + confirmation + restart overlay) | Handle 502 / network errors in health polling; poll `GET /query/health` (not `/health` which is the main API) |
| 20g | Add Admin Panel button to `Header.tsx` | Rightmost position |
| 20h | End-to-end test in running container | Verify: file written, both services restart, new values visible in GET |
