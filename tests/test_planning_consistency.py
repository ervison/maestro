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


def test_repository_planning_artifacts_are_currently_consistent() -> None:
    from maestro.planning import check_planning_consistency

    repo_root = Path(__file__).resolve().parents[1]
    result = check_planning_consistency(repo_root / ".planning")

    assert result.errors == []


# ── Plan 14-01 Task 1: REQUIREMENTS.md milestone alignment checks ─────────────

def test_missing_requirements_reported(tmp_path: Path) -> None:
    planning = _make_planning_tree(tmp_path)
    # Do NOT write REQUIREMENTS.md — absence should be reported

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
