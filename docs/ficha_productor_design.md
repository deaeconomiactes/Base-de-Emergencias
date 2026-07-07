# Diseno de pagina Ficha Productor

Fecha: 2026-07-07

## 1. Objetivo

Evaluar la factibilidad de crear una pagina `Ficha Productor` que concentre en una sola vista la informacion disponible para un productor unico, reduciendo solapamientos entre las paginas actuales de `Productores`, `Detalle DDJJ`, `Adremas`, `Mapa` y `Analisis`.

La propuesta es metodologica y tecnica. No modifica codigo, datos, TiDB ni configuracion de Streamlit Cloud.

## 2. Factibilidad

La pagina es factible, con alcance diferenciado por origen de dato:

- Para datos actuales, la factibilidad es alta porque existe un esquema relacional operativo con `ProductorId`, `id_ddjj`, adremas, establecimientos, documentacion y tablas productivas por rubro.
- Para datos historicos, la factibilidad es media-alta para resumen de productor, DDJJ/eventos, agricultura, ganaderia y alertas de calidad, usando `vw_all_productores`, `vw_all_ddjj_personas`, `vw_all_agricultura` y `vw_all_ganaderia_resumen`.
- Para mapa, adremas, establecimientos y documentacion historica, la factibilidad es baja en esta etapa porque los historicos no tienen estructura catastral/geografica completa ni adjuntos administrativos equivalentes.

La recomendacion es construir la ficha como una pagina integradora con secciones que usen datos unificados cuando hay equivalencia metodologica, y datos actuales cuando la informacion historica no existe o no es comparable.

## 3. Tablas y vistas necesarias

### Productor

- Actual: `productores`
- Unificado: `vw_all_productores`

Uso esperado:

- Busqueda por nombre, CUIT/CUIL o documento.
- Identificacion del productor.
- Actividad principal.
- Departamento/localidad/paraje cuando existan.
- `origen_dato` para distinguir registros actuales e historicos.

Columnas relevantes:

- `ProductorId`
- `id_productor_actual`
- `productor_hist_id`
- `productor_all_id`
- `ProductorDenominacion`
- `productor_nombre`
- `CUITCUIL`
- `cuit_cuil`
- `DocumentoNro`
- `documento_nro`
- `actividad`
- `departamento`
- `localidad`
- `paraje`
- `source_file`
- `severidad_maxima`
- `origen_dato`

### DDJJ y declaraciones

- Actual: `ddjj_personas`
- Unificado: `vw_all_ddjj_personas`

Uso esperado:

- DDJJ asociadas al productor.
- Eventos/resoluciones asociados.
- Fecha, anio, departamento, localidad, paraje.
- Porcentaje de afectacion o `pondf`.
- Flags de calidad historicos.

Columnas relevantes:

- `id_ddjj`
- `id_ddjj_actual`
- `ddjj_hist_id`
- `ddjj_all_id`
- `id_productor`
- `id_productor_actual`
- `productor_hist_id`
- `productor_all_id`
- `id_resolucion`
- `id_resolucion_actual`
- `evento_id`
- `anio`
- `fecha`
- `dto`
- `periodo`
- `pondf`
- `departamento`
- `localidad`
- `paraje`
- `source_file`
- `source_sheet`
- `dataset_role`
- `relation_type`
- `origen_dato`
- `flag_revision_manual`
- `severidad_maxima`

### Resoluciones y eventos

- Actual: `resoluciones`
- Unificado: `vw_all_resoluciones`

Uso esperado:

- Lista de resoluciones/decretos/eventos en los que aparece el productor.
- Conteo de DDJJ por evento.
- Rango temporal.

Columnas relevantes:

- `id_resolucion`
- `id_resolucion_actual`
- `resolucion_all_id`
- `evento_id`
- `anio`
- `dto`
- `numero_resolucion`
- `nombre_resolucion`
- `fec_res`
- `source_file`
- `registros`
- `productores`
- `severidad_maxima`
- `origen_dato`

### Agricultura

- Actual: `agricultura`
- Unificado: `vw_all_agricultura`

Uso esperado:

- Superficie sembrada/uso y afectada por cultivo.
- Produccion estimada y obtenida.
- Porcentaje afectado.
- Trazabilidad historica por evento y archivo.

Columnas relevantes:

- `id_agricultura`
- `id_agricultura_actual`
- `agricultura_hist_id`
- `agricultura_all_id`
- `id_ddjj_actual`
- `ddjj_hist_id`
- `evento_id`
- `anio`
- `dto`
- `source_file`
- `source_sheet`
- `iddj`
- `codigo`
- `solicitud_id`
- `productor_nombre`
- `documento_nro`
- `departamento`
- `actividad`
- `cultivo`
- `especie`
- `categoria`
- `superficie_sembrada_uso`
- `superficie_afectada`
- `produccion_estimada`
- `produccion_obtenida`
- `porcentaje_afectacion`
- `flag_agricola_afectada_mayor_uso`
- `flag_superficie_total_menor_afectadas`
- `flag_revision_manual`
- `severidad_maxima`
- `origen_dato`

### Ganaderia

- Actual: `bovinos` y otras tablas ganaderas especificas.
- Unificado: `vw_all_ganaderia_resumen`.

Uso esperado:

- Existencias.
- Mortandad.
- Tasa de mortandad.
- Superficie ganadera de uso y afectada cuando exista.
- Alertas criticas por `mortandad > existencias`.

Columnas relevantes:

- `ganaderia_all_id`
- `ganaderia_hist_id`
- `id_ddjj_actual`
- `ddjj_hist_id`
- `evento_id`
- `anio`
- `dto`
- `source_file`
- `source_sheet`
- `iddj`
- `codigo`
- `solicitud_id`
- `productor_nombre`
- `documento_nro`
- `departamento`
- `actividad`
- `especie`
- `categoria`
- `superficie_total`
- `superficie_ganadera_uso`
- `superficie_ganadera_afectada`
- `existencias`
- `mortandad`
- `porcentaje_afectacion_ganadera`
- `flag_ganadera_afectada_mayor_uso`
- `flag_mortandad_mayor_existencias`
- `flag_superficie_total_menor_afectadas`
- `flag_revision_manual`
- `severidad_maxima`
- `origen_dato`

### Adremas y establecimientos

- Actual: `adremas`, `establecimientos`.
- Historico: sin equivalente completo en esta etapa.

Uso recomendado:

- Mostrar adremas y establecimientos solo para DDJJ actuales.
- No inferir adremas historicas desde nombre, paraje o localidad.
- No forzar mapa historico sin coordenadas validas.

Claves actuales:

- `adremas.ddjj` -> `ddjj_personas.id_ddjj`
- `adremas.id_establecimiento` -> `establecimientos.id_establecimiento`
- `establecimientos.ddjj` -> `ddjj_personas.id_ddjj`

### Ponderaciones, mejoras y documentacion

- Actual: `ponderaciones_ddjj`, `perdidas_mejoras`, `documentacion`, `fotos`.
- Historico: sin equivalente completo en esta etapa.

Uso recomendado:

- Mostrar estas secciones para datos actuales.
- Para historicos, mostrar una nota de no disponibilidad si el productor seleccionado solo tiene registros historicos.

Claves actuales:

- `ponderaciones_ddjj.id_ddjj` -> `ddjj_personas.id_ddjj`
- `perdidas_mejoras.idddjj` -> `ddjj_personas.id_ddjj`
- `documentacion.idddjj` -> `ddjj_personas.id_ddjj`
- `fotos.iddjj` -> `ddjj_personas.id_ddjj`

## 4. Claves de union disponibles

### Claves recomendadas para la ficha

La clave principal recomendada para navegar la pagina es:

- `productor_all_id`

Motivo: existe tanto para productores actuales como historicos en `vw_all_productores` y se replica en `vw_all_ddjj_personas`.

Para la busqueda, usar:

- `productor_nombre`
- `cuit_cuil`
- `documento_nro`
- `origen_dato`

Para detalles actuales, conservar:

- `id_productor_actual`
- `id_ddjj_actual`

Para detalles historicos, conservar:

- `productor_hist_id`
- `ddjj_hist_id`
- `evento_id`
- `iddj`
- `codigo`
- `solicitud_id`

### Tabla de equivalencias

| Concepto | Actual | Historico | Unificado recomendado |
|---|---|---|---|
| Productor | `ProductorId` | `productor_hist_id` | `productor_all_id` |
| DDJJ/declaracion | `id_ddjj` | `ddjj_hist_id` | `ddjj_all_id` |
| Resolucion/evento | `id_resolucion` | `evento_id` | `resolucion_all_id` |
| Documento | `DocumentoNro` | `documento_nro` | `documento_nro` |
| CUIT/CUIL | `CUITCUIL` | `cuit_cuil` | `cuit_cuil` |
| Origen | tabla operativa | staging/vista historica | `origen_dato` |
| Adrema | `adrema` | no disponible completo | actual solamente |
| Establecimiento | `id_establecimiento` | no disponible completo | actual solamente |

## 5. Riesgos de duplicacion

### Productores

Riesgo: un mismo productor puede aparecer con diferencias de nombre, DNI, CUIT/CUIL o formato documental entre datos actuales e historicos.

Mitigacion:

- Usar `productor_all_id` para navegacion tecnica.
- Mostrar coincidencias potenciales por documento/CUIT como advertencia, no fusionarlas automaticamente.
- Permitir que la ficha muestre grupos separados por `origen_dato` si no hay clave documental confiable.

### DDJJ historicas

Riesgo: en historicos, `codigo`, `IDDJ` y `solicitud_id` pueden representar identificadores equivalentes segun archivo, pero no siempre estan completos.

Mitigacion:

- Usar `ddjj_all_id` como clave tecnica.
- Mostrar `codigo`, `iddj` y `solicitud_id` como trazabilidad.
- No usar solo `documento_nro + nombre` para deduplicar en pantalla si existe `codigo` o `iddj`.

### Agricultura y ganaderia

Riesgo: mezclar detalle actual por rubro con resumen historico puede inducir a interpretar niveles de granularidad distintos como equivalentes.

Mitigacion:

- Mostrar `origen_dato`, `dataset_role` y `relation_type`.
- Separar visualmente agricultura y ganaderia.
- Mantener notas metodologicas para registros historicos.

### Adremas y mapa

Riesgo: atribuir ubicacion historica sin coordenadas o adremas completas.

Mitigacion:

- Limitar mapa/adremas a datos actuales.
- Para historicos, mostrar ubicacion declarada textual: departamento, localidad, paraje y seccion.

## 6. Diseno recomendado de la pagina

### Sidebar o bloque superior de busqueda

Controles:

- Buscador por nombre, CUIT/CUIL o documento.
- Selector de origen: todos, actual, historico.
- Selector de productor resultante.

Resultado del buscador:

- `productor_all_id`
- nombre
- documento
- CUIT/CUIL
- origen
- cantidad de DDJJ/eventos
- severidad maxima si existe

### Cabecera de la ficha

KPIs sugeridos:

- DDJJ/declaraciones asociadas.
- Eventos/resoluciones asociados.
- Años cubiertos.
- Superficie agricola afectada total.
- Superficie ganadera afectada total.
- Existencias ganaderas.
- Mortandad.
- Alertas criticas.

Campos descriptivos:

- Nombre o razon social.
- Documento.
- CUIT/CUIL.
- Actividad.
- Departamento/localidad/paraje mas frecuentes o ultimos.
- Origen de datos disponible.

### Seccion DDJJ asociadas

Tabla con:

- `origen_dato`
- `ddjj_all_id`
- `id_ddjj_actual`
- `ddjj_hist_id`
- fecha/anio
- resolucion/evento
- departamento/localidad/paraje
- `pondf`
- `source_file`
- `severidad_maxima`

Acciones:

- Para DDJJ actuales, permitir copiar `id_ddjj_actual` para ir a `Detalle DDJJ`.
- Para historicas, mostrar trazabilidad pero no enviar a la pagina actual de detalle hasta crear un detalle historico compatible.

### Seccion resoluciones/eventos

Tabla agrupada por:

- resolucion/evento
- anio
- origen
- cantidad de DDJJ
- superficie afectada
- flags de calidad

### Seccion agricultura

Componentes:

- Tabla de cultivos/especies por evento.
- Grafico horizontal de superficie sembrada/uso y afectada.
- Indicador de porcentaje afectado cuando sea metodologicamente valido.
- Nota para cultivos sin clasificar.

### Seccion ganaderia

Componentes:

- Tabla resumen por evento/actividad/especie/categoria.
- Existencias, mortandad y tasa de mortandad.
- Alertas por `mortandad > existencias`.

### Seccion adremas

Alcance recomendado:

- Solo datos actuales.
- Tabla de adremas asociadas a `id_ddjj_actual`.
- Superficie, actividad, tenencia, departamento y establecimiento.

### Seccion mapa o ubicacion

Alcance recomendado:

- Mapa solo para establecimientos actuales con coordenadas validas.
- Para historicos, mostrar ubicacion textual.

### Seccion mejoras/documentacion

Alcance recomendado:

- Solo DDJJ actuales.
- Mostrar ponderaciones, mejoras, documentacion y fotos cuando existan.
- Para historicos, indicar que no hay adjuntos administrativos homologados.

### Seccion alertas de calidad

Mostrar:

- `severidad_maxima`
- `flag_revision_manual`
- `flag_agricola_afectada_mayor_uso`
- `flag_ganadera_afectada_mayor_uso`
- `flag_mortandad_mayor_existencias`
- `flag_superficie_total_menor_afectadas`
- `source_file`
- `source_sheet`

## 7. Consultas SQL sugeridas

### Buscador de productor

```sql
SELECT
    productor_all_id,
    id_productor_actual,
    productor_hist_id,
    productor_nombre,
    documento_nro,
    cuit_cuil,
    actividad,
    departamento,
    localidad,
    paraje,
    origen_dato,
    eventos,
    registros,
    source_file,
    severidad_maxima
FROM vw_all_productores
WHERE
    productor_nombre LIKE :q
    OR documento_nro LIKE :q
    OR cuit_cuil LIKE :q
ORDER BY productor_nombre
LIMIT :limite;
```

### Cabecera y KPIs del productor

```sql
SELECT
    productor_all_id,
    COUNT(DISTINCT ddjj_all_id) AS ddjj,
    COUNT(DISTINCT COALESCE(evento_id, CAST(id_resolucion_actual AS CHAR), dto)) AS eventos,
    MIN(anio) AS anio_min,
    MAX(anio) AS anio_max,
    SUM(CASE WHEN LOWER(COALESCE(severidad_maxima, '')) = 'critico' THEN 1 ELSE 0 END) AS alertas_criticas,
    MAX(severidad_maxima) AS severidad_maxima
FROM vw_all_ddjj_personas
WHERE productor_all_id = :productor_all_id
GROUP BY productor_all_id;
```

### DDJJ asociadas

```sql
SELECT
    origen_dato,
    ddjj_all_id,
    id_ddjj_actual,
    ddjj_hist_id,
    evento_id,
    anio,
    fecha,
    dto,
    periodo,
    departamento,
    localidad,
    paraje,
    pondf,
    source_file,
    source_sheet,
    dataset_role,
    relation_type,
    flag_revision_manual,
    severidad_maxima
FROM vw_all_ddjj_personas
WHERE productor_all_id = :productor_all_id
ORDER BY anio DESC, fecha DESC;
```

### Resoluciones/eventos asociados

```sql
SELECT
    d.origen_dato,
    COALESCE(d.evento_id, CAST(d.id_resolucion_actual AS CHAR)) AS evento_clave,
    d.anio,
    d.dto,
    r.nombre_resolucion,
    COUNT(DISTINCT d.ddjj_all_id) AS ddjj,
    MAX(d.severidad_maxima) AS severidad_maxima
FROM vw_all_ddjj_personas d
LEFT JOIN vw_all_resoluciones r
    ON (
        d.origen_dato = r.origen_dato
        AND (
            d.evento_id = r.evento_id
            OR d.id_resolucion_actual = r.id_resolucion_actual
        )
    )
WHERE d.productor_all_id = :productor_all_id
GROUP BY d.origen_dato, evento_clave, d.anio, d.dto, r.nombre_resolucion
ORDER BY d.anio DESC;
```

### Agricultura del productor

Si `vw_all_agricultura` no tiene `productor_all_id`, unir por documento/productor con cuidado:

```sql
SELECT
    a.origen_dato,
    a.anio,
    a.dto,
    a.evento_id,
    a.departamento,
    COALESCE(a.especie, a.cultivo, a.categoria, '(s/d)') AS cultivo,
    SUM(a.superficie_sembrada_uso) AS superficie_sembrada_uso,
    SUM(a.superficie_afectada) AS superficie_afectada,
    SUM(a.produccion_estimada) AS produccion_estimada,
    SUM(a.produccion_obtenida) AS produccion_obtenida,
    MAX(a.severidad_maxima) AS severidad_maxima
FROM vw_all_agricultura a
JOIN vw_all_ddjj_personas d
    ON (
        (a.id_ddjj_actual IS NOT NULL AND a.id_ddjj_actual = d.id_ddjj_actual)
        OR (a.ddjj_hist_id IS NOT NULL AND a.ddjj_hist_id = d.ddjj_hist_id)
    )
WHERE d.productor_all_id = :productor_all_id
GROUP BY a.origen_dato, a.anio, a.dto, a.evento_id, a.departamento, cultivo
ORDER BY a.anio DESC, superficie_afectada DESC;
```

Recomendacion tecnica: si esta consulta se vuelve central, conviene agregar `productor_all_id` directamente a `vw_all_agricultura` y `vw_all_ganaderia_resumen` para evitar joins costosos o ambiguos.

### Ganaderia del productor

```sql
SELECT
    g.origen_dato,
    g.anio,
    g.dto,
    g.evento_id,
    g.departamento,
    g.actividad,
    g.especie,
    g.categoria,
    SUM(g.existencias) AS existencias,
    SUM(g.mortandad) AS mortandad,
    CASE
        WHEN SUM(g.existencias) > 0
        THEN SUM(g.mortandad) / SUM(g.existencias) * 100
        ELSE NULL
    END AS tasa_mortandad,
    MAX(g.flag_mortandad_mayor_existencias) AS flag_mortandad_mayor_existencias,
    MAX(g.severidad_maxima) AS severidad_maxima
FROM vw_all_ganaderia_resumen g
JOIN vw_all_ddjj_personas d
    ON (
        (g.id_ddjj_actual IS NOT NULL AND g.id_ddjj_actual = d.id_ddjj_actual)
        OR (g.ddjj_hist_id IS NOT NULL AND g.ddjj_hist_id = d.ddjj_hist_id)
    )
WHERE d.productor_all_id = :productor_all_id
GROUP BY g.origen_dato, g.anio, g.dto, g.evento_id, g.departamento, g.actividad, g.especie, g.categoria
ORDER BY g.anio DESC, existencias DESC;
```

### Adremas actuales del productor

```sql
SELECT
    a.adrema,
    a.superficie,
    ta.TipoActividadDesc AS actividad,
    tt.descripcion AS tenencia,
    a.departamento,
    e.nombre_estab,
    e.paraje_estab,
    a.ddjj AS id_ddjj
FROM adremas a
LEFT JOIN tipoactividad ta ON ta.TipoActividadId = a.actividad
LEFT JOIN tipotenencia tt ON tt.id = a.tenencia
LEFT JOIN establecimientos e ON e.id_establecimiento = a.id_establecimiento
JOIN ddjj_personas dj ON dj.id_ddjj = a.ddjj
WHERE dj.id_productor = :id_productor_actual
ORDER BY a.superficie DESC;
```

### Establecimientos actuales con coordenadas

```sql
SELECT
    e.id_establecimiento,
    e.nombre_estab,
    e.departamento_estab,
    e.paraje_estab,
    e.latitud,
    e.longitud,
    e.ddjj AS id_ddjj
FROM establecimientos e
JOIN ddjj_personas dj ON dj.id_ddjj = e.ddjj
WHERE dj.id_productor = :id_productor_actual
  AND e.latitud NOT IN ('', '0')
  AND e.longitud NOT IN ('', '0');
```

### Ponderaciones, mejoras y documentacion actuales

```sql
SELECT p.id_ddjj, rt.nombre AS rubro, p.estimados, p.obtenidos, p.perdidas_ponde
FROM ponderaciones_ddjj p
JOIN rubro_tipos rt ON rt.id_rubro = p.rubro
JOIN ddjj_personas dj ON dj.id_ddjj = p.id_ddjj
WHERE dj.id_productor = :id_productor_actual;
```

```sql
SELECT pm.idddjj, pm.mejora, pm.vestimado, pm.incidencia, pm.pesesp, pm.pesper
FROM perdidas_mejoras pm
JOIN ddjj_personas dj ON dj.id_ddjj = pm.idddjj
WHERE dj.id_productor = :id_productor_actual;
```

```sql
SELECT doc.idddjj, doc.codigo, doc.documentacion, doc.marcar
FROM documentacion doc
JOIN ddjj_personas dj ON dj.id_ddjj = doc.idddjj
WHERE dj.id_productor = :id_productor_actual
ORDER BY doc.idddjj, doc.codigo;
```

## 8. Paginas actuales que podria simplificar luego

La ficha no deberia eliminar paginas actuales en una primera etapa, pero podria reducir solapamientos:

- `Productores`: podria quedar como buscador/listado y derivar a `Ficha Productor`.
- `Detalle DDJJ`: podria mantenerse como vista tecnica por declaracion actual, accesible desde la ficha.
- `Adremas`: podria seguir como explorador catastral general; la ficha mostraria solo las adremas del productor.
- `Mapa`: podria seguir como mapa general; la ficha mostraria puntos del productor cuando existan coordenadas.
- `Analisis`: seguiria como pagina agregada; la ficha mostraria solo indicadores del productor seleccionado.

## 9. Pasos de implementacion recomendados

1. Crear una nueva pagina `dashboard/pages/6_Ficha_Productor.py`.
2. Reutilizar `run_query()`, `is_unified_mode()` y `table()` desde `dashboard/utils.py`.
3. Usar `vw_all_productores` como fuente del buscador cuando `DATA_MODE="unificado"`.
4. Usar `productor_all_id` como clave principal de navegacion.
5. Mostrar primero cabecera, DDJJ y eventos, porque son las secciones mas robustas.
6. Agregar agricultura y ganaderia usando `vw_all_agricultura` y `vw_all_ganaderia_resumen`.
7. Mantener adremas, establecimientos, documentacion y mejoras solo para `id_productor_actual`.
8. Agregar mensajes metodologicos para secciones no disponibles en historicos.
9. Probar localmente con `DATA_SOURCE=tidb` y `DATA_MODE=unificado`.
10. Validar casos: productor solo actual, productor solo historico, productor con posible coincidencia actual/historico, productor sin documento, productor con alertas criticas.
11. Si el rendimiento es lento, crear vistas auxiliares con `productor_all_id` ya incorporado en agricultura y ganaderia.
12. Recién despues de validar la ficha, evaluar simplificar navegacion o agregar links desde `Productores`.

## 10. Recomendacion final

Conviene avanzar con la pagina `Ficha Productor`, pero con un alcance conservador:

- Integrar actuales e historicos en busqueda, cabecera, DDJJ, eventos, agricultura, ganaderia y alertas.
- Mantener adremas, establecimientos, mapa, mejoras y documentacion solo para datos actuales.
- No fusionar automaticamente productores actuales e historicos solo por nombre.
- Conservar siempre `origen_dato`, `source_file`, `source_sheet` y flags de calidad cuando existan.

Esta pagina puede convertirse en la vista principal de consulta individual y reducir la necesidad de navegar manualmente entre `Productores`, `Detalle DDJJ`, `Adremas`, `Mapa` y `Analisis`.
