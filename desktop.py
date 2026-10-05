import os
import socket
import threading
import time
import tkinter as tk
from tkinter import messagebox

os.environ['GAMO_DESKTOP'] = '1'

from waitress import serve
import webview
from app import app
from updater import check_for_update, download_update, launch_installer, current_version

HOST = '127.0.0.1'
PORT = 5050


def run_server():
    serve(app, host=HOST, port=PORT, threads=8)


def wait_for_server(timeout=12):
    end = time.time() + timeout
    while time.time() < end:
        try:
            with socket.create_connection((HOST, PORT), timeout=0.25):
                return True
        except OSError:
            time.sleep(0.12)
    return False


def _update_before_start():
    try:
        manifest = check_for_update()
        if not manifest:
            return False
        root = tk.Tk(); root.withdraw()
        notes = str(manifest.get('notes', '')).strip()
        msg = f"Je dostupná nová verzia GAMO FM {manifest['version']} (máš {current_version()})."
        if notes:
            msg += f"\n\n{notes}"
        msg += "\n\nStiahnuť a nainštalovať aktualizáciu teraz?"
        yes = messagebox.askyesno('GAMO FM – aktualizácia', msg, parent=root)
        if yes:
            installer = download_update(manifest)
            launch_installer(installer)
            root.destroy()
            return True
        root.destroy()
    except Exception as exc:
        print(f'Update check skipped: {exc}')
    return False


def main():
    if _update_before_start():
        return
    threading.Thread(target=run_server, daemon=True, name='GAMO-FM-Server').start()
    if not wait_for_server():
        raise RuntimeError('GAMO FM server sa nepodarilo spustiť.')
    webview.create_window(
        f'GAMO FM {current_version()} — Facility Management',
        f'http://{HOST}:{PORT}',
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
