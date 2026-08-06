"""Análisis agregado del Registro de Emergencias."""
from __future__ import annotations

import re
import unicodedata

import pandas as pd
import plotly.express as px
import streamlit as st

from display_format import (
    clean_display_name,
    format_count,
    format_money,
    format_percentage,
    format_surface,
    format_year,
)
from utils import is_unified_mode, run_query, table


SIN_CLASIFICAR = {
    "",
    "(s/d)",
    "s/d",
    "sd",
    "sin dato",
    "sin datos",
    "none",
    "nan",
}
MENSAJE_SIN_DATOS = "No hay datos suficientes para este indicador con los filtros activos."


def short_label(value, max_len: int = 44) -> str:
    """Acorta etiquetas para los gráficos sin modificar el dato original."""
    text = display_label(value)
    return text if len(text) <= max_len else text[: max_len - 1].rstrip() + "…"


def display_label(value) -> str:
    """Normaliza únicamente las etiquetas mostradas en pantalla."""
    if pd.isna(value):
        return "Sin dato"
    text = str(value).strip()
    replacements = {
        "(s/d)": "Sin dato",
        "s/d": "Sin dato",
        "(no disponible en vista unificada)": "Sin clasificación",
    }
    return replacements.get(text.lower(), text or "Sin dato")


def normalize_livestock_category(value) -> str:
    """Normaliza texto para el mapeo visual sin alterar la categoría original."""
    if value is None or pd.isna(value):
        return ""
    text = unicodedata.normalize("NFKD", str(value).strip().casefold())
    text = "".join(character for character in text if not unicodedata.combining(character))
    text = re.sub(r"[_-]+", " ", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


LIVESTOCK_GROUPS = {
    "Bovinos": {
        "bovino", "bovinos", "bovino2016", "vacas", "vaquillonas",
        "vaquillonas 1ra 2da", "terneras", "terneros", "novillitos",
        "novillos", "novillos bueyes", "toros", "toritos", "bovinos bufalinos",
    },
    "Ovinos": {
        "ovino", "ovinos", "ovino2016", "ganaderos ovinos", "ovejas",
        "corderos as", "capones", "borregos as", "carneros", "ovinos caprinos",
    },
    "Caprinos": {"cabras", "chivos", "cabritos as", "caprinos"},
    "Equinos": {"caballos", "yeguas", "equinos"},
    "Porcinos": {"porcinos", "cerdos", "lechones", "madres", "padrillos"},
    "Avicultura": {"aves", "pollos", "gallinas", "avicultura"},
    "Apicultura": {"colmenas", "apicultura"},
    "Ganadería general / mixta": {
        "ganaderia", "ganadero", "ganaderos", "mixto",
    },
}


def homologar_categoria_ganadera(value) -> str:
    """Devuelve un gran grupo ganadero para uso exclusivamente visual."""
    normalized = normalize_livestock_category(value)
    if not normalized or normalized in {"s d", "sin dato", "none", "nan"}:
        return "Sin clasificar"
    for group, categories in LIVESTOCK_GROUPS.items():
        if normalized in categories:
            return group
    return "Sin clasificar"


def add_percent(
    df: pd.DataFrame, numerator: str, denominator: str, output: str
) -> pd.DataFrame:
    """Calcula porcentajes sin dividir por cero."""
    result = df.copy()
    result[output] = 0.0
    valid = result[denominator].fillna(0) > 0
    result.loc[valid, output] = (
        result.loc[valid, numerator].fillna(0)
        / result.loc[valid, denominator]
        * 100
    )
    return result


def is_unclassified_category(series: pd.Series) -> pd.Series:
    return (
        series.astype("string")
        .fillna("")
        .str.strip()
        .str.lower()
        .isin(SIN_CLASIFICAR)
    )


def safe_query(sql: str, params: dict | None = None) -> pd.DataFrame:
    """Evita que una fuente incompleta interrumpa toda la página."""
    try:
        return run_query(sql, params)
    except Exception:
        return pd.DataFrame()


def compact_number(value) -> str:
    if pd.isna(value):
        return "Sin dato"
    return f"{float(value):,.0f}".replace(",", ".")


def show_table(df: pd.DataFrame, title: str, height: int = 300) -> None:
    """Muestra tablas de apoyo siempre cerradas por defecto."""
    with st.expander(title, expanded=False):
        display = df.copy()
        for column in display.columns:
            name = column.casefold()
            if "superficie" in name:
                display[column] = display[column].map(format_surface)
            elif "%" in name or "tasa" in name or "incidencia" in name:
                display[column] = display[column].map(lambda value: format_percentage(value, scale="0-100"))
            elif name in {"existencias declaradas", "mortandad", "registros", "ddjj", "cantidad de ddjj", "productores"}:
                display[column] = display[column].map(format_count)
            elif "valor total" in name or "valor promedio" in name or "monto" in name:
                display[column] = display[column].map(lambda value: format_money(value, "ARS"))
            elif display[column].dtype == object:
                display[column] = display[column].map(clean_display_name)
        st.dataframe(display, hide_index=True, use_container_width=True, height=height)


unified = is_unified_mode()
res_table = table("resoluciones")
agri_table = table("agricultura")
gan_table = table("ganaderia_resumen")

# ---------- Filtros ----------
if unified:
    res = safe_query(
        f"SELECT resolucion_all_id AS id_resolucion, numero_resolucion, "
        f"nombre_resolucion FROM {res_table} ORDER BY fec_res DESC"
    )
    anios_df = safe_query(
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
    res = safe_query(
        "SELECT id_resolucion, numero_resolucion, nombre_resolucion "
        "FROM resoluciones ORDER BY fec_res DESC"
    )
    anios_df = safe_query(
        "SELECT DISTINCT YEAR(fecha) AS anio FROM ddjj_personas "
        "WHERE fecha IS NOT NULL ORDER BY anio DESC"
    )

with st.sidebar:
    st.header("Filtros")
    opciones = ["(todas)"]
    if {"id_resolucion", "numero_resolucion"}.issubset(res.columns):
        opciones += [
            f"{row.id_resolucion} - {row.numero_resolucion}"
            for row in res.itertuples()
        ]
    sel = st.selectbox(
        "Resolución", opciones, format_func=lambda value: "Todas" if value == "(todas)" else value
    )
    anios = ["(todos)"]
    if "anio" in anios_df.columns:
        anios += [int(value) for value in anios_df["anio"].dropna().tolist()]
    anio_sel = st.selectbox(
        "Año", anios, format_func=lambda value: "Todos" if value == "(todos)" else format_year(value)
    )
    origen_sel = "(todos)"
    if unified:
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
    top_n = st.selectbox("Top N", [10, 15, 20, 30, 50], index=2)
    metric_order = st.selectbox(
        "Ordenar cultivos por",
        ["Superficie afectada", "Superficie sembrada", "Porcentaje afectado"],
    )
    incluir_cultivos_sin_clasificar = st.checkbox(
        "Incluir cultivos sin clasificar", value=False
    )
    superficie_minima_pct = 10.0
    if metric_order == "Porcentaje afectado":
        superficie_minima_pct = st.number_input(
            "Superficie sembrada mínima (ha)", min_value=0.0, value=10.0, step=10.0
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

# ---------- Datos ----------
if unified:
    cultivos = safe_query(
        f"""
        SELECT COALESCE(especie, cultivo, '(s/d)') AS tipo_cultivo,
               SUM(superficie_sembrada_uso) AS sembrada,
               SUM(superficie_afectada) AS afectada,
               COUNT(*) AS registros,
               COUNT(DISTINCT COALESCE(CAST(id_ddjj_actual AS CHAR), ddjj_hist_id,
                   iddj, codigo, solicitud_id)) AS ddjj
        FROM {agri_table}
        WHERE {where_unified}
        GROUP BY COALESCE(especie, cultivo, '(s/d)')
        HAVING COALESCE(sembrada, 0) > 0 OR COALESCE(afectada, 0) > 0
        """,
        params_unified,
    )
    ganaderia = safe_query(
        f"""
        SELECT COALESCE(categoria, especie, actividad, 'GANADERIA') AS categoria,
               SUM(existencias) AS existencias, SUM(mortandad) AS mortandad
        FROM {gan_table}
        WHERE {where_unified}
        GROUP BY COALESCE(categoria, especie, actividad, 'GANADERIA')
        HAVING COALESCE(existencias, 0) > 0 OR COALESCE(mortandad, 0) > 0
        """,
        params_unified,
    )
else:
    cultivos = safe_query(
        f"""
        SELECT COALESCE(ct.CultivoTipoDesc, c.CultivoDesc, '(s/d)') AS tipo_cultivo,
               SUM(a.sup_sembrada) AS sembrada, SUM(a.sup_afectada) AS afectada,
               COUNT(*) AS registros, COUNT(DISTINCT a.ddjj) AS ddjj
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
    ganaderia = safe_query(
        f"""
        SELECT 'Vacas' categoria, SUM(b.cantivaca) existencias, SUM(b.mortavaca) mortandad
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
        UNION ALL SELECT 'Búfalos', SUM(cantibufa), SUM(mortabufa)
          FROM bovinos b JOIN ddjj_personas dj ON dj.id_ddjj=b.idddjj WHERE {where_actual}
        """,
        params_actual,
    )

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

if unified and origen_sel in {"historico", "ddjj_2023_excel"}:
    df_mejoras = pd.DataFrame()
else:
    df_mejoras = safe_query(
        f"""
        SELECT COALESCE(NULLIF(TRIM(pm.mejora), ''), '(s/d)') AS mejora,
               COUNT(DISTINCT pm.idddjj) AS ddjj_con_mejora,
               ROUND(SUM(COALESCE(pm.vestimado, 0)), 0) AS valor_total,
               ROUND(AVG(CASE WHEN pm.vestimado > 0 THEN pm.vestimado END), 0) AS valor_prom,
               ROUND(AVG(CASE WHEN pm.incidencia > 0 THEN pm.incidencia END), 1) AS pct_perdida_prom
        FROM perdidas_mejoras pm
        JOIN ddjj_personas dj ON dj.id_ddjj = pm.idddjj
        LEFT JOIN resoluciones r ON r.id_resolucion = dj.id_resolucion
        WHERE {' AND '.join(filters_mejoras)}
          AND (COALESCE(pm.vestimado, 0) > 0 OR COALESCE(pm.incidencia, 0) > 0
               OR COALESCE(pm.pesesp, 0) > 0 OR COALESCE(pm.pesper, 0) > 0)
        GROUP BY COALESCE(NULLIF(TRIM(pm.mejora), ''), '(s/d)')
        """,
        params_mejoras,
    )

if unified:
    tj_filters = ["1=1"]
    tj_params: dict = {}
    if origen_sel != "(todos)":
        tj_filters.append("p.origen_dato = :tj_origin")
        tj_params["tj_origin"] = origen_sel
    if anio_sel != "(todos)":
        tj_filters.append(
            "EXISTS (SELECT 1 FROM vw_all_ddjj_personas d "
            "WHERE d.productor_all_id=p.productor_all_id AND d.anio=:tj_anio)"
        )
        tj_params["tj_anio"] = int(anio_sel)
    df_actividades = safe_query(
        f"""
        SELECT COALESCE(p.actividad, '(s/d)') AS actividad,
               COUNT(DISTINCT p.productor_all_id) AS productores
        FROM vw_all_productores p
        WHERE {' AND '.join(tj_filters)}
        GROUP BY COALESCE(p.actividad, '(s/d)') ORDER BY productores DESC
        """,
        tj_params,
    )
else:
    df_actividades = safe_query(
        """
        SELECT COALESCE(ta.TipoActividadDesc, '(s/d)') AS actividad,
               COUNT(DISTINCT p.ProductorId) AS productores
        FROM productores p
        LEFT JOIN tipoactividad ta
          ON ta.TipoActividadId=p.EsPrincipalActividadEconomica
        GROUP BY COALESCE(ta.TipoActividadDesc, '(s/d)')
        ORDER BY productores DESC
        """
    )

# ---------- Encabezado y resumen ----------
st.title("Análisis del Registro de Emergencias")
st.markdown(
    "Lectura agregada de declaraciones juradas, productores, territorios, "
    "normas y afectación agropecuaria."
)
st.info(
    "Los indicadores se calculan según los filtros activos y la disponibilidad "
    "de datos en el registro integrado."
)

if unified and origen_sel == "ddjj_2023_excel":
    st.warning(
        "DDJJ 2023 se incorpora al registro bajo Decreto 2099/23. Los valores "
        "cuantitativos inválidos se excluyen de las sumas, pero los registros "
        "se conservan para trazabilidad."
    )

st.subheader("Resumen ejecutivo")
kpis: list[tuple[str, str]] = []
if not cultivos.empty and "tipo_cultivo" in cultivos:
    kpis.append(("Cultivos declarados", compact_number(cultivos["tipo_cultivo"].nunique())))
if not ganaderia.empty and "categoria" in ganaderia:
    kpis.append(("Categorías ganaderas", compact_number(ganaderia["categoria"].nunique())))
if not df_mejoras.empty and "mejora" in df_mejoras:
    kpis.append(("Tipos de mejoras", compact_number(df_mejoras["mejora"].nunique())))
if not df_actividades.empty and "productores" in df_actividades:
    kpis.append(("Productores por actividad", compact_number(df_actividades["productores"].sum())))
fuente = {
    "(todos)": "Todas las fuentes",
    "actual": "Actual",
    "historico": "Histórico",
    "ddjj_2023_excel": "DDJJ 2023 Excel",
}.get(origen_sel, "Fuente operativa")
periodo = "Todos los años" if anio_sel == "(todos)" else format_year(anio_sel)
kpis.append(("Fuente / año", f"{fuente} · {periodo}"))
columns = st.columns(min(len(kpis), 5))
for column, (label, value) in zip(columns, kpis):
    column.metric(label, value)

st.subheader("Lectura rápida")
quick_messages: list[str] = []
if not cultivos.empty and {"tipo_cultivo", "afectada"}.issubset(cultivos.columns):
    valid = cultivos[cultivos["afectada"].fillna(0) > 0]
    if not valid.empty:
        row = valid.loc[valid["afectada"].idxmax()]
        quick_messages.append(
            f"Mayor superficie afectada: {display_label(row['tipo_cultivo'])} "
            f"({format_surface(row['afectada'])})."
        )
if not ganaderia.empty and {"categoria", "existencias"}.issubset(ganaderia.columns):
    valid = ganaderia[ganaderia["existencias"].fillna(0) > 0]
    if not valid.empty:
        row = valid.loc[valid["existencias"].idxmax()]
        quick_messages.append(
            f"Mayor existencia declarada: {display_label(row['categoria'])} "
            f"({compact_number(row['existencias'])} cabezas)."
        )
if not df_mejoras.empty and {"mejora", "ddjj_con_mejora"}.issubset(df_mejoras.columns):
    row = df_mejoras.loc[df_mejoras["ddjj_con_mejora"].idxmax()]
    quick_messages.append(
        f"Mejora más frecuente: {display_label(row['mejora'])} "
        f"({compact_number(row['ddjj_con_mejora'])} DDJJ)."
    )
if not cultivos.empty and "tipo_cultivo" in cultivos:
    if is_unclassified_category(cultivos["tipo_cultivo"]).any():
        quick_messages.append("Existen registros agrícolas sin cultivo clasificado.")
if quick_messages:
    st.info("\n\n".join(f"• {message}" for message in quick_messages[:4]))
else:
    st.info(MENSAJE_SIN_DATOS)

# ---------- Afectación agrícola ----------
st.divider()
st.header("Afectación agrícola")
if cultivos.empty or not {"tipo_cultivo", "sembrada", "afectada"}.issubset(cultivos.columns):
    st.info(MENSAJE_SIN_DATOS)
else:
    cultivos = add_percent(cultivos, "afectada", "sembrada", "pct_afectado")
    cultivos["sin_clasificar"] = is_unclassified_category(cultivos["tipo_cultivo"])
    cultivos["Cultivo"] = cultivos["tipo_cultivo"].apply(
        lambda value: "Sin clasificar" if str(value).strip().lower() in SIN_CLASIFICAR else display_label(value)
    )
    if not incluir_cultivos_sin_clasificar:
        cultivos_plot = cultivos[~cultivos["sin_clasificar"]].copy()
    else:
        cultivos_plot = cultivos.copy()
    order_column = {
        "Superficie afectada": "afectada",
        "Superficie sembrada": "sembrada",
        "Porcentaje afectado": "pct_afectado",
    }[metric_order]
    if metric_order == "Porcentaje afectado":
        cultivos_plot = cultivos_plot[
            cultivos_plot["sembrada"].fillna(0) >= superficie_minima_pct
        ]
    cultivos_plot = cultivos_plot.nlargest(top_n, order_column).sort_values(order_column)
    if cultivos_plot.empty:
        st.info(MENSAJE_SIN_DATOS)
    elif metric_order == "Porcentaje afectado":
        fig = px.bar(
            cultivos_plot,
            x="pct_afectado",
            y="Cultivo",
            orientation="h",
            title="Porcentaje de superficie afectada por cultivo",
            labels={"pct_afectado": "Superficie afectada (%)", "Cultivo": "Cultivo"},
            color_discrete_sequence=["#D97706"],
        )
        fig.update_layout(height=max(380, len(cultivos_plot) * 30), showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    else:
        melted = cultivos_plot.melt(
            id_vars=["Cultivo"], value_vars=["sembrada", "afectada"],
            var_name="medida", value_name="Hectáreas"
        )
        melted["medida"] = melted["medida"].map(
            {"sembrada": "Superficie sembrada", "afectada": "Superficie afectada"}
        )
        fig = px.bar(
            melted, x="Hectáreas", y="Cultivo", color="medida", orientation="h",
            barmode="group", title="Superficie sembrada y afectada por cultivo",
            labels={"medida": "Superficie"},
            color_discrete_map={
                "Superficie sembrada": "#4C78A8", "Superficie afectada": "#E45756"
            },
        )
        fig.update_layout(height=max(380, len(cultivos_plot) * 30))
        st.plotly_chart(fig, use_container_width=True)
    tabla_cultivos = cultivos.rename(
        columns={
            "sembrada": "Superficie sembrada",
            "afectada": "Superficie afectada",
            "pct_afectado": "Superficie afectada (%)",
            "registros": "Registros",
            "ddjj": "DDJJ",
        }
    )
    visible = [
        column for column in ["Cultivo", "Superficie sembrada", "Superficie afectada",
                              "Superficie afectada (%)", "Registros", "DDJJ"]
        if column in tabla_cultivos.columns
    ]
    show_table(tabla_cultivos[visible], "Ver tabla de cultivos")

# ---------- Afectación ganadera ----------
st.divider()
st.header("Afectación ganadera")
vista_ganadera = st.selectbox(
    "Vista ganadera",
    ["Grandes grupos homologados", "Categorías originales"],
)
st.caption(
    "La homologación ganadera es visual y preliminar. Se aplica para facilitar "
    "la lectura comparativa entre fuentes con distinto nivel de detalle y no "
    "modifica los datos originales."
)
if ganaderia.empty or not {"categoria", "existencias", "mortandad"}.issubset(ganaderia.columns):
    st.info(MENSAJE_SIN_DATOS)
else:
    ganaderia_original = ganaderia.copy()
    if vista_ganadera == "Grandes grupos homologados":
        ganaderia_original["grupo_ganadero"] = ganaderia_original["categoria"].apply(
            homologar_categoria_ganadera
        )
        ganaderia_vista = (
            ganaderia_original.groupby("grupo_ganadero", as_index=False, dropna=False)
            .agg(existencias=("existencias", "sum"), mortandad=("mortandad", "sum"))
        )
        ganaderia_vista = add_percent(
            ganaderia_vista, "mortandad", "existencias", "tasa_mortandad"
        )
        ganaderia_vista["Grupo ganadero"] = ganaderia_vista["grupo_ganadero"]
        label_column = "Grupo ganadero"
        existence_title = "Existencias declaradas por grupo ganadero"
        mortality_title = "Mortandad declarada por grupo ganadero"
        table_title = "Ver tabla ganadera homologada"
    else:
        ganaderia_vista = add_percent(
            ganaderia_original, "mortandad", "existencias", "tasa_mortandad"
        )
        ganaderia_vista["Categoría original"] = ganaderia_vista["categoria"].apply(
            display_label
        )
        label_column = "Categoría original"
        existence_title = "Existencias declaradas por categoría original"
        mortality_title = "Mortandad declarada por categoría original"
        table_title = "Ver tabla ganadera original"
        st.warning(
            "Esta vista conserva las categorías originales declaradas. No todas "
            "son comparables entre fuentes, años o resoluciones."
        )

    top_existencias = ganaderia_vista.nlargest(top_n, "existencias").sort_values("existencias")
    top_mortandad = ganaderia_vista.nlargest(top_n, "mortandad").sort_values("mortandad")
    left, right = st.columns(2)
    with left:
        fig = px.bar(
            top_existencias, x="existencias", y=label_column, orientation="h",
            title=existence_title,
            labels={"existencias": "Cabezas"}, color_discrete_sequence=["#4C78A8"]
        )
        fig.update_layout(height=max(360, len(top_existencias) * 28), showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    with right:
        fig = px.bar(
            top_mortandad, x="mortandad", y=label_column, orientation="h",
            title=mortality_title,
            labels={"mortandad": "Mortandad"}, color_discrete_sequence=["#E45756"]
        )
        fig.update_layout(height=max(360, len(top_mortandad) * 28), showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    if (
        ganaderia_original["mortandad"].fillna(0)
        > ganaderia_original["existencias"].fillna(0)
    ).any():
        st.warning(
            "Los registros con mortandad mayor a existencia declarada deben "
            "interpretarse como inconsistencias de carga y no como indicadores finales."
        )
    tabla_ganadera = ganaderia_vista.rename(
        columns={
            "existencias": "Existencias declaradas",
            "mortandad": "Mortandad",
            "tasa_mortandad": "Tasa de mortandad (%)",
        }
    )
    show_table(
        tabla_ganadera[
            [label_column, "Existencias declaradas", "Mortandad", "Tasa de mortandad (%)"]
        ].sort_values("Existencias declaradas", ascending=False),
        table_title,
    )

# ---------- Mejoras afectadas ----------
st.divider()
st.header("Mejoras afectadas")
if df_mejoras.empty or not {"mejora", "ddjj_con_mejora"}.issubset(df_mejoras.columns):
    st.info(MENSAJE_SIN_DATOS)
else:
    mejoras_plot = df_mejoras.nlargest(top_n, "ddjj_con_mejora").sort_values("ddjj_con_mejora")
    mejoras_plot = mejoras_plot.copy()
    mejoras_plot["Mejora"] = mejoras_plot["mejora"].apply(display_label)
    fig = px.bar(
        mejoras_plot, x="ddjj_con_mejora", y="Mejora", orientation="h",
        title="DDJJ con mejoras afectadas declaradas",
        labels={"ddjj_con_mejora": "Cantidad de DDJJ"},
        color_discrete_sequence=["#59A14F"],
    )
    fig.update_layout(height=max(380, len(mejoras_plot) * 30), showlegend=False)
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "Se consideran mejoras afectadas solo aquellas con valor o incidencia positiva informada."
    )
    tabla_mejoras = df_mejoras.copy()
    tabla_mejoras["Mejora"] = tabla_mejoras["mejora"].apply(display_label)
    tabla_mejoras = tabla_mejoras.rename(
        columns={
            "ddjj_con_mejora": "Cantidad de DDJJ",
            "valor_total": "Valor total declarado",
            "valor_prom": "Valor promedio",
            "pct_perdida_prom": "Incidencia promedio",
        }
    )
    visible = [
        column for column in ["Mejora", "Cantidad de DDJJ", "Valor total declarado",
                              "Valor promedio", "Incidencia promedio"]
        if column in tabla_mejoras.columns
    ]
    show_table(tabla_mejoras[visible], "Ver tabla de mejoras")

# ---------- Productores y actividades ----------
st.divider()
st.header("Productores y actividades")
if df_actividades.empty or not {"actividad", "productores"}.issubset(df_actividades.columns):
    st.info(MENSAJE_SIN_DATOS)
else:
    actividades = df_actividades.copy()
    actividades["Actividad"] = actividades["actividad"].apply(display_label)
    limite_actividad = min(top_n, 20)
    actividades_plot = actividades.nlargest(limite_actividad, "productores").sort_values("productores")
    fig = px.bar(
        actividades_plot, x="productores", y="Actividad", orientation="h",
        title="Productores por actividad declarada",
        labels={"productores": "Productores"},
        color_discrete_sequence=["#4C78A8"],
    )
    fig.update_layout(height=max(400, len(actividades_plot) * 30), showlegend=False)
    st.plotly_chart(fig, use_container_width=True)
    show_table(
        actividades[["Actividad", "productores"]].rename(columns={"productores": "Productores"}),
        "Ver tabla de actividades",
    )

# ---------- Metodología ----------
st.divider()
with st.expander("Metodología y cobertura", expanded=False):
    st.markdown(
        """
        - Los indicadores dependen de los filtros activos.
        - DDJJ 2023 se incorpora al registro bajo Decreto 2099/23.
        - Algunas categorías productivas o ganaderas pueden no estar homologadas entre fuentes.
        - Los registros con inconsistencias de carga se conservan para trazabilidad.
        - Las tablas detalladas se muestran como apoyo y no reemplazan la validación metodológica.
        """
    )
