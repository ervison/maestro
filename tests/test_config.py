from __future__ import annotations

from pathlib import Path

import pytest

from maestro.config import Config


def test_config_get_returns_nested_value() -> None:
    config = Config(model="chatgpt/gpt-5", agent={"backend": {"model": "x"}})

    assert config.get("agent.backend.model") == "x"
    assert config.get("agent.backend.missing", "fallback") == "fallback"


def test_config_set_updates_top_level_and_nested_keys() -> None:
    config = Config()

    config.set("model", "chatgpt/gpt-5")
    config.set("agent.backend.model", "github-copilot/gpt-4o")

    assert config.model == "chatgpt/gpt-5"
    assert config.agent == {"backend": {"model": "github-copilot/gpt-4o"}}


def test_config_set_rejects_invalid_top_level_key() -> None:
    config = Config()

    with pytest.raises(KeyError, match="Invalid config key"):
        config.set("missing", "value")


def test_config_set_rejects_nested_assignment_into_scalar() -> None:
    config = Config(model="chatgpt/gpt-5")

    with pytest.raises(KeyError, match="Cannot set key on non-container"):
        config.set("model.version", "mini")


def test_load_returns_defaults_when_file_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import maestro.config as config_module

    monkeypatch.setattr(config_module, "CONFIG_FILE", tmp_path / "missing.json")

    loaded = config_module.load()

    assert loaded == Config()


def test_load_rejects_non_object_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import maestro.config as config_module

    config_file = tmp_path / "config.json"
    config_file.write_text("[]")
    monkeypatch.setattr(config_module, "CONFIG_FILE", config_file)

    with pytest.raises(RuntimeError, match="expected object"):
        config_module.load()


def test_load_rejects_non_string_model(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import maestro.config as config_module

    config_file = tmp_path / "config.json"
    config_file.write_text('{"model": 123}')
    monkeypatch.setattr(config_module, "CONFIG_FILE", config_file)

    with pytest.raises(RuntimeError, match="expected 'model' to be a string"):
        config_module.load()


def test_load_rejects_non_object_agent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import maestro.config as config_module

    config_file = tmp_path / "config.json"
    config_file.write_text('{"agent": []}')
    monkeypatch.setattr(config_module, "CONFIG_FILE", config_file)

    with pytest.raises(RuntimeError, match="expected 'agent' to be an object"):
        config_module.load()


def test_load_rejects_non_object_aggregator(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import maestro.config as config_module

    config_file = tmp_path / "config.json"
    config_file.write_text('{"aggregator": []}')
    monkeypatch.setattr(config_module, "CONFIG_FILE", config_file)

    with pytest.raises(RuntimeError, match="expected 'aggregator' to be an object"):
        config_module.load()


def test_load_rejects_non_boolean_aggregator_enabled(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import maestro.config as config_module

    config_file = tmp_path / "config.json"
    config_file.write_text('{"aggregator": {"enabled": 1}}')
    monkeypatch.setattr(config_module, "CONFIG_FILE", config_file)

    with pytest.raises(RuntimeError, match="expected 'aggregator.enabled' to be a bool"):
        config_module.load()


def test_load_rejects_negative_aggregator_limits(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import maestro.config as config_module

    config_file = tmp_path / "config.json"
    config_file.write_text('{"aggregator": {"max_calls": -1}}')
    monkeypatch.setattr(config_module, "CONFIG_FILE", config_file)

    with pytest.raises(RuntimeError, match="expected 'aggregator.max_calls' to be a non-negative int"):
        config_module.load()


def test_load_rejects_invalid_json_and_max_tokens(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import maestro.config as config_module

    config_file = tmp_path / "config.json"
    config_file.write_text("{")
    monkeypatch.setattr(config_module, "CONFIG_FILE", config_file)

    with pytest.raises(RuntimeError, match="remove or repair the file"):
        config_module.load()

    config_file.write_text('{"aggregator": {"max_tokens_per_run": -1}}')
    with pytest.raises(RuntimeError, match="expected 'aggregator.max_tokens_per_run' to be a non-negative int"):
        config_module.load()


def test_config_set_rejects_invalid_nested_paths() -> None:
    config = Config()

    with pytest.raises(KeyError, match="Invalid config key"):
        config.set("missing.value", 1)

    config.agent = {"backend": "scalar"}
    with pytest.raises(KeyError, match="Cannot set nested key on non-container"):
        config.set("agent.backend.model.value", "x")


def test_save_writes_json_and_restricts_permissions(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import maestro.config as config_module

    config_file = tmp_path / "nested" / "config.json"
    monkeypatch.setattr(config_module, "CONFIG_FILE", config_file)

    config_module.save(
        Config(
            model="chatgpt/gpt-5",
            agent={"backend": {"model": "github-copilot/gpt-4o"}},
            aggregator={"enabled": True},
        )
    )

    loaded = config_module.load()
    assert loaded.model == "chatgpt/gpt-5"
    assert loaded.agent["backend"]["model"] == "github-copilot/gpt-4o"
    assert loaded.aggregator["enabled"] is True
    assert oct(config_file.stat().st_mode & 0o777) == "0o600"
