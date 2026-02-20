# v14 — Admin Control Panel (Environment Variable Editor)

> **Prerequisite:** Auth and endpoint hardening must be done before this
> feature is implemented. This was originally §8 of v13QOL.md but was
> split out because it requires security work first.

> **Shared dependency:** `GET /query/health` liveness endpoint on the
> graph-query-api must exist before the restart overlay can work. This
> endpoint is created in **v13 §3** (Services Panel) since it's also
> needed there.

---

## What

A **⚙ Admin Panel** button at the **extreme top-right** of the header (after
the theme toggle — rightmost element). Clicking it opens a full-screen modal
that lets the operator view and edit every environment variable from
`azure_config.env`. On save, the container's running environment is updated
and both backend services (main API on `:8000`, Graph Query API on `:8100`)
are restarted so all values — including module-level frozen constants — take
effect.

## Why this is non-trivial

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

## Prerequisites (must be done first)

### 1. Enable `supervisorctl` (socket + RPC config)

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

### 2. Fix `load_dotenv` override in main API

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

### 3. `GET /query/health` endpoint (created in v13)

The restart overlay polls `GET /query/health` to detect when the graph
query API is back online. This endpoint is created as part of v13's
Services Panel work (it's needed there for the "Graph Query API" tree
node health check). See v13QOL.md §3 for details.

### 4. Auth / hardening (TBD)

This endpoint lets anyone rewrite the container's environment and restart
services. Before implementing, add:

- Bearer-token auth or Azure AD validation middleware
- Rate limiting on the POST endpoint
- Audit logging of who changed what

The specific auth approach is TBD and should be designed before
implementation begins.

## Architecture

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

## Backend: new endpoints

### `GET /api/admin/env`

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

### `POST /api/admin/env`

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

### Router file

Create `api/app/routers/admin.py` with both endpoints, mounted at prefix
`/api/admin` in `main.py`.

## Frontend: Admin Panel modal

### Button placement

Add a **⚙ Admin Panel** button as the **last** (rightmost) element in the
header controls row — after the theme toggle:

```
… ⚙ Services ●  👁 Tabs  ☀ Light  ⚙ Admin Panel
```

Use a cog icon (Heroicons `Cog6ToothIcon` or similar). Label text:
"Admin Panel". Style: subtle/outline, matching existing header buttons.

### Modal component: `AdminPanel.tsx`

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

### Confirmation dialog

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

### Post-save: restart overlay

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
- **`GET /query/health` must already exist** (created in v13 §3 for the
  Services Panel) — without it this poll returns 404 even when the
  service is up.
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
- Services Panel should also reflect the new status (auto-refresh)

## Files to change

| File | Change |
|------|--------|
| **`supervisord.conf`** | **Add `[unix_http_server]`, `[rpcinterface:supervisor]`, `[supervisorctl]` sections** — prerequisite, without this `supervisorctl` cannot communicate with supervisord |
| `api/app/paths.py` | Change `load_dotenv(CONFIG_FILE)` → `load_dotenv(CONFIG_FILE, override=True)` — ensures file values win over inherited container env vars |
| `api/app/main.py` | Change `load_dotenv(...)` → `load_dotenv(..., override=True)`; import and mount `admin` router |
| **New:** `api/app/routers/admin.py` | `GET /api/admin/env`, `POST /api/admin/env` endpoints; `Popen(start_new_session=True)` for restart; double-quote all values in file writer; split on first `=` and strip quotes in reader |
| **New:** `frontend/src/components/AdminPanel.tsx` | Admin panel modal + confirmation + restart overlay; handle 502 / network errors in health polling |
| `frontend/src/components/Header.tsx` | Add ⚙ Admin Panel button (rightmost) |
| `frontend/src/config/tooltips.ts` | Add `'admin-panel'` tooltip |
| `nginx.conf` | No change needed — existing `/query/` location block already covers `/query/health`, and `/api/` covers `/api/admin/*` |

## Security note

This endpoint has **no authentication** — it trusts the caller. This is
acceptable for a demo/internal tool running in a private container. For
production, add Bearer-token auth or Azure AD validation middleware.

## Edge cases

| Scenario | Handling |
|----------|----------|
| User clears a required value (e.g., `PROJECT_ENDPOINT=""`) | Allow it — the health checks will surface the problem |
| User adds a new variable not in the original file | Append at end of file under a `# --- Custom ---` group |
| File write fails (disk full, permissions) | Return 500, do not restart services |
| Supervisord restart fails | Background task logs the error; frontend timeout triggers warning |
| User opens admin panel during an active investigation | Show a warning banner at the top of the modal: "An investigation is in progress. Restarting services will abort it." |
| Concurrent admin panel usage | Last-write-wins (no locking needed for a demo) |

## Implementation steps

| # | Task | Notes |
|---|------|-------|
| 1 | Auth / hardening design | **Must be done first** — decide auth approach before implementing |
| 2 | Add `[unix_http_server]` + RPC sections to `supervisord.conf` | Blocks everything else |
| 3 | Change `load_dotenv` to `override=True` in `api/app/paths.py` and `api/app/main.py` | Prerequisite for consistent env var behavior |
| 4 | Implement `api/app/routers/admin.py` with GET + POST endpoints | Use `Popen(start_new_session=True)`, double-quote values, parse `# ---` groups, split on first `=`, strip quotes |
| 5 | Mount admin router in `api/app/main.py` | No CORS change needed (POST is already allowed) |
| 6 | Implement `AdminPanel.tsx` (modal + confirmation + restart overlay) | Handle 502 / network errors in health polling; poll `GET /query/health` (created in v13) |
| 7 | Add Admin Panel button to `Header.tsx` | Rightmost position |
| 8 | End-to-end test in running container | Verify: file written, both services restart, new values visible in GET |
