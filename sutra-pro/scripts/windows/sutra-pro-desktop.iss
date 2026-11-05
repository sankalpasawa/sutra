; Sutra Pro installer (Inno Setup 6) for the Electron app (D108). Built by .github/workflows/sutra-pro-release-windows.yml:
;
;   ISCC.exe /DAppVersion=0.2.0 /DSourceDir=<build>\Sutra Pro /DOutputDir=<release> /DIconFile=<assets>\icon\sutra-pro.ico scripts\windows\sutra-pro-desktop.iss
;
; PER-USER, NO ADMIN RIGHTS (D101): it installs to %LOCALAPPDATA%\Programs\Sutra Pro and writes only under the user's profile, so it needs no UAC
; prompt and works on a locked-down machine. The app's data (%USERPROFILE%\.sutra-pro) is never touched by the installer or the uninstaller:
; removing the app does not remove a team's work. UNSIGNED (D102): SmartScreen says so on the first run.
;
; THE SAME AppId AS THE 0.1.x INSTALLER, so installing this over a 0.1.x app is an upgrade, not a second app. The old layout kept the interpreter
; in {app}\python beside the launchers; this one keeps it in {app}\resources\python and starts it from Sutra Pro.exe, so [InstallDelete] clears
; what the old layout left. Upgrading first asks a server that runs from the old files to stop, then copies the new files over.
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
#define AppExe "Sutra Pro.exe"

[Setup]
; a fixed id: it is how a newer installer recognises (and replaces) an older install, the 0.1.x one included
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
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; the version resource wants four numbers: X.Y.Z.0
VersionInfoVersion={#AppVersion}.0
VersionInfoDescription={#AppName} setup
MinVersion=10.0

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; Flags: unchecked

[InstallDelete]
; what the 0.1.x layout (D101) had that this one does not
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\icon"
Type: files; Name: "{app}\Sutra Pro.cmd"
Type: files; Name: "{app}\Quit Sutra Pro.cmd"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"
Name: "{group}\{#AppName} Doctor"; Filename: "{cmd}"; Parameters: "/k """"{app}\sutra-pro.cmd"" doctor"""; WorkingDir: "{app}"; IconFilename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Description: "Start {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; a server that outlives the window (one the command line started) holds its files: ask it to stop. If nothing is running this does nothing
Filename: "{app}\resources\python\python.exe"; Parameters: "-I -X utf8 -m sutra_app stop --wait 20"; WorkingDir: "{app}"; Flags: runhidden; RunOnceId: "StopSutraPro"

[Code]
// An upgrade: stop a server that runs from the old files (the 0.1.x layout's, or this one's) and give it a moment to end, before the new files go over them.
procedure StopServerOf(const Python: String);
var
  ResultCode: Integer;
begin
  if FileExists(Python) then
    Exec(Python, '-I -X utf8 -m sutra_app stop --wait 20', ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  StopServerOf(ExpandConstant('{app}\python\python.exe'));
  StopServerOf(ExpandConstant('{app}\resources\python\python.exe'));
end;
