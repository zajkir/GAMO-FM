#define MyAppName "GAMO a.s."
#ifndef MyAppVersion
#define MyAppVersion "9.0.0.26"
#endif
#define MyAppPublisher "GAMO a.s."
#define MyAppExeName "GAMO_FM.exe"

[Setup]
AppId={{A11D09C2-7E52-4FA7-9CF1-11F74231E35C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\GAMO a.s.
DefaultGroupName=GAMO a.s.
OutputDir=..\dist_installer
OutputBaseFilename=GAMO_FM_Setup_{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog commandline
CloseApplications=yes
CloseApplicationsFilter={#MyAppExeName};GAMO_Launcher.exe
RestartApplications=no
SetupLogging=yes
UninstallDisplayIcon={app}\{#MyAppExeName}
VersionInfoVersion={#MyAppVersion}

; Customer data live in the cloud. Legacy local data, if present, stay in
; %LOCALAPPDATA%\GAMO_FM and are not removed by upgrades or uninstall.

[InstallDelete]
; Remove obsolete launcher-era files during upgrade.
Type: files; Name: "{app}\GAMO_Launcher.exe"
Type: filesandordirs; Name: "{app}\_internal"
Type: files; Name: "{app}\version.json"
Type: files; Name: "{app}\update_config.json"
Type: files; Name: "{autodesktop}\GAMO a.s..lnk"
Type: files; Name: "{autoprograms}\GAMO a.s..lnk"

[Files]
Source: "..\dist_app\GAMO_FM.exe"; DestDir: "{app}"; Flags: ignoreversion restartreplace

[Icons]
Name: "{autoprograms}\GAMO a.s."; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\GAMO a.s."; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Vytvoriť ikonu na ploche"; GroupDescription: "Ďalšie možnosti:"; Flags: checkedonce

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Spustiť GAMO a.s."; Flags: nowait postinstall; Check: ShouldLaunchAfterInstall

[Code]
procedure ForceCloseLegacyLauncher();
var
  ResultCode: Integer;
begin
  { Upgrade compatibility only. New releases do not install or use a launcher. }
  Exec(
    ExpandConstant('{sys}\taskkill.exe'),
    '/F /T /IM "GAMO_Launcher.exe"',
    '',
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  );
end;

function ShouldLaunchAfterInstall(): Boolean;
begin
  Result := Pos('/NOLAUNCH=1', Uppercase(GetCmdTail)) = 0;
end;

function InitializeSetup(): Boolean;
begin
  ForceCloseLegacyLauncher();
  Result := True;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  ForceCloseLegacyLauncher();
  Result := '';
end;
