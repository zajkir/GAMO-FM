"""One-time GAMO SQLite -> PostgreSQL migration.
Usage: set DATABASE_URL to the target PostgreSQL URL, then run:
python migrate_to_postgres.py
"""
import os, sqlite3
import psycopg
from psycopg import sql

DATA_DIR=os.environ.get("GAMO_DATA_DIR",os.path.join(os.path.dirname(__file__),"data"))
SQLITE_DB=os.environ.get("GAMO_SQLITE_DB",os.path.join(DATA_DIR,"gamo.db"))
DATABASE_URL=os.environ.get("DATABASE_URL","").strip()
TABLES=["buildings","floors","rooms","assets","workorders","incidents","users","settings","audit_log","documents"]

if not DATABASE_URL:
 raise SystemExit("DATABASE_URL is required.")
if not os.path.exists(SQLITE_DB):
 raise SystemExit(f"SQLite database not found: {SQLITE_DB}")

src=sqlite3.connect(SQLITE_DB); src.row_factory=sqlite3.Row
dst=psycopg.connect(DATABASE_URL)
try:
 with dst.cursor() as cur:
  for table in TABLES:
   exists=src.execute("select 1 from sqlite_master where type='table' and name=?",(table,)).fetchone()
   if not exists: continue
   rows=src.execute(f'SELECT * FROM "{table}"').fetchall()
   if not rows: continue
   cols=list(rows[0].keys())
   query=sql.SQL("INSERT INTO {} ({}) VALUES ({}) ON CONFLICT DO NOTHING").format(
    sql.Identifier(table),
    sql.SQL(",").join(map(sql.Identifier,cols)),
    sql.SQL(",").join(sql.Placeholder() for _ in cols))
   for row in rows: cur.execute(query,tuple(row[c] for c in cols))
   if "id" in cols:
    cur.execute(sql.SQL("SELECT setval(pg_get_serial_sequence(%s,'id'), COALESCE((SELECT MAX(id) FROM {}),1), true)").format(sql.Identifier(table)),(table,))
 dst.commit()
 print("GAMO migration completed successfully.")
except Exception:
 dst.rollback(); raise
finally:
 src.close(); dst.close()
