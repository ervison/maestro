import sys
import warnings
from pathlib import Path

import pytest

from maestro import agent, auth, cli
from maestro.auth import TokenSet, _save, all_providers, get, remove, set


@pytest.fixture
def auth_file(tmp_path, monkeypatch):
    target = tmp_path / "auth.json"
    monkeypatch.setattr(auth, "AUTH_FILE", target)
    return target


def test_set_get_roundtrip(auth_file):
    payload = {"access": "tok", "refresh": "ref", "expires": 123.0}

    set("chatgpt", payload)

    assert get("chatgpt") == payload


def test_get_nonexistent_returns_none(auth_file):
    assert get("missing") is None


def test_file_permissions(auth_file):
    set("chatgpt", {"access": "tok"})

    assert auth_file.stat().st_mode & 0o777 == 0o600


def test_write_store_uses_secure_create_mode(auth_file, monkeypatch):
    original_open = auth.os.open
    original_fdopen = auth.os.fdopen
    recorded = {}

    def fake_open(path, flags, mode=0o777):
        recorded["path"] = path
        recorded["flags"] = flags
        recorded["mode"] = mode
        return original_open(path, flags, mode)

    def fake_fdopen(fd, mode="r", *args, **kwargs):
        recorded["fdopen_mode"] = mode
        return original_fdopen(fd, mode, *args, **kwargs)

    monkeypatch.setattr(auth.os, "open", fake_open)
    monkeypatch.setattr(auth.os, "fdopen", fake_fdopen)

    set("chatgpt", {"access": "tok"})

    assert recorded["path"] == str(auth_file)
    assert recorded["mode"] == 0o600
    assert recorded["flags"] & auth.os.O_CREAT
    assert recorded["flags"] & auth.os.O_TRUNC
    assert recorded["fdopen_mode"] == "w"


def test_auto_migration(auth_file):
    auth_file.write_text(
        '{"access": "tok", "refresh": "ref", "expires": 123.0, "account_id": "acc"}'
    )

    payload = get("chatgpt")

    assert payload == {
        "access": "tok",
        "refresh": "ref",
        "expires": 123.0,
        "account_id": "acc",
    }
    assert auth_file.stat().st_mode & 0o777 == 0o600
    assert auth_file.read_text() == (
        '{"chatgpt": {"access": "tok", "refresh": "ref", '
        '"expires": 123.0, "account_id": "acc"}}'
    )


def test_invalid_auth_store_raises_runtime_error(auth_file):
    auth_file.write_text('{"broken": ')

    with pytest.raises(RuntimeError, match="Invalid auth store"):
        get("chatgpt")


def test_non_dict_store_raises_runtime_error(auth_file):
    auth_file.write_text('["not", "a", "dict"]')

    with pytest.raises(RuntimeError, match="Invalid auth store"):
        get("chatgpt")


def test_non_dict_provider_entry_raises_runtime_error(auth_file):
    auth_file.write_text('{"chatgpt": "not-a-dict"}')

    with pytest.raises(RuntimeError, match="Invalid auth store"):
        get("chatgpt")


def test_multiple_providers_isolated(auth_file):
    set("chatgpt", {"access": "chatgpt-token"})
    set("copilot", {"token": "copilot-token"})

    assert get("chatgpt") == {"access": "chatgpt-token"}
    assert get("copilot") == {"token": "copilot-token"}


def test_all_providers(auth_file):
    set("chatgpt", {"access": "one"})
    set("copilot", {"access": "two"})

    assert all_providers() == ["chatgpt", "copilot"]


def test_remove(auth_file):
    set("chatgpt", {"access": "tok"})

    assert remove("chatgpt") is True
    assert get("chatgpt") is None


def test_remove_nonexistent_returns_false(auth_file):
    assert remove("missing") is False


def test_load_backward_compat(auth_file):
    set(
        "chatgpt",
        {
            "access": "tok",
            "refresh": "ref",
            "expires": 9999999.0,
            "account_id": "acc",
            "email": "test@example.com",
        },
    )

    loaded = auth.load()

    assert isinstance(loaded, TokenSet)
    assert loaded.access == "tok"
    assert loaded.email == "test@example.com"


def test_save_backward_compat(auth_file):
    _save(
        TokenSet(
            access="tok",
            refresh="ref",
            expires=9999999.0,
            account_id="acc",
            email="test@example.com",
        )
    )

    loaded = auth.load()

    assert loaded is not None
    assert loaded.access == "tok"
    assert loaded.email == "test@example.com"


def test_agent_run_uses_auth_shims(auth_file, monkeypatch):
    set(
        "chatgpt",
        {
            "access": "tok",
            "refresh": "ref",
            "expires": 9999999999.0,
            "account_id": "acc",
            "email": "test@example.com",
        },
    )

    monkeypatch.setattr(agent.auth, "ensure_valid", lambda tokens: tokens)
    monkeypatch.setattr(agent, "_run_agentic_loop", lambda **kwargs: "ok")

    result = agent.run("gpt-5.4-mini", "hello")

    assert result == "ok"


def test_auth_login_defaults_to_chatgpt(monkeypatch, capsys):
    called = {}

    def fake_login(method="browser"):
        called["method"] = method
        return TokenSet(
            access="tok",
            refresh="ref",
            expires=9999999.0,
            account_id="acc",
            email="test@example.com",
        )

    monkeypatch.setattr(auth, "login", fake_login)
    monkeypatch.setattr(sys, "argv", ["maestro", "auth", "login"])

    cli.main()

    assert called == {"method": "browser"}
    assert "Logged in as: test@example.com" in capsys.readouterr().out


def test_auth_login_uses_discovered_provider(monkeypatch, capsys):
    class DummyProvider:
        @property
        def id(self):
            return "dummy"

        @property
        def name(self):
            return "Dummy"

        def list_models(self):
            return ["dummy-model"]

        async def stream(self, messages, model, tools=None):
            if False:
                yield None

        def auth_required(self):
            return True

        def login(self):
            print("dummy login")

        def is_authenticated(self):
            return False

    monkeypatch.setattr(sys, "argv", ["maestro", "auth", "login", "dummy"])
    monkeypatch.setattr(cli, "get_provider", lambda provider_id: DummyProvider())
    monkeypatch.setattr(auth, "login", lambda method="browser": pytest.fail("chatgpt auth.login should not be called"))

    cli.main()

    assert "dummy login" in capsys.readouterr().out


def test_old_login_shows_deprecation(monkeypatch, capsys):
    def fake_login(method="browser"):
        return TokenSet(
            access="tok",
            refresh="ref",
            expires=9999999.0,
            account_id="acc",
            email="test@example.com",
        )

    monkeypatch.setattr(auth, "login", fake_login)
    monkeypatch.setattr(sys, "argv", ["maestro", "login"])

    with warnings.catch_warnings(record=True) as caught:
        cli.main()

    captured = capsys.readouterr()
    assert (
        "'maestro login' is deprecated. Use 'maestro auth login chatgpt' instead."
        in captured.err
    )
    assert any(item.category is DeprecationWarning for item in caught)
    assert "Logged in as: test@example.com" in captured.out


def test_old_logout_no_deprecation(monkeypatch):
    calls = []

    monkeypatch.setattr(auth, "logout", lambda: calls.append("logout"))
    monkeypatch.setattr(sys, "argv", ["maestro", "logout"])

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        cli.main()

    assert calls == ["logout"]
    assert not any(item.category is DeprecationWarning for item in caught)


def test_old_status_no_deprecation(monkeypatch, capsys):
    monkeypatch.setattr(
        auth,
        "load",
        lambda: TokenSet(
            access="tok",
            refresh="ref",
            expires=9999999999.0,
            account_id="acc",
            email="test@example.com",
        ),
    )
    monkeypatch.setattr(sys, "argv", ["maestro", "status"])

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        cli.main()

    out = capsys.readouterr().out
    assert "Email:" in out
    assert not any(item.category is DeprecationWarning for item in caught)


def test_run_with_explicit_unsupported_provider_exits_cleanly(monkeypatch, capsys):
    class DummyProvider:
        id = "other"

    monkeypatch.setattr(sys, "argv", ["maestro", "run", "hello", "--model", "other/model"])
    monkeypatch.setattr(cli, "run", lambda *args, **kwargs: pytest.fail("run should not be called"))

    def fake_resolve_model(model_flag=None, agent_name=None):
        assert model_flag == "other/model"
        return DummyProvider(), "model"

    monkeypatch.setattr("maestro.models.resolve_model", fake_resolve_model)

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    captured = capsys.readouterr()
    assert exc_info.value.code == 1
    assert "Provider 'other' is discoverable but not runnable yet" in captured.out
    assert "Traceback" not in captured.err


def test_run_with_invalid_model_format_exits_cleanly(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["maestro", "run", "hello", "--model", "invalid"])
    monkeypatch.setattr(cli, "run", lambda *args, **kwargs: pytest.fail("run should not be called"))

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    captured = capsys.readouterr()
    assert exc_info.value.code == 1
    assert "Error: Invalid model format" in captured.out
    assert "Traceback" not in captured.err


def test_run_with_env_selected_unsupported_provider_exits_cleanly(monkeypatch, capsys):
    class DummyProvider:
        id = "other"

    monkeypatch.setattr(sys, "argv", ["maestro", "run", "hello"])
    monkeypatch.setenv("MAESTRO_MODEL", "other/model")
    monkeypatch.setattr(cli, "run", lambda *args, **kwargs: pytest.fail("run should not be called"))

    def fake_resolve_model(model_flag=None, agent_name=None):
        assert model_flag is None
        return DummyProvider(), "model"

    monkeypatch.setattr("maestro.models.resolve_model", fake_resolve_model)

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    captured = capsys.readouterr()
    assert exc_info.value.code == 1
    assert "Provider 'other' is discoverable but not runnable yet" in captured.out
    assert "Traceback" not in captured.err


def test_run_with_model_flag_bypasses_invalid_config_reload(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["maestro", "run", "hello", "--model", "chatgpt/gpt-5.4"])
    monkeypatch.setattr(cli, "run", lambda model_id, prompt, system, workdir, auto: f"ran:{model_id}:{prompt}")
    monkeypatch.setattr(
        "maestro.config.load",
        lambda: (_ for _ in ()).throw(RuntimeError("Invalid config file")),
    )

    cli.main()

    captured = capsys.readouterr()
    assert "ran:gpt-5.4:hello" in captured.out


def test_run_without_explicit_selection_falls_back_to_chatgpt(monkeypatch, capsys):
    class DummyProvider:
        id = "auth-free"

    monkeypatch.setattr(sys, "argv", ["maestro", "run", "hello"])
    monkeypatch.delenv("MAESTRO_MODEL", raising=False)
    monkeypatch.setattr(cli, "run", lambda model_id, prompt, system, workdir, auto: f"ran:{model_id}:{prompt}")

    def fake_resolve_model(model_flag=None, agent_name=None):
        assert model_flag is None
        return DummyProvider(), "free-model"

    class DummyConfig:
        model = None

    monkeypatch.setattr("maestro.models.resolve_model", fake_resolve_model)
    monkeypatch.setattr("maestro.config.load", lambda: DummyConfig())

    cli.main()

    captured = capsys.readouterr()
    assert "ran:gpt-5.4-mini:hello" in captured.out
