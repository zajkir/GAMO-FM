import io
import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path

import pyotp
from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if not os.environ.get("DATABASE_URL"):
    tmp = tempfile.mkdtemp(prefix="gamo-smoke-")
    os.environ["GAMO_DATA_DIR"] = tmp
os.environ["GAMO_ADMIN_PASSWORD"] = "TestGamo2026!"
os.environ["GAMO_HTTPS"] = "0"

import app

client = app.app.test_client()


def csrf():
    with client.session_transaction() as sess:
        return sess["csrf"]


def pending_mfa_csrf():
    with client.session_transaction() as sess:
        return sess["mfa_csrf"]


def login_password(email, password):
    return client.post(
        "/login",
        data={"email": email, "password": password},
        follow_redirects=False,
    )


def login_with_mfa(email, password, secret):
    r = login_password(email, password)
    assert r.status_code in (302, 303), r.status_code
    assert r.headers["Location"].endswith("/login/mfa"), r.headers["Location"]
    token = pending_mfa_csrf()
    r = client.post(
        "/login/mfa",
        data={"_csrf": token, "code": pyotp.TOTP(secret).now()},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303), r.status_code
    return r


# ----- GAMO internal tenant / base application -----
r = client.get("/login")
assert r.status_code == 200

r = login_password("admin@gamo.sk", "TestGamo2026!")
assert r.status_code in (302, 303), r.status_code

for path in ("/", "/assets", "/buildings", "/maintenance", "/incidents", "/admin", "/reports", "/privacy"):
    r = client.get(path)
    assert r.status_code == 200, (path, r.status_code)

with client.session_transaction() as sess:
    gamo_org_id = sess["organization_id"]
gamo_admin = app.one_system("select * from users where lower(email)=?", ("admin@gamo.sk",))
assert gamo_admin

r = client.get("/api/assets/options")
assert r.status_code == 200 and isinstance(r.get_json(), list)

# Invalid input must not leave a partial building behind.
before_buildings = app.one("select count(*) n from buildings where organization_id=?", (gamo_org_id,))["n"]
r = client.post(
    "/add/building",
    data={"_csrf": csrf(), "code": "BROKEN", "name": "Broken building", "floors_count": "not-a-number"},
)
assert r.status_code in (302, 303)
after_buildings = app.one("select count(*) n from buildings where organization_id=?", (gamo_org_id,))["n"]
assert before_buildings == after_buildings

# Full facility hierarchy.
r = client.post(
    "/add/building",
    data={
        "_csrf": csrf(),
        "code": "SMK",
        "name": "Smoke Building",
        "address": "Test 1",
        "manager": "QA",
        "floors_count": "1",
    },
)
assert r.status_code in (302, 303)
building = app.one("select * from buildings where organization_id=? and code=?", (gamo_org_id, "SMK"))
assert building
floor = app.one("select * from floors where building_id=?", (building["id"],))
assert floor

r = client.post(
    "/add/room",
    data={
        "_csrf": csrf(),
        "floor_id": str(floor["id"]),
        "code": "R01",
        "name": "QA Room",
        "area": "42.5",
        "tenant": "GAMO",
        "zone": "QA",
    },
)
assert r.status_code in (302, 303)
room = app.one("select * from rooms where floor_id=? and code=?", (floor["id"], "R01"))
assert room

r = client.post(
    "/add/asset",
    data={
        "_csrf": csrf(),
        "asset_id": "QA-000001",
        "name": "Smoke Asset",
        "building_id": str(building["id"]),
        "floor_id": str(floor["id"]),
        "room_id": str(room["id"]),
        "profession": "ELE",
        "grp": "QA",
        "type": "TEST",
        "status": "Prevádzka",
        "criticality": "B",
        "service_months": "6",
        "revision_months": "12",
        "purchase_price": "1250.50",
    },
)
assert r.status_code in (302, 303)
asset = app.one("select * from assets where asset_id=? and organization_id=?", ("QA-000001", gamo_org_id))
assert asset

r = client.post(
    "/add/workorder",
    data={
        "_csrf": csrf(),
        "asset_id": str(asset["id"]),
        "title": "QA servis",
        "kind": "PM",
        "priority": "Stredná",
        "status": "Plánované",
        "due": "2026-01-01",
        "supplier": "QA servis",
        "technician": "Technik",
        "cost": "99.90",
        "description": "Smoke",
    },
)
assert r.status_code in (302, 303)
workorder = app.one("select * from workorders where asset_id=? and title=?", (asset["id"], "QA servis"))
assert workorder

r = client.post(
    "/add/incident",
    data={
        "_csrf": csrf(),
        "asset_id": str(asset["id"]),
        "title": "QA incident",
        "severity": "Vysoká",
        "status": "Otvorená",
        "reported": "2026-10-07",
        "impact": "Test",
        "cause": "Smoke",
        "cost": "10.10",
    },
)
assert r.status_code in (302, 303)
incident = app.one("select * from incidents where asset_id=? and title=?", (asset["id"], "QA incident"))
assert incident

# ----- Facility editing regression coverage -----
r = client.post(
    f"/edit/building/{building['id']}",
    data={"_csrf": csrf(), "code": "SMK", "name": "Smoke Building Edited", "address": "Test 2", "manager": "QA Manager"},
    follow_redirects=False,
)
assert r.status_code in (302, 303)
building = app.one("select * from buildings where id=?", (building["id"],))
assert building["name"] == "Smoke Building Edited" and building["manager"] == "QA Manager"

r = client.post(
    f"/edit/floor/{floor['id']}",
    data={"_csrf": csrf(), "code": "1.NP", "name": "QA podlažie"},
    follow_redirects=False,
)
assert r.status_code in (302, 303)
floor = app.one("select * from floors where id=?", (floor["id"],))
assert floor["name"] == "QA podlažie"

r = client.post(
    f"/edit/room/{room['id']}",
    data={"_csrf": csrf(), "code": "R01", "name": "QA Room Edited", "area": "44.5", "tenant": "GAMO", "zone": "SECURE"},
    follow_redirects=False,
)
assert r.status_code in (302, 303)
room = app.one("select * from rooms where id=?", (room["id"],))
assert room["name"] == "QA Room Edited" and float(room["area"]) == 44.5 and room["zone"] == "SECURE"

asset_edit = {
    "_csrf": csrf(), "asset_id": "QA-000001", "name": "Smoke Asset Edited",
    "building_id": str(building["id"]), "floor_id": str(floor["id"]), "room_id": str(room["id"]),
    "profession": "ELE", "grp": "QA", "type": "TEST", "manufacturer": "GAMO QA",
    "model": "M2", "serial": "QA-SERIAL", "system_id": "QA-SYS", "parent_id": "",
    "status": "Servis", "criticality": "A", "service_months": "3", "revision_months": "6",
    "purchase_price": "1500.25", "ip": "10.0.0.10", "protocol": "HTTPS", "notes": "Edited by smoke test"
}
r = client.post(f"/edit/asset/{asset['id']}", data=asset_edit, follow_redirects=False)
assert r.status_code in (302, 303)
asset = app.one("select * from assets where id=?", (asset["id"],))
assert asset["name"] == "Smoke Asset Edited" and asset["status"] == "Servis" and asset["criticality"] == "A"
assert float(asset["purchase_price"]) == 1500.25

cycle_edit = dict(asset_edit)
cycle_edit.update({"_csrf": csrf(), "name": "SHOULD NOT SAVE", "parent_id": str(asset["id"])})
r = client.post(f"/edit/asset/{asset['id']}", data=cycle_edit, follow_redirects=False)
assert r.status_code in (302, 303)
asset_after_cycle = app.one("select * from assets where id=?", (asset["id"],))
assert asset_after_cycle["name"] == "Smoke Asset Edited" and asset_after_cycle["parent_id"] is None

r = client.post(
    f"/edit/workorder/{workorder['id']}",
    data={
        "_csrf": csrf(), "asset_id": str(asset["id"]), "title": "QA servis upravený", "kind": "REV",
        "priority": "Vysoká", "status": "Prebieha", "due": "2026-10-20",
        "supplier": "QA Service 2", "technician": "Technik 2", "cost": "129.90", "description": "Edited"
    },
    follow_redirects=False,
)
assert r.status_code in (302, 303)
workorder = app.one("select * from workorders where id=?", (workorder["id"],))
assert workorder["title"] == "QA servis upravený" and workorder["status"] == "Prebieha" and workorder["kind"] == "REV"

r = client.post(
    f"/edit/incident/{incident['id']}",
    data={
        "_csrf": csrf(), "asset_id": str(asset["id"]), "title": "QA incident upravený",
        "severity": "Kritická", "status": "Rieši sa", "reported": "2026-10-07",
        "impact": "Kritický test", "cause": "QA cause", "cost": "25.50"
    },
    follow_redirects=False,
)
assert r.status_code in (302, 303)
incident = app.one("select * from incidents where id=?", (incident["id"],))
assert incident["title"] == "QA incident upravený" and incident["severity"] == "Kritická" and incident["status"] == "Rieši sa"

assert app.one("select count(*) n from asset_events where asset_id=? and event_type='ASSET_UPDATE'", (asset["id"],))["n"] >= 1
assert app.one("select count(*) n from asset_events where asset_id=? and event_type='WORKORDER_UPDATE'", (asset["id"],))["n"] >= 1
assert app.one("select count(*) n from asset_events where asset_id=? and event_type='INCIDENT_UPDATE'", (asset["id"],))["n"] >= 1

# Private GAMO document used later for IDOR checks.
r = client.post(
    f"/building/{building['id']}/document",
    data={
        "_csrf": csrf(),
        "category": "Technická",
        "document": (io.BytesIO(b"GAMO private document"), "gamo-private.txt"),
    },
    content_type="multipart/form-data",
)
assert r.status_code in (302, 303)
document = app.one("select * from documents where building_id=? and name=?", (building["id"], "gamo-private.txt"))
assert document

# Tenant-scoped settings and reporting.
r = client.post(
    "/settings/save",
    data={"_csrf": csrf(), "section": "smoke-test", "value": "tenant-value"},
    follow_redirects=False,
)
assert r.status_code in (302, 303)
assert client.get("/api/setting?section=smoke-test").get_json()["value"] == "tenant-value"

r = client.get("/reports/export.xlsx")
assert r.status_code == 200
book = load_workbook(io.BytesIO(r.data), read_only=False, data_only=False)
for sheet in ("Súhrn", "Assety", "Údržba", "Incidenty", "Po termíne"):
    assert sheet in book.sheetnames
assert book["Súhrn"]["A1"].value.startswith("GAMO FACILITY REPORT")
assert "QA-000001" in [cell.value for row in book["Assety"].iter_rows() for cell in row]
assert len(book["Súhrn"]._charts) >= 1

# ----- Create a real customer tenant (secure by default) -----
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
assert r.status_code in (302, 303)
customer = app.one_system("select * from organizations where code=?", ("SMOKE",))
assert customer and customer["plan"] == "BASIC" and bool(customer["mfa_required"])

client.get("/logout")
r = login_password("smoke@example.test", "SmokePass2026!")
assert r.status_code in (302, 303)
assert r.headers["Location"].endswith("/account/password")

# Forced first-password rotation.
r = client.get("/account/password")
assert r.status_code == 200
r = client.post(
    "/account/password",
    data={
        "_csrf": csrf(),
        "current_password": "SmokePass2026!",
        "new_password": "SmokeSecure2026!",
        "confirm_password": "SmokeSecure2026!",
    },
    follow_redirects=False,
)
assert r.status_code in (302, 303)

# MFA is mandatory for newly-created customers.
r = client.get("/account/mfa")
assert r.status_code == 200
with client.session_transaction() as sess:
    smoke_mfa_secret = sess["mfa_setup_secret"]
r = client.post(
    "/account/mfa",
    data={"_csrf": csrf(), "action": "enable", "code": pyotp.TOTP(smoke_mfa_secret).now()},
)
assert r.status_code == 200
smoke_admin = app.one_system("select * from users where lower(email)=?", ("smoke@example.test",))
assert bool(smoke_admin["mfa_enabled"])
assert smoke_admin["mfa_secret"] == smoke_mfa_secret
assert len(json.loads(smoke_admin["mfa_recovery_codes"])) == 10

r = client.get("/assets")
assert r.status_code == 200
assert b"QA-000001" not in r.data

# Customer's private facility.
r = client.post(
    "/add/building",
    data={
        "_csrf": csrf(),
        "code": "PRIVATE",
        "name": "Private Customer Building",
        "address": "Customer only",
        "manager": "Smoke Admin",
        "floors_count": "1",
    },
)
assert r.status_code in (302, 303)
private_building = app.one_system(
    "select * from buildings where organization_id=? and code=?",
    (customer["id"], "PRIVATE"),
)
assert private_building

# ----- Adversarial cross-tenant / IDOR tests -----
assert client.get("/api/buildings/options").status_code == 200
assert all(x["id"] != building["id"] for x in client.get("/api/buildings/options").get_json())
assert client.get("/api/search?q=QA-000001").get_json() == []
assert client.get("/api/setting?section=smoke-test").get_json()["value"] == ""
assert client.get(f"/api/floors/{building['id']}").status_code == 404
assert client.get(f"/api/rooms/{floor['id']}").status_code == 404
assert client.get(f"/building/{building['id']}").status_code == 404
assert client.get(f"/asset/{asset['id']}").status_code == 404
assert client.get(f"/document/{document['id']}/download").status_code == 404

r = client.post(f"/edit/building/{building['id']}", data={"_csrf": csrf(), "code": "FOREIGN", "name": "Other tenant", "address": "", "manager": ""})
assert r.status_code == 404
r = client.post(f"/edit/asset/{asset['id']}", data={"_csrf": csrf(), "asset_id": "FOREIGN"})
assert r.status_code == 404
r = client.post(f"/edit/workorder/{workorder['id']}", data={"_csrf": csrf(), "title": "Other tenant"})
assert r.status_code == 404
r = client.post(f"/edit/incident/{incident['id']}", data={"_csrf": csrf(), "title": "Other tenant"})
assert r.status_code == 404

r = client.post(f"/document/{document['id']}/delete", data={"_csrf": csrf()})
assert r.status_code == 404
assert app.one_system("select id from documents where id=?", (document["id"],))

r = client.post(f"/status/asset/{asset['id']}", data={"_csrf": csrf(), "status": "Porucha"})
assert r.status_code == 404
r = client.post(f"/delete/asset/{asset['id']}", data={"_csrf": csrf()})
assert r.status_code == 404
assert app.one_system("select id from assets where id=?", (asset["id"],))

r = client.post(f"/status/workorder/{workorder['id']}", data={"_csrf": csrf(), "status": "Ukončené"})
assert r.status_code == 404
r = client.post(f"/delete/workorder/{workorder['id']}", data={"_csrf": csrf()})
assert r.status_code == 404
assert app.one_system("select id from workorders where id=?", (workorder["id"],))

r = client.post(f"/status/incident/{incident['id']}", data={"_csrf": csrf(), "status": "Ukončená"})
assert r.status_code == 404
r = client.post(f"/delete/incident/{incident['id']}", data={"_csrf": csrf()})
assert r.status_code == 404
assert app.one_system("select id from incidents where id=?", (incident["id"],))

r = client.post(
    f"/user/{gamo_admin['id']}/update",
    data={
        "_csrf": csrf(),
        "name": "Attack",
        "email": "attack@example.test",
        "role": "Viewer",
        "status": "Aktívny",
    },
)
assert r.status_code == 404
r = client.post(f"/delete/user/{gamo_admin['id']}", data={"_csrf": csrf()})
assert r.status_code == 404
assert app.one_system("select id from users where id=?", (gamo_admin["id"],))

# RLS itself must block a forgotten WHERE and cross-tenant INSERT.
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

# ----- Privacy Center, backup integrity and GDPR tools -----
r = client.get("/privacy")
assert r.status_code == 200
assert b"CUSTOMER PRIVACY &amp; SECURITY CENTER" in r.data or b"CUSTOMER PRIVACY & SECURITY CENTER" in r.data

r = client.post("/privacy/backup/verify", data={"_csrf": csrf()}, follow_redirects=False)
assert r.status_code in (302, 303)
customer = app.one_system("select * from organizations where id=?", (customer["id"],))
assert customer["backup_last_verified_status"] == "OK"
assert customer["backup_last_verified_at"]

r = client.get("/backup/my")
assert r.status_code == 200 and r.mimetype == "application/zip"
backup_bytes = r.data
ok, detail = app.verify_organization_backup_bytes(backup_bytes)
assert ok, detail
with zipfile.ZipFile(io.BytesIO(backup_bytes), "r") as z:
    manifest = json.loads(z.read("manifest.json"))
    assert manifest["format"] == "GAMO_ORGANIZATION_BACKUP_V3"
    assert manifest["privacy"]["password_hashes_included"] is False
    assert manifest["privacy"]["mfa_secrets_included"] is False
    users_export = json.loads(z.read("data/users.json"))
    assert users_export
    assert all("password_hash" not in u for u in users_export)
    assert all("mfa_secret" not in u for u in users_export)
    assert all("mfa_recovery_codes" not in u for u in users_export)

# Secondary customer account for GDPR export/anonymization.
r = client.post(
    "/add/user",
    data={
        "_csrf": csrf(),
        "name": "Privacy Subject",
        "email": "subject@example.test",
        "role": "Viewer",
        "status": "Aktívny",
        "password": "SubjectPass2026!",
    },
)
assert r.status_code in (302, 303)
subject = app.one_system(
    "select * from users where organization_id=? and lower(email)=?",
    (customer["id"], "subject@example.test"),
)
assert subject

r = client.get(f"/privacy/user/{subject['id']}/export.json")
assert r.status_code == 200
personal = r.get_json()
assert personal["account"]["email"] == "subject@example.test"
assert "password_hash" not in personal["account"]
assert "mfa_secret" not in personal["account"]

r = client.post(
    f"/privacy/user/{subject['id']}/anonymize",
    data={"_csrf": csrf(), "confirm_text": "ANONYMIZE"},
    follow_redirects=False,
)
assert r.status_code in (302, 303)
subject_after = app.one_system("select * from users where id=?", (subject["id"],))
assert subject_after["status"] == "Neaktívny"
assert str(subject_after["email"]).endswith("@anonymized.invalid")
assert subject_after["mfa_secret"] is None
assert subject_after["erased_at"]
assert app.one_system(
    "select count(*) n from privacy_requests where organization_id=? and subject_user_id=?",
    (customer["id"], subject["id"]),
)["n"] >= 2

# Customer settings require CSRF.
r = client.post("/settings/save", data={"section": "missing-csrf", "value": "x"})
assert r.status_code == 400

# ----- GAMO customer view without consent -----
client.get("/logout")
r = login_password("admin@gamo.sk", "TestGamo2026!")
assert r.status_code in (302, 303)
r = client.get(f"/platform/customer/{customer['id']}")
assert r.status_code == 200
assert b"Private Customer Building" not in r.data
assert b"CUSTOMER SECURITY POSTURE" in r.data
r = client.get(f"/platform/customer/{customer['id']}/backup", follow_redirects=False)
assert r.status_code in (302, 303)

# ----- Explicit customer consent (login requires MFA) -----
client.get("/logout")
login_with_mfa("smoke@example.test", "SmokeSecure2026!", smoke_mfa_secret)
r = client.post(
    "/privacy/support-access",
    data={
        "_csrf": csrf(),
        "action": "grant",
        "hours": "1",
        "reason": "Automated privacy support test",
    },
    follow_redirects=False,
)
assert r.status_code in (302, 303)
support_org = app.one_system("select * from organizations where id=?", (customer["id"],))
assert bool(support_org["support_access_enabled"])

# GAMO can enter only during the consent window.
client.get("/logout")
r = login_password("admin@gamo.sk", "TestGamo2026!")
assert r.status_code in (302, 303)
r = client.get(f"/platform/customer/{customer['id']}")
assert r.status_code == 200
assert b"Private Customer Building" in r.data
assert b"MFA ON" in r.data

r = client.post(
    f"/platform/customer/{customer['id']}/support-enter",
    data={"_csrf": csrf()},
    follow_redirects=False,
)
assert r.status_code in (302, 303)
assert b"Private Customer Building" in client.get("/buildings").data
assert b"Smoke Building" not in client.get("/buildings").data
assert client.get("/privacy").status_code == 403
assert client.get(f"/asset/{asset['id']}").status_code == 404

r = client.post("/support/exit", data={"_csrf": csrf()}, follow_redirects=False)
assert r.status_code in (302, 303)

r = client.get(f"/platform/customer/{customer['id']}/backup")
assert r.status_code == 200 and r.mimetype == "application/zip"
ok, detail = app.verify_organization_backup_bytes(r.data)
assert ok, detail
assert app.one_system(
    "select action from customer_access_log where target_organization_id=? and action='GAMO_BACKUP_EXPORT' order by id desc limit 1",
    (customer["id"],),
)

# Support-only emergency MFA reset is audited and org policy forces re-enrollment.
r = client.post(
    f"/platform/customer/{customer['id']}/reset-admin-mfa",
    data={"_csrf": csrf()},
    follow_redirects=False,
)
assert r.status_code in (302, 303)
smoke_admin = app.one_system("select * from users where id=?", (smoke_admin["id"],))
assert not bool(smoke_admin["mfa_enabled"])
assert smoke_admin["mfa_secret"] is None
assert app.one_system(
    "select action from customer_access_log where target_organization_id=? and action='GAMO_ADMIN_MFA_RESET' order by id desc limit 1",
    (customer["id"],),
)

client.get("/logout")
r = login_password("smoke@example.test", "SmokeSecure2026!")
assert r.status_code in (302, 303)
assert r.headers["Location"].endswith("/account/mfa")

# ----- Authentication telemetry -----
auth_count = app.one_system(
    "select count(*) n from auth_events where organization_id=?",
    (customer["id"],),
)["n"]
assert auth_count > 0

# Production restart regression: RLS may already be active with an empty users table.
if app.USING_POSTGRES:
    with app.con(system=True) as db:
        db.execute("delete from users")
        db.commit()
    app.init_postgres()
    seeded = app.one_system(
        "select id,organization_id from users where lower(email)=?",
        ("admin@gamo.sk",),
    )
    gamo = app.one_system("select id from organizations where code='GAMO'")
    assert seeded and gamo and seeded["organization_id"] == gamo["id"]

print("GAMO customer security smoke test OK")
