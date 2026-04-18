# Phase 08 UAT — DAG State, Types & Domains

**Date:** 2026-04-18T21:09:46Z  
**Method:** Conversational UAT grounded in phase artifacts (`08-01/02 PLAN+SUMMARY`) plus direct execution of phase tests.

## Does this phase require `uat-test-execution` substep?

**Yes.**

Reason: Phase 08 delivers executable validation behavior (Pydantic schema validation, DAG cycle/dep rejection, domain fallback), so acceptance cannot rely on static review alone. Runtime checks were required and executed.

## UAT Scenarios

### Scenario 1 — Planner payload validation

**Given** a planner JSON payload for `AgentPlan`/`PlanTask`  
**When** payload is valid  
**Then** it is accepted and parsed into models  
**And** invalid/malformed payloads are rejected.

**Evidence:**
- `python -m pytest tests/test_planner_schemas.py -q` → `29 passed`
- Includes tests for unknown fields, missing deps, invalid deps item types, invalid domain values, and `model_validate_json`.

**Result:** ✅ Pass

---

### Scenario 2 — DAG safety validation

**Given** task graphs with dependencies  
**When** graph has cycles or unknown references  
**Then** validator rejects it before dispatch.

**Evidence:**
- `maestro/planner/validator.py` uses `TopologicalSorter(...).prepare()` and unknown-dependency checks.
- `tests/test_planner_schemas.py` covers 2-node cycle, 3-node cycle, self-cycle, unknown deps, duplicate IDs.

**Result:** ✅ Pass

---

### Scenario 3 — Domain prompts and fallback

**Given** worker domain values  
**When** domain is known  
**Then** domain-specific prompt is returned  
**And when** domain is unknown  
**Then** fallback to `general` occurs without error.

**Evidence:**
- `python -m pytest tests/test_domains.py -q` → `31 passed`
- `python -c "from maestro.domains import get_domain_prompt; print(isinstance(get_domain_prompt('unknown'), str))"` → `True`

**Result:** ✅ Pass

---

### Scenario 4 — Phase contract domain set

**Given** Phase 08 roadmap success criteria and REQUIREMENTS DOM-02
**When** checking built-in domain list
**Then** expected set should include `data`.

**Observed Implementation (before fix):** includes `security` instead of `data`.

**Result:** ❌ Fail (contract mismatch)

---

## Remediation Applied (2026-04-18)

**Action:** Option A — Implement `data` domain and align schema/tests.

**Changes made:**
1. Added `data` domain to `maestro/domains.py` DOMAINS dict with domain-specific system prompt
2. Updated `DomainName` Literal in `maestro/planner/schemas.py` to include `"data"`
3. Updated `EXPECTED_DOMAINS` in `tests/test_domains.py` to include `"data"` (7 domains total)
4. All 63 scoped tests pass (test_domains.py + test_planner_schemas.py)

**Verification:**
- `get_domain_prompt('data')` returns a valid string (364 chars)
- Domain prompt includes "data engineering specialist" focus
- All domain tests now pass with 7 domains

## UAT Conclusion (Post-Remediation)

- Runtime behavior and tests are strong for schemas, DAG validation, and fallback mechanics.
- **All contract requirements now met:** `data` domain is implemented alongside existing domains.

**Final UAT verdict:** ✅ **Accepted** — Phase 08 contract mismatch resolved.
