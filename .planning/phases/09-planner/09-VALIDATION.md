---
phase: 9
slug: planner
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-20
---

# Phase 9 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `python -m pytest tests/test_planner_node.py -q` |
| **Full suite command** | `python -m pytest -q` |
| **Estimated runtime** | ~1 second (phase tests) |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_planner_node.py -q`
- **After every plan wave:** Run `python -m pytest -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~1 second

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 09-01-01 | 01 | 1 | SC-1: planner_node returns valid AgentPlan | — | N/A | unit | `python -m pytest tests/test_planner_node.py::test_valid_dag -v` | ✅ | ✅ green |
| 09-01-02 | 01 | 1 | SC-2: model_validate_json rejects invalid output | — | Invalid LLM output rejected, not passed downstream | unit | `python -m pytest tests/test_planner_node.py::test_schema_rejection tests/test_planner_node.py::test_schema_validation_rejection -v` | ✅ | ✅ green |
| 09-01-03 | 01 | 1 | SC-3: Configurable model from config.agent.planner.model | — | N/A | unit | `python -m pytest tests/test_planner_node.py::test_config_model_resolution tests/test_planner_node.py::test_config_provider_resolution tests/test_planner_node.py::test_config_fallback_to_default_provider tests/test_planner_node.py::test_default_provider_first_model_used_when_config_absent -v` | ✅ | ✅ green |
| 09-01-04 | 01 | 1 | SC-4: System prompt produces atomic tasks with domain assignments | — | N/A | unit | `python -m pytest tests/test_planner_node.py::test_planner_exports_prompt tests/test_planner_node.py::test_provider_receives_schema_enforced_system_prompt_and_user_task -v` | ✅ | ✅ green |
| 09-01-05 | 01 | 1 | Cycle detection: validate_dag rejects cyclic DAGs | — | Cyclic plan never passed to scheduler | unit | `python -m pytest tests/test_planner_node.py::test_cycle_rejection -v` | ✅ | ✅ green |
| 09-01-06 | 01 | 1 | Retry logic: up to 3 retries with error feedback | — | N/A | unit | `python -m pytest tests/test_planner_node.py::test_retry_success -v` | ✅ | ✅ green |
| 09-01-07 | 01 | 1 | Markdown fence stripping: robust JSON parsing | — | N/A | unit | `python -m pytest tests/test_planner_node.py::test_markdown_fences_stripped -v` | ✅ | ✅ green |
| 09-01-08 | 01 | 1 | Stream text-chunk handling (CR-01 fix) | — | N/A | unit | `python -m pytest tests/test_planner_node.py::test_stream_with_text_chunks tests/test_planner_node.py::test_stream_mixed_chunks_then_message_uses_message_as_canonical -v` | ✅ | ✅ green |
| 09-01-09 | 01 | 1 | Non-parse errors propagate without retry | — | Auth/network errors not silently swallowed | unit | `python -m pytest tests/test_planner_node.py::test_non_parse_errors_propagate_without_retry -v` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements.

- `tests/test_planner_node.py` — 15 tests covering all acceptance criteria
- `pytest` already installed and configured in `pyproject.toml`

---

## Manual-Only Verifications

All phase behaviors have automated verification.

---

## Validation Sign-Off

- [x] All tasks have automated verify
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 2s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-04-20

---

## Validation Audit 2026-04-20

| Metric | Count |
|--------|-------|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |

All 9 success criteria have automated test coverage. Phase is fully Nyquist-compliant.
15 tests in `tests/test_planner_node.py` — all passing (`python -m pytest tests/test_planner_node.py -q` → 15 passed in 0.06s).
