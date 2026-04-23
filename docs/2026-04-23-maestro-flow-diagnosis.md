# Diagnostico Tecnico do Fluxo Maestro

## Objetivo

Documentar o fluxo atual do Maestro desde `discover` ate `run --multi`, avaliar o status real da proposta em `docs/ideas/multi-agent-dag.md`, registrar lacunas e propor um plano objetivo de implementacao do que ainda falta.

## Escopo analisado

- CLI e roteamento de comandos em `maestro/cli.py`
- Loop agente unico em `maestro/agent.py`
- Pipeline multi-agent em `maestro/multi_agent.py`
- Planejamento e validacao de DAG em `maestro/planner/*.py`
- Registro de providers em `maestro/providers/registry.py`
- Guard rails de ferramentas em `maestro/tools.py`
- Pipeline SDLC `discover` em `maestro/sdlc/*.py`
- Rascunho arquitetural em `docs/ideas/multi-agent-dag.md`

## Resumo executivo

O repositorio ja possui uma implementacao funcional de `maestro run --multi` com Planner, Scheduler, dispatch por `Send`, Workers especializados por dominio e Aggregator opcional. A base arquitetural descrita em `docs/ideas/multi-agent-dag.md` deixou de ser apenas ideia e esta parcialmente implementada no codigo.

O maior ponto faltante nao e o fan-out paralelo em si, mas o fechamento da proposta v1 com seguranca e previsibilidade operacional:

- nao existe recursao real de workers, apenas `depth/max_depth` e um guard local
- `discover` e `run --multi` sao pipelines independentes, sem handoff nem reaproveitamento de artefatos
- a cobertura de testes do motor multi-agent ainda e rasa e concentrada em eventos de dashboard
- o scheduler termina de forma permissiva em alguns estados inconsistentes, em vez de falhar explicitamente

## Fluxo atual

### 1. `maestro discover`

O subcomando `discover` e tratado por `_handle_discover()` em `maestro/cli.py:535-575`.

Fluxo atual:

1. valida e materializa `SDLCRequest`
2. resolve provider/model por `maestro.models.resolve_model()`
3. instancia `DiscoveryHarness`
4. executa `harness.run(request)`
5. grava 13 artefatos em `spec/`

O `DiscoveryHarness` em `maestro/sdlc/harness.py:20-140` executa um pipeline SDLC sequencial:

1. opcionalmente faz um scan brownfield simples (`_scan_codebase`)
2. gera os 13 artefatos na ordem fixa de `ARTIFACT_ORDER`
3. escreve cada artefato imediatamente em disco
4. ao gerar `gaps`, abre o questionario web e injeta respostas no prompt restante
5. opcionalmente roda o reflect loop no final

Observacoes:

- `discover` produz especificacao em `spec/`, nao DAG executavel
- `discover` nao alimenta `run` nem `run --multi`
- o scan brownfield atual e superficial: apenas lista ate 20 arquivos `.py` do diretorio raiz (`maestro/sdlc/harness.py:201-207`)

### 2. `maestro run` sem `--multi`

O fluxo single-agent continua sendo o default em `maestro/cli.py:396-518`.

Fluxo atual:

1. resolve provider/model
2. cai no branch `else` quando `args.multi` e falso
3. chama `maestro.agent.run()`
4. `run()` encapsula `_run_agentic_loop()` em `@task` + `@entrypoint` (`maestro/agent.py:445-495`)
5. `_run_agentic_loop()` chama o provider, recebe tool calls e executa ferramentas ate concluir (`maestro/agent.py:222-360`)

Seguranca relevante:

- o workdir e respeitado por `execute_tool()` e `resolve_path()` (`maestro/tools.py:25-37`, `maestro/tools.py:186-209`)
- isso preserva a compatibilidade do modo antigo e tambem e reutilizado pelos workers do modo multi-agent

### 3. `maestro run --multi`

O branch multi-agent esta em `maestro/cli.py:428-487`.

Fluxo atual:

1. resolve provider/model no CLI
2. sobe o dashboard SSE (`DashboardEmitter` + `start_dashboard_server`)
3. chama `run_multi_agent()`
4. imprime resumo agregado ou saidas por worker
5. retorna codigo de erro se nenhum worker concluir ou se houver falhas

### 4. `run_multi_agent()`

`run_multi_agent()` em `maestro/multi_agent.py:546-696` hoje e o orquestrador principal.

Fluxo atual:

1. valida `workdir`
2. resolve provider default se necessario
3. resolve se agregacao final deve rodar via config
4. chama `planner_node()` fora do grafo para gerar o DAG
5. emite evento `dag_ready`
6. monta o `AgentState` inicial
7. executa o `StateGraph` compilado
8. devolve `outputs`, `failed`, `errors` e opcionalmente `summary`

### 5. Planner

`planner_node()` em `maestro/planner/node.py:166-242` esta implementado.

Capacidades atuais:

- usa `AgentPlan`/`PlanTask` com Pydantic v2 (`maestro/planner/schemas.py:61-89`)
- gera JSON Schema via `model_json_schema()`
- tenta usar `response_format=json_schema` quando o provider suporta (`maestro/planner/node.py:99-163`)
- valida o DAG com `validate_dag()`
- faz ate 3 tentativas com feedback de erro
- escolhe model por `resolve_model(agent_name="planner")`

Limite importante:

- o planner gera DAG apenas para o nivel raiz; nao ha reuso desse mecanismo dentro do worker

### 6. Scheduler, dispatch e workers

O grafo compilado esta em `maestro/multi_agent.py:530-543`.

Nos atuais:

- `scheduler`
- `dispatch`
- `worker`
- `aggregator`

O scheduler em `maestro/multi_agent.py:56-165`:

- materializa o plano serializado
- valida novamente o DAG
- calcula tarefas prontas por checagem direta de dependencias satisfeitas
- detecta tarefas bloqueadas por dependencias falhas

O dispatch em `maestro/multi_agent.py:223-274`:

- cria `Send("worker", payload)` para cada tarefa pronta
- repassa `provider`, `model`, `workdir`, `auto`, `depth`, `max_depth`
- emite eventos de dashboard para inicio dos workers

O worker em `maestro/multi_agent.py:277-400`:

- valida `task_id/domain/prompt`
- aplica guard de profundidade
- resolve e cria `workdir`
- constroi `system_prompt` por dominio via `maestro/domains.py:7-57`
- executa `_run_agentic_loop()` com acesso as mesmas ferramentas do modo single-agent
- devolve atualizacoes reducer-safe em `completed`, `failed`, `outputs`, `errors`

### 7. Aggregator

O aggregator em `maestro/multi_agent.py:425-527` esta implementado e opcional.

Capacidades atuais:

- consolida `outputs`, `failed` e `errors`
- resolve modelo proprio por `resolve_model(agent_name="aggregator")`
- gera um `summary` final via provider
- pode ser desligado por `--no-aggregate` ou config

## Status de `docs/ideas/multi-agent-dag.md`

### Status geral

Status: parcialmente implementado, com base arquitetural principal presente e algumas lacunas de produto e robustez.

### Matriz de aderencia

| Item da proposta | Status | Evidencia |
| --- | --- | --- |
| `maestro run --multi` como modo aditivo | Implementado | `maestro/cli.py:120-128`, `maestro/cli.py:428-487` |
| Planner separado da execucao | Implementado | `maestro/planner/node.py:166-242`, `maestro/multi_agent.py:605-631` |
| DAG estruturado com Pydantic | Implementado | `maestro/planner/schemas.py:61-89` |
| Validacao de DAG | Implementado | `maestro/planner/validator.py:13-50` |
| Scheduler com paralelismo via `Send` | Implementado | `maestro/multi_agent.py:223-274`, `maestro/multi_agent.py:530-543` |
| Workers especializados por dominio | Implementado | `maestro/domains.py:7-57`, `maestro/multi_agent.py:337-372` |
| Reuso de `_run_agentic_loop` | Implementado | `maestro/multi_agent.py:361-372` |
| Aggregator opcional | Implementado | `maestro/multi_agent.py:425-527` |
| Path guard dentro de cada worker | Implementado | `maestro/multi_agent.py:361-372` + `maestro/tools.py:25-37` |
| Recursao de workers | Nao implementado | ha apenas guard de profundidade em `maestro/multi_agent.py:321-325` |
| Scheduler com `TopologicalSorter.get_ready()/done()` | Parcial | `TopologicalSorter` existe so na validacao, nao no scheduler (`maestro/planner/validator.py:47-49`) |
| Final output agregando tudo | Implementado | `maestro/multi_agent.py:687-694` |
| Cobertura de testes para planner/scheduler/recursion | Parcial | testes encontrados focam dashboard, nao invariantes do motor |
| Streaming parcial no CLI como out of scope | Divergiu | hoje existe dashboard SSE no branch multi-agent (`maestro/cli.py:434-441`) |

### Leitura pratica do status

O documento `docs/ideas/multi-agent-dag.md` nao representa mais um backlog hipotetico puro. Ele descreve corretamente a direcao arquitetural adotada, mas esta desatualizado em tres pontos:

1. subestima o quanto ja foi implementado
2. trata recursao como opcional futura, mas o codigo ja carrega `depth/max_depth` sem completar a feature
3. nao reflete a introducao de dashboard/SSE como parte do runtime atual

## Lacunas atuais

### 1. Nao existe recursao funcional

O design fala em workers que podem chamar o Planner novamente e disparar subtarefas. No codigo atual isso nao acontece.

Sinais de implementacao incompleta:

- `depth` e `max_depth` trafegam pelo estado (`maestro/planner/schemas.py:38-40`)
- `dispatch_route()` repassa profundidade ao worker (`maestro/multi_agent.py:256-265`)
- `worker_node()` apenas bloqueia quando `depth > max_depth` (`maestro/multi_agent.py:321-325`)
- nao existe nenhum ponto que incremente profundidade nem chame `run_multi_agent()` ou `planner_node()` de dentro do worker

Impacto:

- a feature de recursao, tratada como requisito importante no contexto do projeto, ainda nao existe

### 2. `discover` e `run --multi` estao desconectados

Hoje existem duas trilhas:

- `discover`: produz especificacao SDLC em `spec/`
- `run --multi`: produz execucao paralela orientada a DAG

Nao existe ponte entre elas. O resultado e que o fluxo "discover ate run/multi-agent" nao e um pipeline continuo, mas dois subsistemas independentes.

Impacto:

- artefatos de descoberta nao influenciam o planner multi-agent
- nao ha modo de usar `discover` como etapa preparatoria do `run --multi`
- o usuario precisa repetir contexto em vez de aproveitar os artefatos ja gerados

### 3. Scheduler tolera estados inconsistentes em vez de falhar cedo

Em `scheduler_route()` (`maestro/multi_agent.py:168-206`), se nao houver `ready_tasks` e ainda existirem tarefas inacabadas, o fluxo ainda pode seguir para `aggregator` ou `END`.

Isso conflita com a expectativa de seguranca operacional para um motor DAG: estados impossiveis deveriam falhar explicitamente, nao encerrar silenciosamente.

Impacto:

- risco de terminar com trabalho incompleto sem caracterizar erro estrutural do scheduler

### 4. Cobertura de testes do motor multi-agent ainda e insuficiente

Os testes encontrados para multi-agent estao concentrados em emissao de eventos de dashboard (`tests/test_dashboard_integration.py:1-159`). Nao apareceram testes dedicados para:

- parser/validacao do planner em casos reais de resposta invalida
- ordenacao e desbloqueio de dependencias do scheduler
- tarefas bloqueadas por falha de dependencia
- guard de profundidade
- conflitos de escrita paralela no reducer de `outputs`
- comportamento do aggregator quando provider falha

Impacto:

- maior risco de regressao justamente na parte mais concorrente e sensivel do sistema

### 5. Sem integracao com config por dominio de worker

O sistema ja possui prompts por dominio (`maestro/domains.py`), mas o worker nao resolve modelo por dominio ou por agente especializado. Ele recebe um `model` unico vindo do CLI (`maestro/multi_agent.py:678-680`).

Ja o planner e aggregator usam `resolve_model(agent_name=...)`.

Impacto:

- a especializacao de dominio existe no prompt, mas nao no plano de execucao/modelo
- isso reduz o valor do conceito de agentes especializados

### 6. Brownfield/contexto de codigo ainda e raso para `discover`

O scan brownfield atual so lista arquivos `.py` de topo (`maestro/sdlc/harness.py:201-207`).

Impacto:

- o discovery pipeline ainda nao usa contexto estrutural real do repositorio
- em projetos nao triviais, os artefatos podem nascer desconectados do codigo existente

## Riscos e dividas tecnicas

### Riscos imediatos

- encerramento silencioso do grafo em estados nao totalmente resolvidos
- regressao facil no planner/scheduler por falta de testes estruturais
- expectativas de recursao nao atendidas apesar de haver API aparente para isso

### Dividas tecnicas claras

- `discover` e multi-agent evoluiram em paralelo sem contrato entre si
- parte do desenho arquitetural esta no codigo, mas a documentacao de ideia nao foi promovida para uma especificacao de implementacao
- a escolha de modelo para workers ainda e global, nao por agente/dominio

## Plano de implementacao recomendado

### Fase 1. Fechar v1 do motor multi-agent

Objetivo: tornar o runtime confiavel sem ampliar escopo.

Entregas:

1. endurecer o scheduler para falhar quando houver tarefas inacabadas sem `ready_tasks` e sem bloqueio explicito por falha
2. adicionar testes unitarios para:
   - DAG valido, DAG com ciclo, DAG com dependencia inexistente
   - desbloqueio progressivo de tarefas dependentes
   - tarefas bloqueadas por `failed`
   - guard `depth/max_depth`
   - merge reducer de `outputs`
3. documentar `run --multi` como funcionalidade suportada e nao experimental implita

Criterio de saida:

- o motor multi-agent falha de forma deterministica em estados invalidos
- cobertura automatizada das invariantes principais do grafo

### Fase 2. Implementar recursao real com guard forte

Objetivo: entregar o requisito de recursao que o desenho ja anuncia.

Entregas:

1. definir criterio explicito para um worker escalar uma sub-DAG
2. implementar um caminho controlado no worker para chamar `run_multi_agent(..., depth=depth+1, ...)`
3. manter `max_depth` obrigatorio e falha dura quando excedido
4. agregar saidas de sub-DAG de volta ao output do worker pai
5. criar testes cobrindo:
   - recursao em um nivel
   - bloqueio no limite de profundidade
   - ausencia de loop infinito

Observacao:

Antes de codar, vale decidir se a recursao sera automatica por heuristica do prompt ou acionada por um tool/contrato explicito. Para v1.1, a versao explicita e mais previsivel.

### Fase 3. Integrar `discover` com o pipeline multi-agent

Objetivo: transformar o fluxo "discover ate run/multi-agent" em uma jornada coerente.

Opcoes viaveis:

1. `run --multi` aceitar `--spec-dir` e injetar artefatos do `discover` no planner
2. novo comando composto, por exemplo `maestro deliver`, que rode `discover` e depois `run --multi`
3. planner ler contexto de `spec/` automaticamente quando existir no `workdir`

Recomendacao:

Comecar pela opcao 3 por ser a menor mudanca correta. O planner pode enriquecer a tarefa com um resumo dos arquivos em `spec/` quando presentes, sem quebrar o fluxo atual.

### Fase 4. Especializacao real por agente/dominio

Objetivo: alinhar runtime com a ideia de agentes especializados.

Entregas:

1. permitir `resolve_model(agent_name=f"worker.{domain}")` ou equivalente
2. manter fallback para o modelo unico vindo do CLI
3. opcionalmente permitir prompts de dominio configuraveis por arquivo de config

Resultado esperado:

- planner, workers e aggregator podem usar modelos diferentes de forma controlada

### Fase 5. Evoluir `discover` brownfield

Objetivo: melhorar a qualidade da descoberta em bases reais.

Entregas:

1. trocar o scan de topo por uma amostragem estruturada do repositorio
2. incluir modulos, entry points, testes e arquivos de config relevantes
3. limitar tamanho com resumo em vez de dump bruto

## Priorizacao objetiva

Ordem recomendada:

1. Fase 1, porque reduz risco operacional e facilita qualquer evolucao posterior
2. Fase 2, porque fecha a maior lacuna entre desenho e implementacao
3. Fase 3, porque conecta os dois fluxos principais do produto
4. Fase 4, porque aumenta qualidade e separacao de responsabilidades
5. Fase 5, porque melhora contexto, mas nao bloqueia o core multi-agent

## Conclusao

O Maestro ja nao esta na fase de "ideia" para multi-agent: a espinha dorsal do DAG paralelo esta codificada e exposta no CLI. O documento `docs/ideas/multi-agent-dag.md` deve ser tratado como referencia arquitetural parcialmente entregue, nao como proposta futura integral.

O que falta agora e menos sobre inventar arquitetura e mais sobre fechar produto e confiabilidade:

- completar recursao
- conectar `discover` ao `run --multi`
- endurecer regras de termino do scheduler
- ampliar testes do motor

Com isso, o fluxo de `discover` ate `run/multi-agent` passa de duas capacidades vizinhas para um pipeline coerente de descoberta, planejamento e execucao paralela.
