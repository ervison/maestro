# Modelo de dados da aplicação

Abaixo está a modelagem lógica para uma aplicação completa de cadastro de raças de gatos, com autenticação, tags e persistência em banco de dados.

## 1) Entidades

### `usuario`
Entidade responsável pelo login no sistema.

| Atributo | Tipo lógico | Obrigatório | Regras |
|---|---|---:|---|
| `id` | identificador | Sim | Chave primária |
| `email` | texto | Sim | Usado no login |
| `senha_hash` | texto | Sim | A senha deve ser armazenada de forma segura |
| `perfil` | enum | Sim | Valores: `administrador`, `editor`, `visitante` |

**Observação:**  
`acesso público` não é uma entidade persistida; é uma forma de acesso sem autenticação.

---

### `raca_gato`
Entidade principal do cadastro de raças.

| Atributo | Tipo lógico | Obrigatório | Regras |
|---|---|---:|---|
| `id` | identificador | Sim | Chave primária |
| `nome` | texto | Sim | Nome da raça |
| `origem` | texto | Sim | Origem da raça |
| `porte` | texto | Não | Usado em filtro |
| `peso` | numérico | Não | Deve ser um valor numérico válido |
| `expectativa_vida` | numérico | Não | Deve ser um valor numérico válido |
| `temperamento` | texto | Não | Campo descritivo |
| `pelagem` | texto | Não | Campo descritivo |
| `cor` | texto | Não | Campo descritivo |
| `descricao` | texto | Não | Campo descritivo |
| `imagem_referencia` | texto | Não | Referência da imagem cadastrada |

**Nota de modelagem:**  
O agrupamento “porte e peso” foi separado em dois atributos, pois o sistema precisa filtrar por porte e validar peso numericamente.

---

### `tag`
Entidade para classificar raças com rótulos adicionais.

| Atributo | Tipo lógico | Obrigatório | Regras |
|---|---|---:|---|
| `id` | identificador | Sim | Chave primária |
| `nome` | texto | Sim | Nome da tag |

---

### `raca_tag`
Tabela de associação entre raças e tags.

| Atributo | Tipo lógico | Obrigatório | Regras |
|---|---|---:|---|
| `raca_id` | FK | Sim | Referência a `raca_gato.id` |
| `tag_id` | FK | Sim | Referência a `tag.id` |

**Chave primária composta:** (`raca_id`, `tag_id`)

---

## 2) Relacionamentos

### `raca_gato` ↔ `tag`
- Relacionamento **muitos-para-muitos**
- Uma raça pode ter várias tags
- Uma tag pode estar associada a várias raças
- Implementado pela tabela `raca_tag`

### `usuario`
- Entidade de autenticação independente
- Não há, no requisito, relacionamento persistido entre `usuario` e `raca_gato`

---

## 3) Restrições e validações

### Restrições obrigatórias
- `raca_gato.nome` é obrigatório
- `raca_gato.origem` é obrigatória
- `usuario.email` é obrigatório
- `usuario.senha_hash` é obrigatória
- `usuario.perfil` é obrigatório

### Validações de conteúdo
- Campos numéricos devem aceitar apenas valores numéricos válidos
- Campos textuais devem respeitar limites de caracteres definidos na implementação
- Imagens devem aceitar apenas:
  - `JPEG`
  - `PNG`
  - tamanho máximo de `2 MB`

### Regra de conteúdo
- Conteúdo ofensivo deve ser proibido nos dados cadastrados, incluindo textos e imagens

### Regras funcionais que impactam o modelo
- Busca por nome da raça
- Filtro por origem
- Filtro por porte
- Ordenação alfabética
- Paginação na listagem
- Importação/exportação em CSV

Esses itens não exigem novas entidades, mas orientam consultas e integrações.

---

## 4) Observações de modelagem

- O modelo foi pensado para suportar **cadastro, listagem, edição e exclusão** de raças.
- A **multilíngue configurável** é tratada na camada de interface e não exige, pelos requisitos informados, uma tabela específica de tradução.
- Não há requisito de auditoria, histórico de alterações ou logs.
- Não há modelo de dados pré-definido; portanto, esta estrutura serve como base inicial para banco relacional.

Se quiser, posso transformar esse modelo em:
1. **SQL para PostgreSQL**,  
2. **schema Prisma**, ou  
3. **arquitetura completa com API em Next.js + Tailwind CSS**.