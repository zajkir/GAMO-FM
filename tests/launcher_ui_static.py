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
print("Launcher fullscreen binding OK")

assert 'self.geometry("1180x720")' in source
assert 'font=("Segoe UI", size, weight)' in source
assert 'F11  ·  celá obrazovka' in source
print("Launcher readable layout checks OK")

assert 'GAMO_CLOUD_VERIFIED' in source
assert 'method="HEAD"' in source
assert 'def _post(self, delay, callback):' in source
assert 'report_callback_exception = self._callback_error' in source
print("Launcher stability and fast cloud handoff checks OK")
