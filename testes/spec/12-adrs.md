# ADRs para validação do fluxo de pausa de gaps

## ADR 001 — Escopo do fluxo: apenas pausa temporária, em web
**Status:** Em validação

**Contexto**  
O escopo informado limita a evolução à ação de pausar gaps. O fluxo será usado no canal web, seguirá o fluxo já existente e deve respeitar as restrições de idioma e nomenclatura da aplicação.

**Decisão**  
- Implementar somente a ação de **pausar temporariamente** o gap.
- Não expandir este fluxo para editar, comentar, reabrir ou finalizar gaps.
- Reaproveitar o fluxo existente como referência funcional e de navegação.
- Exibir rótulos, botões e mensagens de acordo com a restrição de idioma definida para o produto.

**Consequências**  
- Redução de escopo e de risco funcional.
- Menor chance de divergência entre o novo comportamento e o fluxo já existente.
- Outras jornadas ficam fora deste ADR.

---

## ADR 002 — Modelo de estado, reversibilidade e controle de pausas
**Status:** Em validação

**Contexto**  
A pausa é reversível, possui tempo máximo, pode ocorrer mais de uma vez no mesmo gap e seu comportamento varia conforme tipo e status atual. Também há impacto em SLA e necessidade de histórico.

**Decisão**  
- Tratar a pausa como um **estado temporário de suspensão**.
- Manter suporte à **reativação** do gap após a pausa.
- Registrar histórico de cada ocorrência de pausa.
- Validar a elegibilidade da pausa conforme o **status atual** e o **tipo do gap**.
- Aplicar o **tempo máximo de pausa** definido pela regra de negócio.
- Tratar pausas repetidas no mesmo gap como ocorrências distintas, com rastreabilidade.
- Considerar o estado de pausa no tratamento de **SLA**.

**Consequências**  
- A implementação precisa armazenar data/hora de início e fim, usuário e motivo.
- O fluxo precisa controlar expiração e histórico.
- O comportamento fica dependente do estado atual e do tipo do gap.

---

## ADR 003 — UI com opções fixas, coerentes e confirmação obrigatória
**Status:** Em validação

**Contexto**  
As opções da interface precisam ser coerentes, o conjunto deve ser fixo e o fluxo exige confirmação antes da execução. Também é necessário exibir mensagens de sucesso e erro.

**Decisão**  
- Expor na UI um **conjunto fixo de opções**, sem configuração dinâmica.
- Vincular os motivos da pausa a esse conjunto fixo, com validação.
- Exigir **confirmação explícita** antes de executar a pausa.
- Exibir mensagens de **sucesso** e **erro** ao usuário.
- Garantir consistência entre o texto da interface, a nomenclatura do produto e a documentação de referência.

**Consequências**  
- A experiência de uso fica previsível e consistente.
- Mudanças nas opções exigirão alteração controlada no produto.
- A validação fica mais simples e menos sujeita a divergências entre telas.

---

## ADR 004 — Validação de negócio centralizada no backend
**Status:** Em validação

**Contexto**  
O fluxo precisa validar regras de negócio, incluindo motivos inválidos, status permitidos e comportamento diferente por tipo de gap. Há também uma separação de permissões para visualização.

**Decisão**  
- Centralizar a **validação de negócio** no backend ou no workflow responsável.
- Fazer com que a UI apenas reflita o que o backend autoriza.
- Bloquear a pausa quando houver motivo inválido, ausência de motivo obrigatório ou status/tipo incompatível.
- Tratar permissões de **visualização** como um concern independente do ato de pausar.
- Respeitar o comportamento diferenciado por **tipo de gap** e por **status atual**.

**Consequências**  
- O backend passa a ser a fonte de verdade das regras.
- A UI fica mais leve e menos propensa a inconsistências.
- Mudanças de regra não dependem exclusivamente de ajuste visual.

---

## ADR 005 — Auditoria, notificações, segurança e relatórios
**Status:** Em validação

**Contexto**  
O fluxo exige auditoria com data, hora, usuário e motivo, integração com notificações, requisitos de segurança e necessidade de relatórios/indicadores.

**Decisão**  
- Registrar **auditoria completa** de cada pausa.
- Integrar o evento de pausa com o sistema de **notificações**.
- Persistir dados suficientes para **relatórios e indicadores** sobre gaps pausados.
- Considerar **requisitos de segurança e compliance** no acesso e no rastreamento.
- Monitorar o **limite operacional** de gaps pausados simultaneamente.

**Consequências**  
- Maior rastreabilidade e suporte a análise operacional.
- Dependência de integrações de notificação e de consumo de dados para relatórios.
- Maior exigência de controle e observabilidade do fluxo.

---

Se quiser, eu também posso transformar esses ADRs em um formato mais formal de repositório, com numeração, data, autor e seção de “alternativas consideradas”.