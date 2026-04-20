---
phase: 02
slug: multi-slot-auth-store
status: compliant
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-20
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `python -m pytest tests/test_auth_store.py -v` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~2 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_auth_store.py -v`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~2 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | AUTH-01, AUTH-02 | T-02-01 | `auth.json` created with `0o600` | unit | `python -m pytest tests/test_auth_store.py::test_set_get_roundtrip tests/test_auth_store.py::test_get_nonexistent_returns_none tests/test_auth_store.py::test_file_permissions tests/test_auth_store.py::test_multiple_providers_isolated tests/test_auth_store.py::test_all_providers tests/test_auth_store.py::test_remove tests/test_auth_store.py::test_remove_nonexistent_returns_false -v` | ✅ | ✅ green |
| 02-01-02 | 01 | 1 | AUTH-01, AUTH-02 | T-02-01 | Legacy flat migration preserves credentials | unit | `python -m pytest tests/test_auth_store.py::test_auto_migration tests/test_auth_store.py::test_load_backward_compat tests/test_auth_store.py::test_save_backward_compat -v` | ✅ | ✅ green |
| 02-01-03 | 01 | 1 | AUTH-08 | — | Only `maestro login` emits deprecation; `logout`/`status` do not | unit | `python -m pytest tests/test_auth_store.py::test_auth_login_defaults_to_chatgpt tests/test_auth_store.py::test_old_login_shows_deprecation tests/test_auth_store.py::test_old_logout_deprecation tests/test_auth_store.py::test_old_status_no_deprecation -v` | ✅ | ✅ green |
| 02-02-01 | 02 | 2 | AUTH-01 | T-02-01 | `_write_store` uses `0o600` on every write (first-write mode + subsequent chmod) | unit | `python -m pytest tests/test_auth_store.py::test_write_store_uses_secure_create_mode -v` | ✅ | ✅ green |
| 02-02-02 | 02 | 2 | AUTH-01, AUTH-02 | T-02-01 | Corrupt/non-dict store raises `RuntimeError` rather than silently corrupting | unit | `python -m pytest tests/test_auth_store.py::test_invalid_auth_store_raises_runtime_error tests/test_auth_store.py::test_non_dict_store_raises_runtime_error tests/test_auth_store.py::test_non_dict_provider_entry_raises_runtime_error -v` | ✅ | ✅ green |
| 02-02-03 | 02 | 2 | AUTH-01, AUTH-02 | — | `agent.py` path via `auth.load()` and `auth._save()` still works through shims | integration | `python -m pytest tests/test_auth_store.py::test_agent_run_uses_auth_shims -v` | ✅ | ✅ green |
| 02-03-01 | 03 | 3 | AUTH-08 | — | `maestro auth login [provider]` defaults to `chatgpt` and uses discovered provider plugin | unit | `python -m pytest tests/test_auth_store.py::test_auth_login_defaults_to_chatgpt tests/test_auth_store.py::test_auth_login_uses_discovered_provider -v` | ✅ | ✅ green |
| 02-03-02 | 03 | 3 | AUTH-08 | — | Browser OAuth PKCE shape matches upstream plugin contract | unit | `python -m pytest tests/test_auth_store.py::test_login_browser_matches_working_plugin_authorize_url tests/test_auth_store.py::test_generate_pkce_matches_upstream_codex_shape tests/test_auth_store.py::test_generate_state_matches_working_plugin_shape -v` | ✅ | ✅ green |
| 02-03-03 | 03 | 3 | AUTH-08 | — | CLI routing falls back correctly for missing/invalid model/provider combinations | integration | `python -m pytest tests/test_auth_store.py::test_run_with_explicit_unsupported_provider_calls_run tests/test_auth_store.py::test_run_with_invalid_model_format_exits_cleanly tests/test_auth_store.py::test_run_with_env_selected_unsupported_provider_calls_run tests/test_auth_store.py::test_run_with_model_flag_bypasses_invalid_config_reload tests/test_auth_store.py::test_run_without_explicit_selection_falls_back_to_chatgpt -v` | ✅ | ✅ green |
| 02-03-04 | 03 | 3 | AUTH-08 | — | OAuth callback server handles stray/malformed requests without crashing | unit | `python -m pytest tests/test_auth_store.py::test_callback_server_survives_stray_request_before_real_callback tests/test_auth_store.py::test_callback_server_rejects_wrong_path_with_404 -v` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements. `tests/test_auth_store.py` was created in Plan 01 (TDD RED phase) as part of Wave 1.

---

## Requirements Coverage Summary

| Requirement | Description | Tests | Status |
|-------------|-------------|-------|--------|
| AUTH-01 | Per-provider auth storage in `~/.maestro/auth.json` with mode `0o600` | `test_set_get_roundtrip`, `test_file_permissions`, `test_write_store_uses_secure_create_mode`, `test_auto_migration`, `test_multiple_providers_isolated`, `test_invalid_auth_store_raises_runtime_error`, `test_non_dict_store_raises_runtime_error`, `test_non_dict_provider_entry_raises_runtime_error` | ✅ COVERED |
| AUTH-02 | Public auth API: `get`, `set`, `remove`, `all_providers` | `test_set_get_roundtrip`, `test_get_nonexistent_returns_none`, `test_all_providers`, `test_remove`, `test_remove_nonexistent_returns_false`, `test_load_backward_compat`, `test_save_backward_compat`, `test_agent_run_uses_auth_shims` | ✅ COVERED |
| AUTH-08 | `maestro auth login [provider]` canonical path; `maestro login` deprecated only | `test_auth_login_defaults_to_chatgpt`, `test_auth_login_uses_discovered_provider`, `test_old_login_shows_deprecation`, `test_old_logout_deprecation`, `test_old_status_no_deprecation`, `test_login_browser_matches_working_plugin_authorize_url`, `test_generate_pkce_matches_upstream_codex_shape`, `test_generate_state_matches_working_plugin_shape` | ✅ COVERED |

---

## Manual-Only Verifications

All phase behaviors have automated verification.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify commands
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0: existing test infrastructure covers all phase requirements
- [x] No watch-mode flags
- [x] Feedback latency < 2s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-04-20

---

## Validation Audit 2026-04-20

| Metric | Count |
|--------|-------|
| Requirements audited | 3 |
| Tasks audited | 10 |
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |
| Total tests | 30 |
| All passing | ✅ yes |
