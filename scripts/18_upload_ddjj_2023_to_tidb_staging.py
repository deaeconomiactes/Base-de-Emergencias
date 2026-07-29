"""Carga controlada de DDJJ 2023 Excel a tablas staging de TiDB.

El script solo reemplaza las tablas ``stg_ddjj_2023_*`` declaradas en
``TABLE_NAMES``. No modifica tablas productivas, vistas ni archivos fuente.
"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from urllib.parse import quote_plus

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.types import Boolean, Date, Float, Integer, String, Text

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    load_dotenv = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
NORMALIZED_DIR = PROJECT_ROOT / "data_processed" / "ddjj_2023_excel" / "normalized"
BRIDGE_DIR = PROJECT_ROOT / "data_processed" / "ddjj_2023_excel" / "bridge"

SOURCE_FILES = {
    "tramite": NORMALIZED_DIR / "fact_ddjj_tramite_2023.csv",
    "productor": NORMALIZED_DIR / "dim_productor_2023.csv",
    "adrema": NORMALIZED_DIR / "fact_adrema_establecimiento_2023.csv",
    "agricultura": NORMALIZED_DIR / "fact_agricultura_perdida_2023.csv",
    "ganaderia": NORMALIZED_DIR / "fact_ganaderia_declarada_2023.csv",
    "calidad": NORMALIZED_DIR / "fact_calidad_dato_2023.csv",
    "bridge": BRIDGE_DIR / "bridge_ddjj_evento_normativo_2023.csv",
}

TABLE_NAMES = {
    "tramite": "stg_ddjj_2023_tramite",
    "productor": "stg_ddjj_2023_productor",
    "adrema": "stg_ddjj_2023_adrema",
    "agricultura": "stg_ddjj_2023_agricultura",
    "ganaderia": "stg_ddjj_2023_ganaderia",
    "calidad": "stg_ddjj_2023_calidad",
    "bridge": "stg_ddjj_2023_bridge_normativo",
}

EXPECTED_EVENT_ID = "DECRETO_2099_2023"
EXPECTED_ROWS = 1_483
ORIGIN = "ddjj_2023_excel"
SOURCE_LABEL = "DDJJ 2023 Excel"

BOOL_TRUE = {"true", "1", "si", "sí", "yes", "y"}
DATE_COLUMNS = {
    "fecha",
    "fecha_anulacion",
    "certificado_fecha_desde",
    "certificado_fecha_hasta",
    "fecha_inicio_evento",
    "fecha_fin_evento",
    "fecha_validacion",
}
NUMERIC_COLUMNS = {
    "anio",
    "anio_norma",
    "superficie",
    "superficie_sembrada",
    "superficie_afectada",
    "produccion_estimada",
    "produccion_obtenida",
    "cantidad",
    "mortandad",
    "superficie_uso",
}


def env_value(
    primary: str, fallback: str | None = None, default: str | None = None
) -> str | None:
    return os.environ.get(primary) or (
        os.environ.get(fallback) if fallback else None
    ) or default


def load_env_file(path: Path) -> None:
    if load_dotenv is not None:
        load_dotenv(path)
        return
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def ssl_connect_args() -> dict:
    ssl_ca = env_value("TIDB_SSL_CA")
    if not ssl_ca:
        print("TIDB_SSL_CA no definido; se intentara conectar sin ssl_ca.")
        return {}
    ca_path = Path(ssl_ca)
    if not ca_path.is_absolute():
        ca_path = PROJECT_ROOT / ca_path
    if not ca_path.exists():
        raise FileNotFoundError(f"TIDB_SSL_CA apunta a un archivo inexistente: {ca_path}")
    return {"ssl": {"ca": str(ca_path)}}


def connection_url(
    user: str, password: str, host: str, port: str, database: str
) -> str:
    return (
        f"mysql+pymysql://{quote_plus(user)}:{quote_plus(password)}"
        f"@{host}:{port}/{database}?charset=utf8mb4"
    )


def make_engine() -> Engine:
    """Replica el mecanismo de conexión usado por los scripts 05 a 10."""
    load_env_file(PROJECT_ROOT / ".env")
    values = {
        "TIDB_USER": env_value("TIDB_USER"),
        "TIDB_PASSWORD": env_value("TIDB_PASSWORD", "TIDB_PASS"),
        "TIDB_HOST": env_value("TIDB_HOST"),
        "TIDB_PORT": env_value("TIDB_PORT", default="4000"),
        "TIDB_DATABASE": env_value("TIDB_DATABASE", "TIDB_DB"),
    }
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise RuntimeError(f"Faltan variables en .env: {', '.join(missing)}")
    return create_engine(
        connection_url(
            values["TIDB_USER"],
            values["TIDB_PASSWORD"],
            values["TIDB_HOST"],
            values["TIDB_PORT"],
            values["TIDB_DATABASE"],
        ),
        pool_pre_ping=True,
        future=True,
        connect_args=ssl_connect_args(),
    )


def read_source(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(path)
    frame = pd.read_csv(path, dtype="string", low_memory=False)
    frame.columns = [str(column).strip() for column in frame.columns]
    return frame


def clean_key(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip().replace("", pd.NA)


def as_bool(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip().str.casefold().isin(BOOL_TRUE)


def bool_column(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(False, index=frame.index, dtype=bool)
    return as_bool(frame[column])


def stable_row_id(prefix: str, frame: pd.DataFrame) -> pd.Series:
    source_sheet = frame.get("source_sheet", pd.Series("", index=frame.index))
    source_row = frame.get("source_row_number", pd.Series("", index=frame.index))
    values = (
        frame["tramite_id"].fillna("").astype(str)
        + "|"
        + source_sheet.fillna("").astype(str)
        + "|"
        + source_row.fillna("").astype(str)
    )
    return values.map(
        lambda value: f"{prefix}_{hashlib.sha256(value.encode('utf-8')).hexdigest()}"
    )


def convert_types(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in result.columns:
        if column.startswith(("dq_", "apto_")) or column == "adrema_unica_indicador":
            result[column] = as_bool(result[column])
        elif column in DATE_COLUMNS:
            result[column] = pd.to_datetime(result[column], errors="coerce").dt.date
        elif column in NUMERIC_COLUMNS:
            result[column] = pd.to_numeric(result[column], errors="coerce")
    return result


def _require_columns(frame: pd.DataFrame, source: str, columns: set[str]) -> None:
    missing = sorted(columns - set(frame.columns))
    if missing:
        raise RuntimeError(f"{source}: faltan columnas obligatorias: {', '.join(missing)}")


def build_staging_frames() -> dict[str, pd.DataFrame]:
    """Construye en memoria las siete tablas sin modificar los CSV."""
    raw = {name: read_source(path) for name, path in SOURCE_FILES.items()}
    _require_columns(raw["tramite"], "tramite", {"tramite_id", "productor_id_2023"})
    _require_columns(raw["bridge"], "bridge", {"tramite_id", "evento_id_normativo"})
    _require_columns(raw["calidad"], "calidad", {"tramite_id"})

    for frame in raw.values():
        if "tramite_id" in frame.columns:
            frame["tramite_id"] = clean_key(frame["tramite_id"])

    bridge = raw["bridge"].dropna(subset=["tramite_id"]).copy()
    if bridge["tramite_id"].duplicated().any():
        raise RuntimeError("El bridge contiene tramite_id duplicados; no se carga staging.")
    if len(bridge) != EXPECTED_ROWS:
        raise RuntimeError(
            f"El bridge contiene {len(bridge):,} filas; se esperaban {EXPECTED_ROWS:,}."
        )
    if not bridge["evento_id_normativo"].eq(EXPECTED_EVENT_ID).all():
        raise RuntimeError("El bridge contiene eventos distintos de DECRETO_2099_2023.")

    master = raw["tramite"].dropna(subset=["tramite_id"]).copy()
    if master["tramite_id"].duplicated().any():
        raise RuntimeError("La tabla maestra contiene tramite_id duplicados.")

    quality = (
        raw["calidad"]
        .dropna(subset=["tramite_id"])
        .drop_duplicates("tramite_id", keep="first")
        .drop(columns=["origen_dato"], errors="ignore")
    )
    main = master.merge(
        bridge,
        on="tramite_id",
        how="inner",
        validate="one_to_one",
        suffixes=("", "_bridge"),
    ).merge(quality, on="tramite_id", how="left", validate="one_to_one")
    if len(main) != EXPECTED_ROWS:
        raise RuntimeError(
            f"La unión maestra + bridge produjo {len(main):,} filas; "
            f"se esperaban {EXPECTED_ROWS:,}."
        )

    main = main.rename(
        columns={
            "cuit_cuil": "cuit",
            "productor_nombre": "razon_social",
            "fecha_presentacion": "fecha",
            "anio_presentacion": "anio",
            "estado_tramite": "estado",
        }
    )
    main["resolucion_label"] = "Decreto 2099/23"
    main["fuente_datos"] = SOURCE_LABEL
    main["origen_dato"] = ORIGIN
    main = main.drop(columns=["origen_dato_bridge"], errors="ignore")

    integrable_ids = set(main["tramite_id"].dropna())
    producer_ids = set(main["productor_id_2023"].dropna())

    producers = raw["productor"].copy()
    _require_columns(producers, "productor", {"productor_id_2023"})
    producers["productor_id_2023"] = clean_key(producers["productor_id_2023"])
    producers = producers[producers["productor_id_2023"].isin(producer_ids)].copy()
    producers["fuente_datos"] = SOURCE_LABEL
    producers["origen_dato"] = ORIGIN

    adremas = raw["adrema"]
    _require_columns(adremas, "adrema", {"tramite_id", "adrema"})
    adremas = adremas[adremas["tramite_id"].isin(integrable_ids)].copy()
    adremas["adrema_id_2023"] = stable_row_id("adrema", adremas)
    valid_adrema = adremas["adrema"].fillna("").str.strip().ne("")
    first_pair = ~adremas.duplicated(["tramite_id", "adrema"], keep="first")
    adremas["adrema_unica_indicador"] = valid_adrema & first_pair
    surface = pd.to_numeric(adremas.get("superficie"), errors="coerce")
    adremas["apto_indicador_superficie"] = (
        surface.notna()
        & surface.ge(0)
        & ~bool_column(adremas, "dq_superficie_negativa")
        & ~bool_column(adremas, "dq_adrema_duplicada_en_tramite")
    )

    agriculture = raw["agricultura"]
    _require_columns(agriculture, "agricultura", {"tramite_id"})
    agriculture = agriculture[agriculture["tramite_id"].isin(integrable_ids)].copy()
    agriculture["agricultura_id_2023"] = stable_row_id("agricultura", agriculture)
    sown = pd.to_numeric(agriculture.get("superficie_sembrada"), errors="coerce")
    affected = pd.to_numeric(agriculture.get("superficie_afectada"), errors="coerce")
    agriculture["apto_indicador_superficie"] = (
        ~bool_column(agriculture, "dq_superficie_sembrada_negativa")
        & ~bool_column(agriculture, "dq_superficie_afectada_negativa")
        & ~(sown.lt(0).fillna(False) | affected.lt(0).fillna(False))
    )

    livestock = raw["ganaderia"]
    _require_columns(livestock, "ganaderia", {"tramite_id"})
    livestock = livestock[livestock["tramite_id"].isin(integrable_ids)].copy()
    livestock["ganaderia_id_2023"] = stable_row_id("ganaderia", livestock)
    quantity = pd.to_numeric(livestock.get("cantidad"), errors="coerce")
    mortality = pd.to_numeric(livestock.get("mortandad"), errors="coerce")
    mortality_gt_quantity = bool_column(livestock, "dq_mortandad_mayor_cantidad")
    livestock["apto_indicador_cantidad"] = (
        quantity.notna()
        & quantity.ge(0)
        & ~bool_column(livestock, "dq_cantidad_negativa")
        & ~mortality_gt_quantity
    )
    livestock["apto_indicador_mortandad"] = (
        mortality.notna()
        & mortality.ge(0)
        & ~bool_column(livestock, "dq_mortandad_negativa")
        & ~mortality_gt_quantity
    )
    use_surface = pd.to_numeric(livestock.get("superficie_uso"), errors="coerce")
    affected_surface = pd.to_numeric(
        livestock.get("superficie_afectada"), errors="coerce"
    )
    livestock["apto_indicador_superficie"] = ~(
        use_surface.lt(0).fillna(False) | affected_surface.lt(0).fillna(False)
    )

    quality = quality[quality["tramite_id"].isin(integrable_ids)].copy()
    quality["fuente_datos"] = SOURCE_LABEL
    quality["origen_dato"] = ORIGIN
    bridge = bridge.copy()
    bridge["fuente_datos"] = SOURCE_LABEL

    frames = {
        "tramite": main,
        "productor": producers,
        "adrema": adremas,
        "agricultura": agriculture,
        "ganaderia": livestock,
        "calidad": quality,
        "bridge": bridge,
    }
    return {name: convert_types(frame) for name, frame in frames.items()}


def sql_dtypes(frame: pd.DataFrame) -> dict:
    result: dict = {}
    short_strings = {
        "tramite_id": 64,
        "productor_id_2023": 80,
        "evento_id_normativo": 100,
        "adrema_id_2023": 80,
        "agricultura_id_2023": 96,
        "ganaderia_id_2023": 96,
        "adrema": 100,
        "cuit": 50,
        "cuit_cuil": 50,
        "origen_dato": 30,
        "fuente_datos": 50,
        "source_file": 255,
        "source_file_bridge": 255,
        "source_sheet": 255,
    }
    for column in frame.columns:
        if column in short_strings:
            result[column] = String(short_strings[column])
        elif column.startswith(("dq_", "apto_")) or column == "adrema_unica_indicador":
            result[column] = Boolean()
        elif column in DATE_COLUMNS:
            result[column] = Date()
        elif column in {"anio", "anio_norma"}:
            result[column] = Integer()
        elif column in NUMERIC_COLUMNS:
            result[column] = Float()
        elif pd.api.types.is_string_dtype(frame[column]) or pd.api.types.is_object_dtype(
            frame[column]
        ):
            result[column] = Text()
    return result


def upload_frame(engine: Engine, table_name: str, frame: pd.DataFrame) -> None:
    if table_name not in set(TABLE_NAMES.values()):
        raise RuntimeError(f"Tabla fuera de la lista staging autorizada: {table_name}")
    frame.to_sql(
        table_name,
        engine,
        if_exists="replace",
        index=False,
        chunksize=1_000,
        method="multi",
        dtype=sql_dtypes(frame),
    )


def create_indexes(engine: Engine) -> None:
    statements = [
        "CREATE UNIQUE INDEX idx_stg_ddjj_2023_tramite_id "
        "ON stg_ddjj_2023_tramite (tramite_id)",
        "CREATE INDEX idx_stg_ddjj_2023_tramite_productor "
        "ON stg_ddjj_2023_tramite (productor_id_2023)",
        "CREATE UNIQUE INDEX idx_stg_ddjj_2023_productor_id "
        "ON stg_ddjj_2023_productor (productor_id_2023)",
        "CREATE INDEX idx_stg_ddjj_2023_adrema_tramite "
        "ON stg_ddjj_2023_adrema (tramite_id)",
        "CREATE INDEX idx_stg_ddjj_2023_agricultura_tramite "
        "ON stg_ddjj_2023_agricultura (tramite_id)",
        "CREATE INDEX idx_stg_ddjj_2023_ganaderia_tramite "
        "ON stg_ddjj_2023_ganaderia (tramite_id)",
        "CREATE UNIQUE INDEX idx_stg_ddjj_2023_calidad_tramite "
        "ON stg_ddjj_2023_calidad (tramite_id)",
        "CREATE UNIQUE INDEX idx_stg_ddjj_2023_bridge_tramite "
        "ON stg_ddjj_2023_bridge_normativo (tramite_id)",
    ]
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def main() -> None:
    frames = build_staging_frames()
    print("Controles locales previos: OK")
    for name, frame in frames.items():
        print(f"- {TABLE_NAMES[name]}: {len(frame):,} filas preparadas")

    engine = make_engine()
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        print("Conexion a TiDB: OK")
        for name, frame in frames.items():
            upload_frame(engine, TABLE_NAMES[name], frame)
            print(f"{TABLE_NAMES[name]}: {len(frame):,} filas cargadas")
        create_indexes(engine)
        print("Carga staging DDJJ 2023 finalizada.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
