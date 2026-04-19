"""Configuration management for maestro.

This module handles loading, saving, and accessing configuration from
~/.maestro/config.json with support for nested agent-specific settings.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


# Default config location (override with MAESTRO_CONFIG_FILE env var)
CONFIG_FILE = Path(
    os.environ.get("MAESTRO_CONFIG_FILE", Path.home() / ".maestro" / "config.json")
)


@dataclass
class Config:
    """Maestro configuration with provider and agent settings.

    Attributes:
        model: Default model to use (format: "provider_id/model_id")
        agent: Agent-specific configuration keyed by agent name
        aggregator: Aggregator-specific configuration (e.g., enabled flag)
    """

    model: str | None = None
    agent: dict[str, dict[str, Any]] = field(default_factory=dict)
    aggregator: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a config value using dot notation.

        Args:
            key: Dot-separated key path (e.g., "agent.backend.model")
            default: Value to return if key not found

        Returns:
            Config value or default
        """
        parts = key.split(".")
        value: Any = asdict(self)

        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return default

        return value

    def set(self, key: str, value: Any) -> None:
        """Set a config value using dot notation.

        Args:
            key: Dot-separated key path (e.g., "agent.backend.model")
            value: Value to set
        """
        parts = key.split(".")

        if len(parts) == 1:
            # Direct attribute set
            if hasattr(self, parts[0]):
                setattr(self, parts[0], value)
            else:
                raise KeyError(f"Invalid config key: {key}")
            return

        # Navigate to parent container
        current: Any = self
        for part in parts[:-1]:
            if isinstance(current, Config):
                if not hasattr(current, part):
                    raise KeyError(f"Invalid config key: {key}")
                current = getattr(current, part)
            elif isinstance(current, dict):
                if part not in current:
                    current[part] = {}
                current = current[part]
            else:
                raise KeyError(f"Cannot set nested key on non-container: {key}")

        # Set final value
        final_key = parts[-1]
        if isinstance(current, dict):
            current[final_key] = value
        else:
            raise KeyError(f"Cannot set key on non-container: {key}")


def load() -> Config:
    """Load configuration from disk.

    Returns:
        Config instance with values from config file, or defaults if file
        doesn't exist.

    Raises:
        RuntimeError: If config file exists but contains invalid JSON.
    """
    if not CONFIG_FILE.exists():
        return Config()

    try:
        data = json.loads(CONFIG_FILE.read_text())
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Invalid config file at {CONFIG_FILE}; remove or repair the file."
        ) from exc

    if not isinstance(data, dict):
        raise RuntimeError(
            f"Invalid config file at {CONFIG_FILE}; expected object, got {type(data).__name__}"
        )

    model = data.get("model")
    if model is not None and not isinstance(model, str):
        raise RuntimeError(
            f"Invalid config file at {CONFIG_FILE}; expected 'model' to be a string"
        )

    agent = data.get("agent", {})
    if not isinstance(agent, dict):
        raise RuntimeError(
            f"Invalid config file at {CONFIG_FILE}; expected 'agent' to be an object"
        )

    aggregator = data.get("aggregator", {})
    if not isinstance(aggregator, dict):
        raise RuntimeError(
            f"Invalid config file at {CONFIG_FILE}; expected 'aggregator' to be an object"
        )

    return Config(
        model=model,
        agent=agent,
        aggregator=aggregator,
    )


def save(config: Config) -> None:
    """Save configuration to disk with secure permissions.

    Writes config to ~/.maestro/config.json with file mode 0o600.
    Creates parent directories if needed.

    Args:
        config: Config instance to save
    """
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Write with restricted permissions
    fd = os.open(str(CONFIG_FILE), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        json.dump(asdict(config), handle, indent=2)

    # Ensure permissions are set (in case umask interfered)
    CONFIG_FILE.chmod(0o600)
