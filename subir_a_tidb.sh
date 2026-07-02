#!/usr/bin/env bash
# Carga un dump limpio a TiDB Cloud Serverless.
#
# Uso:
#   ./subir_a_tidb.sh [dump_limpio.sql]
#
# Variables requeridas en .env (o entorno):
#   TIDB_HOST   p.ej. gateway01.us-west-2.prod.aws.tidbcloud.com
#   TIDB_PORT   p.ej. 4000
#   TIDB_USER   p.ej. xxxxxxxx.root
#   TIDB_PASS   contraseña generada al crear el cluster
#   TIDB_DB     p.ej. emergencias
#
# Opcionales:
#   TIDB_SSL_CA  path al CA (mac: /etc/ssl/cert.pem ; linux: /etc/ssl/certs/ca-certificates.crt)

set -euo pipefail

if [ -f .env ]; then
    set -a; . ./.env; set +a
fi

DUMP="${1:-dump_limpio.sql}"

: "${TIDB_HOST:?TIDB_HOST no configurado (revisar .env)}"
: "${TIDB_USER:?TIDB_USER no configurado}"
: "${TIDB_PASS:?TIDB_PASS no configurado}"
: "${TIDB_DB:?TIDB_DB no configurado}"

TIDB_PORT="${TIDB_PORT:-4000}"

# Detectar CA por OS si no está definida
if [ -z "${TIDB_SSL_CA:-}" ]; then
    if [ -f /etc/ssl/cert.pem ]; then
        TIDB_SSL_CA=/etc/ssl/cert.pem                       # macOS
    elif [ -f /etc/ssl/certs/ca-certificates.crt ]; then
        TIDB_SSL_CA=/etc/ssl/certs/ca-certificates.crt      # Debian/Ubuntu
    elif [ -f /etc/pki/tls/certs/ca-bundle.crt ]; then
        TIDB_SSL_CA=/etc/pki/tls/certs/ca-bundle.crt        # Fedora/CentOS
    else
        echo "ERROR: no encuentro un CA bundle, definir TIDB_SSL_CA en .env" >&2
        exit 1
    fi
fi

if [ ! -f "$DUMP" ]; then
    echo "ERROR: no encuentro el archivo '$DUMP'" >&2
    exit 1
fi

CRED=(
    --connect-timeout=20
    --ssl-mode=VERIFY_IDENTITY
    --ssl-ca="$TIDB_SSL_CA"
    -h "$TIDB_HOST"
    -P "$TIDB_PORT"
    -u "$TIDB_USER"
    -p"$TIDB_PASS"
)

echo "  → Probando conexión TiDB: $TIDB_USER@$TIDB_HOST:$TIDB_PORT"
if ! mysql "${CRED[@]}" -e "SELECT 1" &>/dev/null; then
    echo "  → Cliente mysql CLI incompatible (mysql 9.x); usando PyMySQL ..."
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    PY="${SCRIPT_DIR}/.venv/bin/python"
    [ -x "$PY" ] || PY=python3
    exec "$PY" "${SCRIPT_DIR}/subir_a_tidb.py" "$DUMP"
fi
mysql "${CRED[@]}" -e "SELECT VERSION();"

echo "  → (Re)creando base '$TIDB_DB'"
mysql "${CRED[@]}" -e "
CREATE DATABASE IF NOT EXISTS \`$TIDB_DB\` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
"

echo "  → Subiendo '$DUMP' ($(du -h "$DUMP" | cut -f1)) ..."
START=$(date +%s)
mysql "${CRED[@]}" "$TIDB_DB" < "$DUMP"
END=$(date +%s)
echo "  ✓ Subido en $((END-START)) s"

echo
echo "  Tablas en TiDB:"
mysql "${CRED[@]}" "$TIDB_DB" -e "
  SELECT TABLE_NAME, TABLE_ROWS
  FROM information_schema.TABLES
  WHERE TABLE_SCHEMA='$TIDB_DB'
  ORDER BY TABLE_ROWS DESC;
"
