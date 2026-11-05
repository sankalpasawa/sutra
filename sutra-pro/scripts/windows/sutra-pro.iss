; Sutra Pro installer (Inno Setup 6). Built by .github/workflows/sutra-pro-release-windows.yml:
;
;   ISCC.exe /DAppVersion=0.1.0 /DSourceDir=<build>\Sutra Pro /DOutputDir=<release> /DIconFile=<assets>\icon\sutra-pro.ico scripts\windows\sutra-pro.iss
;
; PER-USER, NO ADMIN RIGHTS (D101): it installs to %LOCALAPPDATA%\Programs\Sutra Pro and writes only under the user's profile, so it
; needs no UAC prompt and works on a locked-down machine. The app's data (%USERPROFILE%\.sutra-pro) is never touched by the installer or
; by the uninstaller: removing the app does not remove a team's work. UNSIGNED (D102): SmartScreen says so on the first run.
; Upgrading over an older version first asks the running app to stop (its stop request file), then copies the new files over the old.
#ifndef AppVersion
  #error AppVersion is not defined: pass /DAppVersion=X.Y.Z
#endif
#ifndef SourceDir
  #error SourceDir is not defined: pass /DSourceDir=<the built Sutra Pro folder>
#endif
#ifndef OutputDir
  #define OutputDir "."
#endif
#ifndef IconFile
  #error IconFile is not defined: pass /DIconFile=<sutra-pro.ico>
#endif

#define AppName "Sutra Pro"

[Setup]
; a fixed id: it is how a newer installer recognises (and replaces) an older install
AppId={{EEB8082D-0A9F-46C1-86A9-C3B459572C1F}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Sutra
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename=Sutra-Pro-Setup-x64
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\icon\sutra-pro.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; the version resource wants four numbers: X.Y.Z.0
VersionInfoVersion={#AppVersion}.0
VersionInfoDescription={#AppName} setup
MinVersion=10.0

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\python\SutraPro.exe"; Parameters: "-I -X utf8 -m sutra_app.desktop"; WorkingDir: "{app}"; IconFilename: "{app}\icon\sutra-pro.ico"
Name: "{group}\Quit {#AppName}"; Filename: "{app}\python\python.exe"; Parameters: "-I -X utf8 -m sutra_app stop"; WorkingDir: "{app}"; IconFilename: "{app}\icon\sutra-pro.ico"
Name: "{group}\{#AppName} Doctor"; Filename: "{cmd}"; Parameters: "/k """"{app}\sutra-pro.cmd"" doctor"""; WorkingDir: "{app}"; IconFilename: "{app}\icon\sutra-pro.ico"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\python\SutraPro.exe"; Parameters: "-I -X utf8 -m sutra_app.desktop"; WorkingDir: "{app}"; IconFilename: "{app}\icon\sutra-pro.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\python\SutraPro.exe"; Parameters: "-I -X utf8 -m sutra_app.desktop"; WorkingDir: "{app}"; Description: "Start {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; the running app must let go of its files before they are removed; if nothing is running this does nothing
Filename: "{app}\python\python.exe"; Parameters: "-I -X utf8 -m sutra_app stop --wait 20"; WorkingDir: "{app}"; Flags: runhidden; RunOnceId: "StopSutraPro"

[Code]
// An upgrade: stop the app that is running from the old files, and give it a moment to end, before the new files go over them.
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  OldPython: String;
  ResultCode: Integer;
begin
  Result := '';
  OldPython := ExpandConstant('{app}\python\python.exe');
  if FileExists(OldPython) then
    Exec(OldPython, '-I -X utf8 -m sutra_app stop --wait 20', ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;
