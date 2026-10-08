from pathlib import Path
import ast
import json

root = Path(__file__).resolve().parents[1]
source = (root / "desktop.py").read_text(encoding="utf-8")
tree = ast.parse(source)
config = json.loads((root / "desktop_config.json").read_text(encoding="utf-8"))

assert config.get("start_maximized") is True
assert config.get("renderer") == "edge_app"
assert config.get("embedded_fallback") is True

# Primary renderer: full Microsoft Edge in application mode, not embedded
# WebView2. This avoids the keyboard/focus freeze class seen in the old shell.
assert "def find_edge_executable():" in source
assert "def launch_edge_app(server_url):" in source
assert 'f"--app={server_url}"' in source
assert 'f"--user-data-dir={profile}"' in source
assert '"--disable-background-mode"' in source
assert '"--no-first-run"' in source
assert "process.wait()" in source
assert "edge-app-profile-v1" in source

# Emergency fallback remains available when Edge executable cannot be located.
assert "def launch_embedded_fallback(server_url):" in source
assert "class DesktopApi:" in source
assert "window.toggle_fullscreen()" in source
assert "js_api=api" in source
assert "webview.start(" in source
assert 'gui="edgechromium"' in source
assert "webview-safe-v2" in source
assert "private_mode=False" in source
assert 'webview.settings["ALLOW_DOWNLOADS"] = True' in source

assert "single_instance_guard()" in source
assert "check_update_before_open()" in source

# Direct application regression: no launcher hand-off or launcher verification env.
for forbidden in ("GAMO_CLOUD_VERIFIED", "GAMO_SKIP_UPDATE", "GAMO_Launcher.exe", "launch_cloud_client_process"):
    assert forbidden not in source, forbidden

print("Stable GAMO desktop renderer checks OK")
