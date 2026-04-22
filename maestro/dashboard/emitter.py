"""DashboardEmitter - thread-safe SSE event broadcaster.

Maintains a list of subscriber callables. When emit() is called,
all subscribers receive the event dict. Used by multi_agent nodes
to push real-time updates to the dashboard SSE server.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable


logger = logging.getLogger(__name__)


class DashboardEmitter:
    """Thread-safe event broadcaster for dashboard SSE updates.

    Usage:
        emitter = DashboardEmitter()
        emitter.subscribe(my_handler)  # handler(event: dict) -> None
        emitter.emit({"type": "node_update", "id": "t1", "status": "active"})
    """

    def __init__(self) -> None:
        self._subscribers: list[Callable[[dict[str, Any]], None]] = []
        self._history: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def subscribe(self, handler: Callable[[dict[str, Any]], None]) -> None:
        """Register a handler and immediately replay all past events to it."""
        with self._lock:
            past = list(self._history)
            self._subscribers.append(handler)
        # Replay history outside the lock to avoid deadlock
        for event in past:
            try:
                handler(event)
            except Exception as exc:
                logger.warning(
                    "DashboardEmitter: replay subscriber raised: %s", exc, exc_info=True
                )

    def unsubscribe(self, handler: Callable[[dict[str, Any]], None]) -> None:
        """Remove a previously registered handler."""
        with self._lock:
            try:
                self._subscribers.remove(handler)
            except ValueError:
                pass

    def emit(self, event: dict[str, Any]) -> None:
        """Broadcast event to all subscribers.

        Subscribers are called synchronously in registration order.
        If a subscriber raises, the exception is suppressed to avoid
        disrupting the agent graph execution.
        """
        with self._lock:
            handlers = list(self._subscribers)
            self._history.append(event)

        for handler in handlers:
            try:
                handler(event)
            except Exception as exc:
                logger.warning(
                    "DashboardEmitter: subscriber raised: %s", exc, exc_info=True
                )
