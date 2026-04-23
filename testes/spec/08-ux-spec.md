# Fluxo completo de pausa de gaps — validação UX e regras de negócio

## Escopo
Este fluxo cobre **apenas a ação de pausar um gap**, seguindo o fluxo já existente no produto.  
A pausa é **temporária**, **reversível** e deve respeitar:

- regras por **tipo de gap**
- regras por **status atual**
- **limite máximo de pausa**
- **motivo obrigatório**
- **ações subsequentes** após a pausa
- **auditoria**, **segurança** e **notificações**

---

## Visão geral do fluxo

```text
Tela de gaps / detalhe
→ selecionar gap elegível
→ acionar "Pausar"
→ confirmar em modal
→ escolher motivo fixo
→ validar regras
→ executar pausa
→ atualizar status, auditoria, SLA, notificações e histórico
→ exibir sucesso ou erro
```

---

## Telas e componentes

### 1) Tela de lista ou detalhe do gap
A ação de pausa deve aparecer no ponto de entrada já existente do fluxo.

**Comportamento esperado:**
- exibir a ação **Pausar**
- habilitar ou restringir a ação conforme:
  - tipo do gap
  - status atual
  - permissões aplicáveis
  - limite operacional de gaps pausados simultaneamente
  - regras de segurança

**Requisitos de interface:**
- linguagem consistente com a documentação e nomenclatura do produto
- ação clara, sem ambiguidade
- indicação visual do status atual do gap
- se a ação não puder ser executada, o motivo deve ficar claro para o usuário

---

### 2) Modal de confirmação de pausa
A pausa precisa de **confirmação antes da execução**.

**Conteúdo mínimo do modal:**
- identificação do gap
- status atual
- aviso de que a pausa é temporária
- indicação do impacto da pausa
- seleção obrigatória de **motivo**
- ação de confirmar
- ação de cancelar

**Sobre as opções:**
- as opções devem ser **fixas**
- a UI deve mostrar uma **seleção única** com rótulos claros
- as opções precisam ser coerentes com a linguagem do produto
- motivos inválidos não devem ser aceitos

**Feedback no modal:**
- avisos sobre impacto em SLA
- aviso sobre dependências vinculadas
- aviso sobre prazo máximo de pausa
- aviso de segurança, quando aplicável

---

### 3) Estado após confirmação
Após confirmar, o sistema deve:
- alterar o estado do gap para **pausado**
- registrar **data, hora, usuário e motivo**
- disparar **notificação**
- atualizar o **histórico**
- refletir o impacto no **SLA**
- aplicar o comportamento definido para dependências, vínculos ou subtarefas
- alimentar auditoria e relatórios

**UX pós-ação:**
- mostrar mensagem de sucesso
- atualizar o chip/label de status
- evitar dupla submissão
- manter o usuário no contexto atual

---

## Regras de validação

### A pausa deve ser permitida somente quando:
- o gap estiver em um **status elegível**
- o tipo de gap permitir pausa
- o usuário puder ver o gap e tiver acesso à ação segundo a política de segurança
- o número de gaps pausados simultaneamente estiver dentro do limite operacional
- houver motivo válido selecionado
- as regras de segurança e compliance forem atendidas

### A pausa deve ser bloqueada quando:
- o gap não estiver em um status permitido
- o tipo de gap não aceitar pausa
- o limite operacional de pausas simultâneas tiver sido atingido
- o motivo não for selecionado
- o motivo informado for inválido
- houver restrição de segurança
- houver inconsistência com as regras do fluxo existente

---

## Estados do gap relacionados à pausa

### Antes da pausa
- gap em estado anterior permitido
- ação disponível ou indisponível conforme regra

### Durante a pausa
- gap com estado visual de **pausado**
- prazo máximo de pausa deve ficar visível ou rastreável
- impactos em SLA e dependências precisam estar explícitos

### Depois da pausa
- a pausa deve ser **reversível**
- a reativação deve existir como caminho de retorno dentro do fluxo já existente
- o histórico deve preservar o evento de pausa

---

## Dependências, SLA e automações

### SLA
A pausa **afeta o SLA**, então a interface deve:
- avisar o usuário antes da confirmação
- deixar claro que a métrica será ajustada conforme a regra do sistema

### Dependências
Se houver vínculos, dependências ou subtarefas:
- o usuário deve ser informado do impacto
- o sistema deve aplicar o comportamento definido pela regra vigente
- não pode haver ambiguidade sobre o que foi afetado

### Ações subsequentes
A pausa deve acionar:
- notificação
- auditoria
- histórico de alteração
- atualização de indicadores/relatórios

---

## Mensagens de feedback

O sistema deve exibir:
- **mensagem de sucesso** após pausa concluída
- **mensagens de erro** quando a pausa não puder ser executada
- validação inline ou imediata quando o motivo for inválido ou ausente

As mensagens precisam ser:
- objetivas
- consistentes com o idioma do produto
- compatíveis com a nomenclatura aprovada

---

## Requisitos de usabilidade

- fluxo simples, com poucos passos
- confirmação obrigatória antes de executar
- motivo fixo e fácil de selecionar
- clareza sobre impacto em SLA e dependências
- proteção contra ação acidental
- prevenção de duplo clique ou reenvio
- layout consistente com o fluxo já existente
- acessibilidade básica em web: foco claro, leitura adequada e contraste adequado

---

## Critérios de aceite

O fluxo é considerado validado quando:

- a ação de pausar aparece apenas para gaps elegíveis
- o usuário precisa confirmar antes de pausar
- o motivo obrigatório é escolhido entre opções fixas
- motivos inválidos são bloqueados
- a pausa altera o estado corretamente
- o sistema registra data, hora, usuário e motivo
- o sistema dispara notificações
- o SLA é impactado conforme a regra
- o histórico da alteração é preservado
- o limite operacional de pausas simultâneas é respeitado
- a experiência segue o fluxo já existente
- o comportamento varia conforme tipo e status do gap
- a pausa permanece reversível

---

## Cenários de exceção

- usuário sem acesso adequado
- gap em status não elegível
- tipo de gap que não permite pausa
- limite operacional excedido
- motivo ausente ou inválido
- falha na integração de notificação
- falha de gravação de auditoria
- tentativa de execução repetida

Se quiser, eu posso transformar isso em uma **matriz de validação** com colunas de **regra, tela, comportamento esperado e exceção**.