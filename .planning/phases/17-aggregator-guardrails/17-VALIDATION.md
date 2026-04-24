---
phase: 17
slug: aggregator-guardrails
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-24
---

# Phase 17 — Validation Strategy

> Reconstructed Nyquist validation contract for the completed aggregator guardrails phase.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `python3 -m pytest tests/test_aggregator_guardrails.py -v` |
| **Full suite command** | `python3 -m pytest tests/ -x -q` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python3 -m pytest tests/test_aggregator_guardrails.py -v`
- **After every plan wave:** Run `python3 -m pytest tests/ -x -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 17-01-01 | 01 | 1 | AGG-GUARD-01 | T-17-02 | `check_aggregator_guardrail()` must allow safe runs and block call-count or token-budget violations with explicit reasons. | unit | `python3 -m pytest tests/test_aggregator_guardrails.py -v -k "call_count_checks or token_budget_checks or combined_limits"` | ✅ | ✅ green |
| 17-01-02 | 01 | 1 | AGG-GUARD-02 | T-17-02 | `scheduler_route()` and `run_multi_agent()` must stop the optional aggregator when `max_calls=0` or configured limits are exceeded. | integration | `python3 -m pytest tests/test_aggregator_guardrails.py -v -k "scheduler_route or run_multi_agent"` | ✅ | ✅ green |
| 17-01-02 | 01 | 1 | AGG-GUARD-03 | T-17-03 | Blocked aggregation must print `[aggregator] skipped — <reason>` so unattended runs explain the policy decision. | integration | `python3 -m pytest tests/test_aggregator_guardrails.py -v -k "scheduler_route_blocks"` | ✅ | ✅ green |
| 17-01-02 | 01 | 1 | AGG-GUARD-04 | — | The phase must retain automated coverage for allow, block-by-call-count, skip-by-token-budget, and config-validation paths. | regression | `python3 -m pytest tests/test_aggregator_guardrails.py -v && python3 -m pytest tests/ -x -q` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements.

---

## Manual-Only Verifications

All phase behaviors have automated verification.

---

## Audit Notes

- State detected: **B** (`17-01-SUMMARY.md` present, no existing `17-VALIDATION.md`)
- Artifacts audited: `17-01-PLAN.md`, `17-01-SUMMARY.md`, `tests/test_aggregator_guardrails.py`, `maestro/multi_agent.py`, `maestro/planner/schemas.py`, `maestro/config.py`, `pyproject.toml`
- Fresh verification evidence:
  - `python3 -m pytest tests/test_aggregator_guardrails.py -v` → `15 passed`
  - `python3 -m pytest tests/test_aggregator_guardrails.py tests/test_aggregator.py tests/test_multi_agent_cli.py -x -q` → failed immediately because `tests/test_aggregator.py` does not exist in the current repository
  - `python3 -m pytest tests/ -x -q` → `119 passed, 2 skipped`
- Requirement coverage result:
  - `AGG-GUARD-01` → covered by `TestAggregatorGuardrail::test_call_count_checks`, `test_token_budget_checks`, and `test_combined_limits`
  - `AGG-GUARD-02` → covered by `TestSchedulerRouteIntegration::test_scheduler_route_blocks_when_max_calls_zero`, `test_scheduler_route_allows_when_no_guardrail`, and `TestRunMultiAgentGuardrailIntegration::test_run_multi_agent_respects_max_calls_zero`
  - `AGG-GUARD-03` → covered by lifecycle assertions in `test_scheduler_route_blocks_when_max_calls_zero` and `test_scheduler_route_blocks_token_budget_exceeded`
  - `AGG-GUARD-04` → covered by the dedicated phase test file plus full-suite regression evidence
- Gap analysis: **0 missing tests**, **0 failing tests**, **1 stale automated command corrected in this validation map**

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 10s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-04-24
