---
phase: 15
slug: external-provider-install-smoke-test
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-24
---

# Phase 15 — Validation Strategy

> Reconstructed Nyquist validation contract for the completed external provider install smoke-test phase.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `MAESTRO_RUN_INTEGRATION=1 python3 -m pytest tests/test_provider_install_smoke.py -v` |
| **Full suite command** | `python3 -m pytest tests/ -x -q` |
| **Estimated runtime** | ~20 seconds |

---

## Sampling Rate

- **After every task commit:** Run `MAESTRO_RUN_INTEGRATION=1 python3 -m pytest tests/test_provider_install_smoke.py -v`
- **After every plan wave:** Run `python3 -m pytest tests/ -x -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 20 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 15-01-01 | 01 | 1 | PLUGIN-01 | T-15-01 | Fixture package declares the `maestro.providers` entry point and exposes a provider implementation with the expected protocol surface. | fixture sanity | `python3 -c "import sys; sys.path.insert(0, 'tests/fixtures/hello_provider'); from hello_provider import HelloProvider; h = HelloProvider(); assert h.id == 'hello'; assert h.name == 'Hello Provider'; assert h.auth_required() is False; assert h.is_authenticated() is True; print('fixture ok')"` | ✅ | ✅ green |
| 15-01-02 | 01 | 1 | PLUGIN-01 | T-15-02 | Smoke test creates a fresh venv in `tmp_path` and installs both maestro and the external fixture package inside that isolated environment. | integration | `MAESTRO_RUN_INTEGRATION=1 python3 -m pytest tests/test_provider_install_smoke.py -v` | ✅ | ✅ green |
| 15-01-02 | 01 | 1 | PLUGIN-02 | T-15-03 | `discover_providers()` runs in a subprocess and must return a mapping containing `hello` without any source edits to maestro. | integration | `MAESTRO_RUN_INTEGRATION=1 python3 -m pytest tests/test_provider_install_smoke.py -v` | ✅ | ✅ green |
| 15-01-02 | 01 | 1 | PLUGIN-03 | T-15-02 / T-15-04 | Validation remains opt-in for the heavy smoke path while the default suite stays green and the global Python environment remains untouched. | regression | `python3 -m pytest tests/ -x -q` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements.

---

## Manual-Only Verifications

All phase behaviors have automated verification.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 20s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-04-24
