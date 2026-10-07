import hashlib
import json
import subprocess
import sys
import tempfile
import urllib.request
import os
import shutil
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent


def _load_json(name, default):
    for base in (APP_DIR, BASE_DIR):
        p = base / name
        if p.exists():
            try:
                return json.loads(p.read_text(encoding='utf-8'))
            except Exception:
                pass
    return default


def current_version():
    return str(_load_json('version.json', {'version': '0.0.0'}).get('version', '0.0.0'))


def _version_tuple(value):
    parts = []
    for p in str(value).split('.'):
        digits = ''.join(c for c in p if c.isdigit())
        parts.append(int(digits or 0))
    return tuple((parts + [0, 0, 0, 0])[:4])


def check_for_update():
    cfg = _load_json('update_config.json', {})
    if not cfg.get('enabled'):
        return None
    url = str(cfg.get('manifest_url', '')).strip()
    if not url.startswith(('https://', 'http://')):
        return None
    timeout = max(1, int(cfg.get('check_timeout_seconds', 4)))
    req = urllib.request.Request(url, headers={'User-Agent': f'GAMO-FM/{current_version()}'})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        manifest = json.loads(response.read().decode('utf-8'))
    remote = str(manifest.get('version', '0.0.0'))
    if _version_tuple(remote) <= _version_tuple(current_version()):
        return None
    installer_url = str(manifest.get('installer_url', '')).strip()
    sha256 = str(manifest.get('sha256', '')).strip().lower()
    if not installer_url.startswith('https://') or len(sha256) != 64:
        raise ValueError('Aktualizačný manifest nemá platnú HTTPS adresu alebo SHA-256.')
    return manifest


def download_update(manifest, progress=None):
    """Download and verify an installer.

    progress, when provided, receives an integer percentage from 0 to 100.
    """
    version = str(manifest['version'])
    url = str(manifest['installer_url'])
    expected = str(manifest['sha256']).lower()
    target = Path(tempfile.gettempdir()) / f'GAMO_FM_Setup_{version}.exe'
    req = urllib.request.Request(url, headers={'User-Agent': f'GAMO-FM/{current_version()}'})
    downloaded = 0
    if progress:
        progress(0)
    with urllib.request.urlopen(req, timeout=30) as src, target.open('wb') as dst:
        total = int(src.headers.get('Content-Length') or 0)
        while True:
            chunk = src.read(1024 * 1024)
            if not chunk:
                break
            dst.write(chunk)
            downloaded += len(chunk)
            if progress and total:
                progress(min(99, int(downloaded * 100 / total)))
    actual = hashlib.sha256(target.read_bytes()).hexdigest().lower()
    if actual != expected:
        target.unlink(missing_ok=True)
        raise ValueError('Kontrola aktualizácie zlyhala: SHA-256 nesedí.')
    if progress:
        progress(100)
    return target



def desktop_data_dir():
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'GAMO_FM' / 'data'


def backup_user_data(reason='update'):
    """Create a safe copy of persistent desktop data before replacing app files."""
    data_dir = desktop_data_dir()
    db = data_dir / 'gamo.db'
    if not db.exists():
        return None
    backup_dir = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'GAMO_FM' / 'backups'
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    target = backup_dir / f'gamo_{reason}_{stamp}.db'
    # SQLite online backup produces a consistent snapshot even if the DB was recently used.
    import sqlite3
    src = sqlite3.connect(str(db))
    dst = sqlite3.connect(str(target))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    # Keep the newest 10 automatic backups.
    backups = sorted(backup_dir.glob('gamo_*.db'), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in backups[10:]:
        try:
            old.unlink()
        except OSError:
            pass
    return target


def restore_latest_backup():
    """Emergency helper: restore the newest automatic backup to the persistent DB path."""
    data_dir = desktop_data_dir()
    backup_dir = data_dir.parent / 'backups'
    backups = sorted(backup_dir.glob('gamo_*.db'), key=lambda p: p.stat().st_mtime, reverse=True)
    if not backups:
        return None
    data_dir.mkdir(parents=True, exist_ok=True)
    target = data_dir / 'gamo.db'
    if target.exists():
        shutil.copy2(target, data_dir / f'gamo_before_restore_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db')
    shutil.copy2(backups[0], target)
    return backups[0]


def launch_installer(path):
    flags = ['/VERYSILENT', '/SUPPRESSMSGBOXES', '/CLOSEAPPLICATIONS', '/RESTARTAPPLICATIONS']
    subprocess.Popen([str(path), *flags], close_fds=True)
