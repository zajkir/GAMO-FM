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
assert 'Result := True;' in iss
assert 'PrivilegesRequired=admin' in iss
assert 'PrivilegesRequiredOverridesAllowed=dialog commandline' in iss
assert 'Check: ShouldLaunchAfterInstall' in iss
assert 'function PrepareToInstall(var NeedsRestart: Boolean): String;' in iss
assert 'ForceCloseLauncher();' in iss
assert 'Source: "..\\dist\\GAMO_FM\\*"' not in iss
assert 'Type: files; Name: "{app}\\{#MyAppExeName}"' in iss
assert 'DestName: "{#MyAppExeName}"' in iss
assert 'Source: "..\\dist_launcher\\GAMO_Launcher.exe"; DestDir: "{app}"; DestName: "{#MyAppExeName}"' in iss
assert 'Type: files; Name: "{autodesktop}\\GAMO a.s..lnk"' in iss
assert 'Type: files; Name: "{autoprograms}\\GAMO a.s..lnk"' in iss
assert 'Type: filesandordirs; Name: "{app}\\_internal"' in iss
assert 'Type: files; Name: "{app}\\version.json"' in iss
assert 'Type: files; Name: "{app}\\update_config.json"' in iss
assert "Pos('/NOLAUNCH=1', Uppercase(GetCmdTail)) = 0" in iss
assert f'#define MyAppVersion "{version}"' in iss

print("Installer fallback regression checks OK")
