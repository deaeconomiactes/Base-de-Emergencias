"""Mapa operativo y resumen territorial DDJJ 2023."""
from __future__ import annotations

import pandas as pd
import pydeck as pdk
import streamlit as st

from utils import fix_coord, is_unified_mode, run_query

st.set_page_config(page_title="Mapa", layout="wide")
st.title("Mapa y resumen territorial")

unified = is_unified_mode()
with st.sidebar:
    st.header("Filtros")
    origen_sel = st.selectbox(
        "Origen de datos", ["(todos)", "actual", "ddjj_2023_excel"],
        format_func=lambda value: {"(todos)": "Todos", "actual": "Actual", "ddjj_2023_excel": "DDJJ 2023 Excel"}[value],
    ) if unified else "actual"
    anio_sel = st.selectbox("Año", ["(todos)", 2023]) if unified else "(todos)"

if unified and origen_sel in {"(todos)", "ddjj_2023_excel"}:
    st.warning(
        "La base DDJJ 2023 está integrada al registro, pero su representación cartográfica depende de la disponibilidad de geometrías/adremas unificadas."
    )
    territorial = run_query(
        """
        SELECT COALESCE(NULLIF(TRIM(departamento),''),'Sin departamento') AS departamento,
               COUNT(DISTINCT ddjj_all_id) AS ddjj,
               COUNT(DISTINCT productor_all_id) AS productores
        FROM vw_all_ddjj_personas
        WHERE origen_dato='ddjj_2023_excel' AND (:anio IS NULL OR anio=:anio)
        GROUP BY COALESCE(NULLIF(TRIM(departamento),''),'Sin departamento')
        ORDER BY ddjj DESC
        """,
        {"anio": None if anio_sel == "(todos)" else int(anio_sel)},
    )
    st.subheader("DDJJ 2023 por departamento (sin geometría)")
    st.dataframe(territorial, use_container_width=True, hide_index=True)

if origen_sel == "ddjj_2023_excel":
    st.info("No se dibujan puntos: la fuente 2023 no contiene coordenadas validadas.")
    st.stop()

params = {"anio": None if anio_sel == "(todos)" else int(anio_sel)}
df = run_query(
    """
    SELECT e.id_establecimiento, e.nombre_estab, e.departamento_estab,
           e.latitud, e.longitud, p.ProductorDenominacion AS productor,
           dj.id_ddjj, dj.pondf, ta.TipoActividadDesc AS actividad
    FROM establecimientos e
    LEFT JOIN ddjj_personas dj ON dj.id_ddjj=e.ddjj
    LEFT JOIN productores p ON p.ProductorId=dj.id_productor
    LEFT JOIN tipoactividad ta ON ta.TipoActividadId=p.EsPrincipalActividadEconomica
    WHERE e.latitud NOT IN ('','0') AND e.longitud NOT IN ('','0')
      AND (:anio IS NULL OR YEAR(dj.fecha)=:anio)
    """,
    params,
)
df["lat"] = df["latitud"].apply(fix_coord)
df["lng"] = df["longitud"].apply(fix_coord)
df = df.dropna(subset=["lat", "lng"])
df = df[df["lat"].between(-55, -21) & df["lng"].between(-74, -53)]
st.subheader("Establecimientos con coordenadas operativas")
st.caption(f"{len(df):,} establecimientos actuales con coordenadas válidas.")
if df.empty:
    st.info("No hay coordenadas válidas para los filtros seleccionados.")
    st.stop()
df["pondf_num"] = pd.to_numeric(df["pondf"], errors="coerce").fillna(0)
df["r"] = (df["pondf_num"].clip(0, 100) / 100 * 255).astype(int)
df["g"] = 80
df["b"] = (255 - df["r"]).clip(0, 255)
df["radius"] = 400
layer = pdk.Layer("ScatterplotLayer", data=df, get_position="[lng, lat]", get_radius="radius", get_fill_color="[r,g,b,180]", pickable=True)
view = pdk.ViewState(latitude=float(df["lat"].mean()), longitude=float(df["lng"].mean()), zoom=6.5)
st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view, map_style="light", tooltip={"html": "<b>{nombre_estab}</b><br/>Productor: {productor}<br/>DDJJ: {id_ddjj}<br/>Depto: {departamento_estab}"}))
st.dataframe(df[["nombre_estab", "productor", "departamento_estab", "actividad", "pondf", "lat", "lng"]], use_container_width=True, hide_index=True)
