# Memória de Sessão — Maestro SDLC v2

**Data:** 2026-04-25  
**Propósito:** Arquivo de handoff para continuar o trabalho em nova sessão.

---

## Estado Atual do Projeto

### O que é Maestro
CLI-driven AI agent que executa tarefas de engenharia de software. Foi estendido de single-agent para multi-agent com suporte a DAG paralelo (LangGraph Send API). O subcomando `maestro discover` gera pacotes de especificação SDLC completos.

### Versão / Branch
- Branch: `main`
- Último commit relevante: `bb317f2` (fix harness sprint mode)
- Testes passando: **104 testes SDLC + CLI** (157 total, 2 falham — veja seção "Falhas Conhecidas")

---

## Sessão 2026-04-25 — Consistência de Artefatos (Cross-Artifact Coherence)

### Problema Identificado
Análise manual dos artefatos gerados revelou **3 problemas críticos de consistência**:

1. **Conflito de limite de upload de imagem (14 NFR ↔ 09 + 05 + 06)** — NFR definia 5 MB, API-contracts/functional-spec/business-rules usavam 2 MB. NFR é a fonte normativa mas não era injetado como contexto nos downstream.
2. **Contradição estrutural na auth-matrix (11 ↔ 05 + 06)** — auth-matrix restringia veterinários a read-only; functional-spec permitia create/edit/delete para usuários autenticados. Gerados em paralelo no Sprint 3 sem ver um ao outro.
3. **API-contracts sem controle de papel por endpoint (09 ↔ 11)** — endpoints POST/PUT/DELETE permitiam qualquer token JWT sem distinção de papel.

**Inconsistências leves:** stack decisions espalhados (PRD/func-spec em vez de ADRs); `data_model` sem campo `role`; acceptance-criteria sem cenários de controle de acesso.

### Root Cause
Dois vetores:
- `generators.py` passava apenas `request.prompt` para cada artefato — sem contexto dos upstream já gerados
- Gates do reviewer validavam estrutura/presença mas não faziam cross-check de valores concretos entre documentos

### Solução Implementada

#### `maestro/sdlc/prompts.py`
Prompts reformulados com instruções explícitas de ancoragem:
- `NFR`: declarado como fonte normativa única para thresholds numéricos
- `API_CONTRACTS`: instrução `CRITICAL` para usar exatamente os valores do NFR e implementar controle de papel por endpoint
- `AUTH_MATRIX`: instrução `CRITICAL` para ser consistente com o que `functional-spec` define
- `DATA_MODEL`: instrução `CRITICAL` para incluir campo `role` na entidade User
- `BUSINESS_RULES`: proibido inventar valores — copiar do PRD/NFR
- `FUNCTIONAL_SPEC`: definir papéis e permissões explicitamente (fonte para auth-matrix)
- `ADRS`: tecnologia de stack deve ir aqui, não dispersa em outros artefatos
- `ACCEPTANCE_CRITERIA` e `TEST_PLAN`: cobertura obrigatória de papéis e thresholds NFR

#### `maestro/sdlc/generators.py`
- Nova função `_build_user_message()` injeta artefatos upstream como seção `## Prior Artifacts (use as authoritative source)` no prompt de usuário
- `generate_artifact()` aceita `prior_artifacts: list[SDLCArtifact] | None = None`

#### `maestro/sdlc/harness.py`
- `_run_with_sprints()` mantém `artifact_map: dict[ArtifactType, SDLCArtifact]` durante a execução
- Novo método estático `_get_prior_artifacts()` consulta o DAG de deps de `sprints.py` e retorna os artefatos já gerados como contexto
- `_generate_artifact()` aceita e repassa `prior_artifacts`

#### `maestro/sdlc/reviewer.py`
- Gates 3, 4, 5, 6 reforçados com instruções `CROSS-CHECK` explícitas:
  - Gate 3: compara thresholds numéricos entre business-rules e NFR
  - Gate 4: verifica consistência de papéis entre UX-spec e func-spec
  - Gate 5: verifica role/permission match entre auth-matrix e func-spec, verifica campo `role` no data-model, verifica thresholds NFR nos contratos de API
  - Gate 6: exige cenários de controle de acesso por papel nos acceptance-criteria

#### `tests/test_sdlc_harness.py`
- Todos os `fake_generate` e closures `capturing_gen`/`counting_gen` atualizados para aceitar `prior_artifacts=None`

### Resultado
- **104 testes passando** — zero regressions
- Modo `--sprints` agora injeta artefatos upstream como contexto real no LLM call de cada artefato downstream
- O reviewer agora detecta e reporta discrepâncias de valores concretos entre documentos

---

## O Que Foi Feito Nesta Sessão (SDLC Discovery v2)

### Contexto
O objetivo foi evoluir o `maestro discover` de geração sequencial de 13 artefatos para um sistema DAG baseado em 6 sprints com 14 artefatos, quality gates e reviewer LLM.

### Waves Implementadas

| Wave | Commit | O que foi feito |
|------|--------|-----------------|
| Wave 1 | `f3cc713` | `ArtifactType.NFR` como 14º tipo de artefato; prompt NFR; todas as refs 13→14 atualizadas nos testes |
| Wave 2 | `fbe35de` | `maestro/sdlc/sprints.py` (6 sprints + DAG); dataclasses `GateResult` e `SprintResult` |
| Wave 3 | `65442d0` | `maestro/sdlc/reviewer.py` com validação LLM dos gates (6 prompts) |
| Wave 4 | `52eea20` | Harness sprint DAG (`_run_with_sprints`, `_run_sequential`, `_run_gate`); campo `gate_failures` em `DiscoveryResult`; 11ª dimensão NFR no `ReflectLoop` |
| Wave 5 | `a8240f1` | Flag `--sprints` no CLI; banner dinâmico de artefatos; exit code 2 em gate failures; docs README |
| Wave 6 | `2acbd86`, `aaffc0a` | Verificação de integração — todos os 11 critérios de aceite ✅ |
| Fix matriz | `7d7ad25` | `BUSINESS_RULES` deps `(PRD,)` somente (co-evolução, não bloqueante); `ARTIFACT_ORDER` reordenado |
| Bug fix | `bb317f2` | `_ensure_no_open_markers` ficava disparando em artefatos pré-gap (briefing); adicionado flag `gaps_resolved` |

### Verificação Final (Esta Sessão)
- Rodada completa com `maestro discover --sprints --model github-copilot/gpt-4o --no-reflect`
- **14 artefatos gerados** e escritos em `testes/spec/` incluindo `14-nfr.md`
- Gaps questionnaire abriu em `localhost:4041` e bloqueou corretamente até resposta
- Gate failures são warn-only (exit code 2), não abortam
- `ERR_CONNECTION_REFUSED` reportado anteriormente era falso alarme — o usuário acessava a URL após o servidor já ter encerrado (respostas submetidas)

---

## Arquitetura SDLC Atual

### Arquivos Principais

| Arquivo | Responsabilidade |
|---------|-----------------|
| `maestro/sdlc/schemas.py` | `ArtifactType` (14 membros), `ARTIFACT_ORDER`, `ARTIFACT_FILENAMES`, `GateResult`, `SprintResult`, `DiscoveryResult` |
| `maestro/sdlc/sprints.py` | 6 `SprintDef` com deps DAG; `get_ready_artifacts()`, `all_sprint_artifacts()`, `validate_sprint_coverage()` |
| `maestro/sdlc/harness.py` | `DiscoveryHarness`: `_run_sequential()` (compat), `_run_with_sprints()` (novo), `_run_gate()`, `_resolve_gaps()` |
| `maestro/sdlc/reviewer.py` | `Reviewer` class; `GATE_PROMPTS` dict (6 entradas) |
| `maestro/sdlc/reflect.py` | `DIMENSIONS` (11 entradas, inclui NFR) |
| `maestro/sdlc/gaps_server.py` | `GapsServer`, `resolve_gaps()`, `parse_gaps()`, `enrich_gap_items()` |
| `maestro/sdlc/generators.py` | `generate_artifact()` — usa `PROMPTS[artifact_type]` |
| `maestro/sdlc/prompts.py` | Prompts de todos os 14 artefatos |
| `maestro/cli.py` | Flag `--sprints`, exit code 2, banner dinâmico |

### Ordem dos Artefatos (ARTIFACT_ORDER)
```
1  briefing          → 01-briefing.md
2  hypotheses        → 02-hypotheses.md
3  gaps              → 03-gaps.md
4  prd               → 04-prd.md
5  functional_spec   → 05-functional-spec.md
6  business_rules    → 06-business-rules.md
7  nfr               → 14-nfr.md        ← arquivo fora de sequência numérica (intencional)
8  adrs              → 12-adrs.md
9  ux_spec           → 08-ux-spec.md
10 auth_matrix       → 11-auth-matrix.md
11 data_model        → 10-data-model.md
12 api_contracts     → 09-api-contracts.md
13 acceptance_criteria → 07-acceptance-criteria.md
14 test_plan         → 13-test-plan.md
```

### Sprints
| Sprint | Nome | Artefatos |
|--------|------|-----------|
| 1 | Descoberta | briefing → hypotheses + gaps (paralelo) |
| 2 | Definição | prd |
| 3 | Especificação | functional_spec + business_rules + nfr + adrs (paralelo) |
| 4 | Experiência | ux_spec |
| 5 | Realização Técnica | auth_matrix → data_model → api_contracts (sequencial por deps) |
| 6 | Validação | acceptance_criteria → test_plan |

---

## Decisões de Design Tomadas

1. **`BUSINESS_RULES` deps = `(PRD,)` apenas** — co-evolui com `FUNCTIONAL_SPEC` mas não é bloqueado por ele (matriz formal v2: "não como pré-requisito bloqueante")
2. **`ADRS` no sprint 3** com dep `(PRD,)` — comportamento "continuous track" não modelável no DAG de sprints; aceito como limitação conhecida
3. **`DATA_MODEL` dep inclui `ADRS` e `NFR`** — grafos `10 → 09` e `14 → 10` da matriz formal
4. **`--sprints` é opt-in** — `maestro discover` sem flag mantém comportamento sequencial legado (zero regressions)
5. **Gate failures são warn-only** — exit code 2, não abortam a geração
6. **`gaps_resolved` flag** — `_ensure_no_open_markers` só dispara depois do artefato GAPS ser processado

---

## Falhas Conhecidas (Não Bloqueantes)

| Teste | Motivo |
|-------|--------|
| `test_planning_check_command_exits_zero_when_consistent` | Planning consistency gate detecta drift — roadmap/milestone precisam ser atualizados com fases 18-20 |
| `test_repository_planning_artifacts_are_currently_consistent` | Mesma causa acima |

Esses 2 testes falham porque as fases 18-20 existem no roadmap mas não têm artefatos de planning completos. Não são bugs do SDLC v2.

---

## Próximas Fases no Roadmap

| Fase | Nome | Descrição |
|------|------|-----------|
| 18 | Milestone Evidence & Traceability Closure | Reconciliar artefatos de milestone e adicionar evidências de verificação faltantes para fases 14-17 |
| 19 | Planning Drift Detection Hardening | Fazer o gate de consistência falhar em drift real do milestone e enforçar em automação |
| 20 | Copilot Release Path E2E Smoke Gate | Verificar CLI e provider-registry do Copilot end-to-end |

---

## Como Continuar o Trabalho

### Contexto Técnico
- Stack: Python 3.12.7, LangGraph 1.1.6, httpx 0.28.1, Pydantic 2.11.7
- Instalar: `pip install -e ".[dev]"` no root do projeto
- Rodar testes SDLC: `pytest tests/test_sdlc_*.py tests/test_cli.py`
- Rodar todos: `pytest tests/` (2 falhas esperadas em planning consistency)

### Testar o discover manualmente
```bash
maestro discover "descrição do projeto" \
  --workdir ./output \
  --model github-copilot/gpt-4o \
  --no-reflect \
  --sprints
```

### Para retomar as fases 18-20
Ver `.planning/ROADMAP.md` para detalhes de cada fase.  
O workflow padrão é `/gsd-plan-phase` → `/gsd-execute-phase`.

---

## Referências

- Matriz formal de dependências: `docs/Matriz_formal_de_dependência_v2.md`
- Roadmap completo: `.planning/ROADMAP.md`
- Plano de waves do SDLC v2: `docs/superpowers/plans/2026-04-24-sdlc-discovery-v2.md`
- Stack research: `.planning/research/STACK.md` (via `AGENTS.md`)
