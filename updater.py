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
    partial = target.with_suffix(target.suffix + '.part')
    digest = hashlib.sha256()
    try:
        with urllib.request.urlopen(req, timeout=30) as src, partial.open('wb') as dst:
            total = int(src.headers.get('Content-Length') or 0)
            while True:
                chunk = src.read(512 * 1024)
                if not chunk:
                    break
                dst.write(chunk)
                digest.update(chunk)
                downloaded += len(chunk)
                if progress and total:
                    progress(min(99, int(downloaded * 100 / total)))
        actual = digest.hexdigest().lower()
        if actual != expected:
            raise ValueError('Kontrola aktualizácie zlyhala: SHA-256 nesedí.')
        partial.replace(target)
    except Exception:
        partial.unlink(missing_ok=True)
        raise
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


def update_state_dir():
    base = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'GAMO_FM' / 'updates'
    base.mkdir(parents=True, exist_ok=True)
    return base


def update_result_path():
    return update_state_dir() / 'last_update.json'


def consume_update_result():
    """Read and remove the result written by the detached update helper."""
    path = update_result_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding='utf-8-sig'))
    except Exception:
        data = {'status': 'failed', 'message': 'Výsledok aktualizácie sa nepodarilo načítať.'}
    try:
        path.unlink()
    except OSError:
        pass
    return data


def launch_installer(path):
    flags = ['/VERYSILENT', '/SUPPRESSMSGBOXES', '/CLOSEAPPLICATIONS', '/NORESTART']
    return subprocess.Popen([str(path), *flags], close_fds=True)


def launch_installer_after_process_exit(path, process_id=None, relaunch_path=None, version=''):
    """Install a verified update after the current launcher exits, then relaunch.

    A detached PowerShell helper owns the handoff because Windows cannot replace
    GAMO_Launcher.exe while that executable is still running. The helper waits
    for this PID, runs Inno Setup synchronously, writes a durable result file,
    and starts the newly-installed launcher. If Setup fails or Windows blocks it,
    the previous launcher is started again so the user sees the failure instead
    of the application simply disappearing.
    """
    if os.name != 'nt' or not process_id:
        process = launch_installer(path)
        return process

    installer = str(Path(path).resolve())
    relaunch = str(Path(relaunch_path or (APP_DIR / 'GAMO_Launcher.exe')).resolve())
    pid = int(process_id)
    state_dir = update_state_dir()
    result_file = str(update_result_path())
    log_file = str(state_dir / 'update_helper.log')
    helper = state_dir / f'update_helper_{datetime.now().strftime("%Y%m%d_%H%M%S")}.ps1'

    script = r'''param(
  [int]$LauncherPid,
  [string]$Installer,
  [string]$Relaunch,
  [string]$ResultFile,
  [string]$LogFile,
  [string]$TargetVersion
)
$ErrorActionPreference = 'Stop'

function Write-UpdateLog([string]$Message) {
  try {
    $stamp = (Get-Date).ToString('s')
    Add-Content -LiteralPath $LogFile -Value "$stamp  $Message" -Encoding UTF8
  } catch {}
}

function Save-Result([string]$Status, [string]$Message, [int]$ExitCode) {
  try {
    $payload = [ordered]@{
      status = $Status
      message = $Message
      exit_code = $ExitCode
      version = $TargetVersion
      finished_at = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    } | ConvertTo-Json
    $payload | Set-Content -LiteralPath $ResultFile -Encoding UTF8
  } catch {}
}

try {
  Write-UpdateLog "Waiting for launcher PID $LauncherPid to exit."
  Wait-Process -Id $LauncherPid -ErrorAction SilentlyContinue
  Start-Sleep -Milliseconds 900

  if (-not (Test-Path -LiteralPath $Installer)) {
    throw "Verified installer file is missing: $Installer"
  }

  Write-UpdateLog "Starting installer: $Installer"
  $setup = Start-Process -FilePath $Installer -ArgumentList @(
    '/VERYSILENT',
    '/SUPPRESSMSGBOXES',
    '/CLOSEAPPLICATIONS',
    '/NORESTART'
  ) -Wait -PassThru

  $code = [int]$setup.ExitCode
  Write-UpdateLog "Installer exited with code $code."

  if ($code -eq 0) {
    Save-Result 'success' "Aktualizácia $TargetVersion bola úspešne nainštalovaná." $code
  } else {
    Save-Result 'failed' "Inštalátor skončil s kódom $code." $code
  }
} catch {
  $message = $_.Exception.Message
  Write-UpdateLog "Update helper failed: $message"
  Save-Result 'failed' $message -1
} finally {
  try {
    if (Test-Path -LiteralPath $Relaunch) {
      Write-UpdateLog "Relaunching: $Relaunch"
      Start-Process -FilePath $Relaunch
    } else {
      Write-UpdateLog "Relaunch executable not found: $Relaunch"
    }
  } catch {
    Write-UpdateLog "Relaunch failed: $($_.Exception.Message)"
  }
  try { Remove-Item -LiteralPath $Installer -Force -ErrorAction SilentlyContinue } catch {}
}
'''
    helper.write_text(script, encoding='utf-8-sig')

    creationflags = (
        getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        | getattr(subprocess, 'DETACHED_PROCESS', 0)
    )
    subprocess.Popen(
        [
            'powershell.exe',
            '-NoProfile',
            '-NonInteractive',
            '-ExecutionPolicy',
            'Bypass',
            '-WindowStyle',
            'Hidden',
            '-File',
            str(helper),
            str(pid),
            installer,
            relaunch,
            result_file,
            log_file,
            str(version or ''),
        ],
        close_fds=True,
        creationflags=creationflags,
    )
    return True
