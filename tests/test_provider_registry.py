"""Tests for maestro.providers.registry module."""

import pytest

from maestro.providers import registry
from maestro.providers.base import ProviderPlugin


class TestDiscoverProviders:
    """Tests for discover_providers() function."""

    def test_discovers_chatgpt_provider(self):
        """Registry discovers chatgpt provider from entry points."""
        providers = registry.discover_providers()
        assert "chatgpt" in providers

    def test_returns_provider_classes(self):
        """Discovered values are provider classes."""
        providers = registry.discover_providers()
        chatgpt_class = providers["chatgpt"]

        # Can instantiate the class
        instance = chatgpt_class()
        assert isinstance(instance, ProviderPlugin)
        assert instance.id == "chatgpt"

    def test_caching(self):
        """Results are cached across calls."""
        # Clear cache first
        registry.discover_providers.cache_clear()

        first = registry.discover_providers()
        second = registry.discover_providers()

        # Should be same object due to lru_cache
        assert first is second


class TestListProviders:
    """Tests for list_providers() function."""

    def test_returns_sorted_list(self):
        """Returns sorted list of provider IDs."""
        providers = registry.list_providers()
        assert isinstance(providers, list)
        assert "chatgpt" in providers
        # List should be sorted
        assert providers == sorted(providers)


class TestGetProvider:
    """Tests for get_provider() function."""

    def test_returns_chatgpt_provider(self):
        """Can get chatgpt provider by ID."""
        provider = registry.get_provider("chatgpt")
        assert isinstance(provider, ProviderPlugin)
        assert provider.id == "chatgpt"
        assert provider.name == "ChatGPT"

    def test_raises_for_unknown_provider(self):
        """Raises ValueError for unknown provider."""
        with pytest.raises(ValueError) as exc_info:
            registry.get_provider("nonexistent-provider")

        assert "Unknown provider" in str(exc_info.value)
        assert "nonexistent-provider" in str(exc_info.value)
        # Should include available providers in message
        assert "chatgpt" in str(exc_info.value)

    def test_error_message_format(self):
        """Error message has helpful format."""
        with pytest.raises(ValueError) as exc_info:
            registry.get_provider("unknown")

        msg = str(exc_info.value)
        assert "Unknown provider" in msg
        assert "Available providers" in msg


class TestGetDefaultProvider:
    """Tests for get_default_provider() function."""

    def test_returns_chatgpt_when_no_auth(self):
        """Returns chatgpt provider when no providers authenticated."""
        provider = registry.get_default_provider()
        assert provider.id == "chatgpt"

    def test_returns_provider_instance(self):
        """Returns a ProviderPlugin instance."""
        from maestro.providers.base import ProviderPlugin

        provider = registry.get_default_provider()
        assert isinstance(provider, ProviderPlugin)

    def test_raises_when_no_providers_installed(self, monkeypatch):
        """Raises ValueError when no providers installed."""
        from functools import lru_cache

        # Create cached function that returns empty dict
        @lru_cache(maxsize=1)
        def mock_discover():
            return {}

        # Replace with mock and clear any existing cache
        original = registry.discover_providers
        monkeypatch.setattr(registry, "discover_providers", mock_discover)
        mock_discover.cache_clear()

        try:
            with pytest.raises(ValueError) as exc_info:
                registry.get_default_provider()

            assert "No providers installed" in str(exc_info.value)
        finally:
            # Restore original and clear
            registry.discover_providers = original
            registry.discover_providers.cache_clear()


class TestIsUsable:
    """Tests for _is_usable() helper function."""

    def test_auth_free_provider_is_usable(self):
        """Provider with auth_required=False is always usable."""
        # Create a mock provider that doesn't require auth
        class AuthFreeProvider:
            def auth_required(self):
                return False

            def is_authenticated(self):
                return False  # Not authenticated but not required

        provider = AuthFreeProvider()
        assert registry._is_usable(provider) is True

    def test_auth_required_and_authenticated_is_usable(self):
        """Provider with auth_required=True and is_authenticated=True is usable."""
        class AuthRequiredProvider:
            def auth_required(self):
                return True

            def is_authenticated(self):
                return True

        provider = AuthRequiredProvider()
        assert registry._is_usable(provider) is True

    def test_auth_required_but_not_authenticated_is_not_usable(self):
        """Provider with auth_required=True but is_authenticated=False is not usable."""
        class UnauthenticatedProvider:
            def auth_required(self):
                return True

            def is_authenticated(self):
                return False

        provider = UnauthenticatedProvider()
        assert registry._is_usable(provider) is False


class TestProviderContractValidation:
    """Tests for WR-01: Provider contract validation at discovery time."""

    def test_malformed_entry_point_skipped(self, monkeypatch):
        """Entry points that don't implement ProviderPlugin are skipped."""
        from functools import lru_cache

        # Create a malformed provider class (missing required methods)
        class MalformedProvider:
            def __init__(self):
                self.id = "malformed"
            # Missing list_models, stream, auth_required, login, is_authenticated

        # Create a valid provider class
        class ValidProvider:
            def __init__(self):
                self.id = "valid"

            def list_models(self):
                return []

            def stream(self, messages, model, tools=None):
                return iter([])

            def auth_required(self):
                return False

            def login(self):
                pass

            def is_authenticated(self):
                return True

            @property
            def name(self):
                return "Valid"

        # Create mock EntryPoint class that allows setting load
        class MockEntryPoint:
            def __init__(self, name, group, provider_class):
                self.name = name
                self.group = group
                self._provider_class = provider_class

            def load(self):
                return self._provider_class

        # Mock entry points function
        def mock_entry_points(group):
            return [
                MockEntryPoint("malformed", "maestro.providers", MalformedProvider),
                MockEntryPoint("valid", "maestro.providers", ValidProvider),
            ]

        # Replace entry_points function
        monkeypatch.setattr(registry, "entry_points", mock_entry_points)

        # Clear cache and discover
        original_discover = registry.discover_providers
        registry.discover_providers = lru_cache(maxsize=1)(registry.discover_providers.__wrapped__)
        registry.discover_providers.cache_clear()

        try:
            providers = registry.discover_providers()

            # Malformed provider should be skipped, valid should be present
            assert "malformed" not in providers
            assert "valid" in providers
        finally:
            # Restore
            registry.discover_providers = original_discover
            registry.discover_providers.cache_clear()


class TestGetDefaultProviderAuthLogic:
    """Tests for WR-02: Provider selection respects auth_required()."""

    def test_prefers_auth_free_provider(self, monkeypatch):
        """When an auth-free provider is available, it is selected."""
        from functools import lru_cache

        class AuthFreeProvider:
            def __init__(self):
                self.id = "auth-free"
                self._name = "Auth Free"

            @property
            def name(self):
                return self._name

            def list_models(self):
                return ["model-1"]

            def stream(self, messages, model, tools=None):
                return iter([])

            def auth_required(self):
                return False

            def login(self):
                pass

            def is_authenticated(self):
                return False

        class AuthRequiredProvider:
            def __init__(self):
                self.id = "auth-required"
                self._name = "Auth Required"

            @property
            def name(self):
                return self._name

            def list_models(self):
                return ["model-2"]

            def stream(self, messages, model, tools=None):
                return iter([])

            def auth_required(self):
                return True

            def login(self):
                pass

            def is_authenticated(self):
                return False  # Not authenticated!

        # Mock discover_providers to return our test providers
        @lru_cache(maxsize=1)
        def mock_discover():
            return {
                "auth-required": AuthRequiredProvider,
                "auth-free": AuthFreeProvider,
            }

        original = registry.discover_providers
        monkeypatch.setattr(registry, "discover_providers", mock_discover)
        mock_discover.cache_clear()

        try:
            provider = registry.get_default_provider()
            # Should select the auth-free provider (auth-required is not usable)
            assert provider.id == "auth-free"
        finally:
            registry.discover_providers = original
            registry.discover_providers.cache_clear()

    def test_raises_when_no_usable_provider(self, monkeypatch):
        """When no provider is usable, raises ValueError."""
        from functools import lru_cache

        class UnusableProvider:
            def __init__(self):
                self.id = "unusable"
                self._name = "Unusable"

            @property
            def name(self):
                return self._name

            def list_models(self):
                return []

            def stream(self, messages, model, tools=None):
                return iter([])

            def auth_required(self):
                return True

            def login(self):
                pass

            def is_authenticated(self):
                return False  # Not authenticated!

        @lru_cache(maxsize=1)
        def mock_discover():
            return {"unusable": UnusableProvider}

        original = registry.discover_providers
        monkeypatch.setattr(registry, "discover_providers", mock_discover)
        mock_discover.cache_clear()

        try:
            with pytest.raises(ValueError) as exc_info:
                registry.get_default_provider()

            msg = str(exc_info.value)
            assert "No usable provider found" in msg
            assert "authenticate" in msg.lower() or "install" in msg.lower()
        finally:
            registry.discover_providers = original
            registry.discover_providers.cache_clear()
