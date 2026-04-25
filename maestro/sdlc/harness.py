"""SDLC Discovery Harness — orchestrates 14-artifact specification generation with sprint-based DAG."""
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
    GateResult,
    SDLCArtifact,
    SDLCRequest,
    SprintResult,
)


class DiscoveryHarness:
    """Orchestrates the 14-artifact SDLC discovery pipeline."""

    def __init__(
        self,
        provider=None,
        model: str | None = None,
        workdir: str = ".",
        gaps_port: int = 4041,
        open_browser: bool = True,
        reflect: bool = True,
        reflect_max_cycles: int = 5,
        use_sprints: bool = False,
        reviewer=None,
    ) -> None:
        self._provider = provider
        self._model = model
        self._workdir = workdir
        self._gaps_port = gaps_port
        self._open_browser = open_browser
        self.reflect = reflect
        self.reflect_max_cycles = reflect_max_cycles
        self.use_sprints = use_sprints
        self._gate_failures: list[GateResult] = []

        if reviewer is not None:
            self._reviewer = reviewer
        else:
            from maestro.sdlc.reviewer import Reviewer
            self._reviewer = Reviewer()

    def run(self, request: SDLCRequest) -> DiscoveryResult:
        """Synchronous entry point — wraps async run."""
        return asyncio.run(self.arun(request))

    async def arun(self, request: SDLCRequest) -> DiscoveryResult:
        """Generate all 14 artifacts and write them to spec/."""
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

        if self.use_sprints and self._provider is not None:
            artifacts = await self._run_with_sprints(effective_request, spec_dir)
        else:
            artifacts = await self._run_sequential(effective_request, spec_dir)

        result = DiscoveryResult(
            request=request,
            artifacts=artifacts,
            spec_dir=str(spec_dir),
            gate_failures=list(self._gate_failures),
        )

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
                gate_failures=list(self._gate_failures),
            )

        return result

    async def _run_sequential(
        self,
        request: SDLCRequest,
        spec_dir: Path,
    ) -> list[SDLCArtifact]:
        """Legacy sequential generation (backward compatible)."""
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
            artifact = await self._generate_artifact(request, artifact_type)
            artifact = self._normalize_artifact(artifact)
            if self._provider is not None and i > gaps_index + 1:
                self._ensure_no_open_markers(artifact)
            artifacts.append(artifact)
            write_artifact(spec_dir, artifact)
            if artifact_type == ArtifactType.GAPS and self._provider is not None:
                request = await self._resolve_gaps(request, artifact)
            print(
                f"[{i}/{total}] ✓ {artifact.filename}",
                file=sys.stderr,
                flush=True,
            )
        return artifacts

    async def _run_with_sprints(
        self,
        request: SDLCRequest,
        spec_dir: Path,
    ) -> list[SDLCArtifact]:
        """Sprint-based DAG generation with gate reviews."""
        from maestro.sdlc.sprints import SPRINTS, get_ready_artifacts
        from maestro.sdlc.writer import write_artifact

        artifacts: list[SDLCArtifact] = []
        completed: set[ArtifactType] = set()
        sprint_results: list[SprintResult] = []
        current_request = request

        for sprint in SPRINTS:
            print(
                f"\n=== Sprint {sprint.sprint_id}: {sprint.name} ===",
                file=sys.stderr,
                flush=True,
            )

            sprint_artifacts: list[SDLCArtifact] = []
            waves = get_ready_artifacts(sprint, completed.copy())

            for wave_idx, wave in enumerate(waves):
                if len(wave) > 1:
                    print(
                        f"  Wave {wave_idx + 1}: {', '.join(a.value for a in wave)} (parallel)",
                        file=sys.stderr,
                        flush=True,
                    )
                    tasks = [
                        self._generate_artifact(current_request, artifact_type)
                        for artifact_type in wave
                    ]
                    wave_artifacts = list(await asyncio.gather(*tasks))
                else:
                    artifact_type = wave[0]
                    print(
                        f"  Wave {wave_idx + 1}: {artifact_type.value}",
                        file=sys.stderr,
                        flush=True,
                    )
                    artifact = await self._generate_artifact(current_request, artifact_type)
                    wave_artifacts = [artifact]

                for artifact in wave_artifacts:
                    artifact = self._normalize_artifact(artifact)
                    self._ensure_no_open_markers(artifact)
                    sprint_artifacts.append(artifact)
                    artifacts.append(artifact)
                    completed.add(artifact.artifact_type)
                    write_artifact(spec_dir, artifact)
                    print(
                        f"  ✓ {artifact.filename}",
                        file=sys.stderr,
                        flush=True,
                    )

                for artifact in wave_artifacts:
                    if artifact.artifact_type == ArtifactType.GAPS:
                        current_request = await self._resolve_gaps(current_request, artifact)

            gate = await self._run_gate(sprint.sprint_id, sprint_artifacts, artifacts)
            sprint_results.append(SprintResult(
                sprint_id=sprint.sprint_id,
                name=sprint.name,
                artifacts=sprint_artifacts,
                gate=gate,
            ))

            if not gate.passed:
                print(
                    f"\n  [discover] ⚠ Sprint {sprint.sprint_id} ({sprint.name}) gate FAILED: {gate.notes}",
                    file=sys.stderr,
                    flush=True,
                )
                for issue in gate.issues:
                    print(f"[discover]   - {issue}", file=sys.stderr)
                self._gate_failures.append(gate)

        return artifacts

    async def _run_gate(
        self,
        sprint_id: int,
        sprint_artifacts: list[SDLCArtifact],
        all_artifacts: list[SDLCArtifact],
    ) -> GateResult:
        """Run gate review for a sprint. Returns auto-pass if no provider."""
        if self._provider is None:
            return GateResult(sprint_id=sprint_id, passed=True)

        prior = [a for a in all_artifacts if a not in sprint_artifacts]
        return await self._reviewer.review(
            provider=self._provider,
            model=self._model,
            sprint_id=sprint_id,
            artifacts=sprint_artifacts,
            prior_artifacts=prior,
        )

    async def _resolve_gaps(
        self,
        request: SDLCRequest,
        gaps_artifact: SDLCArtifact,
    ) -> SDLCRequest:
        """Resolve gap questions via the gaps server."""
        answers = await resolve_gaps(
            gaps_artifact.content,
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
            return SDLCRequest(
                prompt=f"{request.prompt}\n\n## Gap Answers\n{answers_text}",
                language=request.language,
                brownfield=request.brownfield,
                workdir=request.workdir,
            )
        return request

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
