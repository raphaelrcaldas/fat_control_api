# -------- Stage 1: Build dependencies --------
FROM python:3.14-slim AS builder

WORKDIR /app

# Instala dependências de build
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gcc g++ make \
    && rm -rf /var/lib/apt/lists/*

# Instala Poetry (versão pinada para reprodutibilidade)
ENV POETRY_VERSION=2.1.3
RUN curl -sSL https://install.python-poetry.org | python3 - --version $POETRY_VERSION
ENV PATH="/root/.local/bin:$PATH"
ENV POETRY_VIRTUALENVS_CREATE=false

# Copia arquivos de dependência
COPY pyproject.toml poetry.lock ./

# Instala apenas dependências de produção direto no Python do sistema
RUN poetry install --no-root --only main \
    && rm -rf /root/.cache

# -------- Stage 2: Runtime --------
FROM python:3.14-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

# Cria usuário não-root
RUN groupadd --gid 1000 appuser \
    && useradd --uid 1000 --gid appuser --no-create-home appuser

# Copia pacotes Python instalados no builder
COPY --from=builder /usr/local /usr/local

# Copia código da aplicação já com ownership correto (evita camada extra de chown)
COPY --chown=appuser:appuser . .

# Pré-compila .pyc para todo o código + site-packages do Python do sistema.
# Economiza 100-300ms de compilação on-the-fly no 1º import em cold start
# (Fly), às custas de ~10-20s a mais no build. O caminho do site-packages é
# derivado em runtime para não travar em uma versão específica do Python.
# -q: silencia output; `|| true` absorve warnings em arquivos sem sintaxe
# válida (ex.: templates em pacotes third-party) — sem ele, um único arquivo
# problemático quebra o build inteiro.
RUN SITE_PACKAGES="$(python -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')" \
    && python -m compileall -q -j 0 /app "$SITE_PACKAGES" || true

USER appuser

EXPOSE 8000

CMD ["uvicorn", "fcontrol_api.app:app", "--host", "0.0.0.0", "--port", "8000"]
