"""Tests for maestro/sdlc/reviewer.py — gate validation."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from maestro.sdlc.reviewer import Reviewer, _extract_code_fences, _extract_json
from maestro.sdlc.schemas import ArtifactType, GateResult, SDLCArtifact

from test_sdlc_sprints import *  # noqa: F401,F403


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
async def test_reviewer_prefers_last_json_fence() -> None:
    first = {"passed": False, "notes": "wrong", "issues": ["wrong fence"]}
    second = {"passed": True, "notes": "last fence", "issues": []}
    response = (
        f"```json\n{json.dumps(first)}\n```\n"
        f"some prose\n"
        f"```json\n{json.dumps(second)}\n```"
    )
    provider = FakeReviewerProvider(response)
    reviewer = Reviewer()

    artifacts = [SDLCArtifact(ArtifactType.BRIEFING, "01-briefing.md", "# B")]
    result = await reviewer.review(provider, None, sprint_id=1, artifacts=artifacts)

    assert result.passed is True
    assert result.notes == "last fence"


@pytest.mark.asyncio
async def test_reviewer_sprint_id_6_has_prompt() -> None:
    """Verify that gate prompt 6 (validation) is used and present."""
    from maestro.sdlc.reviewer import GATE_PROMPTS
    assert 6 in GATE_PROMPTS
    assert "QA" in GATE_PROMPTS[6] or "test" in GATE_PROMPTS[6].lower()


def test_extract_code_fences_stops_when_opening_fence_has_no_body() -> None:
    assert _extract_code_fences("```json") == []


def test_extract_code_fences_stops_when_closing_fence_missing() -> None:
    assert _extract_code_fences("```json\n{}") == []


def test_extract_json_falls_back_to_last_non_json_fence() -> None:
    payload = {"passed": False, "notes": "plain fence", "issues": ["x"]}

    result = _extract_json(f"```text\n{json.dumps(payload)}\n```")

    assert result == payload


@pytest.mark.asyncio
async def test_reviewer_prefers_final_assistant_message_object() -> None:
    class Provider:
        async def stream(self, messages, tools, model):
            del messages, tools, model
            yield "partial"
            yield SimpleNamespace(role="assistant", content=json.dumps({"passed": True, "notes": "final", "issues": []}))

    reviewer = Reviewer()

    result = await reviewer.review(
        Provider(),
        None,
        sprint_id=1,
        artifacts=[SDLCArtifact(ArtifactType.BRIEFING, "01-briefing.md", "# B")],
    )

    assert result.passed is True
    assert result.notes == "final"


def test_get_ready_artifacts_breaks_when_external_dependencies_not_completed() -> None:
    from maestro.sdlc.sprints import SprintDef, get_ready_artifacts

    sprint = SprintDef(
        sprint_id=99,
        name="custom",
        artifacts=(ArtifactType.PRD, ArtifactType.UX_SPEC),
        deps={
            ArtifactType.PRD: (),
            ArtifactType.UX_SPEC: (ArtifactType.BRIEFING,),
        },
    )

    assert get_ready_artifacts(sprint, completed=set()) == [[ArtifactType.PRD]]


def test_validate_sprint_coverage_reports_missing_artifact(monkeypatch: pytest.MonkeyPatch) -> None:
    from maestro.sdlc import sprints as sprints_mod
    original_all = sprints_mod.all_sprint_artifacts

    monkeypatch.setattr(
        sprints_mod,
        "all_sprint_artifacts",
        lambda: set(original_all()) - {ArtifactType.TEST_PLAN},
    )

    errors = sprints_mod.validate_sprint_coverage()

    assert any("ArtifactTypes not covered" in error for error in errors)


def test_validate_sprint_coverage_reports_extra_artifact(monkeypatch: pytest.MonkeyPatch) -> None:
    from maestro.sdlc import sprints as sprints_mod
    original_all = sprints_mod.all_sprint_artifacts

    monkeypatch.setattr(
        sprints_mod,
        "all_sprint_artifacts",
        lambda: set(original_all()) | {"unexpected"},
    )

    errors = sprints_mod.validate_sprint_coverage()

    assert any("Sprint artifacts not in ArtifactType" in error for error in errors)
