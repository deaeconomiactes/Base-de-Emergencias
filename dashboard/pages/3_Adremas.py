"""Listado de ADREMAS actuales y DDJJ 2023 con granularidad controlada."""
from __future__ import annotations

import streamlit as st

from utils import is_unified_mode, run_query

st.set_page_config(page_title="Adremas", layout="wide")
st.title("Adremas (parcelas catastrales)")

unified = is_unified_mode()
with st.sidebar:
    st.header("Filtros")
    q = st.text_input("Adrema o productor contiene", "")
    origen_sel = st.selectbox(
        "Origen de datos", ["(todos)", "actual", "ddjj_2023_excel"],
        format_func=lambda value: {"(todos)": "Todos", "actual": "Actual", "ddjj_2023_excel": "DDJJ 2023 Excel"}[value],
    ) if unified else "actual"
    anio_sel = st.selectbox("Año", ["(todos)", 2023]) if unified else "(todos)"
    sup_min = st.number_input("Superficie mínima (ha)", min_value=0.0, value=0.0, step=10.0)
    limite = st.slider("Filas máximas", 50, 5000, 500, step=50)

parts = []
if origen_sel in {"(todos)", "actual"}:
    parts.append(
        """
        SELECT CAST(a.ddjj AS CHAR) AS tramite_id, a.adrema, a.superficie,
               ta.TipoActividadDesc AS actividad, a.departamento,
               NULL AS municipio, NULL AS localidad, e.paraje_estab AS paraje,
               p.ProductorDenominacion AS productor, p.CUITCUIL AS cuit_cuil,
               YEAR(dj.fecha) AS anio, r.numero_resolucion AS norma_evento,
               'actual' AS origen_dato
        FROM adremas a
        LEFT JOIN tipoactividad ta ON ta.TipoActividadId=a.actividad
        LEFT JOIN establecimientos e ON e.id_establecimiento=a.id_establecimiento
        JOIN ddjj_personas dj ON dj.id_ddjj=a.ddjj
        LEFT JOIN productores p ON p.ProductorId=dj.id_productor
        LEFT JOIN resoluciones r ON r.id_resolucion=dj.id_resolucion
        """
    )
if unified and origen_sel in {"(todos)", "ddjj_2023_excel"}:
    parts.append(
        """
        SELECT a.tramite_id, a.adrema, a.superficie,
               COALESCE(a.actividad_normalizada_preliminar,a.actividad_original) AS actividad,
               a.departamento, a.municipio, a.localidad, a.paraje,
               d.productor_nombre AS productor, d.cuit_cuil,
               d.anio, d.dto AS norma_evento, a.origen_dato
        FROM stg_ddjj_2023_adrema a
        JOIN vw_all_ddjj_personas d
          ON d.origen_dato='ddjj_2023_excel' AND d.ddjj_hist_id=a.tramite_id
        WHERE a.adrema_unica_indicador=1
        """
    )

params = {"q": f"%{q}%", "sup_min": sup_min, "limite": limite}
year_clause = "AND base.anio=:anio" if anio_sel != "(todos)" else ""
if anio_sel != "(todos)":
    params["anio"] = int(anio_sel)
sql = " UNION ALL ".join(parts)
df = run_query(
    f"""
    SELECT * FROM ({sql}) base
    WHERE (base.adrema IS NOT NULL AND TRIM(base.adrema)<>'')
      AND (:q='%%' OR base.adrema LIKE :q OR base.productor LIKE :q)
      AND COALESCE(base.superficie,0)>=:sup_min
      {year_clause}
    ORDER BY base.superficie DESC LIMIT :limite
    """,
    params,
)
st.caption(
    f"{len(df):,} pares trámite + ADREMA · superficie visible: "
    f"{df['superficie'].fillna(0).sum():,.2f} ha. En DDJJ 2023 se muestra una sola fila por par."
)
st.dataframe(df, use_container_width=True, hide_index=True, height=620)
st.download_button("Descargar CSV", df.to_csv(index=False).encode("utf-8-sig"), "adremas.csv", "text/csv")
