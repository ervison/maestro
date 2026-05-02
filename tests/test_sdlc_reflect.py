"""Tests for maestro/sdlc/reflect.py — ReflectLoop and ReflectReport."""
from __future__ import annotations

import json
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

import pytest

from maestro.sdlc.reflect import (
    DIMENSIONS,
    ReflectLoop,
    TARGET_MEAN,
    _extract_first_code_fence,
    _extract_json,
    run_reflect_loop,
)
from maestro.sdlc.schemas import ArtifactType, ReflectCycle, ReflectDimensionScore, ReflectReport, SDLCArtifact, SDLCRequest

from test_sdlc_generators import *  # noqa: F401,F403
from test_sdlc_writer import *  # noqa: F401,F403


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_scores(score_value: float) -> list[dict]:
    return [
        {"dimension": d, "score": score_value, "justification": "ok"}
        for d in DIMENSIONS
    ]


def _make_eval_response(score_value: float, problems=None) -> str:
    return json.dumps(
        {
            "scores": _make_scores(score_value),
            "problems": problems or [],
        }
    )


def _make_fix_response(patches: list[dict]) -> str:
    return json.dumps(patches)


class FakeProvider:
    """Provider that returns pre-set responses in order."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self._idx = 0

    async def stream(self, messages, tools, model):
        response = self._responses[self._idx % len(self._responses)]
        self._idx += 1
        # yield the response as a single assistant message chunk
        yield response


class SequenceProvider:
    def __init__(self, responses) -> None:
        self._responses = list(responses)

    async def stream(self, messages, tools, model):
        del messages, tools, model
        for response in self._responses:
            yield response


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_reflect_report_dataclass() -> None:
    """ReflectReport and ReflectCycle dataclasses are instantiable with correct fields."""
    score = ReflectDimensionScore(dimension="foo", score=8.5, justification="good")
    cycle = ReflectCycle(cycle=1, scores=[score], mean=8.5)
    report = ReflectReport(cycles=[cycle], final_mean=8.5, passed=True)

    assert report.passed is True
    assert report.final_mean == 8.5
    assert len(report.cycles) == 1
    assert report.cycles[0].mean == 8.5
    assert report.cycles[0].scores[0].dimension == "foo"


def test_extract_json_reads_first_fenced_block() -> None:
    payload = {"scores": [], "problems": []}

    result = _extract_json(f"prefix\n```json\n{json.dumps(payload)}\n```\nsuffix")

    assert result == payload


def test_extract_first_code_fence_requires_newline_after_fence() -> None:
    assert _extract_first_code_fence("```json") is None


def test_extract_first_code_fence_requires_closing_fence() -> None:
    assert _extract_first_code_fence("```json\n{}") is None


def test_reflect_dimensions_cover_sdlc_consistency_completeness_and_traceability() -> None:
    normalized = [dimension.casefold() for dimension in DIMENSIONS]

    assert len(DIMENSIONS) <= 8
    assert any("consist" in dimension for dimension in normalized)
    assert any("complet" in dimension or "corret" in dimension for dimension in normalized)
    assert any("rastreab" in dimension for dimension in normalized)


@pytest.mark.asyncio
async def test_reflect_loop_passes_when_scores_high(tmp_path: Path) -> None:
    """When mean >= 8.0 on first eval, loop stops with passed=True and 1 cycle."""
    # Write a dummy spec file
    (tmp_path / "01-briefing.md").write_text("# Briefing\nSome content.")

    provider = FakeProvider([_make_eval_response(9.0)])
    loop = ReflectLoop()
    report = await loop.run(provider=provider, model=None, spec_dir=tmp_path, max_cycles=5)

    assert report.passed is True
    assert len(report.cycles) == 1
    assert report.cycles[0].mean >= TARGET_MEAN


@pytest.mark.asyncio
async def test_reflect_loop_applies_patches(tmp_path: Path) -> None:
    """Low scores on cycle 1 trigger fix → high scores on cycle 2 → passed=True."""
    spec_file = tmp_path / "01-briefing.md"
    spec_file.write_text("# Briefing\nOriginal content here.")

    problems = [
        {"file": "01-briefing.md", "dimension": "Qualidade individual", "what_to_change": "improve"}
    ]
    patches = [
        {"file": "01-briefing.md", "old": "Original content here.", "new": "Improved content here."}
    ]

    # Cycle 1: low scores + problems; fix response with patches
    # Cycle 2: high scores → pass
    responses = [
        _make_eval_response(5.0, problems=problems),  # cycle 1 eval
        _make_fix_response(patches),                    # cycle 1 fix
        _make_eval_response(9.0),                       # cycle 2 eval
    ]

    provider = FakeProvider(responses)
    loop = ReflectLoop()
    report = await loop.run(provider=provider, model=None, spec_dir=tmp_path, max_cycles=5)

    assert report.passed is True
    assert len(report.cycles) == 2
    # Patch was applied to the file
    content = spec_file.read_text()
    assert "Improved content here." in content
    assert "Original content here." not in content


@pytest.mark.asyncio
async def test_reflect_loop_stops_at_max_cycles(tmp_path: Path) -> None:
    """When max_cycles is reached without passing, report.passed == False."""
    (tmp_path / "01-briefing.md").write_text("# Briefing\nContent.")

    # Always return low scores + empty patches — never reaches 8.0
    low_eval = _make_eval_response(4.0)
    empty_fix = _make_fix_response([])

    # For each cycle: one eval + one fix (except the last which has no fix)
    provider = FakeProvider([low_eval, empty_fix])
    loop = ReflectLoop()
    max_cycles = 3
    report = await loop.run(provider=provider, model=None, spec_dir=tmp_path, max_cycles=max_cycles)

    assert report.passed is False
    assert len(report.cycles) == max_cycles


@pytest.mark.asyncio
async def test_reflect_loop_uses_configurable_target_mean(tmp_path: Path) -> None:
    (tmp_path / "01-briefing.md").write_text("# Briefing\nSome content.")

    provider = FakeProvider([_make_eval_response(7.5)])
    loop = ReflectLoop(target_mean=7.0)
    report = await loop.run(provider=provider, model=None, spec_dir=tmp_path, max_cycles=2)

    assert report.passed is True
    assert report.cycles[0].mean == 7.5


def test_read_spec_files_skips_unreadable_markdown(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    good = tmp_path / "01-good.md"
    bad = tmp_path / "02-bad.md"
    good.write_text("good", encoding="utf-8")
    bad.write_text("bad", encoding="utf-8")

    original_read_text = Path.read_text

    def fake_read_text(self: Path, *args, **kwargs):
        if self.name == "02-bad.md":
            raise OSError("boom")
        return original_read_text(self, *args, **kwargs)

    loop = ReflectLoop()
    with patch.object(Path, "read_text", new=fake_read_text):
        result = loop._read_spec_files(tmp_path)

    assert result == {"01-good.md": "good"}
    assert "could not read 02-bad.md" in capsys.readouterr().err


def test_apply_patches_skips_malformed_patch(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    loop = ReflectLoop()

    applied = loop._apply_patches(tmp_path, [{"file": "", "old": "x", "new": "y"}])

    assert applied == []
    assert "skipping malformed patch" in capsys.readouterr().err


def test_apply_patches_rejects_path_escape(tmp_path: Path) -> None:
    loop = ReflectLoop()

    with pytest.raises(RuntimeError, match="Patch target escapes spec_dir"):
        loop._apply_patches(tmp_path, [{"file": "../escape.md", "old": "x", "new": "y"}])


def test_apply_patches_skips_missing_target(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    loop = ReflectLoop()

    applied = loop._apply_patches(tmp_path, [{"file": "missing.md", "old": "x", "new": "y"}])

    assert applied == []
    assert "patch target not found" in capsys.readouterr().err


def test_apply_patches_skips_when_old_text_missing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    loop = ReflectLoop()
    target = tmp_path / "01-briefing.md"
    target.write_text("original", encoding="utf-8")

    applied = loop._apply_patches(
        tmp_path,
        [{"file": "01-briefing.md", "old": "not-there", "new": "replacement"}],
    )

    assert applied == []
    assert "patch 'old' string not found" in capsys.readouterr().err


@pytest.mark.asyncio
async def test_do_eval_cycle_returns_none_on_malformed_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    del tmp_path
    loop = ReflectLoop()

    result = await loop._do_eval_cycle(FakeProvider(["not json"]), None, {"01.md": "x"}, 1)

    assert result is None
    assert "malformed eval JSON" in capsys.readouterr().err


@pytest.mark.asyncio
async def test_do_eval_cycle_ignores_invalid_score_entries() -> None:
    payload = json.dumps(
        {
            "scores": [
                {"dimension": "valid", "score": 7, "justification": "ok"},
                {"dimension": "invalid", "score": None},
            ],
            "problems": [],
        }
    )
    loop = ReflectLoop()

    scores, problems = await loop._do_eval_cycle(FakeProvider([payload]), None, {"01.md": "x"}, 1)

    assert [score.dimension for score in scores] == ["valid"]
    assert problems == []


@pytest.mark.asyncio
async def test_do_fix_cycle_returns_empty_on_non_list_json(capsys: pytest.CaptureFixture[str]) -> None:
    loop = ReflectLoop()

    result = await loop._do_fix_cycle(
        FakeProvider([json.dumps({"file": "x"})]),
        None,
        {"01.md": "x"},
        [{"file": "01.md", "dimension": "d", "what_to_change": "w"}],
        Path("."),
        1,
        2,
    )

    assert result == []
    assert "malformed fix JSON" in capsys.readouterr().err


@pytest.mark.asyncio
async def test_call_provider_prefers_final_assistant_message_object() -> None:
    loop = ReflectLoop()
    provider = SequenceProvider(["partial", SimpleNamespace(role="assistant", content="final")])

    result = await loop._call_provider(provider, None, "prompt")

    assert result == "final"


@pytest.mark.asyncio
async def test_reflect_loop_records_zero_mean_cycle_after_eval_failure(tmp_path: Path) -> None:
    (tmp_path / "01-briefing.md").write_text("# Briefing", encoding="utf-8")

    report = await ReflectLoop().run(
        provider=FakeProvider(["not json", _make_eval_response(9.0)]),
        model=None,
        spec_dir=tmp_path,
        max_cycles=2,
    )

    assert [cycle.mean for cycle in report.cycles] == [0.0, 9.0]
    assert report.passed is True


@pytest.mark.asyncio
async def test_run_reflect_loop_convenience_wrapper(tmp_path: Path) -> None:
    (tmp_path / "01-briefing.md").write_text("# Briefing", encoding="utf-8")

    report = await run_reflect_loop(
        provider=FakeProvider([_make_eval_response(8.5)]),
        model=None,
        spec_dir=tmp_path,
        max_cycles=1,
        target_mean=8.0,
    )

    assert report.passed is True


def test_build_user_message_includes_prior_artifacts() -> None:
    from maestro.sdlc.generators import _build_user_message

    request = SDLCRequest("Base prompt")
    prior = [SDLCArtifact(ArtifactType.BRIEFING, "01-briefing.md", "brief")]

    message = _build_user_message(request, prior)

    assert "## Prior Artifacts" in message
    assert "01-briefing.md" in message


def test_build_user_message_without_prior_artifacts_returns_prompt() -> None:
    from maestro.sdlc.generators import _build_user_message

    request = SDLCRequest("Base prompt")

    assert _build_user_message(request, None) == "Base prompt"


@pytest.mark.asyncio
async def test_stream_artifact_content_prefers_final_assistant_message_and_object() -> None:
    from maestro.providers.base import Message
    from maestro.sdlc.generators import _stream_artifact_content

    provider = SequenceProvider([
        "chunk-1",
        Message(role="assistant", content="final-a"),
        SimpleNamespace(role="assistant", content="final-b"),
    ])

    result = await _stream_artifact_content(provider, [], None)

    assert result == "final-b"


@pytest.mark.asyncio
async def test_generate_artifact_raises_non_retryable_runtime_error() -> None:
    from maestro.sdlc.generators import generate_artifact

    class ExplodingProvider:
        async def stream(self, messages, tools, model):
            del messages, tools, model
            raise RuntimeError("totally different failure")
            yield

    with pytest.raises(RuntimeError, match="totally different failure"):
        await generate_artifact(
            ExplodingProvider(),
            None,
            SDLCRequest("Build X"),
            ArtifactType.PRD,
        )


def test_write_artifact_raises_runtime_error_on_os_error(tmp_path: Path) -> None:
    from maestro.sdlc.writer import write_artifact

    artifact = SDLCArtifact(ArtifactType.BRIEFING, "01-briefing.md", "content")

    with patch("pathlib.Path.write_text", side_effect=PermissionError(13, "Permission denied")):
        with pytest.raises(RuntimeError, match="Failed to write artifact 01-briefing.md"):
            write_artifact(tmp_path / "spec", artifact)
