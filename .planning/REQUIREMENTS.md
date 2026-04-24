# Maestro - v1.2 Requirements

## Scope

This file is scoped to milestone `v1.2`. It tracks the hardening work selected for the next milestone rather than replaying already-completed roadmap requirements from `v1.0` and `v1.1`.

## Milestone Goals

- Prevent planning metadata drift from recurring.
- Validate the external provider plugin contract through a real install path.
- Add a release-grade Copilot smoke gate for the most user-sensitive auth path.
- Bound optional aggregator usage with explicit runtime controls.

## Requirements

### Planning Integrity (META)

- [ ] **META-01**: A repository-level planning consistency check validates alignment between `.planning/ROADMAP.md`, `.planning/STATE.md`, the active milestone summary, and phase evidence references.
- [ ] **META-02**: The consistency check runs in automated verification for the repository so planning drift fails fast instead of being discovered during milestone closeout.
- [ ] **META-03**: New-milestone and milestone-close documentation paths reference the consistency gate so future planning updates keep the artifact set synchronized.

### External Provider Contract (PLUGIN)

- [ ] **PLUGIN-01**: A smoke test creates or installs a minimal third-party provider package in an isolated environment and exposes it through the `maestro.providers` entry-point group.
- [ ] **PLUGIN-02**: After installation, Maestro discovers the third-party provider through its runtime registry without any source edits inside the main repository.
- [ ] **PLUGIN-03**: The smoke path is repeatable in automation and does not depend on mutating a developer's global Python environment.

### Copilot Release Gate (COP-SMOKE)

- [ ] **COP-SMOKE-01**: A release-grade smoke path exercises the real GitHub Copilot device-code login flow, including user instructions and polling completion.
- [ ] **COP-SMOKE-02**: The same gate verifies at least one live authenticated Copilot API request after login succeeds.
- [ ] **COP-SMOKE-03**: The smoke gate is safe to skip when credentials, a real account, or network access are unavailable, with the skip condition documented explicitly.

### Aggregator Runtime Guardrails (AGG-GUARD)

- [ ] **AGG-GUARD-01**: Optional aggregator calls are protected by explicit spend or call-count guardrails rather than running unbounded.
- [ ] **AGG-GUARD-02**: Repeated aggregation attempts are rate-limited or budget-limited in a way that applies during unattended multi-agent usage.
- [ ] **AGG-GUARD-03**: When a guardrail blocks or skips aggregation, the CLI emits a clear user-facing explanation instead of failing silently.
- [ ] **AGG-GUARD-04**: Automated tests cover the allow, block, and skip paths for aggregator guardrail decisions.

## Out of Scope

- Recursive sub-planner worker expansion (`TD-02`)
- New provider families beyond the current plugin ecosystem
- Changes to the main multi-agent DAG architecture beyond guardrails needed for TD-06
- UI or web surfaces for these controls

## Traceability

| REQ-ID | Phase | Description |
|--------|-------|-------------|
| META-01 | Phase 19 | Planning consistency check validates roadmap, state, summary, and evidence alignment |
| META-02 | Phase 19 | Consistency check is part of automated verification |
| META-03 | Phase 18 | Workflow documentation points future milestone updates through the consistency gate |
| PLUGIN-01 | Phase 18 | Isolated third-party provider install smoke path |
| PLUGIN-02 | Phase 18 | Runtime provider discovery works after install without source edits |
| PLUGIN-03 | Phase 18 | Smoke path is automation-safe and avoids global environment mutation |
| COP-SMOKE-01 | Phase 20 | Real Copilot device-code login gate |
| COP-SMOKE-02 | Phase 20 | Live authenticated Copilot API request after login |
| COP-SMOKE-03 | Phase 18 | Explicit safe-skip path for unavailable credentials or network |
| AGG-GUARD-01 | Phase 18 | Explicit spend or call-count guardrails around aggregator |
| AGG-GUARD-02 | Phase 18 | Repeated aggregation attempts are bounded in unattended runs |
| AGG-GUARD-03 | Phase 18 | CLI explains aggregator blocks or skips clearly |
| AGG-GUARD-04 | Phase 18 | Guardrail behavior is covered by automated tests |
