from pathlib import Path
import json
import re

root = Path(__file__).resolve().parents[1]

app = (root / "app.py").read_text(encoding="utf-8")
js = (root / "static" / "app.js").read_text(encoding="utf-8")
css = (root / "static" / "app.css").read_text(encoding="utf-8")
template = (root / "templates" / "index.html").read_text(encoding="utf-8")
workflow = (root / ".github" / "workflows" / "build-windows.yml").read_text(encoding="utf-8")
quality = (root / ".github" / "workflows" / "quality.yml").read_text(encoding="utf-8")
installer = (root / "installer" / "GAMO_FM.iss").read_text(encoding="utf-8")
updater = (root / "updater.py").read_text(encoding="utf-8")
desktop = (root / "desktop.py").read_text(encoding="utf-8")
readme = (root / "README.md").read_text(encoding="utf-8")
version = json.loads((root / "version.json").read_text(encoding="utf-8"))["version"]
version_info = (root / "version_info.txt").read_text(encoding="utf-8")
python_version = (root / ".python-version").read_text(encoding="utf-8").strip()
update_cfg = json.loads((root / "update_config.json").read_text(encoding="utf-8"))
desktop_cfg = json.loads((root / "desktop_config.json").read_text(encoding="utf-8"))

# Runtime and deployment stay aligned with the CI runtime we actually test.
assert python_version.startswith("3.12"), python_version
assert "python-version: '3.12'" in workflow
assert 'python-version: "3.12"' in quality or "python-version: '3.12'" in quality
assert desktop_cfg["server_url"].startswith("https://")
assert desktop_cfg.get("health_path") == "/healthz"
assert update_cfg.get("manifest_url", "").startswith("https://")

# Product version must be consistent across Windows metadata and installer.
assert f'#define MyAppVersion "{version}"' in installer
assert f"FileVersion','{version}'" in version_info
assert f"ProductVersion','{version}'" in version_info
assert "--version-file version_info.txt" in workflow

# Production hardening: persistent session key, health check and safe bootstrap.
assert "def configure_persistent_secret():" in app
assert "flask_secret_key_v1" in app
assert "@app.get('/healthz')" in app
assert "'healthz'" in app
assert "GAMO_ADMIN_PASSWORD must be set before bootstrapping a new production database." in app
assert "DB_INTEGRITY_ERRORS" in app
assert "except IntegrityError:" not in app

# Multi-write user operations that would be dangerous when partially committed
# must use a shared database transaction.
assert "with con() as db:" in app
assert "Ticket sa nepodarilo vytvoriť pre súbežný konflikt" in app
assert "with con(system=platform_view) as db:" in app

# Every statically rendered POST form in the main app must carry CSRF.
post_forms = [
    match.group(0)
    for match in re.finditer(r"<form\b[\s\S]*?</form>", template, flags=re.IGNORECASE)
    if re.search(r'method="post"', match.group(0), flags=re.IGNORECASE)
]
assert post_forms
for form in post_forms:
    assert 'name="_csrf"' in form, form[:220]

# Static DOM IDs must stay unique. Jinja loop-generated dynamic IDs are not
# included by this check because this only inspects literal id attributes.
ids = re.findall(r'\bid="([^"]+)"', template)
duplicates = sorted({value for value in ids if ids.count(value) > 1})
assert not duplicates, duplicates

# Inline UI handlers must resolve to real JS functions (apart from browser/
# element built-ins deliberately called inline).
functions = set(re.findall(r"function\s+([A-Za-z_$][\w$]*)\s*\(", js))
inline_code = re.findall(r'(?:onclick|onsubmit|onchange|oninput)="([^"]+)"', template)
calls = []
for code in inline_code:
    calls.extend(re.findall(r"\b([A-Za-z_$][\w$]*)\s*\(", code))
builtins = {"if", "submit", "reload", "toUpperCase", "querySelector", "scrollIntoView", "confirm"}
missing = sorted({name for name in calls if name not in functions and name not in builtins})
assert not missing, missing

# Ticket chat must be two-sided and self-refreshing without waiting for the
# other participant to submit a message.
assert "async function refreshTicketMessages" in js
assert "document.hidden?15000:1200" in js
assert "GAMO-Live-Chat" in js
assert "/api/ticket/" in js
assert "ticketLiveIndicator" in template

# Digital Twin interaction must remain complete and keyboard accessible.
for name in (
    "twinPreset", "twinExplode", "twinFocusSelected", "twinToggleTech",
    "twinSelectFloor", "twinOpenSelectedFloor", "initDigitalTwinV2",
):
    assert f"function {name}" in js
assert 'id="dt2Stage" tabindex="0"' in template
assert "pointerdown" in js and "wheel" in js and "ArrowLeft" in js
assert "@media (prefers-reduced-motion:reduce)" in css

# Windows is a direct application, not the obsolete launcher architecture.
assert "GAMO_Launcher.exe" not in desktop
assert "def cloud_health(server_url):" in desktop
assert "confirm_open_when_offline(server_url)" in desktop
assert "--onefile" in workflow and "--name GAMO_FM" in workflow
assert "GAMO_Launcher_$version.exe" not in workflow
assert 'Source: "..\\dist_app\\GAMO_FM.exe"' in installer

# The release pipeline is prepared for enterprise Authenticode signing while
# remaining buildable when the private certificate is not configured.
assert "GAMO_SIGNING_PFX_BASE64" in workflow
assert "signtool sign /fd SHA256" in workflow
assert "signtool verify /pa /v" in workflow

# Updater wording must not confuse a SHA-256 checksum with a digital signature.
assert "platný podpísaný installer payload" not in updater
assert "SHA-256 kontrolný súčet" in updater

# Documentation must describe the current cloud architecture rather than the
# old local-database/launcher product.
assert "Microsoft Edge application režime" in readme
assert "PostgreSQL v produkcii" in readme
assert "Zákazník nepotrebuje Python" in readme
assert "GAMO FM Desktop v9 — Installer + Online Updater" not in readme

print(f"GAMO final production audit static checks OK · v{version}")
