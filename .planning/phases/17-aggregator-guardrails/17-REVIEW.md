---
phase: 17-aggregator-guardrails
reviewed: 2026-04-24T15:05:56Z
depth: deep
files_reviewed: 42
files_reviewed_list:
  - AGENTS.md
  - maestro/agent.py
  - maestro/auth.py
  - maestro/cli.py
  - maestro/config.py
  - maestro/domains.py
  - maestro/models.py
  - maestro/multi_agent.py
  - maestro/planner/__init__.py
  - maestro/planner/node.py
  - maestro/planner/schemas.py
  - maestro/planner/validator.py
  - maestro/planning.py
  - maestro/providers/__init__.py
  - maestro/providers/base.py
  - maestro/providers/chatgpt.py
  - maestro/providers/copilot.py
  - maestro/providers/registry.py
  - maestro/sdlc/__init__.py
  - maestro/sdlc/gaps_server.py
  - maestro/sdlc/generators.py
  - maestro/sdlc/harness.py
  - maestro/sdlc/prompts.py
  - maestro/sdlc/reflect.py
  - maestro/sdlc/schemas.py
  - maestro/sdlc/writer.py
  - pyproject.toml
  - run-phase.sh
  - script.py
  - tests/test_aggregator_guardrails.py
  - tests/test_cli_discover.py
  - tests/test_cli_planning.py
  - tests/test_copilot_smoke.py
  - tests/test_dashboard_integration.py
  - tests/test_planning_consistency.py
  - tests/test_provider_install_smoke.py
  - tests/test_sdlc_gaps_server.py
  - tests/test_sdlc_generators.py
  - tests/test_sdlc_harness.py
  - tests/test_sdlc_reflect.py
  - .github/workflows/planning-consistency.yml
  - .opencode/plugins/graphify.js
findings:
  critical: 2
  warning: 3
  info: 0
  total: 5
status: issues_found
---

# Phase 17: Code Review Report

**Reviewed:** 2026-04-24T15:05:56Z
**Depth:** deep
**Files Reviewed:** 42
**Status:** issues_found

## Summary

Reviewed the multi-agent guardrail work plus adjacent provider/SDLC/runtime paths. The main problems are a workdir escape in the shell tool, a broken LLM gap-enrichment call path that silently degrades to heuristics, an HTTP server cleanup leak, duplicated test definitions that mask test intent, and an overly complex CLI dispatcher.

## Critical Issues

### CR-01: `execute_shell` bypasses the worker path guard

**File:** `maestro/tools.py:135-148`
**Issue:** `execute_shell()` runs arbitrary text with `shell=True` and only sets `cwd=workdir`. That does not enforce the repo's required path guard inside workers: commands can still target absolute paths or traverse outside the workdir (`rm -rf /tmp/x`, `cat /etc/passwd`, `rm ../file`). This is a direct escape hatch around `resolve_path()`.
**Fix:** Disable free-form shell execution for workers until it is sandboxed, or replace it with structured commands executed with `shell=False` and per-argument path validation.

```python
def execute_shell(args: dict, workdir: Path) -> dict:
    return {
        "error": "execute_shell is disabled because it bypasses the workdir path guard"
    }
```

### CR-02: `main()` has critical cyclomatic complexity

**File:** `maestro/cli.py:56-553`
**Issue:** `main()` has CC well above 20 by static count (top-level command dispatch plus nested auth/models/run/planning branches). At this size it is hard to reason about and easy to break when adding new commands or compatibility branches.
**Fix:** Split each subcommand into dedicated handlers and use a small dispatch layer in `main()`.

```python
def main() -> None:
    args = build_parser().parse_args()
    handlers = {
        "auth": _handle_auth,
        "login": _handle_legacy_login,
        "logout": _handle_legacy_logout,
        "models": _handle_models,
        "status": _handle_status,
        "run": _handle_run,
        "discover": _handle_discover,
        "planning": _handle_planning,
    }
    handlers.get(args.command, _print_help)(args)
```

## Warnings

### WR-01: Gap enrichment sends the wrong message type to providers

**File:** `maestro/sdlc/gaps_server.py:222-230`
**Issue:** `_llm_enrich()` builds `messages` as raw dicts, but the real provider implementations expect `maestro.providers.base.Message` objects. With ChatGPT/Copilot this path raises inside `provider.stream()`, and `enrich_gap_items()` catches the exception and silently falls back to heuristic options. Result: the advertised LLM enrichment path never actually works with real providers.
**Fix:** Build provider-neutral `Message` objects before calling `provider.stream()`.

```python
from maestro.providers.base import Message

messages = [
    Message(role="system", content=_ENRICH_SYSTEM),
    Message(
        role="user",
        content=_ENRICH_USER_TMPL.format(context=context, question=item.question),
    ),
]
```

### WR-02: `GapsServer.stop()` does not close the listening socket

**File:** `maestro/sdlc/gaps_server.py:325-329`
**Issue:** `stop()` calls `shutdown()` but never calls `server_close()`. Repeated questionnaire runs can leave sockets/file descriptors hanging around longer than necessary and can keep ports bound unexpectedly.
**Fix:** Close the server explicitly and, ideally, join the serving thread.

```python
def stop(self) -> None:
    if self._server:
        self._server.shutdown()
        self._server.server_close()
        self._server = None
```

### WR-03: Duplicate test classes silently disable half of the guardrail tests

**File:** `tests/test_aggregator_guardrails.py:11-272, 275-536`
**Issue:** The module contains two copies of the same test classes. In Python, the later class definitions overwrite the earlier ones, so the first half of the file becomes dead code. That reduces test reliability and can hide mistakes in the overwritten copy.
**Fix:** Keep one canonical copy of each test class and delete the duplicate block.

```python
# Keep a single copy of:
class TestAggregatorGuardrail:
    ...

class TestSchedulerRouteIntegration:
    ...

class TestRunMultiAgentGuardrailIntegration:
    ...
```

---

_Reviewed: 2026-04-24T15:05:56Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: deep_
