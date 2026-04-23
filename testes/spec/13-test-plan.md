# Plano de Testes — Fluxo completo de pausa de gaps

## 1. Objetivo

Validar as **regras de negócio** do fluxo **web** de **pausa temporária de gaps**, cobrindo:

- confirmação antes da execução
- motivo obrigatório e motivos inválidos
- opções de UI fixas e coerentes
- regras por tipo e status do gap
- reversibilidade da pausa
- limite máximo de pausa
- efeitos colaterais após pausar
- impacto em SLA
- auditoria e histórico
- integrações com notificações
- restrições de segurança
- limites operacionais
- comportamento conforme documentação e fluxo existente

---

## 2. Escopo

### Incluído
- Ação de **pausar** gap
- Tela web e seus componentes de UI
- Modal/etapa de confirmação
- Validação de motivo
- Regras de elegibilidade para pausar
- Tratamento de gaps em status intermediário
- Tratamento por tipo de gap
- Regras para múltiplas pausas no mesmo gap
- Validação de tempo máximo de pausa
- Registro de auditoria
- Histórico de alterações de estado
- Disparo de notificações
- Impacto em SLA, prazos e métricas relacionadas
- Limites operacionais para gaps pausados simultaneamente
- Mensagens de sucesso e erro
- Comportamento com restrições de idioma
- Regra de permissões de visualização

### Fora do escopo
- Editar gap
- Comentar gap
- Reabrir gap fora do contexto de reversibilidade da pausa
- Finalizar gap
- Outras funcionalidades não ligadas diretamente ao fluxo de pausa

---

## 3. Estratégia de teste

A estratégia será **baseada em risco** e em **regras de negócio**, priorizando cenários que afetam:

1. **Elegibilidade da pausa**
   - status atual
   - tipo do gap
   - permissões
   - limite operacional
   - múltiplas pausas

2. **Consistência da UI**
   - opções fixas
   - labels em idioma correto
   - confirmação obrigatória
   - mensagens de erro e sucesso
   - comportamento visual coerente com a documentação e fluxo existente

3. **Efeitos sistêmicos**
   - auditoria
   - histórico
   - notificações
   - impacto em SLA
   - relatórios/indicadores

4. **Segurança e controle de acesso**
   - visibilidade por perfil
   - proteção contra ação indevida

5. **Regressão**
   - compatibilidade com o fluxo já existente
   - ausência de impacto em demais comportamentos relacionados

---

## 4. Tipos de teste

## 4.1 Testes unitários
Foco em lógica isolada, validações e regras puras.

### Coberturas principais
- validação de elegibilidade para pausa
- validação de status do gap
- validação de tipo do gap
- validação de motivo obrigatório
- rejeição de motivos inválidos
- regra de tempo máximo de pausa
- regra de múltiplas pausas
- regra de limite operacional de gaps pausados
- regra de reversibilidade da pausa
- geração de payload de auditoria
- disparo das ações subsequentes previstas
- lógica de impacto em SLA
- lógica de autorização para ações permitidas

### Critérios unitários esperados
- cada regra deve ter casos positivos e negativos
- entradas inválidas devem retornar erro controlado
- a lista de opções da UI deve permanecer fixa conforme a base de referência
- mensagens e códigos de validação devem ser consistentes

---

## 4.2 Testes de integração
Foco na comunicação entre camadas e sistemas envolvidos.

### Coberturas principais
- front-end web → backend
- backend → persistência
- gravação de histórico
- gravação de auditoria com data, hora, usuário e motivo
- integração com notificações
- atualização de estado após pausa
- atualização de SLA e dados associados
- compatibilidade com o fluxo existente
- resposta correta para falhas de integração

### Cenários de integração
- pausa executada com sucesso e refletida na base
- falha no envio de notificação sem corromper o estado principal
- persistência correta do motivo e do usuário
- histórico atualizado após pausa
- relatórios/indicadores refletindo a nova condição do gap

---

## 4.3 Testes end-to-end (E2E)
Foco na jornada completa do usuário no web.

### Fluxos principais
1. usuário com permissão de visualização acessa o gap
2. sistema exibe a ação conforme as regras definidas
3. usuário inicia a pausa
4. sistema exibe opções fixas e coerentes na UI
5. usuário seleciona um motivo válido
6. sistema exige confirmação
7. usuário confirma
8. sistema executa a pausa
9. sistema exibe mensagem de sucesso
10. sistema registra auditoria e histórico
11. sistema dispara notificações
12. sistema atualiza SLA e demais efeitos previstos

### Fluxos alternativos e exceções
- tentativa de pausar sem motivo
- tentativa de pausar com motivo inválido
- tentativa de pausar em status não elegível
- tentativa de pausar um gap já submetido a outra condição intermediária
- tentativa de pausar acima do limite operacional
- tentativa com perfil sem permissão adequada
- validação do comportamento quando o gap já está pausado
- validação da reversibilidade da pausa conforme a regra definida

---

## 5. Cobertura de testes

## 5.1 Cobertura funcional mínima
A cobertura deve garantir validação de:

- 100% dos caminhos críticos de pausa
- 100% das validações obrigatórias do fluxo
- 100% dos estados previstos para o fluxo de pausa
- 100% das variações por tipo de gap
- 100% das variações por status do gap
- 100% dos cenários de motivo obrigatório e motivos inválidos
- 100% dos cenários de confirmação
- 100% dos efeitos subsequentes após a pausa
- 100% dos casos de auditoria e histórico
- 100% dos casos de notificação
- 100% dos impactos em SLA
- 100% dos casos de segurança relacionados ao fluxo
- 100% dos casos de idioma e nomenclatura da UI
- 100% dos cenários de regressão do fluxo existente

## 5.2 Cobertura de UI
Validar:
- exibição apenas das opções fixas previstas
- consistência visual entre tela, modal e mensagens
- nomenclatura coerente com o idioma definido
- presença de confirmação
- estados de carregamento, sucesso e erro
- comportamento de botões e ações indisponíveis

## 5.3 Cobertura de dados
Validar:
- motivo selecionado
- usuário que executou a ação
- data e hora
- estado anterior e novo estado
- histórico de alterações
- registro de auditoria
- refletividade em relatórios e indicadores

## 5.4 Cobertura de integração
Validar:
- notificações disparadas corretamente
- persistência correta
- atualização do SLA
- compatibilidade com o fluxo já existente
- tratamento de falhas entre componentes

---

## 6. Matriz de cenários recomendada

| Dimensão | Variações a cobrir |
|---|---|
| Tipo de gap | tipos suportados pela documentação |
| Status atual | status elegíveis e não elegíveis |
| Permissão | perfis com visualização e perfis sem acesso à ação |
| Motivo | válido, obrigatório ausente, inválido |
| UI | opções fixas, idioma, confirmação, mensagens |
| Reversibilidade | pausa ativa e retorno conforme regra definida |
| Limite operacional | abaixo, no limite, acima |
| Múltiplas pausas | primeira pausa, nova pausa, bloqueio ou tratamento previsto |
| SLA | sem impacto, com impacto esperado |
| Notificação | sucesso, falha, reprocessamento conforme política |
| Auditoria/histórico | registro completo e consistente |

---

## 7. Critérios de entrada

Os testes podem iniciar quando houver:

- documentação do fluxo disponível
- referência do fluxo existente disponível
- regras e opções fixas definidas
- ambiente web configurado
- massa de dados preparada
- perfis de acesso configurados
- integração de notificações disponível ou simulada
- base de auditoria e histórico disponível
- critérios de negócio mínimos confirmados para execução

---

## 8. Critérios de saída

A validação será considerada concluída quando:

- todos os cenários críticos passarem
- as validações obrigatórias estiverem cobertas
- não houver defeitos bloqueadores ou críticos abertos
- o comportamento da UI estiver consistente com a documentação
- a auditoria e o histórico estiverem corretos
- as notificações forem disparadas conforme esperado
- o impacto em SLA estiver validado
- os limites operacionais forem respeitados
- a regressão do fluxo existente estiver aprovada
- as mensagens de erro e sucesso estiverem consistentes
- houver aprovação formal da entrega de teste

---

## 9. Riscos e pontos de atenção

- divergência entre documentação e comportamento real da UI
- inconsistência entre front-end e backend
- falhas no disparo de notificações
- efeito incorreto em SLA
- auditoria incompleta
- comportamento diferente por tipo ou status sem cobertura adequada
- falhas de localidade/idioma nas opções e mensagens
- limite operacional não aplicado corretamente
- regressão no fluxo existente após a implementação da pausa

---

## 10. Prioridade de execução

1. fluxo feliz de pausa
2. validações obrigatórias
3. confirmação
4. status e tipo do gap
5. múltiplas pausas e reversibilidade
6. impacto em SLA
7. auditoria e histórico
8. notificações
9. segurança e permissões
10. limites operacionais
11. regressão do fluxo existente
12. validação de idioma e coerência visual

---

Se quiser, posso transformar este plano em uma **tabela de casos de teste** com colunas como *cenário, pré-condição, passos, resultado esperado e prioridade*.