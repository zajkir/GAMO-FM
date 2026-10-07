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
from db_migrations import _migration_12

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

# Regression: new asset may leave Asset ID empty; server must generate a tenant-safe ID.
expected_auto_id = client.get("/api/assets/next-id?profession=HVAC").get_json()["asset_id"]
r = client.post(
    "/add/asset",
    data={
        "_csrf": csrf(),
        "asset_id": "",
        "name": "Automatic HVAC Asset",
        "building_id": str(building["id"]),
        "floor_id": str(floor["id"]),
        "room_id": str(room["id"]),
        "profession": "HVAC",
        "grp": "VZT",
        "type": "AHU",
        "status": "Prevádzka",
        "criticality": "B",
        "service_months": "6",
        "revision_months": "12",
        "purchase_price": "0",
    },
    follow_redirects=False,
)
assert r.status_code in (302, 303)
auto_asset = app.one(
    "select * from assets where organization_id=? and name=?",
    (gamo_org_id, "Automatic HVAC Asset"),
)
assert auto_asset and auto_asset["asset_id"] == expected_auto_id
assert client.get("/api/assets/next-id?profession=HVAC").get_json()["asset_id"] != expected_auto_id

# A manually duplicated ID must be rejected without creating another row.
before_auto = app.one("select count(*) n from assets where organization_id=?", (gamo_org_id,))["n"]
r = client.post(
    "/add/asset",
    data={
        "_csrf": csrf(),
        "asset_id": expected_auto_id,
        "name": "Duplicate Must Not Save",
        "building_id": str(building["id"]),
        "floor_id": str(floor["id"]),
        "room_id": str(room["id"]),
        "profession": "HVAC",
        "grp": "VZT",
        "type": "AHU",
        "status": "Prevádzka",
        "criticality": "B",
    },
)
assert r.status_code in (302, 303)
after_auto = app.one("select count(*) n from assets where organization_id=?", (gamo_org_id,))["n"]
assert before_auto == after_auto
assert app.one("select id from assets where organization_id=? and name=?", (gamo_org_id, "Duplicate Must Not Save")) is None

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

# Regression: resolved incidents and cancelled workorders are not active,
# overdue or notification-worthy anywhere in the application.
r = client.post(
    "/add/incident",
    data={
        "_csrf": csrf(), "asset_id": str(asset["id"]), "title": "QA resolved incident",
        "severity": "Kritická", "status": "Vyriešená", "reported": "2026-10-06",
        "impact": "Resolved", "cause": "Resolved", "cost": "0"
    },
)
assert r.status_code in (302, 303)
r = client.post(
    "/add/workorder",
    data={
        "_csrf": csrf(), "asset_id": str(asset["id"]), "title": "QA cancelled overdue",
        "kind": "PM", "priority": "Kritická", "status": "Zrušené", "due": "2020-01-01",
        "supplier": "", "technician": "", "cost": "0", "description": "Cancelled"
    },
)
assert r.status_code in (302, 303)
active_notifications = client.get("/api/notifications").get_json()
assert not any(x.get("title") == "QA resolved incident" for x in active_notifications)
assert not any(x.get("title") == "QA cancelled overdue" for x in active_notifications)
# Legacy NULL room area must not break the Digital Twin aggregation.
null_room_id = app.x(
    "insert into rooms(floor_id,code,name,area,tenant,zone) values(?,?,?,?,?,?)",
    (floor["id"], "NULL-AREA", "Legacy room without area", None, "GAMO", "LEGACY"),
)
building_page = client.get(f"/building/{building['id']}")
assert building_page.status_code == 200
assert b"GAMO DIGITAL TWIN" in building_page.data
assert b'NULL-AREA' in building_page.data
assert b'data-floor-incidents="1"' in building_page.data
dashboard_page = client.get("/")
assert dashboard_page.status_code == 200
assert b"dashboard-commandbar" in dashboard_page.data

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
building_after_asset_edit = client.get(f"/building/{building['id']}#twin")
assert building_after_asset_edit.status_code == 200
assert b'data-floor-critical="1"' in building_after_asset_edit.data
assert b'data-floor-faults=' in building_after_asset_edit.data
assert b"dt2FocusButton" in building_after_asset_edit.data and b"dt2TechButton" in building_after_asset_edit.data

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

viewer_id = app.x_system(
    "insert into users(name,email,role,status,password_hash,organization_id,must_change_password) values(?,?,?,?,?,?,?)",
    ("Settings Viewer", "settings-viewer@example.test", "Viewer", "Aktívny", app.generate_password_hash("ViewerPass2026!"), gamo_org_id, False if app.USING_POSTGRES else 0),
)
viewer_client = app.app.test_client()
with viewer_client.session_transaction() as sess:
    sess["user_id"] = viewer_id
    sess["user_name"] = "Settings Viewer"
    sess["user_role"] = "Viewer"
    sess["organization_id"] = gamo_org_id
    sess["organization_code"] = "GAMO"
    sess["must_change_password"] = False
    sess["csrf"] = "viewer-csrf"
r = viewer_client.post("/settings/save", data={"_csrf": "viewer-csrf", "section": "forbidden", "value": "x"})
assert r.status_code == 403
assert app.one_system("select v from organization_settings where organization_id=? and k=?", (gamo_org_id, "forbidden")) is None

# Viewer must not be able to bypass hidden UI controls with forged POST requests.
for path, payload in [
    ("/add/asset", {"_csrf": "viewer-csrf"}),
    (f"/edit/building/{building['id']}", {"_csrf": "viewer-csrf", "code": "HACK", "name": "Hacked"}),
    (f"/status/asset/{asset['id']}", {"_csrf": "viewer-csrf", "status": "Porucha"}),
    (f"/delete/workorder/{workorder['id']}", {"_csrf": "viewer-csrf"}),
    (f"/delete/incident/{incident['id']}", {"_csrf": "viewer-csrf"}),
    (f"/user/{gamo_admin['id']}/update", {
        "_csrf": "viewer-csrf", "name": "Hacked Admin", "email": "hacked@example.test",
        "role": "Viewer", "status": "Aktívny"
    }),
]:
    denied = viewer_client.post(path, data=payload, follow_redirects=False)
    assert denied.status_code == 403, (path, denied.status_code)

denied_upload = viewer_client.post(
    f"/building/{building['id']}/document",
    data={"_csrf": "viewer-csrf", "category": "Technická", "document": (io.BytesIO(b"blocked"), "blocked.txt")},
    content_type="multipart/form-data",
    follow_redirects=False,
)
assert denied_upload.status_code == 403
denied_delete_doc = viewer_client.post(
    f"/document/{document['id']}/delete", data={"_csrf": "viewer-csrf"}, follow_redirects=False
)
assert denied_delete_doc.status_code == 403
assert app.one_system("select name from buildings where id=?", (building["id"],))["name"] == "Smoke Building Edited"
assert app.one_system("select status from assets where id=?", (asset["id"],))["status"] == "Servis"
assert app.one_system("select id from documents where id=?", (document["id"],))
assert app.one_system("select name from users where id=?", (gamo_admin["id"],))["name"] == "GAMO Administrator"

r = client.get("/reports/export.xlsx")
assert r.status_code == 200
book = load_workbook(io.BytesIO(r.data), read_only=False, data_only=False)
for sheet in ("Súhrn", "Assety", "Údržba", "Incidenty", "Po termíne"):
    assert sheet in book.sheetnames
assert book["Súhrn"]["A1"].value.startswith("GAMO FACILITY REPORT")
assert "QA-000001" in [cell.value for row in book["Assety"].iter_rows() for cell in row]
assert len(book["Súhrn"]._charts) >= 1
expected_open_incidents = app.one(
    """select count(*) n from incidents i join assets a on a.id=i.asset_id
       where a.organization_id=? and i.status not in ('Ukončená','Vyriešená')""",
    (gamo_org_id,),
)["n"]
assert book["Súhrn"]["E5"].value == expected_open_incidents
overdue_values = [cell.value for row in book["Po termíne"].iter_rows() for cell in row]
assert "QA cancelled overdue" not in overdue_values

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
assert b"ACCOUNT SECURITY" in r.data
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

# ----- Customer ticket + in-app manager conversation -----
# Create a normal customer requester and a Facility Manager. Their sessions are
# prepared directly so this smoke test focuses on authorization and ticket flow.
bool_true = True if app.USING_POSTGRES else 1
bool_false = False if app.USING_POSTGRES else 0
requester_id = app.x_system(
    "insert into users(name,email,role,status,password_hash,organization_id,must_change_password,mfa_enabled) values(?,?,?,?,?,?,?,?)",
    ("Customer Requester", "requester@example.test", "Viewer", "Aktívny", app.generate_password_hash("Requester2026!"), customer["id"], bool_false, bool_true),
)
manager_id = app.x_system(
    "insert into users(name,email,role,status,password_hash,organization_id,must_change_password,mfa_enabled) values(?,?,?,?,?,?,?,?)",
    ("Facility Manager QA", "manager@example.test", "Facility Manager", "Aktívny", app.generate_password_hash("Manager2026!"), customer["id"], bool_false, bool_true),
)
requester = app.one_system("select * from users where id=?", (requester_id,))
manager = app.one_system("select * from users where id=?", (manager_id,))
assert requester and manager

def force_user_session(user, org_code="SMOKE"):
    with client.session_transaction() as sess:
        sess.clear()
        sess["user_id"] = user["id"]
        sess["user_name"] = user["name"]
        sess["user_role"] = user["role"]
        sess["organization_id"] = user["organization_id"]
        sess["organization_code"] = org_code
        sess["must_change_password"] = False
        sess["csrf"] = "smoke-csrf-ticket"

force_user_session(requester)
assert client.get("/tickets").status_code == 200
r = client.post(
    "/tickets/create",
    data={
        "_csrf": csrf(),
        "subject": "Nefunguje klimatizácia",
        "category": "Porucha",
        "priority": "Vysoká",
        "building_id": str(private_building["id"]),
        "asset_id": "",
        "message": "Prosím správcu o kontrolu klimatizácie v kancelárii.",
    },
    follow_redirects=False,
)
assert r.status_code in (302, 303)
ticket = app.one_system(
    "select * from tickets where organization_id=? and created_by=?",
    (customer["id"], requester["id"]),
)
assert ticket and ticket["ticket_no"] == "TKT-000001"
assert ticket["assigned_to"] == manager["id"]
assert client.get(f"/ticket/{ticket['id']}").status_code == 200
assert client.post(
    f"/ticket/{ticket['id']}/manage",
    data={"_csrf": csrf(), "status": "Rieši sa", "priority": "Vysoká"},
).status_code == 403

force_user_session(manager)
manager_list = client.get("/tickets")
assert manager_list.status_code == 200 and b"Nefunguje klimatiz" in manager_list.data
assert b"ticket-row unread" in manager_list.data
assert b"1 nov" in manager_list.data
manager_state = client.get("/api/tickets/inbox-state")
assert manager_state.status_code == 200
assert manager_state.get_json()["unread"] >= 1
assert "|" in manager_state.get_json()["version"]

# Regression: the second participant must see the first participant's message
# through the live API without sending anything or refreshing the whole page.
live_initial = client.get(f"/api/ticket/{ticket['id']}/messages?after=0")
assert live_initial.status_code == 200
live_initial_json = live_initial.get_json()
assert any(m["body"].startswith("Prosím správcu") for m in live_initial_json["messages"])
first_message_id = live_initial_json["last_id"]
manager_after_read = client.get("/tickets")
assert manager_after_read.status_code == 200
assert b"ticket-row unread" not in manager_after_read.data
assert client.get("/api/tickets/inbox-state").get_json()["unread"] == 0

# Live/AJAX reply returns JSON instead of forcing a page reload.
r = client.post(
    f"/ticket/{ticket['id']}/message",
    data={"_csrf": csrf(), "message": "Požiadavku som prevzal, prídem ju skontrolovať."},
    headers={"X-Requested-With": "GAMO-Live-Chat", "Accept": "application/json"},
    follow_redirects=False,
)
assert r.status_code == 200 and r.get_json()["ok"] is True
manager_message_id = r.get_json()["message_id"]
r = client.post(
    f"/ticket/{ticket['id']}/manage",
    data={
        "_csrf": csrf(),
        "status": "Čaká na zákazníka",
        "priority": "Vysoká",
        "assigned_to": str(manager["id"]),
    },
    follow_redirects=False,
)
assert r.status_code in (302, 303)

force_user_session(requester)
notifications = client.get("/api/notifications").get_json()
assert any(x.get("url") == f"/ticket/{ticket['id']}" for x in notifications)
requester_list_unread = client.get("/tickets")
assert requester_list_unread.status_code == 200
assert b"ticket-row unread" in requester_list_unread.data
assert client.get("/api/tickets/inbox-state").get_json()["unread"] >= 1

# Requester receives the manager reply immediately from the live endpoint.
live_reply = client.get(f"/api/ticket/{ticket['id']}/messages?after={first_message_id}")
assert live_reply.status_code == 200
live_reply_json = live_reply.get_json()
assert live_reply_json["last_id"] == manager_message_id
assert any(m["body"].startswith("Požiadavku som prevzal") and not m["mine"] for m in live_reply_json["messages"])

# No duplicate payload after the last known message.
empty_live = client.get(f"/api/ticket/{ticket['id']}/messages?after={manager_message_id}")
assert empty_live.status_code == 200 and empty_live.get_json()["messages"] == []

thread = client.get(f"/ticket/{ticket['id']}")
assert thread.status_code == 200 and "Požiadavku som prevzal".encode("utf-8") in thread.data
assert b"ticketLiveIndicator" in thread.data and b"ticketReplyForm" in thread.data

# Restore the customer administrator for the remaining privacy/IDOR suite.
force_user_session(smoke_admin)

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
    assert "data/tickets.json" in z.namelist()
    assert "data/ticket_messages.json" in z.namelist()
    ticket_export = json.loads(z.read("data/tickets.json"))
    assert any(t["ticket_no"] == ticket["ticket_no"] for t in ticket_export)

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

# ----- GAMO platform support inbox without broad customer-data consent -----
client.get("/logout")
r = login_password("admin@gamo.sk", "TestGamo2026!")
assert r.status_code in (302, 303)
r = client.get(f"/platform/customer/{customer['id']}")
assert r.status_code == 200
assert b"Private Customer Building" not in r.data
assert b"CUSTOMER SECURITY POSTURE" in r.data

# Customer-created tickets are an explicit support communication channel:
# GAMO may see/reply to that ticket, but still may not browse other tenant data.
platform_inbox = client.get("/tickets")
assert platform_inbox.status_code == 200
assert b"Nefunguje klimatiz" in platform_inbox.data
assert b"Smoke Customer" in platform_inbox.data
platform_notifications = client.get("/api/notifications").get_json()
assert any(x.get("url") == f"/ticket/{ticket['id']}" for x in platform_notifications)
platform_thread = client.get(f"/ticket/{ticket['id']}")
assert platform_thread.status_code == 200
assert "Prosím správcu".encode("utf-8") in platform_thread.data
assert "Požiadavku som prevzal".encode("utf-8") in platform_thread.data
assert client.get(f"/building/{private_building['id']}").status_code == 404

r = client.post(
    f"/ticket/{ticket['id']}/message",
    data={"_csrf": csrf(), "message": "GAMO support vidí ticket a odpovedá priamo zákazníkovi."},
    follow_redirects=False,
)
assert r.status_code in (302, 303)
r = client.post(
    f"/ticket/{ticket['id']}/manage",
    data={"_csrf": csrf(), "status": "Rieši sa", "priority": "Vysoká", "assigned_to": str(manager["id"])},
    follow_redirects=False,
)
assert r.status_code in (302, 303)
assert app.one_system(
    "select action from customer_access_log where target_organization_id=? and action='TICKET_SUPPORT_REPLY' order by id desc limit 1",
    (customer["id"],),
)

# Full customer backup still requires explicit support consent.
r = client.get(f"/platform/customer/{customer['id']}/backup", follow_redirects=False)
assert r.status_code in (302, 303)

# ----- Explicit customer consent (login requires MFA) -----
client.get("/logout")
login_with_mfa("smoke@example.test", "SmokeSecure2026!", smoke_mfa_secret)
customer_notifications = client.get("/api/notifications").get_json()
assert any(x.get("url") == f"/ticket/{ticket['id']}" for x in customer_notifications)
customer_ticket_after_gamo = client.get(f"/ticket/{ticket['id']}")
assert customer_ticket_after_gamo.status_code == 200
assert b"GAMO support vid" in customer_ticket_after_gamo.data
assert b"GAMO Support" in customer_ticket_after_gamo.data
live_messages = client.get(f"/api/ticket/{ticket['id']}/messages?after=0").get_json()["messages"]
support_messages = [m for m in live_messages if "GAMO support vid" in m.get("body", "")]
assert support_messages and support_messages[-1]["support"] is True
assert support_messages[-1]["sender_role"] == "GAMO Support"
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

# ----- Rich demo seed for the customer's fdsfsdf building -----
demo_building = app.one_system(
    "select * from buildings where organization_id=? and lower(name)=?",
    (customer["id"], "fdsfsdf"),
)
if not demo_building:
    demo_bid = app.x_system(
        "insert into buildings(code,name,address,manager,customer,status,organization_id) values(?,?,?,?,?,?,?)",
        ("FDSFSDF", "fdsfsdf", "", "", customer["name"], "Aktívna", customer["id"]),
    )
    demo_building = app.one_system("select * from buildings where id=?", (demo_bid,))

with app.con(system=True) as db:
    _migration_12(db, app.USING_POSTGRES)
    db.commit()

demo_bid = demo_building["id"]
assert app.one_system(
    "select count(*) n from floors where building_id=?", (demo_bid,)
)["n"] >= 3
assert app.one_system(
    "select count(*) n from rooms r join floors f on f.id=r.floor_id where f.building_id=?", (demo_bid,)
)["n"] >= 8
assert app.one_system(
    "select count(*) n from assets where building_id=? and organization_id=?", (demo_bid, customer["id"])
)["n"] >= 12
assert app.one_system(
    "select count(*) n from workorders w join assets a on a.id=w.asset_id where a.building_id=?", (demo_bid,)
)["n"] >= 7
assert app.one_system(
    "select count(*) n from incidents i join assets a on a.id=i.asset_id where a.building_id=?", (demo_bid,)
)["n"] >= 4
assert app.one_system(
    "select count(*) n from documents where building_id=?", (demo_bid,)
)["n"] >= 3
assert app.one_system(
    "select count(*) n from tickets where organization_id=? and building_id=?", (customer["id"], demo_bid)
)["n"] >= 3
assert app.one_system(
    "select count(*) n from ticket_messages where organization_id=? and ticket_id in (select id from tickets where building_id=?)",
    (customer["id"], demo_bid),
)["n"] >= 7
demo_ahu = app.one_system(
    "select id from assets where organization_id=? and asset_id=?",
    (customer["id"], "HVAC-900001"),
)
assert demo_ahu
assert app.one_system(
    "select count(*) n from assets where organization_id=? and parent_id=?",
    (customer["id"], demo_ahu["id"]),
)["n"] >= 2

# The seed is idempotent and stays inside this customer.
before_demo_assets = app.one_system(
    "select count(*) n from assets where building_id=? and organization_id=?",
    (demo_bid, customer["id"]),
)["n"]
with app.con(system=True) as db:
    _migration_12(db, app.USING_POSTGRES)
    db.commit()
after_demo_assets = app.one_system(
    "select count(*) n from assets where building_id=? and organization_id=?",
    (demo_bid, customer["id"]),
)["n"]
assert before_demo_assets == after_demo_assets
assert app.one_system(
    "select count(*) n from assets where asset_id like ? and organization_id<>?",
    ("HVAC-900%", customer["id"]),
)["n"] == 0

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
