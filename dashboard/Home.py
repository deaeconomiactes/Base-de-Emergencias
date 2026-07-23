"""
Dashboard de Emergencias Agropecuarias - Home

Ejecutar:
    cd dashboard && streamlit run app.py
"""
from __future__ import annotations

import re

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
HOME_FILTER_KEYS = (
    "home_resolucion",
    "home_departamentos",
    "home_anios",
    "home_origen",
    "home_origen_actual",
    "home_periodo",
    "home_filtrar_pondf",
    "home_pondf_rango",
    "filtros",
)


def restablecer_filtros_home() -> None:
    for key in HOME_FILTER_KEYS:
        st.session_state.pop(key, None)


def texto_resolucion_legible(valor, *, truncar=False) -> str | None:
    if es_sin_dato(valor):
        return None
    texto = " ".join(str(valor).strip().split())
    compacto = re.sub(r"[-_]", "", texto)
    if len(compacto) >= 20 and re.fullmatch(r"[0-9a-fA-F]+", compacto):
        return None
    if len(texto) > 60:
        return f"{texto[:57].rstrip()}..." if truncar else None
    return texto


def opciones_resolucion_legibles(
    resoluciones: pd.DataFrame,
) -> tuple[list[str], dict[str, object]]:
    columnas_valor = (
        "dto",
        "resolucion",
        "numero_resolucion",
        "evento",
        "nombre_evento",
        "nombre_resolucion",
        "descripcion",
    )
    columnas_descripcion = (
        "actividad",
        "nombre_resolucion",
        "nombre_evento",
        "descripcion",
    )
    filas = []
    for _, row in resoluciones.iterrows():
        etiqueta_base = next(
            (
                texto
                for columna in columnas_valor
                if columna in resoluciones.columns
                and (texto := texto_resolucion_legible(row.get(columna)))
            ),
            None,
        )
        if not etiqueta_base:
            continue

        descripcion = next(
            (
                texto
                for columna in columnas_descripcion
                if columna in resoluciones.columns
                and (texto := texto_resolucion_legible(row.get(columna), truncar=True))
                and texto != etiqueta_base
            ),
            None,
        )

        anio = None
        if "anio" in resoluciones.columns:
            anio_num = pd.to_numeric(row.get("anio"), errors="coerce")
            if pd.notna(anio_num):
                anio = int(anio_num)
        if anio is None and "fec_res" in resoluciones.columns:
            fecha = pd.to_datetime(row.get("fec_res"), errors="coerce")
            if pd.notna(fecha):
                anio = int(fecha.year)

        origen = texto_resolucion_legible(row.get("origen_dato"))
        filas.append(
            {
                "base": etiqueta_base,
                "descripcion": descripcion,
                "anio": anio,
                "origen": origen,
                "valor_real": row.get("id_resolucion"),
            }
        )

    filas.sort(
        key=lambda item: (
            item["anio"] is None,
            -(item["anio"] or 0),
            item["base"].casefold(),
        )
    )
    repeticiones_base = pd.Series(
        [item["base"] for item in filas], dtype="string"
    ).value_counts()

    etiqueta_a_valor: dict[str, object] = {"Todas": None}
    for item in filas:
        partes = [item["base"]]
        if repeticiones_base.get(item["base"], 0) > 1:
            if item["anio"] is not None:
                partes.append(str(item["anio"]))
            if item["descripcion"]:
                partes.append(item["descripcion"])

        etiqueta = " · ".join(partes)
        if len(etiqueta) > 60:
            etiqueta = f"{etiqueta[:57].rstrip()}..."
        if etiqueta in etiqueta_a_valor and item["origen"]:
            origen_visible = {
                "actual": "Actual",
                "historico": "Histórico",
            }.get(item["origen"], item["origen"])
            sufijo = f" · {origen_visible}"
            etiqueta = f"{etiqueta[:60 - len(sufijo)].rstrip()}{sufijo}"

        etiqueta_original = etiqueta
        numero_opcion = 2
        while etiqueta in etiqueta_a_valor:
            sufijo = f" · {numero_opcion}"
            etiqueta = f"{etiqueta_original[:60 - len(sufijo)].rstrip()}{sufijo}"
            numero_opcion += 1
        etiqueta_a_valor[etiqueta] = item["valor_real"]

    return list(etiqueta_a_valor), etiqueta_a_valor


with st.sidebar:
    st.subheader("Filtros principales")
    resoluciones = list_resoluciones()
    res_options, resolucion_valor_real = opciones_resolucion_legibles(resoluciones)
    if st.session_state.get("home_resolucion") not in res_options:
        st.session_state.pop("home_resolucion", None)
    res_sel = st.selectbox("Resolución", res_options, key="home_resolucion")
    res_id = resolucion_valor_real[res_sel]
    if res_id is not None and not is_unified_mode():
        res_id = int(res_id)

    deps_df = run_query(
        f"SELECT DISTINCT departamento FROM {ddjj_table} "
        "WHERE departamento <> '' ORDER BY departamento"
    )
    dep_sel = st.multiselect(
        "Departamento",
        deps_df["departamento"].tolist(),
        placeholder="Todos",
        key="home_departamentos",
    )

    anios_df = run_query(
        f"SELECT DISTINCT YEAR(fecha) as anio "
        f"FROM {ddjj_table} {fecha_base_filter} ORDER BY anio DESC"
    )
    anios_list = [int(x) for x in anios_df["anio"].dropna().tolist()]
    anio_sel = st.multiselect(
        "Año",
        anios_list,
        placeholder="Todos",
        key="home_anios",
    )

    with st.expander("Filtros avanzados", expanded=False):
        if is_unified_mode():
            origen_sel = st.selectbox(
                "Fuente de datos",
                ["Todos", "actual", "historico"],
                format_func=lambda valor: {
                    "Todos": "Todos",
                    "actual": "Actual",
                    "historico": "Histórico",
                }[valor],
                key="home_origen",
            )
        else:
            origen_sel = st.selectbox(
                "Fuente de datos",
                ["actual"],
                format_func=lambda _valor: "Actual",
                disabled=True,
                key="home_origen_actual",
            )

        fechas_df = run_query(
            f"SELECT MIN(fecha) AS mn, MAX(fecha) AS mx "
            f"FROM {ddjj_table} {fecha_base_filter}"
        )
        fmin = pd.to_datetime(fechas_df.iloc[0]["mn"]).date()
        fmax = pd.to_datetime(fechas_df.iloc[0]["mx"]).date()
        rango = st.date_input(
            "Período",
            (fmin, fmax),
            min_value=fmin,
            max_value=fmax,
            key="home_periodo",
        )
        if isinstance(rango, tuple) and len(rango) == 2:
            f_desde, f_hasta = rango
        else:
            f_desde, f_hasta = fmin, fmax

        filtrar_pondf = st.checkbox(
            "Filtrar por daño ponderado",
            value=False,
            key="home_filtrar_pondf",
        )
        pondf_min = pondf_max = None
        if filtrar_pondf:
            pondf_min, pondf_max = st.slider(
                "Daño ponderado (%)",
                min_value=0,
                max_value=100,
                value=(0, 100),
                step=5,
                key="home_pondf_rango",
            )

    st.button(
        "Restablecer filtros",
        on_click=restablecer_filtros_home,
        use_container_width=True,
    )

    st.session_state["filtros"] = {
        "id_resolucion": res_id,
        "departamentos": dep_sel,
        "anios": anio_sel,
        "filtrar_pondf": filtrar_pondf,
        "pondf_min": pondf_min,
        "pondf_max": pondf_max,
        "f_desde": str(f_desde),
        "f_hasta": str(f_hasta),
        "origen_dato": (
            None if not is_unified_mode() or origen_sel == "Todos" else origen_sel
        ),
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


resolucion_texto = texto_filtro(res_sel, {"Todas"})
origen_texto = {
    "Todos": "Todos",
    "actual": "Actual",
    "historico": "Histórico",
}.get(origen_sel, texto_filtro(origen_sel))
departamento_texto = texto_filtro(dep_sel)
anio_texto = texto_filtro(anio_sel)
rango_fechas_texto = (
    f"{texto_valor(f_desde)} a {texto_valor(f_hasta)}"
    if not es_sin_dato(f_desde) and not es_sin_dato(f_hasta)
    else "Sin dato"
)
rango_dano_texto = "No aplicado"
if filtrar_pondf:
    rango_dano_texto = (
        f"{texto_valor(pondf_min)} % a {texto_valor(pondf_max)} %"
        if not es_sin_dato(pondf_min) and not es_sin_dato(pondf_max)
        else "Sin dato"
    )

with resumen_filtros.container():
    st.markdown("**Filtros activos**")
    rf1, rf2, rf3 = st.columns(3)
    rf1.caption(f"**Resolución:** {resolucion_texto}")
    rf2.caption(f"**Fuente de datos:** {origen_texto}")
    rf3.caption(f"**Departamento:** {departamento_texto}")
    rf4, rf5, rf6 = st.columns(3)
    rf4.caption(f"**Año:** {anio_texto}")
    rf5.caption(f"**Período:** {rango_fechas_texto}")
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
    if f.get("filtrar_pondf"):
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
        }
    ).copy()
    etiquetas_resolucion = df_top["Resolución / DTO"].astype("string").str.strip()
    etiquetas_sin_dato = etiquetas_resolucion.isna() | etiquetas_resolucion.str.casefold().isin(
        {"", "none", "nan", "null"}
    )
    df_top["Resolución / DTO"] = etiquetas_resolucion.mask(
        etiquetas_sin_dato, "Sin dato"
    ).astype(str)
    df_top["DDJJ"] = pd.to_numeric(df_top["DDJJ"], errors="coerce").fillna(0)
    df_consolidado_resoluciones = (
        df_top.groupby("Resolución / DTO", as_index=False, dropna=False)["DDJJ"]
        .sum()
    )
    ddjj_sin_resolucion = int(
        df_consolidado_resoluciones.loc[
            df_consolidado_resoluciones["Resolución / DTO"].eq("Sin dato"),
            "DDJJ",
        ].sum()
    )
    df_top = (
        df_consolidado_resoluciones.loc[
            ~df_consolidado_resoluciones["Resolución / DTO"].eq("Sin dato")
        ]
        .sort_values("DDJJ", ascending=False)
        .head(15)
    )
    df_top = df_top.sort_values("DDJJ", ascending=True)

    if not df_top.empty:
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
    else:
        st.info("No hay resoluciones informadas para los filtros seleccionados.")

    st.markdown(f"**DDJJ sin resolución informada:** {ddjj_sin_resolucion:,}")

    tabla_resoluciones_informadas = (
        df_top[["Resolución / DTO", "DDJJ"]]
        .sort_values("DDJJ", ascending=False)
        .reset_index(drop=True)
    )
    fila_sin_resolucion = pd.DataFrame(
        [{"Resolución / DTO": "Sin dato", "DDJJ": ddjj_sin_resolucion}]
    )
    tabla_resoluciones = pd.concat(
        [tabla_resoluciones_informadas, fila_sin_resolucion],
        ignore_index=True,
    )
    tabla_resoluciones["DDJJ"] = tabla_resoluciones["DDJJ"].astype(int)

    st.dataframe(tabla_resoluciones, hide_index=True, use_container_width=True)
    st.caption(
        "Las DDJJ sin número de resolución informado se reportan como Sin dato y "
        "se excluyen del ranking principal."
    )
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
