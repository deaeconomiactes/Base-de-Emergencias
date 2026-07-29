"""Valida la integración DDJJ 2023 en las vistas unificadas de TiDB."""
from __future__ import annotations

import importlib.util
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import text


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = PROJECT_ROOT / "data_processed" / "ddjj_2023_excel" / "tidb_staging"
REPORT_MD = REPORT_DIR / "validation_unified_views_ddjj_2023.md"
REPORT_CSV = REPORT_DIR / "validation_unified_views_ddjj_2023_checks.csv"
ORIGIN = "ddjj_2023_excel"
EXPECTED_ROWS = 1_483

VIEWS = [
    "vw_all_resoluciones",
    "vw_all_ddjj_personas",
    "vw_all_productores",
    "vw_all_tipoactividad",
    "vw_all_agricultura",
    "vw_all_cultivos",
    "vw_all_cultivostipo",
    "vw_all_ganaderia_resumen",
]


def load_upload_module():
    path = Path(__file__).with_name("18_upload_ddjj_2023_to_tidb_staging.py")
    spec = importlib.util.spec_from_file_location("upload_ddjj_2023", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"No se pudo cargar {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


UPLOAD = load_upload_module()


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
    def status(self) -> str:
        states = {row["estado"] for row in self.rows}
        if "FAIL" in states:
            return "FAIL"
        if "WARN" in states:
            return "WARN"
        return "PASS"


def scalar(engine, sql: str, params: dict | None = None):
    with engine.connect() as connection:
        return connection.execute(text(sql), params or {}).scalar()


def add_equal(
    checks: Checks,
    check_id: str,
    category: str,
    description: str,
    observed,
    expected,
    detail: str = "",
) -> None:
    checks.add(
        check_id,
        category,
        description,
        "PASS" if observed == expected else "FAIL",
        observed,
        expected,
        detail,
    )


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
        "# Validación de vistas unificadas con DDJJ 2023",
        "",
        f"- **Fecha:** {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"- **Estado global:** **{checks.status}**",
        f"- **PASS:** {counts.get('PASS', 0)}",
        f"- **WARN:** {counts.get('WARN', 0)}",
        f"- **FAIL:** {counts.get('FAIL', 0)}",
        "",
        "## Checks",
        "",
        markdown_table(frame),
        "",
        "## Regla analítica",
        "",
        "Los registros con mortandad mayor que cantidad o superficies negativas ",
        "permanecen trazables, pero sus medidas no aptas se exponen como NULL.",
    ]
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    checks = Checks()
    engine = UPLOAD.make_engine()
    try:
        with engine.connect() as connection:
            existing = {
                row.TABLE_NAME
                for row in connection.execute(
                    text(
                        """
                        SELECT TABLE_NAME FROM information_schema.VIEWS
                        WHERE TABLE_SCHEMA = DATABASE()
                          AND TABLE_NAME IN (
                            'vw_all_resoluciones', 'vw_all_ddjj_personas',
                            'vw_all_productores', 'vw_all_tipoactividad',
                            'vw_all_agricultura', 'vw_all_cultivos',
                            'vw_all_cultivostipo', 'vw_all_ganaderia_resumen'
                          )
                        """
                    )
                ).fetchall()
            }
        for view in VIEWS:
            add_equal(
                checks,
                f"view_exists_{view}",
                "existencia",
                f"Existe {view}",
                view in existing,
                True,
            )
        if set(VIEWS) - existing:
            write_reports(checks)
            raise SystemExit(1)

        ddjj_rows = int(
            scalar(
                engine,
                "SELECT COUNT(*) FROM vw_all_ddjj_personas WHERE origen_dato = :origin",
                {"origin": ORIGIN},
            )
        )
        ddjj_unique = int(
            scalar(
                engine,
                """
                SELECT COUNT(DISTINCT ddjj_all_id)
                FROM vw_all_ddjj_personas WHERE origen_dato = :origin
                """,
                {"origin": ORIGIN},
            )
        )
        add_equal(checks, "ddjj_rows", "universo", "DDJJ 2023 integrables", ddjj_rows, EXPECTED_ROWS)
        add_equal(checks, "ddjj_unique", "unicidad", "DDJJ 2023 únicas", ddjj_unique, EXPECTED_ROWS)

        duplicate_keys = int(
            scalar(
                engine,
                """
                SELECT COUNT(*) FROM (
                    SELECT ddjj_all_id FROM vw_all_ddjj_personas
                    GROUP BY ddjj_all_id HAVING COUNT(*) > 1
                ) duplicates
                """,
            )
        )
        add_equal(
            checks,
            "all_ddjj_duplicates",
            "unicidad",
            "No se duplicaron claves unificadas de DDJJ",
            duplicate_keys,
            0,
        )

        normative_rows = int(
            scalar(
                engine,
                """
                SELECT COUNT(*) FROM vw_all_resoluciones
                WHERE origen_dato = 'ddjj_2023_excel'
                  AND evento_id = 'DECRETO_2099_2023'
                  AND numero_resolucion = 'Decreto 2099/23'
                  AND nombre_resolucion = 'Decreto 2099/23'
                """,
            )
        )
        add_equal(
            checks,
            "normative_event_visible",
            "normativa",
            "Decreto 2099/23 visible como resolución/evento",
            normative_rows,
            1,
        )

        orphan_norm = int(
            scalar(
                engine,
                """
                SELECT COUNT(*)
                FROM vw_all_ddjj_personas d
                LEFT JOIN vw_all_resoluciones r
                  ON r.origen_dato = d.origen_dato AND r.evento_id = d.evento_id
                WHERE d.origen_dato = 'ddjj_2023_excel'
                  AND r.resolucion_all_id IS NULL
                """,
            )
        )
        add_equal(
            checks,
            "normative_orphans",
            "integridad",
            "DDJJ 2023 sin evento normativo",
            orphan_norm,
            0,
        )

        year_rows = int(
            scalar(
                engine,
                """
                SELECT COUNT(*) FROM vw_all_ddjj_personas
                WHERE origen_dato = 'ddjj_2023_excel' AND YEAR(fecha) = 2023
                """,
            )
        )
        add_equal(
            checks,
            "year_filter_2023",
            "filtros",
            "Filtro por año 2023 recupera universo integrable",
            year_rows,
            EXPECTED_ROWS,
        )

        source_rows = int(
            scalar(
                engine,
                """
                SELECT COUNT(*) FROM vw_all_ddjj_personas
                WHERE origen_dato = 'ddjj_2023_excel'
                  AND source_file IS NOT NULL AND source_file <> ''
                """,
            )
        )
        add_equal(
            checks,
            "source_traceability",
            "trazabilidad",
            "Fuente DDJJ 2023 Excel identificable",
            source_rows,
            EXPECTED_ROWS,
        )

        producer_orphans = int(
            scalar(
                engine,
                """
                SELECT COUNT(*)
                FROM vw_all_ddjj_personas d
                LEFT JOIN vw_all_productores p
                  ON p.origen_dato = d.origen_dato
                 AND p.productor_all_id = d.productor_all_id
                WHERE d.origen_dato = 'ddjj_2023_excel'
                  AND p.productor_all_id IS NULL
                """,
            )
        )
        add_equal(
            checks,
            "producer_links",
            "integridad",
            "DDJJ 2023 sin productor unificado",
            producer_orphans,
            0,
        )

        for detail, key in (
            ("vw_all_agricultura", "agricultura_all_id"),
            ("vw_all_ganaderia_resumen", "ganaderia_all_id"),
        ):
            orphan_details = int(
                scalar(
                    engine,
                    f"""
                    SELECT COUNT(*)
                    FROM `{detail}` x
                    LEFT JOIN vw_all_ddjj_personas d
                      ON d.origen_dato = x.origen_dato
                     AND d.ddjj_hist_id = x.ddjj_hist_id
                    WHERE x.origen_dato = 'ddjj_2023_excel'
                      AND d.ddjj_all_id IS NULL
                    """,
                )
            )
            duplicates = int(
                scalar(
                    engine,
                    f"""
                    SELECT COUNT(*) FROM (
                        SELECT `{key}` FROM `{detail}`
                        GROUP BY `{key}` HAVING COUNT(*) > 1
                    ) duplicates
                    """,
                )
            )
            add_equal(
                checks,
                f"orphans_{detail}",
                "integridad",
                f"{detail} sin DDJJ unificada",
                orphan_details,
                0,
            )
            add_equal(
                checks,
                f"duplicates_{detail}",
                "unicidad",
                f"Claves duplicadas en {detail}",
                duplicates,
                0,
            )

        invalid_livestock_measures = int(
            scalar(
                engine,
                """
                SELECT COUNT(*) FROM vw_all_ganaderia_resumen
                WHERE origen_dato = 'ddjj_2023_excel'
                  AND flag_mortandad_mayor_existencias = 1
                  AND (existencias IS NOT NULL OR mortandad IS NOT NULL)
                """,
            )
        )
        add_equal(
            checks,
            "invalid_livestock_excluded",
            "regla_analitica",
            "Mortandad > cantidad no alimenta medidas cuantitativas",
            invalid_livestock_measures,
            0,
        )

        negative_surface_measures = int(
            scalar(
                engine,
                """
                SELECT
                    (SELECT COUNT(*) FROM vw_all_agricultura
                     WHERE origen_dato = 'ddjj_2023_excel'
                       AND (superficie_sembrada_uso < 0 OR superficie_afectada < 0))
                  + (SELECT COUNT(*) FROM vw_all_ganaderia_resumen
                     WHERE origen_dato = 'ddjj_2023_excel'
                       AND (superficie_ganadera_uso < 0 OR superficie_ganadera_afectada < 0))
                """,
            )
        )
        add_equal(
            checks,
            "negative_surfaces_excluded",
            "regla_analitica",
            "No se exponen superficies negativas como medidas",
            negative_surface_measures,
            0,
        )

        home_queries = {
            "home_list_resolutions": """
                SELECT resolucion_all_id, nombre_resolucion, numero_resolucion,
                       fec_res, origen_dato
                FROM vw_all_resoluciones ORDER BY fec_res DESC LIMIT 100
            """,
            "home_date_range": """
                SELECT MIN(fecha), MAX(fecha) FROM vw_all_ddjj_personas
            """,
            "home_year_filter": """
                SELECT YEAR(fecha), COUNT(*) FROM vw_all_ddjj_personas
                WHERE origen_dato = 'ddjj_2023_excel' AND YEAR(fecha) = 2023
                GROUP BY YEAR(fecha)
            """,
            "home_resolution_ranking": """
                SELECT r.numero_resolucion, r.nombre_resolucion, COUNT(*) AS ddjj
                FROM vw_all_ddjj_personas d
                JOIN vw_all_resoluciones r
                  ON r.origen_dato = d.origen_dato
                 AND ((r.origen_dato = 'actual'
                       AND r.id_resolucion_actual = d.id_resolucion_actual)
                      OR (r.origen_dato <> 'actual' AND r.evento_id = d.evento_id))
                WHERE d.origen_dato = 'ddjj_2023_excel'
                GROUP BY r.numero_resolucion, r.nombre_resolucion
            """,
        }
        with engine.connect() as connection:
            for check_id, sql in home_queries.items():
                try:
                    rows = connection.execute(text(sql)).fetchall()
                    checks.add(
                        check_id,
                        "dashboard",
                        f"Consulta principal de Home: {check_id}",
                        "PASS" if rows else "FAIL",
                        len(rows),
                        "> 0",
                    )
                except Exception as exc:
                    checks.add(
                        check_id,
                        "dashboard",
                        f"Consulta principal de Home: {check_id}",
                        "FAIL",
                        "error",
                        "sin error",
                        str(exc),
                    )

        bridge_table = "stg_ddjj_2023_bridge_normativo"
        for check_id, description, sql in (
            (
                "pending_validated_by",
                "validado_por pendiente de completar",
                f"SELECT COUNT(*) FROM {bridge_table} WHERE validado_por = 'pendiente_completar'",
            ),
            (
                "blank_event_start",
                "fecha_inicio_evento vacía",
                f"SELECT COUNT(*) FROM {bridge_table} WHERE fecha_inicio_evento IS NULL",
            ),
            (
                "blank_event_end",
                "fecha_fin_evento vacía",
                f"SELECT COUNT(*) FROM {bridge_table} WHERE fecha_fin_evento IS NULL",
            ),
        ):
            observed = int(scalar(engine, sql))
            checks.add(
                check_id,
                "advertencia_institucional",
                description,
                "WARN" if observed else "PASS",
                observed,
                0,
                "Advertencia documentada; no modifica la asignación al Decreto 2099/23.",
            )

        write_reports(checks)
        print(f"Estado global: {checks.status}")
        print(f"Reporte: {REPORT_MD}")
        print(f"Checks: {REPORT_CSV}")
        if checks.status == "FAIL":
            raise SystemExit(1)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
