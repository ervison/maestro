# Maestro

Maestro is a CLI-driven AI agent that executes complex software engineering tasks using file system tools and shell commands.

## Usage

### `maestro run`

Run the agent with a prompt:

```bash
maestro run "build a REST API with tests"
maestro run --multi "build a REST API with tests and docs"
```

### `maestro discover`

Run the SDLC discovery planner to generate structured project artifacts:

```bash
maestro discover "<project description>"
maestro discover --workdir ./my-project "Build a CRM platform"
maestro discover --model chatgpt/gpt-4o "Build a CRM platform"
maestro discover --brownfield "Extend existing API with new endpoints"
maestro discover --no-reflect "Quick prototype spec"
maestro discover --sprints "Build a fintech platform"
```

Options:
- `--workdir PATH` — Working directory for spec/ output (default: current directory)
- `--model PROVIDER/MODEL` — Model to use (e.g. `chatgpt/gpt-4o`)
- `--brownfield` — Enable brownfield codebase scan (opt-in)
- `--gaps-port INT` — Port for the gap questionnaire web UI (default: 4041)
- `--no-browser` — Do not auto-open browser for gap questionnaire
- `--no-reflect` — Skip iterative quality evaluation after artifact generation
- `--reflect-max-cycles INT` — Maximum reflect loop iterations (default: 5)
- `--sprints` — Use sprint-based DAG execution with gate reviews (opt-in, experimental)

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

## Authentication

```bash
maestro auth login chatgpt
maestro auth login github-copilot
maestro auth status
maestro auth logout chatgpt
```

## Models

```bash
maestro models
maestro models --provider github-copilot
maestro models --check
```
