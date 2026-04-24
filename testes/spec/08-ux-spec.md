# Aplicação web de cadastro de raças de gatos — proposta de UX

A proposta é uma experiência **limpa, moderna, lúdica e pet-friendly**, alinhada à referência visual externa do projeto, com foco em **clareza de navegação, rapidez no cadastro e boa leitura em qualquer dispositivo**.

## Objetivo da aplicação

Permitir que o usuário:

- **cadastre novas raças**
- **liste as raças cadastradas**
- **edite raças existentes**
- **exclua raças**
- **busque, filtre, ordene e pagine a listagem**
- **importe/exporte dados em CSV**
- **faça login com e-mail e senha**
- use a interface em **idioma configurável**

---

## Estrutura geral da experiência

### 1. Cabeçalho fixo
Deve concentrar os elementos mais importantes:

- logo/nome da aplicação
- seletor de idioma
- acesso de login/perfil
- ação principal de criar nova raça
- busca rápida

### 2. Área principal
A tela principal deve funcionar como o centro operacional da aplicação, com:

- barra de busca por nome
- filtros por origem e porte
- ordenação alfabética
- listagem paginada
- ações de editar e excluir
- acesso a importação/exportação CSV

### 3. Layout responsivo
A interface deve se adaptar bem a:

- **mobile**: filtros e ações empilhados, listagem em cards ou tabela compacta
- **tablet**: equilíbrio entre espaço de conteúdo e controles
- **desktop**: listagem ampla, com leitura confortável e acesso rápido às ações

---

## Telas principais

### Tela de login
Tela simples e direta, com:

- campo de e-mail
- campo de senha
- botão de entrar
- mensagens de erro discretas
- estados de carregamento e validação

A experiência deve ser limpa, sem excesso de elementos, para não competir com o restante do sistema.

---

### Tela de listagem de raças
É a tela mais importante da aplicação.

#### Conteúdo da listagem
Cada item deve mostrar de forma clara:

- nome da raça
- origem
- porte
- imagem em miniatura
- tags
- ações de editar e excluir

#### Controles da listagem
A listagem deve oferecer:

- **busca por nome da raça**
- **filtro por origem**
- **filtro por porte**
- **ordenação alfabética**
- **paginação**
- **exportação CSV**
- **importação CSV**
- botão de **novo cadastro**

#### Estados da tela
A tela precisa prever:

- lista carregando
- lista vazia
- erro ao carregar dados
- resultados da busca sem correspondência
- feedback após criação, edição, exclusão, importação e exportação

---

### Tela de cadastro e edição
Pode ser a mesma estrutura, mudando apenas o modo de uso.

#### Campos do formulário
A tela deve incluir:

- **Nome da raça** — obrigatório
- **Origem** — obrigatório
- Porte e peso
- Expectativa de vida
- Temperamento
- Pelagem e cor
- Descrição
- Tags
- Imagem

#### Experiência do formulário
O formulário deve ser organizado em blocos para facilitar a leitura:

- **Informações básicas**
- **Características físicas**
- **Comportamento**
- **Conteúdo visual**
- **Tags e descrição**

#### Upload de imagem
O campo de imagem deve:

- aceitar **JPEG ou PNG**
- respeitar limite de **até 2 MB**
- mostrar **preview**
- permitir **trocar/remover a imagem**
- informar claramente erros de formato ou tamanho

#### Boas práticas de formulário
- validação inline
- indicação clara de campos obrigatórios
- prevenção de perda de dados ao sair da tela
- botão de salvar em destaque
- botão de cancelar visível, porém secundário

---

### Confirmação de exclusão
A exclusão deve sempre exigir confirmação.

A experiência ideal é um modal simples com:

- nome da raça selecionada
- aviso claro de que a ação é irreversível
- botão de cancelar
- botão de confirmar exclusão

Isso reduz erros acidentais e melhora a confiança do usuário.

---

### Importação e exportação CSV
A operação com CSV deve ser fácil de entender.

#### Importação
A tela ou modal de importação deve:

- orientar o usuário sobre o envio do arquivo
- validar o formato CSV
- apresentar o resultado da importação
- destacar registros com erro, se houver
- dar feedback amigável e discreto

#### Exportação
A exportação deve ser simples:

- ação visível na listagem
- retorno claro após a execução
- arquivo gerado sem etapas desnecessárias

---

## Fluxos principais

### Fluxo 1: consultar raças
1. O usuário acessa a listagem.
2. Visualiza os registros cadastrados.
3. Usa busca, filtros, ordenação e paginação para localizar uma raça.
4. Interage com editar ou excluir, se tiver permissão.

### Fluxo 2: cadastrar nova raça
1. Clica em “Nova raça”.
2. Preenche os campos obrigatórios e opcionais.
3. Faz upload da imagem, se desejar.
4. Adiciona tags.
5. Salva o cadastro.
6. Recebe feedback de sucesso e volta à listagem.

### Fluxo 3: editar raça
1. Seleciona “Editar” em um item da lista.
2. O formulário abre com dados preenchidos.
3. O usuário altera o necessário.
4. Salva as mudanças.
5. Recebe feedback de sucesso.

### Fluxo 4: excluir raça
1. Clica em “Excluir”.
2. Confirma a ação em um modal.
3. O item é removido.
4. A lista é atualizada com feedback discreto.

### Fluxo 5: importar/exportar CSV
1. O usuário abre a ação correspondente.
2. Escolhe o arquivo CSV ou solicita exportação.
3. O sistema processa a solicitação.
4. Exibe o resultado de forma objetiva.

---

## Requisitos de usabilidade

### Clareza
- rótulos simples e diretos
- hierarquia visual evidente
- campos agrupados por contexto

### Redução de esforço
- busca rápida
- filtros acessíveis
- ações frequentes sempre visíveis
- preenchimento facilitado ao editar

### Feedback
- mensagens amigáveis e discretas
- validação próxima ao campo
- confirmação em ações destrutivas
- estado de carregamento visível

### Prevenção de erros
- campos obrigatórios claramente marcados
- valores numéricos válidos
- limites de texto
- validação de imagem permitida
- confirmação antes de excluir

---

## Acessibilidade

A aplicação deve ser utilizável com:

- **navegação por teclado**
- **leitor de tela**

Requisitos importantes:

- foco visível em todos os elementos interativos
- ordem de navegação lógica
- labels associados aos campos
- textos alternativos para imagens relevantes
- contraste adequado entre texto e fundo
- botões e áreas clicáveis com tamanho confortável

---

## Multilinguismo configurável

A interface deve permitir troca de idioma de forma simples e consistente.

Isso significa:

- seletor de idioma no topo
- textos, botões e mensagens traduzidos
- consistência em rotulagem, validação e feedback

---

## Regras de conteúdo

A aplicação deve **bloquear conteúdo ofensivo** nos dados cadastrados, incluindo:

- nome da raça
- tags
- descrição
- demais textos livres

---

## Direção visual

O visual deve transmitir:

- limpeza
- modernidade
- leveza
- simpatia
- tema pet-friendly

Sugestões de linguagem visual:

- cards com cantos arredondados
- espaços em branco bem distribuídos
- ícones amigáveis
- tipografia legível
- composição organizada, sem poluição visual

O resultado deve parecer profissional, mas acolhedor.

---

## Resumo da experiência ideal

Uma aplicação com:

- **login por e-mail e senha**
- **listagem pública ou protegida conforme perfil**
- **cadastro completo de raças**
- **edição e exclusão com confirmação**
- **busca, filtros, ordenação e paginação**
- **upload de imagem com validação**
- **importação/exportação CSV**
- **interface responsiva, acessível e multilíngue**
- **estética bonita, limpa e pet-friendly**

Se quiser, eu também posso transformar isso em:

1. **wireframe textual tela por tela**,  
2. **fluxo de navegação completo**, ou  
3. **estrutura pronta para desenvolvimento em Next.js + Tailwind CSS**.