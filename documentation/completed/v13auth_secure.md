# v13 — Security Assessment: Environment Variable & Config Exposure

> **Purpose:** Enumerate all threat surfaces where environment variables,
> Azure resource identifiers, endpoints, or internal configuration could be
> exposed to unauthorized viewers. This document is a living recon artifact —
> each pass adds newly discovered vectors. Future-risk items (from planned
> features in `v13QOL.md`) are marked with 🔮.
>
> **Scope:** The fabricdemo application — frontend, backend APIs, infra,
> deploy scripts, and planned features.
>
> **Key mitigating factor:** No actual secrets (API keys, connection strings,
> passwords) are embedded anywhere today. The architecture uses Azure Managed
> Identity throughout. The `azure_config.env` file contains only endpoints,
> resource names, and IDs — not credentials. However, these values enable
> **reconnaissance** (identifying specific Azure resources for targeted
> attacks) and may become more sensitive as features are added.

---

## Table of Contents

1. [Threat Surface Summary Matrix](#1-threat-surface-summary-matrix)
2. [CRITICAL — Live Log Streams (SSE)](#2-critical--live-log-streams-sse)
3. [CRITICAL — `/api/config/resources` Endpoint](#3-critical--apiconfigresources-endpoint)
4. [CRITICAL — No Authentication on Any Endpoint](#4-critical--no-authentication-on-any-endpoint)
5. [HIGH — `/api/services/health` Leaks Resource Names](#5-high--apiserviceshealth-leaks-resource-names)
6. [HIGH — Unfiltered Exception Messages in Responses](#6-high--unfiltered-exception-messages-in-responses)
7. [HIGH — `azure_config.env` Baked into Docker Image](#7-high--azure_configenv-baked-into-docker-image)
8. [MEDIUM — Resource Tooltips Render Raw Env Vars](#8-medium--resource-tooltips-render-raw-env-vars)
9. [MEDIUM — Error Banner Renders Raw Backend Errors](#9-medium--error-banner-renders-raw-backend-errors)
10. [MEDIUM — Orchestrator Exception Passthrough (SSE)](#10-medium--orchestrator-exception-passthrough-sse)
11. [MEDIUM — Container Env Vars Visible in Azure Portal](#11-medium--container-env-vars-visible-in-azure-portal)
12. [MEDIUM — Deploy/Hook Scripts Echo Values to Logs](#12-medium--deployhook-scripts-echo-values-to-logs)
13. [LOW — Scenario Config Exposes Index & Graph Names](#13-low--scenario-config-exposes-index--graph-names)
14. [LOW — Agent Metadata Reveals Architecture](#14-low--agent-metadata-reveals-architecture)
15. [LOW — Browser DevTools Console Logging](#15-low--browser-devtools-console-logging)
16. [LOW — nginx Fingerprinting & Missing Headers](#16-low--nginx-fingerprinting--missing-headers)
17. [🔮 FUTURE — Admin Panel (v13QOL §8)](#17--future--admin-panel-v13qol-8)
18. [🔮 FUTURE — Enriched Health Tooltips (v13QOL §3)](#18--future--enriched-health-tooltips-v13qol-3)
19. [🔮 FUTURE — Log Stream Clear & Level Filter (v13QOL §7g)](#19--future--log-stream-clear--level-filter-v13qol-7g)
20. [🔮 FUTURE — Auto-Run Health Checks (v13QOL §7i)](#20--future--auto-run-health-checks-v13qol-7i)
21. [🔮 FUTURE — Copy Buttons on Step Cards (v13QOL §7c)](#21--future--copy-buttons-on-step-cards-v13qol-7c)
22. [Env Var Classification](#22-env-var-classification)
23. [Full Endpoint Inventory](#23-full-endpoint-inventory)
24. [Network Tab Exposure Map](#24-network-tab-exposure-map)

---

## 1. Threat Surface Summary Matrix

| # | Surface | Severity | Status | Affected Layer | Exposed Data |
|---|---------|----------|--------|----------------|--------------|
| 2 | SSE log streams (`/api/logs`, `/query/logs`) | **CRITICAL** | Current | Backend → Frontend | Any logged env var, endpoint, traceback, request body |
| 3 | `/api/config/resources` endpoint | **CRITICAL** | Current | Backend API | `COSMOS_NOSQL_ENDPOINT`, `AZURE_SEARCH_ENDPOINT`, `AI_FOUNDRY_NAME`, `STORAGE_ACCOUNT_NAME`, `FABRIC_WORKSPACE_ID` |
| 4 | No authentication anywhere | **CRITICAL** | Current | All layers | All endpoints fully open |
| 5 | `/api/services/health` response | **HIGH** | Current | Backend API | `AI_FOUNDRY_NAME`, `AI_SEARCH_NAME` |
| 6 | Raw exception messages in responses | **HIGH** | Current | Graph Query API | Connection details, SDK internals |
| 7 | Config file in Docker image layer | **HIGH** | Current | Build/Deploy | All `azure_config.env` values |
| 8 | `ResourceTooltip` renders `node.meta` | **MEDIUM** | Current | Frontend | Cosmos endpoint, Search endpoint, Foundry project |
| 9 | `ErrorBanner` renders raw error text | **MEDIUM** | Current | Frontend | Backend error messages (truncated to 200 chars) |
| 10 | Orchestrator SSE error events | **MEDIUM** | Current | Backend → Frontend | Azure SDK exception messages |
| 11 | Portal-visible container env vars | **MEDIUM** | Current | Infra (Bicep) | All env vars in plaintext |
| 12 | Deploy scripts echo values | **MEDIUM** | Current | CI/CD | Env var values in build logs |
| 13 | Scenario config API | **LOW** | Current | Backend API | Index names, graph model name |
| 14 | Agent metadata in tooltips | **LOW** | Current | Frontend | Model names, tool specs, agent graph |
| 15 | `console.error` in frontend | **LOW** | Current | Browser DevTools | Error objects, raw SSE data |
| 16 | nginx fingerprinting | **LOW** | Current | nginx | Server version, default error pages |
| 17 | 🔮 Admin Panel | **CRITICAL** | Planned | New feature | **ALL env vars** — full read/write |
| 18 | 🔮 Enriched health tooltips | **MEDIUM** | Planned | Frontend | Service connection details in DOM |
| 19 | 🔮 Log level filter | **LOW** | Planned | Frontend | Doesn't remove data, just hides it client-side |
| 20 | 🔮 Auto-run health checks | **LOW** | Planned | Frontend | Auto-fetches env-containing responses on load |
| 21 | 🔮 Copy buttons on step cards | **LOW** | Planned | Frontend | Makes agent responses (which may contain infra data) one-click copyable |

---

## 2. CRITICAL — Live Log Streams (SSE)

### What

Three SSE endpoints stream raw Python log output to the browser in real time:

| Endpoint | Service | Logger filter |
|----------|---------|---------------|
| `GET /api/logs` | Main API | `app`, `api`, `azure`, `uvicorn` |
| `GET /query/logs` | Graph Query API | `app`, `graph-query-api`, `azure`, `uvicorn` |
| `GET /query/logs/data-ops` | Graph Query API | Data operations |

### How it works

- `log_broadcaster.py` installs a custom `logging.Handler` that buffers log
  records and broadcasts them via `asyncio.Queue` to all SSE subscribers.
- `LogStream.tsx` connects to all three streams and renders `line.msg` raw
  (only stripping a duplicate `timestamp level name:` prefix via regex).
- **Zero sanitization** on either side.

### What leaks

Any `logger.info()`/`logger.error()`/`logger.debug()` call in either backend
service that includes:

| Source file | What's logged | Risk |
|-------------|---------------|------|
| `fabric_discovery.py` L148-186 | Graph model IDs, KQL DB names, Eventhouse query URIs | **HIGH** |
| `graph-query-api/main.py` L99-105 | Request bodies (up to 1000 bytes) | **HIGH** |
| `orchestrator.py` L275 | Agent step queries (up to 300 chars) | **MEDIUM** |
| `orchestrator.py` L277 | Agent step responses (up to 200 chars) | **MEDIUM** |
| `orchestrator.py` L140-150 | Foundry run failure error codes/messages | **MEDIUM** |
| Any Azure SDK call | SDK debug logging includes endpoint URLs, request IDs | **MEDIUM** |
| Any unhandled exception | Full traceback including local variables | **HIGH** |

### Exposure vectors

1. **DOM** — visible in the terminal panels in the app UI
2. **Network tab** — SSE streams are plaintext `text/event-stream`, visible
   in browser DevTools
3. **Azure Log Analytics** — supervisor routes all stdout to container logs,
   which are ingested by Log Analytics

### Why this is #1 risk

Even if every other endpoint is locked down, the log streams act as a
**meta-amplifier**: any env var that appears in any log statement anywhere in
the codebase gets streamed to unauthorized viewers. The blast radius is
unbounded — it depends on what developers happen to log.

---

## 3. CRITICAL — `/api/config/resources` Endpoint

### What

`GET /api/config/resources` returns a resource graph for the infrastructure
visualizer. The `_infra_nodes_only()` function in `api/app/routers/config.py`
(~L258-276) embeds raw env var values into node `meta` fields:

```python
{"id": "infra-foundry",  "meta": {"resource": os.getenv("AI_FOUNDRY_NAME", ""),
                                   "project":  os.getenv("AI_FOUNDRY_PROJECT_NAME", "")}},
{"id": "infra-cosmos-n", "meta": {"resource": os.getenv("COSMOS_NOSQL_ENDPOINT", "")}},
{"id": "infra-storage",  "meta": {"resource": os.getenv("STORAGE_ACCOUNT_NAME", "")}},
{"id": "infra-search",   "meta": {"resource": os.getenv("AZURE_SEARCH_ENDPOINT", "")}},
```

### What leaks

| Env var | Example value | Risk |
|---------|---------------|------|
| `AI_FOUNDRY_NAME` | `aif-22eeqli26cwru` | Resource name |
| `AI_FOUNDRY_PROJECT_NAME` | `aifproj-22eeqli26cwru` | Resource name |
| `COSMOS_NOSQL_ENDPOINT` | `https://cosmos-22eeq.documents.azure.com:443/` | **Full endpoint URL** |
| `STORAGE_ACCOUNT_NAME` | `st22eeqli26cwru` | Resource name |
| `AZURE_SEARCH_ENDPOINT` | `https://srch-22eeq.search.windows.net` | **Full endpoint URL** |
| `FABRIC_WORKSPACE_ID` | `<GUID>` (via L107) | Workspace GUID |

### Exposure vectors

1. **Network tab** — JSON response visible in DevTools
2. **DOM** — `ResourceTooltip.tsx` renders `node.meta` key-value pairs via
   `Object.entries(node.meta).map(...)` (see §8)
3. **Persisted** — if the frontend caches or logs this data

---

## 4. CRITICAL — No Authentication on Any Endpoint

### What

Neither the main API, the graph-query-api, nor nginx enforce any
authentication or authorization. Every endpoint in both services is fully
open to any HTTP client that can reach the Container App FQDN.

### Architecture assumption

The code comments state the graph-query-api *"runs inside the VNet and is
called by Foundry's OpenApiTool on behalf of agents."* However:

1. The Container App has a **public FQDN** (set via Bicep `ingress.external: true`)
2. nginx proxies both `/api/` and `/query/` — the graph-query-api is
   reachable from outside the VNet via nginx
3. There is no VNet-only ingress restriction in the Bicep config

### Impact

| Action available to unauthenticated callers | Endpoint |
|---------------------------------------------|----------|
| Read all env vars via resource graph | `GET /api/config/resources` |
| Subscribe to live backend logs | `GET /api/logs`, `GET /query/logs` |
| Trigger AI agent orchestration (costs $$$) | `POST /api/alert` |
| Read all Fabric graph data | `POST /query/graph` |
| Read all telemetry data | `POST /query/telemetry` |
| Read full network topology | `POST /query/topology` |
| Read/delete investigation history | `GET/DELETE /query/interactions` |
| Trigger Fabric rediscovery (cache invalidation) | `POST /query/health/rediscover` |
| Read service health with resource names | `GET /api/services/health` |
| Enumerate all AI agents and their config | `GET /api/agents` |

### No rate limiting

nginx has no `limit_req_zone` or `limit_conn_zone`. An attacker could:
- Flood `POST /api/alert` to burn through Azure OpenAI TPM quotas
- Repeatedly call `POST /query/health/rediscover` to destabilize Fabric discovery

---

## 5. HIGH — `/api/services/health` Leaks Resource Names

### What

`GET /api/services/health` (in `api/app/main.py` ~L89-120) returns:

```json
{
  "services": [
    {"name": "AI Foundry", "status": "configured", "details": "<AI_FOUNDRY_NAME>"},
    {"name": "AI Search",  "status": "configured", "details": "<AI_SEARCH_NAME>"},
    {"name": "Cosmos DB",  "status": "configured", "details": "NoSQL interactions store"},
    {"name": "Graph Query API", "status": "configured", "details": "Fabric GQL"}
  ]
}
```

The `details` field for AI Foundry and AI Search contains raw `os.getenv()`
values — actual Azure resource names.

### Exposure vectors

1. **DOM** — `ServiceHealthPopover.tsx` renders `svc.details` directly
2. **Network tab** — JSON response
3. **Health button tooltips** — `HealthButtonBar.tsx` constructs summary strings

---

## 6. HIGH — Unfiltered Exception Messages in Responses

### What

Several endpoints return raw `str(e)` from caught exceptions:

| File | Endpoint | Return pattern |
|------|----------|----------------|
| `graph-query-api/router_graph.py` L68-72 | `POST /query/graph` | `f"Graph query error: {type(e).__name__}: {e}"` |
| `graph-query-api/router_telemetry.py` L78-82 | `POST /query/telemetry` | `f"KQL backend error: {type(e).__name__}: {e}"` |
| `graph-query-api/router_topology.py` L172 | `POST /query/topology` | `error=str(exc)` |
| `api/app/orchestrator.py` L410-412 | SSE via `POST /api/alert` | `_put("error", {"message": str(e)})` |

### What could leak

Python exceptions from Azure SDK calls can contain:
- Full endpoint URLs (with subscription ID segments)
- Request IDs and correlation IDs
- HTTP request/response details
- Internal stack trace context
- For `httpx`-based calls: request headers (potentially including
  `api-key` if `AZURE_SEARCH_KEY` is used — see below)

### Special concern: `AZURE_SEARCH_KEY` in memory

`graph-query-api/router_health.py` L28 captures `AZURE_SEARCH_KEY` as a
module-level constant and uses it in HTTP headers at L70-71:
```python
AI_SEARCH_KEY = os.getenv("AZURE_SEARCH_KEY", "")
# ...
if AI_SEARCH_KEY:
    headers["api-key"] = AI_SEARCH_KEY
```

If an exception in `_ping_search_index` includes request headers in the
error message (which `httpx` can do), the API key could be leaked through
the error response path or the SSE log stream.

---

## 7. HIGH — `azure_config.env` Baked into Docker Image

### What

The `Dockerfile` (L52) copies the config file into the image:
```dockerfile
COPY azure_config.env /app/azure_config.env
```

And `deploy.sh` (Step 6c, ~L969-985) generates this file right before
the image build, containing all env var values from the deployment.

### Impact

- Docker image layers are **immutable**. Even if the file is later
  overridden at runtime, the original layer still contains all values.
- Anyone with `docker pull` access to the ACR can extract it via
  `docker save` and layer inspection.
- Values include: `AZURE_SUBSCRIPTION_ID`, `COSMOS_NOSQL_ENDPOINT`,
  `AI_FOUNDRY_ENDPOINT`, `FABRIC_WORKSPACE_ID`, `FABRIC_API_URL`, etc.

### Compounding factor: ACR admin credentials

The ACR uses admin credentials for Container App image pulls
(`container-app.bicep` L72-82, `adminUserEnabled: true`). The more secure
approach would be managed-identity-based `acrPull` role assignment.

---

## 8. MEDIUM — Resource Tooltips Render Raw Env Vars

### What

`ResourceTooltip.tsx` (~L51-56) renders all `node.meta` key-value pairs:
```tsx
{Object.entries(node.meta).map(([k, v]) => (
  <div key={k}><span>{k}:</span> <span>{String(v)}</span></div>
))}
```

The `meta` object comes from `/api/config/resources` (§3) and contains
raw env var values. Hovering over any infrastructure node in the resource
visualizer shows `COSMOS_NOSQL_ENDPOINT`, `AZURE_SEARCH_ENDPOINT`, etc.
in a tooltip rendered directly in the DOM.

---

## 9. MEDIUM — Error Banner Renders Raw Backend Errors

### What

`ErrorBanner.tsx` (~L15) handles unrecognized error messages with a
fallthrough:
```tsx
message.slice(0, 200)
```

For 404/429/400, it shows canned text. For everything else, it renders the
first 200 characters of the raw backend error message, unfiltered.

### What could leak

Backend error messages that include Azure endpoint URLs, internal service
names, or SDK exception details.

---

## 10. MEDIUM — Orchestrator Exception Passthrough (SSE)

### What

`orchestrator.py` (~L410-412) catches top-level exceptions and sends the
full `str(e)` as an SSE error event to the client:
```python
except Exception as e:
    logger.exception("Orchestrator run failed")
    _put("error", {"message": str(e)})
```

The `logger.exception()` also sends the full traceback to the SSE log
stream (§2), compounding the exposure.

---

## 11. MEDIUM — Container Env Vars Visible in Azure Portal

### What

`infra/main.bicep` (~L153-177) passes all container environment variables
as plaintext `value` entries (not `secretRef`):

```bicep
env: [
  { name: 'PROJECT_ENDPOINT',        value: aiFoundry.outputs.projectEndpoint }
  { name: 'AI_FOUNDRY_PROJECT_NAME', value: aiFoundry.outputs.projectName }
  { name: 'COSMOS_NOSQL_ENDPOINT',   value: cosmosNoSql.outputs.cosmosNoSqlEndpoint }
  { name: 'AZURE_SUBSCRIPTION_ID',   value: subscription().subscriptionId }
  ...
]
secrets: []   // empty — nothing uses secretRef
```

All values are visible in:
- **Azure Portal** → Container App → Settings → Environment variables
- **ARM deployment history** → `az deployment sub show`
- **`az containerapp show`** output

Anyone with `Reader` role on the resource group can see every value.

---

## 12. MEDIUM — Deploy/Hook Scripts Echo Values to Logs

### What

Several scripts echo env var values to stdout, which would be captured
in CI/CD build logs:

| File | What's echoed |
|------|---------------|
| `hooks/preprovision.sh` L35-38 | Every synced env var: `→ KEY=VALUE` |
| `hooks/preprovision.sh` L56-72 | `AZURE_PRINCIPAL_ID`, `AZURE_FABRIC_ADMIN` |
| `deploy.sh` L1120-1145 | Full infrastructure summary (names, endpoints) |
| `deploy.sh` L855-875 | Fabric bearer token in shell variable (risk if `set -x` is enabled) |

---

## 13. LOW — Scenario Config Exposes Index & Graph Names

### What

`GET /api/config/scenario` returns scenario YAML metadata including:
- `runbooksIndex` — AI Search index name
- `ticketsIndex` — AI Search index name
- `graph` — Fabric Graph model name

Rendered in `ScenarioPanel.tsx` and `Header.tsx`. These are logical names,
not secrets, but reveal internal resource naming conventions.

---

## 14. LOW — Agent Metadata Reveals Architecture

### What

`GET /api/agents` returns and `AgentCard.tsx` renders:
- Agent names, roles, and statuses
- AI model names (e.g., `gpt-4.1`)
- Tool types with spec template filenames
- AI Search index key names
- Agent delegation graph (`connected_agents`)

Reveals the internal multi-agent architecture, which tools each agent uses,
and how they delegate work.

---

## 15. LOW — Browser DevTools Console Logging

### What

Frontend code contains `console.error` / `console.warn` calls:

| File | What's logged |
|------|---------------|
| `ScenarioContext.tsx` L12 | Error from failed scenario config fetch |
| `useInteractions.ts` L19, 44, 58 | Error objects from interaction CRUD |
| `useInvestigation.ts` L94 | **Raw SSE `ev.data`** on parse failure |
| `useInvestigation.ts` L99, 107 | SSE error objects |

Only visible in browser DevTools Console tab. The `ev.data` log at L94 is
the most concerning — it could contain partial backend responses with
infrastructure details.

---

## 16. LOW — nginx Fingerprinting & Missing Headers

### What

- No `server_tokens off` → `Server: nginx/x.x.x` header reveals version
- No custom `error_page` → default nginx error pages expose version string
- Missing security headers: `Strict-Transport-Security`,
  `Content-Security-Policy`, `Referrer-Policy`, `Permissions-Policy`
- Present (good): `X-Frame-Options SAMEORIGIN`, `X-Content-Type-Options nosniff`

---

## 17. 🔮 FUTURE — Admin Panel (v13QOL §8)

### Planned feature

A full-screen modal accessible from the header that:
1. `GET /api/admin/env` — reads **all** env vars from disk with their values
2. `POST /api/admin/env` — writes new values and restarts both services

### Threat assessment: **CRITICAL**

This is by far the highest-risk planned feature:

| Concern | Detail |
|---------|--------|
| **Full env var read access** | Every single value from `azure_config.env` is returned in one JSON payload — subscription IDs, all endpoints, Fabric workspace IDs, capacity IDs, ontology IDs, etc. |
| **Write access** | An attacker could change `PROJECT_ENDPOINT` to a malicious server, redirect AI agent traffic, or change `CORS_ORIGINS` to `*` |
| **Service restart** | `POST` triggers `supervisorctl restart` — enables DoS by repeatedly restarting services |
| **No auth planned** | The spec says *"This endpoint has no authentication — it trusts the caller. This is acceptable for a demo/internal tool."* |
| **Network tab** | The full env var payload is visible as a JSON response in browser DevTools |
| **Confirmation dialog** | Shows changed variable names and values (old → new) in the DOM |
| **Restart overlay** | Polls health endpoints — low risk on its own |

### Specific exposure vectors when implemented

1. **`GET /api/admin/env` response** — full env var dump in Network tab
2. **Admin Panel DOM** — every env var key and value rendered in text inputs
3. **Confirmation dialog DOM** — changed values shown in plaintext
4. **Screenshot/screen-share risk** — during demos, the admin panel is
   visible with all values if opened
5. **Browser history/autocomplete** — text inputs may be cached by browser
6. **Popen restart command** — `supervisorctl restart` runs as root with
   full env context

### Files that will be affected

| File | Risk area |
|------|-----------|
| `api/app/routers/admin.py` (new) | Unauthenticated read/write of all env vars |
| `AdminPanel.tsx` (new) | Full env var display in DOM |
| `Header.tsx` | Admin Panel button (access control needed) |
| `supervisord.conf` | New RPC socket enables remote process control |

### Minimum auth requirements before implementing

- [ ] Authentication middleware (at least API key or Azure AD)
- [ ] Restrict `GET /api/admin/env` to authenticated admin users only
- [ ] Restrict `POST /api/admin/env` to authenticated admin users only
- [ ] Mask sensitive values in the UI (show `****` with reveal toggle)
- [ ] Audit log for admin panel access and changes
- [ ] Rate limit the restart endpoint

---

## 18. 🔮 FUTURE — Enriched Health Tooltips (v13QOL §3)

### Planned feature

Health button tooltips will show full structured API responses instead of
summary strings. For example, the Services tooltip will show:
```
● AI Foundry  — connected (aif-22eeqli26cwru)
● AI Search   — connected (srch-22eeqli26cwru)
```

### Threat assessment: **MEDIUM**

| Concern | Detail |
|---------|--------|
| **Resource names in DOM** | Currently only visible in Network tab and `ServiceHealthPopover`. Moving to tooltips makes them visible on hover — more casual exposure |
| **Fabric Sources tooltip** | Will show per-source reachability including index names |
| **Agent Discovery tooltip** | Will show all agent names and statuses |
| **`detail` type change** | Changing from `string` to `unknown` (structured response) means the full API response object is stored in component state — accessible via React DevTools |

### Planned backend change compounds risk

v13QOL §3 also plans to upgrade `GET /api/services/health` to do **real
connectivity probes** instead of just checking env var presence. This means
the response will include actual connection results, endpoint URLs, and
possibly error messages from failed probes — all of which will flow into
the enriched tooltips.

### Files that will be affected

| File | Risk area |
|------|-----------|
| `HealthButtonBar.tsx` | Full API responses stored in state, rendered in tooltips |
| `api/app/main.py` | Real probe results (including error details) in response |

---

## 19. 🔮 FUTURE — Log Stream Clear & Level Filter (v13QOL §7g)

### Planned feature

Add a "Clear" button and log-level filter dropdown to `LogStream.tsx`.

### Threat assessment: **LOW** (but see caveat)

The level filter **hides** log lines client-side — it does **not** prevent
them from being received. The SSE stream still delivers all log levels.
An attacker monitoring the Network tab would still see every log line
regardless of the UI filter setting.

The "Clear" button only clears the rendered buffer — it doesn't affect
the SSE connection or prevent future log delivery.

**Net effect:** This feature provides a false sense of security. The
filter makes it *look* like sensitive DEBUG logs aren't visible, but they
are still delivered to the browser and visible in DevTools.

---

## 20. 🔮 FUTURE — Auto-Run Health Checks (v13QOL §7i)

### Planned feature

Auto-trigger all health checks on page load with staggered timing.

### Threat assessment: **LOW**

Currently health data requires a manual click. Auto-run means the
env-var-containing responses from `/api/services/health` and
`/query/health/rediscover` are fetched automatically on every page load
— no user action needed. This increases the **passive exposure** surface:
even a casual page visit populates the Network tab with infrastructure
details.

---

## 21. 🔮 FUTURE — Copy Buttons on Step Cards (v13QOL §7c)

### Planned feature

One-click copy buttons on agent step query/response sections.

### Threat assessment: **LOW**

Agent responses may contain infrastructure details (graph data, telemetry
results, resource references). Copy buttons make it trivial to extract
this data to the clipboard. Low risk on its own, but compounds with the
fact that agent responses are already unsanitized (§6, §10).

---

## 22. Env Var Classification

Every variable in `azure_config.env` classified by exposure risk:

### Tier 1 — Secrets / Credentials (do NOT expose)

| Variable | Current status |
|----------|---------------|
| `AZURE_SEARCH_KEY` | Module-level constant in `router_health.py`; used in HTTP headers; not in config template but may exist at runtime |

> **Note:** This is the **only actual secret** found. Everything else uses
> managed identity. If `AZURE_SEARCH_KEY` is ever populated, it becomes
> the highest-priority item to protect.

### Tier 2 — Endpoints / URIs (enable targeted attacks)

| Variable | Exposed via |
|----------|-------------|
| `COSMOS_NOSQL_ENDPOINT` | `/api/config/resources`, ResourceTooltip, logs |
| `AZURE_SEARCH_ENDPOINT` | `/api/config/resources`, ResourceTooltip |
| `AI_FOUNDRY_ENDPOINT` | Logs, error messages |
| `PROJECT_ENDPOINT` | Logs, error messages |
| `FABRIC_API_URL` | Logs |
| `EVENTHOUSE_QUERY_URI` | `/query/health/rediscover`, logs |
| `APP_URI` | Deploy summary |
| `GRAPH_QUERY_API_URI` | Logs, health checks |

### Tier 3 — Resource Names / IDs (enable reconnaissance)

| Variable | Exposed via |
|----------|-------------|
| `AI_FOUNDRY_NAME` | `/api/services/health`, `/api/config/resources` |
| `AI_FOUNDRY_PROJECT_NAME` | `/api/config/resources` |
| `AI_SEARCH_NAME` | `/api/services/health` |
| `STORAGE_ACCOUNT_NAME` | `/api/config/resources` |
| `FABRIC_WORKSPACE_ID` | `/api/config/resources`, `/query/health/rediscover`, logs |
| `FABRIC_WORKSPACE_NAME` | Logs |
| `FABRIC_CAPACITY_ID` | Config file only |
| `FABRIC_ONTOLOGY_ID` | Config file only |
| `FABRIC_ONTOLOGY_NAME` | Logs |
| `FABRIC_LAKEHOUSE_NAME/ID` | Logs |
| `FABRIC_EVENTHOUSE_NAME/ID` | Logs |
| `FABRIC_KQL_DB_NAME/ID` | `/query/health/rediscover`, logs |
| `AZURE_SUBSCRIPTION_ID` | Portal (Bicep env), logs |
| `AZURE_RESOURCE_GROUP` | Portal (Bicep env), logs |
| `APP_PRINCIPAL_ID` | Config file, Portal |

### Tier 4 — Configuration (low sensitivity)

| Variable | Exposed via |
|----------|-------------|
| `DEFAULT_SCENARIO` | `/api/config/scenario` |
| `RUNBOOKS_INDEX_NAME` | `/api/config/scenario` |
| `TICKETS_INDEX_NAME` | `/api/config/scenario` |
| `MODEL_DEPLOYMENT_NAME` | Agent metadata |
| `EMBEDDING_MODEL` | Config file only |
| `EMBEDDING_DIMENSIONS` | Config file only |
| `GPT_CAPACITY_1K_TPM` | Config file only |
| `CORS_ORIGINS` | Process env only |
| `GRAPH_BACKEND` | `/health` response |
| `TOPOLOGY_SOURCE` | Config file only |
| `AZURE_LOCATION` | Config file/Portal |
| `FABRIC_CAPACITY_SKU` | Config file only |
| `FABRIC_SCOPE` | Config file only |
| `AZURE_FABRIC_ADMIN` | Deploy logs (email address — PII) |

---

## 23. Full Endpoint Inventory

Every endpoint, whether it requires auth, and what sensitive data it returns:

| Endpoint | Method | Auth | Sensitive data in response |
|----------|--------|------|---------------------------|
| `/health` | GET | None | None (`{"status": "ok"}`) |
| `/api/services/health` | GET | None | `AI_FOUNDRY_NAME`, `AI_SEARCH_NAME` |
| `/api/config/scenario` | GET | None | Index names, graph name |
| `/api/config/current` | GET | None | Agent IDs, index names, scenario config |
| `/api/config/resources` | GET | None | **Cosmos endpoint, Search endpoint, Storage name, Foundry name/project, Workspace ID** |
| `/api/agents` | GET | None | Agent IDs, model names, tool specs |
| `/api/agents/rediscover` | POST | None | Agent discovery results |
| `/api/alert` | POST | None | Agent responses via SSE, error messages |
| `/api/logs` | GET | None | **All backend logs (SSE)** |
| `/api/logs/data-ops` | GET | None | Data operation logs (SSE) |
| `/query/health` | GET | None | Backend type |
| `/query/health/sources` | GET | None | Per-source connectivity |
| `/query/health/rediscover` | POST | None | **Workspace ID, Graph Model ID, Eventhouse URI, KQL DB name** |
| `/query/graph` | POST | None | Graph data + unfiltered exceptions |
| `/query/telemetry` | POST | None | Telemetry data + unfiltered exceptions |
| `/query/topology` | POST | None | Full network topology |
| `/query/interactions` | GET | None | Investigation history |
| `/query/interactions` | POST | None | Save investigation |
| `/query/interactions/{id}` | DELETE | None | Delete investigation |
| `/query/logs` | GET | None | **All graph-query-api logs (SSE)** |
| `/query/logs/data-ops` | GET | None | Data-ops logs (SSE) |
| 🔮 `/api/admin/env` | GET | None (planned) | **ALL env vars** |
| 🔮 `/api/admin/env` | POST | None (planned) | Write env vars + restart |

---

## 24. Network Tab Exposure Map

What an observer sees in browser DevTools Network tab without any
interaction beyond opening the app:

### On page load (automatic)

| Request | Response contains |
|---------|-------------------|
| `GET /api/config/scenario` | Scenario name, index names, graph model |
| `SSE /api/logs` | Live backend logs (auto-connects) |
| `SSE /query/logs` | Live graph-query-api logs (auto-connects) |
| `SSE /query/logs/data-ops` | Live data-ops logs (auto-connects) |

### On health check click (or auto-run if 🔮 §7i is implemented)

| Request | Response contains |
|---------|-------------------|
| `GET /api/services/health` | `AI_FOUNDRY_NAME`, `AI_SEARCH_NAME` |
| `GET /query/health/sources` | Source reachability |
| `POST /query/health/rediscover` | Workspace ID, Graph Model ID, Eventhouse URI |
| `POST /api/agents/rediscover` | Agent IDs and config |

### On resource graph view

| Request | Response contains |
|---------|-------------------|
| `GET /api/config/resources` | **All Tier 2+3 env vars** (endpoints, names, IDs) |

### On investigation

| Request | Response contains |
|---------|-------------------|
| `POST /api/alert` | SSE stream: agent queries, responses, error messages |
| `POST /query/topology` | Full network graph |

### 🔮 On admin panel open

| Request | Response contains |
|---------|-------------------|
| `GET /api/admin/env` | **EVERY env var, every value** |

---

## Revision Log

| Date | Pass | Changes |
|------|------|---------|
| 2026-02-19 | Initial recon | Full threat surface enumeration across all layers |
