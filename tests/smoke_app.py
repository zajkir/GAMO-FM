import io
import os
import tempfile
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if not os.environ.get("DATABASE_URL"):
    tmp = tempfile.mkdtemp(prefix="gamo-smoke-")
    os.environ["GAMO_DATA_DIR"] = tmp
os.environ["GAMO_ADMIN_PASSWORD"] = "TestGamo2026!"
os.environ["GAMO_HTTPS"] = "0"

import app
from openpyxl import load_workbook

client = app.app.test_client()

def csrf():
    with client.session_transaction() as sess:
        return sess["csrf"]

r = client.get("/login")
assert r.status_code == 200, r.status_code

r = client.post("/login", data={"email": "admin@gamo.sk", "password": "TestGamo2026!"})
assert r.status_code in (302, 303), r.status_code

for path in ("/", "/assets", "/buildings", "/maintenance", "/incidents", "/admin", "/reports"):
    r = client.get(path)
    assert r.status_code == 200, (path, r.status_code)

r = client.get("/api/assets/options")
assert r.status_code == 200 and isinstance(r.get_json(), list)

# Invalid building input must not leave a partially-created record behind.
with client.session_transaction() as sess:
    gamo_org_id = sess["organization_id"]
before_buildings = app.one("select count(*) n from buildings where organization_id=?", (gamo_org_id,))["n"]
r = client.post("/add/building", data={
    "_csrf": csrf(), "code": "BROKEN", "name": "Broken building", "floors_count": "not-a-number"
})
assert r.status_code in (302, 303)
after_buildings = app.one("select count(*) n from buildings where organization_id=?", (gamo_org_id,))["n"]
assert before_buildings == after_buildings

# Full facility hierarchy + operational records.
r = client.post("/add/building", data={
    "_csrf": csrf(), "code": "SMK", "name": "Smoke Building", "address": "Test 1",
    "manager": "QA", "floors_count": "1"
})
assert r.status_code in (302, 303)
building = app.one("select * from buildings where organization_id=? and code=?", (gamo_org_id, "SMK"))
assert building
floor = app.one("select * from floors where building_id=?", (building["id"],))
assert floor

r = client.post("/add/room", data={
    "_csrf": csrf(), "floor_id": str(floor["id"]), "code": "R01", "name": "QA Room",
    "area": "42.5", "tenant": "GAMO", "zone": "QA"
})
assert r.status_code in (302, 303)
room = app.one("select * from rooms where floor_id=? and code=?", (floor["id"], "R01"))
assert room

r = client.post("/add/asset", data={
    "_csrf": csrf(), "asset_id": "QA-000001", "name": "Smoke Asset",
    "building_id": str(building["id"]), "floor_id": str(floor["id"]), "room_id": str(room["id"]),
    "profession": "ELE", "grp": "QA", "type": "TEST", "status": "Prevádzka", "criticality": "B",
    "service_months": "6", "revision_months": "12", "purchase_price": "1250.50"
})
assert r.status_code in (302, 303)
asset = app.one("select * from assets where asset_id=? and organization_id=?", ("QA-000001", gamo_org_id))
assert asset

r = client.post("/add/workorder", data={
    "_csrf": csrf(), "asset_id": str(asset["id"]), "title": "QA servis", "kind": "PM",
    "priority": "Stredná", "status": "Plánované", "due": "2026-01-01",
    "supplier": "QA servis", "technician": "Technik", "cost": "99.90", "description": "Smoke"
})
assert r.status_code in (302, 303)
r = client.post("/add/incident", data={
    "_csrf": csrf(), "asset_id": str(asset["id"]), "title": "QA incident", "severity": "Vysoká",
    "status": "Otvorená", "reported": "2026-10-07", "impact": "Test", "cause": "Smoke", "cost": "10.10"
})
assert r.status_code in (302, 303)

r = client.get("/settings/save")
assert r.status_code in (405, 302)

r = client.post(
    "/settings/save",
    data={"_csrf": csrf(), "section": "smoke-test", "value": "tenant-value"},
    follow_redirects=False,
)
assert r.status_code in (302, 303), r.status_code
r = client.get("/api/setting?section=smoke-test")
assert r.get_json()["value"] == "tenant-value"

r = client.get("/reports/export.xlsx")
assert r.status_code == 200, r.status_code
book = load_workbook(io.BytesIO(r.data), read_only=False, data_only=False)
for sheet in ("Súhrn", "Assety", "Údržba", "Incidenty", "Po termíne"):
    assert sheet in book.sheetnames, book.sheetnames
assert book["Súhrn"]["A1"].value.startswith("GAMO FACILITY REPORT")
asset_values = [cell.value for row in book["Assety"].iter_rows() for cell in row]
assert "QA-000001" in asset_values
assert len(book["Súhrn"]._charts) >= 1

r = client.post(
    "/platform/customer",
    data={
        "_csrf": csrf(),
        "code": "SMOKE",
        "name": "Smoke Customer s.r.o.",
        "admin_name": "Smoke Admin",
        "email": "smoke@example.test",
        "password": "SmokePass2026!",
        "plan": "BASIC",
        "license_status": "Aktívna",
    },
    follow_redirects=False,
)
assert r.status_code in (302, 303), r.status_code
customer = app.one("select * from organizations where code=?", ("SMOKE",))
assert customer and customer["plan"] == "BASIC"

client.get("/logout")
r = client.post("/login", data={"email": "smoke@example.test", "password": "SmokePass2026!"})
assert r.status_code in (302, 303), r.status_code
assert r.headers["Location"].endswith("/account/password")
r = client.get("/account/password")
assert r.status_code == 200
r = client.post("/account/password", data={
    "_csrf": csrf(),
    "current_password": "SmokePass2026!",
    "new_password": "SmokeSecure2026!",
    "confirm_password": "SmokeSecure2026!",
}, follow_redirects=False)
assert r.status_code in (302, 303), r.status_code
r = client.get("/assets")
assert r.status_code == 200
assert b"HVAC-000001" not in r.data

r = client.get("/api/buildings/options")
assert r.status_code == 200 and r.get_json() == []

r = client.get("/api/search?q=QA-000001")
assert r.status_code == 200 and r.get_json() == []

# Tenant settings are private as well: GAMO's setting cannot bleed into this customer.
r = client.get("/api/setting?section=smoke-test")
assert r.status_code == 200 and r.get_json()["value"] == ""
r = client.get(f"/api/floors/{building['id']}")
assert r.status_code == 404
r = client.get(f"/api/rooms/{floor['id']}")
assert r.status_code == 404

# Cross-tenant object IDs must stay inaccessible.
r = client.get(f"/building/{building['id']}")
assert r.status_code == 404
r = client.get(f"/asset/{asset['id']}")
assert r.status_code == 404
r = client.post(f"/status/asset/{asset['id']}", data={"_csrf": csrf(), "status": "Porucha"})
assert r.status_code == 404
r = client.post(f"/delete/asset/{asset['id']}", data={"_csrf": csrf()})
assert r.status_code == 404
assert app.one_system("select id from assets where id=?", (asset["id"],))

# Create a private customer object used to verify consent-gated GAMO support access.
r = client.post("/add/building", data={
    "_csrf": csrf(), "code": "PRIVATE", "name": "Private Customer Building",
    "address": "Customer only", "manager": "Smoke Admin", "floors_count": "1"
})
assert r.status_code in (302, 303)
private_building = app.one_system(
    "select * from buildings where organization_id=? and code=?",
    (customer["id"], "PRIVATE"),
)
assert private_building

r = client.get("/privacy")
assert r.status_code == 200
assert b"Private Customer Building" not in r.data
r = client.get("/privacy/access-log.json")
assert r.status_code == 200 and r.mimetype == "application/json"
assert r.get_json()["organization"]["code"] == "SMOKE"

# PostgreSQL RLS must still isolate data even if a future query forgets WHERE organization_id.
if app.USING_POSTGRES:
    from flask import session as flask_session
    with app.app.test_request_context("/"):
        flask_session["organization_id"] = customer["id"]
        flask_session["organization_code"] = "SMOKE"
        flask_session["user_role"] = "Administrator"
        assert app.one("select count(*) n from buildings")["n"] == 1
        assert app.one("select * from buildings where id=?", (building["id"],)) is None
        blocked = False
        try:
            app.x(
                "insert into buildings(code,name,organization_id) values(?,?,?)",
                ("ESCAPE", "Cross tenant attempt", gamo_org_id),
            )
        except Exception:
            blocked = True
        assert blocked, "PostgreSQL RLS allowed a cross-tenant INSERT"

r = client.get("/reports/export.xlsx")
assert r.status_code == 200
empty_book = load_workbook(io.BytesIO(r.data), read_only=False, data_only=False)
assert "Súhrn" in empty_book.sheetnames

r = client.post("/settings/save", data={"section": "missing-csrf", "value": "x"})
assert r.status_code == 400

# GAMO may see aggregate customer metadata, but not customer content without consent.
client.get("/logout")
r = client.post("/login", data={"email": "admin@gamo.sk", "password": "TestGamo2026!"})
assert r.status_code in (302, 303)
r = client.get(f"/platform/customer/{customer['id']}")
assert r.status_code == 200
assert b"Private Customer Building" not in r.data
r = client.get(f"/platform/customer/{customer['id']}/backup", follow_redirects=False)
assert r.status_code in (302, 303)

# Customer explicitly grants temporary support access.
client.get("/logout")
r = client.post("/login", data={"email": "smoke@example.test", "password": "SmokeSecure2026!"})
assert r.status_code in (302, 303)
r = client.post(
    "/privacy/support-access",
    data={"_csrf": csrf(), "action": "grant", "hours": "1", "reason": "Automated privacy test"},
    follow_redirects=False,
)
assert r.status_code in (302, 303)
support_org = app.one_system("select * from organizations where id=?", (customer["id"],))
assert bool(support_org["support_access_enabled"])

# GAMO can now access only through the audited support window.
client.get("/logout")
r = client.post("/login", data={"email": "admin@gamo.sk", "password": "TestGamo2026!"})
assert r.status_code in (302, 303)
r = client.get(f"/platform/customer/{customer['id']}")
assert r.status_code == 200
assert b"Private Customer Building" in r.data

r = client.post(
    f"/platform/customer/{customer['id']}/support-enter",
    data={"_csrf": csrf()},
    follow_redirects=False,
)
assert r.status_code in (302, 303)
r = client.get("/buildings")
assert r.status_code == 200
assert b"Private Customer Building" in r.data
assert b"Smoke Building" not in r.data
r = client.get("/privacy")
assert r.status_code == 403
r = client.get(f"/asset/{asset['id']}")
assert r.status_code == 404
with client.session_transaction() as sess:
    assert sess.get("organization_id") == gamo_org_id
    assert sess.get("support_target_org_id") == customer["id"]

r = client.post("/support/exit", data={"_csrf": csrf()}, follow_redirects=False)
assert r.status_code in (302, 303)
with client.session_transaction() as sess:
    assert sess.get("support_target_org_id") is None

r = client.get(f"/platform/customer/{customer['id']}/backup")
assert r.status_code == 200 and r.mimetype == "application/zip"
access = app.one_system(
    "select action from customer_access_log where target_organization_id=? and action='GAMO_BACKUP_EXPORT' order by id desc limit 1",
    (customer["id"],),
)
assert access

# Regression: production may restart with PostgreSQL RLS already enabled and
# an empty users table. Bootstrap must reseed the internal GAMO administrator
# through the privileged system connection instead of being blocked by RLS.
if app.USING_POSTGRES:
    with app.con(system=True) as db:
        db.execute("delete from users")
        db.commit()
    app.init_postgres()
    seeded = app.one_system("select id,organization_id from users where lower(email)=?", ("admin@gamo.sk",))
    gamo = app.one_system("select id from organizations where code='GAMO'")
    assert seeded and gamo and seeded["organization_id"] == gamo["id"]

print("GAMO smoke test OK")
