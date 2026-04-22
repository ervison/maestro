"""SDLC Discovery Planner — schema contracts and artifact type system."""
from __future__ import annotations

import enum
from dataclasses import dataclass, field


class ArtifactType(enum.Enum):
    """The 13 SDLC artifact types produced by the discovery planner."""

    BRIEFING = "briefing"
    HYPOTHESES = "hypotheses"
    GAPS = "gaps"
    PRD = "prd"
    FUNCTIONAL_SPEC = "functional_spec"
    BUSINESS_RULES = "business_rules"
    ACCEPTANCE_CRITERIA = "acceptance_criteria"
    UX_SPEC = "ux_spec"
    API_CONTRACTS = "api_contracts"
    DATA_MODEL = "data_model"
    AUTH_MATRIX = "auth_matrix"
    ADRS = "adrs"
    TEST_PLAN = "test_plan"


ARTIFACT_FILENAMES: dict[ArtifactType, str] = {
    ArtifactType.BRIEFING: "01-briefing.md",
    ArtifactType.HYPOTHESES: "02-hypotheses.md",
    ArtifactType.GAPS: "03-gaps.md",
    ArtifactType.PRD: "04-prd.md",
    ArtifactType.FUNCTIONAL_SPEC: "05-functional-spec.md",
    ArtifactType.BUSINESS_RULES: "06-business-rules.md",
    ArtifactType.ACCEPTANCE_CRITERIA: "07-acceptance-criteria.md",
    ArtifactType.UX_SPEC: "08-ux-spec.md",
    ArtifactType.API_CONTRACTS: "09-api-contracts.md",
    ArtifactType.DATA_MODEL: "10-data-model.md",
    ArtifactType.AUTH_MATRIX: "11-auth-matrix.md",
    ArtifactType.ADRS: "12-adrs.md",
    ArtifactType.TEST_PLAN: "13-test-plan.md",
}

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
]


@dataclass
class SDLCRequest:
    """A discovery request from the user."""

    prompt: str
    language: str | None = None
    brownfield: bool = False
    workdir: str = "."

    def __post_init__(self) -> None:
        self.prompt = self.prompt.strip()
        if not self.prompt:
            raise ValueError("prompt cannot be empty")


@dataclass
class SDLCArtifact:
    """A single generated SDLC artifact."""

    artifact_type: ArtifactType
    filename: str
    content: str


@dataclass
class DiscoveryResult:
    """The completed result of a discovery run."""

    request: SDLCRequest
    artifacts: list[SDLCArtifact] = field(default_factory=list)
    spec_dir: str = ""

    @property
    def artifact_count(self) -> int:
        return len(self.artifacts)
