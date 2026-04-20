---
phase: 03
slug: chatgpt-provider-migration
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-20
---

# Phase 03 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 + pytest-anyio |
| **Config file** | `pyproject.toml` ([tool.pytest.ini_options]) |
| **Quick run command** | `python -m pytest tests/test_chatgpt_provider.py -v` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~2 seconds (unit) / ~6 seconds (full suite) |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_chatgpt_provider.py -v`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~6 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 1 | LOOP-04 | T-03-01 | Credentials never logged; read via auth.get() only | unit | `python -m pytest tests/test_chatgpt_provider.py::TestProtocolCompliance tests/test_chatgpt_provider.py::TestStreamContract -v` | ✅ | ✅ green |
| 03-01-02 | 01 | 1 | LOOP-04 | — | N/A | unit | `python -m pytest tests/test_chatgpt_provider.py::TestBackwardCompatibility -v` | ✅ | ✅ green |
| 03-01-03 | 01 | 1 | PROV-03 | T-03-02 | Hardcoded API base; no user-controlled endpoint | unit | `python -m pytest tests/test_chatgpt_provider.py::TestEntryPointRegistration -v` | ✅ | ✅ green |
| 03-01-04 | 01 | 1 | LOOP-04 | — | N/A | unit | `python -m pytest tests/test_chatgpt_provider.py::TestTypeConversionHelpers -v` | ✅ | ✅ green |
| 03-01-05 | 01 | 1 | PROV-03 / LOOP-04 | — | N/A | unit | `python -m pytest tests/test_chatgpt_provider.py tests/test_provider_protocol.py tests/test_auth_store.py -v` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covered all phase requirements. No Wave 0 install steps needed.

- ✅ `tests/test_chatgpt_provider.py` — 30 tests covering PROV-03, LOOP-04 (created during phase execution)
- ✅ pytest + pytest-anyio already installed

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `stream()` yields real text chunks from ChatGPT API | LOOP-04 | Requires live ChatGPT credentials and network | Run `maestro run "say hello"` and observe streamed output |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (none were missing at phase start)
- [x] No watch-mode flags
- [x] Feedback latency < 6s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-04-20

---

## Validation Audit 2026-04-20

| Metric | Count |
|--------|-------|
| Gaps found | 2 |
| Resolved | 2 |
| Escalated | 0 |

**Gaps resolved:**
1. Added `TestEntryPointRegistration::test_entry_point_discoverable` — verifies `chatgpt` entry point discoverable via `importlib.metadata`
2. Added `TestEntryPointRegistration::test_chatgpt_provider_importable_from_package` — verifies `ChatGPTProvider` importable from `maestro.providers.__init__`

**Final test count:** 30 tests, 30 passed
