"""Mapa operativo y resumen territorial del universo DDJJ unificado."""
from __future__ import annotations

import pandas as pd
import pydeck as pdk
import streamlit as st

from display_format import clean_display_name, format_count, format_percentage, format_year
from data_quality_rules import METHODOLOGY_NOTE, quality_status, unsuitable_ids
from utils import fix_coord, is_unified_mode, run_query

st.title("Mapa y resumen territorial")

unified = is_unified_mode()
with st.sidebar:
    st.header("Filtros")
    if unified:
        anios_df = run_query(
            "SELECT DISTINCT anio FROM vw_all_ddjj_personas "
            "WHERE anio IS NOT NULL ORDER BY anio DESC"
        )
    else:
        anios_df = run_query(
            "SELECT DISTINCT YEAR(fecha) AS anio FROM ddjj_personas "
            "WHERE fecha IS NOT NULL ORDER BY anio DESC"
        )
    anios = ["(todos)"] + [int(value) for value in anios_df["anio"].dropna()]
    anio_sel = st.selectbox(
        "Año", anios,
        format_func=lambda value: "Todos" if value == "(todos)" else format_year(value),
    )

params = {"anio": None if anio_sel == "(todos)" else int(anio_sel)}
totals = run_query(
    """SELECT COUNT(*) AS total FROM establecimientos e
       LEFT JOIN ddjj_personas dj ON dj.id_ddjj=e.ddjj
       WHERE (:anio IS NULL OR YEAR(dj.fecha)=:anio)""",
    params,
)
total_establishments = int(totals.iloc[0]["total"]) if not totals.empty else 0
adremas_without_gps = 0
if unified and params["anio"] in {None, 2023}:
    adremas_result = run_query(
        "SELECT COUNT(DISTINCT adrema_id_2023) AS total "
        "FROM stg_ddjj_2023_adrema WHERE COALESCE(dq_tramite_huerfano,0)=0"
    )
    adremas_without_gps = int(adremas_result.iloc[0]["total"]) if not adremas_result.empty else 0
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
map_excluded_ids = unsuitable_ids(
    "Georreferenciación y mapa", "registro_id", "apto_mapa"
)
if map_excluded_ids:
    df = df[~df["id_establecimiento"].astype(str).isin(map_excluded_ids)].copy()
st.subheader("Establecimientos con coordenadas operativas")
coverage = len(df) / total_establishments * 100 if total_establishments else 0.0
m1, m2, m3, m4 = st.columns(4)
m1.metric("Establecimientos totales", format_count(total_establishments))
m2.metric("ADREMAS sin coordenadas", format_count(adremas_without_gps))
m3.metric("Georreferenciados aptos", format_count(len(df)))
m4.metric("Cobertura de establecimientos", format_percentage(coverage, scale="0-100"))
if adremas_without_gps:
    st.caption(
        "Las ADREMAS sin coordenadas forman parte del universo territorial no georreferenciado "
        "y no se convierten automáticamente en puntos ni establecimientos."
    )
st.caption(METHODOLOGY_NOTE)
if quality_status()["estado"] not in {"local_disponible", "tidb_staging"}:
    st.warning(
        "Las banderas locales de aptitud no están disponibles. El mapa aplica únicamente "
        "las validaciones de coordenadas presentes en la página; para paridad completa en "
        "Streamlit Cloud se deben publicar las banderas en TiDB o una vista analítica."
    )
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
map_display = df[["nombre_estab", "productor", "departamento_estab", "actividad", "pondf", "lat", "lng"]].copy()
map_display = map_display.rename(columns={"nombre_estab": "Establecimiento", "productor": "Productor", "departamento_estab": "Departamento", "actividad": "Actividad", "pondf": "Daño ponderado", "lat": "Latitud", "lng": "Longitud"})
for column in ["Establecimiento", "Productor", "Departamento", "Actividad"]:
    map_display[column] = map_display[column].map(clean_display_name)
map_display["Daño ponderado"] = map_display["Daño ponderado"].map(lambda value: format_percentage(value, scale="0-100"))
map_display["Latitud"] = pd.to_numeric(map_display["Latitud"], errors="coerce").round(6)
map_display["Longitud"] = pd.to_numeric(map_display["Longitud"], errors="coerce").round(6)
st.dataframe(map_display, use_container_width=True, hide_index=True)
