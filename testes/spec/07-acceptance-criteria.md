# Critérios de aceitação — Aplicação web de cadastro de raças de gatos

## 1. Acesso, autenticação e perfis
- **Dado** que o usuário acessa a aplicação pela área pública **quando** abre o sistema sem autenticação **então** ele consegue acessar o conteúdo público disponível.
- **Dado** que o usuário informa e-mail e senha válidos **quando** envia o formulário de login **então** o sistema autentica o acesso e aplica as permissões do perfil.
- **Dado** que o usuário informa credenciais inválidas **quando** tenta entrar **então** o sistema exibe feedback amigável e discreto, sem expor informações sensíveis.
- **Dado** que o usuário possui um perfil configurado como administrador, editor ou visitante **quando** acessa a aplicação **então** o sistema respeita as permissões definidas para esse perfil.

## 2. Cadastro e edição de raças
- **Dado** que o usuário autorizado abre o formulário de cadastro ou edição **quando** a tela é exibida **então** ele encontra os campos Nome da raça, Origem, Porte, Peso, Expectativa de vida, Temperamento, Pelagem, Cor, Descrição, Imagem e Tags.
- **Dado** que o Nome da raça ou a Origem não foram preenchidos **quando** o usuário tenta salvar **então** o sistema impede o envio e indica claramente os campos obrigatórios.
- **Dado** que os valores de Peso ou Expectativa de vida são inválidos **quando** o usuário tenta salvar **então** o sistema bloqueia a gravação e apresenta validação adequada.
- **Dado** que o usuário informa textos acima do limite configurado **quando** tenta salvar **então** o sistema não persiste os dados e informa a restrição de forma clara.
- **Dado** que o usuário preenche as informações e envia o cadastro **quando** a operação é concluída com sucesso **então** a nova raça é persistida no banco de dados e passa a aparecer na listagem.
- **Dado** que o usuário abre uma raça cadastrada para edição **quando** o formulário é carregado **então** os dados existentes aparecem preenchidos para alteração.
- **Dado** que o usuário edita uma raça e confirma a alteração **quando** o salvamento é concluído **então** os dados atualizados ficam persistidos no banco de dados.
- **Dado** que o usuário exclui uma raça cadastrada **quando** a operação é concluída **então** o registro deixa de existir na listagem e no banco de dados.

## 3. Imagens, tags e regras de conteúdo
- **Dado** que o usuário seleciona uma imagem JPEG ou PNG com até 2 MB **quando** salva a raça **então** a imagem é aceita e vinculada ao registro.
- **Dado** que a imagem enviada não está em JPEG ou PNG ou ultrapassa 2 MB **quando** o usuário tenta salvar **então** o sistema rejeita o arquivo e exibe feedback amigável.
- **Dado** que o usuário adiciona tags ao cadastro **quando** salva a raça **então** as tags informadas ficam associadas ao registro.
- **Dado** que o conteúdo informado contém material ofensivo **quando** o usuário tenta salvar **então** o sistema bloqueia o cadastro e não persiste o conteúdo.

## 4. Listagem, busca, filtros, ordenação e paginação
- **Dado** que existem raças cadastradas no banco de dados **quando** o usuário acessa a listagem **então** o sistema exibe os registros persistidos.
- **Dado** que o usuário pesquisa pelo nome da raça **quando** informa um termo de busca **então** a listagem retorna apenas os registros correspondentes.
- **Dado** que o usuário aplica filtro por origem **quando** seleciona um valor **então** a listagem exibe apenas as raças daquela origem.
- **Dado** que o usuário aplica filtro por porte **quando** seleciona um valor **então** a listagem exibe apenas as raças daquele porte.
- **Dado** que o usuário escolhe a ordenação alfabética **quando** aplica a ordenação **então** a lista é reorganizada em ordem alfabética.
- **Dado** que a quantidade de registros excede a exibição de uma tela **quando** a listagem é apresentada **então** o sistema disponibiliza paginação para navegação entre os resultados.

## 5. Importação e exportação em CSV
- **Dado** que o usuário autorizado solicita exportação **quando** executa a ação **então** o sistema gera um arquivo CSV com os dados cadastrados.
- **Dado** que o usuário envia um arquivo CSV válido **quando** inicia a importação **então** o sistema processa os dados e persiste os registros correspondentes.
- **Dado** que o arquivo CSV está inválido **quando** a importação falha **então** o sistema informa o problema com feedback claro e discreto.

## 6. Interface multilíngue configurável
- **Dado** que a aplicação possui idiomas configurados **quando** o usuário altera o idioma **então** menus, formulários, botões e mensagens passam a ser exibidos no idioma selecionado.
- **Dado** que o idioma é alterado **quando** o usuário navega entre as telas **então** a interface mantém a tradução escolhida para os elementos exibidos.

## 7. Experiência visual, responsividade e acessibilidade
- **Dado** que a aplicação é aberta em mobile, tablet ou desktop **quando** a tela é exibida **então** os componentes se adaptam ao tamanho disponível sem comprometer a usabilidade.
- **Dado** que o usuário navega por teclado **quando** percorre a interface **então** consegue alcançar campos, botões e controles principais sem depender do mouse.
- **Dado** que um leitor de tela é utilizado **quando** a aplicação é acessada **então** os elementos possuem estrutura e rótulos compatíveis com leitura assistiva.
- **Dado** que as telas principais são apresentadas **quando** o usuário visualiza a interface **então** o visual segue uma proposta limpa, moderna, lúdica e pet-friendly.

## 8. Feedback e validações
- **Dado** que uma ação é concluída com sucesso **quando** o sistema finaliza criar, editar, excluir, importar ou exportar **então** ele exibe feedback amigável e discreto.
- **Dado** que uma validação falha **quando** o usuário envia dados inválidos **então** o sistema informa o erro de forma clara, preferencialmente no campo ou na ação correspondente.
- **Dado** que o arquivo de imagem não atende às regras **quando** o usuário tenta anexá-lo **então** o sistema informa o motivo da rejeição.
- **Dado** que o conteúdo é ofensivo **quando** o usuário tenta salvar **então** o sistema impede o avanço e apresenta retorno adequado.

## 9. API, banco de dados e persistência
- **Dado** que o usuário cria, edita ou exclui uma raça **quando** a operação é concluída **então** os dados ficam persistidos no banco de dados.
- **Dado** que a aplicação é recarregada ou acessada novamente **quando** a listagem é carregada **então** os registros persistidos permanecem disponíveis.
- **Dado** que o frontend precisa consultar ou alterar dados **quando** executa uma operação **então** ele utiliza a API desenvolvida para a aplicação.

## 10. Deploy em Docker
- **Dado** que o ambiente suporta Docker **quando** a aplicação é empacotada e executada **então** frontend, API e acesso ao banco ficam disponíveis conforme a configuração do projeto.

## 11. Testes automatizados
- **Dado** que os fluxos principais da aplicação são validados **quando** as suítes de teste são executadas **então** existem testes unitários, de integração, de componente e end-to-end cobrindo as funcionalidades principais.
- **Dado** que uma alteração quebra um fluxo principal **quando** os testes são executados **então** a falha é identificada pela suíte correspondente.