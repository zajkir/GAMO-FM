from pathlib import Path
import json

root = Path(__file__).resolve().parents[1]
workflow = (root / ".github" / "workflows" / "build-windows.yml").read_text(encoding="utf-8")
version = json.loads((root / "version.json").read_text(encoding="utf-8"))["version"]

assert "branches:" in workflow and "- main" in workflow
assert "Publish versioned GitHub Release" in workflow
assert "Prepare versioned launcher payload" in workflow
assert "GAMO_Launcher_$version.exe" in workflow
assert "gh release create" in workflow
assert "gh release upload" in workflow
assert "Get-FileHash" in workflow and "SHA256" in workflow
assert "launcher_url" in workflow
assert "launcher_sha256" in workflow
assert "installer_url" in workflow
assert "sha256" in workflow
assert 'update_mode = "launcher"' in workflow
assert "git push origin HEAD:main" in workflow
assert "GAMO_FM_Setup_$version.exe" in workflow
assert "Build desktop application" not in workflow
assert "Build GAMO single-process cloud client" in workflow
assert "--collect-all webview" in workflow

print(f"Windows direct self-update release workflow OK for {version}")
