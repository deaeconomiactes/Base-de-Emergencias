"""Transforma el Excel DDJJ/trámites 2023 a tablas CSV normalizadas.

La fuente se abre exclusivamente en modo lectura. Ningún registro se descarta
por problemas de calidad: los casos observados se conservan y se acompañan de
banderas `dq_*` y trazabilidad hasta la fila original.

Ejecución desde la raíz del repositorio:
    python scripts/14_transform_ddjj_2023_excel.py
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

import openpyxl


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = (
    PROJECT_ROOT
    / "data_raw"
    / "ddjj_2023_excel"
    / "original"
    / "Informes Tramites Emerg. Agrop - Actualizado 21052026.xlsx"
)
DEFAULT_OUTPUT_DIR = (
    PROJECT_ROOT / "data_processed" / "ddjj_2023_excel" / "normalized"
)
ORIGEN_DATO = "ddjj_2023_excel"

MAIN_LIVESTOCK_SHEETS = {
    "GANADERIA - Bovinos_Buf": "bovinos_bufalinos",
    "GANADERIA - Ovina": "ovinos_caprinos",
    "GANADERIA - Porcinos": "porcinos",
    "GANADERIA - Equinos": "equinos",
}

ADDITIONAL_LIVESTOCK_SHEETS = {
    "GANADERIA - Bovinos Datos Adic": "bovinos_bufalinos",
    "GANADERIA - Bovinos Nota Fucosa": "bovinos_bufalinos",
    "GANADERIA - Ovina Datos A": "ovinos_caprinos",
    "GANADERIA - Porcinos Datos Adic": "porcinos",
    "GANADERIA - Equinos Datos Adic.": "equinos",
}


@dataclass
class SheetData:
    name: str
    header_row: int | None
    headers: list[str | None]
    rows: list[tuple[int, list[Any]]]


def is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def clean_text(value: Any) -> str | None:
    if is_blank(value):
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return re.sub(r"\s+", " ", str(value).strip()) or None


def canonical(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]", "", text.lower())


def normalize_key(value: Any) -> str | None:
    text = clean_text(value)
    return re.sub(r"\.0$", "", text).strip() if text else None


def normalize_cuit(value: Any) -> str | None:
    text = clean_text(value)
    if text is None:
        return None
    digits = re.sub(r"\D", "", text)
    return digits or None


def valid_cuit(value: Any) -> bool:
    digits = normalize_cuit(value) or ""
    if len(digits) != 11:
        return False
    multipliers = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
    verifier = 11 - sum(int(digits[i]) * multipliers[i] for i in range(10)) % 11
    verifier = 0 if verifier == 11 else 9 if verifier == 10 else verifier
    return verifier == int(digits[-1])


def parse_number(value: Any) -> int | float | None:
    if is_blank(value) or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        text = str(value).strip().replace(" ", "")
        if "," in text and "." in text:
            text = text.replace(".", "").replace(",", ".") if text.rfind(",") > text.rfind(".") else text.replace(",", "")
        elif "," in text:
            text = text.replace(",", ".")
        try:
            number = float(text)
        except ValueError:
            return None
    if not math.isfinite(number):
        return None
    return int(number) if number.is_integer() else number


def date_iso(value: Any) -> str:
    if is_blank(value):
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = clean_text(value) or ""
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return text


def year_from_value(value: Any) -> int | None:
    if isinstance(value, (datetime, date)):
        return value.year
    text = clean_text(value)
    if not text:
        return None
    match = re.search(r"(?:19|20)\d{2}", text)
    return int(match.group(0)) if match else None


def normalize_bool(value: Any) -> bool | None:
    if is_blank(value):
        return None
    normalized = canonical(value)
    if normalized in {"1", "si", "s", "true", "verdadero", "yes", "incluido"}:
        return True
    if normalized in {"0", "no", "n", "false", "falso", "excluido"}:
        return False
    return None


def stable_productor_id(identity: str) -> str:
    digest = hashlib.sha256(f"{ORIGEN_DATO}|{identity}".encode("utf-8")).hexdigest()
    return f"prod_2023_{digest[:16]}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def find_column(headers: Sequence[str | None], candidates: Iterable[str]) -> int | None:
    expected = {canonical(candidate) for candidate in candidates}
    return next((index for index, header in enumerate(headers) if canonical(header) in expected), None)


def find_columns(headers: Sequence[str | None], candidate: str) -> list[int]:
    expected = canonical(candidate)
    return [index for index, header in enumerate(headers) if canonical(header) == expected]


def find_key_column(headers: Sequence[str | None]) -> int | None:
    exact = find_column(headers, ("Tramite Id", "tramiteId", "TRAMITE_ID"))
    if exact is not None:
        return exact
    return next(
        (
            index
            for index, header in enumerate(headers)
            if "tramite" in canonical(header) and canonical(header).endswith("id")
        ),
        None,
    )


def get_cell(row: Sequence[Any], index: int | None) -> Any:
    return row[index] if index is not None and index < len(row) else None


def source_value(sheet: SheetData, row: Sequence[Any], *candidates: str) -> Any:
    return get_cell(row, find_column(sheet.headers, candidates))


def json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        return clean_text(value)
    return value


def read_workbook(path: Path) -> dict[str, SheetData]:
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    result: dict[str, SheetData] = {}
    try:
        for worksheet in workbook.worksheets:
            raw_rows = list(worksheet.iter_rows(values_only=True))
            header_row: int | None = None
            headers: list[str | None] = []
            for row_number, row in enumerate(raw_rows[:20], start=1):
                if any(not is_blank(value) for value in row):
                    header_row = row_number
                    headers = [clean_text(value) for value in row]
                    break
            data_rows: list[tuple[int, list[Any]]] = []
            if header_row is not None:
                for row_number, row in enumerate(raw_rows[header_row:], start=header_row + 1):
                    if any(not is_blank(value) for value in row):
                        padded = list(row) + [None] * max(0, len(headers) - len(row))
                        data_rows.append((row_number, padded[: len(headers)]))
            result[canonical(worksheet.title)] = SheetData(worksheet.title, header_row, headers, data_rows)
    finally:
        workbook.close()
    return result


def get_sheet(sheets: dict[str, SheetData], name: str, warnings: list[str]) -> SheetData | None:
    sheet = sheets.get(canonical(name))
    if sheet is None:
        warnings.append(f"Falta la hoja esperada: {name}")
    return sheet


def normalize_activity(value: Any) -> str:
    original = clean_text(value)
    if original is None:
        return ""
    code = canonical(original)
    if code.startswith("ga"):
        return "ganaderia"
    if code.startswith("ag"):
        return "agricultura"
    if code.startswith("ho"):
        return "horticultura"
    if code.startswith("fo"):
        return "forestal"
    if code.startswith(("mix", "ma", "mg")):
        return "mixta"
    if code.startswith("ot"):
        return "otros"
    return original.casefold()


CATEGORY_MAP = {
    "vaca": "vacas", "vacas": "vacas", "vacasviejas": "vacas_viejas",
    "toro": "toros", "toros": "toros", "torito": "toritos", "toritos": "toritos",
    "ternero": "terneros", "terneros": "terneros", "ternera": "terneras", "terneras": "terneras",
    "vaquillona": "vaquillonas", "vaquillonas": "vaquillonas", "vaquilla": "vaquillas", "vaquillas": "vaquillas",
    "novillito": "novillitos", "novillitos": "novillitos", "novillo": "novillos", "novillos": "novillos",
    "novillosbueyes": "novillos_bueyes", "bueyes": "bueyes", "bovino": "bovinos", "bufalos": "bufalinos",
    "oveja": "ovejas", "ovejas": "ovejas", "carnero": "carneros", "carneros": "carneros",
    "cordero": "corderos", "corderos": "corderos", "corderosas": "corderos_as",
    "borrego": "borregos", "borregos": "borregos", "borregosas": "borregos_as", "borregas": "borregas",
    "cabra": "cabras", "cabras": "cabras", "cabrito": "cabritos", "cabritos": "cabritos",
    "cabritosasy": "cabritos_as", "cabritosas": "cabritos_as", "chivo": "chivos", "chivos": "chivos",
    "cerda": "cerdas", "cerdas": "cerdas", "lechon": "lechones", "lechones": "lechones",
    "cachorro": "cachorros", "cachorros": "cachorros", "capon": "capones", "capones": "capones",
    "padrillo": "padrillos", "padrillos": "padrillos", "caballo": "caballos", "caballos": "caballos",
    "yegua": "yeguas", "yeguas": "yeguas", "potrillo": "potrillos", "potrillos": "potrillos",
    "potrillosas": "potrillos_as", "mulas": "mulas", "asnos": "asnos",
}


def normalize_category(value: Any) -> str:
    original = clean_text(value)
    if original is None:
        return ""
    return CATEGORY_MAP.get(canonical(original), original.casefold())


def write_csv(path: Path, fieldnames: Sequence[str], rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def transform_tramites(
    sheet: SheetData | None,
    source_file: str,
    warnings: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, dict[str, Any]], set[str]]:
    dim_rows: list[dict[str, Any]] = []
    fact_rows: list[dict[str, Any]] = []
    main_by_key: dict[str, dict[str, Any]] = {}
    if sheet is None:
        return dim_rows, fact_rows, main_by_key, set()

    key_index = find_key_column(sheet.headers)
    cuit_index = find_column(sheet.headers, ("CUIT", "CUIT/CUIL", "cuit_cuil"))
    name_index = find_column(sheet.headers, ("Razón Social", "Razon Social", "productor_nombre"))
    date_index = find_column(sheet.headers, ("Fecha de Creación", "Fecha Creacion"))
    state_index = find_column(sheet.headers, ("Estado Actual", "estado"))
    expired_index = find_column(sheet.headers, ("Caduco", "caducidad"))
    type_index = find_column(sheet.headers, ("Tipo Certificado",))
    number_index = find_column(sheet.headers, ("Numero Certificado", "Número Certificado"))
    from_index = find_column(sheet.headers, ("Fecha Desde",))
    to_index = find_column(sheet.headers, ("Fecha Hasta",))
    annul_index = find_column(sheet.headers, ("Fecha Anulación", "Fecha Anulacion"))
    if key_index is None:
        warnings.append("Tramites no contiene una columna de clave reconocible.")

    producer_groups: dict[str, dict[str, Any]] = {}
    for row_number, row in sheet.rows:
        tramite_id = normalize_key(get_cell(row, key_index))
        cuit = normalize_cuit(get_cell(row, cuit_index))
        name = clean_text(get_cell(row, name_index)) or ""
        identity = f"cuit:{cuit}" if cuit else f"fallback:{tramite_id or f'row:{row_number}'}"
        productor_id = stable_productor_id(identity)
        group = producer_groups.setdefault(
            identity,
            {
                "productor_id_2023": productor_id,
                "cuit_cuil": cuit or "",
                "productor_nombre": name,
                "cuit_valido": valid_cuit(cuit),
                "cantidad_tramites": 0,
                "origen_dato": ORIGEN_DATO,
                "source_file": source_file,
            },
        )
        group["cantidad_tramites"] += 1
        if not group["productor_nombre"] and name:
            group["productor_nombre"] = name

        fecha = get_cell(row, date_index)
        fact = {
            "tramite_id": tramite_id or "",
            "productor_id_2023": productor_id,
            "cuit_cuil": cuit or "",
            "productor_nombre": name,
            "fecha_presentacion": date_iso(fecha),
            "anio_presentacion": year_from_value(fecha) or "",
            "estado_tramite": clean_text(get_cell(row, state_index)) or "",
            "caducidad": clean_text(get_cell(row, expired_index)) or "",
            "tipo_certificado": clean_text(get_cell(row, type_index)) or "",
            "numero_certificado": clean_text(get_cell(row, number_index)) or "",
            "certificado_fecha_desde": date_iso(get_cell(row, from_index)),
            "certificado_fecha_hasta": date_iso(get_cell(row, to_index)),
            "fecha_anulacion": date_iso(get_cell(row, annul_index)),
            "origen_dato": ORIGEN_DATO,
            "source_file": source_file,
            "source_sheet": sheet.name,
            "source_row_number": row_number,
        }
        fact_rows.append(fact)
        if tramite_id:
            if tramite_id in main_by_key:
                warnings.append(f"Tramite Id duplicado preservado: {tramite_id}")
            else:
                main_by_key[tramite_id] = fact

    dim_rows = sorted(producer_groups.values(), key=lambda row: row["productor_id_2023"])
    return dim_rows, fact_rows, main_by_key, set(main_by_key)


def transform_adremas(
    sheet: SheetData | None,
    main_keys: set[str],
    source_file: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows_out: list[dict[str, Any]] = []
    if sheet is None:
        return rows_out, {"keys": set(), "orphan_keys": set(), "orphan_rows": 0, "negative_keys": set(), "negative_values": 0, "duplicate_keys": set(), "duplicate_pairs": 0, "duplicate_rows": 0}

    key_index = find_key_column(sheet.headers)
    adrema_index = find_column(sheet.headers, ("adrema",))
    surface_index = find_column(sheet.headers, ("superficie",))
    seccion_indices = find_columns(sheet.headers, "seccion")
    pairs = Counter(
        (
            normalize_key(get_cell(row, key_index)),
            clean_text(get_cell(row, adrema_index)),
        )
        for _, row in sheet.rows
        if normalize_key(get_cell(row, key_index)) and clean_text(get_cell(row, adrema_index))
    )
    duplicate_keys = {key for (key, _), count in pairs.items() if count > 1 and key}
    keys: set[str] = set()
    orphan_keys: set[str] = set()
    negative_keys: set[str] = set()
    orphan_rows = negative_values = 0

    for row_number, row in sheet.rows:
        tramite_id = normalize_key(get_cell(row, key_index))
        adrema = clean_text(get_cell(row, adrema_index))
        superficie_raw = get_cell(row, surface_index)
        superficie = parse_number(superficie_raw)
        orphan = bool(tramite_id and tramite_id not in main_keys)
        negative = superficie is not None and superficie < 0
        if tramite_id:
            keys.add(tramite_id)
        if orphan:
            orphan_rows += 1
            orphan_keys.add(tramite_id)
        if negative:
            negative_values += 1
            if tramite_id:
                negative_keys.add(tramite_id)
        duplicate = bool(tramite_id and adrema and pairs[(tramite_id, adrema)] > 1)

        rows_out.append(
            {
                "tramite_id": tramite_id or "",
                "adrema": adrema or "",
                "renspa": clean_text(source_value(sheet, row, "renspa")) or "",
                "actividad_original": clean_text(source_value(sheet, row, "tipoActividad")) or "",
                "actividad_normalizada_preliminar": normalize_activity(source_value(sheet, row, "tipoActividad")),
                "departamento": clean_text(source_value(sheet, row, "departamentoDescr", "departamento")) or "",
                "municipio": clean_text(source_value(sheet, row, "municipioDesc", "municipio")) or "",
                "localidad": "",
                "paraje": clean_text(source_value(sheet, row, "parajeDesc", "paraje")) or "",
                "superficie": superficie if superficie is not None else "",
                "pertenencia": clean_text(source_value(sheet, row, "pertenencia")) or "",
                "incluido_emergencia_agropecuaria": normalize_bool(source_value(sheet, row, "incluidoEmergAgrop")),
                "incluido_emergencia_agropecuaria_original": clean_text(source_value(sheet, row, "incluidoEmergAgrop")) or "",
                "seccion_1_original": clean_text(get_cell(row, seccion_indices[0])) if seccion_indices else "",
                "seccion_2_original": clean_text(get_cell(row, seccion_indices[1])) if len(seccion_indices) > 1 else "",
                "origen_dato": ORIGEN_DATO,
                "source_file": source_file,
                "source_sheet": sheet.name,
                "source_row_number": row_number,
                "dq_tramite_huerfano": orphan,
                "dq_superficie_nula": is_blank(superficie_raw),
                "dq_superficie_cero": superficie == 0 if superficie is not None else False,
                "dq_superficie_negativa": negative,
                "dq_superficie_no_numerica": not is_blank(superficie_raw) and superficie is None,
                "dq_adrema_duplicada_en_tramite": duplicate,
            }
        )

    return rows_out, {
        "keys": keys,
        "orphan_keys": orphan_keys,
        "orphan_rows": orphan_rows,
        "negative_keys": negative_keys,
        "negative_values": negative_values,
        "duplicate_keys": duplicate_keys,
        "duplicate_pairs": sum(count > 1 for count in pairs.values()),
        "duplicate_rows": sum(count - 1 for count in pairs.values() if count > 1),
    }


def transform_agriculture(
    sheet: SheetData | None,
    main_keys: set[str],
    source_file: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows_out: list[dict[str, Any]] = []
    keys: set[str] = set()
    orphan_keys: set[str] = set()
    negative_keys: set[str] = set()
    orphan_rows = negative_values = 0
    if sheet is None:
        return rows_out, {"keys": keys, "orphan_keys": orphan_keys, "orphan_rows": 0, "negative_keys": negative_keys, "negative_values": 0}

    key_index = find_key_column(sheet.headers)
    species_id_index = find_column(sheet.headers, ("especieId",))
    species_index = find_column(sheet.headers, ("especieDesc", "especie", "cultivo"))
    planted_index = find_column(sheet.headers, ("superficieSembrada",))
    affected_index = find_column(sheet.headers, ("superficieAfectada",))
    estimated_index = find_column(sheet.headers, ("produccionEstimada",))
    obtained_index = find_column(sheet.headers, ("produccionObtenida",))

    for row_number, row in sheet.rows:
        tramite_id = normalize_key(get_cell(row, key_index))
        species = clean_text(get_cell(row, species_index))
        planted_raw = get_cell(row, planted_index)
        affected_raw = get_cell(row, affected_index)
        planted = parse_number(planted_raw)
        affected = parse_number(affected_raw)
        orphan = bool(tramite_id and tramite_id not in main_keys)
        planted_negative = planted is not None and planted < 0
        affected_negative = affected is not None and affected < 0
        if tramite_id:
            keys.add(tramite_id)
        if orphan:
            orphan_rows += 1
            orphan_keys.add(tramite_id)
        if planted_negative or affected_negative:
            negative_values += int(planted_negative) + int(affected_negative)
            if tramite_id:
                negative_keys.add(tramite_id)

        rows_out.append(
            {
                "tramite_id": tramite_id or "",
                "rubro": "agricultura",
                "producto": species or "",
                "especie_cultivo": species or "",
                "especie_id_original": clean_text(get_cell(row, species_id_index)) or "",
                "superficie_sembrada": planted if planted is not None else "",
                "superficie_afectada": affected if affected is not None else "",
                "produccion_estimada": parse_number(get_cell(row, estimated_index)) if not is_blank(get_cell(row, estimated_index)) else "",
                "produccion_obtenida": parse_number(get_cell(row, obtained_index)) if not is_blank(get_cell(row, obtained_index)) else "",
                "unidad_medida": "",
                "estado_cultivo_original": clean_text(source_value(sheet, row, "estadoCultivoDesc")) or "",
                "lote_exportacion_original": clean_text(source_value(sheet, row, "loteExportacion")) or "",
                "origen_dato": ORIGEN_DATO,
                "source_file": source_file,
                "source_sheet": sheet.name,
                "source_row_number": row_number,
                "dq_tramite_huerfano": orphan,
                "dq_superficie_afectada_negativa": affected_negative,
                "dq_superficie_sembrada_negativa": planted_negative,
                "dq_superficie_afectada_no_numerica": not is_blank(affected_raw) and affected is None,
                "dq_superficie_sembrada_no_numerica": not is_blank(planted_raw) and planted is None,
            }
        )

    return rows_out, {
        "keys": keys,
        "orphan_keys": orphan_keys,
        "orphan_rows": orphan_rows,
        "negative_keys": negative_keys,
        "negative_values": negative_values,
    }


def transform_livestock(
    sheets: dict[str, SheetData],
    main_keys: set[str],
    source_file: str,
    warnings: list[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows_out: list[dict[str, Any]] = []
    main_livestock_keys: set[str] = set()
    all_keys: set[str] = set()
    orphan_keys: set[str] = set()
    negative_keys: set[str] = set()
    mortality_gt_keys: set[str] = set()
    orphan_rows = negative_values = mortality_gt_rows = 0

    for expected_name, species in MAIN_LIVESTOCK_SHEETS.items():
        sheet = get_sheet(sheets, expected_name, warnings)
        if sheet is None:
            continue
        key_index = find_key_column(sheet.headers)
        category_desc_index = find_column(sheet.headers, ("descripcionAnimalDesc",))
        category_code_index = find_column(sheet.headers, ("descripcionAnimal",))
        quantity_index = find_column(sheet.headers, ("cantidad",))
        mortality_index = find_column(sheet.headers, ("mortandad",))
        for row_number, row in sheet.rows:
            tramite_id = normalize_key(get_cell(row, key_index))
            category = clean_text(get_cell(row, category_desc_index)) or clean_text(get_cell(row, category_code_index))
            quantity_raw = get_cell(row, quantity_index)
            mortality_raw = get_cell(row, mortality_index)
            quantity = parse_number(quantity_raw)
            mortality = parse_number(mortality_raw)
            orphan = bool(tramite_id and tramite_id not in main_keys)
            quantity_negative = quantity is not None and quantity < 0
            mortality_negative = mortality is not None and mortality < 0
            mortality_gt = quantity is not None and mortality is not None and mortality > quantity
            if tramite_id:
                all_keys.add(tramite_id)
                main_livestock_keys.add(tramite_id)
            if orphan:
                orphan_rows += 1
                orphan_keys.add(tramite_id)
            if mortality_gt:
                mortality_gt_rows += 1
                if tramite_id:
                    mortality_gt_keys.add(tramite_id)

            rows_out.append(
                {
                    "tramite_id": tramite_id or "",
                    "especie": species,
                    "categoria_original": category or "",
                    "categoria_normalizada_preliminar": normalize_category(category),
                    "cantidad": quantity if quantity is not None else "",
                    "mortandad": mortality if mortality is not None else "",
                    "superficie_uso": "",
                    "superficie_afectada": "",
                    "datos_adicionales_json": "",
                    "origen_dato": ORIGEN_DATO,
                    "source_file": source_file,
                    "source_sheet": sheet.name,
                    "source_row_number": row_number,
                    "dq_tramite_huerfano": orphan,
                    "dq_cantidad_nula": is_blank(quantity_raw),
                    "dq_cantidad_cero": quantity == 0 if quantity is not None else False,
                    "dq_cantidad_negativa": quantity_negative,
                    "dq_cantidad_no_numerica": not is_blank(quantity_raw) and quantity is None,
                    "dq_mortandad_nula": is_blank(mortality_raw),
                    "dq_mortandad_cero": mortality == 0 if mortality is not None else False,
                    "dq_mortandad_negativa": mortality_negative,
                    "dq_mortandad_no_numerica": not is_blank(mortality_raw) and mortality is None,
                    "dq_mortandad_mayor_cantidad": mortality_gt,
                    "dq_columna_sospechosa_equinos_porcinos": False,
                }
            )

    for expected_name, species in ADDITIONAL_LIVESTOCK_SHEETS.items():
        sheet = get_sheet(sheets, expected_name, warnings)
        if sheet is None:
            continue
        key_index = find_key_column(sheet.headers)
        normalized_sheet = canonical(sheet.name)
        suspicious_equine = "equinosdatosadic" in normalized_sheet and any(
            canonical(header).startswith("porcinos") for header in sheet.headers
        )
        if "bovinosdatosadic" in normalized_sheet:
            use_index = None
            affected_index = find_column(sheet.headers, ("superficieAfectada",))
            category = "datos adicionales"
        elif "ovinadatos" in normalized_sheet:
            use_index = find_column(sheet.headers, ("OVINOS_SUP_USO",))
            affected_index = find_column(sheet.headers, ("OVINOS_SUP_AFECTADA",))
            category = "datos adicionales"
        elif "porcinosdatosadic" in normalized_sheet or "equinosdatosadic" in normalized_sheet:
            use_index = find_column(sheet.headers, ("PORCINOS_SUP_USO",))
            affected_index = find_column(sheet.headers, ("PORCINOS_SUP_AFECTADA",))
            category = "datos adicionales"
        else:
            use_index = affected_index = None
            category = "nota fucosa"

        for row_number, row in sheet.rows:
            tramite_id = normalize_key(get_cell(row, key_index))
            use_raw = get_cell(row, use_index)
            affected_raw = get_cell(row, affected_index)
            surface_use = parse_number(use_raw)
            surface_affected = parse_number(affected_raw)
            orphan = bool(tramite_id and tramite_id not in main_keys)
            use_negative = surface_use is not None and surface_use < 0
            affected_negative = surface_affected is not None and surface_affected < 0
            if tramite_id:
                all_keys.add(tramite_id)
            if orphan:
                orphan_rows += 1
                orphan_keys.add(tramite_id)
            if use_negative or affected_negative:
                negative_values += int(use_negative) + int(affected_negative)
                if tramite_id:
                    negative_keys.add(tramite_id)

            additional: dict[str, Any] = {}
            for index, header in enumerate(sheet.headers):
                if is_blank(header) or index == key_index or is_blank(get_cell(row, index)):
                    continue
                additional[str(header)] = json_value(get_cell(row, index))

            rows_out.append(
                {
                    "tramite_id": tramite_id or "",
                    "especie": species,
                    "categoria_original": category,
                    "categoria_normalizada_preliminar": category.replace(" ", "_"),
                    "cantidad": "",
                    "mortandad": "",
                    "superficie_uso": surface_use if surface_use is not None else "",
                    "superficie_afectada": surface_affected if surface_affected is not None else "",
                    "datos_adicionales_json": json.dumps(additional, ensure_ascii=False, sort_keys=True),
                    "origen_dato": ORIGEN_DATO,
                    "source_file": source_file,
                    "source_sheet": sheet.name,
                    "source_row_number": row_number,
                    "dq_tramite_huerfano": orphan,
                    "dq_cantidad_nula": "",
                    "dq_cantidad_cero": "",
                    "dq_cantidad_negativa": "",
                    "dq_cantidad_no_numerica": "",
                    "dq_mortandad_nula": "",
                    "dq_mortandad_cero": "",
                    "dq_mortandad_negativa": "",
                    "dq_mortandad_no_numerica": "",
                    "dq_mortandad_mayor_cantidad": "",
                    "dq_columna_sospechosa_equinos_porcinos": suspicious_equine,
                }
            )

    return rows_out, {
        "keys": all_keys,
        "main_keys": main_livestock_keys,
        "orphan_keys": orphan_keys,
        "orphan_rows": orphan_rows,
        "negative_keys": negative_keys,
        "negative_values": negative_values,
        "mortality_gt_keys": mortality_gt_keys,
        "mortality_gt_rows": mortality_gt_rows,
    }


def transform_manifest(
    sheet: SheetData | None,
    main_keys: set[str],
    source_file: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows_out: list[dict[str, Any]] = []
    keys: set[str] = set()
    orphan_keys: set[str] = set()
    orphan_rows = 0
    if sheet is None:
        return rows_out, {"keys": keys, "orphan_keys": orphan_keys, "orphan_rows": 0}
    key_index = find_key_column(sheet.headers)
    for row_number, row in sheet.rows:
        tramite_id = normalize_key(get_cell(row, key_index))
        orphan = bool(tramite_id and tramite_id not in main_keys)
        if tramite_id:
            keys.add(tramite_id)
        if orphan:
            orphan_rows += 1
            orphan_keys.add(tramite_id)
        rows_out.append(
            {
                "tramite_id": tramite_id or "",
                "especie": clean_text(source_value(sheet, row, "especies")) or "",
                "categoria": clean_text(source_value(sheet, row, "codanimal")) or "",
                "cantidad_manifestada": parse_number(source_value(sheet, row, "totalExistencias")) if not is_blank(source_value(sheet, row, "totalExistencias")) else "",
                "fecha_manifestacion": "",
                "anio_manifestacion_original": clean_text(source_value(sheet, row, "Año", "Ano")) or "",
                "manifestacion_id_original": clean_text(source_value(sheet, row, "titulo")) or "",
                "codigo_especie_original": clean_text(source_value(sheet, row, "codespecies")) or "",
                "codigo_animal_original": clean_text(source_value(sheet, row, "codanimal")) or "",
                "origen_dato": ORIGEN_DATO,
                "source_file": source_file,
                "source_sheet": sheet.name,
                "source_row_number": row_number,
                "dq_tramite_huerfano": orphan,
            }
        )
    return rows_out, {"keys": keys, "orphan_keys": orphan_keys, "orphan_rows": orphan_rows}


def transform_insurance(
    sheet: SheetData | None,
    main_keys: set[str],
    source_file: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows_out: list[dict[str, Any]] = []
    keys: set[str] = set()
    orphan_keys: set[str] = set()
    orphan_rows = 0
    if sheet is None:
        return rows_out, {"keys": keys, "orphan_keys": orphan_keys, "orphan_rows": 0}
    key_index = find_key_column(sheet.headers)
    for row_number, row in sheet.rows:
        tramite_id = normalize_key(get_cell(row, key_index))
        orphan = bool(tramite_id and tramite_id not in main_keys)
        if tramite_id:
            keys.add(tramite_id)
        if orphan:
            orphan_rows += 1
            orphan_keys.add(tramite_id)
        rows_out.append(
            {
                "tramite_id": tramite_id or "",
                "evento_original": clean_text(source_value(sheet, row, "eventoDesc", "evento")) or "",
                "cultivo_original": clean_text(source_value(sheet, row, "cultivoDesc", "cultivo")) or "",
                "asistencia_original": clean_text(source_value(sheet, row, "asistencia")) or "",
                "entidad_original": clean_text(source_value(sheet, row, "Entidad", "entidad")) or "",
                "origen_dato": ORIGEN_DATO,
                "source_file": source_file,
                "source_sheet": sheet.name,
                "source_row_number": row_number,
                "dq_tramite_huerfano": orphan,
            }
        )
    return rows_out, {"keys": keys, "orphan_keys": orphan_keys, "orphan_rows": orphan_rows}


def build_quality(
    main_by_key: dict[str, dict[str, Any]],
    adrema: dict[str, Any],
    agriculture: dict[str, Any],
    livestock: dict[str, Any],
    manifest: dict[str, Any],
    insurance: dict[str, Any],
) -> list[dict[str, Any]]:
    all_orphans = (
        adrema["orphan_keys"]
        | agriculture["orphan_keys"]
        | livestock["orphan_keys"]
        | manifest["orphan_keys"]
        | insurance["orphan_keys"]
    )
    all_ids = set(main_by_key) | all_orphans
    negative_keys = adrema["negative_keys"] | agriculture["negative_keys"] | livestock["negative_keys"]
    rows: list[dict[str, Any]] = []
    for tramite_id in sorted(all_ids):
        main = main_by_key.get(tramite_id)
        is_main = main is not None
        year = main.get("anio_presentacion") if main else None
        cuit = main.get("cuit_cuil") if main else None
        rows.append(
            {
                "tramite_id": tramite_id,
                "dq_cuit_invalido": (not valid_cuit(cuit)) if is_main else "",
                "dq_fecha_fuera_2023": (bool(year) and int(year) != 2023) if is_main else "",
                "dq_estado_anulado": canonical(main.get("estado_tramite")) == "anulado" if is_main else "",
                "dq_adrema_faltante": tramite_id not in adrema["keys"] if is_main else "",
                "dq_tiene_adrema": tramite_id in adrema["keys"],
                "dq_tiene_agricultura": tramite_id in agriculture["keys"],
                "dq_tiene_ganaderia": tramite_id in livestock["main_keys"],
                "dq_tiene_tramite_huerfano_en_detalle": tramite_id in all_orphans,
                "dq_tiene_superficie_negativa": tramite_id in negative_keys,
                "dq_tiene_adrema_duplicada": tramite_id in adrema["duplicate_keys"],
                "dq_tiene_mortandad_mayor_cantidad": tramite_id in livestock["mortality_gt_keys"],
                "dq_numero_certificado_nulo": not bool(main.get("numero_certificado")) if is_main else "",
                "dq_fecha_presentacion_nula": not bool(main.get("fecha_presentacion")) if is_main else "",
                "origen_dato": ORIGEN_DATO,
            }
        )
    return rows


DIM_PRODUCTOR_FIELDS = (
    "productor_id_2023", "cuit_cuil", "productor_nombre", "cuit_valido",
    "cantidad_tramites", "origen_dato", "source_file",
)
FACT_DDJJ_FIELDS = (
    "tramite_id", "productor_id_2023", "cuit_cuil", "productor_nombre",
    "fecha_presentacion", "anio_presentacion", "estado_tramite", "caducidad",
    "tipo_certificado", "numero_certificado", "certificado_fecha_desde",
    "certificado_fecha_hasta", "fecha_anulacion", "origen_dato", "source_file",
    "source_sheet", "source_row_number",
)
ADREMA_FIELDS = (
    "tramite_id", "adrema", "renspa", "actividad_original", "actividad_normalizada_preliminar",
    "departamento", "municipio", "localidad", "paraje", "superficie", "pertenencia",
    "incluido_emergencia_agropecuaria", "incluido_emergencia_agropecuaria_original",
    "seccion_1_original", "seccion_2_original", "origen_dato", "source_file", "source_sheet",
    "source_row_number", "dq_tramite_huerfano", "dq_superficie_nula", "dq_superficie_cero",
    "dq_superficie_negativa", "dq_superficie_no_numerica", "dq_adrema_duplicada_en_tramite",
)
AGRICULTURE_FIELDS = (
    "tramite_id", "rubro", "producto", "especie_cultivo", "especie_id_original",
    "superficie_sembrada", "superficie_afectada", "produccion_estimada", "produccion_obtenida",
    "unidad_medida", "estado_cultivo_original", "lote_exportacion_original", "origen_dato",
    "source_file", "source_sheet", "source_row_number", "dq_tramite_huerfano",
    "dq_superficie_afectada_negativa", "dq_superficie_sembrada_negativa",
    "dq_superficie_afectada_no_numerica", "dq_superficie_sembrada_no_numerica",
)
LIVESTOCK_FIELDS = (
    "tramite_id", "especie", "categoria_original", "categoria_normalizada_preliminar",
    "cantidad", "mortandad", "superficie_uso", "superficie_afectada", "datos_adicionales_json",
    "origen_dato", "source_file", "source_sheet", "source_row_number", "dq_tramite_huerfano",
    "dq_cantidad_nula", "dq_cantidad_cero", "dq_cantidad_negativa", "dq_cantidad_no_numerica",
    "dq_mortandad_nula", "dq_mortandad_cero", "dq_mortandad_negativa",
    "dq_mortandad_no_numerica", "dq_mortandad_mayor_cantidad",
    "dq_columna_sospechosa_equinos_porcinos",
)
MANIFEST_FIELDS = (
    "tramite_id", "especie", "categoria", "cantidad_manifestada", "fecha_manifestacion",
    "anio_manifestacion_original", "manifestacion_id_original", "codigo_especie_original",
    "codigo_animal_original", "origen_dato", "source_file", "source_sheet", "source_row_number",
    "dq_tramite_huerfano",
)
INSURANCE_FIELDS = (
    "tramite_id", "evento_original", "cultivo_original", "asistencia_original", "entidad_original",
    "origen_dato", "source_file", "source_sheet", "source_row_number", "dq_tramite_huerfano",
)
QUALITY_FIELDS = (
    "tramite_id", "dq_cuit_invalido", "dq_fecha_fuera_2023", "dq_estado_anulado",
    "dq_adrema_faltante", "dq_tiene_adrema", "dq_tiene_agricultura", "dq_tiene_ganaderia",
    "dq_tiene_tramite_huerfano_en_detalle", "dq_tiene_superficie_negativa",
    "dq_tiene_adrema_duplicada", "dq_tiene_mortandad_mayor_cantidad",
    "dq_numero_certificado_nulo", "dq_fecha_presentacion_nula", "origen_dato",
)


def build_summary(
    source: Path,
    output_counts: dict[str, int],
    main_by_key: dict[str, dict[str, Any]],
    dim_rows: Sequence[dict[str, Any]],
    adrema: dict[str, Any],
    agriculture: dict[str, Any],
    livestock: dict[str, Any],
    manifest: dict[str, Any],
    insurance: dict[str, Any],
    warnings: Sequence[str],
) -> str:
    annulled = sum(canonical(row["estado_tramite"]) == "anulado" for row in main_by_key.values())
    outside_2023 = sum(bool(row["anio_presentacion"]) and int(row["anio_presentacion"]) != 2023 for row in main_by_key.values())
    negative_values = adrema["negative_values"] + agriculture["negative_values"] + livestock["negative_values"]
    orphan_rows = {
        "fact_adrema_establecimiento_2023.csv": adrema["orphan_rows"],
        "fact_agricultura_perdida_2023.csv": agriculture["orphan_rows"],
        "fact_ganaderia_declarada_2023.csv": livestock["orphan_rows"],
        "fact_manifestacion_existencias_2023.csv": manifest["orphan_rows"],
        "fact_seguro_agricola_2023.csv": insurance["orphan_rows"],
    }
    lines = [
        "# Resumen de transformación DDJJ/trámites 2023",
        "",
        f"- **Fecha/hora de transformación:** {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"- **Archivo fuente:** `{source.name}`",
        f"- **SHA256 fuente:** `{sha256_file(source)}`",
        f"- **Origen normalizado:** `{ORIGEN_DATO}`",
        "- **Modo:** transformación local; sin carga a TiDB.",
        "",
        "## Filas generadas",
        "",
        "| Tabla | Filas |",
        "| --- | ---: |",
    ]
    lines.extend(f"| `{name}` | {count} |" for name, count in output_counts.items())
    lines.extend(
        [
            "",
            "## Conteos principales",
            "",
            f"- Trámites únicos: **{len(main_by_key)}**.",
            f"- Productores únicos: **{len(dim_rows)}**.",
            f"- Trámites anulados: **{annulled}**.",
            f"- Trámites fuera de 2023: **{outside_2023}**.",
            f"- Trámites sin ADREMA: **{len(set(main_by_key) - adrema['keys'])}**.",
            f"- Pares `tramite_id + adrema` duplicados: **{adrema['duplicate_pairs']}** ({adrema['duplicate_rows']} filas excedentes).",
            f"- Valores de superficie negativos preservados: **{negative_values}**.",
            f"- Registros con mortandad mayor que cantidad: **{livestock['mortality_gt_rows']}**.",
            "",
            "## Registros huérfanos por tabla",
            "",
            "| Tabla | Filas huérfanas |",
            "| --- | ---: |",
        ]
    )
    lines.extend(f"| `{name}` | {count} |" for name, count in orphan_rows.items())
    lines.extend(
        [
            "",
            "## Advertencias metodológicas",
            "",
            "- `Numero Certificado` se conserva como identificador de certificado. No se interpreta como resolución, decreto ni evento normativo.",
            "- La vinculación con un evento o norma permanece pendiente. No se generó `bridge_ddjj_evento_normativo_2023.csv`.",
            "- Los trámites anulados y caducos se preservan; no fueron filtrados.",
            "- Los duplicados de ADREMA y los casos de mortandad mayor que cantidad se preservan y se marcan mediante banderas.",
            "- Las superficies de hojas ganaderas adicionales se guardan en filas independientes para evitar repetirlas sobre cada categoría animal.",
            "- Las columnas `PORCINOS_*` presentes en datos adicionales de Equinos se conservan con una bandera específica.",
            "- `ULTIMO_MANIFIESTO` solo informa año; no se fabricó una fecha de manifestación.",
            "- No cargar estas tablas a TiDB hasta completar la validación técnica e institucional.",
        ]
    )
    if warnings:
        lines.extend(["", "## Advertencias de ejecución", ""])
        lines.extend(f"- {warning}" for warning in sorted(set(warnings)))
    else:
        lines.extend(["", "## Advertencias de ejecución", "", "- No se detectaron hojas obligatorias faltantes durante esta ejecución."])
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Transformar el Excel DDJJ/trámites 2023.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.input if args.input.is_absolute() else PROJECT_ROOT / args.input
    output_dir = args.output_dir if args.output_dir.is_absolute() else PROJECT_ROOT / args.output_dir
    if not source.is_file():
        raise FileNotFoundError(f"No existe el Excel fuente: {source}")

    warnings: list[str] = []
    sheets = read_workbook(source)
    source_file = source.name
    tramites_sheet = get_sheet(sheets, "Tramites", warnings)
    dim_rows, ddjj_rows, main_by_key, main_keys = transform_tramites(tramites_sheet, source_file, warnings)
    if not main_keys:
        warnings.append("No se obtuvieron claves válidas desde Tramites; revisar la salida antes de usarla.")

    adrema_rows, adrema_summary = transform_adremas(get_sheet(sheets, "ADREMAS", warnings), main_keys, source_file)
    agriculture_rows, agriculture_summary = transform_agriculture(get_sheet(sheets, "PERDIDAS_PRODUCCION", warnings), main_keys, source_file)
    livestock_rows, livestock_summary = transform_livestock(sheets, main_keys, source_file, warnings)
    manifest_rows, manifest_summary = transform_manifest(get_sheet(sheets, "ULTIMO_MANIFIESTO", warnings), main_keys, source_file)
    insurance_rows, insurance_summary = transform_insurance(get_sheet(sheets, "Seguro Agricola", warnings), main_keys, source_file)
    quality_rows = build_quality(main_by_key, adrema_summary, agriculture_summary, livestock_summary, manifest_summary, insurance_summary)

    outputs = {
        "dim_productor_2023.csv": (DIM_PRODUCTOR_FIELDS, dim_rows),
        "fact_ddjj_tramite_2023.csv": (FACT_DDJJ_FIELDS, ddjj_rows),
        "fact_adrema_establecimiento_2023.csv": (ADREMA_FIELDS, adrema_rows),
        "fact_agricultura_perdida_2023.csv": (AGRICULTURE_FIELDS, agriculture_rows),
        "fact_ganaderia_declarada_2023.csv": (LIVESTOCK_FIELDS, livestock_rows),
        "fact_manifestacion_existencias_2023.csv": (MANIFEST_FIELDS, manifest_rows),
        "fact_seguro_agricola_2023.csv": (INSURANCE_FIELDS, insurance_rows),
        "fact_calidad_dato_2023.csv": (QUALITY_FIELDS, quality_rows),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, (fields, rows) in outputs.items():
        write_csv(output_dir / name, fields, rows)

    counts = {name: len(rows) for name, (_, rows) in outputs.items()}
    summary = build_summary(
        source, counts, main_by_key, dim_rows, adrema_summary, agriculture_summary,
        livestock_summary, manifest_summary, insurance_summary, warnings,
    )
    summary_path = output_dir / "transform_ddjj_2023_resumen.md"
    summary_path.write_text(summary, encoding="utf-8")

    print(f"Fuente leída correctamente: {source}")
    for name, count in counts.items():
        print(f"{name}: {count} filas")
    print(f"Resumen: {summary_path}")
    print("No se creó bridge_ddjj_evento_normativo_2023.csv")
    print("No se realizó ninguna carga a TiDB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
