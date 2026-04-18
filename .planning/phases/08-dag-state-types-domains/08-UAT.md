# Phase 08 UAT — DAG State, Types & Domains

**Date:** 2026-04-18T21:27:23Z  
**Method:** Re-verification UAT with executable checks (pytest + runtime smoke), grounded in ROADMAP/REQUIREMENTS contract.

## Does this phase require `uat-test-execution` substep?

**Yes.**

Reason: Phase 08 delivers runtime-validatable behavior (schema validation, DAG safety checks, domain fallback/selection). Static review alone is insufficient.

## UAT Scenarios

### Scenario 1 — Planner payload validation

**Given** planner JSON payloads for `PlanTask` and `AgentPlan`  
**When** payloads are valid/invalid  
**Then** valid payloads are accepted and malformed payloads are rejected.

**Evidence:**
- `python -m pytest tests/test_planner_schemas.py -q` → `29 passed, 1 warning`
- Covers unknown fields, missing deps, invalid dep item types, invalid domain values, and `model_validate_json`.

**Result:** ✅ Pass

---

### Scenario 2 — DAG safety validation

**Given** DAG task graphs  
**When** cycles or unknown dependencies are present  
**Then** `validate_dag` rejects before dispatch.

**Evidence:**
- `maestro/planner/validator.py` uses `TopologicalSorter(graph)` + `ts.prepare()` and explicit unknown-dependency checks.
- Cycle and invalid-dependency tests pass in `tests/test_planner_schemas.py`.

**Result:** ✅ Pass

---

### Scenario 3 — Domain prompts and fallback

**Given** known and unknown domain values  
**When** requesting prompts  
**Then** known domains return specialized prompts and unknown domains fall back to `general` without error.

**Evidence:**
- `python -m pytest tests/test_domains.py -q` → `34 passed, 1 warning`
- `python -c "from maestro.domains import DOMAINS,get_domain_prompt; print('data_in_domains', 'data' in DOMAINS); print('fallback_general', get_domain_prompt('UNKNOWN')==DOMAINS['general'])"`
  - `data_in_domains True`
  - `fallback_general True`

**Result:** ✅ Pass

---

### Scenario 4 — Phase contract domain set (`data`)

**Given** Phase 08 success criteria / DOM-02 contract  
**When** verifying built-in domain vocabulary  
**Then** required domain set includes `backend`, `testing`, `docs`, `devops`, `data`, `general`.

**Evidence:**
- `maestro/domains.py` contains all required domains including `data`.
- `maestro/planner/schemas.py` `DomainName` accepts `data`.
- Runtime smoke: `PlanTask(id='t1', domain='data', ...)` validates successfully.

**Result:** ✅ Pass

## UAT Conclusion

- Phase 08 runtime checks pass after remediation.
- Contract gap from previous verification (`data` domain missing) is now resolved.

**Final UAT verdict:** ✅ **Accepted**
