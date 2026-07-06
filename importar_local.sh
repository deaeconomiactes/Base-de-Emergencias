#!/usr/bin/env bash
# Importa un dump limpio a MySQL local.
#
# Uso:
#   ./importar_local.sh [dump_limpio.sql]
#
# Variables opcionales (.env o entorno):
#   MYSQL_HOST       (def 127.0.0.1)
#   MYSQL_PORT       (def 3306)
#   MYSQL_USER       (def root)
#   MYSQL_PASSWORD   (def vacío)
#   MYSQL_DATABASE   (def emergencias)

set -euo pipefail

# Cargar .env si existe
if [ -f .env ]; then
    set -a; . ./.env; set +a
fi

DUMP="${1:-dump_limpio.sql}"
HOST="${MYSQL_HOST:-127.0.0.1}"
PORT="${MYSQL_PORT:-3306}"
USER="${MYSQL_USER:-root}"
PASS="${MYSQL_PASSWORD:-}"
DB="${MYSQL_DATABASE:-emergencias}"

if [ ! -f "$DUMP" ]; then
    echo "ERROR: no encuentro el archivo '$DUMP'" >&2
    echo "Uso: $0 [archivo.sql]" >&2
    exit 1
fi

# Construir el array de credenciales (con o sin password)
CRED=(-h "$HOST" -P "$PORT" -u "$USER")
if [ -n "$PASS" ]; then
    CRED+=(-p"$PASS")
fi

echo "  → Recreando base '$DB' en $HOST:$PORT (usuario '$USER')"
mysql "${CRED[@]}" -e "
DROP DATABASE IF EXISTS \`$DB\`;
CREATE DATABASE \`$DB\` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
"

echo "  → Importando '$DUMP' ($(du -h "$DUMP" | cut -f1)) ..."
START=$(date +%s)
mysql "${CRED[@]}" "$DB" < "$DUMP"
END=$(date +%s)
echo "  ✓ Importado en $((END-START)) s"

echo
echo "  Tablas en '$DB':"
mysql "${CRED[@]}" "$DB" -e "
  SELECT TABLE_NAME, TABLE_ROWS
  FROM information_schema.TABLES
  WHERE TABLE_SCHEMA='$DB'
  ORDER BY TABLE_ROWS DESC;
"
