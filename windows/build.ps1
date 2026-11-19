<#
.SYNOPSIS
  Build murdic for Windows: PyInstaller onedir (dist\murdic) and one installer,
  dist\murdic-setup.exe (plus the versioned copy dist\murdic-setup-<version>.exe).

  The installer carries the Python runtime and all libraries. The Whisper model
  and, on NVIDIA PCs, cuBLAS are downloaded with progress on first run.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File windows\build.ps1
#>
param(
    [string]$Python = "",
    [switch]$SkipInstall,
    [switch]$SkipInstaller
)
$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo
[Environment]::CurrentDirectory = $Repo
$env:PYTHONIOENCODING = "utf-8"

if (-not $Python) {
    $Python = Join-Path $Repo ".venv\Scripts\python.exe"
    if (-not (Test-Path $Python)) {
        Write-Host "Creating .venv with Python 3.13"
        & py -3.13 -m venv .venv
        if ($LASTEXITCODE) { throw "Python 3.13 x64 is required (py -3.13)" }
    }
}
function Invoke-Py { & $Python @args; if ($LASTEXITCODE) { throw "python $args failed ($LASTEXITCODE)" } }

if (-not $SkipInstall) { Invoke-Py -m pip install --disable-pip-version-check -q -r windows\requirements-build.txt }
$Version = (& $Python -c "import sys; sys.path.insert(0, 'windows'); import murdic_win; print(murdic_win.__version__)").Trim()
New-Item -ItemType Directory -Force build, dist | Out-Null

Write-Host "== Icon"
Invoke-Py -c "from PIL import Image; Image.open('mac/assets/murdic.png').convert('RGBA').save('build/murdic.ico', sizes=[(16,16),(20,20),(24,24),(32,32),(40,40),(48,48),(64,64),(128,128),(256,256)])"

Write-Host "== PyInstaller"
Invoke-Py -m PyInstaller --noconfirm --clean --log-level WARN --distpath dist --workpath build\pyinstaller windows\murdic.spec

Write-Host "== Smoke test of the frozen CLI (model downloaded once into build\smoke-local)"
if (-not (Test-Path build\sample.wav)) { Invoke-Py tests\sample.py build\sample.wav }
$Saved = $env:LOCALAPPDATA
try {
    $env:LOCALAPPDATA = Join-Path $Repo "build\smoke-local"
    $Out = & dist\murdic\murdic-cli.exe --config-dir build\smoke-config --device cpu wav build\sample.wav --json
    if ($LASTEXITCODE) { throw "frozen CLI failed" }
    Write-Host $Out
} finally { $env:LOCALAPPDATA = $Saved }

if (-not $SkipInstaller) {
    Write-Host "== Inno Setup"
    $Iscc = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source
    if (-not $Iscc) { $Iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" }
    & $Iscc /Q "/DAppVersion=$Version" windows\installer.iss
    if ($LASTEXITCODE) { throw "ISCC failed" }
    Copy-Item "dist\murdic-setup-$Version.exe" "dist\murdic-setup.exe" -Force
    Get-Item "dist\murdic-setup.exe", "dist\murdic-setup-$Version.exe" |
        Select-Object Name, @{n = "MB"; e = { [math]::Round($_.Length / 1MB, 1) } },
                      @{n = "SHA256"; e = { (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower() } }
}
