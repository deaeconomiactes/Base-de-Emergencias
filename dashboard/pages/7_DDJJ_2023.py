"""Módulo local de consulta de las DDJJ 2023 vinculadas al Decreto 2099/23."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[2]
NORMALIZED_DIR = PROJECT_ROOT / "data_processed" / "ddjj_2023_excel" / "normalized"
BRIDGE_DIR = PROJECT_ROOT / "data_processed" / "ddjj_2023_excel" / "bridge"

FILES = {
    "trámites": NORMALIZED_DIR / "fact_ddjj_tramite_2023.csv",
    "productores": NORMALIZED_DIR / "dim_productor_2023.csv",
    "ADREMAS": NORMALIZED_DIR / "fact_adrema_establecimiento_2023.csv",
    "agricultura": NORMALIZED_DIR / "fact_agricultura_perdida_2023.csv",
    "ganadería": NORMALIZED_DIR / "fact_ganaderia_declarada_2023.csv",
    "calidad": NORMALIZED_DIR / "fact_calidad_dato_2023.csv",
    "bridge": BRIDGE_DIR / "bridge_ddjj_evento_normativo_2023.csv",
    "validación del bridge": BRIDGE_DIR / "validation_bridge_normativo_2023_checks.csv",
}

MISSING_FILES_MESSAGE = (
    "No se encontraron los archivos locales normalizados de DDJJ 2023. "
    "Ejecutar scripts 14, 15 y 17 antes de abrir esta página."
)


@st.cache_data(show_spinner=False)
def read_csv_cached(path: str, modified_at: float) -> pd.DataFrame:
    """Lee un CSV local sin inferir identificadores como números.

    ``modified_at`` invalida la caché cuando cambia el archivo, sin modificarlo.
    """
    del modified_at
    return pd.read_csv(path, dtype="string", low_memory=False)


def normalized_name(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "_", text.casefold()).strip("_")


def find_column(frame: pd.DataFrame, *aliases: str) -> str | None:
    by_normalized = {normalized_name(column): column for column in frame.columns}
    for alias in aliases:
        if normalized_name(alias) in by_normalized:
            return by_normalized[normalized_name(alias)]
    return None


def rename_aliases(
    frame: pd.DataFrame, aliases: dict[str, tuple[str, ...]]
) -> pd.DataFrame:
    rename: dict[str, str] = {}
    for canonical, variants in aliases.items():
        found = find_column(frame, canonical, *variants)
        if found is not None and canonical not in frame.columns:
            rename[found] = canonical
    return frame.rename(columns=rename).copy()


def clean_key(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip().replace("", pd.NA)


def bool_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(False, index=frame.index, dtype=bool)
    return (
        frame[column]
        .astype("string")
        .str.strip()
        .str.casefold()
        .isin({"true", "1", "si", "sí", "yes", "y"})
    )


def nonblank(series: pd.Series) -> pd.Series:
    values = series.astype("string").str.strip()
    missing_labels = {
        "",
        "nan",
        "none",
        "null",
        "sin dato",
        "no hay opciones configuradas",
    }
    return values.notna() & ~values.str.casefold().isin(missing_labels)


def options_from(series: pd.Series) -> list[str]:
    values = series.loc[nonblank(series)].astype(str).str.strip().drop_duplicates()
    return sorted(values.tolist(), key=str.casefold)


def format_count(value: int) -> str:
    return f"{int(value):,}".replace(",", ".")


def distinct_ids(frame: pd.DataFrame) -> set[str]:
    if "tramite_id" not in frame.columns:
        return set()
    return set(clean_key(frame["tramite_id"]).dropna().astype(str))


def unique_tramite_count(frame: pd.DataFrame) -> int:
    return len(distinct_ids(frame))


def bar_chart(
    frame: pd.DataFrame,
    category: str,
    value: str,
    *,
    x_title: str,
    y_title: str,
):
    figure = px.bar(frame, x=category, y=value, text=value)
    figure.update_traces(texttemplate="%{text:,.0f}", textposition="outside")
    figure.update_xaxes(title_text=x_title)
    figure.update_yaxes(title_text=y_title, rangemode="tozero")
    figure.update_layout(
        height=350,
        margin=dict(l=25, r=20, t=20, b=40),
        showlegend=False,
    )
    return figure


missing = [str(path.relative_to(PROJECT_ROOT)) for path in FILES.values() if not path.is_file()]
if missing:
    st.error(MISSING_FILES_MESSAGE)
    st.caption("Archivos faltantes: " + ", ".join(f"`{path}`" for path in missing))
    st.stop()

try:
    loaded = {
        name: read_csv_cached(str(path), path.stat().st_mtime)
        for name, path in FILES.items()
    }
except Exception as exc:
    st.error(MISSING_FILES_MESSAGE)
    st.caption(f"Detalle de lectura: {exc}")
    st.stop()


COMMON_ALIASES = {
    "tramite_id": ("Tramite Id", "tramiteId", "TRAMITE_ID"),
}
MASTER_ALIASES = {
    **COMMON_ALIASES,
    "productor_id_2023": ("productor_id", "Productor Id"),
    "cuit_cuil": ("cuit", "CUIT", "CUIT CUIL"),
    "productor_nombre": ("razon_social", "Razón Social", "productor"),
    "fecha_presentacion": ("fecha_creacion", "Fecha de Creación", "fecha"),
    "estado_tramite": ("estado", "Estado Actual"),
    "tipo_certificado": ("Tipo Certificado",),
    "numero_certificado": ("Numero Certificado", "Número Certificado"),
}
ADREMA_ALIASES = {
    **COMMON_ALIASES,
    "adrema": ("ADREMA",),
    "departamento": ("Departamento",),
    "actividad_normalizada_preliminar": ("actividad", "actividad_original"),
}

master = rename_aliases(loaded["trámites"], MASTER_ALIASES)
producers = rename_aliases(loaded["productores"], MASTER_ALIASES)
adremas = rename_aliases(loaded["ADREMAS"], ADREMA_ALIASES)
agriculture = rename_aliases(loaded["agricultura"], COMMON_ALIASES)
livestock = rename_aliases(loaded["ganadería"], COMMON_ALIASES)
quality = rename_aliases(loaded["calidad"], COMMON_ALIASES)
bridge = rename_aliases(loaded["bridge"], COMMON_ALIASES)
bridge_checks = loaded["validación del bridge"].copy()

if "tramite_id" not in master.columns or "tramite_id" not in bridge.columns:
    st.error(MISSING_FILES_MESSAGE)
    st.caption("No se pudo identificar `tramite_id` en la tabla maestra o en el bridge.")
    st.stop()

for frame in (master, producers, adremas, agriculture, livestock, quality, bridge):
    if "tramite_id" in frame.columns:
        frame["tramite_id"] = clean_key(frame["tramite_id"])

bridge_columns = [
    column
    for column in (
        "tramite_id",
        "evento_id_normativo",
        "tipo_norma",
        "numero_norma",
        "anio_norma",
        "nombre_evento",
        "fecha_inicio_evento",
        "fecha_fin_evento",
        "validado_por",
        "confianza_asignacion",
    )
    if column in bridge.columns
]
bridge_unique = bridge[bridge_columns].dropna(subset=["tramite_id"]).drop_duplicates(
    "tramite_id", keep="first"
)
universe = master.dropna(subset=["tramite_id"]).merge(
    bridge_unique,
    on="tramite_id",
    how="inner",
    validate="one_to_one",
    suffixes=("", "_bridge"),
)

# La dimensión de productores se usa solo como respaldo para nombre y CUIT.
if "productor_id_2023" in universe.columns and "productor_id_2023" in producers.columns:
    producer_fields = [
        column
        for column in ("productor_id_2023", "productor_nombre", "cuit_cuil")
        if column in producers.columns
    ]
    producer_lookup = producers[producer_fields].drop_duplicates("productor_id_2023")
    universe = universe.merge(
        producer_lookup,
        on="productor_id_2023",
        how="left",
        suffixes=("", "_dim"),
    )
    for field in ("productor_nombre", "cuit_cuil"):
        fallback = f"{field}_dim"
        if fallback in universe.columns:
            if field not in universe.columns:
                universe[field] = universe[fallback]
            else:
                universe[field] = universe[field].fillna(universe[fallback])

quality_alert_columns = {
    "CUIT inválido": "dq_cuit_invalido",
    "Certificado nulo": "dq_numero_certificado_nulo",
    "Mortandad mayor que cantidad": "dq_tiene_mortandad_mayor_cantidad",
    "Superficie negativa": "dq_tiene_superficie_negativa",
    "ADREMA duplicada": "dq_tiene_adrema_duplicada",
    "Trámite anulado": "dq_estado_anulado",
    "Fuera de 2023": "dq_fecha_fuera_2023",
}
additional_alert_columns = (
    "dq_adrema_faltante",
    "dq_tiene_tramite_huerfano_en_detalle",
    "dq_fecha_presentacion_nula",
)

quality_columns = ["tramite_id"] + [
    column
    for column in (*quality_alert_columns.values(), *additional_alert_columns)
    if column in quality.columns
]
quality_lookup = (
    quality[quality_columns]
    .dropna(subset=["tramite_id"])
    .drop_duplicates("tramite_id", keep="first")
)
universe = universe.merge(quality_lookup, on="tramite_id", how="left")

department_by_id = pd.DataFrame(columns=["tramite_id", "departamento"])
if "tramite_id" in adremas.columns and "departamento" in adremas.columns:
    valid_departments = adremas.loc[
        adremas["tramite_id"].notna() & nonblank(adremas["departamento"]),
        ["tramite_id", "departamento"],
    ].copy()
    valid_departments["departamento"] = valid_departments["departamento"].str.strip()
    department_by_id = (
        valid_departments.drop_duplicates()
        .groupby("tramite_id", as_index=False)["departamento"]
        .agg(lambda values: " | ".join(sorted(set(values), key=str.casefold)))
    )
universe = universe.merge(department_by_id, on="tramite_id", how="left")

agriculture_ids = distinct_ids(agriculture)
livestock_ids = distinct_ids(livestock)
universe_ids = distinct_ids(universe)

st.title("DDJJ 2023 - Decreto 2099/23")
st.caption(
    "Módulo local de seguimiento de declaraciones juradas 2023 normalizadas "
    "desde Excel y vinculadas al Decreto 2099/23."
)
st.info(
    "Esta página usa archivos locales normalizados y validados. No modifica TiDB "
    "ni las vistas históricas. La integración al registro unificado queda pendiente "
    "de carga controlada a staging."
)

check_state_column = find_column(bridge_checks, "estado", "status")
check_counts: dict[str, int] = {}
if check_state_column is not None:
    check_counts = (
        bridge_checks[check_state_column]
        .astype("string")
        .str.strip()
        .str.upper()
        .value_counts()
        .to_dict()
    )

master_count = master["tramite_id"].nunique(dropna=True)
integrable_count = universe["tramite_id"].nunique(dropna=True)
coverage = 100 * integrable_count / len(bridge_unique) if len(bridge_unique) else 0
status_cols = st.columns(5)
status_cols[0].metric("Universo maestro", format_count(master_count))
status_cols[1].metric("Universo integrable", format_count(integrable_count))
status_cols[2].metric("Cobertura del bridge", f"{coverage:.0f}%")
status_cols[3].metric(
    "Validación bridge",
    "WARN sin FAIL" if check_counts.get("FAIL", 0) == 0 else "FAIL",
)
status_cols[4].metric("Norma", "Decreto 2099/23")


def reset_filters() -> None:
    for key in (
        "ddjj23_states",
        "ddjj23_departments",
        "ddjj23_certificate_types",
        "ddjj23_search",
        "ddjj23_activities",
    ):
        st.session_state.pop(key, None)


filtered = universe.copy()
with st.sidebar:
    st.header("Filtros DDJJ 2023")
    if "estado_tramite" in filtered.columns:
        selected_states = st.multiselect(
            "Estado del trámite",
            options_from(universe["estado_tramite"]),
            placeholder="Todos",
            key="ddjj23_states",
        )
        if selected_states:
            filtered = filtered[filtered["estado_tramite"].isin(selected_states)]

    selected_departments: list[str] = []
    if "departamento" in adremas.columns:
        selected_departments = st.multiselect(
            "Departamento",
            options_from(adremas["departamento"]),
            placeholder="Todos",
            key="ddjj23_departments",
        )
        if selected_departments:
            department_ids = distinct_ids(
                adremas[adremas["departamento"].isin(selected_departments)]
            )
            filtered = filtered[filtered["tramite_id"].isin(department_ids)]

    if "tipo_certificado" in filtered.columns:
        selected_certificates = st.multiselect(
            "Tipo de certificado",
            options_from(universe["tipo_certificado"]),
            placeholder="Todos",
            key="ddjj23_certificate_types",
        )
        if selected_certificates:
            filtered = filtered[filtered["tipo_certificado"].isin(selected_certificates)]

    if "productor_nombre" in filtered.columns or "cuit_cuil" in filtered.columns:
        search = st.text_input(
            "Productor / CUIT",
            placeholder="Buscar texto...",
            key="ddjj23_search",
        ).strip()
        if search:
            search_mask = pd.Series(False, index=filtered.index)
            for column in ("productor_nombre", "cuit_cuil"):
                if column in filtered.columns:
                    search_mask |= filtered[column].astype("string").str.contains(
                        search, case=False, regex=False, na=False
                    )
            filtered = filtered[search_mask]

    activity_options = []
    if agriculture_ids:
        activity_options.append("Agricultura")
    if livestock_ids:
        activity_options.append("Ganadería")
    selected_activities = st.multiselect(
        "Tipo de actividad",
        activity_options,
        placeholder="Todas",
        key="ddjj23_activities",
    )
    if selected_activities:
        selected_activity_ids: set[str] = set()
        if "Agricultura" in selected_activities:
            selected_activity_ids |= agriculture_ids
        if "Ganadería" in selected_activities:
            selected_activity_ids |= livestock_ids
        filtered = filtered[filtered["tramite_id"].isin(selected_activity_ids)]

    st.button(
        "Restablecer filtros",
        on_click=reset_filters,
        width="stretch",
    )

filtered_ids = distinct_ids(filtered)
adremas_filtered = adremas[adremas["tramite_id"].isin(filtered_ids)].copy()
if selected_departments and "departamento" in adremas_filtered.columns:
    adremas_filtered = adremas_filtered[
        adremas_filtered["departamento"].isin(selected_departments)
    ]
agriculture_filtered = agriculture[agriculture["tramite_id"].isin(filtered_ids)]
livestock_filtered = livestock[livestock["tramite_id"].isin(filtered_ids)]

if filtered.empty:
    st.warning("No hay DDJJ integrables para la combinación de filtros seleccionada.")

unique_adremas = 0
if {"tramite_id", "adrema"}.issubset(adremas_filtered.columns):
    unique_adremas = len(
        adremas_filtered.loc[nonblank(adremas_filtered["adrema"]), ["tramite_id", "adrema"]]
        .drop_duplicates()
    )

unique_producers = 0
if "productor_id_2023" in filtered.columns:
    unique_producers = filtered["productor_id_2023"].nunique(dropna=True)
elif "productor_nombre" in filtered.columns:
    unique_producers = filtered.loc[
        nonblank(filtered["productor_nombre"]), "productor_nombre"
    ].nunique()

unique_cuits = 0
if "cuit_cuil" in filtered.columns:
    unique_cuits = filtered.loc[nonblank(filtered["cuit_cuil"]), "cuit_cuil"].nunique()

null_certificates = 0
if "numero_certificado" in filtered.columns:
    null_certificates = int((~nonblank(filtered["numero_certificado"])).sum())
elif "dq_numero_certificado_nulo" in filtered.columns:
    null_certificates = int(bool_series(filtered, "dq_numero_certificado_nulo").sum())

all_alert_columns = [
    column
    for column in (*quality_alert_columns.values(), *additional_alert_columns)
    if column in filtered.columns
]
has_alert = pd.Series(False, index=filtered.index)
for column in all_alert_columns:
    has_alert |= bool_series(filtered, column)

st.subheader("Indicadores del universo filtrado")
kpi_values = [
    ("DDJJ integrables", len(filtered_ids)),
    ("Productores únicos", unique_producers),
    ("CUIT únicos", unique_cuits),
    ("ADREMAS únicas", unique_adremas),
    ("Trámites con agricultura", unique_tramite_count(agriculture_filtered)),
    ("Trámites con ganadería", unique_tramite_count(livestock_filtered)),
    ("Certificado nulo", null_certificates),
    ("Con alertas de calidad", int(has_alert.sum())),
]
for start in range(0, len(kpi_values), 4):
    columns = st.columns(4)
    for column, (label, value) in zip(columns, kpi_values[start : start + 4]):
        column.metric(label, format_count(value))
st.caption(
    "ADREMAS únicas cuenta una vez cada par `tramite_id + adrema`; no suma "
    "superficies de filas duplicadas."
)

left, right = st.columns(2)
with left:
    st.subheader("Distribución por estado")
    if "estado_tramite" in filtered.columns and filtered["estado_tramite"].notna().any():
        state_chart = (
            filtered.assign(
                estado_visible=filtered["estado_tramite"].fillna("Sin dato").replace("", "Sin dato")
            )
            .groupby("estado_visible", as_index=False)["tramite_id"]
            .nunique()
            .rename(columns={"estado_visible": "Estado", "tramite_id": "DDJJ"})
            .sort_values("DDJJ", ascending=False)
        )
        st.plotly_chart(
            bar_chart(state_chart, "Estado", "DDJJ", x_title="Estado", y_title="DDJJ"),
            width="stretch",
        )
    else:
        st.info("No hay una columna de estado disponible para graficar.")

with right:
    st.subheader("DDJJ por departamento")
    if not adremas_filtered.empty and "departamento" in adremas_filtered.columns:
        department_chart = (
            adremas_filtered.loc[nonblank(adremas_filtered["departamento"])]
            .groupby("departamento", as_index=False)["tramite_id"]
            .nunique()
            .rename(columns={"departamento": "Departamento", "tramite_id": "DDJJ"})
            .sort_values("DDJJ", ascending=False)
        )
        if not department_chart.empty:
            st.plotly_chart(
                bar_chart(
                    department_chart,
                    "Departamento",
                    "DDJJ",
                    x_title="Departamento",
                    y_title="DDJJ",
                ),
                width="stretch",
            )
            st.caption(
                "Un trámite con ADREMAS en más de un departamento puede aparecer en "
                "más de una barra; las barras no son aditivas."
            )
        else:
            st.info("No hay departamentos informados para los filtros seleccionados.")
    else:
        st.info("No hay información territorial disponible para graficar.")

left, right = st.columns(2)
with left:
    st.subheader("Presencia de actividad declarada")
    activity_chart = pd.DataFrame(
        {
            "Actividad": ["Agricultura", "Ganadería"],
            "Trámites": [
                unique_tramite_count(agriculture_filtered),
                unique_tramite_count(livestock_filtered),
            ],
        }
    )
    st.plotly_chart(
        bar_chart(
            activity_chart,
            "Actividad",
            "Trámites",
            x_title="Actividad",
            y_title="Trámites",
        ),
        width="stretch",
    )
    st.caption(
        "Conteos descriptivos de trámites con al menos un detalle; agricultura y "
        "ganadería no son categorías excluyentes. La ganadería se presenta como "
        "base declarada sin depuración cuantitativa final."
    )

with right:
    st.subheader("Alertas de calidad")
    alert_rows = []
    for label, column in quality_alert_columns.items():
        alert_rows.append(
            {
                "Alerta": label,
                "Trámites": int(bool_series(filtered, column).sum()),
            }
        )
    alerts_chart = pd.DataFrame(alert_rows).sort_values("Trámites", ascending=False)
    st.plotly_chart(
        bar_chart(
            alerts_chart,
            "Alerta",
            "Trámites",
            x_title="Alerta",
            y_title="Trámites",
        ),
        width="stretch",
    )
    st.caption(
        "Las alertas se cuentan por trámite dentro del universo integrable filtrado. "
        "Anulados y fuera de 2023 quedan en cero porque el bridge los excluye."
    )

mortality_alerts = int(
    bool_series(filtered, "dq_tiene_mortandad_mayor_cantidad").sum()
)
negative_surface_alerts = int(bool_series(filtered, "dq_tiene_superficie_negativa").sum())
if mortality_alerts:
    st.warning(
        f"Ganadería: {format_count(mortality_alerts)} trámites filtrados tienen "
        "mortandad mayor que cantidad. Se muestran solamente conteos descriptivos; "
        "estos registros no alimentan totales ni tasas ganaderas cuantitativas."
    )
if negative_surface_alerts:
    st.warning(
        f"Superficies: {format_count(negative_surface_alerts)} trámites filtrados "
        "tienen superficies negativas. Esos valores se conservan para auditoría y no "
        "se suman ni promedian como indicadores principales."
    )

st.subheader("Exploración de DDJJ integrables")
explorer_fields = [
    "tramite_id",
    "fecha_presentacion",
    "cuit_cuil",
    "productor_nombre",
    "estado_tramite",
    "tipo_certificado",
    "numero_certificado",
    "evento_id_normativo",
    "nombre_evento",
    "departamento",
]
explorer = filtered[[column for column in explorer_fields if column in filtered.columns]].copy()
explorer = explorer.rename(
    columns={
        "tramite_id": "Trámite ID",
        "fecha_presentacion": "Fecha de presentación",
        "cuit_cuil": "CUIT/CUIL",
        "productor_nombre": "Productor",
        "estado_tramite": "Estado",
        "tipo_certificado": "Tipo de certificado",
        "numero_certificado": "Número de certificado",
        "evento_id_normativo": "Evento normativo",
        "nombre_evento": "Norma",
        "departamento": "Departamento(s)",
    }
)
st.caption(f"Mostrando {format_count(len(explorer))} trámites según los filtros activos.")
st.dataframe(explorer, hide_index=True, width="stretch", height=500)

with st.expander("Metodología"):
    st.markdown(
        """
- `Numero Certificado` es un dato administrativo y no se usa como decreto, resolución ni evento.
- Los trámites integrables se vinculan por confirmación institucional al **Decreto 2099/23** mediante el bridge local.
- Los 5 trámites anulados y los 5 fuera de 2023 se conservan en las fuentes normalizadas, pero se excluyen de los indicadores principales porque no están en el bridge.
- Los registros con mortandad mayor que cantidad o superficies negativas se conservan para auditoría, pero no alimentan indicadores cuantitativos finales.
- La página no integra estas DDJJ con el registro histórico unificado y no realiza escrituras en TiDB.
"""
    )

expected_quality = quality[quality["tramite_id"].isin(master["tramite_id"])]
exclusion_mask = bool_series(expected_quality, "dq_estado_anulado") | bool_series(
    expected_quality, "dq_fecha_fuera_2023"
)
expected_integrable_ids = distinct_ids(expected_quality.loc[~exclusion_mask])
bridge_ids = distinct_ids(bridge)
missing_bridge_ids = expected_integrable_ids - bridge_ids
orphan_bridge_ids = bridge_ids - universe_ids
duplicate_bridge_rows = int(bridge["tramite_id"].duplicated(keep=False).sum())
computed_coverage = (
    100 * len(expected_integrable_ids & bridge_ids) / len(expected_integrable_ids)
    if expected_integrable_ids
    else 0
)

with st.expander("Validación del bridge"):
    validation_table = pd.DataFrame(
        {
            "Indicador": [
                "Estado global",
                "PASS",
                "WARN",
                "FAIL",
                "Cobertura",
                "Faltantes",
                "Huérfanos",
                "Duplicados",
            ],
            "Resultado": [
                "WARN" if check_counts.get("WARN", 0) else "PASS",
                format_count(check_counts.get("PASS", 0)),
                format_count(check_counts.get("WARN", 0)),
                format_count(check_counts.get("FAIL", 0)),
                f"{computed_coverage:.0f}%",
                format_count(len(missing_bridge_ids)),
                format_count(len(orphan_bridge_ids)),
                format_count(duplicate_bridge_rows),
            ],
        }
    )
    st.table(validation_table)
    st.caption(
        "Los WARN documentados corresponden a `validado_por` pendiente de completar "
        "y a las fechas de inicio y fin del evento vacías; no hay checks FAIL."
    )

with st.expander("Advertencias de calidad"):
    st.dataframe(alerts_chart, hide_index=True, width="stretch")
    st.markdown(
        """
- Las inconsistencias se conservan con trazabilidad: la página no corrige ni elimina datos.
- Mortandad mayor que cantidad queda fuera de totales, tasas y pérdidas ganaderas cuantitativas.
- Las superficies negativas quedan fuera de sumas, promedios e indicadores territoriales/productivos de superficie.
- Cada par `tramite_id + adrema` se cuenta una vez como establecimiento; las superficies duplicadas no se suman sin criterio institucional.
"""
    )

with st.expander("Archivos usados"):
    st.markdown(
        "\n".join(
            f"- **{name.capitalize()}:** `{path.relative_to(PROJECT_ROOT).as_posix()}`"
            for name, path in FILES.items()
        )
    )
    st.caption(
        "Fuentes locales de solo lectura. La caché se invalida cuando cambia la fecha "
        "de modificación de cada archivo."
    )
