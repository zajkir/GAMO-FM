from pathlib import Path
import hashlib
import json
import os
import tempfile

root = Path(__file__).resolve().parents[1]

import sys
sys.path.insert(0, str(root))
import updater

source = (root / "updater.py").read_text(encoding="utf-8")
version = json.loads((root / "version.json").read_text(encoding="utf-8"))["version"]

assert "def check_for_update(" in source
assert "def download_update(" in source
assert "def launch_installer(" in source
assert "sha256" in source.lower()
assert "Cache-Control" in source
assert "GAMO_Launcher" not in source
assert "launch_launcher_self_update" not in source
assert "download_launcher_update" not in source

assert updater._version_tuple("9.0.0.24") > updater._version_tuple("9.0.0.23")
assert updater._version_tuple("10.0") > updater._version_tuple("9.99.99")

# Bundled release metadata must win over stale files beside the installed EXE.
with tempfile.TemporaryDirectory() as tmp:
    install = Path(tmp) / "install"
    bundle = Path(tmp) / "bundle"
    install.mkdir()
    bundle.mkdir()
    (install / "version.json").write_text(json.dumps({"version": "9.0.0.1"}), encoding="utf-8")
    (bundle / "version.json").write_text(json.dumps({"version": version}), encoding="utf-8")

    old_app_dir, old_base_dir = updater.APP_DIR, updater.BASE_DIR
    updater.APP_DIR, updater.BASE_DIR = install, bundle
    try:
        assert updater.current_version() == version
    finally:
        updater.APP_DIR, updater.BASE_DIR = old_app_dir, old_base_dir

# SHA-256 helper must detect changed payloads.
with tempfile.TemporaryDirectory() as tmp:
    payload = Path(tmp) / "payload.exe"
    payload.write_bytes(b"GAMO-DIRECT-APP")
    expected = hashlib.sha256(b"GAMO-DIRECT-APP").hexdigest()
    assert updater.file_sha256(payload) == expected

# Legacy local data backup still survives application upgrades.
with tempfile.TemporaryDirectory() as tmp:
    old = os.environ.get("LOCALAPPDATA")
    os.environ["LOCALAPPDATA"] = tmp
    try:
        data = Path(tmp) / "GAMO_FM" / "data"
        data.mkdir(parents=True)
        import sqlite3
        db = sqlite3.connect(data / "gamo.db")
        db.execute("create table demo(id integer primary key, value text)")
        db.execute("insert into demo(value) values('safe')")
        db.commit()
        db.close()

        backup = updater.backup_user_data("test")
        assert backup and backup.exists()
        check = sqlite3.connect(backup)
        assert check.execute("select value from demo").fetchone()[0] == "safe"
        check.close()
    finally:
        if old is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = old

print("Direct application update regression checks OK")
