# Modelo de dados para o fluxo de pausa de gaps

Com base nas respostas informadas, a pausa é **temporária**, **reversível**, exige **motivo obrigatório**, **confirmação prévia**, gera **auditoria**, **notificações**, impacta **SLA** e possui **catálogo fixo de opções** com **restrições de idioma**.  
Para suportar isso sem assumir valores não informados, o desenho separa o **estado do gap** do **estado da pausa**.

## Entidades principais

### 1) `Gap`
Representa o gap do domínio.

**Atributos**
- `id_gap` (PK)
- `id_tipo_gap` (FK para `TipoGap`)
- `id_status_gap` (FK para `StatusGap`)
- `data_criacao`
- `data_atualizacao`

**Relacionamentos**
- Um `Gap` pertence a um `TipoGap`
- Um `Gap` possui um `StatusGap`
- Um `Gap` pode ter várias `SessaoPausaGap`
- Um `Gap` pode ter vários `HistoricoEstadoGap`
- Um `Gap` pode ter vários `VinculoGap`
- Um `Gap` pode ter vários registros de `ImpactoSLA`

---

### 2) `TipoGap`
Catálogo de tipos de gap.

**Atributos**
- `id_tipo_gap` (PK)
- `codigo_tipo`
- `chave_label_idioma`

**Regras**
- O comportamento da pausa varia conforme o tipo do gap
- O rótulo deve ser exibido conforme o idioma configurado

---

### 3) `StatusGap`
Catálogo de status do gap.

**Atributos**
- `id_status_gap` (PK)
- `codigo_status`
- `chave_label_idioma`
- `ordem_exibicao`

**Regras**
- O comportamento da pausa varia conforme o status atual do gap
- O status usado na validação deve ser o status vigente no momento da solicitação

---

### 4) `MotivoPausaGap`
Catálogo fixo de motivos de pausa.

**Atributos**
- `id_motivo_pausa` (PK)
- `codigo_motivo`
- `chave_label_idioma`
- `ordem_exibicao`

**Regras**
- Catálogo fechado
- Motivo obrigatório para pausar
- Motivos inválidos não devem estar cadastrados no catálogo
- A UI deve apresentar apenas os motivos válidos e localizados no idioma adequado

---

### 5) `PoliticaPausaGap`
Define a elegibilidade da pausa por tipo e status.

**Atributos**
- `id_politica_pausa` (PK)
- `id_tipo_gap` (FK para `TipoGap`)
- `id_status_gap` (FK para `StatusGap`)
- `permite_pausa`
- `exige_confirmacao`
- `exige_motivo`
- `prazo_maximo_pausa`
- `exige_notificacao`

**Relacionamentos**
- Um `TipoGap` pode ter várias políticas
- Um `StatusGap` pode ter várias políticas

**Regras**
- O par `tipo/status` define se a pausa é permitida
- Deve existir uma política por combinação relevante de tipo e status
- O prazo máximo de pausa é validado por essa política

---

### 6) `SessaoPausaGap`
Entidade central do fluxo de pausa.

**Atributos**
- `id_sessao_pausa` (PK)
- `id_gap` (FK para `Gap`)
- `id_politica_pausa` (FK para `PoliticaPausaGap`)
- `id_motivo_pausa` (FK para `MotivoPausaGap`)
- `id_status_gap_original` (FK para `StatusGap`)
- `status_pausa`
- `usuario_solicitante`
- `data_solicitacao`
- `usuario_confirmador`
- `data_confirmacao`
- `usuario_encerrador`
- `data_encerramento`
- `prazo_limite_encerramento`
- `data_atualizacao`

**Relacionamentos**
- Um `Gap` possui várias sessões de pausa ao longo do tempo
- Cada sessão referencia um motivo fixo
- Cada sessão referencia a política que validou a operação

**Regras**
- Guarda o status do gap antes da pausa
- Suporta reversibilidade por meio de encerramento da sessão
- Permite histórico de múltiplas pausas no mesmo gap, desde que não haja sobreposição de pausas abertas
- A pausa só se torna efetiva após confirmação
- O prazo máximo deve ser calculado e controlado por sessão

---

### 7) `HistoricoEstadoPausaGap`
Histórico das transições da pausa.

**Atributos**
- `id_historico_pausa` (PK)
- `id_sessao_pausa` (FK para `SessaoPausaGap`)
- `estado_origem`
- `estado_destino`
- `usuario`
- `data_hora`
- `codigo_evento`

**Regras**
- Registra toda transição de estado da pausa
- Atende ao requisito de histórico de alterações do estado de pausa

---

### 8) `HistoricoEstadoGap`
Histórico das transições do gap.

**Atributos**
- `id_historico_gap` (PK)
- `id_gap` (FK para `Gap`)
- `status_origem`
- `status_destino`
- `id_sessao_pausa` (FK opcional para `SessaoPausaGap`)
- `usuario`
- `data_hora`
- `codigo_evento`

**Regras**
- Registra o efeito da pausa e da retomada no status do gap
- Suporta auditoria e relatórios

---

### 9) `LogAuditoria`
Auditoria do fluxo.

**Atributos**
- `id_auditoria` (PK)
- `entidade`
- `id_entidade`
- `acao`
- `usuario`
- `data_hora`
- `detalhes_evento`

**Regras**
- Obrigatório para ações de pausa, confirmação, retomada e validação
- Deve registrar data, hora, usuário e motivo

---

### 10) `NotificacaoGap`
Registro das notificações disparadas pelo evento de pausa.

**Atributos**
- `id_notificacao` (PK)
- `id_sessao_pausa` (FK para `SessaoPausaGap`)
- `tipo_notificacao`
- `destinatario`
- `canal`
- `status_envio`
- `data_envio`

**Regras**
- Deve ser criada após o evento de pausa quando a política exigir notificação
- Suporta integração com notificações

---

### 11) `ImpactoSLA`
Registro do impacto da pausa sobre SLA e contagem de tempo.

**Atributos**
- `id_impacto_sla` (PK)
- `id_gap` (FK para `Gap`)
- `id_sessao_pausa` (FK para `SessaoPausaGap`)
- `inicio_interrupcao`
- `fim_interrupcao`
- `duracao_interrupcao`
- `status_sla`

**Regras**
- O tempo em pausa deve ser excluído ou suspenso da contagem de SLA conforme a regra vigente
- Permite relatórios e indicadores

---

### 12) `VinculoGap`
Vínculos, dependências ou subtarefas associados ao gap.

**Atributos**
- `id_vinculo_gap` (PK)
- `id_gap` (FK para `Gap`)
- `tipo_relacao`
- `tipo_entidade_relacionada`
- `id_entidade_relacionada`
- `status_vinculo`

**Regras**
- Permite representar dependências sem assumir o comportamento funcional específico delas
- Suporta o tratamento de vínculos afetados pela pausa

---

### 13) `LimiteOperacionalPausa`
Controle do limite operacional de gaps pausados simultaneamente.

**Atributos**
- `id_limite_operacional` (PK)
- `escopo_limite`
- `valor_limite`
- `vigencia_inicio`
- `vigencia_fim`

**Regras**
- Valida o número de gaps pausados simultaneamente
- O valor do limite deve ser parametrizado
- Pode ser aplicado em escopo global ou no escopo definido pelo negócio

---

## Relacionamentos principais

- `TipoGap` 1:N `Gap`
- `StatusGap` 1:N `Gap`
- `TipoGap` 1:N `PoliticaPausaGap`
- `StatusGap` 1:N `PoliticaPausaGap`
- `Gap` 1:N `SessaoPausaGap`
- `MotivoPausaGap` 1:N `SessaoPausaGap`
- `PoliticaPausaGap` 1:N `SessaoPausaGap`
- `SessaoPausaGap` 1:N `HistoricoEstadoPausaGap`
- `Gap` 1:N `HistoricoEstadoGap`
- `SessaoPausaGap` 1:N `NotificacaoGap`
- `SessaoPausaGap` 1:N `ImpactoSLA`
- `Gap` 1:N `VinculoGap`
- `Gap` 1:N `LogAuditoria`

---

## Restrições e validações

1. **Motivo obrigatório**
   - Não permitir pausa sem `id_motivo_pausa`

2. **Catálogo fixo**
   - Motivos, tipos, status e estados devem vir de catálogo fechado
   - Não aceitar texto livre para motivo

3. **Confirmação obrigatória**
   - A sessão não pode ficar efetiva sem confirmação explícita

4. **Elegibilidade por tipo/status**
   - A pausa só é permitida quando `PoliticaPausaGap.permite_pausa = true`

5. **Reversibilidade**
   - A sessão de pausa deve possuir campos para encerramento/retomada
   - O status original do gap deve ser preservado

6. **Prazo máximo**
   - `prazo_limite_encerramento` deve ser calculado com base na política
   - Bloquear ou sinalizar ultrapassagem conforme regra de negócio

7. **Histórico obrigatório**
   - Toda alteração de estado da pausa e do gap deve gerar histórico

8. **Auditoria obrigatória**
   - Registrar usuário, data/hora, ação e motivo em `LogAuditoria`

9. **Notificações**
   - Disparar `NotificacaoGap` quando a política ou o fluxo exigir

10. **SLA**
   - Durante a pausa, o SLA deve ficar suspenso ou ter sua contagem ajustada

11. **Permissões separadas**
   - Visualização e pausa devem usar permissões distintas
   - A permissão de pausa deve ser verificada antes de criar ou confirmar a sessão

12. **Limite operacional**
   - Impedir ou sinalizar novas pausas quando o limite de gaps pausados simultaneamente for atingido

13. **Idioma**
   - Rótulos, mensagens e opções exibidas na UI devem respeitar a restrição de idioma
   - Os códigos de domínio devem ser independentes do idioma

14. **Sem sobreposição de pausa aberta no mesmo gap**
   - O modelo deve impedir que o mesmo gap tenha duas sessões de pausa abertas ao mesmo tempo

---

## Observação de implementação

Como o escopo informado é **apenas pausar**, o modelo não cria entidades para editar, comentar, reabrir ou finalizar gaps como funcionalidades independentes.  
A reversão da pausa é tratada dentro da própria `SessaoPausaGap`, preservando o escopo e mantendo o histórico completo.

Se quiser, posso transformar este modelo em:
- **DDL SQL**
- **diagrama ER textual**
- **matriz de validação/regra de negócio por estado**