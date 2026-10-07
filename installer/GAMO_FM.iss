#define MyAppName "GAMO a.s."
#define MyAppVersion "9.0.0.5"
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
PrivilegesRequired=lowest
CloseApplications=yes
RestartApplications=yes
UninstallDisplayIcon={app}\{#MyAppExeName}

[Files]
Source: "..\dist\GAMO_FM\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\GAMO a.s."; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\GAMO a.s."; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Vytvoriť ikonu na ploche"; GroupDescription: "Ďalšie možnosti:"; Flags: checkedonce

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Spustiť GAMO a.s."; Flags: nowait postinstall skipifsilent
