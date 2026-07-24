# Integración de la base DDJJ 2023 Excel

## Objetivo y alcance

Este documento consolida el estado técnico y metodológico de la incorporación local de la fuente:

`Informes Tramites Emerg. Agrop - Actualizado 21052026.xlsx`

La fecha incluida en el nombre del archivo corresponde al 21/05/2026 y no implica que el contenido esté compuesto exclusivamente por altas de 2023. El período efectivo debe interpretarse a partir de las fechas contenidas en los trámites.

La documentación se basa en los resultados reproducibles de auditoría, transformación y validación disponibles en `data_processed/ddjj_2023_excel/`. No autoriza una carga a TiDB ni una integración al dashboard.

## Estado actual de integración

- La fuente cruda está preservada en `data_raw/ddjj_2023_excel/original/` y no fue modificada por el pipeline local.
- La auditoría fue ejecutada mediante `scripts/13_audit_ddjj_2023_excel.py`.
- La transformación local fue ejecutada mediante `scripts/14_transform_ddjj_2023_excel.py`.
- La validación de las tablas normalizadas fue ejecutada mediante `scripts/15_validate_ddjj_2023_processed.py`.
- El estado global de validación es **WARN**.
- Se obtuvieron **126 checks PASS**.
- Se obtuvieron **6 checks WARN**.
- Se obtuvieron **0 checks FAIL**.
- Los conteos, claves, referencias y campos de trazabilidad requeridos superaron los controles técnicos implementados.
- No se modificó TiDB, ninguna vista SQL ni el dashboard.
- No se realizó carga, commit ni push como parte de estas etapas.

El estado `WARN` significa que la estructura normalizada es técnicamente consistente, pero todavía existen decisiones metodológicas e institucionales que impiden autorizar su integración operativa.

## Tablas normalizadas generadas

Las salidas están almacenadas bajo `data_processed/ddjj_2023_excel/normalized/`.

| Tabla | Filas | Unidad principal |
| --- | ---: | --- |
| `dim_productor_2023.csv` | 1.485 | Productor normalizado |
| `fact_ddjj_tramite_2023.csv` | 1.493 | Trámite/DDJJ |
| `fact_adrema_establecimiento_2023.csv` | 2.441 | Fila original de ADREMA/establecimiento |
| `fact_agricultura_perdida_2023.csv` | 195 | Fila original de pérdida agrícola |
| `fact_ganaderia_declarada_2023.csv` | 18.047 | Fila ganadera o de datos adicionales |
| `fact_manifestacion_existencias_2023.csv` | 917 | Existencia del último manifiesto |
| `fact_seguro_agricola_2023.csv` | 13 | Registro de seguro agrícola |
| `fact_calidad_dato_2023.csv` | 1.494 | Trámite o clave huérfana documentada |

La tabla de calidad tiene una fila más que la tabla principal porque conserva una clave ganadera huérfana para hacer visible la excepción, en lugar de descartarla.

## Resultados técnicos consolidados

- Trámites únicos: **1.493**.
- Productores únicos: **1.485**.
- Trámites anulados: **5**.
- Trámites fuera de 2023: **5**.
- Trámites sin ADREMA: **111**.
- Huérfanos ganaderos: **1**.
- Huérfanos en las demás tablas de detalle: **0**.
- Pares `tramite_id + adrema` duplicados: **20**.
- Filas pertenecientes a pares ADREMA duplicados: **49**.
- Valores de superficie negativos: **4**, correspondientes a **3 trámites**.
- Registros con cantidad ganadera negativa: **1**.
- Registros con mortandad negativa: **1**.
- Registros con mortandad mayor que cantidad: **924**, distribuidos en **367 trámites**.
- Trámites con número de certificado nulo: **590**.

Estas anomalías fueron preservadas y marcadas mediante banderas de calidad. No se eliminaron ni corrigieron registros automáticamente.

## Bloqueos metodológicos antes de carga

La carga y la integración permanecen bloqueadas hasta resolver o documentar formalmente los siguientes puntos:

1. Validar institucionalmente qué representan los campos `cantidad` y `mortandad` en cada hoja ganadera.
2. Resolver o documentar los **924 registros con mortandad mayor que cantidad**. No deben descartarse sin confirmar si `cantidad` representa existencia inicial, existencia remanente u otra unidad.
3. Revisar los **4 valores de superficie negativos** y definir si corresponden a errores de carga, convenciones administrativas o valores que requieren corrección en origen.
4. Revisar el **registro con cantidad ganadera negativa**.
5. Revisar el **registro con mortandad negativa**.
6. Resolver o documentar el **registro ganadero huérfano** cuyo `tramite_id` no existe en la hoja principal `Tramites`.
7. Definir el tratamiento de las **49 filas ADREMA duplicadas**. No deben colapsarse sin una regla institucional que considere la combinación `tramite_id + adrema` y la fila original.
8. No interpretar `Numero Certificado` como resolución, decreto, DTO ni evento normativo. El campo se conserva únicamente como identificador de certificado.
9. Construir una correspondencia normativa externa y trazable entre DDJJ, evento de emergencia y norma aplicable antes de generar un bridge.
10. Mantener bloqueada la carga a TiDB mientras estos puntos no cuenten con definición institucional y validación documentada.

## Decisión de control

> La base DDJJ 2023 Excel queda en estado normalizada-local-validada-con-advertencias. No debe integrarse al Registro unificado ni al dashboard hasta cerrar la correspondencia normativa y las definiciones institucionales de calidad.

Esta decisión implica que:

- los CSV normalizados son artefactos locales de trabajo y validación;
- el estado `WARN` no equivale a autorización de carga;
- no debe crearse todavía una vinculación normativa basada en inferencias;
- no debe ejecutarse ninguna carga directa a tablas o vistas finales;
- cualquier avance requiere aprobación explícita posterior.

## Próximos pasos recomendados

1. Realizar una reunión institucional para acordar definiciones, responsables y criterios de resolución.
2. Resolver o documentar la relación entre mortandad y cantidad, incluyendo los 924 casos observados.
3. Revisar las superficies negativas y los valores negativos de cantidad y mortandad.
4. Definir el tratamiento de las ADREMAS duplicadas sin perder trazabilidad.
5. Construir el bridge normativo DDJJ–evento utilizando una fuente externa autorizada y documentada.
6. Crear un eventual `scripts/16_*` solamente después de contar con aprobación institucional explícita.
7. Cargar primero a tablas de staging; nunca cargar directamente a vistas o tablas finales.
8. Validar staging contra las tablas normalizadas locales, conciliando filas, claves, nulos y banderas.
9. Recién después evaluar la integración en vistas unificadas y en el dashboard.

## Fuentes de control

- `data_processed/ddjj_2023_excel/audit/audit_ddjj_2023_resultados.md`
- `data_processed/ddjj_2023_excel/normalized/transform_ddjj_2023_resumen.md`
- `data_processed/ddjj_2023_excel/normalized/validation_ddjj_2023_resultados.md`
- `data_processed/ddjj_2023_excel/normalized/validation_ddjj_2023_checks.csv`

