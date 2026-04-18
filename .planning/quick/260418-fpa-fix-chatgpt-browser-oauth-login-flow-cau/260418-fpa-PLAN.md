---
phase: quick
plan: 260418-fpa
type: execute
wave: 1
depends_on: []
files_modified:
  - maestro/auth.py
  - tests/test_auth_browser_oauth.py
autonomous: true
requirements: [QUICK-FIX]
must_haves:
  truths:
    - "Browser OAuth login works against current OpenAI auth contract"
    - "Callback server listens on dynamic port using localhost (not 127.0.0.1)"
    - "Authorize URL includes all required scopes from official contract"
    - "Test coverage exists for authorize URL construction and callback behavior"
  artifacts:
    - path: "maestro/auth.py"
      provides: "Updated browser OAuth flow matching official Codex contract"
      contains: "localhost"
    - path: "tests/test_auth_browser_oauth.py"
      provides: "Automated tests for browser OAuth authorize URL and callback"
      min_lines: 40
  key_links:
    - from: "maestro/auth.py:login_browser()"
      to: "https://auth.openai.com/oauth/authorize"
      via: "urlencode params with correct scope and redirect_uri"
      pattern: "api.connectors"
---

<objective>
Fix ChatGPT browser OAuth login flow (`maestro auth login chatgpt`) that currently fails with `unknown_error`.

**Root Cause (established):**
- Current `REDIRECT_URI` hardcodes `http://127.0.0.1:1455/auth/callback`
- Official OpenAI Codex CLI uses `http://localhost:<dynamic_port>/auth/callback`
- Current `SCOPE` missing `api.connectors.read api.connectors.invoke` from official contract

**Purpose:** Restore working browser OAuth login by aligning with official OpenAI auth contract.

**Output:** Updated `maestro/auth.py` with correct OAuth parameters and new test coverage.
</objective>

<execution_context>
@.planning/quick/260418-fpa-fix-chatgpt-browser-oauth-login-flow-cau/260418-fpa-PLAN.md
</execution_context>

<context>
@maestro/auth.py (current implementation with stale OAuth parameters)
@tests/test_auth_store.py (existing auth tests — new file for browser-specific tests)
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add test coverage for browser OAuth authorize URL and callback</name>
  <files>tests/test_auth_browser_oauth.py</files>
  <behavior>
    - Test: authorize URL contains `http://localhost:{port}/auth/callback` (not 127.0.0.1)
    - Test: authorize URL scope includes `api.connectors.read api.connectors.invoke`
    - Test: authorize URL includes all required params (response_type, client_id, code_challenge, state, etc.)
    - Test: callback handler validates state and extracts code correctly
  </behavior>
  <action>
Create `tests/test_auth_browser_oauth.py` with focused tests:

1. `test_authorize_url_uses_localhost_redirect()` — verify `redirect_uri` param uses `localhost` not `127.0.0.1`
2. `test_authorize_url_includes_connector_scopes()` — verify scope includes `api.connectors.read api.connectors.invoke`
3. `test_authorize_url_has_required_params()` — verify all PKCE/OAuth params present
4. `test_callback_extracts_code_on_valid_state()` — verify code extraction logic
5. `test_callback_rejects_mismatched_state()` — verify state validation

Use `urllib.parse.parse_qs` to inspect constructed URL params. Mock the HTTP server parts; focus on URL construction and callback parsing logic.
  </action>
  <verify>
    <automated>pytest tests/test_auth_browser_oauth.py -v --tb=short 2>&1 | head -50</automated>
  </verify>
  <done>New test file exists with 5+ tests covering authorize URL params and callback behavior; tests fail initially (RED phase) because auth.py still has old values</done>
</task>

<task type="auto">
  <name>Task 2: Update auth.py browser OAuth to match official contract</name>
  <files>maestro/auth.py</files>
  <action>
Modify `maestro/auth.py` to align with official OpenAI Codex CLI OAuth contract:

1. **Change SCOPE constant** (line ~29):
   - FROM: `SCOPE = "openid profile email offline_access"`
   - TO: `SCOPE = "openid profile email offline_access api.connectors.read api.connectors.invoke"`

2. **Use dynamic port for callback** in `login_browser()` (line ~235+):
   - Remove hardcoded `CALLBACK_PORT = 1455`
   - Bind to port 0 to get OS-assigned available port
   - Extract actual port from server socket after binding
   - Update `redirect_uri` to use `localhost` with dynamic port

3. **Update REDIRECT_URI construction**:
   - Change from hardcoded `http://127.0.0.1:1455/auth/callback`
   - To dynamically constructed `http://localhost:{port}/auth/callback`

Implementation detail for dynamic port:
```python
srv = http.server.HTTPServer(("127.0.0.1", 0), Handler)
port = srv.server_address[1]
redirect_uri = f"http://localhost:{port}/auth/callback"
```

Keep `127.0.0.1` as the bind address (IPv4 loopback) but use `localhost` in the redirect_uri string — this matches the official Codex CLI behavior.

Pass the dynamic `redirect_uri` to `_exchange_code()` call at end of `login_browser()`.
  </action>
  <verify>
    <automated>pytest tests/test_auth_browser_oauth.py tests/test_auth_store.py -v --tb=short 2>&1 | tail -30</automated>
  </verify>
  <done>All browser OAuth tests pass (GREEN); existing auth_store tests still pass (no regressions)</done>
</task>

<task type="auto">
  <name>Task 3: Verify full test suite and commit</name>
  <files>maestro/auth.py, tests/test_auth_browser_oauth.py</files>
  <action>
1. Run full test suite to confirm no regressions
2. Commit with message: `fix(auth): align browser OAuth with official Codex contract`
   - Dynamic port allocation (0 → OS-assigned)
   - localhost in redirect_uri (not 127.0.0.1)
   - Add connector scopes to SCOPE constant
   - Add test coverage for authorize URL construction
  </action>
  <verify>
    <automated>pytest --tb=short -q 2>&1 | tail -10</automated>
  </verify>
  <done>Full test suite passes; changes committed</done>
</task>

</tasks>

<verification>
- `pytest tests/test_auth_browser_oauth.py -v` — new tests pass
- `pytest tests/test_auth_store.py -v` — existing tests pass (no regressions)
- `pytest --tb=short -q` — full suite passes
- Code inspection: `grep -n "localhost" maestro/auth.py` shows redirect_uri uses localhost
- Code inspection: `grep -n "api.connectors" maestro/auth.py` shows new scopes present
</verification>

<success_criteria>
- [ ] `maestro/auth.py` SCOPE includes `api.connectors.read api.connectors.invoke`
- [ ] `login_browser()` uses dynamic port (binds to 0, extracts actual port)
- [ ] `redirect_uri` in authorize URL uses `localhost` not `127.0.0.1`
- [ ] `tests/test_auth_browser_oauth.py` exists with 5+ tests
- [ ] All tests pass including existing 188+ tests
- [ ] Changes committed with descriptive message
</success_criteria>

<output>
After completion, update `.planning/quick/260418-fpa-fix-chatgpt-browser-oauth-login-flow-cau/260418-fpa-SUMMARY.md` with:
- Files changed
- Tests added
- Key implementation details
- Verification output
</output>
