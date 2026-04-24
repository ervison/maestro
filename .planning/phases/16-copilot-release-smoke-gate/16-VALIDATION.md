---
phase: 16
slug: copilot-release-smoke-gate
status: partial
nyquist_compliant: false
wave_0_complete: true
created: 2026-04-24
---

# Phase 16 — Validation Strategy

> Reconstructed Nyquist validation contract for the completed Copilot release smoke-gate phase.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `python3 -m pytest tests/test_copilot_smoke.py -v` |
| **Full suite command** | `python3 -m pytest tests/ -x -q` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python3 -m pytest tests/test_copilot_smoke.py -v`
- **After every plan wave:** Run `python3 -m pytest tests/ -x -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 16-01-01 | 01 | 1 | COP-SMOKE-01 | T-16-04 | When `MAESTRO_COPILOT_SMOKE=1` and no token is pre-seeded, the smoke test must call `provider.login()` and exercise the real device-code flow in an isolated auth store. | integration | `MAESTRO_COPILOT_SMOKE=1 python3 -m pytest tests/test_copilot_smoke.py -v` | ✅ | ⬜ pending |
| 16-01-01 | 01 | 1 | COP-SMOKE-02 | T-16-01 / T-16-02 | In token-seeded mode, the smoke test must use an isolated auth store, call `provider.stream(...)`, and assert a non-empty live Copilot API response. | integration | `MAESTRO_COPILOT_SMOKE=1 MAESTRO_COPILOT_TOKEN=<ghu_token> python3 -m pytest tests/test_copilot_smoke.py -v` | ✅ | ⬜ pending |
| 16-01-01 | 01 | 1 | COP-SMOKE-03 | T-16-02 | The smoke gate must skip cleanly by default, document all skip conditions, and keep the default regression suite green. | regression | `python3 -m pytest tests/test_copilot_smoke.py -v && python3 -m pytest tests/ -x -q` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real GitHub device-code authorization completes end-to-end | COP-SMOKE-01 | Requires a human to authorize the displayed `user_code` with a real GitHub Copilot subscription. | Run `MAESTRO_COPILOT_SMOKE=1 python3 -m pytest tests/test_copilot_smoke.py -v`, approve the device-code prompt on GitHub, and confirm `1 passed`. |
| Live authenticated Copilot API request succeeds against `api.githubcopilot.com` | COP-SMOKE-02 | Requires a valid long-lived `ghu_...` token or equivalent live subscription credentials plus outbound network access. | Run `MAESTRO_COPILOT_SMOKE=1 MAESTRO_COPILOT_TOKEN=<ghu_token> python3 -m pytest tests/test_copilot_smoke.py -v` and confirm `1 passed`. |

---

## Audit Notes

- State detected: **B** (`SUMMARY.md` artifacts present, no existing `16-VALIDATION.md`)
- Artifacts audited: `16-01-PLAN.md`, `16-01-SUMMARY.md`, `tests/test_copilot_smoke.py`, `maestro/providers/copilot.py`, `maestro/providers/base.py`, `maestro/auth.py`, `tests/test_provider_install_smoke.py`, `pyproject.toml`
- Fresh verification evidence:
  - `python3 -m pytest tests/test_copilot_smoke.py -v` → `1 skipped`
  - `python3 -m pytest tests/test_copilot_smoke.py -v --collect-only` → `1 test collected`
  - `python3 -m pytest tests/ -x -q` → `119 passed, 2 skipped`
- Requirement coverage result:
  - `COP-SMOKE-01` → structurally covered by the interactive branch in `tests/test_copilot_smoke.py`, but not executable here without live authorization
  - `COP-SMOKE-02` → structurally covered by the token-seeded live API branch in `tests/test_copilot_smoke.py`, but not executable here without live credentials/network
  - `COP-SMOKE-03` → freshly verified green via skip dry-run and full regression suite
- Gap analysis: **0 missing**, **2 partial (environment-gated execution)**, **1 green**

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending live credentialed smoke run
