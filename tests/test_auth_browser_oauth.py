import threading
import time
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from maestro import auth
from maestro.auth import TokenSet


def _capture_browser_url(monkeypatch):
    opened = {}

    class DummyServer:
        timeout = 1

        def handle_request(self):
            return None

        def server_close(self):
            return None

    class DummyThread:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def start(self):
            return None

        def join(self, timeout=None):
            return None

    monkeypatch.setattr(auth, "_generate_pkce", lambda: ("verifier", "challenge"))
    monkeypatch.setattr(auth, "_generate_state", lambda: "state123")
    monkeypatch.setattr(auth.http.server, "HTTPServer", lambda *args, **kwargs: DummyServer())
    monkeypatch.setattr(auth.threading, "Thread", DummyThread)
    monkeypatch.setattr(auth.webbrowser, "open", lambda url: opened.setdefault("url", url))

    with pytest.raises(RuntimeError, match="No authorization code received"):
        auth.login_browser()

    return opened["url"]


def test_authorize_url_uses_localhost_redirect(monkeypatch):
    url = _capture_browser_url(monkeypatch)
    params = parse_qs(urlparse(url).query)

    assert params["redirect_uri"] == [auth.REDIRECT_URI]
    assert "127.0.0.1" not in params["redirect_uri"][0]


def test_authorize_url_includes_connector_scopes(monkeypatch):
    url = _capture_browser_url(monkeypatch)
    scope = parse_qs(urlparse(url).query)["scope"][0]

    assert "openid" in scope
    assert "offline_access" in scope
    assert "api.connectors.read" in scope
    assert "api.connectors.invoke" in scope


def test_authorize_url_has_required_params(monkeypatch):
    url = _capture_browser_url(monkeypatch)
    params = parse_qs(urlparse(url).query)

    assert params["response_type"] == ["code"]
    assert params["client_id"] == [auth.CLIENT_ID]
    assert params["code_challenge"] == ["challenge"]
    assert params["code_challenge_method"] == ["S256"]
    assert params["state"] == ["state123"]
    assert params["id_token_add_organizations"] == ["true"]
    assert params["codex_cli_simplified_flow"] == ["true"]
    assert params["originator"] == ["codex_cli_rs"]


def test_callback_exchanges_code_on_valid_state(monkeypatch):
    monkeypatch.setattr(auth, "_generate_pkce", lambda: ("verifier", "challenge"))
    monkeypatch.setattr(auth, "_generate_state", lambda: "state123")
    monkeypatch.setattr(auth.webbrowser, "open", lambda url: None)

    captured = {}

    def fake_exchange(code, verifier, redirect_uri):
        captured["code"] = code
        captured["verifier"] = verifier
        captured["redirect_uri"] = redirect_uri
        return TokenSet(
            access="tok",
            refresh="ref",
            expires=9999999.0,
            account_id="acc",
            email="test@example.com",
        )

    monkeypatch.setattr(auth, "_exchange_code", fake_exchange)

    def do_request():
        time.sleep(0.3)
        httpx.get(
            "http://127.0.0.1:1455/auth/callback",
            params={"code": "auth-code", "state": "state123"},
            timeout=2,
        )

    t = threading.Thread(target=do_request, daemon=True)
    t.start()

    result = auth.login_browser()
    t.join(timeout=5)

    assert captured == {
        "code": "auth-code",
        "verifier": "verifier",
        "redirect_uri": auth.REDIRECT_URI,
    }
    assert result.email == "test@example.com"


def test_callback_state_mismatch_allows_later_valid_callback(monkeypatch):
    monkeypatch.setattr(auth, "_generate_pkce", lambda: ("verifier", "challenge"))
    monkeypatch.setattr(auth, "_generate_state", lambda: "state123")
    monkeypatch.setattr(auth.webbrowser, "open", lambda url: None)

    captured = {}

    def fake_exchange(code, verifier, redirect_uri):
        captured["code"] = code
        return TokenSet(
            access="tok",
            refresh="ref",
            expires=9999999.0,
            account_id="acc",
            email="test@example.com",
        )

    monkeypatch.setattr(auth, "_exchange_code", fake_exchange)

    def do_requests():
        time.sleep(0.3)
        httpx.get(
            "http://127.0.0.1:1455/auth/callback",
            params={"code": "wrong-code", "state": "wrong-state"},
            timeout=2,
        )
        time.sleep(0.1)
        httpx.get(
            "http://127.0.0.1:1455/auth/callback",
            params={"code": "auth-code", "state": "state123"},
            timeout=2,
        )

    t = threading.Thread(target=do_requests, daemon=True)
    t.start()

    result = auth.login_browser()
    t.join(timeout=5)

    assert captured["code"] == "auth-code"
    assert result.email == "test@example.com"


def test_callback_surfaces_provider_error(monkeypatch):
    monkeypatch.setattr(auth, "_generate_pkce", lambda: ("verifier", "challenge"))
    monkeypatch.setattr(auth, "_generate_state", lambda: "state123")
    monkeypatch.setattr(auth.webbrowser, "open", lambda url: None)

    def do_request():
        time.sleep(0.3)
        httpx.get(
            "http://127.0.0.1:1455/auth/callback",
            params={"state": "state123", "error": "unknown_error"},
            timeout=2,
        )

    t = threading.Thread(target=do_request, daemon=True)
    t.start()

    with pytest.raises(RuntimeError, match="OAuth error: unknown_error"):
        auth.login_browser()

    t.join(timeout=5)
