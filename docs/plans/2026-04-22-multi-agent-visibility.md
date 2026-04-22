# Multi-Agent Visibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dar visibilidade em tempo real do que cada agente está fazendo no modo `--multi`, eliminando a caixa preta entre o início da execução e o resultado final.

**Architecture:** Adicionar prints de ciclo de vida (`[planner] started`, DAG summary, `[aggregator] started`, timestamps), promover logs de scheduler de DEBUG para stdout, e passar callbacks `on_text`/`on_tool_start` para os workers no `worker_node`.

**Tech Stack:** Python stdlib (`time`, `logging`), `_print_lifecycle` helper já existente em `multi_agent.py`.

---

## File Map

| Arquivo | Mudança |
|---------|---------|
| `maestro/multi_agent.py` | Adicionar prints lifecycle faltantes, expor streaming do worker, promover logs scheduler |
| `maestro/cli.py` | Adicionar spinner no path `--multi`, configurar logging para stderr |
| `tests/test_scheduler_workers.py` | Atualizar/adicionar testes para os novos prints |

---

### Task 1: Adicionar `[planner] started` e DAG summary após planning

**Files:**
- Modify: `maestro/multi_agent.py:540-560`

- [ ] **Step 1: Localizar o ponto de chamada do planner_node**

```bash
grep -n "planner_node\|planner.*done\|\[planner\]" maestro/multi_agent.py
```
Esperado: linha ~550 com `[planner] done`.

- [ ] **Step 2: Adicionar `[planner] started` antes da chamada e DAG summary depois**

No arquivo `maestro/multi_agent.py`, localizar a função `run_multi_agent`. Antes da chamada a `planner_node`, adicionar print de início. Após a chamada, imprimir o número de tasks e seus IDs/domínios.

```python
# Antes de: plan = planner_node(state, provider=provider, model=model)
_print_lifecycle("planner", "started")
plan = planner_node(state, provider=provider, model=model)
_print_lifecycle("planner", "done")

# Imprimir resumo do DAG
tasks = plan.get("dag", {}).get("tasks", [])
_print_lifecycle("planner", f"DAG: {len(tasks)} task(s) — " + ", ".join(
    f"{t['id']}({t.get('domain','?')})" for t in tasks
))
```

- [ ] **Step 3: Verificar manualmente (sem testes ainda)**

```bash
cd /home/ervison/Documents/PROJETOS/labs/timeIA/maestro
python -c "
from maestro.multi_agent import _print_lifecycle
_print_lifecycle('planner', 'started')
_print_lifecycle('planner', 'done')
_print_lifecycle('planner', 'DAG: 3 task(s) — t1(code), t2(test), t3(docs)')
"
```
Esperado: 3 linhas `[planner] ...` no stdout.

- [ ] **Step 4: Commit**

```bash
git add maestro/multi_agent.py
git commit -m "feat: add [planner] started and DAG summary output"
```

---

### Task 2: Adicionar `[aggregator] started`

**Files:**
- Modify: `maestro/multi_agent.py:362-380`

- [ ] **Step 1: Localizar o início de `aggregator_node`**

```bash
grep -n "def aggregator_node\|\[aggregator\]" maestro/multi_agent.py
```
Esperado: `def aggregator_node` em ~362, `[aggregator] done` em ~381 e ~453.

- [ ] **Step 2: Adicionar print no início de `aggregator_node`**

Logo após a linha `def aggregator_node(state: AgentState, ...)`, inserir:

```python
_print_lifecycle("aggregator", "started")
```

- [ ] **Step 3: Verificar que os dois prints existem**

```bash
grep -n "\[aggregator\]" maestro/multi_agent.py
```
Esperado: 3 linhas — `started`, `done` (early return), `done` (normal).

- [ ] **Step 4: Commit**

```bash
git add maestro/multi_agent.py
git commit -m "feat: add [aggregator] started lifecycle print"
```

---

### Task 3: Promover progresso do scheduler de DEBUG para stdout

**Files:**
- Modify: `maestro/multi_agent.py:147-153`

- [ ] **Step 1: Localizar o log DEBUG do scheduler**

```bash
grep -n "Scheduler:.*ready\|ready.*completed\|DEBUG" maestro/multi_agent.py | head -20
```
Esperado: linha ~147 com `logger.debug(f"Scheduler: {n_ready} ready, ...")`.

- [ ] **Step 2: Substituir logger.debug por _print_lifecycle**

Trocar:
```python
logger.debug(
    f"Scheduler: {n_ready} ready, {n_completed} completed, "
    f"{n_failed} failed, {n_unfinished} unfinished"
)
```
Por:
```python
_print_lifecycle(
    "scheduler",
    f"{n_ready} ready | {n_completed} done | {n_failed} failed | {n_unfinished} pending"
)
```

- [ ] **Step 3: Rodar testes do scheduler para garantir que não quebrou nada**

```bash
pytest tests/test_scheduler_workers.py -v -x 2>&1 | head -60
```
Esperado: todos passam (output imprime para stdout mas não afeta assertions).

- [ ] **Step 4: Commit**

```bash
git add maestro/multi_agent.py
git commit -m "feat: promote scheduler progress from DEBUG to stdout"
```

---

### Task 4: Expor streaming de texto dos workers (on_text callback)

**Files:**
- Modify: `maestro/multi_agent.py:255-337` (`worker_node`)

- [ ] **Step 1: Localizar a chamada de `_run_agentic_loop` no worker_node**

```bash
grep -n "_run_agentic_loop\|on_text\|on_tool_start" maestro/multi_agent.py
```
Esperado: linha ~320 com `_run_agentic_loop(...)` sem `on_text`.

- [ ] **Step 2: Adicionar callbacks no worker_node**

Na chamada a `_run_agentic_loop` dentro de `worker_node`, adicionar callbacks que prefixam a saída com o task_id:

```python
task_id = state.get("task_id", "?")

def _on_text(chunk: str) -> None:
    # Escreve direto, sem newline extra — chunks chegam fragmentados
    print(chunk, end="", flush=True)

def _on_tool_start(name: str, args: dict) -> None:
    _print_lifecycle(f"worker:{task_id}", f"tool:{name}")

result = _run_agentic_loop(
    ...,  # args existentes
    on_text=_on_text,
    on_tool_start=_on_tool_start,
)
```

> **Nota:** `_run_agentic_loop` já aceita `on_text` (agent.py:232) e `on_tool_start` (agent.py:233). Confirmar a assinatura exata antes de aplicar.

- [ ] **Step 3: Verificar assinatura de _run_agentic_loop**

```bash
grep -n "def _run_agentic_loop" maestro/agent.py
sed -n '222,240p' maestro/agent.py
```
Confirmar parâmetros `on_text` e `on_tool_start` existem e seus tipos.

- [ ] **Step 4: Rodar testes de agent loop para garantir compatibilidade**

```bash
pytest tests/test_agent_loop.py tests/test_agent_loop_provider.py -v -x 2>&1 | head -60
```
Esperado: todos passam.

- [ ] **Step 5: Rodar testes do scheduler/worker**

```bash
pytest tests/test_scheduler_workers.py -v -x 2>&1 | head -60
```
Esperado: todos passam.

- [ ] **Step 6: Commit**

```bash
git add maestro/multi_agent.py
git commit -m "feat: stream worker LLM output to stdout via on_text callback"
```

---

### Task 5: Adicionar spinner no modo --multi no CLI

**Files:**
- Modify: `maestro/cli.py` (path `--multi`, linha ~398)

- [ ] **Step 1: Localizar o path --multi no cli.py**

```bash
grep -n "\-\-multi\|run_multi_agent\|_Spinner" maestro/cli.py | head -20
```
Esperado: `run_multi_agent` em ~398, `_Spinner` instanciado apenas no path single-agent (~431).

- [ ] **Step 2: Inspecionar a implementação de _Spinner**

```bash
grep -n "class _Spinner\|def _Spinner\|_Spinner" maestro/cli.py | head -10
sed -n '$(grep -n "class _Spinner" maestro/cli.py | cut -d: -f1)p' maestro/cli.py
```

Alternativamente:
```bash
grep -n "class _Spinner" maestro/cli.py
```
Ler as linhas do `_Spinner` para entender a API (start/stop, thread-safe?).

- [ ] **Step 3: Configurar logging para stderr antes de run_multi_agent**

No início do bloco `--multi` no `cli.py`, antes de chamar `run_multi_agent`:

```python
import logging
logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s %(name)s: %(message)s",
    stream=sys.stderr,
)
```

Isso garante que `logger.warning()` e `logger.error()` de `multi_agent.py` apareçam.

- [ ] **Step 4: Adicionar indicador visual no path --multi**

O `_Spinner` provavelmente usa uma thread com output periódico. Para o modo `--multi`, os workers já imprimem via `_print_lifecycle`, então um spinner simples de "aguardando" que para ao receber output pode conflitar. A solução mais simples e compatível é usar um print antes da chamada:

```python
print("[maestro] planning...", flush=True)
result = run_multi_agent(task=task, ...)
```

Se `_Spinner` for thread-safe e não conflitar com os prints dos workers, usá-lo apenas para a fase de planning (antes de `[planner] done`).

- [ ] **Step 5: Rodar testes de CLI**

```bash
pytest tests/test_multi_agent_cli.py -v -x 2>&1 | head -60
```
Esperado: todos passam.

- [ ] **Step 6: Commit**

```bash
git add maestro/cli.py
git commit -m "feat: add logging setup and planning indicator for --multi mode"
```

---

### Task 6: Adicionar timestamps aos lifecycle prints

**Files:**
- Modify: `maestro/multi_agent.py:39` (`_print_lifecycle`)

- [ ] **Step 1: Ver a implementação atual de _print_lifecycle**

```bash
sed -n '35,45p' maestro/multi_agent.py
```

- [ ] **Step 2: Adicionar timestamp relativo ao início**

```python
import time

_start_time: float = time.monotonic()

def _print_lifecycle(component: str, event: str) -> None:
    elapsed = time.monotonic() - _start_time
    print(f"[{elapsed:6.1f}s] [{component}] {event}", flush=True)
```

> O `_start_time` é definido no nível do módulo, portanto marca o início do processo. Considera-se aceitável — mostra o tempo desde o import, que é essencialmente o início da execução.

- [ ] **Step 3: Rodar toda a suite de testes**

```bash
pytest tests/ -v -x 2>&1 | tail -30
```
Esperado: todos passam. Se algum teste fizer assert exato no output de `_print_lifecycle`, atualizar o assert para usar `assertIn` no componente/evento em vez de string exata.

- [ ] **Step 4: Commit**

```bash
git add maestro/multi_agent.py
git commit -m "feat: add elapsed time to lifecycle prints for --multi mode"
```

---

### Task 7: Testes de regressão — verificar suite completa

- [ ] **Step 1: Rodar toda a suite**

```bash
pytest tests/ -v 2>&1 | tail -40
```
Esperado: todos os 26+ testes passam.

- [ ] **Step 2: Se houver falhas de assert em prints, corrigir**

Padrão de correção: trocar asserts de string exata por `assertIn` ou `re.search`:

```python
# Antes (frágil):
assert captured == "[planner] done\n"

# Depois (robusto):
assert "[planner]" in captured
assert "done" in captured
```

- [ ] **Step 3: Commit final se houve correções de teste**

```bash
git add tests/
git commit -m "test: update assertions to be resilient to lifecycle print format changes"
```

---

## Resultado esperado

Após a implementação, `maestro run --multi "..."` produzirá saída similar a:

```
[maestro] planning...
[  0.0s] [planner] started
[  3.2s] [planner] done
[  3.2s] [planner] DAG: 3 task(s) — t1(code), t2(test), t3(docs)
[  3.2s] [scheduler] 3 ready | 0 done | 0 failed | 0 pending
[  3.3s] [worker:t1] started
[  3.3s] [worker:t2] started
[  3.3s] [worker:t3] started
[  3.3s] [worker:t1] tool:write_file
[  3.5s] [worker:t2] tool:execute_shell
... (streaming LLM output dos workers)
[  8.1s] [worker:t2] done
[ 10.4s] [worker:t1] done
[ 11.2s] [worker:t3] done
[ 11.2s] [scheduler] 0 ready | 3 done | 0 failed | 0 pending
[ 11.3s] [aggregator] started
[ 14.7s] [aggregator] done

--- Final Summary ---
...
```
