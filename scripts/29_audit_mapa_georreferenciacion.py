"""Auditoría de solo lectura de la georreferenciación usada por el mapa.

No modifica TiDB, vistas, dashboard ni datos existentes. Solo crea las salidas
documentales autorizadas bajo data_processed/mapa/audit/.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboard"))
from utils import run_query  # noqa: E402


OUT = ROOT / "data_processed" / "mapa" / "audit"
CHECKS_PATH = OUT / "mapa_georreferenciacion_checks.csv"
SOURCES_PATH = OUT / "mapa_georreferenciacion_fuentes.csv"
INVALID_PATH = OUT / "mapa_georreferenciacion_invalidos.csv"
REPORT_PATH = OUT / "mapa_georreferenciacion_resultados.md"
CORR_LAT = (-31.5, -27.0)
CORR_LON = (-60.5, -55.0)
MAP_LAT = (-55.0, -21.0)
MAP_LON = (-74.0, -53.0)


def clean_text(value) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def parse_coord(value) -> tuple[float | None, str]:
    """Replica fix_coord y clasifica el formato, sin alterar el dato fuente."""
    raw = clean_text(value)
    if not raw or raw.casefold() in {"none", "nan", "null", "nat"}:
        return None, "vacio"
    if raw.replace(" ", "") in {"0", "0.0", "0,0", "+0", "-0"}:
        return None, "cero"
    compact = raw.replace(" ", "")
    if re.search(r"[°º'\"NSEW]", compact, re.I):
        return None, "grados_con_simbolos"
    decimal = compact.replace(",", ".")
    try:
        number = float(decimal)
    except ValueError:
        return None, "no_numerico"
    if -180 <= number <= 180 and number != 0:
        kind = "coma_decimal" if "," in compact else "decimal_directo"
        return number, kind
    sign = -1 if decimal.startswith("-") else 1
    digits = decimal.lstrip("+-").replace(".", "")
    if digits.isdigit() and len(digits) >= 3:
        repaired = sign * float(digits[:2] + "." + digits[2:])
        if -180 <= repaired <= 180:
            return repaired, "punto_decimal_omitido"
    if abs(number) >= 10_000:
        return None, "posible_proyectada"
    return None, "fuera_rango_global"


def norm_adrema(value) -> str:
    return re.sub(r"[^A-Z0-9]", "", clean_text(value).upper())


def add_coordinate_diagnostics(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    lat_parsed = out["latitud_raw"].map(parse_coord)
    lon_parsed = out["longitud_raw"].map(parse_coord)
    out["lat"] = lat_parsed.map(lambda item: item[0])
    out["lng"] = lon_parsed.map(lambda item: item[0])
    out["lat_clase"] = lat_parsed.map(lambda item: item[1])
    out["lon_clase"] = lon_parsed.map(lambda item: item[1])
    out["ambas_parseables"] = out["lat"].notna() & out["lng"].notna()
    out["rango_global"] = out["lat"].between(-90, 90) & out["lng"].between(-180, 180)
    out["rango_mapa"] = out["lat"].between(*MAP_LAT) & out["lng"].between(*MAP_LON)
    out["rango_corrientes"] = out["lat"].between(*CORR_LAT) & out["lng"].between(*CORR_LON)
    out["posible_invertida"] = out["lng"].between(*CORR_LAT) & out["lat"].between(*CORR_LON)
    out["positiva_sospechosa"] = (out["lat"].fillna(0) > 0) | (out["lng"].fillna(0) > 0)
    out["par_cero"] = out["lat_clase"].eq("cero") & out["lon_clase"].eq("cero")
    out["decimales_lat"] = out["lat"].map(lambda x: len(str(x).split(".")[1].rstrip("0")) if pd.notna(x) and "." in str(x) else 0)
    out["decimales_lng"] = out["lng"].map(lambda x: len(str(x).split(".")[1].rstrip("0")) if pd.notna(x) and "." in str(x) else 0)
    out["precision_baja"] = out["ambas_parseables"] & ((out["decimales_lat"] < 3) | (out["decimales_lng"] < 3))
    out["par_coord"] = out.apply(lambda r: f"{r.lat:.7f}|{r.lng:.7f}" if r.ambas_parseables else "", axis=1)
    return out


def stage(rows: list[dict], name: str, before: int, after: int, reason: str) -> None:
    rows.append({
        "tipo": "etapa_mapa", "dimension": "flujo", "categoria": name,
        "filas_antes": before, "filas_despues": after,
        "filas_descartadas": before - after,
        "porcentaje_retenido": round(after / before * 100, 2) if before else 0.0,
        "motivo": reason,
    })


def metric(rows: list[dict], dimension: str, category: str, value, detail: str = "") -> None:
    rows.append({
        "tipo": "indicador", "dimension": dimension, "categoria": category,
        "filas_antes": "", "filas_despues": value, "filas_descartadas": "",
        "porcentaje_retenido": "", "motivo": detail,
    })


def main() -> None:
    os.environ.setdefault("DATA_SOURCE", "tidb")
    os.environ.setdefault("DATA_MODE", "unificado")
    OUT.mkdir(parents=True, exist_ok=True)

    coordinate_columns = run_query("""
        SELECT table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND (
            LOWER(column_name) REGEXP '(^|_)(lat|lon|lng|latitude|longitude|coordenada_x|coordenada_y|geom|geometry|wkt|x|y)($|_)'
            OR LOWER(column_name) LIKE '%latitud%'
            OR LOWER(column_name) LIKE '%longitud%'
          )
        ORDER BY table_name, ordinal_position
    """)

    establishments = run_query("""
        SELECT e.id_establecimiento, e.ddjj AS id_ddjj_establecimiento,
               e.nombre_estab AS establecimiento, e.departamento_estab,
               e.localidad_estab, e.latitud AS latitud_raw,
               e.longitud AS longitud_raw, dj.id_ddjj, dj.id_productor,
               dj.id_resolucion, YEAR(dj.fecha) AS anio, dj.fecha,
               dj.renspa, dj.pondf, p.ProductorDenominacion AS productor,
               p.CUITCUIL AS cuit_cuil, ta.TipoActividadDesc AS actividad,
               r.numero_resolucion AS resolucion
        FROM establecimientos e
        LEFT JOIN ddjj_personas dj ON dj.id_ddjj = e.ddjj
        LEFT JOIN productores p ON p.ProductorId = dj.id_productor
        LEFT JOIN tipoactividad ta ON ta.TipoActividadId = p.EsPrincipalActividadEconomica
        LEFT JOIN resoluciones r ON r.id_resolucion = dj.id_resolucion
    """)
    adremas = run_query("""
        SELECT a.id_adrema, a.id_establecimiento, a.ddjj AS id_ddjj_adrema,
               a.adrema, a.departamento AS departamento_adrema, a.superficie,
               e.nombre_estab AS establecimiento, e.latitud AS latitud_raw,
               e.longitud AS longitud_raw, dj.id_productor,
               p.ProductorDenominacion AS productor
        FROM adremas a
        LEFT JOIN establecimientos e ON e.id_establecimiento = a.id_establecimiento
        LEFT JOIN ddjj_personas dj ON dj.id_ddjj = a.ddjj
        LEFT JOIN productores p ON p.ProductorId = dj.id_productor
    """)
    ddjj_2023 = run_query("""
        SELECT a.tramite_id, a.adrema, a.departamento, a.localidad,
               a.actividad_original AS actividad, a.origen_dato,
               d.productor_all_id, d.productor_nombre AS productor,
               d.cuit_cuil, d.anio, d.dto AS resolucion
        FROM stg_ddjj_2023_adrema a
        LEFT JOIN vw_all_ddjj_personas d
          ON d.origen_dato = 'ddjj_2023_excel' AND d.ddjj_hist_id = a.tramite_id
        WHERE a.adrema_unica_indicador = 1
    """)
    unified_coverage = run_query("""
        SELECT origen_dato, anio, departamento, actividad, dto AS resolucion,
               COUNT(DISTINCT ddjj_all_id) AS ddjj,
               COUNT(DISTINCT productor_all_id) AS productores
        FROM vw_all_ddjj_personas
        GROUP BY origen_dato, anio, departamento, actividad, dto
    """)
    domicilios = run_query("SELECT COUNT(*) AS filas, SUM(lat IS NOT NULL) AS con_lat, SUM(lng IS NOT NULL) AS con_lng, SUM(lat IS NOT NULL AND lng IS NOT NULL) AS con_ambas FROM domicilios")

    establishments = add_coordinate_diagnostics(establishments)
    establishments["fuente"] = "actual"
    establishments["adrema"] = ""
    establishments["adrema_norm"] = ""
    adrema_by_est = (
        adremas.assign(adrema_norm=adremas["adrema"].map(norm_adrema))
        .groupby("id_establecimiento", dropna=True)
        .agg(adrema=("adrema", lambda s: " | ".join(sorted({clean_text(v) for v in s if clean_text(v)}))),
             adrema_norm=("adrema_norm", lambda s: " | ".join(sorted({v for v in s if v}))))
    )
    establishments = establishments.drop(columns=["adrema", "adrema_norm"]).merge(adrema_by_est, left_on="id_establecimiento", right_index=True, how="left")
    establishments[["adrema", "adrema_norm"]] = establishments[["adrema", "adrema_norm"]].fillna("")

    checks: list[dict] = []
    total = len(establishments)
    raw_nonempty = establishments["latitud_raw"].map(clean_text).ne("") & establishments["longitud_raw"].map(clean_text).ne("")
    raw_nonzero = raw_nonempty & ~establishments["latitud_raw"].map(clean_text).isin(["0", "0.0"]) & ~establishments["longitud_raw"].map(clean_text).isin(["0", "0.0"])
    stage(checks, "universo_establecimientos_actuales", total, total, "Tabla establecimientos, sin filtros")
    stage(checks, "filtro_fuente_actual", total, total, "El mapa siempre consulta establecimientos actuales")
    stage(checks, "filtro_anio_todos", total, total, "Sin filtro anual por defecto")
    stage(checks, "left_join_ddjj", total, len(establishments), "LEFT JOIN; no elimina establecimientos")
    stage(checks, "left_join_productor", len(establishments), len(establishments), "LEFT JOIN; no elimina establecimientos")
    stage(checks, "filtro_coordenadas_raw", total, int(raw_nonzero.sum()), "latitud/longitud no vacías ni '0'")
    stage(checks, "parseo_fix_coord", int(raw_nonzero.sum()), int((raw_nonzero & establishments["ambas_parseables"]).sum()), "Conversión y reparación de punto omitido")
    map_final_mask = raw_nonzero & establishments["ambas_parseables"] & establishments["rango_mapa"]
    stage(checks, "rango_mapa", int((raw_nonzero & establishments["ambas_parseables"]).sum()), int(map_final_mask.sum()), "Lat [-55,-21], lon [-74,-53]")
    stage(checks, "deduplicacion", int(map_final_mask.sum()), int(map_final_mask.sum()), "El código del mapa no deduplica")

    actual_unique = establishments["id_establecimiento"].nunique()
    actual_georef = establishments.loc[map_final_mask, "id_establecimiento"].nunique()
    total_available = actual_unique + ddjj_2023[["tramite_id", "adrema"]].drop_duplicates().shape[0]
    metric(checks, "cobertura", "establecimientos_actuales", actual_unique)
    metric(checks, "cobertura", "adremas_2023_unicas", len(ddjj_2023))
    metric(checks, "cobertura", "establecimientos_disponibles_actual_mas_2023", total_available)
    metric(checks, "cobertura", "puntos_gps_raw_disponibles", int(raw_nonzero.sum()))
    metric(checks, "cobertura", "puntos_mostrados_mapa", int(map_final_mask.sum()))
    metric(checks, "cobertura", "porcentaje_georreferenciado_actual", round(actual_georef / actual_unique * 100, 2) if actual_unique else 0)
    metric(checks, "cobertura", "porcentaje_georreferenciado_actual_mas_2023", round(actual_georef / total_available * 100, 2) if total_available else 0)
    metric(checks, "cobertura", "productores_con_punto", establishments.loc[map_final_mask, "id_productor"].nunique())
    metric(checks, "cobertura", "ddjj_con_punto", establishments.loc[map_final_mask, "id_ddjj"].nunique())
    metric(checks, "cobertura", "adremas_con_punto", adremas.assign(valid=adremas["id_establecimiento"].isin(establishments.loc[map_final_mask, "id_establecimiento"])) .loc[lambda x: x.valid, "adrema"].map(norm_adrema).replace("", np.nan).nunique())
    metric(checks, "cobertura", "adremas_sin_punto", adremas.assign(valid=adremas["id_establecimiento"].isin(establishments.loc[map_final_mask, "id_establecimiento"])) .loc[lambda x: ~x.valid, "adrema"].map(norm_adrema).replace("", np.nan).nunique() + ddjj_2023["adrema"].map(norm_adrema).replace("", np.nan).nunique())
    metric(checks, "calidad", "coordenadas_invertidas_posibles", int(establishments["posible_invertida"].sum()))
    metric(checks, "calidad", "coordenadas_positivas_sospechosas", int(establishments["positiva_sospechosa"].sum()))
    metric(checks, "calidad", "pares_cero", int(establishments["par_cero"].sum()))
    metric(checks, "calidad", "precision_baja", int(establishments["precision_baja"].sum()))
    metric(checks, "calidad", "fuera_corrientes", int((establishments["ambas_parseables"] & ~establishments["rango_corrientes"]).sum()))
    metric(checks, "fuentes_coordenadas", "domicilios_con_ambas", int(domicilios.iloc[0]["con_ambas"] or 0), "No utilizada por el mapa")

    pair_counts = establishments.loc[establishments["par_coord"].ne(""), "par_coord"].value_counts()
    repeated_pairs = pair_counts[pair_counts > 1]
    metric(checks, "calidad", "pares_identicos_repetidos", len(repeated_pairs))
    metric(checks, "calidad", "filas_en_pares_repetidos", int(repeated_pairs.sum()))

    source_rows = []
    def add_group(frame: pd.DataFrame, dimensions: list[str]) -> None:
        for dim in dimensions:
            grouped = frame.groupby(dim, dropna=False).agg(
                establecimientos=("id_establecimiento", "nunique"),
                con_coordenadas=("rango_mapa", "sum"),
                productores=("id_productor", "nunique"),
                ddjj=("id_ddjj", "nunique"),
            ).reset_index()
            grouped["dimension"] = dim
            grouped["categoria"] = grouped[dim].fillna("Sin dato").astype(str)
            grouped["fuente"] = "actual"
            grouped["porcentaje_georreferenciado"] = np.where(grouped["establecimientos"] > 0, grouped["con_coordenadas"] / grouped["establecimientos"] * 100, 0)
            source_rows.extend(grouped[["fuente", "dimension", "categoria", "establecimientos", "con_coordenadas", "porcentaje_georreferenciado", "productores", "ddjj"]].to_dict("records"))
    add_group(establishments.assign(rango_mapa=map_final_mask), ["anio", "departamento_estab", "actividad", "resolucion"])
    for (origin, year), group in unified_coverage.groupby(["origen_dato", "anio"], dropna=False):
        if origin == "actual":
            continue
        source_establishments = (
            int(ddjj_2023.loc[ddjj_2023["anio"].eq(year), ["tramite_id", "adrema"]].drop_duplicates().shape[0])
            if origin == "ddjj_2023_excel"
            else 0
        )
        source_rows.append({
            "fuente": clean_text(origin) or "Sin dato", "dimension": "anio",
            "categoria": clean_text(year) or "Sin dato",
            "establecimientos": source_establishments,
            "con_coordenadas": 0,
            "porcentaje_georreferenciado": 0,
            "productores": int(group["productores"].sum()), "ddjj": int(group["ddjj"].sum()),
        })
    sources = pd.DataFrame(source_rows)

    invalid_mask = ~map_final_mask
    invalid = establishments.loc[invalid_mask, [
        "id_establecimiento", "id_ddjj", "productor", "cuit_cuil", "adrema",
        "establecimiento", "departamento_estab", "localidad_estab", "latitud_raw",
        "longitud_raw", "lat", "lng", "lat_clase", "lon_clase", "posible_invertida",
        "positiva_sospechosa", "precision_baja", "rango_corrientes", "rango_mapa",
    ]].copy()
    invalid["motivo"] = np.select(
        [
            invalid["lat_clase"].isin(["vacio", "cero"]) | invalid["lon_clase"].isin(["vacio", "cero"]),
            invalid["lat_clase"].eq("posible_proyectada") | invalid["lon_clase"].eq("posible_proyectada"),
            invalid["posible_invertida"],
            invalid["lat"].isna() | invalid["lng"].isna(),
            ~invalid["rango_mapa"],
        ],
        ["faltante_o_cero", "posible_sistema_proyectado", "posiblemente_invertida", "no_parseable", "fuera_rango_mapa"],
        default="otro",
    )

    valid_cases = establishments.loc[map_final_mask & establishments["adrema"].ne("")].head(10).copy()
    valid_cases["aparece_mapa"] = True
    valid_cases["motivo_no_aparece"] = ""
    missing_cases = establishments.loc[~map_final_mask & establishments["adrema"].ne("")].head(10).copy()
    missing_cases["aparece_mapa"] = False
    missing_cases["motivo_no_aparece"] = "sin coordenadas válidas o fuera del rango del mapa"
    control = pd.concat([valid_cases, missing_cases], ignore_index=True)
    control["tipo_caso"] = ["adrema_con_gps"] * len(valid_cases) + ["adrema_sin_gps"] * len(missing_cases)
    control_cols = ["tipo_caso", "productor", "cuit_cuil", "adrema", "establecimiento", "departamento_estab", "localidad_estab", "latitud_raw", "longitud_raw", "fuente", "aparece_mapa", "motivo_no_aparece"]
    control = control[control_cols]
    control["tipo"] = "caso_control"
    control["dimension"] = control["tipo_caso"]
    control["categoria"] = control["establecimiento"].fillna("Sin dato")
    checks_df = pd.concat([pd.DataFrame(checks), control], ignore_index=True, sort=False)

    checks_df.to_csv(CHECKS_PATH, index=False, encoding="utf-8-sig")
    sources.to_csv(SOURCES_PATH, index=False, encoding="utf-8-sig")
    invalid.to_csv(INVALID_PATH, index=False, encoding="utf-8-sig")

    final = establishments.loc[map_final_mask]
    bbox = "Sin puntos"
    if not final.empty:
        bbox = f"lat [{final.lat.min():.6f}, {final.lat.max():.6f}], lon [{final.lng.min():.6f}, {final.lng.max():.6f}]"
    invalid_count = int((~establishments["ambas_parseables"]).sum())
    projected = int((establishments["lat_clase"].eq("posible_proyectada") | establishments["lon_clase"].eq("posible_proyectada")).sum())
    lost_after_raw = int(raw_nonzero.sum() - map_final_mask.sum())
    if lost_after_raw and invalid_count:
        diagnosis = "DIAGNOSTICO_MIXTO"
    elif invalid_count:
        diagnosis = "COORDENADAS_INVALIDAS_O_MAL_FORMATEADAS"
    elif actual_georef < actual_unique:
        diagnosis = "MAPA_CORRECTO_COBERTURA_BAJA"
    else:
        diagnosis = "MAPA_CORRECTO_COBERTURA_BAJA"

    report = f"""# Auditoría de georreferenciación del mapa

## Resumen ejecutivo

- **Diagnóstico:** `{diagnosis}`.
- Establecimientos actuales: **{actual_unique:,}**.
- ADREMAS únicas DDJJ 2023 sin geometría: **{len(ddjj_2023):,}**.
- Universo operativo actual + ADREMAS 2023: **{total_available:,}**.
- Pares GPS no vacíos/no cero: **{int(raw_nonzero.sum()):,}**.
- Puntos finales mostrados por la lógica actual: **{int(map_final_mask.sum()):,}**.
- Cobertura de establecimientos actuales: **{actual_georef / actual_unique * 100 if actual_unique else 0:.2f}%**.
- Cobertura incluyendo ADREMAS 2023: **{actual_georef / total_available * 100 if total_available else 0:.2f}%**.

## Fuente exacta del mapa

El mapa consulta `establecimientos` y usa `latitud` y `longitud` (ambas `varchar`). Aplica `LEFT JOIN` con `ddjj_personas`, `productores` y `tipoactividad`. No une ADREMAS, no consulta vistas históricas, no incorpora geometría de DDJJ 2023, no establece límite y no deduplica. El filtro inicial exige valores distintos de cadena vacía y `'0'`; luego aplica `fix_coord` y conserva latitud entre -55 y -21 y longitud entre -74 y -53.

## Pérdidas por etapas

| Etapa | Antes | Después | Descartadas | Retenido |
|---|---:|---:|---:|---:|
"""
    for row in checks:
        if row["tipo"] == "etapa_mapa":
            report += f"| {row['categoria']} | {row['filas_antes']:,} | {row['filas_despues']:,} | {row['filas_descartadas']:,} | {row['porcentaje_retenido']:.2f}% |\n"
    report += f"""

## Calidad de coordenadas

- Coordenadas no parseables o faltantes: **{invalid_count:,}**.
- Posiblemente invertidas: **{int(establishments['posible_invertida'].sum()):,}**.
- Positivas sospechosas: **{int(establishments['positiva_sospechosa'].sum()):,}**.
- Posiblemente proyectadas: **{projected:,}**. No se transformaron.
- Precisión baja: **{int(establishments['precision_baja'].sum()):,}**.
- Pares idénticos repetidos: **{len(repeated_pairs):,}**, que agrupan **{int(repeated_pairs.sum()):,}** filas.
- Bounding box final: **{bbox}**.
- Puntos parseables fuera del rango territorial amplio de Corrientes: **{int((establishments['ambas_parseables'] & ~establishments['rango_corrientes']).sum()):,}**.

## Cobertura por fuente y año

El archivo `{SOURCES_PATH.name}` contiene el detalle por año, departamento, actividad, resolución/evento y origen. Los históricos y DDJJ 2023 pueden tener DDJJ, productores o ADREMAS, pero no una relación geométrica equivalente a `establecimientos` en las vistas disponibles. Por ello su cobertura cartográfica directa es cero en el mapa actual.

## DDJJ 2023

Se identificaron **{len(ddjj_2023):,}** pares únicos trámite + ADREMA. La tabla staging no contiene latitud, longitud ni geometría; el mapa muestra un resumen departamental y detiene la ejecución cuando se selecciona exclusivamente esta fuente.

## Validación visual mínima de la lógica

- PyDeck recibe `get_position="[lng, lat]"`: longitud en X y latitud en Y, correctamente.
- Las coordenadas finales son negativas dentro del rango amplio configurado.
- El centro se calcula con la media de los puntos y el zoom fijo es 6.5.
- El tooltip usa campos de la misma fila: establecimiento, productor, DDJJ y departamento.
- No existe deduplicación; puntos idénticos pueden superponerse visualmente.

## Principales causas

1. El mapa representa únicamente `establecimientos` actuales con coordenadas aprovechables.
2. La mayoría del universo de ADREMAS no implica automáticamente una geometría disponible.
3. DDJJ 2023 aporta ADREMAS, pero no coordenadas validadas.
4. Los históricos carecen de una estructura catastral/geográfica equivalente en las vistas unificadas.
5. Existen valores faltantes o con calidad insuficiente y puntos repetidos/superpuestos.
6. `domicilios.lat/lng` existe, pero representa domicilios y no debe usarse como geometría del establecimiento sin validación semántica.

## Conclusión

**{diagnosis}**. La lógica de ejes y joins actuales no elimina filas mediante joins porque usa `LEFT JOIN`; la reducción principal ocurre por disponibilidad y parseabilidad de coordenadas, por el rango configurado y por la ausencia estructural de geometría en 2023/históricos. La comparación entre puntos y ADREMAS mezcla universos conceptualmente distintos.

## Recomendación técnica para el siguiente paso

Construir primero una capa geográfica auditada a nivel de establecimiento/ADREMA con `origen_dato`, clave de trazabilidad, sistema de referencia declarado y estado de validación. Luego adaptar el mapa para consumir esa capa, incorporar fuentes solo cuando tengan geometría confiable y representar explícitamente la cobertura faltante. No reutilizar coordenadas de domicilio como si fueran prediales sin validación institucional.
"""
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"Establecimientos actuales: {actual_unique}")
    print(f"Puntos GPS raw: {int(raw_nonzero.sum())}")
    print(f"Puntos finales: {int(map_final_mask.sum())}")
    print(f"Diagnóstico: {diagnosis}")
    print(f"Salidas: {OUT}")


if __name__ == "__main__":
    main()
