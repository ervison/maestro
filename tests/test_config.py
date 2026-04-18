"""Tests for maestro.config module."""

import json
import os
import stat
from pathlib import Path

import pytest

from maestro import config


@pytest.fixture
def temp_config_file(tmp_path, monkeypatch):
    """Create a temporary config file and override CONFIG_FILE."""
    config_path = tmp_path / "config.json"
    monkeypatch.setattr(config, "CONFIG_FILE", config_path)
    return config_path


class TestConfig:
    """Tests for Config dataclass."""

    def test_default_values(self):
        """Config has sensible defaults."""
        cfg = config.Config()
        assert cfg.model is None
        assert cfg.agent == {}

    def test_custom_values(self):
        """Config accepts custom values."""
        cfg = config.Config(
            model="chatgpt/gpt-5.4",
            agent={"backend": {"model": "chatgpt/gpt-5.4-mini"}},
        )
        assert cfg.model == "chatgpt/gpt-5.4"
        assert cfg.agent["backend"]["model"] == "chatgpt/gpt-5.4-mini"

    def test_get_simple_key(self):
        """get() retrieves top-level keys."""
        cfg = config.Config(model="chatgpt/gpt-5.4")
        assert cfg.get("model") == "chatgpt/gpt-5.4"

    def test_get_nested_key(self):
        """get() retrieves nested keys with dot notation."""
        cfg = config.Config(agent={"backend": {"model": "chatgpt/gpt-5.4-mini"}})
        assert cfg.get("agent.backend.model") == "chatgpt/gpt-5.4-mini"

    def test_get_missing_key_returns_default(self):
        """get() returns default for missing keys."""
        cfg = config.Config()
        assert cfg.get("missing") is None
        assert cfg.get("missing", "default") == "default"

    def test_get_missing_nested_key_returns_default(self):
        """get() returns default for missing nested keys."""
        cfg = config.Config(agent={})
        assert cfg.get("agent.backend.model") is None

    def test_set_simple_key(self):
        """set() updates top-level keys."""
        cfg = config.Config()
        cfg.set("model", "chatgpt/gpt-5.4")
        assert cfg.model == "chatgpt/gpt-5.4"

    def test_set_nested_key(self):
        """set() updates nested keys with dot notation."""
        cfg = config.Config()
        cfg.set("agent.backend.model", "chatgpt/gpt-5.4-mini")
        assert cfg.agent["backend"]["model"] == "chatgpt/gpt-5.4-mini"

    def test_set_creates_nested_dicts(self):
        """set() creates intermediate dicts as needed."""
        cfg = config.Config()
        cfg.set("agent.new_agent.model", "chatgpt/gpt-5.4")
        assert cfg.agent["new_agent"]["model"] == "chatgpt/gpt-5.4"

    def test_set_invalid_key_raises(self):
        """set() raises KeyError for invalid keys."""
        cfg = config.Config()
        with pytest.raises(KeyError):
            cfg.set("invalid_key", "value")


class TestLoad:
    """Tests for load() function."""

    def test_load_missing_file_returns_defaults(self, temp_config_file):
        """Loading missing config returns defaults."""
        cfg = config.load()
        assert cfg.model is None
        assert cfg.agent == {}

    def test_load_valid_config(self, temp_config_file):
        """Loading valid config file returns Config with values."""
        data = {"model": "chatgpt/gpt-5.4", "agent": {"backend": {"model": "chatgpt/gpt-5.4-mini"}}}
        temp_config_file.write_text(json.dumps(data))

        cfg = config.load()
        assert cfg.model == "chatgpt/gpt-5.4"
        assert cfg.agent["backend"]["model"] == "chatgpt/gpt-5.4-mini"

    def test_load_invalid_json_raises(self, temp_config_file):
        """Loading invalid JSON raises RuntimeError."""
        temp_config_file.write_text("not valid json")

        with pytest.raises(RuntimeError) as exc_info:
            config.load()

        assert "Invalid config file" in str(exc_info.value)

    def test_load_non_dict_raises(self, temp_config_file):
        """Loading non-dict JSON raises RuntimeError."""
        temp_config_file.write_text("[1, 2, 3]")

        with pytest.raises(RuntimeError) as exc_info:
            config.load()

        assert "expected object, got list" in str(exc_info.value)


class TestSave:
    """Tests for save() function."""

    def test_save_creates_file(self, temp_config_file):
        """Saving config creates the file."""
        cfg = config.Config(model="chatgpt/gpt-5.4")
        config.save(cfg)

        assert temp_config_file.exists()

    def test_save_creates_parent_dirs(self, temp_config_file):
        """Saving config creates parent directories."""
        nested_path = temp_config_file.parent / "nested" / "deep" / "config.json"
        config.CONFIG_FILE = nested_path

        cfg = config.Config()
        config.save(cfg)

        assert nested_path.exists()

    def test_save_sets_secure_permissions(self, temp_config_file):
        """Saved config has 0o600 permissions."""
        cfg = config.Config(model="chatgpt/gpt-5.4")
        config.save(cfg)

        mode = stat.S_IMODE(temp_config_file.stat().st_mode)
        assert mode == 0o600

    def test_save_roundtrip(self, temp_config_file):
        """Saved config can be loaded back."""
        original = config.Config(
            model="chatgpt/gpt-5.4",
            agent={"backend": {"model": "chatgpt/gpt-5.4-mini"}},
        )
        config.save(original)

        loaded = config.load()
        assert loaded.model == original.model
        assert loaded.agent == original.agent


class TestConfigFileEnvOverride:
    """Tests for MAESTRO_CONFIG_FILE environment variable."""

    def test_env_override(self, monkeypatch, tmp_path):
        """MAESTRO_CONFIG_FILE overrides default path."""
        custom_path = tmp_path / "custom" / "config.json"
        monkeypatch.setenv("MAESTRO_CONFIG_FILE", str(custom_path))

        # Reload config module to pick up env var
        import importlib

        importlib.reload(config)

        assert config.CONFIG_FILE == custom_path

        # Cleanup: unset env and reload to restore default
        monkeypatch.delenv("MAESTRO_CONFIG_FILE", raising=False)
        importlib.reload(config)

    def test_default_without_env(self, monkeypatch):
        """Without env var, uses default path."""
        # Ensure env var is not set
        monkeypatch.delenv("MAESTRO_CONFIG_FILE", raising=False)

        # Reload config module to ensure default is used
        import importlib

        importlib.reload(config)

        assert config.CONFIG_FILE == Path.home() / ".maestro" / "config.json"
