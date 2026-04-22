---
slug: sdlc-ux-fixes
date: 2026-04-22
status: complete
commit: 4801b24
---

# SDLC Discovery UX Fixes — COMPLETE

Fixed three UX problems reported after testing `maestro discover`.

## Changes

### `maestro/sdlc/harness.py`
- `arun()` now calls `write_artifact(spec_dir, artifact)` immediately after each `_generate_artifact()` call
- Prints `[i/13] Generating <artifact>...` and `[i/13] ✓ <filename>` to stderr in real-time
- Removed batch `write_artifacts()` call at end of pipeline

### `maestro/sdlc/writer.py`
- Added `write_artifact(spec_dir, artifact)` — writes a single artifact immediately
- Kept `write_artifacts()` as batch fallback for direct use

### `maestro/cli.py`
- `_handle_discover()` now prints model name in use before starting
- Explains gaps are recorded in `03-gaps.md` and do not block the pipeline
- Removed monkey-patching of `_generate_artifact` (progress now emitted from harness itself)

### `tests/test_sdlc_harness.py`
- Added `test_harness_writes_each_artifact_incrementally` — verifies one file per write call, in order

## Result

Before: 13 LLM calls complete silently, then all files appear at once.
After: each file appears on disk as soon as its LLM call finishes; stderr shows progress live.
