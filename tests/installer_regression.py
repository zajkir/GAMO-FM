import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
iss = (root / "installer" / "GAMO_FM.iss").read_text(encoding="utf-8")
version = json.loads((root / "version.json").read_text(encoding="utf-8"))["version"]

assert 'CloseApplicationsFilter={#MyAppExeName};{#MyLauncherExeName}' in iss
assert '/F /T /IM "{#MyLauncherExeName}"' in iss
assert '/F /T /IM "{#MyAppExeName}"' in iss
assert 'restartreplace' in iss
assert 'function ShouldLaunchAfterInstall(): Boolean;' in iss
assert "{param:NOLAUNCH|0}" in iss
assert 'Check: ShouldLaunchAfterInstall' in iss
assert 'skipifsilent' not in [line for line in iss.splitlines() if line.startswith('Filename: "{app}\\{#MyLauncherExeName}"')][0]
assert 'function PrepareToInstall(var NeedsRestart: Boolean): String;' in iss
assert 'ForceCloseLauncher();' in iss
assert 'Source: "..\\dist\\GAMO_FM\\*"' not in iss
assert 'Type: files; Name: "{app}\\{#MyAppExeName}"' in iss
assert 'DestName: "{#MyAppExeName}"' in iss
assert 'Source: "..\\dist_launcher\\GAMO_Launcher.exe"; DestDir: "{app}"; DestName: "{#MyAppExeName}"' in iss
assert 'Type: files; Name: "{autodesktop}\\GAMO a.s..lnk"' in iss
assert 'Type: files; Name: "{autoprograms}\\GAMO a.s..lnk"' in iss
assert 'Type: filesandordirs; Name: "{app}\\_internal"' in iss
assert f'#define MyAppVersion "{version}"' in iss

print("Installer self-update regression checks OK")
