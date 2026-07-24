# Organización de fuentes crudas y datos procesados

## Objetivo

Documentar la estructura local de insumos del proyecto de Emergencias Agropecuarias, preservar las fuentes originales y evitar cambios que rompan el pipeline histórico existente.

## Estructura encontrada antes de esta intervención

En la copia local auditada no existían las siguientes carpetas:

- `data_raw/`
- `data/`
- `raw/`
- `input/`
- `historico/` o `históricos/`
- `data_processed/`
- `staging/`
- `outputs/`

Tampoco había archivos Excel dentro del proyecto. Los 35 nombres de libros históricos esperados están registrados en `config/file_formats.csv`.

La documentación previa del repositorio señala que los Excel históricos estuvieron almacenados directamente en `data_raw/` de otra copia del proyecto ubicada en OneDrive. Esas referencias se consideran evidencia documental; OneDrive no debe utilizarse como fuente operativa del pipeline actual.

## Dependencias de rutas del pipeline existente

Los scripts históricos utilizan las siguientes convenciones:

- `scripts/00_inventory_excel.py` toma por defecto `data_raw/` y enumera únicamente los Excel ubicados directamente en esa carpeta. No recorre subcarpetas.
- `scripts/01_transform_historical_files.py` toma por defecto `data_raw/` y busca cada nombre exacto definido en `config/file_formats.csv` mediante la ruta `data_raw/<archivo>`.
- Los scripts posteriores usan principalmente `data_clean/` para CSV armonizados y `data_intermediate/` para reportes de control.
- `scripts/05_upload_to_tidb_staging.py` y `scripts/06_validate_tidb_staging.py` dependen de archivos específicos dentro de `data_clean/`.

Por estas dependencias, los Excel históricos ya utilizados por el pipeline no deben moverse, renombrarse ni distribuirse en subcarpetas sin modificar y validar previamente los scripts 00 y 01.

## Estructura incorporada

```text
data_raw/
└── ddjj_2023_excel/
    ├── original/
    │   └── README.md
    └── metadata/
        └── source_manifest.md

data_processed/
└── ddjj_2023_excel/
    ├── audit/
    └── normalized/

docs/
└── data_sources/
    └── data_raw_organization.md
```

### Fuentes crudas

`data_raw/ddjj_2023_excel/original/` está reservado para la copia inalterada de:

`Informes Tramites Emerg. Agrop - Actualizado 21052026.xlsx`

`data_raw/ddjj_2023_excel/metadata/` contiene documentación sobre origen, alcance, estado y reglas de tratamiento. Los metadatos no reemplazan ni modifican la fuente.

### Salidas procesadas

- `data_processed/ddjj_2023_excel/audit/`: reportes reproducibles de estructura, integridad y calidad.
- `data_processed/ddjj_2023_excel/normalized/`: tablas normalizadas y validadas derivadas de la fuente.

Estas carpetas no sustituyen las salidas históricas vigentes en `data_clean/` y `data_intermediate/`. La convergencia entre ambos modelos deberá definirse en una etapa posterior.

## Estructura propuesta a futuro

Si en el futuro se actualiza el pipeline histórico para aceptar rutas recursivas o configurables, puede evaluarse la siguiente organización:

```text
data_raw/
├── historical/
│   ├── original/
│   └── inventory/
├── current/
│   └── original/
└── ddjj_2023_excel/
    ├── original/
    └── metadata/

data_processed/
├── historical/
├── current/
└── ddjj_2023_excel/
    ├── audit/
    └── normalized/
```

Esta reorganización es solamente una recomendación. No deben moverse automáticamente los archivos históricos existentes porque los scripts 00 y 01 esperan una estructura plana en `data_raw/`.

## Reglas de trabajo

1. Los archivos bajo carpetas `original/` son fuentes crudas e inmutables.
2. No sobrescribir, editar, limpiar ni renombrar fuentes crudas.
3. Las transformaciones deben escribir en carpetas procesadas separadas.
4. Cada fuente debe contar con un manifiesto que registre nombre, fecha de corte, unidad de análisis, responsable o procedencia cuando esté disponible, alcance y advertencias.
5. Los scripts deben registrar `source_file`, `source_sheet` y, cuando corresponda, la fila de origen.
6. No cargar a TiDB ni incorporar al dashboard datos que no hayan superado auditoría, normalización y validación.
7. No almacenar secretos, credenciales ni archivos `.env` junto con las fuentes.
8. Los archivos con información personal deben permanecer fuera del control de versiones público y tratarse como datos sensibles.

## Convención recomendada para futuras bases

Para nuevas fuentes independientes, usar:

```text
data_raw/<identificador_fuente>/original/
data_raw/<identificador_fuente>/metadata/
data_processed/<identificador_fuente>/audit/
data_processed/<identificador_fuente>/normalized/
```

El identificador debe ser estable, breve y descriptivo. El nombre del archivo original debe conservarse siempre que no genere una colisión documentada.

## Ubicación operativa recomendada

OneDrive puede introducir rutas dependientes del usuario, sincronización parcial, archivos bajo demanda, bloqueos y duplicación de copias. Por ello no debe usarse como fuente operativa del pipeline.

Se recomienda utilizar como espacio de trabajo el repositorio local asociado a GitHub, manteniendo fuera de Git los datos sensibles y pesados mediante `.gitignore`. GitHub debe versionar código, configuración no sensible y documentación; no debe utilizarse para publicar fuentes crudas confidenciales.

