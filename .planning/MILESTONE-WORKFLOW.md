# Maestro Milestone Workflow

This document defines the steps for opening a new milestone and closing a completed one.
Run `maestro planning check` at both transitions to ensure planning artifacts stay aligned.

## Opening a New Milestone

1. Update `.planning/ROADMAP.md` — add new phase entries with `[ ]` status and new progress table rows.
2. Update `.planning/STATE.md` frontmatter — set `milestone`, `status: ready_for_planning`, update `progress` counts.
3. Create `.planning/vX.Y-MILESTONE-SUMMARY.md` — set `Status: planned`, list included phases.
4. Update `.planning/REQUIREMENTS.md` — scope file header to `milestone \`vX.Y\``, add new REQ-IDs.
5. **Run the consistency gate:** `maestro planning check`
   - Must exit 0 before any phase planning begins.
   - CI also runs this gate on every push/PR via `.github/workflows/planning-consistency.yml`.

## Closing a Milestone

1. Mark all included phases `[x]` in `.planning/ROADMAP.md` and update the progress table rows to `Complete`.
2. Update `.planning/STATE.md` — set `status: completed`, update `progress.completed_phases` to match.
3. Update `.planning/vX.Y-MILESTONE-SUMMARY.md` — set `Status: complete`, add phase evidence paths for all included phases.
4. **Run the consistency gate:** `maestro planning check`
   - Must exit 0 before tagging the release or opening the next milestone.

## Consistency Gate Reference

The gate validates alignment across four artifact types:

- `.planning/ROADMAP.md` — phase list completion status and progress table row counts
- `.planning/STATE.md` — milestone name, progress counts, evidence paths for included phases
- `.planning/vX.Y-MILESTONE-SUMMARY.md` — milestone mention, references to phase evidence files
- `.planning/REQUIREMENTS.md` — milestone scope alignment with STATE.md

If any artifact is missing or mismatched, the gate prints the error(s) and exits non-zero.

CI workflow: `.github/workflows/planning-consistency.yml`
CLI command: `maestro planning check [--root PATH]`
