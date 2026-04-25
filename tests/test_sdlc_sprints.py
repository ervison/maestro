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
