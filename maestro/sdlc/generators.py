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


def _build_user_message(
    request: SDLCRequest,
    prior_artifacts: list["SDLCArtifact"] | None,
) -> str:
    """Compose the user message, optionally prepending upstream artifact context."""
    if not prior_artifacts:
        return request.prompt

    sections = "\n\n".join(
        f"### {a.filename}\n{a.content}" for a in prior_artifacts
    )
    return (
        f"{request.prompt}\n\n"
        "## Prior Artifacts (use as authoritative source — do not contradict)\n\n"
        f"{sections}"
    )


async def generate_artifact(
    provider,
    model: str | None,
    request: SDLCRequest,
    artifact_type: ArtifactType,
    prior_artifacts: list["SDLCArtifact"] | None = None,
) -> SDLCArtifact:
    """Call the provider to generate a single SDLC artifact.

    Args:
        provider: LLM provider with stream() method.
        model: Model name to use.
        request: The discovery request (prompt + metadata).
        artifact_type: Which artifact to generate.
        prior_artifacts: Already-generated upstream artifacts to inject as
            context so the LLM can copy values verbatim instead of inventing them.
    """
    from maestro.providers.base import Message

    system_prompt = PROMPTS[artifact_type]
    user_message = _build_user_message(request, prior_artifacts)
    messages = [
        Message(role="system", content=system_prompt),
        Message(role="user", content=user_message),
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
