"""
OAuth2 authentication for ChatGPT Plus/Pro subscriptions.
Implements PKCE Authorization Code flow and Device Code flow
against auth.openai.com, same as the official Codex CLI.
"""

import base64
import hashlib
import http.server
import json
import os
import secrets
import threading
import time
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

import httpx

CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
AUTHORIZE_URL = "https://auth.openai.com/oauth/authorize"
TOKEN_URL = "https://auth.openai.com/oauth/token"
DEVICE_CODE_URL = "https://auth.openai.com/api/accounts/deviceauth/usercode"
DEVICE_TOKEN_URL = "https://auth.openai.com/api/accounts/deviceauth/token"
DEVICE_CALLBACK = "https://auth.openai.com/deviceauth/callback"
REDIRECT_URI = "http://127.0.0.1:1455/auth/callback"
SCOPE = "openid profile email offline_access"
CALLBACK_PORT = 1455
AUTH_CLAIM = "https://api.openai.com/auth"

CODEX_API_BASE = "https://chatgpt.com/backend-api"

AUTH_FILE = Path(
    os.environ.get("MAESTRO_AUTH_FILE", Path.home() / ".maestro" / "auth.json")
)


def _read_store() -> dict:
    """Read the full auth store from disk. Auto-migrate old flat format."""
    if not AUTH_FILE.exists():
        return {}
    try:
        data = json.loads(AUTH_FILE.read_text())
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Invalid auth store at {AUTH_FILE}; remove or repair the file."
        ) from exc
    if isinstance(data, dict) and "access" in data and "chatgpt" not in data:
        data = {"chatgpt": data}
        _write_store(data)
    if not isinstance(data, dict) or any(
        not isinstance(provider_data, dict) for provider_data in data.values()
    ):
        raise RuntimeError(
            f"Invalid auth store at {AUTH_FILE}; remove or repair the file."
        )
    return data


def _write_store(store: dict) -> None:
    """Write the full auth store to disk with secure permissions."""
    AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(AUTH_FILE), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write(json.dumps(store))
    AUTH_FILE.chmod(0o600)


def get(provider_id: str) -> dict | None:
    """Get credentials for a specific provider."""
    return _read_store().get(provider_id)


def set(provider_id: str, data: dict) -> None:
    """Store credentials for a specific provider."""
    store = _read_store()
    store[provider_id] = data
    _write_store(store)


def remove(provider_id: str) -> bool:
    """Remove stored credentials for a specific provider."""
    store = _read_store()
    if provider_id not in store:
        return False
    del store[provider_id]
    _write_store(store)
    return True


def all_providers() -> list[str]:
    """List all provider IDs with stored credentials."""
    return list(_read_store().keys())




@dataclass
class TokenSet:
    access: str
    refresh: str
    expires: float
    account_id: str = ""
    email: str = ""


def _save(tokens: TokenSet):
    set(
        "chatgpt",
        {
            "access": tokens.access,
            "refresh": tokens.refresh,
            "expires": tokens.expires,
            "account_id": tokens.account_id,
            "email": tokens.email,
        },
    )


def load() -> TokenSet | None:
    data = get("chatgpt")
    if data is None:
        return None
    return TokenSet(**data)


# --------------- JWT helpers ---------------


def _decode_jwt(token: str) -> dict | None:
    parts = token.split(".")
    if len(parts) != 3:
        return None
    payload = parts[1]
    payload = payload.replace("-", "+").replace("_", "/")
    padding = 4 - len(payload) % 4
    if padding != 4:
        payload += "=" * padding
    try:
        return json.loads(base64.b64decode(payload))
    except Exception:
        return None


def _extract_account_id(access_token: str) -> str:
    claims = _decode_jwt(access_token)
    if not claims:
        return ""
    auth = claims.get(AUTH_CLAIM, {})
    return auth.get("chatgpt_account_id", "")


def _extract_email(id_token: str) -> str:
    claims = _decode_jwt(id_token)
    if not claims:
        return ""
    return claims.get("email", "")


# --------------- PKCE ---------------


def _generate_pkce() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode()
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def _generate_state() -> str:
    return secrets.token_hex(16)


# --------------- Token exchange ---------------


def _exchange_code(code: str, verifier: str, redirect: str = REDIRECT_URI) -> TokenSet:
    r = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": redirect,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    r.raise_for_status()
    d = r.json()
    access = d["access_token"]
    ts = TokenSet(
        access=access,
        refresh=d.get("refresh_token", ""),
        expires=time.time() + d.get("expires_in", 3600),
        account_id=_extract_account_id(access),
        email=_extract_email(d.get("id_token", "")),
    )
    _save(ts)
    return ts


def refresh_token(ts: TokenSet) -> TokenSet:
    r = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": ts.refresh,
            "client_id": CLIENT_ID,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    r.raise_for_status()
    d = r.json()
    access = d["access_token"]
    new = TokenSet(
        access=access,
        refresh=d.get("refresh_token", ts.refresh),
        expires=time.time() + d.get("expires_in", 3600),
        account_id=_extract_account_id(access),
        email=ts.email or _extract_email(d.get("id_token", "")),
    )
    _save(new)
    return new


def ensure_valid(ts: TokenSet) -> TokenSet:
    """Refresh if token expires within 5 minutes."""
    if time.time() > ts.expires - 300:
        return refresh_token(ts)
    return ts


# --------------- Browser OAuth2 PKCE flow ---------------


def login_browser() -> TokenSet:
    verifier, challenge = _generate_pkce()
    state = _generate_state()

    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
        "id_token_add_organizations": "true",
        "codex_cli_simplified_flow": "true",
        "originator": "codex_cli_rs",
    }
    # Use urlencode (encodes spaces as '+') to match JS URLSearchParams behavior.
    # OpenAI's auth server may reject %20-encoded scope values.
    from urllib.parse import urlencode
    query = urlencode(params)
    url = f"{AUTHORIZE_URL}?{query}"

    result: dict = {}
    error: list = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            # Reject anything that isn't /auth/callback
            if parsed.path != "/auth/callback":
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Not found")
                return
            qs = parse_qs(parsed.query)
            if qs.get("state", [None])[0] != state:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"State mismatch")
                return
            if "error" in qs:
                error.append(qs["error"][0])
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"OAuth error")
                return
            code = qs.get("code", [None])[0]
            if not code:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Missing code")
                return
            result["code"] = code
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h2>OK! You can close this tab.</h2>")

        def log_message(self, *_):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", CALLBACK_PORT), Handler)
    srv.timeout = 1  # poll every 1 second

    def serve_until_done():
        deadline = time.time() + 300  # 5 minutes, matching JS plugin
        while time.time() < deadline:
            if result or error:
                return
            srv.handle_request()

    t = threading.Thread(target=serve_until_done, daemon=True)
    t.start()

    print(f"\nOpening browser for login...\n  {url}\n")
    webbrowser.open(url)

    t.join(timeout=300)
    srv.server_close()

    if error:
        raise RuntimeError(f"OAuth error: {error[0]}")
    if "code" not in result:
        raise RuntimeError("No authorization code received (timeout?)")

    return _exchange_code(result["code"], verifier)


# --------------- Device Code flow ---------------


def login_device() -> TokenSet:
    r = httpx.post(
        DEVICE_CODE_URL,
        json={"client_id": CLIENT_ID},
        headers={"Content-Type": "application/json"},
    )
    r.raise_for_status()
    d = r.json()
    device_id = d["device_auth_id"]
    user_code = d["user_code"]
    interval = int(d.get("interval", 5))

    print(f"\n  Go to: https://auth.openai.com/codex/device")
    print(f"  Enter code: {user_code}\n")

    deadline = time.time() + 900  # 15 min
    while time.time() < deadline:
        time.sleep(interval)
        r = httpx.post(
            DEVICE_TOKEN_URL,
            json={
                "device_auth_id": device_id,
                "user_code": user_code,
            },
            headers={"Content-Type": "application/json"},
        )

        if r.status_code in (403, 404):
            continue  # pending
        r.raise_for_status()

        d = r.json()
        auth_code = d["authorization_code"]
        code_verifier = d["code_verifier"]
        return _exchange_code(auth_code, code_verifier, DEVICE_CALLBACK)

    raise RuntimeError("Device code login timed out")


def login(method: str = "browser") -> TokenSet:
    if method == "device":
        return login_device()
    return login_browser()


def logout():
    if remove("chatgpt"):
        print("Logged out.")
    else:
        print("Not logged in.")


# Backward-compat re-exports (moved to maestro.providers.chatgpt in Phase 3)
# The provider module is the canonical source; these are lazy re-exports.
# Using __getattr__ avoids circular imports since chatgpt.py imports from auth.


def __getattr__(name: str):
    """Lazy re-export model constants from maestro.providers.chatgpt."""
    if name in ("MODELS", "MODEL_ALIASES", "DEFAULT_MODEL", "resolve_model"):
        # Import here to avoid circular import at module load time
        from maestro.providers import chatgpt

        return getattr(chatgpt, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
