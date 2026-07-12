#!/bin/bash
# api/scripts/e2e_db_setup.sh

set -e

CONTAINER_NAME="fcontrol_e2e_db"
PORT=5433
DB_USER="postgres"
DB_PASS="e2e_password"
DB_NAME="fcontrol_e2e"

echo "🚀 Iniciando container de banco de dados efêmero ($CONTAINER_NAME)..."

# Garante que não há um container antigo com o mesmo nome
podman rm -f $CONTAINER_NAME 2>/dev/null || true

# Inicia o container efêmero
podman run --name $CONTAINER_NAME \
  -e POSTGRES_PASSWORD=$DB_PASS \
  -e POSTGRES_USER=$DB_USER \
  -e POSTGRES_DB=$DB_NAME \
  -p $PORT:5432 \
  -d postgres:16-alpine

echo "⏳ Aguardando banco de dados ficar pronto..."
until podman exec $CONTAINER_NAME pg_isready -U $DB_USER > /dev/null 2>&1; do
  sleep 1
done

echo "✅ Banco de dados pronto!"

# Executa as migrations do Alembic
echo "📖 Executando migrations do Alembic..."
export DATABASE_URL="postgresql+asyncpg://$DB_USER:$DB_PASS@localhost:$PORT/$DB_NAME"
uv run alembic upgrade head

echo "🌱 Populando dados de seed..."
uv run python scripts/seed_e2e_db.py

echo "✨ Ambiente de teste preparado com sucesso!"
