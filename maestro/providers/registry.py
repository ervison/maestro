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
from collections.abc import AsyncIterator as ABCAsyncIterator
from inspect import isasyncgenfunction, iscoroutinefunction
from inspect import Parameter, Signature, signature
from sys import modules
from typing import get_origin, get_type_hints

from maestro.providers.base import ProviderPlugin


# Entry point group for provider plugins
PROVIDER_ENTRY_GROUP = "maestro.providers"


class DuplicateProviderError(ValueError):
    """Raised when two installed providers claim the same provider ID."""


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


def _validate_simple_method(instance: object, method_name: str, required_args: int) -> bool:
    """Check that a no-extra-arg method exists and has the right signature.

    Args:
        instance: Provider instance to inspect.
        method_name: Name of the method to check.
        required_args: Number of required positional args *after* ``self``.

    Returns:
        True if the method satisfies the contract, False otherwise.
    """
    method = getattr(type(instance), method_name, None)
    if method is None or not callable(method):
        return False

    try:
        params = list(signature(method).parameters.values())
    except (TypeError, ValueError):
        return False

    if len(params) < required_args + 1:
        return False

    if params[0].kind not in {
        Parameter.POSITIONAL_ONLY,
        Parameter.POSITIONAL_OR_KEYWORD,
    }:
        return False

    extra_params = params[1:]

    required_positional = [
        param
        for param in extra_params
        if param.default is Signature.empty
        and param.kind in {Parameter.POSITIONAL_ONLY, Parameter.POSITIONAL_OR_KEYWORD}
    ]
    if len(required_positional) != required_args:
        return False

    required_keyword_only = [
        param
        for param in extra_params
        if param.kind is Parameter.KEYWORD_ONLY and param.default is Signature.empty
    ]
    return not required_keyword_only


def _validate_stream_signature(stream_attr: object) -> bool:
    """Check that the ``stream`` method has the required positional signature.

    Expects ``stream(self, messages, model, ...)`` — exactly two required
    positional parameters after ``self``.

    Args:
        stream_attr: The ``stream`` callable retrieved from the provider class.

    Returns:
        True if the signature is valid, False otherwise.
    """
    try:
        params = list(signature(stream_attr).parameters.values())  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False

    if len(params) < 3:
        return False

    if params[0].kind not in {
        Parameter.POSITIONAL_ONLY,
        Parameter.POSITIONAL_OR_KEYWORD,
    }:
        return False

    required_after_self = [
        param
        for param in params[1:]
        if param.default is Signature.empty
        and param.kind in {Parameter.POSITIONAL_ONLY, Parameter.POSITIONAL_OR_KEYWORD}
    ]
    if len(required_after_self) != 2:
        return False

    required_keyword_only = [
        param
        for param in params[1:]
        if param.default is Signature.empty and param.kind is Parameter.KEYWORD_ONLY
    ]
    return not required_keyword_only


def _validate_stream_return_type(stream_attr: object) -> bool:
    """Check that ``stream`` returns an ``AsyncIterator`` (or has no annotation).

    An async-generator function always satisfies the contract.  A plain
    coroutine never does.  For other callables the return annotation is
    inspected when available.

    Args:
        stream_attr: The ``stream`` callable retrieved from the provider class.

    Returns:
        True if the return type is compatible, False otherwise.
    """
    if isasyncgenfunction(stream_attr):
        return True

    if iscoroutinefunction(stream_attr):
        return False

    try:
        module = modules.get(stream_attr.__module__)  # type: ignore[union-attr]
        globalns = vars(module) if module is not None else None
        return_annotation = get_type_hints(stream_attr, globalns=globalns).get("return")  # type: ignore[arg-type]
    except (NameError, TypeError):
        return True

    if return_annotation is None:
        return True

    origin = get_origin(return_annotation)
    return return_annotation is ABCAsyncIterator or origin is ABCAsyncIterator


def _is_valid_provider(instance: object) -> bool:
    """Check whether an instance satisfies the runtime provider contract.

    Delegates to focused helpers:
    - :func:`_validate_simple_method` — zero-arg interface methods
    - :func:`_validate_stream_signature` — ``stream`` positional signature
    - :func:`_validate_stream_return_type` — ``stream`` async-iterator return type
    """
    if not isinstance(instance, ProviderPlugin):
        return False

    simple_methods = {
        "list_models": 0,
        "auth_required": 0,
        "login": 0,
        "is_authenticated": 0,
    }
    for method_name, required_args in simple_methods.items():
        if not _validate_simple_method(instance, method_name, required_args):
            return False

    stream_attr = getattr(type(instance), "stream", None)
    if stream_attr is None or not callable(stream_attr):
        return False

    if not _validate_stream_signature(stream_attr):
        return False

    return _validate_stream_return_type(stream_attr)


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
            if not _is_valid_provider(instance):
                raise TypeError(
                    f"Provider entry point '{ep.name}' does not implement ProviderPlugin"
                )
            provider_id = instance.id
            if provider_id in providers:
                raise DuplicateProviderError(
                    f"Duplicate provider id '{provider_id}' from entry point '{ep.name}'"
                )
            providers[provider_id] = provider_class
        except DuplicateProviderError:
            # Re-raise only the duplicate-ID error; let callers handle it
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
    1. First authenticated provider (auth_required and is_authenticated)
    2. ChatGPT fallback, if installed (even when unauthenticated, for backward compatibility)
    3. First auth-free provider (auth_required=False)

    Returns:
        Instantiated provider implementing ProviderPlugin Protocol

    Raises:
        ValueError: If no providers are available, or no usable provider
                    exists and ChatGPT is not installed.
    """
    providers = discover_providers()

    if not providers:
        raise ValueError("No providers installed. Install a provider package.")

    chatgpt_fallback: ProviderPlugin | None = None
    auth_free_fallback: ProviderPlugin | None = None

    for provider_id, provider_class in providers.items():
        try:
            instance = provider_class()
            if instance.auth_required() and instance.is_authenticated():
                # Authenticated provider found - return immediately
                return instance
            if provider_id == "chatgpt":
                chatgpt_fallback = instance
            elif not instance.auth_required() and auth_free_fallback is None:
                auth_free_fallback = instance
        except Exception:
            # Skip providers that fail to instantiate/check auth
            continue

    # No authenticated provider found; fall back in priority order
    if chatgpt_fallback is not None:
        return chatgpt_fallback

    if auth_free_fallback is not None:
        return auth_free_fallback

    raise ValueError(
        "No usable provider found: no authenticated providers, ChatGPT is not installed, "
        "and no auth-free providers are available. "
        "Either authenticate a provider (maestro auth login) "
        "or install a provider that doesn't require authentication."
    )
