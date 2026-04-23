## Critérios de aceite — fluxo completo de pausa de gaps

Abaixo estão critérios de aceite em **Dado / Quando / Então**, cobrindo o fluxo web de pausa temporária, sua reversão e os efeitos associados.

### 1) Acesso ao fluxo no web
- **Dado** um usuário com acesso ao gap na interface web  
  **Quando** ele abre os detalhes do gap  
  **Então** o fluxo de pausa é exibido somente para gaps e estados permitidos pela regra vigente, respeitando as permissões de visualização.

### 2) Escopo limitado à pausa
- **Dado** que o escopo da funcionalidade é apenas pausar  
  **Quando** o usuário acessa o fluxo  
  **Então** a interface não exibe ações de editar, comentar, reabrir ou finalizar dentro desse mesmo fluxo.

### 3) Opções de UI fixas e coerentes
- **Dado** que o usuário abriu o fluxo de pausa  
  **Quando** a tela é carregada  
  **Então** o sistema apresenta apenas as opções fixas definidas para a pausa, com nomenclatura coerente com o fluxo existente e no idioma configurado.

### 4) Motivo obrigatório e validação de motivo
- **Dado** que o fluxo exige seleção de motivo  
  **Quando** o usuário tenta confirmar sem selecionar uma opção válida  
  **Então** o sistema bloqueia a confirmação e exibe mensagem de erro.
- **Dado** que o usuário selecionou um motivo válido  
  **Quando** ele confirma a operação  
  **Então** o sistema permite a continuidade do fluxo.

### 5) Confirmação obrigatória antes da pausa
- **Dado** que o usuário iniciou a ação de pausa  
  **Quando** ele cancela a confirmação  
  **Então** nenhuma alteração é aplicada ao gap.
- **Dado** que o usuário confirmou a operação  
  **Quando** a solicitação é processada  
  **Então** o gap é suspenso temporariamente.

### 6) Reativação reversível
- **Dado** um gap em pausa  
  **Quando** a reativação for executada dentro das condições definidas  
  **Então** o gap deixa o estado de pausa e o evento fica registrado no histórico.

### 7) Regras por tipo e status do gap
- **Dado** um gap de tipo ou status com tratamento específico  
  **Quando** a pausa for solicitada  
  **Então** o sistema aplica a regra correspondente e permite ou impede a ação conforme definido para aquele tipo/status.
- **Dado** um gap em estado intermediário permitido  
  **Quando** a pausa for solicitada  
  **Então** o sistema aceita a operação somente se a regra do estado atual permitir.

### 8) Múltiplas pausas e histórico
- **Dado** que o gap já possui eventos anteriores de pausa  
  **Quando** uma nova pausa for solicitada  
  **Então** o sistema aplica a regra definida para múltiplas pausas e mantém o histórico completo.

### 9) Limite máximo de tempo de pausa
- **Dado** que existe um tempo máximo de pausa  
  **Quando** o limite for atingido ou excedido  
  **Então** o sistema aplica a restrição prevista para o prazo máximo.

### 10) Limite operacional de gaps pausados simultaneamente
- **Dado** que o limite operacional de gaps pausados simultaneamente foi atingido  
  **Quando** um novo gap tentar entrar em pausa  
  **Então** o sistema bloqueia a operação e informa o usuário.

### 11) Impacto em SLA
- **Dado** um gap pausado  
  **Quando** a pausa é efetivada  
  **Então** o sistema considera o impacto no SLA conforme a regra vigente.

### 12) Dependências, vínculos e subtarefas
- **Dado** um gap com dependências, vínculos ou subtarefas  
  **Quando** ele é pausado  
  **Então** o tratamento desses elementos segue a regra documentada para o fluxo.

### 13) Ações subsequentes após pausar
- **Dado** que a pausa foi concluída com sucesso  
  **Quando** o sistema processa o evento  
  **Então** ele executa as ações subsequentes previstas, incluindo integração com notificações.

### 14) Auditoria e rastreabilidade
- **Dado** que uma pausa ou reativação foi executada  
  **Quando** o evento é gravado  
  **Então** o sistema registra data, hora, usuário, motivo e a mudança de estado.

### 15) Histórico de alterações do estado de pausa
- **Dado** que houve mudança no estado de pausa  
  **Quando** o evento é concluído  
  **Então** o histórico do gap é atualizado com o registro correspondente.

### 16) Relatórios e indicadores
- **Dado** que existem relatórios ou indicadores sobre gaps pausados  
  **Quando** os eventos de pausa são registrados  
  **Então** as informações ficam disponíveis para composição dos relatórios.

### 17) Mensagens de sucesso e erro
- **Dado** uma operação concluída com sucesso ou recusada por validação  
  **Quando** o sistema responde  
  **Então** ele exibe mensagem de sucesso ou erro no idioma configurado.

### 18) Segurança
- **Dado** um usuário sem a permissão aplicável  
  **Quando** ele tenta visualizar ou acionar a pausa  
  **Então** o sistema impede o acesso conforme as regras de segurança.

### 19) Conformidade com o fluxo existente e documentação
- **Dado** o fluxo de referência já existente  
  **Quando** a funcionalidade de pausa é executada  
  **Então** o comportamento segue a documentação de referência sem incluir ações fora do escopo.

Se você quiser, eu também posso transformar isso em **cenários de teste** mais enxutos, ou em uma **checklist de homologação**.