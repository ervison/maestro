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

    def test_priority_1_model_flag_bypasses_invalid_config(self, monkeypatch):
        """Explicit --model resolution does not depend on loading config first."""
        monkeypatch.setattr(
            config,
            "load",
            lambda: (_ for _ in ()).throw(RuntimeError("Invalid config file")),
        )

        provider, model_id = models.resolve_model(model_flag="chatgpt/gpt-5.4")
        assert provider.id == "chatgpt"
        assert model_id == "gpt-5.4"

    def test_priority_2_env_variable(self, monkeypatch):
        """MAESTRO_MODEL env var is priority 2."""
        # Set up config that should be ignored
        cfg = config.Config(model="chatgpt/gpt-5.4-mini")
        monkeypatch.setattr(config, "load", lambda: cfg)

        # Env should win
        monkeypatch.setenv("MAESTRO_MODEL", "chatgpt/gpt-5.2")
        provider, model_id = models.resolve_model()
        assert model_id == "gpt-5.2"

    def test_priority_2_env_variable_bypasses_invalid_config(self, monkeypatch):
        """MAESTRO_MODEL resolution does not depend on loading config first."""
        monkeypatch.setenv("MAESTRO_MODEL", "chatgpt/gpt-5.2")
        monkeypatch.setattr(
            config,
            "load",
            lambda: (_ for _ in ()).throw(RuntimeError("Invalid config file")),
        )

        provider, model_id = models.resolve_model()
        assert provider.id == "chatgpt"
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
        from functools import lru_cache

        from maestro.providers import chatgpt, registry

        cfg = config.Config()  # No model set
        monkeypatch.setattr(config, "load", lambda: cfg)

        @lru_cache(maxsize=1)
        def mock_discover():
            return {"chatgpt": chatgpt.ChatGPTProvider}

        original = registry.discover_providers
        monkeypatch.setattr(registry, "discover_providers", mock_discover)
        mock_discover.cache_clear()

        try:
            provider, model_id = models.resolve_model()
            assert provider.id == "chatgpt"
            # Should get first available model
            assert model_id in provider.list_models()
        finally:
            registry.discover_providers = original
            registry.discover_providers.cache_clear()

    def test_priority_5_fallback_chatgpt_even_when_unauthenticated(self, monkeypatch):
        """WR-01: Empty-config path falls back to ChatGPT even when unauthenticated.

        This is a regression test ensuring that when no providers are usable
        (all require auth and none are authenticated), resolve_model() still
        returns ChatGPT with DEFAULT_MODEL to preserve backward compatibility.
        """
        from maestro.providers import chatgpt, registry
        from functools import lru_cache

        cfg = config.Config()  # No model set
        monkeypatch.setattr(config, "load", lambda: cfg)

        # Patch ChatGPT to require auth but not be authenticated
        monkeypatch.setattr(chatgpt.ChatGPTProvider, "auth_required", lambda self: True)
        monkeypatch.setattr(chatgpt.ChatGPTProvider, "is_authenticated", lambda self: False)

        # Mock discover_providers to only include the patched ChatGPT
        @lru_cache(maxsize=1)
        def mock_discover():
            return {"chatgpt": chatgpt.ChatGPTProvider}

        original = registry.discover_providers
        monkeypatch.setattr(registry, "discover_providers", mock_discover)
        mock_discover.cache_clear()

        try:
            # Should still return ChatGPT even though it's not "usable"
            provider, model_id = models.resolve_model()
            assert provider.id == "chatgpt"
            assert model_id == chatgpt.DEFAULT_MODEL
        finally:
            registry.discover_providers = original
            registry.discover_providers.cache_clear()

    def test_priority_5_uses_auth_free_provider_when_no_authenticated_provider_exists(
        self, monkeypatch
    ):
        """Generic resolution returns an auth-free provider before ChatGPT fallback."""
        from functools import lru_cache

        from maestro.providers import chatgpt, registry

        class AuthFreeProvider:
            id = "auth-free"

            def auth_required(self):
                return False

            def is_authenticated(self):
                return False

            def list_models(self):
                return ["free-model"]

        cfg = config.Config()
        monkeypatch.setattr(config, "load", lambda: cfg)
        monkeypatch.setattr(chatgpt.ChatGPTProvider, "auth_required", lambda self: True)
        monkeypatch.setattr(chatgpt.ChatGPTProvider, "is_authenticated", lambda self: False)

        @lru_cache(maxsize=1)
        def mock_discover():
            return {
                "auth-free": AuthFreeProvider,
                "chatgpt": chatgpt.ChatGPTProvider,
            }

        original = registry.discover_providers
        monkeypatch.setattr(registry, "discover_providers", mock_discover)
        mock_discover.cache_clear()

        try:
            provider, model_id = models.resolve_model()
            assert provider.id == "auth-free"
            assert model_id == "free-model"
        finally:
            registry.discover_providers = original
            registry.discover_providers.cache_clear()

    def test_parse_error_propagates(self):
        """Invalid model string raises ValueError."""
        with pytest.raises(ValueError):
            models.resolve_model(model_flag="invalid-no-slash")

    def test_unknown_provider_raises(self):
        """Unknown provider raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            models.resolve_model(model_flag="unknown/model")

        assert "Unknown provider" in str(exc_info.value)


class TestIsUsable:
    """Tests for _is_usable() helper function."""

    def test_auth_free_provider_is_usable(self):
        """Provider with auth_required=False is usable regardless of auth state."""
        class AuthFreeProvider:
            def auth_required(self):
                return False

            def is_authenticated(self):
                return False

        assert models._is_usable(AuthFreeProvider()) is True

    def test_auth_required_and_authenticated_is_usable(self):
        """Provider requiring auth with valid credentials is usable."""
        class AuthRequiredProvider:
            def auth_required(self):
                return True

            def is_authenticated(self):
                return True

        assert models._is_usable(AuthRequiredProvider()) is True

    def test_auth_required_but_not_authenticated_is_not_usable(self):
        """Provider requiring auth without credentials is not usable."""
        class UnauthenticatedProvider:
            def auth_required(self):
                return True

            def is_authenticated(self):
                return False

        assert models._is_usable(UnauthenticatedProvider()) is False


class TestGetAvailableModels:
    """Tests for get_available_models() function."""

    def test_returns_authenticated_providers(self, monkeypatch):
        """Only includes authenticated providers (WR-02 fix)."""
        # Mock ChatGPTProvider to require auth but not be authenticated
        from maestro.providers import chatgpt

        monkeypatch.setattr(chatgpt.ChatGPTProvider, "auth_required", lambda self: True)
        monkeypatch.setattr(chatgpt.ChatGPTProvider, "is_authenticated", lambda self: False)

        result = models.get_available_models()
        assert result == {}

    def test_includes_chatgpt_when_authenticated(self, monkeypatch):
        """Includes chatgpt models when authenticated."""
        from maestro.providers import chatgpt

        monkeypatch.setattr(chatgpt.ChatGPTProvider, "auth_required", lambda self: True)
        monkeypatch.setattr(chatgpt.ChatGPTProvider, "is_authenticated", lambda self: True)
        result = models.get_available_models()
        assert "chatgpt" in result
        assert len(result["chatgpt"]) > 0

    def test_includes_auth_free_provider(self, monkeypatch):
        """Includes auth-free providers even when not authenticated (WR-02 fix)."""
        from maestro.providers import chatgpt

        # ChatGPT requires auth but isn't authenticated
        monkeypatch.setattr(chatgpt.ChatGPTProvider, "auth_required", lambda self: True)
        monkeypatch.setattr(chatgpt.ChatGPTProvider, "is_authenticated", lambda self: False)

        # Add a mock auth-free provider
        class AuthFreeProvider:
            id = "auth-free"

            def auth_required(self):
                return False

            def is_authenticated(self):
                return False

            def list_models(self):
                return ["free-model"]

        # Mock discover_providers to include both
        from maestro.providers import registry
        from functools import lru_cache

        @lru_cache(maxsize=1)
        def mock_discover():
            return {
                "chatgpt": chatgpt.ChatGPTProvider,
                "auth-free": AuthFreeProvider,
            }

        original = registry.discover_providers
        monkeypatch.setattr(registry, "discover_providers", mock_discover)
        mock_discover.cache_clear()

        try:
            result = models.get_available_models()
            # Auth-free provider should be included even though not authenticated
            assert "auth-free" in result
            assert "free-model" in result["auth-free"]
            # ChatGPT should NOT be included (requires auth but not authenticated)
            assert "chatgpt" not in result
        finally:
            registry.discover_providers = original
            registry.discover_providers.cache_clear()


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
