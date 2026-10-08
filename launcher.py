import ctypes
import json
import os
import sys
import threading
import webbrowser
import traceback
import urllib.request
from datetime import datetime
from pathlib import Path
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox, ttk

from updater import (
    backup_user_data,
    check_for_update,
    current_version,
    download_update,
    download_launcher_update,
    can_self_update_install_dir,
    launch_launcher_self_update,
    launch_installer_after_process_exit,
    run_launcher_self_update_helper,
    cleanup_stale_update_files,
    consume_update_result,
)

BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent

NAVY = "#071627"
NAVY_2 = "#0B2038"
NAVY_3 = "#113251"
BLUE = "#246BFD"
BLUE_DARK = "#1857D8"
BLUE_SOFT = "#EEF4FF"
GREEN = "#138A63"
GREEN_SOFT = "#E9F8F1"
RED = "#D94157"
RED_SOFT = "#FDEEF1"
AMBER = "#A76C07"
AMBER_SOFT = "#FFF5DF"
TEXT = "#132238"
MUTED = "#64748A"
SOFT_TEXT = "#8B98A9"
LINE = "#DDE5EF"
BG = "#EAF0F6"
CARD = "#F7F9FC"
CARD_2 = "#F1F5FA"
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
        path = log_path()
        if path.exists() and path.stat().st_size > 1_000_000:
            previous = path.with_name("launcher.previous.log")
            previous.unlink(missing_ok=True)
            path.replace(previous)
        with path.open("a", encoding="utf-8") as handle:
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


def enable_high_dpi():
    """Use crisp Windows scaling without changing security or window behavior."""
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


def webview_storage_path():
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "GAMO_FM" / "webview"
    base.mkdir(parents=True, exist_ok=True)
    return base



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
        self._retry_after_id = None
        self._cloud_target = None

        self.title("GAMO a.s. — Facility Platform")
        self.geometry("1240x760")
        self.minsize(1080, 680)
        self.configure(bg=BG)
        self.ui_font = self._detect_font()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind("<F11>", self.toggle_fullscreen)
        self.bind("<Escape>", self.exit_fullscreen)
        self.bind("<Return>", self._launch_from_keyboard)
        self.report_callback_exception = self._callback_error

        try:
            self.state("normal")
        except tk.TclError:
            pass

        self._center()
        self._build_styles()
        self._build_ui()
        self._update_result = consume_update_result()
        self._post(120, self._show_previous_update_result)
        self._post(320, self.refresh_status)

    def _center(self):
        self.update_idletasks()
        width, height = 1240, 760
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
        self._cancel_retry()
        try:
            self.destroy()
        except tk.TclError:
            pass

    def _launch_from_keyboard(self, _event=None):
        if self.online and not self.busy and not self.launching:
            self.launch_app()
        return "break"

    def _cancel_retry(self):
        if self._retry_after_id is not None:
            try:
                self.after_cancel(self._retry_after_id)
            except tk.TclError:
                pass
            self._retry_after_id = None

    def _schedule_retry(self, delay_ms=15000):
        self._cancel_retry()
        if self._closing:
            return
        try:
            self._retry_after_id = self.after(delay_ms, self._retry_connection)
        except tk.TclError:
            self._retry_after_id = None

    def _retry_connection(self):
        self._retry_after_id = None
        if not self._closing and not self.busy and not self.online:
            self.refresh_status()

    def _show_previous_update_result(self):
        result = self._update_result
        self._update_result = None
        if not result or self._closing:
            return
        status = str(result.get("status", "")).lower()
        version = str(result.get("version", "")).strip()
        message = str(result.get("message", "")).strip()
        exit_code = result.get("exit_code")
        if status == "success":
            write_log(f"Update completed successfully · v{version or current_version()} · code={exit_code}")
            try:
                messagebox.showinfo(
                    "GAMO a.s. — Aktualizácia",
                    f"Aktualizácia na verziu {version or current_version()} bola úspešne dokončená.\n\n"
                    "Launcher sa automaticky znovu spustil a môžeš pokračovať.",
                    parent=self,
                )
            except Exception:
                pass
        else:
            write_log(f"Previous update failed · v{version or '?'} · code={exit_code} · {message}")
            try:
                messagebox.showerror(
                    "GAMO a.s. — Aktualizácia zlyhala",
                    "Aktualizáciu sa nepodarilo dokončiť. Launcher bol znovu spustený, "
                    "takže aplikácia nezostane zatvorená.\n\n"
                    f"Detail: {message or 'Neznáma chyba'}\n"
                    f"Kód: {exit_code if exit_code is not None else '—'}\n\n"
                    "Klikni na Diagnostika a pošli update_helper.log, ak sa chyba zopakuje.",
                    parent=self,
                )
            except Exception:
                pass

    def open_diagnostics(self):
        folder = log_path().parent
        write_log("Diagnostics folder opened.")
        try:
            if os.name == "nt":
                os.startfile(str(folder))
            else:
                messagebox.showinfo(
                    "GAMO a.s. — Diagnostika",
                    f"Diagnostické logy nájdeš tu:\n\n{folder}",
                    parent=self,
                )
        except Exception as exc:
            write_log(f"Diagnostics open failed: {exc}")
            messagebox.showinfo(
                "GAMO a.s. — Diagnostika",
                f"Diagnostické logy nájdeš tu:\n\n{folder}",
                parent=self,
            )

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

    def _detect_font(self):
        try:
            families = set(tkfont.families(self))
            for candidate in ("Segoe UI Variable Display", "Segoe UI Variable Text", "Segoe UI"):
                if candidate in families:
                    return candidate
        except Exception:
            pass
        return "Segoe UI"

    def _build_styles(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "GAMO.Horizontal.TProgressbar",
            troughcolor="#E8EDF4",
            background=BLUE,
            bordercolor="#E8EDF4",
            lightcolor=BLUE,
            darkcolor=BLUE,
            thickness=8,
        )

    def _label(self, parent, text, size=10, weight="normal", fg=TEXT, bg=WHITE, **kwargs):
        return tk.Label(
            parent,
            text=text,
            font=(self.ui_font, size, weight),
            fg=fg,
            bg=bg,
            **kwargs,
        )

    def _button(self, parent, text, command, primary=False, small=False):
        bg = BLUE if primary else WHITE
        fg = WHITE if primary else TEXT
        active_bg = BLUE_DARK if primary else BLUE_SOFT
        return tk.Button(
            parent,
            text=text,
            command=command,
            relief="flat",
            bd=0,
            bg=bg,
            fg=fg,
            activebackground=active_bg,
            activeforeground=WHITE if primary else BLUE,
            disabledforeground="#A7B2C1",
            font=(self.ui_font, 10 if small else 11, "bold"),
            padx=17 if small else 24,
            pady=9 if small else 13,
            cursor="hand2",
            highlightthickness=1 if not primary else 0,
            highlightbackground=LINE,
            highlightcolor=LINE,
        )

    def _build_ui(self):
        outer = tk.Frame(self, bg=BG)
        outer.pack(fill="both", expand=True, padx=18, pady=18)
        outer.grid_rowconfigure(0, weight=1)
        outer.grid_columnconfigure(0, weight=1)

        shell = tk.Frame(outer, bg=WHITE, highlightthickness=1, highlightbackground="#D4DEE9")
        shell.grid(row=0, column=0, sticky="nsew")
        shell.grid_rowconfigure(0, weight=1)
        shell.grid_columnconfigure(0, minsize=316)
        shell.grid_columnconfigure(1, weight=1)

        self._build_sidebar(shell)
        self._build_main(shell)

    def _build_sidebar(self, shell):
        left = tk.Frame(shell, bg=NAVY, width=316)
        left.grid(row=0, column=0, sticky="nsew")
        left.grid_propagate(False)
        left.grid_rowconfigure(5, weight=1)

        top = tk.Frame(left, bg=NAVY)
        top.grid(row=0, column=0, sticky="ew", padx=32, pady=(34, 0))

        mark = tk.Frame(top, bg=BLUE, width=46, height=46)
        mark.pack(side="left")
        mark.pack_propagate(False)
        self._label(mark, "G", 21, "bold", WHITE, BLUE).place(relx=.5, rely=.5, anchor="center")

        brand = tk.Frame(top, bg=NAVY)
        brand.pack(side="left", padx=(14, 0))
        self._label(brand, "GAMO a.s.", 18, "bold", WHITE, NAVY).pack(anchor="w")
        self._label(brand, "CLOUD FACILITY SUITE", 8, "bold", "#7FA1C6", NAVY).pack(anchor="w", pady=(3, 0))

        self._label(
            left,
            "Prevádzka pod kontrolou.",
            9, "bold", "#6F92B9", NAVY,
        ).grid(row=1, column=0, sticky="w", padx=32, pady=(62, 0))

        self._label(
            left,
            "Budovy, technológie\na servis v jednom\npracovnom priestore.",
            22, "bold", WHITE, NAVY, justify="left",
        ).grid(row=2, column=0, sticky="w", padx=32, pady=(8, 0))

        self._label(
            left,
            "Desktop klient je iba bezpečná brána do GAMO Cloud.\n"
            "Dáta zákazníka zostávajú centrálne, izolované\n"
            "a synchronizované bez lokálnej databázy.",
            9, "normal", "#A3B8CF", NAVY, justify="left",
        ).grid(row=3, column=0, sticky="w", padx=32, pady=(18, 0))

        features = tk.Frame(left, bg=NAVY)
        features.grid(row=4, column=0, sticky="ew", padx=32, pady=(34, 0))
        feature_rows = (
            ("01", "Cloudové dáta", "Tenantová izolácia + PostgreSQL RLS"),
            ("02", "Dôveryhodné zariadenie", "Prihlásenie vie zostať zapamätané 30 dní"),
            ("03", "Automatické aktualizácie", "SHA-256 overenie pred inštaláciou"),
        )
        for code, title, subtitle in feature_rows:
            row = tk.Frame(features, bg=NAVY_2, highlightthickness=1, highlightbackground="#173653")
            row.pack(fill="x", pady=5)
            badge = tk.Label(
                row, text=code, bg=NAVY_3, fg="#76A7FF",
                font=(self.ui_font, 8, "bold"), width=4, height=2
            )
            badge.pack(side="left", padx=9, pady=9)
            copy = tk.Frame(row, bg=NAVY_2)
            copy.pack(side="left", fill="x", expand=True, padx=(2, 8), pady=9)
            self._label(copy, title, 9, "bold", WHITE, NAVY_2).pack(anchor="w")
            self._label(copy, subtitle, 8, "normal", "#89A5C0", NAVY_2).pack(anchor="w", pady=(2, 0))

        footer = tk.Frame(left, bg=NAVY)
        footer.grid(row=6, column=0, sticky="sew", padx=32, pady=(0, 28))
        line = tk.Frame(footer, bg="#18334F", height=1)
        line.pack(fill="x", pady=(0, 17))
        bottom = tk.Frame(footer, bg=NAVY)
        bottom.pack(fill="x")
        vcopy = tk.Frame(bottom, bg=NAVY)
        vcopy.pack(side="left")
        self._label(vcopy, "DESKTOP CLIENT", 7, "bold", "#6483A4", NAVY).pack(anchor="w")
        self._label(vcopy, f"v{current_version()}", 10, "bold", "#D7E3EF", NAVY).pack(anchor="w", pady=(3, 0))
        pill = self._label(bottom, "SECURE", 7, "bold", "#76E1B4", NAVY_2)
        pill.pack(side="right", padx=(8, 0), pady=4, ipadx=9, ipady=5)

    def _build_main(self, shell):
        main = tk.Frame(shell, bg=WHITE)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(7, weight=1)

        header = tk.Frame(main, bg=WHITE)
        header.grid(row=0, column=0, sticky="ew", padx=44, pady=(34, 0))
        header.grid_columnconfigure(0, weight=1)

        head_left = tk.Frame(header, bg=WHITE)
        head_left.grid(row=0, column=0, sticky="w")
        badge = self._label(head_left, "GAMO CLOUD DESKTOP", 8, "bold", BLUE, BLUE_SOFT)
        badge.pack(anchor="w", ipadx=10, ipady=5)
        self._label(head_left, "Facility Platform", 32, "bold", TEXT, WHITE).pack(anchor="w", pady=(12, 0))
        self._label(
            head_left,
            "Rýchly vstup do bezpečného cloudového prostredia GAMO a.s.",
            10, "normal", MUTED, WHITE,
        ).pack(anchor="w", pady=(6, 0))

        head_right = tk.Frame(header, bg=WHITE)
        head_right.grid(row=0, column=1, sticky="ne")
        self.last_check_label = self._label(head_right, "Posledná kontrola: —", 8, "normal", SOFT_TEXT, WHITE)
        self.last_check_label.pack(anchor="e")
        self._label(head_right, "F11  ·  celá obrazovka", 8, "normal", SOFT_TEXT, WHITE).pack(anchor="e", pady=(5, 0))

        status_wrap = tk.Frame(main, bg=WHITE)
        status_wrap.grid(row=1, column=0, sticky="ew", padx=44, pady=(28, 12))
        status_wrap.grid_columnconfigure(1, weight=1)
        accent = tk.Frame(status_wrap, bg=BLUE, width=5)
        accent.grid(row=0, column=0, sticky="ns")

        status = tk.Frame(status_wrap, bg=CARD, highlightthickness=1, highlightbackground=LINE)
        status.grid(row=0, column=1, sticky="ew")
        status.grid_columnconfigure(1, weight=1)

        self.status_badge = tk.Label(
            status, text="…", bg=AMBER_SOFT, fg=AMBER,
            font=(self.ui_font, 15, "bold"), width=3, height=1
        )
        self.status_badge.grid(row=0, column=0, rowspan=2, padx=(18, 13), pady=17)

        self.status_title = self._label(status, "Kontrolujem GAMO Cloud…", 12, "bold", TEXT, CARD)
        self.status_title.grid(row=0, column=1, sticky="sw", pady=(13, 0))
        self.status_detail = self._label(status, "Overujem dostupnosť servera a aktualizácie.", 9, "normal", MUTED, CARD)
        self.status_detail.grid(row=1, column=1, sticky="nw", pady=(3, 13))

        self.refresh_btn = self._button(status, "Obnoviť  ↻", self.refresh_status, small=True)
        self.refresh_btn.grid(row=0, column=2, rowspan=2, padx=16, pady=13)

        info = tk.Frame(main, bg=WHITE)
        info.grid(row=2, column=0, sticky="ew", padx=44)
        for i in range(3):
            info.grid_columnconfigure(i, weight=1)

        self.version_info = self._info_box(info, 0, "VERZIA", f"v{current_version()}", "Aktuálny desktop build")
        self.cloud_info = self._info_box(info, 1, "GAMO CLOUD", "Kontrola…", "Stav centrálnej platformy")
        self.security_info = self._info_box(info, 2, "PRIPOJENIE", "HTTPS", "Šifrované spojenie")

        trust = tk.Frame(main, bg=WHITE)
        trust.grid(row=3, column=0, sticky="w", padx=44, pady=(15, 0))
        for text in ("TLS", "RLS", "MFA", "AUTO UPDATE", "PERSISTENT SESSION"):
            chip = self._label(trust, text, 7, "bold", "#51647A", CARD_2)
            chip.pack(side="left", padx=(0, 6), ipadx=8, ipady=4)

        self.update_card = tk.Frame(main, bg=BLUE_SOFT, highlightthickness=1, highlightbackground="#D7E5FF")
        self.update_card.grid_columnconfigure(0, weight=1)
        self.update_title = self._label(self.update_card, "Je dostupná nová verzia", 10, "bold", TEXT, BLUE_SOFT)
        self.update_title.grid(row=0, column=0, sticky="w", padx=16, pady=(11, 2))
        self.update_detail = self._label(self.update_card, "Odporúčame aktualizovať pred spustením.", 8, "normal", MUTED, BLUE_SOFT)
        self.update_detail.grid(row=1, column=0, sticky="w", padx=16, pady=(0, 11))
        self.update_btn = self._button(self.update_card, "Aktualizovať", self.install_update, primary=True, small=True)
        self.update_btn.grid(row=0, column=1, rowspan=2, padx=13, pady=9)
        self.update_card.grid(row=4, column=0, sticky="ew", padx=44, pady=(13, 0))
        self.update_card.grid_remove()

        self.progress_var = tk.DoubleVar(value=0)
        self.progress = ttk.Progressbar(main, variable=self.progress_var, maximum=100, style="GAMO.Horizontal.TProgressbar")
        self.progress.grid(row=5, column=0, sticky="ew", padx=44, pady=(9, 0))
        self.progress.grid_remove()

        actions = tk.Frame(main, bg=WHITE)
        actions.grid(row=6, column=0, sticky="ew", padx=44, pady=(24, 0))
        actions.grid_columnconfigure(0, weight=1)

        self.launch_btn = self._button(actions, "Spustiť GAMO a.s.   →", self.launch_app, primary=True)
        self.launch_btn.grid(row=0, column=0, sticky="ew", ipady=2)
        self.launch_btn.config(state="disabled")
        self.diagnostics_btn = self._button(actions, "Diagnostika", self.open_diagnostics, small=True)
        self.diagnostics_btn.grid(row=0, column=1, padx=(12, 0))

        hint = tk.Frame(main, bg=WHITE)
        hint.grid(row=7, column=0, sticky="sew", padx=44, pady=(24, 0))
        self._label(
            hint,
            "Prihlásenie môže zostať zapamätané na tomto zariadení.\n"
            "Po otvorení platformy launcher skončí a nezaťažuje aplikáciu na pozadí.",
            8, "normal", SOFT_TEXT, WHITE, justify="left"
        ).pack(anchor="sw", pady=(0, 14))

        bottom = tk.Frame(main, bg="#F8FAFD", highlightthickness=1, highlightbackground="#EEF2F6")
        bottom.grid(row=8, column=0, sticky="ew")
        self._label(
            bottom,
            "GAMO a.s.   ·   Cloud Facility Platform   ·   secure desktop client",
            8, "normal", "#8492A5", "#F8FAFD"
        ).pack(pady=12)

    def _info_box(self, parent, column, label, value, subtitle=""):
        box = tk.Frame(parent, bg=CARD, highlightthickness=1, highlightbackground=LINE)
        box.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 6, 0 if column == 2 else 6))
        self._label(box, label, 8, "bold", "#76869A", CARD).pack(anchor="w", padx=15, pady=(12, 0))
        value_label = self._label(box, value, 13, "bold", TEXT, CARD)
        value_label.pack(anchor="w", padx=15, pady=(4, 0))
        if subtitle:
            self._label(box, subtitle, 7, "normal", SOFT_TEXT, CARD).pack(anchor="w", padx=15, pady=(3, 12))
        else:
            value_label.pack_configure(pady=(4, 12))
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
        self._cancel_retry()
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
        self.last_check_label.config(text=f"Posledná kontrola: {datetime.now().strftime('%H:%M:%S')}")

        if not online:
            self.cloud_info.value_label.config(text="Nedostupný")
            self.security_info.value_label.config(text="Čaká na cloud")
            self.set_status(
                "GAMO Cloud nie je dostupný",
                "Skontroluj internet. Launcher sa automaticky pokúsi pripojiť znova o 15 sekúnd.",
                "offline",
            )
            self.launch_btn.config(state="disabled")
            self._schedule_retry(15000)
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
            manifest = self.update_manifest or {}
            version = str(manifest.get("version", "")).strip()
            progress = lambda value: self._post(0, lambda v=value: self.progress_var.set(v))
            launcher_url = str(manifest.get("launcher_url", "")).strip()
            launcher_sha = str(manifest.get("launcher_sha256", "")).strip().lower()

            # Preferred path: update the one-file launcher directly. A trusted
            # temporary copy of the currently running launcher performs the file
            # replacement after this process exits, then starts the new version.
            if (
                os.name == "nt"
                and getattr(sys, "frozen", False)
                and launcher_url.startswith("https://")
                and len(launcher_sha) == 64
                and can_self_update_install_dir(APP_DIR)
            ):
                payload = download_launcher_update(manifest, progress=progress)
                backup_user_data("pre_update")
                self._post(0, lambda: self.set_status(
                    "Aktualizácia je pripravená",
                    "Launcher sa bezpečne vymení, overí a automaticky znovu spustí.",
                    "update",
                ))
                if not launch_launcher_self_update(
                    payload,
                    os.getpid(),
                    install_dir=APP_DIR,
                    version=version,
                    expected_sha256=launcher_sha,
                ):
                    raise RuntimeError("Priamy self-update launcheru sa nepodarilo pripraviť.")
                write_log(f"Direct launcher self-update handoff · target=v{version} · payload={payload}")
                self._post(450, self._close)
                return

            # Fallback for older manifests or protected install directories:
            # use the signed/packaged installer path.
            installer = download_update(manifest, progress=progress)
            backup_user_data("pre_update")
            self._post(0, lambda: self.set_status(
                "Aktualizácia je pripravená",
                "Spustí sa systémový inštalátor a po dokončení sa GAMO automaticky otvorí.",
                "update",
            ))
            relaunch = APP_DIR / "GAMO_Launcher.exe"
            launch_installer_after_process_exit(
                installer,
                os.getpid(),
                relaunch_path=relaunch,
                version=version,
            )
            write_log(f"Installer fallback handoff · target=v{version} · installer={installer}")
            self._post(450, self._close)
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
        self.launch_btn.config(state="disabled", text="Otváram GAMO a.s. …")
        self.refresh_btn.config(state="disabled")
        self.set_status(
            "Otváram GAMO Cloud…",
            "Launcher sa zmení na desktop klient bez spúšťania ďalšieho EXE súboru.",
            "checking",
        )
        self._cloud_target = self.server_url
        write_log(f"Cloud client handoff prepared · {self.server_url}")
        self._post(120, self._close)


class CloudClientApi:
    """Native window controls exposed to the cloud UI in the same launcher process."""

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
            write_log(f"Window maximize failed: {exc}")
        return False

    def restore(self):
        try:
            if self.window:
                self.window.restore()
                return True
        except Exception as exc:
            write_log(f"Window restore failed: {exc}")
        return False


def _show_cloud_window(window):
    try:
        window.maximize()
    except Exception as exc:
        write_log(f"Initial maximize skipped: {exc}")


def _show_cloud_fallback_error(url, detail):
    try:
        root = tk.Tk()
        root.withdraw()
        messagebox.showwarning(
            "GAMO a.s. — Desktop klient",
            "Natívne okno GAMO sa na tomto počítači nepodarilo otvoriť.\n\n"
            "Aplikáciu som preto otvoril v predvolenom webovom prehliadači.\n\n"
            f"Detail: {detail}\n\n{url}",
            parent=root,
        )
        root.destroy()
    except Exception:
        pass


def open_cloud_client(url):
    """Open GAMO Cloud inside the launcher process.

    No second application executable is spawned. This avoids Windows
    Application Control blocking a legacy child executable while preserving the
    installed desktop experience. The browser fallback does not weaken or
    bypass Windows security policy.
    """
    try:
        import webview

        api = CloudClientApi()
        window = webview.create_window(
            f"GAMO a.s. {current_version()} — Facility Platform",
            url,
            width=1500,
            height=920,
            min_size=(1100, 700),
            resizable=True,
            confirm_close=False,
            text_select=True,
            js_api=api,
        )
        api.bind_window(window)
        write_log("Opening single-process GAMO Cloud client.")
        try:
            webview.settings["ALLOW_DOWNLOADS"] = True
            webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
            webview.settings["OPEN_DEVTOOLS_IN_DEBUG"] = False
        except Exception:
            pass
        storage = webview_storage_path()
        webview.start(
            _show_cloud_window,
            window,
            debug=False,
            gui="edgechromium",
            private_mode=False,
            storage_path=str(storage),
            user_agent=f"GAMO-Desktop/{current_version()} Windows",
        )
        return True
    except Exception as exc:
        detail = str(exc)
        write_log(f"Native cloud client failed: {detail}")
        try:
            opened = bool(webbrowser.open(url, new=1))
        except Exception as browser_exc:
            write_log(f"Browser fallback failed: {browser_exc}")
            opened = False
        if opened:
            _show_cloud_fallback_error(url, detail)
            return False
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "GAMO a.s. — Desktop klient",
                "Aplikáciu sa nepodarilo otvoriť ani v natívnom okne, ani v prehliadači.\n\n"
                "Skontroluj Microsoft Edge WebView2 Runtime alebo kontaktuj správcu.",
                parent=root,
            )
            root.destroy()
        except Exception:
            pass
        return False


def main():
    # Self-update helper mode must run before the single-instance mutex/UI.
    if len(sys.argv) >= 3 and sys.argv[1] == "--gamo-update-helper":
        raise SystemExit(run_launcher_self_update_helper(sys.argv[2]))

    cleanup_stale_update_files()
    enable_high_dpi()
    mutex = single_instance_guard()
    if mutex is False:
        return
    write_log(
        f"Launcher started · v{current_version()} · executable={Path(sys.executable).resolve()} "
        f"· app_dir={APP_DIR} · frozen={bool(getattr(sys, 'frozen', False))}"
    )
    app = Launcher()
    app._mutex = mutex
    app.mainloop()
    target = getattr(app, "_cloud_target", None)
    if target:
        open_cloud_client(target)


if __name__ == "__main__":
    main()
