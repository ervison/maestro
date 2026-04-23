"""Tests for maestro/sdlc/harness.py — DiscoveryHarness orchestrator."""
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maestro.sdlc.harness import DiscoveryHarness
from maestro.sdlc.schemas import (
    ARTIFACT_FILENAMES,
    ARTIFACT_ORDER,
    ArtifactType,
    DiscoveryResult,
    SDLCRequest,
)


def test_harness_instantiation() -> None:
    harness = DiscoveryHarness()
    assert harness is not None


def test_harness_run_returns_discovery_result(tmp_path: Path) -> None:
    harness = DiscoveryHarness(workdir=str(tmp_path))
    result = harness.run(SDLCRequest("Build X", workdir=str(tmp_path)))
    assert isinstance(result, DiscoveryResult)


def test_harness_run_produces_13_artifacts(tmp_path: Path) -> None:
    harness = DiscoveryHarness(workdir=str(tmp_path))
    result = harness.run(SDLCRequest("Build X", workdir=str(tmp_path)))
    assert result.artifact_count == 13


def test_harness_creates_spec_directory(tmp_path: Path) -> None:
    harness = DiscoveryHarness(workdir=str(tmp_path))
    harness.run(SDLCRequest("Build X", workdir=str(tmp_path)))
    assert (tmp_path / "spec").is_dir()


def test_harness_writes_13_files(tmp_path: Path) -> None:
    harness = DiscoveryHarness(workdir=str(tmp_path))
    harness.run(SDLCRequest("Build X", workdir=str(tmp_path)))
    written = list((tmp_path / "spec").glob("*.md"))
    assert len(written) == 13


def test_harness_artifact_filenames_match_schema(tmp_path: Path) -> None:
    harness = DiscoveryHarness(workdir=str(tmp_path))
    result = harness.run(SDLCRequest("Build X", workdir=str(tmp_path)))
    expected = set(ARTIFACT_FILENAMES.values())
    actual = {a.filename for a in result.artifacts}
    assert actual == expected


def test_harness_run_respects_workdir(tmp_path: Path) -> None:
    subdir = tmp_path / "project"
    subdir.mkdir()
    harness = DiscoveryHarness(workdir=str(subdir))
    result = harness.run(SDLCRequest("Build X", workdir=str(subdir)))
    assert result.spec_dir.startswith(str(subdir))
    assert (subdir / "spec").is_dir()


def test_harness_brownfield_false_does_not_scan(tmp_path: Path) -> None:
    harness = DiscoveryHarness(workdir=str(tmp_path))
    with patch.object(harness, "_scan_codebase") as mock_scan:
        harness.run(SDLCRequest("Build X", workdir=str(tmp_path), brownfield=False))
    mock_scan.assert_not_called()


def test_harness_brownfield_true_appends_codebase_context(tmp_path: Path) -> None:
    harness = DiscoveryHarness(workdir=str(tmp_path))
    captured_prompts: list[str] = []

    original_gen = harness._generate_artifact

    async def capturing_gen(req, artifact_type):
        captured_prompts.append(req.prompt)
        return await original_gen(req, artifact_type)

    harness._generate_artifact = capturing_gen
    harness.run(SDLCRequest("Build X", workdir=str(tmp_path), brownfield=True))

    assert captured_prompts, "No artifacts generated"
    assert "## Existing Codebase" in captured_prompts[0]


def test_harness_writes_each_artifact_incrementally(tmp_path: Path) -> None:
    """Each artifact must be written to disk as soon as it is generated, not all at the end."""
    harness = DiscoveryHarness(workdir=str(tmp_path))
    spec_dir = tmp_path / "spec"
    written_counts: list[int] = []

    original_gen = harness._generate_artifact

    async def counting_gen(req, artifact_type):
        artifact = await original_gen(req, artifact_type)
        # Count how many files exist on disk right after this artifact is generated
        # (the write happens inside arun, right after _generate_artifact returns)
        return artifact

    harness._generate_artifact = counting_gen

    # Patch write_artifact to record counts per call
    from maestro.sdlc import writer as writer_mod
    original_write = writer_mod.write_artifact

    def recording_write(sd, artifact):
        original_write(sd, artifact)
        written_counts.append(len(list(spec_dir.glob("*.md"))))

    with patch.object(writer_mod, "write_artifact", side_effect=recording_write):
        harness.run(SDLCRequest("Build X", workdir=str(tmp_path)))

    # Should have 13 write calls, one per artifact
    assert len(written_counts) == 13
    # Each write call should have produced exactly one more file than the previous
    for i, count in enumerate(written_counts, start=1):
        assert count == i, f"Expected {i} files after artifact {i}, got {count}"


def test_harness_resolves_gaps_and_enriches_prompt(tmp_path: Path, monkeypatch) -> None:
    """Harness pauses at GAPS, resolves via mock server, enriches prompt."""
    import asyncio

    from maestro.sdlc.schemas import GapAnswer, SDLCArtifact

    del monkeypatch

    call_log: list[str] = []

    async def fake_generate(self_ref, request, artifact_type):
        del self_ref
        call_log.append(f"{artifact_type.value}:{request.prompt[-30:]}")
        content = "[GAP] Is SSO required?" if artifact_type == ArtifactType.GAPS else "# content"
        return SDLCArtifact(
            artifact_type=artifact_type,
            filename=ARTIFACT_FILENAMES[artifact_type],
            content=content,
        )

    mock_answers = [GapAnswer(question="Is SSO required?", selected_options=["Yes"])]

    with patch.object(DiscoveryHarness, "_generate_artifact", new=fake_generate):
        with patch("maestro.sdlc.harness.resolve_gaps", new=AsyncMock(return_value=mock_answers)) as mock_resolve:
            harness = DiscoveryHarness(provider=object(), model="test", open_browser=False)
            request = SDLCRequest(prompt="Build a CRM", workdir=str(tmp_path))
            result = asyncio.run(harness.arun(request))

    mock_resolve.assert_called_once()
    assert any("Is SSO required? → Yes" in entry for entry in call_log)
    assert result.artifact_count == len(ARTIFACT_ORDER)


def test_harness_post_gap_artifacts_use_resolved_prompt_rules(tmp_path: Path) -> None:
    import asyncio

    captured_prompt_by_type: dict[ArtifactType, str] = {}

    async def fake_generate(self_ref, request, artifact_type):
        del self_ref
        from maestro.sdlc.schemas import SDLCArtifact

        captured_prompt_by_type[artifact_type] = request.prompt
        content = "[GAP] Is SSO required?" if artifact_type == ArtifactType.GAPS else "# content"
        return SDLCArtifact(
            artifact_type=artifact_type,
            filename=ARTIFACT_FILENAMES[artifact_type],
            content=content,
        )

    from maestro.sdlc.schemas import GapAnswer

    with patch.object(DiscoveryHarness, "_generate_artifact", new=fake_generate):
        with patch(
            "maestro.sdlc.harness.resolve_gaps",
            new=AsyncMock(
                return_value=[GapAnswer(question="Is SSO required?", selected_options=["Yes"])]
            ),
        ):
            harness = DiscoveryHarness(provider=object(), model="test", open_browser=False)
            request = SDLCRequest(prompt="Build a CRM", workdir=str(tmp_path))
            asyncio.run(harness.arun(request))

    assert "## Gap Answers" in captured_prompt_by_type[ArtifactType.PRD]


def test_harness_reflect_disabled_produces_no_report(tmp_path: Path) -> None:
    """Stub mode (no provider) always produces reflect_report=None."""
    harness = DiscoveryHarness(workdir=str(tmp_path))  # no provider → stub mode
    result = harness.run(SDLCRequest("Build X", workdir=str(tmp_path)))
    assert result.reflect_report is None


def test_harness_raises_if_post_gap_artifact_has_open_markers(tmp_path: Path) -> None:
    """After GAPS are resolved, later artifacts must not keep [GAP]/[HYPOTHESIS]."""
    import asyncio

    from maestro.sdlc.schemas import SDLCArtifact

    async def fake_generate(self_ref, request, artifact_type):
        del self_ref, request
        if artifact_type == ArtifactType.PRD:
            content = "[HYPOTHESIS] still open"
        elif artifact_type == ArtifactType.GAPS:
            content = "[GAP] Is SSO required?"
        else:
            content = "# content"
        return SDLCArtifact(
            artifact_type=artifact_type,
            filename=ARTIFACT_FILENAMES[artifact_type],
            content=content,
        )

    with patch.object(DiscoveryHarness, "_generate_artifact", new=fake_generate):
        with patch("maestro.sdlc.harness.resolve_gaps", new=AsyncMock(return_value=[])):
            harness = DiscoveryHarness(provider=object(), model="test", open_browser=False)
            request = SDLCRequest(prompt="Build a CRM", workdir=str(tmp_path))
            with pytest.raises(RuntimeError, match=r"Unresolved \[GAP\]/\[HYPOTHESIS\]"):
                asyncio.run(harness.arun(request))


def test_harness_allows_inline_marker_mentions_after_gap_resolution(tmp_path: Path) -> None:
    """Inline mentions like '`[GAP]` marker' should not be treated as unresolved placeholders."""
    import asyncio

    from maestro.sdlc.schemas import SDLCArtifact

    async def fake_generate(self_ref, request, artifact_type):
        del self_ref, request
        if artifact_type == ArtifactType.GAPS:
            content = "[GAP] Is SSO required?"
        elif artifact_type == ArtifactType.PRD:
            content = "The questionnaire used `[GAP]` tags as metadata only."
        else:
            content = "# content"
        return SDLCArtifact(
            artifact_type=artifact_type,
            filename=ARTIFACT_FILENAMES[artifact_type],
            content=content,
        )

    with patch.object(DiscoveryHarness, "_generate_artifact", new=fake_generate):
        with patch("maestro.sdlc.harness.resolve_gaps", new=AsyncMock(return_value=[])):
            harness = DiscoveryHarness(provider=object(), model="test", open_browser=False)
            request = SDLCRequest(prompt="Build a CRM", workdir=str(tmp_path))
            result = asyncio.run(harness.arun(request))

    assert result.artifact_count == len(ARTIFACT_ORDER)


def test_harness_deduplicates_repeated_artifact_content(tmp_path: Path) -> None:
    import asyncio

    from maestro.sdlc.schemas import SDLCArtifact

    repeated = "# PRD\n\nLinha A\nLinha B"

    async def fake_generate(self_ref, request, artifact_type):
        del self_ref, request
        if artifact_type == ArtifactType.GAPS:
            content = "[GAP] Is SSO required?"
        elif artifact_type == ArtifactType.PRD:
            content = repeated + repeated
        else:
            content = "# content"
        return SDLCArtifact(
            artifact_type=artifact_type,
            filename=ARTIFACT_FILENAMES[artifact_type],
            content=content,
        )

    with patch.object(DiscoveryHarness, "_generate_artifact", new=fake_generate):
        with patch("maestro.sdlc.harness.resolve_gaps", new=AsyncMock(return_value=[])):
            harness = DiscoveryHarness(provider=object(), model="test", open_browser=False)
            request = SDLCRequest(prompt="Build a CRM", workdir=str(tmp_path))
            result = asyncio.run(harness.arun(request))

    prd = next(artifact for artifact in result.artifacts if artifact.artifact_type == ArtifactType.PRD)
    assert prd.content == repeated
