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

# ---------- Encabezado ----------
info = db_info()
st.title("Registro de Emergencias Agropecuarias")
st.caption(
    "Tablero de seguimiento de declaraciones juradas, productores, "
    "resoluciones y afectación agropecuaria."
)


def es_sin_dato(valor) -> bool:
    if valor is None:
        return True
    if isinstance(valor, str):
        return not valor.strip()
    try:
        return bool(pd.isna(valor))
    except (TypeError, ValueError):
        return False


def texto_valor(valor) -> str:
    return "Sin dato" if es_sin_dato(valor) else str(valor)


with st.expander("Información técnica"):
    st.markdown(
        f"- **Fuente:** {texto_valor(info.get('source'))}\n"
        f"- **Host:** `{texto_valor(info.get('host'))}`\n"
        f"- **Base:** `{texto_valor(info.get('db'))}`\n"
        f"- **Modo:** `{texto_valor(info.get('mode'))}`"
    )

resumen_filtros = st.empty()

ddjj_table = table("ddjj_personas")
res_table = table("resoluciones")
fecha_base_filter = "" if is_unified_mode() else "WHERE fecha > '2000-01-01'"

# ---------- KPIs ----------
kpis = kpis_generales()


def formato_conteo(valor) -> str:
    return "Sin dato" if es_sin_dato(valor) else f"{int(valor):,}"


def formato_porcentaje(valor) -> str:
    return "Sin dato" if es_sin_dato(valor) else f"{valor:.1f}%"


c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Productores", formato_conteo(kpis["productores"]))
c2.metric("DDJJ", formato_conteo(kpis["ddjj"]))
c3.metric("Resoluciones", formato_conteo(kpis["resoluciones"]))
c4.metric("Establecimientos", formato_conteo(kpis["establecimientos"]))
c5.metric("Adremas", formato_conteo(kpis["adremas"]))
c6.metric("Daño promedio", formato_porcentaje(kpis["pondf_promedio"]))

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


def texto_filtro(valor, marcadores_todos=()) -> str:
    if isinstance(valor, (list, tuple)):
        if not valor:
            return "Todos"
        valores = [texto_valor(item) for item in valor]
        return ", ".join(valores)
    if es_sin_dato(valor):
        return "Sin dato"
    if valor in marcadores_todos:
        return "Todos"
    return str(valor)


resolucion_texto = texto_filtro(res_sel, {"(todas)"})
origen_texto = texto_filtro(origen_sel, {"(todos)"})
departamento_texto = texto_filtro(dep_sel)
anio_texto = texto_filtro(anio_sel)
rango_fechas_texto = (
    f"{texto_valor(f_desde)} a {texto_valor(f_hasta)}"
    if not es_sin_dato(f_desde) and not es_sin_dato(f_hasta)
    else "Sin dato"
)
rango_dano_texto = (
    f"{texto_valor(pondf_min)} % a {texto_valor(pondf_max)} %"
    if not es_sin_dato(pondf_min) and not es_sin_dato(pondf_max)
    else "Sin dato"
)

with resumen_filtros.container():
    st.markdown("**Filtros activos**")
    rf1, rf2, rf3 = st.columns(3)
    rf1.caption(f"**Resolución:** {resolucion_texto}")
    rf2.caption(f"**Origen de datos:** {origen_texto}")
    rf3.caption(f"**Departamento:** {departamento_texto}")
    rf4, rf5, rf6 = st.columns(3)
    rf4.caption(f"**Año:** {anio_texto}")
    rf5.caption(f"**Rango de fechas:** {rango_fechas_texto}")
    rf6.caption(f"**Daño ponderado:** {rango_dano_texto}")


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

# ---------- Evolucion anual de DDJJ ----------
st.subheader("Evolución anual de DDJJ")
df_evolucion = run_query(
    f"""
    SELECT YEAR(dj.fecha) AS anio, COUNT(*) AS ddjj
    FROM {ddjj_table} dj
    WHERE {where_sql}
    GROUP BY YEAR(dj.fecha)
    ORDER BY anio
    """,
    params,
)
if not df_evolucion.empty:
    df_evolucion["ddjj"] = pd.to_numeric(
        df_evolucion["ddjj"], errors="coerce"
    ).fillna(0)
    registros_sin_anio = int(
        df_evolucion.loc[df_evolucion["anio"].isna(), "ddjj"].sum()
    )
    df_evolucion_anual = (
        df_evolucion.dropna(subset=["anio"])
        .rename(columns={"anio": "Año", "ddjj": "DDJJ"})
        .copy()
    )
    df_evolucion_anual["Año"] = df_evolucion_anual["Año"].astype(int)
    df_evolucion_anual["DDJJ"] = df_evolucion_anual["DDJJ"].astype(int)

    if not df_evolucion_anual.empty:
        anio_min = int(df_evolucion_anual["Año"].min())
        anio_max = int(df_evolucion_anual["Año"].max())
        rango_anual = pd.DataFrame({"Año": range(anio_min, anio_max + 1)})
        df_evolucion_anual = rango_anual.merge(
            df_evolucion_anual,
            on="Año",
            how="left",
        )
        df_evolucion_anual["DDJJ"] = df_evolucion_anual["DDJJ"].fillna(0).astype(int)
        df_evolucion_anual["Etiqueta"] = df_evolucion_anual["DDJJ"].map(
            lambda valor: f"{valor:,}" if valor > 0 else ""
        )

        fig = px.bar(
            df_evolucion_anual,
            x="Año",
            y="DDJJ",
            text="Etiqueta",
        )
        fig.update_traces(
            texttemplate="%{text}",
            textposition="outside",
            cliponaxis=False,
            hovertemplate="Año: %{x}<br>DDJJ: %{y:,}<extra></extra>",
        )
        fig.update_xaxes(title_text="Año", tickmode="linear", dtick=1)
        fig.update_yaxes(title_text="Cantidad de DDJJ")
        fig.update_layout(
            title_text="",
            height=360,
            showlegend=False,
            margin=dict(l=45, r=25, t=25, b=40),
        )
        st.plotly_chart(fig, use_container_width=True)

        tabla_evolucion = df_evolucion_anual[["Año", "DDJJ"]].copy()
        tabla_evolucion["DDJJ"] = tabla_evolucion["DDJJ"].map(
            lambda valor: f"{valor:,}"
        )
        with st.expander("Ver tabla de evolución anual"):
            st.dataframe(tabla_evolucion, hide_index=True, use_container_width=True)

        st.caption(
            "La serie anual se calcula con el campo fecha disponible y los filtros "
            "activos. Los años con cero indican ausencia de registros en el conjunto "
            "filtrado, no necesariamente ausencia comprobada de emergencias. La "
            "cobertura histórica puede depender de la disponibilidad de fecha, año "
            "informado y daño ponderado."
        )
        if registros_sin_anio:
            st.caption(
                f"Registros sin año disponible: {registros_sin_anio:,}."
            )
    else:
        st.info("No hay datos temporales para los filtros seleccionados.")
        if registros_sin_anio:
            st.caption(f"Registros sin año disponible: {registros_sin_anio:,}.")
else:
    st.info("No hay datos temporales para los filtros seleccionados.")

# ---------- DDJJ por Resolucion ----------
st.divider()
st.subheader("Top resoluciones por cantidad de DDJJ")
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
    df_top = df_res.rename(
        columns={
            "resolucion": "Resolución / DTO",
            "ddjj": "DDJJ",
            "nombre": "Nombre",
            "anio": "Año",
            "departamentos": "Departamentos",
        }
    ).copy()
    df_top["Resolución / DTO"] = (
        df_top["Resolución / DTO"]
        .fillna("Sin dato")
        .astype(str)
        .str.strip()
        .replace("", "Sin dato")
    )
    df_top["DDJJ"] = pd.to_numeric(df_top["DDJJ"], errors="coerce").fillna(0)
    df_top = df_top.sort_values("DDJJ", ascending=False).head(15)
    df_top = df_top.sort_values("DDJJ", ascending=True)

    columnas_opcionales = [
        col for col in ["Nombre", "Año", "Departamentos"] if col in df_top.columns
    ]
    for column in columnas_opcionales:
        df_top[column] = df_top[column].map(texto_valor)

    fig = px.bar(
        df_top,
        x="DDJJ",
        y="Resolución / DTO",
        orientation="h",
        text="DDJJ",
    )
    fig.update_traces(
        texttemplate="%{text:,.0f}",
        textposition="outside",
        cliponaxis=False,
    )
    fig.update_yaxes(type="category", title_text="Resolución / DTO")
    fig.update_xaxes(title_text="Cantidad de DDJJ")
    fig.update_layout(
        title=None,
        height=max(360, 28 * len(df_top) + 100),
        showlegend=False,
        margin=dict(l=120, r=40, t=20, b=40),
    )
    fig.update_layout(title_text="")
    fig.update_layout(
        annotations=[
            annotation
            for annotation in (fig.layout.annotations or ())
            if str(annotation.text).strip().lower() != "undefined"
        ]
    )
    st.plotly_chart(fig, use_container_width=True)

    columnas_tabla = ["Resolución / DTO", "DDJJ"]
    columnas_tabla.extend(
        col for col in ["Año", "Departamentos"] if col in df_top.columns
    )
    tabla_resoluciones = (
        df_top[columnas_tabla]
        .sort_values("DDJJ", ascending=False)
        .reset_index(drop=True)
    )
    tabla_resoluciones["DDJJ"] = tabla_resoluciones["DDJJ"].astype(int)

    st.dataframe(tabla_resoluciones, hide_index=True, use_container_width=True)
else:
    st.info("No hay declaraciones juradas para los filtros seleccionados.")

# ---------- DDJJ por Departamento (top 12) ----------
left, right = st.columns(2)
with left:
    st.subheader("Top departamentos por cantidad de DDJJ")
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
        df_departamentos = df_dep.rename(
            columns={
                "departamento": "Departamento",
                "ddjj": "DDJJ",
                "productores": "Productores",
                "resoluciones": "Resoluciones",
            }
        ).copy()
        df_departamentos["Departamento"] = (
            df_departamentos["Departamento"]
            .fillna("Sin dato")
            .astype(str)
            .str.strip()
            .replace("", "Sin dato")
        )
        df_departamentos["DDJJ"] = pd.to_numeric(
            df_departamentos["DDJJ"], errors="coerce"
        ).fillna(0)
        df_top_deptos = (
            df_departamentos.sort_values("DDJJ", ascending=False)
            .head(12)
            .sort_values("DDJJ", ascending=True)
        )

        fig = px.bar(
            df_top_deptos,
            x="DDJJ",
            y="Departamento",
            orientation="h",
            text="DDJJ",
        )
        fig.update_traces(
            texttemplate="%{text:,.0f}",
            textposition="outside",
            cliponaxis=False,
        )
        fig.update_yaxes(type="category", title_text="Departamento")
        fig.update_xaxes(title_text="Cantidad de DDJJ")
        fig.update_layout(
            title_text="",
            height=max(360, 24 * len(df_top_deptos) + 80),
            showlegend=False,
            margin=dict(l=80, r=25, t=10, b=35),
        )
        st.plotly_chart(fig, use_container_width=True)

        columnas_departamentos = ["Departamento", "DDJJ"]
        columnas_departamentos.extend(
            col
            for col in ["Productores", "Resoluciones"]
            if col in df_departamentos.columns
        )
        tabla_departamentos = (
            df_top_deptos[columnas_departamentos]
            .sort_values("DDJJ", ascending=False)
            .reset_index(drop=True)
        )
        tabla_departamentos["DDJJ"] = tabla_departamentos["DDJJ"].astype(int)
        tabla_departamentos_mostrar = tabla_departamentos.copy()
        tabla_departamentos_mostrar["DDJJ"] = tabla_departamentos_mostrar[
            "DDJJ"
        ].map(lambda valor: f"{valor:,}")
        with st.expander("Ver tabla de departamentos"):
            st.dataframe(
                tabla_departamentos_mostrar,
                hide_index=True,
                use_container_width=True,
            )
    else:
        st.info("No hay departamentos para los filtros seleccionados.")

# ---------- Distribucion de % dano ----------
with right:
    st.subheader("Declaraciones por tramo de daño")
    df_p = run_query(
        f"""
        SELECT dj.pondf
        FROM {ddjj_table} dj
        WHERE {where_sql}
        """,
        params,
    )
    if not df_p.empty:
        valores_dano = pd.to_numeric(df_p["pondf"], errors="coerce")

        def clasificar_tramo_dano(valor) -> str:
            if pd.isna(valor) or valor < 0:
                return "Sin dato"
            if valor <= 25:
                return "0% a 25%"
            if valor <= 50:
                return "25% a 50%"
            if valor <= 75:
                return "50% a 75%"
            if valor <= 100:
                return "75% a 100%"
            return "Más de 100%"

        orden_tramos = [
            "0% a 25%",
            "25% a 50%",
            "50% a 75%",
            "75% a 100%",
            "Más de 100%",
            "Sin dato",
        ]
        tramos_dano = valores_dano.map(clasificar_tramo_dano)
        conteos_tramos = tramos_dano.value_counts().reindex(orden_tramos, fill_value=0)
        tabla_dano = conteos_tramos.rename_axis("Tramo de daño").reset_index(name="DDJJ")
        total_dano = int(tabla_dano["DDJJ"].sum())
        tabla_dano["Participación"] = (
            tabla_dano["DDJJ"] / total_dano * 100 if total_dano else 0.0
        )
        tabla_dano["Tramo de daño"] = tabla_dano["Tramo de daño"].astype(str)

        grafico_dano = tabla_dano.loc[tabla_dano["DDJJ"] > 0].copy()
        if not grafico_dano.empty:
            fig = px.bar(
                grafico_dano,
                x="Tramo de daño",
                y="DDJJ",
                text="DDJJ",
            )
            fig.update_traces(
                texttemplate="%{text:,.0f}",
                textposition="outside",
                cliponaxis=False,
            )
            fig.update_xaxes(
                title_text="Tramo de daño",
                type="category",
                categoryorder="array",
                categoryarray=orden_tramos,
            )
            fig.update_yaxes(title_text="Cantidad de DDJJ")
            fig.update_layout(
                title_text="",
                height=360,
                showlegend=False,
                margin=dict(l=35, r=20, t=10, b=50),
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No hay datos de daño para los filtros seleccionados.")

        tabla_dano_mostrar = tabla_dano.copy()
        tabla_dano_mostrar["DDJJ"] = tabla_dano_mostrar["DDJJ"].map(
            lambda valor: f"{int(valor):,}"
        )
        tabla_dano_mostrar["Participación"] = tabla_dano_mostrar[
            "Participación"
        ].map(lambda valor: f"{valor:.1f}%")
        with st.expander("Ver tabla de tramos de daño"):
            st.dataframe(
                tabla_dano_mostrar,
                hide_index=True,
                use_container_width=True,
            )
        st.caption(
            "El daño ponderado se agrupa en tramos. Los registros sin porcentaje "
            "informado se clasifican como Sin dato cuando no son excluidos por "
            "filtros activos."
        )
    else:
        st.info("No hay datos de daño para los filtros seleccionados.")

st.divider()
st.caption(
    "Usa el menu lateral para navegar entre: Productores | Detalle DDJJ | "
    "Adremas | Mapa | Analisis."
)
