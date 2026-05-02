# Matriz de Aproveitamento do LangGraph no Maestro

**Objetivo:** mapear onde o Maestro ja usa LangGraph, medir o nivel atual de aproveitamento, e transformar essa leitura em um plano incremental, conservador e orientado a TDD para ampliar esse aproveitamento sem quebrar compatibilidade.

**Escopo:** documentacao, analise e plano. Este documento nao propoe implementacao imediata de codigo de producao.

**Restricoes nao negociaveis:**
- `maestro run` sem `--multi` deve continuar identico ao comportamento atual.
- O path guard precisa continuar valendo dentro de cada worker.
- O limite de recursao precisa continuar sendo hard stop.
- O aumento de uso de LangGraph deve priorizar reaproveitamento de codigo existente, nao reescrita ampla.

---

## 1. Leitura Executiva

O Maestro ja aproveita LangGraph de forma relevante, mas em camadas separadas:

| Area | Estado atual | Aproveitamento |
|------|--------------|----------------|
| Loop single-agent | Usa `@task` + `@entrypoint` em `maestro/agent.py` | Baixo a medio |
| Orquestracao multi-agent | Usa `StateGraph` + `Send` + reducers em `maestro/multi_agent.py` | Alto |
| Planejamento estruturado | Integrado ao grafo, mas fora do `StateGraph` principal como pre-step em `run_multi_agent()` | Medio |
| Descoberta SDLC com sprints | Usa DAG e paralelismo, mas com `TopologicalSorter` + `asyncio.gather` em `maestro/sdlc/*` | Baixo |
| Observabilidade de execucao | Eventos e lifecycle existem, mas ainda nao sao modelados como um padrao unico de grafo | Medio |

Conclusao: o Maestro nao esta subutilizando LangGraph no nucleo multi-agent, mas ainda o utiliza de forma desigual entre os fluxos principais. O maior ganho conservador nao esta em reescrever o que ja funciona em `--multi`, e sim em reduzir a fragmentacao entre os tres estilos atuais de orquestracao:

1. `langgraph.func` no modo single-agent.
2. `StateGraph + Send` no modo multi-agent.
3. DAG manual com `TopologicalSorter` e `asyncio.gather` no fluxo `discover --sprints`.

---

## 2. Matriz Atual de Aproveitamento

| Capacidade do LangGraph | Onde o Maestro usa hoje | Nivel atual | Evidencia no codigo | Valor entregue hoje | Lacuna principal |
|-------------------------|-------------------------|-------------|---------------------|---------------------|------------------|
| `@entrypoint` / `@task` | `maestro/agent.py` | Medio | `run()` encapsula `_run_agentic_loop()` com `@task` e `@entrypoint` | Mantem o loop single-agent simples e compatível | O fluxo continua essencialmente linear; LangGraph aqui e um wrapper fino |
| `StateGraph` | `maestro/multi_agent.py` | Alto | Grafo compilado com `scheduler`, `dispatch`, `worker`, `aggregator` | Estrutura explicita de execucao, isolamento de responsabilidades | Planner ainda roda fora do grafo compilado principal |
| `Send` para fan-out | `maestro/multi_agent.py` | Alto | `dispatch_route()` retorna `list[Send]` | Paralelismo real por tarefa pronta | Uso restrito ao modo `--multi` |
| Reducers (`Annotated[..., operator.add]`) | `maestro/planner/schemas.py` | Alto | `completed`, `failed`, `errors`, `dispatched`, `outputs` | Evita overwrite silencioso em execucao paralela | Nao reaproveitado em outros fluxos DAG do projeto |
| Conditional edges | `maestro/multi_agent.py` | Alto | `add_conditional_edges()` para scheduler e dispatch | Controle claro entre dispatch, espera, agregacao e encerramento | Sem padrao compartilhado com `discover --sprints` |
| Planner com saida estruturada | `maestro/planner/node.py` | Medio | JSON schema + `AgentPlan.model_validate_json()` | Reduz DAG invalido vindo do LLM | O planner nao e um node LangGraph visivel no grafo final de `run_multi_agent()` |
| Reentrada scheduler-worker | `maestro/multi_agent.py` | Alto | `worker -> scheduler` | Reavaliacao segura de dependencias | Nao ha abstracao reutilizavel para outros pipelines DAG |
| Agregacao final como node | `maestro/multi_agent.py` | Medio a alto | `aggregator_node()` + guardrails | Sintese final e bounded call policy | Acoplada ao fluxo multi-agent; sem interface generica para outros pipelines |
| Persistencia/checkpointing LangGraph | Nao usa | Baixo | Ausencia de saver/checkpointer | Nenhum overhead adicional hoje | Sem retentativa/recovery nativo entre etapas |
| Streaming/observabilidade nativa de grafo | Parcial | Medio | emitter + lifecycle prints | Boa visibilidade operacional | Sem uma camada unificada de eventos por node/edge para todos os fluxos |
| Subgrafos reutilizaveis | Nao usa | Baixo | Ausencia de composicao de grafos | Simplicidade | `discover`, `planner`, `aggregator` e `worker loop` evoluem em trilhas separadas |
| Grafo no SDLC discovery | Nao usa LangGraph | Baixo | `maestro/sdlc/sprints.py`, `maestro/sdlc/harness.py` usam `TopologicalSorter` e `asyncio.gather` | Resolve bem o caso atual com pouco codigo | Mantem dois motores de orquestracao paralela no mesmo produto |

---

## 3. Diagnostico por Fluxo

### 3.1 `maestro run` single-agent

- Arquivo principal: `maestro/agent.py:584-605`
- Uso atual de LangGraph: `@task` e `@entrypoint`
- Avaliacao: bom uso para encapsular observabilidade e padronizacao minima, sem aumentar complexidade.
- Limite: o grafo nao modela etapas internas do loop; quem faz o trabalho real continua sendo `_run_agentic_loop()`.
- Recomendacao: preservar. Este fluxo e o principal contrato de compatibilidade do projeto.

### 3.2 `maestro run --multi`

- Arquivo principal: `maestro/multi_agent.py:649-662`
- Uso atual de LangGraph: `StateGraph`, `Send`, reducers, conditional edges, node loop, node final de agregacao.
- Avaliacao: este e hoje o melhor aproveitamento de LangGraph no Maestro.
- Ponto forte: o design ja segue o caminho mais correto para fan-out/fan-in paralelo dentro do stack atual.
- Lacuna: `planner_node()` e chamado antes de `graph.invoke()`, entao o pipeline completo ainda nao e um grafo unico de ponta a ponta.

### 3.3 `maestro discover --sprints`

- Arquivos principais: `maestro/sdlc/harness.py`, `maestro/sdlc/sprints.py`
- Uso atual: DAG manual com `TopologicalSorter` e execucao paralela com `asyncio.gather`.
- Avaliacao: tecnicamente correto e conservador, mas paralelo ao modelo de orquestracao que ja existe em `--multi`.
- Lacuna: o produto passa a manter dois motores de DAG em Python: um com LangGraph e outro manual.
- Maior oportunidade de evolucao: migrar a orquestracao de sprints para um grafo LangGraph simples, sem tocar na geracao sequencial legacy.

---

## 3.4 Capacidades Avancadas Ainda Nao Usadas

As consultas `askdocs` focadas em LangGraph reforcaram que o maior espaco de crescimento do Maestro nao esta em `Send` ou reducers, e sim em capacidades de runtime mais completas que hoje nao sao exploradas.

| Capacidade LangGraph | Uso no Maestro hoje | Quando vale a pena | Recomendacao atual |
|----------------------|---------------------|--------------------|--------------------|
| Checkpointer / durable execution | Nao usa | Fluxos longos, custo alto de recomecar, necessidade de retomar execucao apos falha | Adiar persistencia real nesta etapa; considerar primeiro apenas se a dor operacional aparecer |
| `interrupt()` + `Command(resume=...)` | Nao usa | Gates humanos, compliance, aprovacoes de alto risco, retomada controlada | Nao introduzir agora; os fluxos atuais ainda cabem em gates mais simples |
| `graph.stream()` / `graph.astream()` | Nao usa no grafo principal | UI/telemetria em tempo real, timeline nativa de execucao, feedback incremental do runtime | Candidato bom apos consolidar planner dentro do grafo |
| Subgraphs | Nao usa | Separar fases como planner, execution DAG, discovery, review e aggregation com composicao limpa | Desejavel no medio prazo, mas so depois de estabilizar os grafos principais |
| `get_state()` / `update_state()` / history | Nao usa | Debug operacional, replay, inspeção e correcao de estado | Adiar; ainda nao ha indicio de que o custo compense |

Leitura pratica: o Maestro nao esta deixando valor facil na mesa no nivel basico do LangGraph. A subutilizacao real aparece no nivel de runtime duravel, HITL nativo, streaming de grafo e composicao de subgrafos.

---

## 3.5 Avaliacao especifica sobre streaming do LangGraph

As docs atuais do LangGraph para Python confirmam que `graph.stream()` e `graph.astream()` ja cobrem bem o caso de observabilidade incremental do runtime, com modos distintos como `updates`, `values`, `messages`, `custom` e `debug`.

Leitura conservadora para o Maestro:

- `updates` e o modo mais compativel para adocao inicial, porque expoe apenas as mudancas por node e se aproxima mais do modelo atual de lifecycle/events.
- `values` aumenta o custo de payload e pode expor snapshots completos de state a cada passo; para CLI isso tende a ser mais verboso do que util no curto prazo.
- `messages` e util quando o valor principal esta em chunks do LLM, mas o Maestro hoje ja tem seu proprio caminho de streaming por provider; misturar os dois niveis cedo demais pode duplicar eventos.
- `custom` e interessante para emitir marcos de progresso, mas exige disciplinar um contrato de eventos para nao gerar mais uma semantica paralela a `emitter`.
- `debug` e valioso para diagnostico, porem excessivo como default e arriscado para estabilidade de logs e dashboards.

Conclusao pratica:

- Streaming nativo de grafo e um bom candidato de baixo risco para observabilidade futura.
- Ele nao exige, por si so, mudanca de modelo arquitetural nem persistencia duravel.
- O uso inicial deve ser tratado como adaptador interno de telemetria, nao como troca imediata da API externa do CLI.
- O ganho mais seguro esta em enriquecer eventos do `--multi` e, depois, do fluxo SDLC, sem substituir de uma vez o streaming que ja existe nos providers.

Risco de compatibilidade se adotado cedo demais:

- alterar formato e ordem dos eventos consumidos por testes, dashboard ou parsing de terminal;
- duplicar sinais ao combinar streaming do provider com streaming do grafo;
- aumentar acoplamento do estado interno do grafo com a interface publica de observabilidade.

Por isso, a recomendacao conservadora e:

1. primeiro consolidar o planner dentro do grafo principal;
2. depois experimentar `stream_mode="updates"` como fonte interna de timeline;
3. so por ultimo decidir se essa timeline merece exposicao publica estavel.

---

## 3.6 Avaliacao especifica sobre estado, checkpoint e retomada

As docs atuais do LangGraph tambem confirmam um ponto importante para o Maestro: retomar um fluxo "de onde parou" depende de checkpointing explicito. Na pratica, isso significa compilar o grafo com `checkpointer=...` e executar com um `configurable.thread_id` estavel. Sem isso, ha streaming e execucao normal, mas nao ha continuidade duravel entre invocacoes.

Leitura conservadora do que "continuar de onde parou" realmente significa no runtime do LangGraph:

- apos `interrupt()`, o fluxo pode ser retomado com `Command(resume=...)` usando o mesmo `thread_id`;
- apos falha, uma nova invocacao com o mesmo contexto persistido pode reaproveitar checkpoints anteriores, evitando reexecutar o que foi salvo antes da quebra;
- `get_state()` e `get_state_history()` permitem inspecao e replay de checkpoints ja persistidos;
- `update_state()` permite criar uma continuacao/fork a partir de um checkpoint existente.

Mas esse modelo traz limites que importam muito para compatibilidade:

- `InMemorySaver` ajuda em testes ou em uma unica vida de processo, mas nao entrega retomada real apos reinicio do CLI;
- retomada e checkpoint nao sao equivalentes a "transacao" de ponta a ponta: nodes posteriores ao checkpoint podem reexecutar;
- side effects externos precisam estar em boundaries estaveis e idealmente idempotentes; do contrario, resume/replay pode duplicar escrita, chamadas remotas ou alteracoes no filesystem;
- replay e fork podem repetir side effects se o node nao for idempotente;
- introduzir `thread_id` como conceito operacional afeta contrato de execucao, storage e possivel limpeza de estado;
- persistencia duravel adiciona decisao de backend, lifecycle de dados e superficie de suporte operacional.

Para o Maestro, isso leva a uma conclusao mais restritiva do que no caso de streaming:

- checkpoint/state resume nao e um proximo passo natural apenas para "usar mais LangGraph";
- ele so passa a valer a pena quando o custo de recomecar um fluxo for material ou quando houver requisito real de HITL/recovery;
- antes disso, o recurso mais seguro e apenas mapear onde o estado precisaria ser idempotente caso checkpointing fosse adotado no futuro.

Implicacoes especificas para compatibilidade do projeto:

- `maestro run` sem `--multi` nao deve ganhar estado persistente implicito;
- qualquer futura adocao deve entrar atras de flag, configuracao explicita ou adaptador interno;
- workers que executam ferramentas com side effects precisariam de revisao de idempotencia antes de qualquer rollout de resume duravel;
- qualquer piloto futuro de resume precisa mapear explicitamente quais nodes podem ser repetidos sem dano e quais precisariam de protecao adicional;
- o path guard continuaria obrigatorio dentro de cada worker, inclusive em execucoes retomadas.

Recomendacao conservadora:

1. nao introduzir checkpointer persistente nesta etapa de documentacao/plano;
2. registrar checkpointing como capacidade valida, mas dependente de evidencia de dor operacional;
3. se um piloto futuro acontecer, comecar por `--multi` e por um saver simples de ambiente controlado, nunca pelo fluxo single-agent default.

---

## 4. Matriz de Evolucao

| Area | Estado atual | Proximo estado conservador | Estado posterior desejavel |
|------|--------------|----------------------------|----------------------------|
| Single-agent `run` | `@entrypoint/@task` como wrapper fino | Manter como esta | So revisar se surgir necessidade real de hooks/checkpointing |
| Multi-agent `--multi` | Grafo principal bom, planner fora do grafo | Mover planner para dentro de um grafo ponta a ponta, sem mudar contrato externo | Extrair subgrafos reutilizaveis de planner/worker/aggregator |
| SDLC `--sprints` | DAG manual + `asyncio.gather` | Introduzir um grafo LangGraph dedicado a sprints, atras de flag ou adaptador interno | Unificar padroes de scheduler, eventos e testes com o motor multi-agent |
| Estado e reducers | Bons no modo multi-agent | Reaproveitar conventions de reducers em novos grafos | Definir modulo comum de tipos/reducers/orquestracao |
| Observabilidade | emitter e prints ad hoc | Padronizar eventos por node e transicao, com avaliacao inicial de `stream_mode="updates"` | Expor timeline/grafo de execucao de forma uniforme |
| Robustez operacional | Sem checkpointing LangGraph | Adiar checkpointing persistente ate haver evidencia de necessidade e revisar idempotencia dos nodes com side effects | Considerar primeiro streaming e subgraphs; checkpointer real so apos estabilizar os dois grafos principais |

---

## 5. Principios para Evoluir Sem Regressao

1. Nao substituir o fluxo legacy enquanto o novo fluxo nao estiver coberto por testes equivalentes.
2. Nao migrar dois pipelines ao mesmo tempo.
3. Toda ampliacao de uso de LangGraph deve entrar primeiro atras de uma fronteira existente: funcao, flag, factory ou adaptador.
4. O ganho alvo e reduzir duplicacao de motores de orquestracao, nao "usar mais LangGraph" por si so.
5. O fluxo `maestro run` sem `--multi` deve servir como ancora de compatibilidade e nao deve ser refatorado cedo.

---

## 6. Plano Incremental, Conservador e Orientado a TDD

### Fase 0 - Baseline e blindagem de compatibilidade

**Objetivo:** congelar o comportamento atual antes de qualquer evolucao arquitetural.

**Alvo TDD:** adicionar ou consolidar testes que descrevem o comportamento atual, sem mudar implementacao.

**Testes primeiro:**
- `tests/test_agent_loop.py` e `tests/test_agent_loop_provider.py`: garantir que `maestro run` continua identico no fluxo single-agent.
- `tests/test_scheduler_workers.py`: garantir fan-out, reentrada e reduçao segura no `--multi`.
- `tests/test_aggregator_guardrails.py`: garantir que guardrails continuam encerrando o fluxo corretamente.
- `tests/test_dashboard_integration.py`: garantir que eventos emitidos pelo multi-agent continuam estaveis.
- Testes de `discover --sprints`: congelar ordem por waves, paralelismo por sprint e comportamento de gates.

**Criterio de saida:** existe uma baseline de regressao explicita para os tres modos relevantes: single-agent, multi-agent e discovery com sprints.

### Fase 1 - Colocar o planner dentro do fluxo LangGraph do multi-agent

**Objetivo:** transformar `run_multi_agent()` em um pipeline realmente ponta a ponta sob um unico grafo, sem alterar a interface externa.

**Mudanca arquitetural minima:**
- Adicionar um node `planner` ao `StateGraph` do multi-agent.
- Fazer `START -> planner -> scheduler`.
- Preservar `planner_node()` e sua logica atual, apenas mudando o ponto de invocacao.

**Por que isso vem cedo:**
- E a maior melhoria de coerencia com o menor raio de mudanca.
- Nao muda prompts, reducers, workers nem agregacao.

**TDD sugerido:**
1. Escrever teste falhando provando que o grafo passa pelo planner antes do scheduler.
2. Escrever teste falhando provando que erro de planner impede dispatch de workers.
3. Implementar a costura minima no grafo.
4. Rodar toda a suite atual de multi-agent.

**Criterio de saida:** `run_multi_agent()` continua com a mesma API publica, mas o planner deixa de ser um pre-step externo.

### Fase 2 - Extrair um "padrao de grafo" reutilizavel, sem genericismo excessivo

**Objetivo:** reduzir duplicacao conceitual entre o grafo multi-agent e futuros grafos internos.

**Mudanca arquitetural minima:**
- Extrair apenas o que ja provou ser estavel: conventions de state, helpers de lifecycle, e um pequeno conjunto de utilitarios de roteamento/terminacao.
- Nao criar um framework interno generico de DAG nesta fase.

**TDD sugerido:**
1. Escrever testes unitarios para helpers puros antes da extracao.
2. Mover helpers sem alterar comportamento.
3. Verificar que imports mudaram, mas os testes de comportamento nao.

**Criterio de saida:** o projeto passa a ter um nucleo reutilizavel pequeno para grafos LangGraph, sem abstrair cedo demais.

### Fase 3 - Introduzir uma versao LangGraph para `discover --sprints`, atras de fronteira interna

**Objetivo:** eliminar o segundo motor de orquestracao paralela sem tocar no modo sequencial legacy.

**Mudanca arquitetural minima:**
- Preservar `_run_sequential()` intacto.
- Preservar contrato externo de `DiscoveryHarness`.
- Criar um caminho interno alternativo para `_run_with_sprints()` baseado em LangGraph.
- Manter a definicao de sprints e dependencias como fonte de verdade; trocar apenas o motor executor.

**Por que esta fase nao deve vir antes da Fase 1:**
- O risco de regressao no SDLC e maior.
- O projeto ainda nao tem um padrao de grafo consolidado para reutilizar.

**TDD sugerido:**
1. Congelar em testes a ordem de waves atual produzida por `get_ready_artifacts()`.
2. Congelar em testes quais artefatos podem rodar em paralelo por sprint.
3. Escrever teste falhando para a nova execucao via grafo com o mesmo resultado observavel.
4. Implementar um adapter que consuma `SPRINTS` e emita os mesmos artefatos/eventos.
5. Rodar testes de gates, reflect e writer para garantir que nada mudou acima do orquestrador.

**Criterio de saida:** `discover --sprints` continua entregando os mesmos artefatos, na mesma ordem logica, mas passa a compartilhar o paradigma de orquestracao do resto do produto.

### Fase 4 - Unificar observabilidade de execucao entre grafos

**Objetivo:** fazer com que multi-agent e SDLC emitam eventos com semantica parecida de node start, node done, falha e output.

**Mudanca arquitetural minima:**
- Definir um contrato pequeno de eventos.
- Adaptar emissores existentes (`emitter`, lifecycle prints) sem trocar a interface publica do CLI.
- Avaliar `graph.stream()` / `graph.astream()` em `stream_mode="updates"` como fonte interna de timeline, sem expor isso como contrato publico neste primeiro passo.

**TDD sugerido:**
1. Testes de integracao de eventos primeiro.
2. Adaptacao dos nodes para o contrato comum.
3. Revalidacao do dashboard e logs do terminal.

**Criterio de saida:** o Maestro passa a ter uma semantica de execucao consistente mesmo quando usa grafos diferentes.

### Fase 5 - Reavaliar checkpointing e persistencia somente com evidencia

**Objetivo:** decidir com base em dor real se vale adotar recursos mais avancados do ecossistema LangGraph.

**Recursos a reavaliar nessa fase:**
- checkpointer persistente para durable execution
- `interrupt()` / `Command(...)` para human-in-the-loop nativo
- `graph.stream()` / `graph.astream()` para timeline de grafo
- subgraphs para modularizar planner, discovery e execution
- `get_state()` / `get_state_history()` / `update_state()` para inspecao, replay e eventual continuacao controlada

**Nao fazer antes:**
- checkpointer persistente
- recovery interativo
- memoria cross-run
- human-in-the-loop approval no meio do grafo
- retomada duravel de workers com side effects sem revisao de idempotencia

**Justificativa:** isso aumenta superficie de estado e risco operacional. Hoje a maior oportunidade ainda e coerencia arquitetural e observabilidade consistente, nao persistencia duravel.

---

## 7. Ordem Recomendada de Execucao

1. Fase 0 para congelar baseline e reduzir risco de regressao invisivel.
2. Fase 1 para fechar a principal incoerencia do fluxo `--multi` com baixo risco.
3. Fase 2 para extrair somente o que ficou nitidamente estavel.
4. Fase 3 para migrar `discover --sprints` com seguranca.
5. Fase 4 para unificar telemetria e visibilidade.
6. Fase 5 apenas se surgirem requisitos operacionais que justifiquem maior complexidade.

---

## 8. O Que Nao Recomendo Agora

- Reescrever `_run_agentic_loop()` como grafo detalhado.
- Trocar o fluxo single-agent por `StateGraph` apenas por consistencia estetica.
- Unificar tudo num framework interno grande antes da migracao de sprints.
- Introduzir checkpointing/persistencia LangGraph sem caso de uso comprovado.
- Expor resume/replay como promessa publica do CLI antes de decidir storage, `thread_id` e semantica de idempotencia.
- Tocar simultaneamente em `--multi` e `discover --sprints` na mesma entrega.

Esses movimentos aumentam muito o risco e geram pouco retorno imediato.

---

## 9. Recomendacao Final

Se o objetivo e aumentar o aproveitamento do LangGraph sem quebrar compatibilidade, o melhor plano nao e expandir o uso de forma horizontal em todo o repositorio. O melhor plano e:

1. consolidar o `--multi` como pipeline LangGraph de ponta a ponta,
2. extrair um nucleo pequeno de convencoes reutilizaveis,
3. migrar `discover --sprints` para esse mesmo paradigma somente depois da baseline estar protegida por testes.

Isso aumenta o aproveitamento real do LangGraph onde ele reduz duplicacao arquitetural, preserva o fluxo single-agent como ancora de compatibilidade, e mantem a evolucao alinhada com TDD e com o perfil conservador exigido pelo projeto.

---

## Referencias do Codigo

- `maestro/agent.py:584-605`
- `maestro/multi_agent.py:146-340`
- `maestro/multi_agent.py:600-823`
- `maestro/planner/node.py:172-252`
- `maestro/planner/schemas.py:42-110`
- `maestro/sdlc/harness.py:99-263`
- `maestro/sdlc/sprints.py:1-163`
