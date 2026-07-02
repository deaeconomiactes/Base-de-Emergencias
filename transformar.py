#!/usr/bin/env python3
"""
Limpia un dump .sql del sistema de Emergencias Agropecuarias quitando
tablas innecesarias y normalizando el esquema.

Uso:
    python3 transformar.py dump_original.sql -o dump_limpio.sql

Por defecto:
  - Elimina tablas administrativas/staging/backup (ver DEFAULT_DROP_TABLES).
  - Convierte ENGINE=MyISAM → InnoDB.
  - Fuerza DEFAULT CHARSET=utf8mb4.
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_DROP_TABLES = {
    "ddjj_personas_temp",   # staging duplicado
    "productos_bkp",        # backup interno
    "AnalisisOvinos",       # tabla vacía
    "usuarios_notix",       # MD5 sin salt + datos sensibles
    "menu_admin",           # admin del PHP, no aporta al análisis
    "submenu_admin",
    "permisos_admin",
    "permisos_submenu_admin",
}

# Patrones que delimitan un "bloque" de tabla en un dump de mysqldump.
PATTERNS = [
    re.compile(r"^--\s+Table structure for table `(?P<table>[^`]+)`", re.IGNORECASE),
    re.compile(r"^--\s+Dumping data for table `(?P<table>[^`]+)`", re.IGNORECASE),
    re.compile(r"^DROP TABLE IF EXISTS `(?P<table>[^`]+)`", re.IGNORECASE),
    re.compile(r"^CREATE TABLE `(?P<table>[^`]+)`", re.IGNORECASE),
    re.compile(r"^INSERT INTO `(?P<table>[^`]+)`", re.IGNORECASE),
    re.compile(r"^LOCK TABLES `(?P<table>[^`]+)`", re.IGNORECASE),
    re.compile(r"^ALTER TABLE `(?P<table>[^`]+)`", re.IGNORECASE),
]
VIEW_PATTERN = re.compile(
    r"^(?:--\s+)?(?:Final view structure for view|Temporary view structure for view)\s+`(?P<table>[^`]+)`",
    re.IGNORECASE,
)
CREATE_VIEW_RE = re.compile(r"CREATE\s+(?:ALGORITHM[^ ]+\s+)?(?:DEFINER=[^ ]+\s+)?(?:SQL SECURITY [A-Z]+\s+)?VIEW\s+`(?P<table>[^`]+)`", re.IGNORECASE)

# Sentencias problemáticas al re-importar (GTIDs, log_bin, definer)
SKIP_LINE_PATTERNS = [
    re.compile(r"^SET @@GLOBAL\.GTID_PURGED", re.IGNORECASE),
    re.compile(r"^SET @MYSQLDUMP_TEMP_LOG_BIN", re.IGNORECASE),
    re.compile(r"^SET @@SESSION\.SQL_LOG_BIN", re.IGNORECASE),
    re.compile(r"^SET @@GLOBAL\.GTID_EXECUTED", re.IGNORECASE),
    re.compile(r"^--\s+GTID state at the beginning of the backup", re.IGNORECASE),
]
DEFINER_RE = re.compile(r"DEFINER=`[^`]+`@`[^`]+`\s*", re.IGNORECASE)


def detectar_tabla(linea: str) -> str | None:
    """Devuelve el nombre de tabla mencionado en la línea, si lo hay."""
    for pat in PATTERNS:
        m = pat.match(linea)
        if m:
            return m.group("table")
    m = VIEW_PATTERN.match(linea)
    if m:
        return m.group("table")
    m = CREATE_VIEW_RE.search(linea)
    if m:
        return m.group("table")
    return None


def transformar(
    input_path: Path,
    output_path: Path,
    drop_tables: set[str],
    convertir_innodb: bool,
    forzar_utf8mb4: bool,
) -> dict:
    drop_lower = {t.lower() for t in drop_tables}
    skipping = False
    stats = {
        "lineas_total": 0,
        "lineas_descartadas": 0,
        "bytes_in": input_path.stat().st_size,
        "tablas_eliminadas": set(),
        "tablas_mantenidas": set(),
    }

    with input_path.open("r", encoding="utf-8", errors="replace") as fin, \
         output_path.open("w", encoding="utf-8") as fout:

        fout.write(f"-- Dump LIMPIO generado por transformar.py\n")
        fout.write(f"-- Fecha: {datetime.now().isoformat(timespec='seconds')}\n")
        fout.write(f"-- Origen: {input_path.name} ({stats['bytes_in']:,} bytes)\n")
        fout.write(f"-- Tablas omitidas: {', '.join(sorted(drop_tables))}\n")
        fout.write(f"--\n\n")
        fout.write("SET NAMES utf8mb4;\n")
        fout.write("SET FOREIGN_KEY_CHECKS=0;\n")
        fout.write("SET UNIQUE_CHECKS=0;\n\n")

        for line in fin:
            stats["lineas_total"] += 1

            tabla = detectar_tabla(line)
            if tabla is not None:
                if tabla.lower() in drop_lower:
                    skipping = True
                    stats["tablas_eliminadas"].add(tabla)
                else:
                    skipping = False
                    stats["tablas_mantenidas"].add(tabla)

            if skipping:
                stats["lineas_descartadas"] += 1
                continue

            # Saltar GTIDs / log_bin (causan errores al re-importar)
            if any(p.match(line) for p in SKIP_LINE_PATTERNS):
                stats["lineas_descartadas"] += 1
                continue

            # Quitar DEFINER de vistas y triggers (suelen no existir en destino)
            line = DEFINER_RE.sub("", line)

            if convertir_innodb:
                line = re.sub(r"ENGINE=MyISAM", "ENGINE=InnoDB", line, flags=re.IGNORECASE)
            if forzar_utf8mb4:
                line = re.sub(r"DEFAULT CHARSET=utf8\b", "DEFAULT CHARSET=utf8mb4", line, flags=re.IGNORECASE)
                line = re.sub(r"DEFAULT CHARSET=utf8mb3\b", "DEFAULT CHARSET=utf8mb4", line, flags=re.IGNORECASE)
                line = re.sub(r"DEFAULT CHARSET=latin1", "DEFAULT CHARSET=utf8mb4", line, flags=re.IGNORECASE)
                line = re.sub(r"COLLATE=utf8_general_ci", "COLLATE=utf8mb4_unicode_ci", line, flags=re.IGNORECASE)
                line = re.sub(r"CHARACTER SET ucs2[^,\n)]*", "CHARACTER SET utf8mb4", line, flags=re.IGNORECASE)
                line = re.sub(r"COLLATE ucs2_general_ci", "COLLATE utf8mb4_unicode_ci", line, flags=re.IGNORECASE)
                line = re.sub(
                    r"CHARACTER SET latin1 COLLATE latin1_swedish_ci",
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci",
                    line,
                    flags=re.IGNORECASE,
                )
            # TiDB no soporta LOCK TABLES / DISABLE KEYS del dump
            if re.match(r"^(LOCK TABLES|UNLOCK TABLES|/\*!40000 ALTER TABLE)", line.strip(), re.I):
                stats["lineas_descartadas"] += 1
                continue

            fout.write(line)

        fout.write("\nSET UNIQUE_CHECKS=1;\n")
        fout.write("SET FOREIGN_KEY_CHECKS=1;\n")

    stats["bytes_out"] = output_path.stat().st_size
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", help="Archivo .sql original recibido")
    ap.add_argument("-o", "--output", default="dump_limpio.sql", help="Archivo .sql de salida (default: dump_limpio.sql)")
    ap.add_argument("--drop", nargs="*", default=None, metavar="TABLA",
                    help="Tablas adicionales a eliminar (se suman a las por defecto)")
    ap.add_argument("--keep", nargs="*", default=None, metavar="TABLA",
                    help="Tablas a NO eliminar (se restan de las por defecto)")
    ap.add_argument("--no-innodb", action="store_true", help="No convertir MyISAM → InnoDB")
    ap.add_argument("--no-utf8mb4", action="store_true", help="No forzar utf8mb4")
    args = ap.parse_args()

    drop = set(DEFAULT_DROP_TABLES)
    if args.drop:
        drop.update(args.drop)
    if args.keep:
        drop.difference_update(args.keep)

    inp = Path(args.input)
    if not inp.exists():
        print(f"ERROR: no existe {inp}", file=sys.stderr)
        sys.exit(1)
    out = Path(args.output)

    print(f"  Entrada:  {inp}  ({inp.stat().st_size:,} bytes)")
    print(f"  Salida:   {out}")
    print(f"  Eliminar: {', '.join(sorted(drop)) or 'ninguna'}")
    print(f"  InnoDB:   {not args.no_innodb}    utf8mb4: {not args.no_utf8mb4}")
    print()

    stats = transformar(inp, out, drop, not args.no_innodb, not args.no_utf8mb4)

    print(f"  Líneas leídas:      {stats['lineas_total']:>10,}")
    print(f"  Líneas descartadas: {stats['lineas_descartadas']:>10,}  "
          f"({(stats['lineas_descartadas']/max(stats['lineas_total'],1))*100:.1f}%)")
    print(f"  Tablas eliminadas:  {len(stats['tablas_eliminadas'])} "
          f"({', '.join(sorted(stats['tablas_eliminadas'])) or '—'})")
    print(f"  Tablas mantenidas:  {len(stats['tablas_mantenidas'])}")
    print(f"  Tamaño salida:      {stats['bytes_out']:,} bytes  "
          f"({(1-stats['bytes_out']/max(stats['bytes_in'],1))*100:.1f}% más chico)")
    print()
    print(f"Listo. Importar con:")
    print(f"  ./importar_local.sh {out}        # MySQL local")
    print(f"  ./subir_a_tidb.sh   {out}        # TiDB Cloud")


if __name__ == "__main__":
    main()
