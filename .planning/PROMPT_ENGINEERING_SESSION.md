# Prompt Engineering Session Memory

**Date:** 2026-04-25  
**Branch:** main  
**Last commit before session:** `bb317f2`  
**Test baseline:** 159 passed, 2 pre-existing failures (`test_planning_consistency`, `test_planning_check_command_exits_zero_when_consistent` — `STATE.md` vs `ROADMAP.md` mismatch, unrelated to prompt work)

---

## Goal

Harden the Maestro SDLC prompt pipeline using persuasion-based discipline patterns from the article *"The Psychology Hack That Makes LLMs Obey Engineering Discipline"* (Rick Hightower / Cialdini):

- **Authority language** — role is authoritative and binding, not advisory
- **Rationalization table** — named forbidden excuses with rebuttals inline
- **Commitment device** — declare upstream sources before writing
- **MANDATE blocks** — explicit automatic-FAIL conditions

---

## Technical Defaults (`maestro/sdlc/defaults.py`)

`TECHNICAL_DEFAULTS` is injected into every run via `harness.py:arun()`. It now has:

- **Preamble:** `## AUTHORITATIVE TECHNICAL DEFAULTS` with 5 named forbidden rationalizations:
  - "The user didn't mention a database" → PostgreSQL
  - "A simpler stack would suffice" → defaults are already production-grade minimal
  - "This feature doesn't need auth" → JWT RBAC applies to all features
  - "100% coverage is unrealistic" → non-negotiable baseline
  - "The user might prefer another language" → Go is backend default
- **Closing guard:** `## ENFORCEMENT` — "Silence is NOT an override"

Stack enforced: PostgreSQL, Go, REST/OpenAPI 3.x, JWT RBAC (admin/user), Next.js + shadcn/ui + Tailwind, Docker Compose, TDD/100% coverage, golangci-lint + ESLint, Conventional Commits, slog, Prometheus, `GET /health`, bcrypt/argon2id, CORS, rate limiting, HTTPS, security headers, `/api/v1/` prefix, error envelope `{"error":{"code":"...","message":"..."}}`, dual IDs (BIGSERIAL internal + UUID v4 public), `.env.example`, Makefile (5 targets), README, GitHub Actions CI, storage abstraction via `STORAGE_BACKEND` env var.

---

## Artifact Prompts (`maestro/sdlc/prompts.py`)

All 10 artifact prompts hardened. Status:

| Artifact | Authority | Rationalization Table | Commitment Device |
|---|---|---|---|
| `_BASE` / `_BASE_RESOLVED` | ✅ | — | — |
| `BRIEFING` | ✅ | ✅ | — |
| `HYPOTHESES` | ✅ | ✅ | — |
| `PRD` | ✅ | ✅ | ✅ |
| `FUNCTIONAL_SPEC` | ✅ | ✅ | ✅ |
| `BUSINESS_RULES` | ✅ | ✅ | — |
| `NFR` | ✅ | ✅ | — |
| `UX_SPEC` | ✅ | ✅ | ✅ |
| `AUTH_MATRIX` | ✅ | ✅ | ✅ |
| `DATA_MODEL` | ✅ | ✅ | — |
| `API_CONTRACTS` | ✅ | ✅ | ✅ |
| `ACCEPTANCE_CRITERIA` | ✅ | ✅ | ✅ |
| `ADRS` | ✅ | ✅ | — |
| `TEST_PLAN` | ✅ | ✅ | — |

---

## Gate Reviewer (`maestro/sdlc/reviewer.py`)

All 6 gates hardened:

- Each gate: "Your decision is authoritative and binding."
- Each gate: MANDATE block with named forbidden rationalizations
- Gates 3, 5, 6: CROSS-CHECK explicit — numeric discrepancies, role mismatches, untested access control = automatic FAIL
- `_RESPONSE_FORMAT`: strict — `passed=true` requires `issues=[]`; caveat-in-notes → FAIL; each issue must name exact artifact/field/rule

---

## Generators (`maestro/sdlc/generators.py`)

- Empty content fallback replaced: was silent placeholder `"(no content generated)"`, now raises `RuntimeError("[generators] {artifact_type}: provider returned empty content after all attempts")`
- Test updated: `test_sdlc_generators.py` expects `RuntimeError` on empty stream
- Prior artifacts injected via `_build_user_message()` as `## Prior Artifacts (use as authoritative source — do not contradict)`

---

## Harness (`maestro/sdlc/harness.py`)

Two inline prompt strings hardened:

1. **Brownfield scan:** `## Existing Codebase (AUTHORITATIVE — do not contradict or ignore)` + instruction to flag contradictions as `[GAP]` or architectural decision
2. **Gap Answers:** `## Gap Answers (AUTHORITATIVE — these answers SUPERSEDE any prior hypothesis or assumption)` + "Silence on a topic in these answers does NOT mean the hypothesis stands"

---

## Reflect Loop (`maestro/sdlc/reflect.py`)

Four changes:

1. **`_REFLECT_SYSTEM`** constant added — sent as `role="system"` in both eval and fix calls. Contains authority framing + 4 named forbidden rationalizations ("close enough to threshold", "intent is clear", "can be fixed later", "other artifacts compensate")
2. **Role intro removed** from both `_build_eval_prompt` and `_build_fix_prompt` (role is now in system message)
3. **Eval MANDATE added:** score 8+ requires explicit evidence, not inference; score below 8 must appear in problems if top-3 impactful
4. **Fix MANDATE added:** each patch addresses exactly one problem; "too large to change" rationalization forbidden

**DIMENSIONS** reduced from 11 to 8, now covering:
- Cobertura de domínio e requisitos
- Consistência entre artefatos ← new (cross-artifact)
- Completude dos artefatos ← new (completeness)
- Correção técnica e factual ← new (correctness distinct from completeness)
- Alinhamento modelo ↔ API ↔ dados
- Plano de testes vs. escopo
- Rastreabilidade (fonte → requisito → artefato → decisão) ← expanded
- Cobertura de requisitos não-funcionais (NFR)

**`TARGET_MEAN`** now configurable:
- Module default: `TARGET_MEAN = 8.0`
- `ReflectLoop(target_mean: float = TARGET_MEAN)` → `self._target_mean`
- `Harness(reflect_target_mean: float = 8.0)` → forwarded to `ReflectLoop`

---

## Gaps Server (`maestro/sdlc/gaps_server.py`)

`_ENRICH_SYSTEM` replaced with authoritative version:
- Role: "performing a MANDATORY enrichment task. Your output is consumed directly by a UI — it MUST be machine-parseable."
- MANDATORY RULES section (replaces "Rules:") — named violations produce broken UI
- RATIONALIZATION GUARD — 3 named forbidden shortcuts: "question is self-explanatory", "user will know", "only two obvious answers"

---

## Pre-existing Issues (do not fix without investigation)

- `tests/test_cli_planning.py::test_planning_check_command_exits_zero_when_consistent` — `STATE.md progress.total_phases (17)` does not match `ROADMAP.md phases (20)`. Planning doc mismatch, not related to prompt work.
- `tests/test_planning_consistency.py::test_repository_planning_artifacts_are_currently_consistent` — same root cause.

---

## Next Steps (identified but not executed)

None identified. All surfaces audited and hardened:
- `prompts.py` ✅
- `defaults.py` ✅
- `reviewer.py` ✅
- `generators.py` ✅
- `harness.py` ✅
- `reflect.py` ✅
- `gaps_server.py` ✅

If new artifact types are added to the SDLC pipeline, apply the same pattern:
1. Authority language in role sentence
2. Rationalization table with domain-specific forbidden excuses
3. Commitment device if the artifact has upstream sources it must trace
4. MANDATE block for automatic-FAIL conditions
