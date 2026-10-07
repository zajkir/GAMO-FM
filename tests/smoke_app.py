import io
import os
import tempfile

tmp = tempfile.mkdtemp(prefix="gamo-smoke-")
os.environ.pop("DATABASE_URL", None)
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
r = client.get("/assets")
assert r.status_code == 200
assert b"HVAC-000001" not in r.data

print("GAMO smoke test OK")
