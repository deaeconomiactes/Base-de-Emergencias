"""Detalle trazable de una declaración en el registro unificado."""
from __future__ import annotations

import streamlit as st

from utils import is_unified_mode, run_query

st.set_page_config(page_title="Detalle DDJJ", layout="wide")
st.title("Detalle de una DDJJ")

if not is_unified_mode():
    st.warning("Esta página requiere `DATA_MODE=unificado` para incluir DDJJ 2023 Excel.")

identifier = st.text_input(
    "Identificador (ddjj_all_id, tramite_id o id_ddjj actual)", value=""
).strip()
if not identifier:
    st.info("Ingrese un identificador. Los trámites 2023 pueden buscarse por `tramite_id`.")
    st.stop()

cab = run_query(
    """
    SELECT ddjj_all_id, id_ddjj_actual, ddjj_hist_id AS tramite_id,
           productor_all_id, productor_nombre, cuit_cuil, documento_nro,
           fecha, anio, evento_id, dto AS norma_evento, periodo,
           departamento, localidad, paraje, actividad, pondf,
           superficie_total, source_file, source_sheet, origen_dato,
           flag_revision_manual, severidad_maxima
    FROM vw_all_ddjj_personas
    WHERE ddjj_all_id=:identifier OR ddjj_hist_id=:identifier
       OR iddj=:identifier OR codigo=:identifier OR solicitud_id=:identifier
       OR CAST(id_ddjj_actual AS CHAR)=:identifier
    ORDER BY CASE WHEN ddjj_all_id=:identifier THEN 0 ELSE 1 END
    LIMIT 2
    """,
    {"identifier": identifier},
)
if cab.empty:
    st.warning("No existe una DDJJ con ese identificador en el registro unificado.")
    st.stop()
if len(cab) > 1:
    st.warning("El identificador coincide con más de un origen; use `ddjj_all_id`.")
row = cab.iloc[0]

c1, c2, c3 = st.columns([2, 2, 1])
c1.markdown(f"### {row['productor_nombre'] or 's/d'}")
c1.write(f"**CUIT/CUIL:** {row['cuit_cuil'] or '—'} · **Documento:** {row['documento_nro'] or '—'}")
c2.write(f"**Norma / evento:** {row['norma_evento'] or '—'}  \n**Evento ID:** {row['evento_id'] or '—'}  \n**Fuente:** {row['origen_dato']}")
c3.metric("% daño ponderado", "—" if row["pondf"] is None else f"{row['pondf']:.2f}%")
st.write(
    f"**DDJJ:** {row['ddjj_all_id']} · **Trámite:** {row['tramite_id'] or '—'} · "
    f"**Fecha:** {row['fecha']} · **Ubicación:** {row['departamento'] or '—'} / "
    f"{row['localidad'] or '—'} / {row['paraje'] or '—'}"
)
if row["origen_dato"] == "ddjj_2023_excel":
    st.caption(
        "Numero Certificado no se expone como norma: Decreto 2099/23 proviene del bridge normativo validado."
    )

origin = row["origen_dato"]
current_id = row["id_ddjj_actual"]
historic_id = row["tramite_id"]
params = {"origin": origin, "current_id": current_id, "historic_id": historic_id}
join_filter = "origen_dato=:origin AND ((:current_id IS NOT NULL AND id_ddjj_actual=:current_id) OR (:historic_id IS NOT NULL AND ddjj_hist_id=:historic_id))"

t_ag, t_gan, t_adr, t_trace = st.tabs(["Agricultura", "Ganadería", "Adremas", "Trazabilidad"])
with t_ag:
    agri = run_query(
        f"""SELECT COALESCE(especie,cultivo,categoria) AS producto,
                    superficie_sembrada_uso, superficie_afectada,
                    produccion_estimada, produccion_obtenida, source_sheet,
                    flag_revision_manual, severidad_maxima
             FROM vw_all_agricultura WHERE {join_filter}""",
        params,
    )
    st.dataframe(agri, use_container_width=True, hide_index=True)
with t_gan:
    gan = run_query(
        f"""SELECT especie, categoria, existencias, mortandad,
                    superficie_ganadera_uso, superficie_ganadera_afectada,
                    source_sheet, flag_mortandad_mayor_existencias,
                    flag_revision_manual, severidad_maxima
             FROM vw_all_ganaderia_resumen WHERE {join_filter}""",
        params,
    )
    st.dataframe(gan, use_container_width=True, hide_index=True)
    if origin == "ddjj_2023_excel":
        st.caption("Las medidas inválidas por reglas de calidad se mantienen nulas en la vista analítica.")
with t_adr:
    if origin == "ddjj_2023_excel":
        adr = run_query(
            """SELECT adrema, superficie, actividad_original AS actividad,
                      departamento, municipio, localidad, paraje,
                      source_row_number, dq_adrema_duplicada_en_tramite
               FROM stg_ddjj_2023_adrema
               WHERE tramite_id=:tramite_id AND adrema_unica_indicador=1
               ORDER BY adrema""",
            {"tramite_id": historic_id},
        )
    elif current_id is not None:
        adr = run_query(
            "SELECT adrema, superficie, departamento FROM adremas WHERE ddjj=:id",
            {"id": int(current_id)},
        )
    else:
        adr = run_query("SELECT NULL AS adrema WHERE 1=0")
    st.dataframe(adr, use_container_width=True, hide_index=True)
with t_trace:
    st.dataframe(cab, use_container_width=True, hide_index=True)
