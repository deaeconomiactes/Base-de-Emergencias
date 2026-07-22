"""
Capa de acceso a datos del dashboard.

Lee la conexión del .env (DATA_SOURCE = 'local' | 'tidb') y expone:
- get_engine(): SQLAlchemy Engine cacheado.
- run_query(sql, **params): pd.DataFrame cacheado.
- fix_coord(s): repara coordenadas guardadas como varchar con el punto perdido.
- helpers: listas para filtros (resoluciones, departamentos, etc).
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Cargar .env desde la raíz del proyecto (un nivel arriba de dashboard/)
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _apply_streamlit_secrets() -> None:
    """Streamlit Cloud inyecta Secrets en TOML → los copiamos a os.environ."""
    try:
        for key, value in st.secrets.items():
            if isinstance(value, (str, int, float, bool)):
                os.environ[str(key)] = str(value)
    except Exception:
        pass  # Sin secrets.toml local o fuera de Streamlit


def _env(key: str, default: str | None = None) -> str | None:
    _apply_streamlit_secrets()
    return os.getenv(key, default)


TABLES_ACTUAL = {
    "resoluciones": "resoluciones",
    "ddjj_personas": "ddjj_personas",
    "productores": "productores",
    "tipoactividad": "tipoactividad",
    "agricultura": "agricultura",
    "cultivos": "cultivos",
    "cultivostipo": "cultivostipo",
    "ganaderia_resumen": "bovinos",
}

TABLES_UNIFICADO = {
    "resoluciones": "vw_all_resoluciones",
    "ddjj_personas": "vw_all_ddjj_personas",
    "productores": "vw_all_productores",
    "tipoactividad": "vw_all_tipoactividad",
    "agricultura": "vw_all_agricultura",
    "cultivos": "vw_all_cultivos",
    "cultivostipo": "vw_all_cultivostipo",
    "ganaderia_resumen": "vw_all_ganaderia_resumen",
}


def data_mode() -> str:
    """Modo de datos: actual mantiene tablas originales; unificado usa vw_all_*."""
    mode = (_env("DATA_MODE", "actual") or "actual").lower()
    return "unificado" if mode == "unificado" else "actual"


def is_unified_mode() -> bool:
    return data_mode() == "unificado"


def table(name: str) -> str:
    mapping = TABLES_UNIFICADO if is_unified_mode() else TABLES_ACTUAL
    return mapping.get(name, name)


def _ssl_ca_path() -> str:
    """Ruta al CA para TiDB; en la nube usa certifi si el path del .env no existe."""
    path = _env("TIDB_SSL_CA", "/etc/ssl/cert.pem") or "/etc/ssl/cert.pem"
    if Path(path).is_file():
        return path
    try:
        import certifi
        return certifi.where()
    except ImportError:
        return path


def _connection_url() -> tuple[str, dict]:
    """Construye la URL SQLAlchemy según DATA_SOURCE."""
    source = (_env("DATA_SOURCE", "local") or "local").lower()

    if source == "tidb":
        host = _env("TIDB_HOST")
        port = int(_env("TIDB_PORT", "4000") or "4000")
        user = _env("TIDB_USER")
        pwd = _env("TIDB_PASS")
        db = _env("TIDB_DB")
        ssl_ca = _ssl_ca_path()
        if not all([host, user, pwd, db]):
            raise RuntimeError(
                "DATA_SOURCE=tidb pero faltan variables TIDB_* en .env"
            )
        url = (
            f"mysql+pymysql://{user}:{pwd}@{host}:{port}/{db}"
            "?charset=utf8mb4"
        )
        connect_args = {"ssl": {"ca": ssl_ca}}
        return url, connect_args

    # local
    host = _env("MYSQL_HOST", "127.0.0.1")
    port = int(_env("MYSQL_PORT", "3306") or "3306")
    user = _env("MYSQL_USER", "root")
    pwd = _env("MYSQL_PASSWORD", "") or ""
    db = _env("MYSQL_DATABASE", "emergencias")
    url = f"mysql+pymysql://{user}:{pwd}@{host}:{port}/{db}?charset=utf8mb4"
    return url, {}


@st.cache_resource(show_spinner=False)
def get_engine():
    url, connect_args = _connection_url()
    return create_engine(url, pool_pre_ping=True, connect_args=connect_args)


@st.cache_data(ttl=600, show_spinner=False)
def run_query(sql: str, params: dict | None = None) -> pd.DataFrame:
    """Ejecuta una query y devuelve un DataFrame, con caché de 10 min."""
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params or {})


def db_info() -> dict:
    """Devuelve metadatos del origen activo."""
    source = (_env("DATA_SOURCE", "local") or "local").lower()
    if source == "tidb":
        return {
            "source": "TiDB Cloud",
            "host": _env("TIDB_HOST"),
            "db": _env("TIDB_DB"),
            "mode": data_mode(),
        }
    return {
        "source": "MySQL local",
        "host": _env("MYSQL_HOST", "127.0.0.1"),
        "db": _env("MYSQL_DATABASE", "emergencias"),
        "mode": data_mode(),
    }


# ---------- Helpers de dominio ----------


def fix_coord(s) -> float | None:
    """Repara coordenadas guardadas como varchar con punto faltante.

    Ej: '-2769864082' → -27.69864082 ; '-290000000000' → -29.0
    """
    if s is None:
        return None
    s = str(s).strip()
    if s in ("", "0", "0.0", "NULL"):
        return None
    try:
        val = float(s)
    except ValueError:
        return None
    if -180 <= val <= 180 and val != 0:
        return val
    sign = -1 if s.startswith("-") else 1
    digits = s.lstrip("-").replace(".", "")
    if len(digits) < 3:
        return None
    fixed = digits[:2] + "." + digits[2:]
    try:
        out = sign * float(fixed)
    except ValueError:
        return None
    if -180 <= out <= 180:
        return out
    return None


@st.cache_data(ttl=3600, show_spinner=False)
def list_resoluciones() -> pd.DataFrame:
    if is_unified_mode():
        return run_query(
            """
            SELECT resolucion_all_id AS id_resolucion,
                   nombre_resolucion, numero_resolucion, fec_res, origen_dato
            FROM vw_all_resoluciones
            ORDER BY fec_res DESC
            """
        )
    return run_query(
        "SELECT id_resolucion, nombre_resolucion, numero_resolucion, fec_res "
        "FROM resoluciones ORDER BY fec_res DESC"
    )


@st.cache_data(ttl=3600, show_spinner=False)
def list_departamentos() -> pd.DataFrame:
    return run_query(
        "SELECT DepartamentoId, DepartamentoDesc, ProvinciaId "
        "FROM departamentos ORDER BY DepartamentoDesc"
    )


@st.cache_data(ttl=3600, show_spinner=False)
def list_actividades() -> pd.DataFrame:
    return run_query(
        "SELECT TipoActividadId AS id, TipoActividadDesc AS descripcion "
        "FROM tipoactividad ORDER BY TipoActividadDesc"
    )


@st.cache_data(ttl=3600, show_spinner=False)
def list_rubros() -> pd.DataFrame:
    return run_query("SELECT id_rubro, nombre FROM rubro_tipos ORDER BY id_rubro")


@st.cache_data(ttl=3600, show_spinner=False)
def list_departamentos_ddjj() -> list[str]:
    df = run_query(
        f"SELECT DISTINCT departamento FROM {table('ddjj_personas')} "
        "WHERE departamento <> '' ORDER BY departamento"
    )
    return df["departamento"].tolist()


# ---------- Queries de alto nivel ----------


@st.cache_data(ttl=600, show_spinner=False)
def kpis_generales() -> dict:
    """Calcula cada KPI por separado para aislar fallos de TiDB."""
    kpis = {
        "productores": None,
        "ddjj": None,
        "resoluciones": None,
        "establecimientos": None,
        "adremas": None,
        "pondf_promedio": None,
    }

    consultas = {
        "productores": f"SELECT COUNT(*) AS valor FROM {table('productores')}",
        "ddjj": f"SELECT COUNT(*) AS valor FROM {table('ddjj_personas')}",
        "resoluciones": f"SELECT COUNT(*) AS valor FROM {table('resoluciones')}",
        "establecimientos": "SELECT COUNT(*) AS valor FROM establecimientos",
        "adremas": "SELECT COUNT(*) AS valor FROM adremas",
    }

    for nombre, sql in consultas.items():
        try:
            df = run_query(sql)
            if not df.empty and pd.notna(df.iloc[0]["valor"]):
                kpis[nombre] = int(df.iloc[0]["valor"])
        except Exception:
            kpis[nombre] = None

    try:
        ddjj_table = table("ddjj_personas")
        df = run_query(
            f"SELECT ROUND(AVG(pondf), 2) AS valor FROM {ddjj_table} "
            "WHERE pondf IS NOT NULL AND pondf > 0"
        )
        if not df.empty and pd.notna(df.iloc[0]["valor"]):
            kpis["pondf_promedio"] = float(df.iloc[0]["valor"])
    except Exception:
        kpis["pondf_promedio"] = None

    return kpis
