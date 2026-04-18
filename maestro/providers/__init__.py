"""Provider plugin system for maestro."""

from .base import (
    Message,
    ProviderPlugin,
    Tool,
    ToolCall,
    ToolResult,
)
from .chatgpt import ChatGPTProvider
from .copilot import CopilotProvider

__all__ = [
    "Message",
    "ProviderPlugin",
    "Tool",
    "ToolCall",
    "ToolResult",
    "ChatGPTProvider",
    "CopilotProvider",
]
