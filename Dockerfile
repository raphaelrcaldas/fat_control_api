# -------- Stage 1: Build dependencies --------
FROM python:3.14-slim AS builder

WORKDIR /app

# Instala dependências de build
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gcc g++ make \
    && rm -rf /var/lib/apt/lists/*

# Instala Poetry
RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="/root/.local/bin:$PATH"
ENV POETRY_VIRTUALENVS_CREATE=false

# Copia arquivos de dependência
COPY pyproject.toml poetry.lock ./

# Instala apenas dependências de produção direto no Python do sistema
RUN poetry install --no-root --only main

# -------- Stage 2: Runtime --------
FROM python:3.14-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

# Copia pacotes Python instalados no builder
COPY --from=builder /usr/local /usr/local

# Copia código da aplicação
COPY . .

EXPOSE 8000

CMD ["uvicorn", "fcontrol_api.app:app", "--host", "0.0.0.0", "--port", "8000"]
