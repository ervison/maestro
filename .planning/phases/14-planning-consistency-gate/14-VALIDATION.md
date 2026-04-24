---
phase: 14
slug: planning-consistency-gate
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-24
---

# Phase 14 - Validation Strategy

> Reconstructed Nyquist validation audit for the completed planning consistency gate phase.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `python -m pytest tests/test_planning_consistency.py tests/test_cli_planning.py -v` |
| **Full suite command** | `python -m pytest tests/ -q` |
| **Estimated runtime** | ~8 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_planning_consistency.py tests/test_cli_planning.py -v`
- **After every plan wave:** Run `python -m pytest tests/ -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 14-01-01 | 01 | 1 | META-01 | T-14-01 / T-14-02 | `check_planning_consistency()` rejects missing or mismatched `REQUIREMENTS.md` milestone scope without changing public interfaces. | unit | `python -m pytest tests/test_planning_consistency.py -v -x` | ✅ | ✅ green |
| 14-01-02 | 01 | 1 | META-02 | T-14-01 / T-14-02 | Drift paths for requirements, summary text, and evidence files are covered by isolated fixture tests. | unit | `python -m pytest tests/test_planning_consistency.py -v` | ✅ | ✅ green |
| 14-02-01 | 02 | 2 | META-02 | T-14-04 | CLI exits non-zero on inconsistent planning artifacts and forwards `--root` to the checker. | CLI | `python -m pytest tests/test_cli_planning.py -v` | ✅ | ✅ green |
| 14-02-02 | 02 | 2 | META-03 | T-14-03 | Milestone workflow documentation requires `maestro planning check` at milestone open/close transitions. | docs | `python -c "from pathlib import Path; text = Path('.planning/MILESTONE-WORKFLOW.md').read_text(); assert 'maestro planning check' in text; assert 'Opening a New Milestone' in text; assert 'Closing a Milestone' in text; print('OK')"` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements.

---

## Manual-Only Verifications

All phase behaviors have automated verification.

---

## Audit Notes

- State detected: **B** (`SUMMARY.md` artifacts present, no existing `14-VALIDATION.md`)
- Artifacts audited: `14-01-PLAN.md`, `14-02-PLAN.md`, `14-01-SUMMARY.md`, `14-02-SUMMARY.md`, `maestro/planning.py`, `tests/test_planning_consistency.py`, `tests/test_cli_planning.py`, `.planning/MILESTONE-WORKFLOW.md`
- Requirement coverage result:
  - `META-01` -> covered by `tests/test_planning_consistency.py`
  - `META-02` -> covered by `tests/test_planning_consistency.py` and `tests/test_cli_planning.py`
  - `META-03` -> covered by `.planning/MILESTONE-WORKFLOW.md` content check
- Gap analysis: **0 missing**, **0 partial**, **3 covered requirements**

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 10s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-04-24
