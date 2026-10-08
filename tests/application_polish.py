import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if not os.environ.get("DATABASE_URL"):
    os.environ["GAMO_DATA_DIR"] = tempfile.mkdtemp(prefix="gamo-polish-")
os.environ["GAMO_ADMIN_PASSWORD"] = "TestGamo2026!"
os.environ["GAMO_HTTPS"] = "0"

import app

client = app.app.test_client()


def csrf(c=client):
    with c.session_transaction() as sess:
        return sess["csrf"]


def login(c=client, remember=False):
    r = c.post(
        "/login",
        data={
            "email": "admin@gamo.sk",
            "password": "TestGamo2026!",
            "remember": "1" if remember else "0",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303), r.status_code
    return r


def planner_rows():
    with client.session_transaction() as sess:
        snapshot = dict(sess)
    with app.app.test_request_context("/maintenance"):
        app.session.update(snapshot)
        return app.maintenance_plan_rows()


login()

# Branded error handling instead of raw Flask pages.
r = client.get("/this-page-does-not-exist")
assert r.status_code == 404
assert b"APPLICATION STATUS" in r.data
assert b"404" in r.data

with client.session_transaction() as sess:
    oid = sess["organization_id"]
admin = app.one_system("select * from users where lower(email)=?", ("admin@gamo.sk",))
assert admin

# Create a small hierarchy for search + redirect tests.
r = client.post(
    "/add/building",
    data={
        "_csrf": csrf(),
        "code": "POL",
        "name": "Polish Building",
        "address": "Quality Street 1",
        "manager": "QA",
        "floors_count": "1",
    },
    follow_redirects=False,
)
assert r.status_code in (302, 303)
building = app.one("select * from buildings where organization_id=? and code=?", (oid, "POL"))
assert building
floor = app.one("select * from floors where building_id=?", (building["id"],))
assert floor

r = client.post(
    "/add/room",
    data={
        "_csrf": csrf(),
        "floor_id": str(floor["id"]),
        "code": "POL-101",
        "name": "Polish Room",
        "area": "21.5",
        "tenant": "QA Tenant",
        "zone": "Search Zone",
    },
    follow_redirects=False,
)
assert r.status_code in (302, 303)
room = app.one("select * from rooms where floor_id=? and code=?", (floor["id"], "POL-101"))
assert room

r = client.post(
    "/add/asset",
    data={
        "_csrf": csrf(),
        "asset_id": "POL-000001",
        "name": "Searchable Fan Unit",
        "building_id": str(building["id"]),
        "floor_id": str(floor["id"]),
        "room_id": str(room["id"]),
        "profession": "HVAC",
        "grp": "Ventilation",
        "type": "FAN",
        "manufacturer": "TestMaker",
        "model": "Alpha 42",
        "serial": "SER-POL-1",
        "system_id": "SYS-POLISH",
        "status": "Prevádzka",
        "criticality": "B",
        "service_months": "6",
        "revision_months": "12",
        "purchase_price": "1250",
    },
    follow_redirects=False,
)
assert r.status_code in (302, 303)
asset = app.one("select * from assets where organization_id=? and asset_id=?", (oid, "POL-000001"))
assert asset

# Preventive maintenance planner: calculate an overdue PM cycle from installation date.
desired_due = app.date.today() - app.timedelta(days=1)
installed = app._add_months(desired_due, -6)
app.x("update assets set installed=?,service_months=?,revision_months=? where id=?", (installed.isoformat(), 6, 12, asset["id"]))
plan = [x for x in planner_rows() if x["asset_db_id"] == asset["id"]]
pm = next(x for x in plan if x["kind"] == "PM")
rev = next(x for x in plan if x["kind"] == "REV")
assert pm["state"] == "overdue" and pm["due"] == desired_due.isoformat()
assert rev["due"] == app._add_months(installed, 12).isoformat()

# Planner warnings appear even before an order exists.
notifications = client.get("/api/notifications").get_json()
assert any(str(x["key"]).startswith(f"planner:{asset['id']}:PM:") for x in notifications), notifications

# Sync creates exactly one generated workorder and is idempotent.
r = client.post("/maintenance/generate", data={"_csrf": csrf()}, follow_redirects=False)
assert r.status_code in (302, 303)
auto_orders = app.q(
    "select * from workorders where asset_id=? and kind='PM' and source='AUTO'",
    (asset["id"],),
)
assert len(auto_orders) == 1
auto_order = auto_orders[0]
assert auto_order["generated_key"]
assert str(auto_order["due"])[:10] == desired_due.isoformat()

r = client.post("/maintenance/generate", data={"_csrf": csrf()}, follow_redirects=False)
assert r.status_code in (302, 303)
assert app.one(
    "select count(*) n from workorders where asset_id=? and kind='PM' and source='AUTO'",
    (asset["id"],),
)["n"] == 1

# Completing the cycle records completion time and moves the next PM forward.
r = client.post(
    f"/status/workorder/{auto_order['id']}",
    data={"_csrf": csrf(), "status": "Ukončené"},
    follow_redirects=False,
)
assert r.status_code in (302, 303)
completed = app.one("select completed_at,status from workorders where id=?", (auto_order["id"],))
assert completed["status"] == "Ukončené" and completed["completed_at"]
next_pm = next(
    x for x in planner_rows()
    if x["asset_db_id"] == asset["id"] and x["kind"] == "PM"
)
assert next_pm["last_done"] == str(completed["completed_at"])[:10]
assert next_pm["due"] == app._add_months(app._as_date(completed["completed_at"]), 6).isoformat()

planner_page = client.get("/maintenance")
assert planner_page.status_code == 200
assert b"AUTOMATICK" in planner_page.data
assert b"POL-000001" in planner_page.data

# Global search is case-insensitive and includes rooms.
results = client.get("/api/search?q=pol-000001").get_json()
assert any(x["kind"] == "Asset" and "POL-000001" in x["title"] for x in results), results
results = client.get("/api/search?q=polish room").get_json()
assert any(x["kind"] == "Miestnosť" and "POL-101" in x["title"] for x in results), results
results = client.get("/api/search?q=alpha 42").get_json()
assert any(x["kind"] == "Asset" for x in results), results

# External Referer must never become a redirect target.
r = client.post(
    f"/status/asset/{asset['id']}",
    data={"_csrf": csrf(), "status": "Servis"},
    headers={"Referer": "https://evil.example/phishing"},
    follow_redirects=False,
)
assert r.status_code in (302, 303)
assert r.headers["Location"] == "/"
assert "evil.example" not in r.headers["Location"]

# Remembered devices are visible and can be revoked by their owner.
remember_client = app.app.test_client()
login(remember_client, remember=True)
with remember_client.session_transaction() as sess:
    remember_uid = sess["user_id"]
remembered = app.one_system(
    "select * from remembered_devices where user_id=? and revoked_at is null order by id desc limit 1",
    (remember_uid,),
)
assert remembered
security_page = remember_client.get("/account/mfa")
assert security_page.status_code == 200
assert b"REMEMBERED DEVICES" in security_page.data
assert (remembered["label"] or "Zapam").encode("utf-8")[:5] in security_page.data

r = remember_client.post(
    f"/account/device/{remembered['id']}/revoke",
    data={"_csrf": csrf(remember_client)},
    follow_redirects=False,
)
assert r.status_code in (302, 303)
assert app.one_system(
    "select revoked_at from remembered_devices where id=?",
    (remembered["id"],),
)["revoked_at"]

# Cross-user device revocation is forbidden as a not-found object.
other_id = app.x_system(
    "insert into users(name,email,role,status,password_hash,organization_id,must_change_password,mfa_enabled) values(?,?,?,?,?,?,?,?)",
    (
        "Other User",
        "other-polish@example.test",
        "Viewer",
        "Aktívny",
        app.generate_password_hash("OtherPass2026!"),
        oid,
        False if app.USING_POSTGRES else 0,
        False if app.USING_POSTGRES else 0,
    ),
)
fake_token = "polish-other-token"
device_id = app.x_system(
    "insert into remembered_devices(organization_id,user_id,token_hash,label,user_agent,ip_created,expires_at) values(?,?,?,?,?,?,?)",
    (
        oid,
        other_id,
        app._remember_hash(fake_token),
        "Other device",
        "Test Agent",
        "127.0.0.2",
        "2099-01-01T00:00:00Z",
    ),
)
r = remember_client.post(
    f"/account/device/{device_id}/revoke",
    data={"_csrf": csrf(remember_client)},
    follow_redirects=False,
)
assert r.status_code == 404
assert app.one_system("select revoked_at from remembered_devices where id=?", (device_id,))["revoked_at"] is None

print("GAMO application polish test OK")


# Application Max source-level UX regression.
repo_root = Path(__file__).resolve().parents[1]
js_source = (repo_root / "static" / "app.js").read_text(encoding="utf-8")
css_source = (repo_root / "static" / "app.css").read_text(encoding="utf-8")
template_source = (repo_root / "templates" / "index.html").read_text(encoding="utf-8")

assert "const FORM_SECTIONS=" in js_source
assert "form-section-title full" in js_source
assert "required-mark" in js_source
assert "GAMO_TICKET_AUTO_RELOAD" in js_source
assert "document.hidden?30000:2500" in js_source
assert "angle=((angle+540)%360)-180" in js_source

assert "/* Application Max polish */" in css_source
assert ".form-section-title" in css_source
assert ".required-mark" in css_source
assert ".dt2-floor-top:before" in css_source
assert "@keyframes windowSweep" in css_source
assert "@keyframes techBeacon" in css_source
assert "@media(prefers-reduced-motion:reduce)" in css_source

assert 'id="confirmModal"' in template_source
assert 'id="digitalTwinV2"' in template_source
assert 'id="ticketInboxRefreshHint"' in template_source
assert 'id="planner"' in template_source
assert "Preventívna údržba & revízie" in template_source
assert "/* Preventive maintenance planner */" in css_source

