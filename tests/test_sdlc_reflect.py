"""Tests for maestro/sdlc/reflect.py — ReflectLoop and ReflectReport."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from maestro.sdlc.reflect import ReflectLoop, TARGET_MEAN
from maestro.sdlc.schemas import ReflectCycle, ReflectDimensionScore, ReflectReport


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DIMENSIONS = [
    "Cobertura de domínio",
    "Consistência de nomenclatura",
    "Alinhamento modelo ↔ API",
    "Cobertura de RN em ACs",
    "Coerência PRD ↔ técnico",
    "Qualidade dos ADRs",
    "Plano de testes vs. escopo",
    "Qualidade individual",
    "Rastreabilidade (gaps → decisões)",
    "Integridade dos artefatos",
]


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
