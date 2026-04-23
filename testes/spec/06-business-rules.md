## Regras de negócio, restrições e validações identificadas

- **Pausar gap** significa **suspender temporariamente** o gap.
- O **escopo do fluxo** é **apenas pausar** gaps.
- A pausa deve ser **reversível**.
- Deve existir **reativação posterior** do gap pausado, embora o mecanismo não tenha sido detalhado.
- Deve existir **tempo máximo de pausa** e o sistema deve **validar o prazo**.
- O **motivo da pausa é obrigatório**.
- **Motivos inválidos** devem ser **bloqueados/recusados**.
- As **opções da UI** do fluxo devem ser **fixas**.
- As opções devem ser **coerentes com a interface**.
- O fluxo deve exigir **confirmação antes de executar a pausa**.
- O sistema deve apresentar **mensagens de sucesso e de erro**.
- O comportamento da pausa deve variar conforme o **tipo de gap**.
- O comportamento da pausa deve variar conforme o **status atual do gap**.
- É permitido pausar um gap mesmo quando ele já estiver em **outro estado intermediário**.
- Deve haver **validação de regras de negócio** para permitir ou impedir a pausa.
- Há **limites operacionais** para o **número de gaps pausados simultaneamente**.
- A pausa **afeta o SLA**.
- Após pausar, o sistema deve executar **ações subsequentes**.
- Entre as integrações/subsequências informadas, há **integração com notificações**.
- Deve haver **auditoria/log** com **data, hora, usuário e motivo**.
- Deve haver **histórico de alterações do estado de pausa**.
- Devem existir **relatórios** sobre gaps pausados.
- O fluxo deve ser disponibilizado em **web**.
- A interface das opções deve ter **design específico**.
- Há **restrições de idioma** para estados e botões.
- O fluxo deve **seguir um fluxo já existente** e a **documentação de referência**.
- Há **requisitos de segurança** a serem atendidos.
- Existem **permissões diferentes para visualização**.

## Itens citados sem detalhamento suficiente para fechar a regra

- Tratamento de **dependências, vínculos ou subtarefas** quando o gap é pausado.
- Tratamento de **múltiplas pausas** no mesmo gap.
- **Estados exatos** antes, durante e depois da pausa.
- **Perfis/usuários** autorizados a pausar.
- **Critérios de aceite** e **cenários de exceção**.
- **Aprovação final** da definição do fluxo.
- Definição específica das **ações subsequentes** além das já informadas.