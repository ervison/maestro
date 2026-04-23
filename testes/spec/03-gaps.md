# Lacunas de requisitos e perguntas em aberto

## Escopo do produto
- [GAP] A aplicação será apenas **frontend** (sem backend) ou deverá incluir **backend/API e banco de dados**?
- [GAP] O cadastro de raças será um **CRUD completo** (criar, listar, editar, excluir) ou apenas **cadastro e visualização**?
- [GAP] Quem vai usar a aplicação: **público geral, administradores, veterinários, criadores, pet shops** ou outro perfil?
- [GAP] A aplicação será usada para **uso pessoal**, **projeto acadêmico** ou **produto real em produção**?
- [GAP] Existe algum **fluxo principal** esperado além do cadastro, como busca, filtros, favoritos ou comparação?

## Dados da raça de gato
- [GAP] Quais campos cada raça deve ter? Ex.: nome, origem, descrição, porte, pelagem, temperamento, expectativa de vida, peso, cor, nível de energia, cuidados, imagem.
- [GAP] Quais campos são **obrigatórios** e quais são opcionais?
- [GAP] Haverá **validação específica** para cada campo?
- [GAP] As raças serão cadastradas manualmente ou virão de alguma **base pré-existente/importação**?
- [GAP] Deve existir suporte a **múltiplas imagens** por raça?
- [GAP] As imagens serão enviadas pelo usuário ou apenas via **URL**?
- [GAP] Há necessidade de cadastrar apenas raças reconhecidas oficialmente ou também **variantes/misturas**?

## Funcionalidades
- [GAP] Precisa de **busca** por nome da raça?
- [GAP] Precisa de **filtros** por características como porte, origem ou temperamento?
- [GAP] Precisa de **ordenação** da listagem?
- [GAP] Haverá **paginação** ou carregamento infinito?
- [GAP] É necessário um **detalhe da raça** em página separada ou tudo na mesma tela?
- [GAP] É preciso permitir **exclusão com confirmação**?
- [GAP] Deve haver **importação/exportação** de dados em CSV, JSON ou outro formato?
- [GAP] A aplicação precisa de **dashboard/resumo** com contagem de raças ou estatísticas?
- [GAP] Deve haver **favoritos**, **tags** ou categorização das raças?

## Autenticação e permissões
- [GAP] A aplicação terá **login/cadastro de usuários**?
- [GAP] Existem **papéis de acesso** diferentes, como administrador e usuário comum?
- [GAP] Apenas administradores podem cadastrar/editar/excluir raças?
- [GAP] Haverá recuperação de senha, sessão persistente ou logout?
- [GAP] É necessário algum nível de **proteção contra edição indevida**?

## Frontend e experiência visual
- [GAP] O que significa exatamente “**frontend bonito**” para você: estilo moderno, minimalista, colorido, corporativo, lúdico, dark mode?
- [GAP] Existe alguma **referência visual** ou site de inspiração?
- [GAP] Há **paleta de cores**, fonte ou identidade visual definida?
- [GAP] A interface deve ser **responsiva** para celular, tablet e desktop?
- [GAP] Precisa de suporte a **tema escuro/claro**?
- [GAP] Há exigência de **acessibilidade** específica, como contraste, navegação por teclado e leitores de tela?
- [GAP] O layout deve seguir algum padrão: **cards, tabela, formulário lateral, modal**?
- [GAP] Há preferência por animações, microinterações ou efeitos visuais?

## Conteúdo e idioma
- [GAP] O sistema será em **português** apenas ou deve ser **multilíngue**?
- [GAP] Quais textos padrão devem aparecer na interface?
- [GAP] O conteúdo das raças será fornecido por você ou deve ser criado?
- [GAP] Existe necessidade de textos institucionais, como sobre, ajuda ou termos de uso?

## Tecnologia
- [GAP] Há alguma tecnologia obrigatória para o frontend, como **React, Vue, Angular, Next.js** ou outra?
- [GAP] Há preferência por **CSS puro, Tailwind, Bootstrap, Material UI** ou outro framework de estilo?
- [GAP] O projeto deve usar **TypeScript** ou JavaScript?
- [GAP] Existe stack obrigatória para backend e banco, caso sejam necessários?
- [GAP] Há restrições de hospedagem, como Vercel, Netlify, Firebase, AWS ou outra?
- [GAP] Há necessidade de integração com alguma **API externa**?
- [GAP] O projeto precisa seguir algum padrão de arquitetura?

## Persistência e armazenamento
- [GAP] Onde os dados serão armazenados: memória local, **LocalStorage**, banco de dados ou API?
- [GAP] Os dados precisam persistir entre sessões e dispositivos?
- [GAP] Deve haver sincronização entre múltiplos usuários?
- [GAP] Há necessidade de backup, versionamento ou histórico de alterações?

## Regras de negócio
- [GAP] Existem regras específicas para evitar **duplicidade de raças**?
- [GAP] O nome da raça deve ser único?
- [GAP] Há limites de tamanho para textos e imagens?
- [GAP] Quais ações devem gerar mensagens de sucesso/erro?
- [GAP] Precisa de confirmação antes de apagar registros?
- [GAP] Existe aprovação manual antes de uma raça ficar visível?

## Qualidade, testes e entrega
- [GAP] Quais critérios definem que o projeto está pronto?
- [GAP] São esperados **testes automatizados**? Se sim, quais tipos?
- [GAP] Há requisitos de performance, como tempo de carregamento ou número de registros?
- [GAP] Quais navegadores devem ser suportados?
- [GAP] O projeto precisa de documentação técnica ou de uso?
- [GAP] Existe prazo de entrega ou marcos intermediários?

## Publicação e operação
- [GAP] A aplicação será publicada em algum ambiente específico?
- [GAP] Quem fará manutenção e atualização dos dados?
- [GAP] É necessário log de ações do usuário?
- [GAP] Há requisitos de privacidade ou conformidade legal?
- [GAP] As imagens e descrições terão alguma restrição de direitos autorais?

## Escopo mínimo para começar
- [GAP] Você quer que eu proponha um **MVP** com funcionalidades básicas ou um sistema mais completo?
- [GAP] Posso assumir uma solução padrão com **listagem, cadastro, edição, exclusão e busca**?
- [GAP] Posso assumir que o aplicativo deve ser **responsivo**, em **português** e com visual moderno?

Se quiser, eu posso transformar essas lacunas em um **questionário objetivo de briefing** para você responder e, depois, montar a especificação completa.