"""Artifact generators — one LLM call per SDLC artifact type."""
from __future__ import annotations

import asyncio

from maestro.sdlc.schemas import (
    ARTIFACT_FILENAMES,
    ArtifactType,
    SDLCArtifact,
    SDLCRequest,
)
from maestro.sdlc.prompts import PROMPTS

_TRANSIENT_STREAM_ERRORS = (RuntimeError,)


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
    content = ""
    for attempt in range(2):
        try:
            content = await _stream_artifact_content(provider, messages, model)
            break
        except _TRANSIENT_STREAM_ERRORS as exc:
            if attempt == 1 or not _is_retryable_stream_error(exc):
                raise
            await asyncio.sleep(1)

    if not content:
        content = (
            f"# {artifact_type.value.replace('_', ' ').title()}\n\n(no content generated)\n"
        )
    filename = ARTIFACT_FILENAMES[artifact_type]
    return SDLCArtifact(artifact_type=artifact_type, filename=filename, content=content)


async def _stream_artifact_content(provider, messages, model: str | None) -> str:
    from maestro.providers.base import Message

    content_parts: list[str] = []
    async for msg in provider.stream(messages, tools=None, model=model):
        if isinstance(msg, str):
            content_parts.append(msg)
        elif isinstance(msg, Message) and msg.role == "assistant" and msg.content:
            # Final assistant message replaces streamed chunks to avoid
            # duplicating content (partial deltas + complete response).
            content_parts = [msg.content]
        elif hasattr(msg, "role") and msg.role == "assistant" and msg.content:
            content_parts = [msg.content]
    return "".join(content_parts).strip()


def _is_retryable_stream_error(exc: RuntimeError) -> bool:
    message = str(exc).lower()
    return (
        "remoteprotocolerror" in message
        or "incomplete chunked read" in message
        or "expected sse response" in message
    )
