"""Tests for maestro.providers.registry module."""

from typing import AsyncIterator

import pytest

from maestro.providers import registry
from maestro.providers.base import Message, ProviderPlugin


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
        from functools import lru_cache

        from maestro.providers import chatgpt

        @lru_cache(maxsize=1)
        def mock_discover():
            return {"chatgpt": chatgpt.ChatGPTProvider}

        original = registry.discover_providers
        self_auth_required = chatgpt.ChatGPTProvider.auth_required
        self_is_authenticated = chatgpt.ChatGPTProvider.is_authenticated
        chatgpt.ChatGPTProvider.auth_required = lambda self: True
        chatgpt.ChatGPTProvider.is_authenticated = lambda self: False
        try:
            registry.discover_providers = mock_discover
            mock_discover.cache_clear()
            provider = registry.get_default_provider()
            assert provider.id == "chatgpt"
        finally:
            registry.discover_providers = original
            registry.discover_providers.cache_clear()
            chatgpt.ChatGPTProvider.auth_required = self_auth_required
            chatgpt.ChatGPTProvider.is_authenticated = self_is_authenticated

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


class TestDuplicateProviderIds:
    """Tests for WR-03: Duplicate provider IDs are rejected deterministically."""

    def test_duplicate_provider_id_raises(self, monkeypatch):
        """Duplicate provider IDs raise ValueError during discovery."""
        from functools import lru_cache

        # Create two provider classes with the same ID
        class ProviderOne:
            def __init__(self):
                self.id = "duplicate-id"
                self._name = "Provider One"

            @property
            def name(self):
                return self._name

            def list_models(self):
                return ["model-1"]

            async def stream(self, messages, model, tools=None):
                if False:
                    yield None

            def auth_required(self):
                return False

            def login(self):
                pass

            def is_authenticated(self):
                return True

        class ProviderTwo:
            def __init__(self):
                self.id = "duplicate-id"  # Same ID!
                self._name = "Provider Two"

            @property
            def name(self):
                return self._name

            def list_models(self):
                return ["model-2"]

            async def stream(self, messages, model, tools=None):
                if False:
                    yield None

            def auth_required(self):
                return False

            def login(self):
                pass

            def is_authenticated(self):
                return True

        # Create mock EntryPoint class
        class MockEntryPoint:
            def __init__(self, name, group, provider_class):
                self.name = name
                self.group = group
                self._provider_class = provider_class

            def load(self):
                return self._provider_class

        # Mock entry points function returning duplicates
        def mock_entry_points(group):
            return [
                MockEntryPoint("provider-one", "maestro.providers", ProviderOne),
                MockEntryPoint("provider-two", "maestro.providers", ProviderTwo),
            ]

        # Replace entry_points function
        monkeypatch.setattr(registry, "entry_points", mock_entry_points)

        # Clear cache and discover
        original_discover = registry.discover_providers
        registry.discover_providers = lru_cache(maxsize=1)(registry.discover_providers.__wrapped__)
        registry.discover_providers.cache_clear()

        try:
            with pytest.raises(registry.DuplicateProviderError) as exc_info:
                registry.discover_providers()

            assert "Duplicate provider id" in str(exc_info.value)
            assert "duplicate-id" in str(exc_info.value)
            assert "provider-two" in str(exc_info.value)
        finally:
            # Restore
            registry.discover_providers = original_discover
            registry.discover_providers.cache_clear()

    def test_provider_raising_value_error_on_load_is_skipped(self, monkeypatch):
        """A provider whose ep.load() raises ValueError does not abort discovery."""
        from functools import lru_cache

        class ValidProvider:
            def __init__(self):
                self.id = "valid"

            @property
            def name(self):
                return "Valid"

            def list_models(self):
                return ["valid-model"]

            async def stream(self, messages, model, tools=None):
                if False:
                    yield None

            def auth_required(self):
                return False

            def login(self):
                pass

            def is_authenticated(self):
                return True

        class RaisingEntryPoint:
            name = "raising-ep"

            def load(self):
                raise ValueError("simulated provider init error")

        class ValidEntryPoint:
            name = "valid-ep"

            def load(self):
                return ValidProvider

        def mock_entry_points(group):
            return [RaisingEntryPoint(), ValidEntryPoint()]

        monkeypatch.setattr(registry, "entry_points", mock_entry_points)

        original_discover = registry.discover_providers
        registry.discover_providers = lru_cache(maxsize=1)(registry.discover_providers.__wrapped__)
        registry.discover_providers.cache_clear()

        try:
            providers = registry.discover_providers()
            # The misbehaving provider is skipped; the valid one still loads
            assert "valid" in providers
        finally:
            registry.discover_providers = original_discover
            registry.discover_providers.cache_clear()


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

            async def stream(self, messages, model, tools=None):
                if False:
                    yield None

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

    def test_sync_stream_with_incompatible_annotation_is_skipped(self, monkeypatch):
        """Sync stream() with an explicitly incompatible return type is rejected."""
        from functools import lru_cache

        class SyncStreamProvider:
            def __init__(self):
                self.id = "sync-stream"

            @property
            def name(self):
                return "Sync Stream"

            def list_models(self):
                return ["sync-model"]

            def stream(self, messages, model, tools=None) -> list[str]:
                return iter([])

            def auth_required(self):
                return False

            def login(self):
                pass

            def is_authenticated(self):
                return True

        class ValidProvider:
            def __init__(self):
                self.id = "valid"

            @property
            def name(self):
                return "Valid"

            def list_models(self):
                return ["valid-model"]

            async def stream(self, messages, model, tools=None):
                if False:
                    yield None

            def auth_required(self):
                return False

            def login(self):
                pass

            def is_authenticated(self):
                return True

        class MockEntryPoint:
            def __init__(self, name, group, provider_class):
                self.name = name
                self.group = group
                self._provider_class = provider_class

            def load(self):
                return self._provider_class

        def mock_entry_points(group):
            return [
                MockEntryPoint("sync-stream", "maestro.providers", SyncStreamProvider),
                MockEntryPoint("valid", "maestro.providers", ValidProvider),
            ]

        monkeypatch.setattr(registry, "entry_points", mock_entry_points)

        original_discover = registry.discover_providers
        registry.discover_providers = lru_cache(maxsize=1)(
            registry.discover_providers.__wrapped__
        )
        registry.discover_providers.cache_clear()

        try:
            providers = registry.discover_providers()
            assert "sync-stream" not in providers
            assert "valid" in providers
        finally:
            registry.discover_providers = original_discover
            registry.discover_providers.cache_clear()

    def test_sync_stream_without_annotation_is_allowed(self, monkeypatch):
        """Sync stream() with the right callable shape is allowed without annotations."""
        from functools import lru_cache

        class AsyncIteratorResult:
            def __aiter__(self):
                return self

            async def __anext__(self):
                raise StopAsyncIteration

        class SyncAsyncIteratorProvider:
            def __init__(self):
                self.id = "sync-no-annotation"

            @property
            def name(self):
                return "Sync No Annotation"

            def list_models(self):
                return ["valid-model"]

            def stream(self, messages, model, tools=None):
                return AsyncIteratorResult()

            def auth_required(self):
                return False

            def login(self):
                pass

            def is_authenticated(self):
                return True

        class MockEntryPoint:
            def __init__(self, name, group, provider_class):
                self.name = name
                self.group = group
                self._provider_class = provider_class

            def load(self):
                return self._provider_class

        def mock_entry_points(group):
            return [
                MockEntryPoint(
                    "sync-no-annotation",
                    "maestro.providers",
                    SyncAsyncIteratorProvider,
                )
            ]

        monkeypatch.setattr(registry, "entry_points", mock_entry_points)

        original_discover = registry.discover_providers
        registry.discover_providers = lru_cache(maxsize=1)(
            registry.discover_providers.__wrapped__
        )
        registry.discover_providers.cache_clear()

        try:
            providers = registry.discover_providers()
            assert "sync-no-annotation" in providers
        finally:
            registry.discover_providers = original_discover
            registry.discover_providers.cache_clear()

    def test_sync_stream_returning_async_iterator_is_allowed(self, monkeypatch):
        """A sync stream() returning an AsyncIterator still satisfies the contract."""
        from functools import lru_cache

        class AsyncIteratorResult:
            def __aiter__(self):
                return self

            async def __anext__(self):
                raise StopAsyncIteration

        class SyncAsyncIteratorProvider:
            def __init__(self):
                self.id = "sync-async-iterator"

            @property
            def name(self):
                return "Sync Async Iterator"

            def list_models(self):
                return ["valid-model"]

            def stream(
                self, messages, model, tools=None
            ) -> AsyncIterator[str | Message]:
                return AsyncIteratorResult()

            def auth_required(self):
                return False

            def login(self):
                pass

            def is_authenticated(self):
                return True

        class MockEntryPoint:
            def __init__(self, name, group, provider_class):
                self.name = name
                self.group = group
                self._provider_class = provider_class

            def load(self):
                return self._provider_class

        def mock_entry_points(group):
            return [
                MockEntryPoint(
                    "sync-async-iterator",
                    "maestro.providers",
                    SyncAsyncIteratorProvider,
                )
            ]

        monkeypatch.setattr(registry, "entry_points", mock_entry_points)

        original_discover = registry.discover_providers
        registry.discover_providers = lru_cache(maxsize=1)(
            registry.discover_providers.__wrapped__
        )
        registry.discover_providers.cache_clear()

        try:
            providers = registry.discover_providers()
            assert "sync-async-iterator" in providers
        finally:
            registry.discover_providers = original_discover
            registry.discover_providers.cache_clear()

    def test_sync_stream_with_string_async_iterator_annotation_is_allowed(
        self, monkeypatch
    ):
        """Stringified AsyncIterator annotations are accepted during discovery."""
        from functools import lru_cache

        class AsyncIteratorResult:
            def __aiter__(self):
                return self

            async def __anext__(self):
                raise StopAsyncIteration

        class FutureAnnotatedProvider:
            def __init__(self):
                self.id = "future-annotated"

            @property
            def name(self):
                return "Future Annotated"

            def list_models(self):
                return ["valid-model"]

            def stream(
                self, messages, model, tools=None
            ) -> "AsyncIterator[str | Message]":
                return AsyncIteratorResult()

            def auth_required(self):
                return False

            def login(self):
                pass

            def is_authenticated(self):
                return True

        class MockEntryPoint:
            def __init__(self, name, group, provider_class):
                self.name = name
                self.group = group
                self._provider_class = provider_class

            def load(self):
                return self._provider_class

        def mock_entry_points(group):
            return [
                MockEntryPoint(
                    "future-annotated",
                    "maestro.providers",
                    FutureAnnotatedProvider,
                )
            ]

        monkeypatch.setattr(registry, "entry_points", mock_entry_points)

        original_discover = registry.discover_providers
        registry.discover_providers = lru_cache(maxsize=1)(
            registry.discover_providers.__wrapped__
        )
        registry.discover_providers.cache_clear()

        try:
            providers = registry.discover_providers()
            assert "future-annotated" in providers
        finally:
            registry.discover_providers = original_discover
            registry.discover_providers.cache_clear()

    def test_coroutine_stream_provider_skipped(self, monkeypatch):
        """Coroutine-returning stream() implementations are rejected."""
        from functools import lru_cache

        class CoroutineStreamProvider:
            def __init__(self):
                self.id = "coroutine-stream"

            @property
            def name(self):
                return "Coroutine Stream"

            def list_models(self):
                return ["broken-model"]

            async def stream(self, messages, model, tools=None) -> AsyncIterator[str | Message]:
                return Message(role="assistant", content="not-an-iterator")

            def auth_required(self):
                return False

            def login(self):
                pass

            def is_authenticated(self):
                return True

        class ValidProvider:
            def __init__(self):
                self.id = "valid"

            @property
            def name(self):
                return "Valid"

            def list_models(self):
                return ["valid-model"]

            async def stream(self, messages, model, tools=None):
                if False:
                    yield None

            def auth_required(self):
                return False

            def login(self):
                pass

            def is_authenticated(self):
                return True

        class MockEntryPoint:
            def __init__(self, name, group, provider_class):
                self.name = name
                self.group = group
                self._provider_class = provider_class

            def load(self):
                return self._provider_class

        def mock_entry_points(group):
            return [
                MockEntryPoint(
                    "coroutine-stream",
                    "maestro.providers",
                    CoroutineStreamProvider,
                ),
                MockEntryPoint("valid", "maestro.providers", ValidProvider),
            ]

        monkeypatch.setattr(registry, "entry_points", mock_entry_points)

        original_discover = registry.discover_providers
        registry.discover_providers = lru_cache(maxsize=1)(
            registry.discover_providers.__wrapped__
        )
        registry.discover_providers.cache_clear()

        try:
            providers = registry.discover_providers()
            assert "coroutine-stream" not in providers
            assert "valid" in providers
        finally:
            registry.discover_providers = original_discover
            registry.discover_providers.cache_clear()

    def test_stream_with_required_keyword_only_arg_is_skipped(self, monkeypatch):
        """Providers requiring extra keyword-only stream args are rejected."""
        from functools import lru_cache

        class KeywordOnlyProvider:
            def __init__(self):
                self.id = "keyword-only"

            @property
            def name(self):
                return "Keyword Only"

            def list_models(self):
                return ["broken-model"]

            async def stream(self, messages, model, *, request_id, tools=None):
                if False:
                    yield None

            def auth_required(self):
                return False

            def login(self):
                pass

            def is_authenticated(self):
                return True

        class ValidProvider:
            def __init__(self):
                self.id = "valid"

            @property
            def name(self):
                return "Valid"

            def list_models(self):
                return ["valid-model"]

            async def stream(self, messages, model, tools=None):
                if False:
                    yield None

            def auth_required(self):
                return False

            def login(self):
                pass

            def is_authenticated(self):
                return True

        class MockEntryPoint:
            def __init__(self, name, group, provider_class):
                self.name = name
                self.group = group
                self._provider_class = provider_class

            def load(self):
                return self._provider_class

        def mock_entry_points(group):
            return [
                MockEntryPoint("keyword-only", "maestro.providers", KeywordOnlyProvider),
                MockEntryPoint("valid", "maestro.providers", ValidProvider),
            ]

        monkeypatch.setattr(registry, "entry_points", mock_entry_points)

        original_discover = registry.discover_providers
        registry.discover_providers = lru_cache(maxsize=1)(
            registry.discover_providers.__wrapped__
        )
        registry.discover_providers.cache_clear()

        try:
            providers = registry.discover_providers()
            assert "keyword-only" not in providers
            assert "valid" in providers
        finally:
            registry.discover_providers = original_discover
            registry.discover_providers.cache_clear()

    def test_stream_not_called_during_discovery(self, monkeypatch):
        """Discovery validates provider shape without executing stream()."""
        from functools import lru_cache

        class LazyValidatedProvider:
            def __init__(self):
                self.id = "lazy-validated"

            @property
            def name(self):
                return "Lazy Validated"

            def list_models(self):
                return ["lazy-model"]

            def stream(
                self, messages, model, tools=None
            ) -> AsyncIterator[str | Message]:
                raise RuntimeError("stream() must not run during discovery")

            def auth_required(self):
                return False

            def login(self):
                pass

            def is_authenticated(self):
                return True

        class MockEntryPoint:
            def __init__(self, name, group, provider_class):
                self.name = name
                self.group = group
                self._provider_class = provider_class

            def load(self):
                return self._provider_class

        def mock_entry_points(group):
            return [
                MockEntryPoint(
                    "lazy-validated",
                    "maestro.providers",
                    LazyValidatedProvider,
                )
            ]

        monkeypatch.setattr(registry, "entry_points", mock_entry_points)

        original_discover = registry.discover_providers
        registry.discover_providers = lru_cache(maxsize=1)(
            registry.discover_providers.__wrapped__
        )
        registry.discover_providers.cache_clear()

        try:
            providers = registry.discover_providers()
            assert "lazy-validated" in providers
        finally:
            registry.discover_providers = original_discover
            registry.discover_providers.cache_clear()

    def test_provider_with_invalid_list_models_signature_is_skipped(self, monkeypatch):
        """Providers with incompatible non-stream call signatures are rejected."""
        from functools import lru_cache

        class InvalidListModelsProvider:
            def __init__(self):
                self.id = "invalid-list-models"

            @property
            def name(self):
                return "Invalid List Models"

            def list_models(self, scope):
                return [scope]

            async def stream(self, messages, model, tools=None):
                if False:
                    yield None

            def auth_required(self):
                return False

            def login(self):
                pass

            def is_authenticated(self):
                return True

        class ValidProvider:
            def __init__(self):
                self.id = "valid"

            @property
            def name(self):
                return "Valid"

            def list_models(self):
                return ["valid-model"]

            async def stream(self, messages, model, tools=None):
                if False:
                    yield None

            def auth_required(self):
                return False

            def login(self):
                pass

            def is_authenticated(self):
                return True

        class MockEntryPoint:
            def __init__(self, name, group, provider_class):
                self.name = name
                self.group = group
                self._provider_class = provider_class

            def load(self):
                return self._provider_class

        def mock_entry_points(group):
            return [
                MockEntryPoint(
                    "invalid-list-models",
                    "maestro.providers",
                    InvalidListModelsProvider,
                ),
                MockEntryPoint("valid", "maestro.providers", ValidProvider),
            ]

        monkeypatch.setattr(registry, "entry_points", mock_entry_points)

        original_discover = registry.discover_providers
        registry.discover_providers = lru_cache(maxsize=1)(
            registry.discover_providers.__wrapped__
        )
        registry.discover_providers.cache_clear()

        try:
            providers = registry.discover_providers()
            assert "invalid-list-models" not in providers
            assert "valid" in providers
        finally:
            registry.discover_providers = original_discover
            registry.discover_providers.cache_clear()

    def test_provider_with_optional_login_arg_is_allowed(self, monkeypatch):
        """Providers may add optional parameters without breaking the protocol."""
        from functools import lru_cache

        class OptionalLoginProvider:
            def __init__(self):
                self.id = "optional-login"

            @property
            def name(self):
                return "Optional Login"

            def list_models(self):
                return ["valid-model"]

            async def stream(self, messages, model, tools=None):
                if False:
                    yield None

            def auth_required(self):
                return True

            def login(self, method="browser"):
                return method

            def is_authenticated(self):
                return True

        class MockEntryPoint:
            def __init__(self, name, group, provider_class):
                self.name = name
                self.group = group
                self._provider_class = provider_class

            def load(self):
                return self._provider_class

        def mock_entry_points(group):
            return [
                MockEntryPoint(
                    "optional-login",
                    "maestro.providers",
                    OptionalLoginProvider,
                )
            ]

        monkeypatch.setattr(registry, "entry_points", mock_entry_points)

        original_discover = registry.discover_providers
        registry.discover_providers = lru_cache(maxsize=1)(
            registry.discover_providers.__wrapped__
        )
        registry.discover_providers.cache_clear()

        try:
            providers = registry.discover_providers()
            assert "optional-login" in providers
        finally:
            registry.discover_providers = original_discover
            registry.discover_providers.cache_clear()

    def test_provider_with_optional_keyword_only_login_arg_is_allowed(self, monkeypatch):
        """Optional keyword-only parameters should not break the protocol."""
        from functools import lru_cache

        class OptionalKeywordOnlyLoginProvider:
            def __init__(self):
                self.id = "optional-kw-login"

            @property
            def name(self):
                return "Optional KW Login"

            def list_models(self):
                return ["valid-model"]

            async def stream(self, messages, model, tools=None):
                if False:
                    yield None

            def auth_required(self):
                return True

            def login(self, *, method="browser"):
                return method

            def is_authenticated(self):
                return True

        class MockEntryPoint:
            def __init__(self, name, group, provider_class):
                self.name = name
                self.group = group
                self._provider_class = provider_class

            def load(self):
                return self._provider_class

        def mock_entry_points(group):
            return [
                MockEntryPoint(
                    "optional-kw-login",
                    "maestro.providers",
                    OptionalKeywordOnlyLoginProvider,
                )
            ]

        monkeypatch.setattr(registry, "entry_points", mock_entry_points)

        original_discover = registry.discover_providers
        registry.discover_providers = lru_cache(maxsize=1)(
            registry.discover_providers.__wrapped__
        )
        registry.discover_providers.cache_clear()

        try:
            providers = registry.discover_providers()
            assert "optional-kw-login" in providers
        finally:
            registry.discover_providers = original_discover
            registry.discover_providers.cache_clear()


class TestGetDefaultProviderAuthLogic:
    """Tests for WR-02: Provider selection respects auth_required()."""

    def test_returns_auth_free_provider_when_no_authenticated_provider_exists(self, monkeypatch):
        """Auth-free providers remain valid generic defaults."""
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
            assert provider.id == "auth-free"
        finally:
            registry.discover_providers = original
            registry.discover_providers.cache_clear()

    def test_prefers_authenticated_provider_before_chatgpt_fallback(self, monkeypatch):
        """Authenticated providers win before unauthenticated ChatGPT fallback."""
        from functools import lru_cache

        from maestro.providers import chatgpt

        class AuthenticatedProvider:
            def __init__(self):
                self.id = "authenticated"
                self._name = "Authenticated"

            @property
            def name(self):
                return self._name

            def list_models(self):
                return ["auth-model"]

            async def stream(self, messages, model, tools=None):
                if False:
                    yield None

            def auth_required(self):
                return True

            def login(self):
                pass

            def is_authenticated(self):
                return True

        monkeypatch.setattr(chatgpt.ChatGPTProvider, "auth_required", lambda self: True)
        monkeypatch.setattr(chatgpt.ChatGPTProvider, "is_authenticated", lambda self: False)

        @lru_cache(maxsize=1)
        def mock_discover():
            return {
                "chatgpt": chatgpt.ChatGPTProvider,
                "authenticated": AuthenticatedProvider,
            }

        original = registry.discover_providers
        monkeypatch.setattr(registry, "discover_providers", mock_discover)
        mock_discover.cache_clear()

        try:
            provider = registry.get_default_provider()
            assert provider.id == "authenticated"
        finally:
            registry.discover_providers = original
            registry.discover_providers.cache_clear()

    def test_prefers_first_authenticated_provider_in_discovery_order(self, monkeypatch):
        """First authenticated provider wins even when it is ChatGPT."""
        from functools import lru_cache

        from maestro.providers import chatgpt

        class AuthenticatedProvider:
            def __init__(self):
                self.id = "authenticated"
                self._name = "Authenticated"

            @property
            def name(self):
                return self._name

            def list_models(self):
                return ["auth-model"]

            async def stream(self, messages, model, tools=None):
                if False:
                    yield None

            def auth_required(self):
                return True

            def login(self):
                pass

            def is_authenticated(self):
                return True

        monkeypatch.setattr(chatgpt.ChatGPTProvider, "auth_required", lambda self: True)
        monkeypatch.setattr(chatgpt.ChatGPTProvider, "is_authenticated", lambda self: True)

        @lru_cache(maxsize=1)
        def mock_discover():
            return {
                "chatgpt": chatgpt.ChatGPTProvider,
                "authenticated": AuthenticatedProvider,
            }

        original = registry.discover_providers
        monkeypatch.setattr(registry, "discover_providers", mock_discover)
        mock_discover.cache_clear()

        try:
            provider = registry.get_default_provider()
            assert provider.id == "chatgpt"
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
