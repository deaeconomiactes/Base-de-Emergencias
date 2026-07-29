"""Incorpora la rama DDJJ 2023 a las vistas ``vw_all_*`` de TiDB.

Antes de reemplazar vistas operativas, guarda sus definiciones, crea vistas de
prueba con sufijo ``_test_ddjj_2023`` y valida los conteos de la nueva rama.
Ante un error durante el reemplazo intenta restaurar las definiciones previas.
"""
from __future__ import annotations

import importlib.util
from datetime import datetime
from pathlib import Path

from sqlalchemy import text


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = PROJECT_ROOT / "data_processed" / "ddjj_2023_excel" / "tidb_staging"
RESULT_PATH = REPORT_DIR / "create_unified_views_ddjj_2023_resultados.md"
ORIGIN = "ddjj_2023_excel"

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


ADREMA_AGG = """
    SELECT
        tramite_id,
        GROUP_CONCAT(DISTINCT NULLIF(adrema, '') ORDER BY adrema SEPARATOR ' | ') AS adremas,
        GROUP_CONCAT(DISTINCT NULLIF(renspa, '') ORDER BY renspa SEPARATOR ' | ') AS renspa,
        GROUP_CONCAT(DISTINCT NULLIF(departamento, '') ORDER BY departamento SEPARATOR ' | ') AS departamento,
        GROUP_CONCAT(DISTINCT NULLIF(localidad, '') ORDER BY localidad SEPARATOR ' | ') AS localidad,
        GROUP_CONCAT(DISTINCT NULLIF(paraje, '') ORDER BY paraje SEPARATOR ' | ') AS paraje,
        GROUP_CONCAT(
            DISTINCT NULLIF(CONCAT_WS(' ', seccion_1_original, seccion_2_original), '')
            ORDER BY seccion_1_original, seccion_2_original SEPARATOR ' | '
        ) AS seccion,
        GROUP_CONCAT(
            DISTINCT NULLIF(actividad_normalizada_preliminar, '')
            ORDER BY actividad_normalizada_preliminar SEPARATOR ' | '
        ) AS actividad
    FROM stg_ddjj_2023_adrema
    GROUP BY tramite_id
"""


def branch_sql() -> dict[str, str]:
    alert_expression = """
        COALESCE(t.dq_cuit_invalido, 0) = 1
        OR COALESCE(t.dq_adrema_faltante, 0) = 1
        OR COALESCE(t.dq_tiene_superficie_negativa, 0) = 1
        OR COALESCE(t.dq_tiene_adrema_duplicada, 0) = 1
        OR COALESCE(t.dq_tiene_mortandad_mayor_cantidad, 0) = 1
        OR COALESCE(t.dq_numero_certificado_nulo, 0) = 1
    """
    return {
        "vw_all_resoluciones": """
            SELECT
                SHA2(CONCAT_WS('|', 'ddjj_2023_excel', t.evento_id_normativo), 256) AS resolucion_all_id,
                CAST(NULL AS SIGNED) AS id_resolucion_actual,
                t.evento_id_normativo AS evento_id,
                MAX(t.anio_norma) AS anio,
                MAX(t.resolucion_label) AS dto,
                MAX(t.resolucion_label) AS numero_resolucion,
                MAX(t.nombre_evento) AS nombre_resolucion,
                MIN(t.fecha_inicio_evento) AS fec_res,
                MIN(t.source_file) AS source_file,
                COUNT(DISTINCT t.tramite_id) AS registros,
                COUNT(DISTINCT t.productor_id_2023) AS productores,
                CASE WHEN SUM(CASE WHEN """ + alert_expression + """ THEN 1 ELSE 0 END) > 0
                     THEN 'advertencia' ELSE 'sin_alerta' END AS severidad_maxima,
                'ddjj_2023_excel' AS origen_dato
            FROM stg_ddjj_2023_tramite t
            GROUP BY t.evento_id_normativo
        """,
        "vw_all_ddjj_personas": """
            SELECT
                SHA2(CONCAT_WS('|', 'ddjj_2023_excel', t.tramite_id), 256) AS ddjj_all_id,
                CAST(NULL AS SIGNED) AS id_ddjj_actual,
                t.tramite_id AS ddjj_hist_id,
                SHA2(CONCAT_WS('|', 'ddjj_2023_excel', t.productor_id_2023), 256) AS productor_all_id,
                CAST(NULL AS SIGNED) AS id_productor_actual,
                t.productor_id_2023 AS productor_hist_id,
                CAST(NULL AS SIGNED) AS id_resolucion_actual,
                t.evento_id_normativo AS evento_id,
                t.anio AS anio,
                t.fecha AS fecha,
                t.fecha_inicio_evento AS fecha_evento,
                t.resolucion_label AS dto,
                NULLIF(CONCAT_WS(' - ', t.fecha_inicio_evento, t.fecha_fin_evento), '') AS periodo,
                t.source_file AS source_file,
                t.source_sheet AS source_sheet,
                'ddjj_tramite' AS dataset_role,
                'bridge_normativo_validado' AS relation_type,
                t.tramite_id AS iddj,
                a.adremas AS codigo,
                CAST(NULL AS CHAR(12)) AS solicitud_id,
                CAST(NULL AS CHAR(50)) AS documento_nro,
                t.cuit AS cuit_cuil,
                t.razon_social AS productor_nombre,
                a.departamento AS departamento,
                a.localidad AS localidad,
                a.paraje AS paraje,
                a.seccion AS seccion,
                a.renspa AS renspa,
                a.actividad AS actividad,
                cult.cultivo AS cultivo,
                CAST(NULL AS DECIMAL(18,4)) AS pondf,
                CAST(NULL AS DECIMAL(18,4)) AS porcentaje_afectacion_ganadera,
                CAST(NULL AS DECIMAL(18,4)) AS porcentaje_afectacion,
                CAST(NULL AS DECIMAL(18,4)) AS superficie_total,
                CAST(NULL AS DECIMAL(18,4)) AS superficie_agricola_uso,
                CAST(NULL AS DECIMAL(18,4)) AS superficie_agricola_afectada,
                CAST(NULL AS DECIMAL(18,4)) AS superficie_ganadera_uso,
                CAST(NULL AS DECIMAL(18,4)) AS superficie_ganadera_afectada,
                CAST(NULL AS DECIMAL(18,4)) AS existencias,
                CAST(NULL AS DECIMAL(18,4)) AS mortandad,
                CAST(NULL AS DECIMAL(18,4)) AS produccion_estimada,
                CAST(NULL AS DECIMAL(18,4)) AS produccion_obtenida,
                0 AS flag_anio_corregido,
                COALESCE(t.dq_fecha_fuera_2023, 0) AS flag_anio_fuera_rango,
                COALESCE(t.dq_tiene_superficie_negativa, 0) AS flag_superficie_negativa,
                0 AS flag_agricola_afectada_mayor_uso,
                0 AS flag_ganadera_afectada_mayor_uso,
                COALESCE(t.dq_tiene_mortandad_mayor_cantidad, 0) AS flag_mortandad_mayor_existencias,
                0 AS flag_superficie_total_menor_afectadas,
                CASE WHEN """ + alert_expression + """ THEN 1 ELSE 0 END AS flag_revision_manual,
                CASE WHEN """ + alert_expression + """ THEN 'advertencia'
                     ELSE 'sin_alerta' END AS severidad_maxima,
                'ddjj_2023_excel' AS origen_dato
            FROM stg_ddjj_2023_tramite t
            LEFT JOIN (""" + ADREMA_AGG + """) a ON a.tramite_id = t.tramite_id
            LEFT JOIN (
                SELECT tramite_id,
                       GROUP_CONCAT(
                           DISTINCT COALESCE(NULLIF(producto, ''), NULLIF(especie_cultivo, ''), NULLIF(rubro, ''))
                           ORDER BY COALESCE(NULLIF(producto, ''), NULLIF(especie_cultivo, ''), NULLIF(rubro, ''))
                           SEPARATOR ' | '
                       ) AS cultivo
                FROM stg_ddjj_2023_agricultura
                GROUP BY tramite_id
            ) cult ON cult.tramite_id = t.tramite_id
        """,
        "vw_all_productores": """
            SELECT
                SHA2(CONCAT_WS('|', 'ddjj_2023_excel', p.productor_id_2023), 256) AS productor_all_id,
                CAST(NULL AS SIGNED) AS id_productor_actual,
                p.productor_id_2023 AS productor_hist_id,
                p.productor_nombre AS productor_nombre,
                CAST(NULL AS CHAR(50)) AS documento_nro,
                p.cuit_cuil AS cuit_cuil,
                GROUP_CONCAT(DISTINCT NULLIF(a.departamento, '') ORDER BY a.departamento SEPARATOR ' | ') AS departamento,
                GROUP_CONCAT(DISTINCT NULLIF(a.localidad, '') ORDER BY a.localidad SEPARATOR ' | ') AS localidad,
                GROUP_CONCAT(DISTINCT NULLIF(a.paraje, '') ORDER BY a.paraje SEPARATOR ' | ') AS paraje,
                GROUP_CONCAT(DISTINCT NULLIF(a.renspa, '') ORDER BY a.renspa SEPARATOR ' | ') AS renspa,
                GROUP_CONCAT(DISTINCT NULLIF(a.actividad_normalizada_preliminar, '')
                             ORDER BY a.actividad_normalizada_preliminar SEPARATOR ' | ') AS actividad,
                COUNT(DISTINCT t.evento_id_normativo) AS eventos,
                COUNT(DISTINCT t.tramite_id) AS registros,
                MIN(t.source_file) AS source_file,
                CASE WHEN SUM(CASE WHEN """ + alert_expression + """ THEN 1 ELSE 0 END) > 0
                     THEN 'advertencia' ELSE 'sin_alerta' END AS severidad_maxima,
                'ddjj_2023_excel' AS origen_dato
            FROM stg_ddjj_2023_productor p
            JOIN stg_ddjj_2023_tramite t ON t.productor_id_2023 = p.productor_id_2023
            LEFT JOIN stg_ddjj_2023_adrema a ON a.tramite_id = t.tramite_id
            GROUP BY p.productor_id_2023, p.productor_nombre, p.cuit_cuil
        """,
        "vw_all_tipoactividad": """
            SELECT
                SHA2(CONCAT_WS('|', 'ddjj_2023_excel', 'agricultura'), 256) AS actividad_all_id,
                CAST(NULL AS SIGNED) AS id_actividad_actual,
                'agricultura' AS actividad_hist_id,
                'Agricultura' AS actividad,
                COUNT(*) AS registros,
                COUNT(DISTINCT tramite_id) AS eventos,
                'ddjj_2023_excel' AS origen_dato
            FROM stg_ddjj_2023_agricultura
            HAVING COUNT(*) > 0
            UNION ALL
            SELECT
                SHA2(CONCAT_WS('|', 'ddjj_2023_excel', 'ganaderia'), 256),
                CAST(NULL AS SIGNED),
                'ganaderia',
                'Ganadería',
                COUNT(*),
                COUNT(DISTINCT tramite_id),
                'ddjj_2023_excel'
            FROM stg_ddjj_2023_ganaderia
            HAVING COUNT(*) > 0
        """,
        "vw_all_agricultura": """
            SELECT
                SHA2(CONCAT_WS('|', 'ddjj_2023_excel', ag.agricultura_id_2023), 256) AS agricultura_all_id,
                CAST(NULL AS SIGNED) AS id_agricultura_actual,
                ag.agricultura_id_2023 AS agricultura_hist_id,
                CAST(NULL AS SIGNED) AS id_ddjj_actual,
                ag.tramite_id AS ddjj_hist_id,
                t.evento_id_normativo AS evento_id,
                t.anio AS anio,
                t.fecha_inicio_evento AS fecha_evento,
                t.resolucion_label AS dto,
                ag.source_file AS source_file,
                ag.source_sheet AS source_sheet,
                'agricultura_perdida' AS dataset_role,
                'tramite_id' AS relation_type,
                ag.tramite_id AS iddj,
                a.adremas AS codigo,
                CAST(NULL AS CHAR(12)) AS solicitud_id,
                t.razon_social AS productor_nombre,
                t.cuit AS documento_nro,
                a.departamento AS departamento,
                a.localidad AS localidad,
                a.paraje AS paraje,
                'Agricultura' AS actividad,
                COALESCE(NULLIF(ag.producto, ''), NULLIF(ag.especie_cultivo, ''), NULLIF(ag.rubro, '')) AS cultivo,
                ag.especie_cultivo AS especie,
                ag.estado_cultivo_original AS categoria,
                CASE WHEN ag.apto_indicador_superficie THEN ag.superficie_sembrada ELSE NULL END AS superficie_sembrada_uso,
                CASE WHEN ag.apto_indicador_superficie THEN ag.superficie_afectada ELSE NULL END AS superficie_afectada,
                ag.produccion_estimada AS produccion_estimada,
                ag.produccion_obtenida AS produccion_obtenida,
                CASE WHEN ag.apto_indicador_superficie AND ag.superficie_sembrada > 0
                     THEN 100.0 * ag.superficie_afectada / ag.superficie_sembrada ELSE NULL END AS porcentaje_afectacion,
                CASE WHEN ag.apto_indicador_superficie
                           AND ag.superficie_afectada > ag.superficie_sembrada THEN 1 ELSE 0 END AS flag_agricola_afectada_mayor_uso,
                0 AS flag_superficie_total_menor_afectadas,
                CASE WHEN ag.apto_indicador_superficie THEN 0 ELSE 1 END AS flag_revision_manual,
                CASE WHEN ag.apto_indicador_superficie THEN 'sin_alerta' ELSE 'advertencia' END AS severidad_maxima,
                'ddjj_2023_excel' AS origen_dato
            FROM stg_ddjj_2023_agricultura ag
            JOIN stg_ddjj_2023_tramite t ON t.tramite_id = ag.tramite_id
            LEFT JOIN (""" + ADREMA_AGG + """) a ON a.tramite_id = ag.tramite_id
        """,
        "vw_all_cultivos": """
            SELECT
                SHA2(CONCAT_WS('|', 'ddjj_2023_excel', base.cultivo), 256) AS cultivo_all_id,
                CAST(NULL AS SIGNED) AS id_cultivo_actual,
                SHA2(CONCAT_WS('|', 'ddjj_2023_excel', base.cultivo), 256) AS cultivo_hist_id,
                base.cultivo AS cultivo,
                COUNT(*) AS registros,
                COUNT(DISTINCT base.tramite_id) AS eventos,
                'ddjj_2023_excel' AS origen_dato
            FROM (
                SELECT tramite_id,
                       COALESCE(NULLIF(producto, ''), NULLIF(especie_cultivo, ''), NULLIF(rubro, '')) AS cultivo
                FROM stg_ddjj_2023_agricultura
            ) base
            WHERE base.cultivo IS NOT NULL
            GROUP BY base.cultivo
        """,
        "vw_all_cultivostipo": """
            SELECT
                SHA2(CONCAT_WS('|', 'ddjj_2023_excel', base.cultivo_tipo), 256) AS cultivo_tipo_all_id,
                CAST(NULL AS SIGNED) AS id_cultivo_tipo_actual,
                SHA2(CONCAT_WS('|', 'ddjj_2023_excel', base.cultivo_tipo), 256) AS cultivo_tipo_hist_id,
                base.cultivo_tipo AS cultivo_tipo,
                COUNT(*) AS registros,
                COUNT(DISTINCT base.tramite_id) AS eventos,
                'ddjj_2023_excel' AS origen_dato
            FROM (
                SELECT tramite_id, COALESCE(NULLIF(rubro, ''), 'Agricultura') AS cultivo_tipo
                FROM stg_ddjj_2023_agricultura
            ) base
            GROUP BY base.cultivo_tipo
        """,
        "vw_all_ganaderia_resumen": """
            SELECT
                SHA2(CONCAT_WS('|', 'ddjj_2023_excel', g.ganaderia_id_2023), 256) AS ganaderia_all_id,
                g.ganaderia_id_2023 AS ganaderia_hist_id,
                CAST(NULL AS SIGNED) AS id_ddjj_actual,
                g.tramite_id AS ddjj_hist_id,
                t.evento_id_normativo AS evento_id,
                t.anio AS anio,
                t.fecha_inicio_evento AS fecha_evento,
                t.resolucion_label AS dto,
                g.source_file AS source_file,
                g.source_sheet AS source_sheet,
                'ganaderia_declarada' AS dataset_role,
                'tramite_id' AS relation_type,
                g.tramite_id AS iddj,
                a.adremas AS codigo,
                CAST(NULL AS CHAR(12)) AS solicitud_id,
                t.razon_social AS productor_nombre,
                t.cuit AS documento_nro,
                a.departamento AS departamento,
                a.localidad AS localidad,
                a.paraje AS paraje,
                'Ganadería' AS actividad,
                g.especie AS especie,
                COALESCE(NULLIF(g.categoria_normalizada_preliminar, ''), g.categoria_original) AS categoria,
                CAST(NULL AS DECIMAL(18,4)) AS superficie_total,
                CASE WHEN g.apto_indicador_superficie THEN g.superficie_uso ELSE NULL END AS superficie_ganadera_uso,
                CASE WHEN g.apto_indicador_superficie THEN g.superficie_afectada ELSE NULL END AS superficie_ganadera_afectada,
                CASE WHEN g.apto_indicador_cantidad THEN g.cantidad ELSE NULL END AS existencias,
                CASE WHEN g.apto_indicador_mortandad THEN g.mortandad ELSE NULL END AS mortandad,
                CASE WHEN g.apto_indicador_cantidad AND g.apto_indicador_mortandad AND g.cantidad > 0
                     THEN 100.0 * g.mortandad / g.cantidad ELSE NULL END AS porcentaje_afectacion_ganadera,
                0 AS flag_ganadera_afectada_mayor_uso,
                COALESCE(g.dq_mortandad_mayor_cantidad, 0) AS flag_mortandad_mayor_existencias,
                0 AS flag_superficie_total_menor_afectadas,
                CASE WHEN COALESCE(g.dq_mortandad_mayor_cantidad, 0) = 1
                           OR COALESCE(g.dq_cantidad_negativa, 0) = 1
                           OR COALESCE(g.dq_mortandad_negativa, 0) = 1
                           OR NOT g.apto_indicador_superficie THEN 1 ELSE 0 END AS flag_revision_manual,
                CASE WHEN COALESCE(g.dq_mortandad_mayor_cantidad, 0) = 1
                           OR COALESCE(g.dq_cantidad_negativa, 0) = 1
                           OR COALESCE(g.dq_mortandad_negativa, 0) = 1
                           OR NOT g.apto_indicador_superficie THEN 'advertencia'
                     ELSE 'sin_alerta' END AS severidad_maxima,
                'ddjj_2023_excel' AS origen_dato
            FROM stg_ddjj_2023_ganaderia g
            JOIN stg_ddjj_2023_tramite t ON t.tramite_id = g.tramite_id
            LEFT JOIN (""" + ADREMA_AGG + """) a ON a.tramite_id = g.tramite_id
        """,
    }


def view_definitions(engine) -> dict[str, str]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT TABLE_NAME, VIEW_DEFINITION
                FROM information_schema.VIEWS
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
    return {row.TABLE_NAME: row.VIEW_DEFINITION for row in rows}


def expected_counts(engine) -> dict[str, int]:
    queries = {
        "vw_all_resoluciones": "SELECT COUNT(DISTINCT evento_id_normativo) FROM stg_ddjj_2023_tramite",
        "vw_all_ddjj_personas": "SELECT COUNT(*) FROM stg_ddjj_2023_tramite",
        "vw_all_productores": "SELECT COUNT(DISTINCT productor_id_2023) FROM stg_ddjj_2023_tramite",
        "vw_all_tipoactividad": """
            SELECT (SELECT COUNT(*) > 0 FROM stg_ddjj_2023_agricultura)
                 + (SELECT COUNT(*) > 0 FROM stg_ddjj_2023_ganaderia)
        """,
        "vw_all_agricultura": "SELECT COUNT(*) FROM stg_ddjj_2023_agricultura",
        "vw_all_cultivos": """
            SELECT COUNT(DISTINCT COALESCE(NULLIF(producto, ''), NULLIF(especie_cultivo, ''), NULLIF(rubro, '')))
            FROM stg_ddjj_2023_agricultura
        """,
        "vw_all_cultivostipo": """
            SELECT COUNT(DISTINCT COALESCE(NULLIF(rubro, ''), 'Agricultura'))
            FROM stg_ddjj_2023_agricultura
        """,
        "vw_all_ganaderia_resumen": "SELECT COUNT(*) FROM stg_ddjj_2023_ganaderia",
    }
    with engine.connect() as connection:
        return {
            view: int(connection.execute(text(sql)).scalar() or 0)
            for view, sql in queries.items()
        }


def create_view(connection, name: str, definition: str) -> None:
    if name not in VIEWS and not any(name == f"{view}_test_ddjj_2023" for view in VIEWS):
        raise RuntimeError(f"Vista fuera de alcance: {name}")
    connection.execute(text(f"CREATE OR REPLACE VIEW `{name}` AS {definition}"))


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    engine = UPLOAD.make_engine()
    definitions = view_definitions(engine)
    missing = sorted(set(VIEWS) - set(definitions))
    if missing:
        engine.dispose()
        raise RuntimeError(f"Faltan vistas unificadas base: {', '.join(missing)}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = REPORT_DIR / f"unified_views_backup_before_ddjj_2023_{timestamp}.sql"
    backup_text = "\n\n".join(
        f"CREATE OR REPLACE VIEW `{view}` AS\n{definitions[view]};"
        for view in VIEWS
    )
    backup_path.write_text(backup_text + "\n", encoding="utf-8")
    print(f"Respaldo SQL: {backup_path}")

    branches = branch_sql()
    combined: dict[str, str] = {}
    for view in VIEWS:
        current = definitions[view].strip().rstrip(";")
        already_integrated = (
            "stg_ddjj_2023_" in current.casefold()
            or "ddjj_2023_excel" in current.casefold()
        )
        combined[view] = current if already_integrated else f"{current}\nUNION ALL\n{branches[view]}"

    expected = expected_counts(engine)
    test_results: list[tuple[str, int, int]] = []
    try:
        with engine.begin() as connection:
            for view in VIEWS:
                create_view(connection, f"{view}_test_ddjj_2023", combined[view])

        with engine.connect() as connection:
            for view in VIEWS:
                test_view = f"{view}_test_ddjj_2023"
                observed = int(
                    connection.execute(
                        text(
                            f"SELECT COUNT(*) FROM `{test_view}` "
                            "WHERE origen_dato = :origin"
                        ),
                        {"origin": ORIGIN},
                    ).scalar()
                )
                test_results.append((test_view, observed, expected[view]))
                if observed != expected[view]:
                    raise RuntimeError(
                        f"{test_view}: {observed} filas DDJJ 2023; "
                        f"se esperaban {expected[view]}."
                    )
            normative = int(
                connection.execute(
                    text(
                        """
                        SELECT COUNT(*) FROM vw_all_resoluciones_test_ddjj_2023
                        WHERE origen_dato = 'ddjj_2023_excel'
                          AND evento_id = 'DECRETO_2099_2023'
                          AND numero_resolucion = 'Decreto 2099/23'
                        """
                    )
                ).scalar()
            )
            if normative != 1:
                raise RuntimeError("La vista de prueba no expone Decreto 2099/23 correctamente.")

        replaced: list[str] = []
        try:
            with engine.begin() as connection:
                for view in VIEWS:
                    create_view(connection, view, combined[view])
                    replaced.append(view)
        except Exception:
            with engine.begin() as connection:
                for view in replaced:
                    create_view(connection, view, definitions[view])
            raise

        lines = [
            "# Creación de vistas unificadas con DDJJ 2023",
            "",
            f"- **Fecha:** {datetime.now().astimezone().isoformat(timespec='seconds')}",
            "- **Estado:** PASS",
            f"- **Respaldo:** `{backup_path.relative_to(PROJECT_ROOT).as_posix()}`",
            "- **Origen incorporado:** `ddjj_2023_excel`",
            "- **Norma:** Decreto 2099/23",
            "",
            "## Vistas de prueba",
            "",
            "| Vista | Filas observadas | Filas esperadas |",
            "|---|---:|---:|",
        ]
        lines.extend(
            f"| {view} | {observed} | {expected_rows} |"
            for view, observed, expected_rows in test_results
        )
        lines.extend(
            [
                "",
                "## Vistas operativas actualizadas",
                "",
                *[f"- `{view}`" for view in VIEWS],
                "",
                "Los valores cuantitativos ganaderos y de superficie no aptos se exponen como NULL; ",
                "las banderas de revisión permanecen disponibles.",
            ]
        )
        RESULT_PATH.write_text("\n".join(lines), encoding="utf-8")
        print("Vistas de prueba: PASS")
        print("Vistas unificadas actualizadas: PASS")
        print(f"Resultado: {RESULT_PATH}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
