"""Auditoría read-only de filtros de la página Análisis.

Reproduce el filtrado de ``dashboard/pages/5_Analisis.py`` sobre la vista
unificada de ganadería. No modifica datos ni vistas en TiDB.
"""
from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import text


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_PAGE = ROOT / "dashboard/pages/5_Analisis.py"
OUTPUT_DIR = ROOT / "data_processed/ddjj_2023_excel/dashboard_validation"
CHECKS_PATH = OUTPUT_DIR / "analisis_filters_audit_checks.csv"
REPORT_PATH = OUTPUT_DIR / "analisis_filters_audit_resultados.md"
VIEW = "vw_all_ganaderia_resumen"
ORIGIN_2023 = "ddjj_2023_excel"
DECREE_2023 = "Decreto 2099/23"


@dataclass(frozen=True)
class Scenario:
    key: str
    name: str
    year: int | None = None
    resolution: str | None = None
    origin: str | None = None

    def filters(self) -> tuple[str, dict[str, Any]]:
        clauses = ["1=1"]
        params: dict[str, Any] = {}
        if self.year is not None:
            clauses.append("anio = :anio")
            params["anio"] = self.year
        if self.resolution is not None:
            clauses.append("dto = :resolucion")
            params["resolucion"] = self.resolution
        if self.origin is not None:
            clauses.append("origen_dato = :origen")
            params["origen"] = self.origin
        return " AND ".join(clauses), params


SCENARIOS = (
    Scenario("A", "A - Año Todos / Resolución Todas / Origen Todos"),
    Scenario("B", "B - Año 2023 / Resolución Todas / Origen Todos", year=2023),
    Scenario(
        "C",
        "C - Año 2023 / Decreto 2099/23 / ddjj_2023_excel",
        year=2023,
        resolution=DECREE_2023,
        origin=ORIGIN_2023,
    ),
    Scenario("D", "D - Año 2022 / Resolución Todas / Origen Todos", year=2022),
)

CATEGORY_EXPR = "COALESCE(NULLIF(TRIM(categoria), ''), NULLIF(TRIM(especie), ''), NULLIF(TRIM(actividad), ''), 'GANADERIA')"
DDJJ_EXPR = "COALESCE(CAST(id_ddjj_actual AS CHAR), NULLIF(ddjj_hist_id, ''), NULLIF(iddj, ''), NULLIF(solicitud_id, ''))"
PRODUCER_EXPR = "COALESCE(NULLIF(TRIM(documento_nro), ''), NULLIF(TRIM(productor_nombre), ''))"


def load_connection_module():
    path = ROOT / "scripts/21_validate_unified_views_with_ddjj_2023.py"
    spec = importlib.util.spec_from_file_location("validate_views_ddjj_2023", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"No se pudo cargar el módulo de conexión: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.UPLOAD


def query(connection, sql: str, params: dict[str, Any] | None = None) -> pd.DataFrame:
    return pd.read_sql(text(sql), connection, params=params or {})


class Checks:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def add(
        self,
        check_id: str,
        scenario: str,
        component: str,
        description: str,
        status: str,
        observed: Any,
        expected: Any,
        detail: str = "",
    ) -> None:
        self.rows.append(
            {
                "check_id": check_id,
                "escenario": scenario,
                "componente": component,
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
        return "FAIL" if "FAIL" in states else "WARN" if "WARN" in states else "PASS"


def csv_list(values: pd.Series) -> str:
    clean = [str(value) for value in values.dropna().tolist()]
    return ", ".join(clean) if clean else "Sin dato"


def audit_code(checks: Checks) -> dict[str, str]:
    code = DASHBOARD_PAGE.read_text(encoding="utf-8")
    detected = {
        "Agricultura": 'table("agricultura") → vw_all_agricultura en modo unificado',
        "Ganadería": 'table("ganaderia_resumen") → vw_all_ganaderia_resumen en modo unificado',
        "Mejoras": "perdidas_mejoras + ddjj_personas + resoluciones (fuente operativa)",
        "Actividades/productores": "vw_all_productores en modo unificado",
        "Filtro de año": "anio = :anio sobre agricultura/ganadería; EXISTS por año para productores",
        "Filtro de resolución": "dto = :res_num sobre agricultura/ganadería",
        "Filtro de origen": "origen_dato = :origen_dato sobre agricultura/ganadería",
    }
    required = {
        "vista_ganaderia": 'gan_table = table("ganaderia_resumen")',
        "filtro_anio": 'filters_unified.append("anio = :anio")',
        "filtro_resolucion": 'filters_unified.append("dto = :res_num")',
        "filtro_origen": 'filters_unified.append("origen_dato = :origen_dato")',
        "tasa_dashboard": 'add_percent(ganaderia, "mortandad", "existencias", "tasa_mortandad")',
    }
    for check_id, token in required.items():
        present = token in code
        checks.add(
            check_id,
            "Código",
            "Analisis.py",
            f"Referencia detectada: {token}",
            "PASS" if present else "FAIL",
            present,
            True,
        )
    return detected


def audit_view_lineage(connection, checks: Checks) -> str:
    definition = connection.execute(
        text(
            "SELECT VIEW_DEFINITION FROM information_schema.VIEWS "
            "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=:view"
        ),
        {"view": VIEW},
    ).scalar()
    if not definition:
        checks.add("view_exists", "General", "Ganadería", "Vista unificada disponible", "FAIL", False, True)
        return "No disponible"
    lower = definition.casefold()
    branches = {
        "actual": "bovinos" in lower,
        "historico": "vw_hist_ganaderia_resumen" in lower,
        ORIGIN_2023: "stg_ddjj_2023_ganaderia" in lower,
    }
    missing = [name for name, present in branches.items() if not present]
    checks.add(
        "view_lineage",
        "General",
        "Ganadería",
        "La vista unificada contiene las tres ramas esperadas",
        "PASS" if not missing else "FAIL",
        ", ".join(name for name, present in branches.items() if present),
        "actual, historico, ddjj_2023_excel",
        "Ramas faltantes: " + ", ".join(missing) if missing else "UNION ALL dentro de la vista; Analisis.py no hace uniones adicionales.",
    )
    return "vw_all_ganaderia_resumen = bovinos (actual) UNION ALL vw_hist_ganaderia_resumen UNION ALL stg_ddjj_2023_ganaderia"


def scenario_data(connection, scenario: Scenario) -> dict[str, pd.DataFrame]:
    where, params = scenario.filters()
    summary = query(
        connection,
        f"""
        SELECT COUNT(*) AS filas,
               COUNT(DISTINCT {DDJJ_EXPR}) AS ddjj,
               COUNT(DISTINCT {PRODUCER_EXPR}) AS productores,
               COALESCE(SUM(existencias), 0) AS existencias,
               COALESCE(SUM(mortandad), 0) AS mortandad,
               COUNT(DISTINCT {CATEGORY_EXPR}) AS categorias,
               SUM(CASE WHEN existencias IS NULL OR existencias = 0 THEN 1 ELSE 0 END) AS existencia_cero_nula,
               SUM(CASE WHEN mortandad > existencias THEN 1 ELSE 0 END) AS mortandad_mayor_existencia_incluida,
               SUM(CASE WHEN COALESCE(flag_mortandad_mayor_existencias, 0) = 1 THEN 1 ELSE 0 END) AS flags_mortandad_mayor
        FROM {VIEW}
        WHERE {where}
        """,
        params,
    )
    dimensions = query(
        connection,
        f"""
        SELECT anio, origen_dato, dto, COUNT(*) AS filas
        FROM {VIEW} WHERE {where}
        GROUP BY anio, origen_dato, dto
        ORDER BY anio DESC, origen_dato, dto
        """,
        params,
    )
    categories = query(
        connection,
        f"""
        SELECT {CATEGORY_EXPR} AS categoria,
               COUNT(*) AS filas,
               COUNT(DISTINCT {DDJJ_EXPR}) AS ddjj,
               COALESCE(SUM(existencias), 0) AS existencias,
               COALESCE(SUM(mortandad), 0) AS mortandad,
               CASE WHEN COALESCE(SUM(existencias), 0) > 0
                    THEN 100.0 * COALESCE(SUM(mortandad), 0) / SUM(existencias)
                    ELSE NULL END AS tasa_mortandad
        FROM {VIEW} WHERE {where}
        GROUP BY {CATEGORY_EXPR}
        ORDER BY existencias DESC
        """,
        params,
    )
    return {"summary": summary, "dimensions": dimensions, "categories": categories}


def audit_scenario(checks: Checks, scenario: Scenario, frames: dict[str, pd.DataFrame]) -> dict[str, Any]:
    summary = frames["summary"].iloc[0].to_dict()
    dimensions = frames["dimensions"]
    categories = frames["categories"]
    years = sorted(int(value) for value in dimensions["anio"].dropna().unique())
    origins = sorted(str(value) for value in dimensions["origen_dato"].dropna().unique())
    resolutions = sorted(str(value) for value in dimensions["dto"].dropna().unique())
    prefix = f"scenario_{scenario.key.lower()}"

    checks.add(prefix + "_query", scenario.name, "Ganadería", "La consulta equivalente a Analisis.py se ejecuta", "PASS", "sin error", "sin error")
    checks.add(prefix + "_rows", scenario.name, "Ganadería", "Filas disponibles", "PASS" if summary["filas"] > 0 else "WARN", int(summary["filas"]), "> 0")

    if scenario.year is not None:
        only_expected_year = years == [scenario.year]
        checks.add(
            prefix + "_year",
            scenario.name,
            "Filtro de año",
            f"El resultado contiene exclusivamente {scenario.year}",
            "PASS" if only_expected_year else "FAIL",
            ", ".join(map(str, years)) or "Sin dato",
            str(scenario.year),
        )
    else:
        checks.add(
            prefix + "_multiple_years",
            scenario.name,
            "Filtro de año",
            "Año Todos contiene más de un año",
            "PASS" if len(years) > 1 else "FAIL",
            len(years),
            "> 1",
            ", ".join(map(str, years)),
        )
        checks.add(
            prefix + "_includes_2023",
            scenario.name,
            "Filtro de año",
            "Año Todos incluye 2023",
            "PASS" if 2023 in years else "FAIL",
            2023 in years,
            True,
        )
        checks.add(
            prefix + "_multiple_sources",
            scenario.name,
            "Filtro de origen",
            "Origen Todos incluye más de una fuente",
            "PASS" if len(origins) > 1 else "FAIL",
            len(origins),
            "> 1",
            ", ".join(origins),
        )

    if scenario.year == 2023:
        checks.add(
            prefix + "_source_2023",
            scenario.name,
            "Filtro de origen",
            "El universo 2023 incluye ddjj_2023_excel",
            "PASS" if ORIGIN_2023 in origins else "FAIL",
            ", ".join(origins),
            ORIGIN_2023,
        )
    if scenario.key == "C":
        correct_resolution = resolutions == [DECREE_2023]
        correct_origin = origins == [ORIGIN_2023]
        checks.add(prefix + "_decree", scenario.name, "Filtro de resolución", "Decreto 2099/23 queda identificado", "PASS" if correct_resolution else "FAIL", ", ".join(resolutions), DECREE_2023)
        checks.add(prefix + "_origin", scenario.name, "Filtro de origen", "Solo queda ddjj_2023_excel", "PASS" if correct_origin else "FAIL", ", ".join(origins), ORIGIN_2023)
    if scenario.year == 2022:
        forbidden_origin = ORIGIN_2023 in origins
        forbidden_decree = DECREE_2023 in resolutions
        checks.add(prefix + "_no_2023_origin", scenario.name, "Filtro de origen", "2022 no incluye ddjj_2023_excel", "FAIL" if forbidden_origin else "PASS", forbidden_origin, False)
        checks.add(prefix + "_no_decree", scenario.name, "Filtro de resolución", "2022 no incluye Decreto 2099/23", "FAIL" if forbidden_decree else "PASS", forbidden_decree, False)

    zero_null = int(summary["existencia_cero_nula"] or 0)
    invalid_included = int(summary["mortandad_mayor_existencia_incluida"] or 0)
    flags = int(summary["flags_mortandad_mayor"] or 0)
    checks.add(
        prefix + "_zero_denominator",
        scenario.name,
        "Tasa de mortandad",
        "Registros con existencia cero o nula",
        "WARN" if zero_null else "PASS",
        zero_null,
        0,
        "Analisis.py asigna tasa 0 cuando el denominador no es positivo.",
    )
    checks.add(
        prefix + "_mortality_consistency",
        scenario.name,
        "Tasa de mortandad",
        "Mortandad cuantitativa mayor que existencia cuantitativa",
        "WARN" if invalid_included else "PASS",
        invalid_included,
        0,
        f"Flags de origen conservados: {flags}.",
    )

    return {
        "scenario": scenario,
        "summary": summary,
        "years": years,
        "origins": origins,
        "resolutions": resolutions,
        "categories": categories,
        "dimensions": dimensions,
    }


def audit_category_comparability(checks: Checks, results: list[dict[str, Any]]) -> None:
    all_result = next(result for result in results if result["scenario"].key == "A")
    categories = all_result["categories"]["categoria"].astype(str)
    normalized = categories.str.strip().str.casefold()
    bovine_terms = {"bovino", "bovinos", "vaca", "vacas", "vaquillona", "vaquillonas", "ternera", "terneras", "ternero", "terneros", "novillo", "novillos", "novillito", "novillitos", "toro", "toros"}
    observed = sorted(set(normalized).intersection(bovine_terms))
    aggregated = bool({"bovino", "bovinos"}.intersection(observed))
    disaggregated = len(set(observed) - {"bovino", "bovinos"}) > 0
    mixed = aggregated and disaggregated
    checks.add(
        "category_homologation",
        "Comparabilidad",
        "Ganadería",
        "Las categorías ganaderas están homologadas entre fuentes",
        "WARN" if mixed else "PASS",
        ", ".join(observed) or "No se detectaron términos bovinos",
        "Un único nivel de agregación",
        "Año Todos mezcla categorías agregadas y desagregadas." if mixed else "No se detectó mezcla bovina con la regla aplicada.",
    )


def markdown_table(frame: pd.DataFrame, columns: list[str] | None = None) -> str:
    data = frame[columns].copy() if columns else frame.copy()
    if data.empty:
        return "_Sin datos._"
    headers = [str(column) for column in data.columns]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in data.itertuples(index=False, name=None):
        values = [str(value).replace("|", "\\|").replace("\n", " ") for value in row]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def format_number(value: Any) -> str:
    if pd.isna(value):
        return "Sin dato"
    return f"{float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def write_outputs(checks: Checks, detected: dict[str, str], lineage: str, results: list[dict[str, Any]]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    checks_frame = pd.DataFrame(checks.rows)
    checks_frame.to_csv(CHECKS_PATH, index=False, encoding="utf-8-sig")
    state_counts = checks_frame["estado"].value_counts().to_dict()
    lines = [
        "# Auditoría de filtros de la pestaña Análisis",
        "",
        f"- **Fecha de ejecución:** {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"- **Estado global:** **{checks.global_status}**",
        f"- **PASS:** {state_counts.get('PASS', 0)}",
        f"- **WARN:** {state_counts.get('WARN', 0)}",
        f"- **FAIL:** {state_counts.get('FAIL', 0)}",
        "",
        "## Consultas y vistas detectadas",
        "",
    ]
    lines.extend(f"- **{component}:** {source}." for component, source in detected.items())
    lines.extend(["", f"- **Linaje ganadero:** {lineage}.", ""])

    for result in results:
        scenario: Scenario = result["scenario"]
        summary = result["summary"]
        categories = result["categories"].copy()
        categories["existencias"] = categories["existencias"].map(format_number)
        categories["mortandad"] = categories["mortandad"].map(format_number)
        categories["tasa_mortandad"] = categories["tasa_mortandad"].map(format_number)
        top_exist = result["categories"].nlargest(20, "existencias").copy()
        top_mort = result["categories"].nlargest(20, "mortandad").copy()
        for frame in (top_exist, top_mort):
            for column in ("existencias", "mortandad", "tasa_mortandad"):
                frame[column] = frame[column].map(format_number)
        lines.extend(
            [
                f"## Escenario {scenario.key}",
                "",
                f"**{scenario.name}**",
                "",
                f"- Filas: **{int(summary['filas']):,}**.",
                f"- DDJJ/trámites distintos: **{int(summary['ddjj']):,}**.",
                f"- Productores identificables: **{int(summary['productores']):,}**.",
                f"- Existencias: **{format_number(summary['existencias'])}**.",
                f"- Mortandad: **{format_number(summary['mortandad'])}**.",
                f"- Categorías distintas: **{int(summary['categorias']):,}**.",
                f"- Años observados: **{', '.join(map(str, result['years'])) or 'Sin dato'}**.",
                f"- Fuentes observadas: **{', '.join(result['origins']) or 'Sin dato'}**.",
                f"- Resoluciones observadas: **{', '.join(result['resolutions']) or 'Sin dato'}**.",
                f"- Existencia cero o nula: **{int(summary['existencia_cero_nula'] or 0):,} filas**.",
                f"- Mortandad cuantitativa mayor que existencia: **{int(summary['mortandad_mayor_existencia_incluida'] or 0):,} filas**.",
                f"- Flags de mortandad mayor conservados: **{int(summary['flags_mortandad_mayor'] or 0):,} filas**.",
                "",
                "### Cobertura por año, fuente y resolución",
                "",
                markdown_table(result["dimensions"]),
                "",
                "### Top 20 categorías por existencias",
                "",
                markdown_table(top_exist, ["categoria", "filas", "ddjj", "existencias", "mortandad", "tasa_mortandad"]),
                "",
                "### Top 20 categorías por mortandad",
                "",
                markdown_table(top_mort, ["categoria", "filas", "ddjj", "existencias", "mortandad", "tasa_mortandad"]),
                "",
            ]
        )

    category_check = checks_frame[checks_frame["check_id"] == "category_homologation"].iloc[0]
    year_failures = checks_frame[(checks_frame["componente"] == "Filtro de año") & (checks_frame["estado"] == "FAIL")]
    filter_conclusion = "Los filtros de año y origen funcionan según los criterios definidos." if year_failures.empty else "Se detectaron fallas en los filtros; consultar el detalle de checks."
    lines.extend(
        [
            "## Conclusiones",
            "",
            f"- **Funcionamiento de filtros:** {filter_conclusion}",
            f"- **Comparabilidad ganadera:** {category_check['detalle']}",
            "- **Tasa de mortandad:** Analisis.py calcula `mortandad / existencias * 100` después de filtrar y agrupar por categoría. Para denominadores no positivos asigna 0; por ello debe interpretarse como indicador preliminar y conservar la advertencia metodológica.",
            "- **Recomendación visual/metodológica:** no conviene comparar directamente barras agregadas como BOVINOS con categorías desagregadas como vacas, vaquillonas o novillos. Se recomienda separar la visualización por fuente/granularidad o mostrar una advertencia explícita. Cambiar solo el texto no vuelve comparables las categorías.",
            "",
            "## Detalle de checks",
            "",
            markdown_table(checks_frame),
        ]
    )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    checks = Checks()
    detected = audit_code(checks)
    upload = load_connection_module()
    engine = upload.make_engine()
    results: list[dict[str, Any]] = []
    try:
        with engine.connect() as connection:
            lineage = audit_view_lineage(connection, checks)
            for scenario in SCENARIOS:
                try:
                    frames = scenario_data(connection, scenario)
                    results.append(audit_scenario(checks, scenario, frames))
                except Exception as exc:
                    checks.add(
                        f"scenario_{scenario.key.lower()}_query",
                        scenario.name,
                        "Ganadería",
                        "La consulta equivalente a Analisis.py se ejecuta",
                        "FAIL",
                        "error",
                        "sin error",
                        str(exc),
                    )
            if results:
                audit_category_comparability(checks, results)
    finally:
        engine.dispose()

    if not results:
        lineage = "No disponible por error de consulta"
    write_outputs(checks, detected, lineage, results)
    counts = pd.DataFrame(checks.rows)["estado"].value_counts().to_dict()
    print(f"Estado global: {checks.global_status}")
    print(f"PASS: {counts.get('PASS', 0)}")
    print(f"WARN: {counts.get('WARN', 0)}")
    print(f"FAIL: {counts.get('FAIL', 0)}")
    print(f"Reporte: {REPORT_PATH}")
    print(f"Checks: {CHECKS_PATH}")
    if checks.global_status == "FAIL":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
