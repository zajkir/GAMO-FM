#define MyAppName "GAMO a.s."
#ifndef MyAppVersion
#define MyAppVersion "9.0.0.6"
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
RestartApplications=yes
UninstallDisplayIcon={app}\{#MyLauncherExeName}
VersionInfoVersion={#MyAppVersion}
; Používateľské dáta sú zámerne mimo {app} v %LOCALAPPDATA%\GAMO_FM.
; Installer ich pri upgrade ani odinštalovaní nemaže ani neprepisuje.

[Files]
Source: "..\dist\GAMO_FM\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\dist_launcher\GAMO_Launcher.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\GAMO a.s."; Filename: "{app}\{#MyLauncherExeName}"
Name: "{autodesktop}\GAMO a.s."; Filename: "{app}\{#MyLauncherExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Vytvoriť ikonu na ploche"; GroupDescription: "Ďalšie možnosti:"; Flags: checkedonce

[Run]
Filename: "{app}\{#MyLauncherExeName}"; Description: "Spustiť GAMO a.s. Launcher"; Flags: nowait postinstall skipifsilent
