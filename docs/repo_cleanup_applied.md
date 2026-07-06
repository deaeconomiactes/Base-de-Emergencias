# Limpieza aplicada del repositorio

Fecha de aplicacion: 2026-07-06

## Objetivo

Dejar la raiz del repositorio enfocada en la estructura productiva actual del dashboard y del pipeline historico/unificado, eliminando scripts legacy de cargas puntuales que ya no forman parte del flujo vigente.

## Elementos eliminados

Se eliminaron de la raiz del repositorio los siguientes archivos legacy:

- `importar_local.sh`
- `subir_a_tidb.py`
- `subir_a_tidb.sh`
- `transformar.py`
- `importar_tablas_tidb.py`

Estos archivos correspondian al flujo anterior de importacion, transformacion o carga. Fueron reemplazados por la estructura actual basada en `scripts/`, `sql/`, `config/` y vistas unificadas en TiDB.

## Elementos solicitados que no existian

Al momento de aplicar la limpieza, no se encontraron en la raiz del repositorio:

- `Anibal/`
- `carpeta general/`
- `scratch/`
- `crear_mock_data.py`
- `importar_excel_dto_2016.py`
- `importar_excel_dto_2017_235.py`
- `importar_excel_dto_2018.py`
- `reparar_agri_2017.py`
- `reparar_ponde_2017.py`
- `__MACOSX/`
- `.DS_Store`
- `__pycache__/`
- archivos `*.pyc` fuera de carpetas excluidas

## Estructura productiva preservada

Se preservaron los componentes necesarios para el dashboard productivo y el pipeline historico/unificado:

- `dashboard/`
- `scripts/`
- `sql/`
- `config/`
- `docs/`
- `requirements.txt`
- `README.md`
- `.env.example`
- `.gitignore`
- `ANALISIS_BASE_DATOS.md`

Tambien se verifico que sigan existiendo:

- `dashboard/app.py`
- `requirements.txt`
- `.gitignore`

## Datos y credenciales

No se tocaron datos productivos en TiDB.

No se tocaron datos locales de trabajo ni carpetas de datos:

- `data_raw/`
- `data_clean/`
- `data_intermediate/`

No se tocaron secrets ni configuraciones sensibles:

- `.env`
- `dashboard/.streamlit/secrets.toml`
- Streamlit Cloud secrets

## Regla de exclusion vigente

El archivo `.gitignore` mantiene reglas para excluir datos, dumps, secrets, archivos Excel, entornos virtuales y caches. Esto reduce el riesgo de subir a GitHub informacion sensible, bases pesadas o salidas reproducibles.

## Estado final

La limpieza fue local. No se realizo commit ni push.
