"""Tests for maestro/sdlc/writer.py — artifact persistence."""
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from maestro.sdlc.schemas import (
    ARTIFACT_FILENAMES,
    ArtifactType,
    DiscoveryResult,
    SDLCArtifact,
    SDLCRequest,
)
from maestro.sdlc.writer import prepare_spec_dir, write_artifacts


def _make_result(spec_dir: str) -> DiscoveryResult:
    request = SDLCRequest("Build X")
    artifacts = [
        SDLCArtifact(t, ARTIFACT_FILENAMES[t], f"# {t.value}")
        for t in ArtifactType
    ]
    return DiscoveryResult(request=request, artifacts=artifacts, spec_dir=spec_dir)


def test_write_artifacts_creates_spec_dir(tmp_path: Path) -> None:
    spec_dir = tmp_path / "spec"
    result = _make_result(str(spec_dir))
    write_artifacts(result)
    assert spec_dir.is_dir()


def test_write_artifacts_writes_all_files(tmp_path: Path) -> None:
    spec_dir = tmp_path / "spec"
    result = _make_result(str(spec_dir))
    write_artifacts(result)
    written = list(spec_dir.glob("*.md"))
    assert len(written) == 13


def test_write_artifacts_content_correct(tmp_path: Path) -> None:
    spec_dir = tmp_path / "spec"
    result = _make_result(str(spec_dir))
    write_artifacts(result)
    briefing_file = spec_dir / ARTIFACT_FILENAMES[ArtifactType.BRIEFING]
    assert briefing_file.read_text(encoding="utf-8") == f"# {ArtifactType.BRIEFING.value}"


def test_write_artifacts_filenames_match_schema(tmp_path: Path) -> None:
    spec_dir = tmp_path / "spec"
    result = _make_result(str(spec_dir))
    write_artifacts(result)
    written_names = {f.name for f in spec_dir.glob("*.md")}
    assert written_names == set(ARTIFACT_FILENAMES.values())


def test_prepare_spec_dir_returns_path(tmp_path: Path) -> None:
    result = prepare_spec_dir(str(tmp_path))
    assert isinstance(result, Path)
    assert result.name == "spec"
    assert result.is_dir()


def test_write_artifacts_raises_on_permission_error(tmp_path: Path) -> None:
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    result = _make_result(str(spec_dir))
    with patch("pathlib.Path.write_text", side_effect=PermissionError(13, "Permission denied")):
        with pytest.raises(RuntimeError, match="Failed to write artifacts"):
            write_artifacts(result)
