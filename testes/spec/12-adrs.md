# ADRs — Aplicação web de cadastro de raças de gatos

A seguir estão as principais decisões arquiteturais para a solução completa, com frontend bonito, backend próprio e banco de dados.

---

## ADR 001 — Adotar Next.js para o frontend

**Status:** Aceito

**Contexto:**  
A interface precisa ser moderna, responsiva e fácil de evoluir, com suporte a uma experiência visual bem cuidada.

**Decisão:**  
Usar **Next.js** como base do frontend da aplicação.

**Consequências:**  
- Organização clara das telas e rotas.
- Boa base para evoluir a interface sem perder manutenção.
- Facilita a construção de uma aplicação web completa integrada ao restante do sistema.

---

## ADR 002 — Usar Tailwind CSS para estilização

**Status:** Aceito

**Contexto:**  
O projeto pede um visual limpo, moderno, lúdico e pet-friendly.

**Decisão:**  
Adotar **Tailwind CSS** como framework de estilização.

**Consequências:**  
- Permite criar uma interface consistente e responsiva com rapidez.
- Facilita a padronização visual.
- Ajuda a compor uma experiência bonita sem depender de excesso de CSS manual.

---

## ADR 003 — Construir uma solução full-stack com API própria e banco de dados

**Status:** Aceito

**Contexto:**  
A aplicação não será apenas demonstrativa: precisa persistir dados, autenticar usuários e oferecer operações de cadastro de raças.

**Decisão:**  
Desenvolver a **API própria** do sistema e persistir os dados em **banco de dados**.

**Consequências:**  
- As raças cadastradas não ficam apenas em memória.
- O frontend passa a consumir uma API dedicada.
- A solução suporta cadastro, listagem, edição, exclusão, filtros, autenticação e importação/exportação.

---

## ADR 004 — Padronizar o modelo de dados da raça de gato

**Status:** Aceito

**Contexto:**  
Não havia um modelo definido, mas o cadastro precisa ser consistente desde o início.

**Decisão:**  
A entidade de raça deve contemplar os seguintes dados:

- Nome da raça
- Origem
- Porte e peso
- Expectativa de vida
- Temperamento
- Pelagem e cor
- Descrição
- Imagem
- Tags

Além disso:
- **Nome** e **origem** são obrigatórios.
- Os demais campos seguem a estrutura de cadastro definida no produto.

**Consequências:**  
- Forms e API ficam alinhados.
- Validações ficam previsíveis.
- O modelo pode ser usado de forma consistente em listagem, edição e importação/exportação.

---

## ADR 005 — Implementar autenticação com e-mail e senha e controle de acesso por perfis

**Status:** Aceito

**Contexto:**  
A aplicação exige login e diferentes perfis de uso, além de acesso público.

**Decisão:**  
Adotar **login com e-mail e senha** e **controle de acesso por papéis**, com os perfis:

- Administrador
- Editor
- Visitante
- Acesso público

**Consequências:**  
- Áreas administrativas podem ser protegidas.
- O sistema suporta diferentes níveis de uso.
- O conteúdo público pode ser acessado sem login, enquanto funcionalidades restritas ficam sob controle.

---

## ADR 006 — Preparar a interface para múltiplos idiomas

**Status:** Aceito

**Contexto:**  
A aplicação precisa ser **multilíngue configurável**.

**Decisão:**  
Estruturar a interface para suportar internacionalização desde a base.

**Consequências:**  
- Textos da interface ficam organizados para tradução.
- O sistema pode crescer para novos idiomas sem reescrever a UI.
- A experiência do usuário se torna mais flexível.

---

## ADR 007 — Suportar upload de imagem com validação de formato e tamanho

**Status:** Aceito

**Contexto:**  
O cadastro de raças deve aceitar imagem, com regra clara de formato e limite.

**Decisão:**  
Permitir upload apenas de imagens **JPEG ou PNG**, com tamanho máximo de **2 MB**.

**Consequências:**  
- Evita arquivos fora do padrão esperado.
- Reduz risco de uploads inadequados.
- Garante consistência no cadastro e no consumo das imagens.

---

## ADR 008 — Implementar listagem com busca, filtros, ordenação e paginação

**Status:** Aceito

**Contexto:**  
A listagem precisa ser útil mesmo com crescimento do número de registros.

**Decisão:**  
A listagem de raças deve oferecer:

- Busca por nome da raça
- Filtro por origem
- Filtro por porte
- Ordenação alfabética
- Paginação

**Consequências:**  
- A navegação fica mais prática.
- O usuário encontra registros com mais facilidade.
- O sistema se comporta melhor quando houver muitos cadastros.

---

## ADR 009 — Adotar importação e exportação em CSV

**Status:** Aceito

**Contexto:**  
O sistema precisa permitir troca de dados em formato simples.

**Decisão:**  
Suportar **CSV** para importação e exportação de dados.

**Consequências:**  
- Facilita carga e descarga em massa de registros.
- Simplifica integração com planilhas e ferramentas externas.
- Exige validação cuidadosa na importação para manter a qualidade dos dados.

---

## ADR 010 — Priorizar acessibilidade e experiência visual pet-friendly

**Status:** Aceito

**Contexto:**  
A aplicação precisa funcionar bem em mobile, tablet e desktop, além de ser compatível com teclado e leitor de tela.

**Decisão:**  
Construir a interface com foco em:

- Responsividade
- Navegação por teclado
- Compatibilidade com leitor de tela
- Estrutura semântica
- Feedback amigável e discreto
- Visual limpo, moderno, lúdico e pet-friendly

**Consequências:**  
- A experiência fica mais inclusiva.
- A interface atende a diferentes dispositivos e formas de uso.
- O sistema transmite uma identidade visual mais agradável e coerente com o tema.

---

## ADR 011 — Bloquear conteúdo ofensivo no cadastro

**Status:** Aceito

**Contexto:**  
Há regra explícita para proibir conteúdo ofensivo.

**Decisão:**  
Rejeitar cadastros que contenham **texto ou imagem ofensivos**.

**Consequências:**  
- O sistema ganha uma camada de moderação.
- Reduz risco de conteúdo inadequado.
- Exige validação clara na criação e edição de registros.

---

## ADR 012 — Cobrir a aplicação com testes automatizados

**Status:** Aceito

**Contexto:**  
A aplicação precisa de qualidade verificável em diferentes níveis.

**Decisão:**  
Implementar:

- Testes unitários
- Testes de integração
- Testes de componente
- Testes end-to-end

**Consequências:**  
- Aumenta a confiança nas entregas.
- Ajuda a evitar regressões.
- Dá suporte à evolução contínua do sistema.

---

## ADR 013 — Empacotar e publicar a aplicação com Docker

**Status:** Aceito

**Contexto:**  
Há requisito de deploy em Docker.

**Decisão:**  
Containerizar a aplicação para execução e deploy via **Docker**.

**Consequências:**  
- Facilita a padronização do ambiente.
- Simplifica o processo de entrega.
- Reduz diferenças entre desenvolvimento e produção.

---

Se você quiser, eu posso transformar esses ADRs em um **documento formal versionado** ou em uma **estrutura de projeto inicial** para implementar a aplicação em Next.js.