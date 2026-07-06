import os
from pathlib import Path
from dotenv import load_dotenv
import pymysql

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

source = os.getenv("DATA_SOURCE", "local").lower()
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

conn = pymysql.connect(
    host=host,
    port=port,
    user=user,
    password=password,
    database=database,
    charset="utf8mb4",
    ssl=ssl
)

try:
    with conn.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM ddjj_personas WHERE id_resolucion = 7")
        count = cursor.fetchone()[0]
        print(f"Total ddjj_personas for resolution 7: {count}")
        
        cursor.execute("SELECT COUNT(*) FROM resoluciones WHERE id_resolucion = 7")
        res_count = cursor.fetchone()[0]
        print(f"Resolucion 7 exists: {res_count > 0}")
finally:
    conn.close()
