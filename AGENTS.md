# FATCONTROL API — instruções locais

Leia `../docs/ai/WORKFLOW.md` e `../docs/ai/PROJECT_CONTEXT.md`, mais as regras
aplicáveis:

- `../docs/ai/rules/backend.md` — FastAPI, schemas, política anti-`# noqa`
- `../docs/ai/rules/database-and-migrations.md` — migrations, paginação, dinheiro
- `../docs/ai/rules/rbac.md` — nomes de recurso, gates, catálogo
- `../docs/ai/rules/backend-testing.md` e `../docs/ai/playbooks/pytest.md`

Antes de mexer em data, Enum de schema, FK entre bases ou autorização, leia
`../docs/ai/notes/backend-armadilhas.md` e `../docs/ai/notes/rbac-e-isolamento.md`.

Use `uv run task run`, `test`, `lint` e `format`; não use o FastAPI CLI como
substituto. Consulte `pyproject.toml` antes de usar APIs de dependências.

**Confirme para qual ambiente o `.env` aponta antes de rodar Alembic** — ele
frequentemente aponta para produção. O deploy é por CD, disparado pelo push.
