---
slug: sdlc-ux-fixes
date: 2026-04-22
status: in-progress
---

# SDLC Discovery UX Fixes

Fix three issues reported after testing `maestro discover`:

1. **Flow perception**: User expects gaps (03) to block artifacts 04–13. Current behavior is correct (gaps are content, not blockers), but needs UX communication.
2. **No visible progress**: `write_artifacts()` is called once at the end — files only appear after all 13 LLM calls finish. Fix: write each artifact to disk immediately after generation.
3. **LLM usage unclear**: No indication in CLI output that a real LLM is being called. Fix: print per-artifact progress to stderr in real time.

## Files Modified

- `maestro/sdlc/harness.py` — write each artifact immediately after generation; print progress to stderr
- `maestro/cli.py` — improve progress messaging; clarify gaps are not blockers
- `tests/test_sdlc_harness.py` — verify incremental write behavior
