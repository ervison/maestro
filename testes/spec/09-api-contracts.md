# Contrato de API — fluxo de pausa de gaps

Abaixo está um contrato de API focado no fluxo de **pausa temporária**, com **opções fixas para UI**, validação por **tipo/status do gap**, **confirmação obrigatória**, **retomada reversível**, **auditoria**, **notificações**, **SLA** e **histórico**.

> Observação de contrato: os nomes de **status**, **tipos** e **motivos** não são fixados aqui; o backend deve expor os catálogos e o frontend deve consumi-los para manter a coerência da UI e o suporte a idioma.

---

## 1) Convenções

- **Base URL:** `/v1`
- **Formato:** JSON
- **Autenticação:** `Authorization: Bearer <token>`
- **Headers recomendados:**
  - `Accept-Language: <locale>` — para mensagens e rótulos localizados
  - `X-Request-Id: <id>` — correlação/log
  - `Idempotency-Key: <id>` — obrigatório nas ações de escrita para evitar duplicidade
- **Escopo funcional:** apenas pausa/reativação do estado de pausa; leitura de contexto, histórico e relatórios de suporte

---

## 2) Fluxo recomendado

1. **Consultar contexto** do gap e opções disponíveis.
2. **Selecionar motivo fixo** da pausa.
3. **Validar** regras de negócio e obter `tokenConfirmacao`.
4. **Confirmar e executar** a pausa.
5. O backend registra:
   - **auditoria**
   - **notificação**
   - **impacto em SLA**
6. Se aplicável, executar **reativação** pelo endpoint próprio.
7. Consultar **histórico** e **indicadores/relatórios**.

---

## 3) Endpoints

### 3.1 Consultar contexto e opções da UI

**GET** `/v1/gaps/{gapId}/pause/context`

**Finalidade**
- Retornar o contexto atual do gap
- Listar as **opções fixas** de UI para a pausa
- Informar permissões e restrições por **tipo/status**

**Permissão**
- Requer permissão de **visualização**
- Se o usuário não puder visualizar, retornar `403`

**Resposta 200**
```json
{
  "gapId": "string",
  "tipoGap": "string",
  "statusAtual": "string",
  "permissoes": {
    "visualizar": true,
    "pausar": true,
    "reativar": false
  },
  "acoesDisponiveis": ["string"],
  "motivosDisponiveis": [
    {
      "id": "string",
      "rotulo": "string",
      "descricao": "string",
      "ativo": true,
      "ordem": 1
    }
  ],
  "regras": {
    "motivoObrigatorio": true,
    "maximoPausa": {
      "valor": 0,
      "unidade": "string"
    },
    "limiteSimultaneo": {
      "aplicavel": true,
      "atingido": false
    }
  },
  "sla": {
    "afeta": true
  },
  "requestId": "string"
}
```

---

### 3.2 Validar a pausa antes de confirmar

**POST** `/v1/gaps/{gapId}/pause/validate`

**Finalidade**
- Validar regras de negócio
- Verificar motivo obrigatório/inválido
- Verificar tipo/status do gap
- Verificar limite operacional e tempo máximo de pausa
- Gerar token para confirmação

**Permissão**
- Requer permissão de **visualização** e validação de acesso ao gap

**Headers**
- `Idempotency-Key` recomendado
- `Accept-Language` recomendado

**Request**
```json
{
  "motivoId": "string",
  "observacao": "string"
}
```

**Resposta 200**
```json
{
  "gapId": "string",
  "valido": true,
  "bloqueios": [
    {
      "campo": "string",
      "codigo": "string",
      "mensagem": "string"
    }
  ],
  "avisos": [
    {
      "campo": "string",
      "codigo": "string",
      "mensagem": "string"
    }
  ],
  "tokenConfirmacao": "string",
  "sla": {
    "afeta": true
  },
  "prazoMaximoRetomada": "date-time",
  "requestId": "string"
}
```

**Regras esperadas na validação**
- `motivoId` obrigatório
- `motivoId` deve existir no catálogo fixo retornado pelo contexto
- o gap deve existir e estar acessível
- o tipo do gap deve permitir pausa
- o status atual do gap deve permitir pausa
- o limite operacional de gaps pausados simultaneamente não pode estar excedido
- o tempo máximo de pausa não pode ser excedido
- a confirmação é obrigatória para execução
- dependências, vínculos ou subtarefas devem aparecer como **bloqueios** ou **avisos** conforme a regra vigente
- se o gap mudar entre validação e execução, a confirmação fica inválida

---

### 3.3 Executar a pausa

**POST** `/v1/gaps/{gapId}/pause`

**Finalidade**
- Executar a pausa confirmada

**Permissão**
- Requer permissão de ação de **pausa**

**Headers**
- `Idempotency-Key` obrigatório
- `Accept-Language` recomendado

**Request**
```json
{
  "motivoId": "string",
  "observacao": "string",
  "tokenConfirmacao": "string"
}
```

**Resposta 201**
```json
{
  "gapId": "string",
  "statusAtual": "string",
  "pausa": {
    "pauseId": "string",
    "iniciadaEm": "date-time",
    "iniciadaPor": {
      "usuarioId": "string",
      "nome": "string"
    },
    "motivo": {
      "id": "string",
      "rotulo": "string"
    },
    "prazoMaximoRetomada": "date-time"
  },
  "sla": {
    "afeta": true
  },
  "notificacoes": {
    "enfileiradas": true
  },
  "auditoria": {
    "registrada": true,
    "eventoId": "string"
  },
  "requestId": "string"
}
```

**Side effects obrigatórios**
- registrar auditoria com data/hora, usuário e motivo
- disparar/enfileirar notificação
- refletir impacto em SLA
- persistir histórico da pausa

---

### 3.4 Reativar um gap pausado

**POST** `/v1/gaps/{gapId}/pause/reactivate`

**Finalidade**
- Reverter a pausa

**Permissão**
- Requer permissão de ação de **reativação**

**Headers**
- `Idempotency-Key` obrigatório
- `Accept-Language` recomendado

**Request**
```json
{
  "tokenConfirmacao": "string",
  "observacao": "string"
}
```

**Resposta 200**
```json
{
  "gapId": "string",
  "statusAtual": "string",
  "reativacao": {
    "ocorridaEm": "date-time",
    "ocorridaPor": {
      "usuarioId": "string",
      "nome": "string"
    }
  },
  "notificacoes": {
    "enfileiradas": true
  },
  "auditoria": {
    "registrada": true,
    "eventoId": "string"
  },
  "requestId": "string"
}
```

---

### 3.5 Consultar histórico de pausas e reativações

**GET** `/v1/gaps/{gapId}/pause/history?limit=20&cursor=string`

**Finalidade**
- Exibir histórico de alterações de estado de pausa

**Permissão**
- Requer permissão de **visualização**

**Resposta 200**
```json
{
  "gapId": "string",
  "eventos": [
    {
      "eventoId": "string",
      "tipoEvento": "string",
      "ocorridoEm": "date-time",
      "usuario": {
        "usuarioId": "string",
        "nome": "string"
      },
      "motivo": {
        "id": "string",
        "rotulo": "string"
      },
      "observacao": "string"
    }
  ],
  "proximoCursor": "string",
  "requestId": "string"
}
```

---

### 3.6 Relatórios e indicadores de gaps pausados

**GET** `/v1/reports/gaps/paused/summary?from=date-time&to=date-time&tipoGap=string&statusAtual=string`

**Finalidade**
- Retornar indicadores agregados de gaps pausados

**Permissão**
- Requer permissão de **visualização**

**Resposta 200**
```json
{
  "periodo": {
    "de": "date-time",
    "ate": "date-time"
  },
  "totalPausados": 0,
  "porTipoGap": [
    {
      "tipoGap": "string",
      "total": 0
    }
  ],
  "porStatusAtual": [
    {
      "statusAtual": "string",
      "total": 0
    }
  ],
  "requestId": "string"
}
```

---

## 4) Estruturas de erro

### 4.1 Formato padrão de erro
```json
{
  "erro": {
    "codigo": "string",
    "mensagem": "string",
    "detalhes": [
      {
        "campo": "string",
        "codigo": "string",
        "mensagem": "string"
      }
    ],
    "requestId": "string"
  }
}
```

### 4.2 Códigos HTTP e códigos de negócio

| HTTP | Código de negócio | Quando ocorre |
|---|---|---|
| 400 | `INVALID_PAYLOAD` | JSON inválido, campos malformados |
| 401 | `AUTH_REQUIRED` | Token ausente, inválido ou expirado |
| 403 | `FORBIDDEN` | Sem permissão de visualização ou ação |
| 404 | `GAP_NOT_FOUND` | Gap inexistente ou não acessível |
| 409 | `STATE_CONFLICT` | Conflito com o status atual, mudança concorrente, confirmação obsoleta |
| 422 | `BUSINESS_RULE_VIOLATION` | Regra de negócio da pausa não atendida |
| 429 | `OPERATIONAL_LIMIT_REACHED` | Limite de gaps pausados simultaneamente atingido |
| 500 | `INTERNAL_ERROR` | Falha inesperada no backend |

### 4.3 Subcódigos de negócio recomendados
- `PAUSE_REASON_REQUIRED`
- `PAUSE_REASON_INVALID`
- `PAUSE_NOT_ALLOWED_FOR_TYPE`
- `PAUSE_NOT_ALLOWED_FOR_STATUS`
- `PAUSE_CONFIRMATION_REQUIRED`
- `PAUSE_CONFIRMATION_INVALID`
- `PAUSE_ALREADY_ACTIVE`
- `PAUSE_MAX_DURATION_EXCEEDED`
- `PAUSE_SIMULTANEOUS_LIMIT_EXCEEDED`
- `PAUSE_DEPENDENCY_RESTRICTION`

---

## 5) Regras de contrato importantes

- As **opções de UI** devem ser sempre carregadas do backend.
- O frontend não deve hardcodear motivos, rótulos ou regras dependentes de tipo/status.
- Mensagens de erro e sucesso devem ser **localizadas** conforme `Accept-Language`.
- A validação precisa anteceder a execução para cumprir a exigência de **confirmação obrigatória**.
- O histórico precisa registrar cada alteração de estado de pausa.
- A execução da pausa deve sempre disparar os efeitos subsequentes previstos: **auditoria**, **notificação** e **impacto em SLA**.

Se quiser, eu posso transformar isso agora em um **OpenAPI 3.0 YAML** completo.