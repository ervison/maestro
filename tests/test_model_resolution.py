"""Tests for maestro.models module."""

import os
from unittest import mock

import pytest

from maestro import auth, config, models
from maestro.providers.base import ProviderPlugin


class TestParseModelString:
    """Tests for parse_model_string() function."""

    def test_valid_format(self):
        """Parses valid provider/model format."""
        provider_id, model_id = models.parse_model_string("chatgpt/gpt-5.4")
        assert provider_id == "chatgpt"
        assert model_id == "gpt-5.4"

    def test_with_multiple_slashes(self):
        """Handles model IDs containing slashes."""
        provider_id, model_id = models.parse_model_string("provider/model/with/slashes")
        assert provider_id == "provider"
        assert model_id == "model/with/slashes"

    def test_strips_whitespace(self):
        """Strips whitespace from parts."""
        provider_id, model_id = models.parse_model_string("  chatgpt  /  gpt-5.4  ")
        assert provider_id == "chatgpt"
        assert model_id == "gpt-5.4"

    def test_raises_for_missing_slash(self):
        """Raises ValueError when no slash present."""
        with pytest.raises(ValueError) as exc_info:
            models.parse_model_string("gpt-5.4")

        assert "Invalid model format" in str(exc_info.value)
        assert "Expected format" in str(exc_info.value)

    def test_raises_for_empty_provider(self):
        """Raises ValueError for empty provider ID."""
        with pytest.raises(ValueError) as exc_info:
            models.parse_model_string("/gpt-5.4")

        assert "Provider ID cannot be empty" in str(exc_info.value)

    def test_raises_for_empty_model(self):
        """Raises ValueError for empty model ID."""
        with pytest.raises(ValueError) as exc_info:
            models.parse_model_string("chatgpt/")

        assert "Model ID cannot be empty" in str(exc_info.value)

    def test_error_includes_examples(self):
        """Error message includes example formats."""
        with pytest.raises(ValueError) as exc_info:
            models.parse_model_string("invalid")

        msg = str(exc_info.value)
        assert "chatgpt/gpt-5.4" in msg or "provider_id/model_id" in msg


class TestResolveModel:
    """Tests for resolve_model() function."""

    def test_priority_1_model_flag(self, monkeypatch):
        """--model flag has highest priority."""
        # Set up env and config that should be ignored
        monkeypatch.setenv("MAESTRO_MODEL", "chatgpt/gpt-5.2")
        cfg = config.Config(model="chatgpt/gpt-5.4-mini")
        monkeypatch.setattr(config, "load", lambda: cfg)

        # Flag should win
        provider, model_id = models.resolve_model(model_flag="chatgpt/gpt-5.4")
        assert model_id == "gpt-5.4"
        assert provider.id == "chatgpt"

    def test_priority_2_env_variable(self, monkeypatch):
        """MAESTRO_MODEL env var is priority 2."""
        # Set up config that should be ignored
        cfg = config.Config(model="chatgpt/gpt-5.4-mini")
        monkeypatch.setattr(config, "load", lambda: cfg)

        # Env should win
        monkeypatch.setenv("MAESTRO_MODEL", "chatgpt/gpt-5.2")
        provider, model_id = models.resolve_model()
        assert model_id == "gpt-5.2"

    def test_priority_3_agent_config(self, monkeypatch):
        """config.agent.<name>.model is priority 3."""
        cfg = config.Config(
            model="chatgpt/gpt-5.4-mini",  # Should be ignored
            agent={"backend": {"model": "chatgpt/gpt-5.2"}},
        )
        monkeypatch.setattr(config, "load", lambda: cfg)

        provider, model_id = models.resolve_model(agent_name="backend")
        assert model_id == "gpt-5.2"

    def test_priority_4_global_config(self, monkeypatch):
        """config.model is priority 4."""
        cfg = config.Config(model="chatgpt/gpt-5.4-mini")
        monkeypatch.setattr(config, "load", lambda: cfg)

        provider, model_id = models.resolve_model()
        assert model_id == "gpt-5.4-mini"

    def test_priority_5_fallback(self, monkeypatch):
        """Fallback to first authenticated provider is priority 5."""
        cfg = config.Config()  # No model set
        monkeypatch.setattr(config, "load", lambda: cfg)

        provider, model_id = models.resolve_model()
        assert provider.id == "chatgpt"
        # Should get first available model
        assert model_id in provider.list_models()

    def test_parse_error_propagates(self):
        """Invalid model string raises ValueError."""
        with pytest.raises(ValueError):
            models.resolve_model(model_flag="invalid-no-slash")

    def test_unknown_provider_raises(self):
        """Unknown provider raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            models.resolve_model(model_flag="unknown/model")

        assert "Unknown provider" in str(exc_info.value)


class TestGetAvailableModels:
    """Tests for get_available_models() function."""

    def test_returns_authenticated_providers(self, monkeypatch):
        """Only includes authenticated providers."""
        # Mock ChatGPTProvider.is_authenticated to return False
        from maestro.providers import chatgpt

        monkeypatch.setattr(chatgpt.ChatGPTProvider, "is_authenticated", lambda self: False)

        result = models.get_available_models()
        assert result == {}

    def test_includes_chatgpt_when_authenticated(self, monkeypatch):
        """Includes chatgpt models when authenticated."""
        from maestro.providers import chatgpt

        monkeypatch.setattr(chatgpt.ChatGPTProvider, "is_authenticated", lambda self: True)
        result = models.get_available_models()
        assert "chatgpt" in result
        assert len(result["chatgpt"]) > 0


class TestFormatModelList:
    """Tests for format_model_list() function."""

    def test_empty_dict(self):
        """Empty dict returns empty string."""
        result = models.format_model_list({})
        assert result == ""

    def test_single_provider(self):
        """Formats single provider correctly."""
        data = {"chatgpt": ["gpt-5.4", "gpt-5.4-mini"]}
        result = models.format_model_list(data)

        assert "chatgpt:" in result
        assert "gpt-5.4" in result
        assert "gpt-5.4-mini" in result

    def test_sorted_output(self):
        """Providers and models are sorted."""
        data = {"b-provider": ["z-model", "a-model"], "a-provider": ["model-2", "model-1"]}
        result = models.format_model_list(data)

        lines = result.strip().split("\n")
        # First provider should be a-provider (sorted)
        assert "a-provider:" in lines[0]

    def test_format_structure(self):
        """Output has provider header and indented models."""
        data = {"chatgpt": ["gpt-5.4"]}
        result = models.format_model_list(data)

        lines = [line for line in result.split("\n") if line.strip()]
        assert len(lines) == 2
        assert lines[0].startswith("chatgpt:")
        assert lines[1].startswith("  ")  # Indented
        assert "gpt-5.4" in lines[1]
