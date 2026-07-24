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

El estado operativo continúa siendo: **no apto para carga a TiDB hasta cerrar definiciones institucionales**.

## 3. Evidencia preparada para la reunión

| Extracto | Casos | Uso previsto |
| --- | ---: | --- |
| `review_mortandad_mayor_cantidad.csv` | 924 registros | Revisar la relación entre las variables cantidad y mortandad. |
| `review_superficies_negativas.csv` | 4 registros | Verificar valores de superficie con signo negativo. |
| `review_valores_ganaderos_negativos.csv` | 2 registros | Revisar una cantidad negativa y una mortandad negativa. |
| `review_adremas_duplicadas.csv` | 49 filas | Determinar si son duplicados reales o detalles válidos. |
| `review_ganaderia_huerfana.csv` | 1 registro | Resolver una clave ganadera sin trámite principal. |
| `review_certificados_nulos.csv` | 590 trámites | Definir si la ausencia es válida según estado y circuito. |
| `review_tramites_anulados_fuera_2023.csv` | 10 trámites | Definir reglas para anulados y período de presentación. |

Los conteos de registros de detalle no equivalen necesariamente a trámites únicos. Por ejemplo, los 924 registros con mortandad mayor que cantidad corresponden a 367 trámites; las cuatro filas con superficie negativa corresponden a tres trámites; y las 49 filas ADREMA marcadas corresponden a 20 trámites.

## 4. Tabla de decisiones pendientes

| Problema | Evidencia cuantitativa | Riesgo | Opciones de tratamiento | Decisión requerida | Responsable sugerido |
| --- | ---: | --- | --- | --- | --- |
| Significado de `cantidad` y `mortandad` | 924 registros; 367 trámites con mortandad mayor que cantidad | Clasificar como error una relación que podría responder a universos o períodos diferentes | Validar definiciones; segmentar por especie/categoría; documentar excepciones; corregir solo con respaldo | Definir semántica, período y regla de consistencia | Área técnica ganadera y responsable funcional de la DDJJ |
| Valores ganaderos negativos | 2 registros: una cantidad negativa y una mortandad negativa | Distorsión de totales y tasas | Corregir en origen; documentar como ajuste; excluir solo de métricas específicas | Determinar significado y tratamiento de cada caso | Área técnica ganadera y administración del sistema fuente |
| Superficies negativas | 4 registros; 3 trámites | Distorsión de superficies declaradas y afectadas | Confirmar contra fuente; corregir con evidencia; mantener y marcar; excluir de agregados definidos | Resolver cada registro y documentar criterio | Área agrícola/territorial y responsable de carga |
| ADREMAS duplicadas dentro del trámite | 49 filas; 20 trámites | Doble conteo de establecimientos o superficie | Conservar detalle; colapsar por clave compuesta; distinguir actividades/ubicaciones; marcar repetición | Definir unidad de observación y clave de unicidad | Catastro/área territorial y Economía Agraria |
| Registro ganadero huérfano | 1 registro | Pérdida de trazabilidad y ruptura de integridad referencial | Corregir `tramite_id`; vincular mediante evidencia; mantener en cuarentena; excluir con acta | Identificar el trámite correcto o documentar su exclusión | Administración del sistema fuente |
| Trámites anulados | 5 trámites | Incluir expedientes sin validez en indicadores vigentes | Excluir de indicadores; conservar en histórico; mostrar con estado separado | Definir alcance de cada producto analítico | Área legal/administrativa y responsable del Registro |
| Trámites fuera de 2023 | 5 trámites | Asignación temporal incorrecta por el nombre operativo de la fuente | Mantener por fecha real; excluir del corte 2023; reasignar al año correspondiente | Definir el universo temporal del conjunto “DDJJ 2023” | Economía Agraria y responsable funcional |
| Número de certificado ausente | 590 trámites | Confundir ausencia administrativa con falta de evento normativo | Mantener nulo; analizar por estado/tipo; completar solo desde fuente autorizada | Definir obligatoriedad y uso del campo | Área administrativa/certificaciones |
| Correspondencia normativa inexistente | No existe bridge DDJJ–evento | Asociar trámites a resoluciones o decretos incorrectos | Construir tabla externa validada; cruce asistido; revisión manual de excepciones | Aprobar fuente, clave y responsables del bridge | Área legal/normativa, Emergencia Agropecuaria y datos |

## 5. Criterios específicos a resolver

### 5.1. `Numero Certificado` no es resolución ni decreto

El campo `Numero Certificado` identifica un certificado dentro del circuito administrativo, pero no aporta por sí mismo evidencia suficiente para identificar una resolución, un decreto, un DTO o un evento de emergencia. No debe reutilizarse como clave normativa ni completarse a partir de semejanzas textuales.

La ausencia en 590 trámites tampoco demuestra que esos trámites carezcan de cobertura normativa. Debe evaluarse según el estado del trámite, el tipo de certificado y la documentación externa autorizada.

### 5.2. Bridge normativo DDJJ–evento

Antes de integrar la base se necesita una correspondencia externa y auditable entre `tramite_id` —o el atributo territorial/temporal que institucionalmente se apruebe— y el identificador de evento o norma del Registro. El bridge debería conservar, como mínimo, fuente de la correspondencia, norma, evento, vigencia, criterio de vinculación, responsable de validación y fecha de aprobación.

No debe construirse el bridge mediante una inferencia automática basada únicamente en `Numero Certificado`, fechas aproximadas o texto libre.

### 5.3. Mortandad mayor que cantidad

Hay 924 filas de detalle, correspondientes a 367 trámites, donde `mortandad > cantidad`. No se deben descartar ni corregir hasta confirmar si `cantidad` representa existencias iniciales, existencias al momento de la DDJJ, stock remanente, animales afectados u otra unidad. La comparación solo es un control válido si ambas variables comparten universo, categoría y período.

### 5.4. ADREMAS duplicadas

Se identificaron 49 filas marcadas como duplicadas dentro de 20 trámites. La coincidencia de `tramite_id + adrema` no prueba por sí sola una duplicación: puede haber actividades, ubicaciones o superficies declaradas en filas distintas. No se deben sumar, eliminar ni colapsar hasta definir la unidad de observación y la clave institucional.

### 5.5. Superficies negativas

Los cuatro registros deben cotejarse con el Excel y, si corresponde, con el sistema o expediente de origen. El valor cero no es un reemplazo neutral: cambiaría la declaración y podría alterar indicadores. La salida institucional debe documentar si cada caso es error de carga, ajuste administrativo o valor que requiere exclusión analítica.

### 5.6. Registro ganadero huérfano

Existe un registro cuyo `tramite_id` no aparece en la tabla principal. Debe permanecer en cuarentena lógica hasta identificar una clave válida o aprobar formalmente su exclusión. No corresponde vincularlo por nombre de productor ni por similitud sin evidencia adicional.

### 5.7. Trámites anulados y período 2023

Los cinco trámites anulados deben conservarse para trazabilidad, pero la institución debe definir si se excluyen de indicadores operativos y cómo se presentan históricamente. Los cinco trámites fuera de 2023 deben asignarse por su fecha real; el nombre de la carpeta o del proceso no reemplaza el criterio temporal.

El extracto combinado contiene diez trámites, lo que indica que, en esta versión, ambos grupos no se superponen.

### 5.8. Certificados nulos

Los 590 certificados nulos requieren una lectura por estado del trámite y tipo de certificado. La nulidad puede ser válida para trámites incompletos, anulados o circuitos sin emisión. No debe completarse automáticamente ni usarse para inferir falta de resolución.

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
2. Resolver y documentar la semántica de cantidad y mortandad.
3. Revisar las superficies y los valores negativos contra la fuente.
4. Definir la unidad y el tratamiento de las ADREMAS repetidas.
5. Resolver o documentar el registro ganadero huérfano.
6. Establecer reglas para anulados, fechas fuera de 2023 y certificados nulos.
7. Construir y aprobar el bridge normativo DDJJ–evento.
8. Recién después, diseñar una carga a staging; nunca cargar directamente a vistas finales.
9. Validar staging contra las tablas normalizadas y las decisiones aprobadas.
10. Evaluar luego la integración a vistas unificadas y dashboard.

## 8. Decisión de control vigente

> La base DDJJ 2023 Excel queda en estado normalizada-local-validada-con-advertencias. No debe integrarse al Registro unificado ni al dashboard hasta cerrar la correspondencia normativa y las definiciones institucionales de calidad.

