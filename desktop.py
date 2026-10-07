import json
import os
import socket
import sys
import threading
import time
import tkinter as tk
import urllib.request
from pathlib import Path
from tkinter import messagebox

import webview

from updater import check_for_update, download_update, launch_installer, current_version, backup_user_data

HOST = '127.0.0.1'
PORT = 5050
BASE_DIR = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent


def _load_desktop_config():
    defaults = {
        'mode': 'cloud',
        'server_url': 'https://gamo-fm.onrender.com',
        'connect_timeout_seconds': 20,
        'allow_local_fallback': False,
    }
    for base in (APP_DIR, BASE_DIR):
        p = base / 'desktop_config.json'
        if p.exists():
            try:
                cfg = json.loads(p.read_text(encoding='utf-8-sig'))
                defaults.update(cfg)
                break
            except Exception as exc:
                print(f'Desktop config ignored: {exc}')
    env_url = os.environ.get('GAMO_SERVER_URL', '').strip()
    if env_url:
        defaults['server_url'] = env_url
    return defaults


CONFIG = _load_desktop_config()


def run_local_server():
    os.environ['GAMO_DESKTOP'] = '1'
    from waitress import serve
    from app import app
    serve(app, host=HOST, port=PORT, threads=8)


def wait_for_local_server(timeout=12):
    end = time.time() + timeout
    while time.time() < end:
        try:
            with socket.create_connection((HOST, PORT), timeout=0.25):
                return True
        except OSError:
            time.sleep(0.12)
    return False


def cloud_available(url, timeout):
    try:
        req = urllib.request.Request(
            url.rstrip('/') + '/login',
            headers={'User-Agent': f'GAMO-Facility-Desktop/{current_version()}'},
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return 200 <= response.status < 500
    except Exception as exc:
        print(f'Cloud connectivity check failed: {exc}')
        return False


def _update_before_start():
    try:
        manifest = check_for_update()
        if not manifest:
            return False
        root = tk.Tk()
        root.withdraw()
        notes = str(manifest.get('notes', '')).strip()
        msg = f"Je dostupná nová verzia GAMO a.s. {manifest['version']} (máš {current_version()})."
        if notes:
            msg += f"\n\n{notes}"
        msg += "\n\nStiahnuť a nainštalovať aktualizáciu teraz?"
        yes = messagebox.askyesno('GAMO a.s. – aktualizácia', msg, parent=root)
        if yes:
            installer = download_update(manifest)
            # Legacy/local data are still backed up before every update. Cloud
            # customer data live on the server and are not touched by installer updates.
            backup = backup_user_data('pre_update')
            if backup:
                print(f'Legacy local data backup created: {backup}')
            launch_installer(installer)
            root.destroy()
            return True
        root.destroy()
    except Exception as exc:
        print(f'Update check skipped: {exc}')
    return False


def _show_startup_error(message):
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror('GAMO a.s. – pripojenie', message, parent=root)
    root.destroy()


def main():
    if _update_before_start():
        return

    mode = str(CONFIG.get('mode', 'cloud')).lower()
    cloud_url = str(CONFIG.get('server_url', '')).strip().rstrip('/')
    timeout = max(3, int(CONFIG.get('connect_timeout_seconds', 20)))

    if mode == 'cloud' and cloud_url.startswith(('https://', 'http://')):
        if cloud_available(cloud_url, timeout):
            target_url = cloud_url
        elif CONFIG.get('allow_local_fallback'):
            threading.Thread(target=run_local_server, daemon=True, name='GAMO-Local-Server').start()
            if not wait_for_local_server():
                _show_startup_error('Cloud platforma nie je dostupná a lokálny fallback sa nepodarilo spustiť.')
                return
            target_url = f'http://{HOST}:{PORT}'
        else:
            _show_startup_error(
                'GAMO Facility Platform sa momentálne nevie pripojiť k serveru.\n\n'
                'Skontroluj internetové pripojenie a skús aplikáciu spustiť znova.'
            )
            return
    else:
        threading.Thread(target=run_local_server, daemon=True, name='GAMO-Local-Server').start()
        if not wait_for_local_server():
            raise RuntimeError('GAMO a.s. lokálny server sa nepodarilo spustiť.')
        target_url = f'http://{HOST}:{PORT}'

    webview.create_window(
        f'GAMO a.s. {current_version()} — Facility Platform',
        target_url,
        width=1500,
        height=920,
        min_size=(1100, 700),
        resizable=True,
        confirm_close=True,
        text_select=True,
    )
    webview.start(debug=False)


if __name__ == '__main__':
    main()
