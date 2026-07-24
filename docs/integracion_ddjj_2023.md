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

La base permanece en estado **normalizada-local-validada-con-advertencias**. El estado `WARN` significa que la estructura normalizada es técnicamente consistente, pero el bridge normativo y otros pendientes técnicos todavía impiden autorizar su integración operativa.

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
- Filas excedentes respecto de contar una sola fila por cada par duplicado: **29**.
- Valores de superficie negativos: **4**, correspondientes a **3 trámites**.
- Registros con cantidad ganadera negativa: **1**.
- Registros con mortandad negativa: **1**.
- Registros con mortandad mayor que cantidad: **924**, distribuidos en **367 trámites**.
- Trámites con número de certificado nulo: **590**.

Estas anomalías fueron preservadas y marcadas mediante banderas de calidad. No se eliminaron ni corrigieron registros automáticamente.

## Decisión metodológica sobre mortandad y cantidad ganadera

**Estado de la decisión: resuelta metodológicamente; implementación técnica pendiente.**

La institución confirmó que la variable `cantidad` representa la existencia ganadera declarada por el productor al momento de denunciar la emergencia. En consecuencia, no es lógicamente válido que la `mortandad` declarada sea mayor que esa existencia.

La inconsistencia afecta a **924 registros ganaderos**, correspondientes a **367 trámites**. Se adopta la siguiente regla:

1. Los registros con `mortandad > cantidad` se conservan con su trazabilidad completa.
2. No se corrigen automáticamente.
3. No se eliminan del dataset fuente ni del dataset normalizado.
4. Se mantienen identificados mediante `dq_mortandad_mayor_cantidad = True`.
5. Se excluyen de los indicadores ganaderos cuantitativos que dependan de cantidad o mortandad: total de cabezas declaradas válidas, total de mortandad válida, tasa de mortandad y pérdidas ganaderas cuantitativas.
6. No se excluyen de los conteos generales de trámites/DDJJ, productores, presencia de actividad ganadera ni controles de calidad.
7. Deben informarse como una inconsistencia de calidad de datos.
8. Toda futura carga a staging o vista analítica debe distinguir entre registros ganaderos originales y registros ganaderos aptos para indicadores cuantitativos.

Esta regla todavía no fue implementada en scripts, tablas, staging ni vistas. Su aplicación técnica deberá realizarse en una futura etapa reproducible de transformación o en una vista analítica, luego de la aprobación correspondiente y sin alterar la fuente ni los datos normalizados actuales.

## Decisión metodológica sobre superficies negativas

**Estado de la decisión: resuelta metodológicamente; implementación técnica pendiente.**

Una superficie declarada no puede ser negativa. Por lo tanto, los valores negativos de superficie se consideran inconsistencias de calidad de datos. Se identificaron **4 valores negativos**, correspondientes a **3 trámites**.

La regla adoptada es la siguiente:

1. Los registros con superficie negativa se conservan con su trazabilidad completa.
2. No se corrigen automáticamente.
3. No se eliminan del dataset fuente ni del dataset normalizado.
4. Se mantienen identificados mediante las banderas disponibles en cada tabla, como `dq_superficie_negativa`, `dq_superficie_afectada_negativa`, `dq_superficie_sembrada_negativa` u otras equivalentes.
5. Se excluyen de los indicadores cuantitativos que sumen o promedien superficie: superficie total declarada válida, superficie afectada válida, superficie sembrada válida e indicadores territoriales o productivos basados en superficie.
6. No se excluyen de los conteos generales de trámites/DDJJ, productores, presencia de actividad ni controles de calidad.
7. Deben informarse como inconsistencias de calidad de datos.
8. Toda futura carga a staging o vista analítica debe distinguir entre registros originales y registros aptos para indicadores cuantitativos de superficie.

La exclusión será selectiva y analítica. Esta regla todavía no fue implementada en scripts, tablas, staging ni vistas y deberá aplicarse en una futura etapa reproducible de transformación o en una vista analítica, sin alterar la fuente ni los datos normalizados actuales.

## Decisión metodológica sobre ADREMAS duplicadas

**Estado de la decisión: resuelta metodológicamente; implementación técnica pendiente.**

Se identificaron **49 filas ADREMA** asociadas a **20 pares duplicados de `tramite_id + adrema`**. Esto representa **29 filas excedentes** respecto de contar una sola fila por cada uno de esos pares. La repetición no se considera automáticamente un error, porque puede representar actividades, secciones, superficies, pertenencias, parcelas u otros detalles productivos distintos. Sin embargo, tampoco puede agregarse sin control, dado que podría generar sobreconteo de establecimientos o superficie.

La regla adoptada es la siguiente:

1. Las filas duplicadas por `tramite_id + adrema` se conservan con su trazabilidad completa.
2. No se corrigen automáticamente.
3. No se eliminan del dataset fuente ni del dataset normalizado.
4. Se mantienen identificadas mediante `dq_adrema_duplicada_en_tramite = True`.
5. Para contar ADREMAS o establecimientos únicos, se cuenta una sola vez cada par `tramite_id + adrema`.
6. Para indicadores de superficie, las filas duplicadas no se suman automáticamente hasta definir si representan parcelas distintas, actividades distintas, secciones distintas, repetición de carga u otra estructura válida.
7. Las duplicaciones no excluyen el trámite de los conteos generales de trámites/DDJJ ni de productores.
8. Deben reportarse como alerta de calidad y de estructura relacional.
9. Toda futura vista analítica debe distinguir entre registros ADREMA originales, pares `tramite_id + adrema` únicos y registros aptos para indicadores de superficie.

Esta regla todavía no fue implementada en scripts, tablas, staging ni vistas. Su aplicación técnica deberá realizarse en una futura transformación o vista analítica, sin alterar los registros originales ni las tablas normalizadas actuales.

## Decisión metodológica sobre `Numero Certificado` nulo

**Estado de la decisión: resuelta metodológicamente; bridge normativo externo pendiente.**

`Numero Certificado` es un dato administrativo del trámite o certificado. No representa una resolución, un decreto, un DTO ni un evento normativo. Su ausencia no invalida por sí misma la DDJJ o el trámite. Se identificaron **590 trámites** con este campo nulo.

La regla adoptada es la siguiente:

1. Los trámites con `Numero Certificado` nulo se conservan con su trazabilidad completa.
2. No se corrigen automáticamente.
3. No se eliminan del dataset fuente ni del dataset normalizado.
4. Se mantienen identificados mediante `dq_numero_certificado_nulo` o una bandera equivalente.
5. No se excluyen de los conteos generales de trámites/DDJJ, productores, ADREMAS/establecimientos, agricultura, ganadería ni controles de calidad.
6. El campo no se utiliza para crear ni inferir una resolución, un decreto o un evento normativo.
7. La ausencia se reporta como alerta administrativa o documental.
8. La vinculación normativa debe resolverse mediante una tabla externa `bridge_ddjj_evento_normativo`, o equivalente, validada antes de cualquier carga a TiDB o integración al Registro unificado y al dashboard.

La decisión sobre el tratamiento del valor nulo está cerrada. El pendiente técnico es construir y validar el bridge normativo externo; esta documentación no crea el bridge ni modifica datos, scripts, staging o vistas.

## Decisión metodológica sobre trámites anulados y fuera de 2023

**Estado de ambas decisiones: resueltas metodológicamente; implementación técnica pendiente.**

El extracto conjunto contiene **10 trámites**: **5 anulados** y **5 con fecha de presentación fuera de 2023**. En esta versión, ambos grupos no se superponen.

### Trámites anulados

Un trámite con `Estado Actual = Anulado` no representa administrativamente una DDJJ vigente para el análisis operativo.

1. Los trámites anulados se conservan con trazabilidad.
2. No se eliminan del dataset fuente ni del dataset normalizado.
3. Se mantienen identificados mediante `dq_estado_anulado` o una bandera equivalente.
4. Se excluyen de los indicadores principales de DDJJ vigentes, productores vigentes, ADREMAS/establecimientos vigentes, superficie válida, agricultura válida, ganadería válida e indicadores productivos y territoriales principales.
5. Permanecen en auditoría, controles de calidad, reportes administrativos y trazabilidad histórica.

La exclusión del indicador de productores vigentes se aplica al aporte del trámite anulado. Un productor puede continuar en ese universo si posee otra DDJJ no anulada que cumpla las reglas de inclusión.

### Trámites fuera de 2023

La fuente se trata operativamente como base Excel de DDJJ/trámites 2023, pero el nombre del archivo indica una actualización del **21/05/2026**. Por lo tanto, no debe asumirse que todo su contenido pertenece estrictamente a 2023.

1. Los trámites fuera de 2023 se conservan con trazabilidad.
2. No se eliminan del dataset fuente ni del dataset normalizado.
3. Se mantienen identificados mediante `dq_fecha_fuera_2023` o una bandera equivalente.
4. Se excluyen de los indicadores específicos de DDJJ 2023.
5. Podrán incorporarse a una futura vista multianual según `anio_presentacion`, si ese uso se aprueba metodológicamente.
6. Permanecen en auditoría, trazabilidad y controles de calidad.

Las exclusiones son selectivas y no modifican la fuente ni las tablas normalizadas. Su aplicación deberá implementarse en una futura transformación o vista analítica; no forma parte de esta actualización documental.

## Decisión metodológica sobre vinculación normativa

**Estado de la decisión: resuelta metodológicamente; bloqueo técnico vigente por bridge pendiente.**

La base DDJJ 2023 Excel no contiene por sí sola una clave normativa confiable equivalente a decreto, resolución o evento de emergencia. `Numero Certificado` es un dato administrativo y no debe utilizarse para inferir ninguna de esas identidades.

La regla adoptada es la siguiente:

1. La base no se integrará al Registro unificado sin una vinculación normativa externa validada.
2. No se utilizará `Numero Certificado` para inferir un evento normativo.
3. Se deberá construir una tabla puente externa denominada `bridge_ddjj_evento_normativo`, o equivalente.
4. La tabla puente vinculará `tramite_id` con una identidad normativa validada.
5. La vinculación podrá apoyarse en fuentes externas autorizadas: decreto, resolución, período de emergencia, tipo de certificado, fechas desde/hasta y normativa administrativa validada.
6. Hasta construir y validar el bridge, no se cargará la base a TiDB, no se integrará a vistas unificadas ni se incorporará al dashboard productivo.
7. Mientras tanto, la fuente permanecerá en estado **normalizada-local-validada-con-advertencias**.
8. Toda futura carga se realizará primero a staging y nunca directamente a vistas finales.

### Campos mínimos propuestos para `bridge_ddjj_evento_normativo`

- `tramite_id`
- `evento_id_normativo`
- `tipo_norma`
- `numero_norma`
- `anio_norma`
- `nombre_evento`
- `fecha_inicio_evento`
- `fecha_fin_evento`
- `criterio_asignacion`
- `fuente_normativa`
- `validado_por`
- `fecha_validacion`
- `observaciones`

La decisión conceptual está cerrada, pero el bridge aún no fue diseñado ni validado. Este bloqueo técnico debe resolverse antes de crear o ejecutar cualquier script de carga.

## Bloqueos metodológicos antes de carga

Las definiciones sobre `mortandad > cantidad`, superficies negativas, ADREMAS duplicadas, `Numero Certificado` nulo, trámites anulados y trámites fuera de 2023 ya no constituyen bloqueos metodológicos. La carga y la integración permanecen bloqueadas por los siguientes puntos todavía pendientes:

1. Revisar el **registro con cantidad ganadera negativa**.
2. Revisar el **registro con mortandad negativa**.
3. Resolver o documentar el **registro ganadero huérfano** cuyo `tramite_id` no existe en la hoja principal `Tramites`.
4. Diseñar, construir y validar la correspondencia normativa externa mediante `bridge_ddjj_evento_normativo`, o equivalente, antes de crear un script de carga.
5. Mantener bloqueada la carga a TiDB mientras estos puntos no cuenten con definición institucional y validación documentada.

## Decisión de control

> La base DDJJ 2023 Excel queda en estado normalizada-local-validada-con-advertencias. No debe cargarse a TiDB ni integrarse al Registro unificado, las vistas unificadas o el dashboard hasta diseñar, construir y validar `bridge_ddjj_evento_normativo` y cerrar los demás pendientes técnicos vigentes.

Esta decisión implica que:

- los CSV normalizados son artefactos locales de trabajo y validación;
- el estado `WARN` no equivale a autorización de carga;
- no debe crearse todavía una vinculación normativa basada en inferencias;
- no debe ejecutarse ninguna carga directa a tablas o vistas finales;
- cualquier avance requiere aprobación explícita posterior.

## Próximos pasos recomendados

1. Realizar una reunión institucional para acordar definiciones, responsables y criterios de resolución.
2. Implementar en una futura transformación o vista analítica la exclusión selectiva de los 924 registros con `mortandad > cantidad`, manteniendo el universo original y una separación explícita de los registros aptos para indicadores cuantitativos.
3. Implementar en una futura transformación o vista analítica la exclusión selectiva de los 4 valores de superficie negativos, separando registros originales de registros aptos para indicadores cuantitativos de superficie.
4. Revisar los valores negativos de cantidad y mortandad.
5. Implementar en una futura transformación o vista analítica la regla aprobada para ADREMAS duplicadas: preservar las filas originales, contar pares únicos para establecimientos y no agregar superficies duplicadas sin criterio institucional.
6. Implementar en una futura transformación o vista analítica las reglas aprobadas para trámites anulados y fuera de 2023, preservando el universo original y generando universos analíticos válidos según estado y `anio_presentacion`.
7. Diseñar, construir y validar `bridge_ddjj_evento_normativo`, o equivalente, utilizando una fuente externa autorizada y documentada.
8. Diseñar cualquier script de carga únicamente después de aprobar el bridge normativo.
9. Cargar primero a tablas de staging; nunca cargar directamente a vistas o tablas finales.
10. Validar staging contra las tablas normalizadas locales, conciliando filas, claves, nulos y banderas.
11. Recién después evaluar la integración en vistas unificadas y en el dashboard.

## Fuentes de control

- `data_processed/ddjj_2023_excel/audit/audit_ddjj_2023_resultados.md`
- `data_processed/ddjj_2023_excel/normalized/transform_ddjj_2023_resumen.md`
- `data_processed/ddjj_2023_excel/normalized/validation_ddjj_2023_resultados.md`
- `data_processed/ddjj_2023_excel/normalized/validation_ddjj_2023_checks.csv`
