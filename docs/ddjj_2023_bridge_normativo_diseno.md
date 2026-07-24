# Diseño metodológico y técnico del bridge normativo DDJJ 2023

## 1. Estado y alcance

Este documento define el contrato metodológico y técnico para vincular la base DDJJ 2023 Excel con eventos, decretos, resoluciones u otras normas de emergencia validadas.

La decisión metodológica está resuelta: la vinculación normativa externa es obligatoria. El bloqueo técnico continúa vigente porque el bridge todavía no fue construido ni validado.

El presente diseño:

- no crea el bridge;
- no crea archivos CSV;
- no crea scripts;
- no modifica las tablas normalizadas;
- no carga datos a TiDB;
- no modifica vistas SQL ni el dashboard.

La base permanece en estado **normalizada-local-validada-con-advertencias**.

## 2. Insumos y universo de referencia

El diseño se apoya en:

- `docs/integracion_ddjj_2023.md`;
- `docs/ddjj_2023_revision_institucional.md`;
- `data_processed/ddjj_2023_excel/normalized/fact_ddjj_tramite_2023.csv`;
- `data_processed/ddjj_2023_excel/normalized/fact_calidad_dato_2023.csv`.

La tabla maestra es `fact_ddjj_tramite_2023.csv`, con **1.493 filas y 1.493 `tramite_id` únicos**. La unidad de referencia es un trámite/DDJJ.

`fact_calidad_dato_2023.csv` contiene 1.494 filas porque conserva una fila adicional asociada al detalle huérfano documentado. En consecuencia, la cobertura del bridge debe calcularse siempre desde la tabla maestra de trámites y no desde el total de la tabla de calidad.

Según las decisiones ya adoptadas, existen cinco trámites anulados y cinco fuera de 2023, sin superposición en la versión actual. Por lo tanto, el universo integrable preliminar sería de **1.483 trámites** si se aplicaran solamente esas dos exclusiones. Este valor deberá recalcularse en cada validación y no utilizarse como constante fija.

## 3. Objetivo del bridge

El objetivo de `bridge_ddjj_evento_normativo_2023` es vincular cada `tramite_id` integrable de la base DDJJ 2023 Excel con una identidad normativa validada y trazable.

El bridge debe permitir:

- comparar la fuente Excel con los históricos del Registro unificado;
- identificar el evento normativo aplicable a cada trámite;
- documentar la evidencia y el criterio de asignación;
- separar correspondencias confirmadas, pendientes y no integrables;
- impedir inferencias normativas no respaldadas;
- validar cobertura antes de diseñar una carga a staging.

## 4. Por qué es necesario

La base Excel no contiene una clave normativa confiable equivalente a decreto, resolución o evento de emergencia. `Numero Certificado` es un identificador administrativo del trámite o certificado y no constituye normativa.

Los campos `tipo_certificado`, `certificado_fecha_desde` y `certificado_fecha_hasta` pueden aportar evidencia auxiliar, pero no identifican por sí solos una norma. No deben utilizarse como única fuente para crear una correspondencia.

Sin un bridge validado:

- no hay comparabilidad normativa defendible con los registros históricos;
- un mismo trámite podría asociarse al evento incorrecto;
- se podrían mezclar vigencias, territorios o instrumentos diferentes;
- no debe cargarse la fuente a TiDB;
- no debe integrarse a vistas unificadas;
- no debe incorporarse al dashboard productivo.

## 5. Tabla propuesta

Nombre lógico:

`bridge_ddjj_evento_normativo_2023`

### 5.1. Grano

El grano esperado es una fila por vínculo validado entre `tramite_id` y `evento_id_normativo`.

La cardinalidad preferida es un evento principal por trámite. Si institucionalmente se aprueba que un trámite se vincule con más de un evento, cada vínculo ocupará una fila y deberá documentarse la multiplicidad, distinguiendo un único evento principal de los eventos complementarios.

### 5.2. Claves propuestas

- Clave referencial obligatoria: `tramite_id` → `fact_ddjj_tramite_2023.tramite_id`.
- Clave lógica del vínculo: `tramite_id + evento_id_normativo`.
- Regla de unicidad principal: como máximo un evento principal por `tramite_id`.
- No se permiten filas exactamente duplicadas.

### 5.3. Campos mínimos obligatorios

| Campo | Tipo lógico propuesto | Nulabilidad | Regla de uso |
| --- | --- | --- | --- |
| `tramite_id` | texto | No | Debe existir en la tabla maestra de trámites. |
| `evento_id_normativo` | texto | No para registros integrables | Identificador estable del evento normativo validado. |
| `tipo_norma` | categoría | No | Valor perteneciente al catálogo autorizado. |
| `numero_norma` | texto | No | Se conserva como texto para admitir formatos administrativos. |
| `anio_norma` | entero de cuatro dígitos | No | Año formal de la norma; no se infiere desde el trámite. |
| `nombre_evento` | texto | No | Denominación institucional del evento. |
| `fecha_inicio_evento` | fecha ISO `YYYY-MM-DD` | No para eventos con vigencia definida | Inicio normativo o administrativo validado. |
| `fecha_fin_evento` | fecha ISO `YYYY-MM-DD` | No para eventos con vigencia definida | Fin normativo o administrativo validado. |
| `criterio_asignacion` | categoría | No | Método aprobado utilizado para vincular el trámite. |
| `fuente_normativa` | texto | No | Referencia verificable a la fuente externa. |
| `validado_por` | texto o identificador institucional | No | Responsable que aprueba la correspondencia. |
| `fecha_validacion` | fecha ISO `YYYY-MM-DD` | No | Fecha de aprobación del vínculo. |
| `confianza_asignacion` | categoría | No | Grado de respaldo de la correspondencia. |
| `observaciones` | texto | Sí | Excepciones, multiplicidad y aclaraciones. |
| `origen_dato` | texto | No | Valor recomendado: `ddjj_2023_excel_bridge_normativo`. |
| `source_file_bridge` | texto | No | Archivo de trabajo del cual provino la fila del bridge. |

### 5.4. Extensiones técnicas recomendadas

Estos campos no sustituyen los mínimos, pero hacen controlable la multiplicidad y una eventual integración parcial:

| Campo | Uso propuesto |
| --- | --- |
| `es_evento_principal` | Booleano; exactamente un `True` por `tramite_id` cuando haya varios eventos. |
| `rol_evento` | Catálogo sugerido: `principal`, `complementario`. |
| `estado_vinculacion` | Catálogo sugerido: `validado`, `pendiente`, `no_integrable`. |
| `motivo_no_integrable` | Justificación explícita cuando el trámite no forme parte del universo de carga. |
| `evidencia_referencia` | URL, expediente, archivo, página o identificador que permita revisar la fuente. |

Si se habilita una relación uno-a-muchos, `es_evento_principal` o un mecanismo equivalente pasa a ser obligatorio.

## 6. Valores permitidos

### 6.1. `tipo_norma`

- `Decreto`
- `Resolución`
- `Disposición`
- `Otro`

`Otro` requiere aclaración en `observaciones`.

### 6.2. `confianza_asignacion`

- `alta`
- `media`
- `baja`
- `pendiente`

Solo una asignación con confianza `alta` o `media`, fuente verificable y validación institucional puede considerarse candidata a integración. Los valores `baja` y `pendiente` permanecen fuera del universo integrable hasta decisión expresa.

### 6.3. `criterio_asignacion`

- `coincidencia por período certificado`
- `coincidencia por tipo certificado`
- `correspondencia manual validada`
- `fuente administrativa externa`
- `otro`

La coincidencia por período o tipo de certificado es evidencia auxiliar y requiere confirmación contra una fuente normativa externa. Nunca debe transformarse por sí sola en una asignación automática.

## 7. Fuentes y jerarquía de evidencia

La vinculación puede basarse en:

- decreto oficial;
- resolución oficial;
- disposición oficial;
- período de emergencia validado;
- normativa administrativa validada;
- correspondencia manual aprobada con respaldo documental;
- tipo de certificado y fechas desde/hasta, únicamente como evidencia auxiliar.

Jerarquía recomendada:

1. texto oficial publicado o registro normativo institucional;
2. expediente o sistema administrativo autorizado;
3. correspondencia manual validada por el área competente;
4. atributos del certificado como apoyo, nunca como fuente normativa directa.

`Numero Certificado` no es una fuente normativa directa y no debe utilizarse para completar `tipo_norma`, `numero_norma`, `anio_norma` o `evento_id_normativo`.

## 8. Reglas de calidad del bridge

### 8.1. Integridad referencial

- Todo `tramite_id` del bridge debe existir en `fact_ddjj_tramite_2023.csv`.
- Los trámites de la tabla maestra sin bridge deben clasificarse como pendientes o no integrables; no deben desaparecer del denominador sin explicación.
- La fila huérfana de `fact_calidad_dato_2023.csv` no debe incorporarse al bridge mientras no exista un trámite principal válido.

### 8.2. Completitud crítica

Para registros integrables no pueden ser nulos:

- `tramite_id`;
- `evento_id_normativo`;
- `tipo_norma`;
- `numero_norma`;
- `anio_norma`;
- `nombre_evento`;
- `criterio_asignacion`;
- `fuente_normativa`;
- `validado_por`;
- `fecha_validacion`;
- `confianza_asignacion`;
- `origen_dato`;
- `source_file_bridge`.

Las fechas de inicio y fin solo pueden ser nulas cuando la fuente normativa no defina vigencia y esa excepción esté documentada en `observaciones`.

### 8.3. Validez

- `tipo_norma`, `criterio_asignacion` y `confianza_asignacion` deben pertenecer a sus catálogos.
- `anio_norma` debe tener cuatro dígitos y ser coherente con la fuente normativa.
- `fecha_inicio_evento`, `fecha_fin_evento` y `fecha_validacion` deben ser parseables en formato ISO.
- Cuando existan ambas fechas del evento, `fecha_inicio_evento <= fecha_fin_evento`.
- `fecha_validacion` no puede ser posterior a la fecha de ejecución de la validación.
- Los identificadores y textos críticos no pueden contener solamente espacios ni valores centinela como `N/A`, `s/d` o `pendiente` fuera de los campos donde ese valor esté autorizado.

### 8.4. Unicidad y multiplicidad

- No debe repetirse la combinación `tramite_id + evento_id_normativo`.
- No debe existir más de un evento principal por `tramite_id`.
- Si un trámite tiene varios eventos, la multiplicidad debe estar permitida por una regla institucional explícita.
- Cada vínculo adicional debe indicar su rol y explicar el criterio en `observaciones`.
- Una relación uno-a-muchos no debe multiplicar hechos productivos al unir el bridge con tablas de detalle. Las vistas deberán controlar el grano antes de agregar cantidades o superficies.

### 8.5. Trazabilidad y evidencia

- `fuente_normativa` debe identificar una fuente revisable y no limitarse a una descripción genérica.
- `validado_por` y `fecha_validacion` deben permitir auditar la aprobación.
- `criterio_asignacion` debe describir el mecanismo real utilizado.
- `source_file_bridge` debe conservar el nombre del archivo de trabajo.
- `Numero Certificado` no puede registrarse como única evidencia normativa.

## 9. Plantilla local propuesta, no creada

Ruta prevista:

`data_processed/ddjj_2023_excel/bridge/bridge_ddjj_evento_normativo_2023_template.csv`

La plantilla **no se crea en esta etapa**. Su encabezado mínimo propuesto, en orden, es:

```text
tramite_id,evento_id_normativo,tipo_norma,numero_norma,anio_norma,nombre_evento,fecha_inicio_evento,fecha_fin_evento,criterio_asignacion,fuente_normativa,validado_por,fecha_validacion,confianza_asignacion,observaciones,origen_dato,source_file_bridge
```

Antes de materializarla se debe decidir si se incorporan las extensiones `es_evento_principal`, `rol_evento`, `estado_vinculacion`, `motivo_no_integrable` y `evidencia_referencia`.

La plantilla será un artefacto local de trabajo. No deberá contener fórmulas, filas precargadas por inferencia ni información normativa no validada.

## 10. Futuro script 17, no creado

Nombre propuesto:

`scripts/17_validate_ddjj_2023_bridge_normativo.py`

El script **no se crea en esta etapa**. Deberá ser de solo lectura respecto del bridge y de las tablas normalizadas, usar rutas relativas al repositorio y generar un reporte de validación reproducible.

### 10.1. Validaciones mínimas

1. Existencia y lectura del archivo bridge.
2. Presencia exacta de las columnas obligatorias.
3. Integridad referencial de `tramite_id` contra `fact_ddjj_tramite_2023.csv`.
4. Detección de filas y pares exactamente duplicados.
5. Duplicados o multiplicidad por `tramite_id`.
6. Verificación de un máximo de un evento principal por trámite.
7. Nulos y valores vacíos en campos críticos.
8. Catálogos permitidos para tipo, criterio y confianza.
9. Parseo y coherencia de fechas.
10. Casos con `confianza_asignacion = pendiente` o `baja`.
11. Eventos sin `fuente_normativa` revisable.
12. Uso indebido de `Numero Certificado` como fuente normativa directa.
13. Consistencia de `origen_dato` y `source_file_bridge`.
14. Resumen de cobertura sobre el universo maestro e integrable.

### 10.2. Métricas de cobertura

El reporte deberá incluir, como mínimo:

- trámites totales en la tabla maestra;
- trámites integrables según las reglas vigentes;
- trámites con al menos un vínculo;
- trámites con vínculo validado;
- trámites pendientes;
- trámites documentados como no integrables;
- trámites del bridge huérfanos;
- trámites con más de un evento;
- trámites con más de un evento principal;
- cobertura bruta: trámites con vínculo / trámites integrables;
- cobertura validada: trámites con vínculo validado / trámites integrables.

Los denominadores deben partir de los 1.493 trámites de `fact_ddjj_tramite_2023.csv` y aplicar exclusiones documentadas. No debe utilizarse el total de 1.494 filas de `fact_calidad_dato_2023.csv` como universo de trámites.

### 10.3. Resultado sugerido del script

- `PASS`: cobertura exigida alcanzada, sin errores de integridad, completitud, validez o multiplicidad.
- `WARN`: bridge estructuralmente válido, pero con vínculos no integrables por confianza pendiente/baja o excepciones documentadas; no habilita por sí solo la carga.
- `FAIL`: archivo o columnas faltantes, huérfanos, nulos críticos en registros integrables, fechas inválidas, fuentes ausentes, duplicados incompatibles, más de un evento principal o cobertura inferior al criterio aprobado.

## 11. Criterio de desbloqueo

El diseño de una carga a staging solo podrá comenzar cuando se cumpla una de estas condiciones:

1. **Cobertura completa:** el 100% de los trámites integrables tiene al menos un vínculo normativo validado, con fuente, criterio, responsable y fecha de validación; o
2. **Integración parcial aprobada:** existe una regla institucional escrita que define un subconjunto integrable, su denominador, criterios de inclusión y exclusión, responsable de aprobación y tratamiento de los trámites pendientes.

Una integración parcial no puede consistir simplemente en cargar los trámites que lograron emparejarse. Debe evitar sesgo de selección y permitir reproducir exactamente por qué cada trámite quedó incluido, pendiente o no integrable.

Aunque se alcance el criterio de cobertura:

- el bridge debe superar el futuro script 17;
- debe existir aprobación institucional de la correspondencia;
- la primera carga debe dirigirse a staging;
- staging debe validarse contra las tablas normalizadas y el bridge;
- no se habilita una carga directa a vistas finales ni al dashboard.

## 12. Riesgos metodológicos

| Riesgo | Consecuencia | Control propuesto |
| --- | --- | --- |
| Usar `Numero Certificado` como norma | Asignación de eventos falsos | Prohibición explícita y validación de fuente externa. |
| Emparejar solo por fechas | Confusión entre eventos superpuestos | Exigir evidencia normativa adicional y validación institucional. |
| Uno-a-muchos sin control | Duplicación de trámites, cabezas o superficies | Clave compuesta, evento principal y control del grano en vistas. |
| Bridge incompleto | Sesgo en el subconjunto integrado | Medir cobertura y aprobar formalmente cualquier integración parcial. |
| Fuente no revisable | Pérdida de trazabilidad | `fuente_normativa`, evidencia y responsable obligatorios. |
| Cambios posteriores de normativa | Inconsistencia histórica | Versionar archivo, validación y criterio; no sobrescribir evidencia previa. |
| Datos personales en archivos de revisión | Exposición innecesaria | Acceso restringido y reportes agregados cuando no se requiera identificación. |

## 13. Responsabilidades sugeridas

- Área legal o normativa: validar tipo, número, año y vigencia de la norma.
- Área de Emergencia Agropecuaria: validar la correspondencia sustantiva entre trámite y evento.
- Administración del sistema fuente: aportar evidencia del circuito administrativo.
- Economía Agraria/equipo de datos: controlar integridad, cobertura, trazabilidad y grano.
- Responsable designado: completar `validado_por`, `fecha_validacion` y aprobar excepciones.

La aprobación normativa y la validación técnica son controles complementarios; ninguna reemplaza a la otra.

## 14. Próximos pasos recomendados

1. Designar responsables normativos, funcionales y técnicos.
2. Acordar la identidad y el catálogo maestro de `evento_id_normativo`.
3. Confirmar los campos adicionales necesarios para multiplicidad e integración parcial.
4. Identificar y reunir las fuentes normativas externas autorizadas.
5. Aprobar formalmente este diseño.
6. Crear recién entonces la plantilla local del bridge.
7. Completar la correspondencia sin inferencias automáticas desde `Numero Certificado`.
8. Revisar manualmente asignaciones de confianza media, baja o pendiente.
9. Crear el script 17 solamente después de aprobar la estructura final.
10. Validar integridad, cobertura y trazabilidad del bridge.
11. Evaluar el criterio de desbloqueo.
12. Diseñar posteriormente una carga a staging, nunca directa a vistas finales.

