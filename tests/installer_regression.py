import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
iss = (root / "installer" / "GAMO_FM.iss").read_text(encoding="utf-8")
version = json.loads((root / "version.json").read_text(encoding="utf-8"))["version"]

assert 'CloseApplicationsFilter={#MyAppExeName};{#MyLauncherExeName}' in iss
assert '/F /T /IM "{#MyLauncherExeName}"' in iss
assert '/F /T /IM "{#MyAppExeName}"' in iss
assert 'restartreplace' in iss
assert 'function PrepareToInstall(var NeedsRestart: Boolean): String;' in iss
assert 'ForceCloseLauncher();' in iss
assert f'#define MyAppVersion "{version}"' in iss

print("Installer self-update regression checks OK")
