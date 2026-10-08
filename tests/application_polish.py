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
