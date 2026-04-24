## Matriz de autorização

Legenda: **C** = criar, **R** = ler/listar, **U** = editar, **D** = excluir

| Recurso | Acesso público | Visitante | Editor | Administrador |
|---|---:|---:|---:|---:|
| **Raças de gatos** | R | R | C, R, U | C, R, U, D |
| **Tags** | R | R | C, R, U | C, R, U, D |

### Observações
- **R** cobre listagem e consulta dos dados cadastrados.
- O recurso **Raças de gatos** inclui: nome da raça, origem, porte e peso, expectativa de vida, temperamento, pelagem e cor, descrição, imagem e tags.
- As operações fora de CRUD — como **login**, **busca**, **filtros**, **ordenação**, **paginação**, **importação/exportação CSV**, **upload de imagem** e **troca de idioma** — não entram nesta matriz.
- Para **exclusão**, a permissão fica restrita ao **Administrador**.