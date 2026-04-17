"""Provider registry for runtime discovery and access to LLM providers.

This module handles:
- Discovery of providers via importlib.metadata entry points
- Caching of discovered providers
- Provider instance creation and lookup
- Default provider resolution based on authentication state
"""

from __future__ import annotations

from functools import lru_cache
from importlib.metadata import entry_points

from maestro.providers.base import ProviderPlugin


# Entry point group for provider plugins
PROVIDER_ENTRY_GROUP = "maestro.providers"


def _is_usable(provider: ProviderPlugin) -> bool:
    """Check if a provider is usable (doesn't require auth or is authenticated).

    A provider is usable if:
    - auth_required() returns False (no authentication needed)
    - OR is_authenticated() returns True (has valid credentials)

    Args:
        provider: Provider instance to check

    Returns:
        True if the provider can be used for model operations
    """
    return not provider.auth_required() or provider.is_authenticated()


@lru_cache(maxsize=1)
def discover_providers() -> dict[str, type[ProviderPlugin]]:
    """Discover all providers registered via entry points.

    Uses importlib.metadata to find all providers registered under the
    "maestro.providers" entry point group. Results are cached since entry
    points are static after package installation.

    Returns:
        Dictionary mapping provider IDs to provider classes.
        Provider ID is derived from the entry point name.

    Example:
        >>> providers = discover_providers()
        >>> "chatgpt" in providers
        True
    """
    providers: dict[str, type[ProviderPlugin]] = {}

    for ep in entry_points(group=PROVIDER_ENTRY_GROUP):
        try:
            provider_class = ep.load()
            # Create instance temporarily to get the actual ID
            # This validates the provider can be instantiated
            instance = provider_class()
            # Validate the instance satisfies ProviderPlugin contract
            if not isinstance(instance, ProviderPlugin):
                raise TypeError(
                    f"Provider entry point '{ep.name}' does not implement ProviderPlugin"
                )
            provider_id = instance.id
            if provider_id in providers:
                raise ValueError(
                    f"Duplicate provider id '{provider_id}' from entry point '{ep.name}'"
                )
            providers[provider_id] = provider_class
        except ValueError:
            # Re-raise ValueError for duplicate provider IDs
            raise
        except Exception:
            # Skip providers that fail to load or don't satisfy the contract
            # In production, we might want to log this
            continue

    return providers


def list_providers() -> list[str]:
    """List all discovered provider IDs.

    Returns:
        Sorted list of provider IDs available in the system.
    """
    return sorted(discover_providers().keys())


def get_provider(provider_id: str) -> ProviderPlugin:
    """Get a provider instance by ID.

    Args:
        provider_id: Unique provider identifier (e.g., "chatgpt", "github-copilot")

    Returns:
        Instantiated provider implementing ProviderPlugin Protocol

    Raises:
        ValueError: If provider_id is not found among available providers.
                    Error message includes list of available provider IDs.
    """
    providers = discover_providers()

    if provider_id not in providers:
        available = ", ".join(sorted(providers.keys()))
        raise ValueError(
            f"Unknown provider: '{provider_id}'. "
            f"Available providers: {available if available else '(none installed)'}"
        )

    # Instantiate the provider class
    provider_class = providers[provider_id]
    return provider_class()


def get_default_provider() -> ProviderPlugin:
    """Get the default provider based on authentication state.

    Resolution order:
    1. First usable provider (not requiring auth OR authenticated)

    A provider is usable if auth_required() is False OR is_authenticated() is True.

    Returns:
        Instantiated provider implementing ProviderPlugin Protocol

    Raises:
        ValueError: If no providers are available or no provider is usable.
    """
    providers = discover_providers()

    if not providers:
        raise ValueError("No providers installed. Install a provider package.")

    # Find first usable provider (doesn't require auth or is authenticated)
    for provider_id, provider_class in providers.items():
        try:
            instance = provider_class()
            if _is_usable(instance):
                return instance
        except Exception:
            # Skip providers that fail to instantiate/check auth
            continue

    # No usable provider found - fallback to ChatGPT if available
    if "chatgpt" in providers:
        return providers["chatgpt"]()

    raise ValueError(
        "No usable provider found and no ChatGPT fallback is installed. "
        "Either authenticate a provider (maestro auth login) "
        "or install a provider that doesn't require authentication."
    )
