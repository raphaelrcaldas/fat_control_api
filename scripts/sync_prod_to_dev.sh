#!/bin/bash
#
# Sincroniza dados de producao (Supabase) para desenvolvimento (Podman)
# Uso: ./sync_prod_to_dev.sh
#

set -Eeuo pipefail
umask 077

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Configuracoes
CONTAINER_NAME="fcontrol_db"
DEV_USER="username"
DEV_DB="app_db"

echo -e "${YELLOW}=== Sync Producao -> Desenvolvimento ===${NC}"
echo ""

# Verificar se o container esta rodando
if ! podman ps --format '{{.Names}}' | grep -Fx "$CONTAINER_NAME" >/dev/null; then
    echo -e "${YELLOW}Container $CONTAINER_NAME nao esta rodando. Iniciando...${NC}"
    podman start "$CONTAINER_NAME"
    sleep 2
fi

# Ler URL de producao do .env (pasta pai)
ENV_FILE="$(dirname "$0")/../.env"
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}Erro: Arquivo .env nao encontrado em $ENV_FILE${NC}"
    exit 1
fi

# Extrair URL de producao (prioriza IPv4/pooler, senao usa IPv6)
PROD_URL=$(awk -F '"' '/DATABASE_URL.*pooler\.supabase\.com/ {print $2; exit}' "$ENV_FILE")

# Se nao encontrar pooler (IPv4), tenta URL direta (IPv6)
if [ -z "$PROD_URL" ]; then
    PROD_URL=$(awk -F '"' '/^#.*DATABASE_URL.*supabase\.co/ {print $2; exit}' "$ENV_FILE")
fi

if [ -z "$PROD_URL" ]; then
    echo -e "${RED}Erro: URL de producao nao encontrada no .env${NC}"
    echo "Certifique-se de que existe uma URL do Supabase (pooler ou direta)"
    exit 1
fi

# Converter asyncpg para formato padrao (pg_dump usa libpq)
PROD_URL_SYNC=$(echo "$PROD_URL" | sed 's/postgresql+asyncpg/postgresql/')

# Extrair componentes da URL para pg_dump
PROD_HOST=$(echo "$PROD_URL_SYNC" | sed -E 's|postgresql://[^:]+:[^@]+@([^:]+):.*|\1|')
PROD_PORT=$(echo "$PROD_URL_SYNC" | sed -E 's|postgresql://[^:]+:[^@]+@[^:]+:([0-9]+)/.*|\1|')
PROD_USER=$(echo "$PROD_URL_SYNC" | sed -E 's|postgresql://([^:]+):.*|\1|')
PROD_PASS=$(echo "$PROD_URL_SYNC" | sed -E 's|postgresql://[^:]+:([^@]+)@.*|\1|')
PROD_DB=$(echo "$PROD_URL_SYNC" | sed -E 's|postgresql://[^/]+/([^?]+).*|\1|')

BACKUP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/fcontrol_sync.XXXXXX")
BACKUP_FILE="$BACKUP_DIR/backup.sql"
RESTORE_LOG="$BACKUP_DIR/restore.log"
trap 'echo "Falha no sync. Artefatos preservados em: $BACKUP_DIR" >&2' ERR

echo -e "${GREEN}1. Exportando dados de producao...${NC}"

# Usar pg_dump excluindo schemas especificos do Supabase
PGPASSWORD="$PROD_PASS" podman exec --env PGPASSWORD "$CONTAINER_NAME" pg_dump \
    -h "$PROD_HOST" \
    -p "$PROD_PORT" \
    -U "$PROD_USER" \
    -d "$PROD_DB" \
    --no-owner \
    --no-privileges \
    --no-comments \
    --exclude-schema='pgsodium*' \
    --exclude-schema='vault' \
    --exclude-schema='supabase_*' \
    --exclude-schema='graphql*' \
    --exclude-schema='realtime' \
    --exclude-schema='_realtime' \
    --exclude-schema='storage' \
    --exclude-schema='extensions' \
    --exclude-schema='pgbouncer' \
    --exclude-schema='_analytics' \
    --exclude-table='auth.*' > "$BACKUP_FILE"

test -s "$BACKUP_FILE"

echo -e "${GREEN}2. Limpando banco de desenvolvimento...${NC}"

# O DEV só é removido depois de o dump terminar com sucesso.
podman exec "$CONTAINER_NAME" psql -X -v ON_ERROR_STOP=1 -U "$DEV_USER" -d postgres -c "
    SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DEV_DB' AND pid <> pg_backend_pid();
"
podman exec "$CONTAINER_NAME" psql -X -v ON_ERROR_STOP=1 -U "$DEV_USER" -d postgres -c "DROP DATABASE IF EXISTS $DEV_DB;"
podman exec "$CONTAINER_NAME" psql -X -v ON_ERROR_STOP=1 -U "$DEV_USER" -d postgres -c "CREATE DATABASE $DEV_DB;"

echo -e "${GREEN}3. Importando no ambiente de desenvolvimento...${NC}"

if ! podman exec -i "$CONTAINER_NAME" psql -X -v ON_ERROR_STOP=1 --single-transaction \
    -U "$DEV_USER" -d "$DEV_DB" -f - < "$BACKUP_FILE" > "$RESTORE_LOG" 2>&1; then
    cat "$RESTORE_LOG" >&2
    echo "Restauracao falhou. Dump e log preservados em: $BACKUP_DIR" >&2
    exit 1
fi

echo -e "${GREEN}4. Limpando arquivo temporario...${NC}"
rm -- "$BACKUP_FILE" "$RESTORE_LOG"
rmdir -- "$BACKUP_DIR"

echo ""
echo -e "${GREEN}=== Sincronizacao concluida! ===${NC}"
echo -e "Banco de dev atualizado com dados de producao."
echo ""
