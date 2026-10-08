import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent


def _load_json(name, default):
    # Release metadata bundled inside the one-file application is authoritative.
    for base in (BASE_DIR, APP_DIR):
        path = base / name
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8-sig"))
            except Exception:
                pass
    return default


def current_version():
    return str(_load_json("version.json", {"version": "0.0.0"}).get("version", "0.0.0"))


def _version_tuple(value):
    parts = []
    for part in str(value).split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        parts.append(int(digits or 0))
    return tuple((parts + [0, 0, 0, 0])[:4])


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().lower()


def check_for_update():
    cfg = _load_json("update_config.json", {})
    if not cfg.get("enabled"):
        return None

    url = str(cfg.get("manifest_url", "")).strip()
    if not url.startswith("https://"):
        return None

    timeout = max(1, min(10, int(cfg.get("check_timeout_seconds", 4))))
    sep = "&" if "?" in url else "?"
    req = urllib.request.Request(
        f"{url}{sep}_={int(time.time())}",
        headers={
            "User-Agent": f"GAMO-Desktop/{current_version()}",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        manifest = json.loads(response.read().decode("utf-8"))

    remote = str(manifest.get("version", "0.0.0"))
    if _version_tuple(remote) <= _version_tuple(current_version()):
        return None

    installer_url = str(manifest.get("installer_url", "")).strip()
    installer_sha = str(manifest.get("sha256", "")).strip().lower()
    if not installer_url.startswith("https://") or len(installer_sha) != 64:
        raise ValueError("Aktualizačný manifest nemá platnú HTTPS adresu alebo SHA-256 kontrolný súčet.")
    return manifest


def download_update(manifest, progress=None):
    version = str(manifest["version"])
    url = str(manifest["installer_url"])
    expected = str(manifest["sha256"]).lower()
    target = Path(tempfile.gettempdir()) / f"GAMO_FM_Setup_{version}.exe"
    partial = target.with_suffix(target.suffix + ".part")
    partial.unlink(missing_ok=True)

    req = urllib.request.Request(
        url,
        headers={"User-Agent": f"GAMO-Desktop/{current_version()}"},
    )
    digest = hashlib.sha256()
    downloaded = 0
    if progress:
        progress(0)

    try:
        with urllib.request.urlopen(req, timeout=45) as src, partial.open("wb") as dst:
            total = int(src.headers.get("Content-Length") or 0)
            while True:
                chunk = src.read(512 * 1024)
                if not chunk:
                    break
                dst.write(chunk)
                digest.update(chunk)
                downloaded += len(chunk)
                if progress and total:
                    progress(min(99, int(downloaded * 100 / total)))

        if digest.hexdigest().lower() != expected:
            raise ValueError("Kontrola aktualizácie zlyhala: SHA-256 nesedí.")
        partial.replace(target)
    except Exception:
        partial.unlink(missing_ok=True)
        raise

    if progress:
        progress(100)
    return target


def desktop_data_dir():
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "GAMO_FM" / "data"


def backup_user_data(reason="update"):
    """Back up legacy local SQLite data if an older installation still has it."""
    db_path = desktop_data_dir() / "gamo.db"
    if not db_path.exists():
        return None

    backup_dir = db_path.parent.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    if reason == "daily":
        today = datetime.now().strftime("%Y%m%d")
        existing = sorted(backup_dir.glob(f"gamo_daily_{today}_*.db"))
        if existing:
            return existing[-1]

    target = backup_dir / f"gamo_{reason}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    src = sqlite3.connect(str(db_path))
    dst = sqlite3.connect(str(target))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()

    backups = sorted(backup_dir.glob("gamo_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in backups[10:]:
        try:
            old.unlink()
        except OSError:
            pass
    return target


def restore_latest_backup():
    data_dir = desktop_data_dir()
    backup_dir = data_dir.parent / "backups"
    backups = sorted(backup_dir.glob("gamo_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not backups:
        return None

    data_dir.mkdir(parents=True, exist_ok=True)
    target = data_dir / "gamo.db"
    if target.exists():
        shutil.copy2(
            target,
            data_dir / f"gamo_before_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db",
        )
    shutil.copy2(backups[0], target)
    return backups[0]


def launch_installer(path):
    """Start the verified installer. The current app exits immediately afterwards."""
    flags = [
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/CLOSEAPPLICATIONS",
        "/NORESTART",
    ]
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    return subprocess.Popen(
        [str(Path(path).resolve()), *flags],
        close_fds=True,
        creationflags=creationflags,
    )
