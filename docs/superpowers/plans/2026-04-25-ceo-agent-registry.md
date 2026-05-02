# CEO + Agent Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Evoluir o Maestro de `domain` fixo para um modelo `CEO + Agent Registry`, preservando o comportamento atual de `maestro run` e a compatibilidade do pipeline multi-agent existente.

**Architecture:** A mudanca sera feita por compatibilidade, nao por substituicao brusca. Primeiro codificamos o comportamento atual em testes, depois introduzimos um registro interno de agentes que passa a ser a fonte de verdade dos prompts, e por fim trocamos o planner para um papel de CEO que escolhe `agent_id` em vez de `domain`, mantendo alias legado para planos antigos e testes existentes.

**Tech Stack:** Python 3.12, Pydantic v2, LangGraph `StateGraph` + `Send`, `graphlib.TopologicalSorter`, `pytest`, registry interno sem novas dependencias.

**Constraints:**
- `maestro run` sem `--multi` deve continuar identico.
- O path guard continua sendo aplicado dentro de cada Worker via loop atual; este plano nao move a execucao de tools para fora de `maestro.agent`.
- O limite de recursao (`max_depth`) continua obrigatorio.
- Nao introduzir plugin externo de agentes nesta fase; o registry sera interno e pequeno.

**Out of Scope:**
- Entry points `maestro.agents` para agentes de terceiros.
- Alterar o protocolo de providers ou o fluxo de auth.
- Mudar o contrato CLI do usuario final alem de preservar `--multi` atual.

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `maestro/agent_registry.py` | Fonte de verdade para agentes builtin (`agent_id`, prompt, descricao curta, aliases legados) |
| Modify | `maestro/domains.py` | Camada de compatibilidade; delega para o registry sem quebrar imports atuais |
| Modify | `maestro/planner/schemas.py` | Trocar modelo de tarefa de `domain` fixo para `agent_id` com alias legado `domain` |
| Modify | `maestro/planner/node.py` | Trocar prompt do planner para papel de CEO e embutir catalogo vindo do registry |
| Modify | `maestro/multi_agent.py` | Resolver prompt do worker via `agent_id`/registry com fallback legado |
| Modify | `maestro/planner/validator.py` | Manter validacao de DAG, sem assumir mais `DomainName` literal |
| Create | `tests/test_agent_registry.py` | Cobertura do registry, aliases e compatibilidade com `domains.py` |
| Create | `tests/test_planner_schemas.py` | Cobertura de `agent_id`, alias `domain` e serializacao compatível |
| Create | `tests/test_planner_node.py` | Cobertura do prompt CEO e parsing tolerante a resposta legada/atual |
| Create | `tests/test_multi_agent_registry.py` | Cobertura da resolucao de prompt de worker via registry |
| Modify | `tests/test_dashboard_integration.py` | Ajustar fixtures de `PlanTask` para o contrato novo mantendo compatibilidade |
| Modify | `docs/ideas/multi-agent-dag.md` | Atualizar narrativa arquitetural de `domain` fixo para `CEO + Agent Registry` |

---

### Task 1: Congelar compatibilidade atual em testes

**Files:**
- Create: `tests/test_agent_registry.py`
- Create: `tests/test_planner_schemas.py`
- Modify: `tests/test_dashboard_integration.py`

- [ ] **Step 1: Escrever os testes que falham primeiro**

Criar `tests/test_agent_registry.py` com os contratos minimos de compatibilidade:

```python
from maestro.domains import DEFAULT_DOMAIN, get_domain_prompt, list_domains


def test_legacy_domain_api_still_exposes_general_fallback() -> None:
    assert DEFAULT_DOMAIN == "general"
    assert get_domain_prompt("unknown-domain") == get_domain_prompt("general")


def test_legacy_domain_api_still_lists_builtin_agents() -> None:
    domains = list_domains()
    assert "backend" in domains
    assert "testing" in domains
    assert "general" in domains
```

Criar `tests/test_planner_schemas.py` com o contrato de migracao:

```python
from maestro.planner.schemas import PlanTask


def test_plan_task_accepts_legacy_domain_field() -> None:
    task = PlanTask.model_validate(
        {"id": "t1", "domain": "backend", "prompt": "Build API", "deps": []}
    )
    assert task.agent_id == "backend"


def test_plan_task_serializes_with_agent_id_only() -> None:
    task = PlanTask(agent_id="testing", id="t2", prompt="Write tests", deps=["t1"])
    assert task.model_dump()["agent_id"] == "testing"
```

- [ ] **Step 2: Rodar os testes para ver falhar**

Run: `pytest tests/test_agent_registry.py tests/test_planner_schemas.py -v`
Expected: FAIL porque `agent_id` ainda nao existe e o registry ainda nao foi introduzido.

- [ ] **Step 3: Ajustar fixture que instancia `PlanTask` explicitamente**

Em `tests/test_dashboard_integration.py`, trocar a fixture minima para o contrato futuro:

```python
plan = AgentPlan(
    tasks=[
        PlanTask(
            id="t1",
            agent_id="general",
            prompt="Create README",
            deps=[],
        )
    ]
)
```

Nao remover o teste legado de `domain`; o objetivo e cobrir os dois formatos durante a migracao.

- [ ] **Step 4: Rodar os testes de novo**

Run: `pytest tests/test_agent_registry.py tests/test_planner_schemas.py tests/test_dashboard_integration.py -v`
Expected: ainda FAIL, mas agora somente pelos pontos de implementacao ausentes.

- [ ] **Step 5: Commit**

```bash
git add tests/test_agent_registry.py tests/test_planner_schemas.py tests/test_dashboard_integration.py
git commit -m "test: lock multi-agent compatibility before agent registry refactor"
```

---

### Task 2: Introduzir o Agent Registry interno sem quebrar `domains.py`

**Files:**
- Create: `maestro/agent_registry.py`
- Modify: `maestro/domains.py`
- Test: `tests/test_agent_registry.py`

- [ ] **Step 1: Escrever o teste especifico do registry**

Adicionar em `tests/test_agent_registry.py`:

```python
from maestro.agent_registry import get_agent, list_agents


def test_registry_resolves_builtin_agent_by_id() -> None:
    agent = get_agent("backend")
    assert agent.id == "backend"
    assert "backend development specialist" in agent.system_prompt.lower()


def test_registry_falls_back_to_general_for_unknown_alias() -> None:
    agent = get_agent("unknown-domain")
    assert agent.id == "general"


def test_registry_lists_stable_builtin_ids() -> None:
    assert set(list_agents()) >= {"backend", "testing", "docs", "devops", "security", "data", "general"}
```

- [ ] **Step 2: Rodar o teste para confirmar falha**

Run: `pytest tests/test_agent_registry.py -v`
Expected: FAIL com `ModuleNotFoundError: maestro.agent_registry`.

- [ ] **Step 3: Implementar o registry minimo e o shim de compatibilidade**

Criar `maestro/agent_registry.py` com uma API pequena:

```python
from dataclasses import dataclass, field


@dataclass(frozen=True)
class AgentSpec:
    id: str
    description: str
    system_prompt: str
    aliases: tuple[str, ...] = field(default_factory=tuple)


DEFAULT_AGENT_ID = "general"
```

Definir `BUILTIN_AGENTS` com os prompts atuais copiados de `maestro/domains.py` e expor:

```python
def get_agent(agent_id: str) -> AgentSpec: ...
def get_agent_prompt(agent_id: str) -> str: ...
def list_agents() -> list[str]: ...
def get_agent_catalog() -> list[AgentSpec]: ...
```

Em `maestro/domains.py`, manter a API atual como wrapper:

```python
from maestro.agent_registry import DEFAULT_AGENT_ID, get_agent_prompt, list_agents

DEFAULT_DOMAIN = DEFAULT_AGENT_ID


def get_domain_prompt(domain: str) -> str:
    return get_agent_prompt(domain)


def list_domains() -> list[str]:
    return list_agents()
```

- [ ] **Step 4: Rodar os testes para validar compatibilidade**

Run: `pytest tests/test_agent_registry.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add maestro/agent_registry.py maestro/domains.py tests/test_agent_registry.py
git commit -m "feat: add internal agent registry with legacy domain shim"
```

---

### Task 3: Migrar o schema do planner para `agent_id` com alias legado `domain`

**Files:**
- Modify: `maestro/planner/schemas.py`
- Modify: `maestro/planner/validator.py`
- Test: `tests/test_planner_schemas.py`

- [ ] **Step 1: Escrever os testes de schema e compatibilidade**

Expandir `tests/test_planner_schemas.py`:

```python
import pytest

from maestro.planner.schemas import PlanTask


def test_plan_task_rejects_missing_agent_and_domain() -> None:
    with pytest.raises(Exception):
        PlanTask.model_validate({"id": "t1", "prompt": "x", "deps": []})


def test_plan_task_keeps_agent_id_when_both_fields_present() -> None:
    task = PlanTask.model_validate(
        {
            "id": "t1",
            "agent_id": "docs",
            "domain": "backend",
            "prompt": "Write docs",
            "deps": [],
        }
    )
    assert task.agent_id == "docs"
```

- [ ] **Step 2: Rodar o teste para ver falhar**

Run: `pytest tests/test_planner_schemas.py -v`
Expected: FAIL porque `PlanTask` ainda exige `domain` literal e nao faz alias.

- [ ] **Step 3: Implementar a migracao minima em `PlanTask`**

Trocar o contrato de `PlanTask` para armazenar `agent_id` como campo canonico e aceitar `domain` na entrada:

```python
from pydantic import BaseModel, ConfigDict, Field, model_validator


class PlanTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Unique task identifier, e.g. t1")
    agent_id: str = Field(description="Agent registry identifier")
    prompt: str = Field(description="Specific instruction for this worker")
    deps: list[str] = Field(..., description="IDs of tasks that must complete first")

    @model_validator(mode="before")
    @classmethod
    def _promote_legacy_domain(cls, data):
        if isinstance(data, dict) and "agent_id" not in data and "domain" in data:
            data = dict(data)
            data["agent_id"] = data["domain"]
        return data
```

Remover o `DomainName = Literal[...]` para nao congelar mais a lista de agentes no schema. A fonte de verdade passa a ser o registry.

Em `maestro/planner/validator.py`, manter a validacao apenas de DAG; nao adicionar validacao de `agent_id` ali ainda. O worker fara fallback seguro para `general`, reduzindo risco de regressao.

- [ ] **Step 4: Rodar os testes do schema**

Run: `pytest tests/test_planner_schemas.py tests/test_dashboard_integration.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add maestro/planner/schemas.py maestro/planner/validator.py tests/test_planner_schemas.py tests/test_dashboard_integration.py
git commit -m "refactor: make planner tasks use agent_id with legacy domain alias"
```

---

### Task 4: Transformar o planner em CEO usando o catalogo do registry

**Files:**
- Modify: `maestro/planner/node.py`
- Test: `tests/test_planner_node.py`

- [ ] **Step 1: Escrever os testes do prompt CEO**

Criar `tests/test_planner_node.py`:

```python
from maestro.planner.node import _build_system_prompt


def test_planner_prompt_mentions_ceo_role() -> None:
    prompt = _build_system_prompt()
    assert "CEO" in prompt
    assert "agent_id" in prompt


def test_planner_prompt_embeds_registry_catalog() -> None:
    prompt = _build_system_prompt()
    assert "backend" in prompt
    assert "testing" in prompt
    assert "general" in prompt
```

Adicionar um teste de parsing tolerante a resposta legada:

```python
from unittest.mock import patch

from maestro.planner.node import planner_node


def test_planner_node_accepts_legacy_domain_json() -> None:
    raw = '{"tasks": [{"id": "t1", "domain": "backend", "prompt": "Build API", "deps": []}]}'
    with patch("maestro.planner.node.resolve_model") as mock_resolve, \
         patch("maestro.planner.node._call_provider_with_schema", return_value=raw):
        mock_provider = object()
        mock_resolve.return_value = (mock_provider, "gpt-4o-mini")
        result = planner_node({"task": "Build API"})
    assert result["dag"]["tasks"][0]["agent_id"] == "backend"
```

- [ ] **Step 2: Rodar os testes para ver falhar**

Run: `pytest tests/test_planner_node.py -v`
Expected: FAIL porque o prompt ainda fala em `domain` fixo.

- [ ] **Step 3: Atualizar `maestro/planner/node.py` para o papel de CEO**

Substituir a parte fixa baseada em `DOMAINS` por catalogo do registry:

```python
from maestro.agent_registry import get_agent_catalog
```

Construir o catalogo textual assim:

```python
_AGENT_LIST = "\n".join(
    f"- {agent.id}: {agent.description}"
    for agent in get_agent_catalog()
)
```

Trocar o prompt base para algo do tipo:

```python
PLANNER_SYSTEM_PROMPT = """You are the CEO of a team of specialized agents.
You do not write code. You only decompose work into the minimum number of tasks
and assign each task to exactly one `agent_id` from the registry below.
...
## Agent Registry

{agent_list}
"""
```

Manter o stripping de `<reasoning>` e o retry loop exatamente como estao; o risco aqui e no contrato do prompt, nao no parser.

- [ ] **Step 4: Rodar os testes do planner**

Run: `pytest tests/test_planner_node.py tests/test_planner_schemas.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add maestro/planner/node.py tests/test_planner_node.py tests/test_planner_schemas.py
git commit -m "feat: turn planner into CEO over the internal agent registry"
```

---

### Task 5: Fazer o worker consumir `agent_id` via registry com fallback seguro

**Files:**
- Modify: `maestro/multi_agent.py`
- Test: `tests/test_multi_agent_registry.py`

- [ ] **Step 1: Escrever os testes do worker/scheduler**

Criar `tests/test_multi_agent_registry.py`:

```python
from maestro.multi_agent import _collect_ready_tasks
from maestro.planner.schemas import AgentPlan, PlanTask


def test_collect_ready_tasks_emits_agent_id_in_payload() -> None:
    plan = AgentPlan(tasks=[PlanTask(id="t1", agent_id="docs", prompt="Write docs", deps=[])])
    ready = _collect_ready_tasks(plan, completed=set(), in_progress=set(), terminal=set())
    assert ready == [{"id": "t1", "agent_id": "docs", "prompt": "Write docs"}]
```

Adicionar teste do prompt do worker:

```python
from unittest.mock import patch

from maestro.multi_agent import worker_node


def test_worker_node_uses_registry_prompt_for_agent_id() -> None:
    state = {
        "task": "root",
        "dag": {"tasks": []},
        "completed": [],
        "failed": [],
        "outputs": {},
        "errors": [],
        "depth": 0,
        "max_depth": 2,
        "workdir": ".",
        "auto": True,
        "ready_tasks": [],
        "current_task_id": "t1",
        "current_task_domain": "docs",
        "current_task_prompt": "Write docs",
    }
    with patch("maestro.multi_agent.get_agent_prompt", return_value="DOCS PROMPT") as mock_prompt, \
         patch("maestro.multi_agent.agent_module.run", return_value="ok"):
        worker_node(state)
    mock_prompt.assert_called()
```

- [ ] **Step 2: Rodar os testes para confirmar falha**

Run: `pytest tests/test_multi_agent_registry.py -v`
Expected: FAIL porque o payload pronto ainda usa `domain`.

- [ ] **Step 3: Fazer a migracao minima em `maestro/multi_agent.py`**

Trocar o payload pronto para carregar `agent_id` canonico:

```python
ready_tasks.append(
    {"id": task.id, "agent_id": task.agent_id, "prompt": task.prompt}
)
```

No `dispatch_route`, propagar tanto o canonico quanto o nome legado temporario:

```python
"current_task_agent_id": task.get("agent_id", task.get("domain", "general")),
"current_task_domain": task.get("agent_id", task.get("domain", "general")),
```

No worker, resolver o prompt pelo registry:

```python
from maestro.agent_registry import get_agent_prompt

agent_id = state.get("current_task_agent_id") or state.get("current_task_domain", "general")
system_prompt = get_agent_prompt(agent_id)
```

Nao alterar o loop de recursao, `max_depth`, provider/model resolution nem o path guard embutido no agente.

- [ ] **Step 4: Rodar os testes multi-agent relevantes**

Run: `pytest tests/test_multi_agent_registry.py tests/test_aggregator_guardrails.py tests/test_dashboard_integration.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add maestro/multi_agent.py tests/test_multi_agent_registry.py tests/test_aggregator_guardrails.py tests/test_dashboard_integration.py
git commit -m "refactor: resolve worker prompts through agent registry"
```

---

### Task 6: Atualizar documentacao arquitetural e fazer verificacao de regressao

**Files:**
- Modify: `docs/ideas/multi-agent-dag.md`
- Modify: `maestro/domains.py` docstring if needed
- Test: `tests/test_cli_planning.py` and full targeted regression suite

- [ ] **Step 1: Atualizar a documentacao de arquitetura**

Em `docs/ideas/multi-agent-dag.md`, trocar a secao `Domain System` por `CEO + Agent Registry` com o seguinte nucleo:

```md
## CEO + Agent Registry

The planner acts as a CEO: it decomposes the user request and assigns each task to
an `agent_id` from the internal registry. Workers no longer depend on a hard-coded
`DomainName` type; they resolve their system prompt from the registry, while legacy
plans that still emit `domain` remain accepted through schema aliasing.
```

- [ ] **Step 2: Rodar a regressao focada de compatibilidade**

Run: `pytest tests/test_agent_registry.py tests/test_planner_schemas.py tests/test_planner_node.py tests/test_multi_agent_registry.py tests/test_aggregator_guardrails.py tests/test_dashboard_integration.py tests/test_cli_planning.py -v`
Expected: ALL PASS.

- [ ] **Step 3: Rodar a regressao principal do CLI**

Run: `pytest tests/test_cli.py tests/test_cli_planning.py tests/test_copilot_smoke.py -v`
Expected: `test_cli.py` e `test_cli_planning.py` PASS; `test_copilot_smoke.py` permanece skip por default quando o gate opt-in nao estiver habilitado.

- [ ] **Step 4: Rodar a suite completa antes de encerrar**

Run: `pytest -q`
Expected: todas as suites locais passam, sem regressao em `maestro run` e sem falhas novas no pipeline multi-agent.

- [ ] **Step 5: Commit**

```bash
git add docs/ideas/multi-agent-dag.md maestro/domains.py
git commit -m "docs: describe CEO plus agent registry architecture"
```

---

## Rollout Notes

- O alias `domain -> agent_id` deve permanecer por pelo menos um ciclo completo de desenvolvimento enquanto houver testes, fixtures ou artefatos em disco com o formato antigo.
- O fallback para `general` e deliberado: reduz risco de quebra quando o CEO emitir um `agent_id` desconhecido, e preserva o comportamento tolerante atual.
- Nao introduzir descoberta dinamica de agentes nesta fase; primeiro estabilizar o contrato interno.

## Acceptance Checklist

- `maestro run "..."` continua no loop single-agent atual.
- `maestro run --multi "..."` continua executando DAG com `Send` e reducers.
- Planner aceita JSON antigo com `domain` e novo com `agent_id`.
- Worker resolve prompt via registry, nao via `DomainName` literal hardcoded.
- Nenhum teste existente de provider/auth/model resolution precisa mudar de comportamento.
