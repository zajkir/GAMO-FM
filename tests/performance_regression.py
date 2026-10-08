import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# This regression suite intentionally runs against SQLite so it can measure
# request connection reuse without depending on an external database service.
os.environ.pop("DATABASE_URL", None)
os.environ["GAMO_DATA_DIR"] = tempfile.mkdtemp(prefix="gamo-performance-")
os.environ["GAMO_ADMIN_PASSWORD"] = "PerfGamo2026!"
os.environ["GAMO_HTTPS"] = "0"

import app

APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")
JS_SOURCE = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
CSS_SOURCE = (ROOT / "static" / "app.css").read_text(encoding="utf-8")
MIGRATIONS = (ROOT / "db_migrations.py").read_text(encoding="utf-8")

# Static guards: these are deliberate performance invariants.
assert "setInterval(" not in JS_SOURCE, "Periodic jobs must use a single recursive timeout, not accumulating setInterval timers."
assert "async function fetchWithTimeout" in JS_SOURCE
assert "await refreshTicketMessages(true)" not in JS_SOURCE, "Ticket POST must render its returned message instead of issuing an immediate second GET."
assert ".dt2-world{will-change:transform" not in CSS_SOURCE, "Digital Twin must not reserve a GPU layer permanently."
assert ".dt2-stage.dragging .dt2-world{will-change:transform" in CSS_SOURCE
assert "LIST_PAGE_SIZE" in APP_SOURCE and "limit ? offset ?" in APP_SOURCE
assert "attachment_rows=read_all('select id,message_id" in APP_SOURCE
assert "for m in messages:\n  m['attachments']=read_all" not in APP_SOURCE
runner = MIGRATIONS[MIGRATIONS.index("def run_migrations("):]
assert runner.count("with connect() as db:") == 1, "Startup migrations should reuse one database connection."
assert len(CSS_SOURCE.encode("utf-8")) < 200_000, "CSS bundle grew beyond the reviewed performance budget."

client = app.app.test_client()
admin = app.one_system("select * from users where lower(email)=?", ("admin@gamo.sk",))
gamo = app.one_system("select * from organizations where code='GAMO'")
assert admin and gamo

with client.session_transaction() as sess:
    sess["user_id"] = admin["id"]
    sess["user_name"] = admin["name"]
    sess["user_role"] = "Administrator"
    sess["organization_id"] = gamo["id"]
    sess["organization_code"] = "GAMO"
    sess["must_change_password"] = False
    sess["csrf"] = "performance-csrf"

# Seed a dataset larger than one page in a single transaction.
with app.con(system=True) as db:
    building_id = app.tx_insert_id(
        db,
        "insert into buildings(code,name,address,manager,customer,status,organization_id) values(?,?,?,?,?,?,?)",
        ("PERF", "Performance Building", "", "QA", "GAMO a.s.", "Aktívna", gamo["id"]),
    )
    floor_id = app.tx_insert_id(
        db,
        "insert into floors(building_id,code,name) values(?,?,?)",
        (building_id, "1.NP", "Performance Floor"),
    )
    room_id = app.tx_insert_id(
        db,
        "insert into rooms(floor_id,code,name,area,tenant,zone) values(?,?,?,?,?,?)",
        (floor_id, "P01", "Performance Room", 100, "GAMO", "PERF"),
    )
    for n in range(1, 131):
        db.execute(
            """insert into assets(
                asset_id,name,building_id,floor_id,room_id,profession,grp,type,
                status,criticality,organization_id
            ) values(?,?,?,?,?,?,?,?,?,?,?)""",
            (
                f"PERF-{n:06d}",
                f"Performance Asset {n}",
                building_id,
                floor_id,
                room_id,
                "ELE",
                "PERF",
                "TEST",
                "Prevádzka",
                "C",
                gamo["id"],
            ),
        )
    db.commit()

# Server-side pagination must keep the DOM bounded while still finding later rows.
page1 = client.get("/assets?q=PERF-&page=1")
assert page1.status_code == 200
assert b"PERF-000001" in page1.data
assert b"PERF-000130" not in page1.data
assert b"130 z" in page1.data or b"130 zÃ¡znamov" in page1.data

page2 = client.get("/assets?q=PERF-&page=2")
assert page2.status_code == 200
assert b"PERF-000130" in page2.data

exact = client.get("/assets?q=PERF-000130")
assert exact.status_code == 200 and b"PERF-000130" in exact.data

# One request should open at most one system and one tenant connection.
real_open = app._open_db
opens = []

def counted_open(system=False, autocommit=False):
    opens.append((system, autocommit))
    return real_open(system=system, autocommit=autocommit)

app._open_db = counted_open
try:
    response = client.get("/")
    assert response.status_code == 200
finally:
    app._open_db = real_open

assert len(opens) <= 2, f"Dashboard reopened the DB too often: {opens}"

# Oversized requests must fail cleanly instead of reaching application handlers.
oversized = client.post(
    "/settings/save",
    data=b"x" * (17 * 1024 * 1024),
    content_type="application/octet-stream",
)
assert oversized.status_code == 413
assert b"SÃºbor je prÃ­liÅ¡ veÄ¾kÃ½" in oversized.data or b"16 MB" in oversized.data

print("GAMO performance regression OK")
