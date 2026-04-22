"""DashboardEmitter - thread-safe SSE event broadcaster.

Maintains a list of subscriber callables. When emit() is called,
all subscribers receive the event dict. Used by multi_agent nodes
to push real-time updates to the dashboard SSE server.
"""

from __future__ import annotations

import threading
from typing import Any, Callable


class DashboardEmitter:
    """Thread-safe event broadcaster for dashboard SSE updates.

    Usage:
        emitter = DashboardEmitter()
        emitter.subscribe(my_handler)  # handler(event: dict) -> None
        emitter.emit({"type": "node_update", "id": "t1", "status": "active"})
    """

    def __init__(self) -> None:
        self._subscribers: list[Callable[[dict[str, Any]], None]] = []
        self._lock = threading.Lock()

    def subscribe(self, handler: Callable[[dict[str, Any]], None]) -> None:
        """Register a handler to receive all future events."""
        with self._lock:
            self._subscribers.append(handler)

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

        for handler in handlers:
            try:
                handler(event)
            except Exception:
                pass
