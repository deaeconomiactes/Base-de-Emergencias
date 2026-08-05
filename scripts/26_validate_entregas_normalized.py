"""Validación no destructiva de la base normalizada de entregas.

Lee exclusivamente las salidas del script 25 y genera checks y un informe.
No corrige, recodifica ni sobrescribe los datos normalizados.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parents[1]
NORMALIZED_DIR = PROJECT_DIR / "data_processed" / "entregas" / "normalized"
FACT_PATH = NORMALIZED_DIR / "fact_entregas_emergencia.csv"
QUALITY_PATH = NORMALIZED_DIR / "fact_entregas_calidad_dato.csv"
TRANSFORM_REPORT_PATH = NORMALIZED_DIR / "transform_entregas_resumen.md"
CHECKS_PATH = NORMALIZED_DIR / "validation_entregas_checks.csv"
REPORT_PATH = NORMALIZED_DIR / "validation_entregas_resultados.md"

FACT_COLUMNS = [
    "entrega_id", "anio", "fecha_entrega", "productor_nombre",
    "cuit_cuil_original", "cuit_cuil_norm", "documento_original",
    "documento_norm", "renspa", "adrema", "departamento", "localidad",
    "municipio", "paraje", "tipo_asistencia", "proveedor",
    "insumo_producto", "cantidad", "unidad", "monto_estimado", "moneda",
    "norma_evento", "expediente", "fuente_archivo", "fuente_hoja",
    "source_row_number", "origen_dato", "calidad_identificacion", "observaciones",
]

QUALITY_COLUMNS = [
    "entrega_id", "fuente_archivo", "fuente_hoja", "source_row_number",
    "alerta_tipo", "alerta_descripcion", "severidad",
]

EXPECTED_ROWS = 14_368
EXPECTED_ALERTS = 9_867
EXPECTED_YEARS = {"2022": 8_457, "2023": 892, "2024": 2_241, "2025": 2_778}
EXPECTED_PROVIDERS = {
    "Sin dato": 8_457, "Prieto": 4_710, "Kofman": 784,
    "Fitosan": 402, "Borderes": 15,
}
EXPECTED_QUALITY = {"alta": 14_147, "media": 219, "baja": 2, "pendiente": 0}
EXPECTED_COVERAGE = {"CUIT/CUIL válido": 14_147, "Documento": 14_324, "RENSPA": 7_730, "ADREMA": 269}
EXPECTED_ALERT_TYPES = {
    "producto_no_inferido": 5_509, "posible_duplicado": 4_304,
    "documento_faltante": 44, "cuit_invalido": 8, "solo_nombre": 2,
}


class Validator:
    def __init__(self) -> None:
        self.checks: list[dict[str, str]] = []

    def add(
        self,
        categoria: str,
        descripcion: str,
        estado: str,
        valor_observado: Any,
        valor_esperado: Any,
        detalle: str = "",
    ) -> None:
        self.checks.append({
            "check_id": f"CHK_{len(self.checks) + 1:03d}",
            "categoria": categoria,
            "descripcion": descripcion,
            "estado": estado,
            "valor_observado": stringify(valor_observado),
            "valor_esperado": stringify(valor_esperado),
            "detalle": detalle,
        })

    def compare(
        self,
        categoria: str,
        descripcion: str,
        observed: Any,
        expected: Any,
        mismatch_state: str = "WARN",
        detail: str = "",
    ) -> None:
        self.add(
            categoria, descripcion, "PASS" if observed == expected else mismatch_state,
            observed, expected, detail if observed != expected else "Coincide con el valor esperado.",
        )


def stringify(value: Any) -> str:
    if isinstance(value, dict):
        return "; ".join(f"{key}: {item}" for key, item in value.items())
    if isinstance(value, (list, tuple, set)):
        return ", ".join(map(str, value))
    return str(value)


def read_csv_text(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")


def counts(series: pd.Series, ordered_keys: list[str] | None = None) -> dict[str, int]:
    found = {str(key): int(value) for key, value in series.value_counts(dropna=False).items()}
    if ordered_keys is None:
        return found
    return {key: found.get(key, 0) for key in ordered_keys}


def validate_files(validator: Validator) -> bool:
    all_exist = True
    for path in (FACT_PATH, QUALITY_PATH, TRANSFORM_REPORT_PATH):
        exists = path.is_file()
        all_exist &= exists
        validator.add(
            "archivos", f"Existencia de {path.name}", "PASS" if exists else "FAIL",
            "existe" if exists else "no existe", "existe",
            str(path),
        )
    return all_exist


def validate_structure(validator: Validator, fact: pd.DataFrame, quality: pd.DataFrame) -> None:
    missing_fact = [column for column in FACT_COLUMNS if column not in fact.columns]
    extra_fact = [column for column in fact.columns if column not in FACT_COLUMNS]
    validator.add(
        "estructura", "Columnas obligatorias de fact_entregas_emergencia",
        "PASS" if not missing_fact else "FAIL", len(fact.columns), len(FACT_COLUMNS),
        f"Faltantes: {missing_fact or 'ninguna'}. Adicionales: {extra_fact or 'ninguna'}.",
    )
    missing_quality = [column for column in QUALITY_COLUMNS if column not in quality.columns]
    extra_quality = [column for column in quality.columns if column not in QUALITY_COLUMNS]
    validator.add(
        "estructura", "Columnas obligatorias de fact_entregas_calidad_dato",
        "PASS" if not missing_quality else "FAIL", len(quality.columns), len(QUALITY_COLUMNS),
        f"Faltantes: {missing_quality or 'ninguna'}. Adicionales: {extra_quality or 'ninguna'}.",
    )


def validate_counts_and_ids(validator: Validator, fact: pd.DataFrame, quality: pd.DataFrame) -> None:
    validator.compare("conteos", "Filas normalizadas", len(fact), EXPECTED_ROWS, "WARN", "Se informa el valor real; no se fuerza el conteo.")
    validator.compare("conteos", "Filas de alertas", len(quality), EXPECTED_ALERTS, "WARN", "Se informa el valor real; no se fuerza el conteo.")
    empty_ids = int(fact["entrega_id"].eq("").sum())
    validator.add("identificadores", "entrega_id informado", "PASS" if empty_ids == 0 else "FAIL", empty_ids, 0, "Cantidad de IDs vacíos.")
    duplicated_ids = int(fact["entrega_id"].duplicated(keep=False).sum())
    validator.add("identificadores", "Unicidad de entrega_id", "PASS" if duplicated_ids == 0 else "FAIL", duplicated_ids, 0, "Filas que participan en IDs duplicados.")
    unique_ids = int(fact["entrega_id"].nunique())
    validator.add("identificadores", "Cantidad de entrega_id únicos", "PASS" if unique_ids == len(fact) else "FAIL", unique_ids, len(fact))
    invalid_hash = int((~fact["entrega_id"].str.fullmatch(r"[0-9a-f]{64}")).sum())
    validator.add("identificadores", "Formato estable SHA-256 de entrega_id", "PASS" if invalid_hash == 0 else "WARN", invalid_hash, 0)

    orphan_alerts = int((~quality["entrega_id"].isin(fact["entrega_id"])).sum())
    validator.add("integridad", "Alertas referenciadas a una entrega existente", "PASS" if orphan_alerts == 0 else "FAIL", orphan_alerts, 0)


def validate_years(validator: Validator, fact: pd.DataFrame) -> None:
    observed = counts(fact["anio"], list(EXPECTED_YEARS))
    validator.compare("años", "Años y conteos detectados", observed, EXPECTED_YEARS, "WARN", "No se recodifican años ante diferencias.")
    unexpected = sorted(set(fact.loc[fact["anio"].ne(""), "anio"]) - set(EXPECTED_YEARS))
    validator.add("años", "Años fuera del conjunto esperado", "PASS" if not unexpected else "WARN", unexpected or "ninguno", "ninguno")
    missing_year = int(fact["anio"].eq("").sum())
    validator.add("años", "Año informado", "PASS" if missing_year == 0 else "WARN", missing_year, 0)

    rows_2023 = fact[fact["anio"].eq("2023")]
    sources_2023 = sorted(rows_2023["fuente_archivo"].unique())
    validator.add(
        "años", "Registros 2023 en archivos de la campaña/carpeta 2024", "WARN",
        len(rows_2023), 892,
        "Se conserva 2023 porque la fecha de la fila tiene prioridad. Archivos: " + "; ".join(sources_2023),
    )

    dates = pd.to_datetime(fact["fecha_entrega"], errors="coerce")
    informed_date = fact["fecha_entrega"].ne("")
    invalid_date = int((informed_date & dates.isna()).sum())
    validator.add("valores", "Fechas informadas parseables", "PASS" if invalid_date == 0 else "FAIL", invalid_date, 0)
    numeric_year = pd.to_numeric(fact["anio"], errors="coerce")
    inconsistent = int((informed_date & dates.notna() & numeric_year.notna() & dates.dt.year.ne(numeric_year)).sum())
    validator.add(
        "años", "Consistencia entre anio y fecha_entrega", "PASS" if inconsistent == 0 else "WARN",
        inconsistent, 0, "No se recodifican las inconsistencias.",
    )


def validate_distributions(validator: Validator, fact: pd.DataFrame, quality: pd.DataFrame) -> None:
    observed_providers = counts(fact["proveedor"], list(EXPECTED_PROVIDERS))
    validator.compare("proveedores", "Distribución de proveedores", observed_providers, EXPECTED_PROVIDERS, "WARN")
    unexpected_providers = sorted(set(fact["proveedor"]) - set(EXPECTED_PROVIDERS))
    validator.add("proveedores", "Proveedores no esperados", "PASS" if not unexpected_providers else "WARN", unexpected_providers or "ninguno", "ninguno")

    observed_quality = counts(fact["calidad_identificacion"], list(EXPECTED_QUALITY))
    validator.compare("calidad_identificacion", "Distribución de calidad de identificación", observed_quality, EXPECTED_QUALITY, "WARN")
    unexpected_quality = sorted(set(fact["calidad_identificacion"]) - set(EXPECTED_QUALITY))
    validator.add("calidad_identificacion", "Categorías de calidad válidas", "PASS" if not unexpected_quality else "FAIL", unexpected_quality or "ninguna", "alta, media, baja, pendiente")

    observed_alerts = counts(quality["alerta_tipo"], list(EXPECTED_ALERT_TYPES))
    validator.compare("alertas", "Conteos de alertas principales", observed_alerts, EXPECTED_ALERT_TYPES, "WARN")
    allowed_severity = {"alta", "media", "baja"}
    invalid_severity = sorted(set(quality["severidad"]) - allowed_severity)
    validator.add("alertas", "Severidades válidas", "PASS" if not invalid_severity else "FAIL", invalid_severity or "ninguna", sorted(allowed_severity))


def validate_identification_rules(validator: Validator, fact: pd.DataFrame, quality: pd.DataFrame) -> None:
    cuit_informed = fact["cuit_cuil_norm"].ne("")
    cuit_digits = fact["cuit_cuil_norm"].str.fullmatch(r"\d+")
    cuit_valid = fact["cuit_cuil_norm"].str.fullmatch(r"\d{11}")
    invalid_cuit_chars = int((cuit_informed & ~cuit_digits).sum())
    invalid_cuit_length = int((cuit_informed & ~cuit_valid).sum())
    validator.add("identificadores", "CUIT/CUIL normalizado solo con dígitos", "PASS" if invalid_cuit_chars == 0 else "FAIL", invalid_cuit_chars, 0)
    validator.add("identificadores", "CUIT/CUIL informado con 11 dígitos", "PASS" if invalid_cuit_length == 0 else "FAIL", invalid_cuit_length, 0)

    document_informed = fact["documento_norm"].ne("")
    document_digits = fact["documento_norm"].str.fullmatch(r"\d+")
    invalid_document_chars = int((document_informed & ~document_digits).sum())
    dot_zero = int(fact["documento_norm"].str.contains(r"\.0(?:$|\D)", regex=True).sum())
    punctuation = int(fact["cuit_cuil_norm"].str.contains(r"[.-]", regex=True).sum() + fact["documento_norm"].str.contains(r"[.-]", regex=True).sum())
    validator.add("identificadores", "Documento normalizado solo con dígitos", "PASS" if invalid_document_chars == 0 else "FAIL", invalid_document_chars, 0)
    validator.add("identificadores", "Documento normalizado sin sufijo .0", "PASS" if dot_zero == 0 else "FAIL", dot_zero, 0)
    validator.add("identificadores", "Identificadores normalizados sin puntos ni guiones", "PASS" if punctuation == 0 else "FAIL", punctuation, 0)

    high = fact["calidad_identificacion"].eq("alta")
    invalid_high = int((high & ~cuit_valid).sum())
    validator.add("calidad_identificacion", "Calidad alta respaldada por CUIT/CUIL válido", "PASS" if invalid_high == 0 else "FAIL", invalid_high, 0)

    name = fact["productor_nombre"].ne("")
    medium = fact["calidad_identificacion"].eq("media")
    medium_support = name & (document_informed | fact["renspa"].ne("") | fact["adrema"].ne(""))
    invalid_medium = int((medium & ~medium_support).sum())
    validator.add("calidad_identificacion", "Calidad media respaldada por nombre y clave complementaria", "PASS" if invalid_medium == 0 else "FAIL", invalid_medium, 0)

    low = fact["calidad_identificacion"].eq("baja")
    weak_only = name & ~cuit_valid & ~document_informed & fact["renspa"].eq("") & fact["adrema"].eq("")
    invalid_low = int((low & ~weak_only).sum())
    validator.add("calidad_identificacion", "Calidad baja consistente con identificación débil", "PASS" if invalid_low == 0 else "WARN", invalid_low, 0)

    pending_count = int(fact["calidad_identificacion"].eq("pendiente").sum())
    validator.add("calidad_identificacion", "Registros pendientes", "PASS" if pending_count == 0 else "WARN", pending_count, 0)

    empty_name = fact["productor_nombre"].eq("")
    alerted_missing_id = set(quality.loc[quality["alerta_tipo"].eq("sin_identificador"), "entrega_id"])
    empty_name_without_alert = int((empty_name & ~fact["entrega_id"].isin(alerted_missing_id)).sum())
    validator.add("identificadores", "Productor informado o vacío con alerta", "PASS" if empty_name_without_alert == 0 else "FAIL", empty_name_without_alert, 0)


def validate_coverage(validator: Validator, fact: pd.DataFrame) -> None:
    observed = {
        "CUIT/CUIL válido": int(fact["cuit_cuil_norm"].str.fullmatch(r"\d{11}").sum()),
        "Documento": int(fact["documento_norm"].ne("").sum()),
        "RENSPA": int(fact["renspa"].ne("").sum()),
        "ADREMA": int(fact["adrema"].ne("").sum()),
    }
    validator.compare("cobertura", "Cobertura de identificadores", observed, EXPECTED_COVERAGE, "WARN")


def validate_duplicates(validator: Validator, fact: pd.DataFrame, quality: pd.DataFrame) -> None:
    possible = quality[quality["alerta_tipo"].eq("posible_duplicado")]
    possible_count = len(possible)
    validator.add(
        "duplicados", "Posibles duplicados conservados y marcados", "WARN" if possible_count else "PASS",
        possible_count, EXPECTED_ALERT_TYPES["posible_duplicado"],
        "Es una advertencia de conciliación; no implica eliminación ni entrega_id repetido.",
    )
    missing_in_fact = int((~possible["entrega_id"].isin(fact["entrega_id"])).sum())
    validator.add("duplicados", "Marcas de duplicado referidas a filas conservadas", "PASS" if missing_in_fact == 0 else "FAIL", missing_in_fact, 0)


def validate_values_and_source(validator: Validator, fact: pd.DataFrame) -> None:
    for column, label in (("cantidad", "cantidad"), ("monto_estimado", "monto_estimado")):
        informed = fact[column].ne("")
        numeric = pd.to_numeric(fact[column], errors="coerce")
        invalid = int((informed & numeric.isna()).sum())
        validator.add("valores", f"{label} numérico o nulo", "PASS" if invalid == 0 else "FAIL", invalid, 0)

    invalid_origin = int((fact["origen_dato"] != "entregas_emergencia_excel").sum())
    validator.add("fuente", "origen_dato estandarizado", "PASS" if invalid_origin == 0 else "FAIL", invalid_origin, 0, 'Valor esperado: "entregas_emergencia_excel".')
    empty_file = int(fact["fuente_archivo"].eq("").sum())
    empty_sheet = int(fact["fuente_hoja"].eq("").sum())
    empty_row = int(fact["source_row_number"].eq("").sum())
    invalid_row = int((fact["source_row_number"].ne("") & pd.to_numeric(fact["source_row_number"], errors="coerce").isna()).sum())
    validator.add("fuente", "fuente_archivo informado", "PASS" if empty_file == 0 else "FAIL", empty_file, 0)
    validator.add("fuente", "fuente_hoja informada", "PASS" if empty_sheet == 0 else "FAIL", empty_sheet, 0)
    validator.add("fuente", "source_row_number informado y numérico", "PASS" if empty_row + invalid_row == 0 else "FAIL", empty_row + invalid_row, 0)


def global_status(checks: pd.DataFrame) -> str:
    states = set(checks["estado"])
    if "FAIL" in states:
        return "FAIL"
    if "WARN" in states:
        return "WARN"
    return "PASS"


def write_report(
    checks: pd.DataFrame,
    fact: pd.DataFrame | None,
    quality: pd.DataFrame | None,
    files_read: list[str],
) -> None:
    status = global_status(checks)
    state_counts = checks["estado"].value_counts().to_dict()
    suitable = status != "FAIL"
    recommendation = "apta para integración local con advertencias" if suitable else "no apta por fallas estructurales"

    lines = [
        "# Validación de entregas normalizadas", "",
        f"- **Fecha de ejecución:** {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"- **Archivos leídos:** {', '.join(files_read) or 'ninguno'}",
        f"- **Estado global:** **{status}**",
        f"- **Conclusión:** **{recommendation}**.",
        f"- **Checks:** PASS {state_counts.get('PASS', 0)}; WARN {state_counts.get('WARN', 0)}; FAIL {state_counts.get('FAIL', 0)}.", "",
    ]
    if fact is None or quality is None:
        lines.extend(["## Resultado", "", "No fue posible realizar las validaciones de contenido porque falta al menos un insumo obligatorio.", ""])
    else:
        years = counts(fact["anio"])
        providers = counts(fact["proveedor"])
        id_quality = counts(fact["calidad_identificacion"])
        alert_types = counts(quality["alerta_tipo"])
        coverage = {
            "CUIT/CUIL válido": int(fact["cuit_cuil_norm"].str.fullmatch(r"\d{11}").sum()),
            "Documento": int(fact["documento_norm"].ne("").sum()),
            "RENSPA": int(fact["renspa"].ne("").sum()),
            "ADREMA": int(fact["adrema"].ne("").sum()),
        }
        lines.extend([
            "## Resumen observado", "",
            f"- Filas normalizadas: **{len(fact)}**.",
            f"- entrega_id únicos: **{fact['entrega_id'].nunique()}**.",
            f"- Filas de alertas: **{len(quality)}**.",
            f"- Posibles duplicados marcados: **{alert_types.get('posible_duplicado', 0)}**.", "",
            "## Años detectados", "", "| Año | Filas |", "|---:|---:|",
        ])
        for label in sorted(years):
            lines.append(f"| {label or 'Sin dato'} | {years[label]} |")
        lines.extend(["", "Las filas 2023 se mantienen en 2023 por prioridad de la fecha de registro. Su presencia en archivos de la campaña/carpeta 2024 es una advertencia de trazabilidad, no un error de recodificación.", "",
                      "## Proveedores", "", "| Proveedor | Filas |", "|---|---:|"])
        for label, count_value in providers.items():
            lines.append(f"| {label or 'Sin dato'} | {count_value} |")
        lines.extend(["", "## Calidad de identificación", "", "| Calidad | Filas |", "|---|---:|"])
        for label in ["alta", "media", "baja", "pendiente"]:
            lines.append(f"| {label} | {id_quality.get(label, 0)} |")
        lines.extend(["", "## Cobertura", "", "| Identificador | Filas |", "|---|---:|"])
        for label, count_value in coverage.items():
            lines.append(f"| {label} | {count_value} |")
        lines.extend(["", "## Alertas principales", "", "| Alerta | Filas |", "|---|---:|"])
        for label, count_value in sorted(alert_types.items(), key=lambda item: (-item[1], item[0])):
            lines.append(f"| {label} | {count_value} |")

    lines.extend(["", "## Checks WARN y FAIL", "", "| Check | Estado | Descripción | Observado | Esperado |", "|---|---|---|---|---|"])
    relevant = checks[checks["estado"].isin(["WARN", "FAIL"])]
    if relevant.empty:
        lines.append("| — | PASS | No hay advertencias ni fallas | — | — |")
    else:
        for _, row in relevant.iterrows():
            description = str(row["descripcion"]).replace("|", "/")
            observed = str(row["valor_observado"]).replace("|", "/")
            expected = str(row["valor_esperado"]).replace("|", "/")
            lines.append(f"| {row['check_id']} | {row['estado']} | {description} | {observed} | {expected} |")

    lines.extend(["", "## Recomendación para Ficha Productor", ""])
    if suitable:
        lines.extend([
            "La base queda **apta para integración local con advertencias**. Antes de una integración productiva se recomienda:", "",
            "1. Conciliar los registros marcados como posibles duplicados entre hojas operativas y de rendición.",
            "2. Mantener 2023 como año de las filas cuya fecha corresponde a 2023, documentando su origen en archivos 2024.",
            "3. Revisar productos no inferidos y CUIT/CUIL originales inválidos.",
            "4. Vincular primero por CUIT/CUIL válido; usar documento, RENSPA y ADREMA como claves complementarias.",
            "5. Mantener trazabilidad mediante entrega_id, archivo, hoja y número de fila.",
        ])
    else:
        lines.append("La base queda **no apta por fallas estructurales**. Deben resolverse todos los checks FAIL antes de integrarla.")
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    validator = Validator()
    all_files_exist = validate_files(validator)
    fact: pd.DataFrame | None = None
    quality: pd.DataFrame | None = None
    files_read: list[str] = []

    if all_files_exist:
        fact = read_csv_text(FACT_PATH)
        quality = read_csv_text(QUALITY_PATH)
        TRANSFORM_REPORT_PATH.read_text(encoding="utf-8")
        files_read = [FACT_PATH.name, QUALITY_PATH.name, TRANSFORM_REPORT_PATH.name]
        validate_structure(validator, fact, quality)
        if set(FACT_COLUMNS).issubset(fact.columns) and set(QUALITY_COLUMNS).issubset(quality.columns):
            validate_counts_and_ids(validator, fact, quality)
            validate_years(validator, fact)
            validate_distributions(validator, fact, quality)
            validate_identification_rules(validator, fact, quality)
            validate_coverage(validator, fact)
            validate_duplicates(validator, fact, quality)
            validate_values_and_source(validator, fact)

    checks = pd.DataFrame(validator.checks, columns=[
        "check_id", "categoria", "descripcion", "estado",
        "valor_observado", "valor_esperado", "detalle",
    ])
    checks.to_csv(CHECKS_PATH, index=False, encoding="utf-8-sig")
    write_report(checks, fact, quality, files_read)
    status = global_status(checks)
    state_counts = checks["estado"].value_counts().to_dict()
    print(
        f"Validación finalizada: estado {status}; "
        f"PASS={state_counts.get('PASS', 0)}, WARN={state_counts.get('WARN', 0)}, "
        f"FAIL={state_counts.get('FAIL', 0)}."
    )
    print(f"Salidas: {CHECKS_PATH.name}, {REPORT_PATH.name}")


if __name__ == "__main__":
    main()
