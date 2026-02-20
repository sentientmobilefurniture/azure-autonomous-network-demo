"""
Shared Fabric throttle gate — concurrency semaphore + circuit breaker.

All Fabric API calls (GQL + KQL) must acquire/release through the singleton
FabricThrottleGate to bound total concurrent load against the shared Fabric
capacity (e.g. F8 = 8 CU).

Implements the Azure Architecture Circuit Breaker pattern:
  Closed → Open → Half-Open → Closed

See documentation/fabric_control.md for full design rationale.
"""

from __future__ import annotations

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
        self._half_open_probe_allowed = False

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
                    self._half_open_probe_allowed = True
                    logger.info("Circuit breaker → HALF_OPEN (cooldown expired)")
                else:
                    remaining = int(self._open_until - time.monotonic())
                    raise HTTPException(
                        status_code=503,
                        detail=f"Fabric capacity overloaded — circuit breaker open. "
                               f"Retry in {remaining}s.",
                        headers={"Retry-After": str(remaining)},
                    )

            # In half-open state, let the first caller bypass the semaphore
            # to act as the probe request (avoids semaphore starvation).
            if self._state == CircuitState.HALF_OPEN and self._half_open_probe_allowed:
                self._half_open_probe_allowed = False
                return  # probe bypasses semaphore

        # Semaphore: block if at max concurrency (queuing, not rejecting)
        await self._semaphore.acquire()

        # Double-check: if circuit tripped to OPEN while we waited for
        # the semaphore, release and reject.
        async with self._lock:
            if self._state == CircuitState.OPEN:
                self._semaphore.release()
                remaining = max(1, int(self._open_until - time.monotonic()))
                raise HTTPException(
                    status_code=503,
                    detail=f"Fabric capacity overloaded — circuit breaker open. "
                           f"Retry in {remaining}s.",
                    headers={"Retry-After": str(remaining)},
                )

    def release(self, *, was_probe: bool = False) -> None:
        """Release the semaphore slot after a Fabric API call completes.

        Args:
            was_probe: If True, the caller bypassed the semaphore (half-open
                       probe) and should NOT release it.
        """
        if not was_probe:
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


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
# Safe without lock because asyncio runs a single event loop per process.
# If using multiple workers (e.g., gunicorn with --workers > 1), each worker
# gets its own singleton — which is correct (each has its own event loop).

_gate: FabricThrottleGate | None = None


def get_fabric_gate() -> FabricThrottleGate:
    """Return the singleton FabricThrottleGate."""
    global _gate
    if _gate is None:
        _gate = FabricThrottleGate()
    return _gate
