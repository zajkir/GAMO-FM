#define MyAppName "GAMO a.s."
#ifndef MyAppVersion
#define MyAppVersion "9.0.0.21"
#endif
#define MyAppPublisher "GAMO a.s."
#define MyAppExeName "GAMO_FM.exe"
#define MyLauncherExeName "GAMO_Launcher.exe"

[Setup]
AppId={{A11D09C2-7E52-4FA7-9CF1-11F74231E35C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={code:GetDefaultInstallDir}
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
CloseApplicationsFilter={#MyAppExeName};{#MyLauncherExeName}
RestartApplications=no
SetupLogging=yes
UninstallDisplayIcon={app}\{#MyLauncherExeName}
VersionInfoVersion={#MyAppVersion}
; Používateľské dáta sú zámerne mimo {app} v %LOCALAPPDATA%\GAMO_FM.
; Installer ich pri upgrade ani odinštalovaní nemaže ani neprepisuje.

[InstallDelete]
; Remove obsolete legacy payload and recreate managed shortcuts on every repair/upgrade.
; A fresh GAMO_FM.exe compatibility alias is installed below so old pinned/manual
; shortcuts never fail with "The system cannot find the path specified."
Type: files; Name: "{app}\{#MyAppExeName}"
Type: filesandordirs; Name: "{app}\_internal"
Type: files; Name: "{app}\version.json"
Type: files; Name: "{app}\update_config.json"
Type: files; Name: "{autodesktop}\GAMO a.s..lnk"
Type: files; Name: "{autoprograms}\GAMO a.s..lnk"

[Files]
Source: "..\dist_launcher\GAMO_Launcher.exe"; DestDir: "{app}"; Flags: ignoreversion restartreplace
Source: "..\dist_launcher\GAMO_Launcher.exe"; DestDir: "{app}"; DestName: "{#MyAppExeName}"; Flags: ignoreversion restartreplace

[Icons]
Name: "{autoprograms}\GAMO a.s."; Filename: "{app}\{#MyLauncherExeName}"
Name: "{autodesktop}\GAMO a.s."; Filename: "{app}\{#MyLauncherExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Vytvoriť ikonu na ploche"; GroupDescription: "Ďalšie možnosti:"; Flags: checkedonce

[Run]
Filename: "{app}\{#MyLauncherExeName}"; Description: "Spustiť GAMO a.s. Launcher"; Flags: nowait postinstall; Check: ShouldLaunchAfterInstall


[Code]
function IsSafeLegacyLauncherDir(const Candidate: String): Boolean;
var
  UserRoot, NormalizedCandidate, NormalizedRoot: String;
begin
  Result := False;
  if Candidate = '' then
    Exit;

  UserRoot := ExpandConstant('{userprofile}');
  NormalizedCandidate := Lowercase(AddBackslash(Candidate));
  NormalizedRoot := Lowercase(AddBackslash(UserRoot));

  { Legacy portable launchers are only trusted when they live inside the
    current user's profile and the expected launcher file is present there.
    Normal installed copies continue to use Inno Setup's previous AppDir. }
  if Pos(NormalizedRoot, NormalizedCandidate) <> 1 then
    Exit;

  if not FileExists(AddBackslash(Candidate) + '{#MyLauncherExeName}') then
    Exit;

  Result := True;
end;

function GetDefaultInstallDir(Param: String): String;
var
  Lines: TArrayOfString;
  LogPath, Line, Candidate, Delimiter: String;
  I, P, P2: Integer;
begin
  Result := ExpandConstant('{autopf}\GAMO a.s.');
  LogPath := ExpandConstant('{localappdata}\GAMO_FM\logs\launcher.log');

  if not LoadStringsFromFile(LogPath, Lines) then
    Exit;

  Delimiter := ' ' + Chr(183) + ' frozen=';
  for I := GetArrayLength(Lines) - 1 downto 0 do
  begin
    Line := Lines[I];
    P := Pos('app_dir=', Line);
    if P > 0 then
    begin
      Candidate := Copy(Line, P + Length('app_dir='), MaxInt);
      P2 := Pos(Delimiter, Candidate);
      if P2 > 0 then
        Candidate := Copy(Candidate, 1, P2 - 1);
      Candidate := Trim(Candidate);

      if IsSafeLegacyLauncherDir(Candidate) then
      begin
        Log('Legacy GAMO launcher detected at: ' + Candidate);
        Result := Candidate;
        Exit;
      end;
    end;
  end;
end;

function ShouldLaunchAfterInstall(): Boolean;
begin
  { The detached updater owns relaunch during /NOLAUNCH=1 upgrades. Avoid
    starting a second launcher before SHA-256 post-install verification. }
  Result := Pos('/NOLAUNCH=1', Uppercase(GetCmdTail)) = 0;
end;

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
