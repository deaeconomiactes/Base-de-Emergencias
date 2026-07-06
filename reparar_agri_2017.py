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

def chunked_insert(cur, query, data, conn, chunk_size=50):
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
            # Leer Excel
            print("Leyendo archivo Excel...", flush=True)
            df = pd.read_excel(excel_path, sheet_name='agric')

            # Cargar cachés
            print("Cargando cachés...", flush=True)
            cur.execute("SELECT CUITCUIL, DocumentoNro, ProductorId FROM productores")
            cuit_to_id = {}
            doc_to_id = {}
            for cuit_db, doc_db, prod_id in cur.fetchall():
                if cuit_db:
                    cuit_to_id[str(cuit_db).strip()] = prod_id
                if doc_db:
                    doc_to_id[str(doc_db).strip()] = prod_id

            cur.execute("SELECT id, cultivodesc, cultivotipoid FROM cultivos")
            cultivos_cache = {}
            max_cultivo_id = 0
            for cid, cdesc, ctipo in cur.fetchall():
                if cdesc:
                    cultivos_cache[cdesc.upper().strip()] = (cid, ctipo)
                if cid > max_cultivo_id:
                    max_cultivo_id = cid

            cur.execute("SELECT id_productor, id_ddjj FROM ddjj_personas WHERE id_resolucion = 10")
            existing_ddjj = {id_prod: id_dj for id_prod, id_dj in cur.fetchall()}
            print(f"Encontradas {len(existing_ddjj)} DDJJs en la base de datos.", flush=True)

            cur.execute("SELECT DISTINCT ddjj FROM agricultura WHERE ddjj IN (SELECT id_ddjj FROM ddjj_personas WHERE id_resolucion = 10)")
            existing_agri = {row[0] for row in cur.fetchall()}
            print(f"Encontrados {len(existing_agri)} registros agrícolas existentes en la base de datos.", flush=True)

            agricultura_to_insert = []
            ponderaciones_to_insert = []

            for idx, row in df.iterrows():
                denominacion = clean_str(row.get('ProductorDenominacion'))
                cuit = clean_cuit(row.get('CUITCUIL'))
                doc = clean_doc(row.get('DocumentoNro'))
                if not denominacion:
                    continue

                prod_id = cuit_to_id.get(cuit) or doc_to_id.get(doc)
                if not prod_id:
                    continue

                ddjj_id = existing_ddjj.get(prod_id)
                if not ddjj_id:
                    continue

                # Si ya tiene registros agrícolas en la BD, no duplicar
                if ddjj_id in existing_agri:
                    continue

                sup_sembrada = safe_float(row.get('SuperficiePlantada'))
                sup_afectada = safe_float(row.get('SuperficieAfectada'))
                pondf = (sup_afectada / sup_sembrada * 100.0) if sup_sembrada > 0 else 0.0

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
                
                # Evitar duplicar en el mismo script
                existing_agri.add(ddjj_id)

            if agricultura_to_insert:
                print(f"Insertando {len(agricultura_to_insert)} registros agrícolas faltantes...", flush=True)
                chunked_insert(cur, """
                    INSERT INTO agricultura (ddjj, tipo_cultivo, id_cultivo, sup_sembrada, sup_afectada, prod_estimada, prod_obtenida, estado, lote_expor, estimados, obtenidos, porcentaje)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, '', '', %s, %s, %s)
                """, agricultura_to_insert, conn, chunk_size=50)

                print("Insertando ponderaciones...", flush=True)
                chunked_insert(cur, """
                    INSERT INTO ponderaciones_ddjj (id_ddjj, rubro, estimados, obtenidos, perdidas_ponde)
                    VALUES (%s, 1, %s, %s, %s)
                """, ponderaciones_to_insert, conn, chunk_size=50)

                print("¡REPARACIÓN COMPLETADA CON ÉXITO!", flush=True)
            else:
                print("No hay registros agrícolas faltantes.", flush=True)

    except Exception as e:
        conn.rollback()
        print(f"\nERROR DURANTE LA REPARACIÓN (transacción revertida): {e}", file=sys.stderr, flush=True)
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
