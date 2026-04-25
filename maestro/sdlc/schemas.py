"""SDLC Discovery Planner — schema contracts and artifact type system."""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Literal


class ArtifactType(enum.Enum):
    """The 14 SDLC artifact types produced by the discovery planner."""

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
    NFR = "nfr"


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
    ArtifactType.NFR: "14-nfr.md",
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
    ArtifactType.NFR,
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
class ReflectDimensionScore:
    """Score for a single evaluation dimension."""

    dimension: str
    score: float
    justification: str


@dataclass
class ReflectCorrection:
    """A single correction applied during a reflect cycle."""

    cycle: int
    file: str
    dimension: str
    description: str


@dataclass
class ReflectCycle:
    """Results of a single reflect cycle (evaluation + corrections)."""

    cycle: int
    scores: list[ReflectDimensionScore] = field(default_factory=list)
    mean: float = 0.0
    corrections: list[ReflectCorrection] = field(default_factory=list)


@dataclass
class ReflectReport:
    """Full report from the reflect loop."""

    cycles: list[ReflectCycle] = field(default_factory=list)
    final_mean: float = 0.0
    passed: bool = False


@dataclass
class DiscoveryResult:
    """The completed result of a discovery run."""

    request: SDLCRequest
    artifacts: list[SDLCArtifact] = field(default_factory=list)
    spec_dir: str = ""
    reflect_report: ReflectReport | None = None

    @property
    def artifact_count(self) -> int:
        return len(self.artifacts)


@dataclass
class GapItem:
    """A single gap question with answer options and UI metadata."""

    question: str
    options: list[str]
    selection_mode: Literal["single", "multiple"] = "single"
    recommended_index: int = 0
    recommended_options: list[str] = field(default_factory=list)
    allow_free_text: bool = False
    free_text_placeholder: str = ""


@dataclass
class GapAnswer:
    """User's answer to a single gap question."""

    question: str
    selected_options: list[str]
    free_text: str = ""

    def __post_init__(self) -> None:
        if not self.selected_options:
            raise ValueError("selected_options must have at least one item")
