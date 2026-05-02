"""Tests for planning artifact consistency checks."""
from __future__ import annotations

from pathlib import Path

import pytest


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_planning_tree(root: Path) -> Path:
    planning = root / ".planning"

    _write(
        planning / "ROADMAP.md",
        """# Roadmap: Maestro

## Phases

- [x] **Phase 1: First** - Done
- [x] **Phase 2: Second** - Done

## Phase Details

### Phase 1: First ✅ COMPLETE
### Phase 2: Second ✅ COMPLETE

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. First | 1/1 | Complete | 2026-04-20 |
| 2. Second | 1/1 | Complete | 2026-04-21 |
""",
    )

    _write(
        planning / "STATE.md",
        """---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: milestone
status: completed
stopped_at: Done
last_updated: "2026-04-23T16:51:33-03:00"
last_activity: 2026-04-23 - Done
progress:
  total_phases: 2
  completed_phases: 2
  total_plans: 2
  completed_plans: 2
  percent: 100
---

# Maestro - Project State

## Project Reference

- `.planning/ROADMAP.md`
- `.planning/v1.1-MILESTONE-SUMMARY.md`

## Current Position

Milestone: `v1.1` - Demo
Status: COMPLETE

## Milestone Snapshot

### Included phases

| Phase | Status | Evidence |
|------|--------|----------|
| 1 - First | Complete | `.planning/phases/01-first/01-SUMMARY.md` |
| 2 - Second | Complete | `.planning/phases/02-second/02-SUMMARY.md` |
""",
    )

    _write(planning / "phases/01-first/01-SUMMARY.md", "# Phase 1\n")
    _write(planning / "phases/02-second/02-SUMMARY.md", "# Phase 2\n")

    _write(
        planning / "REQUIREMENTS.md",
        "# Maestro - v1.1 Requirements\n\n## Scope\n\nThis file is scoped to milestone `v1.1`.\n",
    )

    _write(
        planning / "v1.1-MILESTONE-SUMMARY.md",
        """# Maestro v1.1 - Milestone Summary Report

**Status:** `complete`

## Planning Artifacts Reviewed

- `.planning/ROADMAP.md`
- `.planning/phases/01-first/01-SUMMARY.md`
- `.planning/phases/02-second/02-SUMMARY.md`

## Verdict

Milestone `v1.1` is complete in planning artifacts.
""",
    )

    return planning


def test_check_planning_consistency_accepts_aligned_artifacts(tmp_path: Path) -> None:
    planning = _make_planning_tree(tmp_path)

    from maestro.planning import check_planning_consistency

    result = check_planning_consistency(planning)

    assert result.errors == []


def test_check_planning_consistency_reports_state_progress_drift(tmp_path: Path) -> None:
    planning = _make_planning_tree(tmp_path)
    state_path = planning / "STATE.md"
    state_text = state_path.read_text(encoding="utf-8")
    state_path.write_text(
        state_text.replace("completed_phases: 2", "completed_phases: 1"),
        encoding="utf-8",
    )

    from maestro.planning import check_planning_consistency

    result = check_planning_consistency(planning)

    assert any("STATE.md progress.completed_phases" in error for error in result.errors)


def test_repository_planning_artifacts_can_be_checked() -> None:
    from maestro.planning import check_planning_consistency

    repo_root = Path(__file__).resolve().parents[1]
    result = check_planning_consistency(repo_root / ".planning")

    assert isinstance(result.ok, bool)
    assert all(isinstance(error, str) for error in result.errors)


# ── Plan 14-01 Task 1: REQUIREMENTS.md milestone alignment checks ─────────────

def test_missing_requirements_reported(tmp_path: Path) -> None:
    planning = _make_planning_tree(tmp_path)
    (planning / "REQUIREMENTS.md").unlink()  # Remove to simulate absence

    from maestro.planning import check_planning_consistency

    result = check_planning_consistency(planning)

    assert any("Missing REQUIREMENTS.md" in e for e in result.errors)


def test_requirements_milestone_mismatch_reported(tmp_path: Path) -> None:
    planning = _make_planning_tree(tmp_path)
    _write(
        planning / "REQUIREMENTS.md",
        "# Maestro - v9.9 Requirements\n\n## Scope\n\nThis file is scoped to milestone `v9.9`.\n",
    )

    from maestro.planning import check_planning_consistency

    result = check_planning_consistency(planning)

    assert any("REQUIREMENTS.md is scoped to" in e for e in result.errors)


def test_requirements_milestone_aligned_no_error(tmp_path: Path) -> None:
    planning = _make_planning_tree(tmp_path)
    _write(
        planning / "REQUIREMENTS.md",
        "# Maestro - v1.1 Requirements\n\n## Scope\n\nThis file is scoped to milestone `v1.1`.\n",
    )

    from maestro.planning import check_planning_consistency

    result = check_planning_consistency(planning)

    assert not any("REQUIREMENTS.md" in e for e in result.errors)


# ── Plan 14-01 Task 2: Additional drift path coverage ────────────────────────

def test_missing_phase_evidence_reported(tmp_path: Path) -> None:
    planning = _make_planning_tree(tmp_path)
    (planning / "phases/01-first/01-SUMMARY.md").unlink()

    from maestro.planning import check_planning_consistency

    result = check_planning_consistency(planning)

    assert any("phases/01-first/01-SUMMARY.md" in e for e in result.errors)


def test_summary_missing_milestone_mention_reported(tmp_path: Path) -> None:
    planning = _make_planning_tree(tmp_path)
    _write(
        planning / "v1.1-MILESTONE-SUMMARY.md",
        "# Milestone Summary\n\nNo version mentioned here.\n",
    )

    from maestro.planning import check_planning_consistency

    result = check_planning_consistency(planning)

    assert any("v1.1" in e and "does not mention" in e for e in result.errors)


def test_planning_helper_functions_cover_edge_cases(tmp_path: Path) -> None:
    from maestro.planning import (
        ConsistencyCheckResult,
        _RoadmapSnapshot,
        _StateSnapshot,
        _is_markdown_divider_row,
        _parse_report_phase_counts,
        _parse_requirements,
        _parse_roadmap,
        _parse_state,
        _parse_summary,
        _require_match,
        _split_markdown_row,
        _validate_report_consistency,
        _validate_roadmap_state_consistency,
        _validate_summary_artifacts,
    )

    assert ConsistencyCheckResult([]).ok is True
    assert ConsistencyCheckResult(["x"]).ok is False
    assert _split_markdown_row("not a row") is None
    assert _is_markdown_divider_row(["---", ":---:"]) is True

    roadmap = _RoadmapSnapshot(2, 1, 1, 0)
    state = _StateSnapshot("v1.1", 3, 0, set(), {".planning/phases/01-first/01-SUMMARY.md"})
    errors = _validate_roadmap_state_consistency(roadmap, state)
    assert len(errors) == 4

    root = tmp_path / ".planning"
    root.mkdir()
    summary_errors = _validate_summary_artifacts(state, roadmap, root)
    assert any("do not include" in error for error in summary_errors)
    assert any("Missing milestone summary" in error for error in summary_errors)

    _write(root / "v1.1-MILESTONE-SUMMARY.md", "Milestone `v0.0`\n")
    _write(root / "phases/01-first/01-SUMMARY.md", "phase one\n")
    report_errors = _validate_summary_artifacts(
        _StateSnapshot(
            "v1.1",
            2,
            1,
            {".planning/v1.1-MILESTONE-SUMMARY.md"},
            {".planning/phases/01-first/01-SUMMARY.md"},
        ),
        _RoadmapSnapshot(2, 1, 2, 1),
        root,
    )
    assert any("does not mention" in error for error in report_errors)
    assert any("does not reference" in error for error in report_errors)

    _write(root / "reports/MILESTONE_SUMMARY-v1.1.md", "Milestone `v0.0`\n**Phases:** 0 complete / 3 total\n")
    report_only_errors: list[str] = []
    _validate_report_consistency(
        _StateSnapshot("v1.1", 2, 1, set(), set()),
        _RoadmapSnapshot(2, 1, 2, 1),
        root,
        report_only_errors,
    )
    assert len(report_only_errors) == 2

    report = root / "reports" / "counts.md"
    _write(report, "no stats here\n")
    assert _parse_report_phase_counts(report) is None
    _write(report, "**Phases:** 1 complete / 2 total\n")
    assert _parse_report_phase_counts(report) == (1, 2)

    bad_state = root / "BROKEN-STATE.md"
    _write(bad_state, "no frontmatter\n")
    with pytest.raises(ValueError, match="missing YAML frontmatter"):
        _parse_state(bad_state)

    with pytest.raises(ValueError, match="Missing required field"):
        _require_match("x: 1", r"^milestone:\s*(?P<value>.+)$", "STATE.md milestone")

    bad_requirements = root / "REQUIREMENTS.md"
    _write(bad_requirements, "missing declaration\n")
    with pytest.raises(ValueError, match="missing 'scoped to milestone"):
        _parse_requirements(bad_requirements)

    roadmap_path = root / "ROADMAP.md"
    _write(
        roadmap_path,
        """- [x] **Phase 1: One** - Done
- [ ] **Phase 2: Two** - Todo
| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| nope | 0/1 | Started | - |

outside table
""",
    )
    assert _parse_roadmap(roadmap_path) == _RoadmapSnapshot(2, 1, 0, 0)

    summary = root / "summary.md"
    _write(summary, "Milestone `v1.1` references `.planning/file.md`\n")
    parsed_summary = _parse_summary(summary)
    assert parsed_summary.milestone_mentions == {"v1.1"}
    assert parsed_summary.referenced_paths == {"v1.1", ".planning/file.md"}


def test_check_planning_consistency_reports_missing_artifacts_and_bad_requirements(
    tmp_path: Path,
) -> None:
    from maestro.planning import check_planning_consistency

    planning = tmp_path / ".planning"
    planning.mkdir()
    assert check_planning_consistency(planning).errors == [
        f"Missing required artifact: {(planning / 'ROADMAP.md').resolve()}"
    ]

    _write(planning / "ROADMAP.md", "# roadmap\n")
    assert check_planning_consistency(planning).errors == [
        f"Missing required artifact: {(planning / 'STATE.md').resolve()}"
    ]

    planning = _make_planning_tree(tmp_path / "second")
    _write(planning / "REQUIREMENTS.md", "broken\n")
    result = check_planning_consistency(planning)
    assert any("Invalid REQUIREMENTS.md milestone scope declaration" in error for error in result.errors)
