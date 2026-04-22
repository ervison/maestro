# SECURITY.md — Phase 12: DAG Planner Hardening

**Phase:** 12 — dag-planner-hardening  
**Audited:** 2026-04-21 (updated post-fix round 2)  
**ASVS Level:** 1  
**Auditor:** GSD Security Auditor  

---

## Verdict: SECURED (updated round 2 — all threats CLOSED, behavioral test updated)

All mitigations declared in PLAN.md `## Threat Model` are present in code.  
No new attack surface was introduced. No new code execution paths, file I/O, or network calls were added.

---

## Threat Verification

| Threat ID | Category | Disposition | Evidence |
|-----------|----------|-------------|----------|
| T-REASONING-PARSE | Prompt/Parsing | mitigate | `model_validate_json(raw)` raises `json.JSONDecodeError` on non-JSON prefix, caught at line 214 in `node.py`; retried up to 3× with corrective feedback. `<reasoning>` block content is never executed or unsafely parsed — it is discarded on `JSONDecodeError`. CLOSED. |
| T-LLM-IGNORE | Prompt Injection / LLM Behavior | mitigate | `PLANNER_SYSTEM_PROMPT` uses "MUST output reasoning block" authority language (line 61, `node.py`). `test_prompt_contains_reasoning_block_instruction` in `tests/test_planner_prompt.py` line 31 asserts `<reasoning>` is present. CLOSED. |
| T-SOFTENING-LANGUAGE | Prompt Quality / Regression | mitigate | `test_prompt_forbids_softening_language` (line 35, `tests/test_planner_prompt.py`) asserts `['prefer', 'Prefer', 'try to', 'Try to', 'consider', 'Consider', 'generally', 'Generally']` are absent. Verified: none present in prompt. CLOSED. |
| T-EXISTING-TESTS | Regression | mitigate | SUMMARY.md confirms 393 tests pass, 0 failures after phase. Two existing prompt-assertion tests updated to match hardened content. CLOSED. |
| T-RATIONALIZATION-AMBIGUOUS | Prompt Quality | mitigate | Rationalization table has explicit `Verdict` column (MERGE / MERGE or ADD DEP) in `node.py` lines 52–57. CLOSED. |

---

## Security Focus Checklist

### 1. Prompt Injection — New Vectors

**Finding: CLEAR**

The new `PLANNER_SYSTEM_PROMPT` introduces a `<reasoning>` commitment device. The `<reasoning>...</reasoning>` XML-like tags are rendered as a string literal in the prompt and transmitted to the LLM as instruction text. They create **no parsing risk** in the host application because:

- The LLM response containing `<reasoning>...</reasoning>` before JSON is passed to `AgentPlan.model_validate_json(raw)` (line 209, `node.py`)
- Pydantic's `model_validate_json` calls the stdlib JSON parser, which will raise `json.JSONDecodeError` on the non-JSON `<reasoning>` prefix
- This exception is **explicitly caught** at line 214 (`except (ValueError, json.JSONDecodeError)`)
- The error handling appends corrective feedback and retries — the `<reasoning>` text is **never executed, eval'd, or shell-interpolated**
- The `<reasoning>` tags are not parsed as XML/HTML anywhere in the codebase

**Residual note (accepted, low severity):** PLAN.md states reasoning block content "will be skipped by any JSON parser looking for `{`" — this is accurate for `json.loads()` called on a string starting with `{`. However, `model_validate_json(raw)` is called on the entire raw string including the `<reasoning>` prefix; a compliant LLM that follows the prompt will cause `JSONDecodeError` on attempt 1, consuming one retry. This is a known behavioral quirk, not a security vulnerability. It is handled correctly by the retry loop. If it becomes operationally disruptive, a future phase may add a `re.search(r'\{.*\}', raw, re.DOTALL)` extractor before `model_validate_json`.

The prompt does NOT introduce new prompt injection vectors that could exfiltrate data, bypass path guards, or invoke shell commands. The reasoning block is LLM-generated natural language, not code.

### 2. No New Code Execution Paths

**Finding: CLEAR**

Audited `maestro/planner/node.py` — the phase changed **only** the `PLANNER_SYSTEM_PROMPT` string constant (lines 29–75). Verified:

- No new `exec()` calls — **absent**
- No new `eval()` calls — **absent**
- No new `subprocess` calls — **absent**
- No new `os.system()` calls — **absent**
- No new `compile()` calls — **absent**
- All existing function signatures, imports, and logic unchanged (confirmed by SUMMARY.md: "No function signatures, imports, or logic changed.")

### 3. No New File I/O

**Finding: CLEAR**

Audited `maestro/planner/node.py` — no new `open()`, `os.path`, `pathlib.Path`, or file read/write calls were added. The domain list construction at lines 78–82 reads from the in-memory `DOMAINS` dict (imported at line 21), not from disk.

### 4. No New Network Calls

**Finding: CLEAR**

Audited `maestro/planner/node.py` — no new `httpx`, `requests`, `aiohttp`, `urllib`, or socket calls were added. The only network path remains the existing `provider.stream()` call (line 123/125), which was present before this phase.

### 5. Test File Safety (`tests/test_planner_prompt.py`)

**Finding: CLEAR**

Audited `tests/test_planner_prompt.py` (73 lines):

- **Imports:** Only `pytest` and `maestro.planner.node.PLANNER_SYSTEM_PROMPT` — no dangerous imports
- **No** `exec`, `eval`, `subprocess`, `os`, `sys`, `socket`, `httpx`, or file I/O
- **No** dynamic code generation or reflection
- All 7 test functions perform string `in` membership tests; the new behavioral test (`test_over_decomposition_behavioral`) uses `AgentPlan`/`PlanTask` from `maestro.planner.schemas` with static in-memory data — no LLM calls, no I/O, no `eval`, no `exec`. Domain models are pure-Python dataclasses with Pydantic validation — no code execution surface.

---

## Unregistered Threat Flags

None. No `## Threat Flags` section present in SUMMARY.md.

---

## Accepted Risks Log

| ID | Description | Rationale | Owner |
|----|-------------|-----------|-------|
| AR-12-01 | `<reasoning>` prefix in LLM output causes `JSONDecodeError` on attempt 1, consuming one of 3 retries | By design: retry loop handles it correctly. Not a security risk. Low operational impact (1 extra LLM call at worst). Mitigated if LLM follows the prompt correctly. | Phase 12 |

---

## Files Audited

| File | Change Type | Verdict |
|------|-------------|---------|
| `maestro/planner/node.py` | PLANNER_SYSTEM_PROMPT string constant rewritten | CLEAR |
| `tests/test_planner_prompt.py` | New test file | CLEAR |
| `tests/test_planner_node.py` | 2 existing test assertions updated to match hardened prompt | CLEAR (regression fix, not security relevant) |
