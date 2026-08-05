"""Carga entregas normalizadas a dos tablas staging de TiDB.

La carga se realiza primero en tablas transitorias y luego se reemplazan
atómicamente únicamente ``stg_entregas_emergencia`` y
``stg_entregas_calidad_dato``. No modifica tablas finales ni vistas.
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.types import Date, Float, Integer, String, Text

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    load_dotenv = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
NORMALIZED_DIR = PROJECT_ROOT / "data_processed" / "entregas" / "normalized"
SOURCE_FILES = {
    "entregas": NORMALIZED_DIR / "fact_entregas_emergencia.csv",
    "calidad": NORMALIZED_DIR / "fact_entregas_calidad_dato.csv",
}
TABLE_NAMES = {
    "entregas": "stg_entregas_emergencia",
    "calidad": "stg_entregas_calidad_dato",
}
EXPECTED_ROWS = 14_368
EXPECTED_ALERTS = 9_867

FACT_COLUMNS = [
    "entrega_id", "anio", "fecha_entrega", "productor_nombre",
    "cuit_cuil_original", "cuit_cuil_norm", "documento_original",
    "documento_norm", "renspa", "adrema", "departamento", "localidad",
    "municipio", "paraje", "tipo_asistencia", "proveedor",
    "insumo_producto", "cantidad", "unidad", "monto_estimado", "moneda",
    "norma_evento", "expediente", "fuente_archivo", "fuente_hoja",
    "source_row_number", "origen_dato", "calidad_identificacion", "observaciones",
]
QUALITY_COLUMNS = [
    "entrega_id", "fuente_archivo", "fuente_hoja", "source_row_number",
    "alerta_tipo", "alerta_descripcion", "severidad",
]
DATE_COLUMNS = {"fecha_entrega"}
INTEGER_COLUMNS = {"anio", "source_row_number"}
FLOAT_COLUMNS = {"cantidad", "monto_estimado"}


def env_value(primary: str, fallback: str | None = None, default: str | None = None) -> str | None:
    return os.environ.get(primary) or (os.environ.get(fallback) if fallback else None) or default


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
        print("TIDB_SSL_CA no definido; se intentará conectar sin ssl_ca.")
        return {}
    ca_path = Path(ssl_ca)
    if not ca_path.is_absolute():
        ca_path = PROJECT_ROOT / ca_path
    if not ca_path.exists():
        raise FileNotFoundError(f"TIDB_SSL_CA apunta a un archivo inexistente: {ca_path}")
    return {"ssl": {"ca": str(ca_path)}}


def connection_url(user: str, password: str, host: str, port: str, database: str) -> str:
    return (
        f"mysql+pymysql://{quote_plus(user)}:{quote_plus(password)}"
        f"@{host}:{port}/{database}?charset=utf8mb4"
    )


def make_engine() -> Engine:
    """Usa el mismo mecanismo de conexión que los scripts staging anteriores."""
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
        raise RuntimeError(f"Faltan variables de conexión: {', '.join(missing)}")
    return create_engine(
        connection_url(
            values["TIDB_USER"], values["TIDB_PASSWORD"], values["TIDB_HOST"],
            values["TIDB_PORT"], values["TIDB_DATABASE"],
        ),
        pool_pre_ping=True,
        future=True,
        connect_args=ssl_connect_args(),
    )


def require_columns(frame: pd.DataFrame, expected: list[str], source: str) -> None:
    missing = [column for column in expected if column not in frame.columns]
    if missing:
        raise RuntimeError(f"{source}: faltan columnas obligatorias: {', '.join(missing)}")


def read_source(path: Path, expected_columns: list[str]) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(path)
    frame = pd.read_csv(path, dtype="string", keep_default_na=False, low_memory=False)
    frame.columns = [str(column).strip() for column in frame.columns]
    require_columns(frame, expected_columns, path.name)
    return frame[expected_columns].copy()


def convert_types(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in result.columns:
        if column in DATE_COLUMNS:
            result[column] = pd.to_datetime(result[column], errors="coerce").dt.date
        elif column in INTEGER_COLUMNS:
            result[column] = pd.to_numeric(result[column], errors="coerce").astype("Int64")
        elif column in FLOAT_COLUMNS:
            result[column] = pd.to_numeric(result[column], errors="coerce")
        else:
            result[column] = result[column].astype("string").str.strip().replace("", pd.NA)
    return result


def build_staging_frames() -> dict[str, pd.DataFrame]:
    fact = convert_types(read_source(SOURCE_FILES["entregas"], FACT_COLUMNS))
    quality = convert_types(read_source(SOURCE_FILES["calidad"], QUALITY_COLUMNS))
    if len(fact) != EXPECTED_ROWS:
        raise RuntimeError(f"Entregas locales: {len(fact):,}; se esperaban {EXPECTED_ROWS:,}.")
    if fact["entrega_id"].isna().any() or fact["entrega_id"].duplicated().any():
        raise RuntimeError("entrega_id contiene nulos o duplicados; se cancela la carga.")
    if len(quality) != EXPECTED_ALERTS:
        raise RuntimeError(f"Alertas locales: {len(quality):,}; se esperaban {EXPECTED_ALERTS:,}.")
    if (~quality["entrega_id"].isin(fact["entrega_id"])).any():
        raise RuntimeError("Existen alertas sin entrega_id presente en la tabla normalizada.")
    return {"entregas": fact, "calidad": quality}


def sql_dtypes(frame: pd.DataFrame) -> dict:
    lengths = {
        "entrega_id": 64, "cuit_cuil_original": 50, "cuit_cuil_norm": 20,
        "documento_original": 50, "documento_norm": 20, "renspa": 100,
        "adrema": 100, "departamento": 150, "localidad": 150,
        "municipio": 150, "paraje": 200, "tipo_asistencia": 100,
        "proveedor": 150, "unidad": 50, "moneda": 20,
        "expediente": 150, "fuente_archivo": 255, "fuente_hoja": 255,
        "origen_dato": 50, "calidad_identificacion": 20,
        "alerta_tipo": 100, "severidad": 20,
    }
    result: dict = {}
    for column in frame.columns:
        if column in DATE_COLUMNS:
            result[column] = Date()
        elif column in INTEGER_COLUMNS:
            result[column] = Integer()
        elif column in FLOAT_COLUMNS:
            result[column] = Float()
        elif column in lengths:
            result[column] = String(lengths[column])
        else:
            result[column] = Text()
    return result


def safe_identifier(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_]+", name):
        raise RuntimeError(f"Identificador SQL no permitido: {name}")
    return name


def table_exists(engine: Engine, table_name: str) -> bool:
    with engine.connect() as connection:
        return bool(connection.execute(
            text("""
                SELECT COUNT(*) FROM information_schema.TABLES
                WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table_name
            """), {"table_name": table_name},
        ).scalar())


def count_rows(engine: Engine, table_name: str) -> int:
    table_name = safe_identifier(table_name)
    with engine.connect() as connection:
        return int(connection.execute(text(f"SELECT COUNT(*) FROM `{table_name}`")).scalar())


def create_indexes(engine: Engine, shadow_tables: dict[str, str]) -> None:
    statements = [
        f"CREATE UNIQUE INDEX idx_entrega_id ON `{safe_identifier(shadow_tables['entregas'])}` (entrega_id)",
        f"CREATE INDEX idx_entrega_cuit ON `{safe_identifier(shadow_tables['entregas'])}` (cuit_cuil_norm)",
        f"CREATE INDEX idx_entrega_documento ON `{safe_identifier(shadow_tables['entregas'])}` (documento_norm)",
        f"CREATE INDEX idx_entrega_renspa ON `{safe_identifier(shadow_tables['entregas'])}` (renspa)",
        f"CREATE INDEX idx_entrega_adrema ON `{safe_identifier(shadow_tables['entregas'])}` (adrema)",
        f"CREATE INDEX idx_calidad_entrega ON `{safe_identifier(shadow_tables['calidad'])}` (entrega_id)",
        f"CREATE INDEX idx_calidad_tipo ON `{safe_identifier(shadow_tables['calidad'])}` (alerta_tipo)",
    ]
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def load_shadow_tables(engine: Engine, frames: dict[str, pd.DataFrame]) -> dict[str, str]:
    suffix = datetime.now().strftime("%Y%m%d%H%M%S")
    shadows = {key: f"{table}__load_{suffix}" for key, table in TABLE_NAMES.items()}
    try:
        for key, shadow in shadows.items():
            shadow = safe_identifier(shadow)
            with engine.begin() as connection:
                connection.execute(text(f"DROP TABLE IF EXISTS `{shadow}`"))
            frames[key].to_sql(
                shadow, engine, if_exists="fail", index=False, chunksize=500,
                method="multi", dtype=sql_dtypes(frames[key]),
            )
            observed = count_rows(engine, shadow)
            if observed != len(frames[key]):
                raise RuntimeError(
                    f"Carga transitoria {shadow}: {observed:,}; esperadas {len(frames[key]):,}."
                )
            print(f"{shadow}: {observed:,} filas verificadas")
        create_indexes(engine, shadows)
        return shadows
    except Exception:
        with engine.begin() as connection:
            for shadow in shadows.values():
                connection.execute(text(f"DROP TABLE IF EXISTS `{safe_identifier(shadow)}`"))
        raise


def atomic_replace(engine: Engine, shadows: dict[str, str]) -> None:
    suffix = datetime.now().strftime("%Y%m%d%H%M%S")
    backups = {key: f"{table}__backup_{suffix}" for key, table in TABLE_NAMES.items()}
    rename_parts: list[str] = []
    with engine.begin() as connection:
        for backup in backups.values():
            connection.execute(text(f"DROP TABLE IF EXISTS `{safe_identifier(backup)}`"))
    for key, target in TABLE_NAMES.items():
        if table_exists(engine, target):
            rename_parts.append(
                f"`{safe_identifier(target)}` TO `{safe_identifier(backups[key])}`"
            )
        rename_parts.append(
            f"`{safe_identifier(shadows[key])}` TO `{safe_identifier(target)}`"
        )
    with engine.begin() as connection:
        connection.execute(text("RENAME TABLE " + ", ".join(rename_parts)))
    with engine.begin() as connection:
        for backup in backups.values():
            connection.execute(text(f"DROP TABLE IF EXISTS `{safe_identifier(backup)}`"))


def main() -> None:
    frames = build_staging_frames()
    print("Controles locales previos: OK")
    print(f"- entregas: {len(frames['entregas']):,}")
    print(f"- alertas: {len(frames['calidad']):,}")
    engine = make_engine()
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        print("Conexión a TiDB: OK")
        shadows = load_shadow_tables(engine, frames)
        atomic_replace(engine, shadows)
        for key, target in TABLE_NAMES.items():
            print(f"{target}: {count_rows(engine, target):,} filas cargadas")
        print("Carga staging de entregas finalizada.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
