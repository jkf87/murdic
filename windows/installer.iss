; Inno Setup 6 script for murdic (Windows). Built by windows\build.ps1:
;   ISCC.exe /DAppVersion=0.3.1 windows\installer.iss
; One per-user installer (no administrator rights) into %LOCALAPPDATA%\Programs\murdic.
; It contains the Python runtime; the Whisper model (and cuBLAS on NVIDIA PCs)
; is downloaded with progress on first run into %LOCALAPPDATA%\murdic.

#ifndef AppVersion
  #define AppVersion "0.3.1"
#endif

[Setup]
AppId={{6B8F2C1E-4D7A-4E59-9C3B-2A61D0E5F7A4}
AppName=머딕 (murdic)
AppVersion={#AppVersion}
AppVerName=머딕 (murdic) {#AppVersion}
AppPublisher=murdic contributors
AppPublisherURL=https://murdic.netlify.app/
DefaultDirName={localappdata}\Programs\murdic
DefaultGroupName=머딕 (murdic)
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir=..\dist
OutputBaseFilename=murdic-setup-{#AppVersion}
SetupIconFile=..\build\murdic.ico
UninstallDisplayIcon={app}\murdic.exe
UninstallDisplayName=머딕 (murdic)
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
LicenseFile=..\LICENSE
; Ask to close a running murdic before installing or uninstalling.
AppMutex=Local\murdic-single-instance
CloseApplications=yes

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "autostart"; Description: "Windows에 로그인하면 머딕 실행"
Name: "desktopicon"; Description: "바탕 화면에 바로 가기 만들기"; Flags: unchecked

[Files]
Source: "..\dist\murdic\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Files of older builds (0.1.0 previews bundled the model and GPU libraries here).
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\cuda"

[Icons]
Name: "{autoprograms}\머딕 (murdic)"; Filename: "{app}\murdic.exe"
Name: "{autoprograms}\머딕 설정·힌트 폴더"; Filename: "{userappdata}\murdic"
Name: "{autodesktop}\머딕 (murdic)"; Filename: "{app}\murdic.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "murdic"; \
  ValueData: """{app}\murdic.exe"""; Tasks: autostart; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueName: "murdic"; \
  Flags: deletevalue uninsdeletevalue; Tasks: not autostart

[Dirs]
Name: "{userappdata}\murdic"

[Run]
Filename: "{app}\murdic.exe"; Description: "머딕 실행 (처음에는 받아쓰기 모델을 내려받습니다)"; \
  Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Downloaded model and GPU files. Settings, hints and terms in %APPDATA%\murdic are kept.
Type: filesandordirs; Name: "{localappdata}\murdic"
