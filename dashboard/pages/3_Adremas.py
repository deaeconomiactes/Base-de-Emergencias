"""Pares trámite + ADREMA del registro integrado."""
from __future__ import annotations

import streamlit as st

from utils import is_unified_mode, run_query

st.set_page_config(page_title="Adremas", layout="wide")
st.title("Adremas (parcelas catastrales)")
st.caption(
    "Pares trámite + ADREMA del registro integrado. En DDJJ 2023 se muestra "
    "una sola fila por par trámite + ADREMA."
)

unified = is_unified_mode()

if unified:
    available_years = run_query(
        """
        SELECT DISTINCT anio FROM (
            SELECT YEAR(dj.fecha) AS anio
            FROM adremas a
            JOIN ddjj_personas dj ON dj.id_ddjj=a.ddjj
            WHERE a.adrema IS NOT NULL AND TRIM(a.adrema)<>''
            UNION
            SELECT anio
            FROM stg_ddjj_2023_tramite
            WHERE anio IS NOT NULL
        ) years_available
        WHERE anio IS NOT NULL
        ORDER BY anio DESC
        """
    )
    year_options = ["(todos)"] + available_years["anio"].astype(int).tolist()
else:
    year_options = ["(todos)"]

with st.sidebar:
    st.header("Filtros")
    q = st.text_input("Adrema o productor contiene", "")
    if unified:
        origen_sel = st.selectbox(
            "Origen de datos",
            ["(todos)", "actual", "ddjj_2023_excel"],
            format_func=lambda value: {
                "(todos)": "Todos",
                "actual": "Registro histórico/operativo",
                "ddjj_2023_excel": "DDJJ 2023 Excel",
            }[value],
        )
        anio_sel = st.selectbox("Año", year_options)
    else:
        origen_sel, anio_sel = "actual", "(todos)"
    sup_min = st.number_input(
        "Superficie mínima (ha)", min_value=0.0, value=0.0, step=10.0
    )
    limite = st.slider("Filas máximas", 50, 5000, 500, step=50)

parts: list[str] = []
if origen_sel in {"(todos)", "actual"}:
    parts.append(
        """
        SELECT CAST(a.ddjj AS CHAR) AS tramite_id,
               a.adrema,
               a.superficie,
               ta.TipoActividadDesc AS actividad,
               a.departamento,
               NULL AS municipio,
               NULL AS localidad,
               e.paraje_estab AS paraje,
               p.ProductorDenominacion AS productor,
               p.CUITCUIL AS cuit_cuil,
               YEAR(dj.fecha) AS anio,
               r.numero_resolucion AS norma_evento,
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
        SELECT a.tramite_id,
               a.adrema,
               a.superficie,
               COALESCE(a.actividad_normalizada_preliminar,a.actividad_original) AS actividad,
               a.departamento,
               a.municipio,
               a.localidad,
               a.paraje,
               d.productor_nombre AS productor,
               d.cuit_cuil,
               d.anio,
               d.dto AS norma_evento,
               a.origen_dato
        FROM stg_ddjj_2023_adrema a
        JOIN vw_all_ddjj_personas d
          ON d.origen_dato='ddjj_2023_excel'
         AND d.ddjj_hist_id=a.tramite_id
        WHERE a.adrema_unica_indicador=1
        """
    )

integrated_sql = " UNION ALL ".join(parts)
params: dict = {
    "q": f"%{q}%",
    "sup_min": sup_min,
    "limite": limite,
}
filters = [
    "base.adrema IS NOT NULL",
    "TRIM(base.adrema)<>''",
    "(:q='%%' OR base.adrema LIKE :q OR base.productor LIKE :q)",
    "(:sup_min=0 OR COALESCE(base.superficie,0)>=:sup_min)",
]
if anio_sel != "(todos)":
    filters.append("base.anio=:anio")
    params["anio"] = int(anio_sel)
where = " AND ".join(filters)

summary = run_query(
    f"""
    SELECT anio, origen_dato, COUNT(*) AS pares_tramite_adrema,
           SUM(COALESCE(superficie,0)) AS superficie_visible
    FROM ({integrated_sql}) base
    WHERE {where}
    GROUP BY anio, origen_dato
    ORDER BY anio DESC, origen_dato
    """,
    params,
)

total_pairs = int(summary["pares_tramite_adrema"].sum()) if not summary.empty else 0
total_surface = summary["superficie_visible"].fillna(0).sum() if not summary.empty else 0

# El orden intercalado evita que el límite visual oculte años/fuentes completos
# cuando el usuario solicita el universo integrado sin filtros temporales.
df = run_query(
    f"""
    SELECT tramite_id, adrema, superficie, actividad, departamento,
           municipio, localidad, paraje, productor, cuit_cuil, anio,
           norma_evento, origen_dato
    FROM (
        SELECT base.*,
               ROW_NUMBER() OVER (
                   PARTITION BY base.anio, base.origen_dato
                   ORDER BY base.superficie DESC, base.tramite_id, base.adrema
               ) AS orden_muestra
        FROM ({integrated_sql}) base
        WHERE {where}
    ) ranked
    ORDER BY orden_muestra, anio DESC, origen_dato, superficie DESC
    LIMIT :limite
    """,
    params,
)

st.caption(
    f"Universo filtrado: **{total_pairs:,}** pares trámite + ADREMA · "
    f"superficie informada: **{total_surface:,.2f} ha**. "
    f"La tabla muestra **{len(df):,}** filas por el límite visual seleccionado."
)
st.dataframe(df, use_container_width=True, hide_index=True, height=570)

with st.expander("Cobertura por año y fuente", expanded=True):
    st.dataframe(summary, use_container_width=True, hide_index=True)

st.download_button(
    "Descargar muestra CSV",
    df.to_csv(index=False).encode("utf-8-sig"),
    "adremas.csv",
    "text/csv",
)
