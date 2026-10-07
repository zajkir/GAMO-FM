import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if not os.environ.get("DATABASE_URL"):
    os.environ["GAMO_DATA_DIR"] = tempfile.mkdtemp(prefix="gamo-seed-test-")
os.environ["GAMO_ADMIN_PASSWORD"] = "SeedTest2026!"
os.environ["GAMO_HTTPS"] = "0"

import app
from db_migrations import _migration_12

bool_true = True if app.USING_POSTGRES else 1

org = app.one_system("select * from organizations where code=?", ("SEEDQA",))
if not org:
    oid = app.x_system(
        "insert into organizations(code,name,status,plan,license_status,branding_name,onboarding_complete,mfa_required) values(?,?,?,?,?,?,?,?)",
        ("SEEDQA", "Seed QA Customer", "Aktívny", "BUSINESS", "Aktívna", "Seed QA Customer", bool_true, bool_true),
    )
    org = app.one_system("select * from organizations where id=?", (oid,))

admin = app.one_system("select * from users where organization_id=? and lower(email)=?", (org["id"], "seedqa@example.test"))
if not admin:
    uid = app.x_system(
        "insert into users(name,email,role,status,password_hash,organization_id,must_change_password,mfa_enabled) values(?,?,?,?,?,?,?,?)",
        ("Seed QA Admin", "seedqa@example.test", "Administrator", "Aktívny", "not-used", org["id"], 0, 0),
    )
    admin = app.one_system("select * from users where id=?", (uid,))

building = app.one_system("select * from buildings where organization_id=? and lower(name)=?", (org["id"], "fdsfsdf"))
if not building:
    bid = app.x_system(
        "insert into buildings(code,name,address,manager,customer,status,organization_id) values(?,?,?,?,?,?,?)",
        ("FDSFSDF", "fdsfsdf", "", "", org["name"], "Aktívna", org["id"]),
    )
    building = app.one_system("select * from buildings where id=?", (bid,))

with app.con(system=True) as db:
    _migration_12(db, app.USING_POSTGRES)
    db.commit()

bid = building["id"]
oid = org["id"]

assert app.one_system(
    "select count(*) n from floors where building_id=?", (bid,)
)["n"] >= 3
assert app.one_system(
    "select count(*) n from rooms r join floors f on f.id=r.floor_id where f.building_id=?", (bid,)
)["n"] >= 8
assert app.one_system(
    "select count(*) n from assets where building_id=? and organization_id=?", (bid, oid)
)["n"] >= 12
assert app.one_system(
    "select count(*) n from workorders w join assets a on a.id=w.asset_id where a.building_id=?", (bid,)
)["n"] >= 7
assert app.one_system(
    "select count(*) n from incidents i join assets a on a.id=i.asset_id where a.building_id=?", (bid,)
)["n"] >= 4
assert app.one_system(
    "select count(*) n from documents where building_id=?", (bid,)
)["n"] >= 3
assert app.one_system(
    "select count(*) n from tickets where organization_id=? and building_id=?", (oid, bid)
)["n"] >= 3
assert app.one_system(
    "select count(*) n from ticket_messages where organization_id=?", (oid,)
)["n"] >= 7

ahu = app.one_system(
    "select id from assets where organization_id=? and asset_id=?", (oid, "HVAC-900001")
)
assert ahu
assert app.one_system(
    "select count(*) n from assets where organization_id=? and parent_id=?", (oid, ahu["id"])
)["n"] >= 2

# Idempotency: running the seed again must not duplicate the demo portfolio.
before = app.one_system(
    "select count(*) n from assets where building_id=? and organization_id=?", (bid, oid)
)["n"]
with app.con(system=True) as db:
    _migration_12(db, app.USING_POSTGRES)
    db.commit()
after = app.one_system(
    "select count(*) n from assets where building_id=? and organization_id=?", (bid, oid)
)["n"]
assert before == after

# The seed must stay inside the selected customer.
assert app.one_system(
    "select count(*) n from assets where asset_id like ? and organization_id<>?", ("HVAC-900%", oid)
)["n"] == 0

print("fdsfsdf demo seed test OK")
