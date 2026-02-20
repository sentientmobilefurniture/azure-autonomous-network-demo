# Fabric Capacity Stability & 429 Mitigation

## Objective

Eliminate Fabric API 429 errors caused by uncontrolled concurrency against an F8 capacity. Implement application-level throttling, circuit breaking, and retry rationalization to stay within Fabric's CU budget. Optionally right-size the capacity SKU.

---

## Current State

- **Capacity SKU:** F8 (8 Compute Units)
- **Graph backend:** Fabric GQL (Interactive operations, ~5-min smoothing)
- **Telemetry backend:** Fabric KQL via Eventhouse
- **Eventhouse background cost:** Continuous `Eventhouse UpTime` CU consumption from the same F8 (Background operation)
- **Topology source:** `static` (no live Fabric queries for topology)
- **Max concurrent sessions:** 20 (hardcoded, not configurable)
- **Concurrency control on Fabric calls:** None
- **Circuit breaker:** None
- **Retry policy:** 8 retries with linearly increasing backoff (15s × attempt)
- **Health check KQL:** Creates new `FabricKQLBackend()` on every invocation (does not reuse singleton)
- **Fabric discovery:** Synchronous `get_token()` blocks event loop on cache miss

---

## Fabric Throttling Model

Source: [Fabric throttling policy](https://learn.microsoft.com/en-us/fabric/enterprise/throttling)

Fabric measures usage in Compute Unit seconds (CU·s). Each SKU has a fixed CU rate. Throttling is progressive based on how far ahead future CU budget has been consumed:

| Overage Window | Effect |
|---|---|
| ≤ 10 min | No throttling (overage protection) |
| 10–60 min | Interactive operations delayed 20s at submission |
| 60 min–24 hr | Interactive operations **rejected** (429) |
| > 24 hr | All requests rejected |

### Key mechanics

- **Bursting:** Operations can temporarily exceed provisioned CU. Fabric does not slow them down — it charges CU after the fact.
- **Smoothing:** CU cost is spread across future 30-second timepoints. Interactive ops smooth over 5–64 minutes. Background ops smooth over 24 hours.
- **Carryforward:** When smoothed CU exceeds available capacity per timepoint, the excess carries forward. Burndown occurs only when future timepoints have idle capacity.
- **Interactive vs Background classification:** GQL Graph Model queries (`executeQuery`) are classified as **Interactive** (per [Fabric operations](https://learn.microsoft.com/en-us/fabric/enterprise/fabric-operations), under "Fabric API for GraphQL"). This means minimal smoothing and early throttling.

### GQL CU rate

Per the Fabric operations page: “Each GraphQL request and response operation processing time is reported in Capacity Units (CUs) in seconds at the rate of ten CUs per hour.” Each GQL call costs `10 CU × (processing_seconds / 3600)`. For a typical 1–5s query: 0.003–0.014 CU per call. Cost is processing-time proportional — complex queries or cold-start retries that take 10+ seconds cost more.

### F8 budget arithmetic

- F8 = 8 CU/s
- 10-min overage window = 8 × 600 = 4,800 CU before throttling triggers
- 60-min rejection window = 8 × 3,600 = 28,800 CU before 429s start
- Burndown rate: only idle timepoints reduce carryforward. On F8, burndown is slow.
- **Eventhouse baseline tax:** The Eventhouse continuously consumes CU via `Eventhouse UpTime` (Background). If it consumes even 1 CU/s continuously, that’s 12.5% of the F8’s total capacity eaten before any queries run.
- **Effective headroom** is 4,800 CU minus whatever the Eventhouse baseline has already consumed in the 10-minute window.

---

## Diagnosis: Why 429s Occur

### 1. No concurrency control

All Fabric API call paths flow through without any semaphore, queue, or admission control:

| File | Issue |
|---|---|
| `graph-query-api/backends/fabric.py` — `execute_query()` | No concurrency limit. Any number of async callers enter simultaneously. |
| `graph-query-api/backends/fabric_kql.py` — `execute_query()` | Same — no limit. |
| `graph-query-api/backends/__init__.py` | Backend instances are cached singletons (connection reuse is correct), but `_backend_lock` guards only cache creation, not query concurrency. |
| `api/app/session_manager.py` | `MAX_ACTIVE_SESSIONS = 20` caps sessions, not Fabric calls. Each session's orchestrator dispatches sub-agents independently. |

**Worst case:** 20 sessions × 2 Fabric-calling sub-agents (GraphExplorer + Telemetry) × iterative multi-query tool calls = 40+ concurrent Fabric requests against 8 CU.

### 2. Retry amplification

`backends/fabric.py` lines 105–175:

```python
max_retries = 8
# On 429: wait = 15 * (attempt + 1) → 15s, 30s, 45s, 60s, 75s, 90s, 105s, 120s
```

Problems:
- Each request enters its own retry loop (up to ~8.5 minutes total)
- New requests keep arriving and start their own loops — CU debt compounds
- Token re-acquired on every retry (unnecessary; tokens valid ~60 min)
- `Retry-After` header from Fabric's 429 response is ignored
- Orchestrator adds another layer: `MAX_RUN_ATTEMPTS = 2` re-dispatches all sub-agents on failure, doubling load

### 3. Topology fan-out (latent risk)

When `TOPOLOGY_SOURCE=live`, `FabricGQLBackend.get_topology()` fires 7 sequential GQL queries (one per `_TOPOLOGY_SCHEMA` relationship type). With retry cascading: 7 × 8 = 56 potential Fabric API calls from one topology request. Currently mitigated by `TOPOLOGY_SOURCE=static` but would be catastrophic if changed on F8.

### 4. Fabric discovery TTL and event-loop blocking

`fabric_discovery.py` caches workspace discovery for 10 minutes (`FABRIC_DISCOVERY_TTL=600`). Each refresh calls 2 Fabric REST APIs. Negligible CU impact (management-plane calls don’t consume F8 data-plane CU), but:

- `_get_fabric_token()` at `fabric_discovery.py:84` uses **synchronous** `cred.get_token()` without `asyncio.to_thread()`. When called from a FastAPI route handler (via `get_scenario_context()` → `get_fabric_config()`), this **blocks the event loop** for the token acquisition duration.
- `_discover_fabric_config()` uses **synchronous** `httpx.get()` (not `httpx.AsyncClient`), further blocking the event loop on cache miss.
- On cache miss (every 600s, or after manual `invalidate_cache()`), all in-flight async requests stall behind the blocking discovery call.

### 5. Health check KQL backend leak

`router_health.py:57` — `_ping_telemetry_backend()` creates a **new** `FabricKQLBackend()` on **every** health check invocation. This instantiates a new `KustoClient` (new connection, new auth setup) each time, rather than reusing the module-level singleton from `router_telemetry.py:25`. This wastes connection setup time, may cause connection leaks, and adds unnecessary token acquisitions.

### 6. Eventhouse background CU consumption

Per the [Fabric operations](https://learn.microsoft.com/en-us/fabric/enterprise/fabric-operations) page, `Eventhouse UpTime` is a **Background** operation charged continuously while the Eventhouse is active. This baseline CU consumption comes from the same F8 capacity budget, reducing headroom available for Interactive GQL operations. The exact CU rate is configuration-dependent but is non-trivial on a small F8.

### 7. External capacity consumers

The F8 capacity is **shared** across the entire Fabric workspace. Any of the following consume CU from the same pool, invisible to the application:

- Power BI reports connected to the Lakehouse or Eventhouse
- Fabric portal browsing/previewing workspace items
- Other users running queries in Fabric Notebook or KQL Queryset editors
- OneLake read/write operations from any source
- Lakehouse table previews

During demos or troubleshooting, a developer previewing data in Fabric portal adds to the CU load and can push the capacity into throttling territory independently.

### 8. Token re-acquisition overhead (corrected)

`backends/fabric.py` re-acquires tokens on every retry (lines 128, 143, 168). While `DefaultAzureCredential.get_token()` has internal MSAL caching that short-circuits if the token isn’t expired, the overhead is still real: each call incurs `asyncio.to_thread()` scheduling plus MSAL cache-check latency (~50-100ms). Across 8 retries × N concurrent requests, this adds up. The primary waste is latency, not CU.

---

## All Code Paths That Hit Fabric

### Fabric GQL (Graph Model REST API)

Endpoint: `POST /workspaces/{id}/GraphModels/{model_id}/executeQuery?beta=true`

| Route | Caller | Queries/call |
|---|---|---|
| `POST /query/graph` | `router_graph.py` → `backend.execute_query()` | 1 |
| `POST /query/topology` (live mode only) | `router_topology.py` → `backend.get_topology()` | 7 |
| `POST /query/replay` (GraphExplorerAgent) | `router_replay.py` → `query_graph()` | 1 |
| `GET /query/health/sources` | `router_health.py` → `backend.ping()` | 1 |

### Fabric KQL (Eventhouse)

Endpoint: Kusto client `execute()` against Eventhouse query URI.

| Route | Caller | Queries/call |
|---|---|---|
| `POST /query/telemetry` | `router_telemetry.py` → `_kql_backend.execute_query()` | 1 |
| `POST /query/replay` (TelemetryAgent) | `router_replay.py` → `query_telemetry()` | 1 |
| `GET /query/health/sources` | `router_health.py` → `FabricKQLBackend().ping()` | 1 |

**Bug:** The KQL health path instantiates a new `FabricKQLBackend()` each call (`router_health.py:57`), unlike the GQL path which reuses the cached singleton via `get_backend_for_graph()`. This should reuse the module-level `_kql_backend` from `router_telemetry.py`.

### Fabric REST API (Discovery)

| Trigger | Calls |
|---|---|
| Startup / 10-min cache expiry | `GET /workspaces/{id}/items` + `GET /workspaces/{id}/kqlDatabases/{id}` |
| Manual rediscovery | Same 2 calls |

### Routes that do NOT hit Fabric

- `POST /query/search` → Azure AI Search
- `GET/POST/DELETE /query/interactions` → Cosmos DB
- `POST /query/topology` when `TOPOLOGY_SOURCE=static` → local JSON file

---

## Implementation Plan

Each fix below is a self-contained unit of work. Ordered by impact. Each specifies the exact mechanism, target files, env var controls, and code structure to implement.

Pattern references:
- [Azure Architecture — Circuit Breaker pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/circuit-breaker)
- [Azure Architecture — Retry pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/retry)
- [Azure Architecture — Throttling pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/throttling)

---

### Fix 1 (P0): Shared Fabric throttle gate — `FabricThrottleGate`

**Problem:** No concurrency control and no circuit breaker. They must be solved together as a single shared module.

**Solution:** Create a new module `graph-query-api/backends/fabric_throttle.py` containing a `FabricThrottleGate` class. Both `FabricGQLBackend` and `FabricKQLBackend` use the same singleton gate instance. This ensures the total concurrent Fabric load across both backends is bounded by one shared semaphore and one shared circuit breaker.

**Target file (new):** `graph-query-api/backends/fabric_throttle.py`

#### Mechanism: Concurrency semaphore

- Shared `asyncio.Semaphore` limits total in-flight Fabric API calls across GQL + KQL.
- Default: 3 concurrent calls. Controlled by `FABRIC_MAX_CONCURRENT` env var.
- When full, callers queue behind the semaphore (not rejected). This converts uncontrolled burst into serialized pressure.
- F8 with 3 concurrent = at most 3 queries accumulating CU at any moment. This is sustainable.

#### Mechanism: Three-state circuit breaker

States: **Closed** → **Open** → **Half-Open** → Closed (per Azure Architecture guidance).

| State | Behavior |
|---|---|
| **Closed** | Requests pass through semaphore normally. Track consecutive 429 count. |
| **Open** | All new requests immediately rejected with HTTP 503 + `Retry-After` header. No Fabric API calls made. Timer starts. |
| **Half-Open** | After cooldown expires, allow 1 probe request through. If it succeeds → Closed. If 429 → back to Open with extended cooldown. |

Transition rules:
- Closed → Open: `FABRIC_CB_THRESHOLD` consecutive 429s (default: 3).
- Open → Half-Open: after `FABRIC_CB_COOLDOWN` seconds (default: 60). Cooldown doubles on each re-trip, capped at 300s.
- Half-Open → Closed: 1 successful request.
- Half-Open → Open: 1 failed request (429/5xx).
- Any non-429/non-5xx response resets the consecutive failure counter.

```python
# graph-query-api/backends/fabric_throttle.py

import asyncio
import logging
import os
import time
from enum import Enum

logger = logging.getLogger("graph-query-api.fabric-throttle")


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half-open"


class FabricThrottleGate:
    """Shared concurrency semaphore + circuit breaker for all Fabric API calls.

    Singleton — use get_fabric_gate() to obtain the instance.
    Thread-safe via asyncio primitives.
    """

    def __init__(self):
        max_concurrent = int(os.getenv("FABRIC_MAX_CONCURRENT", "3"))
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._threshold = int(os.getenv("FABRIC_CB_THRESHOLD", "3"))
        self._base_cooldown = float(os.getenv("FABRIC_CB_COOLDOWN", "60"))
        self._max_cooldown = 300.0

        self._state = CircuitState.CLOSED
        self._consecutive_429s = 0
        self._open_until = 0.0
        self._current_cooldown = self._base_cooldown
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        return self._state

    async def acquire(self) -> None:
        """Acquire permission to make a Fabric API call.

        Raises HTTPException(503) if circuit is open.
        Blocks if semaphore is full (queues behind other callers).
        """
        from fastapi import HTTPException

        async with self._lock:
            if self._state == CircuitState.OPEN:
                if time.monotonic() >= self._open_until:
                    # Transition to half-open — allow one probe
                    self._state = CircuitState.HALF_OPEN
                    logger.info("Circuit breaker → HALF_OPEN (cooldown expired)")
                else:
                    remaining = int(self._open_until - time.monotonic())
                    raise HTTPException(
                        status_code=503,
                        detail=f"Fabric capacity overloaded — circuit breaker open. "
                               f"Retry in {remaining}s.",
                        headers={"Retry-After": str(remaining)},
                    )

        # Semaphore: block if at max concurrency (queuing, not rejecting)
        await self._semaphore.acquire()

    def release(self) -> None:
        """Release the semaphore slot after a Fabric API call completes."""
        self._semaphore.release()

    async def record_success(self) -> None:
        """Record a successful Fabric API response (non-429, non-5xx)."""
        async with self._lock:
            self._consecutive_429s = 0
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED
                self._current_cooldown = self._base_cooldown
                logger.info("Circuit breaker → CLOSED (probe succeeded)")

    async def record_429(self) -> None:
        """Record a 429 response. May trip the circuit."""
        async with self._lock:
            self._consecutive_429s += 1
            if self._state == CircuitState.HALF_OPEN:
                # Probe failed — back to open with extended cooldown
                self._current_cooldown = min(
                    self._current_cooldown * 2, self._max_cooldown
                )
                self._open_until = time.monotonic() + self._current_cooldown
                self._state = CircuitState.OPEN
                logger.warning(
                    "Circuit breaker → OPEN (half-open probe failed, "
                    "cooldown=%.0fs)", self._current_cooldown
                )
            elif self._consecutive_429s >= self._threshold:
                self._open_until = time.monotonic() + self._current_cooldown
                self._state = CircuitState.OPEN
                logger.warning(
                    "Circuit breaker → OPEN (%d consecutive 429s, "
                    "cooldown=%.0fs)",
                    self._consecutive_429s, self._current_cooldown
                )

    async def record_server_error(self) -> None:
        """Record a 5xx that isn't ColdStartTimeout. Treat like 429 for circuit."""
        await self.record_429()

    def status(self) -> dict:
        """Return current gate status for health/debug endpoints."""
        return {
            "state": self._state.value,
            "consecutive_429s": self._consecutive_429s,
            "cooldown_s": self._current_cooldown,
            "open_until": self._open_until,
            "semaphore_available": self._semaphore._value,
        }


# Module-level singleton
# NOTE: Safe without lock because asyncio runs a single event loop per process.
# If using multiple workers (e.g., gunicorn with --workers > 1), each worker
# gets its own singleton — which is correct (each has its own event loop).
_gate: FabricThrottleGate | None = None


def get_fabric_gate() -> FabricThrottleGate:
    """Return the singleton FabricThrottleGate."""
    global _gate
    if _gate is None:
        _gate = FabricThrottleGate()
    return _gate
```

#### Integration into `FabricGQLBackend.execute_query()`

Wrap the entire request-retry body:

```python
from backends.fabric_throttle import get_fabric_gate

async def execute_query(self, query: str, **kwargs) -> dict:
    gate = get_fabric_gate()
    await gate.acquire()
    try:
        return await self._execute_query_inner(query, **kwargs)
    finally:
        gate.release()
```

Inside `_execute_query_inner`, after each response:
- On 429: call `await gate.record_429()` before sleeping/retrying.
- On success (200 with valid data): call `await gate.record_success()`.
- On 5xx (non-ColdStartTimeout): call `await gate.record_server_error()`.

#### Integration into `FabricKQLBackend.execute_query()`

Same pattern — acquire/release around the `asyncio.to_thread(client.execute, ...)` call. The KQL backend currently has no retry loop, so the gate only controls concurrency. If the KQL call fails with a capacity error, call `gate.record_server_error()`.

#### Env vars

| Var | Default | Purpose |
|---|---|---|
| `FABRIC_MAX_CONCURRENT` | `3` | Max in-flight Fabric API calls (GQL + KQL combined) |
| `FABRIC_CB_THRESHOLD` | `3` | Consecutive 429s to trip circuit |
| `FABRIC_CB_COOLDOWN` | `60` | Initial cooldown seconds when circuit opens |

---

### Fix 2 (P0): Retry rationalization

**Problem:** 8 retries with linear backoff (15s × attempt), no jitter, ignores `Retry-After` header, re-acquires token on every retry.

**Solution:** Replace with exponential backoff + jitter, respect `Retry-After`, differentiate 429 retries from cold-start retries, cache token across retries.

**Target file:** `graph-query-api/backends/fabric.py`

#### Retry strategy by error type

| Error | Max retries | Backoff | Rationale |
|---|---|---|---|
| HTTP 429 | 2 | `Retry-After` header, or 30s default + jitter | Circuit breaker handles sustained 429s. Retries here are a brief courtesy. |
| ColdStartTimeout (500) | 5 | Exponential: 10s, 20s, 40s, 60s, 60s + jitter | Cold start is transient; graph engine needs time. Worth waiting. |
| Status 02000 (continuation) | 5 | Fixed 10s | Continuation token — not a failure, just data loading. |
| Other 5xx | 0 | Fail immediately | Non-transient server error. Surface to caller. |

#### Jitter

Add ±25% random jitter to all backoff durations. Prevents thundering herd when multiple retries align. Implementation: `wait *= random.uniform(0.75, 1.25)`.

#### `Retry-After` header

On 429, read `response.headers.get("Retry-After")`. Parse as integer seconds. If present and ≤ 120s, use it. Otherwise fall back to default 30s.

#### Token caching across retries

Acquire token once before the retry loop. Only re-acquire if the retry was caused by a 401 (token expired) or if > 50 minutes have elapsed since acquisition. `DefaultAzureCredential.get_token()` returns tokens valid for ~60 min; re-acquiring on every retry is wasteful and adds latency.

```python
# Pseudocode for the new retry structure in execute_query

import random

gate = get_fabric_gate()
await gate.acquire()

try:
    token = await self._get_token()
    token_acquired_at = time.monotonic()

    for attempt in range(max_attempts):
        response = await client.post(url, json=payload, headers=...)

        if response.status_code == 200:
            body = response.json()
            status_code = body.get("status", {}).get("code", "")

            if status_code == "02000" and body.get("result", {}).get("nextPage"):
                # Cold-start continuation — not a failure
                continuation_token = body["result"]["nextPage"]
                await asyncio.sleep(10)
                continue

            await gate.record_success()
            return normalize(body)

        if response.status_code == 429:
            await gate.record_429()
            if attempt >= MAX_429_RETRIES:
                raise HTTPException(429, "Fabric capacity exhausted")
            retry_after = _parse_retry_after(response, default=30)
            wait = retry_after * random.uniform(0.75, 1.25)
            await asyncio.sleep(wait)
            continue

        if response.status_code == 500:
            body = _try_parse_json(response)
            if body.get("errorCode") == "ColdStartTimeout":
                wait = min(10 * (2 ** attempt), 60) * random.uniform(0.75, 1.25)
                await asyncio.sleep(wait)
                # Re-acquire token only if stale
                if time.monotonic() - token_acquired_at > 3000:
                    token = await self._get_token()
                    token_acquired_at = time.monotonic()
                continue
            await gate.record_server_error()
            raise HTTPException(response.status_code, response.text[:500])

        # Any other non-200 — fail immediately
        raise HTTPException(response.status_code, response.text[:500])

    raise HTTPException(503, "Fabric retries exhausted")
finally:
    gate.release()
```

---

### Fix 3 (P0): Orchestrator retry awareness

**Problem:** `MAX_RUN_ATTEMPTS = 2` in `orchestrator.py` (lines 512 and 1097 — both `run_orchestrator` and `run_orchestrator_session`) retries the entire orchestrator run when any sub-agent tool call fails. If the failure was a Fabric 429/503, retrying immediately doubles the Fabric load. This is the most direct doubling vector — the gate queues individual calls, but the orchestrator creates an entirely new wave of legitimate calls that enter the gate queue.

**Solution:** Before retrying, inspect `handler.run_error_detail`. If it contains capacity-related markers, skip the retry entirely. Apply to both `run_orchestrator()` and `run_orchestrator_session()`.

**Target file:** `api/app/orchestrator.py`

```python
def _is_capacity_error(error_text: str) -> bool:
    """Check if an error message indicates Fabric capacity exhaustion."""
    capacity_markers = [
        "429", "capacity", "circuit breaker", "throttl",
        "Fabric capacity", "too many requests", "503",
    ]
    lower = error_text.lower()
    return any(m.lower() in lower for m in capacity_markers)

# In the retry decision block (BOTH functions):
if handler.run_failed:
    last_error_detail = handler.run_error_detail
    if _is_capacity_error(last_error_detail):
        logger.warning("Skipping orchestrator retry — Fabric capacity error: %s", last_error_detail[:200])
        error_emitted = True
        _put("error", {
            "message": f"Investigation stopped — Fabric capacity exhausted. {total_steps} steps completed.\n\n{last_error_detail}"
        })
        break  # Do not retry
    elif attempt < MAX_RUN_ATTEMPTS:
        # Only retry for non-capacity errors
        continue
```

**Why P0:** Without this, a single Fabric 429 during an investigation triggers a full re-run of all sub-agents. The throttle gate (Fix 1) limits individual query concurrency but cannot prevent the orchestrator from generating a legitimate second wave of queries that queue behind the semaphore. This is the highest-impact fix after the gate itself.

---

### Fix 4 (P1): Session concurrency cap

**Problem:** `MAX_ACTIVE_SESSIONS = 20` allows up to 40+ concurrent Fabric requests. On F8, this is unmanageable even with the semaphore (requests queue for too long).

**Solution:** Make `MAX_ACTIVE_SESSIONS` env-configurable and tie the default to the capacity tier. Lower the hardcoded default to 8.

**Target file:** `api/app/session_manager.py`

```python
# Replace:
MAX_ACTIVE_SESSIONS = 20

# With:
import os
MAX_ACTIVE_SESSIONS = int(os.getenv("MAX_ACTIVE_SESSIONS", "8"))
```

Guidance by SKU:

| SKU | Recommended `MAX_ACTIVE_SESSIONS` |
|---|---|
| F8 | 5 |
| F16 | 8 |
| F32 | 12 |
| F64+ | 20 |

**Note:** This limits new sessions but does not prevent existing sessions from escalating load via multi-turn follow-ups (`continue_session()`). For F8, consider also adding a per-session Fabric call counter that surfaces a warning after N Fabric calls in a single session.

---

### Fix 5 (P1): Health check caching + KQL singleton fix

**Problem:** `GET /query/health/sources` fires a GQL ping + KQL ping on every invocation. During active use, repeated health checks consume CU from the already-constrained budget.

**Solution:** Cache health check results per-source with a TTL. Return cached results within the window; only probe Fabric when cache expires.

**Target file:** `graph-query-api/router_health.py`

#### Mechanism

```python
import time

_health_cache: dict[str, tuple[float, dict]] = {}  # key → (expires_at, result)
HEALTH_CACHE_TTL = float(os.getenv("HEALTH_CACHE_TTL", "30"))  # seconds

async def _cached_ping(key: str, ping_fn) -> dict:
    """Return cached ping result or execute ping_fn and cache."""
    now = time.time()
    cached = _health_cache.get(key)
    if cached and now < cached[0]:
        result = cached[1].copy()
        result["cached"] = True
        return result
    result = await ping_fn()
    _health_cache[key] = (now + HEALTH_CACHE_TTL, result)
    return result
```

Apply to both `_ping_graph_backend()` and `_ping_telemetry_backend()`.

Also:
- **Fix the KQL singleton leak:** Replace `FabricKQLBackend()` in `_ping_telemetry_backend()` with a reused module-level singleton. Import and reuse from `router_telemetry._kql_backend`, or create a shared singleton at module level:

```python
# router_health.py — at module level:
from backends.fabric_kql import FabricKQLBackend
_kql_singleton = FabricKQLBackend()  # reuse across all health checks

# In _ping_telemetry_backend():
async def _ping_telemetry_backend(connector: str, config: dict) -> dict:
    if connector == "fabric-kql":
        return await _kql_singleton.ping()
    ...
```

- Expose the `FabricThrottleGate.status()` in the health endpoint response so the frontend can show circuit breaker state.

---

### Fix 6 (P1): Fabric discovery async conversion

**Problem:** `fabric_discovery.py:84` calls `cred.get_token()` synchronously, and `_discover_fabric_config()` uses synchronous `httpx.get()`. When `get_fabric_config()` is called from a FastAPI route handler (via `get_scenario_context()`), a cache miss blocks the entire event loop for seconds.

**Solution:** Convert the discovery path to use `asyncio.to_thread()` for the blocking calls, or make `get_fabric_config()` cache-only in the hot path and run discovery in a background task.

**Target file:** `graph-query-api/fabric_discovery.py`

**Option A (minimal change):** Wrap the synchronous discovery in `asyncio.to_thread()` at the call site:

```python
# In config.py — get_scenario_context():
async def get_scenario_context() -> ScenarioContext:
    from fabric_discovery import get_fabric_config
    cfg = await asyncio.to_thread(get_fabric_config)  # don't block the event loop
    return ScenarioContext(...)
```

This requires changing `get_scenario_context()` to `async` and updating all callers (3 sites: `router_graph.py`, `router_topology.py`, `router_telemetry.py`).

**Option B (recommended, simpler):** Pre-warm the discovery cache at startup so the hot path never misses:

```python
# main.py — in _lifespan:
from fabric_discovery import get_fabric_config
await asyncio.to_thread(get_fabric_config)  # warm cache at startup
```

With a 600s TTL, cache misses are rare (once per 10 minutes). Option B avoids changing the sync interface and covers the startup case. For runtime cache refreshes, the 600s TTL means the event loop blocks for 1–3 seconds every 10 minutes — acceptable for this workload.

**Tradeoff:** Option A is technically correct but invasive (async propagation). Option B is pragmatic — cache misses are rare and bounded.

---

### Fix 7 (P2): Topology live-mode guard

**Problem:** `TOPOLOGY_SOURCE=live` triggers 7 GQL queries per topology request. On small capacities this is catastrophic.

**Solution:** At startup, if `TOPOLOGY_SOURCE=live` and `FABRIC_CAPACITY_SKU` is below F32, log a warning and override to `static`. Add a comment in `azure_config.env`.

**Target file:** `graph-query-api/config.py`

```python
# After TOPOLOGY_SOURCE is read:
_sku = os.getenv("FABRIC_CAPACITY_SKU", "F8")
_sku_num = int("".join(filter(str.isdigit, _sku)) or "8")
if TOPOLOGY_SOURCE == "live" and _sku_num < 32:
    logger.warning(
        "TOPOLOGY_SOURCE=live is not supported on %s (< F32). "
        "Overriding to 'static'.", _sku
    )
    TOPOLOGY_SOURCE = "static"
```

---

### Fix 8 (P2): Capacity scaling and emergency recovery

These are infrastructure-level actions, not code changes.

#### Scale the SKU

Change `FABRIC_CAPACITY_SKU` in `azure_config.env` and redeploy via `azd up`, or resize directly in the Azure portal. F16 (2× CU) is the minimum recommended for this workload under any concurrent usage.

| SKU | CUs | 10-min headroom | Annual cost (approx, East US) |
|---|---|---|---|
| F8 | 8 | 4,800 CU | ~$6,200 |
| F16 | 16 | 9,600 CU | ~$12,400 |
| F32 | 32 | 19,200 CU | ~$24,800 |
| F64 | 64 | 38,400 CU | ~$49,600 |

Scaling up/down takes effect near-instantly for SKUs ≤ F256.

#### Emergency throttle recovery: pause/resume

If the capacity is deeply throttled (carryforward > 24h), a pause/resume cycle clears all CU debt immediately. Automate with Azure Runbooks or CLI:

```bash
# Pause (clears carryforward, stops billing for new compute)
az rest --method post \
  --url "https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.Fabric/capacities/{name}/suspend?api-version=2023-11-01"

# Resume (starts fresh with zero CU debt)
az rest --method post \
  --url "https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.Fabric/capacities/{name}/resume?api-version=2023-11-01"
```

Caution: pausing makes all workspace content inaccessible until resumed.

#### Scheduled scaling via Azure Automation

Create an Azure Runbook that scales up to F16/F32 at start of business hours and back to F8 after hours. This optimizes cost while providing headroom during active demo/usage periods.

---

---

## Edge Cases and Implementation Risks

These risks must be addressed during implementation of the fixes above.

### 1. Semaphore starvation during circuit half-open transition

When the circuit transitions from Open → Half-Open, one probe request is allowed. But the semaphore may have queued waiters from before the circuit opened. A queued waiter (not the intended probe) could acquire the semaphore first, fail, and re-trip the circuit before the actual probe runs.

**Mitigation:** In Half-Open state, the probe request should bypass the semaphore. Add a `_half_open_bypass` flag that lets one request skip `_semaphore.acquire()`. Reset the flag after the probe completes.

> **⚠ IMPLEMENTATION NOTE:** The `FabricThrottleGate` code in Fix 1 does NOT yet implement this bypass. Add `_half_open_probe_allowed: bool` to `__init__`, set it to `True` on Open→Half-Open transition, and check it in `acquire()` to skip the semaphore for the first caller. Reset to `False` after that caller proceeds.

### 2. Race between circuit state check and semaphore acquisition

In `acquire()`, the lock is released after the state check but before `_semaphore.acquire()`. Between those two operations, another task could trip the circuit to Open. The acquiring task would then hold a semaphore slot while the circuit is open.

**Mitigation:** After acquiring the semaphore, re-check circuit state. If it changed to Open, release the semaphore and raise 503. This is a double-check pattern.

> **⚠ IMPLEMENTATION NOTE:** The `acquire()` method in Fix 1 does NOT yet implement this double-check. Add `async with self._lock:` after `await self._semaphore.acquire()` to re-check `self._state`. If `OPEN`, call `self._semaphore.release()` and raise 503.

### 3. KQL gate holding during blocking I/O

KQL queries use `asyncio.to_thread(client.execute, ...)`. The semaphore slot is held for the entire blocking duration (potentially seconds for large result sets). This reduces throughput for GQL calls that share the same semaphore.

**Mitigation:** Consider whether a split concurrency model is better: e.g., `FABRIC_MAX_CONCURRENT_GQL=3` and `FABRIC_MAX_CONCURRENT_KQL=2` (separate semaphores) with a shared circuit breaker. The single-semaphore model is simpler and sufficient for F8; evaluate split model if scaling to F32+.

### 4. In-flight sessions during capacity exhaustion

Reducing `MAX_ACTIVE_SESSIONS` prevents new sessions but does not limit existing sessions. A session using multi-turn follow-ups (`continue_session()`) can generate unlimited Fabric calls. The throttle gate queues them, but the queue can grow unbounded.

**Mitigation:** Add a per-session Fabric call counter. After N calls (configurable, default 50), emit a warning event to the SSE stream. After 2N, refuse further Fabric calls for that session and surface a "capacity budget exhausted for this investigation" message.

### 5. Frontend during circuit-open state

When Fix 1 is active and the circuit opens, all Fabric-dependent routes return 503. The frontend currently has no handling for 503 — it treats all errors the same.

**Mitigation:** Expose `FabricThrottleGate.status()` in the health endpoint. The frontend can check gate state and display a capacity warning banner ("Fabric is overloaded — investigations may fail") instead of showing cryptic errors.

---

### Summary: Env vars introduced

| Var | Default | File | Purpose |
|---|---|---|---|
| `FABRIC_MAX_CONCURRENT` | `3` | `backends/fabric_throttle.py` | Max in-flight Fabric calls (GQL + KQL) |
| `FABRIC_CB_THRESHOLD` | `3` | `backends/fabric_throttle.py` | Consecutive 429s to trip circuit |
| `FABRIC_CB_COOLDOWN` | `60` | `backends/fabric_throttle.py` | Initial open-state cooldown (seconds) |
| `MAX_ACTIVE_SESSIONS` | `8` | `api/app/session_manager.py` | Max concurrent orchestrator sessions |
| `HEALTH_CACHE_TTL` | `30` | `router_health.py` | Seconds to cache health probe results |

### Implementation order

1. `fabric_throttle.py` (new module — gate singleton)
2. `backends/fabric.py` (integrate gate + new retry logic)
3. `backends/fabric_kql.py` (integrate gate)
4. `api/app/orchestrator.py` (capacity-aware retry skip — **P0, do immediately after gate**)
5. `api/app/session_manager.py` (env-configurable session cap)
6. `router_health.py` (cached pings + KQL singleton fix + gate status)
7. `fabric_discovery.py` / `config.py` (async discovery + topology guard)

Steps 1–4 are **P0** and should be deployed together as a single release.
Steps 5–7 are **P1/P2** and can follow incrementally.

---

## Monitoring

Install the [Fabric Capacity Metrics app](https://learn.microsoft.com/en-us/fabric/enterprise/metrics-app) to:
- View per-operation CU consumption (identify which GQL queries cost the most)
- See throttling events and burndown timelines
- Drill into 30-second timepoints to correlate spikes with app activity
- Use the Overages tab to see 10-min, 60-min, and 24-hr overage charts

The app requires capacity admin role and refreshes data within 10–15 minutes of activity.

---

## Reference Links

- [Fabric throttling policy](https://learn.microsoft.com/en-us/fabric/enterprise/throttling)
- [Fabric operations (Interactive vs Background)](https://learn.microsoft.com/en-us/fabric/enterprise/fabric-operations)
- [Capacity SKUs and CU table](https://learn.microsoft.com/en-us/fabric/enterprise/licenses#capacity)
- [Scale capacity](https://learn.microsoft.com/en-us/fabric/enterprise/scale-capacity)
- [Pause/resume capacity](https://learn.microsoft.com/en-us/fabric/enterprise/pause-resume)
- [Capacity Metrics app](https://learn.microsoft.com/en-us/fabric/enterprise/metrics-app)
- [GraphQL API limits](https://learn.microsoft.com/en-us/fabric/data-engineering/api-graphql-limits)
- [Buy a Fabric subscription](https://learn.microsoft.com/en-us/fabric/enterprise/buy-subscription)
