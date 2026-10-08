import hashlib
import json
import subprocess
import sys
import tempfile
import urllib.request
import os
import shutil
import ctypes
import time
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


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest().lower()


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
    launcher_url = str(manifest.get('launcher_url', '')).strip()
    launcher_sha = str(manifest.get('launcher_sha256', '')).strip().lower()
    installer_url = str(manifest.get('installer_url', '')).strip()
    installer_sha = str(manifest.get('sha256', '')).strip().lower()
    launcher_valid = launcher_url.startswith('https://') and len(launcher_sha) == 64
    installer_valid = installer_url.startswith('https://') and len(installer_sha) == 64
    if not launcher_valid and not installer_valid:
        raise ValueError('Aktualizačný manifest nemá platný launcher ani installer payload.')
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


def download_launcher_update(manifest, progress=None):
    """Download the preferred one-file launcher payload and verify SHA-256."""
    version = str(manifest['version'])
    url = str(manifest['launcher_url'])
    expected = str(manifest['launcher_sha256']).lower()
    target = update_state_dir() / f'GAMO_Launcher_{version}.new.exe'
    partial = target.with_suffix(target.suffix + '.part')
    partial.unlink(missing_ok=True)
    digest = hashlib.sha256()
    downloaded = 0
    if progress:
        progress(0)
    req = urllib.request.Request(url, headers={'User-Agent': f'GAMO-FM/{current_version()}'})
    try:
        with urllib.request.urlopen(req, timeout=45) as src, partial.open('wb') as dst:
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
        if digest.hexdigest().lower() != expected:
            raise ValueError('Kontrola launcher aktualizácie zlyhala: SHA-256 nesedí.')
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



def cleanup_stale_update_files():
    base = update_state_dir()
    current = Path(sys.executable).resolve()
    now = time.time()
    for pattern in ('GAMO_Update_Helper_*.exe', 'GAMO_Launcher_*.new.exe', 'self_update_*.json'):
        for path in base.glob(pattern):
            try:
                if path.resolve() == current:
                    continue
                if now - path.stat().st_mtime > 60:
                    path.unlink(missing_ok=True)
            except OSError:
                pass


def _wait_for_process_exit(pid, timeout_seconds=120):
    if os.name != 'nt' or not pid:
        return True
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(0x00100000, False, int(pid))
    if not handle:
        return True
    try:
        return kernel32.WaitForSingleObject(handle, int(timeout_seconds * 1000)) == 0
    finally:
        kernel32.CloseHandle(handle)


def _replace_launcher_targets(payload, targets, expected_sha256):
    """Replace launcher aliases only after the old launcher has exited."""
    payload = Path(payload)
    expected = str(expected_sha256).lower()
    if not payload.exists():
        raise FileNotFoundError(f'Update payload neexistuje: {payload}')
    if file_sha256(payload) != expected:
        raise ValueError('Launcher payload neprešiel SHA-256 kontrolou.')

    rollback_dir = update_state_dir() / 'rollback'
    rollback_dir.mkdir(parents=True, exist_ok=True)
    backups = {}
    replaced = []
    try:
        for raw_target in targets:
            target = Path(raw_target)
            target.parent.mkdir(parents=True, exist_ok=True)
            backup = rollback_dir / f'{target.name}.previous'
            if target.exists():
                shutil.copy2(target, backup)
                backups[target] = backup
            staged = target.with_name(target.name + '.gamo-new')
            staged.unlink(missing_ok=True)
            shutil.copy2(payload, staged)
            if file_sha256(staged) != expected:
                raise ValueError(f'Staged launcher neprešiel kontrolou: {target.name}')
            last_error = None
            for _ in range(80):
                try:
                    os.replace(staged, target)
                    last_error = None
                    break
                except (PermissionError, OSError) as exc:
                    last_error = exc
                    time.sleep(0.25)
            if last_error is not None:
                raise last_error
            if file_sha256(target) != expected:
                raise ValueError(f'Nainštalovaný launcher neprešiel kontrolou: {target.name}')
            replaced.append(target)
        return replaced
    except Exception:
        for target in reversed(replaced):
            backup = backups.get(target)
            if backup and backup.exists():
                try:
                    shutil.copy2(backup, target)
                except OSError:
                    pass
        raise


def launch_launcher_self_update(payload, process_id, install_dir=None, version='', expected_sha256=''):
    """Run a detached trusted copy of the current launcher as update helper."""
    if os.name != 'nt' or not getattr(sys, 'frozen', False):
        return False
    install_dir = Path(install_dir or APP_DIR).resolve()
    canonical = install_dir / 'GAMO_Launcher.exe'
    compatibility = install_dir / 'GAMO_FM.exe'
    payload = Path(payload).resolve()
    expected = str(expected_sha256 or file_sha256(payload)).lower()

    state = update_state_dir()
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    helper = state / f'GAMO_Update_Helper_{stamp}.exe'
    job = state / f'self_update_{stamp}.json'
    shutil.copy2(Path(sys.executable).resolve(), helper)
    job.write_text(json.dumps({
        'parent_pid': int(process_id),
        'payload': str(payload),
        'targets': [str(canonical), str(compatibility)],
        'relaunch': str(canonical),
        'expected_sha256': expected,
        'version': str(version or ''),
    }, ensure_ascii=False, indent=2), encoding='utf-8')

    flags = getattr(subprocess, 'DETACHED_PROCESS', 0) | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
    subprocess.Popen(
        [str(helper), '--gamo-update-helper', str(job)],
        close_fds=True,
        creationflags=flags,
        cwd=str(state),
    )
    return True


def run_launcher_self_update_helper(job_path):
    """Apply a downloaded launcher payload, verify it, then relaunch GAMO."""
    job_path = Path(job_path)
    relaunch = None
    version = ''
    try:
        job = json.loads(job_path.read_text(encoding='utf-8-sig'))
        version = str(job.get('version', ''))
        relaunch = Path(job['relaunch'])
        if not _wait_for_process_exit(int(job['parent_pid']), 120):
            raise TimeoutError('Pôvodný launcher sa do 120 sekúnd neukončil.')
        time.sleep(0.7)
        _replace_launcher_targets(
            Path(job['payload']),
            [Path(x) for x in job['targets']],
            str(job['expected_sha256']),
        )
        update_result_path().write_text(json.dumps({
            'status': 'success',
            'message': f'Aktualizácia {version} bola úspešne nainštalovaná a overená.',
            'exit_code': 0,
            'version': version,
            'finished_at': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
        }, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception as exc:
        try:
            update_result_path().write_text(json.dumps({
                'status': 'failed',
                'message': str(exc),
                'exit_code': -1,
                'version': version,
                'finished_at': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
            }, ensure_ascii=False, indent=2), encoding='utf-8')
        except Exception:
            pass
    finally:
        try:
            if relaunch and relaunch.exists():
                subprocess.Popen([str(relaunch)], close_fds=True)
        except Exception:
            pass
        try:
            job_path.unlink(missing_ok=True)
        except OSError:
            pass
    return 0

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
    '/NORESTART',
    '/NOLAUNCH=1'
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
