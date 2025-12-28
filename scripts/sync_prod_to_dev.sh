#!/bin/bash
#
# Sincroniza dados de producao (Supabase) para desenvolvimento (Podman)
# Uso: ./sync_prod_to_dev.sh
#

set -e

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Configuracoes
BACKUP_FILE="fcontrol_backup.sql"
CONTAINER_NAME="fcontrol_db"
DEV_USER="username"
DEV_DB="app_db"

echo -e "${YELLOW}=== Sync Producao -> Desenvolvimento ===${NC}"
echo ""

# Verificar se o container esta rodando
if ! podman ps | grep -q "$CONTAINER_NAME"; then
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

# Extrair URL de producao (linha comentada)
PROD_URL=$(grep -E "^#.*DATABASE_URL.*supabase" "$ENV_FILE" | sed 's/^#\s*//' | cut -d'"' -f2)

if [ -z "$PROD_URL" ]; then
    echo -e "${RED}Erro: URL de producao nao encontrada no .env${NC}"
    echo "Certifique-se de que existe uma linha comentada com a URL do Supabase"
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

echo -e "${GREEN}1. Limpando banco de desenvolvimento...${NC}"

# Dropar e recriar o banco para evitar conflitos
podman exec "$CONTAINER_NAME" psql -U "$DEV_USER" -d postgres -c "
    SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DEV_DB' AND pid <> pg_backend_pid();
" 2>/dev/null || true

podman exec "$CONTAINER_NAME" psql -U "$DEV_USER" -d postgres -c "DROP DATABASE IF EXISTS $DEV_DB;"
podman exec "$CONTAINER_NAME" psql -U "$DEV_USER" -d postgres -c "CREATE DATABASE $DEV_DB;"

echo -e "${GREEN}2. Exportando dados de producao...${NC}"
echo "   Host: $PROD_HOST"
echo "   Database: $PROD_DB"

# Usar pg_dump excluindo schemas especificos do Supabase
podman exec "$CONTAINER_NAME" sh -c "PGPASSWORD='$PROD_PASS' pg_dump \
    -h '$PROD_HOST' \
    -p '$PROD_PORT' \
    -U '$PROD_USER' \
    -d '$PROD_DB' \
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
    --exclude-table='auth.*'" > "/tmp/$BACKUP_FILE"

echo -e "${GREEN}3. Importando no ambiente de desenvolvimento...${NC}"

podman exec -i "$CONTAINER_NAME" psql -U "$DEV_USER" -d "$DEV_DB" < "/tmp/$BACKUP_FILE" 2>&1 | grep -v "^ERROR:" | grep -v "^DETAIL:" | grep -v "^HINT:" | head -20 || true

echo -e "${GREEN}4. Limpando arquivo temporario...${NC}"
rm -f "/tmp/$BACKUP_FILE"

echo ""
echo -e "${GREEN}=== Sincronizacao concluida! ===${NC}"
echo -e "Banco de dev atualizado com dados de producao."
echo ""
echo -e "${YELLOW}Nota: Alguns erros de extensoes Supabase sao esperados e podem ser ignorados.${NC}"
