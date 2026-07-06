# Estado final de integración histórica y dashboard unificado

Fecha: 2026-07-06

## 1. Objetivo del trabajo

Documentar el estado final del proyecto luego de integrar datos históricos agropecuarios con los datos actuales del dashboard, migrar la información a TiDB Cloud y dejar operativo el dashboard en Streamlit Cloud.

## 2. Estado actual del sistema

El sistema queda funcionando con:

- TiDB Cloud como base principal.
- Streamlit Cloud como capa de visualización.
- Dashboard desplegado correctamente.
- Datos actuales e históricos integrados mediante vistas unificadas.
- Repositorio GitHub limpio y orientado a producción.

## 3. Fuente de datos activa

La aplicación usa:

- `DATA_SOURCE = "tidb"`
- `DATA_MODE = "unificado"`
- Base: `emergencias`
- Motor: TiDB Cloud compatible con MySQL

`DATA_MODE = "unificado"` permite consultar vistas que combinan registros actuales e históricos cuando corresponde. Esta modalidad no reemplaza las tablas actuales originales, sino que usa una capa de vistas para ampliar la cobertura temporal y mantener trazabilidad del origen de los datos.

## 4. Componentes productivos del repositorio

La estructura productiva queda concentrada en:

- `dashboard/`: aplicación Streamlit.
- `scripts/`: scripts del pipeline histórico/unificado.
- `sql/`: vistas SQL históricas y unificadas.
- `config/`: archivos de configuración y mapeo no sensibles.
- `docs/`: documentación técnica y metodológica.
- `requirements.txt`: dependencias Python.
- `README.md`: guía principal del proyecto.
- `.env.example`: plantilla de variables de entorno.
- `.gitignore`: reglas para excluir datos, dumps, secrets y archivos temporales.
- `ANALISIS_BASE_DATOS.md`: documentación analítica previa.

## 5. Elementos excluidos del repositorio

Se removieron o excluyeron del repositorio:

- Archivos Excel de trabajo.
- Dumps SQL.
- Carpetas `__MACOSX`.
- Cachés Python.
- Entornos virtuales.
- Secrets reales.
- Archivos `.env`.
- Scripts legacy duplicados.
- Carpetas de carga puntual que no forman parte del pipeline productivo.

La limpieza del repositorio no modificó TiDB Cloud ni Streamlit Cloud Secrets.

## 6. Validaciones realizadas

Se verificó:

- Conexión correcta a TiDB Cloud.
- Funcionamiento del dashboard en Streamlit Cloud.
- KPIs principales visibles.
- Página de Análisis funcionando.
- Uso de vistas unificadas.
- Filtro por origen de datos.
- Corrección visual básica de gráficos.
- Limpieza del repositorio sin afectar el despliegue.

## 7. Consideraciones metodológicas

Los datos históricos no reemplazan a los datos actuales. Se combinan mediante vistas unificadas para ampliar el alcance temporal del dashboard y conservar compatibilidad con la estructura operativa existente.

Cuando aplica, se preserva el origen del dato mediante la variable `origen_dato`, distinguiendo entre registros actuales e históricos. Esto permite filtrar, comparar y auditar los resultados según su procedencia.

Las categorías sin clasificar, como cultivos sin dato específico, deben tratarse con cuidado metodológico. No representan cultivos reales y no deben dominar rankings por defecto. Pueden mostrarse como información de calidad o incluirse manualmente cuando el análisis lo requiera.

Las correcciones de calidad deben documentarse antes de modificar indicadores sustantivos. En particular, cualquier ajuste sobre superficies, existencias, mortandad, cultivos o actividades debe quedar trazado en `docs/` y validarse antes de afectar visualizaciones o resultados institucionales.

## 8. Cómo actualizar o mantener el sistema

Para mantener o actualizar el sistema:

1. No subir datos sensibles ni dumps al repositorio.
2. Usar `scripts/` y `sql/` para cambios de pipeline.
3. Probar primero localmente.
4. Validar contra TiDB.
5. Hacer commit con mensaje descriptivo.
6. Hacer push a `main` solo cuando Streamlit local funcione.
7. Reiniciar o redeployar Streamlit Cloud si corresponde.
8. Documentar cambios metodológicos en `docs/`.

## 9. Riesgos pendientes o mejoras futuras

Quedan como próximos puntos de mejora:

- Validación funcional con usuarios del área.
- Revisión metodológica de indicadores agrícolas y ganaderos.
- Mejoras visuales adicionales.
- Página "Acerca de los datos".
- Manual de actualización de nuevos históricos.
- Auditoría periódica de calidad de datos.

## 10. Estado final

Al cierre de esta integración, el proyecto queda operativo, desplegado, documentado y con una estructura de repositorio más limpia, preparada para mantenimiento y futuras ampliaciones.
