; Inno Setup script for Campus Library Management System (LibCore)
; Override version from CLI/CI using:
;   ISCC.exe /DAppVersion=2.0 installer_scipt.iss

#ifndef AppVersion
  #define AppVersion "2.0"
#endif

#define AppName "Library"
#define AppExeName "Library.exe"
#define AppPublisher "Campus Library"
#define AppURL "https://github.com/krishnashashanth-sks/campus-library"

[Setup]
; Fixed AppId ensures upgrades replace prior installations cleanly in Windows Apps
AppId={{8E3C6C6D-4B2A-4D7E-9A1D-2B4C6E8F1A30}}
AppName={#AppName}
AppVerName={#AppName} v{#AppVersion}
AppVersion={#AppVersion}
VersionInfoVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}
CloseApplications=yes
RestartApplications=no
OutputDir=OutputInstaller
OutputBaseFilename=LibraryInstaller
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
SetupIconFile=assets\library_icon.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
; 1. Copy the entire PyInstaller dist folder (includes Python DLLs, modules, and library_version.txt)
Source: "dist\main\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; 2. Copy static assets
Source: "assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\assets\library_icon.ico"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\assets\library_icon.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
