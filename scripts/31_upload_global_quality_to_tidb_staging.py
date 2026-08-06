"""Carga atómica de resultados globales de calidad a TiDB staging."""
from __future__ import annotations

import importlib.util
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.types import Integer, String, Text


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "data_processed" / "data_quality" / "global"
FILES = {
    "records": SOURCE_DIR / "global_quality_records_flagged.csv",
    "checks": SOURCE_DIR / "global_quality_checks.csv",
    "modules": SOURCE_DIR / "global_quality_by_module.csv",
    "summary": SOURCE_DIR / "global_quality_summary.csv",
}
TABLES = {
    "records": "stg_global_quality_records_flagged",
    "checks": "stg_global_quality_checks",
    "modules": "stg_global_quality_by_module",
    "summary": "stg_global_quality_summary",
}
BOOLEAN_COLUMNS = {"apto_conteo_general", "apto_indicador_sustantivo", "apto_mapa", "apto_vinculacion_productor"}
INTEGER_COLUMNS = {"source_row_number", "checks_pass", "checks_warn", "checks_fail", "registros_evaluados", "registros_con_alerta", "modulos_evaluados", "registros_con_alertas", "alertas_criticas"}


def load_connection_module():
    path = Path(__file__).with_name("27_upload_entregas_to_tidb_staging.py")
    spec = importlib.util.spec_from_file_location("tidb_connection", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"No se pudo cargar {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CONNECTION = load_connection_module()


def safe(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_]+", name):
        raise RuntimeError(f"Identificador SQL no permitido: {name}")
    return name


def read_frames() -> dict[str, pd.DataFrame]:
    frames = {}
    for key, path in FILES.items():
        if not path.is_file():
            raise FileNotFoundError(path)
        frame = pd.read_csv(path, dtype="string", keep_default_na=False, low_memory=False)
        frame.columns = frame.columns.astype(str).str.strip()
        for column in frame.columns:
            if column in BOOLEAN_COLUMNS:
                frame[column] = frame[column].str.strip().str.casefold().isin({"true", "1", "si", "sí", "yes"}).astype("int8")
            elif column in INTEGER_COLUMNS:
                frame[column] = pd.to_numeric(frame[column], errors="coerce").astype("Int64")
            else:
                frame[column] = frame[column].str.strip().replace("", pd.NA)
        frames[key] = frame
    records = frames["records"]
    if len(records) != 40_633:
        raise RuntimeError(f"Alertas locales: {len(records):,}; se esperaban 40.633.")
    if len(frames["modules"]) != 9 or len(frames["summary"]) != 1:
        raise RuntimeError("La cantidad de módulos o filas resumen no coincide con el sistema global.")
    if int(frames["summary"].iloc[0]["checks_pass"]) != 231 or int(frames["summary"].iloc[0]["checks_warn"]) != 18 or int(frames["summary"].iloc[0]["checks_fail"]) != 0:
        raise RuntimeError("Los conteos globales de checks no coinciden con la versión autorizada.")
    return frames


def dtypes(frame: pd.DataFrame) -> dict:
    short = {
        "modulo": 100, "entidad": 80, "registro_id": 128, "productor_id": 128,
        "tramite_id": 128, "entrega_id": 128, "adrema": 800, "regla_calidad": 150,
        "severidad": 20, "estado": 20, "check_id": 40, "categoria": 100,
        "fuente": 500, "fuente_resultado": 500, "estado_modulo": 20,
        "estado_global": 20, "fecha_ejecucion": 50,
    }
    result = {}
    for column in frame.columns:
        if column in BOOLEAN_COLUMNS or column in INTEGER_COLUMNS:
            result[column] = Integer()
        elif column in short:
            result[column] = String(short[column])
        else:
            result[column] = Text()
    return result


def exists(engine, name: str) -> bool:
    with engine.connect() as connection:
        return bool(connection.execute(text("SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=:name"), {"name": name}).scalar())


def row_count(engine, name: str) -> int:
    with engine.connect() as connection:
        return int(connection.execute(text(f"SELECT COUNT(*) FROM `{safe(name)}`")).scalar())


def create_indexes(engine, shadows: dict[str, str]) -> None:
    records = safe(shadows["records"])
    statements = [
        f"CREATE INDEX idx_gq_record ON `{records}` (registro_id)",
        f"CREATE INDEX idx_gq_productor ON `{records}` (productor_id)",
        f"CREATE INDEX idx_gq_tramite ON `{records}` (tramite_id)",
        f"CREATE INDEX idx_gq_entrega ON `{records}` (entrega_id)",
        f"CREATE INDEX idx_gq_adrema ON `{records}` (adrema(100))",
        f"CREATE INDEX idx_gq_modulo ON `{records}` (modulo)",
    ]
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def main() -> None:
    frames = read_frames()
    engine = CONNECTION.make_engine()
    suffix = datetime.now().strftime("%Y%m%d%H%M%S")
    shadows = {key: f"{table}__load_{suffix}" for key, table in TABLES.items()}
    backups = {key: f"{table}__backup_{suffix}" for key, table in TABLES.items()}
    try:
        for key, shadow in shadows.items():
            with engine.begin() as connection:
                connection.execute(text(f"DROP TABLE IF EXISTS `{safe(shadow)}`"))
            frames[key].to_sql(shadow, engine, if_exists="fail", index=False, chunksize=500, method="multi", dtype=dtypes(frames[key]))
            if row_count(engine, shadow) != len(frames[key]):
                raise RuntimeError(f"Conteo transitorio inconsistente en {shadow}")
            print(f"{shadow}: {len(frames[key]):,} filas")
        create_indexes(engine, shadows)
        rename = []
        with engine.begin() as connection:
            for backup in backups.values():
                connection.execute(text(f"DROP TABLE IF EXISTS `{safe(backup)}`"))
        for key, target in TABLES.items():
            if exists(engine, target):
                rename.append(f"`{safe(target)}` TO `{safe(backups[key])}`")
            rename.append(f"`{safe(shadows[key])}` TO `{safe(target)}`")
        with engine.begin() as connection:
            connection.execute(text("RENAME TABLE " + ", ".join(rename)))
        for key, target in TABLES.items():
            if row_count(engine, target) != len(frames[key]):
                raise RuntimeError(f"Validación posterior inconsistente en {target}")
        with engine.begin() as connection:
            for backup in backups.values():
                connection.execute(text(f"DROP TABLE IF EXISTS `{safe(backup)}`"))
        print("Carga staging global completada.")
    except Exception:
        with engine.begin() as connection:
            for shadow in shadows.values():
                connection.execute(text(f"DROP TABLE IF EXISTS `{safe(shadow)}`"))
        raise
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
