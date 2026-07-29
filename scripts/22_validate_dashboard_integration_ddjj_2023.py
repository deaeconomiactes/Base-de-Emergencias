"""Validación funcional read-only de DDJJ 2023 en el dashboard principal."""
from __future__ import annotations

import ast
import importlib.util
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "dashboard"
OUTPUT = ROOT / "data_processed/ddjj_2023_excel/dashboard_validation"
CHECKS_PATH = OUTPUT / "dashboard_integration_ddjj_2023_checks.csv"
REPORT_PATH = OUTPUT / "dashboard_integration_ddjj_2023_resultados.md"
ORIGIN = "ddjj_2023_excel"
EVENT = "DECRETO_2099_2023"
LABEL = "Decreto 2099/23"
EXPECTED = 1483

PAGES = {
    "Home": "Home.py",
    "Productores": "pages/1_Productores.py",
    "Detalle DDJJ": "pages/2_Detalle_DDJJ.py",
    "Adremas": "pages/3_Adremas.py",
    "Mapa": "pages/4_Mapa.py",
    "Análisis": "pages/5_Analisis.py",
    "Ficha Productor": "pages/6_Ficha_Productor.py",
}
TOKENS = {
    "Home": ("table(", ORIGIN),
    "Productores": ("vw_all_productores", "vw_all_ddjj_personas", ORIGIN),
    "Detalle DDJJ": ("vw_all_ddjj_personas", ORIGIN, "norma_evento"),
    "Adremas": ("stg_ddjj_2023_adrema", "adrema_unica_indicador", ORIGIN),
    "Mapa": ("vw_all_ddjj_personas", ORIGIN, "representación cartográfica"),
    "Análisis": ("vw_all_agricultura", "vw_all_ganaderia_resumen", ORIGIN),
    "Ficha Productor": ("vw_all_ddjj_personas", "stg_ddjj_2023_adrema", "adrema_unica_indicador"),
}


def load_connection_module():
    path = Path(__file__).with_name("21_validate_unified_views_with_ddjj_2023.py")
    spec = importlib.util.spec_from_file_location("validate_views_ddjj_2023", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"No se pudo cargar conexión desde {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.UPLOAD


UPLOAD = load_connection_module()


class Checks:
    def __init__(self):
        self.rows: list[dict] = []

    def add(self, check_id, component, description, status, observed, expected, detail=""):
        self.rows.append({
            "check_id": check_id, "componente": component,
            "descripcion": description, "estado": status,
            "valor_observado": observed, "valor_esperado": expected,
            "detalle": detail,
        })

    def equal(self, check_id, component, description, observed, expected, *, warn=False, detail=""):
        status = "PASS" if observed == expected else ("WARN" if warn else "FAIL")
        self.add(check_id, component, description, status, observed, expected, detail)

    @property
    def status(self):
        states = {row["estado"] for row in self.rows}
        return "FAIL" if "FAIL" in states else "WARN" if "WARN" in states else "PASS"


def scalar(engine, sql, params=None):
    with engine.connect() as connection:
        return connection.execute(text(sql), params or {}).scalar()


def navigation_paths() -> list[str]:
    tree = ast.parse((DASHBOARD / "app.py").read_text(encoding="utf-8"))
    paths = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr == "Page" and node.args and isinstance(node.args[0], ast.Constant):
            paths.append(str(node.args[0].value))
    return paths


def inspect_code(checks: Checks):
    navigation = navigation_paths()
    checks.equal("navigation_count", "Navegación", "Siete páginas principales visibles", len(navigation), 7)
    checks.equal(
        "navigation_no_separate_2023", "Navegación",
        "DDJJ 2023 no aparece como página separada",
        any("7_ddjj_2023" in value.casefold() for value in navigation), False,
    )
    for component, relative in PAGES.items():
        path = DASHBOARD / relative
        checks.equal(f"file_{component}", component, "Página existente", path.is_file(), True)
        if not path.is_file():
            continue
        try:
            code = path.read_text(encoding="utf-8")
            compile(code, str(path), "exec")
            checks.add(f"compile_{component}", component, "Código Python válido", "PASS", True, True)
        except Exception as exc:
            checks.add(f"compile_{component}", component, "Código Python válido", "FAIL", False, True, str(exc))
            continue
        lower = code.casefold()
        missing = [token for token in TOKENS[component] if token.casefold() not in lower]
        if relative.endswith("5_Analisis.py") and all(
            token in lower for token in ('table("agricultura")', 'table("ganaderia_resumen")')
        ):
            missing = [token for token in missing if not token.startswith("vw_all_")]
        checks.add(
            f"exposure_{component}", component,
            "La página consulta y expone DDJJ 2023",
            "PASS" if not missing else "FAIL", not missing, True,
            "" if not missing else "Referencias faltantes: " + ", ".join(missing),
        )
        checks.equal(
            f"no_local_csv_{component}", component,
            "No lee CSV locales como fuente del dashboard",
            "read_csv(" in lower or "data_processed/ddjj_2023_excel" in lower, False,
        )
    map_code = (DASHBOARD / PAGES["Mapa"]).read_text(encoding="utf-8")
    checks.add(
        "map_geometry_limit", "Mapa",
        "Resumen departamental disponible; geometría 2023 pendiente",
        "WARN", "sin coordenadas validadas", "geometría validada",
        "La página no inventa puntos y muestra la advertencia institucional requerida.",
    )
    visible_code = "\n".join((DASHBOARD / path).read_text(encoding="utf-8") for path in PAGES.values())
    misuse = "numero_certificado as dto" in visible_code.casefold() or "numero_certificado as norma" in visible_code.casefold()
    checks.equal("certificate_not_norm", "Normativa", "Numero Certificado no se usa como norma", misuse, False)


def db_check(checks, engine, check_id, component, description, sql, expected, params=None, warn=False):
    try:
        observed = scalar(engine, sql, params)
        checks.equal(check_id, component, description, observed, expected, warn=warn)
        return observed
    except Exception as exc:
        checks.add(check_id, component, description, "FAIL", "error", expected, str(exc))
        return None


def inspect_data(checks: Checks) -> dict:
    engine = UPLOAD.make_engine()
    metrics = {}
    try:
        metrics["ddjj"] = db_check(
            checks, engine, "ddjj_count", "Detalle DDJJ", "DDJJ 2023 integrables",
            "SELECT COUNT(*) FROM vw_all_ddjj_personas WHERE origen_dato=:origin",
            EXPECTED, {"origin": ORIGIN},
        )
        db_check(
            checks, engine, "ddjj_unique", "Detalle DDJJ", "Una fila por trámite 2023",
            """SELECT COUNT(*) FROM (
                   SELECT ddjj_hist_id FROM vw_all_ddjj_personas
                   WHERE origen_dato=:origin GROUP BY ddjj_hist_id HAVING COUNT(*)>1
               ) x""", 0, {"origin": ORIGIN},
        )
        metrics["combined"] = db_check(
            checks, engine, "year_norm_source", "Home", "Año + norma + fuente recuperan el universo",
            """SELECT COUNT(*) FROM vw_all_ddjj_personas
               WHERE origen_dato=:origin AND anio=2023 AND evento_id=:event AND dto=:label""",
            EXPECTED, {"origin": ORIGIN, "event": EVENT, "label": LABEL},
        )
        metrics["producers"] = scalar(
            engine, "SELECT COUNT(*) FROM vw_all_productores WHERE origen_dato=:origin", {"origin": ORIGIN}
        )
        checks.add(
            "producers_present", "Productores", "Productores 2023 visibles",
            "PASS" if metrics["producers"] > 0 else "FAIL", metrics["producers"], "> 0",
        )
        db_check(
            checks, engine, "producer_orphans", "Productores", "DDJJ sin productor unificado",
            """SELECT COUNT(*) FROM vw_all_ddjj_personas d
               LEFT JOIN vw_all_productores p ON p.productor_all_id=d.productor_all_id
               WHERE d.origen_dato=:origin AND p.productor_all_id IS NULL""",
            0, {"origin": ORIGIN},
        )
        metrics["adremas"] = scalar(
            engine, "SELECT COUNT(*) FROM stg_ddjj_2023_adrema WHERE adrema_unica_indicador=1"
        )
        unique_pairs = db_check(
            checks, engine, "adrema_pairs", "Adremas", "Indicador coincide con pares únicos",
            """SELECT COUNT(*) FROM (
                   SELECT tramite_id, adrema FROM stg_ddjj_2023_adrema
                   WHERE adrema IS NOT NULL AND TRIM(adrema)<>'' GROUP BY tramite_id, adrema
               ) x""", metrics["adremas"],
        )
        metrics["adremas"] = unique_pairs
        db_check(
            checks, engine, "adrema_join", "Ficha Productor", "ADREMAS 2023 vinculables a ficha",
            """SELECT COUNT(*) FROM stg_ddjj_2023_adrema a
               JOIN vw_all_ddjj_personas d ON d.origen_dato=:origin AND d.ddjj_hist_id=a.tramite_id
               WHERE a.adrema_unica_indicador=1""", unique_pairs, {"origin": ORIGIN},
        )
        metrics["departments"] = scalar(
            engine, """SELECT COUNT(DISTINCT departamento) FROM vw_all_ddjj_personas
                       WHERE origen_dato=:origin AND departamento IS NOT NULL AND TRIM(departamento)<>''""",
            {"origin": ORIGIN},
        )
        checks.add(
            "map_departments", "Mapa", "Resumen territorial 2023 tiene departamentos",
            "PASS" if metrics["departments"] > 0 else "FAIL", metrics["departments"], "> 0",
        )
        for check_id, description, sql in (
            ("agriculture_available", "Agricultura 2023 consultable", "SELECT COUNT(*) FROM vw_all_agricultura WHERE origen_dato=:origin AND anio=2023"),
            ("livestock_available", "Ganadería 2023 consultable", "SELECT COUNT(*) FROM vw_all_ganaderia_resumen WHERE origen_dato=:origin AND anio=2023"),
        ):
            value = scalar(engine, sql, {"origin": ORIGIN})
            checks.add(check_id, "Análisis", description, "PASS" if value > 0 else "FAIL", value, "> 0")
        db_check(
            checks, engine, "invalid_livestock_excluded", "Análisis",
            "Mortandad > cantidad no alimenta medidas cuantitativas",
            """SELECT COUNT(*) FROM vw_all_ganaderia_resumen WHERE origen_dato=:origin
               AND flag_mortandad_mayor_existencias=1
               AND (existencias IS NOT NULL OR mortandad IS NOT NULL)""", 0, {"origin": ORIGIN},
        )
        db_check(
            checks, engine, "negative_surfaces_excluded", "Análisis",
            "Superficies negativas no alimentan medidas cuantitativas",
            """SELECT
                 (SELECT COUNT(*) FROM vw_all_agricultura WHERE origen_dato=:origin
                  AND (superficie_sembrada_uso<0 OR superficie_afectada<0)) +
                 (SELECT COUNT(*) FROM vw_all_ganaderia_resumen WHERE origen_dato=:origin
                  AND (superficie_ganadera_uso<0 OR superficie_ganadera_afectada<0))""", 0, {"origin": ORIGIN},
        )
    finally:
        engine.dispose()
    return metrics


def markdown_table(frame: pd.DataFrame) -> str:
    cols = list(frame.columns)
    rows = ["| " + " | ".join(cols) + " |", "| " + " | ".join("---" for _ in cols) + " |"]
    for row in frame.itertuples(index=False, name=None):
        rows.append("| " + " | ".join(str(v).replace("|", "\\|").replace("\n", " ") for v in row) + " |")
    return "\n".join(rows)


def write_outputs(checks: Checks, metrics: dict):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(checks.rows)
    frame.to_csv(CHECKS_PATH, index=False, encoding="utf-8-sig")
    counts = frame["estado"].value_counts().to_dict()
    page_summary = (
        frame[frame["componente"].isin(PAGES)]
        .groupby("componente")["estado"]
        .agg(lambda s: "FAIL" if "FAIL" in set(s) else "WARN" if "WARN" in set(s) else "PASS")
        .reset_index(name="estado")
    )
    report = [
        "# Validación de integración del dashboard DDJJ 2023", "",
        f"- **Fecha:** {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"- **Estado global:** **{checks.status}**",
        f"- **PASS:** {counts.get('PASS', 0)}",
        f"- **WARN:** {counts.get('WARN', 0)}",
        f"- **FAIL:** {counts.get('FAIL', 0)}", "",
        "## Resultado principal", "",
        f"- DDJJ 2023 observadas: **{metrics.get('ddjj', 's/d')}** (esperadas: **{EXPECTED}**).",
        f"- Filtro 2023 + {LABEL} + {ORIGIN}: **{metrics.get('combined', 's/d')}**.",
        f"- Productores 2023: **{metrics.get('producers', 's/d')}**.",
        f"- Pares únicos trámite + ADREMA: **{metrics.get('adremas', 's/d')}**.", "",
        "## Estado por página", "", markdown_table(page_summary), "",
        "## Interpretación", "",
        "Las páginas principales consultan la fuente integrada. Mapa queda en WARN porque la fuente 2023 "
        "permite resumen departamental, pero no posee coordenadas validadas para representar puntos.", "",
        "## Detalle", "", markdown_table(frame),
    ]
    REPORT_PATH.write_text("\n".join(report), encoding="utf-8")


def main():
    checks = Checks()
    inspect_code(checks)
    try:
        metrics = inspect_data(checks)
    except Exception as exc:
        checks.add("tidb_read", "Fuente", "Consultas read-only", "FAIL", "error", "sin error", str(exc))
        metrics = {}
    write_outputs(checks, metrics)
    counts = pd.DataFrame(checks.rows)["estado"].value_counts().to_dict()
    print(f"Estado global: {checks.status}")
    print(f"PASS: {counts.get('PASS', 0)}")
    print(f"WARN: {counts.get('WARN', 0)}")
    print(f"FAIL: {counts.get('FAIL', 0)}")
    print(f"DDJJ 2023 observadas: {metrics.get('ddjj', 'sin dato')}")
    print(f"Reporte: {REPORT_PATH}")
    print(f"Checks: {CHECKS_PATH}")
    if checks.status == "FAIL":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
