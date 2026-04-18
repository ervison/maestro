---
status: complete
phase: 07-github-copilot-provider
source:
  - .planning/phases/07-github-copilot-provider/07-01-SUMMARY.md
started: 2026-04-18T20:53:09Z
updated: 2026-04-18T20:53:09Z
---

## Current Test

[testing complete]

## Tests

### 1. Copilot auth login flow starts from CLI
expected: `maestro auth login github-copilot` dispatches to provider login flow, shows device URL/code, and persists token.
result: pass

### 2. Stream request uses Copilot endpoint and required headers
expected: Provider sends POST to `https://api.githubcopilot.com/chat/completions` with `Authorization`, `x-initiator`, and `Openai-Intent`.
result: pass

### 3. Neutral types convert to and from OpenAI wire format
expected: `Message`/`Tool` values are converted on send and parsed back on receive (including tool calls).
result: pass

### 4. OAuth polling handles slow_down and authorization_pending correctly
expected: `slow_down` increments interval by 5s and `authorization_pending` continues polling.
result: pass

### 5. Models CLI supports provider-filtered Copilot listing
expected: `maestro models --provider github-copilot` is accepted and lists Copilot model IDs.
result: issue
reported: "CLI rejects --provider with: unrecognized arguments: --provider github-copilot"
severity: major

### 6. Copilot is usable as an alternative runtime provider
expected: `maestro run --model github-copilot/gpt-4o \"...\"` should route to Copilot provider stream path.
result: issue
reported: "CLI returns: Provider 'github-copilot' is discoverable but not runnable yet; Phase 5 must wire provider.stream()"
severity: blocker

### 7. Auth state is false without token
expected: `is_authenticated()` returns `False` when no Copilot token is stored.
result: pass

### 8. Copilot model catalog is available
expected: `list_models()` returns known Copilot IDs (`gpt-4o`, `gpt-4o-mini`, `gpt-4-turbo`, `gpt-3.5-turbo`).
result: pass

## Summary

total: 8
passed: 6
issues: 2
pending: 0
skipped: 0
blocked: 0

## Gaps

- truth: "`maestro models --provider github-copilot` lists Copilot model IDs"
  status: failed
  reason: "User reported: CLI rejects --provider with unrecognized argument error"
  severity: major
  test: 5
  root_cause: "CLI parser has no --provider option on models subcommand"
  artifacts:
    - path: "maestro/cli.py"
      issue: "models parser only accepts --check and --refresh"
  missing:
    - "Add --provider argument to models subcommand"
    - "Wire provider-specific model listing path"
  debug_session: ""

- truth: "Users can use GitHub Copilot as an alternative provider"
  status: failed
  reason: "User reported: run command explicitly rejects non-chatgpt providers"
  severity: blocker
  test: 6
  root_cause: "Runtime guard in run command hard-blocks provider.id != chatgpt"
  artifacts:
    - path: "maestro/cli.py"
      issue: "Raises RuntimeError before provider.stream() can execute"
  missing:
    - "Remove legacy non-chatgpt runtime guard"
    - "Allow run path to execute provider.stream() for Copilot"
  debug_session: ""
