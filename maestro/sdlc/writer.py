"""Artifact writer — persists DiscoveryResult artifacts to the spec/ directory."""
from __future__ import annotations

from pathlib import Path

from maestro.sdlc.schemas import DiscoveryResult


def prepare_spec_dir(workdir: str) -> Path:
    """Create and return the spec/ directory under workdir."""
    spec_dir = Path(workdir).resolve() / "spec"
    spec_dir.mkdir(parents=True, exist_ok=True)
    return spec_dir


def write_artifacts(result: DiscoveryResult) -> None:
    """Write all artifacts in result to result.spec_dir."""
    spec_dir = Path(result.spec_dir).resolve()
    try:
        spec_dir.mkdir(parents=True, exist_ok=True)
        for artifact in result.artifacts:
            (spec_dir / artifact.filename).write_text(artifact.content, encoding="utf-8")
    except (OSError, PermissionError) as exc:
        raise RuntimeError(
            f"Failed to write artifacts to spec directory: {exc.strerror}"
        ) from exc
