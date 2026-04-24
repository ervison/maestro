# Contrato da API — Cadastro de Raças de Gatos

## Padrões gerais

- **Base da API:** `/api/v1`
- **Formato padrão:** `application/json`
- **Upload de imagem e importação CSV:** `multipart/form-data`
- **Autenticação:** `Authorization: Bearer <token>` nos endpoints protegidos
- **Idioma das mensagens:** configurável; recomenda-se respeitar `Accept-Language`
- **Paginação:** via query params `page` e `limit`
- **Ordenação padrão:** alfabética por nome da raça

---

## Modelo de dados

### `RacaGato`

| Campo | Tipo | Obrigatório | Observações |
|---|---:|---:|---|
| `id` | string | sim | Identificador gerado pelo backend |
| `nome` | string | sim | Nome da raça |
| `origem` | string | sim | Origem da raça |
| `porte` | string | não | Porte |
| `peso` | string | não | Peso |
| `expectativaDeVida` | string | não | Expectativa de vida |
| `temperamento` | string | não | Temperamento |
| `pelagem` | string | não | Pelagem |
| `cor` | string | não | Cor |
| `descricao` | string | não | Descrição |
| `tags` | array de string | não | Tags da raça |
| `imagemUrl` | string \| null | não | URL da imagem salva pelo backend |

> Em criação e edição, a imagem é enviada como arquivo no campo `imagem`.

---

## Autenticação

### `POST /auth/login`

**Objetivo:** autenticar usuário com e-mail e senha.

**Request**
```json
{
  "email": "usuario@exemplo.com",
  "senha": "senha-segura"
}
```

**Response 200**
```json
{
  "data": {
    "accessToken": "string",
    "user": {
      "id": "string",
      "email": "usuario@exemplo.com",
      "role": "administrador"
    }
  }
}
```

**Perfis suportados**
- `administrador`
- `editor`
- `visitante`

---

## Raças de gatos

### `GET /racas`

**Objetivo:** listar raças cadastradas com busca, filtros, ordenação e paginação.

**Query params**
- `search` — busca por nome da raça
- `origem` — filtro por origem
- `porte` — filtro por porte
- `sort` — ordenação; valor esperado: `nome`
- `order` — `asc` ou `desc`
- `page` — número da página
- `limit` — itens por página

**Response 200**
```json
{
  "data": {
    "items": [
      {
        "id": "string",
        "nome": "string",
        "origem": "string",
        "porte": "string",
        "peso": "string",
        "expectativaDeVida": "string",
        "temperamento": "string",
        "pelagem": "string",
        "cor": "string",
        "descricao": "string",
        "tags": ["string"],
        "imagemUrl": "string"
      }
    ],
    "meta": {
      "page": 1,
      "limit": 10,
      "totalItems": 0,
      "totalPages": 0
    }
  }
}
```

---

### `GET /racas/{id}`

**Objetivo:** obter os dados de uma raça específica.

**Response 200**
```json
{
  "data": {
    "id": "string",
    "nome": "string",
    "origem": "string",
    "porte": "string",
    "peso": "string",
    "expectativaDeVida": "string",
    "temperamento": "string",
    "pelagem": "string",
    "cor": "string",
    "descricao": "string",
    "tags": ["string"],
    "imagemUrl": "string"
  }
}
```

---

### `POST /racas`

**Objetivo:** cadastrar nova raça.

**Content-Type:** `multipart/form-data`

**Campos do formulário**
- `nome` — obrigatório
- `origem` — obrigatório
- `porte` — opcional
- `peso` — opcional
- `expectativaDeVida` — opcional
- `temperamento` — opcional
- `pelagem` — opcional
- `cor` — opcional
- `descricao` — opcional
- `tags` — opcional
- `imagem` — opcional, arquivo JPEG ou PNG, até 2 MB

**Response 201**
```json
{
  "data": {
    "id": "string",
    "nome": "string",
    "origem": "string",
    "porte": "string",
    "peso": "string",
    "expectativaDeVida": "string",
    "temperamento": "string",
    "pelagem": "string",
    "cor": "string",
    "descricao": "string",
    "tags": ["string"],
    "imagemUrl": "string"
  }
}
```

---

### `PATCH /racas/{id}`

**Objetivo:** editar raça existente.

**Content-Type:** `multipart/form-data`

**Campos do formulário**
- mesmos campos de `POST /racas`
- todos opcionais
- se `imagem` for enviado, substitui a imagem atual

**Response 200**
```json
{
  "data": {
    "id": "string",
    "nome": "string",
    "origem": "string",
    "porte": "string",
    "peso": "string",
    "expectativaDeVida": "string",
    "temperamento": "string",
    "pelagem": "string",
    "cor": "string",
    "descricao": "string",
    "tags": ["string"],
    "imagemUrl": "string"
  }
}
```

---

### `DELETE /racas/{id}`

**Objetivo:** excluir raça.

**Response 204**
- Sem corpo

---

## Importação e exportação CSV

### `POST /racas/import/csv`

**Objetivo:** importar raças via arquivo CSV.

**Content-Type:** `multipart/form-data`

**Campos**
- `arquivo` — arquivo CSV

**Response 200**
```json
{
  "data": {
    "importedCount": 0,
    "rejectedCount": 0,
    "errors": [
      {
        "line": 1,
        "field": "nome",
        "code": "VALIDATION_ERROR",
        "message": "Mensagem amigável"
      }
    ]
  }
}
```

---

### `GET /racas/export/csv`

**Objetivo:** exportar a listagem em CSV.

**Query params**
- mesmos parâmetros de `GET /racas`

**Response 200**
- `Content-Type: text/csv`
- `Content-Disposition: attachment; filename="racas.csv"`

---

## Validações

- `nome` e `origem` são obrigatórios no cadastro
- campos textuais devem respeitar limite de caracteres definido pelo backend
- números de paginação devem ser inteiros positivos
- imagem:
  - somente `image/jpeg` ou `image/png`
  - tamanho máximo: `2 MB`
- `tags` deve ser uma lista válida de strings
- conteúdo ofensivo deve ser bloqueado em textos, tags e descrição

---

## Resposta de erro

### Formato padrão
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Mensagem amigável",
    "details": [
      {
        "field": "nome",
        "message": "Campo obrigatório"
      }
    ]
  }
}
```

---

## Códigos de erro HTTP

| HTTP | Code | Quando usar |
|---|---|---|
| 400 | `INVALID_REQUEST` | Requisição malformada |
| 401 | `UNAUTHORIZED` / `INVALID_CREDENTIALS` | Falha de autenticação |
| 403 | `FORBIDDEN` | Usuário autenticado sem permissão |
| 404 | `NOT_FOUND` | Raça ou recurso não encontrado |
| 409 | `CONFLICT` | Conflito de dados |
| 413 | `PAYLOAD_TOO_LARGE` | Imagem ou upload acima do limite |
| 415 | `UNSUPPORTED_MEDIA_TYPE` | Formato de arquivo não permitido |
| 422 | `VALIDATION_ERROR` / `CONTEUDO_PROIBIDO` | Regras de negócio, campos inválidos ou conteúdo ofensivo |
| 500 | `INTERNAL_ERROR` | Erro inesperado no servidor |

---

## Regras de autenticação e acesso

- **Leitura** (`GET /racas`, `GET /racas/{id}`, `GET /racas/export/csv`) pode ser pública
- **Escrita** (`POST /racas`, `PATCH /racas/{id}`, `DELETE /racas/{id}`, `POST /racas/import/csv`) deve exigir autenticação
- O backend deve suportar os perfis:
  - `administrador`
  - `editor`
  - `visitante`

Se quiser, eu também posso transformar isso em um **OpenAPI 3.0 completo** pronto para implementar.