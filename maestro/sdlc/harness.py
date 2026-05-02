"""SDLC Discovery Harness — orchestrates 14-artifact specification generation with sprint-based DAG."""
from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

from maestro.sdlc.defaults import TECHNICAL_DEFAULTS
from maestro.sdlc.gaps_server import parse_gaps, resolve_discovery_profile, resolve_gaps
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


def _build_sprint_deps(sprints) -> dict[ArtifactType, tuple[ArtifactType, ...]]:
    all_deps: dict[ArtifactType, tuple[ArtifactType, ...]] = {}
    for sprint in sprints:
        all_deps.update(sprint.deps)
    return all_deps


def _print_sprint_header(sprint) -> None:
    print(
        f"\n=== Sprint {sprint.sprint_id}: {sprint.name} ===",
        file=sys.stderr,
        flush=True,
    )


def _print_wave_header(wave_idx: int, wave: list[ArtifactType]) -> None:
    if len(wave) > 1:
        label = f"{', '.join(a.value for a in wave)} (parallel)"
    else:
        label = wave[0].value
    print(f"  Wave {wave_idx + 1}: {label}", file=sys.stderr, flush=True)


async def _generate_wave_artifacts(
    harness: "DiscoveryHarness",
    request: SDLCRequest,
    wave: list[ArtifactType],
    artifact_map: dict[ArtifactType, SDLCArtifact],
    all_deps: dict[ArtifactType, tuple[ArtifactType, ...]],
) -> list[SDLCArtifact]:
    if len(wave) == 1:
        artifact_type = wave[0]
        return [
            await harness._generate_artifact(
                request,
                artifact_type,
                harness._get_prior_artifacts(artifact_type, artifact_map, all_deps),
            )
        ]

    tasks = [
        harness._generate_artifact(
            request,
            artifact_type,
            harness._get_prior_artifacts(artifact_type, artifact_map, all_deps),
        )
        for artifact_type in wave
    ]
    return list(await asyncio.gather(*tasks))


def _persist_wave_artifacts(
    harness: "DiscoveryHarness",
    wave_artifacts: list[SDLCArtifact],
    *,
    gaps_resolved: bool,
    sprint_artifacts: list[SDLCArtifact],
    artifacts: list[SDLCArtifact],
    artifact_map: dict[ArtifactType, SDLCArtifact],
    completed: set[ArtifactType],
    spec_dir: Path,
) -> list[SDLCArtifact]:
    from maestro.sdlc.writer import write_artifact

    normalized_artifacts: list[SDLCArtifact] = []
    for artifact in wave_artifacts:
        artifact = harness._normalize_artifact(artifact)
        if gaps_resolved:
            harness._ensure_no_open_markers(artifact)
        sprint_artifacts.append(artifact)
        artifacts.append(artifact)
        artifact_map[artifact.artifact_type] = artifact
        completed.add(artifact.artifact_type)
        write_artifact(spec_dir, artifact)
        print(f"  ✓ {artifact.filename}", file=sys.stderr, flush=True)
        normalized_artifacts.append(artifact)
    return normalized_artifacts


async def _resolve_wave_gaps(
    harness: "DiscoveryHarness",
    request: SDLCRequest,
    wave_artifacts: list[SDLCArtifact],
    spec_dir: Path,
) -> tuple[SDLCRequest, bool]:
    for artifact in wave_artifacts:
        if artifact.artifact_type == ArtifactType.GAPS:
            return await harness._resolve_gaps(request, artifact, spec_dir), True
    return request, False


def _append_sprint_result(
    sprint_results: list[SprintResult],
    sprint,
    sprint_artifacts: list[SDLCArtifact],
    gate: GateResult,
) -> None:
    sprint_results.append(
        SprintResult(
            sprint_id=sprint.sprint_id,
            name=sprint.name,
            artifacts=sprint_artifacts,
            gate=gate,
        )
    )


def _record_gate_failure(
    gate: GateResult,
    sprint,
    gate_failures: list[GateResult],
) -> None:
    if gate.passed:
        return
    print(
        f"\n  [discover] ⚠ Sprint {sprint.sprint_id} ({sprint.name}) gate FAILED: {gate.notes}",
        file=sys.stderr,
        flush=True,
    )
    for issue in gate.issues:
        print(f"[discover]   - {issue}", file=sys.stderr)
    gate_failures.append(gate)


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

    def _build_effective_prompt(self, request: SDLCRequest) -> str:
        """Build the full effective prompt with brownfield scan and defaults."""
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
        return f"{TECHNICAL_DEFAULTS}\n\n## User Request\n\n{effective_prompt}"

    def _setup_spec_dir(self, request: SDLCRequest) -> Path:
        """Create and return the spec/ directory."""
        workdir = request.workdir if request.workdir != "." else self._workdir
        spec_dir = Path(workdir).resolve() / "spec"
        try:
            spec_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise RuntimeError(
                f"Failed to create spec directory: {exc.strerror}"
            ) from exc
        return spec_dir

    async def _maybe_reflect(
        self,
        request: SDLCRequest,
        artifacts: list[SDLCArtifact],
        spec_dir: Path,
        result: DiscoveryResult,
    ) -> DiscoveryResult:
        """Run the reflect loop on generated artifacts if enabled and provider is available."""
        if self._provider is not None and self.reflect and hasattr(self._provider, "stream"):
            from maestro.sdlc.reflect import ReflectLoop

            loop = ReflectLoop(target_mean=self.reflect_target_mean)
            reflect_report = await loop.run(
                provider=self._provider,
                model=self._model,
                spec_dir=spec_dir,
                max_cycles=self.reflect_max_cycles,
            )
            return DiscoveryResult(
                request=request,
                artifacts=artifacts,
                spec_dir=str(spec_dir),
                reflect_report=reflect_report,
                gate_failures=list(self._gate_failures),
            )
        return result

    async def arun(self, request: SDLCRequest) -> DiscoveryResult:
        """Generate all 14 artifacts and write them to spec/."""
        effective_prompt = self._build_effective_prompt(request)
        effective_request = SDLCRequest(
            prompt=effective_prompt,
            language=request.language,
            brownfield=request.brownfield,
            workdir=request.workdir,
        )

        spec_dir = self._setup_spec_dir(request)
        from maestro.sdlc.writer import write_artifact
        _ = write_artifact

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

        return await self._maybe_reflect(request, artifacts, spec_dir, result)

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
        _ = write_artifact

        artifacts: list[SDLCArtifact] = []
        # Map from ArtifactType → generated SDLCArtifact for upstream context injection
        artifact_map: dict[ArtifactType, SDLCArtifact] = {}
        completed: set[ArtifactType] = set()
        sprint_results: list[SprintResult] = []
        current_request = request
        gaps_resolved = False  # becomes True after GAPS artifact is processed

        all_deps = _build_sprint_deps(SPRINTS)

        for sprint in SPRINTS:
            _print_sprint_header(sprint)

            sprint_artifacts: list[SDLCArtifact] = []
            waves = get_ready_artifacts(sprint, completed.copy())

            for wave_idx, wave in enumerate(waves):
                _print_wave_header(wave_idx, wave)
                wave_artifacts = await _generate_wave_artifacts(
                    self,
                    current_request,
                    wave,
                    artifact_map,
                    all_deps,
                )
                wave_artifacts = _persist_wave_artifacts(
                    self,
                    wave_artifacts,
                    gaps_resolved=gaps_resolved,
                    sprint_artifacts=sprint_artifacts,
                    artifacts=artifacts,
                    artifact_map=artifact_map,
                    completed=completed,
                    spec_dir=spec_dir,
                )
                current_request, resolved_in_wave = await _resolve_wave_gaps(
                    self,
                    current_request,
                    wave_artifacts,
                    spec_dir,
                )
                if resolved_in_wave:
                    gaps_resolved = True

            gate = await self._run_gate(sprint.sprint_id, sprint_artifacts, artifacts)
            _append_sprint_result(sprint_results, sprint, sprint_artifacts, gate)
            _record_gate_failure(gate, sprint, self._gate_failures)

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
        if not parse_gaps(gaps_artifact.content):
            return request

        profile = resolve_discovery_profile(
            context_hint=request.prompt,
            port=self._gaps_port,
            open_browser=self._open_browser,
        )
        try:
            answers = await resolve_gaps(
                gaps_artifact.content,
                provider=self._provider,
                model=self._model,
                port=self._gaps_port,
                open_browser=self._open_browser,
                profile=profile,
            )
        except TypeError as exc:
            if "unexpected keyword argument 'profile'" not in str(exc):
                raise
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
