"""
Reusable SSE log broadcast infrastructure.

Provides a LogBroadcaster class that handles:
  - Subscriber management (asyncio.Queue per client)
  - Thread-safe broadcast from logging handlers
  - Custom logging.Handler for integration
  - SSE generator for streaming to clients

Used by both api/app/routers/logs.py and graph-query-api/main.py
to avoid duplicating ~80 lines of identical broadcast code.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections import deque
from datetime import datetime, timezone
from typing import AsyncGenerator


class LogBroadcaster:
    """Fan-out log records to multiple SSE subscriber queues (thread-safe)."""

    def __init__(self, max_buffer: int = 100, max_queue: int = 500):
        self._lock = threading.Lock()
        self._subscribers: set[asyncio.Queue] = set()
        self._buffer: deque[dict] = deque(maxlen=max_buffer)
        self._max_queue = max_queue
        self._event_loop: asyncio.AbstractEventLoop | None = None

    def broadcast(self, record: dict) -> None:
        """Push a log record dict to every subscriber (thread-safe)."""
        with self._lock:
            self._buffer.append(record)
            snapshot = list(self._subscribers)
        dead: list[asyncio.Queue] = []
        for q in snapshot:
            try:
                if self._event_loop is not None and self._event_loop.is_running():
                    self._event_loop.call_soon_threadsafe(q.put_nowait, record)
                else:
                    q.put_nowait(record)
            except (asyncio.QueueFull, RuntimeError):
                dead.append(q)
        if dead:
            with self._lock:
                for q in dead:
                    self._subscribers.discard(q)

    async def subscribe(self) -> AsyncGenerator[str, None]:
        """Async generator yielding SSE-formatted log events."""
        self._event_loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue(maxsize=self._max_queue)
        with self._lock:
            buffered = list(self._buffer)
            self._subscribers.add(q)
        try:
            for rec in buffered:
                yield f"event: log\ndata: {json.dumps(rec)}\n\n"
            while True:
                rec = await q.get()
                yield f"event: log\ndata: {json.dumps(rec)}\n\n"
        finally:
            with self._lock:
                self._subscribers.discard(q)

    def get_handler(self, level: int = logging.INFO) -> logging.Handler:
        """Return a logging.Handler that broadcasts to this instance."""
        handler = _BroadcastHandler(self)
        handler.setLevel(level)
        return handler


class _BroadcastHandler(logging.Handler):
    """Logging handler that serialises records and broadcasts them."""

    def __init__(self, broadcaster: LogBroadcaster):
        super().__init__()
        self._broadcaster = broadcaster

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = {
                "ts": datetime.fromtimestamp(
                    record.created, tz=timezone.utc
                ).strftime("%H:%M:%S.%f")[:-3],
                "level": record.levelname,
                "name": record.name,
                "msg": self.format(record),
            }
            self._broadcaster.broadcast(entry)
        except Exception:
            self.handleError(record)
