"""Listado unificado y búsqueda de productores."""
from __future__ import annotations

import re

import streamlit as st

from utils import display_identifier, is_unified_mode, run_query

st.set_page_config(page_title="Productores", layout="wide")
st.title("Productores")

unified = is_unified_mode()


def _numeric_search(value: str) -> str | None:
    if re.search(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", value):
        return None
    digits = re.sub(r"[^0-9]", "", re.sub(r"\.0$", "", value.strip()))
    return digits or None

with st.sidebar:
    st.header("Filtros")
    q = st.text_input("Nombre / CUIT / Documento", "")
    if unified:
        anios_df = run_query(
            "SELECT DISTINCT anio FROM vw_all_ddjj_personas "
            "WHERE anio IS NOT NULL ORDER BY anio DESC"
        )
        anio_sel = st.selectbox(
            "Año", ["(todos)"] + anios_df["anio"].astype(int).tolist()
        )
        origen_sel = st.selectbox(
            "Origen de datos",
            ["(todos)", "actual", "historico", "ddjj_2023_excel"],
            format_func=lambda value: {
                "(todos)": "Todos",
                "actual": "Actual",
                "historico": "Histórico",
                "ddjj_2023_excel": "DDJJ 2023 Excel",
            }[value],
        )
        norma_sel = st.selectbox(
            "Norma / evento", ["(todas)", "Decreto 2099/23"]
        )
    else:
        anio_sel, origen_sel, norma_sel = "(todos)", "actual", "(todas)"
    limite = st.slider("Filas máximas", 50, 3000, 500, step=50)

if unified:
    conds = ["1=1"]
    params: dict = {"limite": limite}
    if q:
        numeric_q = _numeric_search(q)
        conds.append(
            "(p.productor_nombre LIKE :q OR p.cuit_cuil LIKE :q "
            "OR p.documento_nro LIKE :q "
            "OR (:q_digits IS NOT NULL AND ("
            "REGEXP_REPLACE(REGEXP_REPLACE(COALESCE(p.cuit_cuil,''), '\\\\.0$', ''), '[^0-9]', '') LIKE :q_digits_like "
            "OR REGEXP_REPLACE(REGEXP_REPLACE(COALESCE(p.documento_nro,''), '\\\\.0$', ''), '[^0-9]', '') LIKE :q_digits_like)))"
        )
        params["q"] = f"%{q}%"
        params["q_digits"] = numeric_q
        params["q_digits_like"] = f"%{numeric_q}%" if numeric_q else None
    if origen_sel != "(todos)":
        conds.append("p.origen_dato = :origen")
        params["origen"] = origen_sel
    ddjj_conds = ["d.productor_all_id = p.productor_all_id"]
    if anio_sel != "(todos)":
        ddjj_conds.append("d.anio = :anio")
        params["anio"] = int(anio_sel)
    if norma_sel != "(todas)":
        ddjj_conds.append("d.dto = :norma")
        params["norma"] = norma_sel
    if origen_sel != "(todos)":
        ddjj_conds.append("d.origen_dato = :origen")
    if anio_sel != "(todos)" or norma_sel != "(todas)":
        conds.append(
            "EXISTS (SELECT 1 FROM vw_all_ddjj_personas d WHERE "
            + " AND ".join(ddjj_conds)
            + ")"
        )
    where = " AND ".join(conds)
    df = run_query(
        f"""
        SELECT p.productor_all_id AS productor_id, p.productor_nombre AS productor,
               p.cuit_cuil, p.documento_nro, p.actividad, p.departamento,
               p.localidad, p.renspa, p.origen_dato,
               COUNT(DISTINCT d.ddjj_all_id) AS ddjj,
               GROUP_CONCAT(DISTINCT d.dto ORDER BY d.dto SEPARATOR '; ') AS normativa
        FROM vw_all_productores p
        LEFT JOIN vw_all_ddjj_personas d
          ON d.productor_all_id = p.productor_all_id
         {"AND d.anio = :anio" if anio_sel != "(todos)" else ""}
         {"AND d.dto = :norma" if norma_sel != "(todas)" else ""}
         {"AND d.origen_dato = :origen" if origen_sel != "(todos)" else ""}
        WHERE {where}
        GROUP BY p.productor_all_id, p.productor_nombre, p.cuit_cuil,
                 p.documento_nro, p.actividad, p.departamento, p.localidad,
                 p.renspa, p.origen_dato
        ORDER BY p.productor_nombre
        LIMIT :limite
        """,
        params,
    )
else:
    numeric_q = _numeric_search(q)
    params = {
        "limite": limite,
        "q": f"%{q}%",
        "q_digits": numeric_q,
        "q_digits_like": f"%{numeric_q}%" if numeric_q else None,
    }
    df = run_query(
        """
        SELECT CAST(p.ProductorId AS CHAR) AS productor_id,
               p.ProductorDenominacion AS productor, p.CUITCUIL AS cuit_cuil,
               p.DocumentoNro AS documento_nro, ta.TipoActividadDesc AS actividad,
               dep.DepartamentoDesc AS departamento, loc.LocalidadDesc AS localidad,
               p.renspa, 'actual' AS origen_dato,
               COUNT(DISTINCT dj.id_ddjj) AS ddjj, NULL AS normativa
        FROM productores p
        LEFT JOIN tipoactividad ta ON ta.TipoActividadId=p.EsPrincipalActividadEconomica
        LEFT JOIN domicilios dom ON dom.DomicilioId=p.DomicilioId
        LEFT JOIN departamentos dep ON dep.DepartamentoId=dom.DepartamentoId
        LEFT JOIN localidades loc ON loc.LocalidadId=dom.LocalidadId
        LEFT JOIN ddjj_personas dj ON dj.id_productor=p.ProductorId
        WHERE (:q = '%%' OR p.ProductorDenominacion LIKE :q
               OR p.CUITCUIL LIKE :q OR p.DocumentoNro LIKE :q
               OR (:q_digits IS NOT NULL AND (
                   REGEXP_REPLACE(REGEXP_REPLACE(COALESCE(p.CUITCUIL,''), '\\.0$', ''), '[^0-9]', '') LIKE :q_digits_like
                   OR REGEXP_REPLACE(REGEXP_REPLACE(COALESCE(p.DocumentoNro,''), '\\.0$', ''), '[^0-9]', '') LIKE :q_digits_like)))
        GROUP BY p.ProductorId, p.ProductorDenominacion, p.CUITCUIL,
                 p.DocumentoNro, ta.TipoActividadDesc, dep.DepartamentoDesc,
                 loc.LocalidadDesc, p.renspa
        ORDER BY p.ProductorDenominacion LIMIT :limite
        """,
        params,
    )

st.caption(f"Mostrando **{len(df):,}** productores sin multiplicarlos por sus detalles.")
df_display = df.copy()
df_display["cuit_cuil"] = df_display["cuit_cuil"].apply(lambda value: display_identifier(value, "cuit_cuil"))
df_display["documento_nro"] = df_display["documento_nro"].apply(lambda value: display_identifier(value, "documento"))
st.dataframe(df_display, use_container_width=True, hide_index=True, height=590)

if unified and not df.empty:
    selected = st.selectbox(
        "Ver DDJJ de un productor",
        df["productor_id"].astype(str).tolist(),
        format_func=lambda value: str(
            df.loc[df["productor_id"].astype(str).eq(value), "productor"].iloc[0]
        ),
    )
    ddjj = run_query(
        """
        SELECT ddjj_all_id, ddjj_hist_id AS tramite_id, fecha, anio,
               dto AS norma_evento, departamento, localidad, actividad,
               origen_dato
        FROM vw_all_ddjj_personas
        WHERE productor_all_id=:productor_id
        ORDER BY fecha DESC, ddjj_all_id
        """,
        {"productor_id": selected},
    )
    st.subheader("DDJJ asociadas")
    st.dataframe(ddjj, use_container_width=True, hide_index=True)
    st.info("Use `ddjj_all_id` o `tramite_id` en la página Detalle DDJJ.")
