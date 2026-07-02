#!/usr/bin/env python3
"""
Sube dump_limpio.sql a TiDB Cloud usando PyMySQL (compatible con mysql_native_password).
El cliente mysql 9.x de Homebrew ya no carga ese plugin.

Uso:
    python3 subir_a_tidb.py [dump_limpio.sql]
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")


def main() -> None:
    dump = Path(sys.argv[1] if len(sys.argv) > 1 else "dump_limpio.sql")
    if not dump.exists():
        print(f"ERROR: no existe {dump}", file=sys.stderr)
        sys.exit(1)

    host = os.environ.get("TIDB_HOST")
    port = int(os.environ.get("TIDB_PORT", "4000"))
    user = os.environ.get("TIDB_USER")
    password = os.environ.get("TIDB_PASS")
    database = os.environ.get("TIDB_DB", "emergencias")
    ssl_ca = os.environ.get("TIDB_SSL_CA", "/etc/ssl/cert.pem")

    for var, val in [("TIDB_HOST", host), ("TIDB_USER", user), ("TIDB_PASS", password)]:
        if not val:
            print(f"ERROR: {var} no configurado en .env", file=sys.stderr)
            sys.exit(1)

    import pymysql

    print(f"  → Conectando a {user}@{host}:{port} ...")
    conn = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        charset="utf8mb4",
        ssl={"ca": ssl_ca},
        connect_timeout=30,
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT VERSION()")
            ver = cur.fetchone()[0]
        print(f"  ✓ Conexión OK — {ver}")

        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{database}` "
                "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        conn.select_db(database)
        print(f"  → Base activa: `{database}`")

        size_mb = dump.stat().st_size / (1024 * 1024)
        print(f"  → Importando {dump.name} ({size_mb:.1f} MB) ...")
        start = time.time()
        statements = 0
        errors = 0
        buf: list[str] = []

        with dump.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                stripped = line.strip()
                if not stripped or stripped.startswith("--"):
                    continue
                buf.append(line)
                if stripped.endswith(";"):
                    sql = "".join(buf)
                    buf.clear()
                    try:
                        with conn.cursor() as cur:
                            cur.execute(sql)
                        statements += 1
                        if statements % 500 == 0:
                            conn.commit()
                            print(f"     … {statements} sentencias", flush=True)
                    except pymysql.Error as e:
                        errors += 1
                        if errors <= 5:
                            preview = sql[:120].replace("\n", " ")
                            print(f"  WARN [{e.args[0]}]: {preview}…", file=sys.stderr)

        conn.commit()
        elapsed = time.time() - start
        print(f"  ✓ Importado en {elapsed:.0f} s — {statements} sentencias"
              + (f" ({errors} advertencias)" if errors else ""))

        print("\n  Tablas (top 15 por filas estimadas):")
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT TABLE_NAME, TABLE_ROWS
                FROM information_schema.TABLES
                WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'BASE TABLE'
                ORDER BY TABLE_ROWS DESC
                LIMIT 15
                """,
                (database,),
            )
            for name, rows in cur.fetchall():
                print(f"    {name:30} {rows or 0:>10,}")

        # Conteos reales en tablas clave
        print("\n  Verificación COUNT(*):")
        for tbl in ("productores", "ddjj_personas", "adremas", "resoluciones"):
            with conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) FROM `{tbl}`")
                n = cur.fetchone()[0]
            print(f"    {tbl:20} {n:>10,}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
