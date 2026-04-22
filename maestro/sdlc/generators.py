"""Artifact generators — one LLM call per SDLC artifact type."""
from __future__ import annotations

from maestro.sdlc.schemas import (
    ARTIFACT_FILENAMES,
    ArtifactType,
    SDLCArtifact,
    SDLCRequest,
)
from maestro.sdlc.prompts import PROMPTS


async def generate_artifact(
    provider,
    model: str | None,
    request: SDLCRequest,
    artifact_type: ArtifactType,
) -> SDLCArtifact:
    """Call the provider to generate a single SDLC artifact."""
    from maestro.providers.base import Message

    system_prompt = PROMPTS[artifact_type]
    messages = [
        Message(role="system", content=system_prompt),
        Message(role="user", content=request.prompt),
    ]
    content_parts: list[str] = []
    async for msg in provider.stream(messages, tools=None, model=model):
        if msg.role == "assistant" and msg.content:
            content_parts.append(msg.content)

    content = "".join(content_parts).strip()
    if not content:
        content = (
            f"# {artifact_type.value.replace('_', ' ').title()}\n\n(no content generated)\n"
        )
    filename = ARTIFACT_FILENAMES[artifact_type]
    return SDLCArtifact(artifact_type=artifact_type, filename=filename, content=content)
