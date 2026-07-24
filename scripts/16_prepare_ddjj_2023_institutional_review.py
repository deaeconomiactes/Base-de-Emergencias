"""Prepara extractos locales para la revisión institucional de DDJJ 2023.

El script no corrige ni elimina datos. Lee las tablas normalizadas y genera
copias selectivas con trazabilidad para discutir las advertencias antes de una
eventual carga a staging.

Ejecución desde la raíz del repositorio:
    python scripts/16_prepare_ddjj_2023_institutional_review.py
"""

from __future__ import annotations

import argparse
import csv
import math
import re
import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import Any, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = (
    PROJECT_ROOT / "data_processed" / "ddjj_2023_excel" / "normalized"
)
DEFAULT_OUTPUT_DIR = (
    PROJECT_ROOT / "data_processed" / "ddjj_2023_excel" / "review"
)

INPUT_FILES = {
    "ddjj": "fact_ddjj_tramite_2023.csv",
    "adremas": "fact_adrema_establecimiento_2023.csv",
    "ganaderia": "fact_ganaderia_declarada_2023.csv",
    "calidad": "fact_calidad_dato_2023.csv",
    "productores": "dim_productor_2023.csv",
}

OUTPUT_SCHEMAS = {
    "review_mortandad_mayor_cantidad.csv": (
        "tramite_id", "productor_nombre", "cuit_cuil", "especie",
        "categoria_original", "categoria_normalizada", "cantidad", "mortandad",
        "source_sheet", "source_row_number",
    ),
    "review_superficies_negativas.csv": (
        "tabla_origen", "tramite_id", "productor_nombre", "cuit_cuil", "adrema",
        "especie", "campo_superficie", "valor_superficie", "source_sheet",
        "source_row_number",
    ),
    "review_valores_ganaderos_negativos.csv": (
        "tramite_id", "productor_nombre", "cuit_cuil", "especie",
        "categoria_original", "cantidad", "mortandad", "source_sheet",
        "source_row_number",
    ),
    "review_adremas_duplicadas.csv": (
        "tramite_id", "productor_nombre", "cuit_cuil", "adrema", "departamento",
        "municipio", "superficie", "actividad_original", "source_row_number",
    ),
    "review_ganaderia_huerfana.csv": (
        "tramite_id", "especie", "categoria_original", "cantidad", "mortandad",
        "source_sheet", "source_row_number",
    ),
    "review_certificados_nulos.csv": (
        "tramite_id", "productor_nombre", "cuit_cuil", "fecha_presentacion",
        "estado_tramite", "tipo_certificado", "numero_certificado",
    ),
    "review_tramites_anulados_fuera_2023.csv": (
        "tramite_id", "productor_nombre", "cuit_cuil", "fecha_presentacion",
        "anio_presentacion", "estado_tramite", "caducidad", "fecha_anulacion",
    ),
}


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
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]
    return columns, rows


def write_csv(path: Path, fields: Sequence[str], rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def parse_year(row: dict[str, str]) -> int | None:
    raw_year = row.get("anio_presentacion", "")
    if not is_blank(raw_year):
        try:
            return int(float(raw_year))
        except ValueError:
            pass
    raw_date = row.get("fecha_presentacion", "")
    if is_blank(raw_date):
        return None
    try:
        return date.fromisoformat(raw_date).year
    except ValueError:
        match = re.search(r"(?:19|20)\d{2}", raw_date)
        return int(match.group(0)) if match else None


def load_inputs(input_dir: Path) -> dict[str, list[dict[str, str]]]:
    loaded: dict[str, list[dict[str, str]]] = {}
    for key, filename in INPUT_FILES.items():
        path = input_dir / filename
        if not path.is_file():
            raise FileNotFoundError(f"Falta el insumo requerido: {path}")
        _, rows = read_csv(path)
        loaded[key] = rows
    return loaded


def build_identity_lookup(
    ddjj: Sequence[dict[str, str]],
    productores: Sequence[dict[str, str]],
) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    productor_by_id = {
        row.get("productor_id_2023", ""): row
        for row in productores
        if not is_blank(row.get("productor_id_2023"))
    }
    ddjj_by_id: dict[str, dict[str, str]] = {}
    for row in ddjj:
        tramite_id = row.get("tramite_id", "")
        if is_blank(tramite_id):
            continue
        enriched = dict(row)
        producer = productor_by_id.get(row.get("productor_id_2023", ""), {})
        if is_blank(enriched.get("productor_nombre")):
            enriched["productor_nombre"] = producer.get("productor_nombre", "")
        if is_blank(enriched.get("cuit_cuil")):
            enriched["cuit_cuil"] = producer.get("cuit_cuil", "")
        ddjj_by_id[tramite_id] = enriched
    return ddjj_by_id, productor_by_id


def identity_fields(tramite_id: str, ddjj_by_id: dict[str, dict[str, str]]) -> tuple[str, str]:
    row = ddjj_by_id.get(tramite_id, {})
    return row.get("productor_nombre", ""), row.get("cuit_cuil", "")


def prepare_extracts(
    inputs: dict[str, list[dict[str, str]]]
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    ddjj = inputs["ddjj"]
    adremas = inputs["adremas"]
    ganaderia = inputs["ganaderia"]
    calidad = inputs["calidad"]
    productores = inputs["productores"]
    ddjj_by_id, _ = build_identity_lookup(ddjj, productores)
    main_ids = set(ddjj_by_id)

    mortality_rows: list[dict[str, Any]] = []
    negative_surface_rows: list[dict[str, Any]] = []
    negative_livestock_rows: list[dict[str, Any]] = []
    duplicate_adrema_rows: list[dict[str, Any]] = []
    orphan_livestock_rows: list[dict[str, Any]] = []
    null_certificate_rows: list[dict[str, Any]] = []
    annulled_or_outside_rows: list[dict[str, Any]] = []

    for row in ganaderia:
        tramite_id = row.get("tramite_id", "")
        name, cuit = identity_fields(tramite_id, ddjj_by_id)
        if as_bool(row.get("dq_mortandad_mayor_cantidad")):
            mortality_rows.append(
                {
                    "tramite_id": tramite_id,
                    "productor_nombre": name,
                    "cuit_cuil": cuit,
                    "especie": row.get("especie", ""),
                    "categoria_original": row.get("categoria_original", ""),
                    "categoria_normalizada": row.get("categoria_normalizada_preliminar", ""),
                    "cantidad": row.get("cantidad", ""),
                    "mortandad": row.get("mortandad", ""),
                    "source_sheet": row.get("source_sheet", ""),
                    "source_row_number": row.get("source_row_number", ""),
                }
            )

        quantity = as_number(row.get("cantidad"))
        mortality = as_number(row.get("mortandad"))
        if (quantity is not None and quantity < 0) or (mortality is not None and mortality < 0):
            negative_livestock_rows.append(
                {
                    "tramite_id": tramite_id,
                    "productor_nombre": name,
                    "cuit_cuil": cuit,
                    "especie": row.get("especie", ""),
                    "categoria_original": row.get("categoria_original", ""),
                    "cantidad": row.get("cantidad", ""),
                    "mortandad": row.get("mortandad", ""),
                    "source_sheet": row.get("source_sheet", ""),
                    "source_row_number": row.get("source_row_number", ""),
                }
            )

        for field in ("superficie_uso", "superficie_afectada"):
            value = as_number(row.get(field))
            if value is not None and value < 0:
                negative_surface_rows.append(
                    {
                        "tabla_origen": "fact_ganaderia_declarada_2023.csv",
                        "tramite_id": tramite_id,
                        "productor_nombre": name,
                        "cuit_cuil": cuit,
                        "adrema": "",
                        "especie": row.get("especie", ""),
                        "campo_superficie": field,
                        "valor_superficie": row.get(field, ""),
                        "source_sheet": row.get("source_sheet", ""),
                        "source_row_number": row.get("source_row_number", ""),
                    }
                )

        if not is_blank(tramite_id) and tramite_id not in main_ids:
            orphan_livestock_rows.append(
                {
                    "tramite_id": tramite_id,
                    "especie": row.get("especie", ""),
                    "categoria_original": row.get("categoria_original", ""),
                    "cantidad": row.get("cantidad", ""),
                    "mortandad": row.get("mortandad", ""),
                    "source_sheet": row.get("source_sheet", ""),
                    "source_row_number": row.get("source_row_number", ""),
                }
            )

    for row in adremas:
        tramite_id = row.get("tramite_id", "")
        name, cuit = identity_fields(tramite_id, ddjj_by_id)
        surface = as_number(row.get("superficie"))
        if surface is not None and surface < 0:
            negative_surface_rows.append(
                {
                    "tabla_origen": "fact_adrema_establecimiento_2023.csv",
                    "tramite_id": tramite_id,
                    "productor_nombre": name,
                    "cuit_cuil": cuit,
                    "adrema": row.get("adrema", ""),
                    "especie": "",
                    "campo_superficie": "superficie",
                    "valor_superficie": row.get("superficie", ""),
                    "source_sheet": row.get("source_sheet", ""),
                    "source_row_number": row.get("source_row_number", ""),
                }
            )
        if as_bool(row.get("dq_adrema_duplicada_en_tramite")):
            duplicate_adrema_rows.append(
                {
                    "tramite_id": tramite_id,
                    "productor_nombre": name,
                    "cuit_cuil": cuit,
                    "adrema": row.get("adrema", ""),
                    "departamento": row.get("departamento", ""),
                    "municipio": row.get("municipio", ""),
                    "superficie": row.get("superficie", ""),
                    "actividad_original": row.get("actividad_original", ""),
                    "source_row_number": row.get("source_row_number", ""),
                }
            )

    for row in ddjj:
        if is_blank(row.get("numero_certificado")):
            null_certificate_rows.append(
                {
                    "tramite_id": row.get("tramite_id", ""),
                    "productor_nombre": row.get("productor_nombre", ""),
                    "cuit_cuil": row.get("cuit_cuil", ""),
                    "fecha_presentacion": row.get("fecha_presentacion", ""),
                    "estado_tramite": row.get("estado_tramite", ""),
                    "tipo_certificado": row.get("tipo_certificado", ""),
                    "numero_certificado": row.get("numero_certificado", ""),
                }
            )
        year = parse_year(row)
        if canonical(row.get("estado_tramite")) == "anulado" or (year is not None and year != 2023):
            annulled_or_outside_rows.append(
                {
                    "tramite_id": row.get("tramite_id", ""),
                    "productor_nombre": row.get("productor_nombre", ""),
                    "cuit_cuil": row.get("cuit_cuil", ""),
                    "fecha_presentacion": row.get("fecha_presentacion", ""),
                    "anio_presentacion": row.get("anio_presentacion", ""),
                    "estado_tramite": row.get("estado_tramite", ""),
                    "caducidad": row.get("caducidad", ""),
                    "fecha_anulacion": row.get("fecha_anulacion", ""),
                }
            )

    extracts = {
        "review_mortandad_mayor_cantidad.csv": mortality_rows,
        "review_superficies_negativas.csv": negative_surface_rows,
        "review_valores_ganaderos_negativos.csv": negative_livestock_rows,
        "review_adremas_duplicadas.csv": duplicate_adrema_rows,
        "review_ganaderia_huerfana.csv": orphan_livestock_rows,
        "review_certificados_nulos.csv": null_certificate_rows,
        "review_tramites_anulados_fuera_2023.csv": annulled_or_outside_rows,
    }

    quality_counts = {
        "tramites_con_mortandad_mayor_cantidad": sum(
            as_bool(row.get("dq_tiene_mortandad_mayor_cantidad")) for row in calidad
        ),
        "tramites_con_superficie_negativa": sum(
            as_bool(row.get("dq_tiene_superficie_negativa")) for row in calidad
        ),
        "tramites_con_adrema_duplicada": sum(
            as_bool(row.get("dq_tiene_adrema_duplicada")) for row in calidad
        ),
        "tramites_huerfanos_en_detalle": sum(
            as_bool(row.get("dq_tiene_tramite_huerfano_en_detalle")) for row in calidad
        ),
    }
    return extracts, quality_counts


def build_summary(
    extracts: dict[str, list[dict[str, Any]]],
    quality_counts: dict[str, Any],
) -> str:
    counts = {name: len(rows) for name, rows in extracts.items()}
    lines = [
        "# Resumen del paquete de revisión institucional DDJJ 2023",
        "",
        f"- **Fecha de generación:** {datetime.now().astimezone().isoformat(timespec='seconds')}",
        "- **Objetivo:** facilitar decisiones institucionales sobre advertencias de calidad antes de cualquier carga o integración.",
        "- **Estado:** **no apto para carga a TiDB hasta cerrar definiciones institucionales**.",
        "- **Tratamiento aplicado:** selección y cruce; no se eliminaron ni corrigieron registros.",
        "",
        "## Casos por archivo de revisión",
        "",
        "| Archivo | Casos |",
        "| --- | ---: |",
    ]
    lines.extend(f"| `{name}` | {count} |" for name, count in counts.items())
    lines.extend(
        [
            "",
            "## Explicación, decisión requerida y recomendación preliminar",
            "",
            "| Alerta | Explicación | Decisión institucional requerida | Recomendación preliminar |",
            "| --- | --- | --- | --- |",
            "| Mortandad mayor que cantidad | La relación puede ser inconsistente o responder a una definición distinta de existencia. | Definir qué representa `cantidad` y si la comparación es válida. | No excluir; revisar por rubro y categoría. |",
            "| Superficies negativas | Hay valores incompatibles con una superficie física convencional. | Determinar si son errores, ajustes o códigos administrativos. | Verificar contra fuente y responsable de carga. |",
            "| Valores ganaderos negativos | Existen cantidades o mortandades con signo negativo. | Definir corrección en origen o tratamiento documentado. | No reemplazar automáticamente por cero. |",
            "| ADREMAS duplicadas | Varias filas comparten `tramite_id + adrema`. | Determinar si son duplicados reales o detalles legítimos. | Conservar filas hasta contar con criterio. |",
            "| Ganadería huérfana | La clave no existe en la tabla principal de trámites. | Vincularla, documentarla o excluirla con fundamento. | Revisar identificador contra la fuente original. |",
            "| Certificados nulos | Algunos trámites no informan número de certificado. | Definir si es ausencia válida según estado/caducidad. | No inferir resolución ni completar con otro identificador. |",
            "| Anulados o fuera de 2023 | Requieren una regla explícita de inclusión histórica. | Definir universo analítico y tratamiento de anulaciones. | Preservar en raw/normalizado; filtrar solo en una capa documentada. |",
            "",
            "## Conciliación con calidad consolidada",
            "",
            f"- Trámites con mortandad mayor que cantidad: **{quality_counts['tramites_con_mortandad_mayor_cantidad']}**.",
            f"- Trámites con superficie negativa: **{quality_counts['tramites_con_superficie_negativa']}**.",
            f"- Trámites con ADREMA duplicada: **{quality_counts['tramites_con_adrema_duplicada']}**.",
            f"- Claves con detalle huérfano: **{quality_counts['tramites_huerfanos_en_detalle']}**.",
            "",
            "## Restricciones vigentes",
            "",
            "- `Numero Certificado` no se interpreta como resolución o decreto.",
            "- No existe todavía un bridge normativo DDJJ–evento.",
            "- Los extractos contienen información personal y son de uso interno.",
            "- No cargar a TiDB ni integrar al dashboard hasta documentar las decisiones.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preparar revisión institucional DDJJ 2023.")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_dir = args.input_dir if args.input_dir.is_absolute() else PROJECT_ROOT / args.input_dir
    output_dir = args.output_dir if args.output_dir.is_absolute() else PROJECT_ROOT / args.output_dir
    if not input_dir.is_dir():
        raise FileNotFoundError(f"No existe el directorio normalizado: {input_dir}")

    inputs = load_inputs(input_dir)
    extracts, quality_counts = prepare_extracts(inputs)
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, rows in extracts.items():
        write_csv(output_dir / filename, OUTPUT_SCHEMAS[filename], rows)
    summary_path = output_dir / "revision_institucional_resumen.md"
    summary_path.write_text(build_summary(extracts, quality_counts), encoding="utf-8")

    print("Paquete de revisión institucional generado")
    for filename, rows in extracts.items():
        print(f"{filename}: {len(rows)} casos")
    print(f"Resumen: {summary_path}")
    print("No se modificaron tablas normalizadas, Excel, TiDB ni dashboard")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
