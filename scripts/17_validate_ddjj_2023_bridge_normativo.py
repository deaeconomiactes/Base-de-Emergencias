"""Valida el bridge normativo DDJJ 2023 antes de diseñar una carga a staging.

El script abre los insumos únicamente para lectura y genera dos salidas locales:
`validation_bridge_normativo_2023_checks.csv` y
`validation_bridge_normativo_2023_resultados.md`.

Ejecución desde la raíz del repositorio:
    python scripts/17_validate_ddjj_2023_bridge_normativo.py
"""

from __future__ import annotations

import argparse
import csv
import re
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_NORMALIZED_DIR = (
    PROJECT_ROOT / "data_processed" / "ddjj_2023_excel" / "normalized"
)
DEFAULT_BRIDGE_DIR = (
    PROJECT_ROOT / "data_processed" / "ddjj_2023_excel" / "bridge"
)

MASTER_FILE = "fact_ddjj_tramite_2023.csv"
QUALITY_FILE = "fact_calidad_dato_2023.csv"
BRIDGE_FILE = "bridge_ddjj_evento_normativo_2023.csv"
CHECKS_FILE = "validation_bridge_normativo_2023_checks.csv"
REPORT_FILE = "validation_bridge_normativo_2023_resultados.md"

EXPECTED_MASTER_ROWS = 1493
EXPECTED_ANULADOS = 5
EXPECTED_FUERA_2023 = 5
EXPECTED_OVERLAP = 0
EXPECTED_INTEGRABLE = 1483

EXPECTED_EVENT_ID = "DECRETO_2099_2023"
EXPECTED_TIPO_NORMA = "Decreto"
EXPECTED_NUMERO_NORMA = "2099"
EXPECTED_ANIO_NORMA = "2023"
EXPECTED_CRITERIO = "correspondencia institucional validada"
EXPECTED_ORIGEN = "ddjj_2023_excel"
EXPECTED_SOURCE_FILE = BRIDGE_FILE

BRIDGE_REQUIRED_COLUMNS = [
    "tramite_id",
    "evento_id_normativo",
    "tipo_norma",
    "numero_norma",
    "anio_norma",
    "nombre_evento",
    "fecha_inicio_evento",
    "fecha_fin_evento",
    "criterio_asignacion",
    "fuente_normativa",
    "validado_por",
    "fecha_validacion",
    "confianza_asignacion",
    "observaciones",
    "origen_dato",
    "source_file_bridge",
]

MASTER_REQUIRED_COLUMNS = {
    "tramite_id",
    "estado_tramite",
    "anio_presentacion",
}

QUALITY_REQUIRED_COLUMNS = {
    "tramite_id",
    "dq_estado_anulado",
    "dq_fecha_fuera_2023",
    "dq_numero_certificado_nulo",
    "dq_tiene_adrema_duplicada",
    "dq_tiene_mortandad_mayor_cantidad",
    "dq_tiene_superficie_negativa",
}

CRITICAL_NOT_NULL = [
    "tramite_id",
    "evento_id_normativo",
    "tipo_norma",
    "numero_norma",
    "anio_norma",
    "nombre_evento",
    "criterio_asignacion",
    "fuente_normativa",
    "confianza_asignacion",
    "origen_dato",
]

ALLOWED_TIPO_NORMA = {"Decreto", "Resolución", "Disposición", "Otro"}
ALLOWED_CONFIANZA = {"alta", "media", "baja", "pendiente"}
ALLOWED_STATUS = {"PASS", "WARN", "FAIL"}


@dataclass
class TableData:
    name: str
    path: Path
    columns: list[str]
    rows: list[dict[str, str]]


@dataclass
class Check:
    check_id: str
    categoria: str
    descripcion: str
    estado: str
    valor_observado: Any
    valor_esperado: Any
    detalle: str = ""


@dataclass
class ValidationContext:
    master_rows: int = 0
    quality_rows: int = 0
    bridge_rows: int = 0
    master_unique: int = 0
    integrable_count: int = 0
    anulados_count: int = 0
    fuera_2023_count: int = 0
    overlap_count: int = 0
    excluded_union_count: int = 0
    missing_count: int = 0
    orphan_count: int = 0
    nonintegrable_in_bridge_count: int = 0
    duplicate_key_count: int = 0
    duplicate_excess_rows: int = 0
    coverage_percent: float = 0.0


def is_blank(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def canonical(value: Any) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    normalized = "".join(
        char for char in normalized if not unicodedata.combining(char)
    )
    return re.sub(r"\s+", " ", normalized.strip().lower())


def as_bool(value: Any) -> bool:
    return canonical(value) in {"true", "1", "yes", "si", "verdadero", "x"}


def normalize_id(value: Any) -> str:
    return str(value or "").strip()


def parse_iso_date(value: Any) -> date | None:
    if is_blank(value):
        return None
    text = str(value).strip()
    try:
        return date.fromisoformat(text)
    except ValueError:
        try:
            return datetime.fromisoformat(text).date()
        except ValueError:
            return None


def read_csv(path: Path) -> TableData:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]
    return TableData(path.name, path, columns, rows)


def add_check(
    checks: list[Check],
    check_id: str,
    categoria: str,
    descripcion: str,
    estado: str,
    valor_observado: Any,
    valor_esperado: Any,
    detalle: str = "",
) -> None:
    if estado not in ALLOWED_STATUS:
        raise ValueError(f"Estado de check no permitido: {estado}")
    checks.append(
        Check(
            check_id,
            categoria,
            descripcion,
            estado,
            valor_observado,
            valor_esperado,
            detalle,
        )
    )


def sample_values(values: Iterable[str], limit: int = 10) -> str:
    unique = sorted({value for value in values if not is_blank(value)})
    if not unique:
        return ""
    sample = unique[:limit]
    suffix = f"; y {len(unique) - limit} adicionales" if len(unique) > limit else ""
    return ", ".join(sample) + suffix


def count_duplicate_keys(values: Iterable[str]) -> tuple[int, int]:
    counts = Counter(value for value in values if not is_blank(value))
    duplicated_keys = sum(count > 1 for count in counts.values())
    excess_rows = sum(count - 1 for count in counts.values() if count > 1)
    return duplicated_keys, excess_rows


def load_inputs(
    normalized_dir: Path,
    bridge_dir: Path,
    checks: list[Check],
) -> dict[str, TableData]:
    paths = {
        "master": normalized_dir / MASTER_FILE,
        "quality": normalized_dir / QUALITY_FILE,
        "bridge": bridge_dir / BRIDGE_FILE,
    }
    tables: dict[str, TableData] = {}

    for key, path in paths.items():
        exists = path.is_file()
        add_check(
            checks,
            f"file_exists_{key}",
            "existencia",
            f"Existe {path.name}",
            "PASS" if exists else "FAIL",
            exists,
            True,
            str(path),
        )
        if not exists:
            continue
        try:
            table = read_csv(path)
        except Exception as exc:  # noqa: BLE001 - el error debe quedar reportado
            add_check(
                checks,
                f"file_read_{key}",
                "existencia",
                f"Se puede leer {path.name}",
                "FAIL",
                type(exc).__name__,
                "lectura sin error",
                str(exc),
            )
            continue
        tables[key] = table
        add_check(
            checks,
            f"file_read_{key}",
            "existencia",
            f"Se puede leer {path.name}",
            "PASS",
            f"{len(table.rows)} filas; {len(table.columns)} columnas",
            "lectura sin error",
        )

    return tables


def validate_columns(tables: dict[str, TableData], checks: list[Check]) -> bool:
    specifications = {
        "master": MASTER_REQUIRED_COLUMNS,
        "quality": QUALITY_REQUIRED_COLUMNS,
        "bridge": set(BRIDGE_REQUIRED_COLUMNS),
    }
    all_valid = True
    for key, required in specifications.items():
        table = tables.get(key)
        if table is None:
            all_valid = False
            continue
        missing = sorted(required - set(table.columns))
        extra = sorted(set(table.columns) - required) if key == "bridge" else []
        status = "PASS" if not missing else "FAIL"
        add_check(
            checks,
            f"required_columns_{key}",
            "estructura",
            f"Columnas obligatorias de {table.name}",
            status,
            len(table.columns),
            len(required),
            (
                f"Faltantes: {', '.join(missing) if missing else 'ninguna'}; "
                f"extras: {', '.join(extra) if extra else 'ninguna'}"
            ),
        )
        if missing:
            all_valid = False

    bridge = tables.get("bridge")
    if bridge is not None and set(BRIDGE_REQUIRED_COLUMNS).issubset(bridge.columns):
        exact_order = bridge.columns == BRIDGE_REQUIRED_COLUMNS
        add_check(
            checks,
            "bridge_column_order",
            "estructura",
            "Orden exacto de las 16 columnas del bridge",
            "PASS" if exact_order else "WARN",
            " | ".join(bridge.columns),
            " | ".join(BRIDGE_REQUIRED_COLUMNS),
            "Un orden diferente no altera los nombres, pero dificulta la trazabilidad.",
        )

    return all_valid


def validate_master(
    master: TableData,
    checks: list[Check],
    context: ValidationContext,
) -> set[str]:
    context.master_rows = len(master.rows)
    row_status = "PASS" if context.master_rows == EXPECTED_MASTER_ROWS else "WARN"
    add_check(
        checks,
        "master_row_count",
        "universo_maestro",
        "Cantidad de trámites maestros",
        row_status,
        context.master_rows,
        EXPECTED_MASTER_ROWS,
        "Se informa el conteo real y no se fuerzan registros.",
    )

    master_ids = [normalize_id(row.get("tramite_id")) for row in master.rows]
    blank_count = sum(is_blank(value) for value in master_ids)
    add_check(
        checks,
        "master_blank_tramite_id",
        "universo_maestro",
        "Trámites maestros con tramite_id nulo",
        "PASS" if blank_count == 0 else "FAIL",
        blank_count,
        0,
    )

    duplicate_keys, excess_rows = count_duplicate_keys(master_ids)
    add_check(
        checks,
        "master_duplicate_tramite_id",
        "universo_maestro",
        "Unicidad de tramite_id en la tabla maestra",
        "PASS" if duplicate_keys == 0 else "FAIL",
        f"{duplicate_keys} claves; {excess_rows} filas excedentes",
        "0 claves duplicadas",
    )

    master_set = {value for value in master_ids if not is_blank(value)}
    context.master_unique = len(master_set)
    return master_set


def build_quality_flags(quality: TableData) -> dict[str, dict[str, bool]]:
    flags: dict[str, dict[str, bool]] = {}
    for row in quality.rows:
        tramite_id = normalize_id(row.get("tramite_id"))
        if is_blank(tramite_id):
            continue
        current = flags.setdefault(
            tramite_id,
            {
                "anulado": False,
                "fuera_2023": False,
                "certificado_nulo": False,
                "adrema_duplicada": False,
                "mortandad": False,
                "superficie": False,
            },
        )
        current["anulado"] = current["anulado"] or as_bool(
            row.get("dq_estado_anulado")
        )
        current["fuera_2023"] = current["fuera_2023"] or as_bool(
            row.get("dq_fecha_fuera_2023")
        )
        current["certificado_nulo"] = current["certificado_nulo"] or as_bool(
            row.get("dq_numero_certificado_nulo")
        )
        current["adrema_duplicada"] = current["adrema_duplicada"] or as_bool(
            row.get("dq_tiene_adrema_duplicada")
        )
        current["mortandad"] = current["mortandad"] or as_bool(
            row.get("dq_tiene_mortandad_mayor_cantidad")
        )
        current["superficie"] = current["superficie"] or as_bool(
            row.get("dq_tiene_superficie_negativa")
        )
    return flags


def validate_integrable_universe(
    master: TableData,
    quality: TableData,
    master_ids: set[str],
    checks: list[Check],
    context: ValidationContext,
) -> tuple[set[str], set[str]]:
    context.quality_rows = len(quality.rows)
    quality_flags = build_quality_flags(quality)
    quality_ids = set(quality_flags)
    missing_quality = master_ids - quality_ids
    quality_orphans = quality_ids - master_ids

    add_check(
        checks,
        "quality_master_coverage",
        "universo_integrable",
        "Trámites maestros con fila de calidad",
        "PASS" if not missing_quality else "FAIL",
        len(master_ids - missing_quality),
        len(master_ids),
        f"Sin fila de calidad: {sample_values(missing_quality)}",
    )
    add_check(
        checks,
        "quality_orphan_rows_documented",
        "universo_integrable",
        "Claves de calidad que no existen en trámites maestros",
        "PASS" if len(quality_orphans) == 1 else "WARN",
        len(quality_orphans),
        1,
        "La fila adicional huérfana está documentada y no integra el universo maestro.",
    )

    integrable: set[str] = set()
    excluded: set[str] = set()
    anulado_ids: set[str] = set()
    fuera_ids: set[str] = set()

    for row in master.rows:
        tramite_id = normalize_id(row.get("tramite_id"))
        if is_blank(tramite_id):
            continue
        flags = quality_flags.get(tramite_id, {})
        is_anulado = (
            canonical(row.get("estado_tramite")) == "anulado"
            or bool(flags.get("anulado"))
        )
        anio = str(row.get("anio_presentacion") or "").strip()
        source_fuera = bool(anio) and anio != "2023"
        is_fuera = source_fuera or bool(flags.get("fuera_2023"))

        if is_anulado:
            anulado_ids.add(tramite_id)
        if is_fuera:
            fuera_ids.add(tramite_id)
        if is_anulado or is_fuera:
            excluded.add(tramite_id)
        else:
            integrable.add(tramite_id)

    context.anulados_count = len(anulado_ids)
    context.fuera_2023_count = len(fuera_ids)
    context.overlap_count = len(anulado_ids & fuera_ids)
    context.excluded_union_count = len(excluded)
    context.integrable_count = len(integrable)

    for check_id, description, observed, expected in (
        ("integrable_anulados", "Trámites anulados excluidos", context.anulados_count, EXPECTED_ANULADOS),
        ("integrable_fuera_2023", "Trámites fuera de 2023 excluidos", context.fuera_2023_count, EXPECTED_FUERA_2023),
        ("integrable_overlap", "Superposición entre anulados y fuera de 2023", context.overlap_count, EXPECTED_OVERLAP),
        ("integrable_count", "Universo integrable calculado", context.integrable_count, EXPECTED_INTEGRABLE),
    ):
        add_check(
            checks,
            check_id,
            "universo_integrable",
            description,
            "PASS" if observed == expected else "WARN",
            observed,
            expected,
            "Se conserva el conteo real sin forzarlo.",
        )

    other_flag_counts = {
        "certificado nulo": sum(
            bool(quality_flags.get(tramite_id, {}).get("certificado_nulo"))
            for tramite_id in integrable
        ),
        "ADREMA duplicada": sum(
            bool(quality_flags.get(tramite_id, {}).get("adrema_duplicada"))
            for tramite_id in integrable
        ),
        "mortandad mayor que cantidad": sum(
            bool(quality_flags.get(tramite_id, {}).get("mortandad"))
            for tramite_id in integrable
        ),
        "superficie negativa": sum(
            bool(quality_flags.get(tramite_id, {}).get("superficie"))
            for tramite_id in integrable
        ),
    }
    add_check(
        checks,
        "integrable_selective_exclusions",
        "universo_integrable",
        "Las únicas exclusiones son anulado o fecha fuera de 2023",
        "PASS",
        context.excluded_union_count,
        len(anulado_ids | fuera_ids),
        (
            "Alertas conservadas dentro del universo integrable: "
            + "; ".join(f"{key}={value}" for key, value in other_flag_counts.items())
        ),
    )

    return integrable, excluded


def validate_coverage_and_uniqueness(
    bridge: TableData,
    master_ids: set[str],
    integrable_ids: set[str],
    excluded_ids: set[str],
    checks: list[Check],
    context: ValidationContext,
) -> None:
    context.bridge_rows = len(bridge.rows)
    bridge_ids = [normalize_id(row.get("tramite_id")) for row in bridge.rows]
    bridge_nonblank_set = {value for value in bridge_ids if not is_blank(value)}

    missing = integrable_ids - bridge_nonblank_set
    orphans = bridge_nonblank_set - master_ids
    nonintegrable = bridge_nonblank_set & excluded_ids
    duplicate_keys, duplicate_excess = count_duplicate_keys(bridge_ids)

    context.missing_count = len(missing)
    context.orphan_count = len(orphans)
    context.nonintegrable_in_bridge_count = len(nonintegrable)
    context.duplicate_key_count = duplicate_keys
    context.duplicate_excess_rows = duplicate_excess
    covered = len(integrable_ids & bridge_nonblank_set)
    context.coverage_percent = (
        covered / len(integrable_ids) * 100 if integrable_ids else 0.0
    )

    add_check(
        checks,
        "bridge_row_count",
        "cobertura",
        "Filas del bridge frente al universo integrable real",
        "PASS" if context.bridge_rows == len(integrable_ids) else "FAIL",
        context.bridge_rows,
        len(integrable_ids),
    )
    add_check(
        checks,
        "bridge_missing_integrable",
        "cobertura",
        "Trámites integrables faltantes en el bridge",
        "PASS" if not missing else "FAIL",
        len(missing),
        0,
        f"Muestra: {sample_values(missing)}",
    )
    add_check(
        checks,
        "bridge_orphans",
        "integridad_referencial",
        "Trámites del bridge inexistentes en la tabla maestra",
        "PASS" if not orphans else "FAIL",
        len(orphans),
        0,
        f"Muestra: {sample_values(orphans)}",
    )
    add_check(
        checks,
        "bridge_nonintegrable_rows",
        "cobertura",
        "Trámites anulados o fuera de 2023 presentes en el bridge",
        "PASS" if not nonintegrable else "FAIL",
        len(nonintegrable),
        0,
        f"Muestra: {sample_values(nonintegrable)}",
    )
    add_check(
        checks,
        "bridge_coverage_percent",
        "cobertura",
        "Cobertura del universo integrable",
        "PASS" if context.coverage_percent == 100.0 else "FAIL",
        f"{context.coverage_percent:.2f}%",
        "100.00%",
    )
    add_check(
        checks,
        "bridge_duplicate_tramite_id",
        "unicidad",
        "tramite_id duplicado en el bridge",
        "PASS" if duplicate_keys == 0 else "FAIL",
        f"{duplicate_keys} claves; {duplicate_excess} filas excedentes",
        "0 claves duplicadas",
        "No existe una regla o columna de multiplicidad en la versión actual.",
    )
    add_check(
        checks,
        "bridge_multiple_events",
        "unicidad",
        "Más de un evento por tramite_id",
        "PASS" if duplicate_keys == 0 else "FAIL",
        duplicate_keys,
        0,
        "Cualquier multiplicidad debe estar respaldada por una regla explícita.",
    )


def count_not_equal(rows: Sequence[dict[str, str]], column: str, expected: str) -> int:
    return sum(str(row.get(column) or "").strip() != expected for row in rows)


def validate_normative_values(bridge: TableData, checks: list[Check]) -> None:
    specifications = (
        ("evento_id_normativo", EXPECTED_EVENT_ID),
        ("tipo_norma", EXPECTED_TIPO_NORMA),
        ("numero_norma", EXPECTED_NUMERO_NORMA),
        ("anio_norma", EXPECTED_ANIO_NORMA),
        ("criterio_asignacion", EXPECTED_CRITERIO),
    )
    for column, expected in specifications:
        invalid = count_not_equal(bridge.rows, column, expected)
        add_check(
            checks,
            f"normative_{column}",
            "valores_normativos",
            f"Valor esperado de {column}",
            "PASS" if invalid == 0 else "FAIL",
            f"{invalid} filas diferentes",
            expected,
        )

    blank_names = sum(is_blank(row.get("nombre_evento")) for row in bridge.rows)
    add_check(
        checks,
        "normative_nombre_evento",
        "valores_normativos",
        "nombre_evento informado",
        "PASS" if blank_names == 0 else "FAIL",
        blank_names,
        0,
    )

    invalid_types = sum(
        str(row.get("tipo_norma") or "").strip() not in ALLOWED_TIPO_NORMA
        for row in bridge.rows
    )
    invalid_confidence = sum(
        str(row.get("confianza_asignacion") or "").strip()
        not in ALLOWED_CONFIANZA
        for row in bridge.rows
    )
    add_check(
        checks,
        "allowed_tipo_norma",
        "valores_permitidos",
        "tipo_norma pertenece al catálogo permitido",
        "PASS" if invalid_types == 0 else "FAIL",
        invalid_types,
        0,
    )
    add_check(
        checks,
        "allowed_confianza",
        "valores_permitidos",
        "confianza_asignacion pertenece al catálogo permitido",
        "PASS" if invalid_confidence == 0 else "FAIL",
        invalid_confidence,
        0,
    )


def validate_nulls_pending_dates(bridge: TableData, checks: list[Check]) -> None:
    for column in CRITICAL_NOT_NULL:
        blank_count = sum(is_blank(row.get(column)) for row in bridge.rows)
        add_check(
            checks,
            f"critical_not_null_{column}",
            "nulos_criticos",
            f"{column} no nulo",
            "PASS" if blank_count == 0 else "FAIL",
            blank_count,
            0,
        )

    pending_validator = sum(
        canonical(row.get("validado_por")) == "pendiente_completar"
        for row in bridge.rows
    )
    blank_validator = sum(is_blank(row.get("validado_por")) for row in bridge.rows)
    validator_status = "WARN" if pending_validator or blank_validator else "PASS"
    add_check(
        checks,
        "pending_validado_por",
        "campos_pendientes",
        "Responsable institucional de validación completado",
        validator_status,
        f"pendiente_completar={pending_validator}; nulos={blank_validator}",
        "0 pendientes y 0 nulos",
        "La advertencia requiere decisión institucional, pero no es un error estructural.",
    )

    for column in ("fecha_inicio_evento", "fecha_fin_evento"):
        blank_count = sum(is_blank(row.get(column)) for row in bridge.rows)
        add_check(
            checks,
            f"pending_{column}",
            "campos_pendientes",
            f"{column} informada",
            "WARN" if blank_count else "PASS",
            blank_count,
            0,
            "La fecha normativa vacía requiere decisión institucional y no genera FAIL.",
        )

    invalid_validation_dates = sum(
        parse_iso_date(row.get("fecha_validacion")) is None for row in bridge.rows
    )
    invalid_start_dates = sum(
        not is_blank(row.get("fecha_inicio_evento"))
        and parse_iso_date(row.get("fecha_inicio_evento")) is None
        for row in bridge.rows
    )
    invalid_end_dates = sum(
        not is_blank(row.get("fecha_fin_evento"))
        and parse_iso_date(row.get("fecha_fin_evento")) is None
        for row in bridge.rows
    )
    invalid_order = 0
    for row in bridge.rows:
        start = parse_iso_date(row.get("fecha_inicio_evento"))
        end = parse_iso_date(row.get("fecha_fin_evento"))
        if start is not None and end is not None and start > end:
            invalid_order += 1

    for check_id, description, observed in (
        ("date_validation_parseable", "fecha_validacion parseable", invalid_validation_dates),
        ("date_start_parseable", "fecha_inicio_evento parseable cuando está informada", invalid_start_dates),
        ("date_end_parseable", "fecha_fin_evento parseable cuando está informada", invalid_end_dates),
        ("date_event_order", "fecha_inicio_evento no posterior a fecha_fin_evento", invalid_order),
    ):
        add_check(
            checks,
            check_id,
            "fechas",
            description,
            "PASS" if observed == 0 else "FAIL",
            observed,
            0,
        )


def validate_traceability(bridge: TableData, checks: list[Check]) -> None:
    blank_source = sum(is_blank(row.get("fuente_normativa")) for row in bridge.rows)
    blank_source_file = sum(
        is_blank(row.get("source_file_bridge")) for row in bridge.rows
    )
    invalid_source_file = count_not_equal(
        bridge.rows, "source_file_bridge", EXPECTED_SOURCE_FILE
    )
    invalid_origin = count_not_equal(bridge.rows, "origen_dato", EXPECTED_ORIGEN)

    for check_id, description, observed, expected in (
        ("trace_fuente_normativa", "fuente_normativa informada", blank_source, 0),
        ("trace_source_file_not_null", "source_file_bridge informado", blank_source_file, 0),
        ("trace_source_file_value", "source_file_bridge identifica el bridge actual", invalid_source_file, 0),
        ("trace_origen_dato", "origen_dato = ddjj_2023_excel", invalid_origin, 0),
    ):
        add_check(
            checks,
            check_id,
            "trazabilidad",
            description,
            "PASS" if observed == expected else "FAIL",
            observed,
            expected,
        )


def global_status(checks: Sequence[Check]) -> str:
    statuses = {check.estado for check in checks}
    if "FAIL" in statuses:
        return "FAIL"
    if "WARN" in statuses:
        return "WARN"
    return "PASS"


def write_checks(path: Path, checks: Sequence[Check]) -> None:
    fields = [
        "check_id",
        "categoria",
        "descripcion",
        "estado",
        "valor_observado",
        "valor_esperado",
        "detalle",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(asdict(check) for check in checks)


def md_escape(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def md_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend(
        "| " + " | ".join(md_escape(value) for value in row) + " |" for row in rows
    )
    return "\n".join(lines)


def relative_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def build_markdown(
    normalized_dir: Path,
    bridge_dir: Path,
    tables: dict[str, TableData],
    checks: Sequence[Check],
    context: ValidationContext,
    status: str,
) -> str:
    counts = Counter(check.estado for check in checks)
    technically_valid = counts["FAIL"] == 0
    apt_for_staging_design = technically_valid
    execution_time = datetime.now().astimezone().isoformat(timespec="seconds")

    files = [
        normalized_dir / MASTER_FILE,
        normalized_dir / QUALITY_FILE,
        bridge_dir / BRIDGE_FILE,
    ]
    check_rows = [
        (
            check.check_id,
            check.categoria,
            check.estado,
            check.valor_observado,
            check.valor_esperado,
            check.detalle,
        )
        for check in checks
    ]

    lines = [
        "# Validación del bridge normativo DDJJ 2023",
        "",
        f"- **Fecha de ejecución:** {execution_time}",
        f"- **Estado global:** **{status}**",
        f"- **Bridge técnicamente validado:** **{'Sí' if technically_valid else 'No'}**",
        (
            "- **Apto técnicamente para diseñar staging:** "
            f"**{'Sí, sujeto a decisión institucional sobre WARN' if apt_for_staging_design else 'No'}**"
        ),
        "- **Norma esperada:** Decreto 2099/23 (`DECRETO_2099_2023`)",
        "",
        "## Archivos leídos",
        "",
        *[f"- `{relative_path(path)}`" for path in files],
        "",
        "## Resumen de universos y cobertura",
        "",
        md_table(
            ["Indicador", "Valor"],
            [
                ("Trámites maestros", context.master_rows),
                ("Trámites maestros únicos", context.master_unique),
                ("Trámites anulados excluidos", context.anulados_count),
                ("Trámites fuera de 2023 excluidos", context.fuera_2023_count),
                ("Superposición de exclusiones", context.overlap_count),
                ("Universo integrable real", context.integrable_count),
                ("Filas del bridge", context.bridge_rows),
                ("Cobertura", f"{context.coverage_percent:.2f}%"),
                ("Faltantes", context.missing_count),
                ("Huérfanos", context.orphan_count),
                ("No integrables presentes", context.nonintegrable_in_bridge_count),
                ("Claves duplicadas", context.duplicate_key_count),
                ("Filas duplicadas excedentes", context.duplicate_excess_rows),
            ],
        ),
        "",
        "## Resultado de checks",
        "",
        md_table(
            ["Estado", "Cantidad"],
            [(state, counts[state]) for state in ("PASS", "WARN", "FAIL")],
        ),
        "",
        "## Detalle de validaciones",
        "",
        md_table(
            ["Check", "Categoría", "Estado", "Observado", "Esperado", "Detalle"],
            check_rows,
        ),
        "",
        "## Interpretación del estado",
        "",
    ]

    if technically_valid:
        lines.extend(
            [
                "El bridge queda **validado técnicamente** porque no se registraron checks `FAIL`.",
                "",
                (
                    "Las advertencias por `validado_por = pendiente_completar` o por fechas "
                    "normativas vacías no bloquean necesariamente el diseño de staging, pero "
                    "requieren una decisión y cierre institucional antes de la carga."
                ),
            ]
        )
    else:
        lines.extend(
            [
                "El bridge **no queda validado técnicamente** porque existe al menos un check `FAIL`.",
                "",
                "No debe diseñarse una carga a staging hasta resolver y volver a ejecutar la validación.",
            ]
        )

    lines.extend(
        [
            "",
            "## Restricciones",
            "",
            "- Este script no modifica el bridge ni los datos normalizados.",
            "- Este script no carga datos a TiDB.",
            "- Este script no modifica vistas SQL ni dashboard.",
            "- La salida es una validación local previa a cualquier diseño de staging.",
            "",
            "## Próximo paso recomendado",
            "",
            (
                "Completar la identificación del responsable institucional y resolver las fechas "
                "normativas si corresponde. Luego, con aprobación explícita, diseñar una carga "
                "controlada a staging y validarla contra este bridge."
                if technically_valid
                else "Resolver los checks FAIL y ejecutar nuevamente este script."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Valida el bridge normativo DDJJ 2023 contra el Decreto 2099/23."
    )
    parser.add_argument(
        "--normalized-dir",
        type=Path,
        default=DEFAULT_NORMALIZED_DIR,
        help="Directorio de tablas normalizadas DDJJ 2023.",
    )
    parser.add_argument(
        "--bridge-dir",
        type=Path,
        default=DEFAULT_BRIDGE_DIR,
        help="Directorio local del bridge y sus reportes.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    normalized_dir = (
        args.normalized_dir
        if args.normalized_dir.is_absolute()
        else PROJECT_ROOT / args.normalized_dir
    )
    bridge_dir = (
        args.bridge_dir
        if args.bridge_dir.is_absolute()
        else PROJECT_ROOT / args.bridge_dir
    )
    bridge_dir.mkdir(parents=True, exist_ok=True)

    checks: list[Check] = []
    context = ValidationContext()
    tables = load_inputs(normalized_dir, bridge_dir, checks)
    columns_valid = validate_columns(tables, checks)

    required_tables_available = all(
        key in tables for key in ("master", "quality", "bridge")
    )
    if required_tables_available and columns_valid:
        master_ids = validate_master(tables["master"], checks, context)
        integrable_ids, excluded_ids = validate_integrable_universe(
            tables["master"],
            tables["quality"],
            master_ids,
            checks,
            context,
        )
        validate_coverage_and_uniqueness(
            tables["bridge"],
            master_ids,
            integrable_ids,
            excluded_ids,
            checks,
            context,
        )
        validate_normative_values(tables["bridge"], checks)
        validate_nulls_pending_dates(tables["bridge"], checks)
        validate_traceability(tables["bridge"], checks)
    else:
        add_check(
            checks,
            "dependent_validations_skipped",
            "ejecucion",
            "Validaciones dependientes ejecutadas",
            "FAIL",
            False,
            True,
            "Faltan archivos o columnas obligatorias.",
        )

    status = global_status(checks)
    checks_path = bridge_dir / CHECKS_FILE
    report_path = bridge_dir / REPORT_FILE
    write_checks(checks_path, checks)
    report_path.write_text(
        build_markdown(
            normalized_dir,
            bridge_dir,
            tables,
            checks,
            context,
            status,
        ),
        encoding="utf-8",
    )

    counts = Counter(check.estado for check in checks)
    print(f"Estado global: {status}")
    print(f"PASS: {counts['PASS']}")
    print(f"WARN: {counts['WARN']}")
    print(f"FAIL: {counts['FAIL']}")
    print(f"Universo maestro: {context.master_rows}")
    print(f"Universo integrable: {context.integrable_count}")
    print(f"Filas del bridge: {context.bridge_rows}")
    print(f"Cobertura: {context.coverage_percent:.2f}%")
    print(f"Checks: {checks_path}")
    print(f"Reporte: {report_path}")
    print("No se modificaron bridge, datos normalizados, TiDB ni dashboard")

    return 1 if status == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
