"""SDLC Discovery Harness — orchestrates 13-artifact specification generation."""
from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

from maestro.sdlc.gaps_server import resolve_gaps
from maestro.sdlc.schemas import (
    ArtifactType,
    ARTIFACT_FILENAMES,
    ARTIFACT_ORDER,
    DiscoveryResult,
    SDLCArtifact,
    SDLCRequest,
)


class DiscoveryHarness:
    """Orchestrates the 13-artifact SDLC discovery pipeline."""

    def __init__(
        self,
        provider=None,
        model: str | None = None,
        workdir: str = ".",
        gaps_port: int = 4041,
        open_browser: bool = True,
        reflect: bool = True,
        reflect_max_cycles: int = 5,
    ) -> None:
        self._provider = provider
        self._model = model
        self._workdir = workdir
        self._gaps_port = gaps_port
        self._open_browser = open_browser
        self.reflect = reflect
        self.reflect_max_cycles = reflect_max_cycles

    def run(self, request: SDLCRequest) -> DiscoveryResult:
        """Synchronous entry point — wraps async run."""
        return asyncio.run(self.arun(request))

    async def arun(self, request: SDLCRequest) -> DiscoveryResult:
        """Generate all 13 artifacts and write them to spec/."""
        # Brownfield: optionally enrich prompt with codebase scan
        effective_prompt = request.prompt
        if request.brownfield:
            scan = self._scan_codebase(request.workdir)
            effective_prompt = f"{request.prompt}\n\n## Existing Codebase\n{scan}"

        effective_request = SDLCRequest(
            prompt=effective_prompt,
            language=request.language,
            brownfield=request.brownfield,
            workdir=request.workdir,
        )

        workdir = request.workdir if request.workdir != "." else self._workdir
        spec_dir = Path(workdir).resolve() / "spec"
        try:
            spec_dir.mkdir(parents=True, exist_ok=True)
        except (OSError, PermissionError) as exc:
            raise RuntimeError(
                f"Failed to create spec directory: {exc.strerror}"
            ) from exc

        from maestro.sdlc.writer import write_artifact

        total = len(ARTIFACT_ORDER)
        artifacts: list[SDLCArtifact] = []
        gaps_index = ARTIFACT_ORDER.index(ArtifactType.GAPS)
        for i, artifact_type in enumerate(ARTIFACT_ORDER, start=1):
            print(
                f"[{i}/{total}] Generating {artifact_type.value}...",
                file=sys.stderr,
                flush=True,
            )
            artifact = await self._generate_artifact(effective_request, artifact_type)
            artifact = self._normalize_artifact(artifact)
            if self._provider is not None and i > gaps_index + 1:
                self._ensure_no_open_markers(artifact)
            artifacts.append(artifact)
            # Write immediately so progress is visible on disk
            write_artifact(spec_dir, artifact)
            if artifact_type == ArtifactType.GAPS and self._provider is not None:
                answers = await resolve_gaps(
                    artifact.content,
                    provider=self._provider,
                    model=self._model,
                    port=self._gaps_port,
                    open_browser=self._open_browser,
                )
                if answers:
                    answers_lines = []
                    for answer in answers:
                        opts_str = ", ".join(answer.selected_options)
                        line = f"- {answer.question} → {opts_str}"
                        if answer.free_text:
                            line += f" (note: {answer.free_text})"
                        answers_lines.append(line)
                    answers_text = "\n".join(answers_lines)
                    effective_request = SDLCRequest(
                        prompt=f"{effective_request.prompt}\n\n## Gap Answers\n{answers_text}",
                        language=effective_request.language,
                        brownfield=effective_request.brownfield,
                        workdir=effective_request.workdir,
                    )
            print(
                f"[{i}/{total}] ✓ {artifact.filename}",
                file=sys.stderr,
                flush=True,
            )

        result = DiscoveryResult(
            request=request,
            artifacts=artifacts,
            spec_dir=str(spec_dir),
        )

        # Reflect loop — iterative quality evaluation and correction
        if self._provider is not None and self.reflect and hasattr(self._provider, "stream"):
            from maestro.sdlc.reflect import ReflectLoop

            loop = ReflectLoop()
            reflect_report = await loop.run(
                provider=self._provider,
                model=self._model,
                spec_dir=spec_dir,
                max_cycles=self.reflect_max_cycles,
            )
            result = DiscoveryResult(
                request=request,
                artifacts=artifacts,
                spec_dir=str(spec_dir),
                reflect_report=reflect_report,
            )

        return result

    @staticmethod
    def _ensure_no_open_markers(artifact: SDLCArtifact) -> None:
        """Fail fast if post-gap artifacts still contain unresolved markers."""
        unresolved_marker = re.search(
            r"(?im)^\s*(?:[-*+]\s+|\d+\.\s+)?\[(?:GAP|HYPOTHESIS)\]",
            artifact.content,
        )
        if unresolved_marker:
            raise RuntimeError(
                "Unresolved [GAP]/[HYPOTHESIS] markers found in "
                f"post-gap artifact {artifact.filename}."
            )

    @staticmethod
    def _normalize_artifact(artifact: SDLCArtifact) -> SDLCArtifact:
        """Clean common provider artifacts like repeated full-document echoes."""
        content = artifact.content.strip()
        deduped = DiscoveryHarness._strip_repeated_suffix(content)
        if deduped == content:
            return artifact
        return SDLCArtifact(
            artifact_type=artifact.artifact_type,
            filename=artifact.filename,
            content=deduped,
        )

    @staticmethod
    def _strip_repeated_suffix(content: str) -> str:
        """Remove exact trailing repetition of the full document body."""
        length = len(content)
        if length < 2 or length % 2:
            return content

        half = length // 2
        if content[:half].strip() == content[half:].strip():
            return content[:half].strip()
        return content

    async def _generate_artifact(
        self,
        request: SDLCRequest,
        artifact_type: ArtifactType,
    ) -> SDLCArtifact:
        """Generate a single artifact. Uses real generators if provider set, stub otherwise."""
        if self._provider is None:
            # Stub mode — placeholder content
            filename = ARTIFACT_FILENAMES[artifact_type]
            content = (
                f"# {artifact_type.value.replace('_', ' ').title()}\n\n{request.prompt}\n"
            )
            return SDLCArtifact(
                artifact_type=artifact_type,
                filename=filename,
                content=content,
            )
        from maestro.sdlc.generators import generate_artifact

        return await generate_artifact(self._provider, self._model, request, artifact_type)

    def _scan_codebase(self, workdir: str) -> str:
        """Stub: list top-level .py files for brownfield context (max 20)."""
        root = Path(workdir).resolve()
        py_files = sorted(root.glob("*.py"))[:20]
        if not py_files:
            return "(no Python files found at root level)"
        return "\n".join(f.name for f in py_files)
