# Wave 2 — Sprint DAG Module + Sprint/Gate Dataclasses

## Progress

| Microtask | Description | Status |
|-----------|-------------|--------|
| 2.1 | Create `maestro/sdlc/sprints.py` | `[ ]` |
| 2.2 | Create `tests/test_sdlc_sprints.py` | `[ ]` |
| 2.3 | Add GateResult and SprintResult to schemas.py | `[ ]` |
| 2.4 | Add GateResult/SprintResult tests to test_sdlc_schemas.py | `[ ]` |
| 2.5 | Commit Wave 2 | `[ ]` |

> Update status to `[x]` when a microtask is complete, `[~]` when in progress, `[!]` if blocked.

---

**Goal:** Create `maestro/sdlc/sprints.py` with the full 6-sprint DAG definition, add
`SprintDef`, `GateResult`, and `SprintResult` dataclasses to `maestro/sdlc/schemas.py`, and
write the full test suites for both.

**Why this wave second:** Wave 1 must be complete because `sprints.py` imports
`ArtifactType.NFR`.  The new dataclasses introduced here are required by Wave 3 (reviewer) and
Wave 4 (harness).

**Dependencies:** Wave 1 complete.

**Files touched:**
- `maestro/sdlc/sprints.py` (create)
- `maestro/sdlc/schemas.py` (add dataclasses)
- `tests/test_sdlc_sprints.py` (create)
- `tests/test_sdlc_schemas.py` (add dataclass tests)

---

## `[ ]` Microtask 2.1 — Create `maestro/sdlc/sprints.py`

**File:** `maestro/sdlc/sprints.py` (create new)

**Pre-condition:** Wave 1 complete — `ArtifactType.NFR` exists.

**Action:** Create the file with the following exact content:

```python
"""SDLC Sprint DAG — 6 sprints with dependency edges and parallel groups."""
from __future__ import annotations

from dataclasses import dataclass, field

from graphlib import TopologicalSorter

from maestro.sdlc.schemas import ArtifactType


@dataclass(frozen=True)
class SprintDef:
    """Definition of a single sprint in the SDLC pipeline."""

    sprint_id: int
    name: str
    artifacts: tuple[ArtifactType, ...]
    deps: dict[ArtifactType, tuple[ArtifactType, ...]]
    description: str = ""


SPRINTS: list[SprintDef] = [
    SprintDef(
        sprint_id=1,
        name="Descoberta",
        artifacts=(
            ArtifactType.BRIEFING,
            ArtifactType.HYPOTHESES,
            ArtifactType.GAPS,
        ),
        deps={
            ArtifactType.BRIEFING: (),
            ArtifactType.HYPOTHESES: (ArtifactType.BRIEFING,),
            ArtifactType.GAPS: (ArtifactType.BRIEFING,),
        },
        description="Discovery: briefing, hypotheses, and gaps",
    ),
    SprintDef(
        sprint_id=2,
        name="Definicao",
        artifacts=(
            ArtifactType.PRD,
        ),
        deps={
            ArtifactType.PRD: (ArtifactType.BRIEFING, ArtifactType.HYPOTHESES, ArtifactType.GAPS),
        },
        description="Product definition: PRD",
    ),
    SprintDef(
        sprint_id=3,
        name="Especificacao",
        artifacts=(
            ArtifactType.FUNCTIONAL_SPEC,
            ArtifactType.BUSINESS_RULES,
            ArtifactType.NFR,
            ArtifactType.ADRS,
        ),
        deps={
            ArtifactType.FUNCTIONAL_SPEC: (ArtifactType.PRD,),
            ArtifactType.BUSINESS_RULES: (ArtifactType.PRD, ArtifactType.FUNCTIONAL_SPEC),
            ArtifactType.NFR: (ArtifactType.PRD,),
            ArtifactType.ADRS: (ArtifactType.PRD,),
        },
        description="Specification: func-spec, biz-rules, NFR, ADRs (co-evolution)",
    ),
    SprintDef(
        sprint_id=4,
        name="Experiencia",
        artifacts=(
            ArtifactType.UX_SPEC,
        ),
        deps={
            ArtifactType.UX_SPEC: (ArtifactType.PRD, ArtifactType.FUNCTIONAL_SPEC),
        },
        description="UX: user experience specification",
    ),
    SprintDef(
        sprint_id=5,
        name="Realizacao Tecnica",
        artifacts=(
            ArtifactType.AUTH_MATRIX,
            ArtifactType.DATA_MODEL,
            ArtifactType.API_CONTRACTS,
        ),
        deps={
            ArtifactType.AUTH_MATRIX: (ArtifactType.FUNCTIONAL_SPEC, ArtifactType.BUSINESS_RULES, ArtifactType.UX_SPEC),
            ArtifactType.DATA_MODEL: (ArtifactType.FUNCTIONAL_SPEC, ArtifactType.BUSINESS_RULES, ArtifactType.AUTH_MATRIX, ArtifactType.ADRS, ArtifactType.NFR),
            ArtifactType.API_CONTRACTS: (ArtifactType.FUNCTIONAL_SPEC, ArtifactType.BUSINESS_RULES, ArtifactType.UX_SPEC, ArtifactType.AUTH_MATRIX, ArtifactType.ADRS, ArtifactType.NFR, ArtifactType.DATA_MODEL),
        },
        description="Technical realization: auth-matrix, data-model, api-contracts",
    ),
    SprintDef(
        sprint_id=6,
        name="Validacao",
        artifacts=(
            ArtifactType.ACCEPTANCE_CRITERIA,
            ArtifactType.TEST_PLAN,
        ),
        deps={
            ArtifactType.ACCEPTANCE_CRITERIA: (ArtifactType.PRD, ArtifactType.FUNCTIONAL_SPEC, ArtifactType.BUSINESS_RULES, ArtifactType.UX_SPEC),
            ArtifactType.TEST_PLAN: (ArtifactType.PRD, ArtifactType.FUNCTIONAL_SPEC, ArtifactType.BUSINESS_RULES, ArtifactType.ACCEPTANCE_CRITERIA, ArtifactType.UX_SPEC, ArtifactType.API_CONTRACTS, ArtifactType.AUTH_MATRIX, ArtifactType.ADRS, ArtifactType.NFR),
        },
        description="Validation: acceptance criteria and test plan",
    ),
]


def get_ready_artifacts(sprint: SprintDef, completed: set[ArtifactType]) -> list[list[ArtifactType]]:
    """Return groups of artifacts that can be generated in parallel.

    Returns a list of groups (waves). Each wave contains artifacts whose
    deps are all in `completed`. Waves are ordered by dependency — the
    first wave has zero deps within the sprint, subsequent waves depend
    on earlier waves.

    Artifacts whose deps are already fully satisfied by `completed`
    (from prior sprints) appear in the first wave.
    """
    sorter = TopologicalSorter(
        {artifact: [d for d in sprint.deps.get(artifact, ()) if d in sprint.artifacts] for artifact in sprint.artifacts}
    )
    sorter.prepare()

    waves: list[list[ArtifactType]] = []
    while sorter.is_active():
        ready = [node for node in sorter.get_ready() if all(
            d in completed for d in sprint.deps.get(node, ())
        )]
        if not ready:
            break
        waves.append(ready)
        for node in ready:
            sorter.done(node)
            completed.add(node)

    return waves


def all_sprint_artifacts() -> set[ArtifactType]:
    """Return the union of all artifact types across all sprints."""
    result: set[ArtifactType] = set()
    for sprint in SPRINTS:
        result.update(sprint.artifacts)
    return result


def validate_sprint_coverage() -> None:
    """Assert that every ArtifactType is covered by exactly one sprint."""
    from maestro.sdlc.schemas import ArtifactType as AT

    covered = all_sprint_artifacts()
    all_types = set(AT)
    missing = all_types - covered
    if missing:
        raise ValueError(f"ArtifactTypes not covered by any sprint: {missing}")
    extra = covered - all_types
    if extra:
        raise ValueError(f"Sprint artifacts not in ArtifactType: {extra}")
```

**Verification:** Run `python -c "from maestro.sdlc.sprints import SPRINTS; print(len(SPRINTS))"` — prints `6`.

---

## `[ ]` Microtask 2.2 — Create `tests/test_sdlc_sprints.py`

**File:** `tests/test_sdlc_sprints.py` (create new)

**Pre-condition:** Microtask 2.1 must be applied.

**Action:** Create the file with the following exact content:

```python
"""Tests for maestro/sdlc/sprints.py — sprint DAG topology and parallel groups."""
import pytest

from maestro.sdlc.schemas import ArtifactType
from maestro.sdlc.sprints import (
    SPRINTS,
    SprintDef,
    all_sprint_artifacts,
    get_ready_artifacts,
    validate_sprint_coverage,
)


def test_sprints_has_6_entries() -> None:
    assert len(SPRINTS) == 6


def test_sprint_ids_sequential() -> None:
    assert [s.sprint_id for s in SPRINTS] == [1, 2, 3, 4, 5, 6]


def test_all_artifact_types_covered() -> None:
    validate_sprint_coverage()


def test_no_duplicate_artifacts_across_sprints() -> None:
    seen: set[ArtifactType] = set()
    for sprint in SPRINTS:
        for artifact in sprint.artifacts:
            assert artifact not in seen, f"Artifact {artifact} in multiple sprints"
            seen.add(artifact)
    assert seen == set(ArtifactType)


def test_sprint_1_briefing_first() -> None:
    s1 = SPRINTS[0]
    assert ArtifactType.BRIEFING in s1.artifacts
    waves = get_ready_artifacts(s1, completed=set())
    assert waves[0] == [ArtifactType.BRIEFING]


def test_sprint_1_parallel_after_briefing() -> None:
    s1 = SPRINTS[0]
    waves = get_ready_artifacts(s1, completed=set())
    assert len(waves) == 2
    assert set(waves[1]) == {ArtifactType.HYPOTHESES, ArtifactType.GAPS}


def test_sprint_3_four_artifacts() -> None:
    s3 = SPRINTS[2]
    assert len(s3.artifacts) == 4
    assert ArtifactType.NFR in s3.artifacts


def test_sprint_5_auth_before_data_and_api() -> None:
    s5 = SPRINTS[4]
    prior = {ArtifactType.FUNCTIONAL_SPEC, ArtifactType.BUSINESS_RULES, ArtifactType.UX_SPEC, ArtifactType.ADRS, ArtifactType.NFR}
    waves = get_ready_artifacts(s5, completed=set(prior))
    first_wave_types = set(waves[0])
    assert ArtifactType.AUTH_MATRIX in first_wave_types
    assert ArtifactType.DATA_MODEL not in first_wave_types
    assert ArtifactType.API_CONTRACTS not in first_wave_types


def test_sprint_6_sequential() -> None:
    s6 = SPRINTS[5]
    prior = {ArtifactType.PRD, ArtifactType.FUNCTIONAL_SPEC, ArtifactType.BUSINESS_RULES, ArtifactType.UX_SPEC, ArtifactType.API_CONTRACTS, ArtifactType.AUTH_MATRIX, ArtifactType.ADRS, ArtifactType.NFR}
    waves = get_ready_artifacts(s6, completed=set(prior))
    assert waves[0] == [ArtifactType.ACCEPTANCE_CRITERIA]
    assert waves[1] == [ArtifactType.TEST_PLAN]


def test_all_sprint_artifacts_returns_14() -> None:
    assert len(all_sprint_artifacts()) == 14


# ---------------------------------------------------------------------------
# Matrix conformance — pinned to docs/Matriz_formal_de_dependência_v2.md
# ---------------------------------------------------------------------------
EXPECTED_DEPS: dict[ArtifactType, set[ArtifactType]] = {
    ArtifactType.BRIEFING: set(),
    ArtifactType.HYPOTHESES: {ArtifactType.BRIEFING},
    ArtifactType.GAPS: {ArtifactType.BRIEFING},
    ArtifactType.PRD: {ArtifactType.BRIEFING, ArtifactType.HYPOTHESES, ArtifactType.GAPS},
    ArtifactType.FUNCTIONAL_SPEC: {ArtifactType.PRD},
    ArtifactType.BUSINESS_RULES: {ArtifactType.PRD, ArtifactType.FUNCTIONAL_SPEC},
    ArtifactType.NFR: {ArtifactType.PRD},
    ArtifactType.ADRS: {ArtifactType.PRD},
    ArtifactType.UX_SPEC: {ArtifactType.PRD, ArtifactType.FUNCTIONAL_SPEC},
    ArtifactType.AUTH_MATRIX: {
        ArtifactType.FUNCTIONAL_SPEC,
        ArtifactType.BUSINESS_RULES,
        ArtifactType.UX_SPEC,
    },
    ArtifactType.DATA_MODEL: {
        ArtifactType.FUNCTIONAL_SPEC,
        ArtifactType.BUSINESS_RULES,
        ArtifactType.AUTH_MATRIX,
        ArtifactType.ADRS,
        ArtifactType.NFR,
    },
    ArtifactType.API_CONTRACTS: {
        ArtifactType.FUNCTIONAL_SPEC,
        ArtifactType.BUSINESS_RULES,
        ArtifactType.UX_SPEC,
        ArtifactType.AUTH_MATRIX,
        ArtifactType.ADRS,
        ArtifactType.NFR,
        ArtifactType.DATA_MODEL,
    },
    ArtifactType.ACCEPTANCE_CRITERIA: {
        ArtifactType.PRD,
        ArtifactType.FUNCTIONAL_SPEC,
        ArtifactType.BUSINESS_RULES,
        ArtifactType.UX_SPEC,
    },
    ArtifactType.TEST_PLAN: {
        ArtifactType.PRD,
        ArtifactType.FUNCTIONAL_SPEC,
        ArtifactType.BUSINESS_RULES,
        ArtifactType.ACCEPTANCE_CRITERIA,
        ArtifactType.UX_SPEC,
        ArtifactType.API_CONTRACTS,
        ArtifactType.AUTH_MATRIX,
        ArtifactType.ADRS,
        ArtifactType.NFR,
    },
}


@pytest.mark.parametrize("artifact,expected", list(EXPECTED_DEPS.items()))
def test_sprint_deps_match_formal_matrix(
    artifact: ArtifactType, expected: set[ArtifactType]
) -> None:
    """Every SprintDef.deps entry must match docs/Matriz_formal_de_dependência_v2.md."""
    actual: set[ArtifactType] = set()
    for sprint in SPRINTS:
        if artifact in sprint.deps:
            actual = set(sprint.deps[artifact])
            break
    assert actual == expected, (
        f"{artifact.value}: matrix expects {expected}, sprints.py declares {actual}"
    )
```

**Verification:** Run `pytest tests/test_sdlc_sprints.py -v` — ALL PASS.

---

## `[ ]` Microtask 2.3 — Add GateResult and SprintResult Dataclasses to schemas.py

**File:** `maestro/sdlc/schemas.py`

**Pre-condition:** `DiscoveryResult` dataclass exists in `schemas.py`.

**Action:**

1. Add `field` to the existing `from dataclasses import dataclass` import (if not already there):
```python
from dataclasses import dataclass, field
```

2. Add the following two dataclasses at the end of `maestro/sdlc/schemas.py`, after `DiscoveryResult`:

```python
@dataclass
class GateResult:
    """Result of a sprint gate review."""

    sprint_id: int
    passed: bool
    notes: str = ""
    issues: list[str] = field(default_factory=list)


@dataclass
class SprintResult:
    """Result of a single sprint execution."""

    sprint_id: int
    name: str
    artifacts: list[SDLCArtifact] = field(default_factory=list)
    gate: GateResult | None = None
```

**Verification:** Run `python -c "from maestro.sdlc.schemas import GateResult, SprintResult; print('OK')"` — prints `OK`.

---

## `[ ]` Microtask 2.4 — Add GateResult/SprintResult Tests to test_sdlc_schemas.py

**File:** `tests/test_sdlc_schemas.py`

**Pre-condition:** Microtask 2.3 must be applied.

**Action:** Add the following imports and tests to `tests/test_sdlc_schemas.py`:

Add to the imports at the top of the file:
```python
from maestro.sdlc.schemas import GateResult, SprintResult
```

Add the following test functions at the end of the file:
```python
def test_gate_result_dataclass() -> None:
    gate = GateResult(sprint_id=1, passed=True, notes="All artifacts approved")
    assert gate.passed is True
    assert gate.sprint_id == 1


def test_gate_result_defaults() -> None:
    gate = GateResult(sprint_id=2, passed=False)
    assert gate.notes == ""
    assert gate.issues == []


def test_sprint_result_dataclass() -> None:
    sprint = SprintResult(
        sprint_id=1,
        name="Descoberta",
        artifacts=[
            SDLCArtifact(ArtifactType.BRIEFING, "01-briefing.md", "# Briefing"),
        ],
        gate=GateResult(sprint_id=1, passed=True),
    )
    assert sprint.sprint_id == 1
    assert len(sprint.artifacts) == 1
    assert sprint.gate.passed is True


def test_sprint_result_optional_gate() -> None:
    sprint = SprintResult(
        sprint_id=1,
        name="Descoberta",
        artifacts=[],
    )
    assert sprint.gate is None
```

**Verification:** Run `pytest tests/test_sdlc_schemas.py -v` — ALL PASS.

---

## `[ ]` Microtask 2.5 — Commit Wave 2

**Pre-condition:** All of `tests/test_sdlc_schemas.py` and `tests/test_sdlc_sprints.py` pass.

**Action:**
```bash
git add maestro/sdlc/sprints.py maestro/sdlc/schemas.py \
        tests/test_sdlc_sprints.py tests/test_sdlc_schemas.py
git commit -m "feat(sdlc): add sprint DAG module (6 sprints) and GateResult/SprintResult dataclasses"
```

**Verification:** `git status` shows clean working tree.
