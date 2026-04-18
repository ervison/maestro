# Quick Task 260418-fpa Summary

## Goal

Fix the browser OAuth contract used by `maestro auth login chatgpt` so it matches the current OpenAI/Codex flow and avoids the `unknown_error` browser failure.

## Files Changed

- `maestro/auth.py`
- `tests/test_auth_browser_oauth.py`

## Implementation

- Added connector scopes required by the current browser OAuth contract: `api.connectors.read` and `api.connectors.invoke`.
- Switched the browser callback from a fixed `127.0.0.1:1455` redirect to a dynamic local callback URL using `http://localhost:{port}/auth/callback`.
- Extracted small helpers for browser authorize URL construction and callback parsing so the contract is directly testable.
- Preserved the existing device-code path; the fix stays scoped to the broken browser login flow.

## Tests Added

- `test_authorize_url_uses_localhost_redirect`
- `test_authorize_url_includes_connector_scopes`
- `test_authorize_url_has_required_params`
- `test_callback_extracts_code_on_valid_state`
- `test_callback_rejects_mismatched_state`
- `test_callback_surfaces_provider_error`

## Verification

- `pytest tests/test_auth_browser_oauth.py -q` -> `6 passed`
- `pytest tests/test_auth_store.py -q` -> `25 passed`
- `pytest -q` -> `196 passed`

## Outcome

Maestro now builds the browser OAuth authorize URL using the current contract expected by OpenAI/Codex, which is the minimal fix for the reported `unknown_error` during `maestro auth login chatgpt`.
