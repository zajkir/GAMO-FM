import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
iss = (root / "installer" / "GAMO_FM.iss").read_text(encoding="utf-8")
version = json.loads((root / "version.json").read_text(encoding="utf-8"))["version"]

assert f'#define MyAppVersion "{version}"' in iss
assert '#define MyAppExeName "GAMO_FM.exe"' in iss
assert 'Source: "..\\dist_app\\GAMO_FM.exe"; DestDir: "{app}"' in iss
assert 'Name: "{autoprograms}\\GAMO a.s."; Filename: "{app}\\{#MyAppExeName}"' in iss
assert 'Name: "{autodesktop}\\GAMO a.s."; Filename: "{app}\\{#MyAppExeName}"' in iss
assert 'Filename: "{app}\\{#MyAppExeName}"; Description: "Spustiť GAMO a.s."' in iss
assert 'UninstallDisplayIcon={app}\\{#MyAppExeName}' in iss
assert 'PrivilegesRequired=admin' in iss
assert 'PrivilegesRequiredOverridesAllowed=dialog commandline' in iss
assert 'restartreplace' in iss
assert 'function ShouldLaunchAfterInstall(): Boolean;' in iss
assert "Pos('/NOLAUNCH=1', Uppercase(GetCmdTail)) = 0" in iss

# The only launcher reference allowed is upgrade cleanup for old installations.
assert 'Type: files; Name: "{app}\\GAMO_Launcher.exe"' in iss
assert 'Source: "..\\dist_launcher' not in iss
assert '#define MyLauncherExeName' not in iss
assert 'Filename: "{app}\\GAMO_Launcher.exe"' not in iss
assert 'Description: "Spustiť GAMO a.s. Launcher"' not in iss

print("Direct application installer regression checks OK")
