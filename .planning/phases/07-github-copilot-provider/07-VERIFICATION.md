---
phase: 07-github-copilot-provider
verified: 2026-04-18T20:53:09Z
status: gaps_found
score: 6/8 must-haves verified
overrides_applied: 0
gaps:
  - truth: "`maestro models --provider github-copilot` lists available Copilot model IDs"
    status: failed
    reason: "CLI does not support --provider argument on models subcommand"
    artifacts:
      - path: "maestro/cli.py"
        issue: "argparse rejects --provider github-copilot"
    missing:
      - "Add --provider option to models subcommand"
      - "Wire provider-specific model listing to CopilotProvider.list_models()"
  - truth: "Users can use GitHub Copilot as an alternative provider"
    status: failed
    reason: "run command contains legacy guard rejecting non-chatgpt providers"
    artifacts:
      - path: "maestro/cli.py"
        issue: "Raises RuntimeError when provider.id != chatgpt"
    missing:
      - "Remove non-chatgpt runtime block in run command"
      - "Execute provider.stream() path for github-copilot models"
---

# Phase 7: GitHub Copilot Provider Verification Report

**Phase Goal:** Users can authenticate with GitHub Copilot via device code OAuth and use it as an alternative provider
**Verified:** 2026-04-18T20:53:09Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `maestro auth login github-copilot` initiates device-code flow, shows code+URL, stores token | ✓ VERIFIED | `cli.py` routes non-chatgpt auth login to `provider.login()` (lines 89-94); login behavior covered by tests (`test_login_prints_device_code`, `test_login_stores_token_on_success`). |
| 2 | `CopilotProvider.stream()` sends requests to Copilot API with required headers | ✓ VERIFIED | `copilot.py` posts to `https://api.githubcopilot.com/chat/completions` and sets `Authorization`, `x-initiator`, `Openai-Intent` (lines 119-134); header test passes. |
| 3 | Neutral `Tool`/`Message` types are converted to/from wire format | ✓ VERIFIED | `_convert_messages_to_wire`, `_convert_tools_to_wire`, tool-call parsing in `stream()` (lines 103-218, 316-378); conversion tests pass. |
| 4 | `slow_down` increments polling interval by +5s; `authorization_pending` continues | ✓ VERIFIED | `current_interval += 5` on `slow_down` and continue on `authorization_pending` (lines 274-283); tested in login tests. |
| 5 | `maestro models --provider github-copilot` lists available Copilot model IDs | ✗ FAILED | Behavioral spot-check failed: `python -m maestro.cli models --provider github-copilot` → `unrecognized arguments: --provider github-copilot`. |
| 6 | `is_authenticated()` returns `False` when no Copilot token exists | ✓ VERIFIED | `return bool(creds and creds.get("access_token"))` in `copilot.py` line 308; unit tests cover no-creds/malformed-creds. |
| 7 | `list_models()` returns Copilot model IDs | ✓ VERIFIED | `copilot.py` returns copy of `COPILOT_MODELS` (lines 63-65); spot-check prints expected list. |
| 8 | Users can use Copilot as alternative provider at runtime (`maestro run --model github-copilot/...`) | ✗ FAILED | Behavioral spot-check failed: `python -m maestro.cli run --model github-copilot/gpt-4o "hello"` returns `Provider 'github-copilot' is discoverable but not runnable yet`. |

**Score:** 6/8 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `maestro/providers/copilot.py` | CopilotProvider implementation | ✓ VERIFIED | Exists, 381 lines, protocol/stream/login/model methods implemented and tested. |
| `tests/test_copilot_provider.py` | Unit and integration tests for Copilot provider | ✓ VERIFIED | Exists, 877 lines, 28 passed + 1 skipped in dedicated run. |
| `pyproject.toml` | Entry point registration | ✓ VERIFIED | `github-copilot = "maestro.providers.copilot:CopilotProvider"` present. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `maestro/providers/copilot.py` | `maestro/auth.py` | `auth.get('github-copilot')`, `auth.set('github-copilot', ...)` | ✓ WIRED | Calls found in provider (lines 91, 298, 307). |
| `maestro/providers/copilot.py` | `https://api.githubcopilot.com/chat/completions` | `aconnect_sse(..., "POST", ...)` | ✓ WIRED | URL assembled from `COPILOT_API_BASE` and `/chat/completions` in stream method. |
| `tests/test_copilot_provider.py` | `maestro/providers/copilot.py` | `from maestro.providers.copilot import ...` | ✓ WIRED | Multiple direct imports across test suite. |
| `maestro/cli.py` | Copilot model listing path | `models --provider github-copilot` | ✗ NOT_WIRED | No `--provider` arg defined for models parser. |
| `maestro/cli.py` | Provider runtime execution path | `run --model github-copilot/...` | ✗ NOT_WIRED | Explicit guard blocks non-chatgpt provider execution (lines 208-212). |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `maestro/providers/copilot.py` | `text_parts` / final assistant `Message.content` | SSE `choices[0].delta.content` from Copilot API | Yes | ✓ FLOWING |
| `maestro/providers/copilot.py` | stored `access_token` | OAuth device token endpoint JSON (`access_token`) | Yes | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Protocol compliance | `python -c "...isinstance(CopilotProvider(), ProviderPlugin)..."` | `Protocol check passed` | ✓ PASS |
| Provider discovery | `python -c "...get_provider('github-copilot')..."` | `Found: github-copilot - GitHub Copilot` | ✓ PASS |
| Copilot tests | `pytest tests/test_copilot_provider.py -q` | `28 passed, 1 skipped` | ✓ PASS |
| Full regression | `pytest tests -q` | `234 passed, 1 skipped` | ✓ PASS |
| Models provider filter | `python -m maestro.cli models --provider github-copilot` | `unrecognized arguments` | ✗ FAIL |
| Runtime usage as alternative provider | `python -m maestro.cli run --model github-copilot/gpt-4o "hello"` | `discoverable but not runnable yet` | ✗ FAIL |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| COPILOT-01 | 07-01-PLAN.md | CopilotProvider implements ProviderPlugin | ✓ SATISFIED | Runtime protocol check passes. |
| COPILOT-02 | 07-01-PLAN.md | Neutral type ↔ wire format conversion | ✓ SATISFIED | Conversion and stream tool-call tests pass. |
| COPILOT-03 | 07-01-PLAN.md | Copilot endpoint + required headers | ✓ SATISFIED | Endpoint/header code present; header test passes. |
| COPILOT-04 | 07-01-PLAN.md | list_models returns Copilot IDs | ✓ SATISFIED | `list_models()` and tests validated. |
| COPILOT-05 | 07-01-PLAN.md | is_authenticated false when no token | ✓ SATISFIED | `bool(creds and creds.get("access_token"))` + tests. |
| AUTH-04 | 07-01-PLAN.md | Device-code OAuth login via Copilot | ✓ SATISFIED | `login()` implements device code polling/storage path; tests cover flow branches. |
| AUTH-07 | 07-01-PLAN.md | slow_down increments polling interval | ✓ SATISFIED | `current_interval += 5`; tested by `test_login_handles_slow_down`. |

Orphaned requirements for Phase 7: none (all Phase 7 requirement IDs are declared in plan frontmatter).

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `maestro/cli.py` | 208-212 | Hard-coded non-chatgpt runtime block | 🛑 Blocker | Prevents Copilot from being usable as alternative provider (phase goal miss). |
| `maestro/cli.py` | 69-75 | Missing `--provider` option on `models` subcommand | ⚠️ Warning | Breaks roadmap success criterion for provider-filtered model listing. |
| `tests/test_copilot_provider.py` | 869-877 | Placeholder regression-guard test (`pass`) | ℹ️ Info | Not harmful, but does not validate regressions despite test name. |
| `pyproject.toml` | 27-29 | Missing registration for `integration` pytest marker | ℹ️ Info | Emits `PytestUnknownMarkWarning` during test runs. |

### Human Verification Required

1. **Real GitHub Copilot OAuth round-trip**

**Test:** Run `maestro auth login github-copilot` with a real GitHub account and complete device-code authorization.
**Expected:** URL/code shown, login completes, token persisted in auth store.
**Why human:** Requires external account authorization and interactive browser/device flow.

2. **Live Copilot streaming output quality**

**Test:** Run `CopilotProvider.stream()` with a real token and verify returned streamed content/tool-call behavior on live API.
**Expected:** Incremental text deltas and final assistant `Message` match real API output.
**Why human:** External network/service behavior and account entitlements are environment-dependent.

### Gaps Summary

Phase 7 implementation is solid at the provider module and test layer, but goal-level wiring is incomplete in CLI integration. Two blocking truths fail: provider-filtered model listing (`maestro models --provider ...`) is not implemented, and runtime execution still hard-blocks non-chatgpt providers, so Copilot cannot be used as an alternative provider from `maestro run`. Until these CLI links are wired, Phase 7 goal is not achieved.

---

_Verified: 2026-04-18T20:53:09Z_
_Verifier: the agent (gsd-verifier)_
