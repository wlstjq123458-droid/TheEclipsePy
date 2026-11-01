; 동서대학교 좌석 및 기자재 관리 시스템 — Python(PySide6) 버전 설치파일
; 빌드: python build_exe.py --setup  (먼저 dist\SeatManagerApp-Python 폴더를 만든 뒤 이 스크립트를 컴파일한다)
; C# 버전과 AppId·설치 폴더가 달라서 두 버전을 함께 설치해도 서로 덮어쓰지 않는다.

#define MyAppName "동서대학교 좌석 및 기자재 관리 시스템 (Python)"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "SeatManagerApp"
#define MyAppExeName "SeatManagerApp-Python.exe"

[Setup]
AppId={{CCF2BAF2-C6C0-4A70-9026-EDFFADD4DEB2}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppSupportURL=https://github.com/
DefaultDirName={localappdata}\Programs\SeatManagerApp-Python
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\installer_output
OutputBaseFilename=SeatManagerApp-Python_Setup_v{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
SetupLogging=yes

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\SeatManagerApp-Python\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; 이전 버전에서 남은 라이브러리 파일이 섞이지 않게 _internal 폴더를 비우고 새로 깐다
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent