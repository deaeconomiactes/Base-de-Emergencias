import pymysql
import random
import datetime

def main():
    print("Conectando al servidor local de MySQL...")
    conn = pymysql.connect(
        host="127.0.0.1",
        port=3306,
        user="root",
        password="",
        charset="utf8mb4"
    )
    
    try:
        with conn.cursor() as cur:
            # Recrear la base de datos emergencias
            cur.execute("CREATE DATABASE IF NOT EXISTS `emergencias` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            cur.execute("USE `emergencias`")
            
            # 1. Crear tablas de catálogos
            print("Creando tablas de catálogos...")
            
            cur.execute("""
            CREATE TABLE IF NOT EXISTS `resoluciones` (
                `id_resolucion` INT AUTO_INCREMENT PRIMARY KEY,
                `nombre_resolucion` VARCHAR(255),
                `numero_resolucion` VARCHAR(50),
                `fec_res` DATE
            ) ENGINE=InnoDB;
            """)
            
            cur.execute("""
            CREATE TABLE IF NOT EXISTS `tipoactividad` (
                `TipoActividadId` INT PRIMARY KEY,
                `TipoActividadDesc` VARCHAR(255)
            ) ENGINE=InnoDB;
            """)
            
            cur.execute("""
            CREATE TABLE IF NOT EXISTS `tipojuridico` (
                `TipoJuridicoId` INT PRIMARY KEY,
                `TipoJuridicoDesc` VARCHAR(255)
            ) ENGINE=InnoDB;
            """)
            
            cur.execute("""
            CREATE TABLE IF NOT EXISTS `tipodocumento` (
                `TipoDocumentoId` INT PRIMARY KEY,
                `TipoDocumentoDescripcion` VARCHAR(50)
            ) ENGINE=InnoDB;
            """)
            
            cur.execute("""
            CREATE TABLE IF NOT EXISTS `provincias` (
                `ProvinciaId` INT PRIMARY KEY,
                `ProvinciaDesc` VARCHAR(100)
            ) ENGINE=InnoDB;
            """)
            
            cur.execute("""
            CREATE TABLE IF NOT EXISTS `departamentos` (
                `DepartamentoId` INT PRIMARY KEY,
                `DepartamentoDesc` VARCHAR(100),
                `ProvinciaId` INT
            ) ENGINE=InnoDB;
            """)
            
            cur.execute("""
            CREATE TABLE IF NOT EXISTS `localidades` (
                `LocalidadId` INT PRIMARY KEY,
                `LocalidadDesc` VARCHAR(100),
                `DepartamentoId` INT
            ) ENGINE=InnoDB;
            """)
            
            cur.execute("""
            CREATE TABLE IF NOT EXISTS `domicilios` (
                `DomicilioId` INT AUTO_INCREMENT PRIMARY KEY,
                `ProvinciaId` INT,
                `DepartamentoId` INT,
                `LocalidadId` INT,
                `Direccion` VARCHAR(255)
            ) ENGINE=InnoDB;
            """)
            
            cur.execute("""
            CREATE TABLE IF NOT EXISTS `tipotenencia` (
                `id` INT PRIMARY KEY,
                `descripcion` VARCHAR(100)
            ) ENGINE=InnoDB;
            """)
            
            cur.execute("""
            CREATE TABLE IF NOT EXISTS `rubro_tipos` (
                `id_rubro` INT PRIMARY KEY,
                `nombre` VARCHAR(100)
            ) ENGINE=InnoDB;
            """)
            
            cur.execute("""
            CREATE TABLE IF NOT EXISTS `cultivostipo` (
                `id` INT PRIMARY KEY,
                `CultivoTipoDesc` VARCHAR(100)
            ) ENGINE=InnoDB;
            """)
            
            cur.execute("""
            CREATE TABLE IF NOT EXISTS `cultivos` (
                `id` INT PRIMARY KEY,
                `cultivodesc` VARCHAR(100),
                `cultivotipoid` INT
            ) ENGINE=InnoDB;
            """)
            
            # 2. Crear tablas de negocio
            print("Creando tablas de negocio...")
            
            cur.execute("""
            CREATE TABLE IF NOT EXISTS `productores` (
                `ProductorId` INT AUTO_INCREMENT PRIMARY KEY,
                `ProductorDenominacion` VARCHAR(255),
                `CUITCUIL` VARCHAR(50),
                `TipoDocumentoId` INT,
                `DocumentoNro` VARCHAR(50) UNIQUE,
                `Sexo` CHAR(1),
                `EsPrincipalActividadEconomica` INT,
                `TipoJuridicoId` INT,
                `DomicilioId` INT,
                `renspa` VARCHAR(100)
            ) ENGINE=InnoDB;
            """)
            
            cur.execute("""
            CREATE TABLE IF NOT EXISTS `ddjj_personas` (
                `id_ddjj` INT AUTO_INCREMENT PRIMARY KEY,
                `id_productor` INT,
                `id_resolucion` INT,
                `fecha` DATE,
                `nombre` VARCHAR(255),
                `tipo_doc` VARCHAR(50),
                `num_doc` VARCHAR(50),
                `cuit` VARCHAR(50),
                `renspa` VARCHAR(100),
                `provincia` VARCHAR(100),
                `departamento` VARCHAR(100),
                `localidad` VARCHAR(100),
                `paraje` VARCHAR(100),
                `pondf` FLOAT,
                `cargado` INT,
                `estado` VARCHAR(50)
            ) ENGINE=InnoDB;
            """)
            
            cur.execute("""
            CREATE TABLE IF NOT EXISTS `ponderaciones_ddjj` (
                `id_ponderacion` INT AUTO_INCREMENT PRIMARY KEY,
                `id_ddjj` INT,
                `rubro` INT,
                `estimados` FLOAT,
                `obtenidos` FLOAT,
                `perdidas_ponde` FLOAT
            ) ENGINE=InnoDB;
            """)
            
            cur.execute("""
            CREATE TABLE IF NOT EXISTS `agricultura` (
                `id_agricultura` INT AUTO_INCREMENT PRIMARY KEY,
                `ddjj` INT,
                `tipo_cultivo` INT,
                `id_cultivo` INT,
                `sup_sembrada` FLOAT,
                `sup_afectada` FLOAT,
                `prod_estimada` FLOAT,
                `prod_obtenida` FLOAT,
                `estado` VARCHAR(50),
                `porcentaje` FLOAT
            ) ENGINE=InnoDB;
            """)
            
            cur.execute("""
            CREATE TABLE IF NOT EXISTS `bovinos` (
                `idddjj` INT PRIMARY KEY,
                `cantivaca` INT,
                `cantivaqui` INT,
                `cantiterne` INT,
                `cantinovi` INT,
                `cantinovilli` INT,
                `cantitoro` INT,
                `cantibufa` INT,
                `prodespe` FLOAT,
                `prodobte` FLOAT,
                `carnestimada` FLOAT,
                `carneobtenida` FLOAT,
                `carneperdida` FLOAT,
                `mortavaca` INT,
                `mortavaqui` INT,
                `mortaterne` INT,
                `mortanovi` INT,
                `mortanovilli` INT,
                `mortatoro` INT,
                `mortabufa` INT
            ) ENGINE=InnoDB;
            """)
            
            cur.execute("""
            CREATE TABLE IF NOT EXISTS `ovinos` (
                `idddjj` INT PRIMARY KEY,
                `canticabe` INT,
                `mortacabe` INT,
                `prodcor` FLOAT,
                `corobte` FLOAT,
                `prodlana` FLOAT,
                `lanaobte` FLOAT,
                `perdilana` FLOAT
            ) ENGINE=InnoDB;
            """)
            
            cur.execute("""
            CREATE TABLE IF NOT EXISTS `porcinos` (
                `idddjj` INT PRIMARY KEY,
                `canticabe` INT,
                `mortacabe` INT,
                `prodcor` FLOAT,
                `corobte` FLOAT
            ) ENGINE=InnoDB;
            """)
            
            cur.execute("""
            CREATE TABLE IF NOT EXISTS `avicultura` (
                `idddjj` INT PRIMARY KEY,
                `existencia` INT,
                `perdida` INT,
                `prodnor` FLOAT,
                `prodobte` FLOAT
            ) ENGINE=InnoDB;
            """)
            
            cur.execute("""
            CREATE TABLE IF NOT EXISTS `apicultura` (
                `idddjj` INT PRIMARY KEY,
                `cantcol` INT,
                `canafec` INT,
                `prodnormiel` FLOAT,
                `prodobtemiel` FLOAT,
                `mielperdida` FLOAT
            ) ENGINE=InnoDB;
            """)
            
            cur.execute("""
            CREATE TABLE IF NOT EXISTS `forestacion` (
                `idddjj` INT PRIMARY KEY,
                `supuso` FLOAT,
                `supafe` FLOAT,
                `superdida` FLOAT,
                `prodmaes` FLOAT,
                `prodmaob` FLOAT,
                `madestimada` FLOAT,
                `madeperdida` FLOAT,
                `prodposes` FLOAT,
                `posteperdida` FLOAT,
                `prodreses` FLOAT,
                `resiperdida` FLOAT
            ) ENGINE=InnoDB;
            """)
            
            cur.execute("""
            CREATE TABLE IF NOT EXISTS `perdidas_mejoras` (
                `id_perdida_mejora` INT AUTO_INCREMENT PRIMARY KEY,
                `idddjj` INT,
                `mejora` VARCHAR(100),
                `vestimado` FLOAT,
                `incidencia` FLOAT,
                `pesesp` FLOAT,
                `pesper` FLOAT
            ) ENGINE=InnoDB;
            """)
            
            cur.execute("""
            CREATE TABLE IF NOT EXISTS `perdidas_invernaculos` (
                `id_perdida_invernaculo` INT AUTO_INCREMENT PRIMARY KEY,
                `ddjj` INT,
                `cobertura_plasticas` FLOAT,
                `estructuras` FLOAT,
                `supsemb` FLOAT,
                `supafect` FLOAT,
                `coberplastiperdi` FLOAT,
                `danoplastiperdi` FLOAT
            ) ENGINE=InnoDB;
            """)
            
            cur.execute("""
            CREATE TABLE IF NOT EXISTS `perdidas_plurianuales` (
                `id_perdida_plurianual` INT AUTO_INCREMENT PRIMARY KEY,
                `ddjj` INT,
                `cobertura_plantas` FLOAT,
                `coberperdi` FLOAT,
                `dano_planta` FLOAT,
                `danoperdi` FLOAT
            ) ENGINE=InnoDB;
            """)
            
            cur.execute("""
            CREATE TABLE IF NOT EXISTS `establecimientos` (
                `id_establecimiento` INT AUTO_INCREMENT PRIMARY KEY,
                `ddjj` INT,
                `nombre_estab` VARCHAR(255),
                `departamento_estab` VARCHAR(100),
                `paraje_estab` VARCHAR(100),
                `latitud` VARCHAR(50),
                `longitud` VARCHAR(50),
                `corenea` VARCHAR(100)
            ) ENGINE=InnoDB;
            """)
            
            cur.execute("""
            CREATE TABLE IF NOT EXISTS `adremas` (
                `id_adrema` INT AUTO_INCREMENT PRIMARY KEY,
                `ddjj` INT,
                `id_establecimiento` INT,
                `adrema` VARCHAR(100),
                `superficie` FLOAT,
                `actividad` INT,
                `tenencia` INT,
                `departamento` VARCHAR(100)
            ) ENGINE=InnoDB;
            """)
            
            cur.execute("""
            CREATE TABLE IF NOT EXISTS `documentacion` (
                `id` INT AUTO_INCREMENT PRIMARY KEY,
                `idddjj` INT,
                `codigo` VARCHAR(50),
                `documentacion` VARCHAR(255),
                `marcar` INT
            ) ENGINE=InnoDB;
            """)
            
            cur.execute("""
            CREATE TABLE IF NOT EXISTS `fotos` (
                `id` INT AUTO_INCREMENT PRIMARY KEY,
                `iddjj` INT,
                `file` VARCHAR(255)
            ) ENGINE=InnoDB;
            """)
            
            # 3. Insertar Catálogos Básicos
            print("Poblando catálogos...")
            
            cur.executemany("""
            INSERT INTO `tipoactividad` (`TipoActividadId`, `TipoActividadDesc`) VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE `TipoActividadDesc` = VALUES(`TipoActividadDesc`)
            """, [
                (1, "AG - AGRICULTURA"),
                (2, "GA - GANADERIA"),
                (3, "BM - BOSQ./MONTES")
            ])
            
            cur.executemany("""
            INSERT INTO `tipojuridico` (`TipoJuridicoId`, `TipoJuridicoDesc`) VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE `TipoJuridicoDesc` = VALUES(`TipoJuridicoDesc`)
            """, [
                (1, "Persona Física"),
                (2, "S.A."),
                (3, "S.R.L."),
                (4, "Sociedad de Hecho")
            ])
            
            cur.executemany("""
            INSERT INTO `tipodocumento` (`TipoDocumentoId`, `TipoDocumentoDescripcion`) VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE `TipoDocumentoDescripcion` = VALUES(`TipoDocumentoDescripcion`)
            """, [
                (1, "DNI"),
                (2, "CUIT/CUIL"),
                (3, "LC"),
                (4, "LE")
            ])
            
            cur.executemany("""
            INSERT INTO `provincias` (`ProvinciaId`, `ProvinciaDesc`) VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE `ProvinciaDesc` = VALUES(`ProvinciaDesc`)
            """, [
                (1, "CORRIENTES")
            ])
            
            deptos = [
                (1, "Goya", 1),
                (2, "Mercedes", 1),
                (3, "Curuzú Cuatiá", 1),
                (4, "Bella Vista", 1),
                (5, "Santo Tomé", 1),
                (6, "Esquina", 1),
                (7, "Mercedes", 1)
            ]
            cur.executemany("""
            INSERT INTO `departamentos` (`DepartamentoId`, `DepartamentoDesc`, `ProvinciaId`) VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE `DepartamentoDesc` = VALUES(`DepartamentoDesc`)
            """, deptos)
            
            localidades = [
                (1, "Goya", 1),
                (2, "Mercedes", 2),
                (3, "Curuzú Cuatiá", 3),
                (4, "Bella Vista", 4),
                (5, "Santo Tomé", 5),
                (6, "Esquina", 6),
                (7, "Mercedes", 7)
            ]
            cur.executemany("""
            INSERT INTO `localidades` (`LocalidadId`, `LocalidadDesc`, `DepartamentoId`) VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE `LocalidadDesc` = VALUES(`LocalidadDesc`)
            """, localidades)
            
            cur.executemany("""
            INSERT INTO `tipotenencia` (`id`, `descripcion`) VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE `descripcion` = VALUES(`descripcion`)
            """, [
                (1, "Propiedad"),
                (2, "Arrendamiento"),
                (3, "Aparcería"),
                (4, "Ocupación")
            ])
            
            cur.executemany("""
            INSERT INTO `rubro_tipos` (`id_rubro`, `nombre`) VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE `nombre` = VALUES(`nombre`)
            """, [
                (1, "Agrícola"),
                (2, "Ganadería"),
                (3, "Forestal"),
                (4, "Otros")
            ])
            
            cur.executemany("""
            INSERT INTO `cultivostipo` (`id`, `CultivoTipoDesc`) VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE `CultivoTipoDesc` = VALUES(`CultivoTipoDesc`)
            """, [
                (1, "Cereales y Oleaginosas"),
                (2, "Citrus"),
                (3, "Horticultura"),
                (4, "Plurianuales")
            ])
            
            cur.executemany("""
            INSERT INTO `cultivos` (`id`, `cultivodesc`, `cultivotipoid`) VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE `cultivodesc` = VALUES(`cultivodesc`)
            """, [
                (1, "Arroz", 1),
                (2, "Maíz", 1),
                (3, "Naranja", 2),
                (4, "Limón", 2),
                (5, "Mandarina", 2),
                (6, "Tomate", 3),
                (7, "Pimiento", 3)
            ])
            
            resoluciones = [
                (1, "EMERGENCIA AGROPECUARIA 32/19 - SEQUIA", "32/19", "2019-03-15"),
                (2, "EMERGENCIA AGROPECUARIA 105/22 - INCENDIOS", "105/22", "2022-02-10"),
                (3, "EMERGENCIA AGROPECUARIA 05/25 - INUNDACIONES", "05/25", "2025-01-20")
            ]
            cur.executemany("""
            INSERT INTO `resoluciones` (`id_resolucion`, `nombre_resolucion`, `numero_resolucion`, `fec_res`) VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE `nombre_resolucion` = VALUES(`nombre_resolucion`)
            """, resoluciones)
            
            # 4. Insertar Productores y Domicilios
            print("Poblando productores...")
            nombres_prod = [
                "Establecimiento Las Marías", "Don Juan S.R.L.", "Agropecuaria Correntina S.A.",
                "Finca El Dorado", "La Posta De Goya", "Mercedes Ganadera",
                "Juan Carlos Pérez", "María Elena Rodríguez", "Estancia San Pedro",
                "Cabaña Los Pinos", "Forestal Ituzaingó", "Cooperativa San Roque"
            ]
            
            random.seed(42)
            
            for i, nombre in enumerate(nombres_prod, 1):
                # Crear domicilio
                depto = random.choice(deptos)
                cur.execute("""
                INSERT INTO `domicilios` (`ProvinciaId`, `DepartamentoId`, `LocalidadId`, `Direccion`)
                VALUES (1, %s, %s, %s)
                """, (depto[0], depto[0], f"Ruta Nacional 12, Km {random.randint(10, 300)}"))
                dom_id = conn.insert_id()
                
                cuit = f"20-{random.randint(10000000, 35000000)}-{random.randint(0, 9)}"
                doc = cuit.split("-")[1]
                sexo = random.choice(["M", "F", "S"])
                act = random.choice([1, 2, 3])
                jur = random.choice([1, 2, 3, 4])
                renspa = f"12.{random.randint(100, 999)}.{random.randint(0, 9)}.{random.randint(1000, 9999)}/00"
                
                cur.execute("""
                INSERT INTO `productores` (`ProductorId`, `ProductorDenominacion`, `CUITCUIL`, `TipoDocumentoId`, `DocumentoNro`, `Sexo`, `EsPrincipalActividadEconomica`, `TipoJuridicoId`, `DomicilioId`, `renspa`)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (i, nombre, cuit, 2 if jur > 1 else 1, doc, sexo, act, jur, dom_id, renspa))
                
            # 5. Insertar DDJJ, Establecimientos y Rubros
            print("Poblando DDJJ y datos relacionados...")
            
            # Coordenadas realistas de Corrientes: latitud -27 a -30, longitud -56 a -59
            lat_base = -28.5
            lng_base = -58.2
            
            ddjj_id = 1
            for prod_id in range(1, 13):
                # Cada productor tiene 1 o 2 declaraciones juradas en diferentes resoluciones
                for res in random.sample(resoluciones, random.randint(1, 2)):
                    res_id = res[0]
                    fecha = datetime.date(2025, random.randint(2, 6), random.randint(1, 28))
                    
                    # Cargar datos desnormalizados del productor
                    cur.execute("SELECT ProductorDenominacion, CUITCUIL, DocumentoNro, renspa, DomicilioId FROM productores WHERE ProductorId=%s", (prod_id,))
                    p_row = cur.fetchone()
                    
                    cur.execute("SELECT d.DepartamentoId, dep.DepartamentoDesc, l.LocalidadDesc FROM domicilios d JOIN departamentos dep ON dep.DepartamentoId=d.DepartamentoId JOIN localidades l ON l.LocalidadId=d.LocalidadId WHERE d.DomicilioId=%s", (p_row[4],))
                    geo_row = cur.fetchone()
                    
                    depto_name = geo_row[1]
                    loc_name = geo_row[2]
                    paraje = f"Paraje Tres Bocas"
                    
                    pondf = random.uniform(30.0, 95.0)
                    estado = random.choice(["APROBADO", "PENDIENTE", "EN REVISION"])
                    
                    cur.execute("""
                    INSERT INTO `ddjj_personas` (`id_ddjj`, `id_productor`, `id_resolucion`, `fecha`, `nombre`, `tipo_doc`, `num_doc`, `cuit`, `renspa`, `provincia`, `departamento`, `localidad`, `paraje`, `pondf`, `cargado`, `estado`)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'CORRIENTES', %s, %s, %s, %s, 1, %s)
                    """, (ddjj_id, prod_id, res_id, fecha, p_row[0], "CUIT", p_row[2], p_row[1], p_row[3], depto_name, loc_name, paraje, pondf, estado))
                    
                    # 5.1 Establecimiento
                    lat = lat_base + random.uniform(-1.0, 1.0)
                    lng = lng_base + random.uniform(-1.0, 1.0)
                    # Formatear lat/lng con punto perdido como en fix_coord del proyecto original
                    lat_str = str(int(lat * 100000000))
                    lng_str = str(int(lng * 100000000))
                    
                    cur.execute("""
                    INSERT INTO `establecimientos` (`ddjj`, `nombre_estab`, `departamento_estab`, `paraje_estab`, `latitud`, `longitud`, `corenea`)
                    VALUES (%s, %s, %s, %s, %s, %s, 'CORENEA_MOCK')
                    """, (ddjj_id, f"Finca {p_row[0]}", depto_name, paraje, lat_str, lng_str))
                    est_id = conn.insert_id()
                    
                    # 5.2 Adremas
                    num_adremas = random.randint(1, 3)
                    for adr_idx in range(num_adremas):
                        adrema_num = f"A1-{random.randint(10000, 99999)}-{random.randint(1, 9)}"
                        superficie = random.uniform(50.0, 500.0)
                        tenencia = random.choice([1, 2, 3])
                        actividad = random.choice([1, 2, 3])
                        cur.execute("""
                        INSERT INTO `adremas` (`ddjj`, `id_establecimiento`, `adrema`, `superficie`, `actividad`, `tenencia`, `departamento`)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """, (ddjj_id, est_id, adrema_num, superficie, actividad, tenencia, depto_name))
                    
                    # 5.3 Rubros de Poderaciones
                    for rub in range(1, 5):
                        estimados = random.uniform(100000, 2000000)
                        perdida_pct = random.uniform(20.0, 90.0) if rub in (1, 2) else 0.0
                        obtenidos = estimados * (1 - (perdida_pct/100))
                        cur.execute("""
                        INSERT INTO `ponderaciones_ddjj` (`id_ddjj`, `rubro`, `estimados`, `obtenidos`, `perdidas_ponde`)
                        VALUES (%s, %s, %s, %s, %s)
                        """, (ddjj_id, rub, estimados, obtenidos, perdida_pct))
                    
                    # 5.4 Producción Declarada - Agricultura
                    if random.choice([True, False]):
                        for _ in range(random.randint(1, 2)):
                            cult = random.choice([1, 2, 3, 4, 5, 6, 7])
                            cur.execute("SELECT cultivodesc, cultivotipoid FROM cultivos WHERE id=%s", (cult,))
                            c_info = cur.fetchone()
                            
                            sup_sem = random.uniform(20.0, 150.0)
                            sup_afec = sup_sem * random.uniform(0.3, 1.0)
                            cur.execute("""
                            INSERT INTO `agricultura` (`ddjj`, `tipo_cultivo`, `id_cultivo`, `sup_sembrada`, `sup_afectada`, `prod_estimada`, `prod_obtenida`, `estado`, `porcentaje`)
                            VALUES (%s, %s, %s, %s, %s, 1000.0, 300.0, 'PERDIDA TOTAL', %s)
                            """, (ddjj_id, c_info[1], cult, sup_sem, sup_afec, random.uniform(30.0, 100.0)))
                            
                    # 5.5 Bovinos
                    cur.execute("""
                    INSERT INTO `bovinos` (`idddjj`, `cantivaca`, `cantivaqui`, `cantiterne`, `cantinovi`, `cantinovilli`, `cantitoro`, `cantibufa`, `prodespe`, `prodobte`, `carnestimada`, `carneobtenida`, `carneperdida`, `mortavaca`, `mortavaqui`, `mortaterne`, `mortanovi`, `mortanovilli`, `mortatoro`, `mortabufa`)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1000.0, 800.0, 50000.0, 40000.0, 10000.0, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        ddjj_id,
                        random.randint(100, 800), random.randint(50, 400), random.randint(100, 600),
                        random.randint(50, 200), random.randint(50, 200), random.randint(5, 30), random.randint(0, 10),
                        random.randint(10, 50), random.randint(5, 30), random.randint(10, 50),
                        random.randint(5, 20), random.randint(5, 20), random.randint(0, 2), random.randint(0, 1)
                    ))
                    
                    # 5.6 Ovinos
                    cur.execute("""
                    INSERT INTO `ovinos` (`idddjj`, `canticabe`, `mortacabe`, `prodcor`, `corobte`, `prodlana`, `lanaobte`, `perdilana`)
                    VALUES (%s, %s, %s, 50.0, 40.0, 1000.0, 800.0, 200.0)
                    """, (ddjj_id, random.randint(50, 300), random.randint(5, 40)))
                    
                    # 5.7 Porcinos
                    cur.execute("""
                    INSERT INTO `porcinos` (`idddjj`, `canticabe`, `mortacabe`, `prodcor`, `corobte`)
                    VALUES (%s, %s, %s, 10.0, 8.0)
                    """, (ddjj_id, random.randint(10, 100), random.randint(1, 10)))
                    
                    # 5.8 Avicultura
                    cur.execute("""
                    INSERT INTO `avicultura` (`idddjj`, `existencia`, `perdida`, `prodnor`, `prodobte`)
                    VALUES (%s, %s, %s, 500.0, 400.0)
                    """, (ddjj_id, random.randint(100, 1000), random.randint(10, 100)))
                    
                    # 5.9 Apicultura
                    cur.execute("""
                    INSERT INTO `apicultura` (`idddjj`, `cantcol`, `canafec`, `prodnormiel`, `prodobtemiel`, `mielperdida`)
                    VALUES (%s, %s, %s, 1000.0, 800.0, 200.0)
                    """, (ddjj_id, random.randint(10, 100), random.randint(5, 50)))
                    
                    # 5.10 Forestación
                    cur.execute("""
                    INSERT INTO `forestacion` (`idddjj`, `supuso`, `supafe`, `superdida`, `prodmaes`, `prodmaob`, `madestimada`, `madeperdida`, `prodposes`, `posteperdida`, `prodreses`, `resiperdida`)
                    VALUES (%s, %s, %s, %s, 100.0, 80.0, 500.0, 100.0, 200.0, 50.0, 50.0, 10.0)
                    """, (ddjj_id, random.uniform(10.0, 200.0), random.uniform(5.0, 100.0), random.uniform(0.0, 50.0)))
                    
                    # 5.11 Pérdidas mejoras
                    mej_tipos = ["Alambrados", "Corrales", "Invernáculos", "Pasturas", "Canales de Riego"]
                    for mt in random.sample(mej_tipos, random.randint(1, 3)):
                        cur.execute("""
                        INSERT INTO `perdidas_mejoras` (`idddjj`, `mejora`, `vestimado`, `incidencia`, `pesesp`, `pesper`)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """, (ddjj_id, mt, random.uniform(10000.0, 150000.0), random.uniform(10.0, 50.0), random.uniform(5.0, 25.0), random.uniform(20.0, 90.0)))
                        
                    # 5.12 Invernáculos
                    cur.execute("""
                    INSERT INTO `perdidas_invernaculos` (`ddjj`, `cobertura_plasticas`, `estructuras`, `supsemb`, `supafect`, `coberplastiperdi`, `danoplastiperdi`)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (ddjj_id, random.uniform(500.0, 5000.0), random.uniform(1000.0, 10000.0), random.uniform(1.0, 5.0), random.uniform(0.5, 4.0), random.uniform(20.0, 80.0), random.uniform(20.0, 80.0)))
                    
                    # 5.13 Plurianuales
                    cur.execute("""
                    INSERT INTO `perdidas_plurianuales` (`ddjj`, `cobertura_plantas`, `coberperdi`, `dano_planta`, `danoperdi`)
                    VALUES (%s, %s, %s, %s, %s)
                    """, (ddjj_id, random.uniform(100.0, 1000.0), random.uniform(10.0, 80.0), random.uniform(10.0, 100.0), random.uniform(10.0, 80.0)))
                    
                    # 5.14 Documentación checklist
                    docs_check = [
                        ("D1", "Copia DNI/Contrato"),
                        ("D2", "Título de propiedad / Arriendo"),
                        ("D3", "Certificación RENSPA"),
                        ("D4", "Declaración de Existencia de Ganado (Acta SENASA)"),
                        ("D5", "Informe fotográfico del daño")
                    ]
                    for d_cod, d_desc in docs_check:
                        cur.execute("""
                        INSERT INTO `documentacion` (`idddjj`, `codigo`, `documentacion`, `marcar`)
                        VALUES (%s, %s, %s, %s)
                        """, (ddjj_id, d_cod, d_desc, random.choice([0, 1])))
                        
                    # 5.15 Fotos
                    cur.execute("""
                    INSERT INTO `fotos` (`iddjj`, `file`)
                    VALUES (%s, %s)
                    """, (ddjj_id, f"ddjj_{ddjj_id}_foto_campo.jpg"))
                    
                    ddjj_id += 1
            
            # Commit all inserts
            conn.commit()
            print(f"[OK] Poblados {ddjj_id - 1} declaraciones juradas en total!")
            
    finally:
        conn.close()

if __name__ == "__main__":
    main()
