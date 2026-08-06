"""Ficha integral de un productor."""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from display_format import (
    clean_display_name,
    format_adrema,
    format_count,
    format_cuit_cuil,
    format_date,
    format_document,
    format_money,
    format_percentage,
    format_quantity,
    format_renspa,
    format_surface,
    format_year,
)
from utils import db_info, display_identifier, run_query

st.title("Ficha integral del productor")


PROJECT_DIR = Path(__file__).resolve().parents[2]
ENTREGAS_DIR = PROJECT_DIR / "data_processed" / "entregas" / "normalized"
ENTREGAS_FACT_PATH = ENTREGAS_DIR / "fact_entregas_emergencia.csv"
ENTREGAS_QUALITY_PATH = ENTREGAS_DIR / "fact_entregas_calidad_dato.csv"


SIN_CLASIFICAR = {"", "(s/d)", "s/d", "sd", "sin dato", "sin datos", "none", "nan"}
TECHNICAL_LABELS = {
    "origen_dato": "Origen",
    "productor_all_id": "ID productor unificado",
    "id_productor_actual": "ID productor actual",
    "productor_hist_id": "ID productor histórico",
    "ddjj_all_id": "ID DDJJ unificado",
    "id_ddjj_actual": "ID DDJJ actual",
    "ddjj_hist_id": "ID DDJJ histórico",
    "evento_id": "ID evento",
    "source_file": "Archivo fuente",
    "source_sheet": "Hoja fuente",
    "source_row": "Fila fuente",
    "severity": "Severidad",
    "severity_maxima": "Severidad",
    "severidad_maxima": "Severidad",
}
TECHNICAL_COLUMNS = list(TECHNICAL_LABELS)
DISPLAY_LABELS = {
    "origen_dato": "Origen",
    "productor_nombre": "Productor",
    "cuit_cuil": "CUIT/CUIL",
    "documento_nro": "Documento",
    "renspa": "RENSPA",
    "tipo_juridico": "Tipo jurídico",
    "actividad": "Actividad",
    "actividad_principal": "Actividad principal",
    "provincia": "Provincia",
    "departamento": "Departamento",
    "localidad": "Localidad",
    "dto": "Resolución / DTO",
    "resolucion_evento": "Resolución / DTO",
    "anio": "Año",
    "fecha": "Fecha",
    "pondf": "% daño ponderado",
    "superficie": "Superficie",
    "superficie_afectada": "Sup. afectada",
    "superficie_agricola_afectada": "Sup. agrícola afectada",
    "superficie_ganadera_afectada": "Sup. ganadera afectada",
    "superficie_sembrada": "Sup. sembrada",
    "existencias": "Existencias",
    "mortandad": "Mortandad",
    "tasa_mortandad": "Tasa de mortandad",
    "tasa_perdida": "Tasa de mortandad",
    "cultivo": "Cultivo",
    "categoria": "Categoría",
    "especie": "Especie",
    "adrema": "Adrema",
    "nombre_estab": "Establecimiento",
    "eventos": "Eventos",
    "registros": "Registros",
    "severidad_maxima": "Calidad",
    "tipo_coincidencia": "Tipo de coincidencia",
}


def _safe_str(value) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _display_value(value, default: str = "-") -> str:
    text = _safe_str(value)
    return text if text else default


def _short_label(value, max_len: int = 48) -> str:
    text = _display_value(value, "(s/d)")
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "..."


def _is_unclassified(series: pd.Series) -> pd.Series:
    return series.astype("string").fillna("").str.strip().str.lower().isin(SIN_CLASIFICAR)


def _has_column(df: pd.DataFrame, column: str) -> bool:
    return column in df.columns


def _normalize_numeric_search(value: str) -> str | None:
    text = value.strip()
    if re.search(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", text):
        return None
    text = re.sub(r"\.0$", "", text)
    text = re.sub(r"[\s.\-]", "", text)
    return text if text.isdigit() else None


def _numeric_series(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(df[column], errors="coerce")


def _sum_with_availability(df: pd.DataFrame, column: str) -> tuple[float, bool]:
    values = _numeric_series(df, column)
    if values.empty:
        return 0.0, False
    available = values.notna()
    if not available.any():
        return 0.0, False
    return float(values[available].sum()), True


def _format_ha(value: float, available: bool) -> str:
    return format_surface(value) if available else "Sin dato"


def _format_metric_ha(value: float, available: bool, records_count: int) -> str:
    if records_count == 0:
        return "No registra"
    return _format_ha(value, available)


def _format_number_es(value, suffix: str = "") -> str:
    if value is None or pd.isna(value):
        return "Sin dato"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "Sin dato"
    formatted = f"{number:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{formatted}{suffix}"


def _format_hectares(value) -> str:
    return format_surface(value)


def _format_percent(value) -> str:
    return format_percentage(value, scale="0-100")


def _rename_for_display(df: pd.DataFrame, labels: dict[str, str]) -> pd.DataFrame:
    columns = [column for column in labels if column in df.columns]
    return df[columns].rename(columns=labels)


def _format_display_columns(
    df: pd.DataFrame,
    hectare_columns: list[str] | None = None,
    percent_columns: list[str] | None = None,
) -> pd.DataFrame:
    out = df.copy()
    for column in hectare_columns or []:
        if column in out.columns:
            out[column] = out[column].apply(_format_hectares)
    for column in percent_columns or []:
        if column in out.columns:
            out[column] = out[column].apply(_format_percent)
    for column in out.columns:
        normalized = column.casefold()
        if normalized == "año":
            out[column] = out[column].map(format_year)
        elif normalized.startswith("fecha"):
            out[column] = out[column].map(format_date)
        elif normalized in {"existencias", "mortandad", "registros", "eventos"}:
            out[column] = out[column].map(format_count)
    return out


def _clean_display_table(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out = out.astype(object).where(pd.notna(out), "Sin dato")
    return out.replace(
        {
            "": "Sin dato",
            "None": "Sin dato",
            "none": "Sin dato",
            "nan": "Sin dato",
            "NaN": "Sin dato",
            "NaT": "Sin dato",
            "<NA>": "Sin dato",
        }
    )


def _truncate_identifier(value) -> str:
    text = _display_value(value, "Sin dato")
    if text == "Sin dato":
        return text
    return f"{text[:12]}..." if len(text) > 15 else text


def _technical_summary(df: pd.DataFrame) -> pd.DataFrame:
    flag_columns = [column for column in df.columns if column.startswith("flag_")]
    hash_columns = [column for column in df.columns if "hash" in column.lower()]
    columns = [column for column in [*TECHNICAL_COLUMNS, *flag_columns, *hash_columns] if column in df.columns]
    if not columns:
        return pd.DataFrame()
    out = df[columns].copy()
    for column in ["productor_all_id", "productor_hist_id", "ddjj_all_id", "ddjj_hist_id", "evento_id", *hash_columns]:
        if column in out.columns:
            out[column] = out[column].apply(_truncate_identifier)
    return _clean_display_table(out.rename(columns=TECHNICAL_LABELS))


def _render_technical_expander(df: pd.DataFrame, key: str) -> None:
    with st.expander("Campos técnicos / auditoría", expanded=False):
        st.caption(
            "Información auxiliar para trazabilidad interna. No es necesaria para "
            "la lectura operativa de la ficha."
        )
        summary = _technical_summary(df)
        if summary.empty:
            st.info("No hay campos técnicos disponibles para esta sección.")
        else:
            st.dataframe(summary, use_container_width=True, hide_index=True)
        if st.checkbox("Mostrar tabla técnica completa", key=f"{key}_full_technical"):
            st.dataframe(_clean_display_table(df), use_container_width=True, hide_index=True)


def _deduplicate_ddjj(ddjj_df: pd.DataFrame) -> pd.DataFrame:
    if ddjj_df.empty:
        return ddjj_df.copy()
    dedup = ddjj_df.copy()
    dedup["_row_order"] = range(len(dedup))
    dedup["_dedup_key"] = ""

    key_columns = [
        "dto",
        "anio",
        "fecha",
        "departamento",
        "localidad",
        "actividad",
        "pondf",
    ]
    available = [column for column in key_columns if column in dedup.columns]
    fallback = (
        dedup[available].astype("string").fillna("").agg("|".join, axis=1)
        if available
        else dedup["_row_order"].astype(str)
    )
    dedup["_dedup_key"] = "firma|" + fallback

    surface_cols = [
        column
        for column in ["superficie_agricola_afectada", "superficie_ganadera_afectada"]
        if column in dedup.columns
    ]
    if surface_cols:
        dedup["_surface_available"] = dedup[surface_cols].notna().sum(axis=1)
    else:
        dedup["_surface_available"] = 0

    dedup = dedup.sort_values(
        ["_dedup_key", "_surface_available", "_row_order"],
        ascending=[True, False, True],
    )
    dedup = dedup.drop_duplicates("_dedup_key", keep="first")
    dedup = dedup.sort_values("_row_order").drop(
        columns=["_row_order", "_dedup_key", "_surface_available"],
        errors="ignore",
    )
    return dedup


def _deduplicate_candidates(candidates_df: pd.DataFrame) -> pd.DataFrame:
    if candidates_df.empty:
        return candidates_df.copy()
    candidates_view = candidates_df.copy()
    cuit_norm = candidates_view.get("cuit_norm", pd.Series("", index=candidates_view.index)).astype("string").fillna("").str.strip()
    doc_norm = candidates_view.get("documento_norm", pd.Series("", index=candidates_view.index)).astype("string").fillna("").str.strip()
    candidates_view["_visual_key"] = candidates_view["productor_all_id"].astype(str)
    candidates_view.loc[doc_norm.ne(""), "_visual_key"] = "doc|" + doc_norm[doc_norm.ne("")]
    cuit_only_mask = cuit_norm.ne("") & doc_norm.eq("")
    candidates_view.loc[cuit_only_mask, "_visual_key"] = "cuit|" + cuit_norm[cuit_only_mask]
    candidates_view = candidates_view.sort_values(
        ["_visual_key", "match_rank", "origin_rank", "eventos", "registros"],
        ascending=[True, True, True, False, False],
    )
    candidates_view = candidates_view.drop_duplicates("_visual_key", keep="first")
    candidates_view = candidates_view.sort_values(
        ["match_rank", "origin_rank", "eventos", "registros", "productor_nombre"],
        ascending=[True, True, False, False, True],
    )
    return candidates_view.drop(columns=["_visual_key"], errors="ignore")


def _id_params(productor_ids: list[str]) -> tuple[str, dict[str, str]]:
    params = {f"pid{i}": str(value) for i, value in enumerate(productor_ids)}
    placeholders = ", ".join(f":pid{i}" for i in range(len(productor_ids)))
    return placeholders, params


def _query_candidates(search_text: str, limit: int) -> pd.DataFrame:
    numeric_search = _normalize_numeric_search(search_text)
    base_select = """
        SELECT
            productor_all_id,
            id_productor_actual,
            productor_hist_id,
            productor_nombre,
            documento_nro,
            cuit_cuil,
            renspa,
            actividad,
            departamento,
            localidad,
            paraje,
            origen_dato,
            eventos,
            registros,
            source_file,
            severidad_maxima,
            REGEXP_REPLACE(REGEXP_REPLACE(COALESCE(documento_nro, ''), '\\\\.0$', ''), '[^0-9]', '') AS documento_norm,
            REGEXP_REPLACE(REGEXP_REPLACE(COALESCE(cuit_cuil, ''), '\\\\.0$', ''), '[^0-9]', '') AS cuit_norm
        FROM vw_all_productores
    """

    if numeric_search:
        params = {"q": numeric_search, "partial": f"%{numeric_search}%", "limit": int(limit)}
        exact = run_query(
            f"""
            SELECT
                *,
                CASE
                    WHEN documento_norm = :q THEN 'Documento exacto'
                    WHEN cuit_norm = :q THEN 'CUIT/CUIL exacto'
                    ELSE 'Coincidencia parcial'
                END AS tipo_coincidencia,
                CASE
                    WHEN documento_norm = :q THEN 1
                    WHEN cuit_norm = :q THEN 2
                    ELSE 3
                END AS match_rank,
                CASE WHEN origen_dato = 'actual' THEN 0 ELSE 1 END AS origin_rank
            FROM ({base_select}) base
            WHERE documento_norm = :q OR cuit_norm = :q
            ORDER BY match_rank, origin_rank, COALESCE(eventos, 0) DESC,
                     COALESCE(registros, 0) DESC, productor_nombre
            LIMIT :limit
            """,
            params,
        )
        if not exact.empty:
            return exact
        return run_query(
            f"""
            SELECT
                *,
                'Coincidencia parcial' AS tipo_coincidencia,
                3 AS match_rank,
                CASE WHEN origen_dato = 'actual' THEN 0 ELSE 1 END AS origin_rank
            FROM ({base_select}) base
            WHERE documento_norm LIKE :partial OR cuit_norm LIKE :partial
            ORDER BY match_rank, origin_rank, COALESCE(eventos, 0) DESC,
                     COALESCE(registros, 0) DESC, productor_nombre
            LIMIT :limit
            """,
            params,
        )

    return run_query(
        """
        SELECT
            productor_all_id,
            id_productor_actual,
            productor_hist_id,
            productor_nombre,
            documento_nro,
            cuit_cuil,
            renspa,
            actividad,
            departamento,
            localidad,
            paraje,
            origen_dato,
            eventos,
            registros,
            source_file,
            severidad_maxima,
            REGEXP_REPLACE(REGEXP_REPLACE(COALESCE(documento_nro, ''), '\\\\.0$', ''), '[^0-9]', '') AS documento_norm,
            REGEXP_REPLACE(REGEXP_REPLACE(COALESCE(cuit_cuil, ''), '\\\\.0$', ''), '[^0-9]', '') AS cuit_norm,
            'Nombre' AS tipo_coincidencia,
            4 AS match_rank,
            CASE WHEN origen_dato = 'actual' THEN 0 ELSE 1 END AS origin_rank
        FROM vw_all_productores
        WHERE productor_nombre LIKE :q
        ORDER BY match_rank, origin_rank, COALESCE(eventos, 0) DESC,
                 COALESCE(registros, 0) DESC, productor_nombre
        LIMIT :limit
        """,
        {"q": f"%{search_text}%", "limit": int(limit)},
    )


def _query_related_productores(selected_row: pd.Series) -> pd.DataFrame:
    selected_id = str(selected_row["productor_all_id"])
    documento_norm = _safe_str(selected_row.get("documento_norm"))
    cuit_norm = _safe_str(selected_row.get("cuit_norm"))
    conds = ["productor_all_id = :selected_id"]
    params: dict[str, str] = {"selected_id": selected_id}
    if documento_norm:
        conds.append("documento_norm = :documento_norm")
        params["documento_norm"] = documento_norm
    if cuit_norm:
        conds.append("cuit_norm = :cuit_norm")
        params["cuit_norm"] = cuit_norm

    return run_query(
        f"""
        SELECT
            productor_all_id,
            id_productor_actual,
            productor_hist_id,
            productor_nombre,
            documento_nro,
            cuit_cuil,
            renspa,
            actividad,
            departamento,
            localidad,
            paraje,
            origen_dato,
            eventos,
            registros,
            source_file,
            severidad_maxima,
            documento_norm,
            cuit_norm
        FROM (
            SELECT
                productor_all_id,
                id_productor_actual,
                productor_hist_id,
                productor_nombre,
                documento_nro,
                cuit_cuil,
                renspa,
                actividad,
                departamento,
                localidad,
                paraje,
                origen_dato,
                eventos,
                registros,
                source_file,
                severidad_maxima,
                REGEXP_REPLACE(REGEXP_REPLACE(COALESCE(documento_nro, ''), '\\\\.0$', ''), '[^0-9]', '') AS documento_norm,
                REGEXP_REPLACE(REGEXP_REPLACE(COALESCE(cuit_cuil, ''), '\\\\.0$', ''), '[^0-9]', '') AS cuit_norm
            FROM vw_all_productores
        ) base
        WHERE {" OR ".join(conds)}
        ORDER BY CASE WHEN origen_dato = 'actual' THEN 0 ELSE 1 END,
                 COALESCE(eventos, 0) DESC, COALESCE(registros, 0) DESC,
                 productor_nombre
        """,
        params,
    )


def _query_actual_details(id_productor_actual) -> pd.DataFrame:
    if pd.isna(id_productor_actual):
        return pd.DataFrame()
    return run_query(
        """
        SELECT
            p.ProductorId,
            p.ProductorDenominacion,
            p.CUITCUIL,
            p.DocumentoNro,
            p.renspa,
            tj.TipoJuridicoDesc AS tipo_juridico,
            ta.TipoActividadDesc AS actividad_principal,
            pr.ProvinciaDesc AS provincia,
            dep.DepartamentoDesc AS departamento,
            loc.LocalidadDesc AS localidad
        FROM productores p
        LEFT JOIN tipojuridico tj ON tj.TipoJuridicoId = p.TipoJuridicoId
        LEFT JOIN tipoactividad ta ON ta.TipoActividadId = p.EsPrincipalActividadEconomica
        LEFT JOIN domicilios d ON d.DomicilioId = p.DomicilioId
        LEFT JOIN provincias pr ON pr.ProvinciaId = d.ProvinciaId
        LEFT JOIN departamentos dep ON dep.DepartamentoId = d.DepartamentoId
        LEFT JOIN localidades loc ON loc.LocalidadId = d.LocalidadId
        WHERE p.ProductorId = :id_productor
        """,
        {"id_productor": int(id_productor_actual)},
    )


def _query_ddjj(productor_ids: list[str]) -> pd.DataFrame:
    placeholders, params = _id_params(productor_ids)
    return run_query(
        f"""
        SELECT
            origen_dato,
            ddjj_all_id,
            id_ddjj_actual,
            ddjj_hist_id,
            evento_id,
            anio,
            fecha,
            dto,
            periodo,
            departamento,
            localidad,
            paraje,
            actividad,
            pondf,
            superficie_total,
            superficie_agricola_afectada,
            superficie_ganadera_afectada,
            source_file,
            source_sheet,
            dataset_role,
            relation_type,
            flag_revision_manual,
            severidad_maxima
        FROM vw_all_ddjj_personas
        WHERE productor_all_id IN ({placeholders})
        ORDER BY anio DESC, fecha DESC
        """,
        params,
    )


def _query_agricultura(productor_ids: list[str]) -> pd.DataFrame:
    placeholders, params = _id_params(productor_ids)
    return run_query(
        f"""
        SELECT
            origen_dato,
            anio,
            dto,
            evento_id,
            departamento,
            actividad,
            cultivo,
            SUM(superficie_sembrada_uso) AS superficie_sembrada,
            SUM(superficie_afectada) AS superficie_afectada,
            SUM(produccion_estimada) AS produccion_estimada,
            SUM(produccion_obtenida) AS produccion_obtenida,
            COUNT(*) AS registros,
            COUNT(DISTINCT ddjj_all_id) AS ddjj,
            MAX(flag_agricola_afectada_mayor_uso) AS flag_agricola_afectada_mayor_uso,
            MAX(flag_superficie_total_menor_afectadas) AS flag_superficie_total_menor_afectadas,
            MAX(flag_revision_manual) AS flag_revision_manual,
            MAX(severidad_maxima) AS severidad_maxima
        FROM (
            SELECT
                a.origen_dato,
                a.anio,
                a.dto,
                a.evento_id,
                a.departamento,
                a.actividad,
                COALESCE(a.especie, a.cultivo, a.categoria, '(s/d)') AS cultivo,
                a.superficie_sembrada_uso,
                a.superficie_afectada,
                a.produccion_estimada,
                a.produccion_obtenida,
                d.ddjj_all_id,
                a.flag_agricola_afectada_mayor_uso,
                a.flag_superficie_total_menor_afectadas,
                a.flag_revision_manual,
                a.severidad_maxima
            FROM vw_all_agricultura a
            JOIN vw_all_ddjj_personas d
              ON (
                  (a.id_ddjj_actual IS NOT NULL AND a.id_ddjj_actual = d.id_ddjj_actual)
                  OR (a.ddjj_hist_id IS NOT NULL AND a.ddjj_hist_id = d.ddjj_hist_id)
              )
            WHERE d.productor_all_id IN ({placeholders})
        ) base
        GROUP BY
            origen_dato, anio, dto, evento_id, departamento, actividad, cultivo
        HAVING COALESCE(superficie_sembrada, 0) > 0
            OR COALESCE(superficie_afectada, 0) > 0
            OR COALESCE(produccion_estimada, 0) > 0
            OR COALESCE(produccion_obtenida, 0) > 0
        ORDER BY anio DESC, superficie_afectada DESC
        """,
        params,
    )


def _query_ganaderia(productor_ids: list[str]) -> pd.DataFrame:
    placeholders, params = _id_params(productor_ids)
    return run_query(
        f"""
        SELECT
            origen_dato,
            anio,
            dto,
            evento_id,
            departamento,
            actividad,
            categoria,
            SUM(superficie_ganadera_uso) AS superficie_ganadera_uso,
            SUM(superficie_ganadera_afectada) AS superficie_ganadera_afectada,
            SUM(existencias) AS existencias,
            SUM(mortandad) AS mortandad,
            COUNT(*) AS registros,
            COUNT(DISTINCT ddjj_all_id) AS ddjj,
            MAX(flag_ganadera_afectada_mayor_uso) AS flag_ganadera_afectada_mayor_uso,
            MAX(flag_mortandad_mayor_existencias) AS flag_mortandad_mayor_existencias,
            MAX(flag_superficie_total_menor_afectadas) AS flag_superficie_total_menor_afectadas,
            MAX(flag_revision_manual) AS flag_revision_manual,
            MAX(severidad_maxima) AS severidad_maxima
        FROM (
            SELECT
                g.origen_dato,
                g.anio,
                g.dto,
                g.evento_id,
                g.departamento,
                g.actividad,
                COALESCE(g.categoria, g.especie, g.actividad, 'GANADERIA') AS categoria,
                g.superficie_ganadera_uso,
                g.superficie_ganadera_afectada,
                g.existencias,
                g.mortandad,
                d.ddjj_all_id,
                g.flag_ganadera_afectada_mayor_uso,
                g.flag_mortandad_mayor_existencias,
                g.flag_superficie_total_menor_afectadas,
                g.flag_revision_manual,
                g.severidad_maxima
            FROM vw_all_ganaderia_resumen g
            JOIN vw_all_ddjj_personas d
              ON (
                  (g.id_ddjj_actual IS NOT NULL AND g.id_ddjj_actual = d.id_ddjj_actual)
                  OR (g.ddjj_hist_id IS NOT NULL AND g.ddjj_hist_id = d.ddjj_hist_id)
              )
            WHERE d.productor_all_id IN ({placeholders})
        ) base
        GROUP BY
            origen_dato, anio, dto, evento_id, departamento, actividad, categoria
        HAVING COALESCE(existencias, 0) > 0
            OR COALESCE(mortandad, 0) > 0
            OR COALESCE(superficie_ganadera_uso, 0) > 0
            OR COALESCE(superficie_ganadera_afectada, 0) > 0
        ORDER BY anio DESC, mortandad DESC
        """,
        params,
    )


def _query_adremas(id_productor_actual, ddjj: pd.DataFrame) -> pd.DataFrame:
    """Combina ADREMAS actuales y pares únicos de DDJJ 2023."""
    frames: list[pd.DataFrame] = []
    if not pd.isna(id_productor_actual):
        current = run_query(
            """
        SELECT
            a.adrema,
            a.superficie,
            ta.TipoActividadDesc AS actividad,
            tt.descripcion AS tenencia,
            a.departamento,
            e.nombre_estab,
            e.paraje_estab,
            e.latitud,
            e.longitud,
            a.ddjj AS id_ddjj,
            'actual' AS origen_dato,
            NULL AS municipio,
            NULL AS localidad,
            NULL AS source_row_number
        FROM adremas a
        LEFT JOIN tipoactividad ta ON ta.TipoActividadId = a.actividad
        LEFT JOIN tipotenencia tt ON tt.id = a.tenencia
        LEFT JOIN establecimientos e ON e.id_establecimiento = a.id_establecimiento
        JOIN ddjj_personas dj ON dj.id_ddjj = a.ddjj
        WHERE dj.id_productor = :id_productor
        ORDER BY a.superficie DESC
            """,
            {"id_productor": int(id_productor_actual)},
        )
        frames.append(current)

    if not ddjj.empty and {"origen_dato", "ddjj_hist_id"}.issubset(ddjj.columns):
        tramite_ids = (
            ddjj.loc[ddjj["origen_dato"].eq("ddjj_2023_excel"), "ddjj_hist_id"]
            .dropna().astype(str).unique().tolist()
        )
        if tramite_ids:
            placeholders, params = _id_params(tramite_ids)
            frames.append(
                run_query(
                    f"""
                    SELECT adrema, superficie,
                           COALESCE(actividad_normalizada_preliminar, actividad_original) AS actividad,
                           pertenencia AS tenencia, departamento,
                           NULL AS nombre_estab, paraje AS paraje_estab,
                           NULL AS latitud, NULL AS longitud,
                           tramite_id AS id_ddjj, origen_dato, municipio, localidad,
                           source_row_number
                    FROM stg_ddjj_2023_adrema
                    WHERE adrema_unica_indicador=1
                      AND tramite_id IN ({placeholders})
                    ORDER BY superficie DESC
                    """,
                    params,
                )
            )
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _query_documentacion(id_productor_actual) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if pd.isna(id_productor_actual):
        empty = pd.DataFrame()
        return empty, empty, empty

    ponderaciones = run_query(
        """
        SELECT
            p.id_ddjj,
            rt.nombre AS rubro,
            p.estimados,
            p.obtenidos,
            p.perdidas_ponde
        FROM ponderaciones_ddjj p
        JOIN rubro_tipos rt ON rt.id_rubro = p.rubro
        JOIN ddjj_personas dj ON dj.id_ddjj = p.id_ddjj
        WHERE dj.id_productor = :id_productor
        ORDER BY p.id_ddjj, p.rubro
        """,
        {"id_productor": int(id_productor_actual)},
    )
    mejoras = run_query(
        """
        SELECT
            pm.idddjj AS id_ddjj,
            pm.mejora,
            pm.vestimado,
            pm.incidencia,
            pm.pesesp,
            pm.pesper
        FROM perdidas_mejoras pm
        JOIN ddjj_personas dj ON dj.id_ddjj = pm.idddjj
        WHERE dj.id_productor = :id_productor
        ORDER BY pm.idddjj, pm.mejora
        """,
        {"id_productor": int(id_productor_actual)},
    )
    documentacion = run_query(
        """
        SELECT
            doc.idddjj AS id_ddjj,
            doc.codigo,
            doc.documentacion,
            doc.marcar
        FROM documentacion doc
        JOIN ddjj_personas dj ON dj.id_ddjj = doc.idddjj
        WHERE dj.id_productor = :id_productor
        ORDER BY doc.idddjj, doc.codigo
        """,
        {"id_productor": int(id_productor_actual)},
    )
    return ponderaciones, mejoras, documentacion


def _sum_columns(df: pd.DataFrame, columns: list[str]) -> float:
    total = 0.0
    for column in columns:
        if column in df.columns:
            total += pd.to_numeric(df[column], errors="coerce").fillna(0).sum()
    return float(total)


@st.cache_data(show_spinner=False)
def _read_local_csv(path_text: str, modified_ns: int) -> pd.DataFrame:
    """Lee CSV local como texto; modified_ns invalida caché cuando cambia la fuente."""
    del modified_ns
    return pd.read_csv(path_text, dtype=str, keep_default_na=False, encoding="utf-8-sig")


def _load_local_entregas() -> tuple[pd.DataFrame, pd.DataFrame, bool]:
    if not ENTREGAS_FACT_PATH.is_file():
        return pd.DataFrame(), pd.DataFrame(), False
    fact = _read_local_csv(str(ENTREGAS_FACT_PATH), ENTREGAS_FACT_PATH.stat().st_mtime_ns)
    quality = pd.DataFrame()
    if ENTREGAS_QUALITY_PATH.is_file():
        quality = _read_local_csv(str(ENTREGAS_QUALITY_PATH), ENTREGAS_QUALITY_PATH.stat().st_mtime_ns)
    return fact, quality, True


def _load_entregas() -> tuple[pd.DataFrame, pd.DataFrame, bool, str, str]:
    """Prioriza TiDB Cloud y conserva CSV local como fallback de desarrollo."""
    try:
        use_tidb = db_info().get("source") == "TiDB Cloud"
    except Exception:
        use_tidb = False
    tidb_error = ""
    if use_tidb:
        try:
            fact = run_query("SELECT * FROM stg_entregas_emergencia")
            try:
                quality = run_query("SELECT * FROM stg_entregas_calidad_dato")
            except Exception:
                quality = pd.DataFrame()
                tidb_error = "La tabla de alertas de entregas no está disponible en TiDB."
            return fact, quality, True, "TiDB staging", tidb_error
        except Exception:
            tidb_error = "No se pudo consultar TiDB; se intentó usar el fallback local."

    fact, quality, available = _load_local_entregas()
    if available:
        return fact, quality, True, "CSV local", tidb_error
    return pd.DataFrame(), pd.DataFrame(), False, "Sin fuente disponible", tidb_error


def _normalized_digits(value) -> str:
    text = re.sub(r"\.0$", "", _safe_str(value))
    return re.sub(r"\D", "", text)


def _normalized_agro_key(value) -> str:
    text = _safe_str(value).upper()
    if text.lower() in SIN_CLASIFICAR:
        return ""
    text = re.sub(r"\s*-\s*", "-", text)
    return re.sub(r"\s+", "", text).strip("-")


def _series_text(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series("", index=df.index, dtype="string")
    return df[column].astype("string").fillna("").str.strip()


def _selected_key_sets(
    selected_row: pd.Series,
    actual_row: pd.Series | None,
    related: pd.DataFrame,
    renspa_values: list[str],
    adremas_df: pd.DataFrame,
) -> dict[str, set[str]]:
    cuit_values = [
        actual_row.get("CUITCUIL") if actual_row is not None else None,
        selected_row.get("cuit_cuil"), selected_row.get("cuit_norm"),
        *related.get("cuit_cuil", pd.Series(dtype=object)).tolist(),
        *related.get("cuit_norm", pd.Series(dtype=object)).tolist(),
    ]
    document_values = [
        actual_row.get("DocumentoNro") if actual_row is not None else None,
        selected_row.get("documento_nro"), selected_row.get("documento_norm"),
        *related.get("documento_nro", pd.Series(dtype=object)).tolist(),
        *related.get("documento_norm", pd.Series(dtype=object)).tolist(),
    ]
    adrema_values = adremas_df.get("adrema", pd.Series(dtype=object)).tolist()
    return {
        "cuit": {value for raw in cuit_values if (value := _normalized_digits(raw))},
        "documento": {value for raw in document_values if (value := _normalized_digits(raw))},
        "renspa": {value for raw in renspa_values if (value := _normalized_agro_key(raw))},
        "adrema": {value for raw in adrema_values if (value := _normalized_agro_key(raw))},
    }


def _link_entregas(entregas: pd.DataFrame, keys: dict[str, set[str]]) -> pd.DataFrame:
    if entregas.empty:
        return entregas.copy()
    linked = entregas.copy()
    cuit = _series_text(linked, "cuit_cuil_norm").map(_normalized_digits)
    document = _series_text(linked, "documento_norm").map(_normalized_digits)
    renspa = _series_text(linked, "renspa").map(_normalized_agro_key)
    adrema = _series_text(linked, "adrema").map(_normalized_agro_key)

    cuit_match = cuit.ne("") & cuit.isin(keys["cuit"])
    document_match = document.ne("") & document.isin(keys["documento"])
    renspa_match = renspa.ne("") & renspa.isin(keys["renspa"])
    adrema_match = adrema.ne("") & adrema.isin(keys["adrema"])
    linked = linked[cuit_match | document_match | renspa_match | adrema_match].copy()
    if linked.empty:
        return linked

    # Asigna la coincidencia de mayor prioridad y conserva una sola fila por entrega.
    linked["tipo_coincidencia_entrega"] = "Sin coincidencia confiable"
    linked["_match_priority"] = 99
    for mask, label, priority in [
        (adrema_match, "ADREMA exacta", 4),
        (renspa_match, "RENSPA exacto", 3),
        (document_match, "Documento exacto", 2),
        (cuit_match, "CUIT/CUIL exacto", 1),
    ]:
        matching_index = mask[mask].index.intersection(linked.index)
        linked.loc[matching_index, "tipo_coincidencia_entrega"] = label
        linked.loc[matching_index, "_match_priority"] = priority
    linked = linked.sort_values(["_match_priority", "entrega_id"], kind="stable")
    return linked.drop_duplicates("entrega_id", keep="first").drop(columns="_match_priority")


def _format_entrega_date(value) -> str:
    return format_date(value)


def _format_entrega_number(value) -> str:
    text = _safe_str(value)
    if not text:
        return "Sin dato"
    try:
        number = float(text)
    except (TypeError, ValueError):
        return "Sin dato"
    decimals = 0 if number.is_integer() else 2
    return f"{number:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _render_entregas_tab(
    entregas: pd.DataFrame,
    quality: pd.DataFrame,
    data_available: bool,
    data_source: str,
    load_warning: str,
) -> None:
    st.subheader("Entregas / asistencia")
    st.warning(
        f"La información de entregas/asistencia proviene de {data_source}, con datos "
        "normalizados y validados con advertencias. Esta consulta no modifica TiDB ni "
        "las vistas históricas."
    )
    if load_warning:
        st.warning(load_warning)
    if not data_available:
        st.info(
            "No se encontraron datos de entregas/asistencia en TiDB ni en el fallback local. "
            "Ejecutar los scripts 25 a 28 antes de consultar esta sección."
        )
        return
    if entregas.empty:
        st.info("Sin entregas registradas para este productor.")
        with st.expander("Metodología de vinculación"):
            _render_entregas_methodology()
        return

    delivery_ids = set(_series_text(entregas, "entrega_id"))
    delivery_alerts = quality[
        _series_text(quality, "entrega_id").isin(delivery_ids)
    ].copy() if not quality.empty else pd.DataFrame()
    duplicate_count = int(
        _series_text(delivery_alerts, "alerta_tipo").eq("posible_duplicado").sum()
    ) if not delivery_alerts.empty else 0
    if duplicate_count:
        st.warning("Existen registros marcados como posibles duplicados; se conservan para trazabilidad.")

    numeric_amount = pd.to_numeric(_series_text(entregas, "monto_estimado"), errors="coerce")
    numeric_quantity = pd.to_numeric(_series_text(entregas, "cantidad"), errors="coerce")
    years = _series_text(entregas, "anio").replace("", pd.NA).dropna()
    providers = _series_text(entregas, "proveedor").replace("", pd.NA).dropna()
    linked_renspa = _series_text(entregas, "renspa").replace("", pd.NA).dropna()
    metrics = st.columns(3)
    metrics[0].metric("Entregas registradas", format_count(len(entregas)))
    metrics[1].metric("Años con asistencia", format_count(years.nunique()))
    metrics[2].metric("Proveedores", format_count(providers.nunique()))
    metrics = st.columns(3)
    metrics[0].metric("RENSPA vinculados", format_count(linked_renspa.nunique()))
    metrics[1].metric(
        "Monto total informado",
        format_money(numeric_amount.sum(), currency="ARS") if numeric_amount.notna().any() else "Sin dato",
    )
    normalized_units = _series_text(entregas, "unidad").str.strip().str.casefold()
    informed_units = sorted(unit for unit in normalized_units.unique() if unit)
    if len(informed_units) == 1 and numeric_quantity.notna().any():
        metrics[2].metric(
            "Cantidad total informada",
            format_quantity(numeric_quantity.sum(), informed_units[0]),
        )
    elif len(informed_units) > 1:
        metrics[2].metric("Cantidades informadas por unidad", "Ver detalle")
    else:
        metrics[2].metric("Cantidad total informada", "Sin dato")

    filtered = entregas.copy()
    filter_specs = [
        ("anio", "Año"), ("proveedor", "Proveedor"),
        ("tipo_asistencia", "Tipo de asistencia"),
        ("calidad_identificacion", "Calidad identificación"),
    ]
    available_filters = [
        (column, label, sorted(_series_text(filtered, column).replace("", pd.NA).dropna().unique()))
        for column, label in filter_specs if column in filtered.columns
    ]
    available_filters = [
        (column, label, values)
        for column, label, values in available_filters
        if values and (column != "calidad_identificacion" or len(values) > 1)
    ]
    if available_filters:
        st.write("**Filtros**")
        filter_columns = st.columns(len(available_filters))
        selections: dict[str, list[str]] = {}
        for container, (column, label, values) in zip(filter_columns, available_filters):
            display_values = [format_year(value) for value in values] if column == "anio" else values
            display_to_raw = dict(zip(display_values, values))
            selected_display = container.multiselect(
                label, display_values, default=display_values, key=f"entregas_filter_{column}"
            )
            selections[column] = [display_to_raw[value] for value in selected_display]
        for column, selected_values in selections.items():
            filtered = filtered[_series_text(filtered, column).isin(selected_values)]

    table = filtered.copy()
    table["fuente"] = (
        _series_text(table, "fuente_archivo") + " / "
        + _series_text(table, "fuente_hoja") + " / fila "
        + _series_text(table, "source_row_number")
    )
    labels = {
        "anio": "Año", "fecha_entrega": "Fecha de entrega",
        "tipo_asistencia": "Tipo de asistencia", "proveedor": "Proveedor",
        "insumo_producto": "Insumo / producto", "cantidad": "Cantidad",
        "unidad": "Unidad", "monto_estimado": "Monto estimado", "renspa": "RENSPA",
        "adrema": "ADREMA", "departamento": "Departamento", "localidad": "Localidad",
        "norma_evento": "Norma / evento", "expediente": "Expediente",
        "calidad_identificacion": "Calidad identificación",
        "tipo_coincidencia_entrega": "Tipo de coincidencia", "fuente": "Fuente",
    }
    table = _rename_for_display(table, labels)
    if "Año" in table.columns:
        table["Año"] = table["Año"].map(format_year)
    if "Fecha de entrega" in table.columns:
        table["Fecha de entrega"] = table["Fecha de entrega"].map(_format_entrega_date)
    if "Cantidad" in table.columns:
        table["Cantidad"] = table["Cantidad"].map(format_quantity)
    if "Monto estimado" in table.columns:
        table["Monto estimado"] = table["Monto estimado"].map(lambda value: format_money(value, "ARS"))
    if "RENSPA" in table.columns:
        table["RENSPA"] = table["RENSPA"].map(format_renspa)
    if "ADREMA" in table.columns:
        table["ADREMA"] = table["ADREMA"].map(format_adrema)
    st.dataframe(_clean_display_table(table), use_container_width=True, hide_index=True)

    with st.expander("Ver alertas de calidad de entregas"):
        if delivery_alerts.empty:
            st.info("No hay alertas de calidad asociadas a las entregas vinculadas.")
        else:
            alert_labels = {
                "alerta_tipo": "Tipo de alerta", "alerta_descripcion": "Descripción",
                "severidad": "Severidad",
            }
            st.dataframe(
                _clean_display_table(_rename_for_display(delivery_alerts, alert_labels)),
                use_container_width=True, hide_index=True,
            )
    with st.expander("Metodología de vinculación"):
        _render_entregas_methodology()


def _render_entregas_methodology() -> None:
    st.markdown(
        """
        - La coincidencia confiable se realiza, en orden, por CUIT/CUIL, documento, RENSPA o ADREMA exactos.
        - Una entrega que coincide por varias claves se muestra una sola vez con la coincidencia de mayor prioridad.
        - El nombre del productor no se usa para vincular automáticamente.
        - Los posibles duplicados se conservan para trazabilidad y requieren conciliación administrativa.
        - Las 892 filas clasificadas como 2023 desde archivos de la campaña/carpeta 2024 requieren validación administrativa.
        - Esta integración usa archivos locales y no carga datos a TiDB ni modifica vistas históricas.
        """
    )


with st.sidebar:
    st.header("Búsqueda")
    q = st.text_input("Nombre / CUIT / Documento", "")
    limite = st.slider("Candidatos máximos", 10, 200, 50, step=10)

if len(q.strip()) < 2:
    st.info("Ingrese al menos 2 caracteres para buscar un productor por nombre, CUIT o documento.")
    st.stop()

candidates = _query_candidates(q.strip(), limite)

if candidates.empty:
    st.warning("No se encontraron productores para la busqueda ingresada.")
    st.stop()

numeric_query = _normalize_numeric_search(q.strip())
if numeric_query and candidates["tipo_coincidencia"].eq("Coincidencia parcial").all():
    st.info("No se encontraron coincidencias exactas. Se muestran coincidencias parciales.")

candidates_visual = _deduplicate_candidates(candidates)

st.subheader("Candidatos")
candidate_view = candidates_visual[
    [
        "productor_nombre",
        "cuit_cuil",
        "documento_nro",
        "tipo_coincidencia",
        "actividad",
        "departamento",
        "eventos",
        "registros",
        "severidad_maxima",
]
].copy()
candidate_view["cuit_cuil"] = candidate_view["cuit_cuil"].apply(lambda value: display_identifier(value, "cuit_cuil"))
candidate_view["documento_nro"] = candidate_view["documento_nro"].apply(lambda value: display_identifier(value, "documento"))
st.dataframe(
    _clean_display_table(_rename_for_display(candidate_view, DISPLAY_LABELS)),
    use_container_width=True,
    hide_index=True,
    height=260,
)

options = candidates_visual["productor_all_id"].astype(str).tolist()
selected_id = st.selectbox(
    "Seleccionar productor",
    options,
    format_func=lambda value: (
        f"{_display_value(candidates_visual.loc[candidates_visual['productor_all_id'].astype(str) == value, 'productor_nombre'].iloc[0])}"
        f" | Doc: {display_identifier(candidates_visual.loc[candidates_visual['productor_all_id'].astype(str) == value, 'documento_nro'].iloc[0], 'documento')}"
        f" | {_display_value(candidates_visual.loc[candidates_visual['productor_all_id'].astype(str) == value, 'tipo_coincidencia'].iloc[0])}"
    ),
)

selected = candidates_visual[candidates_visual["productor_all_id"].astype(str) == selected_id].iloc[0]
related_productores = _query_related_productores(selected)
if related_productores.empty:
    related_productores = pd.DataFrame([selected])

productor_ids = related_productores["productor_all_id"].astype(str).dropna().unique().tolist()
actual_ids = related_productores["id_productor_actual"].dropna() if "id_productor_actual" in related_productores else pd.Series(dtype=object)
id_productor_actual = actual_ids.iloc[0] if not actual_ids.empty else selected.get("id_productor_actual")
actual_details = _query_actual_details(id_productor_actual)
actual_row = actual_details.iloc[0] if not actual_details.empty else None

ddjj = _query_ddjj(productor_ids)
ddjj_unique = _deduplicate_ddjj(ddjj)
agricultura = _query_agricultura(productor_ids)
ganaderia = _query_ganaderia(productor_ids)
adremas = _query_adremas(id_productor_actual, ddjj)
ponderaciones, mejoras, documentacion = _query_documentacion(id_productor_actual)

st.divider()
st.subheader("Datos del productor")

nombre = clean_display_name(
    actual_row["ProductorDenominacion"] if actual_row is not None else selected.get("productor_nombre")
)
cuit = format_cuit_cuil(actual_row["CUITCUIL"] if actual_row is not None else selected.get("cuit_cuil"))
documento = format_document(actual_row["DocumentoNro"] if actual_row is not None else selected.get("documento_nro"))
renspa_values: list[str] = []
for value in [
    actual_row["renspa"] if actual_row is not None else None,
    *related_productores.get("renspa", pd.Series(dtype=object)).tolist(),
]:
    for item in re.split(r"\s*[|,;]\s*", _safe_str(value)):
        if item and item.lower() not in SIN_CLASIFICAR and item not in renspa_values:
            renspa_values.append(item)
renspa = ", ".join(format_renspa(value) for value in renspa_values) if renspa_values else "No registra"
actividad = _display_value(
    actual_row["actividad_principal"] if actual_row is not None else selected.get("actividad")
)
tipo_juridico = _display_value(actual_row["tipo_juridico"] if actual_row is not None else None)
provincia = _display_value(actual_row["provincia"] if actual_row is not None else None)
departamento = _display_value(
    actual_row["departamento"] if actual_row is not None else selected.get("departamento")
)
localidad = _display_value(actual_row["localidad"] if actual_row is not None else selected.get("localidad"))

(
    entregas_fact,
    entregas_quality,
    entregas_data_available,
    entregas_data_source,
    entregas_load_warning,
) = _load_entregas()
entregas_keys = _selected_key_sets(selected, actual_row, related_productores, renspa_values, adremas)
entregas = _link_entregas(entregas_fact, entregas_keys) if entregas_data_available else pd.DataFrame()

c1, c2, c3 = st.columns(3)
with c1:
    st.write(f"**Nombre / razón social:** {nombre}")
    st.write(f"**CUIT/CUIL:** {cuit}")
    st.write(f"**Documento:** {documento}")
with c2:
    st.write(f"**Tipo jurídico:** {tipo_juridico}")
    st.write(f"**Actividad principal:** {actividad}")
    st.write(f"**RENSPA:** {renspa}")
with c3:
    st.write(f"**Provincia:** {provincia}")
    st.write(f"**Departamento:** {departamento}")
    st.write(f"**Localidad:** {localidad}")

st.caption(
    "La ficha consolida registros actuales e históricos cuando la identificación "
    "del productor es confiable. La trazabilidad de origen queda disponible en "
    "Campos técnicos / auditoría."
)

ddjj_count = len(ddjj_unique)
eventos_count = 0
if not ddjj_unique.empty:
    evento_cols = ["evento_id", "dto", "periodo"]
    eventos_count = int(
        ddjj_unique[evento_cols]
        .astype("string")
        .fillna("")
        .agg("|".join, axis=1)
        .replace("", pd.NA)
        .dropna()
        .nunique()
    )
anios = pd.to_numeric(ddjj_unique["anio"], errors="coerce").dropna() if _has_column(ddjj_unique, "anio") else pd.Series(dtype=float)
primer_anio = int(anios.min()) if not anios.empty else None
ultimo_anio = int(anios.max()) if not anios.empty else None
sup_agri, sup_agri_available = _sum_with_availability(agricultura, "superficie_afectada")
if not sup_agri_available:
    sup_agri, sup_agri_available = _sum_with_availability(ddjj_unique, "superficie_agricola_afectada")
sup_gan, sup_gan_available = _sum_with_availability(ganaderia, "superficie_ganadera_afectada")
if not sup_gan_available:
    sup_gan, sup_gan_available = _sum_with_availability(ddjj_unique, "superficie_ganadera_afectada")
pondf_prom = pd.to_numeric(ddjj_unique["pondf"], errors="coerce").dropna().mean() if _has_column(ddjj_unique, "pondf") else None

st.subheader("Indicadores")
k1, k2, k3, k4 = st.columns(4)
k1.metric("DDJJ asociadas", format_count(ddjj_count))
k2.metric("Resoluciones / eventos", format_count(eventos_count))
k3.metric("Primer año", format_year(primer_anio))
k4.metric("Último año", format_year(ultimo_anio))

k5, k6, k7, k8 = st.columns(4)
k5.metric("Sup. agrícola afectada", _format_metric_ha(sup_agri, sup_agri_available, len(agricultura)))
k6.metric("Sup. ganadera afectada", _format_metric_ha(sup_gan, sup_gan_available, len(ganaderia)))
k7.metric("Registros agrícolas", format_count(len(agricultura)))
k8.metric("Registros ganaderos", format_count(len(ganaderia)))
st.caption(
    "La superficie afectada se muestra solo cuando existe en las declaraciones vinculadas; "
    "en registros ganaderos puede no estar informada en el mismo campo que agricultura."
)

k9, k10, _, _ = st.columns(4)
k9.metric("Daño promedio", format_percentage(pondf_prom, scale="0-100"))
k10.metric("Entregas/asistencias", format_count(len(entregas)) if entregas_data_available else "Sin datos")

tab_ddjj, tab_agri, tab_gan, tab_geo, tab_entregas, tab_calidad = st.tabs(
    [
        "DDJJ", "Agricultura", "Ganadería", "Adremas / establecimientos",
        "Entregas / asistencia", "Calidad de datos",
    ]
)

with tab_ddjj:
    st.subheader("DDJJ asociadas")
    if ddjj_unique.empty:
        st.info("No hay DDJJ asociadas para este productor.")
    else:
        ddjj_view = ddjj_unique.copy()
        agri_afectada = _numeric_series(ddjj_view, "superficie_agricola_afectada")
        gan_afectada = _numeric_series(ddjj_view, "superficie_ganadera_afectada")
        surface_parts = pd.concat([agri_afectada, gan_afectada], axis=1)
        ddjj_view["superficie_afectada"] = surface_parts.sum(axis=1, min_count=1)
        ddjj_view["resolucion_evento"] = ddjj_view["dto"].fillna(ddjj_view["evento_id"])
        labels = {
            "resolucion_evento": "Resolución / DTO",
            "anio": "Año",
            "fecha": "Fecha",
            "departamento": "Departamento",
            "localidad": "Localidad",
            "actividad": "Actividad",
            "pondf": "% daño ponderado",
            "superficie_afectada": "Sup. afectada",
        }
        ddjj_display = _rename_for_display(ddjj_view, labels)
        ddjj_display = _format_display_columns(
            ddjj_display,
            hectare_columns=["Sup. afectada"],
            percent_columns=["% daño ponderado"],
        )
        st.dataframe(
            _clean_display_table(ddjj_display),
            use_container_width=True,
            hide_index=True,
        )
        st.caption(
            "La tabla muestra declaraciones únicas. Los cultivos, rubros o categorías "
            "asociados se detallan en las pestañas Agricultura y Ganadería."
        )
        _render_technical_expander(ddjj, "ddjj")

with tab_agri:
    st.subheader("Agricultura")
    if agricultura.empty:
        st.info("No hay datos agrícolas asociados para este productor.")
    else:
        incluir_sd = st.checkbox("Incluir cultivos sin clasificar", value=False)
        agricultura_plot = agricultura.copy()
        agricultura_plot["sin_clasificar"] = _is_unclassified(agricultura_plot["cultivo"])
        sd = agricultura_plot[agricultura_plot["sin_clasificar"]].copy()
        if not incluir_sd:
            agricultura_plot = agricultura_plot[~agricultura_plot["sin_clasificar"]].copy()

        agricultura_plot["porcentaje_afectado"] = 0.0
        sembrada = pd.to_numeric(agricultura_plot["superficie_sembrada"], errors="coerce").fillna(0)
        afectada = pd.to_numeric(agricultura_plot["superficie_afectada"], errors="coerce").fillna(0)
        valid = sembrada > 0
        agricultura_plot.loc[valid, "porcentaje_afectado"] = afectada[valid] / sembrada[valid] * 100

        agri_labels = {
            "anio": DISPLAY_LABELS["anio"],
            "dto": DISPLAY_LABELS["dto"],
            "departamento": DISPLAY_LABELS["departamento"],
            "cultivo": DISPLAY_LABELS["cultivo"],
            "superficie_sembrada": DISPLAY_LABELS["superficie_sembrada"],
            "superficie_afectada": DISPLAY_LABELS["superficie_afectada"],
            "porcentaje_afectado": "% afectado",
        }
        agricultura_display = _rename_for_display(agricultura_plot, agri_labels)
        agricultura_display = _format_display_columns(
            agricultura_display,
            hectare_columns=["Sup. sembrada", "Sup. afectada"],
            percent_columns=["% afectado"],
        )
        st.dataframe(
            _clean_display_table(agricultura_display),
            use_container_width=True,
            hide_index=True,
        )
        _render_technical_expander(agricultura_plot, "agricultura")

        if not agricultura_plot.empty:
            top = (
                agricultura_plot.groupby("cultivo", dropna=False, as_index=False)
                .agg(
                    superficie_afectada=("superficie_afectada", "sum"),
                    superficie_sembrada=("superficie_sembrada", "sum"),
                    registros=("registros", "sum"),
                )
                .sort_values("superficie_afectada", ascending=False)
                .head(15)
            )
            top = top.sort_values("superficie_afectada", ascending=True)
            top["cultivo_label"] = top["cultivo"].apply(_short_label)
            fig = px.bar(
                top,
                x="superficie_afectada",
                y="cultivo_label",
                orientation="h",
                hover_data={
                    "cultivo": True,
                    "cultivo_label": False,
                    "superficie_afectada": ":,.2f",
                    "superficie_sembrada": ":,.2f",
                    "registros": ":,",
                },
                labels={
                    "superficie_afectada": "Superficie afectada (ha)",
                    "cultivo_label": "",
                    "cultivo": "Cultivo",
                    "superficie_sembrada": "Superficie sembrada (ha)",
                    "registros": "Registros",
                },
                title="Top cultivos por superficie afectada",
            )
            fig.update_layout(height=430, margin=dict(t=40, b=20, l=20, r=20))
            st.plotly_chart(fig, use_container_width=True)

        if not sd.empty and not incluir_sd:
            st.info(
                "Los cultivos sin clasificar se excluyen por defecto porque no representan "
                "un cultivo especifico. Puede incluirlos activando el filtro."
            )

with tab_gan:
    st.subheader("Ganadería")
    if ganaderia.empty:
        st.info("No hay datos ganaderos asociados para este productor.")
    else:
        gan = ganaderia.copy()
        gan["tasa_perdida"] = 0.0
        exist = pd.to_numeric(gan["existencias"], errors="coerce").fillna(0)
        mort = pd.to_numeric(gan["mortandad"], errors="coerce").fillna(0)
        valid = exist > 0
        gan.loc[valid, "tasa_perdida"] = mort[valid] / exist[valid] * 100
        gan_labels = {
            "anio": DISPLAY_LABELS["anio"],
            "dto": DISPLAY_LABELS["dto"],
            "departamento": DISPLAY_LABELS["departamento"],
            "categoria": DISPLAY_LABELS["categoria"],
            "existencias": DISPLAY_LABELS["existencias"],
            "mortandad": DISPLAY_LABELS["mortandad"],
            "tasa_perdida": DISPLAY_LABELS["tasa_perdida"],
            "superficie_ganadera_afectada": DISPLAY_LABELS["superficie_ganadera_afectada"],
        }
        gan_display = _rename_for_display(gan, gan_labels)
        gan_display = _format_display_columns(
            gan_display,
            hectare_columns=["Sup. ganadera afectada"],
            percent_columns=["Tasa de mortandad"],
        )
        st.dataframe(
            _clean_display_table(gan_display),
            use_container_width=True,
            hide_index=True,
        )
        _render_technical_expander(gan, "ganaderia")

        top_gan = (
            gan.groupby("categoria", dropna=False, as_index=False)
            .agg(mortandad=("mortandad", "sum"), existencias=("existencias", "sum"))
            .sort_values("mortandad", ascending=False)
            .head(15)
        )
        if pd.to_numeric(top_gan["mortandad"], errors="coerce").fillna(0).sum() > 0:
            top_gan = top_gan.sort_values("mortandad", ascending=True)
            top_gan["categoria_label"] = top_gan["categoria"].apply(_short_label)
            fig = px.bar(
                top_gan,
                x="mortandad",
                y="categoria_label",
                orientation="h",
                hover_data={
                    "categoria": True,
                    "categoria_label": False,
                    "mortandad": ":,.0f",
                    "existencias": ":,.0f",
                },
                labels={
                    "mortandad": "Pérdidas / mortandad",
                    "categoria_label": "",
                    "existencias": "Existencias",
                    "categoria": "Categoría",
                },
                title="Pérdidas ganaderas por categoría/especie",
            )
            fig.update_layout(height=420, margin=dict(t=40, b=20, l=20, r=20))
            st.plotly_chart(fig, use_container_width=True)

with tab_geo:
    st.subheader("Adremas / establecimientos")
    st.caption(
        "La vinculación de adremas/establecimientos se muestra solo cuando existe "
        "clave confiable en datos actuales."
    )
    if adremas.empty:
        st.info("No hay adremas o establecimientos asociados para este productor.")
    else:
        adremas_view = adremas.copy()
        adremas_labels = {
            "adrema": DISPLAY_LABELS["adrema"],
            "nombre_estab": DISPLAY_LABELS["nombre_estab"],
            "departamento": DISPLAY_LABELS["departamento"],
            "localidad": DISPLAY_LABELS["localidad"],
            "superficie": DISPLAY_LABELS["superficie"],
        }
        adremas_display = _rename_for_display(adremas_view, adremas_labels)
        if "Adrema" in adremas_display.columns:
            adremas_display["Adrema"] = adremas_display["Adrema"].map(format_adrema)
        if "Superficie" in adremas_display.columns:
            adremas_display["Superficie"] = adremas_display["Superficie"].map(format_surface)
        st.dataframe(
            _clean_display_table(adremas_display),
            use_container_width=True,
            hide_index=True,
        )
        _render_technical_expander(adremas, "adremas")

    with st.expander("Ponderaciones, mejoras y documentación actual"):
        if pd.isna(id_productor_actual):
            st.info("Estas secciones solo estan disponibles para productores con clave actual.")
        else:
            st.write("**Ponderaciones por rubro**")
            st.dataframe(_clean_display_table(ponderaciones), use_container_width=True, hide_index=True)
            st.write("**Pérdidas en mejoras**")
            st.dataframe(_clean_display_table(mejoras), use_container_width=True, hide_index=True)
            st.write("**Documentación**")
            st.dataframe(_clean_display_table(documentacion), use_container_width=True, hide_index=True)

with tab_entregas:
    _render_entregas_tab(
        entregas, entregas_quality, entregas_data_available,
        entregas_data_source, entregas_load_warning,
    )

with tab_calidad:
    st.subheader("Calidad de datos")
    alerts: list[dict[str, object]] = []
    alerts.append({"alerta": "Nombre faltante", "cantidad": int(not bool(_safe_str(nombre)))})
    alerts.append({"alerta": "Documento y CUIT faltantes", "cantidad": int(not _safe_str(documento) and not _safe_str(cuit))})
    alerts.append({"alerta": "DDJJ sin año/fecha", "cantidad": int((ddjj_unique["anio"].isna() & ddjj_unique["fecha"].isna()).sum()) if {"anio", "fecha"}.issubset(ddjj_unique.columns) else 0})
    alerts.append({"alerta": "DDJJ sin departamento/localidad", "cantidad": int((ddjj_unique["departamento"].fillna("").eq("") & ddjj_unique["localidad"].fillna("").eq("")).sum()) if {"departamento", "localidad"}.issubset(ddjj_unique.columns) else 0})
    alerts.append({"alerta": "Cultivos sin clasificar", "cantidad": int(_is_unclassified(agricultura["cultivo"]).sum()) if _has_column(agricultura, "cultivo") else 0})
    alerts.append({"alerta": "Registros con revisión manual", "cantidad": int(pd.to_numeric(ddjj_unique.get("flag_revision_manual", 0), errors="coerce").fillna(0).sum()) if not ddjj_unique.empty else 0})
    alerts.append({"alerta": "Registros críticos", "cantidad": int(ddjj_unique["severidad_maxima"].fillna("").str.lower().eq("critico").sum()) if _has_column(ddjj_unique, "severidad_maxima") else 0})

    alert_df = pd.DataFrame(alerts)
    st.dataframe(
        _clean_display_table(alert_df.rename(columns={"alerta": "Alerta", "cantidad": "Cantidad"})),
        use_container_width=True,
        hide_index=True,
    )

    if not ddjj.empty:
        st.write("**Trazabilidad de fuentes**")
        trace_cols = ["origen_dato", "source_file", "source_sheet", "dataset_role", "relation_type", "severidad_maxima"]
        trace = (
            ddjj[[c for c in trace_cols if c in ddjj.columns]]
            .fillna("(s/d)")
            .groupby([c for c in trace_cols if c in ddjj.columns], dropna=False)
            .size()
            .reset_index(name="registros")
            .sort_values("registros", ascending=False)
        )
        trace_labels = {
            "origen_dato": DISPLAY_LABELS["origen_dato"],
            "source_file": "Archivo fuente",
            "source_sheet": "Hoja fuente",
            "dataset_role": "Rol del conjunto",
            "relation_type": "Tipo de relación",
            "severidad_maxima": "Calidad",
            "registros": DISPLAY_LABELS["registros"],
        }
        st.dataframe(
            _clean_display_table(_rename_for_display(trace, trace_labels)),
            use_container_width=True,
            hide_index=True,
        )
