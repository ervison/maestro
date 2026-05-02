from __future__ import annotations

import base64
import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest


def _jwt(payload: dict) -> str:
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=")
    return f"header.{encoded.decode()}.signature"


def _json_response(payload: dict, status_code: int = 200) -> Mock:
    response = Mock(status_code=status_code)
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def test_read_store_returns_empty_when_auth_file_is_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import maestro.auth as auth_module

    monkeypatch.setattr(auth_module, "AUTH_FILE", tmp_path / "auth.json")

    assert auth_module._read_store() == {}


def test_read_store_migrates_legacy_flat_chatgpt_format(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import maestro.auth as auth_module

    auth_file = tmp_path / "auth.json"
    auth_file.write_text('{"access": "a", "refresh": "r", "expires": 1}')
    monkeypatch.setattr(auth_module, "AUTH_FILE", auth_file)

    store = auth_module._read_store()

    assert store == {"chatgpt": {"access": "a", "refresh": "r", "expires": 1}}
    assert json.loads(auth_file.read_text()) == store


@pytest.mark.parametrize("contents", ["{not-json}", "[]", '{"chatgpt": []}'])
def test_read_store_rejects_invalid_auth_store_shapes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, contents: str
) -> None:
    import maestro.auth as auth_module

    auth_file = tmp_path / "auth.json"
    auth_file.write_text(contents)
    monkeypatch.setattr(auth_module, "AUTH_FILE", auth_file)

    with pytest.raises(RuntimeError, match="Invalid auth store"):
        auth_module._read_store()


def test_token_save_load_and_remove_round_trip(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import maestro.auth as auth_module

    monkeypatch.setattr(auth_module, "AUTH_FILE", tmp_path / "auth.json")

    auth_module._save(
        auth_module.TokenSet(
            access="access-token",
            refresh="refresh-token",
            expires=123.0,
            account_id="acct-1",
            email="user@example.com",
        )
    )
    auth_module.set("github-copilot", {"access": "copilot-token"})

    loaded = auth_module.load()

    assert loaded == auth_module.TokenSet(
        access="access-token",
        refresh="refresh-token",
        expires=123.0,
        account_id="acct-1",
        email="user@example.com",
    )
    assert set(auth_module.all_providers()) == {"chatgpt", "github-copilot"}
    assert auth_module.remove("github-copilot") is True
    assert auth_module.remove("missing") is False
    assert oct((tmp_path / "auth.json").stat().st_mode & 0o777) == "0o600"


def test_exchange_code_saves_tokens_and_extracts_claims(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import maestro.auth as auth_module

    monkeypatch.setattr(auth_module, "AUTH_FILE", tmp_path / "auth.json")
    monkeypatch.setattr(auth_module.time, "time", lambda: 1000.0)

    access_token = _jwt(
        {auth_module.AUTH_CLAIM: {"chatgpt_account_id": "acct-123"}}
    )
    id_token = _jwt({"email": "user@example.com"})

    with patch.object(
        auth_module.httpx,
        "post",
        return_value=_json_response(
            {
                "access_token": access_token,
                "refresh_token": "refresh-123",
                "expires_in": 60,
                "id_token": id_token,
            }
        ),
    ) as mock_post:
        tokens = auth_module._exchange_code("auth-code", "verifier", "redirect-uri")

    assert tokens.access == access_token
    assert tokens.refresh == "refresh-123"
    assert tokens.expires == 1060.0
    assert tokens.account_id == "acct-123"
    assert tokens.email == "user@example.com"
    assert auth_module.load() == tokens
    assert mock_post.call_args.kwargs["data"]["redirect_uri"] == "redirect-uri"


def test_refresh_token_uses_existing_email_when_new_id_token_missing() -> None:
    import maestro.auth as auth_module

    old = auth_module.TokenSet(
        access="old-access",
        refresh="old-refresh",
        expires=10.0,
        account_id="old-account",
        email="saved@example.com",
    )
    access_token = _jwt(
        {auth_module.AUTH_CLAIM: {"chatgpt_account_id": "acct-refreshed"}}
    )

    with (
        patch.object(auth_module.time, "time", return_value=200.0),
        patch.object(
            auth_module.httpx,
            "post",
            return_value=_json_response(
                {"access_token": access_token, "expires_in": 30}
            ),
        ),
        patch.object(auth_module, "_save") as mock_save,
    ):
        refreshed = auth_module.refresh_token(old)

    assert refreshed.refresh == "old-refresh"
    assert refreshed.email == "saved@example.com"
    assert refreshed.account_id == "acct-refreshed"
    mock_save.assert_called_once_with(refreshed)


def test_ensure_valid_refreshes_only_when_token_is_near_expiry() -> None:
    import maestro.auth as auth_module

    expiring = auth_module.TokenSet("a", "r", 1200.0)
    valid = auth_module.TokenSet("b", "r", 1500.0)
    refreshed = auth_module.TokenSet("new", "r", 2000.0)

    with (
        patch.object(auth_module.time, "time", return_value=1000.0),
        patch.object(auth_module, "refresh_token", return_value=refreshed) as mock_refresh,
    ):
        assert auth_module.ensure_valid(expiring) == refreshed
        assert auth_module.ensure_valid(valid) == valid

    mock_refresh.assert_called_once_with(expiring)


def test_login_device_polls_until_authorization_code_is_available() -> None:
    import maestro.auth as auth_module

    token_set = auth_module.TokenSet("access", "refresh", 1.0)
    initial = _json_response(
        {"device_auth_id": "device-1", "user_code": "USER123", "interval": 0}
    )
    pending_403 = Mock(status_code=403)
    pending_404 = Mock(status_code=404)
    success = _json_response(
        {"authorization_code": "auth-code", "code_verifier": "device-verifier"}
    )

    with (
        patch.object(
            auth_module.httpx,
            "post",
            side_effect=[initial, pending_403, pending_404, success],
        ) as mock_post,
        patch.object(auth_module.time, "sleep") as mock_sleep,
        patch.object(auth_module, "_exchange_code", return_value=token_set) as mock_exchange,
    ):
        result = auth_module.login_device()

    assert result == token_set
    assert mock_post.call_count == 4
    assert mock_sleep.call_count == 3
    mock_exchange.assert_called_once_with(
        "auth-code", "device-verifier", auth_module.DEVICE_CALLBACK
    )


def test_login_device_times_out_when_authorization_never_arrives() -> None:
    import maestro.auth as auth_module

    initial = _json_response(
        {"device_auth_id": "device-1", "user_code": "USER123", "interval": 0}
    )
    pending = Mock(status_code=403)

    with (
        patch.object(auth_module.time, "time", side_effect=[0.0, 0.0, 901.0]),
        patch.object(auth_module.time, "sleep"),
        patch.object(auth_module.httpx, "post", side_effect=[initial, pending]),
    ):
        with pytest.raises(RuntimeError, match="timed out"):
            auth_module.login_device()


def test_login_dispatches_to_requested_flow() -> None:
    import maestro.auth as auth_module

    browser_tokens = auth_module.TokenSet("browser", "r", 1.0)
    device_tokens = auth_module.TokenSet("device", "r", 1.0)

    with (
        patch.object(auth_module, "login_browser", return_value=browser_tokens),
        patch.object(auth_module, "login_device", return_value=device_tokens),
    ):
        assert auth_module.login() == browser_tokens
        assert auth_module.login("device") == device_tokens


def test_load_returns_none_when_chatgpt_provider_is_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import maestro.auth as auth_module

    monkeypatch.setattr(auth_module, "AUTH_FILE", tmp_path / "auth.json")
    auth_module.set("github-copilot", {"access": "token"})

    assert auth_module.load() is None


def test_load_raises_type_error_for_invalid_token_shape(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import maestro.auth as auth_module

    auth_file = tmp_path / "auth.json"
    auth_file.write_text('{"chatgpt": {"access": "a"}}')
    monkeypatch.setattr(auth_module, "AUTH_FILE", auth_file)

    with pytest.raises(TypeError):
        auth_module.load()


@pytest.mark.parametrize(
    ("token", "expected_account", "expected_email"),
    [
        ("not-a-jwt", "", ""),
        ("a.invalid!.c", "", ""),
        (_jwt({"sub": "user"}), "", ""),
    ],
)
def test_token_deserialization_helpers_handle_invalid_payloads(
    token: str, expected_account: str, expected_email: str
) -> None:
    import maestro.auth as auth_module

    assert auth_module._extract_account_id(token) == expected_account
    assert auth_module._extract_email(token) == expected_email


def test_auth_url_and_callback_helpers_cover_error_paths() -> None:
    import maestro.auth as auth_module

    verifier, challenge = auth_module._generate_pkce()
    state = auth_module._generate_state()
    redirect_uri = auth_module._build_browser_redirect_uri(9876)
    authorize_url = auth_module._build_authorize_url(redirect_uri, challenge, state)

    assert verifier
    assert challenge
    assert redirect_uri == "http://127.0.0.1:9876/auth/callback"
    assert "response_type=code" in authorize_url
    assert "code_challenge_method=S256" in authorize_url

    assert auth_module._parse_browser_callback("/auth/callback?state=wrong", state) == (
        None,
        "State mismatch",
    )
    assert auth_module._parse_browser_callback(
        f"/auth/callback?state={state}&error=access_denied", state
    ) == (None, "access_denied")
    assert auth_module._parse_browser_callback(f"/auth/callback?state={state}", state) == (
        None,
        "No authorization code received",
    )
    assert auth_module._parse_browser_callback(
        f"/auth/callback?state={state}&code=auth-code", state
    ) == ("auth-code", None)


def test_refresh_token_raises_for_http_and_payload_errors() -> None:
    import maestro.auth as auth_module

    token_set = auth_module.TokenSet("old", "refresh", 1.0)
    http_error_response = Mock()
    http_error_response.raise_for_status.side_effect = RuntimeError("boom")

    with patch.object(auth_module.httpx, "post", return_value=http_error_response):
        with pytest.raises(RuntimeError, match="boom"):
            auth_module.refresh_token(token_set)

    with patch.object(
        auth_module.httpx,
        "post",
        return_value=_json_response({"refresh_token": "new-refresh"}),
    ):
        with pytest.raises(KeyError, match="access_token"):
            auth_module.refresh_token(token_set)


def test_login_browser_handles_wrong_path_then_success() -> None:
    import maestro.auth as auth_module

    token_set = auth_module.TokenSet("access", "refresh", 1.0)
    handled_requests: list[SimpleNamespace] = []
    server_instances = []

    class FakeServer:
        def __init__(self, _addr, handler_cls):
            self.handler_cls = handler_cls
            self.timeout = None
            self.paths = [
                "/wrong",
                "/auth/callback?state=test-state&code=browser-code",
            ]
            server_instances.append(self)

        def handle_request(self):
            path = self.paths.pop(0)
            request = SimpleNamespace(
                path=path,
                wfile=io.BytesIO(),
                sent=[],
                send_response=lambda status: request.sent.append(("status", status)),
                send_header=lambda *args: request.sent.append(("header", args)),
                end_headers=lambda: request.sent.append(("end", None)),
            )
            handled_requests.append(request)
            self.handler_cls.do_GET(request)

        def server_close(self):
            return None

    class FakeThread:
        def __init__(self, target=None, daemon=None):
            self.target = target

        def start(self):
            self.target()

        def join(self, timeout=None):
            return None

    with (
        patch.object(auth_module, "_generate_state", return_value="test-state"),
        patch.object(auth_module.http.server, "HTTPServer", FakeServer),
        patch.object(auth_module.threading, "Thread", FakeThread),
        patch.object(auth_module.webbrowser, "open") as mock_open,
        patch.object(auth_module, "_exchange_code", return_value=token_set) as mock_exchange,
    ):
        result = auth_module.login_browser()

    assert result == token_set
    assert handled_requests[0].sent[0] == ("status", 404)
    assert handled_requests[1].sent[0] == ("status", 200)
    assert handled_requests[1].wfile.getvalue() == b"<h2>OK! You can close this tab.</h2>"
    server_instances[0].handler_cls.log_message(SimpleNamespace(), "ignored")
    mock_open.assert_called_once()
    mock_exchange.assert_called_once_with(
        "browser-code", mock_exchange.call_args.args[1], auth_module.REDIRECT_URI
    )


def test_login_browser_raises_oauth_error_and_timeout() -> None:
    import maestro.auth as auth_module

    class ErrorServer:
        def __init__(self, _addr, handler_cls):
            self.handler_cls = handler_cls
            self.timeout = None

        def handle_request(self):
            request = SimpleNamespace(
                path="/auth/callback?state=test-state&error=access_denied",
                wfile=io.BytesIO(),
                send_response=lambda status: None,
                send_header=lambda *args: None,
                end_headers=lambda: None,
            )
            self.handler_cls.do_GET(request)

        def server_close(self):
            return None

    class TimeoutServer:
        def __init__(self, _addr, handler_cls):
            self.timeout = None

        def handle_request(self):
            return None

        def server_close(self):
            return None

    class FakeThread:
        def __init__(self, target=None, daemon=None):
            self.target = target

        def start(self):
            self.target()

        def join(self, timeout=None):
            return None

    with (
        patch.object(auth_module, "_generate_state", return_value="test-state"),
        patch.object(auth_module.http.server, "HTTPServer", ErrorServer),
        patch.object(auth_module.threading, "Thread", FakeThread),
        patch.object(auth_module.webbrowser, "open"),
    ):
        with pytest.raises(RuntimeError, match="OAuth error: access_denied"):
            auth_module.login_browser()

    with (
        patch.object(auth_module.http.server, "HTTPServer", TimeoutServer),
        patch.object(auth_module.threading, "Thread", FakeThread),
        patch.object(auth_module.webbrowser, "open"),
        patch.object(auth_module.time, "time", side_effect=[0.0, 301.0]),
    ):
        with pytest.raises(RuntimeError, match="No authorization code received"):
            auth_module.login_browser()


def test_logout_and_lazy_reexports_cover_remaining_paths(capsys) -> None:
    import maestro.auth as auth_module
    from maestro.providers import chatgpt

    with patch.object(auth_module, "remove", side_effect=[True, False]):
        auth_module.logout()
        auth_module.logout()

    output = capsys.readouterr().out
    assert "Logged out." in output
    assert "Not logged in." in output

    assert auth_module.__getattr__("DEFAULT_MODEL") == chatgpt.DEFAULT_MODEL
    with pytest.raises(AttributeError):
        auth_module.__getattr__("missing")
