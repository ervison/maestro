---
phase: 17
fixed_at: 2026-04-24T00:00:00Z
review_path: /home/ervison/Documents/PROJETOS/labs/timeIA/worktrees/phase-17/17-REVIEW.md
iteration: 3
findings_in_scope: 4
fixed: 4
skipped: 0
status: all_fixed
---

# Phase 17: Code Review Fix Report

**Fixed at:** 2026-04-24T00:00:00Z
**Source review:** 17-REVIEW.md
**Iteration:** 3

**Summary:**
- Findings in scope: 4
- Fixed: 4
- Skipped: 0

## Fixed Issues

### CR-01: Reflect loop can overwrite files outside `spec/`

**Files modified:** `maestro/sdlc/reflect.py`
**Commit:** 24542cd
**Applied fix:** In `_apply_patches()`, replaced the bare `target = spec_dir / fname` with a resolved path guard: resolves both the candidate target and `spec_dir`, then calls `target.relative_to(spec_root)` and raises `RuntimeError` if the patch target would escape the spec directory. The `exists()` check is now performed on the already-resolved `target`.

### WR-01: Planner can pair a model with the wrong provider

**Files modified:** `maestro/planner/node.py`
**Commit:** ebaf09b
**Applied fix:** Replaced the unconditional `provider = runtime_provider if runtime_provider is not None else resolved_provider` with an id-match guard: `runtime_provider` is only reused when `runtime_provider.id == resolved_provider.id`, otherwise `resolved_provider` is used. This mirrors the aggregator pattern and ensures agent-specific config (e.g. `agent.planner.model=github-copilot/...`) is honoured when the caller injected a different provider.

### WR-02: Gap questionnaire endpoint allows cross-origin reads

**Files modified:** `maestro/sdlc/gaps_server.py`
**Commit:** a615e8a
**Applied fix:** Removed the `self.send_header("Access-Control-Allow-Origin", "*")` line from `_serve_gaps_json()`. Added a comment noting this is a localhost-only UI that does not need wildcard CORS exposure.

### WR-03: `main()` has elevated cyclomatic complexity

**Files modified:** `maestro/cli.py`
**Commit:** f4241a7
**Applied fix:** Replaced the 9-branch `if/elif` command cascade in `main()` with a `handlers` dispatch dict keyed by command name. Each entry is a zero-arg lambda capturing the required args. Added a dedicated `_handle_planning(args, planning_p)` helper (extracted from the inline `if args.planning_command == "check"` block) so the dispatch table entry is a simple `lambda: _handle_planning(args, planning_p)`. Cyclomatic complexity of `main()` drops to CC≈3.

---

_Fixed: 2026-04-24T00:00:00Z_
_Fixer: the agent (gsd-code-fixer)_
_Iteration: 3_
