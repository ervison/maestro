# Wave 5 — CLI Wiring, Gate Failure Policy, and Documentation

## Progress

| Microtask | Description | Status |
|-----------|-------------|--------|
| 5.1 | Add `--sprints` flag to `discover` subparser | `[ ]` |
| 5.2 | Implement exit code 2 for gate failures | `[ ]` |
| 5.3 | Add CLI exit-code-2 unit test | `[ ]` |
| 5.4 | Update user-facing documentation | `[ ]` |
| 5.5 | Run full test suite | `[ ]` |
| 5.6 | Commit Wave 5 | `[ ]` |

> Update status to `[x]` when a microtask is complete, `[~]` when in progress, `[!]` if blocked.

---

**Goal:** Wire `--sprints` flag into `maestro/cli.py`; implement warn-only gate failure policy
with exit code 2; update user-facing documentation.

**Why this wave fifth:** CLI wiring depends on the harness being complete (Wave 4). Gate
failure policy (`exit code 2`) depends on `DiscoveryResult.gate_failures` being populated
(Wave 4). Documentation describes features that must exist before documenting them.

**Dependencies:** Waves 1–4 complete.

**Files touched:**
- `maestro/cli.py` (add `--sprints` flag, dynamic artifact count banner, `use_sprints` kwarg, exit code 2)
- `README.md` (or `docs/README.md` — whichever contains the `maestro discover` section)
- `tests/test_cli.py` (add exit-code-2 test, or create if absent)

---

## `[ ]` Microtask 5.1 — Add `--sprints` Flag to `discover` Subparser

**File:** `maestro/cli.py`

**Pre-condition:** Wave 4 complete; `DiscoveryHarness` accepts `use_sprints=True`.

**Action:**

1. Locate the `discover` subparser block (around line 165). After the `--reflect-max-cycles` argument, add:
```python
    discover_p.add_argument(
        "--sprints",
        action="store_true",
        default=False,
        help="Use sprint-based DAG execution with gate reviews (opt-in, experimental).",
    )
```

2. Locate the artifact count banner (around line 595). Replace the hardcoded `"Generating 13 artifacts.\n"` string with a dynamic version:
```python
    from maestro.sdlc.schemas import ARTIFACT_FILENAMES

    print(
        f"Starting SDLC discovery using model: {model_id or 'default'}\n"
        f"Generating {len(ARTIFACT_FILENAMES)} artifacts"
        f"{' (sprint mode)' if getattr(args, 'sprints', False) else ''}.\n"
        f"  If gaps are found, a questionnaire will open at http://localhost:{getattr(args, 'gaps_port', 4041)}\n"
        "  Answer all questions and click Submit to continue.\n",
        file=sys.stderr,
        flush=True,
    )
```

3. Locate the `DiscoveryHarness(...)` constructor call (around lines 602–610). Add `use_sprints=getattr(args, "sprints", False)` as the last argument:
```python
    harness = DiscoveryHarness(
        provider=provider,
        model=model_id,
        workdir=request.workdir,
        gaps_port=getattr(args, "gaps_port", 4041),
        open_browser=not getattr(args, "no_browser", False),
        reflect=not getattr(args, "no_reflect", False),
        reflect_max_cycles=getattr(args, "reflect_max_cycles", 5),
        use_sprints=getattr(args, "sprints", False),
    )
```

**Verification:**
```bash
maestro discover --help | grep -E "sprints|reflect-max-cycles"
```
Expected: both `--sprints` and `--reflect-max-cycles` appear in the output.

---

## `[ ]` Microtask 5.2 — Implement Exit Code 2 for Gate Failures

**File:** `maestro/cli.py`

**Pre-condition:** Microtask 5.1 applied; `DiscoveryResult.gate_failures` exists (Wave 4).

**Action:** In the `_handle_discover` function (or equivalent), immediately after `result = harness.run(request)` and the success print, add:

```python
    print(f"\n\u2713 {result.artifact_count} artifacts written to {result.spec_dir}")
    if getattr(result, "gate_failures", None):
        print(
            f"\u26a0 {len(result.gate_failures)} sprint gate(s) failed \u2014 review notes above.",
            file=sys.stderr,
        )
        sys.exit(2)
```

Note: `sys.exit(2)` is distinct from `sys.exit(1)` (used for generation errors), allowing CI to differentiate "run completed but quality gates flagged issues" from "run crashed".

**Verification:** Import and call the module in dry-run — no syntax errors:
```bash
python -c "import maestro.cli; print('OK')"
```

---

## `[ ]` Microtask 5.3 — Add CLI Exit-Code-2 Unit Test

**File:** `tests/test_cli.py` (create if absent, otherwise append)

**Pre-condition:** Microtask 5.2 applied.

**Action:** Add the following test. It patches `DiscoveryHarness.run` to return a `DiscoveryResult` with populated `gate_failures`, then asserts the CLI calls `sys.exit(2)`:

```python
"""CLI tests for gate failure exit code behavior."""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from maestro.sdlc.schemas import (
    ArtifactType,
    ARTIFACT_FILENAMES,
    DiscoveryResult,
    GateResult,
    SDLCArtifact,
    SDLCRequest,
)


def _make_result_with_gate_failures(tmp_path) -> DiscoveryResult:
    """Build a DiscoveryResult that has gate failures."""
    arts = [
        SDLCArtifact(t, ARTIFACT_FILENAMES[t], "# content")
        for t in ArtifactType
    ]
    gate_fail = GateResult(sprint_id=1, passed=False, notes="stub fail", issues=["issue"])
    return DiscoveryResult(
        request=SDLCRequest(prompt="x"),
        artifacts=arts,
        spec_dir=str(tmp_path / "spec"),
        gate_failures=[gate_fail],
    )


def test_cli_exits_2_when_gate_failures_present(tmp_path, capsys) -> None:
    """When DiscoveryResult.gate_failures is non-empty, CLI must sys.exit(2)."""
    from maestro.sdlc.harness import DiscoveryHarness

    failing_result = _make_result_with_gate_failures(tmp_path)

    with patch.object(DiscoveryHarness, "run", return_value=failing_result):
        with pytest.raises(SystemExit) as exc_info:
            # Simulate CLI args for discover with --sprints
            import maestro.cli as cli_module
            # Patch sys.argv to simulate: maestro discover --sprints "test"
            with patch.object(sys, "argv", ["maestro", "discover", "--sprints", "--no-reflect", "--no-browser", str(tmp_path), "test prompt"]):
                cli_module.main()

    assert exc_info.value.code == 2, f"expected exit 2, got {exc_info.value.code}"
```

**Verification:** Run `pytest tests/test_cli.py::test_cli_exits_2_when_gate_failures_present -v` — PASS.

---

## `[ ]` Microtask 5.4 — Update User-Facing Documentation

**File:** `README.md` (or `docs/README.md` — whichever contains the `maestro discover` usage section)

**Pre-condition:** Locate the section:
```bash
grep -rn "maestro discover" README.md docs/ 2>/dev/null
```

**Action:** Append the following `### Sprint Mode (Experimental)` section immediately after the existing `maestro discover` usage block:

```markdown
### Sprint Mode (Experimental)

`maestro discover --sprints "<prompt>"` runs the discovery DAG in 6 sprints with
gate reviews between each. Artifacts within a sprint generate in parallel where
the dependency graph allows. Gate failures are reported as warnings and the
process exits with code 2; a future `--strict-gates` flag will add halt-on-fail.

The 6 sprints follow `docs/Matriz_formal_de_dependência_v2.md`:

1. **Descoberta**: BRIEFING → HYPOTHESES, GAPS (parallel after BRIEFING)
2. **Definicao**: PRD
3. **Especificacao**: FUNCTIONAL_SPEC, BUSINESS_RULES, NFR, ADRS (parallel where deps allow)
4. **Experiencia**: UX_SPEC
5. **Realizacao Tecnica**: AUTH_MATRIX → DATA_MODEL → API_CONTRACTS (sequential within sprint)
6. **Validacao**: ACCEPTANCE_CRITERIA → TEST_PLAN (sequential within sprint)

Exit codes:
- `0` — all artifacts generated, all gates passed
- `1` — artifact generation failed
- `2` — all artifacts generated, one or more sprint gates flagged issues
```

**Verification:**
```bash
grep -A 20 "Sprint Mode" README.md
```
Expected: The sprint mode section appears with all 6 sprint descriptions.

---

## `[ ]` Microtask 5.5 — Run Full Test Suite

**Pre-condition:** Microtasks 5.1–5.4 applied.

**Action:**
```bash
pytest tests/ -v
```

**Expected:** ALL PASS — zero regressions; `test_cli_exits_2_when_gate_failures_present` passes; all SDLC tests pass.

---

## `[ ]` Microtask 5.6 — Commit Wave 5

**Pre-condition:** All tests pass.

**Action:**
```bash
git add maestro/cli.py README.md tests/test_cli.py
git commit -m "feat(cli): --sprints flag, dynamic artifact count banner, exit code 2 on gate failures, docs"
```

**Verification:** `git status` shows clean working tree.
