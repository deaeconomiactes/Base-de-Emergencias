"""Valida las tablas staging DDJJ 2023 en TiDB y genera evidencia local."""
from __future__ import annotations

import importlib.util
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = PROJECT_ROOT / "data_processed" / "ddjj_2023_excel" / "tidb_staging"
REPORT_MD = REPORT_DIR / "validation_ddjj_2023_tidb_staging.md"
REPORT_CSV = REPORT_DIR / "validation_ddjj_2023_tidb_staging_checks.csv"


def load_upload_module():
    path = Path(__file__).with_name("18_upload_ddjj_2023_to_tidb_staging.py")
    spec = importlib.util.spec_from_file_location("upload_ddjj_2023", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"No se pudo cargar {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


UPLOAD = load_upload_module()
TABLES = UPLOAD.TABLE_NAMES


class Checks:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def add(
        self,
        check_id: str,
        category: str,
        description: str,
        status: str,
        observed,
        expected,
        detail: str = "",
    ) -> None:
        self.rows.append(
            {
                "check_id": check_id,
                "categoria": category,
                "descripcion": description,
                "estado": status,
                "valor_observado": observed,
                "valor_esperado": expected,
                "detalle": detail,
            }
        )

    @property
    def global_status(self) -> str:
        states = {row["estado"] for row in self.rows}
        if "FAIL" in states:
            return "FAIL"
        if "WARN" in states:
            return "WARN"
        return "PASS"


def scalar(engine: Engine, sql: str, params: dict | None = None):
    with engine.connect() as connection:
        return connection.execute(text(sql), params or {}).scalar()


def table_exists(engine: Engine, table_name: str) -> bool:
    return bool(
        scalar(
            engine,
            """
            SELECT COUNT(*)
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table_name
            """,
            {"table_name": table_name},
        )
    )


def sum_bool(frame: pd.DataFrame, column: str) -> int:
    if column not in frame.columns:
        return 0
    return int(frame[column].fillna(False).astype(bool).sum())


def markdown_table(frame: pd.DataFrame) -> str:
    """Renderiza una tabla Markdown sin depender del paquete tabulate."""
    columns = [str(column) for column in frame.columns]
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in frame.itertuples(index=False, name=None):
        values = [
            str(value).replace("|", "\\|").replace("\n", " ")
            if pd.notna(value)
            else ""
            for value in row
        ]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def write_reports(checks: Checks) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(checks.rows)
    frame.to_csv(REPORT_CSV, index=False, encoding="utf-8-sig")
    counts = frame["estado"].value_counts().to_dict()
    lines = [
        "# Validación de staging TiDB DDJJ 2023",
        "",
        f"- **Fecha de validación:** {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"- **Estado global:** **{checks.global_status}**",
        f"- **PASS:** {counts.get('PASS', 0)}",
        f"- **WARN:** {counts.get('WARN', 0)}",
        f"- **FAIL:** {counts.get('FAIL', 0)}",
        "",
        "## Alcance",
        "",
        "Validación de tablas `stg_ddjj_2023_*` contra las tablas normalizadas locales. ",
        "No valida ni modifica vistas finales.",
        "",
        "## Checks",
        "",
        markdown_table(frame),
        "",
        "## Interpretación",
        "",
        "Los WARN institucionales preservan trazabilidad y no habilitan por sí mismos ",
        "la integración. Cualquier FAIL bloquea la creación de vistas unificadas.",
    ]
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    checks = Checks()
    local_frames = UPLOAD.build_staging_frames()
    engine = UPLOAD.make_engine()
    try:
        missing_tables = []
        for logical_name, table_name in TABLES.items():
            exists = table_exists(engine, table_name)
            checks.add(
                f"table_exists_{logical_name}",
                "existencia",
                f"Existe {table_name}",
                "PASS" if exists else "FAIL",
                exists,
                True,
            )
            if not exists:
                missing_tables.append(table_name)

        if missing_tables:
            write_reports(checks)
            print(f"Estado global: {checks.global_status}")
            print(f"Faltan tablas: {', '.join(missing_tables)}")
            raise SystemExit(1)

        for logical_name, table_name in TABLES.items():
            observed = int(scalar(engine, f"SELECT COUNT(*) FROM `{table_name}`"))
            expected = len(local_frames[logical_name])
            checks.add(
                f"row_count_{logical_name}",
                "conteos",
                f"Conteo de {table_name} coincide con fuente local filtrada",
                "PASS" if observed == expected else "FAIL",
                observed,
                expected,
            )

        main_table = TABLES["tramite"]
        total = int(scalar(engine, f"SELECT COUNT(*) FROM `{main_table}`"))
        unique_ids = int(
            scalar(engine, f"SELECT COUNT(DISTINCT tramite_id) FROM `{main_table}`")
        )
        duplicates = int(
            scalar(
                engine,
                f"""
                SELECT COUNT(*) FROM (
                    SELECT tramite_id FROM `{main_table}`
                    GROUP BY tramite_id HAVING COUNT(*) > 1
                ) duplicate_keys
                """,
            )
        )
        for check_id, description, observed, expected in (
            ("main_rows", "Trámites integrables", total, UPLOAD.EXPECTED_ROWS),
            ("main_unique_ids", "tramite_id únicos", unique_ids, UPLOAD.EXPECTED_ROWS),
            ("main_duplicates", "Claves duplicadas", duplicates, 0),
        ):
            checks.add(
                check_id,
                "unicidad",
                description,
                "PASS" if observed == expected else "FAIL",
                observed,
                expected,
            )

        normative_checks = [
            (
                "event_id",
                "evento_id_normativo",
                "DECRETO_2099_2023",
            ),
            ("numero_norma", "numero_norma", "2099"),
            ("anio_norma", "CAST(anio_norma AS CHAR)", "2023"),
            ("normative_label", "resolucion_label", "Decreto 2099/23"),
        ]
        for check_id, expression, expected in normative_checks:
            invalid = int(
                scalar(
                    engine,
                    f"SELECT COUNT(*) FROM `{main_table}` "
                    f"WHERE COALESCE(CAST({expression} AS CHAR), '') <> :expected",
                    {"expected": expected},
                )
            )
            checks.add(
                check_id,
                "normativa",
                f"Todos los trámites tienen {expression} esperado",
                "PASS" if invalid == 0 else "FAIL",
                invalid,
                0,
                "Se cuentan valores distintos o nulos.",
            )

        for check_id, column in (
            ("producer_not_null", "productor_id_2023"),
            ("cuit_not_null", "cuit"),
        ):
            nulls = int(
                scalar(
                    engine,
                    f"SELECT COUNT(*) FROM `{main_table}` "
                    f"WHERE `{column}` IS NULL OR TRIM(CAST(`{column}` AS CHAR)) = ''",
                )
            )
            checks.add(
                check_id,
                "completitud",
                f"{column} no nulo en trámites integrables",
                "PASS" if nulls == 0 else "WARN",
                nulls,
                0,
                "El registro se conserva si el dato no existe en fuente.",
            )

        adrema_rows = int(scalar(engine, f"SELECT COUNT(*) FROM `{TABLES['adrema']}`"))
        adrema_links = int(
            scalar(
                engine,
                f"""
                SELECT COUNT(*)
                FROM `{TABLES['adrema']}` a
                LEFT JOIN `{main_table}` t ON t.tramite_id = a.tramite_id
                WHERE t.tramite_id IS NULL
                """,
            )
        )
        checks.add(
            "adremas_loaded",
            "detalle",
            "ADREMAS cargadas",
            "PASS" if adrema_rows > 0 else "FAIL",
            adrema_rows,
            "> 0",
        )
        checks.add(
            "adremas_orphan",
            "integridad",
            "ADREMAS sin trámite integrable",
            "PASS" if adrema_links == 0 else "FAIL",
            adrema_links,
            0,
        )

        for logical_name in ("agricultura", "ganaderia", "calidad", "bridge"):
            table_name = TABLES[logical_name]
            orphans = int(
                scalar(
                    engine,
                    f"""
                    SELECT COUNT(*)
                    FROM `{table_name}` d
                    LEFT JOIN `{main_table}` t ON t.tramite_id = d.tramite_id
                    WHERE t.tramite_id IS NULL
                    """,
                )
            )
            checks.add(
                f"orphans_{logical_name}",
                "integridad",
                f"{table_name} sin trámite integrable",
                "PASS" if orphans == 0 else "FAIL",
                orphans,
                0,
            )

        excluded = int(
            scalar(
                engine,
                f"""
                SELECT COUNT(*) FROM `{main_table}`
                WHERE COALESCE(dq_estado_anulado, 0) = 1
                   OR COALESCE(dq_fecha_fuera_2023, 0) = 1
                """,
            )
        )
        checks.add(
            "selective_exclusions",
            "universo",
            "No se cargaron anulados ni fuera de 2023 en tabla principal",
            "PASS" if excluded == 0 else "FAIL",
            excluded,
            0,
        )

        quality_columns = [
            column
            for column in local_frames["calidad"].columns
            if column.startswith("dq_")
        ]
        for column in quality_columns:
            expected = sum_bool(local_frames["calidad"], column)
            observed = int(
                scalar(
                    engine,
                    f"SELECT COALESCE(SUM(CASE WHEN `{column}` THEN 1 ELSE 0 END), 0) "
                    f"FROM `{TABLES['calidad']}`",
                )
            )
            checks.add(
                f"preserved_{column}",
                "trazabilidad",
                f"Bandera {column} preservada",
                "PASS" if observed == expected else "FAIL",
                observed,
                expected,
            )

        bridge_table = TABLES["bridge"]
        warnings = [
            (
                "bridge_validated_by_pending",
                "validado_por pendiente",
                f"SELECT COUNT(*) FROM `{bridge_table}` "
                "WHERE COALESCE(validado_por, '') = 'pendiente_completar'",
            ),
            (
                "bridge_start_date_blank",
                "fecha_inicio_evento vacía",
                f"SELECT COUNT(*) FROM `{bridge_table}` WHERE fecha_inicio_evento IS NULL",
            ),
            (
                "bridge_end_date_blank",
                "fecha_fin_evento vacía",
                f"SELECT COUNT(*) FROM `{bridge_table}` WHERE fecha_fin_evento IS NULL",
            ),
        ]
        for check_id, description, sql in warnings:
            observed = int(scalar(engine, sql))
            checks.add(
                check_id,
                "advertencia_institucional",
                description,
                "WARN" if observed > 0 else "PASS",
                observed,
                0,
                "Advertencia documentada; no altera la clave normativa validada.",
            )

        write_reports(checks)
        print(f"Estado global: {checks.global_status}")
        print(f"Reporte Markdown: {REPORT_MD}")
        print(f"Checks CSV: {REPORT_CSV}")
        if checks.global_status == "FAIL":
            raise SystemExit(1)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
