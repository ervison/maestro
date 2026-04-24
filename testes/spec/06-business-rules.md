# Regras de negócio, restrições e validações da aplicação

## 1) Cadastro de raças de gatos
- O sistema deve permitir **cadastrar novas raças**.
- O sistema deve permitir **listar raças cadastradas**.
- O sistema deve permitir **editar raças**.
- O sistema deve permitir **excluir raças**.
- Cada raça deve ter os seguintes dados no cadastro:
  - **Nome da raça**
  - **Origem**
  - **Porte**
  - **Peso**
  - **Expectativa de vida**
  - **Temperamento**
  - **Pelagem e cor**
  - **Descrição**
  - **Imagem**
  - **Tags**

## 2) Campos obrigatórios e validações de dados
- **Nome da raça** é obrigatório.
- **Origem** é obrigatória.
- O sistema deve validar **campos obrigatórios** antes de salvar.
- O sistema deve validar **valores numéricos válidos** nos campos numéricos.
- O sistema deve validar **limite de caracteres** nos campos de texto.
- O sistema deve validar o **formato da imagem**.
- O sistema deve aceitar upload de imagem apenas nos formatos:
  - **JPEG**
  - **PNG**
- O tamanho máximo da imagem deve ser **2 MB**.

## 3) Busca, filtro, ordenação e paginação
- O sistema deve permitir **busca por nome da raça**.
- O sistema deve permitir **filtro por origem**.
- O sistema deve permitir **filtro por porte**.
- O sistema deve permitir **ordenação alfabética**.
- A listagem deve ter **paginação**.

## 4) Persistência e API
- Os dados devem ser persistidos em **banco de dados**.
- O sistema não deve depender apenas de memória ou local storage para guardar os cadastros.
- A solução deve incluir o desenvolvimento da **API**.

## 5) Autenticação e acesso
- O sistema deve ter **login com e-mail e senha**.
- O sistema deve suportar os perfis/acessos:
  - **Administrador**
  - **Editor**
  - **Visitante**
  - **Acesso público**

## 6) Regras de conteúdo
- O sistema deve **proibir conteúdo ofensivo** nos textos e imagens cadastrados.

## 7) Experiência visual e interface
- O frontend deve ser desenvolvido em **Next.js**.
- O estilo visual deve usar **Tailwind CSS**.
- A interface deve ter visual:
  - **limpo**
  - **moderno**
  - **lúdico**
  - **pet-friendly**
- A aplicação deve ser **responsiva** para:
  - **mobile**
  - **tablet**
  - **desktop**
- A interface deve ter **idioma multilíngue configurável**.
- O sistema deve fornecer **feedback amigável e discreto** para ações e validações.

## 8) Acessibilidade
- A aplicação deve permitir **navegação por teclado**.
- A aplicação deve ser **compatível com leitor de tela**.

## 9) Importação e exportação
- O sistema deve permitir **importação/exportação de dados em CSV**.

## 10) Qualidade e testes
- O sistema deve possuir:
  - **testes unitários**
  - **testes de integração**
  - **testes de componente**
  - **testes end-to-end**

## 11) Implantação e operação
- O deploy deve ser realizado em **Docker**.

## 12) Restrições adicionais informadas
- **Não há requisitos adicionais de auditoria, histórico de alterações ou logs**.
- **Não há restrições relevantes de prazo ou prioridade** informadas.
- **Não há modelo de dados previamente definido**.