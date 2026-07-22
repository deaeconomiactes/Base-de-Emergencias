"""
Dashboard de Emergencias Agropecuarias - Home

Ejecutar:
    cd dashboard && streamlit run app.py
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from utils import (
    db_info,
    is_unified_mode,
    kpis_generales,
    list_resoluciones,
    run_query,
    table,
)

st.set_page_config(
    page_title="Emergencias Agropecuarias",
    page_icon="AG",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------- Encabezado ----------
info = db_info()
st.title("Sistema de Emergencias Agropecuarias")
st.caption(
    f"Conectado a: **{info['source']}** | `{info['host']}` | "
    f"base `{info['db']}` | modo `{info['mode']}`"
)

ddjj_table = table("ddjj_personas")
res_table = table("resoluciones")
fecha_base_filter = "" if is_unified_mode() else "WHERE fecha > '2000-01-01'"

# ---------- KPIs ----------
kpis = kpis_generales()


def formato_conteo(valor) -> str:
    return "Sin dato" if valor is None else f"{int(valor):,}"


def formato_porcentaje(valor) -> str:
    return "Sin dato" if valor is None else f"{valor:.1f}%"


c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Productores", formato_conteo(kpis["productores"]))
c2.metric("DDJJ", formato_conteo(kpis["ddjj"]))
c3.metric("Resoluciones", formato_conteo(kpis["resoluciones"]))
c4.metric("Establecimientos", formato_conteo(kpis["establecimientos"]))
c5.metric("Adremas", formato_conteo(kpis["adremas"]))
c6.metric("% dano promedio", formato_porcentaje(kpis["pondf_promedio"]))

st.divider()

# ---------- Filtros globales ----------
with st.sidebar:
    st.header("Filtros")
    resoluciones = list_resoluciones()
    res_options = ["(todas)"] + [
        f"{row.id_resolucion} - {row.nombre_resolucion}"
        for row in resoluciones.itertuples()
    ]
    res_sel = st.selectbox("Resolucion", res_options)
    res_id = None
    if res_sel != "(todas)":
        raw_res_id = res_sel.split(" - ", 1)[0]
        res_id = raw_res_id if is_unified_mode() else int(raw_res_id)

    origen_sel = "(todos)"
    if is_unified_mode():
        origen_sel = st.selectbox("Origen de datos", ["(todos)", "actual", "historico"])

    deps_df = run_query(
        f"SELECT DISTINCT departamento FROM {ddjj_table} "
        "WHERE departamento <> '' ORDER BY departamento"
    )
    dep_sel = st.multiselect("Departamento", deps_df["departamento"].tolist())

    pondf_min, pondf_max = st.slider(
        "% de dano (pondf)", min_value=0, max_value=100, value=(0, 100), step=5
    )

    anios_df = run_query(
        f"SELECT DISTINCT YEAR(fecha) as anio "
        f"FROM {ddjj_table} {fecha_base_filter} ORDER BY anio DESC"
    )
    anios_list = [int(x) for x in anios_df["anio"].dropna().tolist()]
    anio_sel = st.multiselect("Anio", anios_list)

    fechas_df = run_query(
        f"SELECT MIN(fecha) AS mn, MAX(fecha) AS mx "
        f"FROM {ddjj_table} {fecha_base_filter}"
    )
    fmin = pd.to_datetime(fechas_df.iloc[0]["mn"]).date()
    fmax = pd.to_datetime(fechas_df.iloc[0]["mx"]).date()
    rango = st.date_input("Rango de fechas", (fmin, fmax), min_value=fmin, max_value=fmax)
    if isinstance(rango, tuple) and len(rango) == 2:
        f_desde, f_hasta = rango
    else:
        f_desde, f_hasta = fmin, fmax

    st.session_state["filtros"] = {
        "id_resolucion": res_id,
        "departamentos": dep_sel,
        "anios": anio_sel,
        "pondf_min": pondf_min,
        "pondf_max": pondf_max,
        "f_desde": str(f_desde),
        "f_hasta": str(f_hasta),
        "origen_dato": None if origen_sel == "(todos)" else origen_sel,
    }


# WHERE dinamico para reutilizar
def where_filtros(prefix="dj.") -> tuple[str, dict]:
    f = st.session_state.get("filtros", {})
    conds = [f"{prefix}fecha BETWEEN :f_desde AND :f_hasta"]
    params = {"f_desde": f["f_desde"], "f_hasta": f["f_hasta"]}
    if f.get("id_resolucion"):
        if is_unified_mode():
            conds.append(
                "EXISTS ("
                f"SELECT 1 FROM {res_table} rf "
                "WHERE rf.resolucion_all_id = :id_res "
                f"AND rf.origen_dato = {prefix}origen_dato "
                f"AND ((rf.origen_dato = 'actual' AND rf.id_resolucion_actual = {prefix}id_resolucion_actual) "
                f"OR (rf.origen_dato = 'historico' AND rf.evento_id = {prefix}evento_id))"
                ")"
            )
        else:
            conds.append(f"{prefix}id_resolucion = :id_res")
        params["id_res"] = f["id_resolucion"]
    if f.get("departamentos"):
        placeholders = []
        for i, d in enumerate(f["departamentos"]):
            k = f"dep{i}"
            placeholders.append(f":{k}")
            params[k] = d
        conds.append(f"{prefix}departamento IN ({','.join(placeholders)})")
    if f.get("anios"):
        placeholders_a = []
        for i, a in enumerate(f["anios"]):
            k = f"anio{i}"
            placeholders_a.append(f":{k}")
            params[k] = a
        conds.append(f"YEAR({prefix}fecha) IN ({','.join(placeholders_a)})")
    if is_unified_mode() and f.get("origen_dato"):
        conds.append(f"{prefix}origen_dato = :origen_dato")
        params["origen_dato"] = f["origen_dato"]
    conds.append(f"{prefix}pondf BETWEEN :p_min AND :p_max")
    params["p_min"] = f["pondf_min"]
    params["p_max"] = f["pondf_max"]
    return " AND ".join(conds), params


where_sql, params = where_filtros()

# ---------- DDJJ por Resolucion ----------
st.subheader("DDJJ por Resolucion")
if is_unified_mode():
    df_res = run_query(
        f"""
        SELECT r.numero_resolucion AS resolucion, r.nombre_resolucion AS nombre,
               COUNT(*) AS ddjj
        FROM {ddjj_table} dj
        JOIN {res_table} r
          ON r.origen_dato = dj.origen_dato
         AND ((r.origen_dato = 'actual' AND r.id_resolucion_actual = dj.id_resolucion_actual)
              OR (r.origen_dato = 'historico' AND r.evento_id = dj.evento_id))
        WHERE {where_sql}
        GROUP BY r.numero_resolucion, r.nombre_resolucion
        ORDER BY ddjj DESC
        """,
        params,
    )
else:
    df_res = run_query(
        f"""
        SELECT r.numero_resolucion AS resolucion, r.nombre_resolucion AS nombre,
               COUNT(*) AS ddjj
        FROM {ddjj_table} dj
        JOIN {res_table} r ON r.id_resolucion = dj.id_resolucion
        WHERE {where_sql}
        GROUP BY r.numero_resolucion, r.nombre_resolucion
        ORDER BY ddjj DESC
        """,
        params,
    )
if not df_res.empty:
    fig = px.bar(
        df_res,
        x="resolucion",
        y="ddjj",
        hover_data=["nombre"],
        labels={"resolucion": "Resolucion", "ddjj": "DDJJ"},
    )
    fig.update_layout(height=380, margin=dict(t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Sin datos para los filtros seleccionados.")

# ---------- DDJJ por Departamento (top 15) ----------
left, right = st.columns(2)
with left:
    st.subheader("Top 15 Departamentos")
    df_dep = run_query(
        f"""
        SELECT dj.departamento, COUNT(*) AS ddjj,
               ROUND(AVG(dj.pondf),1) AS pondf_prom
        FROM {ddjj_table} dj
        WHERE {where_sql} AND dj.departamento<>''
        GROUP BY dj.departamento
        ORDER BY ddjj DESC
        LIMIT 15
        """,
        params,
    )
    if not df_dep.empty:
        fig = px.bar(
            df_dep,
            x="ddjj",
            y="departamento",
            orientation="h",
            hover_data=["pondf_prom"],
            labels={"ddjj": "DDJJ", "departamento": "", "pondf_prom": "% prom."},
        )
        fig.update_layout(height=460, yaxis=dict(autorange="reversed"), margin=dict(t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)

# ---------- Distribucion de % dano ----------
with right:
    st.subheader("Distribucion de % de dano")
    df_p = run_query(
        f"""
        SELECT dj.pondf
        FROM {ddjj_table} dj
        WHERE {where_sql} AND dj.pondf > 0
        """,
        params,
    )
    if not df_p.empty:
        fig = px.histogram(df_p, x="pondf", nbins=20, labels={"pondf": "% de dano"})
        fig.update_layout(height=460, margin=dict(t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)

# ---------- DDJJ por mes ----------
st.subheader("Evolucion mensual de DDJJ")
df_t = run_query(
    f"""
    SELECT DATE_FORMAT(dj.fecha,'%Y-%m') AS mes, COUNT(*) AS ddjj,
           ROUND(AVG(dj.pondf),1) AS pondf_prom
    FROM {ddjj_table} dj
    WHERE {where_sql}
    GROUP BY mes
    ORDER BY mes
    """,
    params,
)
if not df_t.empty:
    fig = px.line(df_t, x="mes", y="ddjj", markers=True, hover_data=["pondf_prom"])
    fig.update_layout(height=360, margin=dict(t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)

st.divider()
st.caption(
    "Usa el menu lateral para navegar entre: Productores | Detalle DDJJ | "
    "Adremas | Mapa | Analisis."
)
