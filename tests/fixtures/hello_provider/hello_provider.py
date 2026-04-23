"""Minimal third-party provider fixture for maestro smoke tests.

This package is NOT part of maestro source. It is installed in an isolated
venv during tests/test_provider_install_smoke.py to prove the entry-point
discovery path works for real external packages.
"""

from __future__ import annotations

from typing import AsyncIterator


class HelloProvider:
    """Stub provider that satisfies the ProviderPlugin Protocol."""

    @property
    def id(self) -> str:
        return "hello"

    @property
    def name(self) -> str:
        return "Hello Provider"

    def list_models(self) -> list[str]:
        return ["hello-1"]

    def auth_required(self) -> bool:
        return False

    def is_authenticated(self) -> bool:
        return True

    def login(self) -> None:
        pass  # No-op — no auth required

    async def stream(self, messages, model, tools=None, **kwargs) -> AsyncIterator:
        # Minimal async generator satisfying the Protocol
        from dataclasses import dataclass, field
        from typing import Literal

        @dataclass
        class _Message:
            role: Literal["user", "assistant", "system", "tool"]
            content: str
            tool_calls: list = field(default_factory=list)
            tool_call_id: str | None = None

        yield _Message(role="assistant", content="hello")
