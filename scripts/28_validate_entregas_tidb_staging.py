"""Valida las dos tablas staging de entregas cargadas en TiDB."""
from __future__ import annotations

import importlib.util
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = PROJECT_ROOT / "data_processed" / "entregas" / "tidb_staging"
REPORT_CSV = REPORT_DIR / "validation_entregas_tidb_staging_checks.csv"
REPORT_MD = REPORT_DIR / "validation_entregas_tidb_staging_resultados.md"

EXPECTED_YEARS = {2022: 8_457, 2023: 892, 2024: 2_241, 2025: 2_778}
EXPECTED_PROVIDERS = {
    "Sin dato": 8_457, "Prieto": 4_710, "Kofman": 784,
    "Fitosan": 402, "Borderes": 15,
}
EXPECTED_QUALITY = {"alta": 14_147, "media": 219, "baja": 2, "pendiente": 0}


def load_upload_module():
    path = Path(__file__).with_name("27_upload_entregas_to_tidb_staging.py")
    spec = importlib.util.spec_from_file_location("upload_entregas_tidb", path)
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

    def add(self, check_id: str, category: str, description: str, status: str, observed, expected, detail: str = "") -> None:
        self.rows.append({
            "check_id": check_id, "categoria": category, "descripcion": description,
            "estado": status, "valor_observado": observed,
            "valor_esperado": expected, "detalle": detail,
        })

    def compare(self, check_id: str, category: str, description: str, observed, expected, mismatch: str = "FAIL", detail: str = "") -> None:
        self.add(
            check_id, category, description, "PASS" if observed == expected else mismatch,
            observed, expected, detail,
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


def query(engine: Engine, sql: str, params: dict | None = None) -> pd.DataFrame:
    with engine.connect() as connection:
        return pd.read_sql(text(sql), connection, params=params or {})


def table_exists(engine: Engine, table_name: str) -> bool:
    return bool(scalar(
        engine,
        """SELECT COUNT(*) FROM information_schema.TABLES
           WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table_name""",
        {"table_name": table_name},
    ))


def markdown_table(frame: pd.DataFrame) -> str:
    columns = [str(column) for column in frame.columns]
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in frame.itertuples(index=False, name=None):
        values = [
            str(value).replace("|", "\\|").replace("\n", " ") if pd.notna(value) else ""
            for value in row
        ]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def write_reports(checks: Checks, observed: dict) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(checks.rows)
    frame.to_csv(REPORT_CSV, index=False, encoding="utf-8-sig")
    counts = frame["estado"].value_counts().to_dict()
    lines = [
        "# Validación de entregas en TiDB staging", "",
        f"- **Fecha de validación:** {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"- **Estado global:** **{checks.global_status}**",
        f"- **PASS:** {counts.get('PASS', 0)}",
        f"- **WARN:** {counts.get('WARN', 0)}",
        f"- **FAIL:** {counts.get('FAIL', 0)}", "",
        "## Resumen", "",
        f"- Filas de entregas: **{observed.get('rows', 'No disponible')}**.",
        f"- entrega_id únicos: **{observed.get('unique_ids', 'No disponible')}**.",
        f"- Alertas: **{observed.get('alerts', 'No disponible')}**.",
        f"- Posibles duplicados conservados: **{observed.get('duplicates', 'No disponible')}**.",
        "- Las filas 2023 se conservan en 2023 aunque procedan de archivos de campaña/carpeta 2024.", "",
        "## Casos de control", "",
        f"- CUIL `20114713679`: {observed.get('control_1', 'No disponible')}.",
        f"- CUIL `27138026537`: {observed.get('control_2', 'No disponible')}.", "",
        "## Checks", "", markdown_table(frame), "",
        "## Interpretación", "",
        "Un FAIL indica una falla estructural o de preservación y bloquea el uso del staging. ",
        "Los WARN esperados corresponden a trazabilidad temporal y posibles duplicados conservados.",
    ]
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    checks = Checks()
    observed: dict = {}
    engine = UPLOAD.make_engine()
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        missing: list[str] = []
        for logical, table_name in TABLES.items():
            exists = table_exists(engine, table_name)
            checks.compare(
                f"table_{logical}", "existencia", f"Existe {table_name}", exists, True
            )
            if not exists:
                missing.append(table_name)
        if missing:
            write_reports(checks, observed)
            raise SystemExit(1)

        fact = TABLES["entregas"]
        quality = TABLES["calidad"]
        rows = int(scalar(engine, f"SELECT COUNT(*) FROM `{fact}`"))
        unique_ids = int(scalar(engine, f"SELECT COUNT(DISTINCT entrega_id) FROM `{fact}`"))
        alerts = int(scalar(engine, f"SELECT COUNT(*) FROM `{quality}`"))
        observed.update(rows=rows, unique_ids=unique_ids, alerts=alerts)
        checks.compare("fact_rows", "conteos", "Filas de entregas", rows, UPLOAD.EXPECTED_ROWS)
        checks.compare("fact_unique", "unicidad", "entrega_id únicos", unique_ids, UPLOAD.EXPECTED_ROWS)
        checks.compare("quality_rows", "conteos", "Filas de alertas", alerts, UPLOAD.EXPECTED_ALERTS)

        orphan_alerts = int(scalar(
            engine,
            f"""SELECT COUNT(*) FROM `{quality}` q LEFT JOIN `{fact}` f
                ON f.entrega_id=q.entrega_id WHERE f.entrega_id IS NULL""",
        ))
        checks.compare("quality_orphans", "integridad", "Alertas sin entrega", orphan_alerts, 0)

        years = query(engine, f"SELECT anio, COUNT(*) filas FROM `{fact}` GROUP BY anio")
        year_counts = {int(row.anio): int(row.filas) for row in years.itertuples() if pd.notna(row.anio)}
        checks.compare("years", "distribucion", "Años y conteos", year_counts, EXPECTED_YEARS)

        providers = query(engine, f"SELECT proveedor, COUNT(*) filas FROM `{fact}` GROUP BY proveedor")
        provider_counts = {
            (str(row.proveedor) if pd.notna(row.proveedor) else ""): int(row.filas)
            for row in providers.itertuples()
        }
        checks.compare("providers", "distribucion", "Proveedores y conteos", provider_counts, EXPECTED_PROVIDERS)

        qualities = query(engine, f"SELECT calidad_identificacion, COUNT(*) filas FROM `{fact}` GROUP BY calidad_identificacion")
        quality_counts = {key: 0 for key in EXPECTED_QUALITY}
        for row in qualities.itertuples():
            if pd.notna(row.calidad_identificacion):
                quality_counts[str(row.calidad_identificacion)] = int(row.filas)
        checks.compare("identification_quality", "distribucion", "Calidad de identificación", quality_counts, EXPECTED_QUALITY)

        numeric_units = int(scalar(
            engine,
            f"SELECT COUNT(*) FROM `{fact}` WHERE unidad REGEXP '^[0-9]+([.,][0-9]+)?$'",
        ))
        unit_25 = int(scalar(engine, f"SELECT COUNT(*) FROM `{fact}` WHERE TRIM(COALESCE(unidad,''))='25'"))
        kg_rows = int(scalar(engine, f"SELECT COUNT(*) FROM `{fact}` WHERE unidad='kg'"))
        roll_rows = int(scalar(engine, f"SELECT COUNT(*) FROM `{fact}` WHERE unidad='rollo'"))
        checks.compare("numeric_units", "unidad", "Unidades numéricas sospechosas", numeric_units, 0)
        checks.compare("unit_25", "unidad", "Unidad 25 inexistente", unit_25, 0)
        checks.add("unit_kg", "unidad", "Existen entregas en kg", "PASS" if kg_rows > 0 else "FAIL", kg_rows, "> 0")
        checks.add("unit_roll", "unidad", "Existen entregas en rollos", "PASS" if roll_rows > 0 else "FAIL", roll_rows, "> 0")

        control_1 = query(
            engine,
            f"""SELECT COUNT(*) filas, COALESCE(SUM(monto_estimado),0) monto,
                SUM(CASE WHEN cantidad IS NOT NULL THEN 1 ELSE 0 END) filas_cantidad
                FROM `{fact}` WHERE cuit_cuil_norm=:cuit""",
            {"cuit": "20114713679"},
        ).iloc[0]
        checks.compare("control_1_rows", "casos_control", "CUIL 20114713679: registros", int(control_1.filas), 1)
        checks.compare("control_1_amount", "casos_control", "CUIL 20114713679: monto", float(control_1.monto), 100000.0)
        checks.compare("control_1_quantity", "casos_control", "CUIL 20114713679: cantidad nula", int(control_1.filas_cantidad), 0)
        observed["control_1"] = f"{int(control_1.filas)} registro; monto {float(control_1.monto):.0f}; cantidad nula"

        control_2 = query(
            engine,
            f"""SELECT COUNT(*) filas, COALESCE(SUM(monto_estimado),0) monto,
                COALESCE(SUM(cantidad),0) cantidad,
                SUM(CASE WHEN cantidad=250 AND unidad='kg' THEN 1 ELSE 0 END) filas_250_kg
                FROM `{fact}` WHERE cuit_cuil_norm=:cuit""",
            {"cuit": "27138026537"},
        ).iloc[0]
        checks.compare("control_2_rows", "casos_control", "CUIL 27138026537: registros", int(control_2.filas), 3)
        checks.compare("control_2_amount", "casos_control", "CUIL 27138026537: monto", float(control_2.monto), 70000.0)
        checks.compare("control_2_quantity", "casos_control", "CUIL 27138026537: cantidad", float(control_2.cantidad), 500.0)
        checks.compare("control_2_units", "casos_control", "CUIL 27138026537: filas de 250 kg", int(control_2.filas_250_kg), 2)
        observed["control_2"] = (
            f"{int(control_2.filas)} registros; monto {float(control_2.monto):.0f}; "
            f"cantidad {float(control_2.cantidad):.0f}; {int(control_2.filas_250_kg)} filas de 250 kg"
        )

        duplicates = int(scalar(
            engine,
            f"SELECT COUNT(*) FROM `{quality}` WHERE alerta_tipo='posible_duplicado'",
        ))
        observed["duplicates"] = duplicates
        checks.add(
            "duplicate_warning", "advertencia", "Posibles duplicados conservados",
            "WARN" if duplicates > 0 else "PASS", duplicates, 4_304,
        )
        rows_2023 = year_counts.get(2023, 0)
        checks.add(
            "year_2023_warning", "advertencia",
            "Filas 2023 procedentes de archivos/campaña 2024",
            "WARN" if rows_2023 > 0 else "PASS", rows_2023, 892,
        )

        write_reports(checks, observed)
        print(f"Estado global: {checks.global_status}")
        print(f"Reporte Markdown: {REPORT_MD}")
        print(f"Checks CSV: {REPORT_CSV}")
        if checks.global_status == "FAIL":
            raise SystemExit(1)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
