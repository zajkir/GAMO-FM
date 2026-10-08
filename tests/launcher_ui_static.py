from pathlib import Path
import ast

root = Path(__file__).resolve().parents[1]
source = (root / "launcher.py").read_text(encoding="utf-8")
tree = ast.parse(source)

for node in ast.walk(tree):
    if not isinstance(node, ast.Call):
        continue
    func = node.func
    if not isinstance(func, ast.Attribute) or func.attr != "create_text":
        continue
    keywords = {kw.arg for kw in node.keywords if kw.arg}
    forbidden = {"spacing1", "spacing2", "spacing3"} & keywords
    assert not forbidden, f"Tkinter Canvas.create_text does not support: {sorted(forbidden)}"

print("Launcher Canvas options OK")

assert 'self.bind("<F11>", self.toggle_fullscreen)' in source
assert 'self.attributes("-fullscreen", self._fullscreen)' in source
assert 'self.geometry("1240x760")' in source
assert 'self.minsize(1080, 680)' in source
assert 'Segoe UI Variable Display' in source
assert 'def _detect_font(self):' in source
assert 'F11  ·  celá obrazovka' in source
assert 'Posledná kontrola: —' in source
print("Launcher premium readable layout checks OK")

assert 'method="HEAD"' in source
assert 'def _post(self, delay, callback):' in source
assert 'report_callback_exception = self._callback_error' in source
assert 'self._cloud_target = self.server_url' in source
assert 'def enable_high_dpi():' in source
print("Launcher stability and DPI checks OK")

assert 'self.bind("<Return>", self._launch_from_keyboard)' in source
assert 'def _schedule_retry(self, delay_ms=15000):' in source
assert 'self._schedule_retry(15000)' in source
assert 'def open_diagnostics(self):' in source
assert 'os.startfile(str(folder))' in source
assert 'launcher.previous.log' in source
print("Launcher retry and diagnostics checks OK")

assert 'def open_cloud_client(url):' in source
assert 'webview.create_window(' in source
assert 'private_mode=False' in source
assert 'storage_path=str(storage)' in source
assert 'user_agent=f"GAMO-Desktop/{current_version()} Windows"' in source
assert 'webview.settings["ALLOW_DOWNLOADS"] = True' in source
assert 'webbrowser.open(url, new=1)' in source
assert 'def launch_cloud_client_process(url):' in source
assert 'subprocess.Popen(command, **kwargs)' in source
assert 'CLOUD_CLIENT_ARG = "--gamo-cloud-client"' in source
assert 'if len(sys.argv) >= 3 and sys.argv[1] == CLOUD_CLIENT_ARG:' in source
assert 'launch_cloud_client_process(target)' in source
assert 'GAMO_FM.exe' not in source
print("Launcher dedicated-process WebView2 isolation checks OK")

assert 'executable={Path(sys.executable).resolve()}' in source
assert 'app_dir={APP_DIR}' in source
print("Launcher path diagnostics checks OK")


# Regression: the normal Tk launcher must never start WebView2 in the same
# process after mainloop exits. The cloud client is re-executed as the same
# trusted launcher binary in a dedicated process.
main_segment = source[source.index("def main():"):]
assert "open_cloud_client(target)\n        return" in main_segment
assert "launch_cloud_client_process(target)" in main_segment
assert main_segment.index("if len(sys.argv) >= 3 and sys.argv[1] == CLOUD_CLIENT_ARG:") < main_segment.index("mutex = single_instance_guard()")
assert "enable_crash_diagnostics()" in main_segment
assert "launcher-crash.log" in source
print("Launcher keyboard/focus crash regression checks OK")
