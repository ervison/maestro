"""Maestro - CLI-driven AI agent with multi-provider and multi-agent support."""

from maestro.config import Config, load as load_config, save as save_config
from maestro.models import (
    format_model_list,
    get_available_models,
    parse_model_string,
    resolve_model,
)
from maestro.providers.registry import (
    discover_providers,
    get_default_provider,
    get_provider,
    list_providers,
)

__all__ = [
    # Config
    "Config",
    "load_config",
    "save_config",
    # Model resolution
    "resolve_model",
    "parse_model_string",
    "get_available_models",
    "format_model_list",
    # Provider registry
    "get_provider",
    "get_default_provider",
    "list_providers",
    "discover_providers",
]
