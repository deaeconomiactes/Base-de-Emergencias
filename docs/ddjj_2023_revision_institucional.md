# Guía para la revisión institucional de la base DDJJ 2023 Excel

## 1. Contexto y propósito

Este documento organiza las decisiones necesarias antes de incorporar al Registro unificado la fuente `Informes Tramites Emerg. Agrop - Actualizado 21052026.xlsx`. Aunque se la identifica operativamente como “DDJJ 2023”, la fecha del archivo es 21/05/2026 y la base contiene cinco trámites cuya fecha de presentación no corresponde a 2023. Por ello, el año no debe asumirse como criterio suficiente de inclusión.

La fuente se encuentra en estado **normalizada-local-validada-con-advertencias**. Se ejecutaron la auditoría, la transformación y la validación reproducibles, con resultado global `WARN`: 126 controles `PASS`, 6 `WARN` y 0 `FAIL`.

El paquete de revisión generado reúne casos para discusión; no corrige, elimina ni reemplaza información. Los CSV contienen datos personales y administrativos sensibles y deben mantenerse dentro del circuito institucional autorizado.

## 2. Alcance actual

Se preservó el Excel original y se generaron tablas normalizadas y extractos locales de revisión. Hasta este punto:

- no se cargaron datos a TiDB;
- no se modificó el dashboard;
- no se incorporó la fuente al Registro unificado;
- no se modificaron vistas SQL;
- no se corrigieron datos automáticamente;
- no se interpretaron identificadores administrativos como normativa.

El estado operativo continúa siendo: **no apto para carga a TiDB hasta construir y validar el bridge normativo y cerrar los demás pendientes técnicos vigentes**.

## 3. Evidencia preparada para la reunión

| Extracto | Casos | Uso previsto |
| --- | ---: | --- |
| `review_mortandad_mayor_cantidad.csv` | 924 registros | Revisar la relación entre las variables cantidad y mortandad. |
| `review_superficies_negativas.csv` | 4 registros | Verificar valores de superficie con signo negativo. |
| `review_valores_ganaderos_negativos.csv` | 2 registros | Revisar una cantidad negativa y una mortandad negativa. |
| `review_adremas_duplicadas.csv` | 49 filas | Aplicar el conteo por par único y revisar la aptitud para indicadores de superficie. |
| `review_ganaderia_huerfana.csv` | 1 registro | Resolver una clave ganadera sin trámite principal. |
| `review_certificados_nulos.csv` | 590 trámites | Documentar la alerta administrativa sin invalidar ni excluir la DDJJ. |
| `review_tramites_anulados_fuera_2023.csv` | 10 trámites | Aplicar exclusiones selectivas por vigencia administrativa y corte temporal. |

Los conteos de registros de detalle no equivalen necesariamente a trámites únicos. Por ejemplo, los 924 registros con mortandad mayor que cantidad corresponden a 367 trámites; las cuatro filas con superficie negativa corresponden a tres trámites; y las 49 filas ADREMA marcadas corresponden a 20 pares duplicados de `tramite_id + adrema`, con 29 filas excedentes respecto de contar una fila por par.

## 4. Tabla de decisiones y estado

| Problema | Evidencia cuantitativa | Riesgo | Opciones de tratamiento | Decisión requerida | Responsable sugerido |
| --- | ---: | --- | --- | --- | --- |
| Significado de `cantidad` y `mortandad` | 924 registros; 367 trámites con mortandad mayor que cantidad | Sobreestimar totales o calcular tasas inválidas si se usan registros inconsistentes | Conservar el original y excluir selectivamente de indicadores cuantitativos | **Resuelta metodológicamente:** `cantidad` es la existencia al denunciar la emergencia; falta implementar técnicamente la regla | Área técnica ganadera y equipo de datos |
| Valores ganaderos negativos | 2 registros: una cantidad negativa y una mortandad negativa | Distorsión de totales y tasas | Corregir en origen; documentar como ajuste; excluir solo de métricas específicas | Determinar significado y tratamiento de cada caso | Área técnica ganadera y administración del sistema fuente |
| Superficies negativas | 4 registros; 3 trámites | Distorsión de sumas, promedios e indicadores territoriales o productivos | Conservar el original y excluir selectivamente de indicadores cuantitativos de superficie | **Resuelta metodológicamente:** una superficie no puede ser negativa; falta implementar técnicamente la regla | Área agrícola/territorial y equipo de datos |
| ADREMAS duplicadas dentro del trámite | 49 filas; 20 pares duplicados; 29 filas excedentes | Doble conteo de establecimientos o superficie | Conservar originales; contar una vez cada par para establecimientos; no sumar superficies sin criterio | **Resuelta metodológicamente:** conservación y conteo único aprobados; falta implementar técnicamente la regla | Catastro/área territorial y equipo de datos |
| Registro ganadero huérfano | 1 registro | Pérdida de trazabilidad y ruptura de integridad referencial | Corregir `tramite_id`; vincular mediante evidencia; mantener en cuarentena; excluir con acta | Identificar el trámite correcto o documentar su exclusión | Administración del sistema fuente |
| Trámites anulados | 5 trámites | Incluir expedientes sin vigencia administrativa en indicadores operativos | Conservar para trazabilidad y excluir de indicadores sustantivos vigentes | **Resuelta metodológicamente:** exclusión selectiva aprobada; falta implementarla técnicamente | Área legal/administrativa y equipo de datos |
| Trámites fuera de 2023 | 5 trámites | Asignación temporal incorrecta por el nombre operativo de la fuente | Conservar por fecha real; excluir del corte 2023; admitir futura vista multianual | **Resuelta metodológicamente:** exclusión del corte 2023 aprobada; falta implementarla técnicamente | Economía Agraria y equipo de datos |
| Número de certificado ausente | 590 trámites | Invalidar DDJJ válidas o inferir normativa inexistente | Conservar, marcar y mantener en conteos generales; no inferir normativa | **Resuelta metodológicamente:** el nulo no invalida la DDJJ; falta construir el bridge externo | Área administrativa/certificaciones y equipo de datos |
| Correspondencia normativa inexistente | No existe `bridge_ddjj_evento_normativo` validado | Asociar trámites a resoluciones, decretos o eventos incorrectos | Construir tabla externa validada con fuentes normativas autorizadas | **Resuelta metodológicamente:** el bridge es obligatorio; persiste el bloqueo técnico hasta construirlo y validarlo | Área legal/normativa, Emergencia Agropecuaria y datos |

## 5. Criterios específicos y estado de decisión

### 5.1. `Numero Certificado` no es resolución ni decreto

**Estado de la decisión: resuelta metodológicamente; bridge normativo externo pendiente.**

El campo `Numero Certificado` identifica un dato administrativo dentro del circuito del trámite o certificado, pero no representa una resolución, un decreto, un DTO ni un evento de emergencia. No debe reutilizarse como clave normativa ni completarse a partir de semejanzas textuales.

La ausencia en **590 trámites** no invalida por sí misma la DDJJ ni demuestra que esos trámites carezcan de cobertura normativa. La correspondencia normativa debe provenir de una fuente externa autorizada.

### 5.2. Bridge normativo DDJJ–evento

**Estado de la decisión: resuelta metodológicamente; bloqueo técnico vigente por bridge pendiente.**

La base no contiene por sí sola una clave normativa confiable equivalente a decreto, resolución o evento de emergencia. Antes de integrarla se necesita una correspondencia externa y auditable, denominada `bridge_ddjj_evento_normativo` o equivalente, entre `tramite_id` y una identidad normativa validada.

No debe construirse el bridge mediante una inferencia automática basada únicamente en `Numero Certificado`, fechas aproximadas o texto libre.

Los campos mínimos propuestos son:

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

La asignación podrá sustentarse en decretos, resoluciones, períodos de emergencia, tipo de certificado, fechas desde/hasta y normativa administrativa validada. El criterio aplicado, su fuente y la persona responsable de validarlo deberán quedar registrados para cada vínculo.

Hasta construir y validar el bridge:

- no se cargará la base a TiDB;
- no se integrará a vistas unificadas;
- no se incorporará al dashboard productivo;
- permanecerá como fuente **normalizada-local-validada-con-advertencias**;
- no se diseñará ni ejecutará un script de carga.

Cuando el bridge esté aprobado, toda carga deberá realizarse primero a staging y nunca directamente a vistas finales.

### 5.3. Mortandad mayor que cantidad

**Estado de la decisión: resuelta metodológicamente; implementación técnica pendiente.**

La institución confirmó que `cantidad` representa la existencia ganadera declarada por el productor al momento de denunciar la emergencia. Por lo tanto, no es lógicamente válido que la mortandad declarada supere la cantidad existente.

Hay **924 registros de detalle**, correspondientes a **367 trámites**, donde `mortandad > cantidad`. Para estos casos se adopta la siguiente regla:

1. Conservar los registros y toda su trazabilidad.
2. No corregirlos automáticamente.
3. No eliminarlos de la fuente ni de las tablas normalizadas.
4. Mantener `dq_mortandad_mayor_cantidad = True`.
5. Excluirlos del total de cabezas declaradas válidas, total de mortandad válida, tasa de mortandad y pérdidas ganaderas cuantitativas.
6. Mantenerlos en los conteos de trámites/DDJJ, productores, presencia de actividad ganadera y controles de calidad.
7. Reportarlos como inconsistencia de calidad de datos.
8. Distinguir en toda futura carga a staging o vista analítica los registros ganaderos originales de los registros aptos para indicadores cuantitativos.

La exclusión es selectiva y analítica: no modifica el universo administrativo ni borra evidencia. Su implementación deberá realizarse en una futura etapa de transformación o vista analítica; no forma parte de la presente actualización documental.

### 5.4. ADREMAS duplicadas

**Estado de la decisión: resuelta metodológicamente; implementación técnica pendiente.**

Se identificaron **49 filas ADREMA**, correspondientes a **20 pares duplicados de `tramite_id + adrema`**. Hay **29 filas excedentes** respecto de contar una sola fila por cada par duplicado.

La repetición no debe eliminarse automáticamente, porque puede representar parcelas, actividades, secciones, superficies, pertenencias u otros detalles productivos diferentes. Tampoco debe sumarse sin control, porque podría producir sobreconteo de establecimientos o superficie.

Para estos casos se adopta la siguiente regla:

1. Conservar las filas y toda su trazabilidad.
2. No corregirlas automáticamente.
3. No eliminarlas de la fuente ni de las tablas normalizadas.
4. Mantener `dq_adrema_duplicada_en_tramite = True`.
5. Contar una sola vez cada par `tramite_id + adrema` para los indicadores de ADREMAS o establecimientos únicos.
6. No sumar automáticamente la superficie de las filas duplicadas hasta definir si representan parcelas, actividades o secciones distintas, repetición de carga u otra estructura válida.
7. Mantener los trámites y productores involucrados en los conteos generales.
8. Reportar los casos como alerta de calidad y de estructura relacional.
9. Distinguir en toda futura vista analítica los registros ADREMA originales, los pares `tramite_id + adrema` únicos y los registros aptos para indicadores de superficie.

La regla de conteo único aplica solamente al indicador de establecimientos y no autoriza a colapsar las filas originales. La implementación deberá realizarse en una futura transformación o vista analítica; no forma parte de la presente actualización documental.

### 5.5. Superficies negativas

**Estado de la decisión: resuelta metodológicamente; implementación técnica pendiente.**

Una superficie declarada no puede ser negativa. Los **4 valores negativos**, correspondientes a **3 trámites**, se consideran inconsistencias de calidad de datos.

Para estos casos se adopta la siguiente regla:

1. Conservar los registros y toda su trazabilidad.
2. No corregirlos automáticamente.
3. No eliminarlos de la fuente ni de las tablas normalizadas.
4. Mantener las banderas disponibles según la tabla: `dq_superficie_negativa`, `dq_superficie_afectada_negativa`, `dq_superficie_sembrada_negativa` u otras equivalentes.
5. Excluirlos de la superficie total declarada válida, superficie afectada válida, superficie sembrada válida y demás indicadores territoriales o productivos que sumen o promedien superficie.
6. Mantenerlos en los conteos de trámites/DDJJ, productores, presencia de actividad y controles de calidad.
7. Reportarlos como inconsistencias de calidad de datos.
8. Distinguir en toda futura carga a staging o vista analítica los registros originales de los registros aptos para indicadores cuantitativos de superficie.

El valor cero no es un reemplazo neutral y no debe imputarse automáticamente. La exclusión será únicamente selectiva y analítica. Su implementación deberá realizarse en una futura etapa de transformación o vista analítica; no forma parte de la presente actualización documental.

### 5.6. Registro ganadero huérfano

Existe un registro cuyo `tramite_id` no aparece en la tabla principal. Debe permanecer en cuarentena lógica hasta identificar una clave válida o aprobar formalmente su exclusión. No corresponde vincularlo por nombre de productor ni por similitud sin evidencia adicional.

### 5.7. Trámites anulados y período 2023

**Estado de ambas decisiones: resueltas metodológicamente; implementación técnica pendiente.**

El extracto combinado contiene **10 trámites**: **5 anulados** y **5 fuera de 2023**. En esta versión, ambos grupos no se superponen.

#### Trámites anulados

Un trámite con `Estado Actual = Anulado` no representa una DDJJ vigente para análisis operativo. Se conserva en la fuente y en las tablas normalizadas, con trazabilidad y con `dq_estado_anulado` o una bandera equivalente, pero se excluye de los indicadores principales de:

- DDJJ vigentes;
- productores vigentes;
- ADREMAS/establecimientos vigentes;
- superficie válida;
- agricultura válida;
- ganadería válida;
- indicadores productivos y territoriales principales.

El trámite permanece en auditoría, controles de calidad, reportes administrativos y trazabilidad histórica. Para productores vigentes, la exclusión afecta al aporte del trámite anulado; el productor puede permanecer si cuenta con otra DDJJ válida y no anulada.

#### Trámites fuera de 2023

La base se trata como fuente Excel DDJJ/trámites 2023, pero contiene fechas de presentación fuera de ese año y el nombre del archivo indica actualización **21/05/2026**. Los cinco trámites se conservan, mantienen su fecha real y se identifican mediante `dq_fecha_fuera_2023` o una bandera equivalente.

Se excluyen de los indicadores específicos de DDJJ 2023. Permanecen en auditoría, trazabilidad y controles de calidad, y podrían incorporarse a una futura vista multianual según `anio_presentacion` si ese uso se aprueba metodológicamente.

Ninguno de los dos grupos se elimina de los datasets fuente o normalizado. Las reglas deberán implementarse en una futura transformación o vista analítica; no forman parte de esta actualización documental.

### 5.8. Certificados nulos

Los **590 trámites** con `Numero Certificado` nulo se conservan con trazabilidad y no se corrigen ni eliminan de la fuente o de las tablas normalizadas. Se mantienen identificados mediante `dq_numero_certificado_nulo` o una bandera equivalente.

Estos trámites permanecen incluidos en los conteos generales de trámites/DDJJ, productores, ADREMAS/establecimientos, agricultura, ganadería y controles de calidad. El nulo se reporta como alerta administrativa o documental, pero no invalida la declaración.

`Numero Certificado` no debe usarse para crear ni inferir una resolución, un decreto o un evento. La vinculación normativa deberá resolverse mediante `bridge_ddjj_evento_normativo`, o equivalente, validado antes de cualquier carga a TiDB o integración al Registro unificado y al dashboard.

## 6. Propuesta de acuerdos para dejar asentados

La reunión debería producir un acta o matriz de decisión que, para cada alerta, consigne:

1. definición institucional de las variables involucradas;
2. regla de inclusión, exclusión o conservación;
3. responsable que valida la decisión;
4. fuente documental utilizada;
5. tratamiento en staging;
6. efecto esperado sobre conteos e indicadores;
7. fecha y versión de vigencia del criterio.

Las correcciones, si fueran aprobadas, deben implementarse en una capa reproducible posterior. El dato crudo y las tablas normalizadas actuales deben mantenerse inalterados para conservar trazabilidad.

## 7. Secuencia recomendada

1. Realizar la reunión institucional de definiciones.
2. Implementar en una futura transformación o vista analítica la regla ya aprobada para `mortandad > cantidad`, separando registros originales de registros aptos para indicadores cuantitativos.
3. Implementar en una futura transformación o vista analítica la regla ya aprobada para superficies negativas, separando registros originales de registros aptos para indicadores cuantitativos de superficie.
4. Revisar los valores negativos de cantidad y mortandad contra la fuente.
5. Implementar en una futura transformación o vista analítica la regla aprobada para ADREMAS duplicadas: preservar originales, contar pares únicos para establecimientos y no agregar superficies sin criterio institucional.
6. Resolver o documentar el registro ganadero huérfano.
7. Implementar en una futura transformación o vista analítica las reglas aprobadas para trámites anulados y fuera de 2023, preservando los originales y separando los universos válidos por estado y año.
8. Diseñar, construir y aprobar `bridge_ddjj_evento_normativo`, o equivalente, antes de crear cualquier script de carga.
9. Recién después, diseñar una carga a staging; nunca cargar directamente a vistas finales.
10. Validar staging contra las tablas normalizadas y las decisiones aprobadas.
11. Evaluar luego la integración a vistas unificadas y dashboard.

## 8. Decisión de control vigente

> La base DDJJ 2023 Excel queda en estado normalizada-local-validada-con-advertencias. No debe cargarse a TiDB ni integrarse al Registro unificado, las vistas unificadas o el dashboard hasta diseñar, construir y validar `bridge_ddjj_evento_normativo` y cerrar los demás pendientes técnicos vigentes.
