from pathlib import Path
import ast
import json

root = Path(__file__).resolve().parents[1]
source = (root / "desktop.py").read_text(encoding="utf-8")
tree = ast.parse(source)
config = json.loads((root / "desktop_config.json").read_text(encoding="utf-8"))

assert config.get("start_maximized") is True
assert "class DesktopApi:" in source
assert "window.maximize()" in source
assert "window.toggle_fullscreen()" in source
assert "js_api=api" in source
assert "webview.start(" in source
assert 'gui="edgechromium"' in source
assert "private_mode=False" in source
assert "storage_path=str(webview_storage_path())" in source
assert 'user_agent=f"GAMO-Desktop/{current_version()} Windows"' in source
assert 'webview.settings["ALLOW_DOWNLOADS"] = True' in source
assert "confirm_close=False" in source
assert "single_instance_guard()" in source
assert "check_update_before_open()" in source

# Direct application regression: no launcher hand-off or launcher verification env.
for forbidden in ("GAMO_CLOUD_VERIFIED", "GAMO_SKIP_UPDATE", "GAMO_Launcher.exe", "launch_cloud_client_process"):
    assert forbidden not in source, forbidden

print("Direct GAMO desktop window checks OK")
