import ctypes
import json
import os
import subprocess
import sys
import threading
import traceback
import urllib.request
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from updater import (
    backup_user_data,
    check_for_update,
    current_version,
    download_update,
    launch_installer_after_process_exit,
)

BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent

NAVY = "#07182C"
NAVY_2 = "#0B2440"
NAVY_3 = "#10355D"
BLUE = "#2F6DF6"
BLUE_DARK = "#2459CA"
BLUE_SOFT = "#EDF3FF"
GREEN = "#15865F"
GREEN_SOFT = "#E7F7EF"
RED = "#C93B50"
RED_SOFT = "#FDECEF"
AMBER = "#A86B00"
AMBER_SOFT = "#FFF3D8"
TEXT = "#172337"
MUTED = "#6F7D91"
SOFT_TEXT = "#8D9AAF"
LINE = "#E1E7EF"
BG = "#EEF2F7"
CARD = "#F8FAFD"
WHITE = "#FFFFFF"


def load_desktop_config():
    defaults = {
        "server_url": "https://gamo-fm.onrender.com",
        "connect_timeout_seconds": 8,
    }
    for base in (APP_DIR, BASE_DIR):
        path = base / "desktop_config.json"
        if path.exists():
            try:
                defaults.update(json.loads(path.read_text(encoding="utf-8-sig")))
                break
            except Exception:
                pass
    env_url = os.environ.get("GAMO_SERVER_URL", "").strip()
    if env_url:
        defaults["server_url"] = env_url
    return defaults


def log_path():
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "GAMO_FM" / "logs"
    base.mkdir(parents=True, exist_ok=True)
    return base / "launcher.log"


def write_log(message):
    try:
        with log_path().open("a", encoding="utf-8") as handle:
            handle.write(f"{datetime.now().isoformat(timespec='seconds')}  {message}\n")
    except Exception:
        pass


def single_instance_guard():
    if os.name != "nt":
        return None
    kernel32 = ctypes.windll.kernel32
    for name in ("Global\\GAMO_Facility_Launcher", "Local\\GAMO_Facility_Launcher"):
        try:
            handle = kernel32.CreateMutexW(None, False, name)
            if not handle:
                continue
            if kernel32.GetLastError() == 183:
                kernel32.CloseHandle(handle)
                return False
            return handle
        except Exception:
            continue
    return None


class Launcher(tk.Tk):
    def __init__(self):
        super().__init__()
        self.config_data = load_desktop_config()
        self.server_url = str(self.config_data.get("server_url", "")).strip().rstrip("/")
        self.timeout = max(3, min(15, int(self.config_data.get("connect_timeout_seconds", 8))))
        self.online = False
        self.update_manifest = None
        self.busy = False
        self.launching = False
        self._fullscreen = False
        self._closing = False

        self.title("GAMO a.s. — Facility Platform")
        self.geometry("1180x720")
        self.minsize(1000, 640)
        self.configure(bg=BG)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind("<F11>", self.toggle_fullscreen)
        self.bind("<Escape>", self.exit_fullscreen)
        self.report_callback_exception = self._callback_error

        try:
            self.state("normal")
        except tk.TclError:
            pass

        self._center()
        self._build_styles()
        self._build_ui()
        self._post(220, self.refresh_status)

    def _center(self):
        self.update_idletasks()
        width, height = 1180, 720
        x = max(0, (self.winfo_screenwidth() - width) // 2)
        y = max(0, (self.winfo_screenheight() - height) // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _post(self, delay, callback):
        if self._closing:
            return
        try:
            self.after(delay, lambda: None if self._closing else callback())
        except tk.TclError:
            pass

    def _callback_error(self, exc_type, exc_value, exc_tb):
        detail = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        write_log("UI exception:\n" + detail)
        if self._closing:
            return
        try:
            messagebox.showerror(
                "GAMO a.s. — Launcher",
                "Launcher zachytil chybu rozhrania. Aplikácia zostala bezpečne otvorená.\n\n"
                "Ak sa problém zopakuje, pošli súbor launcher.log podpore.",
                parent=self,
            )
        except Exception:
            pass

    def _close(self):
        self._closing = True
        try:
            self.destroy()
        except tk.TclError:
            pass

    def toggle_fullscreen(self, _event=None):
        self._fullscreen = not self._fullscreen
        try:
            self.attributes("-fullscreen", self._fullscreen)
        except tk.TclError:
            pass
        return "break"

    def exit_fullscreen(self, _event=None):
        if self._fullscreen:
            self._fullscreen = False
            try:
                self.attributes("-fullscreen", False)
            except tk.TclError:
                pass
        return "break"

    def _build_styles(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "GAMO.Horizontal.TProgressbar",
            troughcolor="#E7ECF3",
            background=BLUE,
            bordercolor="#E7ECF3",
            lightcolor=BLUE,
            darkcolor=BLUE,
            thickness=7,
        )

    def _label(self, parent, text, size=10, weight="normal", fg=TEXT, bg=WHITE, **kwargs):
        return tk.Label(
            parent,
            text=text,
            font=("Segoe UI", size, weight),
            fg=fg,
            bg=bg,
            **kwargs,
        )

    def _button(self, parent, text, command, primary=False, small=False):
        bg = BLUE if primary else WHITE
        fg = WHITE if primary else TEXT
        active_bg = BLUE_DARK if primary else BLUE_SOFT
        btn = tk.Button(
            parent,
            text=text,
            command=command,
            relief="flat",
            bd=0,
            bg=bg,
            fg=fg,
            activebackground=active_bg,
            activeforeground=WHITE if primary else BLUE,
            disabledforeground="#A9B5C5",
            font=("Segoe UI", 10 if small else 11, "bold"),
            padx=16 if small else 22,
            pady=8 if small else 12,
            cursor="hand2",
            highlightthickness=0,
        )
        return btn

    def _build_ui(self):
        shell = tk.Frame(self, bg=WHITE, highlightthickness=1, highlightbackground="#D9E1EB")
        shell.pack(fill="both", expand=True, padx=22, pady=22)
        shell.grid_rowconfigure(0, weight=1)
        shell.grid_columnconfigure(0, minsize=300)
        shell.grid_columnconfigure(1, weight=1)

        self._build_sidebar(shell)
        self._build_main(shell)

    def _build_sidebar(self, shell):
        left = tk.Frame(shell, bg=NAVY, width=300)
        left.grid(row=0, column=0, sticky="nsew")
        left.grid_propagate(False)
        left.grid_rowconfigure(5, weight=1)

        brand = tk.Frame(left, bg=NAVY)
        brand.grid(row=0, column=0, sticky="ew", padx=30, pady=(32, 0))
        g = tk.Label(
            brand, text="G", bg=BLUE, fg=WHITE,
            font=("Segoe UI", 20, "bold"), width=2, height=1
        )
        g.pack(side="left")
        btxt = tk.Frame(brand, bg=NAVY)
        btxt.pack(side="left", padx=(13, 0))
        self._label(btxt, "GAMO a.s.", 18, "bold", WHITE, NAVY).pack(anchor="w")
        self._label(btxt, "FACILITY PLATFORM", 8, "bold", "#83A0C1", NAVY).pack(anchor="w", pady=(2, 0))

        self._label(
            left,
            "Riadenie budov,\ntechnológií a servisu.",
            19, "bold", WHITE, NAVY, justify="left"
        ).grid(row=1, column=0, sticky="w", padx=30, pady=(64, 0))

        self._label(
            left,
            "Bezpečný desktop klient pre cloudové\nprostredie GAMO. Žiadna lokálna databáza\nzákazníka, žiadne manuálne aktualizácie.",
            10, "normal", "#A8BDD4", NAVY, justify="left"
        ).grid(row=2, column=0, sticky="w", padx=30, pady=(18, 0))

        features = tk.Frame(left, bg=NAVY)
        features.grid(row=3, column=0, sticky="ew", padx=30, pady=(45, 0))
        for title, subtitle in (
            ("Cloudové dáta", "Centrálne a tenantovo izolované"),
            ("Automatické aktualizácie", "Overené cez SHA-256"),
            ("Bezpečný prístup", "HTTPS · RLS · MFA"),
        ):
            row = tk.Frame(features, bg=NAVY)
            row.pack(fill="x", pady=9)
            badge = tk.Label(
                row, text="✓", bg=NAVY_3, fg="#69D9AA",
                font=("Segoe UI", 9, "bold"), width=2, height=1
            )
            badge.pack(side="left", anchor="n")
            copy = tk.Frame(row, bg=NAVY)
            copy.pack(side="left", fill="x", expand=True, padx=(10, 0))
            self._label(copy, title, 10, "bold", WHITE, NAVY).pack(anchor="w")
            self._label(copy, subtitle, 8, "normal", "#8EA6C0", NAVY).pack(anchor="w", pady=(2, 0))

        footer = tk.Frame(left, bg=NAVY)
        footer.grid(row=6, column=0, sticky="sew", padx=30, pady=(0, 28))
        self._label(footer, "DESKTOP CLIENT", 8, "bold", "#6F89A6", NAVY).pack(anchor="w")
        self._label(footer, f"v{current_version()}", 10, "bold", "#B8C9DA", NAVY).pack(anchor="w", pady=(3, 0))

    def _build_main(self, shell):
        main = tk.Frame(shell, bg=WHITE)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(6, weight=1)

        top = tk.Frame(main, bg=WHITE)
        top.grid(row=0, column=0, sticky="ew", padx=42, pady=(38, 0))
        top.grid_columnconfigure(0, weight=1)

        eyebrow = tk.Frame(top, bg=WHITE)
        eyebrow.grid(row=0, column=0, sticky="ew")
        self._label(eyebrow, "GAMO CLOUD CLIENT", 9, "bold", BLUE, WHITE).pack(side="left")
        self._label(eyebrow, "F11  ·  celá obrazovka", 8, "normal", SOFT_TEXT, WHITE).pack(side="right")

        self._label(top, "Facility Platform", 30, "bold", TEXT, WHITE).grid(row=1, column=0, sticky="w", pady=(8, 0))
        self._label(
            top,
            "Rýchly a bezpečný vstup do cloudového prostredia GAMO a.s.",
            11, "normal", MUTED, WHITE,
        ).grid(row=2, column=0, sticky="w", pady=(5, 0))

        status = tk.Frame(main, bg=CARD, highlightthickness=1, highlightbackground=LINE)
        status.grid(row=1, column=0, sticky="ew", padx=42, pady=(28, 14))
        status.grid_columnconfigure(1, weight=1)

        self.status_badge = tk.Label(
            status, text="…", bg=AMBER_SOFT, fg=AMBER,
            font=("Segoe UI", 14, "bold"), width=3, height=1
        )
        self.status_badge.grid(row=0, column=0, rowspan=2, padx=(18, 12), pady=18)

        self.status_title = self._label(status, "Kontrolujem systém…", 13, "bold", TEXT, CARD)
        self.status_title.grid(row=0, column=1, sticky="sw", pady=(14, 0))
        self.status_detail = self._label(status, "Pripájam sa ku GAMO Cloud.", 9, "normal", MUTED, CARD)
        self.status_detail.grid(row=1, column=1, sticky="nw", pady=(3, 14))

        self.refresh_btn = self._button(status, "↻  Obnoviť", self.refresh_status, small=True)
        self.refresh_btn.grid(row=0, column=2, rowspan=2, padx=16, pady=14)

        info = tk.Frame(main, bg=WHITE)
        info.grid(row=2, column=0, sticky="ew", padx=42)
        for i in range(3):
            info.grid_columnconfigure(i, weight=1)

        self.version_info = self._info_box(info, 0, "VERZIA", f"v{current_version()}")
        self.cloud_info = self._info_box(info, 1, "GAMO CLOUD", "Kontrola…")
        self.security_info = self._info_box(info, 2, "PRIPOJENIE", "HTTPS")

        self.update_card = tk.Frame(main, bg=BLUE_SOFT, highlightthickness=1, highlightbackground="#D6E4FF")
        self.update_card.grid_columnconfigure(0, weight=1)
        self.update_title = self._label(self.update_card, "Je dostupná nová verzia", 10, "bold", TEXT, BLUE_SOFT)
        self.update_title.grid(row=0, column=0, sticky="w", padx=16, pady=(12, 2))
        self.update_detail = self._label(self.update_card, "Odporúčame aktualizovať pred spustením.", 8, "normal", MUTED, BLUE_SOFT)
        self.update_detail.grid(row=1, column=0, sticky="w", padx=16, pady=(0, 12))
        self.update_btn = self._button(self.update_card, "Aktualizovať", self.install_update, primary=True, small=True)
        self.update_btn.grid(row=0, column=1, rowspan=2, padx=14, pady=10)
        self.update_card.grid(row=3, column=0, sticky="ew", padx=42, pady=(14, 0))
        self.update_card.grid_remove()

        self.progress_var = tk.DoubleVar(value=0)
        self.progress = ttk.Progressbar(
            main, variable=self.progress_var, maximum=100, style="GAMO.Horizontal.TProgressbar"
        )
        self.progress.grid(row=4, column=0, sticky="ew", padx=42, pady=(11, 0))
        self.progress.grid_remove()

        actions = tk.Frame(main, bg=WHITE)
        actions.grid(row=5, column=0, sticky="ew", padx=42, pady=(20, 0))
        actions.grid_columnconfigure(0, weight=1)

        self.launch_btn = self._button(actions, "Spustiť GAMO a.s.  →", self.launch_app, primary=True)
        self.launch_btn.grid(row=0, column=0, sticky="ew")
        self.launch_btn.config(state="disabled")

        hint = tk.Frame(main, bg=WHITE)
        hint.grid(row=6, column=0, sticky="sew", padx=42, pady=(24, 0))
        self._label(
            hint,
            "Launcher kontroluje iba dostupnosť cloudu a aktualizácie.\n"
            "Po spustení sa bezpečne zatvorí a nezaťažuje aplikáciu na pozadí.",
            9, "normal", SOFT_TEXT, WHITE, justify="left"
        ).pack(anchor="sw", pady=(0, 14))

        bottom = tk.Frame(main, bg="#F8FAFD", highlightthickness=1, highlightbackground="#EEF2F6")
        bottom.grid(row=7, column=0, sticky="ew")
        self._label(
            bottom,
            "GAMO a.s.   ·   Cloud Facility Platform   ·   HTTPS   ·   automatické aktualizácie",
            8, "normal", "#8492A5", "#F8FAFD"
        ).pack(pady=13)

    def _info_box(self, parent, column, label, value):
        box = tk.Frame(parent, bg=CARD, highlightthickness=1, highlightbackground=LINE)
        box.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 6, 0 if column == 2 else 6))
        self._label(box, label, 8, "bold", "#7B899D", CARD).pack(anchor="w", padx=14, pady=(12, 0))
        value_label = self._label(box, value, 12, "bold", TEXT, CARD)
        value_label.pack(anchor="w", padx=14, pady=(4, 12))
        box.value_label = value_label
        return box

    def set_status(self, title, detail, state="checking"):
        palette = {
            "checking": (AMBER_SOFT, AMBER, "…"),
            "online": (GREEN_SOFT, GREEN, "✓"),
            "offline": (RED_SOFT, RED, "!"),
            "update": (BLUE_SOFT, BLUE, "↥"),
        }
        bg, fg, symbol = palette.get(state, palette["checking"])
        self.status_title.config(text=title)
        self.status_detail.config(text=detail)
        self.status_badge.config(text=symbol, bg=bg, fg=fg)

    def probe_server(self):
        if not self.server_url.startswith(("https://", "http://")):
            return False
        req = urllib.request.Request(
            self.server_url + "/login",
            method="HEAD",
            headers={
                "User-Agent": f"GAMO-Launcher/{current_version()}",
                "Cache-Control": "no-cache",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return 200 <= response.status < 500
        except Exception as exc:
            write_log(f"Cloud probe failed: {exc}")
            return False

    def refresh_status(self):
        if self.busy or self._closing:
            return
        self.busy = True
        self.launch_btn.config(state="disabled")
        self.refresh_btn.config(state="disabled")
        self.update_card.grid_remove()
        self.progress.grid_remove()
        self.progress_var.set(0)
        self.set_status("Kontrolujem GAMO Cloud…", "Overujem dostupnosť servera a aktualizácie.", "checking")
        self.cloud_info.value_label.config(text="Kontrola…")
        threading.Thread(target=self._refresh_worker, daemon=True, name="GAMO-Launcher-Check").start()

    def _refresh_worker(self):
        online = self.probe_server()
        manifest = None
        update_error = None
        if online:
            try:
                manifest = check_for_update()
            except Exception as exc:
                update_error = str(exc)
                write_log(f"Update check skipped: {exc}")
        self._post(0, lambda: self._finish_refresh(online, manifest, update_error))

    def _finish_refresh(self, online, manifest, update_error):
        if self._closing:
            return
        self.busy = False
        self.online = online
        self.update_manifest = manifest
        self.refresh_btn.config(state="normal")

        if not online:
            self.cloud_info.value_label.config(text="Nedostupný")
            self.security_info.value_label.config(text="Čaká na cloud")
            self.set_status(
                "GAMO Cloud nie je dostupný",
                "Skontroluj internetové pripojenie a potom klikni na Obnoviť.",
                "offline",
            )
            self.launch_btn.config(state="disabled")
            return

        self.cloud_info.value_label.config(text="Online")
        self.security_info.value_label.config(text="HTTPS · OK")
        self.launch_btn.config(state="normal")

        if manifest:
            version = str(manifest.get("version", "nová"))
            self.set_status(
                f"Aktualizácia v{version} je dostupná",
                "Novú verziu môžeš bezpečne nainštalovať jedným kliknutím.",
                "update",
            )
            self.update_title.config(text=f"Nová verzia v{version} je pripravená")
            self.update_btn.config(text=f"Aktualizovať na v{version}", state="normal")
            self.update_card.grid()
        else:
            detail = "Cloud je online. Aplikácia je pripravená na spustenie."
            if update_error:
                detail += " Kontrola aktualizácie sa tentoraz preskočila."
            self.set_status("Všetko je pripravené", detail, "online")

    def install_update(self):
        if not self.update_manifest or self.busy or self._closing:
            return
        self.busy = True
        self.launch_btn.config(state="disabled")
        self.refresh_btn.config(state="disabled")
        self.update_btn.config(state="disabled", text="Sťahujem…")
        self.progress.grid()
        self.set_status("Sťahujem aktualizáciu…", "Po stiahnutí overím SHA-256 kontrolný súčet.", "update")
        threading.Thread(target=self._update_worker, daemon=True, name="GAMO-Launcher-Update").start()

    def _update_worker(self):
        try:
            installer = download_update(
                self.update_manifest,
                progress=lambda value: self._post(0, lambda v=value: self.progress_var.set(v)),
            )
            backup_user_data("pre_update")
            self._post(0, lambda: self.set_status(
                "Aktualizácia je pripravená",
                "Spúšťam overený inštalátor.",
                "online",
            ))
            launch_installer_after_process_exit(installer, os.getpid())
            self._post(80, self._close)
        except Exception as exc:
            write_log(f"Update failed: {exc}")
            self._post(0, lambda e=str(exc): self._update_failed(e))

    def _update_failed(self, detail):
        self.busy = False
        self.refresh_btn.config(state="normal")
        self.launch_btn.config(state="normal" if self.online else "disabled")
        self.update_btn.config(state="normal", text="Skúsiť znova")
        short = detail.strip()[:180] if detail else "Skús to znova."
        self.set_status("Aktualizácia zlyhala", short, "offline")

    def launch_app(self):
        if self.busy or self.launching or not self.online or self._closing:
            return
        self.launching = True
        self.launch_btn.config(state="disabled", text="Spúšťam GAMO a.s. …")
        self.refresh_btn.config(state="disabled")
        executable = APP_DIR / "GAMO_FM.exe"
        env = os.environ.copy()
        env["GAMO_SKIP_UPDATE"] = "1"
        env["GAMO_CLOUD_VERIFIED"] = "1"
        if self.server_url:
            env["GAMO_SERVER_URL"] = self.server_url

        try:
            if executable.exists():
                subprocess.Popen([str(executable)], cwd=str(APP_DIR), env=env, close_fds=True)
            else:
                source = APP_DIR / "desktop.py"
                if not source.exists():
                    source = BASE_DIR / "desktop.py"
                if not source.exists():
                    raise FileNotFoundError("GAMO_FM.exe sa v inštalácii nenašiel.")
                subprocess.Popen([sys.executable, str(source)], cwd=str(source.parent), env=env, close_fds=True)
            self._post(300, self._close)
        except Exception as exc:
            self.launching = False
            self.launch_btn.config(state="normal", text="Spustiť GAMO a.s.  →")
            self.refresh_btn.config(state="normal")
            write_log(f"Application launch failed: {exc}")
            messagebox.showerror(
                "GAMO a.s. — Launcher",
                f"Aplikáciu sa nepodarilo spustiť.\n\n{exc}",
                parent=self,
            )


def main():
    mutex = single_instance_guard()
    if mutex is False:
        return
    write_log(f"Launcher started · v{current_version()}")
    app = Launcher()
    app._mutex = mutex
    app.mainloop()


if __name__ == "__main__":
    main()
