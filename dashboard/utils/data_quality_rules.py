"""Acceso seguro y exclusivamente lector a reglas globales de calidad."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import pandas as pd
import streamlit as st


ROOT = Path(__file__).resolve().parents[2]
QUALITY_DIR = ROOT / "data_processed" / "data_quality" / "global"
FLAGS_PATH = QUALITY_DIR / "global_quality_records_flagged.csv"
CHECKS_PATH = QUALITY_DIR / "global_quality_checks.csv"
BOOL_COLUMNS = ["apto_conteo_general", "apto_indicador_sustantivo", "apto_mapa", "apto_vinculacion_productor"]
STAGING_TABLE = "stg_global_quality_records_flagged"


def _as_bool(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.casefold().isin({"true", "1", "si", "sí", "yes"})


@lru_cache(maxsize=1)
def load_quality_results() -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """Carga resultados locales; nunca bloquea la aplicación si faltan."""
    try:
        flags = pd.read_csv(FLAGS_PATH, low_memory=False) if FLAGS_PATH.exists() else pd.DataFrame()
        checks = pd.read_csv(CHECKS_PATH, low_memory=False) if CHECKS_PATH.exists() else pd.DataFrame()
        for column in BOOL_COLUMNS:
            if column in flags:
                flags[column] = _as_bool(flags[column])
        status = "local_disponible" if not flags.empty else "local_no_disponible"
        return flags, checks, status
    except Exception as exc:
        return pd.DataFrame(), pd.DataFrame(), f"error_local:{type(exc).__name__}"


def _tidb_enabled() -> bool:
    return (os.getenv("DATA_SOURCE", "local") or "local").casefold() == "tidb"


@st.cache_data(ttl=300, show_spinner=False)
def _tidb_query(sql: str, params_items: tuple[tuple[str, object], ...] = ()) -> pd.DataFrame:
    from utils import run_query
    return run_query(sql, dict(params_items))


@st.cache_data(ttl=300, show_spinner=False)
def _staging_available() -> bool:
    if not _tidb_enabled():
        return False
    try:
        result = _tidb_query(
            "SELECT COUNT(*) AS n FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=:table",
            (("table", STAGING_TABLE),),
        )
        return bool(int(result.iloc[0]["n"]))
    except Exception:
        return False


def quality_status() -> dict[str, object]:
    if _staging_available():
        try:
            result = _tidb_query(f"SELECT COUNT(*) AS alertas FROM `{STAGING_TABLE}`")
            return {"estado": "tidb_staging", "alertas": int(result.iloc[0]["alertas"]), "checks": None, "ruta": STAGING_TABLE}
        except Exception:
            pass
    flags, checks, status = load_quality_results()
    return {"estado": status, "alertas": len(flags), "checks": len(checks), "ruta": str(FLAGS_PATH)}


def query_flags(*, module: str | None = None, record_ids=None, tramite_ids=None, entrega_ids=None, adremas=None) -> pd.DataFrame:
    if _staging_available():
        conditions = []
        params: dict[str, object] = {}
        if module:
            conditions.append("modulo=:module")
            params["module"] = module
        key_filters = [("registro_id", record_ids), ("tramite_id", tramite_ids), ("entrega_id", entrega_ids), ("adrema", adremas)]
        key_conditions = []
        for column, values in key_filters:
            if values is None:
                continue
            normalized = sorted({str(value).strip() for value in values if str(value).strip()})
            if not normalized:
                continue
            placeholders = []
            for index, value in enumerate(normalized):
                name = f"{column}_{index}"
                params[name] = value
                placeholders.append(f":{name}")
            key_conditions.append(f"{column} IN ({','.join(placeholders)})")
        if key_conditions:
            conditions.append("(" + " OR ".join(key_conditions) + ")")
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        try:
            result = _tidb_query(
                f"SELECT * FROM `{STAGING_TABLE}`{where}",
                tuple(sorted(params.items())),
            )
            for column in BOOL_COLUMNS:
                if column in result:
                    result[column] = pd.to_numeric(result[column], errors="coerce").fillna(1).astype(bool)
            return result
        except Exception:
            pass
    flags, _, _ = load_quality_results()
    if flags.empty:
        return flags.copy()
    result = flags.copy()
    if module:
        result = result[result["modulo"].eq(module)]
    filters = [("registro_id", record_ids), ("tramite_id", tramite_ids), ("entrega_id", entrega_ids), ("adrema", adremas)]
    supplied = False
    mask = pd.Series(False, index=result.index)
    for column, values in filters:
        if values is None or column not in result:
            continue
        normalized = {str(value).strip() for value in values if str(value).strip()}
        if normalized:
            supplied = True
            mask |= result[column].astype(str).str.strip().isin(normalized)
    return result[mask].copy() if supplied else result


def unsuitable_ids(module: str, key: str, aptitude: str) -> set[str]:
    flags = query_flags(module=module)
    if flags.empty or key not in flags or aptitude not in flags:
        return set()
    return set(flags.loc[~flags[aptitude], key].dropna().astype(str).str.strip()) - {""}


def aptitude_for(**keys) -> dict[str, bool]:
    matches = query_flags(
        record_ids=keys.get("record_ids"), tramite_ids=keys.get("tramite_ids"),
        entrega_ids=keys.get("entrega_ids"), adremas=keys.get("adremas"),
    )
    if matches.empty:
        return {column: True for column in BOOL_COLUMNS}
    return {column: bool(matches[column].all()) if column in matches else True for column in BOOL_COLUMNS}


def get_quality_flags_by_tramite(tramite_ids) -> pd.DataFrame:
    return query_flags(tramite_ids=tramite_ids)


def get_quality_flags_by_entrega(entrega_ids) -> pd.DataFrame:
    return query_flags(entrega_ids=entrega_ids)


def get_quality_flags_by_adrema(adremas) -> pd.DataFrame:
    return query_flags(adremas=adremas)


def get_quality_flags_by_productor(productor_ids) -> pd.DataFrame:
    if _staging_available():
        normalized = sorted({str(value).strip() for value in productor_ids if str(value).strip()})
        if normalized:
            params = {f"pid_{i}": value for i, value in enumerate(normalized)}
            placeholders = ",".join(f":pid_{i}" for i in range(len(normalized)))
            try:
                result = _tidb_query(
                    f"SELECT * FROM `{STAGING_TABLE}` WHERE productor_id IN ({placeholders})",
                    tuple(sorted(params.items())),
                )
                for column in BOOL_COLUMNS:
                    if column in result:
                        result[column] = pd.to_numeric(result[column], errors="coerce").fillna(1).astype(bool)
                return result
            except Exception:
                pass
    flags, _, _ = load_quality_results()
    if flags.empty:
        return flags
    normalized = {str(value).strip() for value in productor_ids if str(value).strip()}
    return flags[flags["productor_id"].astype(str).str.strip().isin(normalized)].copy()


def is_apto_indicador(**keys) -> bool:
    return aptitude_for(**keys)["apto_indicador_sustantivo"]


def is_apto_mapa(**keys) -> bool:
    return aptitude_for(**keys)["apto_mapa"]


def is_apto_vinculacion(**keys) -> bool:
    return aptitude_for(**keys)["apto_vinculacion_productor"]


METHODOLOGY_NOTE = (
    "Los indicadores cuantitativos excluyen registros marcados como no aptos por controles de calidad. "
    "Los registros excluidos se conservan para trazabilidad y auditoría."
)
