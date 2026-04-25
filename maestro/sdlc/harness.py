"""SDLC Discovery Harness — orchestrates 14-artifact specification generation with sprint-based DAG."""
from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

from maestro.sdlc.defaults import TECHNICAL_DEFAULTS
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
        reflect_target_mean: float = 8.0,
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
        self.reflect_target_mean = reflect_target_mean
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
            effective_prompt = (
                f"{request.prompt}\n\n"
                "## Existing Codebase (AUTHORITATIVE — do not contradict or ignore)\n\n"
                "The following codebase scan represents the CURRENT STATE of the system. "
                "Every artifact you generate MUST be consistent with this existing implementation. "
                "Do NOT propose patterns, libraries, or architectures that contradict what is already in place "
                "unless you explicitly flag the contradiction as a [GAP] or architectural decision.\n\n"
                f"{scan}"
            )

        # Prepend technical defaults so every artifact generator sees them as
        # authoritative constraints unless the user explicitly overrides them.
        effective_prompt = (
            f"{TECHNICAL_DEFAULTS}\n\n## User Request\n\n{effective_prompt}"
        )

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

            loop = ReflectLoop(target_mean=self.reflect_target_mean)
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
                request = await self._resolve_gaps(request, artifact, spec_dir)
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
        # Map from ArtifactType → generated SDLCArtifact for upstream context injection
        artifact_map: dict[ArtifactType, SDLCArtifact] = {}
        completed: set[ArtifactType] = set()
        sprint_results: list[SprintResult] = []
        current_request = request
        gaps_resolved = False  # becomes True after GAPS artifact is processed

        # Build a full deps lookup from all sprints for context injection
        all_deps: dict[ArtifactType, tuple[ArtifactType, ...]] = {}
        for sprint in SPRINTS:
            all_deps.update(sprint.deps)

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
                        self._generate_artifact(
                            current_request,
                            artifact_type,
                            self._get_prior_artifacts(artifact_type, artifact_map, all_deps),
                        )
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
                    artifact = await self._generate_artifact(
                        current_request,
                        artifact_type,
                        self._get_prior_artifacts(artifact_type, artifact_map, all_deps),
                    )
                    wave_artifacts = [artifact]

                for artifact in wave_artifacts:
                    artifact = self._normalize_artifact(artifact)
                    if gaps_resolved:
                        self._ensure_no_open_markers(artifact)
                    sprint_artifacts.append(artifact)
                    artifacts.append(artifact)
                    artifact_map[artifact.artifact_type] = artifact
                    completed.add(artifact.artifact_type)
                    write_artifact(spec_dir, artifact)
                    print(
                        f"  ✓ {artifact.filename}",
                        file=sys.stderr,
                        flush=True,
                    )

                for artifact in wave_artifacts:
                    if artifact.artifact_type == ArtifactType.GAPS:
                        current_request = await self._resolve_gaps(current_request, artifact, spec_dir)
                        gaps_resolved = True

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

    @staticmethod
    def _get_prior_artifacts(
        artifact_type: ArtifactType,
        artifact_map: dict[ArtifactType, SDLCArtifact],
        all_deps: dict[ArtifactType, tuple[ArtifactType, ...]],
    ) -> list[SDLCArtifact] | None:
        """Return the upstream artifacts declared as deps for artifact_type, if any."""
        dep_types = all_deps.get(artifact_type, ())
        if not dep_types:
            return None
        prior = [artifact_map[d] for d in dep_types if d in artifact_map]
        return prior if prior else None

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
        spec_dir: Path | None = None,
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

            # Persist answers back into the gaps artifact file so the spec
            # directory contains the full question+answer record.
            if spec_dir is not None:
                from maestro.sdlc.writer import write_artifact

                updated_content = (
                    gaps_artifact.content.rstrip()
                    + "\n\n---\n\n## Gap Answers\n\n"
                    + answers_text
                    + "\n"
                )
                updated_artifact = SDLCArtifact(
                    artifact_type=gaps_artifact.artifact_type,
                    filename=gaps_artifact.filename,
                    content=updated_content,
                )
                write_artifact(spec_dir, updated_artifact)

            return SDLCRequest(
                prompt=(
                    f"{request.prompt}\n\n"
                    "## Gap Answers (AUTHORITATIVE — these answers SUPERSEDE any prior hypothesis or assumption)\n\n"
                    "The following answers were provided explicitly by the user. "
                    "They are binding constraints. Do NOT revert to hypotheses or defaults where an answer exists. "
                    "Silence on a topic in these answers does NOT mean the hypothesis stands — "
                    "only explicit answers are binding.\n\n"
                    f"{answers_text}"
                ),
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
        prior_artifacts: list[SDLCArtifact] | None = None,
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

        return await generate_artifact(self._provider, self._model, request, artifact_type, prior_artifacts)

    def _scan_codebase(self, workdir: str) -> str:
        """Stub: list top-level .py files for brownfield context (max 20)."""
        root = Path(workdir).resolve()
        py_files = sorted(root.glob("*.py"))[:20]
        if not py_files:
            return "(no Python files found at root level)"
        return "\n".join(f.name for f in py_files)
