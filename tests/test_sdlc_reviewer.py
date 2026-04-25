"""Tests for maestro/sdlc/reviewer.py — gate validation."""
from __future__ import annotations

import json

import pytest

from maestro.sdlc.reviewer import Reviewer
from maestro.sdlc.schemas import ArtifactType, GateResult, SDLCArtifact


class FakeReviewerProvider:
    def __init__(self, response: str) -> None:
        self._response = response

    async def stream(self, messages, tools, model):
        yield self._response


@pytest.mark.asyncio
async def test_reviewer_passes_valid_artifacts() -> None:
    response = json.dumps({"passed": True, "notes": "All good", "issues": []})
    provider = FakeReviewerProvider(response)
    reviewer = Reviewer()

    artifacts = [
        SDLCArtifact(ArtifactType.BRIEFING, "01-briefing.md", "# Briefing\nContent"),
        SDLCArtifact(ArtifactType.HYPOTHESES, "02-hypotheses.md", "# Hypotheses"),
        SDLCArtifact(ArtifactType.GAPS, "03-gaps.md", "# Gaps"),
    ]

    result = await reviewer.review(provider, None, sprint_id=1, artifacts=artifacts)
    assert isinstance(result, GateResult)
    assert result.passed is True
    assert result.sprint_id == 1
    assert result.issues == []


@pytest.mark.asyncio
async def test_reviewer_fails_with_issues() -> None:
    response = json.dumps({
        "passed": False,
        "notes": "Incomplete",
        "issues": ["Briefing missing stakeholders", "Gaps not actionable"],
    })
    provider = FakeReviewerProvider(response)
    reviewer = Reviewer()

    artifacts = [
        SDLCArtifact(ArtifactType.BRIEFING, "01-briefing.md", "# Briefing"),
    ]

    result = await reviewer.review(provider, None, sprint_id=1, artifacts=artifacts)
    assert result.passed is False
    assert len(result.issues) == 2


@pytest.mark.asyncio
async def test_reviewer_handles_malformed_json() -> None:
    provider = FakeReviewerProvider("not valid json at all")
    reviewer = Reviewer()

    artifacts = [
        SDLCArtifact(ArtifactType.PRD, "04-prd.md", "# PRD"),
    ]

    result = await reviewer.review(provider, None, sprint_id=2, artifacts=artifacts)
    assert result.passed is False
    assert "Malformed reviewer response" in result.notes


@pytest.mark.asyncio
async def test_reviewer_uses_prior_artifacts() -> None:
    response = json.dumps({"passed": True, "notes": "Consistent", "issues": []})
    provider = FakeReviewerProvider(response)
    reviewer = Reviewer()

    prior = [
        SDLCArtifact(ArtifactType.BRIEFING, "01-briefing.md", "# Briefing"),
    ]
    artifacts = [
        SDLCArtifact(ArtifactType.PRD, "04-prd.md", "# PRD"),
    ]

    result = await reviewer.review(provider, None, sprint_id=2, artifacts=artifacts, prior_artifacts=prior)
    assert result.passed is True


@pytest.mark.asyncio
async def test_reviewer_json_in_fence_is_parsed() -> None:
    """Verify that JSON wrapped in ```json ... ``` fences is correctly extracted."""
    payload = {"passed": True, "notes": "fence-wrapped", "issues": []}
    response = f"```json\n{json.dumps(payload)}\n```"
    provider = FakeReviewerProvider(response)
    reviewer = Reviewer()

    artifacts = [SDLCArtifact(ArtifactType.BRIEFING, "01-briefing.md", "# B")]
    result = await reviewer.review(provider, None, sprint_id=1, artifacts=artifacts)
    assert result.passed is True
    assert result.notes == "fence-wrapped"


@pytest.mark.asyncio
async def test_reviewer_sprint_id_6_has_prompt() -> None:
    """Verify that gate prompt 6 (validation) is used and present."""
    from maestro.sdlc.reviewer import GATE_PROMPTS
    assert 6 in GATE_PROMPTS
    assert "QA" in GATE_PROMPTS[6] or "test" in GATE_PROMPTS[6].lower()
