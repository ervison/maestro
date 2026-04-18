# External Integrations

**Analysis Date:** 2025-04-18

## APIs & External Services

### OpenAI / ChatGPT

**Authentication:**
- **Service:** OpenAI OAuth2 (`auth.openai.com`)
- **Flow:** PKCE Authorization Code + Device Code
- **Client ID:** `app_EMoamEEZ73f0CkXaXp7hrann` (hard-coded in `maestro/auth.py:22`)
- **Scope:** `openid profile email offline_access api.connectors.read api.connectors.invoke`

**API Endpoints:**
- **Authorize URL:** `https://auth.openai.com/oauth/authorize`
- **Token URL:** `https://auth.openai.com/oauth/token`
- **Device Code URL:** `https://auth.openai.com/api/accounts/deviceauth/usercode`
- **Device Token URL:** `https://auth.openai.com/api/accounts/deviceauth/token`
- **API Base:** `https://chatgpt.com/backend-api`
- **Responses Endpoint:** `https://chatgpt.com/backend-api/codex/responses`

**SDK/Client:**
- Raw `httpx` with SSE streaming (not OpenAI SDK)
- Custom `httpx.stream()` for synchronous legacy path
- `httpx.AsyncClient.stream()` for provider-based async path

### Models.dev Catalog

**Purpose:** Dynamic model list fetching
- **URL:** `https://models.dev/api.json`
- **Usage:** Filter for codex-compatible models (`gpt-5*` or `*codex*`)
- **Cache:** `~/.cache/maestro/models-dev.json` (1 hour TTL)

## Data Storage

**Local Filesystem Only:**

| File | Purpose | Location |
|------|---------|----------|
| `auth.json` | OAuth tokens | `~/.maestro/auth.json` |
| `config.json` | User configuration | `~/.maestro/config.json` |
| `models-dev.json` | Cached model list | `~/.cache/maestro/models-dev.json` |
| `models-available.json` | Probed available models | `~/.cache/maestro/models-available.json` |

**No External Databases**

## Authentication & Identity

**Auth Provider:** ChatGPT / OpenAI

**Credentials Storage:**
- Format: JSON with per-provider keys
- Encryption: None (relies on filesystem permissions)
- Permissions: 0o600 (user read/write only)

**Token Types:**
- Access token (short-lived, ~1 hour)
- Refresh token (long-lived)
- Claims extracted: `account_id`, `email`

**Auth Methods:**
1. **Browser Flow:** PKCE with local callback server (`localhost:1455`)
2. **Device Flow:** Headless, user enters code at `auth.openai.com/codex/device`

## Monitoring & Observability

**Not Implemented:**
- No error tracking service (Sentry, etc.)
- No metrics collection
- No structured logging (uses standard Python logging)

**Logging:**
- `logging.getLogger(__name__)` pattern
- Debug logs for model fetching failures

## CI/CD & Deployment

**Not Configured:**
- No CI pipeline configuration found
- No automated testing in CI
- No release automation

**Distribution:**
- PyPI-ready via `pyproject.toml`
- Entry point: `maestro = "maestro.cli:main"`
- Install: `pip install -e .` (editable) or `pip install .`

## Environment Configuration

**Required Environment Variables:**
| Variable | Required | Description |
|----------|----------|-------------|
| `MAESTRO_CONFIG_FILE` | No | Override config.json path |
| `MAESTRO_AUTH_FILE` | No | Override auth.json path |
| `MAESTRO_MODEL` | No | Default model (provider/model format) |

**Secrets Location:**
- `~/.maestro/auth.json` - OAuth tokens
- Created by `auth.login()` flows
- Protected by 0o600 permissions

## Webhooks & Callbacks

**Incoming:**
- **OAuth Callback:** `http://localhost:1455/auth/callback`
  - Handler: `auth.py:Handler` class
  - Purpose: Receive authorization code from browser OAuth
  - Lifetime: 5 minutes timeout

**Outgoing:**
- None (no webhook subscriptions)

## Planned Integrations (Per ROADMAP)

### GitHub Copilot (Phase 5)
- **OAuth:** Device code flow (planned)
- **Client ID:** `Ov23li8tweQw6odWQebz` (from design spec)
- **API Base:** `https://api.githubcopilot.com`
- **Endpoint:** `/chat/completions` (OpenAI-compatible)
- **Status:** Not yet implemented

## Network Requirements

**Outbound HTTPS to:**
- `auth.openai.com` - OAuth flows
- `chatgpt.com` - ChatGPT API
- `models.dev` - Model catalog
- `api.githubcopilot.com` - Future Copilot integration

**Inbound:**
- `localhost:1455` - OAuth callback (temporary, browser flow only)

## Security Considerations

- OAuth tokens stored unencrypted (filesystem permissions only)
- No token rotation beyond refresh
- Device flow has 15-minute timeout
- PKCE state parameter used for CSRF protection
- Local callback server bound to localhost only

---

*Integration audit: 2025-04-18*
