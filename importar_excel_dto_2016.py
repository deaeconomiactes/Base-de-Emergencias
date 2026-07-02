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

def main():
    excel_path = ROOT / "Anibal" / "DTO 01-2016" / "DTO 2016-01.xlsx"
    if not excel_path.exists():
        print(f"ERROR: No se encuentra el archivo Excel en {excel_path}", file=sys.stderr)
        sys.exit(1)

    source = os.getenv("DATA_SOURCE", "local").lower()
    print(f"Origen de datos activo: {source}")

    if source == "tidb":
        host = os.getenv("TIDB_HOST")
        port = int(os.getenv("TIDB_PORT", "4000"))
        user = os.getenv("TIDB_USER")
        password = os.getenv("TIDB_PASS")
        database = os.getenv("TIDB_DB", "emergencias")
        ssl_ca = os.getenv("TIDB_SSL_CA", "/etc/ssl/cert.pem")
        ssl = {"ca": ssl_ca} if os.path.exists(ssl_ca) else None
        if not ssl and os.getenv("TIDB_SSL_CA"):
            try:
                import certifi
                ssl = {"ca": certifi.where()}
            except ImportError:
                pass
    else:
        host = os.getenv("MYSQL_HOST", "127.0.0.1")
        port = int(os.getenv("MYSQL_PORT", "3306"))
        user = os.getenv("MYSQL_USER", "root")
        password = os.getenv("MYSQL_PASSWORD", "")
        database = os.getenv("MYSQL_DATABASE", "emergencias")
        ssl = None

    print(f"Conectando a {user}@{host}:{port}/{database}...")
    conn = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        charset="utf8mb4",
        ssl=ssl,
        autocommit=False
    )

    try:
        with conn.cursor() as cur:
            # 1. Asegurar resolución 7
            print("\n--- Asegurando Resolución 7 ---")
            cur.execute("""
                INSERT INTO resoluciones (id_resolucion, nombre_resolucion, numero_resolucion, fec_res, cabeza, pie)
                VALUES (7, 'Emergencia Agropecuaria 2016', '01-2016', '2016-01-01', '', '')
                ON DUPLICATE KEY UPDATE nombre_resolucion=VALUES(nombre_resolucion), numero_resolucion=VALUES(numero_resolucion)
            """)
            print("Resolución 7 asegurada.")

            # Leer Excel
            xl = pd.ExcelFile(excel_path)

            # --- HOJA: AGRICOLA ---
            if 'agric' in xl.sheet_names:
                print("\n--- Procesando hoja 'agric' ---")
                df = xl.parse('agric')
                for idx, row in df.iterrows():
                    denominacion = clean_str(row['ProductorDenominacion'])
                    cuit = clean_cuit(row['CUITCUIL'])
                    doc = clean_doc(row['DocumentoNro'])
                    if not denominacion:
                        continue

                    # Buscar o crear productor
                    prod_id = None
                    if cuit:
                        cur.execute("SELECT ProductorId FROM productores WHERE CUITCUIL = %s", (cuit,))
                        r = cur.fetchone()
                        if r: prod_id = r[0]
                    if not prod_id and doc:
                        cur.execute("SELECT ProductorId FROM productores WHERE DocumentoNro = %s", (doc,))
                        r = cur.fetchone()
                        if r: prod_id = r[0]
                    
                    if not prod_id:
                        cur.execute("""
                            INSERT INTO productores (ProductorDenominacion, CUITCUIL, DocumentoNro, Sexo, renspa, fechaAlta, usuario, DomicilioId, EstablecimientoId)
                            VALUES (%s, %s, %s, 'S', '', '2016-01-01', 1, 0, 0)
                        """, (denominacion, cuit, doc))
                        prod_id = conn.insert_id()
                        print(f"Creado productor nuevo: {denominacion} (ID: {prod_id})")
                    else:
                        print(f"Productor existente encontrado: {denominacion} (ID: {prod_id})")

                    # Calcular pondf
                    sup_sembrada = float(row.get('SuperficiePlantada', 0) or 0)
                    sup_afectada = float(row.get('SuperficieAfectada', 0) or 0)
                    pondf = (sup_afectada / sup_sembrada * 100.0) if sup_sembrada > 0 else 0.0

                    # Buscar o crear Cultivo
                    cultivo_desc = clean_str(row.get('CultivoDesc', 'OTROS'))
                    cur.execute("SELECT id, cultivotipoid FROM cultivos WHERE UPPER(cultivodesc) = %s", (cultivo_desc.upper(),))
                    c_row = cur.fetchone()
                    if c_row:
                        id_cultivo, tipo_cultivo = c_row[0], c_row[1]
                    else:
                        tipo_cultivo = 9 if 'ZAPALLO' in cultivo_desc.upper() or 'MANDIOCA' in cultivo_desc.upper() else 1
                        cur.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM cultivos")
                        next_id = cur.fetchone()[0]
                        cur.execute("INSERT INTO cultivos (id, cultivodesc, cultivotipoid) VALUES (%s, %s, %s)", (next_id, cultivo_desc, tipo_cultivo))
                        id_cultivo = next_id

                    cur.execute("""
                        INSERT INTO ddjj_personas (id_productor, id_resolucion, fecha, nombre, cuit, num_doc, tipo_doc, sexo, provincia, departamento, localidad, paraje, paso, cargado, id_usuario, estado, impreso, fechaimpreso, pondf, dea, renspa, barrio, cod_pos, seccion, calle, sector, piso, manzana, casa, telefono1, telefono2, telefono3)
                        VALUES (%s, 7, '2016-01-01', %s, %s, %s, '1', 'S', 'CORRIENTES', %s, %s, %s, 7, 1, 1, 3, 1, '2016-01-01', %s, 1, '', '', '', '', '', '', '', '', '', '', '', '')
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
                    prod_estimada = float(row.get('ProduccionEstimada', 0) or 0)
                    prod_obtenida = float(row.get('ProduccionObtenida', 0) or 0)
                    cur.execute("""
                        INSERT INTO agricultura (ddjj, tipo_cultivo, id_cultivo, sup_sembrada, sup_afectada, prod_estimada, prod_obtenida, estado, lote_expor, estimados, obtenidos, porcentaje)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, '', '', %s, %s, %s)
                    """, (new_ddjj_id, tipo_cultivo, id_cultivo, sup_sembrada, sup_afectada, prod_estimada, prod_obtenida, prod_estimada, prod_obtenida, pondf))

                    # Insertar ponderaciones_ddjj
                    cur.execute("""
                        INSERT INTO ponderaciones_ddjj (id_ddjj, rubro, estimados, obtenidos, perdidas_ponde)
                        VALUES (%s, 1, %s, %s, %s)
                    """, (new_ddjj_id, sup_sembrada, sup_sembrada - sup_afectada, pondf))

            # --- HOJA: BOVINO ---
            if 'bovino' in xl.sheet_names:
                print("\n--- Procesando hoja 'bovino' ---")
                df = xl.parse('bovino')
                for idx, row in df.iterrows():
                    denominacion = clean_str(row['ProductorDenominacion'])
                    cuit = clean_cuit(row['CUITCUIL'])
                    doc = clean_doc(row['DocumentoNro'])
                    if not denominacion:
                        continue

                    # Buscar o crear productor
                    prod_id = None
                    if cuit:
                        cur.execute("SELECT ProductorId FROM productores WHERE CUITCUIL = %s", (cuit,))
                        r = cur.fetchone()
                        if r: prod_id = r[0]
                    if not prod_id and doc:
                        cur.execute("SELECT ProductorId FROM productores WHERE DocumentoNro = %s", (doc,))
                        r = cur.fetchone()
                        if r: prod_id = r[0]
                    
                    if not prod_id:
                        cur.execute("""
                            INSERT INTO productores (ProductorDenominacion, CUITCUIL, DocumentoNro, Sexo, renspa, fechaAlta, usuario, DomicilioId, EstablecimientoId)
                            VALUES (%s, %s, %s, 'S', '', '2016-01-01', 1, 0, 0)
                        """, (denominacion, cuit, doc))
                        prod_id = conn.insert_id()
                        print(f"Creado productor nuevo: {denominacion} (ID: {prod_id})")
                    else:
                        print(f"Productor existente encontrado: {denominacion} (ID: {prod_id})")

                    # Calcular pondf
                    existenc = int(row.get('Existenc', 0) or 0)
                    mortandad = int(row.get('Mortandad', 0) or 0)
                    pondf = (mortandad / existenc * 100.0) if existenc > 0 else 0.0

                    estado_sol = int(row.get('EstadoSolicitudId', 3) or 3)

                    cur.execute("""
                        INSERT INTO ddjj_personas (id_productor, id_resolucion, fecha, nombre, cuit, num_doc, tipo_doc, sexo, provincia, departamento, localidad, paraje, paso, cargado, id_usuario, estado, impreso, fechaimpreso, pondf, dea, renspa, barrio, cod_pos, seccion, calle, sector, piso, manzana, casa, telefono1, telefono2, telefono3)
                        VALUES (%s, 7, '2016-01-01', %s, %s, %s, '1', 'S', 'CORRIENTES', %s, '', %s, 7, 1, 1, %s, 1, '2016-01-01', %s, 1, '', '', '', '', '', '', '', '', '', '', '', '')
                    """, (
                        prod_id, denominacion, 
                        int(cuit) if cuit and cuit.isdigit() else 0, 
                        int(doc) if doc and doc.isdigit() else 0,
                        clean_str(row.get('DepartamentoDesc', '')),
                        clean_str(row.get('ParajeDesc', '')),
                        estado_sol,
                        pondf
                    ))
                    new_ddjj_id = conn.insert_id()

                    # Insertar bovinos (cantivaca y mortavaca)
                    sup_uso = float(row.get('SupUso', 0) or 0)
                    sup_afect = float(row.get('SupAfect', 0) or 0)
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

            # --- HOJA: APICUL ---
            if 'apicul' in xl.sheet_names:
                print("\n--- Procesando hoja 'apicul' ---")
                df = xl.parse('apicul')
                for idx, row in df.iterrows():
                    denominacion = clean_str(row['ProductorDenominacion'])
                    cuit = clean_cuit(row['CUITCUIL'])
                    doc = clean_doc(row['DocumentoNro'])
                    if not denominacion:
                        continue

                    # Buscar o crear productor
                    prod_id = None
                    if cuit:
                        cur.execute("SELECT ProductorId FROM productores WHERE CUITCUIL = %s", (cuit,))
                        r = cur.fetchone()
                        if r: prod_id = r[0]
                    if not prod_id and doc:
                        cur.execute("SELECT ProductorId FROM productores WHERE DocumentoNro = %s", (doc,))
                        r = cur.fetchone()
                        if r: prod_id = r[0]
                    
                    if not prod_id:
                        cur.execute("""
                            INSERT INTO productores (ProductorDenominacion, CUITCUIL, DocumentoNro, Sexo, renspa, fechaAlta, usuario, DomicilioId, EstablecimientoId)
                            VALUES (%s, %s, %s, 'S', '', '2016-01-01', 1, 0, 0)
                        """, (denominacion, cuit, doc))
                        prod_id = conn.insert_id()
                        print(f"Creado productor nuevo: {denominacion} (ID: {prod_id})")
                    else:
                        print(f"Productor existente encontrado: {denominacion} (ID: {prod_id})")

                    # Apicultura: total colmenas
                    n_colmenas = int(row.get('n\u00ba colmenas', 0) or 0)
                    estado_sol = int(row.get('EstadoSolicitudId', 1) or 1)

                    cur.execute("""
                        INSERT INTO ddjj_personas (id_productor, id_resolucion, fecha, nombre, cuit, num_doc, tipo_doc, sexo, provincia, departamento, localidad, paraje, paso, cargado, id_usuario, estado, impreso, fechaimpreso, pondf, dea, renspa, barrio, cod_pos, seccion, calle, sector, piso, manzana, casa, telefono1, telefono2, telefono3)
                        VALUES (%s, 7, '2016-01-01', %s, %s, %s, '1', 'S', 'CORRIENTES', %s, %s, '', 7, 1, 1, %s, 1, '2016-01-01', 0.0, 1, '', '', '', '', '', '', '', '', '', '', '', '')
                    """, (
                        prod_id, denominacion, 
                        int(cuit) if cuit and cuit.isdigit() else 0, 
                        int(doc) if doc and doc.isdigit() else 0,
                        clean_str(row.get('DepartamentoDesc', '')),
                        clean_str(row.get('LocalidadDesc', '')),
                        estado_sol
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

            # Hacer commit de los cambios
            conn.commit()
            print("\n¡IMPORTACIÓN COMPLETADA EXITOSAMENTE!")

    except Exception as e:
        conn.rollback()
        print(f"\nERROR DURANTE LA IMPORTACIÓN (transacción revertida): {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
