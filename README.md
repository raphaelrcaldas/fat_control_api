# FATCONTROL API

# 🛡️ Sistema de Gestão Operacional - 1º/1º GT

## 📌 Descrição do Projeto

Este aplicativo foi desenvolvido para apoiar o **1º/1º GT** no controle de usuários e na gestão de informações operacionais. Sua arquitetura é flexível e permite o gerenciamento de múltiplos esquadrões, oferecendo uma solução escalável e adaptável para diferentes unidades.

Entre as principais funcionalidades, destacam-se:
- Controle de **estatísticas operacionais**;
- Sistema de **perfis de acesso e roles**, com níveis de permissão locais e globais.

O sistema é ideal para unidades que buscam centralizar e padronizar seus processos administrativos e operacionais em uma plataforma segura e acessível.

## Tecnologias Utilizadas

### Bibliotecas Funcionais
Estas bibliotecas são essenciais para as funcionalidades principais do projeto:
- **FastAPI**: Framework moderno e eficiente para criação de APIs.
- **SQLAlchemy**: ORM para interação com bancos de dados.
- **Pydantic**: Validação e definição de modelos de dados.
- **Alembic**: Gerenciamento de migrações de banco de dados.
- **PyJWT**: Manipulação e geração de tokens JWT para autenticação.
- **Asyncpg**: Driver assíncrono para interação com PostgreSQL.
- **Psycopg** e **Psycopg2-binary**: Drivers para conexão com PostgreSQL.
- **Python-Multipart**: Suporte para upload de arquivos.

### Bibliotecas Não Funcionais
Estas bibliotecas auxiliam no suporte ao desenvolvimento, testes e qualidade do código:
- **Ruff**: Ferramenta rápida de linting para garantir qualidade e padronização do código.
- **Taskipy**: Gerenciador de tarefas para automação de comandos no projeto.
- **Pytest**: Framework para execução de testes.
- **Pytest-Cov**: Plugin para medir cobertura de testes.
- **HTTPX**: Cliente HTTP assíncrono para testes e requisições.
- **Factory-Boy**: Ferramenta para criação de objetos de teste (fixtures).
- **Freezegun**: Manipulação de datas em testes.
- **AioSQLite**: Driver assíncrono para SQLite.
- **Trio**: Biblioteca para programação assíncrona.
- **Pytest-Asyncio**: Plugin para testes assíncronos.

## Funcionalidades

### Gerenciamento de Usuários
- CRUD para operações básicas de manipulação de dados pessoais
- Controle de Indisponibilidade Pessoal

### Acompanhamento Operacional de Tripulantes
- Funções a bordo
- Quadrinhos de Missão
- Pau de Sebo (Ranking de mais voados por função)
- Cartões (Saúde, CVI, Simulador...)

### Controle de Acesso
- **Autenticação via JWT**: O projeto utiliza **JSON Web Tokens (JWT)** para controle de acesso seguro e eficiente.  
  - Após a autenticação, um token JWT é gerado e enviado ao cliente.
  - Esse token é utilizado para acessar endpoints protegidos.
  - O controle é implementado com validação de tokens, garantindo que apenas usuários autenticados possam acessar dados protegidos.

## 🚀 Funcionalidades Futuras
- Logs do Sistema (auditoria);
- Gestão **financeira integrada** (acompanhamento de ordens de serviço, pagamentos de diárias e comissionamentos);
- Módulo de relatórios avançados (relatórios financeiros);
- Dashboards customizáveis por perfil.
- Gerenciamento de **ordens de missão**;

## 📄 Licença
Este projeto é licenciado sob a MIT.
