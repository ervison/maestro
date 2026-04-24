"""Copilot release smoke gate — COP-SMOKE-01, COP-SMOKE-02, COP-SMOKE-03.

This module is the release-grade integration test for the GitHub Copilot provider.
It is **skipped by default** and must be explicitly activated.

Skip conditions (gate is safe to skip when ANY of these apply):
  - MAESTRO_COPILOT_SMOKE env var is not set to "1"
  - No real GitHub Copilot subscription is available
  - No network access to api.githubcopilot.com

Activation:
  MAESTRO_COPILOT_SMOKE=1 pytest tests/test_copilot_smoke.py -v

Two modes:

  1. Token-seeded mode (CI-friendly):
     Set MAESTRO_COPILOT_TOKEN=<ghu_...> in addition to MAESTRO_COPILOT_SMOKE=1.
     The test skips the interactive device-code login and pre-seeds the token
     directly into a temporary auth store, then sends one live API request.
     Use this mode in CI pipelines with a stored secret.

  2. Interactive mode (human-in-the-loop):
     Set MAESTRO_COPILOT_SMOKE=1 but do NOT set MAESTRO_COPILOT_TOKEN.
     The test calls provider.login(), which prints a user_code and URL, then
     blocks until the user authorizes on GitHub and polling completes.
     Use this mode to validate the actual end-to-end device-code OAuth flow.

Auth isolation:
  The test redirects the auth store to a temporary file (via MAESTRO_AUTH_FILE)
  so it never reads from or writes to ~/.maestro/auth.json.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from maestro import auth
from maestro.providers.base import Message
from maestro.providers.copilot import CopilotProvider

# ---------------------------------------------------------------------------
# Default Copilot model to use for the live API request.
# Override by setting MAESTRO_COPILOT_MODEL in the environment.
# ---------------------------------------------------------------------------
_DEFAULT_SMOKE_MODEL = "gpt-4o-mini"


def _is_smoke_enabled() -> bool:
    """Return True only when MAESTRO_COPILOT_SMOKE=1 is explicitly set."""
    return os.environ.get("MAESTRO_COPILOT_SMOKE", "") == "1"


@pytest.mark.copilot_smoke
@pytest.mark.skipif(
    not _is_smoke_enabled(),
    reason="Set MAESTRO_COPILOT_SMOKE=1 to run Copilot release smoke gate",
)
def test_copilot_smoke_login_and_api_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Release smoke gate: device-code login and live Copilot API request.

    Exercises COP-SMOKE-01 (device-code login path), COP-SMOKE-02 (live API
    request and non-empty response), and COP-SMOKE-03 (explicit safe-skip guard).

    Auth isolation: monkeypatches maestro.auth.AUTH_FILE to a tmp_path file so
    ~/.maestro/auth.json is never read or written during this test.
    """
    # --- Auth isolation (T-16-02 mitigation) --------------------------------
    tmp_auth_file = tmp_path / "auth.json"
    monkeypatch.setattr(auth, "AUTH_FILE", tmp_auth_file)

    # --- Provider setup -----------------------------------------------------
    provider = CopilotProvider()
    preseeded_token = os.environ.get("MAESTRO_COPILOT_TOKEN", "")
    model = os.environ.get("MAESTRO_COPILOT_MODEL", _DEFAULT_SMOKE_MODEL)

    # --- Auth gate (COP-SMOKE-01) -------------------------------------------
    if preseeded_token:
        # Token-seeded mode: bypass interactive login, seed directly.
        auth.set("github-copilot", {"access_token": preseeded_token})
        assert provider.is_authenticated(), (
            "is_authenticated() must return True after seeding token via auth.set()"
        )
    else:
        # Interactive mode: exercise the real device-code OAuth flow.
        assert not provider.is_authenticated(), (
            "Expected no token stored before login in the isolated auth store"
        )
        # Blocks until user visits github.com/login/device and enters the code.
        provider.login()
        assert provider.is_authenticated(), (
            "is_authenticated() must return True after provider.login() completes"
        )

    # --- Live API request (COP-SMOKE-02) ------------------------------------
    messages = [Message(role="user", content="Reply with exactly the word: SMOKE_OK")]
    final_content: str = ""

    async def _run_stream() -> None:
        nonlocal final_content
        async for chunk in provider.stream(messages=messages, model=model):
            if isinstance(chunk, Message) and chunk.role == "assistant" and chunk.content:
                # The ProviderPlugin contract guarantees exactly one final Message
                # per stream call. Overwrite (not append) to guard against any
                # future provider that emits a trailing empty sentinel Message.
                final_content = chunk.content

    asyncio.run(_run_stream())

    assert final_content, (
        f"Expected a final assistant Message from live Copilot API using model={model!r}. "
        "Check that the token has Copilot API access."
    )
    assert "SMOKE_OK" in final_content, (
        f"Expected response to contain 'SMOKE_OK', got: {final_content!r}"
    )
