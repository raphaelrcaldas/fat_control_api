# -------- Stage 1: Build dependencies --------
FROM python:3.14-slim AS builder

WORKDIR /app

# Dependências de build para pacotes nativos (asyncpg, gevent, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ make \
    && rm -rf /var/lib/apt/lists/*

# Copia UV do layer oficial (sem curl, sem instalação extra)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copia arquivos de dependência
COPY pyproject.toml uv.lock ./

# Instala dependências de produção no .venv local (/app/.venv)
RUN uv sync --frozen --no-dev --no-install-project \
    && rm -rf /root/.cache

# -------- Stage 2: Runtime --------
FROM python:3.14-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1
# Coloca o venv no PATH para que uvicorn/python resolvam os pacotes corretamente
ENV PATH="/app/.venv/bin:$PATH"

# Ghostscript: usado por fcontrol_api/services/pdf.py para comprimir PDFs
# (fallback transparente no código se ausente, mas reduz ~30-50% o tamanho).
RUN apt-get update && apt-get install -y --no-install-recommends \
    ghostscript \
    && rm -rf /var/lib/apt/lists/*

# Cria usuário não-root
RUN groupadd --gid 1000 appuser \
    && useradd --uid 1000 --gid appuser --no-create-home appuser

# Copia apenas o venv do builder (não /usr/local inteiro)
COPY --from=builder /app/.venv /app/.venv

# Copia código da aplicação já com ownership correto (evita camada extra de chown)
COPY --chown=appuser:appuser . .

# Pré-compila .pyc para código da app + site-packages do venv.
# Economiza 100-300ms de compilação on-the-fly no 1º import em cold start.
RUN python -m compileall -q -j 0 /app /app/.venv/lib || true

USER appuser

EXPOSE 8000

CMD ["uvicorn", "fcontrol_api.app:app", "--host", "0.0.0.0", "--port", "8000"]
