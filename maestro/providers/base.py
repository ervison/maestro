"""ProviderPlugin Protocol and neutral types for maestro providers.

This module defines the interface that all LLM provider plugins must implement,
along with provider-neutral data types for messages, tools, and tool results.
"""

from dataclasses import dataclass, field
from typing import Literal


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
    role: Literal["user", "assistant", "system"]
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
