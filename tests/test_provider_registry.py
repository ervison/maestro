from __future__ import annotations

from collections.abc import AsyncIterator
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import maestro.providers.registry as registry


class ValidProvider:
    @property
    def id(self) -> str:
        return "valid"

    @property
    def name(self) -> str:
        return "Valid"

    def list_models(self) -> list[str]:
        return ["model-a"]

    async def stream(self, messages, model, tools=None, **kwargs) -> AsyncIterator[str]:
        del messages, model, tools, kwargs
        if False:
            yield "never"

    def auth_required(self) -> bool:
        return False

    def login(self) -> None:
        return None

    def is_authenticated(self) -> bool:
        return False


class AuthenticatedProvider(ValidProvider):
    @property
    def id(self) -> str:
        return "authenticated"

    def auth_required(self) -> bool:
        return True

    def is_authenticated(self) -> bool:
        return True


class ChatGPTProvider(ValidProvider):
    @property
    def id(self) -> str:
        return "chatgpt"

    def auth_required(self) -> bool:
        return True


class PublicProvider(ValidProvider):
    @property
    def id(self) -> str:
        return "public"


class MissingMethodProvider:
    @property
    def id(self) -> str:
        return "broken"

    @property
    def name(self) -> str:
        return "Broken"

    def list_models(self) -> list[str]:
        return ["model"]

    def auth_required(self) -> bool:
        return False

    def login(self) -> None:
        return None

    def is_authenticated(self) -> bool:
        return False


class WrongStreamSignatureProvider(ValidProvider):
    async def stream(self, messages, model, extra, tools=None, **kwargs) -> AsyncIterator[str]:
        del messages, model, extra, tools, kwargs
        if False:
            yield "never"


class CoroutineStreamProvider(ValidProvider):
    async def stream(self, messages, model, tools=None, **kwargs) -> str:
        del messages, model, tools, kwargs
        return "wrong"


class NonCallableListModelsProvider(ValidProvider):
    list_models = "not-callable"


class MissingRequiredMethodArgProvider(ValidProvider):
    def list_models(self, include_hidden) -> list[str]:
        del include_hidden
        return ["model-a"]


class NoSelfListModelsProvider(ValidProvider):
    def list_models() -> list[str]:
        return ["model-a"]


class KeywordOnlySelfLikeMethodProvider(ValidProvider):
    def list_models(*, self_ref=None) -> list[str]:
        del self_ref
        return ["model-a"]


class KeywordOnlyRequiredMethodProvider(ValidProvider):
    def auth_required(self, *, required_flag) -> bool:
        del required_flag
        return False


class MissingStreamProvider(ValidProvider):
    stream = None


class TooFewStreamArgsProvider(ValidProvider):
    async def stream(self, messages) -> AsyncIterator[str]:
        del messages
        if False:
            yield "never"


class BadSelfKindStreamProvider(ValidProvider):
    async def stream(*, messages, model) -> AsyncIterator[str]:
        del messages, model
        if False:
            yield "never"


class KeywordOnlySelfLikeStreamProvider(ValidProvider):
    @staticmethod
    async def stream(*, self_ref, messages, model) -> AsyncIterator[str]:
        del self_ref, messages, model
        if False:
            yield "never"


class ForwardRefStreamProvider(ValidProvider):
    def stream(self, messages, model) -> "MissingType":
        del messages, model
        raise AssertionError("not called")


class PlainAnnotatedStreamProvider(ValidProvider):
    def stream(self, messages, model) -> str:
        del messages, model
        raise AssertionError("not called")


class UnannotatedPlainStreamProvider(ValidProvider):
    def stream(self, messages, model):
        del messages, model
        raise AssertionError("not called")


class InstanceOnlyStreamProvider(ValidProvider):
    stream = None

    def __init__(self) -> None:
        self.stream = lambda messages, model: None


@pytest.fixture(autouse=True)
def clear_discovery_cache() -> None:
    registry.discover_providers.cache_clear()
    yield
    registry.discover_providers.cache_clear()


def test_is_valid_provider_accepts_protocol_compatible_provider() -> None:
    assert registry._is_valid_provider(ValidProvider()) is True


def test_is_valid_provider_rejects_missing_stream_method() -> None:
    assert registry._is_valid_provider(MissingMethodProvider()) is False


def test_is_valid_provider_rejects_wrong_stream_signature() -> None:
    assert registry._is_valid_provider(WrongStreamSignatureProvider()) is False


def test_is_valid_provider_rejects_coroutine_stream_return_type() -> None:
    assert registry._is_valid_provider(CoroutineStreamProvider()) is False


def test_is_usable_reflects_auth_requirement_and_authentication_state() -> None:
    assert registry._is_usable(PublicProvider()) is True
    assert registry._is_usable(AuthenticatedProvider()) is True
    assert registry._is_usable(ChatGPTProvider()) is False


def test_validate_simple_method_rejects_missing_or_non_callable_methods() -> None:
    provider = ValidProvider()

    assert registry._validate_simple_method(provider, "missing", 0) is False
    assert registry._validate_simple_method(NonCallableListModelsProvider(), "list_models", 0) is False


def test_validate_simple_method_rejects_signature_introspection_failures() -> None:
    with patch("maestro.providers.registry.signature", side_effect=TypeError("boom")):
        assert registry._validate_simple_method(ValidProvider(), "list_models", 0) is False


def test_validate_simple_method_rejects_wrong_argument_shapes() -> None:
    assert registry._validate_simple_method(NoSelfListModelsProvider(), "list_models", 0) is False
    assert (
        registry._validate_simple_method(KeywordOnlySelfLikeMethodProvider(), "list_models", 0)
        is False
    )
    assert registry._validate_simple_method(MissingRequiredMethodArgProvider(), "list_models", 0) is False
    assert registry._validate_simple_method(KeywordOnlyRequiredMethodProvider(), "auth_required", 0) is False


def test_validate_stream_signature_rejects_invalid_signatures() -> None:
    assert registry._validate_stream_signature(TooFewStreamArgsProvider.stream) is False
    assert registry._validate_stream_signature(BadSelfKindStreamProvider.stream) is False
    assert registry._validate_stream_signature(KeywordOnlySelfLikeStreamProvider.stream) is False

    with patch("maestro.providers.registry.signature", side_effect=ValueError("bad signature")):
        assert registry._validate_stream_signature(ValidProvider.stream) is False


def test_validate_stream_return_type_handles_annotations() -> None:
    assert registry._validate_stream_return_type(ForwardRefStreamProvider.stream) is True
    assert registry._validate_stream_return_type(UnannotatedPlainStreamProvider.stream) is True
    assert registry._validate_stream_return_type(PlainAnnotatedStreamProvider.stream) is False


def test_is_valid_provider_rejects_simple_method_and_stream_validation_failures() -> None:
    assert registry._is_valid_provider(MissingRequiredMethodArgProvider()) is False
    assert registry._is_valid_provider(MissingStreamProvider()) is False
    assert registry._is_valid_provider(InstanceOnlyStreamProvider()) is False


def test_discover_providers_skips_invalid_and_broken_entry_points() -> None:
    entry_points = [
        SimpleNamespace(name="valid", load=lambda: ValidProvider),
        SimpleNamespace(name="invalid", load=lambda: MissingMethodProvider),
        SimpleNamespace(name="broken", load=lambda: (_ for _ in ()).throw(RuntimeError("boom"))),
    ]

    with patch("maestro.providers.registry.entry_points", return_value=entry_points):
        providers = registry.discover_providers()

    assert providers == {"valid": ValidProvider}


def test_discover_providers_raises_on_duplicate_provider_ids() -> None:
    class DuplicateValidProvider(ValidProvider):
        pass

    entry_points = [
        SimpleNamespace(name="first", load=lambda: ValidProvider),
        SimpleNamespace(name="second", load=lambda: DuplicateValidProvider),
    ]

    with patch("maestro.providers.registry.entry_points", return_value=entry_points):
        with pytest.raises(registry.DuplicateProviderError, match="Duplicate provider id 'valid'"):
            registry.discover_providers()


def test_discover_providers_skips_instantiation_failures() -> None:
    class ExplodingProvider(ValidProvider):
        def __init__(self) -> None:
            raise RuntimeError("boom")

    entry_points = [SimpleNamespace(name="exploding", load=lambda: ExplodingProvider)]

    with patch("maestro.providers.registry.entry_points", return_value=entry_points):
        assert registry.discover_providers() == {}


def test_list_providers_returns_sorted_provider_ids() -> None:
    with patch("maestro.providers.registry.discover_providers", return_value={"zeta": ValidProvider, "alpha": PublicProvider}):
        assert registry.list_providers() == ["alpha", "zeta"]


def test_get_provider_returns_instance_for_known_provider() -> None:
    with patch("maestro.providers.registry.discover_providers", return_value={"valid": ValidProvider}):
        provider = registry.get_provider("valid")

    assert isinstance(provider, ValidProvider)


def test_get_provider_raises_for_unknown_provider() -> None:
    with patch("maestro.providers.registry.discover_providers", return_value={"valid": ValidProvider}):
        with pytest.raises(ValueError, match="Available providers: valid"):
            registry.get_provider("missing")


def test_get_default_provider_prefers_authenticated_provider() -> None:
    with patch(
        "maestro.providers.registry.discover_providers",
        return_value={"public": PublicProvider, "authenticated": AuthenticatedProvider, "chatgpt": ChatGPTProvider},
    ):
        provider = registry.get_default_provider()

    assert isinstance(provider, AuthenticatedProvider)


def test_get_default_provider_falls_back_to_chatgpt_before_public_provider() -> None:
    with patch(
        "maestro.providers.registry.discover_providers",
        return_value={"public": PublicProvider, "chatgpt": ChatGPTProvider},
    ):
        provider = registry.get_default_provider()

    assert isinstance(provider, ChatGPTProvider)


def test_get_default_provider_falls_back_to_auth_free_provider() -> None:
    with patch("maestro.providers.registry.discover_providers", return_value={"public": PublicProvider}):
        provider = registry.get_default_provider()

    assert isinstance(provider, PublicProvider)


def test_get_default_provider_raises_when_no_providers_exist() -> None:
    with patch("maestro.providers.registry.discover_providers", return_value={}):
        with pytest.raises(ValueError, match="No providers installed"):
            registry.get_default_provider()


def test_get_default_provider_raises_when_none_are_usable() -> None:
    class LockedProvider(ValidProvider):
        @property
        def id(self) -> str:
            return "locked"

        def auth_required(self) -> bool:
            return True

    with patch("maestro.providers.registry.discover_providers", return_value={"locked": LockedProvider}):
        with pytest.raises(ValueError, match="No usable provider found"):
            registry.get_default_provider()


def test_get_default_provider_skips_provider_instantiation_failures() -> None:
    class ExplodingProvider(ValidProvider):
        @property
        def id(self) -> str:
            return "exploding"

        def __init__(self) -> None:
            raise RuntimeError("boom")

    with patch(
        "maestro.providers.registry.discover_providers",
        return_value={"exploding": ExplodingProvider, "public": PublicProvider},
    ):
        provider = registry.get_default_provider()

    assert isinstance(provider, PublicProvider)
