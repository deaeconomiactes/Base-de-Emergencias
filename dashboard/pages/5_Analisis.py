"""Analisis agregado: cultivos, ganaderia, mejoras."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from utils import is_unified_mode, run_query, table

st.set_page_config(page_title="Analisis", layout="wide")
st.title("Analisis agregado")

unified = is_unified_mode()
res_table = table("resoluciones")
agri_table = table("agricultura")
gan_table = table("ganaderia_resumen")


def short_label(value, max_len: int = 48) -> str:
    text = str(value or "(s/d)").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "..."


def add_percent(df: pd.DataFrame, numerator: str, denominator: str, output: str) -> pd.DataFrame:
    df[output] = 0.0
    valid = df[denominator].fillna(0) > 0
    df.loc[valid, output] = df.loc[valid, numerator].fillna(0) / df.loc[valid, denominator] * 100
    return df


SIN_CLASIFICAR = {"", "(s/d)", "s/d", "sd", "sin dato", "sin datos", "none", "nan"}


def is_unclassified_category(series: pd.Series) -> pd.Series:
    return series.astype("string").fillna("").str.strip().str.lower().isin(SIN_CLASIFICAR)


# ---------- Controles ----------
if unified:
    res = run_query(
        f"SELECT resolucion_all_id AS id_resolucion, numero_resolucion, "
        f"nombre_resolucion FROM {res_table} ORDER BY fec_res DESC"
    )
    anios_df = run_query(
        f"""
        SELECT DISTINCT anio FROM (
            SELECT anio FROM {agri_table}
            UNION ALL
            SELECT anio FROM {gan_table}
        ) x
        WHERE anio IS NOT NULL
        ORDER BY anio DESC
        """
    )
else:
    res = run_query(
        "SELECT id_resolucion, numero_resolucion, nombre_resolucion "
        "FROM resoluciones ORDER BY fec_res DESC"
    )
    anios_df = run_query(
        "SELECT DISTINCT YEAR(fecha) AS anio FROM ddjj_personas "
        "WHERE fecha IS NOT NULL ORDER BY anio DESC"
    )

with st.container():
    c1, c2, c3, c4 = st.columns([2.2, 1, 1, 1.1])
    with c1:
        opciones = ["(todas)"] + [
            f"{r.id_resolucion} - {r.numero_resolucion}" for r in res.itertuples()
        ]
        sel = st.selectbox("Resolucion", opciones)
    with c2:
        top_n = st.selectbox("Top N", [10, 20, 30, 50], index=1)
    with c3:
        anios = ["(todos)"] + [int(x) for x in anios_df["anio"].dropna().tolist()]
        anio_sel = st.selectbox("Anio", anios)
    with c4:
        origen_sel = "(todos)"
        if unified:
            origen_sel = st.selectbox("Origen de datos", ["(todos)", "actual", "historico"])

metric_order = st.segmented_control(
    "Ordenar cultivos por",
    ["superficie afectada", "superficie sembrada", "porcentaje afectado"],
    default="superficie afectada",
)
superficie_minima_pct = 10.0
if metric_order == "porcentaje afectado":
    superficie_minima_pct = st.number_input(
        "Superficie sembrada minima para ranking porcentual (ha)",
        min_value=0.0,
        value=10.0,
        step=10.0,
    )

id_res = None
res_num = None
if sel != "(todas)":
    raw_id, raw_num = sel.split(" - ", 1)
    id_res = raw_id if unified else int(raw_id)
    res_num = raw_num

params_unified: dict = {}
params_actual: dict = {}
filters_unified = ["1=1"]
filters_actual = ["1=1"]

if id_res is not None:
    if unified:
        filters_unified.append("dto = :res_num")
        params_unified["res_num"] = res_num
    else:
        filters_actual.append("dj.id_resolucion = :id_res")
        params_actual["id_res"] = id_res

if anio_sel != "(todos)":
    if unified:
        filters_unified.append("anio = :anio")
        params_unified["anio"] = int(anio_sel)
    else:
        filters_actual.append("YEAR(dj.fecha) = :anio")
        params_actual["anio"] = int(anio_sel)

if unified and origen_sel != "(todos)":
    filters_unified.append("origen_dato = :origen_dato")
    params_unified["origen_dato"] = origen_sel

where_unified = " AND ".join(filters_unified)
where_actual = " AND ".join(filters_actual)

# ---------- Cultivos: hectareas afectadas vs sembradas ----------
st.subheader("Cultivos - superficie sembrada vs afectada")
incluir_cultivos_sin_clasificar = st.checkbox(
    "Incluir cultivos sin clasificar",
    value=False,
)
if unified:
    cultivos = run_query(
        f"""
        SELECT COALESCE(especie, cultivo, '(s/d)') AS tipo_cultivo,
               SUM(superficie_sembrada_uso) AS sembrada,
               SUM(superficie_afectada) AS afectada,
               COUNT(*) AS registros,
               COUNT(DISTINCT COALESCE(CAST(id_ddjj_actual AS CHAR), ddjj_hist_id, iddj, codigo, solicitud_id)) AS ddjj
        FROM {agri_table}
        WHERE {where_unified}
        GROUP BY COALESCE(especie, cultivo, '(s/d)')
        HAVING COALESCE(sembrada, 0) > 0 OR COALESCE(afectada, 0) > 0
        """,
        params_unified,
    )
else:
    cultivos = run_query(
        f"""
        SELECT COALESCE(ct.CultivoTipoDesc, c.CultivoDesc, '(s/d)') AS tipo_cultivo,
               SUM(a.sup_sembrada) AS sembrada,
               SUM(a.sup_afectada) AS afectada,
               COUNT(*) AS registros,
               COUNT(DISTINCT a.ddjj) AS ddjj
        FROM agricultura a
        LEFT JOIN cultivostipo ct ON ct.id = a.tipo_cultivo
        LEFT JOIN cultivos c ON c.id = a.id_cultivo
        JOIN ddjj_personas dj ON dj.id_ddjj = a.ddjj
        WHERE {where_actual}
        GROUP BY COALESCE(ct.CultivoTipoDesc, c.CultivoDesc, '(s/d)')
        HAVING COALESCE(sembrada, 0) > 0 OR COALESCE(afectada, 0) > 0
        """,
        params_actual,
    )

if not cultivos.empty:
    cultivos = add_percent(cultivos, "afectada", "sembrada", "pct_afectado")
    cultivos["sin_clasificar"] = is_unclassified_category(cultivos["tipo_cultivo"])
    sin_clasificar = cultivos[cultivos["sin_clasificar"]].copy()
    total_afectada = cultivos["afectada"].fillna(0).sum()

    if not incluir_cultivos_sin_clasificar:
        cultivos = cultivos[~cultivos["sin_clasificar"]].copy()

    if not cultivos.empty:
        order_column = {
            "superficie afectada": "afectada",
            "superficie sembrada": "sembrada",
            "porcentaje afectado": "pct_afectado",
        }[metric_order]
        if metric_order == "porcentaje afectado" and superficie_minima_pct > 0:
            cultivos = cultivos[cultivos["sembrada"].fillna(0) >= superficie_minima_pct].copy()
            st.caption(
                "Se excluyen cultivos con superficie sembrada menor a "
                f"{superficie_minima_pct:,.0f} ha para evitar porcentajes extremos "
                "sobre bases muy pequenas."
            )

        if cultivos.empty:
            st.info("No quedan cultivos para el ranking con el filtro de superficie minima seleccionado.")
        else:
            cultivos = cultivos.sort_values(order_column, ascending=False).head(top_n).copy()
            cultivos = cultivos.sort_values(order_column, ascending=True)
            cultivos["cultivo_label"] = cultivos["tipo_cultivo"].apply(short_label)

            if metric_order == "porcentaje afectado":
                fig = px.bar(
                    cultivos,
                    x="pct_afectado",
                    y="cultivo_label",
                    orientation="h",
                    hover_data={
                        "tipo_cultivo": True,
                        "cultivo_label": False,
                        "pct_afectado": ":.1f",
                        "sembrada": ":,.2f",
                        "afectada": ":,.2f",
                        "registros": ":,",
                        "ddjj": ":,",
                    },
                    labels={
                        "pct_afectado": "% superficie afectada",
                        "cultivo_label": "",
                        "tipo_cultivo": "Cultivo",
                        "sembrada": "Superficie sembrada (ha)",
                        "afectada": "Superficie afectada (ha)",
                        "registros": "Registros",
                        "ddjj": "DDJJ",
                    },
                    title="Cultivos - porcentaje de superficie afectada",
                )
                fig.update_xaxes(range=[0, max(100, float(cultivos["pct_afectado"].max() or 0))])
            else:
                cultivos_m = cultivos.melt(
                    id_vars=["tipo_cultivo", "cultivo_label", "pct_afectado", "registros", "ddjj"],
                    value_vars=["sembrada", "afectada"],
                    var_name="medida",
                    value_name="hectareas",
                )
                fig = px.bar(
                    cultivos_m,
                    x="hectareas",
                    y="cultivo_label",
                    color="medida",
                    orientation="h",
                    barmode="group",
                    hover_data={
                        "tipo_cultivo": True,
                        "cultivo_label": False,
                        "hectareas": ":,.0f",
                        "pct_afectado": ":.1f",
                        "registros": ":,",
                        "ddjj": ":,",
                    },
                    labels={
                        "hectareas": "Hectareas",
                        "cultivo_label": "",
                        "medida": "Superficie",
                        "pct_afectado": "% afectado",
                        "registros": "Registros",
                        "ddjj": "DDJJ",
                    },
                )
            fig.update_layout(height=max(460, top_n * 24), margin=dict(t=20, b=20, l=20, r=20))
            st.plotly_chart(fig, use_container_width=True)
            st.caption(f"Se muestran los primeros {len(cultivos)} cultivos segun {metric_order}.")
    else:
        st.info("No quedan cultivos clasificados para los filtros seleccionados.")

    if not sin_clasificar.empty:
        registros_sd = int(sin_clasificar["registros"].fillna(0).sum())
        ddjj_sd = int(sin_clasificar["ddjj"].fillna(0).sum())
        sembrada_sd = sin_clasificar["sembrada"].fillna(0).sum()
        afectada_sd = sin_clasificar["afectada"].fillna(0).sum()
        pct_afectada_sd = afectada_sd / total_afectada * 100 if total_afectada else 0
        st.info(
            "Los registros sin cultivo clasificado se excluyen del ranking por defecto "
            "porque no representan un cultivo especifico. Puede incluirlos activando el filtro.\n\n"
            f"Registros sin clasificar: {registros_sd:,}. "
            f"DDJJ asociadas: {ddjj_sd:,}. "
            f"Superficie sembrada: {sembrada_sd:,.2f} ha. "
            f"Superficie afectada: {afectada_sd:,.2f} ha "
            f"({pct_afectada_sd:.2f}% de la superficie afectada agricola filtrada)."
        )
else:
    st.info("Sin datos agricolas para los filtros seleccionados.")

# ---------- Ganaderia: existencias, mortandad y tasa ----------
st.subheader("Ganaderia - existencias, mortandad y tasa")
if unified:
    ganaderia = run_query(
        f"""
        SELECT COALESCE(categoria, especie, actividad, 'GANADERIA') AS categoria,
               SUM(existencias) AS existencias,
               SUM(mortandad) AS mortandad
        FROM {gan_table}
        WHERE {where_unified}
        GROUP BY COALESCE(categoria, especie, actividad, 'GANADERIA')
        HAVING COALESCE(existencias, 0) > 0 OR COALESCE(mortandad, 0) > 0
        """,
        params_unified,
    )
else:
    ganaderia = run_query(
        f"""
        SELECT
          'Vacas' AS categoria, SUM(b.cantivaca) AS existencias, SUM(b.mortavaca) AS mortandad
          FROM bovinos b JOIN ddjj_personas dj ON dj.id_ddjj=b.idddjj WHERE {where_actual}
        UNION ALL SELECT 'Vaquillonas', SUM(cantivaqui), SUM(mortavaqui)
          FROM bovinos b JOIN ddjj_personas dj ON dj.id_ddjj=b.idddjj WHERE {where_actual}
        UNION ALL SELECT 'Terneros', SUM(cantiterne), SUM(mortaterne)
          FROM bovinos b JOIN ddjj_personas dj ON dj.id_ddjj=b.idddjj WHERE {where_actual}
        UNION ALL SELECT 'Novillos', SUM(cantinovi), SUM(mortanovi)
          FROM bovinos b JOIN ddjj_personas dj ON dj.id_ddjj=b.idddjj WHERE {where_actual}
        UNION ALL SELECT 'Novillitos', SUM(cantinovilli), SUM(mortanovilli)
          FROM bovinos b JOIN ddjj_personas dj ON dj.id_ddjj=b.idddjj WHERE {where_actual}
        UNION ALL SELECT 'Toros', SUM(cantitoro), SUM(mortatoro)
          FROM bovinos b JOIN ddjj_personas dj ON dj.id_ddjj=b.idddjj WHERE {where_actual}
        UNION ALL SELECT 'Bufalos', SUM(cantibufa), SUM(mortabufa)
          FROM bovinos b JOIN ddjj_personas dj ON dj.id_ddjj=b.idddjj WHERE {where_actual}
        """,
        params_actual,
    )

if not ganaderia.empty:
    ganaderia = add_percent(ganaderia, "mortandad", "existencias", "tasa_mortandad")
    ganaderia = ganaderia.sort_values("existencias", ascending=False).head(top_n).copy()
    ganaderia["categoria_label"] = ganaderia["categoria"].apply(short_label)
    ganaderia_plot = ganaderia.sort_values("existencias", ascending=True)

    c1, c2 = st.columns(2)
    with c1:
        fig = px.bar(
            ganaderia_plot,
            x="existencias",
            y="categoria_label",
            orientation="h",
            hover_data={"categoria": True, "categoria_label": False, "existencias": ":,.0f"},
            labels={"existencias": "Existencias / cabezas", "categoria_label": ""},
        )
        fig.update_layout(height=390, margin=dict(t=20, b=20, l=20, r=20))
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        fig = px.bar(
            ganaderia_plot.sort_values("mortandad", ascending=True),
            x="mortandad",
            y="categoria_label",
            orientation="h",
            hover_data={
                "categoria": True,
                "categoria_label": False,
                "mortandad": ":,.0f",
                "tasa_mortandad": ":.2f",
            },
            labels={
                "mortandad": "Mortandad",
                "categoria_label": "",
                "tasa_mortandad": "Tasa mortandad (%)",
            },
        )
        fig.update_layout(height=390, margin=dict(t=20, b=20, l=20, r=20))
        st.plotly_chart(fig, use_container_width=True)

    resumen_gan = ganaderia[["categoria", "existencias", "mortandad", "tasa_mortandad"]].copy()
    resumen_gan = resumen_gan.sort_values("existencias", ascending=False)
    st.dataframe(
        resumen_gan,
        hide_index=True,
        use_container_width=True,
        column_config={
            "existencias": st.column_config.NumberColumn("Existencias", format="%.0f"),
            "mortandad": st.column_config.NumberColumn("Mortandad", format="%.0f"),
            "tasa_mortandad": st.column_config.NumberColumn("Tasa mortandad (%)", format="%.2f"),
        },
    )
else:
    st.info("Sin datos ganaderos para los filtros seleccionados.")

# ---------- Top mejoras perdidas ----------
st.subheader("Mejoras afectadas declaradas")
metrica_mejoras = st.selectbox(
    "Ordenar mejoras por",
    ["DDJJ con mejora afectada", "Valor total declarado", "Incidencia promedio"],
)

if unified and origen_sel == "historico":
    df_mejoras = pd.DataFrame()
else:
    filters_mejoras = ["1=1"]
    params_mejoras: dict = {}
    if unified:
        if res_num is not None:
            filters_mejoras.append("r.numero_resolucion = :res_num")
            params_mejoras["res_num"] = res_num
        if anio_sel != "(todos)":
            filters_mejoras.append("YEAR(dj.fecha) = :anio")
            params_mejoras["anio"] = int(anio_sel)
    else:
        filters_mejoras = filters_actual.copy()
        params_mejoras = params_actual.copy()

    where_mejoras = " AND ".join(filters_mejoras)
    df_mejoras = run_query(
        f"""
        SELECT
            COALESCE(NULLIF(TRIM(pm.mejora), ''), '(s/d)') AS mejora,
            COUNT(DISTINCT pm.idddjj) AS ddjj_con_mejora,
            ROUND(SUM(COALESCE(pm.vestimado, 0)), 0) AS valor_total,
            ROUND(AVG(CASE WHEN pm.vestimado > 0 THEN pm.vestimado END), 0) AS valor_prom,
            ROUND(AVG(CASE WHEN pm.incidencia > 0 THEN pm.incidencia END), 1) AS pct_perdida_prom
        FROM perdidas_mejoras pm
        JOIN ddjj_personas dj ON dj.id_ddjj = pm.idddjj
        LEFT JOIN resoluciones r ON r.id_resolucion = dj.id_resolucion
        WHERE {where_mejoras}
          AND (
              COALESCE(pm.vestimado, 0) > 0
              OR COALESCE(pm.incidencia, 0) > 0
              OR COALESCE(pm.pesesp, 0) > 0
              OR COALESCE(pm.pesper, 0) > 0
          )
        GROUP BY COALESCE(NULLIF(TRIM(pm.mejora), ''), '(s/d)')
        """,
        params_mejoras,
    )

st.caption(
    "Se consideran mejoras afectadas solo aquellas con valor o perdida informada positiva. "
    "Las declaraciones sin dato o con valor cero no se cuentan como afectacion declarada."
)

if not df_mejoras.empty:
    metric_column = {
        "DDJJ con mejora afectada": "ddjj_con_mejora",
        "Valor total declarado": "valor_total",
        "Incidencia promedio": "pct_perdida_prom",
    }[metrica_mejoras]
    metric_label = {
        "ddjj_con_mejora": "DDJJ con mejora afectada",
        "valor_total": "Valor total declarado",
        "pct_perdida_prom": "Incidencia promedio",
    }[metric_column]

    df_mejoras = df_mejoras.sort_values(metric_column, ascending=False).head(top_n).copy()
    df_mejoras_plot = df_mejoras.sort_values(metric_column, ascending=True).copy()
    df_mejoras_plot["mejora_label"] = df_mejoras_plot["mejora"].apply(short_label)
    fig = px.bar(
        df_mejoras_plot,
        x=metric_column,
        y="mejora_label",
        orientation="h",
        hover_data={
            "mejora": True,
            "mejora_label": False,
            "ddjj_con_mejora": ":,.0f",
            "valor_total": ":,.0f",
            "valor_prom": ":,.0f",
            "pct_perdida_prom": ":.1f",
        },
        labels={
            metric_column: metric_label,
            "mejora_label": "",
            "ddjj_con_mejora": "DDJJ con mejora afectada",
            "valor_total": "Valor total declarado",
            "valor_prom": "Valor promedio",
            "pct_perdida_prom": "Incidencia promedio",
        },
    )
    fig.update_layout(height=max(420, top_n * 22), margin=dict(t=20, b=20, l=20, r=20))
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(
        df_mejoras.rename(
            columns={
                "mejora": "Tipo de mejora",
                "ddjj_con_mejora": "DDJJ con mejora afectada",
                "valor_total": "Valor total declarado",
                "valor_prom": "Valor promedio",
                "pct_perdida_prom": "Incidencia promedio",
            }
        ),
        hide_index=True,
        use_container_width=True,
        column_config={
            "DDJJ con mejora afectada": st.column_config.NumberColumn(
                "DDJJ con mejora afectada", format="%d"
            ),
            "Valor total declarado": st.column_config.NumberColumn(
                "Valor total declarado", format="%.0f"
            ),
            "Valor promedio": st.column_config.NumberColumn("Valor promedio", format="%.0f"),
            "Incidencia promedio": st.column_config.NumberColumn(
                "Incidencia promedio", format="%.2f"
            ),
        },
    )
else:
    st.info("Sin mejoras afectadas declaradas para los filtros seleccionados.")

# ---------- Tipo juridico de productores ----------
st.subheader("Productores por tipo juridico y actividad")
treemap_mode = st.selectbox(
    "Vista de tipo juridico",
    ["Top combinaciones", "Todas las categorias", "Excluir categoria dominante"],
)
df_tj = run_query(
    """
    SELECT COALESCE(tj.TipoJuridicoDesc,'(s/d)') AS tipo_juridico,
           COALESCE(ta.TipoActividadDesc,'(s/d)') AS actividad,
           COUNT(*) AS n
    FROM productores p
    LEFT JOIN tipojuridico   tj ON tj.TipoJuridicoId   = p.TipoJuridicoId
    LEFT JOIN tipoactividad  ta ON ta.TipoActividadId  = p.EsPrincipalActividadEconomica
    GROUP BY tipo_juridico, actividad
    ORDER BY n DESC
    """
)
if not df_tj.empty:
    plot_tj = df_tj.copy()
    if treemap_mode == "Top combinaciones":
        plot_tj = plot_tj.head(top_n)
    elif treemap_mode == "Excluir categoria dominante":
        dominante = plot_tj.groupby("tipo_juridico")["n"].sum().sort_values(ascending=False).index[0]
        plot_tj = plot_tj[plot_tj["tipo_juridico"] != dominante]

    if not plot_tj.empty:
        fig = px.treemap(
            plot_tj,
            path=["tipo_juridico", "actividad"],
            values="n",
            hover_data={"n": ":,"},
        )
        fig.update_layout(height=520, margin=dict(t=10, b=10, l=10, r=10))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Sin categorias para la opcion seleccionada.")

    st.dataframe(
        df_tj.head(top_n),
        hide_index=True,
        use_container_width=True,
        column_config={"n": st.column_config.NumberColumn("Productores", format="%d")},
    )
