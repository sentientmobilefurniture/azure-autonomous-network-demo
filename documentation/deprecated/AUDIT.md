# Project Audit — Failure Points & Knock-On Effects

**Date:** 2026-02-12
**Scope:** Full codebase — infra, hooks, scripts, API, graph-query-api, frontend

---

## CRITICAL — Will cause production failures

### 1. Container App has no Cosmos DB NoSQL RBAC role

**Location:** [infra/modules/roles.bicep](../infra/modules/roles.bicep) + [infra/main.bicep](../infra/main.bicep)

**Problem:** The `graph-query-api` Container App uses `DefaultAzureCredential` (via its
system-assigned managed identity) to query Cosmos DB NoSQL in
[router_telemetry.py](../graph-query-api/router_telemetry.py#L22). But `roles.bicep` only assigns
the `Cosmos DB Built-in Data Contributor` role to the **user** principal — it never assigns any
Cosmos DB data-plane role to the Container App's managed identity
(`graphQueryApi.outputs.principalId`).

**Consequence chain:**
1. Container App starts, receives `COSMOS_NOSQL_ENDPOINT` env var — config looks correct
2. Foundry TelemetryAgent sends a `/query/telemetry` request
3. `router_telemetry.py` creates `CosmosClient` with `DefaultAzureCredential` (managed identity)
4. **403 Forbidden** — managed identity has no data-plane RBAC on the NoSQL account
5. Error-as-200 returns `"Cosmos SQL query error: Forbidden"` — but the agent can't fix a permissions error
6. Every TelemetryAgent invocation from the orchestrator fails
7. Orchestrator loses its Telemetry sub-agent in production (works locally because user has the role)

**Impact:** TelemetryAgent is completely non-functional when deployed as a Container App.

---

### 2. `postprovision.sh` NoSQL endpoint fallback queries the wrong account

**Location:** [hooks/postprovision.sh](../hooks/postprovision.sh#L199-L201)

**Problem:** The NoSQL endpoint fallback (line 199-201) runs:
```bash
COSMOS_NOSQL_EP=$(az cosmosdb show --name "$COSMOS_ACCOUNT" ...)
```
But `$COSMOS_ACCOUNT` is the **Gremlin** account name (e.g., `cosmos-gremlin-xxx`), not the
NoSQL account (`cosmos-gremlin-xxx-nosql`). If the Bicep output `AZD_COSMOS_NOSQL_ENDPOINT` is
somehow empty, the fallback populates the wrong endpoint — the Gremlin account's `documentEndpoint`
instead of the NoSQL account's.

**Consequence chain:**
1. Normally the Bicep output is populated, so the fallback never fires — this is a **latent defect**
2. If someone deploys without Bicep outputs (manual Azure environment, or `azd` env issue), the
   fallback silently writes the Gremlin account's endpoint into `COSMOS_NOSQL_ENDPOINT`
3. All telemetry scripts and Container App telemetry queries go to the wrong account — either
   silent empty results or auth errors
4. Hard to diagnose because the config *looks* populated

**The same bug exists for `COSMOS_EP` (Gremlin endpoint fallback on line 189)** — it queries
`documentEndpoint` but Gremlin needs the `gremlinEndpoint` (different host:
`xxx.gremlin.cosmos.azure.com` vs `xxx.documents.azure.com`). This would cause
`WSServerHandshakeError` on the Gremlin client.

---

### 3. Gremlin client has no reconnection logic

**Location:** [graph-query-api/backends/cosmosdb.py](../graph-query-api/backends/cosmosdb.py#L38-L46)

**Problem:** The Gremlin client is a module-level singleton (`_gremlin_client`) that's created once
and never refreshed. The retry logic in `_submit_query()` only catches:
- `GremlinServerError` with status 429 or 408 (rate limit / timeout)
- `WSServerHandshakeError` (auth failure at connection time)

It does **not** catch or recover from:
- `ConnectionResetError` (WebSocket dropped mid-query)
- `ConnectionClosedError` / `WebSocketError` (Cosmos DB rotated connections, server restart)
- `asyncio.TimeoutError` / `TimeoutError` (network timeout)
- Any `OSError` subclass (DNS, routing, TLS failures)

**Consequence chain:**
1. Container App runs for hours/days with long-lived WebSocket to Cosmos DB
2. Cosmos DB performs routine maintenance, or network blip drops the connection
3. Next Gremlin query raises an unhandled transport error
4. `router_graph.py` catches it as a generic `Exception` and returns `error` in the 200 body
5. All subsequent queries also fail because the singleton client still references the dead connection
6. GraphExplorerAgent is **permanently broken** until the Container App is restarted
7. Every investigation loses its Graph sub-agent

---

### 4. Cosmos DB Gremlin primary key in Bicep outputs (secret leak)

**Location:** [infra/modules/cosmos-gremlin.bicep](../infra/modules/cosmos-gremlin.bicep#L225)

**Problem:** `output primaryKey string = cosmosAccount.listKeys().primaryMasterKey` emits the
primary key as a Bicep deployment output. This value is:
- Stored in `.azure/<env>/` state files (unencrypted JSON on disk)
- Visible in Azure deployment history (Portal → Resource Group → Deployments)
- Logged by `azd` if verbose output is enabled
- Passed through `main.bicep` to `container-app.bicep` as a secret value (correct), but
  the intermediate output is the leak point

**Consequence chain:**
1. Anyone with access to the deployment history or `.azure/` folder can extract the Cosmos DB key
2. Key grants full read/write access to the entire Cosmos DB account (all databases, all containers)
3. This applies to both the Gremlin graph data AND the NoSQL telemetry data

---

## HIGH — Operational risk or silent failures

### 5. `provision_agents.py` has no idempotency or partial-failure recovery

**Location:** [scripts/provision_agents.py](../scripts/provision_agents.py#L388-L440)

**Problem:** The script creates 5 agents sequentially. If it fails after creating 2 of 4
sub-agents (e.g., API error, rate limit), it exits without writing `agent_ids.json`. The
2 agents that were created are now orphaned in Foundry.

**Consequence chain:**
1. User re-runs `provision_agents.py` → creates 5 **new** agents, totalling 7 (2 orphaned + 5 new)
2. User runs with `--force` → `cleanup_existing_agents()` calls `agents_client.list_agents()`
   which returns all agents. But it only deletes agents with matching names — if Foundry
   has a pagination limit, some may be missed
3. Orphaned agents accumulate, consuming Foundry quota
4. No way to know which orchestrator ID is the correct one without inspecting `agent_ids.json`

### 6. `config.py` reads env vars at import time — no hot reload

**Location:** [graph-query-api/config.py](../graph-query-api/config.py)

**Problem:** All configuration (`COSMOS_NOSQL_ENDPOINT`, `COSMOS_GREMLIN_ENDPOINT`,
`COSMOS_GREMLIN_PRIMARY_KEY`, etc.) is read once at module import via `os.getenv()`. The
Container App template passes env vars from Bicep, so these are set at container start.

**Consequence chain:**
1. If Cosmos DB key is rotated (manual or automatic), the Container App still uses the old key
2. All Gremlin queries start failing with `WSServerHandshakeError (401)`
3. **The error-as-200 pattern surfaces this as** `"Cosmos DB Gremlin authentication failed"` —
   but the agent cannot fix this
4. Requires a Container App restart (`az containerapp revision restart`) or redeployment to pick
   up new credentials
5. No health check reports credential staleness — `/health` returns `ok` even with dead credentials

### 7. Container App ingress is public with no authentication

**Location:** [infra/main.bicep](../infra/main.bicep#L144) — `externalIngress: true`

**Problem:** The `graph-query-api` Container App has external (public) ingress with no
authentication layer. `OpenApiAnonymousAuthDetails()` is used in the agent provisioning
script. The Container App FQDN is publicly accessible.

**Consequence chain:**
1. Anyone who discovers the Container App URL can send arbitrary Gremlin traversal queries
2. Gremlin queries can read **all** graph data (topology, services, SLA policies)
3. Gremlin queries can also **write** data (`g.addV(...)`, `g.V().drop()`) — the primary key
   grants full read/write access
4. SQL queries can read all telemetry data via `/query/telemetry`
5. No rate limiting on the Container App beyond the scaling rules

This is an intentional design choice (Foundry's `OpenApiTool` calls from outside the VNet),
but the trade-off is significant — the entire graph database is publicly accessible.

### 8. `run_orchestrator()` SSE queue has no timeout/deadlock protection

**Location:** [api/app/orchestrator.py](../api/app/orchestrator.py#L429-L436)

**Problem:** The async generator at the bottom of `run_orchestrator()`:
```python
while True:
    item = await queue.get()
    if item is None:
        break
    yield item
```
If the background thread hangs (e.g., Foundry stream never completes, network timeout
without exception), `queue.get()` blocks forever. The SSE connection stays open but idle.

**Consequence chain:**
1. Foundry run hangs (not uncommon with complex agent orchestration)
2. SSE connection stays open — frontend shows "processing..." indefinitely
3. User refreshes page → starts a new investigation, but the old thread is still running
4. Multiple hanging threads accumulate, each holding resources (SDK connection, thread)
5. No server-side timeout kills these hung connections

### 9. `useInvestigation.ts` has no client-side timeout

**Location:** [frontend/src/hooks/useInvestigation.ts](../frontend/src/hooks/useInvestigation.ts)

**Problem:** The `fetchEventSource` call has no timeout. Orchestrator investigations can take
60-120+ seconds normally, but a hung run (Finding #8) could keep the connection open
indefinitely. The `AbortController` is only triggered by the user starting a new investigation.

**Consequence chain:**
1. User submits alert → investigation hangs at "Orchestrator: calling sub-agent..."
2. No automatic timeout or "taking longer than expected" feedback
3. User doesn't know whether to wait or retry
4. If user navigates away and comes back, there's no indication of the previous state

---

## MEDIUM — Degraded behavior or maintenance burden

### 10. `create_runbook_indexer.py` and `create_tickets_indexer.py` are copy-paste duplicates

**Location:** [scripts/create_runbook_indexer.py](../scripts/create_runbook_indexer.py) and
[scripts/create_tickets_indexer.py](../scripts/create_tickets_indexer.py)

**Problem:** The two files are 242-line copies with only 5-6 parameterized differences (index name,
container name, docstring). Any bug fix or enhancement must be applied to both files.

**Consequence chain:**
1. Future changes to index schema, vectorizer config, or skillset parameters must be mirrored
2. Drift between the two is inevitable — one gets updated, the other doesn't
3. A shared `_create_indexer(index_name, container_name, ...)` function would eliminate this risk

### 11. Log streaming memory leak risk under sustained disconnect

**Location:** [api/app/routers/logs.py](../api/app/routers/logs.py) and
[graph-query-api/main.py](../graph-query-api/main.py#L157-L181)

**Problem:** Both services maintain `_subscribers: set[asyncio.Queue]` for SSE log clients. Each
client gets a `Queue(maxsize=500)`. If a client disconnects without the `finally` block executing
(e.g., server-side connection drop, not client-initiated), the queue stays in the set.

Queues are only cleaned on `QueueFull` (reactive cleanup in `_broadcast()`). Between that point
and the queue filling up, 500 log records per orphaned subscriber accumulate.

**Consequence chain:**
1. Under normal use, `finally` in the generator cleans up — this is fine
2. Under abnormal disconnect (network partition), queues orphan
3. With many concurrent page loads + disconnects, memory creeps up
4. For a demo with <10 users this is negligible, but the pattern doesn't scale

### 12. `preprovision.sh` uses Bash associative arrays but runs under `sh`

**Location:** [azure.yaml](../azure.yaml#L12) and [hooks/preprovision.sh](../hooks/preprovision.sh#L23-L28)

**Problem:** `azure.yaml` specifies `shell: sh` for the preprovision hook, but the script uses
`declare -A ENV_MAP=(...)` which is a **Bash 4+** feature, not POSIX `sh`. This works because
most Linux distros symlink `sh → bash`, but:
- On systems where `sh` is `dash` (e.g., Ubuntu default), `declare -A` will fail with a syntax error
- macOS ships `sh` as `zsh` in sh-compatibility mode, where `declare -A` also works differently

**Consequence chain:**
1. On a developer's Ubuntu machine with `dash` as default `sh`, `preprovision.sh` crashes
2. `azd up` fails at the preprovision step with a cryptic "syntax error"
3. User must either change `azure.yaml` to `shell: bash` or ensure bash is the default `sh`

### 13. No Container App RBAC for AI Search (search queries from Container App)

**Location:** [infra/modules/roles.bicep](../infra/modules/roles.bicep)

**Problem:** The Container App's managed identity has no role assignments at all. While
`/query/graph` uses key-based auth for Gremlin (passed as env var), and `/query/telemetry` uses
`DefaultAzureCredential` for Cosmos NoSQL (blocked by Finding #1), there's a forward-looking gap:
if the Container App ever needs to call AI Search or Storage directly, it would fail.

Currently the Container App doesn't call these services, so this is not a runtime failure today.

### 14. `graph-query-api` Dockerfile copies individual files, not patterns

**Location:** [graph-query-api/Dockerfile](../graph-query-api/Dockerfile)

**Problem:** The Dockerfile explicitly lists each Python file:
```dockerfile
COPY main.py config.py models.py router_graph.py router_telemetry.py ./
```
If a new router or module is added (e.g., `router_health.py`, `utils.py`), it must be manually
added to the Dockerfile. Forgetting to add it causes an `ImportError` in the deployed container.

**Consequence chain:**
1. Developer adds a new module, tested locally → works fine
2. `azd deploy graph-query-api` builds the Docker image → new module is missing
3. Container starts → `ImportError` at import time → container crash-loops
4. Previous revision still serves traffic (Container Apps keeps the last healthy revision)
5. Difficult to diagnose because local dev always works

---

## LOW — Robustness improvements

### 15. `step_complete` events lack step-count tracking from `run_complete`

**Location:** [api/app/orchestrator.py](../api/app/orchestrator.py#L410-L413)

**Problem:** The `run_complete` event always uses `handler.ui_step` for the step count, but
the frontend's `useInvestigation.ts` calculates step count independently from `steps.length`.
If the SSE stream is interrupted before `run_complete`, the frontend's `finally` block uses
`prev.length` which should match — so this is actually consistent. No real issue.

### 16. `MockGraphBackend` returns stale canned data

**Location:** [graph-query-api/backends/mock.py](../graph-query-api/backends/mock.py)

**Problem:** The mock backend pattern-matches query strings and returns hardcoded topology data.
If the graph schema evolves (new entity types, renamed fields), the mock data drifts from reality.
The mock backend is only used for offline demos, but stale data could give misleading demo results.

### 17. Container App scaling starts at `minReplicas: 1`

**Location:** [infra/main.bicep](../infra/main.bicep#L146) — `minReplicas: 1`

**Problem:** The Container App always has at least 1 running replica (no scale-to-zero). This
avoids cold-start latency for OpenApiTool calls but means continuous cost even when not in use.
For a demo that runs intermittently, scale-to-zero with fast cold start would save cost.

This is a conscious choice documented in ARCHITECTURE.md ("No cold-start penalty with
min-replicas=1"), so it's not a defect — just a cost trade-off.

---

## Summary Matrix

| # | Severity | Area | Root Cause | Status |
|---|----------|------|-----------|--------|
| 1 | CRITICAL | Bicep RBAC | Container App MI has no Cosmos NoSQL role | **FIXED** — roles.bicep + main.bicep |
| 2 | CRITICAL | postprovision | Fallback queries wrong Cosmos account | **FIXED** — postprovision.sh |
| 3 | CRITICAL | cosmosdb.py | No reconnect on dead WebSocket | **FIXED** — reconnect + client reset |
| 4 | CRITICAL | Bicep output | Primary key in deployment output | **MITIGATED** — `#disable-next-line` + comment (Gremlin requires keys, Key Vault for prod) |
| 5 | HIGH | provision_agents | No partial-failure recovery | **FIXED** — try/except with orphan reporting |
| 6 | HIGH | config.py | Import-time env var reads | **ACCEPTED** — standard for Container Apps; restart on key rotation |
| 7 | HIGH | container-app.bicep | Public ingress + no auth | **ACCEPTED** — required by Foundry OpenApiTool architecture |
| 8 | HIGH | orchestrator.py | No queue timeout | **FIXED** — 2-min per-event timeout via `asyncio.wait_for` |
| 9 | HIGH | useInvestigation.ts | No client timeout | **FIXED** — 5-min auto-abort via `setTimeout` |
| 10 | MEDIUM | scripts/ | Copy-paste indexer scripts | **FIXED** — shared `_indexer_common.py` + thin wrappers |
| 11 | MEDIUM | logs.py + main.py | Reactive subscriber cleanup | **ACCEPTED** — negligible for demo scale (<10 users) |
| 12 | MEDIUM | azure.yaml + preprovision | `sh` shell with bash-isms | **FIXED** — POSIX `case` statement replaces `declare -A` |
| 13 | MEDIUM | roles.bicep | No Container App MI roles | **ACCEPTED** — forward-looking; no current consumer |
| 14 | MEDIUM | Dockerfile | Explicit file list | **FIXED** — `COPY *.py ./` wildcard |
