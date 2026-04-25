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
