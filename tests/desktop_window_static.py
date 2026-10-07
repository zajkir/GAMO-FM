from pathlib import Path
import ast
import json

root = Path(__file__).resolve().parents[1]
source = (root / "desktop.py").read_text(encoding="utf-8")
ast.parse(source)
config = json.loads((root / "desktop_config.json").read_text(encoding="utf-8"))

assert config.get("start_maximized") is True
assert "window.maximize()" in source
assert "webview.start(_show_desktop_window, window, debug=False)" in source
assert "resizable=True" in source

print("Desktop maximize/fullscreen-capable window checks OK")
