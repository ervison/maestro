# Wave 1 — NFR Artifact Foundation

## Progress

| Microtask | Description | Status |
|-----------|-------------|--------|
| 1.1 | Update schema tests to expect 14 artifacts | `[ ]` |
| 1.2 | Add NFR to ArtifactType enum and mappings | `[ ]` |
| 1.3 | Update generators test for 14 prompts | `[ ]` |
| 1.4 | Add NFR system prompt to PROMPTS dict | `[ ]` |
| 1.5 | Fix all remaining 13→14 test references | `[ ]` |
| 1.6 | Commit Wave 1 | `[ ]` |

> Update status to `[x]` when a microtask is complete, `[~]` when in progress, `[!]` if blocked.

---

**Goal:** Introduce the 14th artifact type (`NFR`) to schemas and prompts, then update all
existing tests that hard-code the number 13.

**Why this wave first:** Every subsequent wave depends on `ArtifactType.NFR` existing in the
enum, its filename mapping, and its prompt.  Nothing in wave 1 requires new modules or new
classes — it is purely additive to existing files plus test fixes.

**Dependencies:** None — this wave is the root of the entire plan.

**Files touched:**
- `maestro/sdlc/schemas.py`
- `maestro/sdlc/prompts.py`
- `tests/test_sdlc_schemas.py`
- `tests/test_sdlc_generators.py`
- `tests/test_sdlc_harness.py`
- `tests/test_sdlc_writer.py`

---

## `[ ]` Microtask 1.1 — Update Schema Tests to Expect 14 Artifacts

**File:** `tests/test_sdlc_schemas.py`

**Pre-condition:** Run `pytest tests/test_sdlc_schemas.py -v` — it must currently PASS with 13.

**Action:** Apply the following changes to `tests/test_sdlc_schemas.py`:

1. Rename `test_artifact_type_has_13_members` → `test_artifact_type_has_14_members`, change assertion to `assert len(ArtifactType) == 14`.

2. Rename `test_artifact_filenames_numbered_01_to_13` → `test_artifact_filenames_numbered_01_to_14`, change assertion to:
```python
def test_artifact_filenames_numbered_01_to_14() -> None:
    numbers = sorted(
        int(v.split("-")[0]) for v in ARTIFACT_FILENAMES.values()
    )
    assert numbers == list(range(1, 15))
```

3. Update `test_discovery_result_artifact_count` to expect 14:
```python
def test_discovery_result_artifact_count() -> None:
    req = SDLCRequest("Build X")
    arts = [
        SDLCArtifact(t, ARTIFACT_FILENAMES[t], "content")
        for t in ArtifactType
    ]
    result = DiscoveryResult(request=req, artifacts=arts, spec_dir="/tmp/spec")
    assert result.artifact_count == 14
```

4. Add the length invariant guard test at the end of the file:
```python
def test_artifact_filenames_and_order_have_same_size() -> None:
    assert len(ARTIFACT_FILENAMES) == len(ArtifactType) == len(ARTIFACT_ORDER) == 14
```

**Verification:** Run `pytest tests/test_sdlc_schemas.py -v` — it must FAIL (3–4 failures expected because the source has not changed yet).

---

## `[ ]` Microtask 1.2 — Add NFR to ArtifactType Enum and Mappings

**File:** `maestro/sdlc/schemas.py`

**Pre-condition:** Microtask 1.1 must be applied; tests are failing.

**Action:** Apply the following changes to `maestro/sdlc/schemas.py`:

1. Change the docstring at line 10 from `"""The 13 SDLC artifact types"""` to `"""The 14 SDLC artifact types"""`.

2. Add `NFR = "nfr"` to the `ArtifactType` enum, immediately after `TEST_PLAN = "test_plan"`:
```python
    TEST_PLAN = "test_plan"
    NFR = "nfr"
```

3. Add the filename mapping to `ARTIFACT_FILENAMES` dict, after `ArtifactType.TEST_PLAN`:
```python
    ArtifactType.TEST_PLAN: "13-test-plan.md",
    ArtifactType.NFR: "14-nfr.md",
```

4. Append `ArtifactType.NFR` at the end of `ARTIFACT_ORDER` list (slot 14):
```python
ARTIFACT_ORDER: list[ArtifactType] = [
    ArtifactType.BRIEFING,
    ArtifactType.HYPOTHESES,
    ArtifactType.GAPS,
    ArtifactType.PRD,
    ArtifactType.FUNCTIONAL_SPEC,
    ArtifactType.BUSINESS_RULES,
    ArtifactType.ACCEPTANCE_CRITERIA,
    ArtifactType.UX_SPEC,
    ArtifactType.API_CONTRACTS,
    ArtifactType.DATA_MODEL,
    ArtifactType.AUTH_MATRIX,
    ArtifactType.ADRS,
    ArtifactType.TEST_PLAN,
    ArtifactType.NFR,
]
```

**Verification:** Run `pytest tests/test_sdlc_schemas.py -v` — ALL PASS.

---

## `[ ]` Microtask 1.3 — Update Generators Test for 14 Prompts

**File:** `tests/test_sdlc_generators.py`

**Pre-condition:** Microtask 1.2 must be applied.

**Action:** Locate `test_prompts_cover_all_artifact_types` in `tests/test_sdlc_generators.py` and replace its body so it expects 14 prompts:

```python
def test_prompts_cover_all_artifact_types() -> None:
    assert len(PROMPTS) == 14
    missing = set(ArtifactType) - set(PROMPTS)
    assert not missing, f"Missing prompts for: {missing}"
```

**Verification:** Run `pytest tests/test_sdlc_generators.py::test_prompts_cover_all_artifact_types -v` — it must FAIL (PROMPTS still has 13 entries).

---

## `[ ]` Microtask 1.4 — Add NFR System Prompt to PROMPTS Dict

**File:** `maestro/sdlc/prompts.py`

**Pre-condition:** Microtask 1.3 must be applied; test is failing.

**Action:** In `maestro/sdlc/prompts.py`, add the NFR entry to the `PROMPTS` dict immediately after the `ArtifactType.TEST_PLAN` entry:

```python
    ArtifactType.NFR: (
        "You are a senior performance and reliability engineer. "
        "Write the Non-Functional Requirements (NFR) document: performance targets, "
        "availability SLAs, scalability constraints, security requirements, "
        "compliance obligations, and operational thresholds. "
        "Include measurable criteria for each requirement. "
        + _BASE_RESOLVED
    ),
```

**Verification:** Run `pytest tests/test_sdlc_generators.py::test_prompts_cover_all_artifact_types -v` — PASS.

---

## `[ ]` Microtask 1.5 — Fix All Remaining 13→14 Test References

**Files:** `tests/test_sdlc_harness.py`, `tests/test_sdlc_generators.py`, `tests/test_sdlc_writer.py`

**Pre-condition:** Microtasks 1.2 and 1.4 must be applied.

**Action:**

### In `tests/test_sdlc_harness.py`:
- Rename `test_harness_run_produces_13_artifacts` → `test_harness_run_produces_14_artifacts`, change assertion to `assert result.artifact_count == 14`.
- Rename `test_harness_writes_13_files` → `test_harness_writes_14_files`, change assertion to `assert len(written) == 14`.
- In `test_harness_writes_each_artifact_incrementally`, change assertion to `assert len(written_counts) == 14`.

### In `tests/test_sdlc_generators.py`:
- In `test_harness_with_provider_calls_generators` (if present), change assertions to `assert len(provider.calls) == 14` and `assert result.artifact_count == 14`.

### In `tests/test_sdlc_writer.py`:
- In `test_write_artifacts_writes_all_files`, change assertion to `assert len(written) == 14`.

**Verification:** Run `pytest tests/test_sdlc_*.py -v` — ALL PASS.

---

## `[ ]` Microtask 1.6 — Commit Wave 1

**Pre-condition:** All tests in `tests/test_sdlc_*.py` pass.

**Action:**
```bash
git add maestro/sdlc/schemas.py maestro/sdlc/prompts.py \
        tests/test_sdlc_schemas.py tests/test_sdlc_generators.py \
        tests/test_sdlc_harness.py tests/test_sdlc_writer.py
git commit -m "feat(sdlc): add NFR as 14th artifact type and update all 13→14 test references"
```

**Verification:** `git status` shows clean working tree.
