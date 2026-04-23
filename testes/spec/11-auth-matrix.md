# Matriz de autorização — fluxo de pausa de gaps

Como os perfis formais não foram informados, a matriz abaixo usa apenas os papéis **explicitamente suportados pelo insumo**:

- **Usuário com permissão de visualização**
- **Usuário autorizado a pausar gap**
- **Integração de notificações**  

> Observação: a **pausa** foi tratada como ação de negócio mapeada em **Create/Update** no recurso `Pausa do gap`.  
> Não há base no insumo para conceder **Delete** a qualquer papel neste fluxo.

## Recursos e permissões

| Papel | Recurso | C | R | U | D | Observação |
|---|---|---:|---:|---:|---:|---|
| Usuário com permissão de visualização | Gap |  | ✅ |  |  | Pode consultar o gap; a visualização tem permissão distinta |
| Usuário com permissão de visualização | Histórico de pausa |  | ✅ |  |  | Histórico é necessário e deve ser consultável |
| Usuário com permissão de visualização | Auditoria da pausa |  | ✅ |  |  | Existe exigência de auditoria com data, hora, usuário e motivo |
| Usuário autorizado a pausar gap | Gap |  | ✅ |  |  | Necessita ler o gap antes de executar a ação |
| Usuário autorizado a pausar gap | Pausa do gap | ✅ | ✅ | ✅ |  | Cria a pausa, consulta o estado e pode reativar por ser reversível |
| Usuário autorizado a pausar gap | Histórico de pausa |  | ✅ |  |  | Precisa consultar o histórico de alterações do estado |
| Usuário autorizado a pausar gap | Auditoria da pausa |  | ✅ |  |  | Registro obrigatório de rastreabilidade |
| Integração de notificações | Notificação | ✅ | ✅ |  |  | O sistema deve integrar com notificações |

## Regras de autorização implícitas no fluxo

- A ação de **pausar** só deve ocorrer se o **status atual** e o **tipo do gap** permitirem.
- A pausa exige **confirmação** antes de executar.
- O **motivo é obrigatório** e deve ser validado contra a lista fixa de motivos.
- A ação é **reversível**, então a mesma permissão de execução pode contemplar a **reativação**.
- A pausa deve respeitar:
  - **tempo máximo de pausa**
  - **limite operacional de gaps pausados simultaneamente**
  - **impacto em SLA**
- Toda execução deve gerar **auditoria** e **histórico de alteração**.
- O fluxo deve disparar **notificações** após a pausa.

## Resumo de CRUD por papel

- **Visualização**
  - **Create:** não
  - **Read:** sim
  - **Update:** não
  - **Delete:** não

- **Pausa**
  - **Create:** sim, para iniciar a pausa
  - **Read:** sim
  - **Update:** sim, para reativar
  - **Delete:** não

- **Integração de notificações**
  - **Create:** sim
  - **Read:** sim
  - **Update/Delete:** não informado no insumo, portanto não concedido aqui

Se quiser, eu posso transformar essa matriz em um formato mais formal de **RBAC** ou em uma **matriz de autorização por endpoint/tela**.