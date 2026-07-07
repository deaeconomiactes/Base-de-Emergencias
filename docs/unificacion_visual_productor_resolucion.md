# Unificación visual por productor, año y resolución

Fecha: 2026-07-07

## 1. Objetivo

Redefinir la unidad de visualización del dashboard para que los usuarios operativos no naveguen principalmente por `origen_dato = actual / historico`, sino por las dimensiones institucionalmente relevantes:

- Productor.
- Año.
- Resolución, decreto o DTO.
- Fecha.
- Departamento y localidad.
- Actividad o rubro.
- DDJJ/declaración.

`origen_dato` debe conservarse como campo técnico de auditoría, trazabilidad y control de integración, pero no como categoría principal visible para usuarios finales.

Este documento es una guía de diseño metodológico y técnico. No modifica código, datos, TiDB, vistas SQL ni configuración de Streamlit Cloud.

## 2. Diagnóstico del esquema actual

El dashboard ya funciona con una capa unificada `vw_all_*`, pero esa capa fue diseñada inicialmente para integrar y auditar dos fuentes:

- Registros actuales del esquema operativo normalizado.
- Registros históricos armonizados desde Excel.

Por eso las vistas actuales preservan explícitamente `origen_dato` y generan claves separadas para la rama actual y la rama histórica.

### Vistas unificadas principales

| Vista | Uso actual | Observación metodológica |
|---|---|---|
| `vw_all_productores` | Productores actuales e históricos. | Contiene `productor_all_id`, `id_productor_actual`, `productor_hist_id`, `documento_nro`, `cuit_cuil`, `productor_nombre`, `origen_dato`. Hoy no consolida necesariamente actual + histórico de la misma persona. |
| `vw_all_ddjj_personas` | Declaraciones/DDJJ actuales e históricas. | Contiene `ddjj_all_id`, `id_ddjj_actual`, `ddjj_hist_id`, `productor_all_id`, `evento_id`, `dto`, `anio`, `fecha`, ubicación, actividad y flags. Puede tener filas de granularidad histórica más cercana a registro consolidado o detalle. |
| `vw_all_resoluciones` | Resoluciones actuales y eventos históricos. | Unifica `id_resolucion_actual` con `evento_id`. Para usuario final debe verse como resolución/decreto/DTO, no como fuente. |
| `vw_all_agricultura` | Registros agrícolas actuales e históricos. | Puede tener varias filas legítimas por cultivo, especie o categoría. No debe deduplicarse como DDJJ. |
| `vw_all_ganaderia_resumen` | Ganadería actual resumida e histórica. | Tiene existencias y mortandad, pero no siempre reproduce la granularidad bovina completa de las tablas actuales. |
| `vw_all_tipoactividad`, `vw_all_cultivos`, `vw_all_cultivostipo` | Catálogos combinados. | Útiles para filtros, pero no deben introducir `origen_dato` como categoría visible principal. |

### Tablas físicas actuales todavía usadas

| Tabla | Uso actual |
|---|---|
| `adremas` | Parcelas catastrales, superficie, tenencia, vínculo con DDJJ actual. |
| `establecimientos` | Establecimientos, paraje, coordenadas, mapa. |
| `ponderaciones_ddjj` | Ponderaciones por rubro en DDJJ actuales. |
| `perdidas_mejoras` | Mejoras declaradas en DDJJ actuales. |
| `documentacion` | Adjuntos administrativos de DDJJ actuales. |
| `fotos` | Adjuntos de imagen de DDJJ actuales. |
| `productores`, `ddjj_personas`, `resoluciones`, `agricultura`, `bovinos` | Base operativa normalizada usada por páginas no completamente migradas a vistas unificadas. |

## 3. Cambio metodológico propuesto

La vista operativa debe responder preguntas como:

- ¿Qué productor fue afectado?
- ¿En qué año y resolución/decreto?
- ¿Dónde declaró la afectación?
- ¿Qué actividad, cultivo o categoría productiva fue afectada?
- ¿Qué DDJJ o declaración respalda el dato?

No debe responder primero:

- ¿El dato viene de la rama actual o histórica?

Esa información sigue siendo necesaria, pero como auditoría.

## 4. Claves disponibles para consolidar productor

Las claves hoy disponibles son:

- `productor_all_id`
- `id_productor_actual`
- `productor_hist_id`
- `cuit_cuil`
- `documento_nro`
- `productor_nombre`
- `departamento`
- `localidad`
- `actividad`
- `origen_dato`

### Limitación de `productor_all_id`

`productor_all_id` es una clave técnica útil dentro de cada rama, pero no garantiza por sí sola que un productor actual y uno histórico queden fusionados como la misma persona. Actualmente se construye con prefijos o hashes que preservan origen.

Por lo tanto, para una visualización consolidada se recomienda introducir una clave conceptual nueva en una etapa posterior:

- `productor_visual_id`

Esa clave puede calcularse en SQL o en una vista auxiliar, sin reemplazar las claves técnicas existentes.

## 5. Regla conservadora de identidad de productor

La consolidación debe ser prudente. No conviene unir productores solo por nombre.

### Prioridad A: CUIT/CUIL normalizado exacto

Regla fuerte:

- Normalizar `cuit_cuil` dejando solo dígitos.
- Remover sufijo `.0`, puntos, guiones y espacios.
- Si dos registros tienen el mismo CUIT/CUIL normalizado válido, se consideran el mismo productor visual.

Uso recomendado:

- Unión automática fuerte.

### Prioridad B: Documento normalizado exacto

Regla fuerte con control:

- Normalizar `documento_nro` dejando solo dígitos.
- Remover `.0`, puntos, guiones y espacios.
- Si dos registros tienen el mismo documento normalizado válido, se consideran el mismo productor visual, salvo conflicto evidente de nombre.

Uso recomendado:

- Unión automática fuerte.
- Registrar posibles conflictos si el mismo documento aparece con nombres muy distintos.

### Prioridad C: CUIT/CUIL que contiene DNI + nombre compatible

Regla probable:

- Si un CUIT/CUIL contiene un DNI normalizado y el nombre es compatible, marcar como coincidencia probable.
- Ejemplo: un DNI aparece como `2793631` y un CUIT/CUIL como `27279363189`.

Uso recomendado:

- No fusionar automáticamente sin validación adicional.
- Mostrar como candidato de consolidación o usar en auditoría.

### Prioridad D: Nombre exacto + departamento + actividad

Regla débil:

- Nombre normalizado exacto.
- Departamento coincidente.
- Actividad coincidente o compatible.

Uso recomendado:

- Solo candidato de revisión.
- No unión automática fuerte, porque puede haber homónimos.

## 6. Clave visual de DDJJ/declaración

La tabla visible de DDJJ debe mostrar una fila por declaración operativamente distinguible.

Clave visual recomendada:

- Productor consolidado.
- Año.
- Resolución / DTO.
- Fecha.
- Departamento.
- Localidad.
- Actividad.
- Porcentaje de daño (`pondf` o equivalente).
- Superficie afectada, cuando exista.

`origen_dato`, `ddjj_all_id`, `id_ddjj_actual`, `ddjj_hist_id`, `source_file`, `source_sheet`, `dataset_role`, `relation_type` y flags deben quedar en auditoría.

### Criterio de deduplicación visual

Para tablas de DDJJ:

1. Construir una firma visual con los campos anteriores.
2. Si varias filas comparten esa firma, mostrar una sola fila.
3. Conservar la tabla original en campos técnicos/auditoría.
4. No aplicar esta deduplicación a agricultura ni ganadería, porque allí puede haber varias filas legítimas por cultivo, especie, categoría o rubro.

## 7. Propuesta para Ficha Productor

La página `Ficha Productor` debe ser la primera página en adoptar completamente esta lógica.

### Buscador

Debe buscar por:

- Nombre.
- CUIT/CUIL.
- Documento.

Para búsquedas numéricas:

- Priorizar documento exacto.
- Luego CUIT/CUIL exacto.
- Solo mostrar parciales si no hay exactas.

### Consolidación de productor

Cuando haya coincidencia fuerte:

- Mismo CUIT/CUIL normalizado, o
- Mismo documento normalizado sin conflicto de nombre.

La ficha debe mostrar una sola vista consolidada del productor, aunque existan registros actuales e históricos.

Si la coincidencia es probable o débil:

- Mostrar candidatos relacionados.
- No fusionar automáticamente.

### Tablas principales

No deben mostrar `origen_dato` como columna principal.

Tablas visibles:

- DDJJ por año/resolución.
- Agricultura por cultivo/año/resolución.
- Ganadería por categoría/año/resolución.
- Adremas/establecimientos solo cuando exista clave actual confiable.

Campos técnicos:

- `origen_dato`
- IDs técnicos.
- Archivos fuente.
- Flags.
- Rol de dataset.
- Tipo de relación.

Estos campos deben ir en expanders cerrados de auditoría.

## 8. Propuesta por página

### Home

Estado actual:

- Ya usa parcialmente `vw_all_ddjj_personas` y `vw_all_resoluciones` en modo unificado.
- Tiene filtro por `origen_dato`.

Propuesta:

- Quitar `origen_dato` como filtro principal visible o moverlo a “Filtros avanzados / auditoría”.
- KPIs deben contar productores y DDJJ visualmente consolidados.
- Gráficos principales por resolución, departamento y año deben basarse en dimensiones operativas.

Validación necesaria:

- Conteos antes/después de DDJJ únicas.
- Resoluciones/decretos con registros actuales e históricos asociados.

### Productores

Estado actual:

- Usa tablas actuales `productores`, `ddjj_personas` y catálogos operativos.

Propuesta:

- Migrar progresivamente a una vista o consulta de productores visualmente consolidados.
- Mostrar una fila por `productor_visual_id`.
- Ocultar `origen_dato`.
- Permitir abrir `Ficha Productor`.

No recomendado:

- Fusionar por nombre solamente.

### Detalle DDJJ

Estado actual:

- Está diseñado para `id_ddjj` actual.
- Usa muchas tablas actuales: ponderaciones, agricultura, bovinos, forestación, mejoras, adremas, documentación y fotos.

Propuesta:

- Mantenerlo como detalle técnico de DDJJ actual.
- Para históricos, crear en otra etapa un “Detalle declaración histórica” o una sección dentro de Ficha Productor.
- No forzar históricos dentro de `Detalle DDJJ` si no tienen las tablas auxiliares equivalentes.

### Adremas

Estado actual:

- Depende de `adremas`, `establecimientos`, `ddjj_personas`, `productores`.

Propuesta:

- Mantener como página de datos actuales/catastrales.
- Si se integra con Ficha Productor, hacerlo por `id_productor_actual` o `id_ddjj_actual`.
- No crear adremas históricas inferidas.

### Mapa

Estado actual:

- Depende de coordenadas de `establecimientos`.

Propuesta:

- Mantener mapa solo para registros con coordenadas confiables.
- No representar históricos sin coordenadas.
- En una etapa posterior, permitir que Ficha Productor muestre ubicación textual histórica.

### Análisis

Estado actual:

- Usa `vw_all_agricultura` y `vw_all_ganaderia_resumen`.
- Todavía puede filtrar por `origen_dato`.

Propuesta:

- Usar año, resolución/DTO, departamento, actividad y rubro como filtros principales.
- Mover `origen_dato` a filtro avanzado.
- Mantener tratamiento especial de categorías sin clasificar.
- Para rankings, usar DDJJ/productores visualmente consolidados cuando se calculen conteos.

## 9. Riesgos metodológicos

### Falsos positivos por nombre

Dos personas pueden compartir nombre y departamento.

Mitigación:

- Nombre + departamento + actividad solo como candidato.
- No unión automática fuerte.

### Documentos mal cargados

Puede haber documentos con:

- Ceros.
- Puntos.
- `.0`.
- Guiones.
- Dígitos faltantes.
- CUIT cargado como documento o viceversa.

Mitigación:

- Normalizar.
- Detectar documentos inválidos o de longitud atípica.
- Generar lista de conflictos.

### CUIT con formato inconsistente

Un CUIT puede aparecer con guiones, sin guiones, con espacios o como número decimal.

Mitigación:

- Normalizar a dígitos.
- Validar longitud esperada.

### Mismo productor con múltiples documentos

Puede ocurrir por errores administrativos o distintos representantes.

Mitigación:

- No fusionar automáticamente si hay documentos distintos y CUIT ausente.
- Marcar como posible duplicado para revisión.

### Mismo nombre para personas distintas

Riesgo alto en zonas rurales y apellidos frecuentes.

Mitigación:

- No fusionar por nombre solo.

### DDJJ duplicadas por registros de detalle

Una misma declaración puede aparecer repetida por cultivo, rubro o categoría.

Mitigación:

- Tabla DDJJ visible deduplicada por firma operativa.
- Detalles productivos en pestañas específicas.
- Tabla original en auditoría.

## 10. Validaciones recomendadas

Antes de implementar cambios globales, generar reportes con:

### Productores

- Total de filas en `vw_all_productores`.
- Productores únicos por CUIT normalizado.
- Productores únicos por documento normalizado.
- Productores con mismo documento y nombres distintos.
- Productores con mismo CUIT y nombres distintos.
- Productores sin documento ni CUIT.
- Candidatos por nombre + departamento + actividad.

### DDJJ

- Total de filas en `vw_all_ddjj_personas`.
- DDJJ únicas por firma visual.
- DDJJ únicas por `id_ddjj_actual`.
- DDJJ únicas por `ddjj_hist_id`.
- Casos donde una firma visual contiene múltiples IDs técnicos.
- Casos donde un ID técnico aparece en múltiples firmas visuales.

### Resoluciones/eventos

- Conteos por año y DTO antes/después.
- Eventos con registros actuales e históricos asociados.
- DTO con múltiples formatos equivalentes.

### Agricultura y ganadería

- Registros por DDJJ visual.
- Cultivos por DDJJ.
- Categorías ganaderas por DDJJ.
- Superficies o mortandad agregadas antes/después.

### Casos conflictivos para revisión manual

- Documento exacto con nombres incompatibles.
- CUIT exacto con nombres incompatibles.
- Nombre exacto + departamento con documentos distintos.
- DDJJ visual repetida con superficies diferentes.
- Registros con flags críticos.

## 11. Capa técnica recomendada

Para evitar repetir lógica en Streamlit, conviene crear en una etapa posterior vistas SQL auxiliares:

- `vw_visual_productores`
- `vw_visual_ddjj`
- `vw_visual_agricultura`
- `vw_visual_ganaderia`

Estas vistas no deberían reemplazar `vw_all_*`. Deben ser una capa de presentación operativa sobre ellas.

Campos sugeridos para `vw_visual_productores`:

- `productor_visual_id`
- `productor_nombre`
- `documento_norm`
- `cuit_norm`
- `documento_nro`
- `cuit_cuil`
- `departamento`
- `localidad`
- `actividad`
- `fuentes_origen` como lista técnica, no filtro principal.
- `confianza_union`: fuerte, probable, candidato, sin_unificar.

Campos sugeridos para `vw_visual_ddjj`:

- `ddjj_visual_id`
- `productor_visual_id`
- `anio`
- `dto`
- `fecha`
- `departamento`
- `localidad`
- `actividad`
- `pondf`
- `superficie_afectada`
- `ids_tecnicos_count`
- `origen_dato` solo para auditoría.

## 12. Plan de implementación progresiva

1. Documentar reglas de normalización de CUIT/DNI.
2. Crear reporte de conflictos de identidad de productor.
3. Crear `vw_visual_productores` y validar conteos.
4. Crear `vw_visual_ddjj` y validar duplicados visuales.
5. Adaptar `Ficha Productor` para usar productor visual consolidado.
6. Mover `origen_dato` a auditoría en Ficha Productor.
7. Adaptar Home a conteos visuales.
8. Adaptar Productores a `vw_visual_productores`.
9. Mantener Detalle DDJJ actual para datos operativos actuales.
10. Mantener Adremas y Mapa solo con datos actuales confiables.
11. Adaptar Análisis a filtros por año/resolución/departamento/actividad.
12. Validar con usuarios del área antes de eliminar o reubicar filtros técnicos.

## 13. Recomendación final

La integración histórica ya está técnicamente disponible, pero la experiencia operativa debe pasar de una lógica de fuente (`actual` / `historico`) a una lógica institucional:

- Productor consolidado.
- Año.
- Resolución / decreto / DTO.
- Declaración.
- Actividad o rubro.
- Territorio.

`origen_dato` debe seguir existiendo, pero como auditoría. La consolidación automática debe ser fuerte solo con CUIT/CUIL o documento normalizados exactos. Las coincidencias por nombre deben tratarse como candidatos de revisión, no como uniones definitivas.
