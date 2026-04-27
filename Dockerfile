# -------- Stage 1: Build dependencies --------
FROM python:3.14-slim AS builder

WORKDIR /app

# Dependências de build para pacotes nativos (asyncpg, gevent, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ make \
    && rm -rf /var/lib/apt/lists/*

# Copia UV do layer oficial (sem curl, sem instalação extra)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
ENV UV_SYSTEM_PYTHON=1

# Copia arquivos de dependência
COPY pyproject.toml uv.lock ./

# Instala apenas dependências de produção direto no Python do sistema
RUN uv sync --frozen --no-dev --no-install-project \
    && rm -rf /root/.cache

# -------- Stage 2: Runtime --------
FROM python:3.14-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

# Ghostscript: usado por fcontrol_api/services/pdf.py para comprimir PDFs
# (fallback transparente no código se ausente, mas reduz ~30-50% o tamanho).
RUN apt-get update && apt-get install -y --no-install-recommends \
    ghostscript \
    && rm -rf /var/lib/apt/lists/*

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
