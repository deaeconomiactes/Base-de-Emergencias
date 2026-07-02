#!/usr/bin/env python3
import os
import sys
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv
import pymysql

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

def clean_cuit(val):
    if pd.isna(val):
        return ""
    val_str = str(val).strip().split('.')[0].replace("-", "")
    return val_str

def clean_doc(val):
    if pd.isna(val):
        return None
    val_str = str(val).strip().split('.')[0].replace(".", "").replace(" ", "")
    return val_str if val_str else None

def clean_str(val):
    if pd.isna(val):
        return ""
    return str(val).strip()

def safe_float(val):
    if pd.isna(val):
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0

def chunked_insert(cur, query, data, conn, chunk_size=100):
    for i in range(0, len(data), chunk_size):
        chunk = data[i:i+chunk_size]
        cur.executemany(query, chunk)
        conn.commit()

def main():
    excel_path = ROOT / "Anibal" / "DTO 2017-235.xlsx"
    if not excel_path.exists():
        print(f"ERROR: No se encuentra el archivo Excel en {excel_path}", file=sys.stderr, flush=True)
        sys.exit(1)

    source = os.getenv("DATA_SOURCE", "local").lower()
    print(f"Origen de datos activo: {source}", flush=True)

    if source == "tidb":
        host = os.getenv("TIDB_HOST")
        port = int(os.getenv("TIDB_PORT", "4000"))
        user = os.getenv("TIDB_USER")
        password = os.getenv("TIDB_PASS")
        database = os.getenv("TIDB_DB", "emergencias")
        try:
            import certifi
            ssl = {"ca": certifi.where()}
        except ImportError:
            ssl_ca = os.getenv("TIDB_SSL_CA", "/etc/ssl/cert.pem")
            ssl = {"ca": ssl_ca} if os.path.exists(ssl_ca) else None
    else:
        host = os.getenv("MYSQL_HOST", "127.0.0.1")
        port = int(os.getenv("MYSQL_PORT", "3306"))
        user = os.getenv("MYSQL_USER", "root")
        password = os.getenv("MYSQL_PASSWORD", "")
        database = os.getenv("MYSQL_DATABASE", "emergencias")
        ssl = None

    print(f"Conectando a {user}@{host}:{port}/{database}...", flush=True)
    conn = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        charset="utf8mb4",
        ssl=ssl,
        autocommit=False,
        connect_timeout=30,
        read_timeout=300,
        write_timeout=300
    )

    try:
        with conn.cursor() as cur:
            # 1. Asegurar resolución 10
            print("\n--- Asegurando Resolución 10 (DTO 235-2017) ---", flush=True)
            cur.execute("""
                INSERT INTO resoluciones (id_resolucion, nombre_resolucion, numero_resolucion, fec_res, cabeza, pie)
                VALUES (10, 'EMERGENCIA AGROPECUARIA 235-2017', '235-2017', '2017-01-01', '', '')
                ON DUPLICATE KEY UPDATE nombre_resolucion=VALUES(nombre_resolucion), numero_resolucion=VALUES(numero_resolucion)
            """)
            conn.commit()

            # Leer Excel
            print("Leyendo archivo Excel...", flush=True)
            df = pd.read_excel(excel_path, sheet_name='agric')
            print(f"Filas encontradas en Excel: {len(df)}", flush=True)

            # Cargar cachés iniciales
            print("Cargando caché de productores desde la base de datos...", flush=True)
            cur.execute("SELECT CUITCUIL, DocumentoNro, ProductorId FROM productores")
            cuit_to_id = {}
            doc_to_id = {}
            for cuit_db, doc_db, prod_id in cur.fetchall():
                if cuit_db:
                    cuit_to_id[str(cuit_db).strip()] = prod_id
                if doc_db:
                    doc_to_id[str(doc_db).strip()] = prod_id

            print("Cargando caché de cultivos...", flush=True)
            cur.execute("SELECT id, cultivodesc, cultivotipoid FROM cultivos")
            cultivos_cache = {}
            max_cultivo_id = 0
            for cid, cdesc, ctipo in cur.fetchall():
                if cdesc:
                    cultivos_cache[cdesc.upper().strip()] = (cid, ctipo)
                if cid > max_cultivo_id:
                    max_cultivo_id = cid

            print("Cargando DDJJs ya importadas para Resolución 10...", flush=True)
            cur.execute("SELECT id_productor, id_ddjj FROM ddjj_personas WHERE id_resolucion = 10")
            existing_ddjj = {id_prod: id_dj for id_prod, id_dj in cur.fetchall()}

            # Identificar productores nuevos a insertar
            new_producers_data = []
            seen_producers_in_excel = set()

            # Mapeo de filas válidas procesadas
            valid_rows = []

            for idx, row in df.iterrows():
                denominacion = clean_str(row.get('ProductorDenominacion'))
                cuit = clean_cuit(row.get('CUITCUIL'))
                doc = clean_doc(row.get('DocumentoNro'))
                if not denominacion:
                    continue

                # Determinar si ya lo vimos en este bucle
                prod_key = (cuit, doc, denominacion)
                if prod_key in seen_producers_in_excel:
                    continue
                seen_producers_in_excel.add(prod_key)

                # Buscar ID del productor
                prod_id = None
                if cuit and cuit in cuit_to_id:
                    prod_id = cuit_to_id[cuit]
                elif doc and doc in doc_to_id:
                    prod_id = doc_to_id[doc]

                if not prod_id:
                    # Es nuevo, agregar a la lista para inserción masiva
                    new_producers_data.append((denominacion, cuit, doc))
                
                valid_rows.append({
                    'row': row,
                    'denominacion': denominacion,
                    'cuit': cuit,
                    'doc': doc,
                    'prod_key': prod_key
                })

            # 2. Inserción masiva de productores nuevos
            if new_producers_data:
                print(f"Insertando {len(new_producers_data)} productores nuevos...", flush=True)
                chunked_insert(cur, """
                    INSERT INTO productores (ProductorDenominacion, CUITCUIL, DocumentoNro, Sexo, renspa, fechaAlta, usuario, DomicilioId, EstablecimientoId)
                    VALUES (%s, %s, %s, 'S', '', '2017-01-01', 1, 0, 0)
                """, new_producers_data, conn, chunk_size=50)

                # Recargar la caché de productores para obtener los nuevos IDs
                print("Recargando caché de productores...", flush=True)
                cur.execute("SELECT CUITCUIL, DocumentoNro, ProductorId FROM productores")
                cuit_to_id = {}
                doc_to_id = {}
                for cuit_db, doc_db, prod_id in cur.fetchall():
                    if cuit_db:
                        cuit_to_id[str(cuit_db).strip()] = prod_id
                    if doc_db:
                        doc_to_id[str(doc_db).strip()] = prod_id

            # 3. Preparar inserción de ddjj_personas
            ddjj_to_insert = []
            rows_to_insert_ddjj = []

            for item in valid_rows:
                cuit = item['cuit']
                doc = item['doc']
                denominacion = item['denominacion']
                row = item['row']

                prod_id = cuit_to_id.get(cuit) or doc_to_id.get(doc)
                if not prod_id:
                    continue

                if prod_id in existing_ddjj:
                    continue

                sup_sembrada = safe_float(row.get('SuperficiePlantada'))
                sup_afectada = safe_float(row.get('SuperficieAfectada'))
                pondf = (sup_afectada / sup_sembrada * 100.0) if sup_sembrada > 0 else 0.0

                ddjj_to_insert.append((
                    prod_id, denominacion,
                    int(cuit) if cuit and cuit.isdigit() else 0,
                    int(doc) if doc and doc.isdigit() else 0,
                    clean_str(row.get('DepartamentoDesc', '')),
                    clean_str(row.get('LocalidadDesc', '')),
                    clean_str(row.get('ParajeDesc', '')),
                    pondf
                ))
                rows_to_insert_ddjj.append((prod_id, pondf, row))

            if ddjj_to_insert:
                print(f"Insertando {len(ddjj_to_insert)} DDJJs...", flush=True)
                chunked_insert(cur, """
                    INSERT INTO ddjj_personas (id_productor, id_resolucion, fecha, nombre, cuit, num_doc, tipo_doc, sexo, provincia, departamento, localidad, paraje, paso, cargado, id_usuario, estado, impreso, fechaimpreso, pondf, dea, renspa, barrio, cod_pos, seccion, calle, sector, piso, manzana, casa, telefono1, telefono2, telefono3)
                    VALUES (%s, 10, '2017-01-01', %s, %s, %s, '1', 'S', 'CORRIENTES', %s, %s, %s, 10, 1, 1, 3, 1, '2017-01-01', %s, 1, '', '', '', '', '', '', '', '', '', '', '', '')
                """, ddjj_to_insert, conn, chunk_size=50)

                # Obtener IDs de las DDJJ recién creadas
                print("Cargando IDs de DDJJs creadas...", flush=True)
                cur.execute("SELECT id_productor, id_ddjj FROM ddjj_personas WHERE id_resolucion = 10")
                existing_ddjj = {id_prod: id_dj for id_prod, id_dj in cur.fetchall()}

            # 4. Preparar inserción de agricultura y ponderaciones_ddjj
            agricultura_to_insert = []
            ponderaciones_to_insert = []

            for prod_id, pondf, row in rows_to_insert_ddjj:
                ddjj_id = existing_ddjj.get(prod_id)
                if not ddjj_id:
                    continue

                sup_sembrada = safe_float(row.get('SuperficiePlantada'))
                sup_afectada = safe_float(row.get('SuperficieAfectada'))

                # Buscar o crear Cultivo
                cultivo_desc = clean_str(row.get('CultivoDesc', 'OTROS'))
                cultivo_key = cultivo_desc.upper().strip()
                if cultivo_key in cultivos_cache:
                    id_cultivo, tipo_cultivo = cultivos_cache[cultivo_key]
                else:
                    tipo_cultivo = 9 if 'ZAPALLO' in cultivo_key or 'MANDIOCA' in cultivo_key else 1
                    max_cultivo_id += 1
                    id_cultivo = max_cultivo_id
                    cur.execute("INSERT INTO cultivos (id, cultivodesc, cultivotipoid) VALUES (%s, %s, %s)", (id_cultivo, cultivo_desc, tipo_cultivo))
                    conn.commit()
                    cultivos_cache[cultivo_key] = (id_cultivo, tipo_cultivo)

                prod_estimada = safe_float(row.get('ProduccionEstimada'))
                prod_obtenida = safe_float(row.get('ProduccionObtenida'))

                agricultura_to_insert.append((
                    ddjj_id, tipo_cultivo, id_cultivo, sup_sembrada, sup_afectada,
                    prod_estimada, prod_obtenida, prod_estimada, prod_obtenida, pondf
                ))

                ponderaciones_to_insert.append((
                    ddjj_id, sup_sembrada, sup_sembrada - sup_afectada, pondf
                ))

            if agricultura_to_insert:
                print(f"Insertando {len(agricultura_to_insert)} registros agrícolas...", flush=True)
                chunked_insert(cur, """
                    INSERT INTO agricultura (ddjj, tipo_cultivo, id_cultivo, sup_sembrada, sup_afectada, prod_estimada, prod_obtenida, estado, lote_expor, estimados, obtenidos, porcentaje)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, '', '', %s, %s, %s)
                """, agricultura_to_insert, conn, chunk_size=50)

                print("Insertando ponderaciones...", flush=True)
                chunked_insert(cur, """
                    INSERT INTO ponderaciones_ddjj (id_ddjj, rubro, estimados, obtenidos, perdidas_ponde)
                    VALUES (%s, 1, %s, %s, %s)
                """, ponderaciones_to_insert, conn, chunk_size=50)

            print("\n¡IMPORTACIÓN COMPLETADA EXITOSAMENTE EN MODO BATCH SEGURO!", flush=True)

    except Exception as e:
        conn.rollback()
        print(f"\nERROR DURANTE LA IMPORTACIÓN (transacción revertida): {e}", file=sys.stderr, flush=True)
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
