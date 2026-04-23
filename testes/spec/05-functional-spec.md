# Especificação Funcional — Fluxo de Pausa de Gaps

## 1. Objetivo funcional

Permitir que um **gap** seja **suspenso temporariamente** no sistema web, com controle de permissões, confirmação explícita, registro de auditoria, histórico de alterações, impacto em SLA, integração com notificações e regras de validação compatíveis com o tipo e o status atual do gap.

O escopo desta funcionalidade cobre:

- **pausar** um gap;
- **reativar** um gap previamente pausado;
- registrar os efeitos sistêmicos da pausa e da reativação.

Não fazem parte deste escopo: editar, comentar, encerrar ou executar outras ações fora do fluxo de pausa.

---

## 2. Contexto funcional

O fluxo deve seguir a lógica já existente no módulo de gaps, reaproveitando a navegação e os padrões de interação já adotados no produto.

A experiência deve ser exclusivamente **web**.

Todas as etiquetas, botões, mensagens e rótulos devem respeitar o **idioma configurado no produto**.

---

## 3. Regras de acesso e permissões

### 3.1 Visualização

As permissões de visualização são independentes das permissões de ação. Portanto:

- um usuário só acessa o gap se tiver permissão de visualização;
- ter permissão de visualização **não implica** permissão para pausar ou reativar.

### 3.2 Ação de pausar

A ação de pausar deve ser exibida somente para usuários autorizados a executar essa operação.

### 3.3 Ação de reativar

A reativação também deve respeitar autorização específica do fluxo, seguindo o mesmo padrão de controle de acesso.

### 3.4 Segurança

As validações de permissão devem ocorrer no front-end e, obrigatoriamente, no back-end.

Se o usuário tentar acionar a operação sem permissão, o sistema deve bloquear a ação.

---

## 4. Estados do gap no fluxo de pausa

O sistema deve considerar pelo menos os seguintes comportamentos de estado:

- **estado atual elegível para pausa**;
- **estado intermediário elegível para pausa**;
- **estado pausado**;
- **estado após reativação**, retornando ao estado anterior elegível conforme o fluxo existente.

### 4.1 Antes da pausa

O gap pode estar em um estado ativo ou intermediário, desde que o status atual seja elegível pela regra do produto.

### 4.2 Durante a pausa

O gap passa para o estado de pausa temporária.

### 4.3 Depois da pausa

Ao ser reativado, o gap volta ao estado anterior permitido pelo fluxo.

---

## 5. Interface web

## 5.1 Acesso à ação

Na tela de detalhe do gap, o sistema deve exibir uma ação coerente com o estado atual:

- se o gap estiver elegível para suspensão, exibir a ação **Pausar gap**;
- se o gap já estiver pausado, exibir a ação **Reativar gap**;
- se o gap não for elegível, a ação deve ser ocultada ou desabilitada conforme o padrão do produto.

### 5.2 Modal de confirmação

Ao clicar em **Pausar gap**, o sistema deve abrir uma confirmação antes de efetivar a ação.

O modal deve conter:

- título relacionado à pausa do gap;
- identificação do gap;
- status atual do gap;
- indicação do impacto da pausa;
- campo obrigatório para seleção do motivo;
- botões **Cancelar** e **Confirmar**.

### 5.3 Opções coerentes da interface

Como as opções devem ser fixas, a interface não deve permitir texto livre para motivo.

As opções coerentes do fluxo são:

1. **Pausar gap**
2. **Selecionar motivo da pausa** em lista fixa
3. **Cancelar**
4. **Confirmar pausa**
5. **Reativar gap** quando o gap já estiver pausado

O sistema deve apresentar apenas opções compatíveis com o estado atual e com o tipo do gap.

### 5.4 Botões e rótulos

- O botão principal deve ser claro e direto.
- O texto dos botões deve seguir a nomenclatura do idioma ativo.
- O mesmo padrão visual deve ser mantido no fluxo existente.

### 5.5 Feedback ao usuário

O sistema deve informar o resultado da operação por mensagem de sucesso ou erro.

---

## 6. Fluxo de pausa

### 6.1 Início da ação

1. O usuário acessa a tela do gap.
2. O sistema verifica se o gap está elegível para pausa.
3. Se elegível, a ação **Pausar gap** é exibida.

### 6.2 Confirmação

4. O usuário clica em **Pausar gap**.
5. O sistema abre o modal de confirmação.
6. O usuário seleciona um motivo válido na lista fixa.
7. O usuário confirma a operação.

### 6.3 Validação

8. O sistema valida:
   - permissão do usuário;
   - elegibilidade do status atual;
   - tipo do gap;
   - motivo selecionado;
   - limite operacional de gaps pausados simultaneamente;
   - prazo máximo de pausa.

### 6.4 Persistência

9. Se todas as validações forem aprovadas, o sistema grava a mudança de estado.
10. O gap passa para o estado de pausa temporária.

### 6.5 Pós-processamento

11. O sistema registra auditoria.
12. O sistema atualiza o histórico do gap.
13. O sistema dispara notificações.
14. O sistema aplica o efeito sobre SLA.
15. O sistema registra os efeitos sobre dependências/vínculos conforme a regra do fluxo existente.

---

## 7. Fluxo de reativação

### 7.1 Disponibilidade

A reativação só deve ser permitida quando o gap estiver no estado de pausa.

### 7.2 Execução

1. O usuário aciona **Reativar gap**.
2. O sistema valida permissão e elegibilidade.
3. O sistema confirma a ação.
4. O gap retorna ao estado anterior previsto pelo fluxo.

### 7.3 Efeitos após reativação

- o histórico deve registrar a saída da pausa;
- a auditoria deve ser atualizada;
- as notificações aplicáveis devem ser disparadas;
- o comportamento do SLA deve voltar ao padrão definido para o estado reativado.

---

## 8. Regras de negócio

### 8.1 Pausa temporária

A pausa significa **suspensão temporária**, não bloqueio permanente e não encerramento do gap.

### 8.2 Motivo obrigatório

O motivo da pausa é obrigatório.

O sistema deve impedir a confirmação sem seleção de um motivo válido.

### 8.3 Motivos válidos e inválidos

Como as opções são fixas:

- apenas motivos presentes na lista fixa podem ser aceitos;
- qualquer valor fora da lista é inválido;
- texto livre não é permitido;
- motivo incompatível com tipo ou status do gap é inválido;
- motivo manipulado no envio da requisição é inválido.

### 8.4 Diferença por tipo de gap

O comportamento deve variar conforme o tipo do gap.

Essa variação deve refletir:

- disponibilidade da ação;
- lista de motivos válidos;
- regras de notificação;
- elegibilidade de pausa e reativação.

### 8.5 Diferença por status atual

O comportamento também deve variar conforme o status atual.

O sistema deve impedir a pausa quando o status atual não permitir a transição.

### 8.6 Estados intermediários

É permitido pausar um gap que esteja em estado intermediário, desde que esse estado seja elegível pelas regras do fluxo existente.

### 8.7 Múltiplas pausas no mesmo gap

O sistema deve manter histórico de múltiplos ciclos de pausa do mesmo gap.

Cada novo ciclo deve ser tratado como um novo evento, com rastreabilidade completa.

### 8.8 Limite operacional

Existe um limite operacional para o número de gaps pausados simultaneamente.

Quando esse limite for atingido, novas pausas devem ser bloqueadas até que haja disponibilidade.

### 8.9 Prazo máximo de pausa

Existe um tempo máximo de pausa.

O sistema deve garantir que a pausa respeite esse limite.

### 8.10 Dependências e vínculos

As dependências, vínculos ou subtarefas do gap não devem ser perdidos.

Durante a pausa, o sistema deve manter a relação entre o gap e seus vínculos, aplicando o comportamento do fluxo existente para itens dependentes.

### 8.11 SLA

A pausa afeta o SLA.

Enquanto o gap estiver pausado, o sistema deve suspender o impacto da contagem de SLA conforme a regra vigente.

Ao reativar, a contagem deve retomar conforme o comportamento definido pelo produto.

---

## 9. Validações para permitir ou impedir a pausa

A operação de pausa só pode ser concluída quando todas as condições abaixo forem verdadeiras:

- o usuário possui permissão de ação;
- o gap está em estado elegível;
- o tipo do gap permite pausa;
- o motivo selecionado é válido;
- o limite operacional de gaps pausados simultaneamente não foi atingido;
- o prazo máximo de pausa pode ser respeitado;
- a confirmação do usuário foi recebida.

A operação deve ser impedida quando qualquer uma dessas condições falhar.

---

## 10. Cenários de exceção

O sistema deve tratar, no mínimo, os seguintes cenários:

### 10.1 Falta de permissão

Se o usuário não tiver autorização, a ação não deve ser executada.

### 10.2 Status não elegível

Se o gap estiver em um status que não permite pausa, o sistema deve bloquear a operação.

### 10.3 Tipo não compatível

Se o tipo do gap não permitir pausa, a ação não deve ser disponibilizada ou deve ser bloqueada na confirmação.

### 10.4 Motivo ausente

Se o usuário tentar confirmar sem selecionar um motivo válido, a operação deve ser impedida.

### 10.5 Motivo inválido

Se o motivo informado não estiver na lista fixa ou não for compatível com o tipo/status, a operação deve ser rejeitada.

### 10.6 Limite operacional atingido

Se o número máximo de gaps pausados simultaneamente já tiver sido atingido, a pausa deve ser bloqueada.

### 10.7 Prazo máximo excedido

Se a pausa não puder respeitar o tempo máximo permitido, a operação deve ser bloqueada ou sinalizada conforme a regra vigente do fluxo.

### 10.8 Reativação indevida

Se o usuário tentar reativar um gap que não esteja pausado, a ação deve ser bloqueada.

---

## 11. Mensagens ao usuário

O sistema deve exibir mensagens de feedback coerentes com a situação.

### 11.1 Sucesso

Mensagem de sucesso informando que o gap foi pausado com êxito.

### 11.2 Motivo obrigatório

Mensagem informando que é necessário selecionar um motivo válido.

### 11.3 Status inelegível

Mensagem informando que o gap não pode ser pausado no status atual.

### 11.4 Permissão insuficiente

Mensagem informando que o usuário não possui permissão para executar a ação.

### 11.5 Limite operacional

Mensagem informando que não é possível pausar o gap no momento devido ao limite de pausas simultâneas.

### 11.6 Reativação

Mensagem informando que o gap foi reativado com sucesso.

As mensagens devem seguir o idioma configurado no produto.

---

## 12. Notificações

Ao concluir a pausa, o sistema deve integrar-se ao mecanismo de notificações existente.

A integração deve ocorrer também na reativação, se esse comportamento estiver previsto no fluxo existente.

A notificação deve respeitar as regras do tipo e do status do gap.

---

## 13. Auditoria e histórico

O sistema deve registrar, para cada evento de pausa e reativação:

- data;
- hora;
- usuário;
- motivo da pausa;
- estado anterior;
- novo estado.

O histórico de alterações de pausa deve permanecer disponível para consulta conforme as permissões do produto.

O registro de auditoria deve ser preservado para fins de rastreabilidade e compliance.

---

## 14. Relatórios e indicadores

O sistema deve permitir relatórios sobre gaps pausados e seu histórico.

Os relatórios devem suportar consulta por período e pelo menos pelos atributos já usados pelo produto para classificação dos gaps, como tipo e status, respeitando as permissões de visualização.

---

## 15. Restrições de segurança e compliance

- A ação deve ser executada apenas por usuário autenticado e autorizado.
- A validação não pode depender apenas da interface.
- O registro de auditoria não deve ser editável pelo usuário final pela interface.
- O histórico deve preservar rastreabilidade completa dos eventos.

---

## 16. Critérios de aceite

O fluxo será considerado atendido quando:

1. o usuário autorizado conseguir pausar um gap elegível;
2. o sistema obrigar a seleção de um motivo válido;
3. o sistema bloquear pausas em status/tipos não elegíveis;
4. o sistema respeitar o limite operacional de gaps pausados simultaneamente;
5. o sistema respeitar o tempo máximo de pausa;
6. o sistema registrar auditoria com data, hora, usuário e motivo;
7. o sistema manter histórico das mudanças de estado;
8. o sistema integrar notificações após a pausa;
9. o SLA sofrer o efeito esperado durante a pausa;
10. o fluxo de reativação funcionar de forma reversível;
11. a interface web apresentar opções coerentes, fixas e consistentes com o estado do gap;
12. o comportamento respeitar idioma, segurança e permissões.

---

## 17. Referência de implementação

A implementação deve seguir a documentação existente do fluxo atual de gaps, preservando o que já existe e acrescentando apenas o comportamento de pausa temporária e sua reversão.