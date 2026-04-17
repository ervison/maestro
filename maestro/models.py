"""Model resolution and management for maestro.

This module handles:
- Model string parsing ("provider_id/model_id" format)
- Model resolution following priority chain
- Model availability checking across authenticated providers
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from maestro.providers.base import ProviderPlugin


def parse_model_string(model_str: str) -> tuple[str, str]:
    """Parse a model string into provider_id and model_id.

    Validates the "provider_id/model_id" format.

    Args:
        model_str: Model specification string (e.g., "chatgpt/gpt-5.4", "github-copilot/gpt-4o")

    Returns:
        Tuple of (provider_id, model_id)

    Raises:
        ValueError: If format is invalid. Error message includes guidance.
    """
    if "/" not in model_str:
        raise ValueError(
            f"Invalid model format: '{model_str}'. "
            f"Expected format: 'provider_id/model_id' "
            f"(e.g., 'chatgpt/gpt-5.4', 'github-copilot/gpt-4o')"
        )

    parts = model_str.split("/", 1)
    provider_id = parts[0].strip()
    model_id = parts[1].strip()

    if not provider_id:
        raise ValueError(
            f"Invalid model format: '{model_str}'. "
            "Provider ID cannot be empty. "
            "Expected format: 'provider_id/model_id'"
        )

    if not model_id:
        raise ValueError(
            f"Invalid model format: '{model_str}'. "
            "Model ID cannot be empty. "
            "Expected format: 'provider_id/model_id'"
        )

    return provider_id, model_id


def resolve_model(
    model_flag: str | None = None,
    agent_name: str | None = None,
) -> tuple[ProviderPlugin, str]:
    """Resolve model following the priority chain.

    Resolution priority (highest to lowest):
    1. --model flag (passed as model_flag parameter)
    2. MAESTRO_MODEL environment variable
    3. config.agent.<agent_name>.model (if agent_name provided)
    4. config.model (global default)
    5. First model of first authenticated provider (or chatgpt fallback)

    Args:
        model_flag: Value from --model CLI flag (highest priority)
        agent_name: Name of agent for agent-specific config lookup

    Returns:
        Tuple of (provider_instance, model_id)

    Raises:
        ValueError: If model string format is invalid or provider not found.
    """
    from maestro import auth
    from maestro.config import load as load_config
    from maestro.providers.registry import get_provider, get_default_provider

    config = load_config()

    # Priority 1: --model flag
    if model_flag:
        provider_id, model_id = parse_model_string(model_flag)
        provider = get_provider(provider_id)
        return provider, model_id

    # Priority 2: MAESTRO_MODEL environment variable
    env_model = os.environ.get("MAESTRO_MODEL")
    if env_model:
        provider_id, model_id = parse_model_string(env_model)
        provider = get_provider(provider_id)
        return provider, model_id

    # Priority 3: config.agent.<name>.model
    if agent_name:
        agent_model = config.get(f"agent.{agent_name}.model")
        if agent_model:
            provider_id, model_id = parse_model_string(agent_model)
            provider = get_provider(provider_id)
            return provider, model_id

    # Priority 4: config.model (global default)
    if config.model:
        provider_id, model_id = parse_model_string(config.model)
        provider = get_provider(provider_id)
        return provider, model_id

    # Priority 5: First model of first authenticated provider (or fallback)
    provider = get_default_provider()

    # For ChatGPT, use the explicit default model (not first in list)
    if provider.id == "chatgpt":
        from maestro.providers.chatgpt import DEFAULT_MODEL

        return provider, DEFAULT_MODEL

    available_models = provider.list_models()
    if not available_models:
        raise RuntimeError(
            f"Provider '{provider.id}' returned no models; cannot resolve a default model"
        )
    return provider, available_models[0]


def _is_usable(provider) -> bool:
    """Check if a provider is usable (doesn't require auth or is authenticated)."""
    return not provider.auth_required() or provider.is_authenticated()


def get_available_models() -> dict[str, list[str]]:
    """Get all available models from usable providers.

    Returns:
        Dictionary mapping provider_id to list of model_ids.
        Only includes providers that are usable (don't require auth OR are authenticated).
    """
    from maestro.providers.registry import discover_providers

    result: dict[str, list[str]] = {}
    providers = discover_providers()

    for provider_id, provider_class in providers.items():
        try:
            instance = provider_class()
            if _is_usable(instance):
                result[provider_id] = instance.list_models()
        except Exception:
            # Skip providers that fail to load/check auth
            continue

    return result


def format_model_list(models_by_provider: dict[str, list[str]]) -> str:
    """Format model list for display.

    Args:
        models_by_provider: Dictionary from get_available_models()

    Returns:
        Formatted string suitable for CLI output.
    """
    lines = []
    for provider_id in sorted(models_by_provider.keys()):
        models = models_by_provider[provider_id]
        lines.append(f"\n{provider_id}:")
        for model in sorted(models):
            lines.append(f"  {model}")
    return "\n".join(lines)
