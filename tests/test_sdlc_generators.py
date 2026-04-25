"""Tests for maestro/sdlc/generators.py and prompts.py."""
from __future__ import annotations

import pytest

from maestro.providers.base import Message
from maestro.sdlc.generators import generate_artifact
from maestro.sdlc.prompts import PROMPTS
from maestro.sdlc.schemas import (
    ARTIFACT_FILENAMES,
    ArtifactType,
    SDLCArtifact,
    SDLCRequest,
)


class MockProvider:
    """Mock provider that yields a fixed assistant message."""

    def __init__(self, content: str = "mock content") -> None:
        self._content = content
        self.calls: list[list[Message]] = []

    async def stream(self, messages, tools, model):
        self.calls.append(messages)
        if self._content:
            yield Message(role="assistant", content=self._content)


class EmptyProvider:
    """Mock provider that yields no content."""

    async def stream(self, messages, tools, model):
        return
        yield  # make it an async generator


class FlakyProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def stream(self, messages, tools, model):
        del messages, tools, model
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError(
                "httpx.RemoteProtocolError: peer closed connection without sending complete message body"
            )
        yield Message(role="assistant", content="recovered content")


class NonSSEProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def stream(self, messages, tools, model):
        del messages, tools, model
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError(
                "Expected SSE response from ChatGPT API, got status 429 with Content-Type 'application/json': rate limited"
            )
        yield Message(role="assistant", content="recovered after non-sse error")


@pytest.mark.asyncio
async def test_generate_artifact_returns_sdlc_artifact() -> None:
    provider = MockProvider()
    request = SDLCRequest("Build a CRM")
    result = await generate_artifact(provider, None, request, ArtifactType.BRIEFING)
    assert isinstance(result, SDLCArtifact)


@pytest.mark.asyncio
async def test_generate_artifact_uses_correct_filename() -> None:
    provider = MockProvider()
    request = SDLCRequest("Build a CRM")
    result = await generate_artifact(provider, None, request, ArtifactType.BRIEFING)
    assert result.filename == ARTIFACT_FILENAMES[ArtifactType.BRIEFING]


@pytest.mark.asyncio
async def test_generate_artifact_uses_system_prompt() -> None:
    provider = MockProvider()
    request = SDLCRequest("Build a CRM")
    await generate_artifact(provider, None, request, ArtifactType.BRIEFING)
    assert provider.calls, "provider.stream was not called"
    system_msg = provider.calls[0][0]
    assert system_msg.role == "system"
    assert system_msg.content == PROMPTS[ArtifactType.BRIEFING]


@pytest.mark.asyncio
async def test_generate_artifact_empty_provider_content_raises_runtime_error() -> None:
    provider = EmptyProvider()
    request = SDLCRequest("Build a CRM")
    with pytest.raises(RuntimeError, match="provider returned empty content after all attempts"):
        await generate_artifact(provider, None, request, ArtifactType.PRD)


@pytest.mark.asyncio
async def test_generate_artifact_all_types_succeed() -> None:
    provider = MockProvider()
    request = SDLCRequest("Build a CRM")
    for artifact_type in ArtifactType:
        result = await generate_artifact(provider, None, request, artifact_type)
        assert isinstance(result, SDLCArtifact)
        assert result.artifact_type == artifact_type


@pytest.mark.asyncio
async def test_generate_artifact_retries_transient_stream_error() -> None:
    provider = FlakyProvider()
    request = SDLCRequest("Build a CRM")

    result = await generate_artifact(provider, None, request, ArtifactType.API_CONTRACTS)

    assert result.content == "recovered content"
    assert provider.calls == 2


@pytest.mark.asyncio
async def test_generate_artifact_retries_non_sse_stream_error() -> None:
    provider = NonSSEProvider()
    request = SDLCRequest("Build a CRM")

    result = await generate_artifact(provider, None, request, ArtifactType.API_CONTRACTS)

    assert result.content == "recovered after non-sse error"
    assert provider.calls == 2


@pytest.mark.asyncio
async def test_harness_with_provider_calls_generators(tmp_path) -> None:
    from maestro.sdlc.harness import DiscoveryHarness

    provider = MockProvider()
    harness = DiscoveryHarness(provider=provider, workdir=str(tmp_path), reflect=False)
    result = await harness.arun(SDLCRequest("Build a CRM", workdir=str(tmp_path)))
    # 14 artifacts = 14 stream calls
    assert len(provider.calls) == 14
    assert result.artifact_count == 14


def test_prompts_cover_all_artifact_types() -> None:
    assert len(PROMPTS) == 14
    missing = set(ArtifactType) - set(PROMPTS)
    assert not missing, f"Missing prompts for: {missing}"
