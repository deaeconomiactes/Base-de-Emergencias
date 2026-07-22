# Home: métricas y propuesta de rediseño

## Alcance y carácter del documento

Este documento establece una base metodológica preliminar para rediseñar la página Home del dashboard de Emergencias Agropecuarias. Se elaboró mediante una revisión estática de `dashboard/app.py` y `dashboard/utils.py`, sin ejecutar la aplicación ni consultar TiDB.

Las definiciones marcadas como **pendientes de validación** no deben implementarse hasta confirmar la granularidad, las claves y la cobertura de las tablas o vistas involucradas. Ninguna propuesta de este documento autoriza cambios en datos, vistas SQL o infraestructura.

## 1. Objetivo de la página Home

Home debe funcionar como una **portada ejecutiva para lectura institucional rápida**. Su propósito es permitir que autoridades, equipos técnicos y usuarios de gestión comprendan, en pocos segundos:

- cuál es el universo seleccionado;
- cuántas declaraciones, productores y territorios comprende;
- cómo evoluciona la emergencia en el tiempo;
- dónde se concentra territorialmente;
- qué resoluciones o eventos explican el universo observado;
- cuál es la magnitud del daño informado;
- qué fecha de actualización, cobertura y limitaciones tienen los datos.

La portada debe priorizar síntesis, comparabilidad y trazabilidad. No debe reemplazar las páginas de exploración o detalle ni concentrar tablas extensas, distribuciones estadísticas especializadas o registros individuales.

Todos los indicadores visibles deben referirse al mismo universo o señalar de forma inequívoca cuando son totales generales. Las tarjetas, gráficos y tablas deben reconciliar entre sí bajo los mismos filtros y definiciones.

## 2. Diccionario preliminar de KPIs

### 2.1 Productores

- **Nombre visible:** Productores afectados.
- **Definición:** cantidad de productores únicos asociados con al menos una DDJJ dentro del universo seleccionado.
- **Unidad:** productores únicos.
- **Tabla/vista fuente:** `productores` o `vw_all_productores`; puede requerir vinculación con `ddjj_personas` o `vw_all_ddjj_personas` para aplicar filtros de evento, fecha y territorio.
- **Clave de conteo recomendada:** `COUNT(DISTINCT productor_id)` o clave estable equivalente. No usar `COUNT(*)` hasta validar la granularidad.
- **Filtros que deberían afectarlo:** período, resolución/evento, departamento y origen de datos. El filtro de daño solo debería afectarlo cuando el usuario lo active expresamente como criterio analítico.
- **Tratamiento de nulos:** excluir registros sin clave de productor del conteo principal e informar su cantidad como control de calidad.
- **Riesgo de duplicación:** alto en modo unificado y cuando un productor posee varias DDJJ, establecimientos o adremas.
- **Estado:** pendiente de validación.

### 2.2 DDJJ

- **Nombre visible:** Declaraciones juradas (DDJJ).
- **Definición:** cantidad de declaraciones juradas únicas dentro del universo seleccionado.
- **Unidad:** DDJJ únicas.
- **Tabla/vista fuente:** `ddjj_personas` o `vw_all_ddjj_personas`.
- **Clave de conteo recomendada:** identificador único de DDJJ si existe. En su ausencia, validar una clave compuesta por resolución/evento, DTO, año, fecha y productor.
- **Filtros que deberían afectarlo:** período, resolución/evento, departamento y origen. El daño no debe excluir DDJJ por defecto.
- **Tratamiento de nulos:** una DDJJ puede contarse aunque `pondf` sea nulo. Los componentes nulos de una clave compuesta requieren revisión y no deben concatenarse silenciosamente.
- **Riesgo de duplicación:** medio/alto en vistas unificadas o joins con resoluciones, actividades, establecimientos y adremas.
- **Estado:** pendiente de validación.

### 2.3 Resoluciones / eventos

- **Nombre visible:** Resoluciones o eventos incluidos.
- **Definición:** cantidad de unidades normativas o eventos distintos representados en el universo seleccionado.
- **Unidad:** resoluciones/eventos únicos.
- **Tabla/vista fuente:** `resoluciones` o `vw_all_resoluciones`, relacionadas con las DDJJ.
- **Clave de conteo recomendada:** en modo unificado, `resolucion_all_id` si su unicidad está garantizada; alternativamente `evento_id` para históricos e identificador de resolución para actuales. No mezclar unidades sin una regla de homologación.
- **Filtros que deberían afectarlo:** período, departamento, origen y demás filtros globales aplicados a las DDJJ.
- **Tratamiento de nulos:** excluir claves normativas nulas del KPI e informar DDJJ sin resolución/evento como control de integridad.
- **Riesgo de duplicación:** alto si una resolución aparece repetida por evento, DTO, vigencia u origen.
- **Estado:** pendiente de validación.

### 2.4 Departamentos afectados

- **Nombre visible:** Departamentos afectados.
- **Definición:** cantidad de departamentos distintos con al menos una DDJJ en el universo seleccionado.
- **Unidad:** departamentos únicos.
- **Tabla/vista fuente:** campo `departamento` de `ddjj_personas` o `vw_all_ddjj_personas`; idealmente homologado contra un catálogo territorial.
- **Clave de conteo recomendada:** `COUNT(DISTINCT departamento_id)`; si solo existe texto, usar temporalmente el nombre normalizado y documentar la limitación.
- **Filtros que deberían afectarlo:** período, resolución/evento, departamento y origen. El daño solo cuando se active expresamente.
- **Tratamiento de nulos:** excluir nulos y cadenas vacías del KPI; informar su incidencia como control de calidad.
- **Riesgo de duplicación:** bajo con identificador territorial; medio con nombres que tengan variantes ortográficas.
- **Estado:** pendiente de validación.

### 2.5 Establecimientos / Adremas

- **Nombre visible:** Establecimientos afectados o Adremas alcanzadas, según la unidad que se valide.
- **Definición:** cantidad de unidades productivas o catastrales únicas vinculadas con DDJJ del universo seleccionado.
- **Unidad:** establecimientos únicos o adremas únicas; no deben combinarse en un único indicador.
- **Tabla/vista fuente:** `establecimientos` y `adremas`, vinculadas con DDJJ y productores. El código actual no define variantes unificadas para estas dos fuentes.
- **Clave de conteo recomendada:** identificador estable de establecimiento o identificador normalizado de adrema mediante `COUNT(DISTINCT ...)`.
- **Filtros que deberían afectarlo:** período, resolución/evento, departamento y origen, siempre que exista una relación trazable con DDJJ.
- **Tratamiento de nulos:** excluir claves nulas; informar registros sin vínculo o sin identificador.
- **Riesgo de duplicación:** alto por relaciones de muchos a muchos entre productores, DDJJ, establecimientos y adremas.
- **Estado:** pendiente de validación. No se recomienda como tarjeta principal hasta confirmar definición y vínculo.

### 2.6 Daño promedio

- **Nombre visible:** Daño promedio informado.
- **Definición:** promedio del porcentaje de daño declarado en las DDJJ con dato válido del universo seleccionado. Debe indicarse si es simple o ponderado.
- **Unidad:** porcentaje.
- **Tabla/vista fuente:** campo `pondf` de `ddjj_personas` o `vw_all_ddjj_personas`.
- **Clave de conteo recomendada:** calcular una observación por DDJJ única antes de agregar; no promediar filas duplicadas por joins.
- **Filtros que deberían afectarlo:** período, resolución/evento, departamento y origen. Si el propio rango de daño lo filtra, debe advertirse que se trata de un promedio condicionado.
- **Tratamiento de nulos:** excluir nulos del cálculo e informar el número y porcentaje de DDJJ con dato válido. Los ceros no deben excluirse sin una definición metodológica explícita.
- **Riesgo de duplicación:** medio/alto si una DDJJ se repite en la fuente o luego de un join.
- **Estado:** pendiente de validación.

### 2.7 Superficie afectada agrícola

- **Nombre visible:** Superficie agrícola afectada.
- **Definición:** suma de hectáreas agrícolas afectadas asociadas con DDJJ del universo seleccionado, evitando duplicar parcelas o cultivos.
- **Unidad:** hectáreas.
- **Tabla/vista fuente:** previsiblemente `agricultura`/`vw_all_agricultura` y, si corresponde, `cultivos`/`vw_all_cultivos`. La columna exacta de superficie debe identificarse y validarse antes de implementar.
- **Clave de conteo recomendada:** sumar una superficie validada a la granularidad DDJJ–parcela–cultivo, o la clave de detalle equivalente. No sumar sobre joins no deduplicados.
- **Filtros que deberían afectarlo:** período, resolución/evento, departamento, origen y, cuando corresponda, actividad/cultivo.
- **Tratamiento de nulos:** excluir nulos de la suma, conservar ceros válidos e informar cobertura. Revisar valores negativos y unidades distintas de hectáreas.
- **Riesgo de duplicación:** alto por múltiples cultivos, actividades o filas vinculadas a una misma superficie.
- **Estado:** pendiente de validación.

### 2.8 Superficie afectada ganadera

- **Nombre visible:** Superficie ganadera afectada.
- **Definición:** suma de hectáreas ganaderas afectadas asociadas con DDJJ del universo seleccionado.
- **Unidad:** hectáreas.
- **Tabla/vista fuente:** fuente pendiente de identificar; `bovinos`/`vw_all_ganaderia_resumen` podría aportar información ganadera, pero no se confirmó que contenga superficie.
- **Clave de conteo recomendada:** sumar una única observación de superficie por DDJJ–establecimiento o por la clave territorial/productiva validada.
- **Filtros que deberían afectarlo:** período, resolución/evento, departamento, origen y actividad ganadera cuando corresponda.
- **Tratamiento de nulos:** excluir nulos de la suma, conservar ceros válidos e informar cobertura y unidad.
- **Riesgo de duplicación:** alto si la superficie se repite por categoría de animal o resumen ganadero.
- **Estado:** pendiente de validación.

### 2.9 Primer año

- **Nombre visible:** Primer año con registros.
- **Definición:** año mínimo de la fecha válida de las DDJJ del universo seleccionado.
- **Unidad:** año calendario.
- **Tabla/vista fuente:** campo `fecha` de `ddjj_personas` o `vw_all_ddjj_personas`.
- **Clave de conteo recomendada:** no aplica; usar `MIN(fecha)` sobre DDJJ deduplicadas o sobre la fuente cuya granularidad se haya validado.
- **Filtros que deberían afectarlo:** origen, resolución/evento y departamento si se pretende describir la selección. No debería estar restringido por el rango temporal si se usa para informar cobertura histórica total.
- **Tratamiento de nulos:** excluir fechas nulas e inválidas; en modo actual revisar la regla vigente que descarta fechas anteriores a 2000.
- **Riesgo de duplicación:** bajo, aunque fechas erróneas pueden alterar el mínimo.
- **Estado:** pendiente de validación.

### 2.10 Último año

- **Nombre visible:** Último año con registros.
- **Definición:** año máximo de la fecha válida de las DDJJ del universo seleccionado.
- **Unidad:** año calendario.
- **Tabla/vista fuente:** campo `fecha` de `ddjj_personas` o `vw_all_ddjj_personas`.
- **Clave de conteo recomendada:** no aplica; usar `MAX(fecha)` sobre la fuente validada.
- **Filtros que deberían afectarlo:** misma regla que Primer año.
- **Tratamiento de nulos:** excluir fechas nulas e inválidas; investigar fechas futuras o cargas incorrectas.
- **Riesgo de duplicación:** bajo, aunque fechas erróneas pueden alterar el máximo.
- **Estado:** pendiente de validación.

### 2.11 Fecha de actualización

- **Nombre visible:** Datos actualizados al.
- **Definición:** fecha y hora de la última actualización exitosa de la fuente o del proceso de carga que alimenta el dashboard. No debe confundirse con la fecha máxima de una DDJJ.
- **Unidad:** fecha y hora, con zona horaria indicada.
- **Tabla/vista fuente:** metadato de carga, tabla de auditoría o marca temporal del proceso ETL; fuente todavía no identificada.
- **Clave de conteo recomendada:** no aplica; usar el máximo timestamp de una carga exitosa y completa.
- **Filtros que deberían afectarlo:** ninguno, salvo que actual e histórico tengan procesos de actualización distintos; en ese caso mostrar una fecha por origen.
- **Tratamiento de nulos:** mostrar “Fecha de actualización no disponible” y no sustituir silenciosamente por la hora de apertura de la aplicación.
- **Riesgo de duplicación:** bajo; el riesgo principal es utilizar una fecha que no represente frescura real.
- **Estado:** pendiente de validación.

## 3. Decisiones metodológicas pendientes

### Productor único: clave principal recomendada

Debe identificarse un `productor_id` estable entre los universos actual e histórico. DNI, CUIT, nombre o combinaciones de datos personales no deberían utilizarse como clave visible ni como primera alternativa sin normalización, controles de calidad y resguardo de confidencialidad. Si no existe una clave común, se requiere una tabla de correspondencias documentada.

### DDJJ única: clave por resolución/DTO/año/fecha/productor

La primera opción debe ser un identificador técnico único de DDJJ. Si no existe o no es estable entre orígenes, debe validarse una clave compuesta por resolución/evento, DTO, año, fecha y productor. Antes de adoptarla se debe medir:

- unicidad;
- proporción de componentes nulos;
- colisiones;
- cambios de formato entre actual e histórico;
- posibilidad de múltiples DDJJ legítimas del mismo productor en una fecha.

### Resolución/evento: evento_id, DTO o resolución

Debe definirse la unidad institucional que se desea comunicar:

- `evento_id` representa un episodio o agrupación histórica;
- DTO podría representar un instrumento o trámite administrativo, sujeto a validación;
- resolución representa una norma y puede abarcar más de un evento o período.

No deben sumarse indistintamente. Home puede usar “Eventos/resoluciones incluidos” solo como etiqueta transitoria hasta acordar una unidad homogénea.

### Daño promedio: simple, mediana o ponderado

Se deben evaluar tres alternativas:

- **Promedio simple:** fácil de comunicar, pero cada DDJJ pesa igual y es sensible a extremos.
- **Mediana:** representa mejor el caso típico cuando la distribución es asimétrica.
- **Promedio ponderado:** puede ser más representativo si se pondera por superficie o capacidad productiva, pero exige una variable de ponderación completa, comparable y no duplicada.

Recomendación preliminar: mostrar mediana o promedio simple acompañado por cobertura, y reservar el ponderado hasta validar superficies y granularidad.

### Ceros versus nulos en `pondf`

- Un nulo significa dato ausente o no informado y no debe convertirse en cero.
- Un cero podría significar daño nulo real, valor por defecto o dato incompleto; debe validarse su semántica.
- El código actual excluye ceros del KPI y del histograma, pero el filtro general admite 0–100.
- Toda métrica de daño debe informar el denominador de DDJJ válidas.

### Actual, histórico y unificado

Debe acordarse si Home abre por defecto en:

- datos actuales;
- datos históricos;
- universo unificado.

El modo unificado requiere reglas explícitas de homologación y deduplicación. Los indicadores no deben mezclar vistas unificadas con tablas solo actuales sin advertencia.

### Relación entre año y rango de fechas

Usar simultáneamente ambos filtros produce la intersección de condiciones y puede confundir. Se recomienda:

- mantener el rango de fechas como filtro principal;
- ofrecer accesos rápidos por año; o
- hacer que la selección de año actualice automáticamente el rango.

También debe verificarse si `fecha` es `DATE` o `DATETIME` para incluir completamente el último día elegido.

### Filtros que deben afectar cada métrica

Como regla general, período, resolución/evento, departamento y origen deben afectar tarjetas y gráficos. El filtro de daño debe ser analítico y opcional: no debe eliminar DDJJ, productores o territorios del resumen general por defecto. Primer año, Último año y Fecha de actualización pueden describir cobertura global y, si es así, deben presentarse separados de los KPIs filtrados.

## 4. Diagnóstico de Home actual

### Qué muestra hoy

Home presenta seis tarjetas generales —Productores, DDJJ, Resoluciones, Establecimientos, Adremas y Daño promedio—, filtros laterales y cuatro gráficos: DDJJ por resolución, Top 15 de departamentos, distribución del porcentaje de daño y evolución mensual de DDJJ.

### Indicadores útiles

- DDJJ, como medida de volumen administrativo.
- Productores, si se transforma en conteo único y filtrado.
- Resoluciones/eventos, si se define la unidad.
- Daño, si se aclaran denominador, ceros, nulos y método de agregación.
- Concentración territorial y evolución temporal.

### Elementos que pueden confundir

- Las tarjetas son totales generales y no responden a los filtros; los gráficos sí.
- El rango predeterminado de `pondf` excluye implícitamente registros nulos de los conteos gráficos.
- Año y rango de fechas se superponen.
- Los conteos usan `COUNT(*)`, aunque las vistas podrían contener varias filas por entidad.
- Establecimientos y Adremas no usan una fuente unificada en el código actual.
- El daño promedio excluye ceros sin explicación visible.
- El selector de resolución prioriza un ID interno en vez del número institucional.
- El encabezado expone host y base, información técnica innecesaria para la portada institucional.
- Formatos de miles, decimales, fechas y tildes no están localizados completamente al español de Argentina.

### Consultas potencialmente pesadas

- Se ejecutan seis consultas secuenciales para los KPIs generales.
- Los conteos y el promedio recorren tablas o vistas completas.
- El histograma descarga cada valor individual de `pondf` y agrega en el cliente.
- `YEAR(fecha)` puede limitar el uso de índices sobre la fecha.
- El join del modo unificado incluye condiciones con `OR`.
- El filtro de resolución unificado usa un `EXISTS` correlacionado.
- El gráfico por resolución no establece un límite de categorías.
- Cada combinación de filtros genera una variante de consulta y una entrada de caché.

Estas observaciones son riesgos teóricos basados en el código. Deben comprobarse con planes de ejecución y métricas únicamente con autorización para consultar TiDB.

### Contenido que debería moverse a Análisis

El histograma de porcentaje de daño debería trasladarse a Análisis, donde puede acompañarse con mediana, percentiles, cobertura y segmentaciones. Si se conserva una síntesis en Home, debe agregarse por intervalos en SQL y ocupar un lugar secundario.

También corresponden a Análisis las comparaciones avanzadas, distribuciones, cruces entre variables y diagnósticos de valores extremos. Home debe conservar únicamente visualizaciones de síntesis.

## 5. Propuesta de diseño de Home

### Encabezado institucional simple

- Título: “Emergencias Agropecuarias — Resumen general”.
- Subtítulo breve con período y universo.
- Etiqueta discreta para origen: Actual, Histórico o Unificado.
- Fecha de actualización visible.
- Host y base fuera de la vista institucional ordinaria.

### Resumen de filtros activos

Debajo del encabezado, mostrar una línea o conjunto breve de etiquetas con:

- período;
- resolución/evento;
- departamentos;
- origen;
- filtros avanzados activos.

Debe existir una acción clara para restablecer filtros.

### Tarjetas ejecutivas

Primera fila propuesta:

1. DDJJ únicas.
2. Productores únicos.
3. Departamentos afectados.
4. Daño promedio o mediano informado.
5. Cobertura del dato de daño.

Las superficies agrícola y ganadera pueden incorporarse en una segunda fila cuando sus fuentes y reglas de agregación estén validadas. Establecimientos y Adremas deben permanecer en páginas de detalle salvo que se validen como indicadores ejecutivos filtrables.

### Evolución temporal mensual/anual

Ubicar un gráfico ancho inmediatamente después de las tarjetas:

- evolución mensual para períodos cortos o medianos;
- evolución anual para series largas;
- selector de granularidad o adaptación automática;
- meses/años legibles y ausencia de falsas continuidades en períodos sin datos.

### Composición territorial

Mantener barras horizontales de departamentos con más DDJJ y agregar, si es posible:

- porcentaje sobre el total filtrado;
- cantidad de productores únicos;
- aclaración de que volumen de DDJJ no equivale necesariamente a severidad.

### Composición por resolución/evento

Mostrar las principales resoluciones o eventos mediante barras ordenadas. Usar etiquetas institucionales, limitar categorías y ofrecer el resto en una tabla agregada o página específica.

### Nota metodológica y fecha de actualización

Cerrar Home con una nota breve que informe:

- fuente y modo de datos;
- fecha de actualización;
- definición resumida de DDJJ y productores;
- tratamiento de daño nulo/cero;
- enlace o referencia a este documento metodológico.

## 6. Plan de implementación por etapas

### Etapa 1: Definiciones metodológicas.

- Confirmar unidades estadísticas y claves únicas.
- Validar granularidad y cobertura de tablas y vistas.
- Acordar definiciones de productor, DDJJ y resolución/evento.
- Resolver tratamiento de ceros, nulos y ponderadores.
- Identificar fuentes y columnas de superficies y actualización.
- Aprobar el diccionario definitivo de KPIs.

### Etapa 2: Coherencia de filtros.

- Aplicar el mismo universo a KPIs y gráficos.
- Separar filtros globales de filtros analíticos.
- Resolver la relación entre año y rango de fechas.
- Evitar que `pondf` excluya registros por defecto.
- Mostrar filtros activos y permitir restablecerlos.

### Etapa 3: Optimización SQL.

- Sustituir conteos de filas por conteos distintos cuando corresponda.
- Agregar distribuciones en SQL.
- Evitar funciones no indexables en filtros de fecha.
- Revisar joins y deduplicación del modo unificado.
- Reducir viajes de red y consultas redundantes.
- Evaluar planes de ejecución solo con autorización.

### Etapa 4: Rediseño visual.

- Simplificar encabezado y formatos.
- Reordenar Home desde resumen hacia explicación.
- Implementar tarjetas ejecutivas validadas.
- Priorizar la evolución temporal.
- Mantener composiciones territorial y normativa.
- Trasladar análisis especializados a su página correspondiente.

### Etapa 5: Validación.

- Reconciliar tarjetas, gráficos y tablas.
- Probar filtros individuales y combinados.
- Validar modos actual, histórico y unificado.
- Verificar estados vacíos, nulos y fallos parciales.
- Medir tiempos de respuesta y volumen transferido.
- Revisar resultados con usuarios técnicos e institucionales.

### Etapa 6: Implementación controlada.

- Modificar solo los archivos expresamente autorizados.
- No sobrescribir fuentes ni alterar datos.
- Realizar cambios pequeños y revisables.
- Documentar definiciones, consultas y decisiones.
- Comparar resultados antes y después.
- No publicar, hacer commit o push sin autorización específica.

## 7. Reglas de implementación

- No modificar TiDB sin autorización expresa.
- No modificar vistas SQL sin autorización expresa.
- Evitar consultas pesadas y transferencias de datos individuales cuando una agregación SQL sea suficiente.
- Usar `COUNT(DISTINCT ...)` cuando la unidad estadística lo requiera y después de validar la clave.
- Manejar fallos parciales sin romper la aplicación; indicar “Sin dato” o un mensaje trazable sin ocultar inconsistencias sistemáticas.
- Mantener trazabilidad en `docs`: definición, fuente, columnas, filtros, transformaciones, supuestos, exclusiones y fecha de validación.
- Parametrizar los valores de filtros y mantener controlados los nombres de tablas y vistas.
- No mezclar métricas de fuentes actuales y unificadas sin una etiqueta y regla explícita.
- No presentar como “aprobada” una métrica cuya granularidad, fuente o clave no haya sido validada.
- No exponer datos personales ni información técnica sensible en la portada.
- Mantener separadas las capas de carga, definición de métricas, visualización y documentación.

## Registro de decisiones pendientes prioritarias

Antes de modificar Home se deben resolver, como mínimo:

1. Clave estable del productor entre actual e histórico.
2. Clave única de DDJJ y tratamiento de posibles colisiones.
3. Unidad institucional para resolución/evento/DTO.
4. Semántica de ceros y nulos en `pondf`.
5. Uso de promedio simple, mediana o ponderación para daño.
6. Columnas y granularidad de superficie agrícola y ganadera.
7. Fuente confiable para la fecha de actualización.
8. Alcance de Establecimientos y Adremas en modo unificado.
9. Regla uniforme sobre qué filtros afectan cada KPI.
10. Universo predeterminado de Home: actual, histórico o unificado.
