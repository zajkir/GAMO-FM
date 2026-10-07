import ctypes
import json
import os
import subprocess
import sys
import threading
import urllib.request
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

NAVY = "#071729"
NAVY_2 = "#0D2A49"
BLUE = "#2867F0"
BLUE_SOFT = "#EAF1FF"
GREEN = "#17966C"
GREEN_SOFT = "#EAF8F2"
RED = "#D53A4E"
RED_SOFT = "#FDECEF"
AMBER = "#B9770E"
AMBER_SOFT = "#FFF4D9"
TEXT = "#172337"
MUTED = "#6E7B8E"
LINE = "#E2E8F0"
BG = "#F3F6FA"
WHITE = "#FFFFFF"


def load_desktop_config():
    defaults = {
        "server_url": "https://gamo-fm.onrender.com",
        "connect_timeout_seconds": 12,
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


def single_instance_guard():
    """Return a Windows mutex handle, or None outside Windows.

    Keeping the handle alive for the process lifetime prevents accidental
    duplicate launcher windows.
    """
    if os.name != "nt":
        return None
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateMutexW(None, False, "Global\\GAMO_Facility_Launcher")
    if not handle:
        return None
    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        kernel32.CloseHandle(handle)
        return False
    return handle


class Launcher(tk.Tk):
    def __init__(self):
        super().__init__()
        self.config_data = load_desktop_config()
        self.server_url = str(self.config_data.get("server_url", "")).strip().rstrip("/")
        self.timeout = max(3, int(self.config_data.get("connect_timeout_seconds", 12)))
        self.online = False
        self.update_manifest = None
        self.busy = False

        self.title("GAMO a.s. — Launcher")
        self.geometry("900x540")
        self.minsize(820, 500)
        self.configure(bg=BG)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        self._center()
        self._build_styles()
        self._build_ui()
        self.after(250, self.refresh_status)

    def _center(self):
        self.update_idletasks()
        width, height = 900, 540
        x = max(0, (self.winfo_screenwidth() - width) // 2)
        y = max(0, (self.winfo_screenheight() - height) // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")

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
            thickness=8,
        )

    def _build_ui(self):
        shell = tk.Frame(self, bg=WHITE, highlightthickness=1, highlightbackground=LINE)
        shell.pack(fill="both", expand=True, padx=24, pady=24)

        left = tk.Canvas(shell, width=300, bg=NAVY, highlightthickness=0)
        left.pack(side="left", fill="y")
        left.create_oval(196, -48, 390, 146, fill=NAVY_2, outline="")
        left.create_oval(-80, 350, 160, 590, fill="#0A213B", outline="")
        left.create_text(34, 52, text="G", anchor="nw", fill=WHITE, font=("Segoe UI", 31, "bold"))
        left.create_text(34, 104, text="GAMO a.s.", anchor="nw", fill=WHITE, font=("Segoe UI", 18, "bold"))
        left.create_text(
            34,
            136,
            text="SMART FACILITY PLATFORM",
            anchor="nw",
            fill="#8FA6C0",
            font=("Segoe UI", 8, "bold"),
        )
        left.create_text(
            34,
            220,
            text="Jedna aplikácia.\nBez lokálnej databázy.\nVždy aktuálne dáta.",
            anchor="nw",
            fill="#D9E4F1",
            font=("Segoe UI", 13, "bold"),
            width=220,
        )
        left.create_text(
            34,
            328,
            text="Launcher bezpečne overí cloud,\naktualizácie a až potom otvorí\nGAMO Facility Platform.",
            anchor="nw",
            fill="#8299B4",
            font=("Segoe UI", 9),
            width=220,
        )
        left.create_text(
            34,
            476,
            text=f"DESKTOP CLIENT  ·  v{current_version()}",
            anchor="nw",
            fill="#6F88A5",
            font=("Segoe UI", 8, "bold"),
        )

        right = tk.Frame(shell, bg=WHITE)
        right.pack(side="left", fill="both", expand=True)

        header = tk.Frame(right, bg=WHITE)
        header.pack(fill="x", padx=34, pady=(30, 0))
        tk.Label(
            header, text="GAMO LAUNCHER", bg=WHITE, fg=BLUE, font=("Segoe UI", 8, "bold")
        ).pack(anchor="w")
        tk.Label(
            header, text="Facility Platform", bg=WHITE, fg=TEXT, font=("Segoe UI", 26, "bold")
        ).pack(anchor="w", pady=(4, 0))
        tk.Label(
            header,
            text="Pripravené pre bezpečnú cloudovú prevádzku zákazníka.",
            bg=WHITE,
            fg=MUTED,
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(3, 0))

        self.status_card = tk.Frame(right, bg="#F8FAFD", highlightthickness=1, highlightbackground=LINE)
        self.status_card.pack(fill="x", padx=34, pady=(24, 14))
        status_inner = tk.Frame(self.status_card, bg="#F8FAFD")
        status_inner.pack(fill="x", padx=16, pady=15)

        self.status_dot = tk.Canvas(status_inner, width=34, height=34, bg="#F8FAFD", highlightthickness=0)
        self.status_dot.pack(side="left")
        self.dot_id = self.status_dot.create_oval(5, 5, 29, 29, fill=AMBER_SOFT, outline="")
        self.dot_text = self.status_dot.create_text(17, 17, text="…", fill=AMBER, font=("Segoe UI", 11, "bold"))

        status_text = tk.Frame(status_inner, bg="#F8FAFD")
        status_text.pack(side="left", padx=(10, 0), fill="x", expand=True)
        self.status_title = tk.Label(
            status_text, text="Kontrolujem systém…", bg="#F8FAFD", fg=TEXT, font=("Segoe UI", 11, "bold")
        )
        self.status_title.pack(anchor="w")
        self.status_detail = tk.Label(
            status_text, text="Pripájam sa ku GAMO Cloud.", bg="#F8FAFD", fg=MUTED, font=("Segoe UI", 8)
        )
        self.status_detail.pack(anchor="w", pady=(3, 0))

        self.refresh_btn = tk.Button(
            status_inner,
            text="↻  Obnoviť",
            command=self.refresh_status,
            relief="flat",
            bg=WHITE,
            fg=TEXT,
            activebackground=BLUE_SOFT,
            activeforeground=BLUE,
            font=("Segoe UI", 8, "bold"),
            padx=12,
            pady=7,
            cursor="hand2",
        )
        self.refresh_btn.pack(side="right")

        info = tk.Frame(right, bg=WHITE)
        info.pack(fill="x", padx=34, pady=(0, 16))
        self.version_info = self._info_box(info, "VERZIA", f"v{current_version()}")
        self.version_info.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.cloud_info = self._info_box(info, "CLOUD", "Kontrola…")
        self.cloud_info.pack(side="left", fill="x", expand=True, padx=(6, 0))

        self.progress_var = tk.DoubleVar(value=0)
        self.progress = ttk.Progressbar(
            right, variable=self.progress_var, maximum=100, style="GAMO.Horizontal.TProgressbar"
        )

        self.update_card = tk.Frame(right, bg=BLUE_SOFT, highlightthickness=1, highlightbackground="#D8E5FF")
        update_inner = tk.Frame(self.update_card, bg=BLUE_SOFT)
        update_inner.pack(fill="x", padx=14, pady=11)
        tk.Label(
            update_inner, text="Nová verzia je pripravená", bg=BLUE_SOFT, fg=TEXT, font=("Segoe UI", 9, "bold")
        ).pack(side="left")
        self.update_btn = tk.Button(
            update_inner,
            text="Aktualizovať",
            command=self.install_update,
            relief="flat",
            bg=BLUE,
            fg=WHITE,
            activebackground="#1E55C9",
            activeforeground=WHITE,
            font=("Segoe UI", 8, "bold"),
            padx=14,
            pady=7,
            cursor="hand2",
        )
        self.update_btn.pack(side="right")

        actions = tk.Frame(right, bg=WHITE)
        actions.pack(fill="x", padx=34, pady=(8, 0))
        self.launch_btn = tk.Button(
            actions,
            text="Spustiť GAMO a.s.  →",
            command=self.launch_app,
            relief="flat",
            bg=BLUE,
            fg=WHITE,
            disabledforeground="#AAB6C6",
            activebackground="#1E55C9",
            activeforeground=WHITE,
            font=("Segoe UI", 11, "bold"),
            padx=22,
            pady=13,
            cursor="hand2",
            state="disabled",
        )
        self.launch_btn.pack(fill="x")

        self.footer = tk.Label(
            right,
            text="GAMO a.s.  ·  Cloud Facility Platform  ·  zabezpečené HTTPS pripojenie",
            bg=WHITE,
            fg="#96A1B0",
            font=("Segoe UI", 8),
        )
        self.footer.pack(side="bottom", pady=20)

    def _info_box(self, parent, label, value):
        box = tk.Frame(parent, bg="#F8FAFD", highlightthickness=1, highlightbackground=LINE)
        tk.Label(box, text=label, bg="#F8FAFD", fg="#8B98AA", font=("Segoe UI", 7, "bold")).pack(
            anchor="w", padx=12, pady=(9, 0)
        )
        value_label = tk.Label(box, text=value, bg="#F8FAFD", fg=TEXT, font=("Segoe UI", 10, "bold"))
        value_label.pack(anchor="w", padx=12, pady=(2, 9))
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
        self.status_dot.itemconfigure(self.dot_id, fill=bg)
        self.status_dot.itemconfigure(self.dot_text, text=symbol, fill=fg)

    def probe_server(self):
        if not self.server_url.startswith(("https://", "http://")):
            return False
        req = urllib.request.Request(
            self.server_url + "/login",
            headers={"User-Agent": f"GAMO-Launcher/{current_version()}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return 200 <= response.status < 500
        except Exception:
            return False

    def refresh_status(self):
        if self.busy:
            return
        self.busy = True
        self.launch_btn.config(state="disabled")
        self.refresh_btn.config(state="disabled")
        self.update_card.pack_forget()
        self.progress.pack_forget()
        self.progress_var.set(0)
        self.set_status("Kontrolujem GAMO Cloud…", "Overujem server a dostupné aktualizácie.", "checking")
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
        self.after(0, lambda: self._finish_refresh(online, manifest, update_error))

    def _finish_refresh(self, online, manifest, update_error):
        self.busy = False
        self.online = online
        self.update_manifest = manifest
        self.refresh_btn.config(state="normal")

        if not online:
            self.cloud_info.value_label.config(text="Nedostupný")
            self.set_status(
                "GAMO Cloud nie je dostupný",
                "Skontroluj internetové pripojenie a skús kontrolu zopakovať.",
                "offline",
            )
            self.launch_btn.config(state="disabled")
            return

        self.cloud_info.value_label.config(text="Online · HTTPS")
        self.launch_btn.config(state="normal")

        if manifest:
            version = str(manifest.get("version", "nová"))
            self.set_status(
                f"Aktualizácia v{version} je dostupná",
                "Odporúčame ju nainštalovať pred spustením aplikácie.",
                "update",
            )
            self.update_btn.config(text=f"Aktualizovať na v{version}", state="normal")
            self.update_card.pack(fill="x", padx=34, pady=(0, 10), before=self.launch_btn.master)
        else:
            detail = "Cloud je online. Aplikácia je pripravená."
            if update_error:
                detail += " Kontrola aktualizácie sa preskočila."
            self.set_status("Všetko je pripravené", detail, "online")

    def install_update(self):
        if not self.update_manifest or self.busy:
            return
        self.busy = True
        self.launch_btn.config(state="disabled")
        self.refresh_btn.config(state="disabled")
        self.update_btn.config(state="disabled", text="Sťahujem…")
        self.progress.pack(fill="x", padx=34, pady=(0, 12))
        self.set_status("Sťahujem aktualizáciu…", "Po stiahnutí overím SHA-256 podpis balíka.", "update")
        threading.Thread(target=self._update_worker, daemon=True, name="GAMO-Launcher-Update").start()

    def _update_worker(self):
        try:
            installer = download_update(
                self.update_manifest,
                progress=lambda value: self.after(0, lambda v=value: self.progress_var.set(v)),
            )
            backup_user_data("pre_update")
            self.after(0, lambda: self.set_status("Aktualizácia je pripravená", "Spúšťam bezpečný installer.", "online"))
            launch_installer_after_process_exit(installer, os.getpid())
            self.after(0, self.destroy)
        except Exception as exc:
            self.after(0, lambda: self._update_failed(str(exc)))

    def _update_failed(self, detail):
        self.busy = False
        self.refresh_btn.config(state="normal")
        self.launch_btn.config(state="normal" if self.online else "disabled")
        self.update_btn.config(state="normal", text="Skúsiť znova")
        self.set_status("Aktualizácia zlyhala", detail or "Skús to znova.", "offline")

    def launch_app(self):
        if self.busy or not self.online:
            return
        executable = APP_DIR / "GAMO_FM.exe"
        env = os.environ.copy()
        env["GAMO_SKIP_UPDATE"] = "1"
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
            self.after(350, self.destroy)
        except Exception as exc:
            messagebox.showerror(
                "GAMO a.s. — Launcher",
                f"Aplikáciu sa nepodarilo spustiť.\n\n{exc}",
                parent=self,
            )


def main():
    mutex = single_instance_guard()
    if mutex is False:
        return
    app = Launcher()
    app._mutex = mutex
    app.mainloop()


if __name__ == "__main__":
    main()
