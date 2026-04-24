"""Planning artifact consistency checks for `.planning/` metadata."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(slots=True)
class ConsistencyCheckResult:
    """Outcome of a planning consistency check."""

    errors: list[str]

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass(slots=True)
class _RoadmapSnapshot:
    total_phases: int
    completed_phases: int
    progress_rows: int
    progress_completed_rows: int


@dataclass(slots=True)
class _StateSnapshot:
    milestone: str
    progress_total_phases: int
    progress_completed_phases: int
    references: set[str]
    included_phase_evidence: set[str]


@dataclass(slots=True)
class _SummarySnapshot:
    milestone_mentions: set[str]
    referenced_paths: set[str]


def check_planning_consistency(planning_root: str | Path) -> ConsistencyCheckResult:
    """Validate the current planning artifact set for roadmap/state/summary drift."""
    root = Path(planning_root).resolve()
    errors: list[str] = []

    roadmap_path = root / "ROADMAP.md"
    state_path = root / "STATE.md"

    if not roadmap_path.exists():
        return ConsistencyCheckResult([f"Missing required artifact: {roadmap_path}"])
    if not state_path.exists():
        return ConsistencyCheckResult([f"Missing required artifact: {state_path}"])

    roadmap = _parse_roadmap(roadmap_path)
    state = _parse_state(state_path)

    if roadmap.progress_rows != roadmap.total_phases:
        errors.append(
            "ROADMAP.md progress table rows "
            f"({roadmap.progress_rows}) do not match roadmap phases ({roadmap.total_phases})."
        )

    if roadmap.progress_completed_rows != roadmap.completed_phases:
        errors.append(
            "ROADMAP.md completed progress rows "
            f"({roadmap.progress_completed_rows}) do not match checked roadmap phases "
            f"({roadmap.completed_phases})."
        )

    if state.progress_total_phases != roadmap.total_phases:
        errors.append(
            "STATE.md progress.total_phases "
            f"({state.progress_total_phases}) does not match ROADMAP.md phases "
            f"({roadmap.total_phases})."
        )

    if state.progress_completed_phases != roadmap.completed_phases:
        errors.append(
            "STATE.md progress.completed_phases "
            f"({state.progress_completed_phases}) does not match ROADMAP.md completed "
            f"phases ({roadmap.completed_phases})."
        )

    summary_relpath = f".planning/{state.milestone}-MILESTONE-SUMMARY.md"
    summary_path = root / f"{state.milestone}-MILESTONE-SUMMARY.md"
    if summary_relpath not in state.references:
        errors.append(
            f"STATE.md project references do not include `{summary_relpath}` for milestone {state.milestone}."
        )

    if not summary_path.exists():
        errors.append(f"Missing milestone summary for STATE.md milestone: {summary_path}")
        return ConsistencyCheckResult(errors)

    summary = _parse_summary(summary_path)
    if state.milestone not in summary.milestone_mentions:
        errors.append(
            f"{summary_path.name} does not mention STATE.md milestone `{state.milestone}`."
        )

    for evidence_path in sorted(state.included_phase_evidence):
        evidence_file = root / evidence_path.removeprefix(".planning/")
        if not evidence_file.exists():
            errors.append(f"STATE.md phase evidence path does not exist: `{evidence_path}`")
            continue
        if evidence_path not in summary.referenced_paths:
            errors.append(
                f"{summary_path.name} does not reference STATE.md phase evidence `{evidence_path}`."
            )

    report_path = root / "reports" / f"MILESTONE_SUMMARY-{state.milestone}.md"
    if report_path.exists():
        report = _parse_summary(report_path)
        if state.milestone not in report.milestone_mentions:
            errors.append(
                f"{report_path.relative_to(root.parent)} does not mention STATE.md milestone `{state.milestone}`."
            )
        report_counts = _parse_report_phase_counts(report_path)
        if report_counts is not None:
            complete_count, total_count = report_counts
            if complete_count != roadmap.completed_phases or total_count != roadmap.total_phases:
                errors.append(
                    f"{report_path.relative_to(root.parent)} reports {complete_count}/{total_count} complete phases, "
                    f"but ROADMAP.md shows {roadmap.completed_phases}/{roadmap.total_phases}."
                )

    requirements_path = root / "REQUIREMENTS.md"
    if not requirements_path.exists():
        errors.append("Missing REQUIREMENTS.md — cannot validate milestone scope alignment.")
    else:
        try:
            req_milestone = _parse_requirements(requirements_path)
        except ValueError as exc:
            errors.append(f"Invalid REQUIREMENTS.md milestone scope declaration: {exc}")
        else:
            if req_milestone != state.milestone:
                errors.append(
                    f"REQUIREMENTS.md is scoped to `{req_milestone}` but STATE.md milestone is `{state.milestone}`."
                )

    return ConsistencyCheckResult(errors)


def _parse_roadmap(path: Path) -> _RoadmapSnapshot:
    text = path.read_text(encoding="utf-8")
    phase_matches = re.findall(r"^- \[(?P<done>[ x])\] \*\*Phase (?P<num>\d+):", text, re.MULTILINE)
    progress_matches = re.findall(
        r"^\|\s*(?P<num>\d+)\.\s+[^|]+\|\s*[^|]+\|\s*(?P<status>[^|]+)\|\s*[^|]+\|$",
        text,
        re.MULTILINE,
    )
    completed_phases = sum(done == "x" for done, _ in phase_matches)
    progress_completed = sum(status.strip().lower() == "complete" for _, status in progress_matches)
    return _RoadmapSnapshot(
        total_phases=len(phase_matches),
        completed_phases=completed_phases,
        progress_rows=len(progress_matches),
        progress_completed_rows=progress_completed,
    )


def _parse_state(path: Path) -> _StateSnapshot:
    text = path.read_text(encoding="utf-8")
    frontmatter_match = re.match(r"^---\n(?P<body>.*?)\n---", text, re.DOTALL)
    if frontmatter_match is None:
        raise ValueError(f"STATE.md is missing YAML frontmatter: {path}")

    frontmatter = frontmatter_match.group("body")
    milestone = _require_match(
        frontmatter,
        r"^milestone:\s*(?P<value>.+)$",
        "STATE.md milestone",
    )
    total_phases = int(
        _require_match(
            frontmatter,
            r"^\s*total_phases:\s*(?P<value>\d+)\s*$",
            "STATE.md progress.total_phases",
        )
    )
    completed_phases = int(
        _require_match(
            frontmatter,
            r"^\s*completed_phases:\s*(?P<value>\d+)\s*$",
            "STATE.md progress.completed_phases",
        )
    )

    references = set(re.findall(r"`([^`]+)`", text))
    included_phase_evidence = set(
        re.findall(
            r"^\|\s*\d+\s*-\s*[^|]+\|\s*[^|]+\|\s*`([^`]+)`\s*\|$",
            text,
            re.MULTILINE,
        )
    )

    return _StateSnapshot(
        milestone=milestone.strip(),
        progress_total_phases=total_phases,
        progress_completed_phases=completed_phases,
        references=references,
        included_phase_evidence=included_phase_evidence,
    )


def _parse_summary(path: Path) -> _SummarySnapshot:
    text = path.read_text(encoding="utf-8")
    milestone_mentions = set(re.findall(r"\bv\d+(?:\.\d+)+\b", text))
    referenced_paths = set(re.findall(r"`([^`]+)`", text))
    return _SummarySnapshot(
        milestone_mentions=milestone_mentions,
        referenced_paths=referenced_paths,
    )


def _parse_report_phase_counts(path: Path) -> tuple[int, int] | None:
    text = path.read_text(encoding="utf-8")
    stats_match = re.search(
        r"\*\*Phases:\*\*\s*(?P<complete>\d+) complete / (?P<total>\d+) total",
        text,
    )
    if stats_match is None:
        return None
    return int(stats_match.group("complete")), int(stats_match.group("total"))


def _require_match(text: str, pattern: str, label: str) -> str:
    match = re.search(pattern, text, re.MULTILINE)
    if match is None:
        raise ValueError(f"Missing required field: {label}")
    return match.group("value")


def _parse_requirements(path: Path) -> str:
    """Extract the milestone slug from the REQUIREMENTS.md scope declaration."""
    text = path.read_text(encoding="utf-8")
    match = re.search(r"scoped to milestone [`]([^`]+)[`]", text)
    if match is None:
        raise ValueError(f"REQUIREMENTS.md is missing 'scoped to milestone `...`' declaration: {path}")
    return match.group(1)
