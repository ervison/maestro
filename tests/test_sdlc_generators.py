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
async def test_generate_artifact_empty_provider_content_returns_placeholder() -> None:
    provider = EmptyProvider()
    request = SDLCRequest("Build a CRM")
    result = await generate_artifact(provider, None, request, ArtifactType.PRD)
    assert "(no content generated)" in result.content


@pytest.mark.asyncio
async def test_generate_artifact_all_types_succeed() -> None:
    provider = MockProvider()
    request = SDLCRequest("Build a CRM")
    for artifact_type in ArtifactType:
        result = await generate_artifact(provider, None, request, artifact_type)
        assert isinstance(result, SDLCArtifact)
        assert result.artifact_type == artifact_type


@pytest.mark.asyncio
async def test_harness_with_provider_calls_generators(tmp_path) -> None:
    from maestro.sdlc.harness import DiscoveryHarness

    provider = MockProvider()
    harness = DiscoveryHarness(provider=provider, workdir=str(tmp_path), reflect=False)
    result = await harness.arun(SDLCRequest("Build a CRM", workdir=str(tmp_path)))
    # 13 artifacts = 13 stream calls
    assert len(provider.calls) == 13
    assert result.artifact_count == 13


def test_prompts_cover_all_artifact_types() -> None:
    assert len(PROMPTS) == 13
    missing = set(ArtifactType) - set(PROMPTS)
    assert not missing, f"Missing prompts for: {missing}"
