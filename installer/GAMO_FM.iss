#define MyAppName "GAMO a.s."
#ifndef MyAppVersion
#define MyAppVersion "9.0.0.9"
#endif
#define MyAppPublisher "GAMO a.s."
#define MyAppExeName "GAMO_FM.exe"
#define MyLauncherExeName "GAMO_Launcher.exe"

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
PrivilegesRequired=lowest
CloseApplications=yes
CloseApplicationsFilter={#MyAppExeName};{#MyLauncherExeName}
RestartApplications=no
SetupLogging=yes
UninstallDisplayIcon={app}\{#MyLauncherExeName}
VersionInfoVersion={#MyAppVersion}
; Používateľské dáta sú zámerne mimo {app} v %LOCALAPPDATA%\GAMO_FM.
; Installer ich pri upgrade ani odinštalovaní nemaže ani neprepisuje.

[Files]
Source: "..\dist\GAMO_FM\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\dist_launcher\GAMO_Launcher.exe"; DestDir: "{app}"; Flags: ignoreversion restartreplace

[Icons]
Name: "{autoprograms}\GAMO a.s."; Filename: "{app}\{#MyLauncherExeName}"
Name: "{autodesktop}\GAMO a.s."; Filename: "{app}\{#MyLauncherExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Vytvoriť ikonu na ploche"; GroupDescription: "Ďalšie možnosti:"; Flags: checkedonce

[Run]
Filename: "{app}\{#MyLauncherExeName}"; Description: "Spustiť GAMO a.s. Launcher"; Flags: nowait postinstall skipifsilent


[Code]
procedure ForceCloseDesktop();
var
  ResultCode: Integer;
begin
  Exec(
    ExpandConstant('{sys}\taskkill.exe'),
    '/F /T /IM "{#MyAppExeName}"',
    '',
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  );
  Sleep(600);
end;

procedure ForceCloseLauncher();
var
  ResultCode: Integer;
begin
  { Old launcher versions may still own GAMO_Launcher.exe while Setup is
    preparing an update. Force-close only the launcher process; customer data
    lives in the cloud and no document is stored inside the launcher process. }
  Exec(
    ExpandConstant('{sys}\taskkill.exe'),
    '/F /T /IM "{#MyLauncherExeName}"',
    '',
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  );
  { Give Windows time to release the executable handle before [Files] starts. }
  Sleep(1800);
end;

function InitializeSetup(): Boolean;
begin
  ForceCloseDesktop();
  ForceCloseLauncher();
  Result := True;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  { Repeat immediately before file replacement as defense in depth. }
  ForceCloseDesktop();
  ForceCloseLauncher();
  Result := '';
end;
