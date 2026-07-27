"""Aplica schema.sql no banco apontado por DATABASE_URL — substitui `psql -f
schema.sql` quando o cliente psql não está instalado localmente (usa o
psycopg2 já presente no venv do projeto)."""
import os
import sys

import psycopg2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

sql_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "schema.sql")
with open(sql_path, encoding="utf-8") as f:
    sql = f.read()

dsn = os.getenv("DATABASE_URL") or config.DATABASE_URL
if not dsn:
    print("DATABASE_URL não definido (nem no ambiente, nem no .env).", file=sys.stderr)
    sys.exit(1)

conn = psycopg2.connect(dsn)
try:
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    print("schema.sql aplicado com sucesso.")
finally:
    conn.close()
