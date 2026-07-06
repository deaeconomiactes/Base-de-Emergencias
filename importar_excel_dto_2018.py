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

def safe_int(val):
    if pd.isna(val):
        return 0
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return 0

def safe_float(val):
    if pd.isna(val):
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0

def main():
    excel_path = ROOT / "Anibal" / "DTO 763-2018" / "DTO 2018 - 763.xlsx"
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
        read_timeout=30,
        write_timeout=30
    )


    try:
        with conn.cursor() as cur:
            # 1. Asegurar resolución 9
            print("\n--- Asegurando Resolución 9 (DTO 763-2018) ---", flush=True)
            cur.execute("""
                INSERT INTO resoluciones (id_resolucion, nombre_resolucion, numero_resolucion, fec_res, cabeza, pie)
                VALUES (9, 'Emergencia Agropecuaria 2018', '763/18', '2018-01-01', '', '')
                ON DUPLICATE KEY UPDATE nombre_resolucion=VALUES(nombre_resolucion), numero_resolucion=VALUES(numero_resolucion)
            """)
            print("Resolución 9 asegurada.", flush=True)
            conn.commit()

            # Cargar caché de productores
            print("Cargando caché de productores desde la base de datos...", flush=True)
            cur.execute("SELECT CUITCUIL, DocumentoNro, ProductorId FROM productores")
            cuit_to_id = {}
            doc_to_id = {}
            for cuit_db, doc_db, prod_id in cur.fetchall():
                if cuit_db:
                    cuit_to_id[str(cuit_db).strip()] = prod_id
                if doc_db:
                    doc_to_id[str(doc_db).strip()] = prod_id
            print(f"Caché cargada: {len(cuit_to_id)} CUITs y {len(doc_to_id)} Documentos.", flush=True)

            # Cargar caché de cultivos
            print("Cargando caché de cultivos...", flush=True)
            cur.execute("SELECT id, cultivodesc, cultivotipoid FROM cultivos")
            cultivos_cache = {}
            max_cultivo_id = 0
            for cid, cdesc, ctipo in cur.fetchall():
                if cdesc:
                    cultivos_cache[cdesc.upper().strip()] = (cid, ctipo)
                if cid > max_cultivo_id:
                    max_cultivo_id = cid
            
            state = {
                'max_cultivo_id': max_cultivo_id
            }

            # Cargar DDJJs ya importadas para resolución 9 (id_resolucion = 9)
            print("Cargando DDJJs ya importadas para Resolución 9...", flush=True)
            cur.execute("SELECT id_productor, id_ddjj FROM ddjj_personas WHERE id_resolucion = 9")
            existing_ddjj = {id_prod: id_dj for id_prod, id_dj in cur.fetchall()}
            print(f"Encontradas {len(existing_ddjj)} DDJJs ya registradas.", flush=True)

            # Leer Excel
            print("Leyendo archivo Excel...", flush=True)
            xl = pd.ExcelFile(excel_path)
            print(f"Hojas encontradas: {xl.sheet_names}", flush=True)

            # Helper para buscar o crear productor en caché
            def get_or_create_productor(denominacion, cuit, doc):
                prod_id = None
                if cuit and cuit in cuit_to_id:
                    prod_id = cuit_to_id[cuit]
                elif doc and doc in doc_to_id:
                    prod_id = doc_to_id[doc]

                if not prod_id:
                    cur.execute("""
                        INSERT INTO productores (ProductorDenominacion, CUITCUIL, DocumentoNro, Sexo, renspa, fechaAlta, usuario, DomicilioId, EstablecimientoId)
                        VALUES (%s, %s, %s, 'S', '', '2018-01-01', 1, 0, 0)
                    """, (denominacion, cuit, doc))
                    prod_id = conn.insert_id()
                    if cuit:
                        cuit_to_id[cuit] = prod_id
                    if doc:
                        doc_to_id[doc] = prod_id
                return prod_id

            # --- HOJA: AGRICOLA ---
            if 'agric' in xl.sheet_names:
                print("\n--- Procesando hoja 'agric' ---", flush=True)
                df = xl.parse('agric')
                total = len(df)
                for idx, row in df.iterrows():
                    if idx % 50 == 0:
                        print(f"  -> Agric: Procesando fila {idx} de {total}...", flush=True)
                    denominacion = clean_str(row.get('ProductorDenominacion'))
                    cuit = clean_cuit(row.get('CUITCUIL'))
                    doc = clean_doc(row.get('DocumentoNro'))
                    if not denominacion:
                        continue

                    prod_id = get_or_create_productor(denominacion, cuit, doc)

                    # Si ya existe DDJJ para este productor en esta resolución, omitir
                    if prod_id in existing_ddjj:
                        continue

                    # Calcular pondf
                    sup_sembrada = safe_float(row.get('SuperficiePlantada'))
                    sup_afectada = safe_float(row.get('SuperficieAfectada'))
                    pondf = (sup_afectada / sup_sembrada * 100.0) if sup_sembrada > 0 else 0.0

                    # Buscar o crear Cultivo en caché
                    cultivo_desc = clean_str(row.get('CultivoDesc', 'OTROS'))
                    cultivo_key = cultivo_desc.upper().strip()
                    if cultivo_key in cultivos_cache:
                        id_cultivo, tipo_cultivo = cultivos_cache[cultivo_key]
                    else:
                        tipo_cultivo = 9 if 'ZAPALLO' in cultivo_key or 'MANDIOCA' in cultivo_key else 1
                        state['max_cultivo_id'] += 1
                        id_cultivo = state['max_cultivo_id']
                        cur.execute("INSERT INTO cultivos (id, cultivodesc, cultivotipoid) VALUES (%s, %s, %s)", (id_cultivo, cultivo_desc, tipo_cultivo))
                        cultivos_cache[cultivo_key] = (id_cultivo, tipo_cultivo)

                    cur.execute("""
                        INSERT INTO ddjj_personas (id_productor, id_resolucion, fecha, nombre, cuit, num_doc, tipo_doc, sexo, provincia, departamento, localidad, paraje, paso, cargado, id_usuario, estado, impreso, fechaimpreso, pondf, dea, renspa, barrio, cod_pos, seccion, calle, sector, piso, manzana, casa, telefono1, telefono2, telefono3)
                        VALUES (%s, 9, '2018-01-01', %s, %s, %s, '1', 'S', 'CORRIENTES', %s, %s, %s, 9, 1, 1, 3, 1, '2018-01-01', %s, 1, '', '', '', '', '', '', '', '', '', '', '', '')
                    """, (
                        prod_id, denominacion, 
                        int(cuit) if cuit and cuit.isdigit() else 0, 
                        int(doc) if doc and doc.isdigit() else 0,
                        clean_str(row.get('DepartamentoDesc', '')),
                        clean_str(row.get('LocalidadDesc', '')),
                        clean_str(row.get('ParajeDesc', '')),
                        pondf
                    ))
                    new_ddjj_id = conn.insert_id()

                    # Insertar agricultura
                    prod_estimada = safe_float(row.get('ProduccionEstimada'))
                    prod_obtenida = safe_float(row.get('ProduccionObtenida'))
                    cur.execute("""
                        INSERT INTO agricultura (ddjj, tipo_cultivo, id_cultivo, sup_sembrada, sup_afectada, prod_estimada, prod_obtenida, estado, lote_expor, estimados, obtenidos, porcentaje)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, '', '', %s, %s, %s)
                    """, (new_ddjj_id, tipo_cultivo, id_cultivo, sup_sembrada, sup_afectada, prod_estimada, prod_obtenida, prod_estimada, prod_obtenida, pondf))

                    # Insertar ponderaciones_ddjj
                    cur.execute("""
                        INSERT INTO ponderaciones_ddjj (id_ddjj, rubro, estimados, obtenidos, perdidas_ponde)
                        VALUES (%s, 1, %s, %s, %s)
                    """, (new_ddjj_id, sup_sembrada, sup_sembrada - sup_afectada, pondf))

                    if idx % 20 == 0:
                        conn.commit()

                conn.commit()

            # --- HOJA: BOVINO ---
            if 'bovino' in xl.sheet_names:
                print("\n--- Procesando hoja 'bovino' ---", flush=True)
                df = xl.parse('bovino')
                total = len(df)
                for idx, row in df.iterrows():
                    if idx % 50 == 0:
                        print(f"  -> Bovino: Procesando fila {idx} de {total}...", flush=True)
                    denominacion = clean_str(row.get('ProductorDenominacion'))
                    cuit = clean_cuit(row.get('CUITCUIL'))
                    doc = clean_doc(row.get('DocumentoNro'))
                    if not denominacion:
                        continue

                    prod_id = get_or_create_productor(denominacion, cuit, doc)

                    # Si ya existe DDJJ para este productor en esta resolución, omitir
                    if prod_id in existing_ddjj:
                        continue

                    # Calcular pondf
                    existenc = safe_int(row.get('Existenc'))
                    mortandad = safe_int(row.get('Mortandad'))
                    pondf = (mortandad / existenc * 100.0) if existenc > 0 else 0.0

                    cur.execute("""
                        INSERT INTO ddjj_personas (id_productor, id_resolucion, fecha, nombre, cuit, num_doc, tipo_doc, sexo, provincia, departamento, localidad, paraje, paso, cargado, id_usuario, estado, impreso, fechaimpreso, pondf, dea, renspa, barrio, cod_pos, seccion, calle, sector, piso, manzana, casa, telefono1, telefono2, telefono3)
                        VALUES (%s, 9, '2018-01-01', %s, %s, %s, '1', 'S', 'CORRIENTES', %s, '', %s, 9, 1, 1, 3, 1, '2018-01-01', %s, 1, '', '', '', '', '', '', '', '', '', '', '', '')
                    """, (
                        prod_id, denominacion, 
                        int(cuit) if cuit and cuit.isdigit() else 0, 
                        int(doc) if doc and doc.isdigit() else 0,
                        clean_str(row.get('DepartamentoDesc', '')),
                        clean_str(row.get('ParajeDesc', '')),
                        pondf
                    ))
                    new_ddjj_id = conn.insert_id()

                    # Insertar bovinos
                    sup_uso = safe_float(row.get('SupUso'))
                    sup_afect = safe_float(row.get('SupAfect'))
                    cur.execute("""
                        INSERT INTO bovinos (
                            idddjj, supuso, supafe, superdida, superdidaesti,
                            precvaca, cantivaca, mortavaca, vaestimada, vaobtenida, vaperdida,
                            precvaqui, cantivaqui, mortavaqui, vaquiestimada, vaquiobtenida, vaquiperdida,
                            precterne, cantiterne, mortaterne, terestimada, terobtenida, tereperdida,
                            precnovi, cantinovi, mortanovi, novestimada, novobtenida, noveperdida,
                            precnovilli, cantinovilli, mortanovilli, novilliestimada, novilliobtenida, novilliperdida,
                            prectoro, cantitoro, mortatoro, toroestimada, torobtenida, toroperdida,
                            precbufa, cantibufa, mortabufa, bufaestimada, bufaobtenida, bufaperdida,
                            precarne, prodespe, prodobte, carnestimada, carneobtenida, carneperdida
                        ) VALUES (
                            %s, %s, %s, %s, 0.0,
                            0.0, %s, %s, 0.0, 0.0, 0.0,
                            0.0, 0, 0, 0.0, 0.0, 0.0,
                            0.0, 0, 0, 0.0, 0.0, 0.0,
                            0.0, 0, 0, 0.0, 0.0, 0.0,
                            0.0, 0, 0, 0.0, 0.0, 0.0,
                            0.0, 0, 0, 0.0, 0.0, 0.0,
                            0.0, 0, 0, 0.0, 0.0, 0.0,
                            0.0, 0, 0, 0.0, 0.0, 0.0
                        )
                    """, (new_ddjj_id, int(sup_uso), int(sup_afect), pondf, existenc, mortandad))

                    # Insertar ponderaciones_ddjj
                    cur.execute("""
                        INSERT INTO ponderaciones_ddjj (id_ddjj, rubro, estimados, obtenidos, perdidas_ponde)
                        VALUES (%s, 2, %s, %s, %s)
                    """, (new_ddjj_id, float(existenc), float(existenc - mortandad), pondf))

                    if idx % 20 == 0:
                        conn.commit()

                conn.commit()

            # --- HOJA: OVINO ---
            if 'ovino' in xl.sheet_names:
                print("\n--- Procesando hoja 'ovino' ---", flush=True)
                df = xl.parse('ovino')
                total = len(df)
                for idx, row in df.iterrows():
                    if idx % 50 == 0:
                        print(f"  -> Ovino: Procesando fila {idx} de {total}...", flush=True)
                    denominacion = clean_str(row.get('ProductorDenominacion'))
                    cuit = clean_cuit(row.get('CUITCUIL'))
                    doc = clean_doc(row.get('DocumentoNro'))
                    if not denominacion:
                        continue

                    prod_id = get_or_create_productor(denominacion, cuit, doc)

                    # Si ya existe DDJJ para este productor en esta resolución, omitir
                    if prod_id in existing_ddjj:
                        continue

                    # Calcular pondf
                    existenc = safe_int(row.get('Existenc'))
                    mortandad = safe_int(row.get('Mortandad'))
                    pondf = (mortandad / existenc * 100.0) if existenc > 0 else 0.0

                    cur.execute("""
                        INSERT INTO ddjj_personas (id_productor, id_resolucion, fecha, nombre, cuit, num_doc, tipo_doc, sexo, provincia, departamento, localidad, paraje, paso, cargado, id_usuario, estado, impreso, fechaimpreso, pondf, dea, renspa, barrio, cod_pos, seccion, calle, sector, piso, manzana, casa, telefono1, telefono2, telefono3)
                        VALUES (%s, 9, '2018-01-01', %s, %s, %s, '1', 'S', 'CORRIENTES', %s, '', %s, 9, 1, 1, 3, 1, '2018-01-01', %s, 1, '', '', '', '', '', '', '', '', '', '', '', '')
                    """, (
                        prod_id, denominacion, 
                        int(cuit) if cuit and cuit.isdigit() else 0, 
                        int(doc) if doc and doc.isdigit() else 0,
                        clean_str(row.get('DepartamentoDesc', '')),
                        clean_str(row.get('ParajeDesc', '')),
                        pondf
                    ))
                    new_ddjj_id = conn.insert_id()

                    # Insertar ovinos
                    sup_uso = safe_float(row.get('SupUso'))
                    sup_afect = safe_float(row.get('SupAfect'))
                    cur.execute("""
                        INSERT INTO ovinos (
                            idddjj, supuso, supafe, precovi, canticabe, mortacabe,
                            oviestimada, oviobtenida, oviperdida, prodcor, corobte,
                            preclana, prodlana, lanaobte, estilana, obtelana, perdilana
                        ) VALUES (
                            %s, %s, %s, 0.0, %s, %s,
                            0.0, 0.0, 0.0, 0, 0,
                            0.0, 0, 0, 0.0, 0.0, 0.0
                        )
                    """, (new_ddjj_id, int(sup_uso), int(sup_afect), existenc, mortandad))

                    # Insertar ponderaciones_ddjj
                    cur.execute("""
                        INSERT INTO ponderaciones_ddjj (id_ddjj, rubro, estimados, obtenidos, perdidas_ponde)
                        VALUES (%s, 2, %s, %s, %s)
                    """, (new_ddjj_id, float(existenc), float(existenc - mortandad), pondf))

                    if idx % 20 == 0:
                        conn.commit()

                conn.commit()

            # --- HOJA: APICUL ---
            if 'apicul' in xl.sheet_names:
                print("\n--- Procesando hoja 'apicul' ---", flush=True)
                df = xl.parse('apicul')
                total = len(df)
                for idx, row in df.iterrows():
                    denominacion = clean_str(row.get('ProductorDenominacion'))
                    cuit = clean_cuit(row.get('CUITCUIL'))
                    doc = clean_doc(row.get('DocumentoNro'))
                    if not denominacion:
                        continue

                    prod_id = get_or_create_productor(denominacion, cuit, doc)

                    # Si ya existe DDJJ para este productor en esta resolución, omitir
                    if prod_id in existing_ddjj:
                        continue

                    # Apicultura: total colmenas
                    colmenas_col = [c for c in row.keys() if 'COLMENAS' in str(c).upper()]
                    n_colmenas = safe_int(row.get(colmenas_col[0])) if colmenas_col else 0

                    cur.execute("""
                        INSERT INTO ddjj_personas (id_productor, id_resolucion, fecha, nombre, cuit, num_doc, tipo_doc, sexo, provincia, departamento, localidad, paraje, paso, cargado, id_usuario, estado, impreso, fechaimpreso, pondf, dea, renspa, barrio, cod_pos, seccion, calle, sector, piso, manzana, casa, telefono1, telefono2, telefono3)
                        VALUES (%s, 9, '2018-01-01', %s, %s, %s, '1', 'S', 'CORRIENTES', %s, %s, '', 9, 1, 1, 3, 1, '2018-01-01', 0.0, 1, '', '', '', '', '', '', '', '', '', '', '', '')
                    """, (
                        prod_id, denominacion, 
                        int(cuit) if cuit and cuit.isdigit() else 0, 
                        int(doc) if doc and doc.isdigit() else 0,
                        clean_str(row.get('DepartamentoDesc', '')),
                        clean_str(row.get('LocalidadDesc', ''))
                    ))
                    new_ddjj_id = conn.insert_id()

                    # Insertar apicultura
                    cur.execute("""
                        INSERT INTO apicultura (idddjj, precapi, cantcol, canafec, colestimada, colobtenida, colperdida, precmiel, prodnormiel, prodobtemiel, mielestimada, mielobtenida, mielperdida)
                        VALUES (%s, 0.0, %s, %s, 0.0, 0.0, 0.0, 0.0, 0, 0, 0.0, 0.0, 0.0)
                    """, (new_ddjj_id, n_colmenas, n_colmenas))

                    # Insertar ponderaciones_ddjj
                    cur.execute("""
                        INSERT INTO ponderaciones_ddjj (id_ddjj, rubro, estimados, obtenidos, perdidas_ponde)
                        VALUES (%s, 2, %s, %s, 0.0)
                    """, (new_ddjj_id, float(n_colmenas), float(n_colmenas)))

                    if idx % 20 == 0:
                        conn.commit()

                conn.commit()

            print("\n¡IMPORTACIÓN COMPLETADA EXITOSAMENTE!", flush=True)

    except Exception as e:
        conn.rollback()
        print(f"\nERROR DURANTE LA IMPORTACIÓN (transacción revertida): {e}", file=sys.stderr, flush=True)
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
