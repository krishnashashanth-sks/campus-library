[Setup]
; App Details
AppName=Library
AppVersion=1.0
DefaultDirName={autopf}\Library
DefaultGroupName=Library
PrivilegesRequired=lowest
OutputDir=OutputInstaller
OutputBaseFilename=LibraryInstaller
Compression=lzma
SolidCompression=yes
WizardStyle=modern
SetupIconFile=assets\library_icon.ico

[Files]
; 1. COPY THE ENTIRE PYINSTALLER DIST FOLDER (This pulls all Python DLLs and modules)
Source: "dist\main\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; 2. COPY YOUR STATIC ASSETS AS WELL
Source: "assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion recursesubdirs createallsubdirs

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Icons]
Name: "{group}\Library"; Filename: "{app}\Library.exe"; IconFilename: "{app}\assets\library_icon.ico"
Name: "{userdesktop}\Library"; Filename: "{app}\Library.exe"; IconFilename: "{app}\assets\library_icon.ico"; Tasks: desktopicon
