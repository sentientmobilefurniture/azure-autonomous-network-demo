# Autonomous Network Demo — Failure Mode Audit

## Executive Summary

The system has strong architectural foundations (error-as-200 pattern, backend abstraction, decomposed prompts), but carries **significant risk in 5 systemic areas**: uncontrolled cost, missing auth/rate-limiting, silent config failures, non-thread-safe shared state, and tightly coupled provisioning with no rollback.

---

## 1. COST / WASTE (the silent killer)

| Risk | Impact | Location |
|------|--------|----------|
| **GPT-4.1 at 300K TPM** | Over-provisioned for a demo; still costs even at zero traffic | `infra/main.bicepparam` |
| **No budget alerts** | Nothing detects runaway spend from rogue agent loops or repeated provisioning | Entire infra layer |
| **Container App min-replicas=1** | Never scales to zero; ~$30/month idle | `infra/modules/container-app.bicep` |
| **Log Analytics 30-day retention** | Default retention ingests container logs continuously | `infra/modules/container-apps-environment.bicep` |
| **Orphaned agents on re-provision** | Running `provision_agents.py` without `--force` creates duplicate agents that consume quota | `scripts/provision_agents.py` |
| **Estimated baseline**: ~$1,200+/month with zero traffic | | |

---

## 2. SECURITY / ABUSE (no gate on the front door)

| Risk | Severity | Location |
|------|----------|----------|
| **No authentication on any endpoint** | CRITICAL | `api/app/main.py` — no auth middleware |
| **No rate limiting on POST /api/alert** | CRITICAL | `api/app/routers/alert.py` — each call spawns a thread + Azure agent run |
| **No concurrency limit** | HIGH | Unlimited parallel investigations = unlimited Azure AI token spend |
| **No input length validation** | HIGH | `api/app/routers/alert.py` — multi-MB alert text accepted |
| **Cosmos DB primary key in Bicep output** | HIGH | `infra/modules/cosmos-gremlin.bicep` — visible in ARM deployment JSON |
| **ACR admin credentials enabled** | MEDIUM | `infra/modules/container-apps-environment.bicep` — should use managed identity pull |
| **Exception messages leak to SSE clients** | MEDIUM | `api/app/orchestrator.py` — endpoint URLs, tenant IDs exposed |
| **Dockerfile runs as root** | MEDIUM | `graph-query-api/Dockerfile` — no `USER` instruction |
| **CORS `allow_methods=["*"]`, `allow_headers=["*"]`** | MEDIUM | `api/app/main.py` |

---

## 3. KNOCK-ON / CASCADE FAILURES (one failure breaks everything)

### 3a. Config file as shared mutable state

`azure_config.env` is read and written by 10+ scripts with regex-based updates and **no file locking**. Concurrent scripts corrupt the file. A corrupted file breaks every downstream consumer (API, graph-query-api, all provisioning scripts).

### 3b. Provisioning ordering not enforced

The provisioning pipeline has strict ordering dependencies documented only in READMEs:

```
azd up → indexers → cosmos_graph → cosmos_telemetry → provision_agents
```

No script validates its prerequisites exist. Running out of order produces **silently broken state**: agents created with empty tool URLs, Cosmos DB containers missing data, search indexes with zero documents.

### 3c. Half-provisioned agent state

If `provision_agents.py` fails mid-way (after creating GraphExplorerAgent but before TelemetryAgent), `agent_ids.json` is never written. The old file still references the old agent set. The new half-created agents become orphaned with no cleanup path.

### 3d. Schema defined in 5 places

Graph structure is replicated across: `graph_schema.yaml`, Cosmos Gremlin loader, agent prompts (`core_schema.md`), and OpenAPI specs. Any change requires coordinated updates with no automated validation.

### 3e. DefaultAzureCredential crash at import

`graph-query-api/config.py` instantiates `DefaultAzureCredential()` at module import time. If no identity is available (common during pure mock/offline demos), the entire service crashes before even loading — including the mock backend that needs no Azure identity.

---

## 4. RESOURCE LEAKS / STABILITY

| Risk | Severity | Location |
|------|----------|----------|
| **Daemon thread runs to completion after SSE disconnect** | HIGH | `api/app/orchestrator.py` — no cancellation signal; wastes Azure AI tokens |
| **SSE consumer hangs forever if sentinel fails** | HIGH | `api/app/orchestrator.py` — `queue.get()` with no timeout |
| **Log subscriber coroutine leak** | HIGH | `api/app/routers/logs.py` — evicted subscribers never receive sentinel; generator hangs forever |
| **Thread-safety on subscriber set** | HIGH | `api/app/routers/logs.py` + `graph-query-api/main.py` — `set` iterated and mutated from different threads |
| **CosmosClient leaked on URI change** | HIGH | `graph-query-api/router_telemetry.py` — old client never closed |
| **Gremlin WSS no reconnection** | HIGH | `graph-query-api/backends/cosmosdb.py` — dead WebSocket causes all queries to fail permanently |
| **Gremlin close() not thread-safe** | HIGH | `graph-query-api/backends/cosmosdb.py` — concurrent close + query = corruption |
| **Backend singleton race** | MEDIUM | `graph-query-api/router_graph.py` — no lock on init |
| **No graceful shutdown** | MEDIUM | `api/app/main.py` — no lifespan handler; daemon threads killed on SIGTERM |
| **HealthDot checks once, never again** | MEDIUM | `frontend/src/components/HealthDot.tsx` — green forever after first check |

---

## 5. SILENT FAILURES (things that look fine but aren't)

| Risk | Location | Symptom |
|------|----------|---------|
| **Stub mode without indication** | `api/app/routers/alert.py` | Misconfigured prod returns fake 4-agent walkthrough with HTTP 200 |
| **Agents created with empty tool URLs** | `scripts/provision_agents.py` | `GRAPH_QUERY_API_URI=""` → agents have `tools=[]`, appear healthy but can't query anything |
| **Missing env vars produce warnings, not errors** | `graph-query-api/main.py` | App starts, fails at request time with confusing backend errors |
| **Search indexer counts "transient failures" as success** | `scripts/create_runbook_indexer.py` | Exit code 0 even with failed items |
| **CORS blocks production graph-query-api** | `graph-query-api/main.py` | Hardcoded localhost origins; production frontend will fail CORS preflight |
| **Errors returned as HTTP 200** | `graph-query-api/router_graph.py` | Monitoring/alerting that watches 4xx/5xx will never fire on graph query failures |
| **`hook shell: sh` but scripts use bash features** | `azure.yaml` | Will break on systems where `sh` → `dash` (Ubuntu/Debian default) |

---

## 6. DETAILED FILE-LEVEL FINDINGS

### 6.1 API Service — `api/app/main.py`

| # | Category | Issue |
|---|----------|-------|
| 1 | Health check depth | `/health` returns static `{"status": "ok"}` without validating any downstream dependency — no check on Azure AI Project connectivity, `agent_ids.json` readability, or env-var presence. A deployment can pass health checks while being completely unable to process alerts. |
| 2 | Configuration validation | `load_dotenv()` silently succeeds if the file doesn't exist. No validation that critical env vars are loaded. |
| 3 | Configuration validation | `CORS_ORIGINS` defaults to `http://localhost:5173`. In production this default is wrong but won't fail loudly — requests from actual production origins will be CORS-blocked with no helpful error. |
| 4 | Security | `allow_methods=["*"]` and `allow_headers=["*"]` are overly broad. `allow_credentials=True` + wildcard is a security anti-pattern. |
| 5 | Auth/AuthZ | No authentication or authorization middleware anywhere. POST `/api/alert` can be called by anyone, enabling abuse. |
| 6 | Shutdown | No `@app.on_event("shutdown")` or lifespan handler to gracefully shut down background threads, SSE connections, or SDK clients. |

### 6.2 API Service — `api/app/orchestrator.py`

| # | Category | Issue |
|---|----------|-------|
| 1 | Daemon thread leak | Background thread is `daemon=True`. If SSE client disconnects, the daemon thread continues running inside `stream.until_done()` until the Azure SDK call completes. No cancellation signal — wastes Azure AI tokens and holds an SDK client open. |
| 2 | Queue poisoning | `asyncio.run_coroutine_threadsafe(queue.put(...), loop)` enqueues from a background thread. If the event loop is closed (server shutdown while orchestrator run is in flight), the sentinel `None` in the `finally` block also fails, so the consumer hangs forever on `await queue.get()`. |
| 3 | Unbounded generator lifetime | The consumer `while True: item = await queue.get()` has no timeout. If `_thread_target` crashes before enqueuing `None`, the SSE connection hangs open forever. |
| 4 | Missing SDK client cleanup | No timeout on the entire operation. A hung Azure endpoint means the thread blocks indefinitely. |
| 5 | Retry on silent failure | When `handler.response_text` is empty, `agents_client.messages.list()` could itself throw. This exception is caught by outer `try/except Exception` which only emits a generic error, losing retry context. |
| 6 | Retry step numbering | On retry, a new `SSEEventHandler` is created but `ui_step` resets to 0. The frontend sees step numbers restart from 1, causing UI confusion. |
| 7 | TOCTOU on agent_ids.json | `is_configured()` reads `agent_ids.json`, then `run_orchestrator()` reads it again. File could be modified between reads. |
| 8 | Error message leaks | `_put("error", {"message": str(e)})` exposes raw Python exception messages (credential paths, endpoint URLs, SDK internals) to SSE clients. |
| 9 | Credential per-call | `DefaultAzureCredential()` instantiated per call. Creates a new credential chain for each alert — wasteful and can cause token-refresh storms. Should be cached. |
| 10 | Unbounded queue | `asyncio.Queue()` has no `maxsize`. If consumer is slow, queue grows without bound. |
| 11 | No concurrency limit | Nothing prevents hundreds of concurrent `POST /api/alert` calls, each spawning a thread + SDK client + agent run. |

### 6.3 API Service — `api/app/routers/alert.py`

| # | Category | Issue |
|---|----------|-------|
| 1 | SSE disconnect | `EventSourceResponse` does not pass `send_timeout` or dead-client detection. |
| 2 | No request timeout | No maximum duration for SSE stream. A single agent run could hang forever. |
| 3 | Input validation | `AlertRequest.text` has no max-length constraint. Multi-MB strings accepted. |
| 4 | No rate limiting | Combined with unbounded concurrency, this is an abuse vector. |
| 5 | Stub/real ambiguity | Fallback to `_stub_event_generator` happens silently with HTTP 200. No indicator that stub mode is active. |

### 6.4 API Service — `api/app/routers/logs.py`

| # | Category | Issue |
|---|----------|-------|
| 1 | Coroutine leak | When a subscriber queue is full (`QueueFull`), `_broadcast` removes it from `_subscribers`. But the SSE generator still holds a reference to the queue and hangs on `await q.get()` forever — it never receives a `None` sentinel. |
| 2 | Thread safety | `_broadcast()` is called from `_SSELogHandler.emit()` on any thread. `_subscribers` is a plain `set` iterated and mutated concurrently → `RuntimeError: Set changed size during iteration`. |
| 3 | SSE generator never terminates | `_log_event_generator` loops `while True`. No mechanism to tell connected log clients to disconnect on server shutdown. |
| 4 | Global handler side effects | `logging.getLogger().addHandler(_handler)` runs at import time. Multiple imports = duplicate handlers = duplicate broadcasts. |
| 5 | Filter too broad | Filter `r.name.startswith(("app", "azure", "uvicorn"))` matches any logger starting with "app" (e.g., `application_insights`). |
| 6 | Silent subscriber eviction | Queue overflow causes subscriber to be silently dropped. No backpressure signal — client doesn't know it was kicked. |

### 6.5 API Service — `api/app/mcp/server.py`

| # | Category | Issue |
|---|----------|-------|
| 1 | Dead code | All three tools return `[STUB]` strings. Never mounted or imported by `main.py`. Orphaned code that could mislead developers. |

### 6.6 graph-query-api — `config.py`

| # | Category | Issue |
|---|----------|-------|
| 1 | Import-time crash | `DefaultAzureCredential()` at module import. No identity = crash before mock backend can load. |
| 2 | No credential recreation | If identity provider goes down temporarily, no way to recreate credential without restart. |
| 3 | Mock requires telemetry vars | `BACKEND_REQUIRED_VARS` lists telemetry env vars for mock, contradicting offline purpose. |

### 6.7 graph-query-api — `main.py`

| # | Category | Issue |
|---|----------|-------|
| 1 | Hardcoded DEBUG | No env var to control log level. Enormous log volume in production. |
| 2 | CORS hardcoded localhost | Production domain not listed. CORS preflight will fail from real frontend. |
| 3 | Request body logged | Up to 1000 bytes of query payload logged — potential sensitive data exposure. |
| 4 | Log broadcast not thread-safe | `_log_subscribers` set iterated/mutated from multiple threads. Data race. |
| 5 | QueueFull permanently disconnects | Slow client loses all future logs, not just the overflowed message. |
| 6 | SSE no heartbeat/keepalive | Reverse proxies kill idle connections after ~60-120s. No keepalive events sent. |
| 7 | Missing env vars only warn | App starts anyway, fails at request time with confusing errors. |

### 6.8 graph-query-api — `router_graph.py`

| # | Category | Issue |
|---|----------|-------|
| 1 | Backend singleton race | `get_graph_backend()` has no lock. Two concurrent first-requests create two backend instances; one leaks. |
| 2 | All errors HTTP 200 | Intentional for LLM consumption, but monitoring/alerting never triggers on failures. |
| 3 | HTTPException downgraded | 429 rate-limit `Retry-After` headers lost when converted to 200 error payload. |

### 6.9 graph-query-api — `router_telemetry.py`

| # | Category | Issue |
|---|----------|-------|
| 1 | CosmosClient leaked | When URI changes, new client created but old one never closed. Leaks HTTP connections. |
| 2 | IndexError on empty results | `primary_results[0]` can raise `IndexError` — guard only checks for `None`, not empty list. |
| 3 | All rows loaded into memory | No pagination. SQL queries returning millions of rows could OOM the container. |

### 6.10 graph-query-api — `backends/cosmosdb.py`

| # | Category | Issue |
|---|----------|-------|
| 1 | No WebSocket reconnection | Singleton WSS connection. Silent drop → all subsequent queries fail permanently. No health check or reconnect. |
| 2 | Lock held during handshake | `_gremlin_lock` held during initial WSS handshake (seconds). All other requests block. |
| 3 | `close()` not thread-safe | Sets `_gremlin_client = None` without lock. Concurrent close + query = corrupted state. |
| 4 | Only retries 429/408 | Cosmos DB 503 (partition moves) not retried. |
| 5 | `time.sleep()` blocks thread pool | Failing queries with exponential backoff block threads for 6+ seconds. Can exhaust pool. |

### 6.11 graph-query-api — `Dockerfile`

| # | Category | Issue |
|---|----------|-------|
| 1 | Runs as root | No `USER` instruction. Compromised container = root access. |
| 2 | Base image unpinned | `python:3.11-slim` resolves differently over time. Should pin digest. |
| 3 | uv tag `:latest` | Build not reproducible across time. |
| 4 | Explicit file copies | New `.py` files require manual Dockerfile update. Should `COPY . .` with `.dockerignore`. |
| 5 | No HEALTHCHECK | Container orchestrators can't detect unhealthy app without external probe config. |

### 6.12 OpenAPI Specs — `graph-query-api/openapi/`

| # | File | Issue |
|---|------|-------|
| 1 | `mock.yaml` | Telemetry endpoint requires cloud credentials even in mock spec. Offline demos impossible for telemetry. |
| 2 | All | Template placeholders (`{base_url}`) make raw YAML un-parseable by OpenAPI validators until substituted. |

---

## 7. PROVISIONING SCRIPT FINDINGS

### 7.1 `scripts/provision_agents.py`

| # | Category | Issue |
|---|----------|-------|
| 1 | Idempotency | `cleanup_existing_agents()` only scans first page. >100 agents → duplicates missed. |
| 2 | Idempotency | Without `--force`, running twice creates duplicate agents. Old orchestrator in `agent_ids.json` becomes orphaned. |
| 3 | Orphaned resources | `--force` deletes old agents before creating new ones. Mid-way failure leaves half-created agents with no cleanup path. |
| 4 | No error handling | `create_agent()` calls have no try/except. 429 or network error crashes with uncaught exception. |
| 5 | Silent degradation | Empty `GRAPH_QUERY_API_URI` → agents created with `tools=[]`. Appear healthy but functionally useless. |
| 6 | Placeholder substitution | Missing env vars silently substituted as empty strings in OpenAPI specs. Invalid URLs propagate to agents. |

### 7.2 `scripts/create_runbook_indexer.py` / `create_tickets_indexer.py`

| # | Category | Issue |
|---|----------|-------|
| 1 | Code duplication | Near-identical copies. Bugs must be fixed twice. Should extract shared module. |
| 2 | False success | `transientFailure` → exit code 0 with `"✅ Indexing complete!"` even though items failed. |
| 3 | Missing env validation | Unset `AI_SEARCH_NAME` produces `https://None.search.windows.net` → cryptic DNS error. |
| 4 | Race on re-run | Running while indexer is active → `409 Conflict` on `run_indexer()`. |

### 7.3 `scripts/cosmos/provision_cosmos_gremlin.py`

| # | Category | Issue |
|---|----------|-------|
| 1 | Destructive default | Without `--no-clear`, `g.V().drop()` deletes all data. Interrupted mid-load = partial graph. |
| 2 | No upsert | `g.addV()` always creates new vertex. With `--no-clear`, duplicates created. |
| 3 | Insufficient retry | Max ~8s wait for 429. Cosmos Gremlin can require 30-60s. `Retry-After` header not parsed. |
| 4 | Sequential writes | Each vertex/edge loaded one-at-a-time. ~200 entities = minutes. No batching. |

---

## 8. FRONTEND FINDINGS

### 8.1 `frontend/src/hooks/useInvestigation.ts`

| # | Category | Issue |
|---|----------|-------|
| 1 | No abort on unmount | SSE connection never closed if component unmounts mid-stream. Leaks connection; React "setState on unmounted" warnings. |
| 2 | No reconnection | `onerror` throws, permanently closing connection. Transient network blip = investigation lost. |
| 3 | Unbounded step accumulation | `setSteps(prev => [...prev, data])` appends indefinitely. No max-steps limit. |
| 4 | Missing Content-Type validation | `onopen` checks `res.ok` but not `Content-Type: text/event-stream`. JSON error body parsed as empty SSE stream. |

### 8.2 `frontend/src/components/ErrorBanner.tsx`

| # | Category | Issue |
|---|----------|-------|
| 1 | Fragile classification | `message.includes('404')` matches anywhere — "Checked 404 nodes" misclassified. Should match HTTP status directly. |

### 8.3 `frontend/src/components/HealthDot.tsx`

| # | Category | Issue |
|---|----------|-------|
| 1 | Check once, never again | Health checked on mount only. Backend going down = green dot forever. |
| 2 | False positive | Only checks `r.ok`. Response body (degraded status) never inspected. |
| 3 | No timeout | `fetch('/health')` has no `AbortSignal`. Hung backend = perpetual gray "..." state. |

### 8.4 `frontend/src/components/LogStream.tsx`

| # | Category | Issue |
|---|----------|-------|
| 1 | No auth headers | Native `EventSource` doesn't support custom headers. Only works via Vite proxy. |
| 2 | Reconnection storm | `EventSource` auto-reconnects with no backoff. Backend down = rapid reconnection attempts. |
| 3 | No render batching | `MAX_LINES = 200` with `slice(-MAX_LINES)` creates new array on every event. 10 msgs/sec = 10 re-renders/sec. Should debounce. |

### 8.5 `frontend/vite.config.ts`

| # | Category | Issue |
|---|----------|-------|
| 1 | Hardcoded backend port | `target: 'http://localhost:8000'` hardcoded 5 times. Should use env var. |
| 2 | No production proxy | Proxy only works in dev mode. No production reverse proxy config exists. |

### 8.6 `frontend/package.json`

| # | Category | Issue |
|---|----------|-------|
| 1 | No tests | No `"test"` script. No testing framework. Zero test coverage. |
| 2 | No linting | No ESLint in devDependencies. |

---

## 9. INFRASTRUCTURE (BICEP) FINDINGS

| # | Category | Issue |
|---|----------|-------|
| 1 | Cosmos DB key exposed | Primary key exposed as Bicep output → visible in ARM deployment JSON and `azd` terminal output. Should use Key Vault. |
| 2 | ACR admin user enabled | Shared credential for image pull, never rotated. Should use managed identity-based ACR pull. |
| 3 | Hook shell mismatch | `azure.yaml` specifies `shell: sh` but hooks use bash features (`[[ ]]`, process substitution). Breaks on Ubuntu/Debian where `sh` → `dash`. |

---

## 10. CROSS-CUTTING CONCERNS

| # | Category | Issue |
|---|----------|-------|
| 1 | No request tracing | No correlation ID propagated through SSE. Concurrent alerts produce interleaved logs with no way to attribute. |
| 2 | No graceful shutdown | No lifespan handler to drain threads, send sentinels to SSE subscribers, or close SDK clients. `uvicorn --reload` sends SIGTERM = killed daemon threads = unfinished Azure runs. |
| 3 | Blocking I/O in async | `is_configured()` and `load_agents_from_file()` do sync file reads from async route handlers. Blocks event loop. |
| 4 | No structured error responses | Errors are SSE events with free-text messages. No error codes, no categories, no retry-after headers. |
| 5 | Data schema in 4+ places | `graph_schema.yaml`, Cosmos Gremlin loader, agent prompts, OpenAPI specs. Any change requires coordinated updates with no automated validation. |
| 6 | Pre-release SDK | `azure-ai-agents==1.2.0b6` is a beta pin. API surface may change at GA. No security patches picked up. |
| 7 | No tests anywhere | Zero test files across API, graph-query-api, frontend, scripts. All `dev-dependencies = []`. |

---

## Recommended Priority Actions

1. **Add auth + rate limiting** on `/api/alert` (prevents abuse and runaway spend)
2. **Add concurrency semaphore** (max parallel investigations = 3)
3. **Lazy-init `DefaultAzureCredential`** in graph-query-api config (unblocks mock mode)
4. **Fix thread-safety** on log subscriber sets (prevents `RuntimeError` crashes)
5. **Add input validation** (max alert length, required fields)
6. **Make provisioning idempotent with prerequisite checks** (each script validates its inputs exist)
7. **Fix daemon thread leak** (add cancellation token that stops SDK thread on SSE disconnect)
8. **Move Cosmos key to Key Vault** (or at minimum, don't expose via Bicep outputs)
9. **Add `CORS_ORIGINS` env var to graph-query-api** (production will fail without this)
