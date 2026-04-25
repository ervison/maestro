# Wave 4 — Harness Refactor + Reflect Loop Update

## Progress

| Microtask | Description | Status |
|-----------|-------------|--------|
| 4.1 | Refactor `maestro/sdlc/harness.py` to sprint-based DAG execution | `[ ]` |
| 4.2 | Add sprint-mode tests to `tests/test_sdlc_harness.py` | `[ ]` |
| 4.3 | Update reflect loop DIMENSIONS for NFR | `[ ]` |
| 4.4 | Update reflect tests for 11 dimensions | `[ ]` |
| 4.5 | Run full SDLC test suite | `[ ]` |
| 4.6 | Commit Wave 4 | `[ ]` |

> Update status to `[x]` when a microtask is complete, `[~]` when in progress, `[!]` if blocked.

---

**Goal:** Replace the sequential `ARTIFACT_ORDER` loop in `DiscoveryHarness` with a
sprint-based DAG executor that uses `sprints.py` and calls `Reviewer` gates; update the
`ReflectLoop` to include the NFR coverage dimension; add new harness tests.

**Why this wave fourth:** Depends on all of Wave 1 (NFR enum), Wave 2 (sprint/gate
dataclasses + `sprints.py`), and Wave 3 (`Reviewer`).  This is the most invasive change in
the plan and must land after its prerequisites are solid.

**Dependencies:** Waves 1, 2, 3 complete.

**Files touched:**
- `maestro/sdlc/harness.py` (modify — replace sequential loop, add sprint path)
- `maestro/sdlc/reflect.py` (modify — add NFR dimension, update prompt text)
- `tests/test_sdlc_harness.py` (add sprint-mode tests)
- `tests/test_sdlc_reflect.py` (update DIMENSIONS list)

---

## `[ ]` Microtask 4.1 — Refactor `maestro/sdlc/harness.py` to Sprint-Based DAG Execution

**File:** `maestro/sdlc/harness.py`

**Pre-condition:** Waves 1–3 complete.

**Action:** Replace the content of `maestro/sdlc/harness.py` with the following implementation.
**Do not delete any helper methods** (`_normalize_artifact`, `_strip_repeated_suffix`,
`_ensure_no_open_markers`, `_generate_artifact`, `_scan_codebase`) — they are used by both
the sequential and sprint paths.

Key changes to apply:
1. Add `use_sprints: bool = False` and `reviewer: "Reviewer | None" = None` to `__init__`.
2. Add `self._gate_failures: list[GateResult] = []` to `__init__`.
3. Initialize `self._reviewer = reviewer if reviewer is not None else Reviewer()` in `__init__`.
4. In `arun`, branch on `self.use_sprints and self._provider is not None` to call either `_run_with_sprints` or `_run_sequential`.
5. Add `_run_sequential` method that extracts the existing sequential loop verbatim (with 14 as total, using `ARTIFACT_ORDER`).
6. Add `_run_with_sprints` method that loops over `SPRINTS`, calls `get_ready_artifacts`, uses `asyncio.gather` for parallel waves, writes artifacts, and calls `_run_gate` after each sprint.
7. Add `_run_gate` method that calls `self._reviewer.review(...)` when provider is set, else returns auto-pass `GateResult`.
8. Add `_resolve_gaps` method extracted from existing code.
9. Populate `gate_failures` on `DiscoveryResult` return: `DiscoveryResult(..., gate_failures=self._gate_failures)`.

The full replacement content for `maestro/sdlc/harness.py`:

```python
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
                f"[{i}/{total}] \u2713 {artifact.filename}",
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
                        f"  \u2713 {artifact.filename}",
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
                    f"\n  [discover] \u26a0 Sprint {sprint.sprint_id} ({sprint.name}) gate FAILED: {gate.notes}",
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
                line = f"- {answer.question} \u2192 {opts_str}"
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
```

Also update `DiscoveryResult` in `maestro/sdlc/schemas.py` to add the `gate_failures` field (if not already added in Wave 2):
```python
@dataclass
class DiscoveryResult:
    request: SDLCRequest
    artifacts: list[SDLCArtifact]
    spec_dir: str
    reflect_report: str = ""
    gate_failures: list[GateResult] = field(default_factory=list)

    @property
    def artifact_count(self) -> int:
        return len(self.artifacts)
```

**Verification:** Run `python -c "from maestro.sdlc.harness import DiscoveryHarness; print('OK')"` — prints `OK`.

---

## `[ ]` Microtask 4.2 — Add Sprint-Mode Tests to `tests/test_sdlc_harness.py`

**File:** `tests/test_sdlc_harness.py`

**Pre-condition:** Microtask 4.1 must be applied.

**Action:**

1. Update the imports block at the top of `tests/test_sdlc_harness.py` to include `GateResult`:
```python
from maestro.sdlc.schemas import (
    ARTIFACT_FILENAMES,
    ARTIFACT_ORDER,
    ArtifactType,
    DiscoveryResult,
    GateResult,
    SDLCRequest,
)
```

2. Add the following two test functions at the end of the file:

```python
@pytest.mark.asyncio
async def test_harness_sprint_mode_produces_14_artifacts(tmp_path: Path) -> None:
    from unittest.mock import patch, AsyncMock
    from maestro.sdlc.schemas import SDLCArtifact

    call_order: list[str] = []

    async def fake_generate(self_ref, request, artifact_type):
        call_order.append(artifact_type.value)
        return SDLCArtifact(
            artifact_type=artifact_type,
            filename=ARTIFACT_FILENAMES[artifact_type],
            content="# content",
        )

    with patch.object(DiscoveryHarness, "_generate_artifact", new=fake_generate):
        with patch("maestro.sdlc.harness.resolve_gaps", new=AsyncMock(return_value=[])):
            harness = DiscoveryHarness(provider=object(), model="test", open_browser=False, use_sprints=True, reflect=False)
            request = SDLCRequest(prompt="Build a CRM", workdir=str(tmp_path))
            result = await harness.arun(request)

    assert result.artifact_count == 14
    assert call_order[0] == "briefing"


@pytest.mark.asyncio
async def test_harness_sprint_mode_runs_gate_reviews(tmp_path: Path) -> None:
    from unittest.mock import patch, AsyncMock
    from maestro.sdlc.schemas import SDLCArtifact

    async def fake_generate(self_ref, request, artifact_type):
        return SDLCArtifact(
            artifact_type=artifact_type,
            filename=ARTIFACT_FILENAMES[artifact_type],
            content="# content",
        )

    gate_calls: list[int] = []

    async def tracking_gate(self_ref, sprint_id, sprint_artifacts, all_artifacts):
        gate_calls.append(sprint_id)
        return GateResult(sprint_id=sprint_id, passed=True)

    with patch.object(DiscoveryHarness, "_generate_artifact", new=fake_generate):
        with patch.object(DiscoveryHarness, "_run_gate", new=tracking_gate):
            with patch("maestro.sdlc.harness.resolve_gaps", new=AsyncMock(return_value=[])):
                harness = DiscoveryHarness(provider=object(), model="test", open_browser=False, use_sprints=True, reflect=False)
                request = SDLCRequest(prompt="Build a CRM", workdir=str(tmp_path))
                await harness.arun(request)

    assert gate_calls == [1, 2, 3, 4, 5, 6]
```

3. Add the gate-failure warn-only test using `StubReviewer`:

```python
class StubReviewer:
    """Stub matching Reviewer.review() async signature for tests."""

    def __init__(self, *, always_fail: bool = False) -> None:
        self.always_fail = always_fail
        self.calls: list[int] = []

    async def review(
        self, provider, model, sprint_id, artifacts, prior_artifacts=None
    ) -> GateResult:
        self.calls.append(sprint_id)
        return GateResult(
            sprint_id=sprint_id,
            passed=not self.always_fail,
            notes="stub-fail" if self.always_fail else "stub-ok",
            issues=[f"stub issue for sprint {sprint_id}"] if self.always_fail else [],
        )


@pytest.mark.asyncio
async def test_sprint_mode_continues_after_gate_failure(tmp_path) -> None:
    """Gate failure must not abort the run; all sprints must execute."""
    from unittest.mock import patch, AsyncMock
    from maestro.sdlc.schemas import SDLCArtifact

    failing_reviewer = StubReviewer(always_fail=True)

    async def fake_generate(self_ref, request, artifact_type):
        return SDLCArtifact(
            artifact_type=artifact_type,
            filename=ARTIFACT_FILENAMES[artifact_type],
            content="# content",
        )

    with patch.object(DiscoveryHarness, "_generate_artifact", new=fake_generate):
        with patch("maestro.sdlc.harness.resolve_gaps", new=AsyncMock(return_value=[])):
            harness = DiscoveryHarness(
                provider=object(),
                model="stub/model",
                workdir=str(tmp_path),
                use_sprints=True,
                reviewer=failing_reviewer,
                reflect=False,
                open_browser=False,
            )
            result = harness.run(SDLCRequest(prompt="x", workdir=str(tmp_path)))

    assert result.artifact_count == 14, "all artifacts must be generated despite gate failure"
    assert len(result.gate_failures) == 6, "all 6 sprint gates failed and were recorded"
    assert failing_reviewer.calls == [1, 2, 3, 4, 5, 6], "all sprints must invoke the gate"
```

**Verification:** Run `pytest tests/test_sdlc_harness.py -v` — ALL PASS (no regressions, new tests pass).

---

## `[ ]` Microtask 4.3 — Update Reflect Loop DIMENSIONS for NFR

**File:** `maestro/sdlc/reflect.py`

**Pre-condition:** Microtask 4.1 applied.

**Action:**

1. Locate `DIMENSIONS` list in `maestro/sdlc/reflect.py` (around lines 17–28). Add the NFR dimension as the 11th entry:
```python
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
    "Cobertura de requisitos não-funcionais",
]
```

2. Locate the `_build_eval_prompt` method. Find the string literal `"Evaluate the following spec files across 10 quality dimensions"` and replace it with an f-string using `len(DIMENSIONS)`:
```python
f"Evaluate the following spec files across {len(DIMENSIONS)} quality dimensions, then identify the top-3 most important problems to fix."
```

3. Find the string `'The "scores" array must contain exactly 10 entries, one per dimension.'` and replace with:
```python
f'The "scores" array must contain exactly {len(DIMENSIONS)} entries, one per dimension.'
```

**Verification:** Run `python -c "from maestro.sdlc.reflect import DIMENSIONS; print(len(DIMENSIONS))"` — prints `11`.

---

## `[ ]` Microtask 4.4 — Update Reflect Tests for 11 Dimensions

**File:** `tests/test_sdlc_reflect.py`

**Pre-condition:** Microtask 4.3 applied.

**Action:** In `tests/test_sdlc_reflect.py`, locate the local `DIMENSIONS` list used in tests and update it to match the production list exactly (11 entries):
```python
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
    "Cobertura de requisitos não-funcionais",
]
```

Also update any test assertions that check for `== 10` dimensions to `== 11`.

**Verification:** Run `pytest tests/test_sdlc_reflect.py -v` — ALL PASS.

---

## `[ ]` Microtask 4.5 — Run Full SDLC Test Suite

**Pre-condition:** Microtasks 4.1–4.4 applied.

**Action:**
```bash
pytest tests/test_sdlc_*.py -v
```

**Expected:** ALL PASS — zero regressions, all 14-artifact assertions pass, sprint tests pass, reflect tests pass.

---

## `[ ]` Microtask 4.6 — Commit Wave 4

**Pre-condition:** All `tests/test_sdlc_*.py` tests pass.

**Action:**
```bash
git add maestro/sdlc/harness.py maestro/sdlc/reflect.py maestro/sdlc/schemas.py \
        tests/test_sdlc_harness.py tests/test_sdlc_reflect.py
git commit -m "feat(sdlc): sprint-based DAG harness + NFR dimension in reflect loop"
```

**Verification:** `git status` shows clean working tree.
