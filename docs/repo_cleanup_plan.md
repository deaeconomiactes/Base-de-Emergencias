# Plan de limpieza segura del repositorio

## Objetivo

Dejar el repositorio limpio para produccion despues de la integracion historica/unificada, sin romper el dashboard desplegado en Streamlit Cloud y sin eliminar datos ni scripts sin revision.

Esta auditoria no borra ni mueve archivos. Solo clasifica y recomienda.

## Verificaciones realizadas

- El main file del despliegue sigue siendo `dashboard/app.py`.
- `README.md` documenta `dashboard/app.py` como main file de Streamlit Cloud.
- `dashboard/.streamlit/secrets.toml.example` incluye `DATA_SOURCE = "tidb"` y `DATA_MODE = "unificado"`.
- `requirements.txt` cubre las dependencias principales del dashboard.
- `git` no estuvo disponible en esta terminal, por lo que la auditoria se hizo por inventario local.

## Estructura recomendada final

```text
BaseEmergencias-main/
|-- .env.example
|-- .gitignore
|-- ANALISIS_BASE_DATOS.md
|-- README.md
|-- requirements.txt
|-- config/
|   |-- event_mapping.csv
|   `-- file_formats.csv
|-- dashboard/
|   |-- app.py
|   |-- utils.py
|   |-- .streamlit/
|   |   |-- config.toml
|   |   `-- secrets.toml.example
|   `-- pages/
|       |-- 1_Productores.py
|       |-- 2_Detalle_DDJJ.py
|       |-- 3_Adremas.py
|       |-- 4_Mapa.py
|       `-- 5_Analisis.py
|-- docs/
|-- scripts/
|   |-- 00_inventory_excel.py
|   |-- 01_transform_historical_files.py
|   |-- 02_quality_report.py
|   |-- 03_consolidate_events.py
|   |-- 04_quality_report_consolidated.py
|   |-- 05_upload_to_tidb_staging.py
|   |-- 06_validate_tidb_staging.py
|   |-- 07_create_historical_views.py
|   |-- 08_validate_historical_views.py
|   |-- 09_create_unified_views.py
|   |-- 10_validate_unified_views.py
|   |-- 11_copy_current_tables_to_tidb.py
|   `-- 12_validate_current_tables_in_dest.py
`-- sql/
    |-- 01_create_historical_views.sql
    `-- 02_create_unified_views.sql
```

## Archivos imprescindibles para produccion

### Dashboard

- `dashboard/app.py`
- `dashboard/utils.py`
- `dashboard/pages/1_Productores.py`
- `dashboard/pages/2_Detalle_DDJJ.py`
- `dashboard/pages/3_Adremas.py`
- `dashboard/pages/4_Mapa.py`
- `dashboard/pages/5_Analisis.py`
- `dashboard/.streamlit/config.toml`
- `dashboard/.streamlit/secrets.toml.example`

Riesgo de borrar: alto. Rompe Streamlit o deja sin paginas al dashboard.

### Configuracion y dependencias

- `requirements.txt`
- `.env.example`
- `.gitignore`
- `README.md`

Riesgo de borrar: alto/medio. Puede romper deploy, instalacion local o documentacion de despliegue.

### Pipeline historico/unificado

- `config/event_mapping.csv`
- `config/file_formats.csv`
- `scripts/00_inventory_excel.py`
- `scripts/01_transform_historical_files.py`
- `scripts/02_quality_report.py`
- `scripts/03_consolidate_events.py`
- `scripts/04_quality_report_consolidated.py`
- `scripts/05_upload_to_tidb_staging.py`
- `scripts/06_validate_tidb_staging.py`
- `scripts/07_create_historical_views.py`
- `scripts/08_validate_historical_views.py`
- `scripts/09_create_unified_views.py`
- `scripts/10_validate_unified_views.py`
- `scripts/11_copy_current_tables_to_tidb.py`
- `scripts/12_validate_current_tables_in_dest.py`
- `sql/01_create_historical_views.sql`
- `sql/02_create_unified_views.sql`

Riesgo de borrar: alto si se necesita reproducibilidad o reconstruccion de vistas/staging.

### Documentacion util

- `docs/commit_plan_integracion_historica.md`
- `docs/current_data_migration_plan.md`
- `docs/current_data_source_audit.md`
- `docs/dump_search_report.md`
- `docs/streamlit_data_dependencies.md`
- `docs/streamlit_unified_integration_plan.md`
- `docs/visual_cleanup_plan.md`
- `ANALISIS_BASE_DATOS.md`

Riesgo de borrar: medio. No rompe ejecucion, pero elimina trazabilidad metodologica.

## Archivos seguros para borrar despues de revisar

Estos archivos/carpetas son artefactos locales o de sistema. No son necesarios para produccion:

- `dashboard/__MACOSX/`
- `dashboard/__MACOSX/._.streamlit`
- `dashboard/__MACOSX/.streamlit/._config.toml`
- `dashboard/__MACOSX/.streamlit/._secrets.toml.example`
- cualquier `__pycache__/`
- cualquier `*.pyc`
- `.venv/`
- `.venv_local/`

Riesgo de borrar: bajo. Son caches, entornos locales o metadatos de macOS.

Comandos sugeridos, solo cuando se decida ejecutar limpieza:

```powershell
Remove-Item -Recurse -Force dashboard\__MACOSX
Get-ChildItem -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force
Get-ChildItem -Recurse -File -Filter *.pyc | Remove-Item -Force
```

No ejecutar esos comandos sin una confirmacion especifica previa.

## Archivos candidatos a mover a `legacy/`

Estos archivos pertenecen al flujo original o a cargas previas. No fueron usados directamente en la integracion historica/unificada actual, pero pueden ser utiles como referencia:

- `generar_mock.py`
- `importar_local.ps1`
- `importar_local.sh`
- `importar_tablas_tidb.py`
- `subir_a_tidb.py`
- `subir_a_tidb.sh`
- `transformar.py`

Riesgo de borrar: medio. Pueden contener conocimiento del flujo original, scripts de importacion previos o ejemplos de conexion. Recomendacion: mover a `legacy/` en vez de borrar.

Comando sugerido futuro:

```powershell
New-Item -ItemType Directory -Force legacy
Move-Item generar_mock.py, importar_local.ps1, importar_local.sh, importar_tablas_tidb.py, subir_a_tidb.py, subir_a_tidb.sh, transformar.py legacy\
```

No ejecutar sin confirmacion especifica.

## Candidatos mencionados pero no encontrados en este workspace

No se encontraron en el inventario local:

- `Anibal/`
- `carpeta general/`
- `scratch/`
- `crear_mock_data.py`
- `importar_excel_dto_2016.py`
- `importar_excel_dto_2017_235.py`
- `importar_excel_dto_2018.py`
- `reparar_agri_2017.py`
- `reparar_ponde_2017.py`

Si aparecen en otro clone/worktree, recomendacion: mover a `legacy/companero/` o excluir del commit hasta clasificarlos.

## Archivos que no se deben tocar

- `.env`
- `dashboard/.streamlit/secrets.toml`
- `data_raw/`
- `data_clean/`
- `data_intermediate/`
- dumps reales `.sql`, `.sql.gz`, `.dump`, `.bak`
- certificados privados
- cualquier archivo con contrasenas o tokens

Motivo: seguridad, datos sensibles o salidas reproducibles que no deben versionarse.

## Revision de `.gitignore`

El `.gitignore` actual ya incluye:

- `.env`
- `dashboard/.streamlit/secrets.toml`
- `*.sql`
- `*.sql.gz`
- `*.dump`
- `__pycache__/`
- `*.pyc`
- `.venv/`
- `venv/`
- `.DS_Store`
- `*.log`

Recomendacion: agregar estas entradas faltantes:

```gitignore
__MACOSX/
.env
dashboard/.streamlit/secrets.toml
data_raw/
data_clean/
data_intermediate/
*.xlsx
*.xls
*.xlsm
*.csv
*.sql
*.sql.gz
*.dump
*.bak
*.zip
*.rar
*.7z
.venv/
.venv_local/
__pycache__/
*.pyc
```

Nota: `*.csv` debe evaluarse con cuidado porque `config/event_mapping.csv` y `config/file_formats.csv` si deben versionarse. Si se agrega `*.csv`, tambien hay que agregar excepciones:

```gitignore
!config/event_mapping.csv
!config/file_formats.csv
```

## Revision de `requirements.txt`

`requirements.txt` cubre el dashboard:

- `streamlit`
- `pandas`
- `numpy`
- `plotly`
- `SQLAlchemy`
- `PyMySQL`
- `cryptography`
- `python-dotenv`
- `pydeck`
- `certifi`

Para reproducir tambien scripts de pipeline historico convendria agregar:

- `openpyxl`
- `xlrd`

Riesgo de no agregarlos: el dashboard puede seguir funcionando, pero scripts que leen/generan Excel pueden fallar en entornos nuevos.

## Recomendacion final

1. Mantener intacta la estructura productiva: `dashboard/`, `scripts/`, `sql/`, `config/`, `docs/`, `requirements.txt`, `README.md`, `.env.example`, `.gitignore`.
2. Borrar solo artefactos evidentes de sistema/caches cuando se autorice: `dashboard/__MACOSX/`, `__pycache__/`, `*.pyc`.
3. Mover a `legacy/` los scripts sueltos de raiz del flujo anterior, no borrarlos inmediatamente.
4. Actualizar `.gitignore` antes de hacer nuevos commits para evitar datos, Excel, reportes intermedios y entornos virtuales.
5. Considerar agregar `openpyxl` y `xlrd` a `requirements.txt` si se quiere que el repo reproduzca tambien el pipeline completo, no solo el dashboard.
