"""ProviderPlugin Protocol and neutral types for maestro providers.

This module defines the interface that all LLM provider plugins must implement,
along with provider-neutral data types for messages, tools, and tool results.
"""

from dataclasses import dataclass, field
from typing import AsyncIterator, Literal, Protocol, runtime_checkable


@dataclass
class Tool:
    """Provider-neutral tool definition (matches OpenAI function calling schema)."""

    name: str
    description: str
    parameters: dict  # JSON Schema for arguments


@dataclass
class ToolCall:
    """A request from the LLM to invoke a tool."""

    id: str
    name: str
    arguments: dict  # Parsed arguments (not JSON string)


@dataclass
class ToolResult:
    """Result of a tool execution, to be sent back to the LLM."""

    call_id: str
    output: str  # JSON-serializable string


@dataclass
class Message:
    """Provider-neutral message for conversation history."""

    role: Literal["user", "assistant", "system", "tool"]
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None


@runtime_checkable
class ProviderPlugin(Protocol):
    """
    Protocol for LLM provider plugins.

    Third-party providers implement this interface to integrate with maestro.
    Use @runtime_checkable for isinstance() validation at registry time.

    Note: @runtime_checkable only checks method existence, not signatures.
    Integration tests must verify actual call compatibility.
    """

    @property
    def id(self) -> str:
        """Unique provider identifier (e.g., 'chatgpt', 'github-copilot')."""
        ...

    @property
    def name(self) -> str:
        """Human-readable provider name (e.g., 'ChatGPT', 'GitHub Copilot')."""
        ...

    def list_models(self) -> list[str]:
        """Return list of available model IDs for this provider."""
        ...

    def stream(
        self,
        messages: list[Message],
        model: str,
        tools: list[Tool] | None = None,
    ) -> AsyncIterator[str | Message]:
        """
        Stream a completion from the provider.

        Yields:
            str: Partial text chunks during streaming
            Message: Complete message when stream ends (with role="assistant")

        The final yield MUST be a Message with the complete response.
        """
        ...

    def auth_required(self) -> bool:
        """Return True if this provider requires authentication."""
        ...

    def login(self) -> None:
        """Perform interactive authentication. Blocks until complete or raises."""
        ...

    def is_authenticated(self) -> bool:
        """Return True if valid credentials are currently available."""
        ...
