<#
.SYNOPSIS
  Build murdic for Windows: PyInstaller onedir (dist\murdic), GPU pack (dist\murdic-cuda)
  and the Inno Setup installer (dist\murdic-setup-<version>.exe).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File windows\build.ps1
  powershell -ExecutionPolicy Bypass -File windows\build.ps1 -SkipInstaller
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

Write-Host "== Whisper small model"
$ModelOut = "build\models\faster-whisper-small"
Invoke-Py -c @"
import shutil, sys
from pathlib import Path
from faster_whisper.utils import download_model
src = Path(download_model('small'))
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
for name in ('config.json', 'model.bin', 'tokenizer.json', 'vocabulary.txt', 'preprocessor_config.json'):
    if (src / name).exists() and not (out / name).exists():
        shutil.copyfile(src / name, out / name)
print('model', out, sum(f.stat().st_size for f in out.iterdir()) // 2**20, 'MB')
"@ $ModelOut

Write-Host "== PyInstaller"
Invoke-Py -m PyInstaller --noconfirm --clean --log-level WARN --distpath dist --workpath build\pyinstaller windows\murdic.spec

Write-Host "== GPU pack (cuBLAS)"
$Cuda = "dist\murdic-cuda"
if (Test-Path $Cuda) { Remove-Item -Recurse -Force $Cuda }
New-Item -ItemType Directory -Force $Cuda | Out-Null
$Cublas = Join-Path (Split-Path $Python -Parent) "..\Lib\site-packages\nvidia\cublas\bin"
foreach ($dll in "cublas64_12.dll", "cublasLt64_12.dll") { Copy-Item (Join-Path $Cublas $dll) $Cuda }
$License = Get-ChildItem (Join-Path (Split-Path $Python -Parent) "..\Lib\site-packages") -Directory -Filter "nvidia_cublas_cu12-*.dist-info" |
    ForEach-Object { Get-ChildItem $_.FullName -Filter "License*" } | Select-Object -First 1
if ($License) { Copy-Item $License.FullName "$Cuda\NVIDIA-cuBLAS-LICENSE.txt" }

Write-Host "== Smoke test of the frozen CLI"
if (-not (Test-Path build\sample.wav)) { Invoke-Py tests\sample.py build\sample.wav }
$Out = & dist\murdic\murdic-cli.exe --config-dir build\smoke-config --device cpu wav build\sample.wav --json
if ($LASTEXITCODE) { throw "frozen CLI failed" }
Write-Host $Out

if (-not $SkipInstaller) {
    Write-Host "== Inno Setup"
    $Iscc = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source
    if (-not $Iscc) { $Iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" }
    & $Iscc /Q "/DAppVersion=$Version" windows\installer.iss
    if ($LASTEXITCODE) { throw "ISCC failed" }
    Get-Item "dist\murdic-setup-$Version.exe" | Select-Object FullName, @{n = "MB"; e = { [math]::Round($_.Length / 1MB) } }
}
