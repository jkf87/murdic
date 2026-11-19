; Inno Setup 6 script for murdic (Windows). Built by windows\build.ps1:
;   ISCC.exe /DAppVersion=0.1.0 windows\installer.iss
; Per-user install (no administrator rights) into %LOCALAPPDATA%\Programs\murdic.

#ifndef AppVersion
  #define AppVersion "0.1.0"
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
SolidCompression=no
WizardStyle=modern
LicenseFile=..\LICENSE
; Ask to close a running murdic before installing or uninstalling.
AppMutex=Local\murdic-single-instance
CloseApplications=yes

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Types]
Name: "full"; Description: "전체 (NVIDIA GPU 가속 포함)"
Name: "compact"; Description: "기본 (CPU 전사)"
Name: "custom"; Description: "사용자 지정"; Flags: iscustom

[Components]
Name: "main"; Description: "머딕 앱과 Whisper small 모델 (오프라인)"; Types: full compact custom; Flags: fixed
Name: "gpu"; Description: "NVIDIA GPU 가속 — cuBLAS 12 (약 735 MB, GPU가 없으면 쓰이지 않음)"; Types: full

[Tasks]
Name: "autostart"; Description: "Windows에 로그인하면 머딕 실행"
Name: "desktopicon"; Description: "바탕 화면에 바로 가기 만들기"; Flags: unchecked

[Files]
Source: "..\dist\murdic\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Components: main
Source: "..\dist\murdic-cuda\*"; DestDir: "{app}\cuda"; Flags: ignoreversion recursesubdirs; Components: gpu

[InstallDelete]
; Do not keep GPU libraries from an earlier install when the component is deselected.
Type: filesandordirs; Name: "{app}\cuda"; Components: not gpu

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
Filename: "{app}\murdic.exe"; Description: "머딕 실행"; Flags: nowait postinstall skipifsilent

[Code]
function HasNvidiaDriver(): Boolean;
begin
  { nvcuda.dll is installed by the NVIDIA display driver. }
  Result := FileExists(ExpandConstant('{sys}\nvcuda.dll'));
end;

procedure InitializeWizard();
begin
  if not HasNvidiaDriver() then
    WizardSelectComponents('!gpu');
end;
