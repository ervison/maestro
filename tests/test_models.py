from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from maestro.models import format_model_list, get_available_models, parse_model_string, resolve_model


def test_parse_model_string_returns_provider_and_model() -> None:
    assert parse_model_string(" chatgpt / gpt-5 ") == ("chatgpt", "gpt-5")


@pytest.mark.parametrize(
    "value,message",
    [
        ("chatgpt", "Expected format"),
        ("/gpt-5", "Provider ID cannot be empty"),
        ("chatgpt/", "Model ID cannot be empty"),
    ],
)
def test_parse_model_string_rejects_invalid_values(value: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_model_string(value)


def test_resolve_model_uses_cli_flag_first() -> None:
    provider = SimpleNamespace(id="chatgpt")

    with patch("maestro.providers.registry.get_provider", return_value=provider) as mock_get_provider:
        resolved_provider, model = resolve_model(model_flag="chatgpt/gpt-5")

    assert resolved_provider is provider
    assert model == "gpt-5"
    mock_get_provider.assert_called_once_with("chatgpt")


def test_resolve_model_uses_environment_before_config(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = SimpleNamespace(id="github-copilot")
    config = SimpleNamespace(model="chatgpt/gpt-5", get=lambda key: None)
    monkeypatch.setenv("MAESTRO_MODEL", "github-copilot/gpt-4o")

    with (
        patch("maestro.config.load", return_value=config),
        patch("maestro.providers.registry.get_provider", return_value=provider) as mock_get_provider,
    ):
        resolved_provider, model = resolve_model()

    assert resolved_provider is provider
    assert model == "gpt-4o"
    mock_get_provider.assert_called_once_with("github-copilot")


def test_resolve_model_uses_agent_specific_config() -> None:
    provider = SimpleNamespace(id="github-copilot")
    config = SimpleNamespace(
        model="chatgpt/gpt-5",
        get=lambda key: "github-copilot/gpt-4o" if key == "agent.reviewer.model" else None,
    )

    with (
        patch("maestro.config.load", return_value=config),
        patch("maestro.providers.registry.get_provider", return_value=provider),
    ):
        resolved_provider, model = resolve_model(agent_name="reviewer")

    assert resolved_provider is provider
    assert model == "gpt-4o"


def test_resolve_model_uses_global_config_when_agent_setting_missing() -> None:
    provider = SimpleNamespace(id="chatgpt")
    config = SimpleNamespace(model="chatgpt/gpt-5", get=lambda key: None)

    with (
        patch("maestro.config.load", return_value=config),
        patch("maestro.providers.registry.get_provider", return_value=provider),
    ):
        resolved_provider, model = resolve_model(agent_name="backend")

    assert resolved_provider is provider
    assert model == "gpt-5"


def test_resolve_model_uses_chatgpt_default_model_fallback() -> None:
    provider = SimpleNamespace(id="chatgpt")
    config = SimpleNamespace(model=None, get=lambda key: None)

    with (
        patch("maestro.config.load", return_value=config),
        patch("maestro.providers.registry.get_default_provider", return_value=provider),
    ):
        resolved_provider, model = resolve_model()

    assert resolved_provider is provider
    assert model == "gpt-5.4-mini"


def test_resolve_model_uses_first_model_from_non_chatgpt_default_provider() -> None:
    provider = SimpleNamespace(id="local", list_models=lambda: ["small", "large"])
    config = SimpleNamespace(model=None, get=lambda key: None)

    with (
        patch("maestro.config.load", return_value=config),
        patch("maestro.providers.registry.get_default_provider", return_value=provider),
    ):
        resolved_provider, model = resolve_model()

    assert resolved_provider is provider
    assert model == "small"


def test_resolve_model_raises_when_default_provider_has_no_models() -> None:
    provider = SimpleNamespace(id="local", list_models=lambda: [])
    config = SimpleNamespace(model=None, get=lambda key: None)

    with (
        patch("maestro.config.load", return_value=config),
        patch("maestro.providers.registry.get_default_provider", return_value=provider),
    ):
        with pytest.raises(RuntimeError, match="returned no models"):
            resolve_model()


def test_get_available_models_filters_unusable_and_broken_providers() -> None:
    class PublicProvider:
        def auth_required(self) -> bool:
            return False

        def is_authenticated(self) -> bool:
            return False

        def list_models(self) -> list[str]:
            return ["open"]

    class PrivateProvider:
        def auth_required(self) -> bool:
            return True

        def is_authenticated(self) -> bool:
            return False

        def list_models(self) -> list[str]:
            return ["secret"]

    class BrokenProvider:
        def __init__(self) -> None:
            raise RuntimeError("boom")

    with patch(
        "maestro.providers.registry.discover_providers",
        return_value={
            "public": PublicProvider,
            "private": PrivateProvider,
            "broken": BrokenProvider,
        },
    ):
        assert get_available_models() == {"public": ["open"]}


def test_format_model_list_sorts_providers_and_models() -> None:
    formatted = format_model_list({"zeta": ["b", "a"], "alpha": ["c"]})

    assert formatted == "\nalpha:\n  c\n\nzeta:\n  a\n  b"
