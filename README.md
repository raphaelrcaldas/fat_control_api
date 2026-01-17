# FATCONTROL API

## Sistema de Gestao Operacional - 1o/1o GT

### Descricao

Backend do sistema de gestao operacional desenvolvido para o **1o/1o GT**. Oferece uma API RESTful para controle de usuarios, gestao de informacoes operacionais e sistema de pagamentos.

---

## Stack Tecnologica

| Tecnologia       | Versao    | Descricao                           |
| ---------------- | --------- | ----------------------------------- |
| Python           | >= 3.13   | Linguagem principal                 |
| FastAPI          | 0.x       | Framework web assincrono            |
| SQLAlchemy       | 2.x       | ORM com suporte a async             |
| Pydantic         | 2.x       | Validacao e schemas                 |
| Alembic          | 1.13+     | Migracao de banco de dados          |
| PostgreSQL       | -         | Banco de dados (Supabase/Podman)    |
| PyJWT            | 2.9+      | Autenticacao JWT                    |
| pwdlib (Argon2)  | 0.x       | Hash seguro de senhas               |
| asyncpg          | 0.30+     | Driver assincrono PostgreSQL        |
| Ruff             | 0.x       | Linting e formatacao                |
| Pytest           | 8.x       | Framework de testes                 |
| Testcontainers   | 4.x       | Containers para testes              |

---

## Estrutura do Projeto

```
api/
├── fcontrol_api/
│   ├── app.py              # Ponto de entrada FastAPI
│   ├── database.py         # Configuracao do banco de dados
│   ├── middlewares.py      # Middlewares customizados
│   ├── security.py         # Autenticacao e autorizacao
│   ├── settings.py         # Configuracoes da aplicacao
│   ├── models/             # Modelos SQLAlchemy
│   ├── schemas/            # Schemas Pydantic
│   ├── routers/            # Endpoints da API
│   │   ├── auth.py         # Autenticacao (login, refresh)
│   │   ├── users.py        # Gerenciamento de usuarios
│   │   ├── indisp.py       # Indisponibilidades
│   │   ├── logs.py         # Logs de auditoria
│   │   ├── postos.py       # Postos/Graduacoes
│   │   ├── cities.py       # Cidades
│   │   ├── cegep/          # Modulo financeiro
│   │   │   ├── comiss.py       # Comissionamento
│   │   │   ├── diarias.py      # Controle de diarias
│   │   │   ├── financeiro.py   # Dados financeiros
│   │   │   ├── missao.py       # Missoes
│   │   │   ├── soldos.py       # Soldos
│   │   │   └── dados_bancarios.py
│   │   ├── ops/            # Modulo operacional
│   │   │   ├── funcoes.py      # Funcoes a bordo
│   │   │   ├── quads.py        # Quadrinhos de missao
│   │   │   ├── tripulantes.py  # Tripulantes
│   │   │   └── om.py           # Ordens de missao
│   │   ├── nav/            # Modulo navegacao
│   │   │   └── aerodromos.py   # Aerodromos
│   │   └── security/       # Modulo seguranca
│   │       ├── roles.py        # Roles de acesso
│   │       ├── resources.py    # Recursos protegidos
│   │       └── permissions.py  # Permissoes
│   ├── services/           # Logica de negocio
│   └── utils/              # Utilitarios
├── migrations/             # Migrações Alembic
├── tests/                  # Testes automatizados
├── scripts/                # Scripts auxiliares
├── assets/                 # Arquivos estaticos
├── alembic.ini             # Configuracao Alembic
├── pyproject.toml          # Dependencias e configuracao
└── Dockerfile              # Build da imagem
```

---

## Configuracao do Ambiente

### Variaveis de Ambiente

Crie um arquivo `.env` na raiz do projeto:

```env
DATABASE_URL="postgresql+asyncpg://username:password@127.0.0.1:5432/app_db"
SECRET_KEY="sua-chave-secreta"
ALGORITHM="HS256"
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

## Funcionalidades

### Autenticacao e Seguranca
- Autenticacao via JWT com refresh tokens
- Hash de senhas com Argon2 (pwdlib)
- Sistema de roles e permissoes granulares
- Logs de auditoria de acoes

### Gerenciamento de Usuarios
- CRUD completo de usuarios
- Controle de indisponibilidades pessoais
- Vinculacao a esquadroes

### Modulo Operacional (ops/)
- Funcoes a bordo
- Quadrinhos de missao
- Gestao de tripulantes
- Ordens de missao

### Modulo Financeiro (cegep/)
- Controle de comissionamento
- Gestao de diarias
- Dados bancarios
- Controle de soldos

### Modulo Navegacao (nav/)
- Cadastro de aerodromos

## Deploy

O projeto inclui configuracao para deploy no Fly.io:

- `Dockerfile` - Build da imagem
- `fly.toml` - Configuracao do Fly.io

---

## Licenca

Este projeto e licenciado sob a MIT.
