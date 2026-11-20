"""Copy the bundled SQLite database into a hosted DB (Postgres) so accounts persist on Vercel.

Usage:  DATABASE_URL=postgresql://user:pass@host/db python scripts/migrate_to_hosted_db.py [source.db]
"""
import os, sys
from sqlalchemy import create_engine, MetaData

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(root, "api", "medisafe.db")
url = os.environ.get("DATABASE_URL", "")
if url.startswith("postgres://"):
    url = "postgresql://" + url[len("postgres://"):]
if url.startswith("postgresql://"):
    url = "postgresql+psycopg2://" + url[len("postgresql://"):]
if not url:
    sys.exit("Set DATABASE_URL first")

src = create_engine(f"sqlite:///{src_path}")
dst = create_engine(url)
md = MetaData()
md.reflect(bind=src)
sys.path.insert(0, os.path.join(root, "backend"))
from app.models import db  # create the schema from the app's own models (portable types)
db.metadata.create_all(dst)
with src.connect() as s, dst.begin() as d:
    for t in md.sorted_tables:
        dt = db.metadata.tables[t.name]
        if d.execute(dt.select().limit(1)).first():
            print(f"skip {t.name} (already has data)"); continue
        rows = [dict(r._mapping) for r in s.execute(t.select())]
        for i in range(0, len(rows), 2000):
            d.execute(dt.insert(), rows[i:i + 2000])
        print(f"{t.name}: {len(rows)} rows")
    if dst.dialect.name == "postgresql":  # fix id sequences after explicit-id inserts
        for t in md.sorted_tables:
            if "id" in t.c:
                d.exec_driver_sql(
                    f"SELECT setval(pg_get_serial_sequence('\"{t.name}\"','id'), COALESCE((SELECT MAX(id) FROM \"{t.name}\"),1))")
print("done")
