[Setup]
; App Details
AppName=LibCore
AppVersion=1.0
DefaultDirName={autopf}\LibCore
DefaultGroupName=LibCore
PrivilegesRequired=lowest
OutputDir=OutputInstaller
OutputBaseFilename=LibCore
Compression=lzma
SolidCompression=yes
WizardStyle=modern
SetupIconFile=assets\library_icon.ico

[Files]
Source: "dist\main.exe"; DestDir: "{app}"; DestName: "LibCore.exe"; Flags: ignoreversion

; Copies your assets folder
Source: "assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion recursesubdirs createallsubdirs

[Tasks]
; This defines the task that the icon points to
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Icons]
Name: "{userdesktop}\LibCore"; Filename: "{app}\LibCore.exe"; IconFilename: "{app}\assets\library_icon.ico"; Tasks: desktopicon