from pathlib import Path
import json

root = Path(__file__).resolve().parents[1]
workflow = (root / ".github" / "workflows" / "build-windows.yml").read_text(encoding="utf-8")
version = json.loads((root / "version.json").read_text(encoding="utf-8"))["version"]

assert "branches:" in workflow and "- main" in workflow
assert "Build GAMO direct Windows application" in workflow
assert "--name GAMO_FM" in workflow
assert "--onefile" in workflow
assert "--collect-all webview" in workflow
assert "--version-file version_info.txt" in workflow
assert "dist_app\\GAMO_FM.exe" in workflow
assert "GAMO_FM_Setup_$version.exe" in workflow
assert "GAMO_FM_$version.exe" in workflow
assert "Publish versioned GitHub Release" in workflow
assert "Get-FileHash" in workflow and "SHA256" in workflow
assert "GAMO_SIGNING_PFX_BASE64" in workflow
assert "signtool sign /fd SHA256" in workflow
assert "signtool verify /pa /v" in workflow
assert 'update_mode = "installer"' in workflow
assert "installer_url" in workflow
assert "portable_url" in workflow
assert "git push origin HEAD:main" in workflow

for forbidden in ("Build GAMO single-process cloud client", "GAMO_Launcher_$version.exe", "launcher_url", "launcher_sha256", "launcher.py", "launcher_ui_static.py"):
    assert forbidden not in workflow, forbidden

print(f"Windows direct-app release workflow OK for {version}")
