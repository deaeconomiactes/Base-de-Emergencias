"""Valida las tablas normalizadas DDJJ 2023 antes de cualquier integración.

El script abre los CSV únicamente para lectura y genera dos reportes agregados:
`validation_ddjj_2023_resultados.md` y `validation_ddjj_2023_checks.csv`.

Ejecución desde la raíz del repositorio:
    python scripts/15_validate_ddjj_2023_processed.py
"""

from __future__ import annotations

import argparse
import csv
import math
import re
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = (
    PROJECT_ROOT / "data_processed" / "ddjj_2023_excel" / "normalized"
)
REPORT_MD = "validation_ddjj_2023_resultados.md"
REPORT_CSV = "validation_ddjj_2023_checks.csv"
SUMMARY_FILE = "transform_ddjj_2023_resumen.md"
ORIGEN_ESPERADO = "ddjj_2023_excel"

EXPECTED_COUNTS = {
    "dim_productor_2023.csv": 1485,
    "fact_ddjj_tramite_2023.csv": 1493,
    "fact_adrema_establecimiento_2023.csv": 2441,
    "fact_agricultura_perdida_2023.csv": 195,
    "fact_ganaderia_declarada_2023.csv": 18047,
    "fact_manifestacion_existencias_2023.csv": 917,
    "fact_seguro_agricola_2023.csv": 13,
    "fact_calidad_dato_2023.csv": 1494,
}

EXPECTED_ORPHAN_ROWS = {
    "fact_adrema_establecimiento_2023.csv": 0,
    "fact_agricultura_perdida_2023.csv": 0,
    "fact_ganaderia_declarada_2023.csv": 1,
    "fact_manifestacion_existencias_2023.csv": 0,
    "fact_seguro_agricola_2023.csv": 0,
}

REQUIRED_COLUMNS = {
    "dim_productor_2023.csv": {
        "productor_id_2023", "cuit_cuil", "productor_nombre", "cuit_valido",
        "cantidad_tramites", "origen_dato", "source_file",
    },
    "fact_ddjj_tramite_2023.csv": {
        "tramite_id", "productor_id_2023", "fecha_presentacion", "anio_presentacion",
        "estado_tramite", "numero_certificado", "origen_dato", "source_file",
        "source_sheet", "source_row_number",
    },
    "fact_adrema_establecimiento_2023.csv": {
        "tramite_id", "adrema", "superficie", "origen_dato", "source_file",
        "source_sheet", "source_row_number", "dq_tramite_huerfano",
        "dq_superficie_negativa", "dq_adrema_duplicada_en_tramite",
    },
    "fact_agricultura_perdida_2023.csv": {
        "tramite_id", "superficie_sembrada", "superficie_afectada", "origen_dato",
        "source_file", "source_sheet", "source_row_number", "dq_tramite_huerfano",
    },
    "fact_ganaderia_declarada_2023.csv": {
        "tramite_id", "especie", "cantidad", "mortandad", "superficie_uso",
        "superficie_afectada", "origen_dato", "source_file", "source_sheet",
        "source_row_number", "dq_tramite_huerfano", "dq_cantidad_negativa",
        "dq_mortandad_negativa", "dq_mortandad_mayor_cantidad",
    },
    "fact_manifestacion_existencias_2023.csv": {
        "tramite_id", "especie", "cantidad_manifestada", "origen_dato", "source_file",
        "source_sheet", "source_row_number", "dq_tramite_huerfano",
    },
    "fact_seguro_agricola_2023.csv": {
        "tramite_id", "evento_original", "origen_dato", "source_file", "source_sheet",
        "source_row_number", "dq_tramite_huerfano",
    },
    "fact_calidad_dato_2023.csv": {
        "tramite_id", "dq_cuit_invalido", "dq_fecha_fuera_2023", "dq_estado_anulado",
        "dq_adrema_faltante", "dq_tiene_tramite_huerfano_en_detalle",
        "dq_tiene_superficie_negativa", "dq_tiene_adrema_duplicada",
        "dq_tiene_mortandad_mayor_cantidad", "dq_numero_certificado_nulo",
        "dq_fecha_presentacion_nula", "origen_dato",
    },
}

DETAIL_TABLES = (
    "fact_ddjj_tramite_2023.csv",
    "fact_adrema_establecimiento_2023.csv",
    "fact_agricultura_perdida_2023.csv",
    "fact_ganaderia_declarada_2023.csv",
    "fact_manifestacion_existencias_2023.csv",
    "fact_seguro_agricola_2023.csv",
)


@dataclass
class TableData:
    name: str
    path: Path
    columns: list[str]
    rows: list[dict[str, str]]


@dataclass
class Check:
    check_id: str
    category: str
    table: str
    description: str
    status: str
    observed: Any
    expected: Any
    details: str = ""


def is_blank(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def canonical(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]", "", text.lower())


def as_bool(value: Any) -> bool:
    return str(value or "").strip().lower() in {"true", "1", "yes", "si", "sí", "verdadero"}


def as_number(value: Any) -> float | None:
    if is_blank(value):
        return None
    text = str(value).strip().replace(" ", "")
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".") if text.rfind(",") > text.rfind(".") else text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        result = float(text)
    except ValueError:
        return None
    return result if math.isfinite(result) else None


def read_csv(path: Path) -> TableData:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]
    return TableData(path.name, path, columns, rows)


def duplicate_summary(values: Iterable[str]) -> tuple[int, int]:
    counts = Counter(value for value in values if not is_blank(value))
    distinct = sum(count > 1 for count in counts.values())
    excess = sum(count - 1 for count in counts.values() if count > 1)
    return distinct, excess


def add_check(
    checks: list[Check],
    check_id: str,
    category: str,
    table: str,
    description: str,
    status: str,
    observed: Any,
    expected: Any,
    details: str = "",
) -> None:
    checks.append(Check(check_id, category, table, description, status, observed, expected, details))


def equality_check(
    checks: list[Check],
    check_id: str,
    category: str,
    table: str,
    description: str,
    observed: Any,
    expected: Any,
    details: str = "",
) -> None:
    add_check(
        checks, check_id, category, table, description,
        "PASS" if observed == expected else "FAIL", observed, expected, details,
    )


def parse_summary_counts(text: str) -> dict[str, int]:
    result: dict[str, int] = {}
    pattern = re.compile(r"\|\s*`([^`]+\.csv)`\s*\|\s*([\d.]+)\s*\|")
    for filename, count in pattern.findall(text):
        # El resumen vuelve a mencionar tablas de detalle en la sección de
        # huérfanos. La primera aparición corresponde a "Filas generadas".
        result.setdefault(filename, int(count.replace(".", "")))
    return result


def validate_files(input_dir: Path, checks: list[Check]) -> tuple[dict[str, TableData], str]:
    tables: dict[str, TableData] = {}
    for filename in EXPECTED_COUNTS:
        path = input_dir / filename
        exists = path.is_file()
        equality_check(
            checks, f"file_exists_{canonical(filename)}", "existencia", filename,
            "El archivo esperado existe", exists, True,
        )
        if not exists:
            continue
        try:
            table = read_csv(path)
        except Exception as exc:  # la validación debe continuar para reportar todos los faltantes
            add_check(
                checks, f"file_read_{canonical(filename)}", "lectura", filename,
                "El CSV puede leerse", "FAIL", "error", "lectura correcta", str(exc),
            )
            continue
        tables[filename] = table
        add_check(
            checks, f"file_read_{canonical(filename)}", "lectura", filename,
            "El CSV puede leerse", "PASS", f"{len(table.rows)} filas; {len(table.columns)} columnas",
            "lectura correcta",
        )
        missing_columns = sorted(REQUIRED_COLUMNS[filename] - set(table.columns))
        equality_check(
            checks, f"required_columns_{canonical(filename)}", "estructura", filename,
            "Están presentes las columnas mínimas", len(missing_columns), 0,
            "; ".join(missing_columns),
        )

    summary_path = input_dir / SUMMARY_FILE
    summary_text = ""
    equality_check(
        checks, "summary_exists", "existencia", SUMMARY_FILE,
        "El resumen de transformación existe", summary_path.is_file(), True,
    )
    if summary_path.is_file():
        try:
            summary_text = summary_path.read_text(encoding="utf-8")
            add_check(
                checks, "summary_read", "lectura", SUMMARY_FILE,
                "El resumen puede leerse", "PASS", "lectura correcta", "lectura correcta",
            )
        except Exception as exc:
            add_check(
                checks, "summary_read", "lectura", SUMMARY_FILE,
                "El resumen puede leerse", "FAIL", "error", "lectura correcta", str(exc),
            )
    return tables, summary_text


def validate_counts(
    tables: dict[str, TableData], summary_text: str, checks: list[Check]
) -> None:
    summary_counts = parse_summary_counts(summary_text)
    for filename, expected in EXPECTED_COUNTS.items():
        table = tables.get(filename)
        if table is None:
            continue
        actual = len(table.rows)
        equality_check(
            checks, f"row_count_{canonical(filename)}", "conteos", filename,
            "El conteo coincide con el valor crítico esperado", actual, expected,
        )
        summary_expected = summary_counts.get(filename)
        equality_check(
            checks, f"summary_count_{canonical(filename)}", "conciliacion_resumen", filename,
            "El conteo coincide con el resumen de transformación", actual,
            summary_expected if summary_expected is not None else "no informado",
        )


def validate_uniqueness(tables: dict[str, TableData], checks: list[Check]) -> None:
    dim = tables.get("dim_productor_2023.csv")
    if dim:
        null_ids = sum(is_blank(row.get("productor_id_2023")) for row in dim.rows)
        distinct, excess = duplicate_summary(row.get("productor_id_2023", "") for row in dim.rows)
        equality_check(checks, "dim_productor_id_null", "unicidad", dim.name, "productor_id_2023 no tiene nulos", null_ids, 0)
        equality_check(checks, "dim_productor_id_duplicate", "unicidad", dim.name, "productor_id_2023 es único", excess, 0, f"claves duplicadas distintas: {distinct}")
        nonnull_cuits = [row.get("cuit_cuil", "") for row in dim.rows if not is_blank(row.get("cuit_cuil"))]
        distinct, excess = duplicate_summary(nonnull_cuits)
        equality_check(checks, "dim_cuit_duplicate", "unicidad", dim.name, "cuit_cuil no nulo es único", excess, 0, f"CUIT duplicados distintos: {distinct}")

    ddjj = tables.get("fact_ddjj_tramite_2023.csv")
    if ddjj:
        null_ids = sum(is_blank(row.get("tramite_id")) for row in ddjj.rows)
        distinct, excess = duplicate_summary(row.get("tramite_id", "") for row in ddjj.rows)
        equality_check(checks, "ddjj_tramite_null", "unicidad", ddjj.name, "tramite_id no tiene nulos", null_ids, 0)
        equality_check(checks, "ddjj_tramite_duplicate", "unicidad", ddjj.name, "tramite_id es único", excess, 0, f"claves duplicadas distintas: {distinct}")

    quality = tables.get("fact_calidad_dato_2023.csv")
    if quality:
        null_ids = sum(is_blank(row.get("tramite_id")) for row in quality.rows)
        distinct, excess = duplicate_summary(row.get("tramite_id", "") for row in quality.rows)
        equality_check(checks, "quality_tramite_null", "unicidad", quality.name, "tramite_id no tiene nulos", null_ids, 0)
        equality_check(checks, "quality_tramite_duplicate", "unicidad", quality.name, "Hay como máximo una fila por tramite_id", excess, 0, f"claves duplicadas distintas: {distinct}")


def validate_references(tables: dict[str, TableData], checks: list[Check]) -> None:
    dim = tables.get("dim_productor_2023.csv")
    ddjj = tables.get("fact_ddjj_tramite_2023.csv")
    if not dim or not ddjj:
        return
    producer_ids = {row.get("productor_id_2023", "") for row in dim.rows if not is_blank(row.get("productor_id_2023"))}
    missing_producers = [row for row in ddjj.rows if is_blank(row.get("productor_id_2023")) or row.get("productor_id_2023") not in producer_ids]
    equality_check(
        checks, "ddjj_productor_fk", "integridad_referencial", ddjj.name,
        "Todos los productor_id_2023 existen en la dimensión", len(missing_producers), 0,
    )

    main_ids = {row.get("tramite_id", "") for row in ddjj.rows if not is_blank(row.get("tramite_id"))}
    orphan_ids_by_table: dict[str, set[str]] = {}
    for filename, expected_rows in EXPECTED_ORPHAN_ROWS.items():
        table = tables.get(filename)
        if not table:
            continue
        null_keys = sum(is_blank(row.get("tramite_id")) for row in table.rows)
        equality_check(
            checks, f"detail_key_null_{canonical(filename)}", "integridad_referencial", filename,
            "Las filas de detalle tienen tramite_id", null_keys, 0,
        )
        orphan_rows = [row for row in table.rows if not is_blank(row.get("tramite_id")) and row.get("tramite_id") not in main_ids]
        orphan_ids = {row.get("tramite_id", "") for row in orphan_rows}
        orphan_ids_by_table[filename] = orphan_ids
        equality_check(
            checks, f"orphan_rows_{canonical(filename)}", "integridad_referencial", filename,
            "Los huérfanos coinciden con la excepción documentada", len(orphan_rows), expected_rows,
            f"claves huérfanas distintas: {len(orphan_ids)}",
        )

    quality = tables.get("fact_calidad_dato_2023.csv")
    if quality:
        quality_ids = {row.get("tramite_id", "") for row in quality.rows if not is_blank(row.get("tramite_id"))}
        extra_quality_ids = quality_ids - main_ids
        gan_orphans = orphan_ids_by_table.get("fact_ganaderia_declarada_2023.csv", set())
        equality_check(
            checks, "quality_extra_id_count", "integridad_referencial", quality.name,
            "Calidad contiene una única fila adicional huérfana", len(extra_quality_ids), 1,
        )
        equality_check(
            checks, "quality_extra_id_matches_orphan", "integridad_referencial", quality.name,
            "La fila adicional de calidad corresponde al huérfano ganadero",
            extra_quality_ids, gan_orphans,
        )
        flagged = {
            row.get("tramite_id", "")
            for row in quality.rows
            if as_bool(row.get("dq_tiene_tramite_huerfano_en_detalle"))
        }
        equality_check(
            checks, "quality_orphan_flag_matches", "integridad_referencial", quality.name,
            "La bandera consolidada identifica el huérfano esperado", flagged, gan_orphans,
        )


def validate_traceability(tables: dict[str, TableData], checks: list[Check]) -> None:
    for filename, table in tables.items():
        if "origen_dato" in table.columns:
            null_origin = sum(is_blank(row.get("origen_dato")) for row in table.rows)
            wrong_origin = sum(
                not is_blank(row.get("origen_dato")) and row.get("origen_dato") != ORIGEN_ESPERADO
                for row in table.rows
            )
            equality_check(checks, f"origin_null_{canonical(filename)}", "trazabilidad", filename, "origen_dato no es nulo", null_origin, 0)
            equality_check(checks, f"origin_value_{canonical(filename)}", "trazabilidad", filename, "origen_dato conserva el valor esperado", wrong_origin, 0)
        if "source_file" in table.columns:
            null_source = sum(is_blank(row.get("source_file")) for row in table.rows)
            equality_check(checks, f"source_file_{canonical(filename)}", "trazabilidad", filename, "source_file no es nulo", null_source, 0)
        if filename in DETAIL_TABLES:
            null_sheet = sum(is_blank(row.get("source_sheet")) for row in table.rows)
            null_row = sum(is_blank(row.get("source_row_number")) for row in table.rows)
            invalid_row = sum(
                not is_blank(row.get("source_row_number"))
                and (as_number(row.get("source_row_number")) is None or as_number(row.get("source_row_number")) <= 0)
                for row in table.rows
            )
            equality_check(checks, f"source_sheet_{canonical(filename)}", "trazabilidad", filename, "source_sheet no es nulo", null_sheet, 0)
            equality_check(checks, f"source_row_null_{canonical(filename)}", "trazabilidad", filename, "source_row_number no es nulo", null_row, 0)
            equality_check(checks, f"source_row_valid_{canonical(filename)}", "trazabilidad", filename, "source_row_number es positivo", invalid_row, 0)


def validate_dates(tables: dict[str, TableData], checks: list[Check]) -> None:
    ddjj = tables.get("fact_ddjj_tramite_2023.csv")
    if not ddjj:
        return
    null_dates = invalid_dates = inconsistent_years = outside_2023 = 0
    for row in ddjj.rows:
        raw_date = row.get("fecha_presentacion", "")
        raw_year = row.get("anio_presentacion", "")
        if is_blank(raw_date):
            null_dates += 1
            continue
        try:
            parsed = date.fromisoformat(raw_date)
        except ValueError:
            invalid_dates += 1
            continue
        if parsed.year != 2023:
            outside_2023 += 1
        if not is_blank(raw_year):
            try:
                year = int(float(raw_year))
            except ValueError:
                inconsistent_years += 1
            else:
                inconsistent_years += year != parsed.year
    equality_check(checks, "date_null", "fechas", ddjj.name, "fecha_presentacion no es nula", null_dates, 0)
    equality_check(checks, "date_parseable", "fechas", ddjj.name, "fecha_presentacion es ISO parseable", invalid_dates, 0)
    equality_check(checks, "date_year_consistency", "fechas", ddjj.name, "anio_presentacion coincide con fecha_presentacion", inconsistent_years, 0)
    equality_check(checks, "date_outside_2023", "fechas", ddjj.name, "Los trámites fuera de 2023 coinciden con lo documentado", outside_2023, 5)


def flag_count(table: TableData, column: str) -> int:
    return sum(as_bool(row.get(column)) for row in table.rows)


def validate_quality(tables: dict[str, TableData], checks: list[Check]) -> None:
    quality = tables.get("fact_calidad_dato_2023.csv")
    if not quality:
        return
    expectations = {
        "dq_cuit_invalido": 1,
        "dq_estado_anulado": 5,
        "dq_fecha_fuera_2023": 5,
        "dq_adrema_faltante": 111,
        "dq_tiene_superficie_negativa": 3,
        "dq_tiene_mortandad_mayor_cantidad": 367,
        "dq_numero_certificado_nulo": 590,
        "dq_tiene_tramite_huerfano_en_detalle": 1,
    }
    for column, expected in expectations.items():
        equality_check(
            checks, f"quality_flag_{canonical(column)}", "calidad_consolidada", quality.name,
            f"La bandera {column} coincide con la alerta documentada", flag_count(quality, column), expected,
        )

    adrema = tables.get("fact_adrema_establecimiento_2023.csv")
    if adrema:
        flagged_rows = flag_count(adrema, "dq_adrema_duplicada_en_tramite")
        pairs = Counter(
            (row.get("tramite_id", ""), row.get("adrema", ""))
            for row in adrema.rows
            if not is_blank(row.get("tramite_id")) and not is_blank(row.get("adrema"))
        )
        duplicated_pairs = sum(count > 1 for count in pairs.values())
        duplicated_rows = sum(count for count in pairs.values() if count > 1)
        equality_check(checks, "adrema_duplicate_flagged_rows", "calidad_consolidada", adrema.name, "Las filas ADREMA duplicadas marcadas coinciden", flagged_rows, 49)
        equality_check(checks, "adrema_duplicate_pairs", "calidad_consolidada", adrema.name, "Los pares tramite_id + adrema duplicados coinciden", duplicated_pairs, 20)
        equality_check(checks, "adrema_duplicate_rows_recomputed", "calidad_consolidada", adrema.name, "Las filas pertenecientes a pares duplicados coinciden", duplicated_rows, 49)


def count_negative_values(rows: Sequence[dict[str, str]], columns: Sequence[str]) -> int:
    return sum(
        1
        for row in rows
        for column in columns
        if (number := as_number(row.get(column))) is not None and number < 0
    )


def validate_critical_values(tables: dict[str, TableData], checks: list[Check]) -> None:
    adrema = tables.get("fact_adrema_establecimiento_2023.csv")
    agriculture = tables.get("fact_agricultura_perdida_2023.csv")
    livestock = tables.get("fact_ganaderia_declarada_2023.csv")
    ddjj = tables.get("fact_ddjj_tramite_2023.csv")

    negative_surfaces = 0
    if adrema:
        negative_surfaces += count_negative_values(adrema.rows, ("superficie",))
    if agriculture:
        negative_surfaces += count_negative_values(agriculture.rows, ("superficie_sembrada", "superficie_afectada"))
    if livestock:
        negative_surfaces += count_negative_values(livestock.rows, ("superficie_uso", "superficie_afectada"))
    equality_check(checks, "critical_negative_surfaces_count", "valores_criticos", "múltiples", "Los valores de superficie negativos coinciden con el resumen", negative_surfaces, 4)
    if negative_surfaces:
        add_check(checks, "method_negative_surfaces", "riesgo_metodologico", "múltiples", "Existen superficies negativas que requieren revisión", "WARN", negative_surfaces, 0, "Se preservan; no se corrigen automáticamente.")

    if livestock:
        quantity_negative = count_negative_values(livestock.rows, ("cantidad",))
        mortality_negative = count_negative_values(livestock.rows, ("mortandad",))
        mortality_gt = 0
        for row in livestock.rows:
            quantity = as_number(row.get("cantidad"))
            mortality = as_number(row.get("mortandad"))
            mortality_gt += quantity is not None and mortality is not None and mortality > quantity
        equality_check(checks, "critical_quantity_negative", "valores_criticos", livestock.name, "La cantidad negativa coincide con la auditoría", quantity_negative, 1)
        equality_check(checks, "critical_mortality_negative", "valores_criticos", livestock.name, "La mortandad negativa coincide con la auditoría", mortality_negative, 1)
        equality_check(checks, "critical_mortality_gt_quantity", "valores_criticos", livestock.name, "mortandad > cantidad coincide con la auditoría", mortality_gt, 924)
        if mortality_gt:
            add_check(checks, "method_mortality_gt_quantity", "riesgo_metodologico", livestock.name, "mortandad > cantidad requiere validación institucional", "WARN", mortality_gt, 0, "No descartar hasta confirmar el significado de cantidad.")

    if ddjj:
        certificate_null = sum(is_blank(row.get("numero_certificado")) for row in ddjj.rows)
        annulled = sum(canonical(row.get("estado_tramite")) == "anulado" for row in ddjj.rows)
        equality_check(checks, "critical_certificate_null", "valores_criticos", ddjj.name, "Los certificados nulos coinciden", certificate_null, 590)
        equality_check(checks, "critical_annulled", "valores_criticos", ddjj.name, "Los estados anulados coinciden", annulled, 5)

    if adrema and flag_count(adrema, "dq_adrema_duplicada_en_tramite"):
        add_check(checks, "method_adrema_duplicates", "riesgo_metodologico", adrema.name, "Las ADREMAS duplicadas requieren criterio de consolidación", "WARN", flag_count(adrema, "dq_adrema_duplicada_en_tramite"), 0, "No colapsar automáticamente.")


def validate_methodology(input_dir: Path, checks: list[Check]) -> None:
    bridge = input_dir / "bridge_ddjj_evento_normativo_2023.csv"
    equality_check(checks, "bridge_normative_absent", "metodologia", bridge.name, "El bridge normativo todavía no existe", bridge.exists(), False)
    add_check(checks, "method_certificate_not_resolution", "riesgo_metodologico", "fact_ddjj_tramite_2023.csv", "Numero Certificado no se interpreta como resolución/decreto", "WARN", "pendiente de vinculación normativa", "bridge/documentación normativa")
    add_check(checks, "method_no_tidb_load", "riesgo_metodologico", "pipeline", "No cargar a TiDB antes de la validación institucional", "WARN", "carga bloqueada metodológicamente", "validación institucional completa")


def global_status(checks: Sequence[Check]) -> str:
    statuses = {check.status for check in checks}
    if "FAIL" in statuses:
        return "FAIL"
    if "WARN" in statuses:
        return "WARN"
    return "PASS"


def write_checks(path: Path, checks: Sequence[Check]) -> None:
    fields = tuple(Check.__dataclass_fields__)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(asdict(check) for check in checks)


def md_escape(value: Any) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


def md_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    lines = [
        "| " + " | ".join(md_escape(value) for value in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(md_escape(value) for value in row) + " |" for row in rows)
    return "\n".join(lines)


def build_markdown(
    input_dir: Path,
    tables: dict[str, TableData],
    checks: Sequence[Check],
    status: str,
) -> str:
    failed = [check for check in checks if check.status == "FAIL"]
    warned = [check for check in checks if check.status == "WARN"]
    passed = [check for check in checks if check.status == "PASS"]
    inventory_rows = [
        (filename, len(table.rows), len(table.columns), "sí")
        for filename, table in sorted(tables.items())
    ]
    check_rows = [
        (check.check_id, check.category, check.table, check.status, check.observed, check.expected, check.details or "—")
        for check in checks
    ]
    lines = [
        "# Validación de tablas normalizadas DDJJ 2023",
        "",
        f"## Estado global: **{status}**",
        "",
        f"- **Fecha/hora:** {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"- **Directorio validado:** `{input_dir.relative_to(PROJECT_ROOT) if input_dir.is_relative_to(PROJECT_ROOT) else input_dir}`",
        f"- **Checks PASS:** {len(passed)}",
        f"- **Checks WARN:** {len(warned)}",
        f"- **Checks FAIL:** {len(failed)}",
        "- **Modo:** lectura local; los CSV normalizados no fueron modificados.",
        "",
        "## Interpretación del estado",
        "",
    ]
    if status == "FAIL":
        lines.append("La estructura no está habilitada para avanzar: existen errores críticos en archivos, claves, conteos o relaciones.")
    elif status == "WARN":
        lines.append("La estructura técnica es consistente, pero permanecen riesgos metodológicos que requieren decisión institucional antes de cargar datos.")
    else:
        lines.append("No se detectaron errores estructurales ni advertencias metodológicas pendientes.")
    lines.extend(
        [
            "",
            "## Inventario leído",
            "",
            md_table(("Tabla", "Filas", "Columnas", "Lectura"), inventory_rows),
            "",
            "## Checks fallidos",
            "",
        ]
    )
    if failed:
        lines.extend(f"- **{check.check_id}** ({check.table}): {check.description}. Observado: {check.observed}; esperado: {check.expected}." for check in failed)
    else:
        lines.append("- Ninguno.")
    lines.extend(["", "## Advertencias", ""])
    if warned:
        lines.extend(f"- **{check.check_id}** ({check.table}): {check.description}. {check.details}" for check in warned)
    else:
        lines.append("- Ninguna.")
    lines.extend(
        [
            "",
            "## Riesgos metodológicos vigentes",
            "",
            "- `Numero Certificado` no se interpreta como resolución o decreto.",
            "- No existe todavía un bridge entre DDJJ y evento normativo.",
            "- La base no debe cargarse a TiDB hasta completar validaciones institucionales.",
            "- Los casos `mortandad > cantidad` no deben descartarse sin confirmar el significado de `cantidad`.",
            "- Las ADREMAS duplicadas no deben colapsarse sin un criterio documentado.",
            "",
            "## Detalle completo de checks",
            "",
            md_table(("Check", "Categoría", "Tabla", "Estado", "Observado", "Esperado", "Detalle"), check_rows),
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validar tablas procesadas DDJJ 2023.")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_dir = args.input_dir if args.input_dir.is_absolute() else PROJECT_ROOT / args.input_dir
    if not input_dir.is_dir():
        raise FileNotFoundError(f"No existe el directorio normalizado: {input_dir}")

    checks: list[Check] = []
    tables, summary_text = validate_files(input_dir, checks)
    validate_counts(tables, summary_text, checks)
    validate_uniqueness(tables, checks)
    validate_references(tables, checks)
    validate_traceability(tables, checks)
    validate_dates(tables, checks)
    validate_quality(tables, checks)
    validate_critical_values(tables, checks)
    validate_methodology(input_dir, checks)

    status = global_status(checks)
    add_check(
        checks, "global_status", "resultado_global", "conjunto normalizado",
        "Estado global de validación", status, status, "PASS/WARN/FAIL",
        "FAIL prevalece sobre WARN; WARN prevalece sobre PASS.",
    )
    checks_path = input_dir / REPORT_CSV
    report_path = input_dir / REPORT_MD
    write_checks(checks_path, checks)
    report_path.write_text(build_markdown(input_dir, tables, checks, status), encoding="utf-8")

    failed = [check for check in checks if check.status == "FAIL"]
    warned = [check for check in checks if check.status == "WARN"]
    print(f"Estado global: {status}")
    print(f"Checks totales: {len(checks)}")
    print(f"Checks FAIL: {len(failed)}")
    print(f"Checks WARN: {len(warned)}")
    print(f"Reporte: {report_path}")
    print(f"Checks CSV: {checks_path}")
    print("No se modificaron los CSV validados ni se realizó carga a TiDB")
    return 1 if status == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
