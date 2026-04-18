from urllib.parse import parse_qs, urlparse

from maestro import auth


def test_authorize_url_uses_127_0_0_1_redirect():
    url = auth._build_authorize_url(
        auth._build_browser_redirect_uri(4321), "challenge", "state123"
    )

    params = parse_qs(urlparse(url).query)

    assert params["redirect_uri"] == ["http://127.0.0.1:4321/auth/callback"]
    assert "localhost" not in params["redirect_uri"][0]


def test_authorize_url_includes_connector_scopes():
    url = auth._build_authorize_url(
        auth._build_browser_redirect_uri(4321), "challenge", "state123"
    )

    scope = parse_qs(urlparse(url).query)["scope"][0]

    assert "openid" in scope
    assert "offline_access" in scope
    assert "api.connectors.read" in scope
    assert "api.connectors.invoke" in scope


def test_authorize_url_has_required_params():
    url = auth._build_authorize_url(
        auth._build_browser_redirect_uri(4321), "challenge", "state123"
    )

    params = parse_qs(urlparse(url).query)

    assert params["response_type"] == ["code"]
    assert params["client_id"] == [auth.CLIENT_ID]
    assert params["code_challenge"] == ["challenge"]
    assert params["code_challenge_method"] == ["S256"]
    assert params["state"] == ["state123"]
    assert params["id_token_add_organizations"] == ["true"]
    assert params["codex_cli_simplified_flow"] == ["true"]
    assert params["originator"] == ["codex_cli_rs"]


def test_callback_extracts_code_on_valid_state():
    code, error = auth._parse_browser_callback(
        "/auth/callback?state=state123&code=auth-code", "state123"
    )

    assert code == "auth-code"
    assert error is None


def test_callback_rejects_mismatched_state():
    code, error = auth._parse_browser_callback(
        "/auth/callback?state=wrong&code=auth-code", "state123"
    )

    assert code is None
    assert error == "State mismatch"


def test_callback_surfaces_provider_error():
    code, error = auth._parse_browser_callback(
        "/auth/callback?state=state123&error=unknown_error", "state123"
    )

    assert code is None
    assert error == "unknown_error"
