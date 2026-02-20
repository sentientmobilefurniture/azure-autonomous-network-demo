"""
Session model — persistent async investigation sessions.

Decouples investigation lifecycle from SSE connections. Each investigation
runs as a server-side session that persists independently of the frontend.
The UI can reconnect, poll, or browse investigations at any time.

See documentation/persistent.md §3.1 for the full design.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
import asyncio
import uuid
import threading


class SessionStatus(str, Enum):
    PENDING = "pending"              # Created but orchestrator not yet started
    IN_PROGRESS = "in_progress"      # Orchestrator thread is running
    COMPLETED = "completed"          # Final message received
    FAILED = "failed"                # Error or timeout
    CANCELLED = "cancelled"          # User-initiated cancellation


@dataclass
class Session:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    scenario: str = ""
    alert_text: str = ""
    status: SessionStatus = SessionStatus.PENDING
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    # Accumulated event log — survives client disconnects
    event_log: list[dict] = field(default_factory=list)

    # Extracted final data (populated on completion)
    steps: list[dict] = field(default_factory=list)
    diagnosis: str = ""
    run_meta: Optional[dict] = None
    error_detail: str = ""

    # Multi-turn support (see §13)
    thread_id: Optional[str] = None        # Foundry thread ID — persists across turns
    turn_count: int = 0                     # Each user→orchestrator exchange = 1 turn

    # Runtime (not persisted)
    _subscribers: list[asyncio.Queue] = field(
        default_factory=list, repr=False
    )
    _cancel_event: threading.Event = field(
        default_factory=threading.Event, repr=False
    )
    _idle_task: Optional[asyncio.Task] = field(default=None, repr=False)

    # Threading lock — protects _subscribers and event_log against
    # concurrent access from the orchestrator thread and asyncio loop.
    # Mirrors the LogBroadcaster pattern (log_broadcaster.py).
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    # The asyncio event loop — needed for thread-safe queue delivery.
    _loop: Optional[asyncio.AbstractEventLoop] = field(default=None, repr=False)

    def push_event(self, event: dict):
        """Append to log and fan out to all live SSE subscribers.

        Thread-safe: called from the orchestrator's background thread.
        Uses loop.call_soon_threadsafe() to safely enqueue to asyncio.Queues,
        matching the pattern in LogBroadcaster.broadcast().
        """
        with self._lock:
            self.event_log.append(event)
            self.updated_at = datetime.now(timezone.utc).isoformat()
            snapshot = list(self._subscribers)
        dead: list[asyncio.Queue] = []
        for q in snapshot:
            try:
                if self._loop is not None and self._loop.is_running():
                    self._loop.call_soon_threadsafe(q.put_nowait, event)
                else:
                    q.put_nowait(event)
            except (asyncio.QueueFull, RuntimeError):
                dead.append(q)
        if dead:
            with self._lock:
                for q in dead:
                    try:
                        self._subscribers.remove(q)
                    except ValueError:
                        pass

    def subscribe(self) -> tuple[list[dict], asyncio.Queue]:
        """Return (existing_events, live_queue) for SSE replay + tail.

        Atomic: snapshot and subscriber registration happen under the same
        lock, so no event can fall between the snapshot and the queue.
        """
        loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        with self._lock:
            if self._loop is None:
                self._loop = loop
            snapshot = list(self.event_log)
            self._subscribers.append(q)
        return snapshot, q

    def unsubscribe(self, q: asyncio.Queue):
        with self._lock:
            try:
                self._subscribers.remove(q)
            except ValueError:
                pass

    def to_dict(self) -> dict:
        """Serialise for API response / Cosmos persistence."""
        return {
            "id": self.id,
            "scenario": self.scenario,
            "alert_text": self.alert_text,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "event_log": self.event_log,
            "steps": self.steps,
            "diagnosis": self.diagnosis,
            "run_meta": self.run_meta,
            "error_detail": self.error_detail,
            "thread_id": self.thread_id,
            "turn_count": self.turn_count,
        }
