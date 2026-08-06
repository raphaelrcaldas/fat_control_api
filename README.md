# FATCONTROL API

Backend do sistema de gestão operacional FATCONTROL. API REST assíncrona
(FastAPI + SQLAlchemy async) que serve os três frontends: `login` (hub de
autenticação), `client` (dashboard administrativo) e `fatbird` (portal do
tripulante).

A API é **multi-tenant**: os dados são escopados pela organização ativa do
token, e o usuário troca de escopo pelo endpoint `/auth/switch-org`.

- **Porta padrão:** 8000
- **Docs interativas:** `http://localhost:8000/docs`

---

## Stack

Versões exatas em [`pyproject.toml`](pyproject.toml).

| Tecnologia          | Papel                                          |
| ------------------- | ---------------------------------------------- |
| Python 3.13+        | Linguagem (imagem de produção: 3.14-slim)      |
| FastAPI             | Framework web assíncrono                       |
| SQLAlchemy 2 async  | ORM                                            |
| Pydantic 2          | Schemas e validação                            |
| Alembic             | Migrations                                     |
| PostgreSQL          | Banco (Podman local / Supabase em produção)    |
| asyncpg             | Driver assíncrono                              |
| PyJWT + pwdlib      | JWT e hash de senha (Argon2)                   |
| boto3               | Storage S3 (MinIO local / Supabase em produção)|
| openpyxl / pdfplumber / pillow | Exportações e extração de documentos |
| uv                  | Gerenciador de dependências e execução         |
| Ruff                | Lint e formatação                              |
| Pytest + Testcontainers | Testes com Postgres efêmero                |

---

## Como rodar

### 1. Dependências

```bash
uv sync
```

### 2. Serviços locais (Postgres + MinIO)

```bash
podman compose up -d      # ou docker compose up -d
```

Sobe `postgres:17` em `:5432` e MinIO em `:9000` (console em `:9001`).

### 3. Variáveis de ambiente

Crie um `.env` na raiz da `api/`:

```env
# Banco
DATABASE_URL="postgresql+asyncpg://username:password@127.0.0.1:5432/app_db"

# Autenticação
SECRET_KEY="troque-esta-chave"
ALGORITHM="HS256"
ACCESS_TOKEN_EXPIRE_MINUTES=30
FIRST_LOGIN_TOKEN_EXPIRE_MINUTES=15
DEFAULT_USER_PASSWORD="senha-padrao-do-primeiro-acesso"

# Origens permitidas no CORS (os três frontends)
FATLOGIN_URL="http://localhost:3000"
FATCONTROL_URL="http://localhost:4000"
FATBIRD_URL="http://localhost:5000"

ENV="development"

# Storage (MinIO local). O nome do bucket NÃO é config: cada domínio
# declara o seu como constante no próprio router.
STORAGE_ENDPOINT="localhost:9000"
STORAGE_ACCESS_KEY="minioadmin"
STORAGE_SECRET_KEY="minioadmin"
STORAGE_SECURE=False
STORAGE_REGION="sa-east-1"
STORAGE_QUOTA_MB=1024

# Integrações externas (opcionais)
AISWEB_API_KEY=""
AISWEB_API_PASS=""
PORTAL_API_KEY=""
```

> ⚠️ O `.env` também é lido pelo Alembic. **Confira para qual banco ele aponta
> antes de rodar qualquer migration** — o mesmo arquivo já foi usado para
> apontar para produção.

### 4. Migrations e servidor

```bash
uv run alembic upgrade head
uv run task run            # http://localhost:8000
```

---

## Comandos

```bash
uv run task run       # sobe a API com reload na porta 8000
uv run task test      # lint + pytest com cobertura (gera htmlcov/)
uv run task lint      # ruff check + ruff format --check
uv run task format    # ruff check --fix + ruff format
uv run task cleanup   # rotinas de limpeza de dados órfãos

uv run alembic revision --autogenerate -m "descricao"
uv run alembic upgrade head
uv run alembic check   # detecta drift entre models e banco
```

O gate de lint **reprova formatação**, não só regra: `ruff format --check` faz
parte do `task lint`, e o `task test` roda o lint antes (`pre_test`).

Os testes sobem um PostgreSQL efêmero via **Testcontainers**, então o Podman
(ou Docker) precisa estar rodando.

---

## Estrutura

```
api/
├── fcontrol_api/
│   ├── app.py            # Instância FastAPI, CORS, middlewares, exception handlers
│   ├── database.py       # Engine e sessão async
│   ├── security.py       # JWT, hash de senha, dependências de RBAC
│   ├── middlewares.py    # Auditoria, gate de troca de senha, escopo de org
│   ├── settings.py       # Configuração (pydantic-settings)
│   ├── exceptions.py     # Handlers padronizados de erro
│   ├── models/           # Modelos SQLAlchemy, por domínio
│   ├── schemas/          # Schemas Pydantic, por domínio
│   ├── enums/            # Enums de domínio (posto/graduação, quadro, tema, ...)
│   ├── routers/          # Endpoints (ver tabela abaixo)
│   ├── services/         # Regra de negócio (OM, comissionamento, etapas, storage, ...)
│   ├── cleanup/          # Tarefas de limpeza de registros órfãos
│   └── utils/            # Datas, validadores, paginação, sanitização
├── migrations/           # Revisões Alembic
├── tests/                # api/ · integration/ · services/ · schemas/ · seed/
├── scripts/              # Seeds, sincronização dev↔prod, PKCE, manutenção
├── assets/               # Tabelas estáticas (diárias, cidades) e queries
├── docker-compose.yml    # Postgres + MinIO locais
├── Dockerfile            # Imagem de produção (multi-stage)
└── fly.toml              # Deploy no Fly.io
```

### Módulos de rota

| Módulo          | Conteúdo                                                             |
| --------------- | -------------------------------------------------------------------- |
| `auth`          | OAuth PKCE (`/authorize`, `/token`), refresh, `switch-org`, dev login |
| `users`         | Cadastro de usuários, completude, promoções                          |
| `security/`     | Roles, resources e permissions (RBAC)                                |
| `organizacoes` · `tenants` · `projetos` · `postos` · `cities` | Cadastros base e multi-tenancy |
| `ops/`          | Tripulantes, escala, quadrinhos, aeronaves, operações, ordens de missão |
| `cegep/`        | Missões, comissionamento, orçamento, dados bancários, financeiro      |
| `admin/`        | Soldos e diárias (escopo de administração de sistema)                 |
| `admin_cleanup` | Disparo das rotinas de limpeza                                       |
| `estatistica/`  | Horas de aeronave, etapas, esforço aéreo, indicadores, SEBO           |
| `aeromedica/`   | Cartões de saúde e atas                                              |
| `instrucao/`    | Cartões de instrução                                                 |
| `inteligencia/` | Passaportes                                                          |
| `seg_voo/`      | CRM                                                                  |
| `nav/`          | Aeródromos                                                           |
| `aisweb/`       | Proxy do AISWEB/DECEA (METAR, ROTAER, nascer/pôr do sol)              |
| `indisp`        | Indisponibilidades                                                   |
| `storage`       | Upload/download de arquivos (S3)                                     |
| `logs`          | Auditoria                                                            |
| `config`        | Configurações expostas ao frontend                                   |

---

## Autenticação

Fluxo **OAuth 2.0 com PKCE**, orquestrado pelo `login`:

1. O frontend sem sessão gera `code_verifier`/`code_challenge` e redireciona
   para o `login` com `client_id` (`fatcontrol` ou `fatbird`).
2. O usuário autentica; a API retorna um `code` em `POST /auth/authorize`.
3. O frontend troca o `code` pelo JWT em `POST /auth/token`, enviando o
   `code_verifier`.
4. O token carrega a **organização ativa**; `POST /auth/switch-org` reemite o
   token para outro escopo.

Primeiro acesso emite um token de curta duração com `first_login: true`, que só
libera a troca de senha. Autorização por endpoint usa RBAC granular
(role → resource → permission).

---

## Deploy

- **Fly.io** — `Dockerfile` (multi-stage) + `fly.toml` (região `gru`,
  `auto_stop_machines`). Deploy com `fly deploy`.
- **Vercel** — `vercel.json` mantém a alternativa serverless via
  `@vercel/python`.

As variáveis de ambiente de produção são configuradas na plataforma, nunca
versionadas.
