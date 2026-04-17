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
