import ctypes
import faulthandler
import json
import os
import sys
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox

import webview

from updater import (
    backup_user_data,
    check_for_update,
    current_version,
    download_update,
    launch_installer,
)

BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
_FAULT_LOG_HANDLE = None


def load_config():
    config = {
        "server_url": "https://gamo-fm.onrender.com",
        "start_maximized": True,
    }
    for base in (BASE_DIR, APP_DIR):
        path = base / "desktop_config.json"
        if path.exists():
            try:
                config.update(json.loads(path.read_text(encoding="utf-8-sig")))
                break
            except Exception:
                pass

    env_url = os.environ.get("GAMO_SERVER_URL", "").strip()
    if env_url:
        config["server_url"] = env_url
    return config


CONFIG = load_config()


def log_path():
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "GAMO_FM" / "logs"
    base.mkdir(parents=True, exist_ok=True)
    return base / "app.log"


def write_log(message):
    try:
        path = log_path()
        if path.exists() and path.stat().st_size > 1_000_000:
            previous = path.with_name("app.previous.log")
            previous.unlink(missing_ok=True)
            path.replace(previous)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"{datetime.now().isoformat(timespec='seconds')}  {message}\n")
    except Exception:
        pass


def enable_crash_diagnostics():
    global _FAULT_LOG_HANDLE
    try:
        _FAULT_LOG_HANDLE = log_path().with_name("app-crash.log").open("a", encoding="utf-8")
        _FAULT_LOG_HANDLE.write(
            f"\n{datetime.now().isoformat(timespec='seconds')}  diagnostics enabled · "
            f"pid={os.getpid()} · argv={sys.argv!r}\n"
        )
        _FAULT_LOG_HANDLE.flush()
        faulthandler.enable(file=_FAULT_LOG_HANDLE, all_threads=True)
    except Exception as exc:
        write_log(f"Crash diagnostics unavailable: {exc}")


def enable_high_dpi():
    if os.name != "nt":
        return
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass


def single_instance_guard():
    if os.name != "nt":
        return None
    try:
        handle = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\GAMO_Facility_Desktop")
        if not handle:
            return None
        if ctypes.windll.kernel32.GetLastError() == 183:
            ctypes.windll.kernel32.CloseHandle(handle)
            return False
        return handle
    except Exception:
        return None


def webview_storage_path():
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "GAMO_FM" / "webview"
    base.mkdir(parents=True, exist_ok=True)
    return base


def show_error(title, message):
    try:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(title, message, parent=root)
        root.destroy()
    except Exception:
        pass


def check_update_before_open():
    """Offer a verified installer update without showing any launcher UI."""
    try:
        manifest = check_for_update()
        if not manifest:
            return False

        root = tk.Tk()
        root.withdraw()
        version = str(manifest.get("version", "")).strip()
        notes = str(manifest.get("notes", "")).strip()
        message = f"Je dostupná nová verzia GAMO a.s. {version} (máš {current_version()})."
        if notes:
            message += f"\n\n{notes}"
        message += "\n\nNainštalovať aktualizáciu teraz?"

        install_now = messagebox.askyesno("GAMO a.s. — aktualizácia", message, parent=root)
        root.destroy()
        if not install_now:
            return False

        installer = download_update(manifest)
        backup_user_data("pre_update")
        launch_installer(installer)
        write_log(f"Verified installer update started · target={version}")
        return True
    except Exception as exc:
        # An update server issue must never prevent the application from opening.
        write_log(f"Update check skipped: {exc}")
        return False


class DesktopApi:
    def __init__(self):
        self.window = None

    def bind_window(self, window):
        self.window = window

    def toggle_fullscreen(self):
        try:
            if self.window:
                self.window.toggle_fullscreen()
                return True
        except Exception as exc:
            write_log(f"Fullscreen toggle failed: {exc}")
        return False

    def maximize(self):
        try:
            if self.window:
                self.window.maximize()
                return True
        except Exception as exc:
            write_log(f"Maximize failed: {exc}")
        return False

    def restore(self):
        try:
            if self.window:
                self.window.restore()
                return True
        except Exception as exc:
            write_log(f"Restore failed: {exc}")
        return False


def show_desktop_window(window):
    try:
        if bool(CONFIG.get("start_maximized", True)):
            window.maximize()
    except Exception as exc:
        write_log(f"Window maximize skipped: {exc}")


def main():
    enable_crash_diagnostics()
    enable_high_dpi()

    mutex = single_instance_guard()
    if mutex is False:
        return

    if check_update_before_open():
        return

    server_url = str(CONFIG.get("server_url", "")).strip().rstrip("/")
    if not server_url.startswith(("https://", "http://")):
        show_error(
            "GAMO a.s. — konfigurácia",
            "Aplikácia nemá platnú adresu cloudovej platformy.",
        )
        return

    write_log(
        f"Application started · v{current_version()} · target={server_url} · "
        f"executable={Path(sys.executable).resolve()}"
    )

    api = DesktopApi()
    window = webview.create_window(
        f"GAMO a.s. {current_version()} — Facility Platform",
        server_url,
        width=1500,
        height=920,
        min_size=(1100, 700),
        resizable=True,
        confirm_close=False,
        text_select=True,
        js_api=api,
    )
    api.bind_window(window)

    try:
        webview.settings["ALLOW_DOWNLOADS"] = True
        webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = False
        webview.settings["OPEN_DEVTOOLS_IN_DEBUG"] = False
    except Exception:
        pass

    try:
        webview.start(
            show_desktop_window,
            window,
            debug=False,
            gui="edgechromium",
            private_mode=False,
            storage_path=str(webview_storage_path()),
            user_agent=f"GAMO-Desktop/{current_version()} Windows",
        )
    except Exception as exc:
        write_log(f"Desktop WebView failed: {exc}")
        show_error(
            "GAMO a.s. — aplikácia",
            "GAMO a.s. sa nepodarilo spustiť.\n\n"
            "Skontroluj Microsoft Edge WebView2 Runtime a internetové pripojenie.\n\n"
            f"Detail: {exc}",
        )


if __name__ == "__main__":
    main()
