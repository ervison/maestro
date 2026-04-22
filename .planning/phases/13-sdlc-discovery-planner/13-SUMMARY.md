# Phase 13 — Summary

**Phase**: 13-sdlc-discovery-planner
**Status**: COMPLETE
**Date**: 2026-04-22
**Tests added**: 41 new tests (444 total, 403 baseline, zero regressions)

## What was built

`maestro discover "<prompt>"` — a CLI command that generates a complete 13-artifact SDLC specification package from a plain-language project description.

## Files created

| File | Purpose |
|------|---------|
| `maestro/sdlc/__init__.py` | Package exports |
| `maestro/sdlc/schemas.py` | ArtifactType (13 members), SDLCRequest, SDLCArtifact, DiscoveryResult |
| `maestro/sdlc/harness.py` | DiscoveryHarness — orchestrates full pipeline |
| `maestro/sdlc/prompts.py` | 13 domain-specific system prompts |
| `maestro/sdlc/generators.py` | generate_artifact() — LLM dispatch per artifact |
| `maestro/sdlc/writer.py` | write_artifacts() — spec/ filesystem I/O |
| `maestro/cli.py` | `discover` subcommand (argparse) |
| `tests/test_sdlc_schemas.py` | 9 schema tests |
| `tests/test_sdlc_harness.py` | 9 harness tests (including brownfield) |
| `tests/test_sdlc_generators.py` | 7 generator + prompt tests |
| `tests/test_sdlc_writer.py` | 6 writer tests |
| `tests/test_cli_discover.py` | 10 CLI integration tests |

## Key design decisions

- **ArtifactType enum** (13 members, slugs match filenames) is the single contract shared by all layers
- **Stub mode**: DiscoveryHarness with `provider=None` generates placeholder content — enables offline testing
- **Fact/hypothesis/gap separation**: Every prompt carries `_BASE` instructions: mark with [HYPOTHESIS], [GAP], never invent
- **Brownfield**: opt-in only via `--brownfield` flag; scans top-level `.py` files and appends to prompt
- **Writer**: I/O separated from orchestration; PermissionError surfaces as RuntimeError (no raw path leaks)
- **Multilingual**: every prompt includes "Respond in the same language as the user's request"

## Verification

```
python -m pytest tests/ -q --tb=no
# 444 passed, 1 skipped

maestro discover --help
# shows discover usage

maestro run --help
# shows run usage unchanged (zero regressions)
```

## Success criteria check

1. ✅ `maestro discover "Crie um cadastro de imóveis"` triggers SDLC planner
2. ✅ All 13 artifact types generated
3. ✅ Planner never invents — [HYPOTHESIS] / [GAP] separation enforced in every prompt
4. ✅ Brownfield mode opt-in via `--brownfield` flag
5. ✅ `maestro run` and `maestro run --multi` completely unaffected
